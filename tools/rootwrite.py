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

    def add_hist(self, hist) -> None:
        """Add a histogram, whose payload needs its own key's length.

        Map positions are measured from the start of the record
        (`WritingObjects.md` 4), so a payload cannot be built until the key is
        sized -- and a histogram's key length depends on its name and title.
        """
        key_len = Key(class_name=hist.class_name, name=hist.name,
                      title=hist.title, obj_len=0, nbytes=0, seek_key=0,
                      seek_pdir=BEGIN).key_len
        self.add(hist.obj(key_len))

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


# ---------------------------------------------------------------------------
# Histograms, spec/06-writing/WritingHistograms.md.
# ---------------------------------------------------------------------------

#: TH1::fMaximum and fMinimum when unset. Not a value -- a sentinel.
NO_LIMIT = -1111.0
#: TObject::kMustCleanup, which ROOT sets on a histogram (it lives in a
#: directory), and the two bits it leaves on TH1::fFunctions.
HIST_BITS = K_MUST_CLEANUP
FUNCTIONS_BITS = 0x00014000

#: What ROOT writes for a histogram's attribute bases, from gStyle. None of it
#: is required; reproducing it keeps a diff against a ROOT-written file short.
LINE_DEFAULTS = (602, 1, 1)          # fLineColor, fLineStyle, fLineWidth
FILL_DEFAULTS = (0, 1001)            # fFillColor, fFillStyle
MARKER_DEFAULTS = (1, 1, 1.0)        # fMarkerColor, fMarkerStyle, fMarkerSize


@dataclass
class Axis:
    """A `TAxis` at class version 10.

    `edges` holds `nbins + 1` bin edges for a variable-width axis and is the
    only way `fXbins` is non-empty; for a fixed-width axis it is None and
    `xmin`/`xmax` carry the range.
    """

    name: str = "xaxis"
    title: str = ""
    nbins: int = 1
    xmin: float = 0.0
    xmax: float = 1.0
    edges: list | None = None
    first: int = 0
    last: int = 0
    bits2: int = 0
    time_display: bool = False
    time_format: str = ""
    # TAttAxis, all of it free; these are ROOT's own values.
    ndivisions: int = 510
    axis_color: int = 1
    label_color: int = 1
    label_font: int = 42
    label_offset: float = 0.005
    label_size: float = 0.035
    tick_length: float = 0.03
    title_offset: float = 1.0
    title_size: float = 0.035
    title_color: int = 1
    title_font: int = 42

    def write(self, p: Payload) -> None:
        def body(q: Payload) -> None:
            q.tnamed(self.name, self.title)

            def att(r: Payload) -> None:
                r.raw(i32(self.ndivisions) + i16(self.axis_color)
                      + i16(self.label_color) + i16(self.label_font)
                      + f32(self.label_offset) + f32(self.label_size)
                      + f32(self.tick_length) + f32(self.title_offset)
                      + f32(self.title_size) + i16(self.title_color)
                      + i16(self.title_font))
            q.framed(4, att)

            q.raw(i32(self.nbins) + f64(self.xmin) + f64(self.xmax))
            q.raw(tarray_d(self.edges or []))
            q.raw(i32(self.first) + i32(self.last) + u16(self.bits2)
                  + bytes([1 if self.time_display else 0])
                  + counted_string(self.time_format))
            q.null()          # fLabels
            q.null()          # fModLabs
        p.framed(10, body)


def tarray_d(values) -> bytes:
    """A `TArrayD` as a member object: `fN` and the values, nothing else."""
    return i32(len(values)) + b"".join(f64(v) for v in values)


def tarray_f(values) -> bytes:
    return i32(len(values)) + b"".join(f32(v) for v in values)


@dataclass
class Stats:
    """`TH1`'s statistics, which are not derivable from the bin contents.

    `entries` counts every fill, in range or not; the four sums cover only the
    fills inside the range. `GetMean` is `tsumwx / tsumw`, so a writer that
    leaves them zero produces a histogram whose bins are right and whose mean
    is not.
    """

    entries: float = 0.0
    tsumw: float = 0.0
    tsumw2: float = 0.0
    tsumwx: float = 0.0
    tsumwx2: float = 0.0


