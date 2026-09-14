"""Minimal pure-Python ROOT file structure reader.

Implements only what `spec/01-container/` specifies: the file header and the
record chain. It exists so that the fixture tooling does not depend on ROOT,
and so that the container specification has an independent implementation
exercising it. It deliberately does NOT decode object payloads.

No third-party dependencies.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"root"
LARGE_FILE_VERSION_FLAG = 1000000

#: A key whose fVersion exceeds this stores 8-byte offsets.
LARGE_KEY_VERSION = 1000
#: fPidOffset occupies the top 16 bits of a large key's fSeekPdir word.
PID_OFFSET_SHIFT = 48
PID_OFFSET_MASK = 0xFFFFFFFFFFFF


class FormatError(Exception):
    pass


@dataclass
class FileHeader:
    version: int
    begin: int
    end: int
    seek_free: int
    nbytes_free: int
    nfree: int
    nbytes_name: int
    units: int
    compress: int
    seek_info: int
    nbytes_info: int
    uuid_version: int
    uuid: bytes
    uuid_offset: int
    large: bool

    @property
    def root_version(self) -> tuple[int, int, int]:
        """(major, minor, patch) of the ROOT release that wrote the file."""
        v = self.version % LARGE_FILE_VERSION_FLAG
        return v // 10000, (v // 100) % 100, v % 100

    @property
    def compression_algorithm(self) -> int:
        return self.compress // 100

    @property
    def compression_level(self) -> int:
        return self.compress % 100


@dataclass
class Record:
    """One record in the chain starting at `FileHeader.begin`."""

    offset: int
    nbytes: int          # as stored: negative marks a free/unused segment
    key_version: int | None = None
    obj_len: int | None = None
    pid_offset: int = 0
    keep: bool = False
    datime: int | None = None
    datime_offset: int | None = None
    key_len: int | None = None
    cycle: int | None = None
    seek_key: int | None = None
    seek_pdir: int | None = None
    class_name: str | None = None
    name: str | None = None
    title: str | None = None

    @property
    def free(self) -> bool:
        return self.nbytes < 0

    @property
    def payload_offset(self) -> int:
        return self.offset + self.key_len

    @property
    def payload_nbytes(self) -> int:
        return self.nbytes - self.key_len

    @property
    def compressed(self) -> bool:
        return self.payload_nbytes != self.obj_len


def _u8(b, o):
    return b[o]


def _u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def _i16(b, o):
    return struct.unpack_from(">h", b, o)[0]


def _i32(b, o):
    return struct.unpack_from(">i", b, o)[0]


def _u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def _i64(b, o):
    return struct.unpack_from(">q", b, o)[0]


def _counted_string(b, o):
    """The `TKey` string encoding: 1 length byte, then that many bytes."""
    n = b[o]
    return b[o + 1 : o + 1 + n].decode("latin-1"), o + 1 + n


def read_header(buf: bytes) -> FileHeader:
    if buf[:4] != MAGIC:
        raise FormatError(f"not a ROOT file: magic is {buf[:4]!r}, expected {MAGIC!r}")
    version = _i32(buf, 4)
    # ROOT's own test is `fVersion < 1000000` for the small-file layout
    # (root/io/io/src/TFile.cxx:738), so the large-file predicate is >=.
    large = version >= LARGE_FILE_VERSION_FLAG
    # fBEGIN is written as a 32-bit int even in the large-file layout
    # (root/io/io/src/TFile.cxx:2681), so it never widens.
    begin = _i32(buf, 8)
    o = 12
    if large:
        end, seek_free = _i64(buf, o), _i64(buf, o + 8)
        o += 16
    else:
        end, seek_free = _i32(buf, o), _i32(buf, o + 4)
        o += 8
    nbytes_free = _i32(buf, o)
    nfree = _i32(buf, o + 4)
    nbytes_name = _i32(buf, o + 8)
    units = _u8(buf, o + 12)
    compress = _i32(buf, o + 13)
    o += 17
    if large:
        seek_info, nbytes_info = _i64(buf, o), _i32(buf, o + 8)
        o += 12
    else:
        seek_info, nbytes_info = _i32(buf, o), _i32(buf, o + 4)
        o += 8
    uuid_version = _i16(buf, o)
    return FileHeader(
        version=version, begin=begin, end=end, seek_free=seek_free,
        nbytes_free=nbytes_free, nfree=nfree, nbytes_name=nbytes_name,
        units=units, compress=compress, seek_info=seek_info,
        nbytes_info=nbytes_info, uuid_version=uuid_version,
        uuid=buf[o + 2 : o + 18], uuid_offset=o + 2, large=large,
    )


def read_records(buf: bytes, header: FileHeader) -> list[Record]:
    """Walk the record chain from `header.begin` to `header.end`.

    Raises FormatError, never a struct error, when the chain runs past the end of
    the buffer -- which is what a file truncated after `fEND` was written looks
    like.
    """
    if header.end > len(buf):
        raise FormatError(
            f"fEND is {header.end} but the file is {len(buf)} bytes: truncated")
    records, off = [], header.begin
    while off < header.end:
        if off + 4 > len(buf):
            raise FormatError(f"record header at {off} runs past the end of the file")
        nbytes = _i32(buf, off)
        if nbytes == 0:
            raise FormatError(f"zero-length record at {off}")
        if nbytes < 0:
            records.append(Record(offset=off, nbytes=nbytes))
            off += -nbytes
            continue
        rec = Record(offset=off, nbytes=nbytes)
        rec.key_version = _i16(buf, off + 4)
        rec.obj_len = _i32(buf, off + 6)
        rec.datime = _u32(buf, off + 10)
        rec.datime_offset = off + 10
        rec.key_len = _i16(buf, off + 14)
        # fCycle is negative when the key is marked "keep"; the cycle is its
        # magnitude (root/io/io/src/TKey.cxx:623-626, :731-734).
        raw_cycle = _i16(buf, off + 16)
        rec.keep = raw_cycle < 0
        rec.cycle = abs(raw_cycle)
        p = off + 18
        if rec.key_version > LARGE_KEY_VERSION:  # large key: 8-byte seeks
            rec.seek_key = _i64(buf, p)
            # In a large key the top 16 bits of the fSeekPdir word hold
            # fPidOffset, not address bits (root/io/io/src/TKey.cxx:670, :1281).
            pdir = _i64(buf, p + 8)
            rec.pid_offset = (pdir >> PID_OFFSET_SHIFT) & 0xFFFF
            rec.seek_pdir = pdir & PID_OFFSET_MASK
            p += 16
        else:
            rec.seek_key, rec.seek_pdir = _i32(buf, p), _i32(buf, p + 4)
            p += 8
        rec.class_name, p = _counted_string(buf, p)
        rec.name, p = _counted_string(buf, p)
        rec.title, p = _counted_string(buf, p)
        records.append(rec)
        off += nbytes
    return records


def read_free_segments(buf: bytes, header: FileHeader) -> list[tuple[int, int]]:
    """The `TFree` list from the FreeSegments record: (first, last) byte ranges."""
    if not header.seek_free:
        return []
    rec = next(r for r in read_records(buf, header) if r.offset == header.seek_free)
    o, end, out = rec.payload_offset, rec.offset + rec.nbytes, []
    while o < end:
        version = _i16(buf, o)
        o += 2
        if version > 1000:
            first, last = _i64(buf, o), _i64(buf, o + 8)
            o += 16
        else:
            first, last = _i32(buf, o), _i32(buf, o + 4)
            o += 8
        out.append((first, last))
    return out


def load(path) -> tuple[bytes, FileHeader, list[Record]]:
    with open(path, "rb") as fh:
        buf = fh.read()
    header = read_header(buf)
    return buf, header, read_records(buf, header)


@dataclass
class Directory:
    """The TDirectoryFile structure inside a directory record's payload."""

    version: int
    datime_c: int
    datime_m: int
    datime_offset: int
    nbytes_keys: int
    nbytes_name: int
    seek_dir: int
    seek_parent: int
    seek_keys: int
    uuid: bytes
    uuid_offset: int
    fields_offset: int


