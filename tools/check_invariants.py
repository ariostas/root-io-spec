#!/usr/bin/env python3
"""Check the `Invariants` sections of spec/01-container/ against every fixture.

Each layer document ends with a list of properties a conforming file satisfies
(see PLAN.md 2.8). This makes those lists executable, which serves two purposes:
it validates the reference files, and it validates the invariants themselves --
a property stated wrongly fails here against files ROOT actually wrote.

Each check names the document and section it comes from. Needs no third-party
packages; the one exception is noted where it arises.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import rootfile  # noqa: E402

KNOWN_KEY_VERSIONS = {1, 2, 3, 4, 1002, 1003, 1004}
BLOCK_MAGICS = {b"ZL": 8, b"XZ": 0, b"L4": None, b"ZS": 1, b"CS": 8}
KMAXZIPBUF = 0xFFFFFF
KSTART_BIG_FILE = 2000000000


def counted_string_len(buf: bytes, offset: int) -> int:
    n = buf[offset]
    return 1 + 4 + struct.unpack_from(">i", buf, offset + 1)[0] if n == 255 else 1 + n


class Checker:
    def __init__(self, path: Path):
        self.path = path
        self.failures: list[str] = []
        self.buf = path.read_bytes()
        self.header = self.records = None
        try:
            self.header = rootfile.read_header(self.buf)
            self.records = rootfile.read_records(self.buf, self.header)
        except rootfile.FormatError as exc:
            self.bad("structure", str(exc))

    def bad(self, where: str, message: str) -> None:
        self.failures.append(f"{self.path.name}: {where}: {message}")

    # -- FileHeader.md 10 ---------------------------------------------------
    def check_header(self) -> None:
        h, size = self.header, len(self.buf)
        if self.buf[:4] != b"root":
            self.bad("FileHeader 10.1", "magic is not 'root'")
        if not 0 <= h.begin <= h.end:
            self.bad("FileHeader 10.2", f"fBEGIN {h.begin}, fEND {h.end}")
        if not 10 <= h.nbytes_name <= 10000:
            self.bad("FileHeader 10.4", f"fNbytesName {h.nbytes_name} outside [10, 10000]")
        if h.end != size:
            self.bad("FileHeader 10.5", f"fEND {h.end} != file size {size}")

        if h.seek_free:
            if not h.begin < h.seek_free < h.end:
                self.bad("FileHeader 10.6", f"fSeekFree {h.seek_free} outside the record area")
            else:
                rec = self.at(h.seek_free)
                if rec is None or rec.nbytes != h.nbytes_free:
                    got = "no record" if rec is None else rec.nbytes
                    self.bad("FileHeader 10.6",
                             f"fNbytesFree {h.nbytes_free} != fNbytes at fSeekFree ({got})")
            segments = rootfile.read_free_segments(self.buf, h)
            if h.nfree != len(segments):
                self.bad("FileHeader 10.7",
                         f"nfree {h.nfree} != {len(segments)} entries in the free list")
            if h.nfree < 1:
                self.bad("FileHeader 10.7", "nfree is 0 for a closed file")

        if h.seek_info > h.begin:
            if not h.seek_info < h.end:
                self.bad("FileHeader 10.8", f"fSeekInfo {h.seek_info} beyond fEND")
            else:
                rec = self.at(h.seek_info)
                if rec is None or rec.nbytes != h.nbytes_info:
                    got = "no record" if rec is None else rec.nbytes
                    self.bad("FileHeader 10.8",
                             f"fNbytesInfo {h.nbytes_info} != fNbytes at fSeekInfo ({got})")

        if h.large != (h.end > KSTART_BIG_FILE):
            self.bad("FileHeader 10.9",
                     f"large flag {h.large} but fEND is {h.end}")
        if h.units != (8 if h.large else 4):
            self.bad("FileHeader 10.10", f"fUnits {h.units} disagrees with the version flag")

    def at(self, offset: int):
        return next((r for r in self.records if r.offset == offset and not r.free), None)

    # -- Record.md 8 --------------------------------------------------------
    def check_records(self) -> None:
        cursor = self.header.begin
        for rec in self.records:
            if rec.offset != cursor:
                self.bad("Record 8.8",
                         f"gap in the chain: expected a record at {cursor}, found one at {rec.offset}")
            cursor = rec.offset + abs(rec.nbytes)
            if rec.free:
                continue

            if rec.seek_key != rec.offset:
                self.bad("Record 8.1", f"fSeekKey {rec.seek_key} != offset {rec.offset}")
            if not 0 < rec.key_len <= rec.nbytes:
                self.bad("Record 8.2", f"fKeylen {rec.key_len}, fNbytes {rec.nbytes}")
            if rec.offset + rec.nbytes > self.header.end:
                self.bad("Record 8.4", f"record at {rec.offset} extends past fEND")
            if rec.obj_len < 0:
                self.bad("Record 8.5", f"fObjlen {rec.obj_len}")
            if rec.key_version not in KNOWN_KEY_VERSIONS:
                self.bad("Record 8.7", f"unexpected key fVersion {rec.key_version}")

            # 8.3: fKeylen equals the fixed part plus the three counted strings.
            fixed = 34 if rec.key_version > rootfile.LARGE_KEY_VERSION else 26
            o, total = rec.offset + fixed, fixed
            for _ in range(3):
                n = counted_string_len(self.buf, o)
                o, total = o + n, total + n
            if total != rec.key_len:
                self.bad("Record 8.3",
                         f"fKeylen {rec.key_len} != computed key length {total}")

            # 8.6: fSeekPdir is 0 only for the top-level record.
            if rec.seek_pdir == 0:
                if rec.offset != self.header.begin:
                    self.bad("Record 8.6", f"fSeekPdir 0 on a record at {rec.offset}")
            else:
                parent = self.at(rec.seek_pdir)
                if parent is None or rootfile.read_directory(self.buf, parent) is None:
                    self.bad("Record 8.6",
                             f"fSeekPdir {rec.seek_pdir} does not name a directory record")

        if cursor != self.header.end:
            self.bad("Record 8.8", f"chain ends at {cursor}, fEND is {self.header.end}")

    # -- Compression.md 9 ---------------------------------------------------
    def check_compression(self) -> None:
        for rec in self.records:
            if rec.free:
                continue
            payload, end = rec.payload_offset, rec.offset + rec.nbytes
            if rec.payload_nbytes == rec.obj_len:
                continue                                   # stored raw, 9.1

            produced, o, blocks = 0, payload, 0
            while o < end:
                if o + 9 > end:
                    self.bad("Compression 9.2", f"truncated block header at {o}")
                    break
                magic = self.buf[o:o+2]
                if magic not in BLOCK_MAGICS:
                    self.bad("Compression 9.4", f"unknown block magic {magic!r} at {o}")
                    break
                expect = BLOCK_MAGICS[magic]
                if expect is not None and self.buf[o+2] != expect:
                    self.bad("Compression 9.4",
                             f"{magic.decode()} block at {o} has method {self.buf[o+2]}, expected {expect}")
                comp = self.buf[o+3] | (self.buf[o+4] << 8) | (self.buf[o+5] << 16)
                unc  = self.buf[o+6] | (self.buf[o+7] << 8) | (self.buf[o+8] << 16)
                if o + 9 + comp > end:
                    self.bad("Compression 9.2",
                             f"block at {o} claims {comp} bytes, past the end of the payload")
                    break
                if unc > KMAXZIPBUF:
                    self.bad("Compression 9.5", f"block at {o} declares {unc} uncompressed bytes")
                if magic == b"L4" and comp < 8:
                    self.bad("Compression 9.6", f"LZ4 block at {o} has compressed size {comp} < 8")
                produced += unc
                blocks += 1
                o += 9 + comp
                if produced >= rec.obj_len:
                    break

            if produced != rec.obj_len:
                self.bad("Compression 9.3",
                         f"blocks decode to {produced} bytes, fObjlen is {rec.obj_len}")
            if o != end:
                self.bad("Compression 9.2",
                         f"block chain ends at {o}, payload ends at {end}")
            # 9.5: every block but the last carries exactly kMAXZIPBUF bytes.
            if blocks > 1 and rec.obj_len > KMAXZIPBUF:
                expected = 1 + (rec.obj_len - 1) // KMAXZIPBUF
                if blocks != expected:
                    self.bad("Compression 9.5",
                             f"{blocks} blocks for fObjlen {rec.obj_len}, expected {expected}")

    # -- free list vs. the chain -------------------------------------------
    def check_free_list(self) -> None:
        if not self.header.seek_free:
            return
        listed = {(f, l) for f, l in rootfile.read_free_segments(self.buf, self.header)}
        walked = {(r.offset, r.offset - r.nbytes - 1) for r in self.records if r.free}
        interior = {(f, l) for f, l in listed if l < self.header.end}
        if interior != walked:
            self.bad("FreeSegments",
                     f"interior free entries {sorted(interior)} do not match the spans "
                     f"found in the chain {sorted(walked)}")

    def run(self) -> list[str]:
        if self.records is None:
            # The chain could not be walked; report only what the header says.
            if self.header is not None:
                if self.header.end != len(self.buf):
                    self.bad("FileHeader 10.5",
                             f"fEND {self.header.end} != file size {len(self.buf)}")
            return self.failures
        self.check_header()
        self.check_records()
        self.check_compression()
        self.check_free_list()
        return self.failures


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or sorted((REPO / "data").rglob("*.root"))
    failures = []
    for path in paths:
        failures += Checker(path).run()
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    print(f"invariants checked on {len(paths)} file(s), {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
