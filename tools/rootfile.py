"""Minimal pure-Python ROOT file structure reader.

Implements only what `spec/01-container/` specifies: the file header and the
record chain. It keeps the fixture tooling independent of ROOT and gives the
container specification an independent implementation. It deliberately does NOT decode object payloads.

No third-party dependencies.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

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
    #: For a key read as an image inside a key list: the bytes the image itself
    #: occupies there, which is NOT always its fKeylen. A directory key written
    #: before ROOT 5.34 spells its class name `TDirectoryFile` in the list and
    #: `TDirectory` in the record, four bytes apart, while fKeylen describes the
    #: record. Directory.md 6.5: a reader advances by this, never by fKeylen.
    image_len: int | None = None

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
        # Compression.md 1.1: the test is `>`, not `!=`. A payload LONGER than
        # fObjlen is stored raw with trailing slack, which is what an RNTuple
        # RBlob looks like.
        return self.obj_len > self.payload_nbytes


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


def _u64(b, o):
    return struct.unpack_from(">Q", b, o)[0]


def _i64(b, o):
    return struct.unpack_from(">q", b, o)[0]


def _counted_string(b, o):
    """A counted string: Conventions 5.1.

    One length byte, then that many bytes, except that a length byte of 255
    escapes to a 4-byte big-endian length. The escape triggers above 254, so a
    leading 0xFF never means "255 characters".
    """
    n = b[o]
    o += 1
    if n == 255:
        n = _i32(b, o)
        o += 4
    return b[o:o + n].decode("latin-1"), o + n


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
    the buffer, as it does in a file truncated after `fEND` was written.
    """
    if header.end > len(buf):
        raise FormatError(
            f"fEND is {header.end} but the file is {len(buf)} bytes: truncated")
    # A gap whose marker was never written is still in the free list, and a
    # reader that finds a key where the list says there is a gap SHOULD trust the
    # list (FreeSegments.md 4.2). RNTuple's TFile writer left such gaps before
    # ROOT 6.36 (root commit d328b598b32), so the list is read first, directly
    # from fSeekFree rather than through the chain it is used to repair.
    unmarked = {first: last for first, last in _free_list_at(buf, header)
                if last < header.end}
    records, off = [], header.begin
    while off < header.end:
        if off + 4 > len(buf):
            raise FormatError(f"record header at {off} runs past the end of the file")
        nbytes = _i32(buf, off)
        if nbytes >= 0 and off in unmarked:
            nbytes = -(unmarked[off] - off + 1)
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


def parse_free_entries(chunk: bytes, key_len: int,
                       payload_nbytes: int) -> list[tuple[int, int, int]]:
    """The TFree entries with their version words: (version, fFirst, fLast).

    `chunk` holds the record from its key onwards. It need not be the whole file,
    so a caller can read the list of a multi-gigabyte file with one HTTP range
    request. Each entry sizes itself from its own version word, so the
    10-byte and 18-byte forms may be interleaved (FreeSegments.md section 2.1,
    LargeFiles.md section 4).
    """
    o, end, out = key_len, key_len + payload_nbytes, []
    while o + 10 <= end:
        version = _i16(chunk, o)
        o += 2
        if version > 1000:
            if o + 16 > end:
                break
            first, last = _i64(chunk, o), _i64(chunk, o + 8)
            o += 16
        else:
            first, last = _i32(chunk, o), _i32(chunk, o + 4)
            o += 8
        out.append((version, first, last))
    return out


def parse_free_list(chunk: bytes, key_len: int,
                    payload_nbytes: int) -> list[tuple[int, int]]:
    """The TFree entries of a free-segment record. FreeSegments.md section 2."""
    return [(first, last)
            for _, first, last in parse_free_entries(chunk, key_len,
                                                     payload_nbytes)]


def _free_list_at(buf: bytes, header: FileHeader) -> list[tuple[int, int]]:
    """The free list read from the key at fSeekFree, or [] if there is none.

    Not through read_records, which consults this: the header says where the
    record is, and its key says how long its own header is.
    """
    off = header.seek_free
    if not off or off + 18 > len(buf):
        return []
    nbytes, key_len = _i32(buf, off), _i16(buf, off + 14)
    if nbytes <= 0 or key_len <= 0 or key_len > nbytes or off + nbytes > len(buf):
        return []
    return parse_free_list(buf[off:off + nbytes], key_len, nbytes - key_len)


def read_free_segments(buf: bytes, header: FileHeader) -> list[tuple[int, int]]:
    """The `TFree` list from the FreeSegments record: (first, last) byte ranges."""
    return _free_list_at(buf, header)


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
    the record's own offset, a self-check ROOT itself relies on.

    Equivalently: the fields always begin at `rec.offset + fNbytesName`, which is
    why `fNbytesName` differs between the root directory and a subdirectory.
    """
    if rec.free:
        return None
    # Not gated on the class name: the record that holds a file's root directory
    # has the name of whatever TFile subclass wrote it (CMS files say
    # TStorageFactoryFile). The fSeekDir self-check below identifies a directory
    # record. spec/01-container/Directory.md section 1.
    if not rec.class_name:
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
        # The class version and the offset width are independent: a record at
        # version 1001 is class version 1 (no UUID at all) in the wide layout.
        # The width test above is on `version > 1000` and this one on
        # `version % 1000`, which also handles version 2: it stores the 16 bytes
        # with no TUUID version word in front of them.
        # Directory.md 7; TDirectoryFile.cxx:1792-1797.
        class_version = version % 1000
        if class_version == 2:              # raw 16 bytes, no version word
            uuid = buf[p : p + 16]
        elif class_version > 2:
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


def read_key_list(buf: bytes, directory: Directory) -> list[Record]:
    """Parse a directory's key list: a count, then that many key images.

    The list is located only via `Directory.seek_keys`; its own record's key is
    indistinguishable from the directory record's. `fSeekKeys == 0` means the
    directory was never saved and has no list, which is not an error.

    The count is authoritative. The record may be allocated up to 8 bytes larger
    than the entries occupy, and that slack is uninitialized, so a parse driven by
    the payload length rather than the count can yield a bogus trailing entry.
    """
    if not directory.seek_keys:
        return []
    header = read_header(buf)
    record = next((r for r in read_records(buf, header)
                   if r.offset == directory.seek_keys and not r.free), None)
    if record is None:
        raise FormatError(f"no record at fSeekKeys {directory.seek_keys}")

    o = record.payload_offset
    count = _i32(buf, o)
    o += 4
    entries = []
    for _ in range(count):
        entry, o = _read_key_at(buf, o)
        entries.append(entry)
    return entries


def _read_key_at(buf: bytes, off: int) -> tuple[Record, int]:
    """Read one key image, returning it and the offset just past it."""
    rec = Record(offset=off, nbytes=_i32(buf, off))
    rec.key_version = _i16(buf, off + 4)
    rec.obj_len = _i32(buf, off + 6)
    rec.datime = _u32(buf, off + 10)
    rec.datime_offset = off + 10
    rec.key_len = _i16(buf, off + 14)
    raw_cycle = _i16(buf, off + 16)
    rec.keep = raw_cycle < 0
    rec.cycle = abs(raw_cycle)
    p = off + 18
    if rec.key_version > LARGE_KEY_VERSION:
        rec.seek_key = _i64(buf, p)
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
    rec.image_len = p - off
    return rec, p


# ---------------------------------------------------------------------------
# The buffer framing layer, spec/02-serialization/Buffer.md.
#
# This is deliberately an independent implementation of that document, written
# from the document rather than from ROOT's code, so that a disagreement between
# the two can be detected.
#
# Buffer positions are measured from the start of the *record*, key included, so
# a position p in the file is at buffer offset p - record.offset. See Buffer.md
# section 1.
# ---------------------------------------------------------------------------

BYTE_COUNT_MASK = 0x40000000
MAX_MAP_COUNT = 0x3FFFFFFE
MAX_VERSION = 0x3FFF
NEW_CLASS_TAG = 0xFFFFFFFF
CLASS_MASK = 0x80000000
MAP_OFFSET = 2
# Map position 1 is the record's own top-level object, not a buffer offset.
SELF_POSITION = 1
STREAMED_MEMBER_WISE = 0x4000

# TObject::kIsReferenced, which adds a trailing u16 to the TObject base.
IS_REFERENCED = 0x10


@dataclass
class Frame:
    """A `byteCount? version` object header (Buffer.md section 3)."""

    offset: int                  # position of the byte count, else of the version
    byte_count: int | None
    version: int
    member_wise: bool
    body: int                    # first content byte
    end: int | None              # one past the object, when a byte count is present


def read_frame(buf: bytes, offset: int) -> Frame:
    """Read a version word and the byte count that may precede it."""
    word = _u32(buf, offset)
    if word & BYTE_COUNT_MASK:
        byte_count = word & ~BYTE_COUNT_MASK
        version_at = offset + 4
        end = offset + 4 + byte_count
    else:
        byte_count = None
        version_at = offset
        end = None
    raw = _i16(buf, version_at)
    return Frame(
        offset=offset,
        byte_count=byte_count,
        version=raw & ~STREAMED_MEMBER_WISE,
        member_wise=bool(raw & STREAMED_MEMBER_WISE),
        body=version_at + 2,
        end=end,
    )


def is_compressed(rec: Record) -> bool:
    """Compression.md 1. The test is `>`: see 1.1 for why not `!=`."""
    return rec.obj_len > rec.nbytes - rec.key_len


def payload_range(rec: Record) -> tuple[int, int]:
    """Where `rec`'s object data lies in the buffer `object_data` returns.

    For a raw record that buffer is the file itself; for a compressed one it is
    the file with the payload decompressed in place, so the range ends at
    `start + obj_len` and not at the record's end. Index the file with it only
    for a record known to be raw. Every caller was audited against that on
    2026-09-22 (PLAN-corpus.md C7): all of them comply, and the one that got the
    *start* wrong (Compression 9.7, adding the record's offset twice) is fixed.
    """
    start = rec.offset + rec.key_len
    return start, start + rec.obj_len


@dataclass
class TObjectBase:
    """A TObject base: Buffer.md section 7, References.md section 1."""

    version: int
    unique_id: int
    bits: int
    pidf: int | None     # present iff fBits & kIsReferenced
    end: int

    @property
    def referenced(self) -> bool:
        return bool(self.bits & IS_REFERENCED)

    @property
    def serial(self) -> int:
        """The reference serial: the low 24 bits (References.md section 5)."""
        return self.unique_id & 0x00FFFFFF


def read_tobject(buf: bytes, offset: int) -> TObjectBase:
    """A TObject base. Ten bytes, or twelve when kIsReferenced is set."""
    version = _i16(buf, offset)
    unique_id = _u32(buf, offset + 2)
    bits = _u32(buf, offset + 6)
    if bits & IS_REFERENCED:
        return TObjectBase(version, unique_id, bits, _u16(buf, offset + 10),
                           offset + 12)
    return TObjectBase(version, unique_id, bits, None, offset + 10)


def skip_tobject(buf: bytes, offset: int) -> int:
    """Skip a TObject base: version, fUniqueID, fBits, and a pidf if referenced.

    Buffer.md section 7. There is no byte count.
    """
    return read_tobject(buf, offset).end


# ---------------------------------------------------------------------------
# Decompression (spec/01-container/Compression.md).
#
# Written from that document: the 9-byte header with its two 24-bit little-endian
# sizes, the magics, LZ4's 8-byte checksum, and the block chain of section 7.
#
# The codecs themselves are not reimplemented. zlib and lzma are in the standard
# library everywhere; zstd only from Python 3.14, and lz4 needs a package. A
# record whose algorithm is unavailable raises MissingCodec, which callers report
# as "not checked" rather than as a failure, so the invariant checks do not
# depend on third-party packages and the fixtures stay checkable with stdlib
# Python alone.
# ---------------------------------------------------------------------------

KMAXZIPBUF = 0xFFFFFF          # root/core/zip/inc/RZip.h, the 24-bit size cap
BLOCK_HEADER = 9
LZ4_CHECKSUM = 8


class MissingCodec(FormatError):
    """The block's algorithm is not available in this Python."""


def _zlib(payload: bytes, nout: int) -> bytes:
    import zlib
    return zlib.decompress(payload)


def _lzma(payload: bytes, nout: int) -> bytes:
    import lzma
    return lzma.decompress(payload)


def _zstd(payload: bytes, nout: int) -> bytes:
    try:
        from compression import zstd            # Python 3.14+
    except ImportError:
        try:
            import zstandard
        except ImportError:
            raise MissingCodec("zstd needs Python 3.14 or the zstandard package")
        return zstandard.ZstdDecompressor().decompress(payload, max_output_size=nout)
    return zstd.decompress(payload)


def _lz4(payload: bytes, nout: int) -> bytes:
    try:
        import lz4.block
    except ImportError:
        raise MissingCodec("lz4 needs the lz4 package")
    return lz4.block.decompress(payload, uncompressed_size=nout)


def _legacy(payload: bytes, nout: int) -> bytes:
    """The `CS` block of Compression.md 3.1: raw deflate, no zlib wrapper."""
    import zlib
    return zlib.decompressobj(-zlib.MAX_WBITS).decompress(payload, nout)


# Magic -> (expected method byte, decompressor). Compression.md section 3.
CODECS = {
    b"ZL": (8, _zlib),
    b"XZ": (0, _lzma),
    b"L4": (None, _lz4),      # the method byte is the LZ4 major version
    b"ZS": (1, _zstd),
    b"CS": (8, _legacy),
}


def _u24le(b: bytes, o: int) -> int:
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)


def decompress_blocks(buf: bytes, src: int, src_end: int, want: int,
                      where: str) -> bytes:
    """A sequence of compression blocks, decompressed to `want` bytes.

    Compression.md section 7. Separate from `decompress` because RNTuple uses
    the same block format for its envelopes and pages without a TKey around
    them, so the block walk has to be reachable without a Record
    (spec/05-rntuple/, "Compression Block").
    """
    rec_obj_len = want
    out = bytearray()
    while len(out) < rec_obj_len:
        if src + BLOCK_HEADER > src_end:
            raise FormatError(
                f"{where}: payload ends mid-block-header")
        magic = bytes(buf[src:src + 2])
        if magic not in CODECS:
            raise FormatError(
                f"{where}: unknown compression magic {magic!r}")
        method, codec = CODECS[magic]
        if method is not None and buf[src + 2] != method:
            raise FormatError(
                f"{where}: {magic.decode()} block has method byte "
                f"{buf[src + 2]}, expected {method}")
        nin = BLOCK_HEADER + _u24le(buf, src + 3)
        nout = _u24le(buf, src + 6)
        if src + nin > src_end:
            raise FormatError(
                f"{where}: block claims {nin} bytes, only "
                f"{src_end - src} remain")
        if len(out) + nout > rec_obj_len:
            raise FormatError(
                f"{where}: block would exceed fObjLen")
        skip = BLOCK_HEADER + (LZ4_CHECKSUM if magic == b"L4" else 0)
        try:
            chunk = codec(bytes(buf[src + skip:src + nin]), nout)
        except MissingCodec:
            raise
        except Exception as exc:
            # Every codec raises its own exception type; a corrupt block is a
            # format error here, not a crash.
            raise FormatError(
                f"{where}: {magic.decode()} block at {src} did not "
                f"decompress: {exc}") from exc
        if len(chunk) != nout:
            raise FormatError(
                f"{where}: block decompressed to {len(chunk)} "
                f"bytes, header says {nout}")
        out += chunk
        src += nin
    if len(out) != rec_obj_len:
        raise FormatError(
            f"{where}: decompressed {len(out)} bytes, fObjLen is "
            f"{rec_obj_len}")
    return bytes(out)


def decompress(buf: bytes, rec: Record) -> bytes:
    """The object data of a compressed record. Compression.md section 7."""
    return decompress_blocks(buf, rec.offset + rec.key_len,
                             rec.offset + rec.nbytes, rec.obj_len,
                             f"record at {rec.offset}")


def object_data(buf: bytes, rec: Record) -> bytes:
    """A buffer in which `rec`'s object data is uncompressed and in place.

    Returns `buf` unchanged when the record is stored raw. Otherwise returns the
    file truncated after this record, with the payload replaced by the
    decompressed bytes, so the record still starts at `rec.offset` and every
    offset convention in this module, which counts from the start of the record,
    still holds. Callers pass the result wherever they would pass the file.
    """
    if not is_compressed(rec):
        return buf
    return bytes(buf[:rec.offset + rec.key_len]) + decompress(buf, rec)


@dataclass
class Slot:
    """One object slot and how it was encoded (Buffer.md section 6)."""

    offset: int                  # position of the first word
    kind: str                    # "null" | "reference" | "object"
    end: int                     # one past the slot
    reference: int | None = None  # map position, for "reference"
    class_name: str | None = None
    class_reference: int | None = None  # map position, for a class back-reference
    object_position: int | None = None  # map position this object was recorded at
    class_position: int | None = None   # map position its class tag was recorded at


def read_slot(buf: bytes, offset: int, base: int) -> Slot:
    """Read one object slot. `base` is the record start, i.e. buffer position 0.

    Raises FormatError when the slot cannot be skipped, which happens only for a
    new-class record with no byte count, a form no fixture contains.
    """
    word = _u32(buf, offset)
    if word == 0:
        return Slot(offset=offset, kind="null", end=offset + 4)
    if not (word & BYTE_COUNT_MASK) and word != NEW_CLASS_TAG:
        return Slot(offset=offset, kind="reference", end=offset + 4, reference=word)

    if word == NEW_CLASS_TAG:
        raise FormatError(f"new-class record with no byte count at {offset}")
    byte_count = word & ~BYTE_COUNT_MASK
    tag_after_count = _u32(buf, offset + 4)
    if not (tag_after_count & CLASS_MASK) and tag_after_count != NEW_CLASS_TAG:
        # A byte count wrapping a bare object reference. ROOT does not write this
        # but its reader accepts it, and files in the wild contain it.
        # Buffer.md section 6.1.
        return Slot(offset=offset, kind="reference", end=offset + 4 + byte_count,
                    reference=tag_after_count)
    if byte_count > MAX_MAP_COUNT:
        raise FormatError(f"byte count {byte_count} at {offset} exceeds kMaxMapCount")
    end = offset + 4 + byte_count
    tag = _u32(buf, offset + 4)
    slot = Slot(offset=offset, kind="object", end=end,
                object_position=offset - base + MAP_OFFSET)
    if tag == NEW_CLASS_TAG:
        name, _ = _counted_string_c(buf, offset + 8)
        slot.class_name = name
        slot.class_position = offset + 4 - base + MAP_OFFSET
    elif tag & CLASS_MASK:
        slot.class_reference = tag & ~CLASS_MASK
    else:
        raise FormatError(f"object slot at {offset} has a byte count but tag {tag:#x}")
    return slot


def _counted_string_c(buf: bytes, offset: int) -> tuple[str, int]:
    """A null-terminated class name (Conventions 5.2). Returns (name, next)."""
    end = buf.index(b"\x00", offset)
    return buf[offset:end].decode("latin-1"), end + 1


def read_tlist(buf: bytes, rec: Record) -> list[Slot]:
    """Walk a TList record and return its object slots.

    TList's layout is version dependent (root/core/cont/src/TList.cxx:1323): the
    option string per entry exists only for version > 3, and its 255 escape only
    for version > 4.
    """
    base = rec.offset
    start, end = payload_range(rec)
    frame = read_frame(buf, start)
    if frame.version < 1 or frame.version > 5:
        raise FormatError(f"unexpected TList version {frame.version}")
    o = frame.body
    if frame.version > 2:
        o = skip_tobject(buf, o)
    if frame.version > 1:
        o = _counted_string(buf, o)[1]   # returns the next offset, not a length
    count = _i32(buf, o)
    o += 4
    slots = []
    for _ in range(count):
        slot = read_slot(buf, o, base)
        slots.append(slot)
        o = slot.end
        if frame.version > 3:
            n = buf[o]
            if n == 255 and frame.version > 4:
                o += 5 + _i32(buf, o + 1)
            else:
                o += 1 + n
    if o != end:
        raise FormatError(f"TList at {rec.offset} ends at {o}, payload ends at {end}")
    return slots


# ---------------------------------------------------------------------------
# The StreamerInfo record, spec/02-serialization/StreamerInfo.md.
#
# These classes cannot be read using streamer info, because the streamer info is
# made of them, so the layout below is hardcoded. This is the bootstrap problem
# the specification describes.
# ---------------------------------------------------------------------------

# TStreamerElement status bits that survive to disk, in the TObject base's fBits.
ELEMENT_HAS_RANGE = 1 << 6       # kHasRange: the title carries a Double32/Float16 range
ELEMENT_DO_NOT_DELETE = 1 << 13  # kDoNotDelete

# The subclass tail after the TStreamerElement base, as (member, reader) pairs.
# ---------------------------------------------------------------------------
# The hand-written containers: TMap, TExMap, TBtree (03-classes/Containers.md).
#
# None of the three has a usable streamer info (none calls WriteClassBuffer, so
# no info is written), and all three hold ordinary object slots, so they are
# read here from the specification rather than through the streamer-driven
# path.
# ---------------------------------------------------------------------------

#: The fixed part of a TExMap record: slot, hash, key, value.
EXMAP_RECORD = 4 + 8 + 8 + 8


@dataclass
class Collection:
    """A TCollection frame: what TMap, TBtree and TList all end with."""

    version: int
    name: str
    count: int
    slots: list[Slot]
    end: int


@dataclass
class ExMap:
    """A TExMap: fSize slots, fTally of them written."""

    version: int
    size: int
    tally: int
    records: list[tuple[int, int, int, int]]   # slot, hash, key, value
    end: int


@dataclass
class BTree:
    """A TBtree: six shape integers and then a TCollection frame."""

    version: int
    order: int
    order2: int
    inner_low: int
    leaf_low: int
    inner_max: int
    leaf_max: int
    collection: Collection
    end: int


def read_collection_frame(buf: bytes, offset: int, base: int,
                          pairs: bool = False) -> Collection:
    """The `TObject`, `fName`, count and object slots of a TCollection frame.

    `pairs` reads two slots per count, as `TMap::Streamer` writes them: the
    count is the number of pairs, not the number of slots.
    """
    frame = read_frame(buf, offset)
    at = skip_tobject(buf, frame.body)
    name, at = _counted_string(buf, at)
    count = _i32(buf, at)
    at += 4
    slots = []
    for _ in range(count * (2 if pairs else 1)):
        slot = read_slot(buf, at, base)
        slots.append(slot)
        at = slot.end
    if at != frame.end:
        raise FormatError(
            f"TCollection frame at {offset} consumed {at - offset} bytes, "
            f"byte count says {frame.end - offset}")
    return Collection(version=frame.version, name=name, count=count,
                      slots=slots, end=frame.end)


def read_tmap(buf: bytes, rec: Record) -> Collection:
    """A TMap record. Containers.md section 1."""
    start, _ = payload_range(rec)
    return read_collection_frame(buf, start, rec.offset, pairs=True)


