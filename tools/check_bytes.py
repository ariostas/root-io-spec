#!/usr/bin/env python3
"""Verify the byte-level assertions in a fixture's `case.toml`.

Each `[[bytes]]` entry names an absolute file offset, a type, and the expected
value. The byte tables in `spec/` and these assertions are written from the same
reading, so a mistake in either shows up as a failure. It needs no ROOT
installation, so a third party can use the fixtures directly.

Each `[[records]]` entry is a record of the file's chain, in order: `offset`,
`nbytes` (negative for a free segment, as the file stores it), and optionally
`class`, `name`, `cycle` and `seek_pdir` of its key; `role` is prose. The chain
is walked here with the standard library alone (spec/01-container/Record.md 1).
A table may list only the records it is about; each one listed must be in the
chain at its offset. Until 2026-09-24 nothing read these tables
for gen/cases, so 504 of them were unverified prose (PLAN-review.md V36).
"""

from __future__ import annotations

import struct
import sys
import tomllib
from pathlib import Path

# Big-endian by default: the TFile container and the TBuffer object layers are
# big-endian regardless of host byte order (spec/00-conventions.md 3).
#
# The `le` suffix is for RNTuple, whose envelopes and pages are little-endian.
# Only its anchor, a TKey payload like any other, is big-endian, so one fixture
# needs both and must say which at every offset. See spec/05-rntuple/NOTES.md 3.
FORMATS = {
    "i8": ">b", "u8": ">B", "i16": ">h", "u16": ">H",
    "i32": ">i", "u32": ">I", "i64": ">q", "u64": ">Q",
    "f32": ">f", "f64": ">d",
    "i16le": "<h", "u16le": "<H",
    "i32le": "<i", "u32le": "<I", "i64le": "<q", "u64le": "<Q",
    "f32le": "<f", "f64le": "<d",
}


def counted_string(buf: bytes, off: int) -> tuple[str, int]:
    """The counted string at `off` and the offset after it (conventions 5.1)."""
    n = buf[off]
    off += 1
    if n == 255:
        n = struct.unpack_from(">i", buf, off)[0]
        off += 4
    return buf[off:off + n].decode("latin-1"), off + n


def walk_records(buf: bytes) -> list[dict]:
    """The record chain from fBEGIN to fEND, as `[[records]]` tables spell it.

    Record.md 1 and 2: a negative fNbytes is a free segment of that many bytes;
    a key whose fVersion is above 1000 has 8-byte seeks.
    """
    version, begin = struct.unpack_from(">ii", buf, 4)
    if version >= 1000000:
        end = struct.unpack_from(">q", buf, 12)[0]
    else:
        end = struct.unpack_from(">i", buf, 12)[0]
    out, pos = [], begin
    while pos < end:
        nbytes = struct.unpack_from(">i", buf, pos)[0]
        if nbytes < 0:
            out.append({"offset": pos, "nbytes": nbytes})
            pos -= nbytes
            continue
        if nbytes == 0:
            raise ValueError(f"a zero fNbytes at {pos}")
        key_version = struct.unpack_from(">h", buf, pos + 4)[0]
        cycle = struct.unpack_from(">h", buf, pos + 16)[0]
        if key_version > 1000:
            seek_pdir = struct.unpack_from(">q", buf, pos + 26)[0]
            at = pos + 34
        else:
            seek_pdir = struct.unpack_from(">i", buf, pos + 22)[0]
            at = pos + 26
        class_name, at = counted_string(buf, at)
        name, _ = counted_string(buf, at)
        out.append({"offset": pos, "nbytes": nbytes, "class": class_name,
                    "name": name, "cycle": cycle, "seek_pdir": seek_pdir})
        pos += nbytes
    return out


def check_records(buf: bytes, expected: list[dict], label: str) -> list[str]:
    try:
        records = walk_records(buf)
    except (ValueError, struct.error, IndexError) as exc:
        return [f"{label}: the record chain does not walk: {exc}"]
    failures = []
    at = {r["offset"]: r for r in records}
    for want in expected:
        got = at.get(want["offset"])
        if got is None:
            failures.append(f"{label}: no record starts at {want['offset']}")
            continue
        for field, value in want.items():
            if field == "role":
                continue
            if field not in ("offset", "nbytes", "class", "name", "cycle",
                             "seek_pdir"):
                failures.append(f"{label}: record at {want['offset']}: "
                                f"unknown field {field!r}")
            elif got.get(field) != value:
                failures.append(f"{label}: record at {got['offset']}: {field} "
                                f"{got.get(field)!r}, case.toml says {value!r}")
    return failures


def check(buf: bytes, assertions: list[dict], label: str) -> list[str]:
    failures = []
    for a in assertions:
        off, want, name = a["offset"], a["value"], a.get("name", "")
        kind = a["type"]
        where = f"{label}: offset {off} ({name})" if name else f"{label}: offset {off}"
        if kind == "bytes":
            want = want.encode("latin-1") if isinstance(want, str) else bytes(want)
            got = buf[off : off + len(want)]
        elif kind == "string":
            # counted string: one length byte, or 255 and an i32 length
            got, want = counted_string(buf, off)[0], str(want)
        elif kind in FORMATS:
            got = struct.unpack_from(FORMATS[kind], buf, off)[0]
        else:
            failures.append(f"{where}: unknown type {kind!r}")
            continue
        if got != want:
            failures.append(f"{where}: expected {want!r}, got {got!r}")
    return failures


def main(case_dirs: list[str]) -> int:
    repo = Path(__file__).resolve().parent.parent
    failures, checked, records = [], 0, 0
    for case_dir in case_dirs:
        case = tomllib.loads((Path(case_dir) / "case.toml").read_text())
        path = repo / case["file"]
        if not path.exists():
            failures.append(f"{case['id']}: {case['file']} missing; run tools/generate.py")
            continue
        buf = path.read_bytes()
        # `size` is optional: a case whose file length differs between platforms
        # cannot assert one. So far only serialization/pairs omits it; its
        # case.toml gives the reason.
        if "size" in case and len(buf) != case["size"]:
            failures.append(f"{case['id']}: size {len(buf)}, expected {case['size']}")
        assertions = case.get("bytes", [])
        failures += check(buf, assertions, case["id"])
        checked += len(assertions)
        if case.get("records"):
            failures += check_records(buf, case["records"], case["id"])
            records += len(case["records"])
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    print(f"{checked} byte assertions and {records} records checked across "
          f"{len(case_dirs)} case(s), {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    dirs = sys.argv[1:] or [str(p.parent) for p in
                            sorted((Path(__file__).resolve().parent.parent / "gen/cases")
                                   .rglob("case.toml"))]
    sys.exit(main(dirs))
