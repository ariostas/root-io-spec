#!/usr/bin/env python3
"""Pure-Python ROOT file writer, built from `spec/06-writing/`.

It is the executable form of that layer, in the same way `tools/rootfile.py` is
the executable form of the reading layers -- and, like it, deliberately an
independent implementation: written from the specification rather than from
ROOT's writing code, so that the two disagreeing is a detectable event.

Three properties are on purpose:

* **Deterministic.** The timestamp and the UUID are inputs, not read from the
  clock, so a file is byte-reproducible and `data/written/` needs no digest
  normalization (`tools/normalize.py` exists for the ROOT-written fixtures,
  which cannot be).
* **Create-only.** Nothing here updates an existing file, so free-space reuse and
  key cycles never arise (`spec/06-writing/index.md` 4).
* **Small-file layout only.** A file this writer produces is refused if it would
  cross 2 GB, rather than written in a layout that has not been exercised here.

No third-party dependencies.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

#: spec/01-container/FileHeader.md 1 -- ROOT reserves 100 bytes for the header.
BEGIN = 100
#: spec/01-container/Record.md 2 -- the fixed part of a small-form key.
KEY_FIXED = 26
#: spec/01-container/Directory.md 2 -- 48 bytes of fields plus 12 reserved (5).
DIR_RECORD_LEN = 60
#: spec/01-container/FileHeader.md 5.7 -- 4 in the small layout.
UNITS_SMALL = 4
#: spec/01-container/LargeFiles.md 1 -- every large-file test is on this value.
BIG = 2000000000
#: The default ROOT writes for a fresh key (spec/01-container/Record.md 4.6).
CYCLE = 1

#: TObject::kMustCleanup, which ROOT sets on anything owned by a directory.
K_MUST_CLEANUP = 0x8


class WriteError(Exception):
    pass


# ---------------------------------------------------------------------------
# Primitives, spec/00-conventions.md. Everything in a record is big-endian.
# ---------------------------------------------------------------------------

def i16(v: int) -> bytes:
    return struct.pack(">h", v)


def u16(v: int) -> bytes:
    return struct.pack(">H", v)


def i32(v: int) -> bytes:
    return struct.pack(">i", v)


def u32(v: int) -> bytes:
    return struct.pack(">I", v)


def i64(v: int) -> bytes:
    return struct.pack(">q", v)


def f32(v: float) -> bytes:
    return struct.pack(">f", v)


def f64(v: float) -> bytes:
    return struct.pack(">d", v)


def counted_string(s: str) -> bytes:
    """A counted string: one length byte, or 255 then an i32 (conventions 5.1)."""
    raw = s.encode("utf-8")
    if len(raw) < 255:
        return bytes([len(raw)]) + raw
    return b"\xff" + i32(len(raw)) + raw


def string_len(s: str) -> int:
    n = len(s.encode("utf-8"))
    return n + (1 if n < 255 else 5)


def pack_datime(year: int, month: int, day: int,
                hour: int, minute: int, second: int) -> int:
    """TDatime's packed form (`root/core/base/src/TDatime.cxx:392`).

    Six bit fields in one 32-bit word, with the year biased by 1995. A writer
    that has no meaningful time still has to put something here; 0 is legal and
    ROOT prints it as 1995-00-00.
    """
    if not 1995 <= year <= 1995 + 63:
        raise WriteError(f"year {year} is outside TDatime's range 1995-2058")
    return ((year - 1995) << 26 | month << 22 | day << 17
            | hour << 12 | minute << 6 | second)


#: A fixed, obviously-synthetic stamp, so nothing reads as "written just now".
#: 2000-01-01 00:00:00.
DEFAULT_DATIME = pack_datime(2000, 1, 1, 0, 0, 0)

#: A fixed UUID. Version 4 (random) in RFC 4122 terms, but constant on purpose;
#: spec/01-container/FileHeader.md 6.
DEFAULT_UUID = bytes.fromhex("00112233445566778899aabbccddeeff")


# ---------------------------------------------------------------------------
# The buffer framing layer, spec/02-serialization/Buffer.md, from the writing
# side: spec/06-writing/WritingObjects.md.
# ---------------------------------------------------------------------------

BYTE_COUNT_MASK = 0x40000000


def framed(version: int, body: bytes) -> bytes:
    """`body` preceded by a byte count and a version word (Buffer.md 2).

    The count covers the version word and the body, and excludes its own four
    bytes.
    """
    if version > 0x3FFF:
        raise WriteError(f"version {version} does not fit in 14 bits")
    payload = u16(version) + body
    return u32(BYTE_COUNT_MASK | len(payload)) + payload


def tobject(bits: int = 0, unique_id: int = 0) -> bytes:
    """A `TObject` base: version 1, `fUniqueID`, `fBits` (Buffer.md 3).

    Ten bytes, and unframed -- `TObject::Streamer` writes no byte count. ROOT
    masks kIsOnHeap and kNotDeleted out of `fBits` on the way to the file, so a
    writer that has no bits to set writes 0.
    """
    return u16(1) + u32(unique_id) + u32(bits)


def tnamed(name: str, title: str, bits: int = 0) -> bytes:
    """A framed `TNamed`: its `TObject` base, then two counted strings."""
    return framed(1, tobject(bits) + counted_string(name) + counted_string(title))


def tobjstring(s: str) -> bytes:
    """A `TObjString`: a `TObject` base and one counted string, framed."""
    return framed(1, tobject() + counted_string(s))


# ---------------------------------------------------------------------------
# Compression, spec/01-container/Compression.md, from the writing side.
# ---------------------------------------------------------------------------

#: The largest uncompressed block, and the cap of the 24-bit size fields.
MAX_ZIP_BUF = 0xFFFFFF
#: Below this ROOT does not attempt compression at all (TKey.cxx:262-264).
MIN_COMPRESS = 256


def _u24le(v: int) -> bytes:
    return bytes((v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF))


def zlib_blocks(data: bytes, level: int) -> bytes | None:
    """`data` as one or more ROOT compression blocks, or None if it did not pay.

    Each block is a 9-byte header -- `ZL`, method 8, then the compressed and
    uncompressed sizes as 24-bit **little-endian** fields inside an otherwise
    big-endian format -- followed by a zlib stream (`Compression.md` 2 and 4).
    A payload above `MAX_ZIP_BUF` is split into blocks of that many
    *uncompressed* bytes each, and the block count is stored nowhere
    (`Compression.md` 7).

    Returns None when the result is not smaller than the input, which is the
    condition ROOT uses to fall back to storing the payload raw
    (`root/io/io/src/TKey.cxx:276-284`).
    """
    import zlib
    out = bytearray()
    for start in range(0, len(data), MAX_ZIP_BUF):
        chunk = data[start:start + MAX_ZIP_BUF]
        body = zlib.compress(chunk, level)
        if len(body) > MAX_ZIP_BUF:
            return None
        out += b"ZL" + bytes([8]) + _u24le(len(body)) + _u24le(len(chunk))
        out += body
    return bytes(out) if len(out) < len(data) else None


def compression_level(setting: int) -> int:
    """The level half of `fCompress`, which is `algorithm * 100 + level`."""
    return setting % 100


# ---------------------------------------------------------------------------
# Keys and records, spec/06-writing/WritingFiles.md.
# ---------------------------------------------------------------------------

@dataclass
class Key:
    """One key image. `spec/01-container/Record.md` 2, small form only."""

    class_name: str
    name: str
    title: str
    obj_len: int
    nbytes: int
    seek_key: int
    seek_pdir: int
    datime: int = DEFAULT_DATIME
    cycle: int = CYCLE
    version: int = 4

    @property
    def key_len(self) -> int:
        return (KEY_FIXED + string_len(self.class_name)
                + string_len(self.name) + string_len(self.title))

    def to_bytes(self) -> bytes:
        if max(self.seek_key, self.seek_pdir) > BIG:
            raise WriteError(
                "an offset past 2000000000 needs the large key form; "
                "see spec/01-container/LargeFiles.md 3")
        return (i32(self.nbytes) + i16(self.version) + i32(self.obj_len)
                + u32(self.datime) + i16(self.key_len) + i16(self.cycle)
                + i32(self.seek_key) + i32(self.seek_pdir)
                + counted_string(self.class_name)
                + counted_string(self.name) + counted_string(self.title))


@dataclass
class Obj:
    """One object to be written as a record of its own."""

    class_name: str
    name: str
    title: str
    payload: bytes


@dataclass
class _Placed:
    key: Key
    payload: bytes

    def to_bytes(self) -> bytes:
        return self.key.to_bytes() + self.payload


class FileWriter:
    """Builds a complete ROOT file in memory.

    The procedure is `spec/06-writing/WritingFiles.md` 3: place every record,
    then write the free list, then the header, because the header cannot be
    written until the end of the file is known.
    """

    def __init__(self, file_name: str, title: str = "", *,
                 version: int = 64004, datime: int = DEFAULT_DATIME,
                 uuid: bytes = DEFAULT_UUID, compress: int = 0):
        if len(uuid) != 16:
            raise WriteError("a TUUID is 16 bytes")
        # fCompress is algorithm * 100 + level (FileHeader.md 5.8). Only ZLIB
        # is implemented here; the others are somebody else's standards
        # (spec/index.md, what is out of scope).
        if compress != 0 and not 101 <= compress <= 109:
            raise WriteError(
                f"fCompress {compress} is not 0 or ZLIB (101-109); "
                "see spec/01-container/Compression.md 3")
        if version < 40000:
            raise WriteError("fVersion below 40000 selects the 48-byte "
                             "directory record; see Directory.md 5")
        self.file_name = file_name
        self.title = title
        self.version = version
        self.datime = datime
        self.uuid = uuid
        self.compress = compress
        self.objects: list[Obj] = []
        self.infos: list[Info] = []

    def add(self, obj: Obj) -> None:
        self.objects.append(obj)

    def add_info(self, info: Info) -> None:
        """Add a `TStreamerInfo` to the record this writer will emit.

        Optional for ROOT, which reads a class it has compiled in without one,
        and required in practice for everything else
        (`spec/06-writing/WritingFiles.md` 6.1).
        """
        self.infos.append(info)

    def _stored(self, payload: bytes) -> bytes:
        """`payload` as it goes on disk, compressed if that is smaller.

        ROOT does not attempt compression below 257 bytes
        (`root/io/io/src/TKey.cxx:262-264`); matching that is not required, but
        it keeps a diff against a ROOT-written file readable.
        """
        level = compression_level(self.compress)
        if level == 0 or len(payload) <= MIN_COMPRESS:
            return payload
        blocks = zlib_blocks(payload, level)
        return blocks if blocks is not None else payload

    # -- the file's own key, which names the file and the root directory ----

    def _self_key(self, seek_key: int, obj_len: int, seek_pdir: int = 0) -> Key:
        """A key carrying the file's name, title and class `TFile`.

        The root directory record, the key list and the free list all use it,
        which is why none of the three can be identified by its key
        (`spec/01-container/Directory.md` 6.2).
        """
        key = Key(class_name="TFile", name=self.file_name, title=self.title,
                  obj_len=obj_len, nbytes=0, seek_key=seek_key,
                  seek_pdir=seek_pdir, datime=self.datime)
        key.nbytes = key.key_len + obj_len
        return key

    @property
    def nbytes_name(self) -> int:
        """`fNbytesName`: the key plus the name and title repeated after it."""
        key_len = self._self_key(BEGIN, 0).key_len
        return key_len + string_len(self.file_name) + string_len(self.title)

    def _dir_payload(self, nbytes_keys: int, seek_keys: int) -> bytes:
        """The root directory record's payload (`Directory.md` 2, version 5).

        The name and title are repeated ahead of the directory's own fields,
        which is what makes `fNbytesName` larger than the key.
        """
        body = (u16(5) + u32(self.datime) + u32(self.datime)
                + i32(nbytes_keys) + i32(self.nbytes_name)
                + i32(BEGIN) + i32(0) + i32(seek_keys)
                + u16(1) + self.uuid)
        body += b"\x00" * (DIR_RECORD_LEN - len(body))
        return counted_string(self.file_name) + counted_string(self.title) + body

    # -- layout -----------------------------------------------------------

    def _record(self, class_name: str, name: str, title: str,
                payload: bytes, pos: int) -> _Placed:
        """One record: a key, and the payload as it goes on disk.

        `fObjlen` stays the **uncompressed** length whatever happens to the
        payload, because `fObjlen > fNbytes - fKeylen` is the only thing that
        tells a reader the payload is compressed (`Compression.md` 1).
        """
        stored = self._stored(payload)
        key = Key(class_name=class_name, name=name, title=title,
                  obj_len=len(payload), nbytes=0, seek_key=pos,
                  seek_pdir=BEGIN, datime=self.datime)
        key.nbytes = key.key_len + len(stored)
        return _Placed(key=key, payload=stored)

    def to_bytes(self) -> bytes:
        dir_obj_len = (string_len(self.file_name) + string_len(self.title)
                       + DIR_RECORD_LEN)
        dir_key = self._self_key(BEGIN, dir_obj_len)

        pos = BEGIN + dir_key.nbytes
        placed: list[_Placed] = []
        for obj in self.objects:
            rec = self._record(obj.class_name, obj.name, obj.title,
                               obj.payload, pos)
            placed.append(rec)
            pos += rec.key.nbytes

        # The StreamerInfo record: a TList named "StreamerInfo", written before
        # the key list because that is TFile::Close's order, and deliberately
        # *not* in the key list (WritingFiles.md 6).
        seek_info = nbytes_info = 0
        info_record = None
        if self.infos:
            key_len = Key(class_name="TList", name="StreamerInfo",
                          title="Doubly linked list", obj_len=0, nbytes=0,
                          seek_key=pos, seek_pdir=BEGIN).key_len
            payload = Payload(key_len)
            payload.tlist("", [i.write for i in self.infos])
            info_record = self._record("TList", "StreamerInfo",
                                       "Doubly linked list",
                                       bytes(payload.buf), pos)
            seek_info, nbytes_info = pos, info_record.key.nbytes
            pos += info_record.key.nbytes

        # The key list: a count, then each data record's key image verbatim
        # (Directory.md 6). The root directory's own key is not in it.
        images = b"".join(p.key.to_bytes() for p in placed)
        keys_payload = i32(len(placed)) + images
        seek_keys = pos
        keys_key = self._self_key(seek_keys, len(keys_payload), seek_pdir=BEGIN)
        pos += keys_key.nbytes

        # The free list: one entry, covering everything past the end of the
        # file (FreeSegments.md 2). Its own record has to be placed before the
        # entry can name the end, so the length is computed first.
        seek_free = pos
        free_key = self._self_key(seek_free, 10, seek_pdir=BEGIN)
        end = seek_free + free_key.nbytes
        if end > BIG:
            raise WriteError("this writer produces small-layout files only; "
                             "see spec/01-container/LargeFiles.md")
        free_payload = i16(1) + i32(end) + i32(BIG)

        out = bytearray(BEGIN)
        out[0:4] = b"root"
        out[4:8] = i32(self.version)
        out[8:12] = i32(BEGIN)
        out[12:16] = i32(end)
        out[16:20] = i32(seek_free)
        out[20:24] = i32(free_key.nbytes)
        out[24:28] = i32(1)                       # nfree
        out[28:32] = i32(self.nbytes_name)
        out[32:33] = bytes([UNITS_SMALL])
        out[33:37] = i32(self.compress)
        out[37:41] = i32(seek_info)               # WritingFiles.md 6
        out[41:45] = i32(nbytes_info)
        out[45:47] = u16(1)                       # TUUID version
        out[47:63] = self.uuid

        out += dir_key.to_bytes()
        out += self._dir_payload(keys_key.nbytes, seek_keys)
        for p in placed:
            out += p.to_bytes()
        if info_record is not None:
            out += info_record.to_bytes()
        out += keys_key.to_bytes() + keys_payload
        out += free_key.to_bytes() + free_payload

        if len(out) != end:
            raise WriteError(f"placed {len(out)} bytes, header says {end}")
        return bytes(out)

    def write(self, path) -> bytes:
        data = self.to_bytes()
        with open(path, "wb") as fh:
            fh.write(data)
        return data


# ---------------------------------------------------------------------------
# The object map, spec/02-serialization/Buffer.md 5 and 6, from the writing
# side: spec/06-writing/WritingObjects.md.
# ---------------------------------------------------------------------------

NEW_CLASS_TAG = 0xFFFFFFFF
CLASS_MASK = 0x80000000
#: Map positions 0 and 1 are reserved, so every real one is biased by 2.
MAP_OFFSET = 2


class Payload:
    """One record's object data, with the class and object maps.

    Map positions are measured from the start of the **record**, key included
    (`Buffer.md` 1), so the key's length is an input. A writer that measures
    from the start of the object data instead produces class tags that are off
    by `fKeylen` -- readable only by a reader that makes the same mistake.
    """

    def __init__(self, key_len: int):
        self.key_len = key_len
        self.buf = bytearray()
        self.classes: dict[str, int] = {}
        self.objects: dict[int, int] = {}

    @property
    def pos(self) -> int:
        return self.key_len + len(self.buf)

    def raw(self, data: bytes) -> None:
        self.buf += data

    def framed(self, version: int, build) -> None:
        """A byte count, a version word, and whatever `build` appends."""
        start = len(self.buf)
        self.buf += b"\x00\x00\x00\x00"
        self.buf += u16(version)
        build(self)
        n = len(self.buf) - start - 4
        self.buf[start:start + 4] = u32(BYTE_COUNT_MASK | n)

    def class_record(self, name: str) -> None:
        """Name a class, or refer back to where it was named (`Buffer.md` 5).

        A class is mapped at the position of its **tag** word; an object at the
        position of its **byte count**, four bytes earlier. Both then add 2.
        """
        tag_pos = self.pos
        if name in self.classes:
            self.raw(u32(CLASS_MASK | self.classes[name]))
        else:
            self.raw(u32(NEW_CLASS_TAG))
            # The one null-terminated string in the format.
            self.raw(name.encode("utf-8") + b"\x00")
            self.classes[name] = tag_pos + MAP_OFFSET

    def slot(self, class_name: str, version: int, build, key=None) -> None:
        """A pointer slot: a byte count, a class record, then the object.

        The object carries its own byte count and version word inside this
        one, so the outer count covers the class record as well.
        """
        start = len(self.buf)
        record_pos = self.pos
        self.buf += b"\x00\x00\x00\x00"
        self.class_record(class_name)
        self.framed(version, build)
        n = len(self.buf) - start - 4
        self.buf[start:start + 4] = u32(BYTE_COUNT_MASK | n)
        if key is not None:
            self.objects[key] = record_pos + MAP_OFFSET

    def null(self) -> None:
        """A null pointer: four zero bytes and nothing else (`Buffer.md` 6)."""
        self.raw(i32(0))

    def reference(self, key) -> None:
        """A reference to an object already written in this record."""
        self.raw(u32(self.objects[key]))

    def tobject(self, bits: int = 0, unique_id: int = 0) -> None:
        self.raw(tobject(bits, unique_id))

    def tnamed(self, name: str, title: str, bits: int = 0) -> None:
        def body(p: Payload) -> None:
            p.tobject(bits)
            p.raw(counted_string(name) + counted_string(title))
        self.framed(1, body)

    def tlist(self, name: str, entries, bits: int = 0) -> None:
        """A `TList` at version 5 (`StreamerInfo.md` 4).

        `entries` are callables appending one object slot each. Every entry is
        followed by an option-length byte, which is 0 when there is no option
        -- the single most common way to desynchronise on this record.
        """
        def body(p: Payload) -> None:
            p.tobject(bits)
            p.raw(counted_string(name) + i32(len(entries)))
            for entry in entries:
                entry(p)
                p.raw(b"\x00")
        self.framed(5, body)

    def tobjarray(self, name: str, entries, lower_bound: int = 0,
                  bits: int = 0, key=None) -> None:
        """A `TObjArray` at version 3 (`StreamerInfo.md` 5): no options.

        Emitted as a **pointer slot**, which is how it occurs: every use of it
        in the format is a `TObjArray *` member, so the record is preceded by a
        class record naming it. A writer that emits the bare framed object --
        the shape an embedded member object has -- is 18 bytes short and
        desynchronises the reader at the first element.
        """
        def body(p: Payload) -> None:
            p.tobject(bits)
            p.raw(counted_string(name) + i32(len(entries)) + i32(lower_bound))
            for entry in entries:
                entry(p)
        self.slot("TObjArray", 3, body, key=key)


# ---------------------------------------------------------------------------
# Streamer information, spec/02-serialization/StreamerInfo.md, from the
# writing side.
# ---------------------------------------------------------------------------

#: TVirtualStreamerInfo::kIsCompiled, which ROOT leaves set in fBits.
K_IS_COMPILED = 0x00010000

#: Current class versions of the records a streamer info is built from.
STREAMER_INFO_VERSION = 10
STREAMER_ELEMENT_VERSION = 4

#: Version of each element subclass (StreamerInfo.md 8).
ELEMENT_VERSIONS = {
    "TStreamerBase": 3,
    "TStreamerBasicType": 2,
    "TStreamerBasicPointer": 2,
    "TStreamerLoop": 2,
    "TStreamerObject": 2,
    "TStreamerObjectAny": 2,
    "TStreamerObjectPointer": 2,
    "TStreamerObjectAnyPointer": 1,
    "TStreamerString": 2,
    "TStreamerSTL": 3,
    "TStreamerSTLstring": 2,
}


@dataclass
class Element:
    """One `TStreamerElement`, in the form a writer has to supply it."""

    cls: str
    name: str
    title: str
    ftype: int
    size: int
    type_name: str
    array_length: int = 0
    array_dim: int = 0
    max_index: tuple = (0, 0, 0, 0, 0)
    #: TStreamerBase only; goes in fMaxIndex[1] as fBaseCheckSum.
    base_version: int | None = None
    base_checksum: int | None = None
    #: TStreamerBasicPointer and TStreamerLoop.
    count_name: str = ""
    count_class: str = ""
    count_version: int = 0
    #: TStreamerSTL.
    stl_type: int = 0
    ctype: int = 0
    #: An enum member folds an extra 1 into the checksum (StreamerInfo.md 11).
    is_enum: bool = False

    @property
    def is_base(self) -> bool:
        return self.cls == "TStreamerBase"

    def indices(self) -> tuple:
        if self.is_base and self.base_checksum is not None:
            # fBaseCheckSum is a reference bound to fMaxIndex[1]
            # (StreamerInfo.md 9), so it travels in the base's array.
            return (self.max_index[0], self.base_checksum) + tuple(self.max_index[2:])
        return self.max_index

    def write(self, p: Payload) -> None:
        version = ELEMENT_VERSIONS[self.cls]

        def body(q: Payload) -> None:
            def base(r: Payload) -> None:
                r.tnamed(self.name, self.title)
                r.raw(i32(self.ftype) + i32(self.size)
                      + i32(self.array_length) + i32(self.array_dim))
                for v in self.indices():
                    # fMaxIndex is i32, but fMaxIndex[1] carries a checksum
                    # whose top bit may be set (StreamerInfo.md 9), so it is
                    # emitted as an unsigned word and reads back negative.
                    r.raw(u32(v & 0xFFFFFFFF))
                r.raw(counted_string(self.type_name))
            q.framed(STREAMER_ELEMENT_VERSION, base)
            if self.cls == "TStreamerBase":
                q.raw(i32(self.base_version if self.base_version is not None else 0))
            elif self.cls in ("TStreamerBasicPointer", "TStreamerLoop"):
                q.raw(i32(self.count_version)
                      + counted_string(self.count_name)
                      + counted_string(self.count_class))
            elif self.cls == "TStreamerSTL":
                q.raw(i32(self.stl_type) + i32(self.ctype))

        p.slot(self.cls, version, body, key=id(self))


@dataclass
class Info:
    """One `TStreamerInfo`: the description of one class's layout."""

    name: str
    class_version: int
    elements: list
    title: str = ""
    checksum: int | None = None

    def write(self, p: Payload) -> None:
        total = self.checksum if self.checksum is not None else checksum(self)

        def body(q: Payload) -> None:
            # kIsCompiled is an artifact of ROOT's writer and is persisted
            # (StreamerInfo.md 6). A reader ignores it; reproducing it is what
            # lets a record be compared byte for byte with a ROOT-written one.
            q.tnamed(self.name, self.title, bits=K_IS_COMPILED)
            q.raw(u32(total) + i32(abs(self.class_version)))
            q.tobjarray("", [e.write for e in self.elements])

        # ROOT leaves kIsCompiled set in the info's fBits, and it is persisted
        # (StreamerInfo.md 6). It is an artifact of the writer, ignorable on
        # read -- but reproducing it is what makes a byte comparison against a
        # ROOT-written record possible.
        p.slot("TStreamerInfo", STREAMER_INFO_VERSION, body, key=id(self))


