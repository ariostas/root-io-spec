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
        if compress != 0:
            raise WriteError("only uncompressed records are implemented; "
                             "see spec/06-writing/WritingObjects.md")
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

    def add(self, obj: Obj) -> None:
        self.objects.append(obj)

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

    def to_bytes(self) -> bytes:
        dir_obj_len = (string_len(self.file_name) + string_len(self.title)
                       + DIR_RECORD_LEN)
        dir_key = self._self_key(BEGIN, dir_obj_len)

        pos = BEGIN + dir_key.nbytes
        placed: list[_Placed] = []
        for obj in self.objects:
            key = Key(class_name=obj.class_name, name=obj.name, title=obj.title,
                      obj_len=len(obj.payload), nbytes=0, seek_key=pos,
                      seek_pdir=BEGIN, datime=self.datime)
            key.nbytes = key.key_len + key.obj_len
            placed.append(_Placed(key=key, payload=obj.payload))
            pos += key.nbytes

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
        out[37:41] = i32(0)                       # fSeekInfo, WritingObjects.md
        out[41:45] = i32(0)                       # fNbytesInfo
        out[45:47] = u16(1)                       # TUUID version
        out[47:63] = self.uuid

        out += dir_key.to_bytes()
        out += self._dir_payload(keys_key.nbytes, seek_keys)
        for p in placed:
            out += p.to_bytes()
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