def read_texmap(buf: bytes, rec: Record) -> ExMap:
    """A TExMap record. Containers.md section 2."""
    start, _ = payload_range(rec)
    frame = read_frame(buf, start)
    at = skip_tobject(buf, frame.body)
    size, tally = _i32(buf, at), _i32(buf, at + 4)
    at += 8
    records = []
    for _ in range(max(tally, 0)):
        records.append((_i32(buf, at), _u64(buf, at + 4),
                        _i64(buf, at + 12), _i64(buf, at + 20)))
        at += EXMAP_RECORD
    if at != frame.end:
        raise FormatError(
            f"TExMap at {start} consumed {at - start} bytes, byte count says "
            f"{frame.end - start}")
    return ExMap(version=frame.version, size=size, tally=tally,
                 records=records, end=frame.end)


def read_tbtree(buf: bytes, rec: Record) -> BTree:
    """A TBtree record. Containers.md section 3.

    The six integers are followed by one more frame, TCollection's:
    `TSeqCollection` is a version-0 class whose generated
    `Streamer` forwards to its bases and writes nothing of its own, so it
    contributes no frame at all (Containers.md section 6).
    """
    start, _ = payload_range(rec)
    frame = read_frame(buf, start)
    at = frame.body
    shape = [_i32(buf, at + 4 * i) for i in range(6)]
    at += 24
    collection = read_collection_frame(buf, at, rec.offset)
    if collection.end != frame.end:
        raise FormatError(
            f"TBtree at {start}: its TCollection frame ends at "
            f"{collection.end}, the TBtree byte count at {frame.end}")
    return BTree(version=frame.version, order=shape[0], order2=shape[1],
                 inner_low=shape[2], leaf_low=shape[3], inner_max=shape[4],
                 leaf_max=shape[5], collection=collection, end=frame.end)


# Empty for the subclasses that add nothing.
_ELEMENT_TAILS = {
    "TStreamerBase": [("fBaseVersion", "i32")],
    "TStreamerBasicType": [],
    "TStreamerBasicPointer": [("fCountVersion", "i32"),
                              ("fCountName", "string"), ("fCountClass", "string")],
    "TStreamerLoop": [("fCountVersion", "i32"),
                      ("fCountName", "string"), ("fCountClass", "string")],
    "TStreamerObject": [],
    "TStreamerObjectAny": [],
    "TStreamerObjectPointer": [],
    "TStreamerObjectAnyPointer": [],
    "TStreamerString": [],
    "TStreamerSTL": [("fSTLtype", "i32"), ("fCtype", "i32")],
    "TStreamerSTLstring": [],   # nests one level deeper, inside TStreamerSTL
}


@dataclass
class Element:
    """One TStreamerElement subclass instance out of a TStreamerInfo."""

    cls: str                 # concrete subclass name
    version: int             # of that subclass
    name: str                # fName: the member or base-class name
    title: str               # fTitle: the declaration comment
    bits: int                # the TObject base's fBits
    ftype: int
    fsize: int
    array_length: int
    array_dim: int
    max_index: list[int]
    type_name: str
    tail: dict               # subclass-specific members
    fsize_offset: int = -1   # where fSize sits in the buffer; see normalize.py

    @property
    def has_range(self) -> bool:
        return bool(self.bits & ELEMENT_HAS_RANGE)

    @property
    def base_checksum(self) -> int:
        """For a TStreamerBase, fBaseCheckSum is an alias for fMaxIndex[1].

        fMaxIndex is declared Int_t but fBaseCheckSum is a UInt_t reference onto
        it, so a checksum with the top bit set reads back negative and must be
        reinterpreted as unsigned.
        """
        return self.max_index[1] & 0xFFFFFFFF

    @property
    def count_name(self) -> str:
        """For a TStreamerBasicPointer or TStreamerLoop, the counter it names."""
        return self.tail.get("fCountName", "")


@dataclass
class StreamerInfo:
    name: str                # the described class
    title: str
    version: int             # of TStreamerInfo itself
    bits: int
    checksum: int
    class_version: int
    elements: list[Element]


def _skip_named(buf: bytes, offset: int) -> tuple[str, str, int, int]:
    """Skip a TNamed record; return (fName, fTitle, fBits, next offset)."""
    frame = read_frame(buf, offset)
    o = frame.body
    bits = _u32(buf, o + 6)
    o = skip_tobject(buf, o)
    name, o = _counted_string(buf, o)
    title, o = _counted_string(buf, o)
    if frame.end is not None:
        o = frame.end
    return name, title, bits, o


def resolve_class(slot: Slot, classes: dict[int, str]) -> tuple[str, int]:
    """The slot's class name and the offset its object body starts at.

    `classes` maps map positions to class names and is filled as the buffer is
    walked, so that a class back-reference can be resolved (Buffer.md section
    5.2). It must be shared across one whole record.
    """
    if slot.kind != "object":
        raise FormatError(f"slot at {slot.offset} is {slot.kind}, not an object")
    if slot.class_name is not None:
        classes[slot.class_position] = slot.class_name
        # class name is NUL-terminated, starting 8 bytes into the slot
        return slot.class_name, slot.offset + 8 + len(slot.class_name) + 1
    ref = slot.class_reference
    if ref not in classes:
        raise FormatError(f"slot at {slot.offset} references class position {ref}, "
                          f"which was not seen earlier in this buffer")
    return classes[ref], slot.offset + 8


def read_element(buf: bytes, offset: int, base: int,
                 classes: dict[int, str]) -> tuple[Element, int]:
    """Read one element slot out of a TStreamerInfo's fElements array."""
    slot = read_slot(buf, offset, base)
    cls, body = resolve_class(slot, classes)
    return _read_element_body(buf, body, cls), slot.end


def _read_element_body(buf: bytes, offset: int, cls: str) -> Element:
    outer = read_frame(buf, offset)
    o = outer.body
    if cls == "TStreamerSTLstring":
        # Nests TStreamerSTL, which itself nests TStreamerElement.
        inner = read_frame(buf, o)
        el = _read_element_body(buf, o, "TStreamerSTL")
        return Element(cls=cls, version=outer.version, name=el.name, title=el.title,
                       bits=el.bits, ftype=el.ftype, fsize=el.fsize,
                       array_length=el.array_length, array_dim=el.array_dim,
                       max_index=el.max_index, type_name=el.type_name, tail=el.tail,
                       fsize_offset=el.fsize_offset)

    # The TStreamerElement base.
    elem = read_frame(buf, o)
    eo = elem.body
    name, title, bits, eo = _skip_named(buf, eo)
    fsize_offset = eo + 4
    ftype, fsize, array_length, array_dim = struct.unpack_from(">iiii", buf, eo)
    eo += 16
    max_index = list(struct.unpack_from(">5i", buf, eo))
    eo += 20
    type_name, eo = _counted_string(buf, eo)
    if elem.version == 3:
        eo += 24        # fXmin, fXmax, fFactor, persisted only at version 3
    if elem.end is not None:
        eo = elem.end

    tail = {}
    for member, kind in _ELEMENT_TAILS.get(cls, []):
        if kind == "i32":
            tail[member] = _i32(buf, eo)
            eo += 4
        else:
            tail[member], eo = _counted_string(buf, eo)

    if ftype == 11 and type_name in ("Bool_t", "bool"):
        ftype = 18      # read-time fixup, root/core/meta/src/TStreamerElement.cxx:566

    # The second read-time fixup, which cannot be skipped: until 5.34/13
    # `TStreamerSTL` numbered kSTLset 5 and kSTLmultimap 6, the reverse of every
    # other use of the enum, and the element version did not change. fSTLtype
    # alone cannot tell which convention wrote it, so fTypeName is used. Mirrors
    # root/core/meta/src/TStreamerElement.cxx:2112-2122 exactly, including its
    # prefix test and its indifference to kOffsetP. Collections.md 1.
    if tail.get("fSTLtype") in (STL_MULTIMAP, STL_SET):
        if type_name.startswith(("set", "std::set")):
            tail["fSTLtype"] = STL_SET
        elif type_name.startswith(("multimap", "std::multimap")):
            tail["fSTLtype"] = STL_MULTIMAP

    return Element(cls=cls, version=outer.version, name=name, title=title, bits=bits,
                   ftype=ftype, fsize=fsize, array_length=array_length,
                   array_dim=array_dim, max_index=max_index, type_name=type_name,
                   tail=tail, fsize_offset=fsize_offset)


def read_streamer_info(buf: bytes, rec: Record, slot: Slot,
                      classes: dict[int, str]) -> StreamerInfo:
    """Read one TStreamerInfo out of the StreamerInfo record's list."""
    _, o = resolve_class(slot, classes)
    frame = read_frame(buf, o)
    o = frame.body
    bits = _u32(buf, read_frame(buf, o).body + 6)
    name, title, _, o = _skip_named(buf, o)
    checksum = _u32(buf, o)
    class_version = _i32(buf, o + 4)
    o += 8

    # fElements: an object slot holding a TObjArray.
    arr = read_slot(buf, o, rec.offset)
    _, ao = resolve_class(arr, classes)
    aframe = read_frame(buf, ao)
    ao = aframe.body
    if aframe.version > 2:
        ao = skip_tobject(buf, ao)
    if aframe.version > 1:
        ao = _counted_string(buf, ao)[1]
    count = _i32(buf, ao)
    ao += 8                      # nobjects, then fLowerBound
    elements = []
    for _ in range(count):
        el, ao = read_element(buf, ao, rec.offset, classes)
        elements.append(el)
    return StreamerInfo(name=name, title=title, version=frame.version, bits=bits,
                        checksum=checksum, class_version=class_version,
                        elements=elements)


def read_streamer_infos(buf: bytes, rec: Record) -> list[StreamerInfo]:
    """Every TStreamerInfo in the StreamerInfo record. Non-TStreamerInfo entries
    (the optional `listOfRules`) are skipped by their byte count."""
    infos: list[StreamerInfo] = []
    classes: dict[int, str] = {}
    for slot in read_tlist(buf, rec):
        if slot.kind != "object":
            continue
        cls, _ = resolve_class(slot, classes)
        if cls != "TStreamerInfo":
            continue   # the optional listOfRules; skipped by its byte count
        infos.append(read_streamer_info(buf, rec, slot, classes))
    return infos


# ---------------------------------------------------------------------------
# The streamer-driven read (spec/02-serialization/StreamerDriven.md).
#
# Written from the specification, not from ROOT's source, so that a
# disagreement between the two can be detected. It produces a value tree and an
# exact end position, which StreamerDriven.md invariants 1 and 2 check.
# ---------------------------------------------------------------------------

# On-disk width of a scalar type code (ElementTypes.md section 2). kDouble32 (9)
# and kFloat16 (19) are absent because their width depends on the comment string,
# and kCharStar (7) because its length is in the stream.
SCALAR_WIDTH = {
    1: 1, 2: 2, 3: 4, 4: 8, 5: 4, 6: 4, 8: 8, 10: 1,
    11: 1, 12: 2, 13: 4, 14: 8, 15: 4, 16: 8, 17: 8, 18: 1,
}

OFFSET_L = 20
OFFSET_P = 40

# Classes whose Streamer is hand-written *at the versions a current file uses*, so
# that their streamer info, though still in the file, does not describe their
# bytes (StreamerDriven.md section 7).
#
# The list is deliberately short. Many ROOT classes have a hand-written Streamer,
# but it is a version guard that delegates to ReadClassBuffer above some
# threshold and keeps a legacy layout below it: TH1 and TGraph above class
# version 2, TAxis above 5, TTree above 4, TLeaf above 1, and
# TBranch/TBranchElement unconditionally. Those are streamer-info driven for
# every version a modern file contains, and listing them here would wrongly
# refuse files this specification can describe.
#
# What remains are the classes that diverge at every version.
# std::string has a hand-written streamer registered on its TClass
# (root/core/base/src/String.cxx:36) and is written with no framing at all.
# Every spelling libstdc++ and libc++ give it reaches a file as a class name.
STD_STRING_NAMES = {
    "string", "std::string",
    "basic_string<char,char_traits<char>,allocator<char> >",
    "std::basic_string<char>",
}


def read_std_string(buf: bytes, offset: int) -> Value:
    """A std::string object: a bare counted string. Collections.md 10.1."""
    _, end = _counted_string(buf, offset)
    return Value(name="string", ftype=61, start=offset, end=end,
                 type_name="string")


CUSTOM_STREAMER = {
    # The container's own bookkeeping, specified in spec/01-container/.
    "TFile", "TDirectory", "TDirectoryFile",
    # TArray itself is abstract and never streamed; its streamer info, which
    # lists fN, describes nothing any file contains. The concrete subclasses are
    # implemented below, from spec/03-classes/TArray.md.
    "TArray",
    # Reachable only through TList's streamer info, which describes bases its
    # hand-written streamer never writes. read_sequence bypasses that info, so
    # these should never be reached.
    "TCollection", "TSeqCollection",
    # Implemented below, from spec/02-serialization/References.md.
    "TRef", "TRefArray",
    # Writes nothing in either direction, so a kBase element for it occupies
    # zero bytes, and a modern file has no streamer info for it at all, leaving
    # a reader with an element it can neither describe nor skip.
    # StreamerDriven.md 4.4; every TPad and TCanvas has one.
    "TQObject",
    # A version word, a TPad read through its own info, then fourteen fields
    # and seven bytes of fBits that its info does not mention.
    # spec/03-classes/Canvas.md.
    "TCanvas",
    # An i32 count and then the characters: no length byte, no 255 escape, no
    # version word and no byte count. It appears as element code 62 (kAny), so
    # the streamer-driven path would look for a frame, and no file has an info
    # for it. Conventions 5.1.1.
    "TStringLong",
    # Derives from TBranch and streams a TNamed plus ten hand-picked TBranch
    # fields instead of a TBranch base. No file has an info for it, as with
    # TBasket and TTreeIndex. spec/04-ttree/TBranchElement.md 12.1.
    "TBranchClones",
    # `extending`: calls ReadClassBuffer with TMatrixTBase's TClass and then
    # reads the upper-right triangle, outside the byte count. The name in a file
    # is a specialization (TMatrixTSym<double>), so read_object dispatches on the
    # prefix; this entry is the template, as the sidecar and Bootstrap.md name
    # it. spec/03-classes/Matrix.md.
    "TMatrixTSym",
    # RooFit. All four are implemented below, from spec/03-classes/RooFit.md.
    # RooRealVar writes no info for itself at all, and RooLinkedList writes one
    # that names a member it never streams; neither describes the bytes.
    # RooAbsBinning and RooRefArray are reached from a RooRealVar (as the base
    # of its binning and as RooAbsArg's proxy list) and write no info either.
    "RooRealVar", "RooLinkedList", "RooAbsBinning", "RooRefArray",
}

# Classes whose *generated* Streamer writes only their base classes: ClassDef
# version <= 0 selected with a plain `#pragma link C++ class X;`, for which
# rootcling emits a body that calls each base's Streamer and returns, with no
# version word, no byte count and none of its own members
# (root/core/dictgen/src/rootcling_impl.cxx:1332-1367).
#
# Nothing in a file distinguishes such a class from a version-0 class read
# through ReadClassBuffer, which writes a version word of 0, so a reader has to
# know the list in advance. spec/99-appendix/ForwardingStreamers.md publishes
# all 534 of them; these are the three that any file in either corpus names,
# and the rest are a lookup table in case a file needs one. StreamerDriven.md
# 4.5.
FORWARDING_STREAMER = {
    # a kBase of TList and TObjArray, in 240 files
    "TSeqCollection",
    # TAxis::fLabels and TGeoManager::fHashPNE are THashList*, so any labelled
    # axis writes one. Read by read_sequence, which implements the TList base
    # this would forward to, so the dispatch below never reaches it.
    "THashList",
    # a kBase of TTreePerfStats, in aod_flushed.root
    "TVirtualPerfStats",
}

_PI_LITERALS = {
    "pi": 3.141592653589793,
    "2pi": 6.283185307179586,
    "twopi": 6.283185307179586,
    "pi/2": 1.5707963267948966,
    "pi/4": 0.7853981633974483,
}


def _range_literal(text: str) -> float:
    text = text.strip()
    sign = 1.0
    if text[:1] in "+-":
        sign, text = (-1.0 if text[0] == "-" else 1.0), text[1:].strip()
    key = text.lower()
    if key in _PI_LITERALS:
        return sign * _PI_LITERALS[key]
    return sign * float(text)


def quantised_width(ftype: int, title: str) -> int:
    """On-disk width of a kDouble32 or kFloat16 member (ElementTypes.md 5.2).

    The annotation is in the declaration comment, so the streamer info's type
    fields alone are not enough. The first bracket group may be an array
    dimension, which has no comma; the range grammar always has one.
    """
    xmin = xmax = 0.0
    nbits = 32
    rest = title
    while "[" in rest and "]" in rest:
        inner = rest[rest.index("[") + 1:rest.index("]")]
        rest = rest[rest.index("]") + 1:]
        if "," not in inner:
            continue
        parts = inner.split(",")
        try:
            xmin = _range_literal(parts[0])
            xmax = _range_literal(parts[1])
            if len(parts) > 2:
                nbits = int(parts[2].strip())
        except ValueError:
            continue
        break
    if not 2 <= nbits <= 32:
        nbits = 32
    bigint = (1 << nbits) if nbits < 32 else 0xFFFFFFFF
    factor = 0.0
    if xmin < xmax:
        factor = bigint / (xmax - xmin)
    elif nbits < 15:
        xmin = nbits + 0.1
    if factor != 0.0:
        return 4
    if int(xmin) != 0:
        return 3
    return 4 if ftype == 9 else 3


@dataclass
class Value:
    """One member, and the byte range it occupied."""

    name: str
    ftype: int
    start: int
    end: int
    type_name: str = ""
    members: list | None = None   # for a nested object
    note: str = ""                # why it was skipped rather than decoded
    tobject: TObjectBase | None = None
    reference: int | None = None  # map position, when the slot was a reference


class UnsupportedClass(FormatError):
    """The class has a hand-written Streamer, or no streamer info in this file."""


def _bare_class(type_name: str) -> str:
    name = type_name.strip()
    if name.startswith("const "):
        name = name[6:]
    return name.rstrip("*").strip()


def _tobject_versions(values: list[Value]):
    """The version word of every TObject base inside `values`, depth first."""
    for value in values:
        if value.tobject is not None:
            yield value.tobject.version
        yield from _tobject_versions(value.members or [])