#: The type names an integer member can carry without being an enum. Anything
#: else at fType 3 is one, which is how an enum can be recognised in a record
#: at all -- see looks_like_enum.
PRIMITIVE_TYPE_NAMES = {
    "bool", "char", "signed char", "unsigned char", "short", "unsigned short",
    "int", "unsigned int", "long", "unsigned long", "long long",
    "unsigned long long", "float", "double", "long double",
    "Bool_t", "Char_t", "UChar_t", "Short_t", "UShort_t", "Int_t", "UInt_t",
    "Long_t", "ULong_t", "Long64_t", "ULong64_t", "Float_t", "Double_t",
}


def looks_like_enum(ftype: int, type_name: str) -> bool:
    """Whether an element describes an enum member, from the record alone.

    `TStreamerInfo::Build` stores every enum as an Int_t with `fType` 3, so the
    two are indistinguishable by type code -- but `fTypeName` keeps the enum's
    own qualified name. ROOT's own checksum code uses exactly this test
    (`root/io/io/src/TStreamerInfo.cxx:3612-3620`), so it is the rule rather
    than a guess. It matters because an enum folds an extra 1 into the
    checksum. See `spec/02-serialization/StreamerInfo.md` 11.1.
    """
    return ftype == 3 and type_name not in PRIMITIVE_TYPE_NAMES


