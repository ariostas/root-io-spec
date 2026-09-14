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
    """Walk the record chain from `header.begin` to `header.end`."""
    records, off = [], header.begin
    while off < header.end:
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
        rec.cycle = _i16(buf, off + 16)
        p = off + 18
        if rec.key_version > 1000:      # large-file key: 8-byte seeks
            rec.seek_key, rec.seek_pdir = _i64(buf, p), _i64(buf, p + 8)
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
