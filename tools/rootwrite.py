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
#: TDirectoryFile's ClassDef version (root/io/io/inc/TDirectoryFile.h:131).
DIR_VERSION = 5
#: What a directory key spells for its class, whatever the class really is.
#: ROOT substitutes it on the way out and undoes it on the way in
#: (spec/01-container/Directory.md 6.5).
DIR_CLASS_ON_DISK = "TDirectory"
#: spec/01-container/FileHeader.md 5.7 -- 4 in the small layout.
UNITS_SMALL = 4
#: spec/01-container/LargeFiles.md 1 -- every large-file test is on this value.
BIG = 2000000000
#: The default ROOT writes for a fresh key (spec/01-container/Record.md 4.6).
CYCLE = 1
#: A key whose version exceeds this stores 8-byte offsets. A TBasket always
#: does, whatever the file's size (spec/06-writing/WritingTrees.md 5).
LARGE_KEY_VERSION = 1000

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
    #: Bytes that follow the three strings and count inside fKeylen. Only a
    #: TBasket has any: its own header lives there (WritingTrees.md 5).
    extra: bytes = b""

    @property
    def large(self) -> bool:
        """A key with 8-byte offsets, selected by its version (Record.md 3)."""
        return self.version > LARGE_KEY_VERSION

    @property
    def key_len(self) -> int:
        fixed = KEY_FIXED + (8 if self.large else 0)
        return (fixed + string_len(self.class_name) + string_len(self.name)
                + string_len(self.title) + len(self.extra))

    def to_bytes(self) -> bytes:
        if not self.large and max(self.seek_key, self.seek_pdir) > BIG:
            raise WriteError(
                "an offset past 2000000000 needs the large key form; "
                "see spec/01-container/LargeFiles.md 3")
        seeks = (i64(self.seek_key) + i64(self.seek_pdir) if self.large
                 else i32(self.seek_key) + i32(self.seek_pdir))
        return (i32(self.nbytes) + i16(self.version) + i32(self.obj_len)
                + u32(self.datime) + i16(self.key_len) + i16(self.cycle)
                + seeks + counted_string(self.class_name)
                + counted_string(self.name) + counted_string(self.title)
                + self.extra)


@dataclass
class Obj:
    """One object to be written as a record of its own."""

    class_name: str
    name: str
    title: str
    payload: bytes
    #: A TBasket overrides both of these (WritingTrees.md 5).
    key_version: int = 4
    key_extra: bytes = b""
    cycle: int = CYCLE
    #: Set when the record must not be compressed whatever the file says.
    raw: bool = False
    #: A payload that cannot be built until earlier records are placed -- the
    #: TTree record, which needs its baskets' offsets. Called as
    #: builder(key_len, placed) once the position is known.
    builder: object = None
    #: A basket is a key that is deliberately absent from the directory's key
    #: list, because TKey(TDirectory*) never appends it (WritingTrees.md 6).
    in_key_list: bool = True


@dataclass
class _Placed:
    key: Key
    payload: bytes
    listed: bool = True

    def to_bytes(self) -> bytes:
        return self.key.to_bytes() + self.payload


class Directory:
    """One directory in the file: the root directory, or a subdirectory.

    A subdirectory differs from the root one in four places and nowhere else
    (`spec/06-writing/WritingFiles.md` 5): its record payload carries no name
    and title, so `fNbytesName` is the key length alone; its key's `fSeekPdir`
    and its record's `fSeekParent` name the mother; its key's class name on disk
    is `TDirectory`; and its key-list record is keyed by its own name rather than
    the file's.

    Nothing here is created lazily: `FileWriter.to_bytes` fills in `seek_dir`,
    `seek_keys` and `nbytes_keys` as it walks the layout, which is why a
    directory's record can be placed before its key list exists.
    """

    def __init__(self, writer: "FileWriter", name: str, title: str,
                 parent: "Directory | None", uuid: bytes, saved: bool = True):
        if len(uuid) != 16:
            raise WriteError("a TUUID is 16 bytes")
        self.writer = writer
        self.name = name
        self.title = title
        self.parent = parent
        self.uuid = uuid
        #: False reproduces a directory ROOT created and never saved: its record
        #: is written with fSeekKeys 0 and it gets no key-list record at all
        #: (`spec/01-container/Directory.md` 6.4).
        self.saved = saved
        self.seek_dir = 0
        self.seek_keys = 0
        self.nbytes_keys = 0
        #: The records this directory's key list names, in write order.
        self.listed: list[_Placed] = []
        #: Set once the record is placed, so its payload can be filled in after
        #: the key lists are laid out.
        self.record: _Placed | None = None

    @property
    def is_root(self) -> bool:
        return self.parent is None

    # -- building ---------------------------------------------------------

    def mkdir(self, name: str, title: str | None = None, *,
              uuid: bytes = DEFAULT_UUID, saved: bool = True) -> "Directory":
        """A subdirectory of this one, in creation order.

        ROOT defaults the title to the name (`TDirectoryFile::mkdir`,
        `root/io/io/src/TDirectoryFile.cxx:1275`) and gives every directory a
        fresh random UUID (`root/core/base/inc/TDirectory.h:143`); this writer
        takes the UUID as an input so the file stays reproducible.
        """
        sub = Directory(self.writer, name, name if title is None else title,
                        self, uuid, saved)
        self.writer._sequence.append((self, sub))
        self.writer.subdirs.append(sub)
        return sub

    def add(self, obj: Obj) -> None:
        self.writer._sequence.append((self, obj))

    def add_hist(self, hist) -> None:
        """Add a histogram, whose payload needs its own key's length."""
        key_len = Key(class_name=hist.class_name, name=hist.name,
                      title=hist.title, obj_len=0, nbytes=0, seek_key=0,
                      seek_pdir=BEGIN).key_len
        self.add(hist.obj(key_len))

    # -- the two keys a directory owns ------------------------------------

    def record_key(self, seek_key: int, obj_len: int) -> Key:
        """The key at the head of this directory's own record.

        The root directory's carries the file's class and a `fSeekPdir` of 0,
        which is an artefact of ROOT's construction order
        (`spec/06-writing/WritingFiles.md` 4.1).
        """
        if self.is_root:
            return self.writer._self_key(seek_key, obj_len, seek_pdir=0)
        return self._dir_key(seek_key, obj_len, self.parent.seek_dir)

    def keys_key(self, seek_key: int, obj_len: int) -> Key:
        """The key at the head of this directory's key-list record.

        Its `fSeekPdir` is this directory's own `fSeekDir`, not its parent's:
        `TDirectoryFile::WriteKeys` passes `this` as the mother
        (`root/io/io/src/TDirectoryFile.cxx:2213`).
        """
        if self.is_root:
            return self.writer._self_key(seek_key, obj_len, seek_pdir=BEGIN)
        return self._dir_key(seek_key, obj_len, self.seek_dir)

    def _dir_key(self, seek_key: int, obj_len: int, seek_pdir: int) -> Key:
        key = Key(class_name=DIR_CLASS_ON_DISK, name=self.name,
                  title=self.title, obj_len=obj_len, nbytes=0,
                  seek_key=seek_key, seek_pdir=seek_pdir,
                  datime=self.writer.datime)
        key.nbytes = key.key_len + obj_len
        return key

    # -- the record ------------------------------------------------------

    @property
    def obj_len(self) -> int:
        """The record's `fObjlen`: 60 bytes of fields, plus the root's prefix."""
        if self.is_root:
            return (string_len(self.name) + string_len(self.title)
                    + DIR_RECORD_LEN)
        return DIR_RECORD_LEN

    @property
    def nbytes_name(self) -> int:
        """`fNbytesName`: the key alone, plus the repeated strings for the root.

        This is the number a reader adds to `fSeekDir` to find the fields, so
        for a subdirectory the fields start where the key ends
        (`spec/01-container/Directory.md` 1).
        """
        key_len = self.record_key(BEGIN, 0).key_len
        if self.is_root:
            key_len += string_len(self.name) + string_len(self.title)
        return key_len

    def payload(self) -> bytes:
        """The directory record's payload (`Directory.md` 2, version 5).

        `fDatimeC` and `fDatimeM` are one value here. ROOT sets both at
        construction and refreshes `fDatimeM` on every header rewrite
        (`root/io/io/src/TDirectoryFile.cxx:315-316`, `:2175`), which in a
        single-pass write lands in the same second.
        """
        body = (u16(DIR_VERSION) + u32(self.writer.datime)
                + u32(self.writer.datime)
                + i32(self.nbytes_keys) + i32(self.nbytes_name)
                + i32(self.seek_dir)
                + i32(0 if self.is_root else self.parent.seek_dir)
                + i32(self.seek_keys)
                + u16(1) + self.uuid)
        body += b"\x00" * (DIR_RECORD_LEN - len(body))
        if self.is_root:
            return (counted_string(self.name) + counted_string(self.title)
                    + body)
        return body


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
        self.infos: list[Info] = []
        #: Every record to place, paired with the directory that owns it, in the
        #: order ROOT would create them: an object, or a subdirectory whose own
        #: record goes here (`spec/06-writing/WritingFiles.md` 5.1).
        self._sequence: list[tuple[Directory, object]] = []
        #: Every subdirectory, in creation order, which is the order their key
        #: lists are written in.
        self.subdirs: list[Directory] = []
        self.root = Directory(self, file_name, title, None, uuid)

    def add(self, obj: Obj) -> None:
        """Add an object to the root directory."""
        self.root.add(obj)

    def add_hist(self, hist) -> None:
        """Add a histogram to the root directory, sizing its key first.

        Map positions are measured from the start of the record
        (`WritingObjects.md` 4), so a payload cannot be built until the key is
        sized -- and a histogram's key length depends on its name and title.
        """
        self.root.add_hist(hist)

    def mkdir(self, name: str, title: str | None = None, *,
              uuid: bytes = DEFAULT_UUID, saved: bool = True) -> Directory:
        """A subdirectory of the root directory."""
        return self.root.mkdir(name, title, uuid=uuid, saved=saved)

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
        """`fNbytesName`: the key plus the name and title repeated after it.

        The header carries the **root** directory's value; a subdirectory's is a
        different number and lives only in its own record
        (`spec/01-container/Directory.md` 1).
        """
        return self.root.nbytes_name

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

    def _record_of(self, obj: Obj, pos: int, seek_pdir: int) -> _Placed:
        """One record from an Obj, honouring its key version and tail.

        `seek_pdir` is the owning directory's `fSeekDir`, which is what says
        which directory the record belongs to -- the key list is a copy, not the
        authority (`spec/01-container/Directory.md` 9.7).
        """
        stored = obj.payload if obj.raw else self._stored(obj.payload)
        key = Key(class_name=obj.class_name, name=obj.name, title=obj.title,
                  obj_len=len(obj.payload), nbytes=0, seek_key=pos,
                  seek_pdir=seek_pdir, datime=self.datime, cycle=obj.cycle,
                  version=obj.key_version, extra=obj.key_extra)
        key.nbytes = key.key_len + len(stored)
        return _Placed(key=key, payload=stored, listed=obj.in_key_list)

    def to_bytes(self) -> bytes:
        root = self.root
        root.seek_dir = BEGIN
        dir_key = root.record_key(BEGIN, root.obj_len)

        pos = BEGIN + dir_key.nbytes
        placed: list[_Placed] = []
        for home, item in self._sequence:
            if isinstance(item, Directory):
                # A subdirectory's record is placed where ROOT places it: at
                # creation, before anything it holds, with fSeekKeys still 0
                # (WritingFiles.md 5.1). Its payload is filled in at the end,
                # once the key lists have addresses -- it is 60 bytes either way,
                # which is what lets ROOT rewrite it in place.
                item.seek_dir = pos
                key = item.record_key(pos, DIR_RECORD_LEN)
                rec = _Placed(key=key, payload=b"")
                item.record = rec
                placed.append(rec)
                home.listed.append(rec)
                pos += key.nbytes
                continue
            obj = item
            if obj.builder is not None:
                # A record whose payload depends on where earlier records
                # landed. The TTree record is the only one: a branch stores its
                # baskets' offsets (WritingTrees.md 4).
                probe = Key(class_name=obj.class_name, name=obj.name,
                            title=obj.title, obj_len=0, nbytes=0, seek_key=pos,
                            seek_pdir=home.seek_dir, version=obj.key_version,
                            extra=obj.key_extra)
                obj.payload = obj.builder(probe.key_len, placed)
            rec = self._record_of(obj, pos, home.seek_dir)
            placed.append(rec)
            if rec.listed:
                home.listed.append(rec)
            pos += rec.key.nbytes

        # The StreamerInfo record: a TList named "StreamerInfo", written before
        # the key lists because that is TFile::Close's order, and deliberately
        # *not* in any key list (WritingFiles.md 6).
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

        # One key list per saved directory: a count, then each record's key image
        # verbatim (Directory.md 6). The root directory's comes first, because
        # TDirectoryFile::Save writes itself before recursing
        # (root/io/io/src/TDirectoryFile.cxx:1575-1587).
        key_lists: list[tuple[Key, bytes]] = []
        for d in [root] + self.subdirs:
            if not d.saved:
                continue
            images = b"".join(p.key.to_bytes() for p in d.listed)
            payload = i32(len(d.listed)) + images
            key = d.keys_key(pos, len(payload))
            d.seek_keys, d.nbytes_keys = pos, key.nbytes
            key_lists.append((key, payload))
            pos += key.nbytes
        if any(d.listed and not d.saved for d in self.subdirs):
            raise WriteError("an unsaved directory cannot hold anything: its "
                             "keys would be unreachable "
                             "(spec/01-container/Directory.md 6.4)")

        # The free list: one entry, covering everything past the end of the
        # file (FreeSegments.md 2). Its own record has to be placed before the
        # entry can name the end, so the length is computed first. A directory
        # record is never freed and never moves, so one entry is right however
        # many directories the file has (WritingFiles.md 5.3).
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

        # Every directory record's payload is known only now, because it names
        # its own key list.
        for d in self.subdirs:
            d.record.payload = d.payload()

        out += dir_key.to_bytes() + root.payload()
        for p in placed:
            out += p.to_bytes()
        if info_record is not None:
            out += info_record.to_bytes()
        for key, payload in key_lists:
            out += key.to_bytes() + payload
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

    def framed(self, version: int, build=None) -> None:
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
                  bits: int = 0, key=None, embedded: bool = False,
                  count: int | None = None) -> None:
        """A `TObjArray` at version 3 (`StreamerInfo.md` 5): no options.

        `embedded` picks the framing, and getting it wrong is an 18-byte error:

        * a **pointer** member -- `TStreamerInfo::fElements`, `fType` 63/64 --
          is a slot, so the record is preceded by a class record naming the
          class;
        * a **member object** -- `TTree::fBranches`, `fType` 61 -- is the bare
          framed object, with no class record at all.

        `count` overrides the entry count, which is the index of the last
        occupied slot plus one and so may exceed the number of entries written:
        `TBranch::fBaskets` is `fWriteBasket + 1` slots of null.
        """
        def body(p: Payload) -> None:
            p.tobject(bits)
            p.raw(counted_string(name)
                  + i32(count if count is not None else len(entries))
                  + i32(lower_bound))
            for entry in entries:
                entry(p)
        if embedded:
            self.framed(3, build=body)
        else:
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