def stats_from_cells(cells, axis: Axis, sumw2=None) -> Stats:
    """Statistics for binned input, using bin centres.

    The exact values ROOT would have written are unrecoverable once the data is
    binned -- it accumulates the true x of each fill. Bin centres are the best a
    writer starting from a histogram can do, and the result is self-consistent.

    Two of the five need care:

    * `entries` counts **fills**, not weight. From binned data the count is
      gone, so the sum of the contents is used; for unit weights the two agree.
    * `tsumw2` is the sum of squared *weights*, which is not the sum of squared
      bin contents. When `sumw2` is known it is exactly its in-range sum;
      without it, unit weights are assumed and it equals `tsumw`.
    """
    edges = axis.edges or [
        axis.xmin + (axis.xmax - axis.xmin) * i / axis.nbins
        for i in range(axis.nbins + 1)
    ]
    st = Stats(entries=float(sum(cells)))
    for i in range(1, len(cells) - 1):
        w = cells[i]
        x = 0.5 * (edges[i - 1] + edges[i])
        st.tsumw += w
        st.tsumw2 += sumw2[i] if sumw2 is not None else w
        st.tsumwx += w * x
        st.tsumwx2 += w * x * x
    return st


@dataclass
class Hist1D:
    """A `TH1F` or `TH1D`: the `TH1` base at version 8, then the `TArray` base.

    `cells` holds `nbins + 2` values -- underflow, the bins, overflow -- and its
    length is `TH1::fNcells`. `sumw2` is either None or the same length.
    """

    name: str
    title: str
    axis: Axis
    cells: list
    stats: Stats
    sumw2: list | None = None
    kind: str = "F"                  # "F" for TH1F, "D" for TH1D
    maximum: float = NO_LIMIT
    minimum: float = NO_LIMIT
    norm_factor: float = 0.0
    bar_offset: int = 0
    bar_width: int = 1000
    option: str = ""
    bin_stat_err_opt: int = 0        # kNormal
    stat_overflows: int = 2          # kNeutral
    contour: list | None = None

    @property
    def class_name(self) -> str:
        return f"TH1{self.kind}"

    def __post_init__(self):
        if self.kind not in ("F", "D"):
            raise WriteError("only TH1F and TH1D are implemented")
        if len(self.cells) != self.axis.nbins + 2:
            raise WriteError(
                f"{len(self.cells)} cells for {self.axis.nbins} bins; "
                "fNcells is nbins + 2 (WritingHistograms.md 3)")
        if self.sumw2 is not None and len(self.sumw2) != len(self.cells):
            raise WriteError("fSumw2 must be empty or one entry per cell")
        if self.axis.edges and len(self.axis.edges) != self.axis.nbins + 1:
            raise WriteError("fXbins holds nbins + 1 edges")

    def payload(self, key_len: int) -> bytes:
        p = Payload(key_len)

        def th1(q: Payload) -> None:
            q.tnamed(self.name, self.title, bits=HIST_BITS)

            def line(r: Payload) -> None:
                r.raw(b"".join(i16(v) for v in LINE_DEFAULTS))
            q.framed(2, line)

            def fill(r: Payload) -> None:
                r.raw(b"".join(i16(v) for v in FILL_DEFAULTS))
            q.framed(2, fill)

            def marker(r: Payload) -> None:
                r.raw(i16(MARKER_DEFAULTS[0]) + i16(MARKER_DEFAULTS[1])
                      + f32(MARKER_DEFAULTS[2]))
            q.framed(3, marker)

            q.raw(i32(len(self.cells)))            # fNcells
            self.axis.write(q)                     # fXaxis
            # A 1-D histogram still carries a Y and a Z axis, each with one bin.
            # The Y axis's fTitleOffset is 0 rather than 1 in ROOT's default
            # style, which is why the three attribute blocks are not identical
            # in a ROOT-written file. Free, like the rest of TAttAxis.
            Axis(name="yaxis", title_offset=0.0).write(q)
            Axis(name="zaxis").write(q)
            q.raw(i16(self.bar_offset) + i16(self.bar_width))
            q.raw(f64(self.stats.entries) + f64(self.stats.tsumw)
                  + f64(self.stats.tsumw2) + f64(self.stats.tsumwx)
                  + f64(self.stats.tsumwx2))
            q.raw(f64(self.maximum) + f64(self.minimum) + f64(self.norm_factor))
            q.raw(tarray_d(self.contour or []))    # fContour
            q.raw(tarray_d(self.sumw2 or []))      # fSumw2
            q.raw(counted_string(self.option))

            # fFunctions is declared `//->`, so it is streamed in place: a
            # framed TList with no class record and no pointer form.
            def functions(r: Payload) -> None:
                r.tobject(bits=FUNCTIONS_BITS)
                r.raw(counted_string("") + i32(0))
            q.framed(5, functions)

            q.raw(i32(0))                          # fBufferSize
            q.raw(b"\x00")                         # fBuffer: absent
            q.raw(i32(self.bin_stat_err_opt) + i32(self.stat_overflows))

        def body(q: Payload) -> None:
            q.framed(8, th1)
            q.raw(tarray_f(self.cells) if self.kind == "F"
                  else tarray_d(self.cells))
        p.framed(3, body)
        return bytes(p.buf)

    def obj(self, key_len: int) -> Obj:
        return Obj(class_name=self.class_name, name=self.name,
                   title=self.title, payload=self.payload(key_len))


