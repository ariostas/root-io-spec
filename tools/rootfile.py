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
    return rec, p


# ---------------------------------------------------------------------------
# The buffer framing layer, spec/02-serialization/Buffer.md.
#
# This is deliberately an independent implementation of what that document
# specifies, written from the document rather than from ROOT's code, so that the
# two disagreeing is a detectable event.
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
    return rec.nbytes - rec.key_len != rec.obj_len


def payload_range(rec: Record) -> tuple[int, int]:
    """File offsets of the payload of an uncompressed record."""
    start = rec.offset + rec.key_len
    return start, start + rec.obj_len


def skip_tobject(buf: bytes, offset: int) -> int:
    """Skip a TObject base: version, fUniqueID, fBits, and a pidf if referenced.

    Buffer.md section 7. There is no byte count.
    """
    bits = _u32(buf, offset + 6)
    return offset + 10 + (2 if bits & IS_REFERENCED else 0)


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
    new-class record with no byte count -- a form no fixture contains.
    """
    word = _u32(buf, offset)
    if word == 0:
        return Slot(offset=offset, kind="null", end=offset + 4)
    if not (word & BYTE_COUNT_MASK) and word != NEW_CLASS_TAG:
        return Slot(offset=offset, kind="reference", end=offset + 4, reference=word)

    if word == NEW_CLASS_TAG:
        raise FormatError(f"new-class record with no byte count at {offset}")
    byte_count = word & ~BYTE_COUNT_MASK
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
# These classes cannot be read using streamer info, because they are what the
# streamer info is made of, so the layout below is hardcoded -- which is exactly
# the bootstrap problem the specification describes.
# ---------------------------------------------------------------------------

# TStreamerElement status bits that survive to disk, in the TObject base's fBits.
ELEMENT_HAS_RANGE = 1 << 6       # kHasRange: the title carries a Double32/Float16 range
ELEMENT_DO_NOT_DELETE = 1 << 13  # kDoNotDelete

# The subclass tail after the TStreamerElement base, as (member, reader) pairs.
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
    walked, which is what lets a class back-reference be resolved (Buffer.md
    section 5.2). It must be shared across one whole record.
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
                       max_index=el.max_index, type_name=el.type_name, tail=el.tail)

    # The TStreamerElement base.
    elem = read_frame(buf, o)
    eo = elem.body
    name, title, bits, eo = _skip_named(buf, eo)
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

    return Element(cls=cls, version=outer.version, name=name, title=title, bits=bits,
                   ftype=ftype, fsize=fsize, array_length=array_length,
                   array_dim=array_dim, max_index=max_index, type_name=type_name,
                   tail=tail)


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