class Decoder:
    """Applies streamer infos to a record's object data.

    `base` is the record start, which is buffer position 0 (Buffer.md section 1).
    """

    def __init__(self, buf: bytes, base: int, infos: list[StreamerInfo],
                 tolerant: bool = False, custom: "set[str] | None" = None):
        self.buf = buf
        self.base = base
        # StreamerDriven.md section 7: nothing in a file marks a class whose
        # Streamer is hand-written, so a reader needs a list. CUSTOM_STREAMER is
        # this specification's; `custom` extends it with classes a caller has
        # diagnosed in a particular file.
        self.custom = CUSTOM_STREAMER | set(custom or ())
        # A second list, for the opposite reason: these have a *generated*
        # Streamer that writes only their bases. ForwardingStreamers.md.
        self.forwarding = FORWARDING_STREAMER
        # In tolerant mode an object whose class cannot be read is skipped by its
        # byte count and recorded, instead of failing the whole read, as
        # StreamerDriven.md section 8 says a partial reader should. It is off by
        # default so that the fixture checks stay strict.
        self.tolerant = tolerant
        self.unread: list[tuple[str, int]] = []   # (reason, buffer offset)
        self.infos: dict[str, dict[int, StreamerInfo]] = {}
        for info in infos:
            self.infos.setdefault(info.name, {})[info.class_version] = info
        self.classes: dict[int, str] = {}
        # (member name, value class, frame offset) for each member-wise
        # collection reached, recorded before it is decoded so that it survives
        # a failure to decode it.
        self.member_wise: list[tuple[str, str, int]] = []
        # (class, offset, reading) for each object read with no byte count;
        # StreamerDriven.md 7.1.
        self.unframed: list[tuple[str, int, str]] = []
        # Classes whose unframed objects are to be read version-first, because
        # an enclosing extent rejected the no-version reading of them.
        self.versioned: set[str] = set()

    def base_info(self, el: Element) -> StreamerInfo:
        """The info a TStreamerBase element selects, where no version word does.

        By fBaseVersion when it is not negative or there is no checksum, and by
        fBaseCheckSum otherwise (root/core/meta/src/TStreamerElement.cxx:762-765).
        The checksum is the only way to find a base whose class declares no
        version (fBaseVersion -1).
        """
        version, checksum = el.tail.get("fBaseVersion", -1), el.base_checksum
        if version >= 0 or checksum == 0:
            return self.info_for(el.name, version)
        for info in self.infos.get(el.name, {}).values():
            if info.checksum == checksum:
                return info
        raise UnsupportedClass(
            f"base {el.name} with checksum {checksum:#010x}, which matches no "
            f"streamer info in this file")

    def info_for(self, cls: str, version: int) -> StreamerInfo:
        if cls in self.custom:
            raise UnsupportedClass(f"{cls} has a hand-written Streamer")
        by_version = self.infos.get(cls)
        if not by_version:
            raise UnsupportedClass(f"no streamer info for {cls}")
        if version in by_version:
            return by_version[version]
        if len(by_version) == 1:
            # A single info for the class: ROOT renumbers a version of 0, so an
            # exact match is not required (SchemaEvolution).
            return next(iter(by_version.values()))
        raise UnsupportedClass(f"no streamer info for {cls} version {version}")

    # -- objects ----------------------------------------------------------

    # TList and THashList share a layout; TObjArray differs only in having no
    # per-entry option string and one extra Int_t. StreamerInfo.md 4 and 5.
    SEQUENCES = {"TList": True, "THashList": True, "TObjArray": False}

    def read_object(self, cls: str, offset: int,
                    counters: dict[str, int] | None = None) -> Value:
        """An object introduced by its own `byteCount version` (no class record).

        `counters` is passed down only for a base class, whose counted pointers
        may name a counter in a base of their own.
        """
        if cls in self.custom and cls not in CUSTOM_STREAMER:
            # A class a caller has diagnosed as having a hand-written Streamer.
            # Checked before the dispatch below so that it wins over any reader
            # this module has of its own.
            raise UnsupportedClass(f"{cls} has a hand-written Streamer")
        if cls == "TClonesArray":
            return self.read_clones_array(offset)
        if cls in self.SEQUENCES:
            return self.read_sequence(cls, offset)
        if cls in TARRAY_WIDTH:
            return self.read_tarray(cls, offset)
        if cls in STD_STRING_NAMES:
            return read_std_string(self.buf, offset)
        if cls == "TTreeIndex":
            # No streamer info for it is ever written, so the streamer-driven
            # path cannot read it. Its layout is hand-coded in read_tree_index;
            # here the object is framed by its byte count and left to that.
            # Auxiliary.md section 2.
            frame = read_frame(self.buf, offset)
            if frame.end is None:
                raise FormatError("TTreeIndex with no byte count")
            return Value(name=cls, ftype=61, start=offset, end=frame.end,
                         type_name=cls,
                         note="TTreeIndex: read with read_tree_index")
        if cls == "TString":
            # TString::Streamer writes a bare counted string (no version word
            # and no byte count) wherever the class appears, not only under
            # element code 65. A kStreamLoop of TString reaches here, and so
            # does an object slot whose class is TString.
            # ElementTypes.md 7.1.
            _, end = _counted_string(self.buf, offset)
            return Value(name="TString", ftype=65, start=offset, end=end,
                         type_name="TString")
        if cls == "TObject":
            # A TObject stored as an object in its own right (a record, or a
            # slot whose class is TObject) is the base of Buffer.md 7: a bare
            # version word, fUniqueID, fBits and a pidf when referenced.
            # TObject::Streamer writes no byte count and there is no separate
            # base inside it; the generic path read a version word here and
            # then a TObject base after it, ending two bytes past the end.
            # Buffer.md 2.3, found by serialization/unframed-records.
            base = read_tobject(self.buf, offset)
            return Value(name="TObject", ftype=66, start=offset, end=base.end,
                         type_name="TObject", tobject=base)
        if cls == "TQObject":
            # Reads nothing and writes nothing, in either direction
            # (root/core/base/src/TQObject.cxx:1033-1040). A kBase element for it
            # occupies no bytes: not a framed empty object, not a version word.
            # StreamerDriven.md 4.4.
            return Value(name="TQObject", ftype=0, start=offset, end=offset,
                         type_name="TQObject",
                         note="TQObject: contributes no bytes")
        if cls == "TCanvas":
            return self.read_tcanvas(offset)
        if cls == "TBranchClones":
            return self.read_branch_clones(offset)
        if cls == "TStringLong":
            # A signed count and then that many bytes, bare
            # (root/core/base/src/TStringLong.cxx:131-147). Not TString's
            # encoding: no length byte and no escape. Conventions 5.1.1.
            n = _i32(self.buf, offset)
            if n < 0:
                raise FormatError(
                    f"TStringLong at {offset} has a negative length {n}")
            return Value(name="TStringLong", ftype=62, start=offset,
                         end=offset + 4 + n, type_name="TStringLong")
        if cls == "TDatime":
            # A hand-written streamer that writes fDatime and nothing else: no
            # version word and no byte count. Record.md section 3.7.
            return Value(name="TDatime", ftype=62, start=offset, end=offset + 4,
                         type_name="TDatime")
        if cls.startswith("TMatrixTSym<"):
            return self.read_matrix_sym(cls, offset)
        if cls == "RooLinkedList":
            return self.read_roo_linked_list(offset)
        if cls == "RooRealVar":
            return self.read_roo_real_var(offset)
        if cls == "RooAbsBinning":
            return self.read_roo_abs_binning(offset)
        if cls == "RooCategory":
            return self.read_roo_category(offset)
        if cls == "RooRefArray":
            return self.read_roo_ref_array(offset)
        if cls == "TRefArray":
            # As a *member* rather than a record payload. Its Streamer is
            # hand-written and no info describes it, but the layout is the same
            # one read_ref_array implements. References.md section 4. Reached
            # through RooAbsArg::_proxyList, which was declared TRefArray until
            # ROOT 6.26 and RooRefArray after it.
            array = read_ref_array(self.buf, offset)
            return Value(name="TRefArray", ftype=61, start=offset,
                         end=array.end, type_name="TRefArray")
        if cls in self.forwarding:
            return self.read_forwarded(cls, offset, counters)
        try:
            frame = read_frame(self.buf, offset)
            if frame.end is None and self.is_tobject(cls):
                if cls in self.versioned:
                    self.unframed.append((cls, offset, "version-first"))
                else:
                    unframed = self.read_unframed(cls, offset, counters)
                    if unframed is not None:
                        return unframed
            version, body = self.resolve_version(cls, frame)
            members = self.read_members(cls, version, body, frame.end, counters)
            if (frame.end is None and self.is_tobject(cls)
                    and any(v != 1 for v in _tobject_versions(members))):
                # Neither reading of an unframed object is admissible: the
                # no-version one was rejected already, and this one finds a
                # TObject version word ROOT never writes. StreamerDriven.md 7.1.
                raise UnsupportedClass(
                    f"{cls} has no byte count and its bytes are not what its "
                    f"streamer info describes: a hand-written Streamer "
                    f"(StreamerDriven.md 7.1)")
        except UnsupportedClass as exc:
            return self.skip_or_fail(cls, offset, exc)
        end = frame.end if frame.end is not None else (
            members[-1].end if members else body)
        return Value(name=cls, ftype=61, start=offset, end=end,
                     type_name=cls, members=members)

    def is_tobject(self, cls: str) -> bool:
        """Does `cls` derive from TObject, per the file's own infos?"""
        seen: set[str] = set()
        stack = [cls]
        while stack:
            current = stack.pop()
            if current == "TObject":
                return True
            if current in seen:
                continue
            seen.add(current)
            for info in self.infos.get(current, {}).values():
                stack += [el.name for el in info.elements
                          if el.cls == "TStreamerBase"]
        return False

    def read_unframed(self, cls: str, offset: int,
                      counters: dict[str, int] | None = None) -> Value | None:
        """An object of a TObject-derived class with no byte count at all.

        What ROOT does depends on a dictionary the file does not hold: with the
        class's library it runs that Streamer, and without one it assumes there
        is **no version word** either and applies the elements from the object's
        first byte (root/io/io/src/TBufferFile.cxx:3412-3436). This is that
        second reading, which ROOT uses for every class it knows only from the
        file. The info is the one at the version the first two bytes give, else
        the class's first, as ROOT's fallback does. StreamerDriven.md 7.1.

        Returns None when the reading is not admissible (it raises, or a TObject
        base inside it does not have the version word 1 that ROOT always writes,
        Buffer.md 7); the caller then takes the version-first reading of ROOT's
        own Streamers. Which one was taken is recorded in `unframed`, so that a
        caller that knows the enclosing extent can tell a reading that does not
        fit it from a failure (within_extent).
        """
        by_version = self.infos.get(cls, {})
        if not by_version:
            return None
        info = by_version.get(_i16(self.buf, offset)) \
            or next(iter(by_version.values()))
        try:
            members = self.read_members(cls, info.class_version, offset, None,
                                        counters)
        except (FormatError, struct.error, IndexError, ValueError):
            self.unframed.append((cls, offset, "version-first"))
            return None
        if any(v != 1 for v in _tobject_versions(members)):
            self.unframed.append((cls, offset, "version-first"))
            return None
        self.unframed.append((cls, offset, "no version word"))
        end = members[-1].end if members else offset
        return Value(name=cls, ftype=61, start=offset, end=end, type_name=cls,
                     members=members, note="no byte count and no version "
                     "word: StreamerDriven.md 7.1")

    def read_in_slot(self, cls: str, body_at: int, slot_end: int) -> Value:
        """The object inside an object slot, whose byte count gives its extent.

        The slot's end wins whatever the object consumed (StreamerDriven.md 8),
        but an object read with no byte count of its own that does not fill the
        slot is the hand-written Streamer of section 7.1, reported as such rather
        than stepped over.
        """
        return self.within_extent(lambda: self.read_object(cls, body_at),
                                  body_at, slot_end, lambda v: v.end)

    def within_extent(self, read, start: int, end: int, end_of):
        """Run `read`, whose result must end at `end`, with StreamerDriven.md 7.1.

        If it does not, and it read an object with no byte count by the
        no-version reading, it is run again with those classes read version
        first. If that does not end there either, the class has a hand-written
        Streamer its info does not describe.
        """
        mark = len(self.unframed)
        result = read()
        if end_of(result) == end:
            return result
        chosen = {c for c, at, how in self.unframed[mark:]
                  if start <= at < end and how == "no version word"}
        if not chosen - self.versioned:
            within = [c for c, at, _ in self.unframed[mark:] if start <= at < end]
            if within:
                raise UnsupportedClass(
                    f"{within[0]} has no byte count and its bytes are not what "
                    f"its streamer info describes: a hand-written Streamer "
                    f"(StreamerDriven.md 7.1)")
            return result
        added = chosen - self.versioned
        self.versioned |= added
        try:
            return self.within_extent(read, start, end, end_of)
        finally:
            self.versioned -= added

    def read_forwarded(self, cls: str, offset: int,
                       counters: dict[str, int] | None = None) -> Value:
        """A class whose generated Streamer calls its bases and nothing else.

        No version word and no byte count: the first byte of the object is the
        first byte of its first base. The base list comes from the class's own
        streamer info, which for a version-0 class holds only its bases, since
        TStreamerInfo::Build skips every data member of such a class
        (root/io/io/src/TStreamerInfo.cxx:552-554). Any non-base element is
        therefore a member the streamer does not write and is ignored here.
        ForwardingStreamers.md section 3.
        """
        by_version = self.infos.get(cls, {})
        if not by_version:
            raise UnsupportedClass(
                f"{cls} writes only its bases, and no streamer info in this "
                f"file names them")
        info = by_version[min(by_version)]
        members: list[Value] = []
        pos = offset
        if counters is None:
            counters = {}
        for el in info.elements:
            if el.ftype not in (0, 66):
                continue        # a member the forwarding streamer never writes
            value = self.read_element_value(el, pos, counters)
            members.append(value)
            pos = value.end
        return Value(name=cls, ftype=61, start=offset, end=pos, type_name=cls,
                     members=members,
                     note=f"{cls}: a forwarding Streamer, so its bases and "
                          f"nothing else")

    def read_matrix_sym(self, cls: str, offset: int) -> Value:
        """A symmetric matrix: TMatrixTBase's frame, then the upper triangle.

        `TMatrixTSym<Element>::Streamer` hands `ReadClassBuffer` the *base*
        class's TClass (root/math/matrix/src/TMatrixTSym.cxx:2036), so the frame
        has TMatrixTBase's class version and the file holds an info for
        TMatrixTBase and none for this class. Past the byte count come
        fNrows*(fNrows+1)/2 elements, row i holding fNcols-i of them from the
        diagonal on, with the lower triangle reconstructed rather than stored.
        Matrix.md section 2.
        """
        args = template_args(cls)
        element = args[0] if args else ""
        if element not in FUNDAMENTAL:
            raise UnsupportedClass(
                f"{cls}: element type {element!r} is not a fundamental type")
        width = SCALAR_WIDTH[FUNDAMENTAL[element]]
        base = f"TMatrixTBase<{element}>"
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise FormatError(f"{cls} at {offset} has no byte count")
        version, body = self.resolve_version(base, frame)
        members = self.read_members(base, version, body, frame.end)
        shape = {m.name: m for m in members}
        if "fNrows" not in shape or "fNcols" not in shape:
            raise UnsupportedClass(
                f"{base} version {version} has no fNrows/fNcols: "
                f"it cannot describe a symmetric matrix")
        rows = _int_member(self.buf, shape["fNrows"])
        cols = _int_member(self.buf, shape["fNcols"])
        if rows != cols:
            raise FormatError(
                f"{cls} at {offset}: fNrows {rows} != fNcols {cols}, "
                f"and a symmetric matrix is square -- Matrix.md invariant 2")
        if rows < 0:
            raise FormatError(f"{cls} at {offset}: fNrows {rows} is negative")
        stored = rows * (rows + 1) // 2
        end = frame.end + width * stored
        if end > len(self.buf):
            raise FormatError(
                f"{cls} at {offset}: {stored} elements of {width} bytes run "
                f"past the buffer")
        members.append(Value(name="fElements", ftype=FUNDAMENTAL[element] + 20,
                             start=frame.end, end=end, type_name=element,
                             note=f"the upper-right triangle, {stored} of "
                                  f"{rows * cols} elements, outside the byte "
                                  f"count"))
        return Value(name=cls, ftype=61, start=offset, end=end,
                     type_name=cls, members=members)

    def read_roo_linked_list(self, offset: int) -> Value:
        """A RooLinkedList: a bare version word, TObject, a count, then slots.

        `RooLinkedList::Streamer` opens with `WriteVersion(IsA())` and no
        `useBcnt`, so **there is no byte count**: the object begins with its
        version word (root/roofit/roofitcore/src/RooLinkedList.cxx:890-922).
        Then a TObject base, an Int_t size, that many object slots, and a
        TString. The info in the file lists `_hashThresh`, which the streamer
        never writes, and no slots at all. RooFit.md section 3.
        """
        version = _i16(self.buf, offset)
        pos = skip_tobject(self.buf, offset + 2)
        members = [Value(name="TObject", ftype=66, start=offset + 2, end=pos,
                         type_name="TObject")]
        size = _i32(self.buf, pos)
        if size < 0:
            raise FormatError(
                f"RooLinkedList at {offset}: _size {size} is negative")
        members.append(Value(name="_size", ftype=3, start=pos, end=pos + 4,
                             type_name="Int_t"))
        pos += 4
        for _ in range(size):
            slot = read_slot(self.buf, pos, self.base)
            if slot.kind == "object":
                cls, body_at = resolve_class(slot, self.classes)
                self.read_object(cls, body_at)
            members.append(Value(name="element", ftype=64, start=pos,
                                 end=slot.end, type_name=slot.class_name or ""))
            pos = slot.end
        # ROOT reads the trailing TString only when 1 < version < 4, and the
        # write branch has always written it, so a version-1 record, written
        # before the member existed, has none. The info corroborates this: the
        # RooLinkedList info in stressRooFit_v522_ref.root lists TObject,
        # _hashThresh and _size, and no _name.
        if 1 < version < 4:
            _, end = _counted_string(self.buf, pos)
            members.append(Value(name="_name", ftype=65, start=pos, end=end,
                                 type_name="TString"))
            pos = end
        return Value(name="RooLinkedList", ftype=61, start=offset, end=pos,
                     type_name="RooLinkedList", members=members)

    def read_roo_real_var(self, offset: int) -> Value:
        """A RooRealVar: its base, three doubles, a binning, and a tail.

        `RooRealVar::Streamer` never calls ReadClassBuffer
        (root/roofit/roofitcore/src/RooRealVar.cxx:1252-1308), so no info for
        the class is written at all. The frame it opens with
        `WriteVersion(IsA(), true)` has a byte count, and
        `SetByteCount(R__c, true)` closes it after the tail, so the object can
        be skipped by its byte count; only decoding it needs this.
        RooFit.md section 2.
        """
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise FormatError(f"RooRealVar at {offset} has no byte count")
        version = frame.version
        base = self.read_object("RooAbsRealLValue", frame.body)
        members = [base]
        pos = base.end
        if version == 1:
            # The version-1 shape: the binning was three loose fields, read
            # before the errors rather than after them.
            for name, ftype, width in (("fitMin", 8, 8), ("fitMax", 8, 8),
                                       ("fitBins", 3, 4)):
                members.append(Value(name=name, ftype=ftype, start=pos,
                                     end=pos + width, type_name="Double_t"))
                pos += width
        for name in ("_error", "_asymErrLo", "_asymErrHi"):
            members.append(Value(name=name, ftype=8, start=pos, end=pos + 8,
                                 type_name="Double_t"))
            pos += 8
        if version >= 2:
            pos = self.read_pointer_member(members, "_binning", pos)
        if version == 3:
            # At version 3 alone the shared properties were a pointer.
            pos = self.read_pointer_member(members, "_sharedProp", pos)
        elif version >= 4:
            # From version 4 they are written in place, by calling the object's
            # own Streamer. No streamer info describes this part, and it is
            # inside the byte count.
            tail = self.read_object("RooRealVarSharedProperties", pos)
            tail.name = "_sharedProp"
            members.append(tail)
            pos = tail.end
        if pos != frame.end:
            raise FormatError(
                f"RooRealVar v{version} at {offset} ends at {pos}, "
                f"but its byte count says {frame.end}")
        return Value(name="RooRealVar", ftype=61, start=offset, end=frame.end,
                     type_name="RooRealVar", members=members)

    def read_roo_abs_binning(self, offset: int) -> Value:
        """A RooAbsBinning base: a frame, a TNamed, and RooPrintable.

        Its `Streamer` writes a TNamed where its own class declares none, and
        at version 1 wrote a bare TObject instead
        (root/roofit/roofitcore/src/RooAbsBinning.cxx:117-137). No info for it
        is written, so every concrete binning in a file has a `kBase` element
        naming a class the file does not describe. RooFit.md section 4.
        """
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise FormatError(f"RooAbsBinning at {offset} has no byte count")
        if frame.version == 1:
            end = skip_tobject(self.buf, frame.body)
            members = [Value(name="TObject", ftype=66, start=frame.body,
                             end=end, type_name="TObject")]
        else:
            named = self.read_object("TNamed", frame.body)
            members, end = [named], named.end
        printable = self.read_object("RooPrintable", end)
        members.append(printable)
        if printable.end != frame.end:
            raise FormatError(
                f"RooAbsBinning v{frame.version} at {offset} ends at "
                f"{printable.end}, but its byte count says {frame.end}")
        return Value(name="RooAbsBinning", ftype=61, start=offset,
                     end=frame.end, type_name="RooAbsBinning", members=members)

    def read_roo_category(self, offset: int) -> Value:
        """A RooCategory. Streamer-info driven at version 3 and above only.

        Below that its `Streamer` hand-writes the base and then a
        RooCategorySharedProperties, as an object slot at version 1 and as an
        embedded object at version 2
        (root/roofit/roofitcore/src/RooCategory.cxx:431-455). Neither is in any
        streamer info: the class's own info lists the base and, from version 3,
        `_rangesPointerForIO`. RooFit.md section 5.
        """
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise FormatError(f"RooCategory at {offset} has no byte count")
        if frame.version >= 3:
            version, body = self.resolve_version("RooCategory", frame)
            members = self.read_members("RooCategory", version, body, frame.end)
            return Value(name="RooCategory", ftype=61, start=offset,
                         end=frame.end, type_name="RooCategory",
                         members=members)
        base = self.read_object("RooAbsCategoryLValue", frame.body)
        members = [base]
        if frame.version == 1:
            pos = self.read_pointer_member(members, "_sharedProp", base.end)
        else:
            tail = self.read_object("RooCategorySharedProperties", base.end)
            tail.name = "_sharedProp"
            members.append(tail)
            pos = tail.end
        if pos != frame.end:
            raise FormatError(
                f"RooCategory v{frame.version} at {offset} ends at {pos}, "
                f"but its byte count says {frame.end}")
        return Value(name="RooCategory", ftype=61, start=offset, end=frame.end,
                     type_name="RooCategory", members=members)

    def read_roo_ref_array(self, offset: int) -> Value:
        """A RooRefArray: its own frame, and then a TRefArray inside it.

        `RooRefArray::Streamer` builds a temporary TRefArray and streams that
        (root/roofit/roofitcore/src/RooAbsArg.cxx:2195-2228), so the bytes are
        a TRefArray's with one more frame around them, and the class it derives
        from, TObjArray, never appears. RooFit.md section 4.
        """
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise FormatError(f"RooRefArray at {offset} has no byte count")
        array = read_ref_array(self.buf, frame.body)
        if array.end != frame.end:
            raise FormatError(
                f"RooRefArray at {offset}: the TRefArray inside it ends at "
                f"{array.end}, but the byte count says {frame.end}")
        inner = Value(name="TRefArray", ftype=61, start=frame.body,
                      end=array.end, type_name="TRefArray")
        return Value(name="RooRefArray", ftype=61, start=offset, end=frame.end,
                     type_name="RooRefArray", members=[inner])

    def read_pointer_member(self, members: list, name: str, offset: int) -> int:
        """One object slot written by `buffer << pointer`, appended to members."""
        slot = read_slot(self.buf, offset, self.base)
        nested = None
        cls = slot.class_name or ""
        if slot.kind == "object":
            cls, body_at = resolve_class(slot, self.classes)
            nested = self.read_in_slot(cls, body_at, slot.end).members
        members.append(Value(name=name, ftype=64, start=offset, end=slot.end,
                             type_name=cls, members=nested,
                             note="" if slot.kind == "object" else slot.kind))
        return slot.end

    #: The fields TCanvas writes after its TPad base, in order, as
    #: (name, element code, width). Canvas.md section 2. `fCatt` is a framed
    #: TAttCanvas and `fDISPLAY` a counted string, so both are handled apart.
    CANVAS_TAIL = (
        ("fDoubleBuffer", 3, 4), ("fRetained", 18, 1),
        ("fXsizeUser", 5, 4), ("fYsizeUser", 5, 4),
        ("fXsizeReal", 5, 4), ("fYsizeReal", 5, 4),
        ("fWindowTopX", 3, 4), ("fWindowTopY", 3, 4),
        ("fWindowWidth", 13, 4), ("fWindowHeight", 13, 4),
        ("fCw", 13, 4), ("fCh", 13, 4),
    )

    #: What follows fCatt: five bits of fBits written as separate bytes, with
    #: fHighLightColor and a discarded fBatch among them. Canvas.md 2.1.
    CANVAS_BITS = (
        ("kMoveOpaque", 18, 1), ("kResizeOpaque", 18, 1),
        ("fHighLightColor", 2, 2), ("fBatch", 18, 1),
        ("kShowEventStatus", 18, 1), ("kAutoExec", 18, 1),
        ("kMenuBar", 18, 1),
    )

    #: What TBranchClones::Streamer writes after the TNamed, in order. Ten of
    #: TBranch's fields, hand-picked: it derives from TBranch and never streams a
    #: TBranch base. TBranchElement.md 12.1.
    BRANCH_CLONES_FIELDS = (
        ("fCompress", 3, 4), ("fBasketSize", 3, 4), ("fEntryOffsetLen", 3, 4),
        ("fMaxBaskets", 3, 4), ("fWriteBasket", 3, 4),
        ("fEntryNumber", 16, 8), ("fEntries", 16, 8), ("fTotBytes", 16, 8),
        ("fZipBytes", 16, 8), ("fOffset", 3, 4),
    )

    def read_branch_clones(self, offset: int) -> Value:
        """A TBranchClones. TBranchElement.md 12.1.

        No file has a streamer info for it, so this is the only way to read one,
        as with TBasket and TTreeIndex.
        """
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise FormatError(f"TBranchClones at {offset} has no byte count")
        named = self.read_object("TNamed", frame.body)
        members = [named]
        at = named.end
        for name, code, width in self.BRANCH_CLONES_FIELDS:
            members.append(Value(name=name, ftype=code, start=at,
                                 end=at + width))
            at += width
        count = read_slot(self.buf, at, self.base)
        nested = None
        if count.kind == "object":
            # The slot must be READ, not skipped. It holds a complete TBranch,
            # and the classes that object declares (TBranch itself, TLeafI,
            # TLeaf) are referenced by position from the sub-branches in
            # fBranches (Buffer.md 5.2). Skipping the body leaves those
            # references unresolvable; an earlier version made that mistake.
            name, body = resolve_class(count, self.classes)
            nested = self.read_object(name, body)
            if nested.end != count.end:
                raise FormatError(
                    f"fBranchCount at {at}: {name} consumed "
                    f"{nested.end - body} bytes, slot says {count.end - body}")
        members.append(Value(name="fBranchCount", ftype=64, start=at,
                             end=count.end, type_name="TBranch",
                             members=nested.members if nested else None,
                             note=f"object slot: {count.kind}"))
        at = count.end
        _, end = _counted_string(self.buf, at)
        members.append(Value(name="fClassName", ftype=65, start=at, end=end,
                             type_name="TString"))
        branches = self.read_object("TObjArray", end)
        members.append(Value(name="fBranches", ftype=61, start=end,
                             end=branches.end, type_name="TObjArray",
                             members=branches.members))
        if branches.end != frame.end:
            raise FormatError(
                f"TBranchClones at {offset} consumed "
                f"{branches.end - offset} bytes, byte count says "
                f"{frame.end - offset}")
        return Value(name="TBranchClones", ftype=61, start=offset,
                     end=frame.end, type_name="TBranchClones",
                     members=members)

    #: The scalars TBranch::Streamer reads below class version 10, in order
    #: (root/tree/tree/src/TBranch.cxx:3035-3059), as (name, element code,
    #: width). fEntries, fTotBytes and fZipBytes are Stat_t (a double) and
    #: fEntryNumber is an Int_t; both widen at version 10. TBranch.md 13.1.
    LEGACY_BRANCH_SCALARS = (
        ("fCompress", 3, 4), ("fBasketSize", 3, 4), ("fEntryOffsetLen", 3, 4),
        ("fWriteBasket", 3, 4), ("fEntryNumber", 3, 4), ("fOffset", 3, 4),
        ("fMaxBaskets", 6, 4),
    )

    def read_legacy_branch(self, version: int, offset: int,
                           limit: int | None) -> list[Value]:
        """A TBranch below class version 10. TBranch.md 13.1.

        The member order is taken from TBranch::Streamer rather than from the
        file's streamer info. The two agree element for element on every legacy
        file measured, which is a measurement rather than a guarantee a reader
        should rely on (TBranch.md 13.1). They disagree at version 9 about the
        width of fBasketSeek, where the source is right and the info is not
        (13.3).
        """
        buf = self.buf
        values: list[Value] = []
        pos = offset
        named = self.read_object("TNamed", pos)
        values.append(Value(name="TNamed", ftype=67, start=pos, end=named.end,
                            type_name="TNamed", members=named.members))
        pos = named.end
        if version > 7:
            fill = self.read_object("TAttFill", pos)
            values.append(Value(name="TAttFill", ftype=0, start=pos,
                                end=fill.end, type_name="TAttFill",
                                members=fill.members))
            pos = fill.end
        fields = list(self.LEGACY_BRANCH_SCALARS)
        if version > 6:
            fields.append(("fSplitLevel", 3, 4))
        fields += [("fEntries", 8, 8), ("fTotBytes", 8, 8), ("fZipBytes", 8, 8)]
        max_baskets = 0
        for name, code, width in fields:
            values.append(Value(name=name, ftype=code, start=pos,
                                end=pos + width))
            if name == "fMaxBaskets":
                max_baskets = _i32(buf, pos)
            pos += width
        for name in ("fBranches", "fLeaves", "fBaskets"):
            array = self.read_object("TObjArray", pos)
            values.append(Value(name=name, ftype=61, start=pos, end=array.end,
                                type_name="TObjArray", members=array.members))
            pos = array.end
        if max_baskets < 0:
            raise FormatError(
                f"TBranch v{version} at {offset} has fMaxBaskets {max_baskets}")
        for name in ("fBasketBytes", "fBasketEntry", "fBasketSeek"):
            # All three are read unconditionally, whatever the flag byte says:
            # the legacy streamer reads fMaxBaskets values after it and only
            # fBasketSeek gives the byte a meaning, 2 for 8-byte values and any
            # other value for 4-byte ones (root/tree/tree/src/TBranch.cxx:3055-3066).
            flag = buf[pos]
            width = 8 if (name == "fBasketSeek" and flag == 2) else 4
            end = pos + 1 + max_baskets * width
            values.append(Value(
                name=name, ftype=OFFSET_P + (16 if width == 8 else 3),
                start=pos, end=end, type_name="Int_t",
                note=f"flag byte {flag}: {max_baskets} value(s) of {width} bytes"))
            pos = end
        _, end = _counted_string(buf, pos)
        values.append(Value(name="fFileName", ftype=65, start=pos, end=end,
                            type_name="TString"))
        pos = end
        if limit is not None and pos != limit:
            raise FormatError(
                f"TBranch v{version} consumed {pos - offset} bytes, "
                f"byte count says {limit - offset}")
        return values

    def read_tcanvas(self, offset: int) -> Value:
        """A TCanvas. Canvas.md sections 1 and 2.

        Class versions below 4 are refused rather than guessed: v <= 2 omits
        fWindowWidth and fWindowHeight, v <= 3 omits kAutoExec, and v < 2 stops
        after fBatch (root/graf2d/gpad/src/TCanvas.cxx:2303-2357). No file here
        contains one, and a refusal is safer than an untested branch.
        """
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise FormatError(f"TCanvas at {offset} has no byte count")
        if frame.version < 4:
            raise UnsupportedClass(
                f"TCanvas class version {frame.version}: Canvas.md 5 records "
                f"the layout, no reference file has one")

        members = [self.read_object("TPad", frame.body)]
        at = members[0].end
        _, end = _counted_string(self.buf, at)
        members.append(Value(name="fDISPLAY", ftype=65, start=at, end=end,
                             type_name="TString"))
        at = end
        for name, code, width in self.CANVAS_TAIL:
            members.append(Value(name=name, ftype=code, start=at,
                                 end=at + width))
            at += width
        catt = self.read_object("TAttCanvas", at)
        members.append(Value(name="fCatt", ftype=61, start=at, end=catt.end,
                             type_name="TAttCanvas", members=catt.members))
        at = catt.end
        for name, code, width in self.CANVAS_BITS:
            members.append(Value(name=name, ftype=code, start=at,
                                 end=at + width))
            at += width
        if at != frame.end:
            raise FormatError(
                f"TCanvas at {offset} consumed {at - offset} bytes, byte count "
                f"says {frame.end - offset}")
        return Value(name="TCanvas", ftype=61, start=offset, end=frame.end,
                     type_name="TCanvas", members=members)

    def resolve_version(self, cls: str, frame: Frame) -> tuple[int, int]:
        """Apply the version-0 rule of Buffer.md section 4.

        A version word of 0 is followed by a checksum for a foreign class and by
        nothing for a class that declares version 0. Nothing in the stream says
        which, so the file's own streamer info is used: an entry with
        fClassVersion == 0 means no checksum follows.
        """
        if frame.version > 0:
            return frame.version, frame.body
        by_version = self.infos.get(cls, {})
        if 0 in by_version:
            return 0, frame.body
        if not by_version:
            raise UnsupportedClass(
                f"version word 0 for {cls}, which has no streamer info here")
        checksum = _u32(self.buf, frame.body)
        for version, info in by_version.items():
            if info.checksum == checksum:
                return version, frame.body + 4
        raise FormatError(
            f"version word 0 for {cls} with checksum {checksum:#x}, "
            f"which matches no streamer info in this file")

    def read_members(self, cls: str, version: int, offset: int,
                     limit: int | None,
                     counters: dict[str, int] | None = None) -> list[Value]:
        """The element loop of StreamerDriven.md section 3.

        `counters` is shared with the object's base classes, because a counted
        pointer may name a counter declared in a base (ElementTypes.md 4.1).
        """
        if cls == "TObject":
            base = read_tobject(self.buf, offset)
            return [Value(name="TObject", ftype=66, start=offset, end=base.end,
                          tobject=base)]
        if cls == "TBranch" and version < 10:
            return self.read_legacy_branch(version, offset, limit)
        info = self.info_for(cls, version)
        values: list[Value] = []
        pos = offset
        if counters is None:
            counters = {}
        for el in info.elements:
            try:
                value = self.read_element_value(el, pos, counters)
            except UnsupportedClass as exc:
                # Skip just this member, by its byte count, and keep reading the
                # rest of the object. StreamerDriven.md section 8.
                if not self.tolerant:
                    raise
                frame = read_frame(self.buf, pos)
                if frame.end is None:
                    raise
                self.unread.append((str(exc), pos))
                value = Value(name=el.name, ftype=el.ftype, start=pos,
                              end=frame.end, type_name=el.type_name,
                              note=f"unread: {exc}")
            if el.ftype == 6:                 # kCounter: retain it for later
                counters[el.name] = _i32(self.buf, pos)
            values.append(value)
            pos = value.end
        if limit is not None and pos != limit:
            raise FormatError(
                f"{cls} v{version} consumed {pos - offset} bytes, "
                f"byte count says {limit - offset}")
        return values

    def read_elements(self, info, offset: int,
                      counters: dict[str, int] | None = None) -> int:
        """Every element of `info` in order, with no class-level framing.

        read_members with the streamer info already chosen and no byte count to
        check against, for an unsplit branch's entry (ReadingEntries.md 3.3):
        the members' own serialisations concatenated, with no byte count and no
        version word for the branch's class.
        """
        pos = offset
        if counters is None:
            counters = {}
        for el in info.elements:
            value = self.read_element_value(el, pos, counters)
            if el.ftype == 6:                 # kCounter: retain it for later
                counters[el.name] = _i32(self.buf, pos)
            pos = value.end
        return pos

    # -- elements ---------------------------------------------------------

    def read_element_value(self, el: Element, offset: int,
                           counters: dict[str, int]) -> Value:
        t = el.ftype
        buf = self.buf

        def done(end, **kw):
            kw.setdefault("type_name", el.type_name)
            return Value(name=el.name, ftype=t, start=offset, end=end, **kw)

        if t == -1:                                   # kNoType: nothing at all
            return done(offset)

        if t == 0:                                    # kBase
            nested = self.read_object(el.name, offset, counters)
            return done(nested.end, members=nested.members)

        if t == 66:                                   # kTObject: no byte count
            base = read_tobject(buf, offset)
            return done(base.end, tobject=base)

        if t == 67:                                   # kTNamed
            nested = self.read_object("TNamed", offset)
            return done(nested.end, members=nested.members)

        if t == 65:                                   # kTString: bare, unframed
            _, end = _counted_string(buf, offset)
            return done(end)

        if t == 7:                                    # kCharStar: i32 then n bytes
            n = _i32(buf, offset)
            return done(offset + 4 + max(n, 0))

        if t in SCALAR_WIDTH:
            return done(offset + SCALAR_WIDTH[t])

        if t in (9, 19):                              # kDouble32 / kFloat16
            return done(offset + quantised_width(t, el.title))

        if OFFSET_L <= t < OFFSET_P:                  # fixed C array of a scalar
            inner = t - OFFSET_L
            n = el.array_length
            if inner in SCALAR_WIDTH:
                return done(offset + n * SCALAR_WIDTH[inner])
            if inner in (9, 19):
                return done(offset + n * quantised_width(inner, el.title))
            raise UnsupportedClass(f"array of type code {inner}")

        if OFFSET_L + 61 <= t <= OFFSET_L + 71:       # fixed C array of objects
            inner = t - OFFSET_L
            if inner in (61, 62):                     # 81, 82: no outer framing
                pos = offset
                for _ in range(el.array_length):
                    pos = self.read_object(_bare_class(el.type_name), pos).end
                return done(pos)
            if inner in (65, 66, 67):                 # 85, 86, 87: bc ver, then n
                frame = read_frame(buf, offset)
                if frame.end is None:
                    raise FormatError(f"array element {el.name} has no byte count")
                return done(frame.end)
            raise UnsupportedClass(f"array of type code {inner}")

        if OFFSET_P <= t < 60:                        # counted pointer
            inner = t - OFFSET_P
            if buf[offset] == 0:
                return done(offset + 1)               # absent: one byte, no more
            count = counters.get(el.count_name)
            if count is None:
                raise FormatError(
                    f"{el.name} names counter {el.count_name!r}, not yet seen")
            n = max(el.array_length, 1) * count
            if inner in SCALAR_WIDTH:
                return done(offset + 1 + n * SCALAR_WIDTH[inner])
            if inner in (9, 19):
                return done(offset + 1 + n * quantised_width(inner, el.title))
            raise UnsupportedClass(f"counted pointer of type code {inner}")

        # 63, 64, 68 and 69 never gain kOffsetL: a fixed array of them keeps the
        # scalar code and says its length in fArrayLength instead
        # (ElementTypes.md 7.2). Take the count from fArrayLength, never from
        # whether the code carries kOffsetL.
        if t in (61, 62, 63, 68):                     # embedded or `->` pointer
            pos, members = offset, None
            for _ in range(max(el.array_length, 1)):
                nested = self.read_object(_bare_class(el.type_name), pos)
                pos, members = nested.end, nested.members
            return done(pos, members=members)

        if t in (64, 69):                             # pointer with a class record
            pos, note, cls, members = offset, None, None, None
            for _ in range(max(el.array_length, 1)):
                slot = read_slot(buf, pos, self.base)
                pos = slot.end
                if slot.kind == "null":
                    note = "null"
                    continue
                if slot.kind == "reference":
                    note = f"reference to {slot.reference}"
                    continue
                cls, body_at = resolve_class(slot, self.classes)
                # Go through read_object, not read_members, so that a class with a
                # hand-written reader here (TList, TObjArray, TClonesArray) gets
                # it. Reading TList through its streamer info instead produces a
                # TSeqCollection base that its streamer never writes: the divergence
                # of StreamerDriven.md section 7, in a real file.
                nested = self.read_in_slot(cls, body_at, slot.end)
                members = nested.members
            if cls is None:
                return done(pos, note=note)
            return done(pos, type_name=cls, members=members)

        if t == 500 and el.cls in ("TStreamerSTL", "TStreamerSTLstring"):
            end = self.read_collection(el, offset)
            return done(end)

        if t == 501:                                  # kStreamLoop
            frame = read_frame(buf, offset)
            if frame.end is None:
                raise FormatError(f"element {el.name} type 501 has no byte count")
            count = counters.get(el.count_name)
            if count is None:
                raise FormatError(
                    f"{el.name} names counter {el.count_name!r}, not yet seen")
            # No length is written: the counter is the only source (ElementTypes.md
            # 8). A counter of 0 writes the frame and nothing else, so the loop
            # below does not run. Two stars in the type name mean object slots
            # rather than bare objects.
            slots = "**" in el.type_name
            cls = _bare_class(el.type_name)
            pos = frame.body
            for _ in range(max(el.array_length, 1)):
                for _ in range(count):
                    if slots:
                        slot = read_slot(buf, pos, self.base)
                        if slot.kind == "object":
                            name, body_at = resolve_class(slot, self.classes)
                            self.read_in_slot(name, body_at, slot.end)
                        pos = slot.end
                    else:
                        pos = self.read_object(cls, pos).end
            if pos != frame.end:
                raise FormatError(
                    f"element {el.name} type 501 ends at {pos}, "
                    f"but its byte count says {frame.end}")
            return done(frame.end)

        if t == 500 or t == 71:                       # a genuine custom streamer
            frame = read_frame(buf, offset)
            if frame.end is None:
                raise FormatError(f"element {el.name} type {t} has no byte count")
            return done(frame.end, note="skipped by byte count")

        raise UnsupportedClass(f"type code {t}")


    def skip_or_fail(self, cls: str, offset: int, exc: Exception):
        """Either skip an unreadable object by its byte count, or re-raise."""
        if not self.tolerant:
            raise exc
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise exc
        self.unread.append((str(exc), offset))
        return Value(name=cls, ftype=61, start=offset, end=frame.end,
                     type_name=cls, note=f"unread: {exc}")

    def read_tarray(self, cls: str, offset: int) -> Value:
        """A TArrayC/S/I/L/L64/F/D. spec/03-classes/TArray.md.

        `fN:i32` then fN values, with no byte count and no version word: the
        shortest hand-written streamer in ROOT, and the reason a kBase element is
        not always framed.
        """
        count = _i32(self.buf, offset)
        if count < 0:
            raise FormatError(f"{cls} at {offset} has fN {count}")
        end = offset + 4 + count * TARRAY_WIDTH[cls]
        return Value(name=cls, ftype=61, start=offset, end=end, type_name=cls)

    def read_sequence(self, cls: str, offset: int) -> Value:
        """A TList, THashList or TObjArray. StreamerInfo.md sections 4 and 5."""
        options = self.SEQUENCES[cls]
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise FormatError(f"{cls} at {offset} has no byte count")
        pos = frame.body
        if frame.version > 2:
            pos = read_tobject(self.buf, pos).end
        if frame.version > 1:
            _, pos = _counted_string(self.buf, pos)
        count = _i32(self.buf, pos)
        pos += 4
        if not options:
            pos += 4                      # fLowerBound
        members = []
        for _ in range(max(count, 0)):
            slot = read_slot(self.buf, pos, self.base)
            if slot.kind == "object":
                name, body = resolve_class(slot, self.classes)
                note, inner_members = "", None
                try:
                    if name == "TBasket":
                        # A basket streamed into this buffer rather than written
                        # as a record: TBasket.md section 4's second shape. It
                        # can only appear here, as an entry of TBranch::fBaskets.
                        note = f"embedded basket, flag {read_embedded_basket(self.buf, body).basket.flag}"
                    else:
                        # Through read_object, so that a class with a reader of
                        # its own (a std::string, a TArray) is dispatched rather
                        # than looked up in the streamer info.
                        inner_members = self.read_object(name, body).members
                except UnsupportedClass as exc:
                    if not self.tolerant:
                        raise
                    self.unread.append((str(exc), slot.offset))
                    note = f"unread: {exc}"
                members.append(Value(name=name, ftype=61, start=slot.offset,
                                     end=slot.end, type_name=name, note=note,
                                     members=inner_members))
            elif slot.kind == "reference":
                members.append(Value(name="", ftype=61, start=slot.offset,
                                     end=slot.end, type_name="",
                                     reference=slot.reference,
                                     note=f"reference to {slot.reference}"))
            pos = slot.end
            if options and frame.version > 3:
                # The option string. Present after *every* entry, empty or not;
                # missing it is the commonest way to desynchronise on a TList.
                n = self.buf[pos]
                pos += 1
                if n == 255 and frame.version > 4:
                    pos += 4 + _i32(self.buf, pos)
                else:
                    pos += n
        if pos != frame.end:
            raise FormatError(
                f"{cls} at {offset} consumed to {pos}, byte count says {frame.end}")
        return Value(name=cls, ftype=61, start=offset, end=frame.end,
                     type_name=cls, members=members)

    # -- TClonesArray -----------------------------------------------------

    # TClonesArray::kBypassStreamer, root/core/cont/inc/TClonesArray.h:37.
    # BIT(12) at class version 4; it was BIT(14) at version 3.
    BYPASS_STREAMER = 0x1000
    BYPASS_STREAMER_V3 = 0x4000

    def read_clones_array(self, offset: int) -> Value:
        """Collections.md section 12. The encoding is a bit in fBits."""
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise FormatError(f"TClonesArray at {offset} has no byte count")
        version = frame.version
        pos = frame.body
        bits = 0
        if version > 2:
            base = read_tobject(self.buf, pos)
            bits, pos = base.bits, base.end
        if version > 1:
            _, pos = _counted_string(self.buf, pos)
        spec, pos = _counted_string(self.buf, pos)
        count = _i32(self.buf, pos)
        pos += 8                       # nobjects, then fLowerBound

        cls, _, text = spec.partition(";")
        if not text.lstrip("-").isdigit():
            raise UnsupportedClass(f"TClonesArray element spec {spec!r}")
        mask = self.BYPASS_STREAMER if version >= 4 else self.BYPASS_STREAMER_V3
        if bits & mask:
            info = self.info_for(cls, int(text))
            for element in info.elements:
                pos = self.read_column(element, count, pos)
        else:
            for _ in range(max(count, 0)):
                present = self.buf[pos]
                pos += 1
                if present:
                    pos = self.read_object(cls, pos).end
        if pos != frame.end:
            raise FormatError(
                f"TClonesArray at {offset} consumed to {pos}, byte count says "
                f"{frame.end}")
        return Value(name="TClonesArray", ftype=61, start=offset, end=frame.end,
                     type_name=cls,
                     note="bypass" if bits & mask else "per-slot flags")

    # -- collections ------------------------------------------------------

    def read_collection(self, el, offset: int) -> int:
        """One TStreamerSTL or TStreamerSTLstring member. Returns the end.

        The frame is `byteCount version`, where version is TStreamerInfo's own
        class version and bit 14 is kStreamedMemberWise (Collections.md 2).
        """
        stl = el.tail.get("fSTLtype", 0)
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise FormatError(f"collection {el.name} has no byte count")
        if stl == STL_BITSET:
            # An ordinary object-wise collection of bool: a count, then one
            # byte per bit, bit 0 first. The bits are not packed and the count
            # is written although the width is in the type name.
            # ReadingEntries.md 3.6.
            pos = self.read_object_wise("bool", STL_VECTOR, frame.body)
            if pos != frame.end:
                raise FormatError(
                    f"bitset {el.name} consumed to {pos}, byte count says "
                    f"{frame.end}")
            return frame.end
        if stl == STL_STRING:
            _, end = _counted_string(self.buf, frame.body)
            if end != frame.end:
                raise FormatError(
                    f"std::string {el.name} ends at {end}, byte count says "
                    f"{frame.end}")
            return frame.end
        if stl >= OFFSET_P:
            raise UnsupportedClass(f"pointer to a collection, fSTLtype {stl}")

        value, stl = collection_value(el)
        # A fixed array of collections shares ONE frame and then repeats the
        # collection fArrayLength times. The stored fType is still 500, and
        # kOffsetL only appears after the read-time recompute of
        # StreamerInfo.md 10, so only fArrayLength indicates it.
        # Collections.md 11.1.
        pos = frame.body
        for _ in range(max(el.array_length, 1)):
            if frame.member_wise:
                self.member_wise.append((el.name, value, offset))
                pos = self.read_member_wise(value, pos, el, frame.version)
            else:
                pos = self.read_object_wise(value, stl, pos)
        if pos != frame.end:
            raise FormatError(
                f"collection {el.name} consumed to {pos}, byte count says "
                f"{frame.end}")
        return frame.end

    def read_object_wise(self, value: str, stl: int, offset: int) -> int:
        """`count`, then each element in full (Collections.md 3)."""
        count = _i32(self.buf, offset)
        pos = offset + 4
        for _ in range(max(count, 0)):
            if stl in PAIRED:
                key, val = template_args(value)
                pos = self.read_value(key, pos)
                pos = self.read_value(val, pos)
            else:
                pos = self.read_value(value, pos)
        return pos

    def read_value(self, name: str, offset: int) -> int:
        """One element of a collection, written in full."""
        if name in FUNDAMENTAL:
            return offset + SCALAR_WIDTH[FUNDAMENTAL[name]]
        bare = name[5:] if name.startswith("std::") else name
        if bare in ("string", "TString"):
            return _counted_string(self.buf, offset)[1]
        if is_collection_name(bare):
            # A nested collection is bare: a count and its elements, with no
            # byte count and no version word of its own.
            inner = value_type_name(bare)
            head = bare[:bare.index("<")]
            stl = STL_MAP if head.endswith("map") else STL_VECTOR
            return self.read_object_wise(inner, stl, offset)
        if bare.endswith("*"):
            return read_slot(self.buf, offset, self.base).end
        return self.read_object(bare, offset).end

    #: Above this collection version an empty member-wise collection writes no
    #: columns at all; at or below it, the columns are written and empty
    #: (root/io/io/src/TStreamerInfoReadBuffer.cxx:1197-1199).
    EMPTY_WRITES_NO_COLUMNS_ABOVE = 6

    def read_member_wise(self, value: str, offset: int, el,
                         collection_version: int = 99) -> int:
        """A second version word, a count, then one column per member.

        `collection_version` is the version on the collection's own frame, not
        the value class's; the empty case below depends on it.
        """
        version, pos = self.resolve_bare_version(value, offset)
        count = _i32(self.buf, pos)
        pos += 4
        if count == 0 and collection_version > self.EMPTY_WRITES_NO_COLUMNS_ABOVE:
            # Nothing follows, not even the empty columns. Byte-verified on an
            # empty map<string,string> in uproot-issue465-flat.root, whose byte
            # count leaves no room for them. Collections.md 4.3.
            return pos
        for element in self.value_info(value, version).elements:
            pos = self.read_column(element, count, pos)
        return pos

    def resolve_bare_version(self, cls: str, offset: int) -> tuple[int, int]:
        """ReadVersionForMemberWise: a Version_t with no byte count.

        As with an ordinary version word, 0 or less is followed by a checksum
        for a foreign class (Buffer.md 4), and the checksum selects the info.
        """
        version = _i16(self.buf, offset)
        if version > 0:
            return version, offset + 2
        checksum = _u32(self.buf, offset + 2)
        for candidate, info in self.infos.get(cls, {}).items():
            if info.checksum == checksum:
                return candidate, offset + 6
        if cls.startswith("pair<"):
            return 0, offset + 6      # synthesised below; the checksum is moot
        raise UnsupportedClass(
            f"member-wise collection of {cls}, whose checksum {checksum:#010x} "
            f"matches no streamer info in this file")

    def value_info(self, cls: str, version: int):
        if cls.startswith("pair<"):
            found = self.pair_info(cls)
            return found if found is not None else synthesise_pair(cls)
        return self.info_for(cls, version)

    def pair_info(self, cls: str) -> "StreamerInfo | None":
        """The file's own info for a pair, matched by NAME, or None.

        By name and not by checksum. The checksum in a member-wise header is
        scoped to the class ROOT has already resolved from the member's declared
        type name, so it need not be unique across pairs, and is not:
        `serialization/pairs` has two distinct pairs sharing one
        (Collections.md 8.2). Names differ only in whitespace between files, so
        they are compared with it removed.
        """
        wanted = cls.replace(" ", "")
        for name, by_version in self.infos.items():
            if name.replace(" ", "") == wanted:
                return max(by_version.values(), key=lambda i: i.class_version)
        return None

    def read_column(self, element, count: int, offset: int,
                    counters: dict[str, int] | None = None) -> int:
        """One member, written `count` times back to back.

        Two things in this specification have that shape and ROOT reads them with
        the same action: a member-wise collection's column (Collections.md 4) and
        a split branch's member column (ReadingEntries.md 3.2). They also share
        the once-per-column header of ReadingEntries.md 5.3, so this cannot be a
        loop over read_element_value for every type.
        """
        t = element.ftype
        width = element_width(element)
        if width is not None:
            return offset + count * width
        if t == 0 and element.cls == "TStreamerBase":
            # A base in array mode is its own info read over the same array:
            # one column per member of the base, and nothing around them
            # (root/io/io/src/TStreamerInfoReadBuffer.cxx:1409-1410). Not the base
            # once per element; the two differ as soon as the base has two
            # members. Collections.md 4.1 and 4.2.
            for member in self.base_info(element).elements:
                offset = self.read_column(member, count, offset)
            return offset
        if OFFSET_L <= t < OFFSET_P:                  # a C array per element
            inner = t - OFFSET_L
            if inner in SCALAR_WIDTH:
                return offset + count * element.array_length * SCALAR_WIDTH[inner]
            if inner in (9, 19):
                return (offset + count * element.array_length
                        * quantised_width(inner, element.title))
        if t == 500 and element.cls in ("TStreamerSTL", "TStreamerSTLstring"):
            return self.read_collection_column(element, count, offset)
        if t == 501:
            # kStreamLoop: a pointer whose length is another member of the class
            # (fCountName). In a split branch that member is a column on a
            # sibling branch, so the per-element lengths are not reachable from
            # here. The column is framed like 5.3's kStreamer case, with one byte
            # count for all of it, so its extent is known even though its
            # contents are not. Byte-verified on uproot-issue433-splitlevel4.root.
            frame = read_frame(self.buf, offset)
            if frame.end is None:
                raise FormatError(f"column {element.name} type 501 has no "
                                  f"byte count")
            return frame.end
        # Everything else is the scalar encoding repeated: the rule of
        # ReadingEntries.md 5.3, to which 5.3's two families are the exceptions.
        pos = offset
        for _ in range(count):
            pos = self.read_element_value(element, pos, counters or {}).end
        return pos

    def read_collection_column(self, el, count: int, offset: int) -> int:
        """`count` collections of one member, under one shared header.

        ReadingEntries.md 5.3. The version word and byte count are read once for
        the whole column rather than once per collection
        (root/io/io/src/TStreamerInfoReadBuffer.cxx:1251-1256), and a member-wise
        column reads the value class's version once as well, outside the loop
        (root/io/io/src/TStreamerInfoReadBuffer.cxx:1271-1274). A reader that
        frames each collection separately desynchronises on the second.
        """
        stl = el.tail.get("fSTLtype", 0)
        frame = read_frame(self.buf, offset)
        if frame.end is None:
            raise FormatError(f"collection column {el.name} has no byte count")
        if stl == STL_BITSET:
            pos = frame.body
            for _ in range(count):
                pos = self.read_object_wise("bool", STL_VECTOR, pos)
            if pos != frame.end:
                raise FormatError(
                    f"bitset column {el.name} consumed to {pos}, byte count "
                    f"says {frame.end}")
            return frame.end
        if stl >= OFFSET_P and stl != STL_STRING:
            raise UnsupportedClass(f"pointer to a collection, fSTLtype {stl}")
        pos = frame.body
        if stl == STL_STRING:
            # A column of std::string: bare counted strings back to back, with
            # no count of their own, since the collection is the string.
            for _ in range(count):
                _, pos = _counted_string(self.buf, pos)
            if pos != frame.end:
                raise FormatError(
                    f"string column {el.name} consumed to {pos}, byte count "
                    f"says {frame.end}")
            return frame.end
        value, stl = collection_value(el)
        if frame.member_wise:
            self.member_wise.append((el.name, value, offset))
            version = 0
            if frame.version >= 8:
                version, pos = self.resolve_bare_version(value, pos)
            info = self.value_info(value, version)
            for _ in range(count):
                n = _i32(self.buf, pos)
                pos += 4
                if n == 0 and frame.version > self.EMPTY_WRITES_NO_COLUMNS_ABOVE:
                    continue          # as above: an empty one writes no columns
                for member in info.elements:
                    pos = self.read_column(member, max(n, 0), pos)
        else:
            for _ in range(count):
                pos = self.read_object_wise(value, stl, pos)
        if pos != frame.end:
            raise FormatError(
                f"collection column {el.name} consumed to {pos}, byte count "
                f"says {frame.end}")
        return frame.end