# ---------------------------------------------------------------------------
# The streamer infos for the histogram chain. Fourteen classes, and a writer
# that wants its histograms readable by anything but ROOT has to emit them.
#
# They are built in dependency order so that each TStreamerBase element takes
# its fBaseCheckSum from the info built just before it: an error in one
# checksum then shows up twice, which is what makes the arrangement worth the
# awkwardness. Two checksums cannot be computed here and are supplied --
# spec/02-serialization/StreamerInfo.md 11.2 says why.
# ---------------------------------------------------------------------------

def _basic(name, title, ftype, size, type_name, **kw) -> Element:
    return Element("TStreamerBasicType", name, title, ftype, size, type_name,
                   **kw)


def _base(name, title, ftype, version, checksum) -> Element:
    return Element("TStreamerBase", name, title, ftype, 0, "BASE",
                   base_version=version, base_checksum=checksum)


#: THashList and TSeqCollection are class version 0, so their infos list no
#: members while their checksums fold them (StreamerInfo.md 11.2). A writer
#: must carry these two values rather than compute them.
KNOWN_CHECKSUMS = {
    "THashList": 0xCC7E49C1,
    "TSeqCollection": 0xFC6C3BC6,
}


def histogram_infos(kinds=("F",)) -> list:
    """Every `TStreamerInfo` a `TH1F`/`TH1D` file needs, in ROOT's own order."""
    by_name: dict = {}

    def add(info: Info) -> Info:
        if info.checksum is None:
            info.checksum = KNOWN_CHECKSUMS.get(info.name) or checksum(info)
        by_name[info.name] = info
        return info

    def cs(name: str) -> int:
        return by_name[name].checksum

    add(Info("TObject", 1, [
        _basic("fUniqueID", "object unique identifier", 13, 4, "unsigned int"),
        _basic("fBits", "bit field status word", 15, 4, "unsigned int"),
    ]))
    add(Info("TNamed", 1, [
        _base("TObject", "Basic ROOT object", 66, 1, cs("TObject")),
        Element("TStreamerString", "fName", "object identifier", 65, 24,
                "TString"),
        Element("TStreamerString", "fTitle", "object title", 65, 24, "TString"),
    ]))
    add(Info("TAttLine", 2, [
        _basic("fLineColor", "Line color", 2, 2, "short"),
        _basic("fLineStyle", "Line style", 2, 2, "short"),
        _basic("fLineWidth", "Line width", 2, 2, "short"),
    ]))
    add(Info("TAttFill", 2, [
        _basic("fFillColor", "Fill area color", 2, 2, "short"),
        _basic("fFillStyle", "Fill area style", 2, 2, "short"),
    ]))
    add(Info("TAttMarker", 3, [
        _basic("fMarkerColor", "Marker color", 2, 2, "short"),
        _basic("fMarkerStyle", "Marker style", 2, 2, "short"),
        _basic("fMarkerSize", "Marker size", 5, 4, "float"),
    ]))
    add(Info("TAttAxis", 4, [
        _basic("fNdivisions", "Number of divisions(10000*n3 + 100*n2 + n1)",
               3, 4, "int"),
        _basic("fAxisColor", "Color of the line axis", 2, 2, "short"),
        _basic("fLabelColor", "Color of labels", 2, 2, "short"),
        _basic("fLabelFont", "Font for labels", 2, 2, "short"),
        _basic("fLabelOffset", "Offset of labels", 5, 4, "float"),
        _basic("fLabelSize", "Size of labels", 5, 4, "float"),
        _basic("fTickLength", "Length of tick marks", 5, 4, "float"),
        _basic("fTitleOffset", "Offset of axis title", 5, 4, "float"),
        _basic("fTitleSize", "Size of axis title", 5, 4, "float"),
        _basic("fTitleColor", "Color of axis title", 2, 2, "short"),
        _basic("fTitleFont", "Font for axis title", 2, 2, "short"),
    ]))
    # TString's info carries no elements at all, so its checksum -- which the
    # class does have -- cannot come from them.
    add(Info("TString", 2, [], checksum=0x00017419))
    add(Info("TCollection", 3, [
        _base("TObject", "Basic ROOT object", 66, 1, cs("TObject")),
        Element("TStreamerString", "fName", "name of the collection", 65, 24,
                "TString"),
        _basic("fSize", "number of elements in collection", 3, 4, "int"),
    ]))
    add(Info("TSeqCollection", 0, [
        _base("TCollection", "Collection abstract base class", 0, 3,
              cs("TCollection")),
    ]))
    add(Info("TList", 5, [
        _base("TSeqCollection", "Sequenceable collection ABC", 0, 0,
              cs("TSeqCollection")),
    ]))
    add(Info("THashList", 0, [
        _base("TList", "Doubly linked list", 0, 5, cs("TList")),
    ]))
    add(Info("TAxis", 10, [
        _base("TNamed", "The basis for a named object (name, title)", 67, 1,
              cs("TNamed")),
        _base("TAttAxis", "Axis attributes", 0, 4, cs("TAttAxis")),
        _basic("fNbins", "Number of bins", 3, 4, "int"),
        _basic("fXmin", "Low edge of first bin", 8, 8, "double"),
        _basic("fXmax", "Upper edge of last bin", 8, 8, "double"),
        Element("TStreamerObjectAny", "fXbins", "Bin edges array in X", 62, 24,
                "TArrayD"),
        _basic("fFirst", "First bin to display", 3, 4, "int"),
        _basic("fLast", "Last bin to display", 3, 4, "int"),
        _basic("fBits2", "Second bit status word", 12, 2, "unsigned short"),
        _basic("fTimeDisplay",
               "On/off displaying time values instead of numerics", 18, 1,
               "bool"),
        Element("TStreamerString", "fTimeFormat",
                "Date&time format, ex: 09/12/99 12:34:00", 65, 24, "TString"),
        Element("TStreamerObjectPointer", "fLabels", "List of labels", 64, 8,
                "THashList*"),
        Element("TStreamerObjectPointer", "fModLabs", "List of modified labels",
                64, 8, "TList*"),
    ]))
    add(Info("TH1", 8, [
        _base("TNamed", "The basis for a named object (name, title)", 67, 1,
              cs("TNamed")),
        _base("TAttLine", "Line attributes", 0, 2, cs("TAttLine")),
        _base("TAttFill", "Fill area attributes", 0, 2, cs("TAttFill")),
        _base("TAttMarker", "Marker attributes", 0, 3, cs("TAttMarker")),
        _basic("fNcells", "Number of bins(1D), cells (2D) +U/Overflows", 3, 4,
               "int"),
        Element("TStreamerObject", "fXaxis", "X axis descriptor", 61, 216,
                "TAxis"),
        Element("TStreamerObject", "fYaxis", "Y axis descriptor", 61, 216,
                "TAxis"),
        Element("TStreamerObject", "fZaxis", "Z axis descriptor", 61, 216,
                "TAxis"),
        _basic("fBarOffset", "(1000*offset) for bar charts or legos", 2, 2,
               "short"),
        _basic("fBarWidth", "(1000*width) for bar charts or legos", 2, 2,
               "short"),
        _basic("fEntries", "Number of entries", 8, 8, "double"),
        _basic("fTsumw", "Total Sum of weights", 8, 8, "double"),
        _basic("fTsumw2", "Total Sum of squares of weights", 8, 8, "double"),
        _basic("fTsumwx", "Total Sum of weight*X", 8, 8, "double"),
        _basic("fTsumwx2", "Total Sum of weight*X*X", 8, 8, "double"),
        _basic("fMaximum", "Maximum value for plotting", 8, 8, "double"),
        _basic("fMinimum", "Minimum value for plotting", 8, 8, "double"),
        _basic("fNormFactor", "Normalization factor", 8, 8, "double"),
        Element("TStreamerObjectAny", "fContour",
                "Array to display contour levels", 62, 24, "TArrayD"),
        Element("TStreamerObjectAny", "fSumw2",
                "Array of sum of squares of weights", 62, 24, "TArrayD"),
        Element("TStreamerString", "fOption", "Histogram options", 65, 24,
                "TString"),
        Element("TStreamerObjectPointer", "fFunctions",
                "->Pointer to list of functions (fits and user)", 63, 8,
                "TList*"),
        _basic("fBufferSize", "fBuffer size", 6, 4, "int"),
        Element("TStreamerBasicPointer", "fBuffer", "[fBufferSize] entry buffer",
                48, 8, "double*", count_version=8, count_name="fBufferSize",
                count_class="TH1"),
        _basic("fBinStatErrOpt", "Option for bin statistical errors", 3, 4,
               "TH1::EBinErrorOpt", is_enum=True),
        _basic("fStatOverflows",
               "Per object flag to use under/overflows in statistics", 3, 4,
               "TH1::EStatOverflows", is_enum=True),
    ]))
    # TArray, TArrayF and TArrayD get no info of their own in a ROOT-written
    # file: their Streamer is hand-written, so nothing ever marks them
    # (WritingObjects.md 7.2) and a reader has to know their layout out of band
    # (TArray.md). Their checksums are needed all the same, as the base of
    # TH1F/TH1D -- so they are built here and then left out of the record, which
    # is exactly what ROOT does.
    add(Info("TArray", 1, [
        _basic("fN", "Number of array elements", 3, 4, "int"),
    ]))
    for kind, word in (("F", "float"), ("D", "double")):
        add(Info(f"TArray{kind}", 1, [
            _base("TArray", "Abstract array base class", 0, 1, cs("TArray")),
            Element("TStreamerBasicPointer", "fArray",
                    f"[fN] Array of fN {word}s", 40 + (5 if kind == "F" else 8),
                    8, f"{word}*", count_version=1, count_name="fN",
                    count_class=f"TArray{kind}"),
        ]))
    for kind in kinds:
        cls = f"TH1{kind}"
        array = f"TArray{kind}"
        add(Info(cls, 3, [
            _base("TH1", "1-Dim histogram base class", 0, 8, cs("TH1")),
            _base(array, f"Array of {'floats' if kind == 'F' else 'doubles'}",
                  0, 1, cs(array)),
        ]))

    order = ["TH1F", "TH1", "TNamed", "TObject", "TAttLine", "TAttFill",
             "TAttMarker", "TAxis", "TAttAxis", "THashList", "TList",
             "TSeqCollection", "TCollection", "TString", "TH1D"]
    return [by_name[n] for n in order if n in by_name]