def _counter_start(title: str) -> int | None:
    """Where the counter's `[` starts in a comment, or None.

    Only `/` and whitespace may precede it, so an ordinary comment that happens
    to contain brackets -- `// x position [0, 1]` -- contributes nothing to the
    checksum. ROOT's rule, `TVirtualStreamerInfo::GetElementCounterStart`,
    `root/core/meta/src/TVirtualStreamerInfo.cxx:98-110`; the looser plain search
    belongs to checksum variants 6 and below (`StreamerInfo.md` 11).
    """
    for i, c in enumerate(title):
        if c == "[":
            return i
        if c != "/" and not c.isspace():
            return None
    return None


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
        left = _counter_start(e.title)
        if left is not None and "]" in e.title[left + 1:]:
            inner = e.title[left + 1:]
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
    #: None takes gStyle's per-axis default, which is 0 for the Y axis and 1
    #: for X and Z -- the reason the three attribute blocks of a ROOT-written
    #: histogram are not identical (`WritingHistograms.md` 4.1).
    title_offset: float | None = None
    title_size: float = 0.035
    title_color: int = 1
    title_font: int = 42

    def __post_init__(self):
        if self.title_offset is None:
            self.title_offset = 0.0 if self.name == "yaxis" else 1.0

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
    """A histogram's statistics, which are not derivable from the bin contents.

    `entries` counts every fill, in range or not; the sums cover only the fills
    inside the range. `GetMean` is `tsumwx / tsumw`, so a writer that leaves
    them zero produces a histogram whose bins are right and whose mean is not.

    The first five are `TH1`'s and every histogram writes them. The last three
    are written by the classes that have a second dimension: a `TH2` adds all
    three, in `fScalefactor`'s company, and a `TProfile` adds `tsumwy` and
    `tsumwy2` only -- it has no `fTsumwxy` (`WritingHistograms.md` 7 and 8).
    """

    entries: float = 0.0
    tsumw: float = 0.0
    tsumw2: float = 0.0
    tsumwx: float = 0.0
    tsumwx2: float = 0.0
    tsumwy: float = 0.0
    tsumwy2: float = 0.0
    tsumwxy: float = 0.0


def tarray(values, kind: str) -> bytes:
    """The `TArray` base of a `TH1F`/`TH2F` (`F`) or a `TH1D`/`TH2D` (`D`)."""
    return tarray_f(values) if kind == "F" else tarray_d(values)


def check_kind(kind: str, base: str) -> None:
    if kind not in ("F", "D"):
        raise WriteError(f"only {base}F and {base}D are implemented")


def check_cells(cells, want: int, why: str) -> None:
    if len(cells) != want:
        raise WriteError(f"{len(cells)} cells, expected {want}: {why} "
                         "(WritingHistograms.md 3)")


def check_parallel(values, cells, name: str, optional: bool = False) -> None:
    if values is None or (optional and not values):
        return
    if len(values) != len(cells):
        raise WriteError(f"{name} must be empty or one entry per cell, "
                         f"{len(cells)} of them, not {len(values)}")


def check_axis(axis: Axis) -> None:
    if axis.edges and len(axis.edges) != axis.nbins + 1:
        raise WriteError("fXbins holds nbins + 1 edges")


def _centres(axis: Axis) -> list:
    """The centre of each of `axis.nbins` bins, indexed from 1."""
    edges = axis.edges or [
        axis.xmin + (axis.xmax - axis.xmin) * i / axis.nbins
        for i in range(axis.nbins + 1)
    ]
    return [0.0] + [0.5 * (edges[i - 1] + edges[i])
                    for i in range(1, axis.nbins + 1)]


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
    centre = _centres(axis)
    st = Stats(entries=float(sum(cells)))
    for i in range(1, len(cells) - 1):
        w = cells[i]
        x = centre[i]
        st.tsumw += w
        st.tsumw2 += sumw2[i] if sumw2 is not None else w
        st.tsumwx += w * x
        st.tsumwx2 += w * x * x
    return st