def read_directory(buf: bytes, rec: Record) -> Directory | None:
    """Parse a record's payload as a TDirectoryFile, or return None.

    The root directory's record repeats the name and title before the directory
    fields, while a subdirectory's record does not. Rather than special-case the
    two, both candidate offsets are tried and accepted only if `fSeekDir` equals
    the record's own offset -- a self-check ROOT itself relies on.

    Equivalently: the fields always begin at `rec.offset + fNbytesName`, which is
    why `fNbytesName` differs between the root directory and a subdirectory.
    """
    if rec.free or rec.class_name not in ("TFile", "TDirectory"):
        return None
    candidates = [rec.payload_offset]
    o = rec.payload_offset
    for _ in range(2):                      # skip the duplicated name and title
        o += 1 + buf[o]
    candidates.append(o)

    for start in candidates:
        try:
            version = _i16(buf, start)
            p = start + 2
            datime_offset = p
            datime_c, datime_m = _u32(buf, p), _u32(buf, p + 4)
            p += 8
            nbytes_keys, nbytes_name = _i32(buf, p), _i32(buf, p + 4)
            p += 8
            if version > 1000:              # large-file directory
                seek_dir, seek_parent, seek_keys = (
                    _i64(buf, p), _i64(buf, p + 8), _i64(buf, p + 16))
                p += 24
            else:
                seek_dir, seek_parent, seek_keys = (
                    _i32(buf, p), _i32(buf, p + 4), _i32(buf, p + 8))
                p += 12
        except Exception:
            continue
        if seek_dir != rec.offset:
            continue
        uuid, uuid_offset = b"", p
        if version > 1:                     # a UUID is present from version 2
            uuid_offset = p + 2             # after the TUUID version word
            uuid = buf[uuid_offset : uuid_offset + 16]
        return Directory(
            version=version, datime_c=datime_c, datime_m=datime_m,
            datime_offset=datime_offset, nbytes_keys=nbytes_keys,
            nbytes_name=nbytes_name, seek_dir=seek_dir, seek_parent=seek_parent,
            seek_keys=seek_keys, uuid=uuid, uuid_offset=uuid_offset,
            fields_offset=start,
        )
    return None