def basket_value(buf: bytes, rec: Record, data: bytes) -> Value:
    """A basket record as a Value, so the probe and the checkers can treat it
    like any other record. A basket is not a serialized object: its payload is
    entry data plus an optional offset array, so the Value's members are the
    entries. spec/04-ttree/TBasket.md."""
    basket = read_basket(buf, rec, data)
    start, end = payload_range(rec)
    members = []
    for index in range(basket.nev_buf):
        lo, hi = basket_entry_range(rec, basket, index)
        members.append(Value(name=f"entry{index}", ftype=0, start=lo, end=hi))
    return Value(name="TBasket", ftype=61, start=start, end=end,
                 type_name="TBasket", members=members,
                 note=f"{basket.nev_buf} entries, "
                      f"{'offsets' if basket.has_offsets else 'fixed width'}")


def decode_record_verbose(buf: bytes, rec: Record, infos: list[StreamerInfo],
                          tolerant: bool = False) -> tuple[Decoder, Value | None]:
    """decode_record, but hand back the Decoder even when the read fails.

    A checker needs what the decoder saw on the way to the failure, notably
    which collections were member-wise, which only the data records.
    """
    start, end = payload_range(rec)
    decoder = Decoder(buf, rec.offset, infos, tolerant=tolerant)
    if rec.class_name == "TBasket":
        try:
            return decoder, basket_value(buf, rec, buf)
        except (FormatError, struct.error, IndexError, ValueError):
            return decoder, None
    try:
        value = decoder.read_object(rec.class_name, start)
    except (FormatError, struct.error, IndexError, ValueError):
        return decoder, None
    if value.end != end:
        return decoder, None
    return decoder, value