def cell_index(binx: int, biny: int, nx: int) -> int:
    """The cell a 2-D bin occupies: `biny * (nx + 2) + binx`.

    `binx` and `biny` run from 0 (underflow) to `nx + 1` / `ny + 1` (overflow),
    so the first `nx + 2` cells are the whole underflow row in y
    (`WritingHistograms.md` 7.1).
    """
    if not 0 <= binx <= nx + 1:
        raise WriteError(f"binx {binx} is outside 0..{nx + 1}")
    return biny * (nx + 2) + binx


def stats_from_cells_2d(cells, xaxis: Axis, yaxis: Axis, sumw2=None) -> Stats:
    """The same for a `TH2`, over the in-range cells of both axes.

    A fill that is outside the range in **either** axis increments its cell and
    none of the seven sums, so the in-range region is the rectangle
    `1 <= binx <= nx`, `1 <= biny <= ny` -- not "every cell but the first and
    last" (`WritingHistograms.md` 7.1).
    """
    nx, ny = xaxis.nbins, yaxis.nbins
    xc, yc = _centres(xaxis), _centres(yaxis)
    st = Stats(entries=float(sum(cells)))
    for biny in range(1, ny + 1):
        for binx in range(1, nx + 1):
            i = biny * (nx + 2) + binx
            w, x, y = cells[i], xc[binx], yc[biny]
            st.tsumw += w
            st.tsumw2 += sumw2[i] if sumw2 is not None else w
            st.tsumwx += w * x
            st.tsumwx2 += w * x * x
            st.tsumwy += w * y
            st.tsumwy2 += w * y * y
            st.tsumwxy += w * x * y
    return st


def stats_from_profile(cells, sumw2, bin_entries, axis: Axis,
                       bin_sumw2=None) -> Stats:
    """A `TProfile`'s statistics, of which only the x moments are approximate.

    A profile already stores per cell what a `TH1` throws away: `cells` is
    sum(w*y) and `sumw2` is sum(w*y*y), so `fTsumwy` and `fTsumwy2` are their
    in-range sums **exactly**, and `fTsumw`/`fTsumw2` come the same way from
    `bin_entries` and `bin_sumw2`. Only `fTsumwx` and `fTsumwx2` need bin
    centres, and only `fEntries` is unrecoverable -- it counts fills, and a
    weighted fill moves `bin_entries` by its weight instead (§8.3).
    """
    centre = _centres(axis)
    st = Stats(entries=float(sum(bin_entries)))
    for i in range(1, len(cells) - 1):
        e, x = bin_entries[i], centre[i]
        st.tsumw += e
        st.tsumw2 += bin_sumw2[i] if bin_sumw2 else e
        st.tsumwx += e * x
        st.tsumwx2 += e * x * x
        st.tsumwy += cells[i]
        st.tsumwy2 += sumw2[i]
    return st


@dataclass
class _Histogram:
    """The `TH1` base at version 8, which every histogram class shares.

    `TH1F`, `TH2F` and `TProfile` differ only in what they wrap around this
    block and what they append after it. The block itself is one procedure
    (`WritingHistograms.md` 3), so it is written once here; `cells` is always
    `fNcells` values long and always the `TArray` base's content, whatever the
    concrete class decides that content means.
    """

    name: str
    title: str
    axis: Axis                       # fXaxis
    cells: list
    stats: Stats
    maximum: float = NO_LIMIT
    minimum: float = NO_LIMIT
    norm_factor: float = 0.0
    bar_offset: int = 0
    bar_width: int = 1000
    option: str = ""
    bin_stat_err_opt: int = 0        # kNormal
    stat_overflows: int = 2          # kNeutral
    contour: list | None = None

    #: The Y and Z axes as the concrete class needs them. A 1-D histogram and a
    #: profile carry a one-bin placeholder for each; a TH2 has a real Y axis.
    def axes(self) -> tuple:
        return (self.axis, Axis(name="yaxis"), Axis(name="zaxis"))

    #: What the TH1 base's fSumw2 holds. For a TH1 it is the sum of squared
    #: weights per cell and may be absent; for a TProfile it is sum(w*y*y) and
    #: never is (`WritingHistograms.md` 8.2).
    def th1_sumw2(self) -> list:
        return []

    def th1(self, q: Payload) -> None:
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
        # All three axes are always present. The Y axis's fTitleOffset is 0
        # rather than 1 in ROOT's default style, which is why the three
        # attribute blocks are not identical in a ROOT-written file; Axis
        # applies that per name. Free, like the rest of TAttAxis.
        for ax in self.axes():
            ax.write(q)
        q.raw(i16(self.bar_offset) + i16(self.bar_width))
        q.raw(f64(self.stats.entries) + f64(self.stats.tsumw)
              + f64(self.stats.tsumw2) + f64(self.stats.tsumwx)
              + f64(self.stats.tsumwx2))
        q.raw(f64(self.maximum) + f64(self.minimum) + f64(self.norm_factor))
        q.raw(tarray_d(self.contour or []))    # fContour
        q.raw(tarray_d(self.th1_sumw2()))      # fSumw2
        q.raw(counted_string(self.option))

        # fFunctions is declared `//->`, so it is streamed in place: a framed
        # TList with no class record and no pointer form.
        def functions(r: Payload) -> None:
            r.tobject(bits=FUNCTIONS_BITS)
            r.raw(counted_string("") + i32(0))
        q.framed(5, functions)

        q.raw(i32(0))                          # fBufferSize
        q.raw(b"\x00")                         # fBuffer: absent
        q.raw(i32(self.bin_stat_err_opt) + i32(self.stat_overflows))

    def obj(self, key_len: int) -> Obj:
        return Obj(class_name=self.class_name, name=self.name,
                   title=self.title, payload=self.payload(key_len))


@dataclass
class Hist1D(_Histogram):
    """A `TH1F` or `TH1D`: the `TH1` base at version 8, then the `TArray` base.

    `cells` holds `nbins + 2` values -- underflow, the bins, overflow -- and its
    length is `TH1::fNcells`. `sumw2` is either None or the same length.
    """

    sumw2: list | None = None
    kind: str = "F"                  # "F" for TH1F, "D" for TH1D

    @property
    def class_name(self) -> str:
        return f"TH1{self.kind}"

    def __post_init__(self):
        check_kind(self.kind, "TH1")
        check_cells(self.cells, self.axis.nbins + 2,
                    f"fNcells is nbins + 2 for a {self.class_name}")
        check_parallel(self.sumw2, self.cells, "fSumw2", optional=True)
        check_axis(self.axis)

    def th1_sumw2(self) -> list:
        return self.sumw2 or []

    def payload(self, key_len: int) -> bytes:
        p = Payload(key_len)

        def body(q: Payload) -> None:
            q.framed(8, self.th1)
            q.raw(tarray(self.cells, self.kind))
        p.framed(3, body)
        return bytes(p.buf)


@dataclass
class Hist2D(_Histogram):
    """A `TH2F` or `TH2D`, which is a `TH2` (version 5) around a `TH1`.

    `cells` is `(nx + 2) * (ny + 2)` values in **x-major** order: cell
    `biny * (nx + 2) + binx`, so the first `nx + 2` of them are the whole
    underflow row of y (`WritingHistograms.md` 7.1).

    `yaxis` is a real `TAxis` rather than the one-bin placeholder a `TH1F`
    carries, and it is the only axis a writer has to fill in twice: `fNbins`
    there and the `y` half of every cell index have to agree.
    """

    yaxis: Axis | None = None
    sumw2: list | None = None
    kind: str = "F"
    scalefactor: float = 1.0

    @property
    def class_name(self) -> str:
        return f"TH2{self.kind}"

    def __post_init__(self):
        check_kind(self.kind, "TH2")
        if self.yaxis is None:
            raise WriteError("a TH2 needs a yaxis")
        check_cells(self.cells,
                    (self.axis.nbins + 2) * (self.yaxis.nbins + 2),
                    "fNcells is (nx + 2) * (ny + 2) for a "
                    f"{self.class_name}")
        check_parallel(self.sumw2, self.cells, "fSumw2", optional=True)
        check_axis(self.axis)
        check_axis(self.yaxis)

    def axes(self) -> tuple:
        return (self.axis, self.yaxis, Axis(name="zaxis"))

    def th1_sumw2(self) -> list:
        return self.sumw2 or []

    def payload(self, key_len: int) -> bytes:
        p = Payload(key_len)

        def th2(q: Payload) -> None:
            q.framed(8, self.th1)
            q.raw(f64(self.scalefactor) + f64(self.stats.tsumwy)
                  + f64(self.stats.tsumwy2) + f64(self.stats.tsumwxy))

        def body(q: Payload) -> None:
            q.framed(5, th2)
            q.raw(tarray(self.cells, self.kind))
        p.framed(4, body)
        return bytes(p.buf)