def _acc_str(acc: int, s: str) -> int:
    for c in s.encode("utf-8"):
        acc = (acc * 3 + c) & 0xFFFFFFFF
    return acc


def _acc_num(acc: int, n: int) -> int:
    return (acc * 3 + n) & 0xFFFFFFFF


def checksum(info: Info) -> int:
    """`fCheckSum` for an info, per `StreamerInfo.md` 11 (current variant).

    Unsigned 32-bit throughout, wrapping. The bases come first as
    name-plus-checksum pairs, then every non-base member with its name, its
    resolved type name, its array extents and the bracketed part of its
    comment.
    """
    acc = _acc_str(0, info.name)
    for e in info.elements:
        if e.is_base:
            acc = _acc_str(acc, e.name)
            acc = _acc_num(acc, e.base_checksum or 0)
    for e in info.elements:
        if e.is_base:
            continue
        if e.is_enum:
            acc = _acc_num(acc, 1)
        acc = _acc_str(acc, e.name)
        acc = _acc_str(acc, e.type_name)
        for i in range(e.array_dim):
            acc = _acc_num(acc, e.max_index[i])
        if "[" in e.title and "]" in e.title[e.title.index("[") + 1:]:
            inner = e.title[e.title.index("[") + 1:]
            acc = _acc_str(acc, inner[:inner.index("]")])
    return acc