def decode_record(buf: bytes, rec: Record, infos: list[StreamerInfo]) -> Value:
    """Apply the streamer-driven read to one uncompressed record's object data.

    Raises UnsupportedClass when the record's class has a hand-written Streamer.
    """
    start, end = payload_range(rec)
    decoder = Decoder(buf, rec.offset, infos)
    value = decoder.read_object(rec.class_name, start)
    if value.end != end:
        raise FormatError(
            f"{rec.class_name} consumed {value.end - start} bytes of {end - start}")
    return value


def walk(value: Value):
    """Every Value in a decoded tree, depth first."""
    yield value
    for member in value.members or ():
        yield from walk(member)


@dataclass
class RefArray:
    """A TRefArray record payload (References.md section 4)."""

    version: int
    tobject: TObjectBase
    name: str
    nobjects: int
    lower_bound: int
    pidf: int
    uids: list[int]
    end: int


def read_ref_array(buf: bytes, offset: int) -> RefArray:
    frame = read_frame(buf, offset)
    base = read_tobject(buf, frame.body)
    name, o = _counted_string(buf, base.end)
    nobjects = _i32(buf, o)
    lower_bound = _i32(buf, o + 4)
    pidf = _u16(buf, o + 8)
    o += 10
    uids = [_u32(buf, o + 4 * i) for i in range(max(nobjects, 0))]
    return RefArray(version=frame.version, tobject=base, name=name,
                    nobjects=nobjects, lower_bound=lower_bound, pidf=pidf,
                    uids=uids, end=o + 4 * max(nobjects, 0))


HAS_UUID = 0x20          # TObject::kHasUUID, BIT(5)
TREF_EXEC_SHIFT = 16     # the TExec index occupies fBits 16-23


def ref_exec_id(bits: int) -> int:
    """The TExec index in a TRef's fBits, 0 when there is none.

    References.md 3.2. TRef::SetAction stores 1 + the index into the list of
    execs, so 0 means no action and the number is one-based.
    """
    return (bits >> TREF_EXEC_SHIFT) & 0xFF


def read_ref(buf: bytes, offset: int) -> TObjectBase:
    """A TRef payload: the TObject layout, with a pidf written unconditionally.

    TRef has no byte count and no version word of its own, and its fBits never
    has kIsReferenced set, so read_tobject would stop two bytes early.

    When fBits has kHasUUID set the trailing u16 is a counted string instead
    (References.md 3.1), the payload is no longer 12 bytes, and there is no
    pidf: `pidf` is None on the returned value.
    """
    version = _i16(buf, offset)
    unique_id = _u32(buf, offset + 2)
    bits = _u32(buf, offset + 6)
    if bits & HAS_UUID:      # kHasUUID: a counted string, not a pidf
        _, end = _counted_string(buf, offset + 10)
        return TObjectBase(version, unique_id, bits, None, end)
    return TObjectBase(version, unique_id, bits, _u16(buf, offset + 10),
                       offset + 12)


def read_streamer_info_entries(buf: bytes, rec: Record) -> list[tuple[str, Slot]]:
    """Every entry of the StreamerInfo record's TList, as (class name, slot).

    SchemaEvolution.md section 6.1: the list is not purely TStreamerInfo. It can
    hold one further entry, a nested TList named "listOfRules".
    """
    entries: list[tuple[str, Slot]] = []
    classes: dict[int, str] = {}
    for slot in read_tlist(buf, rec):
        if slot.kind != "object":
            continue
        cls, _ = resolve_class(slot, classes)
        entries.append((cls, slot))
    return entries


def read_rule_list(buf: bytes, rec: Record, slot: Slot) -> tuple[str, list[str]]:
    """A nested TList of TObjString. Returns (fName, the rule texts).

    Used for the listOfRules entry of SchemaEvolution.md section 6.
    """
    classes: dict[int, str] = {}
    cls, body = resolve_class(slot, classes)
    frame = read_frame(buf, body)
    o = read_tobject(buf, frame.body).end
    name, o = _counted_string(buf, o)
    count = _i32(buf, o)
    o += 4
    rules: list[str] = []
    for _ in range(count):
        entry = read_slot(buf, o, rec.offset)
        entry_cls, entry_body = resolve_class(entry, classes)
        if entry_cls != "TObjString":
            raise FormatError(f"{name} holds a {entry_cls}, not a TObjString")
        inner = read_frame(buf, entry_body)
        text, _ = _counted_string(buf, read_tobject(buf, inner.body).end)
        rules.append(text)
        o = entry.end
        o += 1 + buf[o]          # the list entry's option string
    return name, rules


# ---------------------------------------------------------------------------
# STL collections (spec/02-serialization/Collections.md).
# ---------------------------------------------------------------------------

# ROOT::ESTLType, root/core/foundation/inc/ESTLType.h.
STL_VECTOR, STL_LIST, STL_DEQUE = 1, 2, 3
STL_MAP, STL_MULTIMAP, STL_SET, STL_MULTISET = 4, 5, 6, 7
STL_BITSET, STL_FORWARD_LIST = 8, 9
STL_UNORDERED_SET, STL_UNORDERED_MULTISET = 10, 11
STL_UNORDERED_MAP, STL_UNORDERED_MULTIMAP = 12, 13
STL_RVEC = 14
STL_STRING = 365

PAIRED = {STL_MAP, STL_MULTIMAP, STL_UNORDERED_MAP, STL_UNORDERED_MULTIMAP}

# Type names as they appear in fTypeName, mapped to element type codes.
FUNDAMENTAL = {
    "bool": 18, "char": 1, "signed char": 1, "unsigned char": 11,
    "short": 2, "unsigned short": 12, "int": 3, "unsigned int": 13,
    "long": 4, "unsigned long": 14, "long long": 16,
    "unsigned long long": 17, "float": 5, "double": 8,
    "Bool_t": 18, "Char_t": 1, "UChar_t": 11, "Short_t": 2, "UShort_t": 12,
    "Int_t": 3, "UInt_t": 13, "Long_t": 4, "ULong_t": 14,
    "Long64_t": 16, "ULong64_t": 17, "Float_t": 5, "Double_t": 8,
}

COLLECTION_PREFIXES = ("vector<", "list<", "deque<", "set<", "multiset<",
                       "map<", "multimap<", "forward_list<", "bitset<",
                       "unordered_set<", "unordered_multiset<",
                       "unordered_map<", "unordered_multimap<")


def template_args(name: str) -> list[str]:
    """The top-level template arguments of a type name, as text."""
    start = name.index("<")
    depth = 0
    args: list[str] = []
    current = ""
    for ch in name[start + 1:]:
        if ch == ">" and depth == 0:
            break
        if ch == "," and depth == 0:
            args.append(current.strip())
            current = ""
            continue
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        current += ch
    args.append(current.strip())
    return [a for a in args if a]


def is_collection_name(name: str) -> bool:
    bare = name.strip()
    if bare.startswith("std::"):
        bare = bare[5:]
    return bare.startswith(COLLECTION_PREFIXES)


def value_type_name(type_name: str) -> str:
    """The element type of a sequence, or `pair<K,V>` for an associative one."""
    bare = type_name.strip().rstrip("*").strip()
    if bare.startswith("std::"):
        bare = bare[5:]
    if "<" not in bare:
        # A class with a collection proxy of its own, named by itself: its
        # value type is in a This element's title, which collection_value reads
        # before this is reached (Collections.md 11.2).
        raise UnsupportedClass(
            f"{type_name} is not a container name this specification knows "
            f"(Collections.md 1)")
    args = template_args(bare)
    head = bare[:bare.index("<")]
    if head in ("map", "multimap", "unordered_map", "unordered_multimap"):
        return f"pair<{args[0]},{args[1]}>"
    return args[0]


def collection_value(el: Element) -> tuple[str, int]:
    """`(value type, fSTLtype to read it as)` for a TStreamerSTL element.

    From `fTypeName` for an ordinary collection member. A `This` element is
    different: it is the entire info of a class that has a collection proxy of
    its own (ATLAS's `DataVector`), and its type name is that class, with no
    template argument. TStreamerInfo::Build records the value class in
    the element's **title** instead, as `<Value>` or `<Value*>`
    (root/io/io/src/TStreamerInfo.cxx:421-429), and without a dictionary ROOT
    reads it back from there and emulates a `vector` of it, whatever fSTLtype
    says (root/io/io/src/TStreamerInfo.cxx:1000-1024). Collections.md 11.2.
    """
    if el.name != "This" or is_collection_name(el.type_name):
        # An STL class's own info has a This element too (`map<string,double>`
        # stored as a branch of its own), and ROOT builds its proxy from the
        # name, consulting the title only when there is none
        # (root/io/io/src/TStreamerInfo.cxx:1002-1003), so the name is used here.
        return value_type_name(el.type_name), el.tail.get("fSTLtype", 0)
    if el.title.startswith("<"):
        level = 0
        for i, c in enumerate(el.title):
            level += (c == "<") - (c == ">")
            if level == 0:
                return el.title[1:i].strip(), STL_VECTOR
        raise FormatError(f"unbalanced title on a This element: {el.title!r}")
    raise UnsupportedClass(
        f"{el.type_name} has a collection proxy and its This element does "
        f"not record the value class; ROOT reads no data (Collections.md 11.2)")


#: Collection head name to fSTLtype. Collections.md section 1.
STL_KINDS = {
    "vector": STL_VECTOR, "list": STL_LIST, "deque": STL_DEQUE,
    "map": STL_MAP, "multimap": STL_MULTIMAP,
    "set": STL_SET, "multiset": STL_MULTISET,
    "bitset": STL_BITSET, "forward_list": STL_FORWARD_LIST,
    "unordered_set": STL_UNORDERED_SET,
    "unordered_multiset": STL_UNORDERED_MULTISET,
    "unordered_map": STL_UNORDERED_MAP,
    "unordered_multimap": STL_UNORDERED_MULTIMAP,
    # kROOTRVec: not std:: at all, and spelled in full on disk.
    "ROOT::VecOps::RVec": STL_RVEC,
}


def stl_kind(type_name: str) -> int:
    """The fSTLtype a collection type name would carry. Collections.md 1."""
    bare = type_name.strip()
    if bare.startswith("const "):
        bare = bare[6:].strip()
    if bare.startswith("std::"):
        bare = bare[5:]
    head = bare[:bare.index("<")] if "<" in bare else bare
    if head not in STL_KINDS:
        raise UnsupportedClass(f"unknown collection {type_name}")
    return STL_KINDS[head]


def pair_element(member: str, type_name: str) -> Element:
    """The streamer element a `pair<K,V>` member would have.

    Collections.md section 8.1. The shapes are byte-verified in
    `serialization/pairs`; every one of them is an ordinary element, so the
    column reader needs no special case for a pair.
    """
    def made(cls, ftype, tail=None):
        return Element(cls=cls, version=2, name=member, title="", bits=0,
                       ftype=ftype, fsize=0, array_length=0, array_dim=0,
                       max_index=[0] * 5, type_name=type_name, tail=tail or {})

    bare = type_name.strip()
    if bare in FUNDAMENTAL:
        return made("TStreamerBasicType", FUNDAMENTAL[bare])
    if bare in STD_STRING_NAMES:
        return made("TStreamerSTLstring", 500,
                    {"fSTLtype": STL_STRING, "fCtype": STL_STRING})
    if bare in ("TString", "const TString"):
        return made("TStreamerString", 65)
    if is_collection_name(bare):
        return made("TStreamerSTL", 500, {"fSTLtype": stl_kind(bare), "fCtype": 0})
    if bare.endswith("*"):
        return made("TStreamerObjectAnyPointer", 69)
    return made("TStreamerObjectAny", 62)


def synthesise_pair(name: str) -> StreamerInfo:
    """A streamer info for `pair<K,V>`, built from the type name alone.

    A file may or may not hold one of its own (ROOT's writer is inconsistent
    about it and the corpora have it both ways, Collections.md section 8.1), so
    a reader looks for it first and falls back to this. The layout is always
    `first` then `second`, from the two template arguments.
    """
    key, value = template_args(name)
    elements = [pair_element("first", key), pair_element("second", value)]
    return StreamerInfo(name=name, title="", version=10, bits=0, checksum=0,
                        class_version=0, elements=elements)


# On-disk element width of each concrete TArray. spec/03-classes/TArray.md.
# TArrayL is 8 bytes on disk whatever sizeof(long) is on the writing machine.
TARRAY_WIDTH = {
    "TArrayC": 1, "TArrayS": 2, "TArrayI": 4, "TArrayL": 8,
    "TArrayL64": 8, "TArrayF": 4, "TArrayD": 8,
}


# ---------------------------------------------------------------------------
# Baskets (spec/04-ttree/TBasket.md).
#
# A TBasket is a TKey subclass whose own fields are written inside the key, so
# its header is found by skipping the ordinary key rather than at the payload.
# ---------------------------------------------------------------------------

BASKET_HEADER = 19        # version, four Int_t, and the flag byte
BASKET_HEADER_IOBITS = 20  # the same, plus a UChar_t fIOBits

# TBasket::Streamer's composed flag, root/tree/tree/src/TBasket.cxx:1139-1152.
FLAG_NO_OFFSETS = 2       # flag % 10 == 2: there is no entry-offset array
FLAG_HAS_DATA = 10        # flag == 1 or flag > 10: the entry data follows
FLAG_DISPLACEMENT = 40    # flag > 40: a displacement array follows
FLAG_GENERATE = 80        # flag >= 80: the offsets are to be generated

# TBasket::EIOBits, root/tree/tree/inc/TBasket.h:97-102.
IO_GENERATE_OFFSET_MAP = 0x01
IO_SUPPORTED = IO_GENERATE_OFFSET_MAP
IO_RESERVED = 0x80

# root/tree/tree/src/TBasket.cxx:32. The top byte of an entry offset.
DISPLACEMENT_MASK = 0xFF000000


@dataclass
class Basket:
    """One basket record, parsed. Offsets are absolute file offsets."""

    version: int
    buffer_size: int
    nev_buf_size: int
    nev_buf: int
    last: int             # measured from the start of the RECORD, not the payload
    flag: int
    io_bits: int          # 0 unless fNevBufSize was written negative
    generated: bool       # flag 80: the offsets are not stored, TBasket.md 5.2.1
    key_len: int          # fKeylen: the first entry offset, and where data starts
    header_offset: int    # where the basket's own fields begin, inside the key
    data_start: int       # first entry byte
    data_end: int         # one past the last entry byte
    entry_offsets: list[int] | None    # record-relative, fNevBuf of them
    displacements: list[int] | None = None   # TBasket.md 5.3, fNevBuf of them

    @property
    def has_offsets(self) -> bool:
        return self.entry_offsets is not None