@dataclass
class Profile(_Histogram):
    """A `TProfile` (version 7), which is a `TH1D` plus four parallel arrays.

    Its three per-cell arrays are not bin contents and not errors:

    * `cells` is the `TH1D`'s `TArrayD` base and holds **sum(w * y)**;
    * `sumw2` is `TH1::fSumw2` and holds **sum(w * y * y)**, and unlike a
      `TH1`'s it is never absent -- the constructor allocates it;
    * `bin_entries` is `TProfile::fBinEntries` and holds **sum(w)**;
    * `bin_sumw2` is `TProfile::fBinSumw2` and holds **sum(w * w)**. It is
      empty until a weight other than 1 arrives.

    What a reader calls the bin content is `cells[i] / bin_entries[i]`, computed
    on demand and stored nowhere (`WritingHistograms.md` 8.2).

    `ymin` and `ymax` are the accepted range in y; equal values -- 0 and 0 from
    the ordinary constructor -- mean "no range", and that is the only thing
    that distinguishes "unset" from a range of zero width.
    """

    sumw2: list | None = None
    bin_entries: list | None = None
    bin_sumw2: list | None = None
    error_mode: int = 0              # kERRORMEAN
    ymin: float = 0.0
    ymax: float = 0.0

    class_name = "TProfile"

    def __post_init__(self):
        check_cells(self.cells, self.axis.nbins + 2,
                    "fNcells is nbins + 2 for a TProfile")
        if self.sumw2 is None or self.bin_entries is None:
            raise WriteError(
                "a TProfile's fSumw2 and fBinEntries are never absent "
                "(WritingHistograms.md 8.2)")
        check_parallel(self.sumw2, self.cells, "fSumw2")
        check_parallel(self.bin_entries, self.cells, "fBinEntries")
        check_parallel(self.bin_sumw2, self.cells, "fBinSumw2", optional=True)
        check_axis(self.axis)

    def th1_sumw2(self) -> list:
        return self.sumw2

    def payload(self, key_len: int) -> bytes:
        p = Payload(key_len)

        def th1d(q: Payload) -> None:
            q.framed(8, self.th1)
            q.raw(tarray_d(self.cells))

        def body(q: Payload) -> None:
            q.framed(3, th1d)
            q.raw(tarray_d(self.bin_entries))
            q.raw(i32(self.error_mode))
            q.raw(f64(self.ymin) + f64(self.ymax))
            q.raw(f64(self.stats.tsumwy) + f64(self.stats.tsumwy2))
            q.raw(tarray_d(self.bin_sumw2 or []))
        p.framed(7, body)
        return bytes(p.buf)


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




class InfoSet:
    """A set of `TStreamerInfo`s under construction, in dependency order.

    Each `TStreamerBase` element needs the base class's checksum
    (`StreamerInfo.md` 9), so the classes are built bases-first and every base
    entry takes its value from the info built earlier. An error in one checksum
    then shows up twice, which is what makes the arrangement worth its
    awkwardness.
    """

    def __init__(self):
        self.by_name: dict = {}

    def add(self, info: Info) -> Info:
        if info.checksum is None:
            info.checksum = KNOWN_CHECKSUMS.get(info.name) or checksum(info)
        self.by_name[info.name] = info
        return info

    def cs(self, name: str) -> int:
        return self.by_name[name].checksum

    def ordered(self, order) -> list:
        """The infos ROOT would write, in ROOT's own order.

        The order is class registration order, which is neither alphabetical nor
        dependency order. A reader does not care; matching it is what lets a
        record be compared with a ROOT-written one byte for byte.
        """
        return [self.by_name[n] for n in order if n in self.by_name]

    # -- the classes every file needs -----------------------------------

    def common(self) -> None:
        add, cs = self.add, self.cs
        add(Info("TObject", 1, [
            _basic("fUniqueID", "object unique identifier", 13, 4,
                   "unsigned int"),
            _basic("fBits", "bit field status word", 15, 4, "unsigned int"),
        ]))
        add(Info("TNamed", 1, [
            _base("TObject", "Basic ROOT object", 66, 1, cs("TObject")),
            Element("TStreamerString", "fName", "object identifier", 65, 24,
                    "TString"),
            Element("TStreamerString", "fTitle", "object title", 65, 24,
                    "TString"),
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
        # TString's info carries no elements at all, so its checksum -- which
        # the class does have -- cannot come from them.
        add(Info("TString", 2, [], checksum=0x00017419))
        add(Info("TCollection", 3, [
            _base("TObject", "Basic ROOT object", 66, 1, cs("TObject")),
            Element("TStreamerString", "fName", "name of the collection", 65,
                    24, "TString"),
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
        add(Info("TObjArray", 3, [
            _base("TSeqCollection", "Sequenceable collection ABC", 0, 0,
                  cs("TSeqCollection")),
            _basic("fLowerBound", "Lower bound of the array", 3, 4, "int"),
            _basic("fLast", "Last element in array containing an object", 3, 4,
                   "int"),
        ]))
        add(Info("THashList", 0, [
            _base("TList", "Doubly linked list", 0, 5, cs("TList")),
        ]))

    # -- TArray, which never gets an info of its own ---------------------

    def arrays(self) -> None:
        """`TArray`, `TArrayF` and `TArrayD`, for their checksums only.

        No ROOT-written file contains an info for any of them: their streamers
        are hand-written, so nothing marks them
        (`WritingObjects.md` 7.2). The checksums are needed all the same, as the
        base of `TH1F` and `TH1D`.
        """
        add, cs = self.add, self.cs
        # fN is kCounter (6) rather than kInt (3) because TArrayF::fArray
        # names it: the promotion is done by whatever points at the member, not
        # by its own declaration (`ElementLists.md` erratum 1).
        add(Info("TArray", 1, [
            _basic("fN", "Number of array elements", 6, 4, "int"),
        ]))
        for kind, word, width in (("F", "float", 4), ("D", "double", 8)):
            add(Info(f"TArray{kind}", 1, [
                _base("TArray", "Abstract array base class", 0, 1,
                      cs("TArray")),
                # fSize is the *element* type's size, not a pointer's, and
                # fCountClass is the class that declares fN -- TArray, not the
                # concrete one (`ElementLists.md` sections 1 and 3).
                Element("TStreamerBasicPointer", "fArray",
                        f"[fN] Array of fN {word}s",
                        40 + (5 if kind == "F" else 8), width, f"{word}*",
                        count_version=1, count_name="fN",
                        count_class="TArray"),
            ]))


#: The title a TStreamerBase element carries for each concrete TArray.
ARRAY_TITLES = {"F": "Array of floats", "D": "Array of doubles"}

#: The order ROOT records the histogram classes in, which is registration
#: order -- neither alphabetical nor dependency order. It is a property of the
#: *file*: the first object's class comes first, then its bases as they were
#: built, then whatever each later object adds. Filtering this one list
#: reproduces both reference files, `data/classes/histogram.root` (a TH1F then
#: a TH1D) and `data/classes/th2-profile.root` (a TH2F, a TH2D, then two
#: TProfiles), because neither contains a class the other's first object needs.
#: A reader does not care; matching it is what lets a StreamerInfo record be
#: compared with a ROOT-written one byte for byte.
HISTOGRAM_INFO_ORDER = (
    "TH1F", "TH2F", "TH2", "TH1", "TNamed", "TObject", "TAttLine", "TAttFill",
    "TAttMarker", "TAxis", "TAttAxis", "THashList", "TList", "TSeqCollection",
    "TCollection", "TString", "TH2D", "TProfile", "TH1D",
)


def objstring_info() -> Info:
    """`TObjString`'s streamer info, as ROOT records it.

    Published as `spec/06-writing/ElementLists.md` §4, and the subject of the
    byte-identical comparison in `WritingObjects.md` 7.4.
    """
    info = Info("TObjString", 1, [
        Element("TStreamerBase", "TObject", "Basic ROOT object", 66, 0, "BASE",
                base_version=1, base_checksum=0x901BC02D),
        Element("TStreamerString", "fString", "wrapped TString", 65, 24,
                "TString"),
    ])
    info.checksum = checksum(info)
    return info


def histogram_infos(classes=("TH1F",)) -> list:
    """Every `TStreamerInfo` a histogram file needs, in ROOT's own order.

    `classes` names the concrete histogram classes the file holds, from
    `TH1F`, `TH1D`, `TH2F`, `TH2D` and `TProfile`. The bases each one needs are
    added for it -- a `TProfile` pulls in `TH1D`, a `TH2F` pulls in `TH2` -- and
    the `TArray` infos are built for their checksums without being emitted.
    """
    wanted = set(classes)
    unknown = wanted - set(HISTOGRAM_INFO_ORDER)
    if unknown:
        raise WriteError(f"not a histogram class: {sorted(unknown)}")
    if "TProfile" in wanted:
        wanted.add("TH1D")        # its base, and it is written in the file
    s = InfoSet()
    add, cs = s.add, s.cs
    s.common()
    s.arrays()
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
        Element("TStreamerBasicPointer", "fBuffer",
                "[fBufferSize] entry buffer", 48, 8, "double*",
                count_version=8, count_name="fBufferSize", count_class="TH1"),
        _basic("fBinStatErrOpt", "Option for bin statistical errors", 3, 4,
               "TH1::EBinErrorOpt", is_enum=True),
        _basic("fStatOverflows",
               "Per object flag to use under/overflows in statistics", 3, 4,
               "TH1::EStatOverflows", is_enum=True),
    ]))
    for kind in ("F", "D"):
        if f"TH1{kind}" in wanted:
            add(Info(f"TH1{kind}", 3, [
                _base("TH1", "1-Dim histogram base class", 0, 8, cs("TH1")),
                _base(f"TArray{kind}", ARRAY_TITLES[kind], 0, 1,
                      cs(f"TArray{kind}")),
            ]))
    if any(c.startswith("TH2") for c in wanted):
        add(Info("TH2", 5, [
            _base("TH1", "1-Dim histogram base class", 0, 8, cs("TH1")),
            _basic("fScalefactor", "Scale factor", 8, 8, "double"),
            _basic("fTsumwy", "Total Sum of weight*Y", 8, 8, "double"),
            _basic("fTsumwy2", "Total Sum of weight*Y*Y", 8, 8, "double"),
            _basic("fTsumwxy", "Total Sum of weight*X*Y", 8, 8, "double"),
        ]))
    for kind in ("F", "D"):
        if f"TH2{kind}" in wanted:
            add(Info(f"TH2{kind}", 4, [
                _base("TH2", "2-Dim histogram base class", 0, 5, cs("TH2")),
                _base(f"TArray{kind}", ARRAY_TITLES[kind], 0, 1,
                      cs(f"TArray{kind}")),
            ]))
    if "TProfile" in wanted:
        add(Info("TProfile", 7, [
            _base("TH1D", "1-Dim histograms (one double per channel)", 0, 3,
                  cs("TH1D")),
            Element("TStreamerObjectAny", "fBinEntries",
                    "number of entries per bin", 62, 24, "TArrayD"),
            # An unscoped enum, so fTypeName is the bare EErrorType -- and an
            # enum folds an extra 1 into TProfile's checksum
            # (`StreamerInfo.md` 11.1).
            _basic("fErrorMode", "Option to compute errors", 3, 4,
                   "EErrorType", is_enum=True),
            _basic("fYmin", "Lower limit in Y (if set)", 8, 8, "double"),
            _basic("fYmax", "Upper limit in Y (if set)", 8, 8, "double"),
            _basic("fTsumwy", "Total Sum of weight*Y", 8, 8, "double"),
            _basic("fTsumwy2", "Total Sum of weight*Y*Y", 8, 8, "double"),
            Element("TStreamerObjectAny", "fBinSumw2",
                    "Array of sum of squares of weights per bin", 62, 24,
                    "TArrayD"),
        ]))
    return s.ordered(HISTOGRAM_INFO_ORDER)


def tree_infos(leaf_kinds=("I", "F")) -> list:
    """Every `TStreamerInfo` a flat `TTree` file needs, in ROOT's own order.

    `leaf_kinds` names the concrete leaf classes used: `I` for `TLeafI`, `F` for
    `TLeafF`, `D` for `TLeafD`, `C` for `TLeafC`.

    Eighteen infos for a two-branch tree, and three of them are there for
    reasons a writer would not guess: `TBranchRef` and `TRefTable` because
    `TTree::fBranchRef` is a **null** pointer and a null still forces its
    class's info to be written, and `ROOT::TIOFeatures` because it is a member
    -- a class with no `ClassDef` at all, whose version word on disk is
    therefore 0 followed by a checksum (`WritingObjects.md` 2).
    """
    s = InfoSet()
    add, cs = s.add, s.cs
    s.common()

    add(Info("ROOT::TIOFeatures", 1, [
        _basic("fIOBits", "", 11, 1, "unsigned char"),
    ]))
    add(Info("TLeaf", 2, [
        _base("TNamed", "The basis for a named object (name, title)", 67, 1,
              cs("TNamed")),
        _basic("fLen", "Number of fixed length elements in the leaf's data.",
               3, 4, "int"),
        _basic("fLenType", "Number of bytes for this data type", 3, 4, "int"),
        _basic("fOffset", "Offset in ClonesArray object (if one)", 3, 4, "int"),
        _basic("fIsRange",
               "(=true if leaf has a range, false otherwise).  This is "
               "equivalent to being a 'leafcount'.  For a TLeafElement the "
               "range information is actually store in the TBranchElement.",
               18, 1, "bool"),
        _basic("fIsUnsigned", "(=true if unsigned, false otherwise)", 18, 1,
               "bool"),
        Element("TStreamerObjectPointer", "fLeafCount",
                "Pointer to Leaf count if variable length (we do not own the "
                "counter)", 64, 8, "TLeaf*"),
    ]))
    for kind in leaf_kinds:
        ftype, size, type_name = LEAF_SCALARS[kind]
        add(Info(f"TLeaf{kind}", 1, [
            _base("TLeaf", "Leaf: description of a Branch data type", 0, 2,
                  cs("TLeaf")),
            _basic("fMinimum", "Minimum value if leaf range is specified",
                   ftype, size, type_name),
            _basic("fMaximum", "Maximum value if leaf range is specified",
                   ftype, size, type_name),
        ]))
    add(Info("TBranch", 13, [
        _base("TNamed", "The basis for a named object (name, title)", 67, 1,
              cs("TNamed")),
        _base("TAttFill", "Fill area attributes", 0, 2, cs("TAttFill")),
        _basic("fCompress", "Compression level and algorithm", 3, 4, "int"),
        _basic("fBasketSize", "Initial Size of  Basket Buffer", 3, 4, "int"),
        _basic("fEntryOffsetLen",
               "Initial Length of fEntryOffset table in the basket buffers",
               3, 4, "int"),
        _basic("fWriteBasket", "Last basket number written", 3, 4, "int"),
        _basic("fEntryNumber",
               "Current entry number (last one filled in this branch)", 16, 8,
               "Long64_t"),
        Element("TStreamerObjectAny", "fIOFeatures",
                "IO features for newly-created baskets.", 62, 1,
                "ROOT::TIOFeatures"),
        _basic("fOffset", "Offset of this branch", 3, 4, "int"),
        _basic("fMaxBaskets", "Maximum number of Baskets so far", 6, 4, "int"),
        _basic("fSplitLevel", "Branch split level", 3, 4, "int"),
        _basic("fEntries", "Number of entries", 16, 8, "Long64_t"),
        _basic("fFirstEntry", "Number of the first entry in this branch", 16, 8,
               "Long64_t"),
        _basic("fTotBytes",
               "Total number of bytes in all leaves before compression", 16, 8,
               "Long64_t"),
        _basic("fZipBytes",
               "Total number of bytes in all leaves after compression", 16, 8,
               "Long64_t"),
        Element("TStreamerObject", "fBranches",
                "-> List of Branches of this branch", 61, 64, "TObjArray"),
        Element("TStreamerObject", "fLeaves", "-> List of leaves of this branch",
                61, 64, "TObjArray"),
        Element("TStreamerObject", "fBaskets",
                "-> List of baskets of this branch", 61, 64, "TObjArray"),
        Element("TStreamerBasicPointer", "fBasketBytes",
                "[fMaxBaskets] Length of baskets on file", 43, 4, "int*",
                count_version=13, count_name="fMaxBaskets",
                count_class="TBranch"),
        Element("TStreamerBasicPointer", "fBasketEntry",
                "[fMaxBaskets] Table of first entry in each basket", 56, 8,
                "Long64_t*", count_version=13, count_name="fMaxBaskets",
                count_class="TBranch"),
        Element("TStreamerBasicPointer", "fBasketSeek",
                "[fMaxBaskets] Addresses of baskets on file", 56, 8,
                "Long64_t*", count_version=13, count_name="fMaxBaskets",
                count_class="TBranch"),
        Element("TStreamerString", "fFileName",
                'Name of file where buffers are stored ("" if in same file as '
                'Tree header)', 65, 24, "TString"),
    ]))
    add(Info("TRefTable", 3, [
        _base("TObject", "Basic ROOT object", 66, 1, cs("TObject")),
        _basic("fSize", "dummy for backward compatibility", 3, 4, "int"),
        Element("TStreamerObjectPointer", "fParents",
                "array of Parent objects  (eg TTree branch) holding the "
                "referenced objects", 64, 8, "TObjArray*"),
        Element("TStreamerObjectPointer", "fOwner",
                "Object owning this TRefTable", 64, 8, "TObject*"),
        # fCtype is kObject (61), not kSTLstring: std::string has a
        # dictionary, so the collection's value class is found
        # (`ElementLists.md` erratum 2).
        Element("TStreamerSTL", "fProcessGUIDs",
                "UUIDs of TProcessIDs used in fParentIDs", 500, 24,
                "vector<string>", stl_type=1, ctype=61),
    ]))
    add(Info("TBranchRef", 1, [
        _base("TBranch", "Branch descriptor", 0, 13, cs("TBranch")),
        Element("TStreamerObjectPointer", "fRefTable",
                "pointer to the TRefTable", 64, 8, "TRefTable*"),
    ]))
    add(Info("TTree", 20, [
        _base("TNamed", "The basis for a named object (name, title)", 67, 1,
              cs("TNamed")),
        _base("TAttLine", "Line attributes", 0, 2, cs("TAttLine")),
        _base("TAttFill", "Fill area attributes", 0, 2, cs("TAttFill")),
        _base("TAttMarker", "Marker attributes", 0, 3, cs("TAttMarker")),
        _basic("fEntries", "Number of entries", 16, 8, "Long64_t"),
        _basic("fTotBytes",
               "Total number of bytes in all branches before compression", 16,
               8, "Long64_t"),
        _basic("fZipBytes",
               "Total number of bytes in all branches after compression", 16, 8,
               "Long64_t"),
        _basic("fSavedBytes", "Number of autosaved bytes", 16, 8, "Long64_t"),
        _basic("fFlushedBytes", "Number of auto-flushed bytes", 16, 8,
               "Long64_t"),
        _basic("fWeight", "Tree weight (see TTree::SetWeight)", 8, 8, "double"),
        _basic("fTimerInterval", "Timer interval in milliseconds", 3, 4, "int"),
        _basic("fScanField", "Number of runs before prompting in Scan", 3, 4,
               "int"),
        _basic("fUpdate", "Update frequency for EntryLoop", 3, 4, "int"),
        _basic("fDefaultEntryOffsetLen",
               "Initial Length of fEntryOffset table in the basket buffers", 3,
               4, "int"),
        _basic("fNClusterRange",
               "Number of Cluster range in addition to the one defined by "
               "'AutoFlush'", 6, 4, "int"),
        _basic("fMaxEntries",
               "Maximum number of entries in case of circular buffers", 16, 8,
               "Long64_t"),
        _basic("fMaxEntryLoop", "Maximum number of entries to process", 16, 8,
               "Long64_t"),
        _basic("fMaxVirtualSize",
               "Maximum total size of buffers kept in memory", 16, 8,
               "Long64_t"),
        _basic("fAutoSave",
               "Autosave tree when fAutoSave entries written or -fAutoSave "
               "(compressed) bytes produced", 16, 8, "Long64_t"),
        _basic("fAutoFlush",
               "Auto-flush tree when fAutoFlush entries written or -fAutoFlush "
               "(compressed) bytes produced", 16, 8, "Long64_t"),
        _basic("fEstimate", "Number of entries to estimate histogram limits",
               16, 8, "Long64_t"),
        Element("TStreamerBasicPointer", "fClusterRangeEnd",
                "[fNClusterRange] Last entry of a cluster range.", 56, 8,
                "Long64_t*", count_version=20, count_name="fNClusterRange",
                count_class="TTree"),
        Element("TStreamerBasicPointer", "fClusterSize",
                "[fNClusterRange] Number of entries in each cluster for a given "
                "range.", 56, 8, "Long64_t*", count_version=20,
                count_name="fNClusterRange", count_class="TTree"),
        Element("TStreamerObjectAny", "fIOFeatures",
                "IO features to define for newly-written baskets and branches.",
                62, 1, "ROOT::TIOFeatures"),
        Element("TStreamerObject", "fBranches", "List of Branches", 61, 64,
                "TObjArray"),
        Element("TStreamerObject", "fLeaves",
                "Direct pointers to individual branch leaves", 61, 64,
                "TObjArray"),
        Element("TStreamerObjectPointer", "fAliases",
                "List of aliases for expressions based on the tree branches.",
                64, 8, "TList*"),
        Element("TStreamerObjectAny", "fIndexValues", "Sorted index values", 62,
                24, "TArrayD"),
        Element("TStreamerObjectAny", "fIndex", "Index of sorted values", 62, 24,
                "TArrayI"),
        Element("TStreamerObjectPointer", "fTreeIndex",
                "Pointer to the tree Index (if any)", 64, 8, "TVirtualIndex*"),
        Element("TStreamerObjectPointer", "fFriends",
                "pointer to list of friend elements", 64, 8, "TList*"),
        Element("TStreamerObjectPointer", "fUserInfo",
                "pointer to a list of user objects associated to this Tree", 64,
                8, "TList*"),
        Element("TStreamerObjectPointer", "fBranchRef",
                "Branch supporting the TRefTable (if any)", 64, 8,
                "TBranchRef*"),
    ]))
    order = ["TTree", "TNamed", "TObject", "TAttLine", "TAttFill", "TAttMarker",
             "ROOT::TIOFeatures", "TBranch"]
    for kind in leaf_kinds:
        order.append(f"TLeaf{kind}")
        if kind == leaf_kinds[0]:
            order.append("TLeaf")
    order += ["TList", "TSeqCollection", "TCollection", "TString", "TBranchRef",
              "TRefTable", "TObjArray"]
    return s.ordered(order)


# ---------------------------------------------------------------------------
# Trees, spec/06-writing/WritingTrees.md.
# ---------------------------------------------------------------------------

#: Per leaf kind: the element type of fMinimum/fMaximum, its width and the type
#: name a streamer info records for them. `TLeafC` keeps `Int_t` here like every
#: other leaf -- its own values are bytes, but its range members are not
#: (`WritingTrees.md` 4.5).
LEAF_SCALARS = {
    "I": (3, 4, "int"),
    "F": (5, 4, "float"),
    "D": (8, 8, "double"),
    "L": (16, 8, "Long64_t"),
    "S": (2, 2, "short"),
    "B": (11, 1, "char"),
    "O": (18, 1, "bool"),
    "C": (3, 4, "int"),
}
#: The struct format of fMinimum and fMaximum, which for every kind but C is
#: also the format of one value in a basket.
LEAF_FORMATS = {"I": ">i", "F": ">f", "D": ">d", "L": ">q", "S": ">h",
                "B": ">b", "O": ">b", "C": ">i"}
#: fLenType: the bytes one element occupies. It is *not* sizeof(fMinimum) for a
#: TLeafC, which stores one byte per character (`WritingTrees.md` 4.5).
LEAF_LEN_TYPES = {"C": 1}
#: The letter a leaflist uses for each, which is also what fTitle carries.
LEAF_LETTERS = {"I": "I", "F": "F", "D": "D", "L": "L", "S": "S", "B": "B",
                "O": "O", "C": "C"}

TREE_VERSION = 20
BRANCH_VERSION = 13
LEAF_VERSION = 2
BASKET_VERSION = 3
#: A basket's key version: TKey's 4 plus 1000, added unconditionally by
#: TBasket's constructor (root/tree/tree/src/TBasket.cxx:71).
BASKET_KEY_VERSION = 1004
#: The 19 bytes of TBasket header that sit inside fKeylen.
BASKET_HEADER_LEN = 19

#: TBranch::Streamer floors fMaxBaskets at 10 while writing, whatever the
#: branch's real capacity is (`root/tree/tree/src/TBranch.cxx:3190-3193`).
MIN_MAX_BASKETS = 10

#: ROOT's defaults for the tree record's bookkeeping fields.
DEFAULT_BASKET_SIZE = 32000
DEFAULT_ENTRY_OFFSET_LEN = 1000
DEFAULT_SCAN_FIELD = 25
DEFAULT_MAX_ENTRIES = 1000000000000
DEFAULT_AUTO_SAVE = -300000000
DEFAULT_AUTO_FLUSH = -30000000
DEFAULT_ESTIMATE = 1000000
#: ROOT::TIOFeatures has no ClassDef, so its version word is 0 and a checksum
#: (WritingObjects.md 2). The value is the class's, and constant.
IO_FEATURES_CHECKSUM = 0x1AA12F10
#: TBranch's TObject bits in a ROOT-written file.
BRANCH_BITS = 0x00400000


def io_features(bits: int = 0) -> bytes:
    """`fIOFeatures`: a foreign class, so version 0 and a checksum."""
    payload = u16(0) + u32(IO_FEATURES_CHECKSUM) + bytes([bits])
    return u32(BYTE_COUNT_MASK | len(payload)) + payload


@dataclass
class Leaf:
    """One `TLeaf` subclass instance: the description of a branch's data."""

    name: str
    kind: str
    #: fLen: the fixed multiplicity. 1 for a scalar and for a counted array.
    length: int = 1
    #: fLeafCount: the leaf holding this one's per-entry count.
    counter: "Leaf | None" = None
    #: fIsRange, which a counter leaf carries and nothing else.
    is_range: bool = False
    is_unsigned: bool = False
    offset: int = 0
    minimum: float = 0
    maximum: float = 0
    title: str | None = None

    def __post_init__(self):
        if self.kind not in LEAF_SCALARS:
            raise WriteError(f"unknown leaf kind {self.kind!r}")
        if self.title is None:
            # fTitle carries the dimensions and fName does not; Draw and Scan
            # parse this string (WritingTrees.md 3.1).
            dims = ""
            if self.counter is not None:
                dims = f"[{self.counter.name}]"
            elif self.length > 1:
                dims = f"[{self.length}]"
            self.title = self.name + dims

    @property
    def class_name(self) -> str:
        return f"TLeaf{self.kind}"

    @property
    def len_type(self) -> int:
        return LEAF_LEN_TYPES.get(self.kind, LEAF_SCALARS[self.kind][1])

    @property
    def variable(self) -> bool:
        """Whether this leaf's entries differ in length.

        True for a counted array and for a `TLeafC`, and those are the two
        things that force the branch's `fEntryOffsetLen` non-zero
        (`WritingTrees.md` 4.5).
        """
        return self.kind == "C" or self.counter is not None

    def pack(self, values) -> bytes:
        """One entry's bytes.

        A `TLeafC` writes a counted string and **an empty one writes nothing at
        all** -- not even the length byte, because `WriteFastArrayString`
        returns first (`root/io/io/src/TBufferFile.cxx:2038`). That asymmetry is
        the whole difficulty of the class; `WritingTrees.md` 4.5 and
        `spec/04-ttree/TLeaf.md` 9 are the two halves of it.
        """
        if self.kind == "C":
            if isinstance(values, bytes):
                values = values.decode("latin-1")
            if not isinstance(values, str):
                raise WriteError("a TLeafC entry is a string")
            return b"" if not values else counted_string(values)
        fmt = LEAF_FORMATS[self.kind]
        if not isinstance(values, (list, tuple)):
            values = [values]
        return b"".join(struct.pack(fmt, v) for v in values)

    def note(self, values) -> None:
        """Raise the high-water marks this entry moves.

        A counter leaf's `fMaximum` must cover every count in the file
        (`WritingTrees.md` 4.4). A `TLeafC` keeps a second, separate high-water
        mark: `fLen` **and** `fMaximum` are both the longest string seen plus
        one, and they are equal in every file ROOT writes (§4.5).
        """
        if self.kind == "C":
            n = len(values) + 1
            self.length = max(self.length, n)
            self.maximum = max(self.maximum, n)
        elif self.is_range:
            biggest = max(values) if isinstance(values, (list, tuple)) else values
            self.maximum = max(self.maximum, biggest)

    def write(self, p: Payload) -> None:
        ftype, size, _ = LEAF_SCALARS[self.kind]

        def body(q: Payload) -> None:
            def base(r: Payload) -> None:
                r.tnamed(self.name, self.title)
                r.raw(i32(self.length) + i32(self.len_type) + i32(self.offset))
                r.raw(bytes([1 if self.is_range else 0,
                             1 if self.is_unsigned else 0]))
                if self.counter is None:
                    r.null()
                else:
                    # An object reference, which is why the counter leaf must be
                    # written earlier in the same record (WritingTrees.md 3.2).
                    r.reference(id(self.counter))
            q.framed(LEAF_VERSION, base)
            fmt = LEAF_FORMATS[self.kind]
            q.raw(struct.pack(fmt, self.minimum) + struct.pack(fmt, self.maximum))
        p.slot(self.class_name, 1, body, key=id(self))


@dataclass
class BasketBuffer:
    """One basket's entries, closed and waiting to be written.

    A branch holds one of these per flush. Two of the fields are snapshots of
    branch state at the moment the basket was *closed* rather than now, because
    ROOT rewrites both while filling continues: `buffer_size` is the branch's
    `fBasketSize` then (`WritingTrees.md` 7.3) and `nev_buf_size` is the
    `fEntryOffsetLen` the basket was created with (§5.1).
    """

    data: bytes
    offsets: list
    entries: int
    first_entry: int
    buffer_size: int
    nev_buf_size: int


@dataclass
class Branch:
    """One `TBranch` and its baskets, one per flush."""

    name: str
    leaf: Leaf
    tree_name: str = ""
    title: str | None = None
    compress: int = 0
    basket_size: int = DEFAULT_BASKET_SIZE
    #: Non-zero iff the baskets carry an entry-offset array, which is required
    #: exactly when the entries are not all the same length.
    entry_offset_len: int = 0
    first_entry: int = 0
    # Filled in as entries arrive: the open buffer.
    data: bytearray = field(default_factory=bytearray)
    offsets: list = field(default_factory=list)
    entries: int = 0
    #: The baskets already closed, in flush order, and the entries in them.
    flushed: list = field(default_factory=list)
    written: int = 0

    def __post_init__(self):
        if self.title is None:
            self.title = f"{self.leaf.title}/{LEAF_LETTERS[self.leaf.kind]}"
        if self.leaf.variable and self.entry_offset_len == 0:
            self.entry_offset_len = DEFAULT_ENTRY_OFFSET_LEN
        #: fEntryOffsetLen as it was when the open buffer was created, which is
        #: what that basket records as fNevBufSize (WritingTrees.md 5.1). It
        #: differs from fEntryOffsetLen as soon as one flush has shrunk that.
        self.capacity = self.entry_offset_len

    @property
    def variable(self) -> bool:
        return self.entry_offset_len != 0

    @property
    def basket_key_len(self) -> int:
        return Key(class_name="TBasket", name=self.name, title=self.tree_name,
                   obj_len=0, nbytes=0, seek_key=0, seek_pdir=BEGIN,
                   version=BASKET_KEY_VERSION,
                   extra=b"\x00" * BASKET_HEADER_LEN).key_len

    def fill(self, values) -> None:
        """Append one entry's bytes, and its offset if the branch needs one."""
        self.offsets.append(self.basket_key_len + len(self.data))
        self.data += self.leaf.pack(values)
        self.entries += 1

    # -- the basket record ----------------------------------------------

    def flushed_entry_offset_len(self) -> int:
        """`fEntryOffsetLen` as the branch records it after its basket is out.

        ROOT shrinks the value at flush so the array does not stay large
        unnecessarily: above 10, and when `4 x fNevBuf` is smaller, it becomes
        10 for fewer than three entries and `4 x fNevBuf` otherwise
        (`root/tree/tree/src/TBranch.cxx:3225-3227`). Nothing on the read side
        uses the value beyond "is it non-zero", so reproducing this is only
        about matching ROOT byte for byte.
        """
        n = self.entry_offset_len
        if n > 10 and 4 * self.entries < n:
            return 10 if self.entries < 3 else 4 * self.entries
        if n and self.entries > n:
            return 2 * self.entries
        return n

    def flush(self, next_basket_size: int | None = None) -> bool:
        """Close the open buffer into a basket. False if there was nothing.

        This is the write-side half of a cluster boundary: `fWriteBasket`
        advances, the three counted arrays gain an element, and
        `fEntryOffsetLen` is rewritten from the number of entries the basket
        held (`WritingTrees.md` 7). `next_basket_size` is ROOT's
        `OptimizeBaskets` rewriting `fBasketSize` at the first automatic flush
        (§7.3); it is policy, so it is an input here.
        """
        if not self.entries:
            return False
        if self.variable:
            nev_buf_size = self.capacity
        else:
            nev_buf_size = len(self.data) // self.entries
        self.flushed.append(BasketBuffer(
            data=bytes(self.data), offsets=list(self.offsets),
            entries=self.entries, first_entry=self.first_entry + self.written,
            buffer_size=self.basket_size, nev_buf_size=nev_buf_size))
        self.entry_offset_len = self.flushed_entry_offset_len()
        self.capacity = self.entry_offset_len
        if next_basket_size is not None:
            self.basket_size = next_basket_size
        self.written += self.entries
        self.data, self.offsets, self.entries = bytearray(), [], 0
        return True

    def baskets(self) -> list:
        """Every basket this branch writes, in flush order.

        Closes the open buffer first, which is what `TTree::Write` does through
        `FlushBaskets`, so calling this twice adds nothing.
        """
        self.flush()
        return [self._basket(i, b) for i, b in enumerate(self.flushed)]

    def basket(self) -> Obj:
        """The one basket of a branch that has exactly one."""
        baskets = self.baskets()
        if len(baskets) != 1:
            raise WriteError(f"branch {self.name} has {len(baskets)} baskets")
        return baskets[0]

    def _basket(self, index: int, buf: BasketBuffer) -> Obj:
        """One basket, as a record of its own.

        Its key is 19 bytes longer than the strings account for, because
        `TBasket`'s own header lives inside `fKeylen` -- and its version is
        1004, so the two offsets are 8 bytes wide whatever the file's size. Its
        `fCycle` is the basket number, which nothing reads
        (`root/tree/tree/src/TBasket.cxx:1293`).
        """
        key_len = self.basket_key_len
        payload = buf.data
        last = key_len + len(payload)
        if self.variable:
            # fNevBuf + 1 offsets, the last of which is never read: it is
            # whatever the array was initialised to, and ROOT's is 0.
            payload += i32(buf.entries + 1)
            payload += b"".join(i32(o) for o in buf.offsets) + i32(0)
        header = (u16(BASKET_VERSION) + i32(buf.buffer_size)
                  + i32(buf.nev_buf_size) + i32(buf.entries) + i32(last)
                  + bytes([0]))
        return Obj(class_name="TBasket", name=self.name, title=self.tree_name,
                   payload=payload, key_version=BASKET_KEY_VERSION,
                   key_extra=header, cycle=index, in_key_list=False)

    # -- the branch's own record, inside the tree ------------------------

    def write(self, p: Payload, keys: list) -> None:
        """The branch's own record, inside the tree's `fBranches`.

        `keys` is this branch's basket keys in flush order, which is where the
        three counted arrays come from: a writer cannot build this record until
        every basket is placed (`WritingTrees.md` 7.1).
        """
        n = len(keys)
        if n != len(self.flushed):
            raise WriteError(f"branch {self.name}: {n} basket key(s) for "
                             f"{len(self.flushed)} basket(s)")
        # fMaxBaskets on disk is not the in-memory capacity: TBranch::Streamer
        # sets it to fWriteBasket + 1, floored at 10, for the duration of the
        # write (`root/tree/tree/src/TBranch.cxx:3190-3193`), and the three
        # arrays are that long.
        max_baskets = max(n + 1, MIN_MAX_BASKETS)
        pad = max_baskets - n

        def body(q: Payload) -> None:
            q.tnamed(self.name, self.title, bits=BRANCH_BITS)

            def att_fill(r: Payload) -> None:
                r.raw(b"".join(i16(v) for v in FILL_DEFAULTS))
            q.framed(2, att_fill)

            q.raw(i32(self.compress) + i32(self.basket_size)
                  + i32(self.entry_offset_len)
                  + i32(n))                                   # fWriteBasket
            q.raw(i64(self.first_entry + self.written))        # fEntryNumber
            q.raw(io_features())
            q.raw(i32(0))                                     # fOffset
            q.raw(i32(max_baskets))                           # fMaxBaskets
            q.raw(i32(0))                                      # fSplitLevel
            q.raw(i64(self.written) + i64(self.first_entry))
            q.raw(i64(sum(k.key_len + k.obj_len for k in keys)))  # fTotBytes
            q.raw(i64(sum(k.nbytes for k in keys)))            # fZipBytes
            q.tobjarray("", [], embedded=True)                 # fBranches
            q.tobjarray("", [self.leaf.write], embedded=True)  # fLeaves
            # fBaskets has fWriteBasket + 1 slots and every one of them is
            # null: TBranch::Streamer removes from the array every basket that
            # is already on disk (WritingTrees.md 4.1).
            q.tobjarray("", [lambda r: r.null()] * (n + 1), embedded=True)
            # The three counted pointers: a flag byte, then fMaxBaskets values
            # each, with no length of their own. Element i describes basket i;
            # fBasketEntry has one element more than there are baskets, and the
            # padding past it is zero.
            q.raw(b"\x01" + b"".join(i32(k.nbytes) for k in keys)
                  + i32(0) * pad)                             # fBasketBytes
            q.raw(b"\x01" + b"".join(i64(b.first_entry) for b in self.flushed)
                  + i64(self.first_entry + self.written)
                  + i64(0) * (pad - 1))                       # fBasketEntry
            q.raw(b"\x01" + b"".join(i64(k.seek_key) for k in keys)
                  + i64(0) * pad)                             # fBasketSeek
            q.raw(counted_string(""))                          # fFileName
        p.slot("TBranch", BRANCH_VERSION, body, key=id(self))


@dataclass
class Tree:
    """A `TTree` of flat branches, with one basket per branch per flush."""

    name: str
    title: str = ""
    branches: list = field(default_factory=list)
    entries: int = 0
    weight: float = 1.0
    scan_field: int = DEFAULT_SCAN_FIELD
    default_entry_offset_len: int = DEFAULT_ENTRY_OFFSET_LEN
    max_entries: int = DEFAULT_MAX_ENTRIES
    auto_save: int = DEFAULT_AUTO_SAVE
    auto_flush: int = DEFAULT_AUTO_FLUSH
    estimate: int = DEFAULT_ESTIMATE
    saved_bytes: int = 0
    #: The closed cluster ranges: the last entry of each, inclusive, and the
    #: cluster size within it (`WritingTrees.md` 7.4).
    cluster_range_end: list = field(default_factory=list)
    cluster_size: list = field(default_factory=list)
    #: How many times every branch has been flushed, and how many of those
    #: rounds were automatic -- only the latter move fFlushedBytes (§7.5).
    rounds: int = 0
    automatic_rounds: int = 0

    def branch(self, name: str, kind: str, length: int = 1,
               counter: "Branch | None" = None, title: str | None = None,
               basket_size: int = DEFAULT_BASKET_SIZE):
        """Add a branch of one leaf, optionally counted by another branch."""
        leaf = Leaf(name=name, kind=kind, length=length,
                    counter=counter.leaf if counter is not None else None)
        if counter is not None:
            # fIsRange belongs on the *counter*, and nothing else sets it.
            counter.leaf.is_range = True
        br = Branch(name=name, leaf=leaf, tree_name=self.name, title=title,
                    basket_size=basket_size)
        self.branches.append(br)
        return br

    def flush(self, *, automatic: bool = True,
              basket_size: int | None = None) -> None:
        """Close one basket on every branch: a cluster boundary.

        `automatic` distinguishes the flush ROOT does from `TTree::Fill` when a
        watermark is reached, which sets `fFlushedBytes`, from the one
        `TTree::Write` does at the end, which does not
        (`root/tree/tree/src/TTree.cxx:4816` against `:10012`). A reader uses
        that difference: `fFlushedBytes` of 0 means no cluster boundary was ever
        recorded.
        """
        flushed = [br.flush(next_basket_size=basket_size)
                   for br in self.branches]
        if not any(flushed):
            return
        self.rounds += 1
        if automatic:
            self.automatic_rounds = self.rounds

    def set_auto_flush(self, value: int) -> None:
        """Change the flush watermark, closing a cluster range if one is open.

        `TTree::SetAutoFlush` records the boundary only when flushing has
        already happened, and only when either watermark is a positive entry
        count (`root/tree/tree/src/TTree.cxx:8451-8458`). The size it records is
        the **old** value, because `fAutoFlush` is assigned afterwards.
        """
        if value == self.auto_flush:
            return
        if (self.auto_flush > 0 or value > 0) and self.automatic_rounds:
            self.mark_cluster()
        self.auto_flush = value

    def mark_cluster(self) -> None:
        """Close the open cluster range at the current entry count.

        `TTree::MarkEventCluster` (`root/tree/tree/src/TTree.cxx:8466-8499`):
        the range ends at `fEntries - 1`, inclusive, and its size is the current
        watermark when that is positive.
        """
        if not self.entries:
            return
        self.cluster_range_end.append(self.entries - 1)
        if self.auto_flush > 0:
            self.cluster_size.append(self.auto_flush)
        elif len(self.cluster_range_end) == 1:
            self.cluster_size.append(self.entries)
        else:
            self.cluster_size.append(self.cluster_range_end[-1]
                                     - self.cluster_range_end[-2])

    def fill(self, values: dict) -> None:
        """One entry. `values` maps each branch's name to its value(s)."""
        if set(values) != {b.name for b in self.branches}:
            raise WriteError("every branch needs a value in every entry")
        for br in self.branches:
            v = values[br.name]
            if br.leaf.counter is not None:
                count = values[br.leaf.counter.name]
                if len(v) != count:
                    raise WriteError(
                        f"branch {br.name} got {len(v)} values where "
                        f"{br.leaf.counter.name} says {count}")
            elif (br.leaf.kind != "C" and isinstance(v, (list, tuple))
                  and len(v) != br.leaf.length):
                raise WriteError(
                    f"branch {br.name} got {len(v)} values where fLen is "
                    f"{br.leaf.length}")
            br.fill(v)
            # The high-water marks: a counter leaf's fMaximum, which ROOT clamps
            # the read with if it is too small (WritingTrees.md 4.4), and a
            # TLeafC's fLen and fMaximum (§4.5).
            br.leaf.note(v)
        self.entries += 1

    def records(self) -> list:
        """The baskets, then the tree record. In that order, necessarily.

        Any entries still in an open buffer are flushed first -- one more basket
        per branch -- because a tree record cannot describe a basket that is not
        on disk. Baskets go out in flush order, all branches of round 0 before
        any of round 1, which is the order ROOT's `FlushBaskets` produces.
        """
        self.flush(automatic=False)
        out = []
        for round_ in range(self.rounds):
            for br in self.branches:
                if round_ < len(br.flushed):
                    out.append(br._basket(round_, br.flushed[round_]))
        out.append(Obj(class_name="TTree", name=self.name, title=self.title,
                       payload=b"", builder=self._payload))
        return out

    def _payload(self, key_len: int, placed) -> bytes:
        by_name: dict = {}
        for item in placed:
            if item.key.class_name == "TBasket":
                by_name.setdefault(item.key.name, []).append(item.key)
        p = Payload(key_len)

        def body(q: Payload) -> None:
            q.tnamed(self.name, self.title, bits=K_MUST_CLEANUP)

            def line(r: Payload) -> None:
                r.raw(b"".join(i16(v) for v in LINE_DEFAULTS))
            q.framed(2, line)

            def fill_(r: Payload) -> None:
                r.raw(b"".join(i16(v) for v in FILL_DEFAULTS))
            q.framed(2, fill_)

            def marker(r: Payload) -> None:
                r.raw(i16(MARKER_DEFAULTS[0]) + i16(MARKER_DEFAULTS[1])
                      + f32(MARKER_DEFAULTS[2]))
            q.framed(3, marker)

            keys = {b.name: by_name.get(b.name, []) for b in self.branches}
            tot = sum(k.key_len + k.obj_len
                      for b in self.branches for k in keys[b.name])
            zip_ = sum(k.nbytes for b in self.branches for k in keys[b.name])
            # fFlushedBytes is fZipBytes as of the last *automatic* flush, so
            # it counts the baskets of those rounds only (7.5).
            flushed = sum(k.nbytes for b in self.branches
                          for k in keys[b.name][:self.automatic_rounds])
            q.raw(i64(self.entries) + i64(tot) + i64(zip_)
                  + i64(self.saved_bytes) + i64(flushed))
            q.raw(f64(self.weight))
            q.raw(i32(0) + i32(self.scan_field) + i32(0)
                  + i32(self.default_entry_offset_len)
                  + i32(len(self.cluster_range_end)))          # fNClusterRange
            q.raw(i64(self.max_entries) + i64(self.max_entries) + i64(0))
            q.raw(i64(self.auto_save) + i64(self.auto_flush)
                  + i64(self.estimate))
            # fClusterRangeEnd and fClusterSize: counted pointers of
            # fNClusterRange values each. With no closed range, that is a single
            # *absent* flag byte each and nothing behind it; otherwise a present
            # flag and exactly fNClusterRange values (7.4).
            for values in (self.cluster_range_end, self.cluster_size):
                if values:
                    q.raw(b"\x01" + b"".join(i64(v) for v in values))
                else:
                    q.raw(b"\x00")
            q.raw(io_features())
            # TTree::fBranches is the one TObjArray in the record that ROOT
            # marks kIsOwner.
            q.tobjarray("", [
                (lambda b: (lambda r: b.write(r, keys[b.name])))(br)
                for br in self.branches
            ], bits=0x4000, embedded=True)
            # fLeaves holds references to the leaves already written inside
            # fBranches -- the same objects, not copies.
            q.tobjarray("", [
                (lambda leaf: (lambda r: r.reference(id(leaf))))(br.leaf)
                for br in self.branches
            ], embedded=True)
            q.null()                          # fAliases, a TList*
            # fIndexValues and fIndex are TArray members rather than pointers,
            # so each is an fN of 0 and nothing else.
            q.raw(tarray_d([]) + i32(0))
            q.null()                          # fTreeIndex
            q.null()                          # fFriends
            q.null()                          # fUserInfo
            q.null()                          # fBranchRef
        p.framed(TREE_VERSION, body)
        return bytes(p.buf)