def _standard_key_length(buf: bytes, rec: Record) -> int:
    """The length of the ordinary TKey part: the fixed fields plus three strings."""
    fixed = 34 if rec.key_version > LARGE_KEY_VERSION else 26
    o, total = rec.offset + fixed, fixed
    for _ in range(3):
        n = buf[o]
        if n == 255:
            n = 1 + 4 + _i32(buf, o + 1)
        else:
            n = 1 + n
        o += n
        total += n
    return total


def read_basket(buf: bytes, rec: Record, data: bytes | None = None) -> Basket:
    """Parse a basket record. `data` is the object_data buffer if compressed.

    The header is in the key, which is never compressed, so it is always read from
    `buf`; the entry offsets are in the payload and come from `data`.
    """
    if data is None:
        data = buf
    header = rec.offset + _standard_key_length(buf, rec)
    spare = rec.offset + rec.key_len - header
    if spare not in (BASKET_HEADER, BASKET_HEADER_IOBITS):
        raise FormatError(
            f"basket at {rec.offset}: fKeylen {rec.key_len} leaves {spare} bytes "
            f"for the basket header, which is {BASKET_HEADER} or "
            f"{BASKET_HEADER_IOBITS}")
    version = _i16(buf, header)
    buffer_size = _i32(buf, header + 2)
    # The sign of fNevBufSize is a flag: negative means a UChar_t fIOBits
    # follows, which is how IO features were added without a version bump.
    nev_buf_size = _i32(buf, header + 6)
    o = header + 10
    io_bits = 0
    if nev_buf_size < 0:
        nev_buf_size = -nev_buf_size
        io_bits = buf[o]
        o += 1
        if io_bits == 0 or io_bits & IO_RESERVED:
            raise FormatError(
                f"basket at {rec.offset}: fIOBits {io_bits:#04x} is zero or uses "
                f"the reserved bit 7")
        if io_bits & ~IO_SUPPORTED:
            raise FormatError(
                f"basket at {rec.offset}: fIOBits {io_bits:#04x} sets flags this "
                f"specification does not cover")
    nev_buf = _i32(buf, o)
    last = _i32(buf, o + 4)
    flag = buf[o + 8]

    payload_start = rec.offset + rec.key_len
    data_end = rec.offset + last
    offsets = None
    displacements = None
    if data_end < payload_start + rec.obj_len:
        # An entry-offset array follows the data. It is written with a leading
        # count of fNevBuf + 1; the extra value is not an offset.
        count = _i32(data, data_end)
        if count != nev_buf + 1:
            raise FormatError(
                f"basket at {rec.offset}: offset array count {count}, expected "
                f"fNevBuf + 1 = {nev_buf + 1}")
        offsets = list(struct.unpack_from(f">{nev_buf}i", data, data_end + 4))
        if io_bits & IO_GENERATE_OFFSET_MAP:
            # The array was converted to sizes before writing, with a leading 0;
            # turn it back into record-relative offsets.
            running = rec.key_len
            restored = []
            for size in offsets:
                running += size
                restored.append(running)
            offsets = restored
        else:
            offsets = [v & ~DISPLACEMENT_MASK if flag and 20 < flag < 40 else v
                       for v in offsets]
        # A displacement array may follow, in the same count-prefixed form and
        # with NOTHING in the flag to announce it: a record basket is always
        # written header-only, so its flag is 0 or 80 whatever WriteBuffer
        # appended. Only the arithmetic detects it. TBasket.md 5.3.
        after = data_end + 4 + 4 * (nev_buf + 1)
        if after < payload_start + rec.obj_len:
            count = _i32(data, after)
            if count == nev_buf + 1:
                displacements = list(
                    struct.unpack_from(f">{nev_buf}i", data, after + 4))
    if o + 9 != rec.offset + rec.key_len:
        raise FormatError(
            f"basket at {rec.offset}: header ends at {o + 9}, key ends at "
            f"{rec.offset + rec.key_len}")
    return Basket(version=version, buffer_size=buffer_size,
                  nev_buf_size=nev_buf_size, nev_buf=nev_buf, last=last,
                  flag=flag, io_bits=io_bits,
                  generated=offsets is None and flag >= FLAG_GENERATE,
                  key_len=rec.key_len, header_offset=header,
                  data_start=payload_start, data_end=data_end,
                  entry_offsets=offsets, displacements=displacements)


def generate_entry_offsets(key_len: int, nev_buf: int, len_type: int,
                           counts: list[int], header: int = 0) -> list[int]:
    """The offsets a kGenerateOffsetMap basket does not store.

    spec/04-ttree/TBasket.md section 5.2, from
    `root/tree/tree/src/TLeaf.cxx:210-216`. `counts` is the counter leaf's value
    at each entry, and `header` is 0 for every leaf but TLeafElement.
    """
    offset, out = key_len, []
    for i in range(nev_buf):
        out.append(offset)
        offset += len_type * counts[i] + header
    return out


def basket_entry_range(rec: Record, basket: Basket, index: int) -> tuple[int, int]:
    """The absolute byte range of entry `index`. spec/04-ttree/TBasket.md."""
    if not 0 <= index < basket.nev_buf:
        raise FormatError(f"entry {index} outside [0, {basket.nev_buf})")
    if basket.generated:
        raise FormatError(
            f"basket at {rec.offset} has flag 80: its entry offsets are not "
            f"stored and must be generated from the branch's leaf, TBasket.md 5.2.1")
    if basket.entry_offsets is None:
        width = basket.nev_buf_size
        start = basket.data_start + index * width
        return start, start + width
    start = rec.offset + basket.entry_offsets[index]
    if index + 1 < basket.nev_buf:
        return start, rec.offset + basket.entry_offsets[index + 1]
    return start, basket.data_end


# --- branches and leaves, spec/04-ttree/TBranch.md and TLeaf.md -------------

# fLenType is the writer's sizeof and is not the on-disk width for these three;
# TLeaf.md section 4.1. TLeafC is variable and TLeafF16/TLeafD32 depend on the
# title, so neither appears here; see leaf_width().
LEAF_WIDTH = {
    "TLeafO": 1, "TLeafB": 1, "TLeafS": 2, "TLeafI": 4,
    "TLeafL": 8, "TLeafG": 8, "TLeafF": 4, "TLeafD": 8,
}

COUNTER_LEAVES = {"TLeafO", "TLeafB", "TLeafS", "TLeafI", "TLeafL", "TLeafG"}


@dataclass
class Leaf:
    """One entry of a branch's fLeaves. TLeaf.md section 2."""

    cls: str
    slot: int             # the object slot's offset, for resolving references
    counter: "Leaf | None"  # the counter leaf, when written inline here
    name: str
    title: str
    length: int           # fLen, after the zero-to-one normalisation
    len_type: int
    offset: int
    is_range: bool
    is_unsigned: bool
    leaf_count: int       # the raw reference tag; 0 for none
    count_slot: int       # where that tag points, absolute; -1 for none
    #: fMinimum and fMaximum, read only for a TLeafC, where they are Int_t and
    #: mean something a reader needs (TLeaf.md 9). None for every other class,
    #: whose pair is of the leaf's own type and is only a range.
    minimum: int | None = None
    maximum: int | None = None

    @property
    def width(self) -> int | None:
        """The on-disk width of one value, or None when it is not fixed."""
        if self.cls in LEAF_WIDTH:
            return LEAF_WIDTH[self.cls]
        if self.cls in ("TLeafF16", "TLeafD32"):
            return truncated_width(self.cls, self.title)
        return None       # TLeafC, TLeafElement, TLeafObject


@dataclass
class Tree:
    """A decoded TTree record. TTree.md section 2."""

    name: str
    title: str
    version: int                  # the record's class version
    entries: int
    tot_bytes: int
    zip_bytes: int
    saved_bytes: int
    flushed_bytes: int
    default_entry_offset_len: int | None   # None below class version 17
    n_cluster_range: int | None            # None below class version 19
    max_entries: int | None                # None below class version 14
    auto_save: int
    auto_flush: int | None                 # None below class version 18
    estimate: int
    io_bits: int | None                    # None below class version 20
    cluster_range_end: list[int]
    cluster_size: list[int]
    cluster_present: tuple[int, int]       # the two is-present flag bytes
    index_values_n: int                    # fIndexValues' fN
    index_n: int                           # fIndex' fN
    leaf_slots: int                        # fLeaves' nobjects
    leaf_refs: list[int]                   # map positions of its entries
    leaf_objects: int                      # entries written in full, not as a reference
    pointers: dict                         # fAliases etc -> "null" | "object" | "reference"
    branches: list["Branch"]
    # Optional because a test may build a Tree to exercise the cluster maths
    # alone. Both are read from the file when there is one.
    branch_ref: "Branch | None" = None     # fBranchRef, which is NOT in fBranches
    index_slot: int = -1                   # fTreeIndex's object slot; -1 if null


@dataclass
class Branch:
    """One entry of a tree's or branch's fBranches. TBranch.md section 2."""

    slot: int
    name: str
    title: str
    compress: int
    basket_size: int
    entry_offset_len: int
    write_basket: int
    entry_number: int
    io_bits: int
    offset: int
    max_baskets: int
    split_level: int
    entries: int
    first_entry: int
    tot_bytes: int
    zip_bytes: int
    basket_slots: int           # fBaskets' nobjects
    basket_objects: int         # how many of those slots are not null
    embedded: dict              # slot index -> EmbeddedBasket
    basket_bytes: list[int]
    basket_entry: list[int]
    basket_seek: list[int]
    file_name: str
    leaves: list[Leaf]
    leaf_refs: list[int]        # map positions of fLeaves entries not written here
    branches: list["Branch"]

    # The eleven TBranchElement members. TBranchElement.md section 2. `cls` is
    # the branch's own class; every field below it is None or 0 on a plain
    # TBranch, which has none of them.
    #: Set when this branch stood under a TBranchClones, which is not
    #: itself a readable TBranch (TBranchElement.md 13.1).
    via: str | None = None
    cls: str = "TBranch"
    class_name: str = ""
    parent_name: str = ""
    clones_name: str = ""
    check_sum: int = 0
    class_version: int = 0
    element_id: int | None = None       # fID
    element_type: int | None = None     # fType
    streamer_type: int | None = None
    maximum: int = 0
    count_slot: int = -1                # fBranchCount, resolved; -1 when null
    count_slot2: int = -1               # fBranchCount2, likewise


def truncated_width(cls: str, title: str) -> int:
    """Bytes per value of a TLeafF16 or TLeafD32. TLeaf.md section 7.

    The packing depends only on the annotation in the title.
    """
    letter = "f" if cls == "TLeafF16" else "d"
    at = title.find("/" + letter + "[")
    if at < 0 and title.startswith(letter + "["):
        # Class version 1 stored the type spec alone, with no leaf name and no
        # leading slash. ROOT repairs that on read by prepending one
        # (root/tree/tree/src/TLeafF16.cxx:226-228); accept both forms.
        at = -1
        spec = title
    elif at < 0:
        # No annotation. The two classes disagree: Float16_t falls back to a
        # 12-bit mantissa, Double32_t to a plain Float_t.
        return 3 if cls == "TLeafF16" else 4
    else:
        spec = title[at + 2:]
    inner = spec[spec.find("[") + 1:spec.find("]")]
    parts = [p.strip() for p in inner.split(",")]
    xmin = _range_literal(parts[0]) if parts[0] else 0.0
    xmax = _range_literal(parts[1]) if len(parts) > 1 and parts[1] else 0.0
    nbits = 32
    if len(parts) > 2:
        try:
            nbits = int(parts[2])
        except ValueError:
            nbits = 32
        if nbits < 2 or nbits > 32:
            nbits = 32
    if xmin < xmax:
        return 4                      # a factor: a scaled UInt_t
    if nbits < 15:
        return 3                      # nbits smuggled through fXmin
    return 3 if cls == "TLeafF16" else 4


def _io_bits(buf: bytes, m: dict) -> int | None:
    """fIOFeatures' single member, or None when the class has no fIOFeatures.

    fIOFeatures is a kAny member rather than a base class, so `_named` does not
    flatten it: the byte has to be taken from the nested object.
    """
    outer = m.get("fIOFeatures")
    if outer is None:
        return None
    for member in outer.members or []:
        if member.name == "fIOBits":
            return buf[member.start]
    return None


def _named(buf: bytes, values: list[Value]) -> dict[str, Value]:
    """Flatten a member list, keyed by name, bases included."""
    out: dict[str, Value] = {}

    BASES = (0, 66, 67)

    def walk_members(vs):
        for v in vs:
            out.setdefault(v.name, v)
            if v.members and v.ftype in BASES:
                walk_members(v.members)
    walk_members(values)
    return out


def _string_at(buf: bytes, value: Value) -> str:
    return _counted_string(buf, value.start)[0]


def _counted_pointer(buf: bytes, value: Value, width: int | None,
                     count: int) -> list[int]:
    """The values of a kOffsetP member: a flag byte then `count` of them.

    `width` of None derives the width from the bytes the member occupies, as
    needed for a legacy TBranch's fBasketSeek, whose width is in its flag byte,
    not in the streamer info (TBranch.md 13.3).
    """
    span = value.end - value.start - 1
    if span <= 0 or count <= 0:
        return []
    if width is None:
        width = span // count
    if not buf[value.start] and span < count * width:
        return []
    fmt = {4: _i32, 8: _i64}[width]
    base = value.start + 1
    return [fmt(buf, base + i * width) for i in range(count)]


def _sequence_count(buf: bytes, value: Value) -> int:
    """The nobjects field of a TObjArray member, null slots included."""
    frame = read_frame(buf, value.start)
    pos = frame.body
    if frame.version > 2:
        pos = read_tobject(buf, pos).end
    if frame.version > 1:
        _, pos = _counted_string(buf, pos)
    return _i32(buf, pos)


def _read_leaf(buf: bytes, entry: Value, base: int) -> Leaf:
    m = _named(buf, entry.members or [])
    length = _i32(buf, m["fLen"].start)
    count_at = m["fLeafCount"].start
    tag = _u32(buf, count_at)
    counter = None
    if tag & BYTE_COUNT_MASK:
        # The counter leaf's first occurrence in this buffer is written in full
        # here. Every other leaf that names it back-references this position,
        # so the position identifies it. TLeaf.md section 3.1.
        counter = _read_leaf(buf, m["fLeafCount"], base)
        counter.slot = count_at
    limits = {}
    if entry.type_name == "TLeafC":
        # Int_t on a TLeafC, and the only leaf class whose pair a reader uses.
        for field in ("fMinimum", "fMaximum"):
            if field in m:
                limits[field[1:].lower()] = _i32(buf, m[field].start)
    return Leaf(
        cls=entry.type_name, slot=entry.start, counter=counter, **limits,
        name=_string_at(buf, m["fName"]), title=_string_at(buf, m["fTitle"]),
        length=length or 1,          # TLeaf.cxx:499, a stored 0 means 1
        len_type=_i32(buf, m["fLenType"].start),
        offset=_i32(buf, m["fOffset"].start),
        is_range=bool(buf[m["fIsRange"].start]),
        is_unsigned=bool(buf[m["fIsUnsigned"].start]),
        leaf_count=tag,
        count_slot=count_at if counter is not None else
        ((base + tag - MAP_OFFSET) if tag else -1))


def _embedded_baskets(buf: bytes, baskets: Value, base: int) -> dict:
    """The embedded baskets of one fBaskets array, by slot index.

    read_sequence records only the non-null slots, so the index has to be
    recovered by walking the array again.
    """
    out: dict = {}
    frame = read_frame(buf, baskets.start)
    pos = frame.body
    if frame.version > 2:
        pos = read_tobject(buf, pos).end
    if frame.version > 1:
        _, pos = _counted_string(buf, pos)
    count = _i32(buf, pos)
    pos += 8                              # nobjects, then fLowerBound
    for index in range(max(count, 0)):
        slot = read_slot(buf, pos, base)
        if slot.kind == "object":
            # The class may be a back-reference, and the class map is not
            # available here, so identify the basket by parsing it: the key has
            # its own fClassName, and a correct parse ends exactly where the slot
            # does.
            body = slot.offset + 8
            if slot.class_name is not None:
                body += len(slot.class_name) + 1
            try:
                emb = read_embedded_basket(buf, body)
            except (FormatError, struct.error, IndexError, ValueError):
                emb = None
            if emb is not None and emb.end == slot.end:
                out[index] = emb
        pos = slot.end
    return out


def _branch_list(buf: bytes, entries: list[Value], base: int) -> list[Branch]:
    """Read a branch list, flattening any TBranchClones into its children.

    A TBranchClones has no TBranch base and so no fLeaves, fBaskets or basket
    arrays of its own (TBranchElement.md 13.1): the data is in its sub-branches,
    which are ordinary TBranches with ordinary baskets. Raising on it would
    abandon the whole tree and leave those baskets unchecked, so its children take
    its place, each with a note recording where it came from. The structure is
    still visible in the record: `fBranches` of the parent holds the
    TBranchClones, and the byte assertions in `ttree/branch-clones` pin it.
    """
    out: list[Branch] = []
    for entry in entries:
        if entry.type_name == "TBranchClones":
            m = _named(buf, entry.members or [])
            children = []
            # fBranchCount first, and it is not optional: it holds the count leaf
            # (`fHits_` in ttree/branch-clones) that every sub-branch's
            # fLeafCount refers to by position. Dropping it makes those
            # references unresolvable; an earlier version made that mistake.
            count = m.get("fBranchCount")
            if count is not None and count.members:
                children.append(_read_branch(buf, count, base))
            inner = m.get("fBranches")
            if inner is not None:
                children.extend(_branch_list(buf, inner.members or [], base))
            for child in children:
                child.via = "TBranchClones"
            out.extend(children)
            continue
        out.append(_read_branch(buf, entry, base))
    return out


def _read_branch(buf: bytes, entry: Value, base: int) -> Branch:
    m = _named(buf, entry.members or [])
    if entry.type_name == "TBranchClones":
        # Not a low TBranch version: a TBranchClones writes ten of TBranch's
        # fields individually and none of the rest, so the generic algorithm has
        # nothing to work with however new the file is.
        # TBranchElement.md 13.1.
        raise UnsupportedClass(
            "TBranchClones streams ten TBranch fields and no TBranch base, so "
            "the generic branch layout does not apply: TBranchElement.md 13.1")
    # fFirstEntry arrived at TBranch version 11 and fSplitLevel at 7; below
    # those the field does not exist and its value is 0 by definition (a branch
    # with no fFirstEntry starts at entry 0). TBranch.md 13.1.
    n = _i32(buf, m["fMaxBaskets"].start)
    return Branch(
        slot=entry.start,
        name=_string_at(buf, m["fName"]), title=_string_at(buf, m["fTitle"]),
        compress=_i32(buf, m["fCompress"].start),
        basket_size=_i32(buf, m["fBasketSize"].start),
        entry_offset_len=_i32(buf, m["fEntryOffsetLen"].start),
        write_basket=_i32(buf, m["fWriteBasket"].start),
        entry_number=_int_member(buf, m["fEntryNumber"]),
        io_bits=_io_bits(buf, m) or 0,
        offset=_i32(buf, m["fOffset"].start),
        max_baskets=n,
        split_level=(_i32(buf, m["fSplitLevel"].start)
                     if "fSplitLevel" in m else 0),
        entries=_int_member(buf, m["fEntries"]),
        first_entry=(_i64(buf, m["fFirstEntry"].start)
                     if "fFirstEntry" in m else 0),
        tot_bytes=_int_member(buf, m["fTotBytes"]),
        zip_bytes=_int_member(buf, m["fZipBytes"]),
        basket_slots=_sequence_count(buf, m["fBaskets"]),
        basket_objects=len(m["fBaskets"].members or []),
        embedded=_embedded_baskets(buf, m["fBaskets"], base),
        # Widths from the bytes rather than from the declared type: below
        # version 10 fBasketEntry is Int_t and fBasketSeek's width is in its
        # flag byte. TBranch.md 13.1, 13.3.
        basket_bytes=_counted_pointer(buf, m["fBasketBytes"], None, n),
        basket_entry=_counted_pointer(buf, m["fBasketEntry"], None, n),
        basket_seek=_counted_pointer(buf, m["fBasketSeek"], None, n),
        file_name=_string_at(buf, m["fFileName"]),
        leaves=[_read_leaf(buf, e, base) for e in (m["fLeaves"].members or [])
                if e.reference is None],
        leaf_refs=[e.reference for e in (m["fLeaves"].members or [])
                   if e.reference is not None],
        branches=_branch_list(buf, m["fBranches"].members or [], base),
        cls=entry.type_name or "TBranch",
        **_element_members(buf, m, base))


def _element_members(buf: bytes, m: dict, base: int) -> dict:
    """The eleven TBranchElement fields, or empty for a plain TBranch.

    Keyed off fType rather than off the class name, because TBranchObject and
    the legacy container branches have some of these and not others.
    TBranchElement.md section 2.
    """
    if "fType" not in m:
        return {}
    return dict(
        class_name=_string_at(buf, m["fClassName"]),
        parent_name=_string_at(buf, m["fParentName"]) if "fParentName" in m else "",
        clones_name=_string_at(buf, m["fClonesName"]) if "fClonesName" in m else "",
        check_sum=_u32(buf, m["fCheckSum"].start) if "fCheckSum" in m else 0,
        class_version=(_int_member(buf, m["fClassVersion"])
                       if "fClassVersion" in m else 0),
        element_id=_i32(buf, m["fID"].start),
        element_type=_i32(buf, m["fType"].start),
        streamer_type=_i32(buf, m["fStreamerType"].start),
        maximum=_i32(buf, m["fMaximum"].start) if "fMaximum" in m else 0,
        count_slot=_branch_ref(buf, m.get("fBranchCount"), base),
        count_slot2=_branch_ref(buf, m.get("fBranchCount2"), base))


TREE_POINTERS = ("fAliases", "fTreeIndex", "fFriends", "fUserInfo", "fBranchRef")


def _branch_ref(buf: bytes, value: Value | None, base: int) -> int:
    """fBranchCount / fBranchCount2: a back-reference, not a branch.

    Four bytes holding the map position of a branch written earlier in this same
    record, as fLeafCount does for a leaf. TBranchElement.md section 6.
    Zero means the field is unset, which is every branch but a split container's
    members. Returns the absolute position, or -1.
    """
    if value is None or value.end - value.start < 4:
        return -1
    tag = _u32(buf, value.start)
    if not tag:
        return -1
    if tag & BYTE_COUNT_MASK:
        # Written in full here rather than referenced. No corpus file does this,
        # but the position is still the identity, as for fLeafCount.
        return value.start
    return base + tag - MAP_OFFSET


def _int_member(buf: bytes, value: Value) -> int:
    """An integral member, whatever width the streamer info gave it.

    fEntries and its neighbours were Int_t or Stat_t (a double) below TTree
    class version 13, so the width cannot be assumed. TTree.md section 12.
    """
    if value.ftype in (3, 6, 13):
        return _i32(buf, value.start)
    if value.ftype == 2:
        return _i16(buf, value.start)
    if value.ftype in (16, 17):
        return _i64(buf, value.start)
    if value.ftype == 8:
        return int(struct.unpack_from(">d", buf, value.start)[0])
    raise FormatError(f"{value.name}: unexpected type code {value.ftype}")


@dataclass
class TreeIndex:
    """A decoded TTreeIndex. Auxiliary.md section 2.

    Hand-coded because TTreeIndex::Streamer never calls ReadClassBuffer, so no
    streamer info for it is ever written to a file and the streamer-driven
    algorithm cannot reach it.
    """

    version: int
    major_name: str
    minor_name: str
    n: int
    values: list[int]
    values_minor: list[int]      # empty below class version 2
    index: list[int]


def read_tree_index(buf: bytes, offset: int) -> TreeIndex:
    """Read a TTreeIndex from the object slot at `offset`. Auxiliary.md 2.

    `offset` is the start of the object *slot*, as the fTreeIndex member gives
    it: a byte count, then a class tag, then the object. The tag is resolved
    here rather than by the caller because there is no streamer info to look the
    class up in.
    """
    tag = _u32(buf, offset + 4)
    if tag == NEW_CLASS_TAG:
        o = offset + 8
        while buf[o]:                    # the NUL-terminated class name
            o += 1
        o += 1
    elif tag & CLASS_MASK:
        o = offset + 8
    else:
        raise FormatError(f"TTreeIndex slot at {offset} has tag {tag:#x}")
    frame = read_frame(buf, o)
    o = frame.body
    base = read_frame(buf, o)            # TVirtualIndex
    o = base.body
    named = read_frame(buf, o)           # TNamed
    o = skip_tobject(buf, named.body)
    _, o = _counted_string(buf, o)       # fName
    _, o = _counted_string(buf, o)       # fTitle
    major, o = _counted_string(buf, o)
    minor, o = _counted_string(buf, o)
    n = _i64(buf, o)
    o += 8
    if n < 0:
        raise FormatError(f"TTreeIndex fN {n}")

    def longs(at):
        # WriteFastArray: no is-present flag, unlike a streamer-info [fN].
        return [_i64(buf, at + 8 * i) for i in range(n)], at + 8 * n

    values, o = longs(o)
    minor_values: list[int] = []
    if frame.version >= 2:
        minor_values, o = longs(o)
    index, o = longs(o)
    # The arrays have no count of their own, so a wrong fN is invisible inside
    # the object. The byte count is the only redundancy: the three arrays must
    # fill the frame exactly. Auxiliary.md invariant 1.
    if frame.end is not None and o != frame.end:
        raise FormatError(
            f"TTreeIndex at {offset}: fN {n} accounts for {o - frame.body} "
            f"bytes of {frame.end - frame.body}")
    return TreeIndex(version=frame.version, major_name=major, minor_name=minor,
                     n=n, values=values, values_minor=minor_values, index=index)


def element_width(element: Element) -> int | None:
    """One value of this element, in bytes, or None when it is not fixed.

    The widths are ElementTypes.md; the Double32_t/Float16_t cases take theirs
    from the element's title, which is the only place a split branch records it
    (ReadingEntries.md section 5.2).
    """
    t = element.ftype
    if t in (9, 19):
        return quantised_width(t, element.title)
    if t in SCALAR_WIDTH:
        return SCALAR_WIDTH[t]
    return None


def derives_from(infos: list[StreamerInfo], name: str, ancestor: str) -> bool:
    """Is `ancestor` in `name`'s base-class chain, per the file's own infos?

    A tree's record may be of any class deriving from TTree (TNtuple, TNtupleD,
    TChain), so a reader cannot find trees by comparing the key's class name
    against "TTree". TTree.md section 1.
    """
    by_name = {i.name: i for i in infos}
    seen: set[str] = set()
    stack = [name]
    while stack:
        current = stack.pop()
        if current == ancestor:
            return True
        if current in seen:
            continue
        seen.add(current)
        info = by_name.get(current)
        if info is None:
            continue
        stack += [el.name for el in info.elements if el.cls == "TStreamerBase"]
    return False


def read_tree(buf: bytes, value: Value, base: int) -> Tree:
    """A decoded TTree record, branches nested.

    `value` may be a class deriving from TTree, in which case the TTree part is a
    base-class member of it and the version reported is that base's.

    `base` is the record's offset, i.e. buffer position 0, which is what the
    reference tags in fLeaves and fLeafCount are relative to.
    """
    m = _named(buf, value.members or [])
    if "fBranches" not in m:
        raise FormatError("no fBranches member")
    # The frame whose version word is TTree's own.
    framed = next((mem for mem in (value.members or []) if mem.name == "TTree"),
                  value)

    def opt(name):
        return _int_member(buf, m[name]) if name in m else None

    n = _int_member(buf, m["fNClusterRange"]) if "fNClusterRange" in m else 0
    leaves = m["fLeaves"].members or []
    branches = [_read_branch(buf, e, base)
                for e in (m["fBranches"].members or [])]
    _resolve_leaf_refs(branches, base)
    return Tree(
        name=_string_at(buf, m["fName"]), title=_string_at(buf, m["fTitle"]),
        version=read_frame(buf, framed.start).version,
        entries=_int_member(buf, m["fEntries"]),
        tot_bytes=_int_member(buf, m["fTotBytes"]),
        zip_bytes=_int_member(buf, m["fZipBytes"]),
        saved_bytes=_int_member(buf, m["fSavedBytes"]),
        flushed_bytes=opt("fFlushedBytes") or 0,
        default_entry_offset_len=opt("fDefaultEntryOffsetLen"),
        n_cluster_range=opt("fNClusterRange"),
        max_entries=opt("fMaxEntries"),
        auto_save=_int_member(buf, m["fAutoSave"]),
        auto_flush=opt("fAutoFlush"),
        estimate=_int_member(buf, m["fEstimate"]),
        io_bits=_io_bits(buf, m),
        cluster_range_end=(_counted_pointer(buf, m["fClusterRangeEnd"], 8, n)
                           if "fClusterRangeEnd" in m else []),
        cluster_size=(_counted_pointer(buf, m["fClusterSize"], 8, n)
                      if "fClusterSize" in m else []),
        cluster_present=((buf[m["fClusterRangeEnd"].start],
                          buf[m["fClusterSize"].start])
                         if "fClusterRangeEnd" in m else (0, 0)),
        index_values_n=_i32(buf, m["fIndexValues"].start),
        index_n=_i32(buf, m["fIndex"].start),
        leaf_slots=_sequence_count(buf, m["fLeaves"]),
        leaf_refs=[e.reference for e in leaves if e.reference is not None],
        leaf_objects=sum(1 for e in leaves if e.reference is None),
        pointers={name: read_slot(buf, m[name].start, base).kind
                  for name in TREE_POINTERS if name in m},
        branches=branches,
        branch_ref=_read_branch_ref(buf, m, base),
        index_slot=(m["fTreeIndex"].start
                    if "fTreeIndex" in m and m["fTreeIndex"].type_name else -1))


def _read_branch_ref(buf: bytes, m: dict, base: int) -> "Branch | None":
    """fBranchRef, when the tree has one. TTree.md section 4.

    It is a TBranch and it holds data, but it is not in fBranches, so a walk
    over a tree's branches misses it unless it is asked for by name.
    """
    slot = m.get("fBranchRef")
    if slot is None or not slot.members:
        return None
    try:
        return _read_branch(buf, slot, base)
    except (FormatError, KeyError, struct.error, IndexError, ValueError):
        return None


def read_branches(buf: bytes, tree: Value, base: int) -> list[Branch]:
    """Every top-level branch of a decoded TTree record, sub-branches nested.

    `base` is the TTree record's offset, i.e. buffer position 0, which is what
    fLeafCount's reference tags are relative to.
    """
    members = _named(buf, tree.members or [])
    if "fBranches" not in members:
        raise FormatError("no fBranches member")
    top = _branch_list(buf, members["fBranches"].members or [], base)
    _resolve_leaf_refs(top, base)
    return top


def _resolve_leaf_refs(top: list[Branch], base: int) -> None:
    """Attach leaves whose fLeaves entry was only a reference.

    A branch's fLeaves can hold a back-reference to a leaf written in full
    elsewhere in the same buffer, for instance inside another leaf's fLeafCount.
    TLeaf.md section 3.1.
    """
    known: dict[int, Leaf] = {}
    for branch in walk_branches(top):
        for leaf in branch.leaves:
            known[leaf.slot] = leaf
            if leaf.counter is not None:
                known[leaf.counter.slot] = leaf.counter
    for branch in walk_branches(top):
        for ref in branch.leaf_refs:
            leaf = known.get(base + ref - MAP_OFFSET)
            if leaf is not None:
                branch.leaves.append(leaf)


def cluster_of(tree: Tree, entry: int) -> tuple[int, int] | None:
    """The cluster `[start, end)` containing `entry`. TTree.md section 6.2.

    Returns None when the file does not record the cluster size for that entry,
    which is the case for the open-ended range of any tree whose fAutoFlush is
    not positive. ROOT then estimates it from run-time cache settings, so it is
    not a property of the file.
    """
    ends = tree.cluster_range_end
    n = len(ends)
    r = sum(1 for end in ends if end < entry)
    pedestal = 0 if r == 0 else ends[r - 1] + 1
    size = (tree.auto_flush or 0) if r == n else tree.cluster_size[r]
    if size <= 0:
        return None
    start = pedestal + ((entry - pedestal) // size) * size
    end = start + size
    if r < n:
        end = min(end, ends[r] + 1)
    return start, min(end, tree.entries)


def clusters(tree: Tree):
    """Every cluster of the tree, in order, while the size is recorded."""
    entry = 0
    while entry < tree.entries:
        found = cluster_of(tree, entry)
        if found is None:
            return
        start, end = found
        if end <= entry:
            return
        yield start, end
        entry = end


def walk_branches(branches: list[Branch]):
    """Every branch, depth first."""
    for b in branches:
        yield b
        yield from walk_branches(b.branches)


def find_basket(branch: Branch, entry: int) -> int:
    """The basket index holding `entry`. TBranch.md section 10."""
    if not branch.first_entry <= entry < branch.entry_number:
        raise FormatError(
            f"entry {entry} outside [{branch.first_entry}, {branch.entry_number})")
    found = -1
    for i in range(min(branch.write_basket + 1, len(branch.basket_entry))):
        if branch.basket_entry[i] <= entry:
            found = i
    if found < 0:
        raise FormatError(f"no basket holds entry {entry}")
    return found


def resolve_leaf_count(leaf: Leaf, leaves: list[Leaf]) -> Leaf:
    """The counter leaf `leaf.fLeafCount` refers to. TLeaf.md section 3.1.

    The stored value is a buffer map position; `Leaf.count_slot` has already
    converted it to an absolute offset.
    """
    if leaf.counter is not None:
        return leaf.counter
    for other in leaves:
        if other.slot == leaf.count_slot:
            return other
        if other.counter is not None and other.counter.slot == leaf.count_slot:
            return other.counter
    raise FormatError(
        f"leaf {leaf.name!r} has fLeafCount {leaf.leaf_count}, which is no leaf "
        f"in this record")


def entry_spans(buf: bytes, rec: Record, basket: Basket, branch: Branch,
                index: int, counts: dict[int, int] | None = None,
                leaves: list[Leaf] | None = None
                ) -> list[tuple[Leaf, int, int]]:
    """The byte span of each leaf's data within one entry. TLeaf.md section 5.

    `counts` maps a counter leaf's slot offset to its value for this entry;
    it is required for every leaf of this branch whose fLeafCount is set.
    `leaves` is every leaf of the tree, because a counter usually lives in a
    different branch; it defaults to this branch's own.
    Raises FormatError when the leaves do not account for the entry exactly,
    which is TLeaf.md invariant 7.
    """
    counts = dict(counts or {})
    leaves = leaves if leaves is not None else branch.leaves
    start, end = basket_entry_range(rec, basket, index)
    pos = start
    spans: list[tuple[Leaf, int, int]] = []
    for leaf in branch.leaves:
        width = leaf.width
        if width is None:
            if leaf.cls != "TLeafC":
                raise UnsupportedClass(f"{leaf.cls} has no fixed element width")
            if pos == end:
                # The empty string: zero bytes, not even a length. TLeaf.md 9.
                spans.append((leaf, pos, pos))
                continue
            _, after = _counted_string(buf, pos)
            spans.append((leaf, pos, after))
            pos = after
            continue
        n = leaf.length
        if leaf.leaf_count:
            counter = resolve_leaf_count(leaf, leaves)
            if counter.slot not in counts:
                raise FormatError(
                    f"no count for leaf {leaf.name!r} from {counter.name!r}")
            n = counts[counter.slot] * leaf.length
        spans.append((leaf, pos, pos + n * width))
        # A counter in this same branch precedes what it counts, so read its
        # value here rather than requiring it up front. TLeaf.md section 5.2.
        if leaf.is_range and width and n == 1:
            counts[leaf.slot] = int.from_bytes(buf[pos:pos + width], "big",
                                               signed=True)
        pos += n * width
    if pos != end:
        raise FormatError(
            f"branch {branch.name!r} entry {index}: leaves account for "
            f"{pos - start} bytes of {end - start}")
    return spans


# --- decoding one entry, spec/04-ttree/ReadingEntries.md -------------------


def branch_streamer_info(infos: list[StreamerInfo], branch: Branch) -> StreamerInfo:
    """The streamer info a branch's fClassName, fClassVersion and fCheckSum pick.

    TBranchElement.md section 5: fClassName names the class whose element list
    fID indexes into, not the branch's own type. The choice is made from the
    branch's fields and never from bytes in the entry: nothing in an entry
    identifies a class (ReadingEntries.md 5.1), which is why those two fields
    are on the branch.
    """
    if not branch.class_name:
        raise UnsupportedClass("branch has no fClassName")
    candidates = [i for i in infos if i.name == branch.class_name]
    if not candidates:
        raise UnsupportedClass(
            f"{branch.class_name} has no streamer info in its own file")
    if branch.class_version:
        for info in candidates:
            if info.class_version == branch.class_version:
                return info
    for info in candidates:
        if info.checksum == branch.check_sum:
            return info
    if len(candidates) == 1:
        return candidates[0]
    raise UnsupportedClass(
        f"no streamer info for {branch.class_name} version "
        f"{branch.class_version}")


# fType values that mean "this node holds no bytes of its own", from
# root/tree/tree/src/TBranchElement.cxx:5692; ReadingEntries.md section 2.
INTERIOR_TYPES = (1, 2)
SPLIT_NODE_ID = -2


class TreeReader:
    """Decodes entries of a tree's branches. ReadingEntries.md section 7.

    Written from the specification rather than from ROOT's source, like the rest
    of this module, so that a disagreement between the two can be detected. It
    reports an end position, which is what ReadingEntries.md invariant 5 needs:
    the bytes a branch's entry occupies equal the bytes its decoding consumes.

    `fetch(seek)` returns `(record, buffer)` for the basket at that file offset,
    the record's object data uncompressed in place, or None when it cannot be
    read here. It is a parameter because decompressing a basket is the expensive
    part, and a caller normally caches it already.
    """

    def __init__(self, buf: bytes, tree: Tree, infos: list[StreamerInfo],
                 fetch=None, tolerant: bool = False,
                 custom: "set[str] | None" = None,
                 tree_payload: bytes | None = None):
        self.buf = buf
        # The TTree record's own object data, in which Branch.embedded[i].block
        # is an offset. Without it a basket that was never written as a record is
        # unreachable, and that is most of the baskets in a file written by
        # TDirectory::WriteTObject (TBranch.md 5).
        self.tree_payload = tree_payload
        self.tree = tree
        self.infos = infos
        self.tolerant = tolerant
        self.custom = set(custom or ())
        self.fetch = fetch if fetch is not None else self._default_fetch
        self.branches = list(walk_branches(tree.branches))
        if tree.branch_ref is not None:
            # Not in fBranches, but it holds data. TTree.md 4.
            self.branches.append(tree.branch_ref)
        self.by_slot = {br.slot: br for br in self.branches}
        self.by_name = {br.name: br for br in self.branches}
        # Parent-child structure, for resolving a counter among siblings rather
        # than through fBranchCount. ReadingEntries.md 4.1.
        self._siblings: dict[int, list[Branch]] = {}
        def index(children: list[Branch]) -> None:
            for child in children:
                self._siblings[child.slot] = children
                index(child.branches)
        index(tree.branches)
        self._records: dict[int, Record] | None = None
        self._info: dict[int, StreamerInfo] = {}
        # Keyed by (offset, embedded) rather than by offset alone: an embedded
        # basket's offset is a position in the TTree payload and a record's is a
        # position in the file, so the two number spaces overlap.
        self._decoders: dict[tuple[int, bool], Decoder] = {}
        self._baskets: dict[tuple[int, bool], Basket] = {}
        self._counts: dict[tuple[int, int], int] = {}

    def _default_fetch(self, seek: int):
        raise UnsupportedClass("this TreeReader was given no way to fetch baskets")

    # -- the pieces --------------------------------------------------------

    def info_for_branch(self, br: Branch) -> StreamerInfo:
        if br.slot not in self._info:
            self._info[br.slot] = branch_streamer_info(self.infos, br)
        return self._info[br.slot]

    def basket_for(self, br: Branch, entry: int):
        """`(record, buffer, basket, index, embedded)` for `entry` of `br`."""
        i = find_basket(br, entry)
        if i >= len(br.basket_seek):
            raise FormatError(
                f"branch {br.name!r}: basket {i} holds entry {entry} but "
                f"fBasketSeek has {len(br.basket_seek)} entries")
        if not br.basket_seek[i] and i in br.embedded:
            # Never written as a record: the basket is inside the TTree record,
            # and its raw block is the buffer its own offsets are relative to.
            # The block start plays the part the record offset plays for a
            # basket of its own. TBranch.md 5, TBasket.md 4.1.
            emb = br.embedded[i]
            if self.tree_payload is None or emb.block < 0:
                raise UnsupportedClass(
                    f"basket {i} of branch {br.name!r} is embedded in the tree "
                    f"record, and this reader was given no tree payload")
            rec = Record(offset=emb.block, nbytes=0, key_len=emb.key_len)
            basket, payload, embedded = emb.basket, self.tree_payload, True
        else:
            got = self.fetch(br.basket_seek[i])
            if got is None:
                raise UnsupportedClass(f"basket of branch {br.name!r} unavailable")
            rec, payload = got
            embedded = False
            key = (rec.offset, False)
            if key not in self._baskets:
                self._baskets[key] = read_basket(self.buf, rec, payload)
            basket = self._baskets[key]
        if basket.generated:
            raise UnsupportedClass(
                "basket flag 80: the entry offsets are generated, TBasket.md 5.2.1")
        return rec, payload, basket, entry - br.basket_entry[i], embedded

    def decoder_for(self, rec: Record, payload: bytes,
                    embedded: bool = False) -> Decoder:
        """A Decoder over one basket.

        The base is the basket record's offset, because that is buffer position
        0 for everything inside it: the same convention as every other record
        (Buffer.md section 1), and what basket_entry_range already assumes. For an
        embedded basket the raw block start takes that role: ROOT reads the block
        into the basket's own buffer, so positions inside it are relative to the
        block and not to the TTree record that holds it.
        """
        key = (rec.offset, embedded)
        if key not in self._decoders:
            self._decoders[key] = Decoder(payload, rec.offset, self.infos,
                                          tolerant=self.tolerant,
                                          custom=self.custom)
        return self._decoders[key]

    def count_at(self, br: Branch, entry: int) -> int:
        """The Int_t a count or counter branch holds for `entry`.

        ReadingEntries.md 3.1 and section 4. fMaximum is a read-time bound and
        not a statistic: a count outside [0, fMaximum] is rejected and ROOT
        substitutes 0 (section 6).
        """
        key = (br.slot, entry)
        if key in self._counts:
            return self._counts[key]
        rec, payload, basket, index, _ = self.basket_for(br, entry)
        start, end = basket_entry_range(rec, basket, index)
        if start == end:
            # IsMissingCollection: the four bytes are rewound and the entry
            # consumes nothing. ReadingEntries.md 6.
            count = 0
        else:
            count = int.from_bytes(payload[start:start + 4], "big", signed=True)
            if br.element_type in (3, 4) and not 0 <= count <= br.maximum:
                count = 0
        self._counts[key] = count
        return count

    def counter_branch(self, br: Branch, count_name: str) -> Branch:
        """The branch holding `count_name` for `br`. ReadingEntries.md 4.1.

        Resolved by NAME among this branch's siblings, and only then through
        fBranchCount. ROOT does the opposite and loses data: the writer builds the
        counter's name from this branch's own name and looks it up with
        TTree::GetBranch (root/tree/tree/src/TBranchElement.cxx:432-438), which
        searches the whole tree and returns the first match, so a tree holding two
        split objects of one class records the FIRST object's counter on both.
        ReadingEntries.md erratum 6, observed in alice_ESDs.root.
        """
        prefix = br.name[:br.name.rfind(".") + 1]     # "" when there is no dot
        want = prefix + count_name
        for sibling in self._siblings.get(br.slot, ()):
            if sibling.name == want and sibling is not br:
                return sibling
        if want in self.by_name:
            return self.by_name[want]
        if br.count_slot >= 0 and br.count_slot in self.by_slot:
            return self.by_slot[br.count_slot]
        raise UnsupportedClass(
            f"branch {br.name!r} needs the count {count_name!r} and no branch "
            f"named {want!r} is in this tree")

    def counts_column(self, br: Branch, count_name: str, entry: int,
                      objects: int) -> list[int]:
        """One count per object, from the counter branch's own column.

        A split member of a container whose type is `T *x; //[n]` needs a
        different n for every object in the entry, and the file holds them in the
        sibling branch that holds n, as a column of `objects` values, one per
        object. ReadingEntries.md 4.2.
        """
        counter = self.counter_branch(br, count_name)
        if objects <= 0:
            return []
        rec, payload, basket, index, _ = self.basket_for(counter, entry)
        start, end = basket_entry_range(rec, basket, index)
        span = end - start
        if span % objects:
            raise FormatError(
                f"branch {counter.name!r}: {span} bytes for {objects} object(s), "
                f"which does not divide")
        width = span // objects
        return [int.from_bytes(payload[start + i * width:
                                       start + (i + 1) * width], "big")
                for i in range(objects)]

    def count_for(self, br: Branch, entry: int) -> int:
        """The count a branch's own entry needs, from the branch fBranchCount
        names. ReadingEntries.md section 4."""
        if br.count_slot < 0:
            raise FormatError(f"branch {br.name!r} has no fBranchCount")
        counter = self.by_slot.get(br.count_slot)
        if counter is None:
            raise FormatError(
                f"branch {br.name!r}: fBranchCount points at {br.count_slot}, "
                f"which is no branch of this tree")
        return self.count_at(counter, entry)

    # -- one entry ---------------------------------------------------------

    def holds_data(self, br: Branch) -> bool:
        """ReadingEntries.md section 2: a node with sub-branches reads its own
        basket only when fType is 3 or 4."""
        ft = br.element_type
        if ft is None:
            return True                       # a plain TBranch always does
        if ft in INTERIOR_TYPES:
            return False
        if ft == 0 and br.element_id == SPLIT_NODE_ID:
            return False
        return True

    def entry_end(self, br: Branch, entry: int) -> tuple[int, int, int]:
        """`(start, end, consumed)` for one entry. ReadingEntries.md section 7.

        `start` and `end` are the byte range the basket gives it and `consumed`
        is where decoding stopped. Invariant 5 requires `end` and `consumed` to be
        equal.
        """
        if not self.holds_data(br):
            raise FormatError(
                f"branch {br.name!r} is an interior node and holds no entries")
        rec, payload, basket, index, embedded = self.basket_for(br, entry)
        start, end = basket_entry_range(rec, basket, index)
        decoder = self.decoder_for(rec, payload, embedded)
        consumed = decoder.within_extent(
            lambda: self.decode_entry(br, entry, rec, payload, basket, index,
                                      start, end, embedded),
            start, end, lambda pos: pos)
        return start, end, consumed

    def decode_entry(self, br: Branch, entry: int, rec: Record, payload: bytes,
                     basket: Basket, index: int, start: int, end: int,
                     embedded: bool = False) -> int:
        """Step 5 of ReadingEntries.md section 7, dispatched on fType and fID."""
        ft = br.element_type
        if ft is None:
            raise UnsupportedClass("a plain TBranch: use entry_spans")

        # fType 3 and 4: one Int_t and nothing else, or nothing at all.
        if ft in (3, 4):
            return start if start == end else start + 4

        if ft < 0:
            raise UnsupportedClass(
                f"fType {ft}: the class writes its own Streamer, "
                f"ReadingEntries.md 3.5")

        if br.class_name in self.custom:
            raise UnsupportedClass(
                f"{br.class_name} has a hand-written Streamer")
        decoder = self.decoder_for(rec, payload, embedded)
        info = self.info_for_branch(br)
        fid = br.element_id

        # fID < 0 on a node that holds data: every element of fClassName, in
        # order, with no class-level framing.
        if fid is None or fid < 0:
            return decoder.read_elements(info, start)

        if fid >= len(info.elements):
            raise FormatError(
                f"branch {br.name!r}: fID {fid} is past the {len(info.elements)} "
                f"elements of {info.name} v{info.class_version}")
        el = info.elements[fid]

        # A std::bitset member written before the ROOT-8574 fix, which landed in
        # 6.08/06 (root commit 2caaf15c2f0, 2017-02-24) and was backported to
        # 5.34/38: the collection proxy did not work in this path and ROOT wrote
        # the branch with no bytes in it at all. Every entry is empty, in both
        # the scalar and the column form. ReadingEntries.md 3.6.
        if (start == end and el.cls == "TStreamerSTL"
                and el.tail.get("fSTLtype") == STL_BITSET):
            return start

        # fType 31 and 41: n values of that element, back to back.
        if ft in (31, 41):
            objects = max(self.count_for(br, entry), 0)
            if OFFSET_P <= el.ftype < 60 and el.count_name:
                # Every object has its own count, held in the sibling branch
                # that holds the counter, one value per object.
                # ReadingEntries.md 4.2.
                pos = start
                for n in self.counts_column(br, el.count_name, entry, objects):
                    pos = decoder.read_element_value(
                        el, pos, {el.count_name: n}).end
                return pos
            return decoder.read_column(el, objects, start)

        # fType <= 2 with fBranchCount: the Int_t n; Float_t *x; //[n] shape,
        # whose element is kOffsetP + T and whose count is on the other branch.
        counters: dict[str, int] = {}
        if el.count_name and (br.count_slot >= 0
                              or OFFSET_P <= el.ftype < 60):
            counter = self.counter_branch(br, el.count_name)
            counters[el.count_name] = self.count_at(counter, entry)
        return decoder.read_element_value(el, start, counters).end


# --- an embedded basket, spec/04-ttree/TBasket.md section 4 ----------------

@dataclass
class EmbeddedBasket:
    """A TBasket streamed into another buffer rather than written as a record.

    `TBasket::Streamer` writes the complete TKey first
    (`root/tree/tree/src/TBasket.cxx:1111`), so the layout is the same fields in
    the same order as a record, but the arrays and the data follow the header
    inline, and every offset is relative to `start` rather than to a record.
    """

    start: int            # of the object body, i.e. the first TKey byte
    end: int              # one past the last byte the basket accounts for
    key_len: int          # fKeylen, which covers the key and the basket header
    basket: Basket
    block: int            # where the raw buffer copy begins; -1 if absent


def read_embedded_basket(buf: bytes, offset: int) -> EmbeddedBasket:
    """Read a TBasket object out of the buffer it was streamed into."""
    version = _i16(buf, offset + 4)
    large = version > LARGE_KEY_VERSION
    obj_len = _i32(buf, offset + 6)
    key_len = _i16(buf, offset + 14)
    seek = offset + (18 if large else 18)
    o = offset + (34 if large else 26)
    for _ in range(3):                      # fClassName, fName, fTitle
        _, o = _counted_string(buf, o)

    basket_version = _i16(buf, o)
    buffer_size = _i32(buf, o + 2)
    nev_buf_size = _i32(buf, o + 6)
    o += 10
    io_bits = 0
    if nev_buf_size < 0:
        nev_buf_size = -nev_buf_size
        io_bits = buf[o]
        o += 1
        if io_bits == 0 or io_bits & IO_RESERVED:
            raise FormatError(
                f"embedded basket at {offset}: fIOBits {io_bits:#04x} is zero or "
                f"uses the reserved bit 7")
    nev_buf = _i32(buf, o)
    last = _i32(buf, o + 4)
    flag = buf[o + 8]
    o += 9
    if o - offset != key_len:
        raise FormatError(
            f"embedded basket at {offset}: header ends {o - offset} bytes in, "
            f"fKeylen is {key_len}")

    generate = flag >= FLAG_GENERATE
    if generate:
        flag -= FLAG_GENERATE
    offsets = None
    if not generate and flag and flag % 10 != FLAG_NO_OFFSETS and nev_buf:
        # An empty basket writes no array even when the flag says it has one:
        # both sides are guarded by fNevBuf (root/tree/tree/src/TBasket.cxx:1153,
        # root/tree/tree/src/TBasket.cxx:1046-1071).
        #
        # Unlike the record form, the count here is fNevBuf exactly: the
        # streamer writes the raw array (root/tree/tree/src/TBasket.cxx:1154).
        count = _i32(buf, o)
        if count != nev_buf:
            raise FormatError(
                f"embedded basket at {offset}: offset array count {count}, "
                f"expected fNevBuf = {nev_buf}")
        offsets = list(struct.unpack_from(f">{count}i", buf, o + 4))
        o += 4 + 4 * count
        if 20 < flag < FLAG_DISPLACEMENT:
            offsets = [v & ~DISPLACEMENT_MASK for v in offsets]
        if flag > FLAG_DISPLACEMENT:
            o += 4 + 4 * _i32(buf, o)       # the displacement array
    # The raw block follows the arrays. It is fLast bytes taken from the start
    # of the basket's own buffer, so its first fKeylen bytes are the reserved
    # key area and every entry offset is an offset into it.
    block = o
    if flag == 1 or flag > FLAG_HAS_DATA:
        o = block + last
    else:
        block = -1
    basket = Basket(version=basket_version, buffer_size=buffer_size,
                    nev_buf_size=nev_buf_size, nev_buf=nev_buf, last=last,
                    flag=flag, io_bits=io_bits, generated=generate,
                    key_len=key_len, header_offset=offset + key_len - 9,
                    data_start=block + key_len if block >= 0 else -1,
                    data_end=block + last if block >= 0 else -1,
                    entry_offsets=offsets)
    return EmbeddedBasket(start=offset, end=o, key_len=key_len, basket=basket,
                          block=block)


def embedded_entry_range(emb: EmbeddedBasket, index: int) -> tuple[int, int]:
    """The absolute byte range of one entry of an embedded basket."""
    b = emb.basket
    if not 0 <= index < b.nev_buf:
        raise FormatError(f"entry {index} outside [0, {b.nev_buf})")
    if emb.block < 0:
        raise FormatError(f"embedded basket at {emb.start} carries no data")
    if b.entry_offsets is None:
        start = emb.block + emb.key_len + index * b.nev_buf_size
        return start, start + b.nev_buf_size
    start = emb.block + b.entry_offsets[index]
    if index + 1 < b.nev_buf:
        return start, emb.block + b.entry_offsets[index + 1]
    return start, b.data_end


# -- RNTuple -----------------------------------------------------------------
#
# Written from spec/05-rntuple/BinaryFormatSpecification.md (ROOT's own
# specification, tracked verbatim) and from the errata beside it, so that where
# this reader and ROOT disagree, one of the two is wrong and the disagreement can
# be detected. spec/05-rntuple/ERRATA.md 2, 3 and 5 are all places where
# following the document literally would fail here.
#
# Everything below the anchor is LITTLE-endian; the anchor is a TKey payload and
# is big-endian like the rest of the file (NOTES.md 3). The helper names give
# the byte order.


def _u16le(b: bytes, o: int) -> int:
    return struct.unpack_from("<H", b, o)[0]


def _u32le(b: bytes, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]


def _i64le(b: bytes, o: int) -> int:
    return struct.unpack_from("<q", b, o)[0]


def _u64le(b: bytes, o: int) -> int:
    return struct.unpack_from("<Q", b, o)[0]


RN_ENVELOPE_HEADER = 0x01
RN_ENVELOPE_FOOTER = 0x02
RN_ENVELOPE_PAGELIST = 0x03
RN_CHECKSUM_BYTES = 8


@dataclass
class RNTupleAnchor:
    """The ROOT::RNTuple object that anchors an RNTuple in a TFile.

    Big-endian. Note the two fields the document's schema does not show
    (ERRATA 2) and the checksum outside the byte count (ERRATA 3).
    """

    byte_count: int
    class_version: int
    epoch: int
    major: int
    minor: int
    patch: int
    seek_header: int
    nbytes_header: int
    len_header: int
    seek_footer: int
    nbytes_footer: int
    len_footer: int
    max_key_size: int
    checksum: int
    end: int

    @property
    def version(self) -> str:
        return f"{self.epoch}.{self.major}.{self.minor}.{self.patch}"


def read_rntuple_anchor(buf: bytes, rec: Record) -> RNTupleAnchor:
    """The anchor of `rec`, a ROOT::RNTuple record. Big-endian throughout.

    The offsets below start six bytes into the payload, not at it: the byte
    count and the class version come first and the document's anchor schema does
    not show them (ERRATA 2).

    The anchor is an ordinary TKey payload, so it may be compressed like any
    other record; RNTuple compresses it whenever compression is on, as
    rntuple/compressed shows. Until 2026-09-22 this read the raw file at the
    payload and took the first four bytes of a zlib stream for a byte count
    (PLAN-corpus.md C6). Every offset below is into the decompressed payload;
    the seeks it returns are file offsets and are used against the file.
    """
    buf = object_data(buf, rec)
    start, end = payload_range(rec)
    word = _u32(buf, start)
    if not word & BYTE_COUNT_MASK:
        raise FormatError(f"RNTuple anchor at {start} has no byte count")
    byte_count = word & ~BYTE_COUNT_MASK

    versions = [_u16(buf, start + 6 + 2 * i) for i in range(4)]
    seeks = [_u64(buf, start + 14 + 8 * i) for i in range(7)]

    # ERRATA 3: the checksum is appended after the struct, so it falls outside
    # the byte count. A reader that trusts the byte count to delimit the object
    # never sees it; one that checks the byte count against the payload length
    # finds a mismatch of exactly eight and may reject a good file.
    body_end = start + 4 + byte_count
    if end - body_end != RN_CHECKSUM_BYTES:
        raise FormatError(
            f"RNTuple anchor at {start}: {end - body_end} bytes follow the byte "
            f"count, expected {RN_CHECKSUM_BYTES} of checksum")

    return RNTupleAnchor(
        byte_count=byte_count,
        class_version=_u16(buf, start + 4),
        epoch=versions[0], major=versions[1],
        minor=versions[2], patch=versions[3],
        seek_header=seeks[0], nbytes_header=seeks[1], len_header=seeks[2],
        seek_footer=seeks[3], nbytes_footer=seeks[4], len_footer=seeks[5],
        max_key_size=seeks[6],
        checksum=_u64(buf, body_end), end=end)


@dataclass
class RNEnvelope:
    """An envelope: `typeAndSize`, a payload, and a trailing XXH3 checksum.

    ERRATA 5: `length` covers the whole envelope INCLUDING the checksum, and the
    checksum covers everything before itself. Both halves matter.
    """

    type_id: int
    length: int
    start: int          # of the type/length word
    body: int           # first payload byte
    body_end: int       # one past the payload, i.e. where the checksum starts
    checksum: int


def read_rn_envelope(buf: bytes, offset: int) -> RNEnvelope:
    word = _u64le(buf, offset)
    type_id, length = word & 0xFFFF, word >> 16
    if length < 8 + RN_CHECKSUM_BYTES:
        raise FormatError(f"envelope at {offset} declares {length} bytes")
    body_end = offset + length - RN_CHECKSUM_BYTES
    return RNEnvelope(type_id=type_id, length=length, start=offset,
                      body=offset + 8, body_end=body_end,
                      checksum=_u64le(buf, body_end))


@dataclass
class RNFrame:
    """A record frame (positive size) or a list frame (negative size)."""

    size: int
    items: int | None   # None for a record frame
    start: int
    body: int
    end: int

    @property
    def is_list(self) -> bool:
        return self.items is not None


def read_rn_frame(buf: bytes, offset: int) -> RNFrame:
    raw = _i64le(buf, offset)
    if raw == 0:
        raise FormatError(f"frame at {offset} has size 0")
    if raw > 0:
        return RNFrame(size=raw, items=None, start=offset, body=offset + 8,
                       end=offset + raw)
    size = -raw
    return RNFrame(size=size, items=_u32le(buf, offset + 8), start=offset,
                   body=offset + 12, end=offset + size)


def read_rn_string(buf: bytes, offset: int) -> tuple[str, int]:
    """A u32 length then that many bytes, NOT the counted string of
    Conventions 5.1; a reader coming from TFile easily confuses the two."""
    n = _u32le(buf, offset)
    return buf[offset + 4:offset + 4 + n].decode("utf-8"), offset + 4 + n


# The structural roles of a field, and the column types, both from the tables in
# the tracked specification. Column type 0x17 is deliberately absent: the
# document lists SplitReal16 there and ROOT has no such type (ERRATA 6).
RN_STRUCTURE = {0x00: "plain", 0x01: "collection", 0x02: "record",
                0x03: "variant", 0x04: "streamer"}
RN_COLUMN_TYPE = {
    0x00: "Bit", 0x01: "Byte", 0x02: "Char", 0x03: "Int8", 0x04: "UInt8",
    0x05: "Int16", 0x06: "UInt16", 0x07: "Int32", 0x08: "UInt32",
    0x09: "Int64", 0x0A: "UInt64", 0x0B: "Real16", 0x0C: "Real32",
    0x0D: "Real64", 0x0E: "Index32", 0x0F: "Index64", 0x10: "Switch",
    0x11: "SplitInt16", 0x12: "SplitUInt16", 0x13: "SplitInt32",
    0x14: "SplitUInt32", 0x15: "SplitInt64", 0x16: "SplitUInt64",
    0x18: "SplitReal32", 0x19: "SplitReal64", 0x1A: "SplitIndex32",
    0x1B: "SplitIndex64", 0x1C: "Real32Trunc", 0x1D: "Real32Quant",
}

RN_FLAG_REPETITIVE = 0x01
RN_FLAG_PROJECTED = 0x02
RN_FLAG_CHECKSUM = 0x04
RN_FLAG_SOA = 0x08


@dataclass
class RNField:
    start: int          # of its record frame, for a case.toml assertion
    field_id: int
    parent_id: int
    structure: int
    flags: int
    name: str
    type_name: str
    type_alias: str
    description: str
    field_version: int = 0
    type_version: int = 0
    array_size: int | None = None
    source_id: int | None = None
    type_checksum: int | None = None

    @property
    def role(self) -> str:
        return RN_STRUCTURE.get(self.structure, f"unknown({self.structure})")


@dataclass
class RNColumn:
    start: int          # of its record frame
    field_id_offset: int    # where the type code sits, which is start + 8
    column_id: int
    type_code: int
    bits: int
    field_id: int
    flags: int
    representation: int
    first_element: int | None = None
    value_range: tuple[float, float] | None = None

    @property
    def type_name(self) -> str:
        return RN_COLUMN_TYPE.get(self.type_code, f"unknown({self.type_code:#x})")


@dataclass
class RNAliasColumn:
    """A column with no pages of its own. BinaryFormatSpecification "Alias columns".

    Alias columns have no column ID: they are not referenced from the footer or
    the page list, where only physical IDs may appear.
    """

    start: int
    physical_id: int
    field_id: int


@dataclass
class RNTypeInfo:
    """One extra-type-information record of the header envelope.

    Content identifier 0 is a ROOT-streamed TList of TStreamerInfo, which is why
    `content` is a byte range rather than a decoded value: it belongs to the
    object layer of spec/02-serialization/ rather than to RNTuple's own encoding.
    """

    start: int
    content_id: int
    type_version: int
    type_name: str
    content: int        # where the payload begins
    end: int


@dataclass
class RNSchema:
    name: str
    description: str
    writer: str
    feature_flags: list[int]
    fields: list[RNField]
    columns: list[RNColumn]
    alias_columns: list[RNAliasColumn] = field(default_factory=list)
    type_info: list[RNTypeInfo] = field(default_factory=list)


def _read_rn_field(buf: bytes, offset: int, field_id: int) -> RNField:
    frame = read_rn_frame(buf, offset)
    o = frame.body
    field_version = _u32le(buf, o); o += 4
    type_version = _u32le(buf, o); o += 4
    parent = _u32le(buf, o); o += 4
    structure = _u16le(buf, o); o += 2
    flags = _u16le(buf, o); o += 2
    name, o = read_rn_string(buf, o)
    type_name, o = read_rn_string(buf, o)
    type_alias, o = read_rn_string(buf, o)
    description, o = read_rn_string(buf, o)
    field = RNField(start=offset, field_id=field_id, parent_id=parent,
                    structure=structure,
                    flags=flags, name=name, type_name=type_name,
                    type_alias=type_alias, description=description,
                    field_version=field_version, type_version=type_version)
    # The optional trailing values, in flag order.
    if flags & RN_FLAG_REPETITIVE:
        field.array_size = _u64le(buf, o); o += 8
    if flags & RN_FLAG_PROJECTED:
        field.source_id = _u32le(buf, o); o += 4
    if flags & RN_FLAG_CHECKSUM:
        field.type_checksum = _u32le(buf, o); o += 4
    if o > frame.end:
        raise FormatError(f"field record at {offset} overran its frame")
    return field


def _read_rn_column(buf: bytes, offset: int, column_id: int) -> RNColumn:
    frame = read_rn_frame(buf, offset)
    o = frame.body
    type_code = _u16le(buf, o); o += 2
    bits = _u16le(buf, o); o += 2
    field_id = _u32le(buf, o); o += 4
    flags = _u16le(buf, o); o += 2
    representation = _u16le(buf, o); o += 2
    column = RNColumn(start=offset, field_id_offset=frame.body,
                      column_id=column_id, type_code=type_code, bits=bits,
                      field_id=field_id, flags=flags,
                      representation=representation)
    if flags & 0x01:                             # deferred column
        column.first_element = _i64le(buf, o); o += 8
    if flags & 0x02:                             # a value range follows
        column.value_range = struct.unpack_from("<dd", buf, o)
        o += 16
    if o > frame.end:
        raise FormatError(f"column record at {offset} overran its frame")
    return column


def read_rn_feature_flags(buf: bytes, offset: int) -> tuple[list[int], int]:
    """Words of feature flags, continuing while the top bit is set."""
    flags = []
    while True:
        word = _u64le(buf, offset)
        offset += 8
        flags.append(word & ~(1 << 63))
        if not word & (1 << 63):
            return flags, offset


def read_rn_header(buf: bytes, envelope: RNEnvelope) -> RNSchema:
    """The schema description of a header envelope.

    Only an uncompressed envelope is read: this is an audit tool for fixtures
    written with compression off, not a general RNTuple reader, and failing
    loudly is better than half-decoding a zstd block.
    """
    if envelope.type_id != RN_ENVELOPE_HEADER:
        raise FormatError(f"envelope type {envelope.type_id}, expected a header")
    o = envelope.body
    feature_flags, o = read_rn_feature_flags(buf, o)
    name, o = read_rn_string(buf, o)
    description, o = read_rn_string(buf, o)
    writer, o = read_rn_string(buf, o)

    fields: list[RNField] = []
    frame = read_rn_frame(buf, o)
    if not frame.is_list:
        raise FormatError(f"field list at {o} is a record frame")
    pos = frame.body
    for i in range(frame.items):
        fields.append(_read_rn_field(buf, pos, i))
        pos = read_rn_frame(buf, pos).end
    o = frame.end

    columns: list[RNColumn] = []
    frame = read_rn_frame(buf, o)
    if not frame.is_list:
        raise FormatError(f"column list at {o} is a record frame")
    pos = frame.body
    for i in range(frame.items):
        columns.append(_read_rn_column(buf, pos, i))
        pos = read_rn_frame(buf, pos).end
    o = frame.end

    # Two more lists, and both are usually empty: alias columns exist only for a
    # projected field, and extra type information only for a streamed one.
    aliases: list[RNAliasColumn] = []
    frame = read_rn_frame(buf, o)
    if not frame.is_list:
        raise FormatError(f"alias column list at {o} is a record frame")
    pos = frame.body
    for _ in range(frame.items):
        inner = read_rn_frame(buf, pos)
        aliases.append(RNAliasColumn(start=pos,
                                     physical_id=_u32le(buf, inner.body),
                                     field_id=_u32le(buf, inner.body + 4)))
        pos = inner.end
    o = frame.end

    type_info: list[RNTypeInfo] = []
    frame = read_rn_frame(buf, o)
    if not frame.is_list:
        raise FormatError(f"extra type information list at {o} is a record frame")
    pos = frame.body
    for _ in range(frame.items):
        inner = read_rn_frame(buf, pos)
        content_id = _u32le(buf, inner.body)
        type_version = _u32le(buf, inner.body + 4)
        type_name, after = read_rn_string(buf, inner.body + 8)
        type_info.append(RNTypeInfo(start=pos, content_id=content_id,
                                    type_version=type_version,
                                    type_name=type_name, content=after,
                                    end=inner.end))
        pos = inner.end

    return RNSchema(name=name, description=description, writer=writer,
                    feature_flags=feature_flags, fields=fields, columns=columns,
                    alias_columns=aliases, type_info=type_info)


def read_rntuple(buf: bytes, rec: Record) -> tuple[RNTupleAnchor, RNSchema]:
    """The anchor and header schema of the RNTuple anchored at `rec`.

    A compressed header envelope is decompressed first. RNTuple tests for that
    by equality (`nbytes == len` means stored unmodified), where the container
    layer uses `>` and tolerates a raw payload longer than its length
    (spec/05-rntuple/NOTES.md 2).
    """
    anchor = read_rntuple_anchor(buf, rec)
    start, nbytes, length = (anchor.seek_header, anchor.nbytes_header,
                             anchor.len_header)
    if nbytes == length:
        body = buf
        offset = start
    else:
        body = decompress_blocks(buf, start, start + nbytes, length,
                                 f"RNTuple header envelope at {start}")
        offset = 0
    return anchor, read_rn_header(body, read_rn_envelope(body, offset))
