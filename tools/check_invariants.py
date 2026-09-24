#!/usr/bin/env python3
"""Check the `Invariants` sections of spec/ against every fixture.

Each layer document ends with a list of properties a conforming file satisfies
(see PLAN.md 2.8). This makes those lists executable. It validates the
reference files, and it validates the invariants themselves: a property stated
wrongly fails here against files ROOT wrote.

Each check names the document and section it comes from. Needs no third-party
packages; the one exception is noted where it arises.
"""

from __future__ import annotations

import dataclasses
import re
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import rootfile  # noqa: E402

KNOWN_KEY_VERSIONS = {1, 2, 3, 4, 1002, 1003, 1004}

#: Compression.md 9: RNTuple's artificial key class, whose payload is a sequence
#: of sealed pages rather than one object.
RBLOB_CLASS = "RBlob"

#: Record.md 3.6: the first release whose RNTuple writer stopped pointing an
#: RBlob key's fSeekPdir at the key itself (commit 5fe8a99942).
RBLOB_PDIR_FIXED = (6, 36, 0)

#: Before these releases a TBranchElement constructor allocated the three basket
#: arrays without zeroing them, so every element the writer never assigned holds
#: whatever the heap held: the ones above fWriteBasket, and fBasketSeek at an
#: embedded slot. All TBranchElement constructors until 3.10/02 (root commit
#: 8bc05fa54d7, 2003-12-08); the top-level collection constructor until 5.21/02
#: (root commit f0127d321c7, 2008-08-12). TBranch.md 11.4, 11.9.
ELEMENT_ARRAYS_ZEROED = (3, 10, 2)
COLLECTION_ARRAYS_ZEROED = (5, 21, 2)

#: FreeSegments.md 4.2: the first release whose RNTuple writer wrote the marker of
#: the gap left over when an RBlob took part of a free slot (commit d328b598b32).
RBLOB_MARKER_FIXED = (6, 36, 0)

#: kNBytesPageChecksum, root/tree/ntuple/inc/ROOT/RPageStorage.hxx:74.
RN_PAGE_CHECKSUM = 8

RBLOB_MULTIPAGE = (
    "it holds more than one sealed page, and the page boundaries are in the "
    "page list envelope, which this check does not consult. Compression.md 9"
)

#: TBasket.md 1: the release from which a basket key is always the large form.
#: ROOT 4.00/04 still writes the small form; 4.02/00 is the first production
#: release carrying commit 3970c0bead.
BASKET_LARGE_KEY_SINCE = (4, 2, 0)

#: Collections.md 1: before this release the TStreamerSTL constructor that parses
#: a type name tested "map" before "multimap" and "set" before "multiset"
#: (v5-22-00:core/meta/src/TStreamerElement.cxx:1486-1491), so a multimap was
#: stored as kSTLmap (4) and a multiset as the old kSTLset (5), which ROOT now
#: reads as a multimap. Fixed by root commit 32b2215c0d0 (2009-06-02). ROOT's
#: read-side repair covers neither, and needs to: the container it reads is
#: taken from the name (root/io/io/src/TEmulatedCollectionProxy.cxx:135).
STL_KIND_FROM_NAME_SINCE = (5, 24, 0)
LEGACY_STL_KINDS = {(4, 5), (5, 7)}      # (stored, named): map/multimap, multimap/multiset

#: TTree.md 6.3: the first release whose TTree::AutoSave stores fZipBytes in
#: fSavedBytes; every earlier one stored fTotBytes (root commit fa3ad228d72).
SAVED_BYTES_ZIP_SINCE = (5, 27, 2)
BLOCK_MAGICS = {b"ZL": 8, b"XZ": 0, b"L4": None, b"ZS": 1, b"CS": 8}
KMAXZIPBUF = 0xFFFFFF
KSTART_BIG_FILE = 2000000000
#: The fVersion at which the 12 reserved bytes of a directory record appear.
ROOT_4_FILE_VERSION = 40000

APPENDIX = REPO / "spec/99-appendix"


def _generated_classes(doc: Path, tag: str) -> set[str]:
    """Class names out of one `<!-- BEGIN GENERATED: tag -->` block in spec/.

    Those blocks are written by `tools/inventory.py` from the pinned submodule
    and checked in CI, so they are a current extraction of ROOT's source. They
    are read from the published documents rather than re-extracted, because this
    checker must run without the submodule; `tools/inventory.py --check` keeps
    them current.
    """
    text = doc.read_text()
    start = text.index(f"<!-- BEGIN GENERATED: {tag} -->")
    body = text[start:text.index("<!-- END GENERATED -->", start)]
    if tag == "forwarding":
        # A definition list grouped by module rather than a table. The module
        # headers are backticked too, and those are the ones with a slash.
        return {name for name in re.findall(r"`([^`]+)`", body) if "/" not in name}
    # A table. Only the first column is a class name: the others hold a
    # backticked path, and a `Where` note may quote another class.
    return {line.split("|")[1].strip().strip("`")
            for line in body.splitlines() if line.startswith("| `")}


#: Classes that record **no streamer info of their own**, so a `kBase` element or
#: an inline member naming one is not a file failing to describe itself.
#: StreamerDriven.md 10.5. Two published sets:
#:
#:   * `custom` -- the hand-written `Streamer` never calls `WriteClassBuffer`,
#:     and that call is what tags a class's info to be written
#:     (spec/06-writing/WritingObjects.md 8.2), so nothing records one;
#:   * forwarding -- the generated `Streamer` writes only the base classes.
#:
#: The `guarded`, `extending` and `delegating` classes are **not** exempt: all
#: three call `WriteClassBuffer`, so a file that holds one holds its info too,
#: and exempting them would weaken the invariant by 124 classes.
NO_INFO_OF_ITS_OWN = (
    _generated_classes(APPENDIX / "HandWrittenStreamers.md", "custom")
    | _generated_classes(APPENDIX / "ForwardingStreamers.md", "forwarding"))

#: Element codes whose bytes are an object written **inline**, with no class
#: record in front of it to name the class: `kObject` (61), `kAny` (62) and the
#: two `->` pointer forms `kObjectp` (63) and `kAnyp` (68), which cannot be null.
#: `kOffsetL` is added to the first two only (ElementTypes.md 7), giving 81 and
#: 82. For these the declared type is what was written, so the file must
#: describe it; for `kObjectP` (64) and `kAnyP` (69) it need not
#: (StreamerDriven.md 6.1).
INLINE_OBJECT_TYPES = {61, 62, 63, 68, 81, 82}

#: sizeof("TDirectoryFile") - sizeof("TDirectory"). A key list written before
#: ROOT 5.34 can hold a directory image this much longer than the fKeylen it
#: reports; spec/01-container/Directory.md 6.5.
LEGACY_DIR_SLACK = 4


def _dir_spelling(class_name: str | None) -> str | None:
    """`TDirectory` and `TDirectoryFile` are one class name on the wire.

    ROOT writes the first and reads it back as the second
    (`root/io/io/src/TKey.cxx:1373`, `:1256`), so a comparison of two keys'
    class names must treat them as equal. `spec/01-container/Directory.md` 6.1.
    """
    return "TDirectory" if class_name in ("TDirectory", "TDirectoryFile") \
        else class_name


def directory_payload_length(version: int, file_version: int) -> int:
    """What a directory record's payload occupies. Directory.md 7.1.

    Three inputs, because the version word holds two independent things and the
    reserved bytes depend on a third: `version % 1000` is the class version, which
    determines the UUID framing; `version > 1000` is the offset width; and the
    **file header's** version determines whether the 12 reserved bytes were
    allocated at all (`root/io/io/src/TDirectoryFile.cxx:1725-1735`, `:785-786`).
    """
    wide = version > 1000
    class_version = version % 1000
    #        version word + fNbytesKeys + fNbytesName + fDatimeC + fDatimeM
    length = 2 + 4 + 4 + 4 + 4
    length += 24 if wide else 12                    # the three offsets
    length += 0 if class_version == 1 else (16 if class_version == 2 else 18)
    if file_version >= ROOT_4_FILE_VERSION and not wide:
        length += 12                                # reserved, small layout only
    return length


def counted_string_len(buf: bytes, offset: int) -> int:
    n = buf[offset]
    return 1 + 4 + struct.unpack_from(">i", buf, offset + 1)[0] if n == 255 else 1 + n


def this_element_failures(info) -> list[tuple[str, str]]:
    """Collections.md invariant 11: a `This` element is its info's only element,
    and its type name is the class the info describes.

    The shape TStreamerInfo::Build gives a class with a collection proxy of its
    own (root/io/io/src/TStreamerInfo.cxx:421-435). Its fSTLtype is the proxy's
    and its type name is not a container name, so invariant 10 does not apply
    to it (Collections.md 11.2).
    """
    out = []
    for el in info.elements:
        if el.name != "This" or el.cls != "TStreamerSTL":
            continue
        if len(info.elements) != 1 or el.type_name != info.name:
            out.append(("Collections 14.11",
                        f"{info.name} has a This element of type "
                        f"{el.type_name!r} among {len(info.elements)} "
                        f"element(s)"))
    return out


def element_list_failures(info, by_name=None) -> list[tuple[str, str]]:
    """StreamerDriven.md invariants 3, 4 and 6, over one streamer info.

    Invariant 5 is `undescribed_classes`, separately: it needs the whole file's
    set of described classes rather than one element list.

    `by_name` maps a class name to its info, so that a counter declared in a base
    class can be found (TArrayD's fArray names fN in TArray). Without it, only
    counters in this same list are accepted.

    Separate from Checker so that it can be exercised on element lists no
    fixture contains, such as an out-of-order base class.
    """
    failures: list[tuple[str, str]] = []
    by_name = by_name or {}
    names = [e.name for e in info.elements]
    bases_seen = 0
    for index, el in enumerate(info.elements):
        # A base that is an STL container is a TStreamerSTL, not a
        # TStreamerBase, and may precede one: StreamerDriven.md 4.3. Its fName
        # is the container type rather than a member name.
        if el.cls in ("TStreamerSTL", "TStreamerSTLstring") and el.name == el.type_name:
            bases_seen += 1
        if el.cls == "TStreamerBase":
            if bases_seen != index:
                failures.append((
                    "StreamerDriven 10.4",
                    f"{info.name}: base {el.name!r} at index {index} follows a "
                    f"non-base element"))
            bases_seen += 1
        if el.count_name:
            counter = None
            if el.count_name in names[:index]:
                counter = info.elements[names.index(el.count_name)]
            else:
                # It may be declared in a base class, which fCountClass names.
                # StreamerDriven.md 3.2.
                owner = by_name.get(el.tail.get("fCountClass", ""))
                if owner is not None:
                    counter = next((e for e in owner.elements
                                    if e.name == el.count_name), None)
            if counter is None:
                failures.append((
                    "StreamerDriven 10.3",
                    f"{info.name}.{el.name} names counter {el.count_name!r}, "
                    f"which is neither earlier in this info nor in "
                    f"{el.tail.get('fCountClass', '')!r}"))
            elif counter.ftype not in rootfile.COUNTER_TYPES:
                failures.append((
                    "StreamerDriven 10.3",
                    f"{info.name}.{el.name} names {el.count_name!r}, whose "
                    f"fType is {counter.ftype}, not an integer basic type"))
        if el.ftype == -1 and el.cls != "TStreamerBase":
            failures.append((
                "StreamerDriven 10.6",
                f"{info.name}.{el.name} has fType -1 but is a {el.cls}, not a "
                f"TStreamerBase"))
    return failures


def undescribed_classes(info, described: set[str]) -> list[tuple[str, str]]:
    """StreamerDriven.md invariant 5, over one streamer info.

    `described` is every class name in the file's `StreamerInfo` record. The
    invariant covers the classes whose bytes are written **inline**, where only
    the declared type identifies them: a `kBase` element, and a member with one
    of `INLINE_OBJECT_TYPES`. A `kObjectP` or `kAnyP` member is excluded, because
    it may be null in every object the file holds and because a non-null one
    names its concrete class in the bytes.

    Separate from Checker so that it can be exercised on element lists no file
    contains. The exemptions are tested that way: the published lists are large
    and a file cannot demonstrate the boundary between them.
    """
    failures: list[tuple[str, str]] = []

    def is_described(name: str) -> bool:
        if not name or name in described or name in NO_INFO_OF_ITS_OWN:
            return True
        # An element need not spell the class as its info does: typedefs,
        # `long long`, default template arguments and, before 6.00/00, the
        # owner's scope. StreamerInfo.md 7.3.
        if rootfile.recorded_class_name(name, described, info.name):
            return True
        # A hand-written layout is recorded under the template name, as ClassDef
        # spells it, while a file names the specialization: TMatrixTSym against
        # TMatrixTSym<double>. Matrix.md 2.2.
        bare = name.split("<", 1)[0]
        if bare in described or bare in NO_INFO_OF_ITS_OWN:
            return True
        # An STL container is described by its type name and Collections.md, not
        # by an info, and ROOT records none for one used as an inline member:
        # `vector<double> twovectors[2]` in uproot-issue-586.root, written by
        # 6.24/06, whose StreamerInfo record holds exactly one entry.
        return (name.startswith(rootfile.COLLECTION_PREFIXES)
                or name in ("string", "std::string"))

    for el in info.elements:
        if el.cls == "TStreamerBase":
            name, what = el.name, "base class"
        elif el.ftype in INLINE_OBJECT_TYPES:
            name, what = rootfile._bare_class(el.type_name), \
                f"member {el.name}, of inline type"
        else:
            continue
        if not is_described(name):
            failures.append((
                "StreamerDriven 10.5",
                f"{info.name}: {what} {name} has no streamer info in this file"))
    return failures


def _element_signature(info) -> list[tuple]:
    """What two entries for one layout must agree on. SchemaEvolution.md 9.6.

    Not `fBits`, where the two legitimately differ, and not `fSize`, which is
    `sizeof` on the writing machine and is masked everywhere else for that
    reason.
    """
    return [(e.cls, e.name, e.ftype, e.type_name, e.array_length,
             tuple(e.max_index), e.title) for e in info.elements]


def info_list_failures(infos) -> list[tuple[str, str]]:
    """SchemaEvolution.md invariants 1 and 6, over one StreamerInfo record.

    Separate from Checker so that both can be exercised: no fixture holds an
    out-of-range fClassVersion, and none holds a pair that disagrees, since ROOT
    does not write one (which is what invariant 6 asserts).
    """
    failures: list[tuple[str, str]] = []
    # There is no uniqueness invariant: two entries for one class may share a
    # version and differ in checksum (SchemaEvolution.md 3), and may agree on
    # both (8.1, which ROOT writes for ROOT::TIOFeatures). Invariant 6 says that
    # when they agree on both, the element lists agree too, so taking either
    # entry is safe.
    layouts: dict[tuple, object] = {}
    for info in infos:
        if not 0 <= info.class_version <= 65000:
            failures.append((
                "SchemaEvolution 9.1",
                f"{info.name} has fClassVersion {info.class_version}"))
        key = (info.name, info.class_version, info.checksum)
        first = layouts.setdefault(key, info)
        if first is not info and _element_signature(first) != _element_signature(info):
            failures.append((
                "SchemaEvolution 9.6",
                f"{info.name}: two entries at version {info.class_version} and "
                f"checksum 0x{info.checksum:08x} have different element lists "
                f"({len(first.elements)} and {len(info.elements)} elements)"))
    return failures


class Checker:
    def __init__(self, path: Path, all_entries: bool = False,
                 custom: "set[str] | None" = None):
        self.path = path
        self.all_entries = all_entries
        # Classes this file's writer gave a hand-written Streamer, from
        # gen/foreign/IGNORE.toml. Nothing in a file marks one
        # (StreamerDriven.md 7), so the list has to come from outside it.
        self.custom = set(custom or ())
        self.sampled = 0
        self._sampled_at: set[int] = set()
        self.skipped: dict[tuple[str, str, str], int] = {}
        #: branch-baskets on which an entry check ran to completion. The
        #: denominator for the SKIPPED counts, so that "0 failures" can be read
        #: against how much was reached.
        self.verified = 0
        #: branch-baskets on which an entry check ran and failed, by label. They
        #: stay in the ENTRIES denominator: a basket that fails was reached,
        #: and dropping it would make the ratio rise when a check breaks.
        self.failed: dict[str, int] = {}
        #: Why a record's object data could not be had, by offset: a missing
        #: codec or a failed decompression. Read back as a skip reason.
        self._undecoded: dict[int, str] = {}
        #: The payload of the TTree record whose branches are being checked,
        #: where an embedded basket lives. TBranch.md 5.
        self._tree_payload = None
        self._rblobs_unchecked: set[int] = set()
        self.failures: list[str] = []
        self.no_codec: set[str] = set()
        self._infos: tuple | None = None
        self._all_branches: list = []
        self._container: set | None = None
        # Decompressing a record copies the whole file buffer, and the entry check
        # of TLeaf.md 10.7 asks for the same counter basket once per entry. Without
        # these two caches a 42 000-entry tree takes minutes instead of a second.
        self._data: dict[int, bytes | None] = {}
        self._baskets: dict[int, object] = {}
        self._by_offset: dict[int, object] | None = None
        self._owners: dict[int, object] = {}
        self.buf = path.read_bytes()
        self.header = self.records = None
        try:
            self.header = rootfile.read_header(self.buf)
            self.records = rootfile.read_records(self.buf, self.header)
        except rootfile.FormatError as exc:
            self.bad("structure", str(exc))

    def bad(self, where: str, message: str) -> None:
        self.failures.append(f"{self.path.name}: {where}: {message}")

    def data(self, rec):
        """The file buffer with `rec`'s object data uncompressed in place.

        Returns None when the record's algorithm is unavailable here, which is
        recorded as "not checked" rather than as a failure: the invariant checks
        depend on nothing outside the standard library, and zstd needs Python
        3.14 while LZ4 needs a package.
        """
        if rec.offset in self._data:
            return self._data[rec.offset]
        try:
            out = rootfile.object_data(self.buf, rec)
        except rootfile.MissingCodec as exc:
            self.no_codec.add(f"some records were not decompressed: {exc}")
            self._undecoded[rec.offset] = f"its codec is missing: {exc}"
            out = None
        except (rootfile.FormatError, struct.error, IndexError, ValueError) as exc:
            # An RBlob is a sequence of sealed pages, not one compressed object,
            # so decompress() walking it as a single chain is expected to fail.
            # Compression.md 9; the same carve-out as check_compression.
            if rec.class_name == RBLOB_CLASS:
                self.rblob_unchecked(rec)
            else:
                self.bad("Compression 9.1", str(exc))
            self._undecoded[rec.offset] = "it does not decompress (Compression 9.1)"
            out = None
        # An uncompressed record shares self.buf, so caching it costs nothing; a
        # compressed one is a file-sized copy, so keep only a handful.
        if out is None or out is self.buf or len(self._data) < 8:
            self._data[rec.offset] = out
        return out

    def skip(self, check: str, reason: str,
             unit: str = "branch-basket") -> None:
        """Record that `check` could not run here, and why.

        Not a pass: a check that cannot run must not be hidden inside a
        "0 failures" line. The counts are printed per reason at the end.

        `unit` says what was skipped, and only `branch-basket` feeds the ENTRIES
        ratio. That figure measures decoding a tree's entries, so counting a
        histogram or a matrix record into it would understate coverage of
        something it does not measure. Units are kept separate for the same
        reason reasons are.
        """
        key = (check, reason, unit)
        self.skipped[key] = self.skipped.get(key, 0) + 1

    def basket(self, rec, payload):
        """`rec` parsed as a basket, memoised. TBasket.md 8."""
        if rec.offset not in self._baskets:
            self._baskets[rec.offset] = rootfile.read_basket(self.buf, rec,
                                                             payload)
        return self._baskets[rec.offset]

    def streamer_infos(self):
        """(buffer, record, infos) for this file's StreamerInfo record.

        Cached, because six checks use it and decompressing it has a cost.
        Returns (None, None, None) when there is none or it cannot be read.
        """
        if self._infos is None:
            self._infos = self._read_streamer_infos()
        return self._infos

    def _read_streamer_infos(self):
        rec = next((r for r in self.records
                    if not r.free and r.name == "StreamerInfo"), None)
        if rec is None or rec.class_name != "TList":
            return (None, None, None)
        data = self.data(rec)
        if data is None:
            return (None, None, None)
        try:
            return (data, rec, rootfile.read_streamer_infos(data, rec))
        except (rootfile.FormatError, struct.error, IndexError, ValueError) as exc:
            self.bad("StreamerInfo 13.12", f"could not parse the record: {exc}")
            return (None, None, None)

    # -- FileHeader.md 10 ---------------------------------------------------
    def check_header(self) -> None:
        h, size = self.header, len(self.buf)
        if self.buf[:4] != b"root":
            self.bad("FileHeader 10.1", "magic is not 'root'")
        if not 0 <= h.begin <= h.end:
            self.bad("FileHeader 10.2", f"fBEGIN {h.begin}, fEND {h.end}")
        if not 10 <= h.nbytes_name <= 10000:
            self.bad("FileHeader 10.4", f"fNbytesName {h.nbytes_name} outside [10, 10000]")
        if h.end > size:
            # Only this direction is an error: the file is truncated. Trailing
            # bytes past fEND are outside the format (FileHeader.md 5.2).
            self.bad("FileHeader 10.5",
                     f"fEND {h.end} past file size {size}: truncated")

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
            # nfree is advisory (FileHeader.md 5.4), but every ROOT release
            # available writes it correctly, back to 2.23/12. The two g4tools
            # files that write 0 are in gen/foreign/IGNORE.toml.
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

        # 10.9 in the direction the format requires: a file past 2 GB has the
        # flag. The flag on a smaller file is legal and ROOT reads it (FileHeader.md
        # 3); foreignVec.root in root/roottest has one.
        if h.end > KSTART_BIG_FILE and not h.large:
            self.bad("FileHeader 10.9",
                     f"large flag {h.large} but fEND is {h.end}")
        # 10.10: ROOT sets fUnits to 8 only together with the flag, so a small
        # layout has 4 and a file past 2 GB has 8. A flagged file below 2 GB may
        # hold either; ROOT never reads the field (FileHeader.md 5.7).
        if (not h.large and h.units != 4) or (h.end > KSTART_BIG_FILE and h.units != 8):
            self.bad("FileHeader 10.10", f"fUnits {h.units} disagrees with the version flag")

        self.check_header_floor(h.begin, h.large)

    #: The length of the file header in each layout: 57 bytes of fields plus an
    #: 18-byte UUID when the offsets are 8 bytes wide, 45 plus 18 when they are
    #: 4 (`root/io/io/src/TFile.cxx:2680-2702`).
    HEADER_LEN = {False: 63, True: 75}

    def check_header_floor(self, begin: int, large: bool) -> None:
        """FileHeader 10.11: the header fits before the first record.

        The header is rewritten in place at every close and its length depends
        on `fVersion`, so a file whose first record starts sooner would have
        that record overwritten by its own header. Split out from `check_header`
        because the only way to provoke it is to move `fBEGIN`, which breaks the
        record walk that the rest of `check_header` needs.
        """
        need = self.HEADER_LEN[bool(large)]
        if begin < need:
            self.bad("FileHeader 10.11",
                     f"fBEGIN {begin} is below the {need}-byte header its "
                     f"fVersion selects: the header would overwrite the first "
                     f"record")

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
            # A TKey subclass may append its own fields inside the key, so the
            # strings give a lower bound rather than the length. TBasket adds 19
            # bytes; Record.md 3.11.
            if rec.class_name == "TBasket":
                # 19 bytes, or 20 when the basket has fIOBits.
                if rec.key_len not in (total + 19, total + 20):
                    self.bad("Record 8.3",
                             f"TBasket fKeylen {rec.key_len} != {total} + 19 or 20")
            elif total != rec.key_len:
                self.bad("Record 8.3",
                         f"fKeylen {rec.key_len} != computed key length {total}")

            # 8.6: fSeekPdir is 0 only for the top-level record.
            if rec.seek_pdir == 0:
                if rec.offset != self.header.begin:
                    self.bad("Record 8.6", f"fSeekPdir 0 on a record at {rec.offset}")
            elif (rec.class_name == RBLOB_CLASS and rec.seek_pdir == rec.offset
                    and self.header.root_version < RBLOB_PDIR_FIXED):
                # Record.md 3.6: RNTuple's RFileProper writer passed the key's
                # own offset as its directory until ROOT commit 5fe8a99942,
                # first released in 6.36.00. Scoped to that class, that value
                # and those releases; a self-pointing key anywhere else, or
                # from a later ROOT, still fails.
                pass
            else:
                parent = self.at(rec.seek_pdir)
                if parent is None or rootfile.read_directory(self.buf, parent) is None:
                    self.bad("Record 8.6",
                             f"fSeekPdir {rec.seek_pdir} does not name a directory record")

        if cursor != self.header.end:
            self.bad("Record 8.8", f"chain ends at {cursor}, fEND is {self.header.end}")

    # -- Buffer.md 9 --------------------------------------------------------
    # Records whose payload is not a framed object. Records whose class is
    # TFile or TDirectory are the container's own bookkeeping (root directory,
    # key list, free list, subdirectory records): not streamed objects, so no
    # frame.
    #
    # The rest are classes with a hand-written layout. TRef is a streamed object
    # with no frame: its streamer is TObject::Streamer plus a pidf, and
    # TObject::Streamer asks WriteVersion for no byte count. A TArray has
    # neither a byte count nor a version word; its payload starts with the
    # element count. See Buffer.md 2.3; they are checked by check_references and
    # check_tarray.
    UNFRAMED = ({"TFile", "TDirectory", "TDirectoryFile", "TRef", "TBasket",
                 # RooLinkedList::Streamer calls WriteVersion with no byte
                 # count and then writes a whole object. Buffer.md 2.3.
                 "RooLinkedList",
                 # The rest of Buffer.md 2.3's list, which this set did not
                 # follow until 2026-09-22: TDatime was "described by hand" below
                 # yet required to open with a byte count here, and a TDatime
                 # record in a ROOT-written file (go-hep's tdatime.root) failed
                 # 9.2 because of it. TStringLong and TQObject would have failed
                 # the same way. Each one's payload is still checked
                 # (StreamerDriven 10.1 requires the hand-written shape
                 # rootfile.Decoder.read_object gives it to consume the payload
                 # exactly), so this exempts them from a count, not from a check.
                 # serialization/unframed-records writes all five as records.
                 "TDatime", "TString", "TStringLong", "TObject", "TQObject"}
                | set(rootfile.TARRAY_WIDTH) | rootfile.STD_STRING_NAMES)

    # Classes whose records this reader cannot decode, each with the reason,
    # verified one at a time against the pinned source. Their records are
    # reported as NOT CHECKED with the class named. The reason is per class
    # because `tools/inventory.py` classifies two of these very differently.
    # PLAN.md 9.8.
    UNSPECIFIED_STREAMERS = {
        "RooWorkspace::CodeRepo":
            "the code repository inside a RooWorkspace: a hand-written streamer "
            "this specification does not describe "
            "(root/roofit/roofitcore/src/RooWorkspace.cxx:2427). The other five "
            "RooFit streamers are spec/03-classes/RooFit.md",
        "ROOT::RNTuple":
            "an RNTuple anchor: ReadClassBuffer and then an 8-byte XXH3-64 "
            "checksum outside the byte count. Specified in spec/05-rntuple/ and "
            "read by rootfile.read_rntuple_anchor, not by the streamer-driven "
            "path",
    }

    #: Classes whose `Streamer` writes past the byte count it opened, so that
    #: Buffer.md invariant 9.9 does not hold for them and Buffer.md 2.4 says why.
    #: `tools/inventory.py` extracts this set from the submodule and calls it
    #: `extending`; the two must agree, which `tools/test_inventory.py` checks.
    EXTENDING = ("TMatrixTSym", "TPointSet3D", "ROOT::RNTuple")

    def extends_past_byte_count(self, name: str) -> bool:
        """Is `name` one of Buffer.md 2.4's classes? Templates match the template."""
        return (name or "").split("<", 1)[0] in self.EXTENDING

    def unspecified_streamer(self, name: str) -> str | None:
        """`name` reduced to a class this reader cannot decode, or None."""
        base = (name or "").split("<", 1)[0]
        return base if base in self.UNSPECIFIED_STREAMERS else None

    def needs_unspecified_streamer(self, data, rec) -> str | None:
        """Does reading this record require a class known to diverge?

        Followed through the file's own streamer infos, because an inline member
        is written with no class record and so cannot be found in the bytes.
        """
        _, _, infos = self.streamer_infos()
        by_name = {i.name: i for i in (infos or [])}
        seen: set[str] = set()
        stack = [rec.class_name or ""]
        while stack:
            name = stack.pop()
            if name in seen:
                continue
            seen.add(name)
            found = self.unspecified_streamer(name)
            if found is not None:
                return found
            info = by_name.get(name)
            if info is None:
                continue
            for el in info.elements:
                # An object-pointer member's type name has a trailing `*`,
                # which matches no streamer info; strip it or the walk stops at
                # the first pointer. RooFitResult reaches RooAbsCollection
                # only through `RooArgList*`.
                stack.append(el.name if el.cls == "TStreamerBase"
                             else rootfile._bare_class(el.type_name))
        return None

    def container_records(self) -> set[int]:
        """Offsets of the records that are the container's own bookkeeping.

        Identified structurally, because the class name on them is whatever TFile
        subclass wrote the file (TStorageFactoryFile, ND::TND280Output), not
        necessarily TFile. Record.md 3.
        """
        if self._container is None:
            out = {self.header.begin}
            if self.header.seek_free:
                out.add(self.header.seek_free)
            for rec in self.records:
                if rec.free:
                    continue
                directory = rootfile.read_directory(self.buf, rec)
                if directory is None:
                    continue
                out.add(rec.offset)
                if directory.seek_keys:
                    out.add(directory.seek_keys)
            self._container = out
        return self._container

    def class_is_described(self, name: str) -> bool:
        """Does this file carry a streamer info for `name`?

        A record whose class the file does not describe cannot be checked against
        anything: StreamerDriven.md 6.
        """
        # A template's hand-written layout is recorded under the template name,
        # as `ClassDef` declares it, while a file names the specialization:
        # `TMatrixTSym` against `TMatrixTSym<double>`. Both spellings count as
        # described; otherwise a class whose missing info is *specified*
        # (Matrix.md 2.2) would be reported as a file that fails to describe
        # itself.
        template = (name or "").split("<", 1)[0]
        if (name in rootfile.CUSTOM_STREAMER or template in rootfile.CUSTOM_STREAMER
                or name in self.UNFRAMED
                or name in rootfile.Decoder.SEQUENCES
                or name in ("TClonesArray", "TDatime")
                # Containers.md 4: none of the three ever writes an info, and
                # the document describes each byte (check_containers).
                or name in ("TMap", "TExMap", "TBtree")):
            return True         # described by hand, not by a streamer info
        _, _, infos = self.streamer_infos()
        if infos is None:
            return True
        return any(i.name == name for i in infos)

    def check_buffer_framing(self) -> None:
        # Before ROOT 5 an ordinary class's record payload could begin with a bare
        # version word: Buffer.md 2.3. Nothing in the record indicates this; only
        # the file header's version does.
        framed_by_default = self.header.root_version[0] >= 5
        for rec in self.records:
            if rec.free or rec.class_name in self.UNFRAMED:
                continue
            if rec.offset in self.container_records():
                continue
            base = self.unspecified_streamer(rec.class_name)
            if base is not None:
                self.no_codec.add(
                    f"{base} has a hand-written streamer this specification does "
                    f"not describe")
                continue
            if not self.class_is_described(rec.class_name):
                self.no_codec.add(
                    f"{rec.class_name} has no streamer info in its own file")
                continue
            data = self.data(rec)
            if data is None:
                continue
            start, end = rootfile.payload_range(rec)
            if rec.obj_len < 6:
                self.bad("Buffer 9.2", f"payload of {rec.obj_len} bytes at {rec.offset} "
                                       f"is too short for a byte count and a version")
                continue

            frame = rootfile.read_frame(data, start)

            # 9.9 and 9.2 at the outermost level: the leading byte count spans
            # the payload exactly.
            if frame.byte_count is None:
                if not framed_by_default:
                    continue
                self.bad("Buffer 9.9",
                         f"{rec.class_name} at {rec.offset} has no leading byte count")
                continue
            if start + 4 + frame.byte_count != end:
                if self.extends_past_byte_count(rec.class_name):
                    # Buffer.md 2.4: for an `extending` class the byte count is a
                    # lower bound by design, and the object's full length is
                    # checked by the class's own invariants instead (Matrix 5.4
                    # and 5.5 for a TMatrixTSym).
                    pass
                else:
                    self.bad("Buffer 9.9",
                             f"{rec.class_name} at {rec.offset}: byte count "
                             f"{frame.byte_count} ends at "
                             f"{start + 4 + frame.byte_count}, payload ends at "
                             f"{end}")
            # 9.1
            if frame.byte_count > rootfile.MAX_MAP_COUNT:
                self.bad("Buffer 9.1",
                         f"byte count {frame.byte_count} at {start} exceeds kMaxMapCount")
            # 9.4
            if not 0 <= frame.version <= rootfile.MAX_VERSION:
                self.bad("Buffer 9.4",
                         f"{rec.class_name} at {rec.offset}: class version {frame.version} "
                         f"outside [0, kMaxVersion]")

            if rec.class_name == "TList":
                self.check_tlist_references(data, rec)

    def check_tlist_references(self, data, rec) -> None:
        """Buffer.md 9.5 to 9.8, over the object slots of one TList."""
        try:
            slots = rootfile.read_tlist(data, rec)
        except rootfile.FormatError as exc:
            # Not an independent check of nesting, which Buffer 9.2 and the
            # sequential read imply; see gen/invariants.toml.
            self.bad("Buffer 9.3", f"TList at {rec.offset}: {exc}")
            return

        objects: set[int] = set()   # map positions an object was recorded at
        classes: set[int] = set()   # map positions a class tag was recorded at
        spans: list[tuple[int, int]] = []  # earlier slot interiors, as map positions

        for slot in slots:
            here = slot.offset - rec.offset + rootfile.MAP_OFFSET
            for kind, ref in (("object", slot.reference),
                              ("class", slot.class_reference)):
                if ref is None:
                    continue
                # 9.7: a reference of 1 is the record's own top-level object,
                # which is legitimate and is not a buffer position.
                if kind == "object" and ref == rootfile.SELF_POSITION:
                    continue
                if ref < rootfile.MAP_OFFSET:
                    self.bad("Buffer 9.7",
                             f"TList at {rec.offset}: {kind} reference {ref} is below the "
                             f"first real map position")
                    continue
                # 9.8: a reference above 1 always points backwards.
                if ref >= here:
                    self.bad("Buffer 9.8",
                             f"TList at {rec.offset}: {kind} reference {ref} at map "
                             f"position {here} does not point backwards")
                    continue
                # 9.5 and 9.6: it names something recorded earlier. A reference
                # may name an object nested inside an earlier slot, which this
                # walker does not descend into; such a position must at least
                # fall inside that slot.
                known = objects if kind == "object" else classes
                if ref in known:
                    continue
                if any(lo < ref < hi for lo, hi in spans):
                    continue
                other = classes if kind == "object" else objects
                if ref in other:
                    self.bad("Buffer 9.5" if kind == "class" else "Buffer 9.6",
                             f"TList at {rec.offset}: {kind} reference {ref} names a "
                             f"position recorded for the other kind")
                else:
                    self.bad("Buffer 9.5" if kind == "class" else "Buffer 9.6",
                             f"TList at {rec.offset}: {kind} reference {ref} names no "
                             f"position recorded earlier in this buffer")
            if slot.object_position is not None:
                objects.add(slot.object_position)
            if slot.class_position is not None:
                classes.add(slot.class_position)
            if slot.kind == "object":
                spans.append((slot.offset - rec.offset + rootfile.MAP_OFFSET,
                              slot.end - rec.offset + rootfile.MAP_OFFSET))

    # -- StreamerInfo.md 13 and ElementTypes.md 11 --------------------------
    # The element subclasses that can be written; TStreamerArtificial cannot.
    ELEMENT_CLASSES = {
        "TStreamerBase", "TStreamerBasicType", "TStreamerBasicPointer",
        "TStreamerLoop", "TStreamerObject", "TStreamerObjectAny",
        "TStreamerObjectPointer", "TStreamerObjectAnyPointer", "TStreamerString",
        "TStreamerSTL", "TStreamerSTLstring",
    }
    # Codes that never reach a file, per ElementTypes.md 1.
    FORBIDDEN_TYPES = {10, 70, 71, 300, 365, 600, 1000, 1001, 1002, 99997, 99999, -2, -3}

    def _on_disk_type(self, t: int) -> bool:
        # 521 is kStreamLoop + kOffsetL, `T *m[d]; //[n]`. ElementTypes.md 8.2.
        if t == -1 or t in (500, 501, 521):
            return True
        if t in self.FORBIDDEN_TYPES:
            return False
        # scalars and bases, plus the kOffsetL and kOffsetP families
        if 0 <= t <= 19 or 20 <= t <= 39 or 40 <= t <= 59:
            return True
        return 61 <= t <= 69 or t in (81, 82, 85, 86, 87)

    def check_streamer_info(self) -> None:
        rec = next((r for r in self.records
                    if not r.free and r.name == "StreamerInfo"), None)
        if rec is None:
            return
        if rec.class_name != "TList":
            self.bad("StreamerInfo 13.1",
                     f"StreamerInfo key has fClassName {rec.class_name!r}, not 'TList'")
        if self.header.seek_info != rec.offset:
            self.bad("StreamerInfo 13.1",
                     f"fSeekInfo {self.header.seek_info} != record offset {rec.offset}")
        if self.header.nbytes_info != rec.nbytes:
            self.bad("StreamerInfo 13.1",
                     f"fNbytesInfo {self.header.nbytes_info} != fNbytes {rec.nbytes}")
        _, _, infos = self.streamer_infos()
        if infos is None:
            return

        by_name = {i.name: i for i in infos}
        all_by_name: dict[str, list] = {}
        for i in infos:
            all_by_name.setdefault(i.name, []).append(i)
        seen: set[tuple[str, int]] = set()
        for si in infos:
            if not si.name:
                self.bad("StreamerInfo 13.3", "an info has an empty fName")
            if si.class_version < 0:
                self.bad("StreamerInfo 13.3",
                         f"{si.name}: fClassVersion {si.class_version} is negative")
            # 13.4: version 1 may repeat with a different checksum; nothing else may.
            key = (si.name, si.class_version)
            if key in seen and si.class_version != 1:
                self.bad("StreamerInfo 13.4",
                         f"{si.name}: two infos share fClassVersion {si.class_version}")
            seen.add(key)

            names = {e.name for e in si.elements}
            for e in si.elements:
                where = f"{si.name}.{e.name}"
                if e.cls not in self.ELEMENT_CLASSES:
                    self.bad("StreamerInfo 13.5", f"{where}: element class {e.cls}")
                # No ROOT release writes 300 or 365 here, back to 3.04: the two
                # g4tools files that do are in gen/foreign/IGNORE.toml.
                # ElementTypes.md 11, StreamerInfo.md 10.1.
                if not self._on_disk_type(e.ftype):
                    self.bad("ElementTypes 11.1",
                             f"{where}: fType {e.ftype} is not an on-disk code")
                if e.ftype in self.FORBIDDEN_TYPES:
                    self.bad("ElementTypes 11.2",
                             f"{where}: fType {e.ftype} cannot occur on disk")

                if e.cls == "TStreamerBase":
                    # 13.8
                    if e.type_name != "BASE":
                        self.bad("StreamerInfo 13.8",
                                 f"{where}: fTypeName {e.type_name!r}, expected 'BASE'")
                    if e.ftype not in (0, 66, 67, -1):
                        self.bad("StreamerInfo 13.8",
                                 f"{where}: base fType {e.ftype}")
                    # 13.7: fBaseCheckSum, which is fMaxIndex[1], read unsigned.
                    # 0 means "not recorded": the field did not exist before
                    # ROOT 6, and is 0 whenever the writer had no base class
                    # loaded. StreamerInfo.md 9.1.
                    #
                    # "the base info" is any info for that class in the file: a
                    # file may hold several at different versions, and
                    # fBaseCheckSum identifies a layout (StreamerInfo.md 9.2).
                    # Comparing only against the one by_name kept failed a base
                    # element naming another (PLAN-corpus.md C5).
                    targets = all_by_name.get(e.name, [])
                    if (targets and e.base_checksum
                            and all(t.checksum != e.base_checksum for t in targets)):
                        have = ", ".join(f"0x{t.checksum:08x}" for t in targets)
                        self.bad("StreamerInfo 13.7",
                                 f"{where}: fMaxIndex[1] 0x{e.base_checksum:08x} "
                                 f"matches no {e.name} info in the file ({have})")
                    # There is no invariant on fBaseVersion. It records the base
                    # version the *derived* class's info was built against, which
                    # need not be the version of the base's own info in the same
                    # file: five files in the two corpora disagree, and all five
                    # are correct (StreamerInfo.md 9.2).
                    # ElementTypes 11.6: -1 only for a suppressed TObject base
                    if e.ftype == -1 and e.name != "TObject":
                        self.bad("ElementTypes 11.6",
                                 f"{where}: fType -1 on a base named {e.name!r}")

                # 13.9: 500 on every ROOT-written file available, from 3.04
                # on. StreamerInfo.md 10.1.
                if (e.cls in ("TStreamerSTL", "TStreamerSTLstring")
                        and e.ftype != 500):
                    self.bad("StreamerInfo 13.9",
                             f"{where}: STL element fType {e.ftype}, expected 500")

                if e.cls in ("TStreamerBasicPointer", "TStreamerLoop"):
                    counter = e.tail.get("fCountName", "")
                    if not counter:
                        self.bad("StreamerInfo 13.10", f"{where}: empty fCountName")
                    else:
                        # It may be in a base class, which fCountClass names.
                        owner = by_name.get(e.tail.get("fCountClass", ""))
                        elsewhere = owner is not None and any(
                            x.name == counter for x in owner.elements)
                        if counter not in names and not elsewhere:
                            self.bad("StreamerInfo 13.10",
                                     f"{where}: fCountName {counter!r} is in "
                                     f"neither {si.name} nor "
                                     f"{e.tail.get('fCountClass', '')!r}")

                # 13.11
                if not 0 <= e.array_dim <= 5:
                    self.bad("StreamerInfo 13.11", f"{where}: fArrayDim {e.array_dim}")
                elif e.array_dim > 0:
                    # No exemption for STL elements: the ones ROOT stored
                    # wrongly before 6.24/02 have fArrayDim 0, which this
                    # clause does not test (StreamerInfo.md 13).
                    extents = e.max_index[:e.array_dim]
                    product = 1
                    for x in extents:
                        product *= x
                    if any(x <= 0 for x in extents):
                        self.bad("StreamerInfo 13.11",
                                 f"{where}: fArrayDim {e.array_dim} but extents "
                                 f"{extents} are not all positive")
                    elif product != e.array_length:
                        self.bad("StreamerInfo 13.11",
                                 f"{where}: fMaxIndex product {product} != "
                                 f"fArrayLength {e.array_length}")

                # ElementTypes 11.8
                if e.has_range and e.ftype % 20 not in (9, 19):
                    self.bad("ElementTypes 11.8",
                             f"{where}: kHasRange set on fType {e.ftype}")

                # 11.3. 500 is the two STL element classes; 501 is TStreamerLoop.
                # The published entry omitted TStreamerLoop, the only class that
                # ever has 501.
                if e.ftype in (500, 300, 365) and e.cls not in (
                        "TStreamerSTL", "TStreamerSTLstring"):
                    self.bad("ElementTypes 11.3",
                             f"{where}: fType {e.ftype} on a {e.cls}")
                elif e.ftype in (501, 521) and e.cls != "TStreamerLoop":
                    self.bad("ElementTypes 11.3",
                             f"{where}: fType {e.ftype} on a {e.cls}, not a "
                             f"TStreamerLoop")
                # 11.4. fArrayLength is the fixed extent: positive for a
                # kOffsetL code, and 0 for a kOffsetP one, whose length is its
                # counter's. The published invariant claimed positive for all of
                # [20, 59], which 2229 elements contradict. The only
                # scalar-looking exception is an object pointer, which declares a
                # fixed array with fArrayLength and no kOffsetL
                # (ElementTypes.md 7).
                if ((20 <= e.ftype <= 39 or e.ftype in (81, 82, 85, 86, 87, 521))
                        and e.array_length <= 0):
                    self.bad("ElementTypes 11.4",
                             f"{where}: kOffsetL fType {e.ftype} with fArrayLength "
                             f"{e.array_length}")
                elif e.ftype == 501 and e.array_length != 0:
                    self.bad("ElementTypes 11.4",
                             f"{where}: kStreamLoop carries fArrayLength "
                             f"{e.array_length}")
                elif 40 <= e.ftype <= 59 and e.array_length != 0:
                    self.bad("ElementTypes 11.4",
                             f"{where}: kOffsetP fType {e.ftype} carries "
                             f"fArrayLength {e.array_length}; the counter supplies "
                             f"the length")
                elif (1 <= e.ftype <= 19 or e.ftype in (61, 62, 65, 66, 67)) \
                        and e.array_length != 0:
                    self.bad("ElementTypes 11.4",
                             f"{where}: scalar fType {e.ftype} with fArrayLength "
                             f"{e.array_length}")
                # 11.5
                if 40 <= e.ftype <= 59:
                    if e.cls != "TStreamerBasicPointer":
                        self.bad("ElementTypes 11.5",
                                 f"{where}: fType {e.ftype} on a {e.cls}")
                    elif not e.tail.get("fCountName"):
                        self.bad("ElementTypes 11.5",
                                 f"{where}: fType {e.ftype} names no counter")
                # 11.7
                if e.ftype in (66, 67) and e.cls != "TStreamerBase" \
                        and rootfile._bare_class(e.type_name) not in ("TObject", "TNamed"):
                    self.bad("ElementTypes 11.7",
                             f"{where}: fType {e.ftype} on a {e.cls} of type "
                             f"{e.type_name!r}")

    # -- StreamerDriven.md 10 -----------------------------------------------
    def check_streamer_driven(self) -> None:
        """StreamerDriven.md invariants 1-6: applying the streamer info to a
        record's object data consumes exactly its length, and to a nested object
        exactly its byte count.

        Records whose class has a hand-written Streamer are reported as skipped
        rather than as failures: that divergence is StreamerDriven.md section 7
        and is the subject of spec/03-classes/.
        """
        _, _, infos = self.streamer_infos()
        if infos is None:
            return
        by_info = {i.name: i for i in infos}
        described = set(by_info)

        for info in infos:
            for where, message in element_list_failures(info, by_info):
                self.bad(where, message)
            for where, message in undescribed_classes(info, described):
                self.bad(where, message)

        for target in self.records:
            if target.free:
                continue
            if target.class_name in ("TFile", "TDirectory", "TDirectoryFile"):
                continue
            data = self.data(target)
            if data is None:
                continue
            try:
                value = rootfile.decode_record(data, target, infos,
                                               self.header.version)
            except rootfile.UnsupportedClass:
                continue    # a hand-written Streamer; StreamerDriven.md 7
            except (rootfile.FormatError, struct.error,
                    IndexError, ValueError) as exc:
                # A record may need a class known to diverge that is not
                # specified. Report the gap rather than the symptom.
                needed = self.needs_unspecified_streamer(data, target)
                if needed is not None:
                    self.no_codec.add(
                        f"{needed}: {self.UNSPECIFIED_STREAMERS[needed]}")
                    continue
                self.bad("StreamerDriven 10.1",
                         f"{target.class_name} {target.name!r} at "
                         f"{target.offset}: {exc}")
                continue
            # Buffer.md 9.10: ROOT writes TObject::IsA()'s version, which has
            # been 1 at every release. A reading that finds anything else here
            # has taken a version word for a TObject or the reverse, the only
            # mistake StreamerDriven.md 7.1 leaves a reader to make.
            for v in rootfile.walk(value):
                if v.tobject is not None and v.tobject.version != 1:
                    self.bad("Buffer 9.10",
                             f"{target.class_name} {target.name!r} at "
                             f"{target.offset}: a TObject base at "
                             f"{v.start} has version word {v.tobject.version}")
                    break

    def check_references(self) -> None:
        """References.md invariants 1 to 6."""
        processes: dict[int, object] = {}
        for rec in self.records:
            if rec.free or rec.class_name != "TProcessID":
                continue
            if not rec.name.startswith("ProcessID") or not rec.name[9:].isdigit():
                self.bad("References 8.2",
                         f"a TProcessID record is keyed {rec.name!r}, which is not "
                         f"'ProcessID' followed by a decimal integer")
                continue
            processes[int(rec.name[9:])] = rec

        titles: dict[str, int] = {}
        for index, rec in sorted(processes.items()):
            data = self.data(rec)
            if data is None:
                continue
            start, _ = rootfile.payload_range(rec)
            frame = rootfile.read_frame(data, start)
            name, title, _, _ = rootfile._skip_named(data, frame.body)
            if len(title) != 36:
                self.bad("References 8.3",
                         f"ProcessID{index} fTitle is {len(title)} characters, not 36")
            if title != rec.title:
                self.bad("References 8.3",
                         f"ProcessID{index} fTitle {title!r} != key title {rec.title!r}")
            if title in titles:
                self.bad("References 8.4",
                         f"ProcessID{index} and ProcessID{titles[title]} share the "
                         f"UUID {title!r}")
            titles[title] = index

        def process_exists(pidf: int, rec) -> bool:
            return (pidf + rec.pid_offset) in processes

        for rec in self.records:
            if rec.free:
                continue
            data = self.data(rec)
            if data is None:
                continue

            if rec.class_name == "TRef":
                start, end = rootfile.payload_range(rec)
                bits = rootfile._u32(data, start + 6)
                if bits & rootfile.HAS_UUID:
                    # References 3.1: the trailing u16 is a counted string, so
                    # the payload is not 12 bytes and there is no pidf.
                    ref = rootfile.read_ref(data, start)
                    if ref.end != end:
                        self.bad("References 8.7",
                                 f"kHasUUID TRef at {rec.offset} ends at "
                                 f"{ref.end}, payload ends at {end}")
                elif rec.obj_len != 12:
                    self.bad("References 8.7",
                             f"TRef payload at {rec.offset} is {rec.obj_len} bytes, "
                             f"not 12")
                else:
                    ref = rootfile.read_ref(data, start)
                    if not process_exists(ref.pidf, rec):
                        self.bad("References 8.2",
                                 f"TRef at {rec.offset} names pidf {ref.pidf}, and no "
                                 f"ProcessID{ref.pidf + rec.pid_offset} record exists")

            if rec.class_name == "TRefArray":
                start, end = rootfile.payload_range(rec)
                arr = rootfile.read_ref_array(data, start)
                if arr.nobjects < 0:
                    self.bad("References 8.5",
                             f"TRefArray at {rec.offset} has nobjects {arr.nobjects}")
                elif arr.end != end:
                    self.bad("References 8.5",
                             f"TRefArray at {rec.offset} ends at {arr.end}, payload "
                             f"ends at {end}")
                else:
                    # The published arithmetic itself, not only consumption:
                    # until 2026-09-24 the formula omitted the byte count and
                    # version word, and nothing evaluated it.
                    name = len(arr.name.encode("latin-1"))
                    expected = (4 + 2 + (12 if arr.tobject.referenced else 10)
                                + (1 if name < 255 else 5) + name
                                + 4 + 4 + 2 + 4 * arr.nobjects)
                    if expected != end - start:
                        self.bad("References 8.5",
                                 f"TRefArray at {rec.offset} has a {end - start}-byte "
                                 f"payload, and the formula gives {expected}")
                if not process_exists(arr.pidf, rec):
                    self.bad("References 8.2",
                             f"TRefArray at {rec.offset} names pidf {arr.pidf}, and "
                             f"no ProcessID{arr.pidf + rec.pid_offset} record exists")

        # 8.6, over every TObject base the streamer-driven read reached.
        #
        # 8.1 (kIsReferenced makes the base 12 bytes rather than 10) is not
        # checked here, because read_tobject derives the length from the bit and
        # comparing the two would be vacuous. StreamerDriven 10.1/10.2 check it
        # instead: mis-reading the length desynchronises the enclosing object and
        # its byte count catches it. Confirmed by clearing
        # kIsReferenced on serialization/references, which reports
        # "TObjString v1 consumed 11 bytes, byte count says 14".
        _, _, infos = self.streamer_infos()
        if infos is None:
            return
        for rec in self.records:
            if rec.free:
                continue
            if rec.class_name in ("TFile", "TDirectory", "TDirectoryFile", "TRef"):
                continue
            data = self.data(rec)
            if data is None:
                continue
            try:
                tree = rootfile.decode_record(data, rec, infos)
            except (rootfile.UnsupportedClass, rootfile.FormatError,
                    struct.error, IndexError, ValueError):
                continue
            for value in rootfile.walk(tree):
                base = value.tobject
                if base is None:
                    continue
                if not base.referenced:
                    continue
                if base.unique_id >> 24:
                    self.bad("References 8.6",
                             f"referenced object at {value.start} has fUniqueID "
                             f"{base.unique_id:#010x}, whose top byte is not zero")
                if not process_exists(base.pidf, rec):
                    self.bad("References 8.2",
                             f"object at {value.start} names pidf {base.pidf}, and "
                             f"no ProcessID{base.pidf + rec.pid_offset} record exists")

    def check_schema_evolution(self) -> None:
        """SchemaEvolution.md invariants 1 to 5."""
        data, rec, infos = self.streamer_infos()
        if infos is None:
            return
        try:
            entries = rootfile.read_streamer_info_entries(data, rec)
        except (rootfile.FormatError, struct.error, IndexError, ValueError) as exc:
            self.bad("SchemaEvolution 9.3", f"could not walk the list: {exc}")
            return

        rule_lists = 0
        for cls, slot in entries:
            if cls == "TStreamerInfo":
                continue
            if cls != "TList":
                self.bad("SchemaEvolution 9.3",
                         f"the StreamerInfo list holds a {cls}, which is neither a "
                         f"TStreamerInfo nor a listOfRules")
                continue
            try:
                name, rules = rootfile.read_rule_list(data, rec, slot)
            except (rootfile.FormatError, struct.error, IndexError,
                    ValueError) as exc:
                self.bad("SchemaEvolution 9.4", f"nested TList at {slot.offset}: {exc}")
                continue
            if name != "listOfRules":
                self.bad("SchemaEvolution 9.3",
                         f"the StreamerInfo list holds a TList named {name!r}, "
                         f"not 'listOfRules'")
                continue
            rule_lists += 1
            for text in rules:
                if not text.startswith(("type=read ", "type=readraw ")):
                    self.bad("SchemaEvolution 9.5",
                             f"a rule begins {text[:20]!r}, not with a type= token")
        if rule_lists > 1:
            self.bad("SchemaEvolution 9.4",
                     f"{rule_lists} listOfRules entries; at most one is expected")

        for where, message in info_list_failures(infos):
            self.bad(where, message)

        # StreamerInfo 13.2 and SchemaEvolution 9.2 are the same claim in two
        # documents: the outer list holds infos and at most one listOfRules.
        data, rec, _ = self.streamer_infos()
        try:
            entries = rootfile.read_streamer_info_entries(data, rec)
        except (rootfile.FormatError, struct.error, IndexError, ValueError):
            entries = []
        rules = 0
        for cls, slot in entries:
            if cls == "TStreamerInfo":
                continue
            if cls == "TList":
                name = rootfile.read_rule_list(data, rec, slot)[0]
                if name != "listOfRules":
                    for label in ("StreamerInfo 13.2", "SchemaEvolution 9.2"):
                        self.bad(label, f"a TList entry named {name!r}, not "
                                        f"'listOfRules'")
                else:
                    rules += 1
                continue
            for label in ("StreamerInfo 13.2", "SchemaEvolution 9.2"):
                self.bad(label, f"an entry of class {cls}")
        if rules > 1:
            self.bad("SchemaEvolution 9.3", f"{rules} listOfRules entries")

    def check_collections(self) -> None:
        """Collections.md invariants 1, 2, 3, 4 and 6.

        Invariant 5 is StreamerDriven 10.2 applied inside a collection, and is
        checked by decode_record.
        """
        _, _, infos = self.streamer_infos()
        if infos is None:
            return
        known = {i.name for i in infos}

        for info in infos:
            for where, message in this_element_failures(info):
                self.bad(where, message)
            for el in info.elements:
                if el.cls not in ("TStreamerSTL", "TStreamerSTLstring"):
                    continue
                stl = el.tail.get("fSTLtype", 0)
                # kOffsetP is added for a pointer member, but only to a
                # container code; 300 and 365 stand alone.
                bare = stl - rootfile.OFFSET_P if 40 <= stl <= 54 else stl
                if not (0 <= bare <= 14 or bare in (300, 365)):
                    self.bad("Collections 14.1",
                             f"{info.name}.{el.name} has fSTLtype {stl}")
                if el.cls == "TStreamerSTLstring":
                    if (stl, el.tail.get("fCtype")) != (365, 365):
                        self.bad("Collections 14.2",
                                 f"{info.name}.{el.name} is a TStreamerSTLstring "
                                 f"with fSTLtype {stl} and fCtype "
                                 f"{el.tail.get('fCtype')}, not 365 and 365")
                elif (el.name == "This"
                      and not rootfile.is_collection_name(el.type_name)):
                    # 14.10 does not apply: the fSTLtype is the proxy's and the
                    # type name is not a container name. Collections.md 11.2.
                    pass
                elif bare not in (300, 365):
                    # 14.10. Checked on the value a reader ends up with, so it
                    # fails on a reader that skips the set/multimap repair of
                    # section 1; that is how the repair was found to be needed.
                    try:
                        want = rootfile.stl_kind(el.type_name)
                    except rootfile.UnsupportedClass:
                        self.no_codec.add(
                            f"{el.type_name} is not a container name this "
                            f"specification knows (Collections.md 1)")
                        continue
                    if (bare != want
                            and self.header.root_version < STL_KIND_FROM_NAME_SINCE
                            and (bare, want) in LEGACY_STL_KINDS):
                        continue
                    if bare != want:
                        self.bad("Collections 14.10",
                                 f"{info.name}.{el.name} has fSTLtype {stl}, but "
                                 f"its fTypeName {el.type_name!r} is container "
                                 f"{want}")

        for target in self.records:
            if target.free:
                continue
            if target.class_name in ("TFile", "TDirectory", "TDirectoryFile"):
                continue
            data = self.data(target)
            if data is None:
                continue

            # 14.7. 14.8 (the body matches the encoding fBits selects) is
            # checked through consumption, by decode_record below: reading the
            # wrong encoding desynchronises and the byte count catches it.
            # Confirmed by flipping kBypassStreamer on a copy of
            # serialization/clones-array.
            if target.class_name == "TClonesArray":
                start, _ = rootfile.payload_range(target)
                frame = rootfile.read_frame(data, start)
                pos = frame.body
                if frame.version > 2:
                    pos = rootfile.read_tobject(data, pos).end
                if frame.version > 1:
                    _, pos = rootfile._counted_string(data, pos)
                spec, _ = rootfile._counted_string(data, pos)
                cls, _, text = spec.partition(";")
                match = next((i for i in infos if i.name == cls), None)
                if match is None:
                    self.bad("Collections 14.7",
                             f"TClonesArray at {target.offset} names element class "
                             f"{spec!r}, and {cls!r} has no streamer info here")
                elif text.lstrip("-").isdigit() and match.class_version != int(text):
                    self.bad("Collections 14.7",
                             f"TClonesArray at {target.offset} names {spec!r}, but "
                             f"{cls}'s streamer info has version "
                             f"{match.class_version}")

            try:
                decoder, _ = rootfile.decode_record_verbose(data, target, infos)
            except (rootfile.UnsupportedClass, rootfile.FormatError,
                    struct.error, IndexError, ValueError):
                continue
            for name, value, offset, collections in decoder.member_wise:
                frame = rootfile.read_frame(data, offset)
                if frame.version > 10:
                    self.bad("Collections 14.3",
                             f"{name} has version word {frame.version}, above "
                             f"TStreamerInfo's current class version")
                if (rootfile.is_collection_name(value)
                        or value in ("string", "std::string", "TString")
                        or value.endswith("*")):
                    self.bad("Collections 14.4",
                             f"{name} is member-wise but its value class "
                             f"{value!r} is one CanSplit refuses")
                # A value class may be named in another spelling than its info
                # (StreamerInfo.md 7.3): resolved from the name, or by the
                # decoder from the checksum in the frame.
                if (not value.startswith("pair<") and value not in known
                        and not decoder.aliases.get(value)
                        and rootfile.recorded_class_name(value, known) is None):
                    self.bad("Collections 14.6",
                             f"{name} is a member-wise collection of {value!r}, "
                             f"which has no streamer info in this file")

                # 9. An empty member-wise collection writes no columns at all.
                # Read from the bytes rather than through the decoder, so the
                # rule is checked independently of the reader that implements
                # it. A fixed array shares one frame (Collections.md 11.1), so
                # the frame holds that many counts; the check applies when
                # every one of them is 0, since a non-empty collection's
                # columns cannot be measured without decoding them.
                if frame.end is None:
                    continue
                pos = frame.body
                if rootfile._i16(data, pos) > 0:
                    pos += 2                      # a plain value-class version
                else:
                    pos += 6                      # version 0 and a checksum
                if frame.version <= rootfile.Decoder.EMPTY_WRITES_NO_COLUMNS_ABOVE:
                    continue
                empty = 0
                while (empty < collections and pos + 4 <= frame.end
                       and rootfile._i32(data, pos) == 0):
                    empty += 1
                    pos += 4
                if empty == collections and pos != frame.end:
                    self.bad("Collections 14.9",
                             f"{name} holds 0 elements but runs {frame.end - pos} "
                             f"bytes past its count")

    def check_tarray(self) -> None:
        """TArray.md invariants 1 and 3.

        Invariant 2 (a TArray occupies 4 + fN * width) is checked through the
        enclosing object's byte count by the streamer-driven read, since a
        TArray has no byte count of its own to check against. Confirmed by
        shortening the fN of TH1L's TArrayL64 base on a copy of
        serialization/version-zero, which then reports "TH1L v0 consumed 544
        bytes, byte count says 552".

        Nothing here checks the recorded streamer info of TArray.md section 2: no
        reference file contains one, so the check would pass vacuously.
        """
        for rec in self.records:
            if rec.free or rec.class_name not in rootfile.TARRAY_WIDTH:
                continue
            data = self.data(rec)
            if data is None:
                continue
            start, _ = rootfile.payload_range(rec)
            count = struct.unpack_from(">i", data, start)[0]
            if count < 0:
                self.bad("TArray 5.1",
                         f"{rec.class_name} at {rec.offset} has fN {count}")
                continue
            want = 4 + count * rootfile.TARRAY_WIDTH[rec.class_name]
            if rec.obj_len != want:
                self.bad("TArray 5.3",
                         f"{rec.class_name} at {rec.offset} has fObjlen "
                         f"{rec.obj_len}, but fN {count} needs {want}")

    #: Formula.md 1. The current class version of each, and the threshold at
    #: which the class behind the name changes.
    FORMULA_CURRENT = {"TF1": 12, "TFormula": 14}
    FORMULA_NEW_FROM = {"TF1": 8, "TFormula": 9}

    #: WritingHistograms.md 10. The number of axes each histogram class counts
    #: cells in; every axis past that has exactly one bin. The TH1x, TH2x and
    #: TH3x families follow from the name; TH2Poly, TH1K and TProfile's
    #: relatives outside this map are not described here and are skipped.
    HIST_DIMENSION = {"TProfile": 1, "TProfile2D": 2, "TProfile3D": 3}

    #: The concrete element letters a THnx class name can end in.
    HIST_LETTERS = "CSILFD"

    def hist_dimension(self, name: str) -> int | None:
        if name in self.HIST_DIMENSION:
            return self.HIST_DIMENSION[name]
        if (len(name) == 4 and name.startswith("TH") and name[2] in "123"
                and name[3] in self.HIST_LETTERS):
            return int(name[2])
        return None

    def check_histogram(self) -> None:
        """WritingHistograms.md invariants 1, 2, 3, 4, 6, 8 and 9.

        The shape checks a histogram record must satisfy whatever wrote it. They
        are the same at every TH1 version because they are all about *lengths*:
        fNcells against the axes, the TArray base and fSumw2 against fNcells,
        fXbins against fNbins. A member a legacy version lacks is absent from
        the decoded tree and skipped.

        Invariant 5 is not here: whether every weight was 1 cannot be recovered
        from a record, so a check of `fTsumw <= fEntries` would be wrong for
        every weighted histogram ROOT has ever written. 7 is
        `tools/check_versions.py`.

        Confirmed by corrupting data/written/th2-profile.root, twelve fields one
        at a time. Five land here: fNcells 20 -> 19 gives "TH2F at 286 has
        fNcells 19, but its axes (3, 2 bins) need 20", the Y axis's fNbins gives
        the same check from the other side, fZaxis.fNbins 1 -> 2 gives 10.4,
        fBufferSize 0 -> 4 gives 10.6, a moved fXbins edge gives 10.3, and
        fErrorMode 4 and an inverted Y range give 10.9. The other array lengths
        desynchronise the decode before reaching here (shortening the TArrayF
        base reports "TH2F v4 consumed 807 bytes, byte count says 811"), so the
        length checks only catch a file whose byte count agrees with its wrong
        length, which is what a faulty *writer* produces.
        """
        for rec in self.records:
            if rec.free:
                continue
            dim = self.hist_dimension(rec.class_name)
            if dim is None:
                continue
            data = self.data(rec)
            if data is None:
                continue
            _, _, infos = self.streamer_infos()
            if infos is None:
                self.skip("WritingHistograms 10.1", "no StreamerInfo record",
                          unit="record")
                continue
            try:
                hist = rootfile.decode_record(data, rec, infos)
            except rootfile.UnsupportedClass as exc:
                self.skip("WritingHistograms 10.1", str(exc), unit="record")
                continue
            except (rootfile.FormatError, struct.error, IndexError) as exc:
                self.bad("WritingHistograms 10.1",
                         f"{rec.class_name} at {rec.offset}: {exc}")
                continue
            self.check_hist_shape(data, rec, hist, dim)

    def check_graphs(self) -> None:
        """The Invariants of `spec/06-writing/WritingGraphs.md` 6.

        The obvious check is circular: `rootfile.py` derives each counted
        array's extent *from* `fNpoints`, so comparing the two can never fail.
        The part of invariant 1 that can fail is the flag byte (a value other
        than 0 or 1, or a 0 with points to write) plus `fNpoints >= 0`. The
        "exactly `fNpoints` values" half is enforced one layer down, by the byte
        count, as `StreamerDriven` 10.1.

        Confirmed by corrupting `data/written/graph.root`: a flag byte of 7 gives
        "fX's flag byte is 7, not 0 or 1", and an inverted pair gives invariant 2.
        `fNpoints` 4 -> 3 and 4 -> -1 desynchronise the decode first ("TGraph
        v5 consumed 229 bytes, byte count says 192"), the same division of labour
        the histogram checks have.
        """
        _, _, infos = self.streamer_infos()
        if infos is None:
            return
        for rec in self.records:
            if rec.free or not rec.key_len:
                continue
            if not rootfile.derives_from(infos, rec.class_name or "", "TGraph"):
                continue
            data = self.data(rec)
            if data is None:
                continue
            try:
                value = rootfile.decode_record(data, rec, infos)
            except rootfile.UnsupportedClass as exc:
                self.skip("WritingGraphs 6.1", str(exc), unit="record")
                continue
            except (rootfile.FormatError, struct.error, IndexError) as exc:
                self.bad("WritingGraphs 6.1",
                         f"{rec.class_name} at {rec.offset}: {exc}")
                continue
            self.check_graph_shape(data, rec, value)

    def check_graph_shape(self, data, rec, value) -> None:
        where = f"{rec.class_name} at {rec.offset}"
        by_name = {v.name: v for v in rootfile.walk(value)}
        if "fNpoints" not in by_name:
            self.skip("WritingGraphs 6.1",
                      f"{rec.class_name}: no fNpoints in the decoded record",
                      unit="record")
            return
        npoints = self._i32(data, by_name["fNpoints"])
        if npoints < 0:
            self.bad("WritingGraphs 6.1", f"{where}: fNpoints {npoints}")
            return
        # Invariant 1's flag byte, over every counted array in the record,
        # whichever class declared it: a TGraphErrors' fEX and fEY have the same
        # shape, and so do the four arrays of a TGraphAsymmErrors.
        for name in ("fX", "fY", "fEX", "fEY", "fEXlow", "fEXhigh", "fEYlow",
                     "fEYhigh"):
            member = by_name.get(name)
            if member is None:
                continue
            present = data[member.start]
            if present not in (0, 1):
                self.bad("WritingGraphs 6.1",
                         f"{where}: {name}'s flag byte is {present}, not 0 or 1")
            elif not present and npoints:
                self.bad("WritingGraphs 6.1",
                         f"{where}: {name} is null though fNpoints is {npoints}")
        # Invariant 2.
        lo, hi = by_name.get("fMinimum"), by_name.get("fMaximum")
        if lo is not None and hi is not None:
            low, high = self._f64(data, lo), self._f64(data, hi)
            if low > high:
                self.bad("WritingGraphs 6.2",
                         f"{where}: fMinimum {low} above fMaximum {high}")

    def _i32(self, data: bytes, value) -> int:
        return struct.unpack_from(">i", data, value.start)[0]

    def _f64(self, data: bytes, value) -> float:
        return struct.unpack_from(">d", data, value.start)[0]

    def _array_len(self, data: bytes, value) -> int:
        """`fN` of a `TArrayD`/`TArrayF`, member or base: its first four bytes."""
        return self._i32(data, value)

    def check_hist_shape(self, data, rec, hist, dim: int) -> None:
        where = f"{rec.class_name} at {rec.offset}"
        th1 = next((v for v in rootfile.walk(hist) if v.name == "TH1"), None)
        if th1 is None or not th1.members:
            self.skip("WritingHistograms 10.1",
                      f"{rec.class_name}: no TH1 base in the decoded record",
                      unit="record")
            return
        by_name = {m.name: m for m in th1.members}
        if "fNcells" not in by_name:
            self.skip("WritingHistograms 10.1",
                      f"{rec.class_name}: TH1 records no fNcells",
                      unit="record")
            return
        ncells = self._i32(data, by_name["fNcells"])

        # Invariants 1, 3 and 4, over the three axes.
        want, nbins = 1, []
        for i, name in enumerate(("fXaxis", "fYaxis", "fZaxis")):
            axis = by_name.get(name)
            if axis is None or not axis.members:
                self.bad("WritingHistograms 10.4",
                         f"{where} has no {name}")
                return
            fields = {m.name: m for m in axis.members}
            n = self._i32(data, fields["fNbins"])
            nbins.append(n)
            if i < dim:
                want *= n + 2
            elif n != 1:
                self.bad("WritingHistograms 10.4",
                         f"{where} is {dim}-dimensional but {name} has "
                         f"fNbins {n}, not 1")
            edges = fields.get("fXbins")
            if edges is not None:
                count = self._array_len(data, edges)
                if count not in (0, n + 1):
                    self.bad("WritingHistograms 10.3",
                             f"{where}: {name}.fXbins has {count} edges, "
                             f"expected 0 or {n + 1}")
                elif count:
                    first = struct.unpack_from(">d", data, edges.start + 4)[0]
                    last = struct.unpack_from(">d", data,
                                              edges.start + 4 + 8 * (count - 1))[0]
                    lo = self._f64(data, fields["fXmin"])
                    hi = self._f64(data, fields["fXmax"])
                    if (first, last) != (lo, hi):
                        self.bad("WritingHistograms 10.3",
                                 f"{where}: {name}.fXbins runs {first} to "
                                 f"{last}, but fXmin/fXmax are {lo}/{hi}")
        if ncells != want:
            self.bad("WritingHistograms 10.1",
                     f"{where} has fNcells {ncells}, but its axes "
                     f"({', '.join(str(n) for n in nbins[:dim])} bins) "
                     f"need {want}")

        # Invariant 1's second half: the TArray base holds one value per cell.
        base = next((v for v in rootfile.walk(hist)
                     if v.name in rootfile.TARRAY_WIDTH), None)
        if base is not None:
            count = self._array_len(data, base)
            if count != ncells:
                self.bad("WritingHistograms 10.1",
                         f"{where}: the {base.name} base has fN {count}, "
                         f"not fNcells {ncells}")

        # Invariant 2.
        sumw2 = by_name.get("fSumw2")
        if sumw2 is not None:
            count = self._array_len(data, sumw2)
            if count not in (0, ncells):
                self.bad("WritingHistograms 10.2",
                         f"{where}: fSumw2 has {count} entries, expected 0 "
                         f"or fNcells {ncells}")

        # Invariant 6.
        size, buffer = by_name.get("fBufferSize"), by_name.get("fBuffer")
        if size is not None and buffer is not None:
            declared = self._i32(data, size)
            flag = data[buffer.start]
            if (declared == 0) != (flag == 0):
                self.bad("WritingHistograms 10.6",
                         f"{where}: fBufferSize {declared} with fBuffer flag "
                         f"byte {flag}")

        if rec.class_name in self.HIST_DIMENSION:
            self.check_profile(data, rec, hist, ncells, where)

    #: WritingHistograms.md 8.4: kERRORMEAN, kERRORSPREAD, kERRORSPREADI and
    #: kERRORSPREADG (`root/hist/hist/inc/TProfile.h:28`).
    ERROR_MODES = (0, 1, 2, 3)

    def check_profile(self, data, rec, hist, ncells: int, where: str) -> None:
        """WritingHistograms.md invariants 8 and 9, for the TProfile family."""
        by_name = {m.name: m for m in hist.members or ()}
        th1 = next((v for v in rootfile.walk(hist) if v.name == "TH1"), None)
        th1_by_name = {m.name: m for m in (th1.members or ())} if th1 else {}
        entries = by_name.get("fBinEntries")
        if entries is not None and self._array_len(data, entries) != ncells:
            self.bad("WritingHistograms 10.8",
                     f"{where}: fBinEntries has "
                     f"{self._array_len(data, entries)} entries, not fNcells "
                     f"{ncells}")
        sumw2 = th1_by_name.get("fSumw2")
        if sumw2 is not None and self._array_len(data, sumw2) != ncells:
            self.bad("WritingHistograms 10.8",
                     f"{where}: a profile's fSumw2 holds sum(w*y*y) and is "
                     f"never empty, but it has "
                     f"{self._array_len(data, sumw2)} entries, not {ncells}")
        binsumw2 = by_name.get("fBinSumw2")
        if binsumw2 is not None:
            count = self._array_len(data, binsumw2)
            if count not in (0, ncells):
                self.bad("WritingHistograms 10.2",
                         f"{where}: fBinSumw2 has {count} entries, expected 0 "
                         f"or fNcells {ncells}")
        mode = by_name.get("fErrorMode")
        if mode is not None:
            value = self._i32(data, mode)
            if value not in self.ERROR_MODES:
                self.bad("WritingHistograms 10.9",
                         f"{where}: fErrorMode {value} is not one of "
                         f"{self.ERROR_MODES}")
        lo, hi = by_name.get("fYmin"), by_name.get("fYmax")
        if lo is not None and hi is not None:
            ymin, ymax = self._f64(data, lo), self._f64(data, hi)
            if not ymin <= ymax:
                self.bad("WritingHistograms 10.9",
                         f"{where}: fYmin {ymin} is above fYmax {ymax}")

    def check_canvas(self) -> None:
        """Canvas.md invariants 1 to 3.

        Invariants 1 and 2 are consumption checks: read_tcanvas raises when the
        fields do not exhaust the byte count, and the TVirtualPad frame inside it
        can only balance if the TQObject base occupies nothing. Confirmed by
        making read_object treat TQObject as an ordinary framed object on a copy
        of classes/canvas, which reports "version word 0 for TAttCanvas with
        checksum 0x0".
        """
        for rec in self.records:
            if rec.free or rec.class_name != "TCanvas":
                continue
            data = self.data(rec)
            if data is None:
                continue
            _, _, infos = self.streamer_infos()
            if infos is None:
                self.skip("Canvas 5.1", "no StreamerInfo record", unit="record")
                continue
            start, _ = rootfile.payload_range(rec)
            version = rootfile.read_frame(data, start).version
            if not 1 <= version <= 8:
                self.bad("Canvas 5.1",
                         f"TCanvas at {rec.offset} has version {version}, "
                         f"outside 1 to 8")
                continue
            try:
                canvas = rootfile.decode_record(data, rec, infos)
            except rootfile.UnsupportedClass as exc:
                self.skip("Canvas 5.1", str(exc), unit="record")
                continue
            except (rootfile.FormatError, struct.error, IndexError) as exc:
                self.bad("Canvas 5.1", f"TCanvas at {rec.offset}: {exc}")
                continue
            by_name = {m.name: m for m in canvas.members}
            pad = by_name.get("TPad")
            if pad is not None:
                virtual = next((m for m in (pad.members or [])
                                if m.name == "TVirtualPad"), None)
                qobject = next((m for m in (virtual.members or [])
                                if m.name == "TQObject"), None) if virtual else None
                if qobject is not None and qobject.end != qobject.start:
                    self.bad("Canvas 5.2",
                             f"TQObject base at {qobject.start} occupies "
                             f"{qobject.end - qobject.start} bytes, not 0")
            for name, lowest in (("fCw", 1), ("fCh", 1),
                                 ("fHighLightColor", 0)):
                member = by_name.get(name)
                if member is None:
                    continue
                width = member.end - member.start
                fmt = ">H" if width == 2 else ">I"
                value = struct.unpack_from(fmt, data, member.start)[0]
                if width == 2:
                    value = struct.unpack_from(">h", data, member.start)[0]
                if value < lowest:
                    self.bad("Canvas 5.3",
                             f"TCanvas at {rec.offset} has {name} {value}")

    def check_matrix(self) -> None:
        """Matrix.md invariants 1 to 7.

        Invariants 4 and 5 matter most: the bytes past the byte count are one
        element per stored position, so the object is longer than its own byte
        count by that much. They catch a reader that treats `TMatrixTSym` as an
        ordinary delegating class, since such a reader stops at the byte count
        and reports nothing.

        Confirmed by corrupting a copy of `classes/matrix`, one field at a time:
        the version word (5.1), `fNcols` and `fNelems` (5.2), `fNrowIndex`
        (5.3), the byte count and `fNrows` (5.4, where the element span no
        longer reaches the end of the payload). Invariant 6 is the exception:
        no corruption can add a streamer info under a longer name than the one
        that is there, so it is checked but not corruption-tested.
        """
        _, _, infos = self.streamer_infos()
        for rec in self.records:
            if rec.free or not rec.class_name:
                continue
            cls = rec.class_name
            symmetric = cls.startswith("TMatrixTSym<")
            ordinary = (cls.startswith("TMatrixT<")
                        or cls.startswith("TVectorT<"))
            if not (symmetric or ordinary):
                continue
            if infos is None:
                self.skip("Matrix 5.1", "no StreamerInfo record", unit="record")
                continue
            names = {i.name for i in infos}
            if cls in names and symmetric:
                # Invariant 6. Nothing writes such an info; if one appears it
                # describes a layout the bytes do not follow.
                self.bad("Matrix 5.6",
                         f"the file carries a streamer info for {cls}, which "
                         f"ROOT never records")
            data = self.data(rec)
            if data is None:
                continue
            start, _ = rootfile.payload_range(rec)
            try:
                frame = rootfile.read_frame(data, start)
                value = rootfile.decode_record(data, rec, infos)
            except rootfile.UnsupportedClass as exc:
                self.skip("Matrix 5.1", str(exc), unit="record")
                continue
            except (rootfile.FormatError, struct.error, IndexError) as exc:
                # For a symmetric matrix the frame itself is ordinary, so a
                # failure here is the element span: either it does not reach the
                # end of the payload or it runs past the buffer. Reported as 5.4
                # rather than as a generic decode failure.
                self.bad("Matrix 5.4" if symmetric else "Matrix 5.7",
                         f"{cls} at {rec.offset}: {exc}")
                continue
            payload_end = rec.offset + rec.nbytes if data is self.buf else None
            if not symmetric:
                # Invariant 7: an ordinary member of the family ends where its
                # byte count says.
                if frame.end is not None and value.end != frame.end:
                    self.bad("Matrix 5.7",
                             f"{cls} at {rec.offset} consumed to {value.end}, "
                             f"byte count ends at {frame.end}")
                continue
            element = rootfile.template_args(cls)[0]
            width = rootfile.SCALAR_WIDTH[rootfile.FUNDAMENTAL[element]]
            base = f"TMatrixTBase<{element}>"
            versions = {i.class_version for i in infos if i.name == base}
            if not versions:
                self.skip("Matrix 5.1", f"no streamer info for {base}", unit="record")
                continue
            if frame.version != max(versions):
                # Invariant 1. A version word that is not the base's current one
                # is either an older file (legitimate, and then the file has an
                # info at that version) or a misread frame.
                if frame.version not in versions:
                    self.bad("Matrix 5.1",
                             f"{cls} at {rec.offset} has version word "
                             f"{frame.version}, and no {base} info in this file "
                             f"has that class version")
            shape = {m.name: m for m in value.members}
            rows = rootfile._int_member(data, shape["fNrows"])
            cols = rootfile._int_member(data, shape["fNcols"])
            nelems = rootfile._int_member(data, shape["fNelems"])
            row_index = rootfile._int_member(data, shape["fNrowIndex"])
            if rows != cols:
                self.bad("Matrix 5.2",
                         f"{cls} at {rec.offset} has fNrows {rows} and fNcols "
                         f"{cols}; a symmetric matrix is square")
            elif nelems != rows * cols:
                self.bad("Matrix 5.2",
                         f"{cls} at {rec.offset} has fNelems {nelems}, not "
                         f"fNrows*fNcols = {rows * cols}")
            if row_index != 0:
                self.bad("Matrix 5.3",
                         f"{cls} at {rec.offset} has fNrowIndex {row_index}, "
                         f"which only a sparse matrix carries")
            if frame.end is None:
                self.bad("Matrix 5.5", f"{cls} at {rec.offset} has no byte count")
                continue
            stored = rows * (rows + 1) // 2
            if value.end - frame.end != width * stored:
                self.bad("Matrix 5.4",
                         f"{cls} at {rec.offset} has {value.end - frame.end} "
                         f"bytes past its byte count, not {width * stored} for "
                         f"{stored} elements of {width}")
            if payload_end is not None and value.end != payload_end:
                # Invariant 5, for a top-level record: the object is longer than
                # its own byte count claims, by exactly the elements.
                self.bad("Matrix 5.5",
                         f"{cls} at {rec.offset} ends at {value.end}, and the "
                         f"record's payload ends at {payload_end}")

    def check_formula(self) -> None:
        """Formula.md invariants 1 to 3."""
        for rec in self.records:
            if rec.free or rec.class_name not in self.FORMULA_CURRENT:
                continue
            data = self.data(rec)
            if data is None:
                continue
            start, _ = rootfile.payload_range(rec)
            version = rootfile.read_frame(data, start).version
            if not 1 <= version <= self.FORMULA_CURRENT[rec.class_name]:
                self.bad("Formula 6.1",
                         f"{rec.class_name} at {rec.offset} has version "
                         f"{version}, outside 1 to "
                         f"{self.FORMULA_CURRENT[rec.class_name]}")

        _, _, infos = self.streamer_infos()
        for info in infos or []:
            if info.name not in self.FORMULA_CURRENT:
                continue
            new = info.class_version >= self.FORMULA_NEW_FROM[info.name]
            names = {el.name for el in info.elements}
            where = f"{info.name} v{info.class_version}"
            if info.name == "TF1":
                first = info.elements[0] if info.elements else None
                if first is None:
                    self.bad("Formula 6.2", f"{where} has no elements")
                elif new and not (first.ftype == 67 and first.name == "TNamed"):
                    self.bad("Formula 6.2",
                             f"{where} begins with {first.name} at code "
                             f"{first.ftype}, not TNamed at 67")
                elif not new and not (first.ftype == 0
                                      and first.name == "TFormula"):
                    self.bad("Formula 6.2",
                             f"{where} begins with {first.name} at code "
                             f"{first.ftype}, not a TFormula base at 0")
            else:
                old_only, new_only = "fNoper" in names, "fClingParameters" in names
                if old_only and new_only:
                    self.bad("Formula 6.3",
                             f"{where} has both fNoper and fClingParameters")
                elif new and not new_only:
                    self.bad("Formula 6.3",
                             f"{where} is the ROOT 6 class but has no "
                             f"fClingParameters")
                elif not new and not old_only:
                    self.bad("Formula 6.3",
                             f"{where} is the ROOT 5 class but has no fNoper")

    def check_containers(self) -> None:
        """Containers.md invariants 1 to 6.

        1, 2 and 6 are consumption checks and are raised by the readers in
        `rootfile` rather than computed here: a frame that does not end where its
        byte count says is a FormatError. Confirmed by lowering the fTally of a
        copy of classes/containers, which reports "TExMap at 546 consumed 52
        bytes, byte count says 136".
        """
        for rec in self.records:
            if rec.free or rec.class_name not in ("TMap", "TExMap", "TBtree"):
                continue
            data = self.data(rec)
            if data is None:
                continue
            try:
                if rec.class_name == "TMap":
                    rootfile.read_tmap(data, rec)
                elif rec.class_name == "TExMap":
                    self._check_exmap(rootfile.read_texmap(data, rec), rec)
                else:
                    self._check_btree(rootfile.read_tbtree(data, rec), rec)
            except rootfile.FormatError as exc:
                label = {"TMap": "Containers 7.1", "TExMap": "Containers 7.2",
                         "TBtree": "Containers 7.6"}[rec.class_name]
                self.bad(label, f"{rec.class_name} at {rec.offset}: {exc}")

    def _check_exmap(self, exmap, rec) -> None:
        """Containers.md invariant 3."""
        where = f"TExMap at {rec.offset}"
        if not 0 <= exmap.tally <= exmap.size:
            self.bad("Containers 7.3",
                     f"{where} has fTally {exmap.tally}, fSize {exmap.size}")
            return
        previous = -1
        for slot, hash_, _, _ in exmap.records:
            if not 0 <= slot < exmap.size:
                self.bad("Containers 7.3",
                         f"{where} has slot {slot} outside [0, {exmap.size})")
            if slot <= previous:
                self.bad("Containers 7.3",
                         f"{where} has slot {slot} after {previous}: the write "
                         f"loop walks the table in order")
            previous = slot
            if not hash_ & 1:
                self.bad("Containers 7.3",
                         f"{where} has even hash {hash_} in slot {slot}: "
                         f"SetHash forces bit 0 to mark the slot in use")

    def _check_btree(self, btree, rec) -> None:
        """Containers.md invariants 4 and 5."""
        where = f"TBtree at {rec.offset}"
        if btree.order < 3:
            self.bad("Containers 7.5", f"{where} has fOrder {btree.order}")
        for name, got, want in (
                ("fOrder2", btree.order2, 2 * (btree.order + 1)),
                ("fLeafMaxIndex", btree.leaf_max, btree.order2 - 1),
                ("fInnerMaxIndex", btree.inner_max, btree.order),
                ("fLeafLowWaterMark", btree.leaf_low, btree.leaf_max // 2 - 1),
                ("fInnerLowWaterMark", btree.inner_low, (btree.order - 1) // 2)):
            if got != want:
                self.bad("Containers 7.4",
                         f"{where} has {name} {got}, but fOrder {btree.order} "
                         f"gives {want}")

    #: The five RooFit classes of spec/03-classes/RooFit.md 1 with a Streamer of
    #: their own. RooLinkedList is the one with no byte count of its own.
    ROOFIT_CLASSES = ("RooRealVar", "RooLinkedList", "RooAbsBinning",
                      "RooRefArray", "RooCategory")

    def check_roofit(self) -> None:
        """RooFit.md invariants 1 to 5.

        The five classes are mostly reached as members rather than as records,
        so every record is decoded and its value tree walked. Invariant 1 is
        checked by consumption: rootfile.py's readers raise when an object does
        not end where its byte count says, and the failure is attributed here
        rather than to StreamerDriven 10.1 when the class is one of these.
        """
        _, _, infos = self.streamer_infos()
        if infos is None:
            return

        # Invariant 5. The info is in the file whenever any class reaches
        # RooLinkedList through the generated path, and it always lists a member
        # the Streamer never writes.
        for info in infos:
            if info.name != "RooLinkedList":
                continue
            if not any(e.name == "_hashThresh" for e in info.elements):
                self.bad("RooFit 7.5",
                         f"the RooLinkedList info at class version "
                         f"{info.class_version} does not list _hashThresh")

        for rec in self.records:
            if rec.free or not rec.class_name:
                continue
            if rec.class_name in ("TFile", "TDirectory", "TDirectoryFile"):
                continue
            data = self.data(rec)
            if data is None:
                continue
            try:
                tree = rootfile.decode_record(data, rec, infos)
            except rootfile.UnsupportedClass:
                continue
            except (rootfile.FormatError, struct.error,
                    IndexError, ValueError) as exc:
                label = self.roofit_label(rec, exc)
                if label is not None:
                    self.bad(label, f"{rec.class_name} {rec.name!r} at "
                                    f"{rec.offset}: {exc}")
                continue
            _, payload_end = rootfile.payload_range(rec)
            for value in rootfile.walk(tree):
                cls = self.roofit_class(value)
                if cls is not None:
                    self.check_roofit_object(data, value, cls, payload_end)

    #: How a decode failure is attributed to an invariant. Each reader in
    #: rootfile.py raises with the class name first, so the message names the
    #: class that failed. The failure may be nested several objects deep; the
    #: innermost class named is the one whose rule was violated.
    ROOFIT_LABELS = (("RooLinkedList", "RooFit 7.2"),
                     ("RooRefArray", "RooFit 7.3"),
                     ("RooAbsBinning", "RooFit 7.4"))

    def roofit_label(self, rec, exc) -> str | None:
        """Which RooFit invariant a decode failure belongs to, or None."""
        message = str(exc)
        for cls, label in self.ROOFIT_LABELS:
            if cls in message:
                return label
        if rec.class_name in self.ROOFIT_CLASSES:
            return "RooFit 7.1"
        return None

    @staticmethod
    def roofit_class(value) -> str | None:
        """Which of RooFit.md 1's classes this Value is, or None.

        A base class has its name in `name` and the literal "BASE" in
        `type_name`, which is how RooAbsBinning and RooCategory are reached;
        a member or a record has the class in `type_name`.
        """
        for name in (value.type_name, value.name):
            if name in Checker.ROOFIT_CLASSES:
                return name
        return None

    def check_roofit_object(self, data, value, cls: str,
                            payload_end: int) -> None:
        """RooFit.md invariants 1 to 4, on one decoded object."""
        if cls != "RooLinkedList":
            # Invariant 1, the byte-count half. RooLinkedList has none.
            frame = rootfile.read_frame(data, value.start)
            if frame.end is None:
                self.bad("RooFit 7.1",
                         f"{cls} at {value.start} has no byte count")
                return
            if value.end != frame.end:
                self.bad("RooFit 7.1",
                         f"{cls} at {value.start} consumed to {value.end}, "
                         f"byte count ends at {frame.end}")
        members = value.members or []
        if cls == "RooLinkedList":
            # Invariant 2.
            size = next((m for m in members if m.name == "_size"), None)
            if size is None:
                self.bad("RooFit 7.2",
                         f"RooLinkedList at {value.start} has no _size")
                return
            count = rootfile._int_member(data, size)
            if count < 0:
                self.bad("RooFit 7.2",
                         f"RooLinkedList at {value.start} has _size {count}")
            slots = [m for m in members if m.name == "element"]
            if len(slots) != max(count, 0):
                self.bad("RooFit 7.2",
                         f"RooLinkedList at {value.start} says _size {count} "
                         f"and holds {len(slots)} slot(s)")
            if slots and slots[-1].end > payload_end:
                self.bad("RooFit 7.2",
                         f"RooLinkedList at {value.start}: its last slot ends "
                         f"at {slots[-1].end}, past the payload at {payload_end}")
        elif cls == "RooRefArray":
            # Invariant 3.
            inner = [m for m in members if m.type_name == "TRefArray"]
            if len(inner) != 1:
                self.bad("RooFit 7.3",
                         f"RooRefArray at {value.start} holds {len(inner)} "
                         f"TRefArray(s), not one")
            elif inner[0].end != value.end:
                self.bad("RooFit 7.3",
                         f"RooRefArray at {value.start}: the TRefArray ends at "
                         f"{inner[0].end}, the byte count at {value.end}")
        elif cls == "RooAbsBinning":
            # Invariant 4.
            version = rootfile.read_frame(data, value.start).version
            want = "TObject" if version == 1 else "TNamed"
            names = [m.name for m in members]
            if names != [want, "RooPrintable"]:
                self.bad("RooFit 7.4",
                         f"RooAbsBinning v{version} at {value.start} holds "
                         f"{names}, not ['{want}', 'RooPrintable']")
            elif members[1].end - members[1].start != 6:
                self.bad("RooFit 7.4",
                         f"RooAbsBinning at {value.start}: its RooPrintable is "
                         f"{members[1].end - members[1].start} bytes, not 6")

    def check_basket(self) -> None:
        """TBasket.md invariants."""
        for rec in self.records:
            if rec.free or rec.class_name != "TBasket":
                continue
            data = self.data(rec)
            if data is None:
                continue
            try:
                basket = rootfile.read_basket(self.buf, rec, data)
            except (rootfile.FormatError, struct.error, IndexError,
                    ValueError) as exc:
                self.bad("TBasket 9.1", str(exc))
                continue

            # 9.2 cannot be corruption-tested in isolation: lowering the key
            # version shifts fSeekKey and fSeekPdir by 8 bytes, so the record
            # chain and the class name break first and the file is rejected by
            # Record 8.1/8.3/8.6 before reaching here.
            #
            # TBasket.md 1: the `fVersion += 1000` in TBasket's constructor
            # arrives in ROOT 4.02 (commit 3970c0bead, first production release
            # 4.02/00). Before it a basket key has the ordinary key version and
            # the small layout: 12385 such keys in 19 files of root/roottest/,
            # from 2.23/12 to 4.00/04. So this is a claim about what ROOT writes
            # from 4.02 on, and gating it on the writing release scopes it to
            # where it is true; rootfile.py takes every key's width from the key
            # itself either way.
            if (self.header.root_version >= BASKET_LARGE_KEY_SINCE
                    and rec.key_version <= rootfile.LARGE_KEY_VERSION):
                self.bad("TBasket 9.2",
                         f"basket at {rec.offset} has key fVersion "
                         f"{rec.key_version}, not a large-key form")
            if basket.nev_buf < 0:
                self.bad("TBasket 9.3",
                         f"basket at {rec.offset} has fNevBuf {basket.nev_buf}")
                continue
            if basket.last < rec.key_len:
                self.bad("TBasket 9.3",
                         f"basket at {rec.offset} has fLast {basket.last}, below "
                         f"fKeylen {rec.key_len}")
                continue

            tail = rec.obj_len - (basket.last - rec.key_len)
            if basket.has_offsets:
                one = 4 + 4 * (basket.nev_buf + 1)
                # One array, or two when a displacement array follows, which
                # the flag never indicates because a record basket is written
                # header-only. TBasket.md 5.3.
                want = one * (2 if basket.displacements is not None else 1)
                if tail != want:
                    self.bad("TBasket 9.4",
                             f"basket at {rec.offset} has {tail} bytes after the "
                             f"data, expected {want} for fNevBuf "
                             f"{basket.nev_buf}")
                if basket.displacements is not None:
                    moved = [d - o for o, d in
                             zip(basket.entry_offsets, basket.displacements)]
                    if len(set(moved)) != 1 or moved[0] < 0:
                        self.bad("TBasket 9.9",
                                 f"basket at {rec.offset}: displacements minus "
                                 f"offsets are {moved}, not one constant shift")
                offsets = basket.entry_offsets
                if offsets and offsets[0] != rec.key_len:
                    self.bad("TBasket 9.5",
                             f"basket at {rec.offset}: first entry offset "
                             f"{offsets[0]} != fKeylen {rec.key_len}")
                if any(b < a for a, b in zip(offsets, offsets[1:])):
                    self.bad("TBasket 9.5",
                             f"basket at {rec.offset}: entry offsets decrease")
                if offsets and offsets[-1] > basket.last:
                    self.bad("TBasket 9.5",
                             f"basket at {rec.offset}: last entry offset "
                             f"{offsets[-1]} is above fLast {basket.last}")
            else:
                if tail != 0:
                    self.bad("TBasket 9.4",
                             f"basket at {rec.offset} has {tail} unaccounted "
                             f"bytes and no offset array")
                want = basket.nev_buf * basket.nev_buf_size
                if basket.generated:
                    want = rec.obj_len      # 9.6 does not apply, TBasket.md 5.2
                if rec.obj_len != want:
                    self.bad("TBasket 9.6",
                             f"basket at {rec.offset} has fObjlen {rec.obj_len}, "
                             f"but fNevBuf {basket.nev_buf} x fNevBufSize "
                             f"{basket.nev_buf_size} is {want}")

            if basket.generated:
                # The offsets are not in the basket at all: generating them needs
                # the branch's leaf and its counter, which TBasket.md 5.2 covers
                # and this per-record check does not have.
                continue
            for index in range(basket.nev_buf):
                try:
                    start, end = rootfile.basket_entry_range(rec, basket, index)
                except rootfile.FormatError as exc:
                    self.bad("TBasket 9.7", str(exc))
                    break
                if not basket.data_start <= start <= end <= basket.data_end:
                    self.bad("TBasket 9.7",
                             f"basket at {rec.offset}: entry {index} spans "
                             f"{start}..{end}, outside {basket.data_start}.."
                             f"{basket.data_end}")

    # -- Compression.md 9 ---------------------------------------------------
    def check_raw_is_not_a_block(self, rec, data) -> None:
        """Compression 9.7: a raw payload never looks like a compression block.

        The compressed/raw decision is `fObjlen > fNbytes - fKeylen` and nothing
        else (9.1), so a raw payload that happened to begin with a plausible block
        header would make the two readings of the same record disagree. This
        checks that it does not happen.
        """
        # payload_range's start is already a file offset. Until 2026-09-22 this
        # added rec.offset to it a second time, so the check read 9 bytes at
        # twice the record's offset (another record, or past the end of the
        # file, where it returned early). It passed vacuously on every record;
        # corrupting a raw payload to open with a valid `ZL` header did not
        # trip it (PLAN-corpus.md C7).
        # An RBlob holds pages, not one object (Compression.md 9.1). A single
        # page that compression shrank by 8 bytes or less is kept compressed
        # (root/tree/ntuple/inc/ROOT/RNTupleZip.hxx:70), and its checksum then
        # makes the payload at least fObjLen, so 9.1 calls it raw although it
        # is one block.
        if rec.class_name == RBLOB_CLASS:
            return
        start, end = rootfile.payload_range(rec)
        head = data[start:start + 9]
        if len(head) < 9 or head[:2] not in BLOCK_MAGICS:
            return
        # A block header is magic, method, then two 3-byte little-endian sizes.
        stored = head[3] | head[4] << 8 | head[5] << 16
        raw = head[6] | head[7] << 8 | head[8] << 16
        if stored and raw and stored <= rec.payload_nbytes:
            self.bad("Compression 9.7",
                     f"the raw payload at {rec.offset} begins with {head[:2]!r} "
                     f"and sizes {stored}/{raw}, which a reader taking the magic "
                     f"as authoritative would decompress")

    def rblob_unchecked(self, rec) -> None:
        """Count an RBlob that Compression 9.2 and 9.3 cannot be applied to."""
        if rec.offset not in self._rblobs_unchecked:
            self._rblobs_unchecked.add(rec.offset)
            self.skip("Compression 9.2 and 9.3", RBLOB_MULTIPAGE, unit="RBlob")

    def check_compression(self) -> None:
        for rec in self.records:
            if rec.free:
                continue
            payload, end = rec.payload_offset, rec.offset + rec.nbytes
            if rec.obj_len <= rec.payload_nbytes:
                # Stored raw, 9.1's first branch: Compression.md 1.1.
                self.check_raw_is_not_a_block(rec, self.buf)
                continue

            produced, o, blocks, unreadable = 0, payload, 0, False
            sizes: list[int] = []       # each block's declared uncompressed size
            while o < end:
                if o + 9 > end:
                    self.bad("Compression 9.2", f"truncated block header at {o}")
                    break
                magic = self.buf[o:o+2]
                if magic not in BLOCK_MAGICS:
                    # Inside an RBlob this is a page boundary the walk cannot
                    # place: a raw page, which may also be the first one, or a
                    # page checksum the walk reached. Placing it needs the page
                    # list. Compression.md 9.1.
                    if rec.class_name == RBLOB_CLASS:
                        self.rblob_unchecked(rec)
                        unreadable = True
                        break
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
                sizes.append(unc)
                blocks += 1
                o += 9 + comp
                if produced >= rec.obj_len:
                    break

            # Compression.md 9, "What an RBlob is not": an RBlob does not hold
            # one object. It holds one or more sealed pages, each of them
            # `blocks || optional 8-byte XXH3-64 checksum`, and the checksum is
            # appended after compression and counted outside fObjLen
            # (root/tree/ntuple/src/RPageStorage.cxx:751, and
            # kNBytesPageChecksum at
            # root/tree/ntuple/inc/ROOT/RPageStorage.hxx:74). So a sealed page's
            # chain stops 8 bytes short of the payload and 9.2 does not hold as
            # stated.
            #
            # This suspends 9.2 and 9.3 for that shape and no other. An RBlob
            # holding an envelope still satisfies both, because an envelope's
            # checksum is inside its own declared length; measured on
            # data/rntuple/compressed.root, where the three envelope blobs close
            # exactly and only the page blob is 8 bytes short. A blob holding
            # several pages cannot be checked at all without the page
            # boundaries, which live in the page list envelope; this check does
            # not consult it (rootfile.read_rn_page_list can read one since
            # 2026-09-24), so that case is reported, not passed.
            sealed = rec.class_name == RBLOB_CLASS
            if unreadable:       # already recorded by rblob_unchecked
                continue

            if produced != rec.obj_len:
                # Short of fObjLen inside an RBlob means the walk stopped at a
                # page boundary it could not place. Report that, not a
                # malformed chain.
                if sealed:
                    self.rblob_unchecked(rec)
                    continue
                self.bad("Compression 9.3",
                         f"blocks decode to {produced} bytes, fObjlen is {rec.obj_len}")
            # The blocks account for fObjLen, so the payload must now close. An
            # envelope closes flush; a sealed page closes 8 bytes early, and that
            # gap is the checksum. ROOT writes no other shape, so a chain that
            # ends anywhere else is a failure; without this the carve-out would
            # accept a corrupted page as "unverifiable".
            if o != end and not (sealed and o == end - RN_PAGE_CHECKSUM):
                self.bad("Compression 9.2",
                         f"block chain ends at {o}, payload ends at {end}")
            # 9.5: every block but the last declares exactly kMAXZIPBUF bytes.
            # This too is about one object's chain: ROOT splits a single buffer
            # at kMAXZIPBUF. An RBlob's blocks come from several pages
            # compressed independently, so their sizes follow the page size:
            # 1310 blocks against an "expected" 6 on
            # test_ntuple_storage_1col_10e6evt.root. Until 2026-09-24 this
            # compared only the block count with fObjlen, which a chain of
            # wrong sizes that still summed to fObjlen passed (PLAN-review.md
            # V42).
            if not sealed:
                for k, unc in enumerate(sizes[:-1]):
                    if unc != KMAXZIPBUF:
                        self.bad("Compression 9.5",
                                 f"block {k + 1} of {len(sizes)} in the record "
                                 f"at {rec.offset} declares {unc} bytes, not "
                                 f"0xFFFFFF")
                        break

    # -- spec/05-rntuple/: the footer and its linked attribute sets ---------
    #
    # The tracked copy is upstream's, so these have no numbered Invariants
    # entries; each label names the part of it that it checks. "Linked Attribute
    # Sets", "Linked Attribute Set Record Frame", and ERRATA 11 and 12.
    def check_rntuple(self) -> None:
        anchors = {}          # payload offset -> record, for every RNTuple anchor
        for rec in self.records:
            if not rec.free and rec.class_name == "ROOT::RNTuple":
                anchors[rootfile.payload_range(rec)[0]] = rec
        for rec in anchors.values():
            if self.data(rec) is None:
                continue
            try:
                anchor = rootfile.read_rntuple_anchor(self.buf, rec)
                schema = rootfile.read_rntuple_header(self.buf, anchor)
                footer = rootfile.read_rntuple_footer(self.buf, anchor, schema)
            except rootfile.MissingCodec as exc:
                self.no_codec.add(f"some records were not decompressed: {exc}")
                self.skip("RNTuple footer", f"its codec is missing: {exc}",
                          unit="RNTuple")
                continue
            except (rootfile.FormatError, struct.error, IndexError,
                    ValueError, UnicodeDecodeError) as exc:
                self.bad("RNTuple footer", f"{rec.name!r} at {rec.offset}: {exc}")
                continue
            where = f"RNTuple {rec.name!r} at {rec.offset}"
            # ERRATA 11: the list exists from format 1.0.1.0 on and is absent
            # before it. ROOT's reader tolerates the absence, and so must any
            # reader of an older file (RNTupleSerialize.cxx:2015-2017).
            version = (anchor.epoch, anchor.major, anchor.minor, anchor.patch)
            if footer.attribute_sets is None and version >= (1, 0, 1, 0):
                self.bad("RNTuple footer, attribute set list",
                         f"{where}: format {anchor.version} has no attribute "
                         f"set list after the cluster groups")
            self.check_attribute_sets(where, footer.attribute_sets or [], anchors)

    def check_attribute_sets(self, where, links, anchors) -> None:
        names = [link.name for link in links]
        for link in links:
            here = f"{where}, attribute set {link.name!r}"
            # "All linked attribute sets must have a non-empty, distinct name."
            if not link.name:
                self.bad("RNTuple attribute set, name", f"{here}: the name is empty")
            if names.count(link.name) > 1 and names.index(link.name) == links.index(link):
                self.bad("RNTuple attribute set, name",
                         f"{here}: {names.count(link.name)} sets have this name")
            # The locator points at the anchor OBJECT, the payload of an
            # RNTuple anchor key, and its size is that payload's on-disk size;
            # the record's length is the object's uncompressed length, the
            # key's fObjLen (root/tree/ntuple/src/RMiniFile.cxx:1359-1369). That
            # is the whole object, byte count and class version included
            # (ERRATA 12), which read_rntuple_anchor_at enforces in turn: it
            # refuses a length other than the byte count plus 12.
            loc = link.locator
            target = anchors.get(loc.offset) if loc.kind in ("file", "large") else None
            if target is None:
                self.bad("RNTuple attribute set, locator",
                         f"{here}: a {loc.kind} locator to {loc.offset}, which is "
                         f"not the payload of an RNTuple anchor in this file")
                continue
            if loc.nbytes != target.payload_nbytes or link.anchor_length != target.obj_len:
                self.bad("RNTuple attribute set, locator",
                         f"{here}: the locator says {loc.nbytes} bytes and the "
                         f"record {link.anchor_length} uncompressed; the anchor at "
                         f"{target.offset} has {target.payload_nbytes} and "
                         f"{target.obj_len}")
            try:
                aset = rootfile.read_attribute_set(self.buf, link)
            except rootfile.MissingCodec as exc:
                self.no_codec.add(f"some records were not decompressed: {exc}")
                self.skip("RNTuple attribute set", f"its codec is missing: {exc}",
                          unit="attribute set")
                continue
            except (rootfile.FormatError, struct.error, IndexError,
                    ValueError, UnicodeDecodeError) as exc:
                self.bad("RNTuple attribute set, locator",
                         f"{here}: the linked RNTuple does not read: {exc}")
                continue
            fields = aset.schema.fields + aset.footer.extension_fields
            # Restriction 1: no linked attribute RNTuples of its own.
            if aset.footer.attribute_sets:
                self.bad("RNTuple attribute set, restriction 1",
                         f"{here}: it links {len(aset.footer.attribute_sets)} "
                         f"attribute set(s) of its own")
            # Restriction 2: the alias column lists of header and footer are empty.
            aliases = (len(aset.schema.alias_columns)
                       + len(aset.footer.extension_alias_columns))
            if aliases:
                self.bad("RNTuple attribute set, restriction 2",
                         f"{here}: {aliases} alias column(s)")
            # Restriction 3: no field of structural role 0x04.
            streamed = [f.name for f in fields if f.structure == 0x04]
            if streamed:
                self.bad("RNTuple attribute set, restriction 3",
                         f"{here}: streamer field(s) {streamed}")
            # "readers should refuse reading an attribute set whose Major Schema
            # Version is unknown", so a check of the fields cannot run either.
            if link.major != 1:
                self.skip("RNTuple attribute set, schema version",
                          f"major schema version {link.major} is not 1, the only "
                          f"one specified", unit="attribute set")
                continue
            top = [f for f in fields if f.parent_id == f.field_id]
            got = [(f.name, f.type_name, f.structure) for f in top]
            want = list(rootfile.RN_ATTRIBUTE_SCHEMA_1)
            # Schema 1.0 is exactly the three fields; a later minor version may
            # add optional fields, which can only come after them.
            if got[:3] != want or (link.minor == 0 and len(got) != 3):
                self.bad("RNTuple attribute set, schema version",
                         f"{here}: schema {link.major}.{link.minor} with top-level "
                         f"fields {got}, expected {want}")

    # -- Directory.md 9 -----------------------------------------------------
    def check_directories(self) -> None:
        seen_subdirs: dict[int, int] = {}
        for rec in self.records:
            d = rootfile.read_directory(self.buf, rec)
            if d is None:
                continue
            # 9.1 is what read_directory validates to identify the record.
            if d.fields_offset != rec.offset + d.nbytes_name:
                self.bad("Directory 9.2",
                         f"fields at {d.fields_offset}, but fSeekDir + fNbytesName "
                         f"is {rec.offset + d.nbytes_name}")
            if rec.offset != self.header.begin and d.nbytes_name != rec.key_len:
                self.bad("Directory 9.3",
                         f"subdirectory {rec.name!r}: fNbytesName {d.nbytes_name} "
                         f"!= fKeylen {rec.key_len}")
            # TFile::Init range-checks the top directory's only
            # (TFile.cxx:841); a subdirectory's is its fKeylen (9.3), which a
            # long title can take past 10000.
            if rec.offset == self.header.begin and not 10 <= d.nbytes_name <= 10000:
                self.bad("Directory 9.4", f"fNbytesName {d.nbytes_name} outside [10, 10000]")
            if rec.offset == self.header.begin:
                # FileHeader 10.3, which is ROOT's own open-time check
                # (root/io/io/src/TFile.cxx:781-788): the root directory's fields
                # must fit before fEND, or nothing can be read at all.
                after = d.fields_offset + directory_payload_length(
                    d.version, self.header.version)
                if after > self.header.end:
                    self.bad("FileHeader 10.3",
                             f"the root directory record ends at {after}, past "
                             f"fEND {self.header.end}")
            # LargeFiles.md 8.7: TDirectoryFile::FillBuffer widens on the
            # record's own three offsets and nothing else
            # (root/io/io/src/TDirectoryFile.cxx:751-759).
            offsets = (d.seek_dir, d.seek_parent, d.seek_keys)
            if (d.version > 1000) != (max(offsets) > 2000000000):
                self.bad("LargeFiles 8.7",
                         f"directory record at {rec.offset} has version "
                         f"{d.version} and offsets {offsets}")
            if not 1 <= d.version % 1000 <= 5:
                self.bad("Directory 9.9", f"directory version {d.version}")
            else:
                # 9.15. The class version and the offset width are independent
                # axes (Directory.md 3.1), so the payload length depends on both,
                # and on the file version for the reserved bytes.
                want = directory_payload_length(d.version, self.header.version)
                got = rec.obj_len - (d.nbytes_name - rec.key_len)
                if got != want:
                    self.bad("Directory 9.15",
                             f"payload is {got} bytes, but version {d.version} in "
                             f"a file at fVersion {self.header.version} writes "
                             f"{want}")
            if d.datime_c > d.datime_m:
                self.bad("Directory 9.10",
                         f"fDatimeC {d.datime_c} > fDatimeM {d.datime_m}")

            if not d.seek_keys:
                if d.nbytes_keys:
                    self.bad("Directory 9.5",
                             f"fSeekKeys is 0 but fNbytesKeys is {d.nbytes_keys}")
                continue
            klist = self.at(d.seek_keys)
            if klist is None or klist.nbytes != d.nbytes_keys:
                got = "no record" if klist is None else klist.nbytes
                self.bad("Directory 9.5",
                         f"fNbytesKeys {d.nbytes_keys} != fNbytes at fSeekKeys ({got})")
                continue
            # 9.12. The only link from a key-list record back to its directory:
            # its key names the owning directory, which distinguishes it from the
            # directory record it otherwise looks exactly like.
            if klist.seek_pdir != d.seek_dir:
                self.bad("Directory 9.12",
                         f"the key-list record at {klist.offset} has fSeekPdir "
                         f"{klist.seek_pdir}, not the owning directory's "
                         f"fSeekDir {d.seek_dir}")
            try:
                entries = rootfile.read_key_list(self.buf, d)
            except rootfile.FormatError as exc:
                self.bad("Directory 9.6", str(exc))
                continue
            # The images, measured by what they occupy. fKeylen describes the
            # *record*, and Directory.md 6.5 explains why that is not always the
            # same number.
            consumed = 4 + sum(e.image_len for e in entries)
            if consumed > klist.obj_len:
                self.bad("Directory 9.6",
                         f"key list needs {consumed} bytes, fObjlen is {klist.obj_len}")
            elif klist.obj_len - consumed > 8:
                self.bad("Directory 9.6",
                         f"key list leaves {klist.obj_len - consumed} unused bytes, at most 8 expected")
            for e in entries:
                if self.at(e.seek_key) is None:
                    self.bad("Directory 9.7",
                             f"key list entry {e.name!r} points at {e.seek_key}, not a record")
                if e.seek_pdir != d.seek_dir:
                    self.bad("Directory 9.7",
                             f"entry {e.name!r} fSeekPdir {e.seek_pdir} != "
                             f"containing fSeekDir {d.seek_dir}")
                # 9.11: the image frames the read, and ROOT never cross-checks it
                # against the record's own key. ROOT does not notice a
                # disagreement; other readers fail on it.
                rec_at = self.at(e.seek_key)
                if rec_at is not None:
                    # A directory key has two spellings of one class name and
                    # ROOT normalises on read (TKey::ReadKeyBuffer), so the
                    # comparison must too (Directory.md 6.5).
                    for field, listed, actual in (
                            ("fNbytes", e.nbytes, rec_at.nbytes),
                            ("fObjlen", e.obj_len, rec_at.obj_len),
                            ("fKeylen", e.key_len, rec_at.key_len),
                            ("fCycle", e.cycle, rec_at.cycle),
                            ("fClassName", _dir_spelling(e.class_name),
                             _dir_spelling(rec_at.class_name)),
                            ("fName", e.name, rec_at.name),
                            ("fTitle", e.title, rec_at.title)):
                        if listed != actual:
                            self.bad("Directory 9.11",
                                     f"key list entry {e.name!r}: {field} {listed!r} "
                                     f"!= {actual!r} in the record at {e.seek_key}")
                    # 9.13. An image is a byte copy of the record's key in every
                    # file but one shape: a directory key written before ROOT
                    # 5.34 spells itself TDirectoryFile in the list, four bytes
                    # longer than the fKeylen it still reports.
                    if e.image_len != e.key_len:
                        legacy = (e.class_name == "TDirectoryFile"
                                  and rec_at.class_name == "TDirectory"
                                  and e.image_len - e.key_len == LEGACY_DIR_SLACK)
                        if not legacy:
                            self.bad("Directory 9.13",
                                     f"key list entry {e.name!r} occupies "
                                     f"{e.image_len} bytes but reports fKeylen "
                                     f"{e.key_len}")
                if e.class_name in ("TDirectory", "TDirectoryFile"):
                    if e.seek_key in seen_subdirs:
                        self.bad("Directory 9.8",
                                 f"subdirectory at {e.seek_key} listed in two parents")
                    seen_subdirs[e.seek_key] = d.seek_dir

            # 9.14: within a name, cycles descend and are distinct. ROOT's
            # lookups take the first match rather than the highest cycle, so the
            # order is the resolution rule (WritingFiles.md 8.1).
            runs: dict[str, list[int]] = {}
            for e in entries:
                if e.cycle == 0:
                    self.bad("Directory 9.14",
                             f"key {e.name!r} has cycle 0")
                runs.setdefault(e.name, []).append(abs(e.cycle or 0))
            for name, cycles in runs.items():
                if len(cycles) < 2:
                    continue
                if len(set(cycles)) != len(cycles):
                    self.bad("Directory 9.14",
                             f"key {name!r} has repeated cycles {cycles}")
                elif cycles != sorted(cycles, reverse=True):
                    self.bad("Directory 9.14",
                             f"key {name!r} has cycles {cycles}, not descending: "
                             f"an unqualified lookup resolves to cycle "
                             f"{cycles[0]}, not {max(cycles)}")

    # -- FreeSegments.md 8 --------------------------------------------------
    def check_free_list(self) -> None:
        if not self.header.seek_free:
            return
        segments = rootfile.read_free_segments(self.buf, self.header)
        if not segments:
            self.bad("FreeSegments 8.1", "the free list is empty")
            return

        first, last = segments[-1]
        if first != self.header.end:
            self.bad("FreeSegments 8.1",
                     f"last entry starts at {first}, fEND is {self.header.end}")
        if last <= self.header.end:
            self.bad("FreeSegments 8.2", f"last entry fLast {last} does not exceed fEND")
        if last < KSTART_BIG_FILE:
            self.bad("FreeSegments 8.2", f"last entry fLast {last} below {KSTART_BIG_FILE}")
        # TFile::Recover sets fEND + 1e9 rather than a multiple (TFile.cxx:2190).
        if (last > KSTART_BIG_FILE and last % 1000000000 != 0
                and last != self.header.end + 1000000000):
            self.bad("FreeSegments 8.2",
                     f"last entry fLast {last} is neither a multiple of 1e9 nor "
                     f"fEND + 1e9 above {KSTART_BIG_FILE}")

        previous_last = None
        for f, l in segments:
            if f > l:
                self.bad("FreeSegments 8.5", f"entry ({f}, {l}) is inverted")
            if previous_last is not None and f <= previous_last + 1:
                self.bad("FreeSegments 8.5",
                         f"entry starting {f} overlaps or abuts the previous ending {previous_last}")
            previous_last = l

        interior = [(f, l) for f, l in segments if l < self.header.end]
        # FreeSegments.md 4.2: before 6.36 RNTuple's TFile writer placed an RBlob
        # in a larger free slot and never wrote the remainder's marker. Exempt
        # only that: a gap starting where an RBlob key ends, in such a file.
        rblob_ends = ({r.offset + r.nbytes for r in self.records
                       if r.class_name == RBLOB_CLASS}
                      if self.header.root_version < RBLOB_MARKER_FIXED else set())
        for f, l in interior:
            marker = struct.unpack_from(">i", self.buf, f)[0]
            expected = -min(l - f + 1, KSTART_BIG_FILE)
            if marker != expected and f not in rblob_ends:
                self.bad("FreeSegments 8.6",
                         f"marker at {f} is {marker}, expected {expected}")

        for f, l in interior:
            # 8.10: the allocator skips a span with one, two or three bytes to
            # spare, so a remainder always has room for its own marker.
            if l - f + 1 < 4:
                self.bad("FreeSegments 8.10",
                         f"interior entry ({f}, {l}) is {l - f + 1} bytes, "
                         f"too short to hold its own marker")

        walked = {(r.offset, r.offset - r.nbytes - 1) for r in self.records if r.free}
        if set(interior) != walked:
            self.bad("FreeSegments 8.7",
                     f"interior entries {sorted(interior)} do not match the spans "
                     f"walked in the chain {sorted(walked)}")

        if self.header.end > len(self.buf):
            self.bad("FreeSegments 8.9",
                     f"fEND {self.header.end} exceeds the file size {len(self.buf)}")


    # -- TBranch.md 11 and TLeaf.md 10 --------------------------------------
    def trees(self):
        """(buffer, record, tree) for every readable tree record.

        Found by derivation rather than by class name: TNtuple and TNtupleD are
        trees too, and their records do not say "TTree". TTree.md 1.
        """
        _, _, infos = self.streamer_infos()
        if infos is None:
            return
        for rec in self.records:
            if rec.free or not rec.key_len:
                continue
            if not rootfile.derives_from(infos, rec.class_name or "", "TTree"):
                continue
            data = self.data(rec)
            if data is None:
                continue
            try:
                value = rootfile.decode_record(data, rec, infos)
                yield data, rec, rootfile.read_tree(data, value, rec.offset)
            except rootfile.UnsupportedClass as exc:
                # A layout this specification does not cover, such as a legacy
                # TBranch. Not a failure of the file.
                self.no_codec.add(str(exc))
            except (rootfile.FormatError, struct.error, IndexError,
                    ValueError, KeyError) as exc:
                self.bad("TBranch 11.1", f"tree at {rec.offset}: {exc}")

    def basket_record(self, seek: int):
        if self._by_offset is None:
            self._by_offset = {r.offset: r for r in self.records if not r.free}
        return self._by_offset.get(seek)

    def check_branches(self) -> None:
        found = list(self.trees())
        self._all_branches = [tree.branches for _, _, tree in found]
        for data, rec, tree in found:
            self.check_tree(data, rec, tree)
            self.check_auxiliary(data, rec, tree)
            top = tree.branches
            leaves = []
            for b in rootfile.walk_branches(top):
                for lf in b.leaves:
                    leaves.append(lf)
                    if lf.counter is not None:
                        # A counter leaf whose only full copy is inside this
                        # leaf's fLeafCount. TLeaf.md 3.1.
                        leaves.append(lf.counter)
            by_slot = {b.slot: b for b in rootfile.walk_branches(top)}
            # An embedded basket lives in this record's payload, and the counter
            # lookup below needs it. TBranch.md 5.
            self._tree_payload = data
            _, _, infos = self.streamer_infos()
            reader = rootfile.TreeReader(self.buf, tree, infos or [],
                                         self.fetch_basket, custom=self.custom,
                                         tree_payload=data,
                                         file_version=self.header.version)
            for branch in rootfile.walk_branches(top):
                self.check_branch(data, branch)
                self.check_branch_element(branch, by_slot)
                self.check_splitting(branch, by_slot)
                self.check_reading(branch, by_slot)
                self.check_leaves(data, branch, leaves)
                self.check_entry_decode(reader, branch)

    def fetch_basket(self, seek: int):
        """(record, decompressed buffer) for the basket at `seek`, for a
        TreeReader. None when the record is missing or its codec is not here."""
        rec = self.basket_record(seek)
        if rec is None or rec.class_name != "TBasket":
            return None
        payload = self.data(rec)
        return None if payload is None else (rec, payload)

    def branch_baskets(self, br, tree_payload):
        """Every basket of `br` that holds entries, in slot order.

        Yields `(slot, record, payload, basket, why)`. When the basket can be
        had, `why` is None; otherwise the other three are None and `why` says
        what stopped it, for a SKIPPED line. The one enumeration every entry
        check uses, so that none of them can see a basket another misses.

        An embedded basket is read out of `tree_payload`, the TTree record it
        was streamed into, with its raw block standing in for a record offset
        (TBranch.md 5, TBasket.md 4.1). The slot is consulted before
        fBasketSeek, as ROOT does (root/tree/tree/src/TBranch.cxx:1234-1236)
        and as rootfile.TreeReader does. A slot holding no entries, embedded or
        not, is not a basket anything could check and is not yielded.
        """
        for i in range(min(br.write_basket + 1, len(br.basket_seek))):
            if i in br.embedded_errors:
                # A failure too (TBasket 9.1, check_branch); skipped here
                # so that it stays in the ENTRIES denominator.
                yield i, None, None, None, ("an fBaskets slot holds an object "
                                            "that does not parse as a basket")
                continue
            emb = br.embedded.get(i)
            if emb is not None:
                if not emb.basket.nev_buf:
                    continue
                if br.file_name:
                    # In this file, but a counter it needs may not be: this
                    # checker resolves every fBasketSeek in this file.
                    yield i, None, None, None, (
                        "an embedded basket of a branch whose other baskets "
                        "are in another file, fFileName: not decoded")
                    continue
                if emb.block < 0 or tree_payload is None:
                    yield i, None, None, None, ("an embedded basket with "
                                                "entries but no buffer")
                    continue
                rec = rootfile.Record(offset=emb.block, nbytes=0,
                                      key_len=emb.key_len)
                yield i, rec, tree_payload, emb.basket, None
                continue
            if not br.basket_seek[i]:
                if i < br.write_basket:
                    # TBranch 11.5 reports it as a failure of the branch.
                    yield i, None, None, None, ("the slot has neither a basket "
                                                "record nor an embedded basket")
                continue
            if br.file_name:
                yield i, None, None, None, ("the basket is in another file, "
                                            "fFileName (TBranch.md 9)")
                continue
            rec = self.basket_record(br.basket_seek[i])
            if rec is None or rec.class_name != "TBasket":
                yield i, None, None, None, "fBasketSeek names no TBasket record"
                continue
            payload = self.data(rec)
            if payload is None:
                yield i, None, None, None, (
                    "the basket record was not decompressed: "
                    + self._undecoded.get(rec.offset, "unknown reason"))
                continue
            try:
                basket = self.basket(rec, payload)
            except (rootfile.FormatError, struct.error, IndexError,
                    ValueError):
                yield i, None, None, None, "the basket record does not parse"
                continue
            if basket.nev_buf:
                yield i, rec, payload, basket, None

    @staticmethod
    def decodes_entries(br) -> bool:
        """Is `br` read by rootfile.TreeReader rather than by its leaves?

        A TBranchElement that holds data (ReadingEntries.md 2). Exactly one
        check accounts for each branch-basket in the ENTRIES line: this one,
        the leaf-driven check_entries, or the leafless path of check_leaves.
        """
        ft = br.element_type
        if ft is None:
            return False
        if ft in rootfile.INTERIOR_TYPES:
            return False
        return not (ft == 0 and br.element_id == rootfile.SPLIT_NODE_ID)

    def tally_failed(self, label: str) -> None:
        """A branch-basket whose entry check ran and failed."""
        self.failed[label] = self.failed.get(label, 0) + 1

    def check_entry_decode(self, reader, br) -> None:
        """ReadingEntries.md invariant 5: the bytes a branch's entry occupies
        equal the bytes its decoding consumes.

        It generalises the other four, and is the one a third-party reader
        should test itself against. It needs a decoder rather than a rule;
        rootfile.TreeReader is that decoder.

        Every basket of the branch is accounted for, one outcome each: checked,
        failed or skipped. A skip or a failure in one basket does not end the
        branch, so its later baskets stay in the ENTRIES ratio. The failure is
        reported once per branch, with the number of baskets it failed in.
        """
        if not self.decodes_entries(br) or br.file_name:
            return              # a branch with fFileName: check_leaves counts it
        label = "ReadingEntries 8.5"
        first, nfail = None, 0
        for i, rec, payload, basket, why in self.branch_baskets(
                br, self._tree_payload):
            if why is not None:
                self.skip(label, why)
                continue
            if basket.generated:
                self.skip(label, "basket flag 80: the entry offsets are "
                                 "generated, TBasket.md 5.2.1")
                continue
            problem = None
            for e in self.entry_sample(basket.nev_buf, rec.offset):
                entry = br.basket_entry[i] + e
                try:
                    start, end, consumed = reader.entry_end(br, entry)
                except rootfile.UnsupportedClass as exc:
                    # Not a pass: the decode could not run. Counted and named
                    # in the SKIPPED report.
                    problem = ("skip", str(exc))
                    break
                except (rootfile.FormatError, struct.error, IndexError,
                        ValueError, KeyError) as exc:
                    problem = ("fail", f"branch {br.name!r} entry {entry}: {exc}")
                    break
                if consumed != end:
                    problem = ("fail",
                               f"branch {br.name!r} entry {entry}: the basket "
                               f"gives it {end - start} bytes, decoding "
                               f"consumed {consumed - start}")
                    break
            if problem is None:
                self.verified += 1
            elif problem[0] == "skip":
                self.skip(label, problem[1])
            else:
                self.tally_failed(label)
                nfail += 1
                first = first or problem[1]
        if first is not None:
            more = f" (and {nfail - 1} more basket(s))" if nfail > 1 else ""
            self.bad(label, first + more)

    #: fType values a TBranchElement may carry. TBranchElement.md 10.1.
    ELEMENT_TYPES = {-1, 0, 1, 2, 3, 4, 31, 41}
    #: The two interior types carry no leaf; every other type carries one.
    ELEMENT_NO_LEAF = {1, 2}
    ELEMENT_ONE_LEAF = {-1, 0, 3, 4, 31, 41}
    #: On these the single leaf is always a back-reference, never written here.
    ELEMENT_LEAF_BY_REF = {3, 4}
    #: The ones whose fClonesName is set, and whose fBranchCount is.
    ELEMENT_CLONES_NAME = {3, 4}
    ELEMENT_COUNTED = {31, 41}

    def check_branch_element(self, br, by_slot) -> None:
        """The Invariants of spec/04-ttree/TBranchElement.md.

        Skipped entirely for a plain TBranch, which carries none of these
        members; `element_type` is None exactly then.
        """
        ft = br.element_type
        if ft is None:
            return
        name = f"branch {br.name!r}"

        # 1. fType is one of the eight values the dispatch accepts.
        if ft not in self.ELEMENT_TYPES:
            self.bad("TBranchElement 10.1", f"{name}: fType {ft}")
            return

        # 2. fClassName is never empty.
        if not br.class_name:
            self.bad("TBranchElement 10.2", f"{name}: fClassName is empty")

        # 3. fClassVersion is stored as an absolute value.
        if br.class_version < 0:
            self.bad("TBranchElement 10.3",
                     f"{name}: fClassVersion {br.class_version}")

        # 4. fClonesName is set exactly on the two count branch types.
        if bool(br.clones_name) != (ft in self.ELEMENT_CLONES_NAME):
            self.bad("TBranchElement 10.4",
                     f"{name}: fType {ft} with fClonesName "
                     f"{br.clones_name!r}")

        # 5. The two interior types carry no leaf; every other type carries
        #    exactly one. `leaves` already has any back-reference resolved into
        #    it, so it is the count of leaves however they were written.
        if ft in self.ELEMENT_NO_LEAF and br.leaves:
            self.bad("TBranchElement 10.5",
                     f"{name}: fType {ft} with {len(br.leaves)} leaf/leaves")
        if ft in self.ELEMENT_ONE_LEAF and len(br.leaves) != 1:
            self.bad("TBranchElement 10.5",
                     f"{name}: fType {ft} with {len(br.leaves)} leaf/leaves")

        # 5b. On a count branch with sub-branches that leaf is never written in
        #     place: it is a back-reference to the copy inside a member leaf's
        #     fLeafCount. With no sub-branch (a value class with no data
        #     members) nothing writes it first, and it is in place
        #     (ttree/split-empty-collection, PLAN-review.md V43).
        if ft in self.ELEMENT_LEAF_BY_REF and br.branches and not br.leaf_refs:
            self.bad("TBranchElement 10.5",
                     f"{name}: fType {ft} writes its leaf in full rather than "
                     f"referencing the copy in a member's fLeafCount")

        # 6. An interior node holds nothing. The empty-base branch of TBranch.md
        #    9.2 is not an interior node: it holds one object per entry, and a
        #    writer flushes its baskets like any other (TBranchElement.md 4).
        if (ft in (1, 2) and (br.write_basket or br.tot_bytes)
                and self.empty_base_info(br) is None):
            self.bad("TBranchElement 10.6",
                     f"{name}: fType {ft} with fWriteBasket "
                     f"{br.write_basket} and fTotBytes {br.tot_bytes}")

        # 7. fBranchCount is set on every member of a split container, and on
        #    nothing but those and a counted fType <= 2 member.
        if ft in self.ELEMENT_COUNTED and br.count_slot < 0:
            self.bad("TBranchElement 10.7",
                     f"{name}: fType {ft} with no fBranchCount")
        if br.count_slot >= 0 and ft not in self.ELEMENT_COUNTED and ft > 2:
            self.bad("TBranchElement 10.7",
                     f"{name}: fType {ft} with an fBranchCount")

        # 8. fID, when not a sentinel, indexes the element list of the streamer
        #    info fClassName names.
        if br.element_id is not None and br.element_id >= 0:
            info = self.element_info(br)
            if info is not None and br.element_id >= len(info.elements):
                self.bad("TBranchElement 10.8",
                         f"{name}: fID {br.element_id} past the "
                         f"{len(info.elements)} elements of {br.class_name!r}")

        # 10. fStreamerType agrees with the element fID indexes, apart from the
        #     two divergences of TBranchElement.md 5.2.
        if br.element_id is not None and br.element_id >= 0:
            info = self.element_info(br)
            if info is not None and br.element_id < len(info.elements):
                el = info.elements[br.element_id]
                want = el.ftype
                # -1 is kNoType: the branch declares no element type at all,
                # so there is nothing to compare. The other two divergences of
                # TBranchElement.md 5.2 are in-memory codes the branch sampled
                # and the element record does not carry: an STL element's
                # stored 500 against the code its read path computes
                # (kSTL or kSTLp, plus kOffsetL for an array;
                # root/core/meta/src/TStreamerElement.cxx:2124-2128), and a
                # Bool_t branch written before kBool existed, which agrees with
                # the element's stored 11 but not with the 18 its read-time
                # fixup makes of it (root/core/meta/src/TStreamerElement.cxx:566).
                stl = None
                if el.cls in ("TStreamerSTL", "TStreamerSTLstring") and want == 500:
                    stl = (71 if el.type_name.endswith("*") else 300) + (
                        20 if el.array_length > 0 else 0)
                ok = (br.streamer_type == want
                      or br.streamer_type == -1
                      or br.streamer_type == stl
                      or br.streamer_type == el.stored_ftype)
                if not ok:
                    self.bad("TBranchElement 10.10",
                             f"{name}: fStreamerType {br.streamer_type} but "
                             f"element {br.element_id} of {br.class_name!r} has "
                             f"fType {want}")

        # 9. fBranchCount refers to a count branch written earlier.
        if br.count_slot >= 0:
            target = by_slot.get(br.count_slot)
            if target is None:
                self.bad("TBranchElement 10.9",
                         f"{name}: fBranchCount at {br.count_slot} is no branch")
            elif not (target.element_type in (3, 4)
                      or (target.element_type is not None
                          and target.element_type <= 2
                          and target.streamer_type
                          in rootfile.COUNTER_TYPES)):
                self.bad("TBranchElement 10.9",
                         f"{name}: fBranchCount points at {target.name!r}, "
                         f"fType {target.element_type} fStreamerType "
                         f"{target.streamer_type}: neither a container count "
                         f"branch nor a counter branch")
            elif target.slot >= br.slot:
                self.bad("TBranchElement 10.9",
                         f"{name}: fBranchCount at {br.count_slot} is not "
                         f"earlier than the branch at {br.slot}")

    def check_splitting(self, br, by_slot) -> None:
        """The Invariants of spec/04-ttree/Splitting.md."""
        name = f"branch {br.name!r}"

        # 5. A TBranchSTL has no leaf but still has baskets, which is why
        #    TLeaf 10.5 to 10.7 are scoped to branches that have leaves.
        if br.cls == "TBranchSTL" and br.leaves:
            self.bad("Splitting 8.5",
                     f"{name}: a TBranchSTL with {len(br.leaves)} leaf/leaves")

        ft = br.element_type
        if ft is None:
            return

        # 1 and 2. An interior node with no children describes nothing. The
        #    exception is a top-level split branch of a class whose streamer
        #    info lists no element: Unroll found nothing to make a branch of,
        #    and the branch holds zero-byte entries itself. Splitting.md 1.1.
        if br.element_id == -2 and not br.branches:
            if self.empty_class_info(br) is None:
                self.bad("Splitting 8.1",
                         f"{name}: fID -2 marks a split node, but fBranches is "
                         f"empty")
            else:
                self.check_empty_class_entries(br)
        if ft in (1, 2) and not br.branches and self.empty_base_info(br) is None:
            self.bad("Splitting 8.2",
                     f"{name}: fType {ft} is an interior node, but fBranches "
                     f"is empty")

        # 3. A count branch's title, its leaf's name and its leaf's title are
        #    one string, set together at construction: the construction name,
        #    trailing dot dropped, plus "_". The branch's own fName is not part
        #    of the invariant, because a writing program may rename a branch
        #    afterwards and ROOT never re-derives the title (FairRoot does, in
        #    ship_ROOT_9674.root). Splitting.md 3.3.
        if ft in (3, 4):
            if not br.title.endswith("_"):
                self.bad("Splitting 8.3",
                         f"{name}: count branch title {br.title!r} does not "
                         f"end in _")
            leaf = br.leaves[0] if len(br.leaves) == 1 else None
            if leaf is not None and (leaf.name, leaf.title) != (br.title,
                                                                  br.title):
                self.bad("Splitting 8.3",
                         f"{name}: count branch title {br.title!r}, but its "
                         f"leaf is {leaf.name!r} / {leaf.title!r}")

        # 4. A member of a split container names its count branch's title in
        #    brackets, and its leaf carries the same title (BuildTitle sets
        #    both). tlorentzvec.root breaks the first half with a writer nobody
        #    has identified; it stays a failure. Splitting.md 3.3.
        if ft in (31, 41) and br.count_slot >= 0:
            target = by_slot.get(br.count_slot)
            if target is not None:
                if not br.title.endswith(f"[{target.title}]"):
                    self.bad("Splitting 8.4",
                             f"{name}: title {br.title!r} does not end in "
                             f"[{target.title}]")
                leaf = br.leaves[0] if len(br.leaves) == 1 else None
                if leaf is not None and leaf.title != br.title:
                    self.bad("Splitting 8.4",
                             f"{name}: title {br.title!r}, but its leaf's "
                             f"title is {leaf.title!r}")

    def check_reading(self, br, by_slot) -> None:
        """The Invariants of spec/04-ttree/ReadingEntries.md."""
        ft = br.element_type
        if ft is None or br.file_name:
            return
        name = f"branch {br.name!r}"

        # 1 and 4. A count branch's entry is one Int_t, bounded by fMaximum.
        if ft in (3, 4):
            for i, payload, span in self.entries_of(br):
                if span is None:
                    continue
                lo, hi = span
                if hi - lo != 4:
                    self.bad("ReadingEntries 8.1",
                             f"{name}: a count entry of {hi - lo} bytes")
                    return
                count = int.from_bytes(payload[lo:hi], "big", signed=True)
                if count < 0 or count > br.maximum:
                    self.bad("ReadingEntries 8.4",
                             f"{name}: count {count} outside [0, {br.maximum}]")
                    return

        # 3. A member column of a fixed-width element is n * w bytes.
        if ft in (31, 41) and br.count_slot >= 0:
            counter = by_slot.get(br.count_slot)
            info = self.element_info(br)
            if counter is None or info is None:
                return
            if br.element_id is None or br.element_id >= len(info.elements):
                return
            width = rootfile.element_width(info.elements[br.element_id])
            if width is None:
                return
            counts = {i: (p, sp) for i, p, sp in self.entries_of(counter)}
            for i, payload, span in self.entries_of(br):
                if span is None or i not in counts:
                    continue
                cpayload, cspan = counts[i]
                if cspan is None:
                    continue
                clo, chi = cspan
                if chi - clo != 4:
                    continue
                n = int.from_bytes(cpayload[clo:chi], "big", signed=True)
                lo, hi = span
                if hi - lo != n * width:
                    self.bad("ReadingEntries 8.3",
                             f"{name}: entry {i} is {hi - lo} bytes, count {n} "
                             f"x width {width} is {n * width}")
                    return

    def entries_of(self, br):
        """(entry number, payload, (start, end)) for every entry, sampled.

        The payload is the entry's *own basket*, decompressed. It is returned
        with the span because a span is meaningless without it: on an
        uncompressed file every buffer happens to be the same bytes, and on a
        compressed one they are not.

        An embedded basket is included, read out of the TTree record
        (TBranch.md 5). Leaving it out made ReadingEntries 8.1, 8.3 and 8.4
        pass vacuously on a file whose baskets are all embedded, such as
        roottest's mksm.root.
        """
        out = []
        for i, rec, payload, basket, why in self.branch_baskets(
                br, self._tree_payload):
            if why is not None or basket.generated:
                continue             # TBasket 5.2.1 offsets, not stored
            for e in self.entry_sample(basket.nev_buf, rec.offset):
                try:
                    span = rootfile.basket_entry_range(rec, basket, e)
                except (rootfile.FormatError, struct.error, IndexError,
                        ValueError):
                    span = None
                out.append((br.basket_entry[i] + e, payload, span))
        return out

    def empty_base_info(self, br):
        """The info of the empty base class `br` stands for, or None.

        Before 5.34/20 and 6.02/00, TTree::Bronch gave every base class of a
        top-level split object a sub-branch, empty or not, and an empty base
        yields an fType 1 branch with no leaf and no children that still has a
        basket: one framed object of the base class per entry. TBranch.md 9.2.
        """
        if (getattr(br, "cls", "TBranch") != "TBranchElement"
                or br.element_type != 1 or br.branches):
            return None
        info = self.element_info(br)
        if info is None or br.element_id is None or not 0 <= br.element_id < len(info.elements):
            return None
        elem = info.elements[br.element_id]
        if elem.type_name != "BASE":
            return None
        _, _, all_infos = self.streamer_infos()
        bases = [i for i in (all_infos or []) if i.name == elem.name]
        if bases and all(not i.elements for i in bases):
            return bases[0]
        return None

    def check_empty_class_entries(self, br) -> None:
        """Every entry of an elementless split branch is zero bytes.

        Its fill path writes element fID -2 of an info with no elements, which
        is nothing, and ReadLeavesMember reads nothing back. Without this the
        exemption in Splitting 8.1 would pass vacuously, and these baskets
        would be in neither side of the ENTRIES line. Splitting.md 1.1.
        """
        name = f"branch {br.name!r}"
        for i in range(min(br.write_basket + 1, len(br.basket_seek))):
            emb = br.embedded.get(i)
            if emb is not None:
                basket = emb.basket
            elif br.basket_seek[i] and not br.file_name:
                rec = self.basket_record(br.basket_seek[i])
                payload = self.data(rec) if rec is not None else None
                if payload is None:
                    self.skip("ReadingEntries 8.5", "basket unavailable")
                    continue
                try:
                    basket = rootfile.read_basket(self.buf, rec, payload)
                except (rootfile.FormatError, struct.error, IndexError,
                        ValueError):
                    continue
            else:
                continue
            if not basket.nev_buf:
                continue
            if basket.data_end != basket.data_start:
                self.bad("Splitting 8.1",
                         f"{name}: basket {i} of a split branch of an "
                         f"elementless class holds "
                         f"{basket.data_end - basket.data_start} bytes for "
                         f"{basket.nev_buf} entries, not 0")
            self.verified += 1

    @staticmethod
    def split_parent(br) -> bool:
        """A branch with sub-branches that fills none of its own baskets.

        TBranchElement's fill path counts fEntries and descends for every type
        but a collection counter (TBranchElement.cxx:1308-1320); TBranchObject's
        does the same (TBranchObject.cxx:175-176). TBranch.md 7.
        """
        return bool(br.branches) and br.element_type not in (3, 4)

    def empty_class_info(self, br):
        """The info of the elementless class a childless split branch stands for.

        TTree::Bronch marks a top-level branch fID -2 whenever it splits, and
        Unroll then makes one sub-branch per element. A class whose streamer
        info lists no element (every member transient, or none) gets none, and
        TClass::CanSplit refuses only a class whose sizeof is 1. The branch
        keeps its leaf and fills zero-byte entries. Splitting.md 1.1.
        """
        if (getattr(br, "cls", "TBranch") != "TBranchElement"
                or br.element_type != 0 or br.element_id != -2
                or br.branches):
            return None
        info = self.element_info(br)
        if info is None or info.elements:
            return None
        return info

    def element_info(self, br):
        """The streamer info fClassName/fClassVersion/fCheckSum select."""
        _, _, all_infos = self.streamer_infos()
        infos = [i for i in (all_infos or []) if i.name == br.class_name]
        if not infos:
            return None
        if br.class_version:
            for i in infos:
                if i.class_version == br.class_version:
                    return i
        for i in infos:
            if i.checksum == br.check_sum:
                return i
        return None

    def check_auxiliary(self, data, rec, tree) -> None:
        """The Invariants of spec/04-ttree/Auxiliary.md."""
        name = f"tree {tree.name!r}"

        # 5. A TBranchRef's identity is fixed by its constructor.
        if tree.branch_ref is not None and tree.branch_ref.name != "TRefTable":
            self.bad("Auxiliary 8.5",
                     f"{name}: fBranchRef is named "
                     f"{tree.branch_ref.name!r}, not 'TRefTable'")

        slot = tree.index_slot
        if slot < 0:
            return
        try:
            ix = rootfile.read_tree_index(data, slot)
        except rootfile.FormatError as exc:
            if "TTreeIndex at" in str(exc):
                self.bad("Auxiliary 8.1", f"{name}: {exc}")
            return                       # otherwise a TChainIndex, or unreadable
        except (struct.error, IndexError, ValueError):
            return
        where = f"{name}: TTreeIndex"

        # 1. The three arrays each hold fN values. read_tree_index would have
        #    raised before now if they did not, so this checks the count itself.
        if ix.n < 0 or len(ix.values) != ix.n or len(ix.index) != ix.n:
            self.bad("Auxiliary 8.1",
                     f"{where}: fN {ix.n} against {len(ix.values)} values and "
                     f"{len(ix.index)} index entries")
            return
        if ix.version >= 2 and len(ix.values_minor) != ix.n:
            self.bad("Auxiliary 8.1",
                     f"{where}: {len(ix.values_minor)} minor values for fN "
                     f"{ix.n}")

        # 2. fIndexValues is the sort key, so it is non-decreasing.
        for i in range(1, ix.n):
            if ix.values[i] < ix.values[i - 1]:
                self.bad("Auxiliary 8.2",
                         f"{where}: fIndexValues[{i}] {ix.values[i]} is below "
                         f"[{i - 1}] {ix.values[i - 1]}")
                break

        # 3. fIndex is a permutation of [0, fN): the constructor sorts the
        #    identity (root/tree/treeplayer/src/TTreeIndex.cxx:222-224) and
        #    Append offsets the appended rows by the old fN (:310-312). fN is
        #    not the tree's fEntries: CopyEntries clones the source tree's
        #    whole index onto a copy of fewer entries
        #    (root/tree/tree/src/TTree.cxx:3516-3521), so an entry number may
        #    be past the end of the tree that holds the index. Auxiliary.md 2.
        if sorted(ix.index) != list(range(ix.n)):
            bad = next((i for i, e in enumerate(ix.index)
                        if not 0 <= e < ix.n), None)
            self.bad("Auxiliary 8.3",
                     f"{where}: fIndex is not a permutation of [0, {ix.n})"
                     + (f"; fIndex[{bad}] is {ix.index[bad]}" if bad is not None
                        else "; an entry number repeats"))

    def check_entry_lists(self) -> None:
        """Auxiliary.md invariants 6 and 7, over the records of this file."""
        _, _, infos = self.streamer_infos()
        if not infos:
            return
        for rec in self.records:
            if rec.free or not rec.key_len:
                continue
            if rec.class_name not in ("TEntryList", "TEventList",
                                      "TEntryListArray"):
                continue
            data = self.data(rec)
            if data is None:
                continue
            try:
                value = rootfile.decode_record(data, rec, infos)
            except (rootfile.FormatError, rootfile.UnsupportedClass,
                    struct.error, IndexError, ValueError):
                continue
            if rec.class_name == "TEventList":
                self.check_event_list(data, rec, value)
            else:
                for block in rootfile.walk(value):
                    if block.type_name == "TEntryListBlock":
                        self.check_entry_block(data, rec, block)

    def check_entry_block(self, data, rec, block) -> None:
        m = rootfile._named(data, block.members or [])
        if not {"fN", "fNPassed", "fType"} <= set(m):
            return
        n = struct.unpack_from(">i", data, m["fN"].start)[0]
        passed = struct.unpack_from(">i", data, m["fNPassed"].start)[0]
        kind = struct.unpack_from(">i", data, m["fType"].start)[0]
        where = f"{rec.name!r} block at {block.start}"
        if kind == 0 and n != 4000:
            self.bad("Auxiliary 8.6",
                     f"{where}: fType 0 with fN {n}, expected 4000")
        if kind == 1 and n != passed:
            self.bad("Auxiliary 8.6",
                     f"{where}: fType 1 with fN {n} and fNPassed {passed}")

    def check_event_list(self, data, rec, value) -> None:
        m = rootfile._named(data, value.members or [])
        if not {"fN", "fSize", "fList"} <= set(m):
            return
        n = struct.unpack_from(">i", data, m["fN"].start)[0]
        size = struct.unpack_from(">i", data, m["fSize"].start)[0]
        where = f"TEventList {rec.name!r}"
        if n < 0 or n > size:
            self.bad("Auxiliary 8.7",
                     f"{where}: fN {n} against fSize {size}")

    def check_tree(self, data, rec, tree) -> None:
        """The Invariants of spec/04-ttree/TTree.md."""
        name = f"tree {tree.name!r}"
        branches = list(rootfile.walk_branches(tree.branches))

        # 1. The byte counters are the sums over every branch, at every depth.
        # fBranchRef is a branch, holds data, and is not in fBranches, so it
        # has to be added by name. TTree.md 4.
        ref = [tree.branch_ref] if tree.branch_ref is not None else []
        for label, got, want in (
                ("fTotBytes", tree.tot_bytes,
                 sum(b.tot_bytes for b in branches + ref)),
                ("fZipBytes", tree.zip_bytes,
                 sum(b.zip_bytes for b in branches + ref))):
            if got != want:
                self.bad("TTree 11.1",
                         f"{name}: {label} {got}, sum over {len(branches)} "
                         f"branches {want}")
        if tree.entries < 0:
            self.bad("TTree 11.1", f"{name}: fEntries {tree.entries}")

        # 2. The two watermarks are at most what has been written. Before
        #    5.27/02, AutoSave recorded fTotBytes rather than fZipBytes, so
        #    fSavedBytes is bounded by fTotBytes alone. TTree.md 6.3.
        zip_era = self.header.root_version >= SAVED_BYTES_ZIP_SINCE
        for label, got, cap, cap_name in (
                ("fSavedBytes", tree.saved_bytes,
                 tree.zip_bytes if zip_era else tree.tot_bytes,
                 "fZipBytes" if zip_era else "fTotBytes"),
                ("fFlushedBytes", tree.flushed_bytes, tree.zip_bytes,
                 "fZipBytes")):
            if not 0 <= got <= cap:
                self.bad("TTree 11.2", f"{name}: {label} {got}, {cap_name} {cap}")

        # 3. The cluster arrays hold exactly fNClusterRange values, and the
        #    is-present flag is clear exactly when there are none.
        n = tree.n_cluster_range
        if n is not None:
            if n < 0:
                self.bad("TTree 11.3", f"{name}: fNClusterRange {n}")
            for label, array, flag in (
                    ("fClusterRangeEnd", tree.cluster_range_end,
                     tree.cluster_present[0]),
                    ("fClusterSize", tree.cluster_size,
                     tree.cluster_present[1])):
                if len(array) != max(n, 0):
                    self.bad("TTree 11.3",
                             f"{name}: {label} has {len(array)} values, "
                             f"fNClusterRange is {n}")
                if bool(flag) != bool(n):
                    self.bad("TTree 11.3",
                             f"{name}: {label} is-present flag {flag} with "
                             f"fNClusterRange {n}")

            # 4. The range ends partition the entries, in order.
            ends = tree.cluster_range_end
            if any(b < a for a, b in zip(ends, ends[1:])):
                self.bad("TTree 11.4", f"{name}: fClusterRangeEnd {ends}")
            if ends and ends[-1] >= tree.entries:
                self.bad("TTree 11.4",
                         f"{name}: fClusterRangeEnd ends at {ends[-1]} but "
                         f"fEntries is {tree.entries}")
            if any(s < 0 for s in tree.cluster_size):
                self.bad("TTree 11.4", f"{name}: fClusterSize {tree.cluster_size}")

        # 5. fLeaves is one back-reference per leaf of the whole tree.
        want_slots = [lf.slot for b in branches for lf in b.leaves]
        got_slots = [rec.offset + r - rootfile.MAP_OFFSET for r in tree.leaf_refs]
        if tree.leaf_objects:
            self.bad("TTree 11.5",
                     f"{name}: {tree.leaf_objects} of fLeaves' entries are "
                     f"objects rather than references")
        elif sorted(got_slots) != sorted(want_slots):
            missing = sorted(set(want_slots) - set(got_slots))
            extra = sorted(set(got_slots) - set(want_slots))
            self.bad("TTree 11.5",
                     f"{name}: fLeaves has {len(got_slots)} references and the "
                     f"branches hold {len(want_slots)} leaves; "
                     f"unreferenced at {missing}, references to no leaf at "
                     f"{extra}")
        if tree.leaf_slots != len(tree.leaf_refs) + tree.leaf_objects:
            self.bad("TTree 11.5",
                     f"{name}: fLeaves' nobjects is {tree.leaf_slots} but it "
                     f"holds {len(tree.leaf_refs) + tree.leaf_objects} entries")

        # 6. The old-style index is two arrays of one length.
        if tree.index_n != tree.index_values_n:
            self.bad("TTree 11.6",
                     f"{name}: fIndex has {tree.index_n} values, fIndexValues "
                     f"{tree.index_values_n}")

        # 7. The two write-time lengths are in range.
        if tree.estimate <= 0:
            self.bad("TTree 11.7", f"{name}: fEstimate {tree.estimate}")
        if (tree.default_entry_offset_len is not None
                and tree.default_entry_offset_len < 10):
            self.bad("TTree 11.7",
                     f"{name}: fDefaultEntryOffsetLen "
                     f"{tree.default_entry_offset_len}")

    def branch_class_version(self) -> int:
        """The lowest TBranch class version any info in this file describes.

        Which writer's conventions apply is a property of the file, not of the
        branch: fMaxBaskets is exactly max(fWriteBasket + 1, 10) from version 9
        on and a flat 1000 below it. Version 8 was gated in with 9 until
        2026-09-23, on the strength of two g4tools files; the nine roottest
        files ROOT 3.05-3.10 wrote at version 8 all have 1000. TBranch.md 11.1,
        13.2.
        """
        _, _, infos = self.streamer_infos()
        versions = [i.class_version for i in (infos or []) if i.name == "TBranch"]
        return min(versions) if versions else 13

    def unzeroed_arrays(self, br) -> bool:
        """Did a constructor that left the basket arrays unzeroed build `br`?"""
        if getattr(br, "cls", "TBranch") != "TBranchElement" or self.header is None:
            return False
        version = self.header.root_version
        if version < ELEMENT_ARRAYS_ZEROED:
            return True
        return (version < COLLECTION_ARRAYS_ZEROED and br.element_id == -1
                and rootfile.is_collection_name(br.class_name))

    def check_branch(self, data, br) -> None:
        name = f"branch {br.name!r}"
        want = max(br.write_basket + 1, 10)
        if br.max_baskets < want:
            self.bad("TBranch 11.1",
                     f"{name}: fMaxBaskets {br.max_baskets} is below "
                     f"max(fWriteBasket + 1, 10) = {want}")
        elif br.max_baskets != want and self.branch_class_version() >= 9:
            self.bad("TBranch 11.1",
                     f"{name}: fMaxBaskets {br.max_baskets}, expected {want} for "
                     f"fWriteBasket {br.write_basket}")
        for label, array in (("fBasketBytes", br.basket_bytes),
                             ("fBasketEntry", br.basket_entry),
                             ("fBasketSeek", br.basket_seek)):
            if len(array) != br.max_baskets:
                self.bad("TBranch 11.1",
                         f"{name}: {label} has {len(array)} elements, "
                         f"fMaxBaskets is {br.max_baskets}")
                return
        if not 0 <= br.write_basket < br.max_baskets:
            self.bad("TBranch 11.2", f"{name}: fWriteBasket {br.write_basket}")
            return

        # A split parent fills no basket, so its fBasketEntry and fEntryNumber
        # describe none. Fast cloning sets them anyway: TTreeCloner makes
        # fEntryNumber equal fEntries, and until 6.22/08 and 6.23/02 wrote the
        # last input's first entry into fBasketEntry[0]. TBranch.md 7.
        parent = self.split_parent(br)
        if br.basket_entry[0] != br.first_entry and not parent:
            self.bad("TBranch 11.3",
                     f"{name}: fBasketEntry[0] {br.basket_entry[0]} != fFirstEntry "
                     f"{br.first_entry}")
        span = br.basket_entry[:br.write_basket + 1]
        if any(b < a for a, b in zip(span, span[1:])):
            self.bad("TBranch 11.3", f"{name}: fBasketEntry decreases: {span}")
        last_embedded = br.embedded.get(br.write_basket)
        if parent:
            if br.entry_number not in (0, br.first_entry + br.entries):
                self.bad("TBranch 11.3",
                         f"{name}: a split parent's fEntryNumber "
                         f"{br.entry_number} is neither 0 nor fFirstEntry + "
                         f"fEntries {br.first_entry + br.entries}")
        elif last_embedded is None:
            if span[-1] != br.entry_number:
                self.bad("TBranch 11.3",
                         f"{name}: fBasketEntry[fWriteBasket] {span[-1]} != "
                         f"fEntryNumber {br.entry_number}")
        elif span[-1] > br.entry_number:
            # The terminator was never written: the element is the embedded
            # basket's first entry, so it is at most fEntryNumber (equal when
            # that basket is empty). It is unconstrained on a split parent, where
            # fEntryNumber is 0 and counts nothing (TBranch.md 11.3, section 5,
            # section 7).
            self.bad("TBranch 11.3",
                     f"{name}: fBasketEntry[fWriteBasket] {span[-1]} is past "
                     f"fEntryNumber {br.entry_number} though basket "
                     f"{br.write_basket} is embedded")

        unassigned_garbage = self.unzeroed_arrays(br)
        for label, array in (("fBasketBytes", br.basket_bytes),
                             ("fBasketEntry", br.basket_entry),
                             ("fBasketSeek", br.basket_seek)):
            tail = array[br.write_basket + 1:]
            if any(tail) and not unassigned_garbage:
                self.bad("TBranch 11.4",
                         f"{name}: {label} is not zero above fWriteBasket: {tail}")

        # A split parent counts fEntries without fEntryNumber: TBranch.md 7.
        if not br.branches and br.entries != br.entry_number - br.first_entry:
            self.bad("TBranch 11.8",
                     f"{name}: fEntries {br.entries} != fEntryNumber - fFirstEntry "
                     f"({br.entry_number} - {br.first_entry})")

        # The slot count is not fixed by fWriteBasket: g4tools writes
        # fMaxBaskets slots and alice_ESDs.root writes one more than
        # fWriteBasket + 1, leaving a basket ROOT never reads. What must hold is
        # that the array cannot run past the arrays that index it, and that no
        # slot pairs an embedded basket with a non-zero fBasketSeek.
        # TBranch.md 11.9, section 5.
        if br.basket_slots > br.max_baskets:
            self.bad("TBranch 11.9",
                     f"{name}: fBaskets has {br.basket_slots} slots, more than "
                     f"fMaxBaskets = {br.max_baskets}")
        # Every object in fBaskets is a basket, and an embedded one satisfies
        # TBasket.md invariant 1 as a record does.
        for index, why in sorted(br.embedded_errors.items()):
            self.bad("TBasket 9.1", f"{name}: {why}")
        for index, emb in sorted(br.embedded.items()):
            if unassigned_garbage:
                break           # never assigned: TBranch.md 11.9
            seek = br.basket_seek[index] if index < len(br.basket_seek) else 0
            if not seek:
                continue
            if index < br.write_basket and emb.seek_key == seek:
                # A basket read back from its record and still in memory when
                # the tree was streamed, which no writer before 6.11/02
                # prevented. It is a second copy of the record, and must be
                # the same bytes. TBranch.md 5.1.
                problem = self.readback_mismatch(br, index, emb, data)
                if problem:
                    self.bad("TBranch 11.9",
                             f"{name}: slot {index} holds a copy of the basket "
                             f"record at {seek}, but {problem}")
                continue
            self.bad("TBranch 11.9",
                     f"{name}: slot {index} holds an embedded basket but "
                     f"fBasketSeek[{index}] is {seek}")
        # A slot above fWriteBasket is never read. The only producer measured
        # is the second, never-filled basket that TBranchElement's constructor
        # gave a split collection branch before 5.18/00 (TBranch.md 5), so a
        # basket there holds no entries.
        for index, emb in sorted(br.embedded.items()):
            if index > br.write_basket and emb.basket.nev_buf:
                self.bad("TBranch 11.9",
                         f"{name}: slot {index}, above fWriteBasket "
                         f"{br.write_basket}, holds a basket of "
                         f"{emb.basket.nev_buf} entries")

        # An interior node of a split branch has no leaves of its own: TBranch.md
        # 9.1. ROOT has a dedicated zero-leaf read path for it.
        if (not br.leaves and not br.branches
                and self.empty_base_info(br) is None):
            self.bad("TBranch 11.10", f"{name}: fLeaves is empty")
        if br.entry_offset_len and br.entry_offset_len < 10:
            self.bad("TBranch 11.11",
                     f"{name}: fEntryOffsetLen {br.entry_offset_len} is below the "
                     f"floor of 10")
        # A branch with no leaf goes on: 11.5 to 11.7 are about its baskets,
        # not its leaves, and a TBranchSTL or an empty-base branch (TBranch.md
        # 9.2) has baskets full of data and no leaf. An interior node has no
        # basket, so for it they compare zeros. Returning here once left all
        # three unchecked on every leafless branch.
        variable = any(lf.count_slot >= 0 or lf.cls == "TLeafC"
                       for lf in br.leaves)
        if variable and not br.entry_offset_len:
            self.bad("TBranch 11.11",
                     f"{name}: fEntryOffsetLen is 0 though a leaf is variable-size")

        emb = br.embedded.get(br.write_basket)
        if emb is not None:
            # A split parent never fills its basket (TBranch.md 7), whatever
            # fast cloning left in fEntryNumber.
            want_n = (0 if self.split_parent(br)
                      else br.entry_number - br.basket_entry[br.write_basket])
            if emb.basket.nev_buf != want_n:
                self.bad("TBranch 11.6",
                         f"{name}: the embedded basket holds "
                         f"{emb.basket.nev_buf} entries, fEntryNumber and "
                         f"fBasketEntry say {want_n}")

        if br.file_name:
            return                      # 11.5 to 11.7 are about this file only
        tot = zip_ = 0
        for i in range(min(br.write_basket, len(br.basket_seek) - 1)):
            emb = br.embedded.get(i)
            if emb is not None and not br.basket_seek[i]:
                # A basket that was never written as a record: a tree with no
                # file keeps every basket in its slot (TBasket::WriteBuffer
                # returns 0), and writing the tree later embeds them all. It
                # adds nothing to fZipBytes and fTotBytes (11.7). TBranch.md 5.
                # An embedded basket beside a non-zero seek is 11.9's to
                # report; the record the seek names is checked below as usual.
                want_n = br.basket_entry[i + 1] - br.basket_entry[i]
                if emb.basket.nev_buf != want_n:
                    self.bad("TBranch 11.6",
                             f"{name}: embedded basket {i} holds "
                             f"{emb.basket.nev_buf} entries, fBasketEntry says "
                             f"{want_n}")
                continue
            basket_rec = self.basket_record(br.basket_seek[i])
            if basket_rec is None or basket_rec.class_name != "TBasket":
                self.bad("TBranch 11.5",
                         f"{name}: fBasketSeek[{i}] {br.basket_seek[i]} is not a "
                         f"TBasket record")
                continue
            if basket_rec.nbytes != br.basket_bytes[i]:
                self.bad("TBranch 11.5",
                         f"{name}: fBasketBytes[{i}] {br.basket_bytes[i]} != the "
                         f"record's fNbytes {basket_rec.nbytes}")
            payload = self.data(basket_rec)
            if payload is None:
                continue
            try:
                basket = rootfile.read_basket(self.buf, basket_rec, payload)
            except (rootfile.FormatError, struct.error, IndexError,
                    ValueError) as exc:
                self.bad("TBranch 11.6", f"{name}: basket {i}: {exc}")
                continue
            want_n = br.basket_entry[i + 1] - br.basket_entry[i]
            if basket.nev_buf != want_n:
                self.bad("TBranch 11.6",
                         f"{name}: basket {i} holds {basket.nev_buf} entries, "
                         f"fBasketEntry says {want_n}")
            tot += basket_rec.obj_len + basket_rec.key_len
            zip_ += basket_rec.nbytes
        if zip_ != br.zip_bytes:
            self.bad("TBranch 11.7",
                     f"{name}: fZipBytes {br.zip_bytes} != the sum of the basket "
                     f"records' fNbytes {zip_}")
        if tot != br.tot_bytes:
            self.bad("TBranch 11.7",
                     f"{name}: fTotBytes {br.tot_bytes} != the sum of "
                     f"fObjlen + fKeylen {tot}")

    def readback_mismatch(self, br, index, emb, data) -> str | None:
        """How a read-back copy in slot `index` differs from its record, if it does.

        TBranch.md 5.1: the key keeps the record's fNbytes and fSeekKey, and
        the fLast bytes of the block are the record's key area and uncompressed
        data. Only the data and the entry offsets are compared: the key area of
        the block is outside every entry.
        """
        rec = self.basket_record(br.basket_seek[index])
        if rec is None or rec.class_name != "TBasket":
            return "no TBasket record starts there"
        if emb.nbytes != rec.nbytes or rec.nbytes != br.basket_bytes[index]:
            return (f"its key's fNbytes {emb.nbytes}, the record's {rec.nbytes} and "
                    f"fBasketBytes[{index}] {br.basket_bytes[index]} disagree")
        payload = self.data(rec)
        if payload is None:
            return None                 # codec missing: counted as not checked
        try:
            disk = rootfile.read_basket(self.buf, rec, payload)
        except (rootfile.FormatError, struct.error, IndexError, ValueError) as exc:
            return f"the record does not parse: {exc}"
        copy = emb.basket
        if (copy.nev_buf, copy.last, copy.key_len) != (disk.nev_buf, disk.last,
                                                      disk.key_len):
            return (f"fNevBuf/fLast/fKeylen are {copy.nev_buf}/{copy.last}/"
                    f"{copy.key_len} in the copy and {disk.nev_buf}/{disk.last}/"
                    f"{disk.key_len} in the record")
        if copy.entry_offsets is not None:
            if (disk.entry_offsets is None
                    or disk.entry_offsets[:copy.nev_buf] != copy.entry_offsets):
                return "the entry offsets differ"
        if emb.block >= 0:
            a, b = emb.block + copy.key_len, emb.block + copy.last
            if data[a:b] != payload[rec.offset + disk.key_len:rec.offset + disk.last]:
                return "the entry data differ"
        return None

    def check_empty_base_entries(self, data, br, base) -> None:
        """Each entry of an empty-base branch is one framed object of `base`.

        ReadingEntries 8.5: the entry's span must be exactly the object's byte
        count, and its version word (or, at version 0, its checksum) must
        name the base class's streamer info. TBranch.md 9.2.
        """
        name = f"branch {br.name!r}"
        for i, _, buf, basket, why in self.branch_baskets(br, data):
            if why is not None:
                self.skip("ReadingEntries 8.5", why)
                continue
            if basket.entry_offsets is None:
                self.skip("ReadingEntries 8.5",
                          "empty-base branch basket with no entry offsets")
                continue
            origin = basket.data_start - basket.key_len
            starts = [origin + o for o in basket.entry_offsets]
            ends = starts[1:] + [basket.data_end]
            ok = True
            for j, (a, b) in enumerate(zip(starts, ends)):
                frame = rootfile.read_frame(buf, a)
                if frame.end != b:
                    ok = False
                    self.bad("ReadingEntries 8.5",
                             f"{name}: basket {i} entry {j} spans {b - a} bytes, "
                             f"its {base.name} frame {None if frame.end is None else frame.end - a}")
                elif frame.version == 0 and rootfile._u32(buf, frame.body) != base.checksum:
                    ok = False
                    self.bad("ReadingEntries 8.5",
                             f"{name}: basket {i} entry {j} checksum "
                             f"{rootfile._u32(buf, frame.body):#x}, {base.name} has "
                             f"{base.checksum:#x}")
                elif frame.version not in (0, base.class_version):
                    ok = False
                    self.bad("ReadingEntries 8.5",
                             f"{name}: basket {i} entry {j} version "
                             f"{frame.version}, {base.name} is {base.class_version}")
            if ok:
                self.verified += 1
            else:
                self.tally_failed("ReadingEntries 8.5")

    def check_leaves(self, data, br, leaves) -> None:
        name = f"branch {br.name!r}"
        counted = {lf.count_slot for lf in leaves if lf.count_slot >= 0}
        for i, lf in enumerate(br.leaves):
            where = f"{name} leaf {lf.name!r}"
            # fLen may be -1: the title's dimension named something the writer
            # could not resolve. TLeaf.md 4.2.
            if lf.len_type < 0 or (lf.length < 1 and lf.length != -1):
                self.bad("TLeaf 10.1",
                         f"{where}: fLenType {lf.len_type}, fLen {lf.length}")
            if lf.is_range and lf.slot not in counted:
                self.bad("TLeaf 10.2",
                         f"{where}: fIsRange is set but no leaf counts with it")
            if (lf.is_range and lf.cls != "TLeafElement"
                    and lf.cls not in rootfile.COUNTER_LEAVES):
                self.bad("TLeaf 10.3",
                         f"{where}: fIsRange is set on a {lf.cls}")
            if lf.count_slot >= 0:
                try:
                    rootfile.resolve_leaf_count(lf, leaves)
                except rootfile.FormatError as exc:
                    self.bad("TLeaf 10.4", f"{where}: {exc}")
            if lf.cls == "TLeafC":
                self.check_leafc(br, lf)
            if i == 0 and lf.offset != 0 and br.via != "TBranchClones":
                # A sub-branch of a TBranchClones carries the member's offset
                # inside the object, and ROOT forces it to -1 on read
                # (root/tree/tree/src/TBranchClones.cxx:413). TLeaf.md 10.8.
                self.bad("TLeaf 10.8",
                         f"{where}: the first leaf has fOffset {lf.offset}")

        if br.file_name:
            # The baskets are in another file (TBranch.md 9). Not a pass: each
            # one that holds entries is a branch-basket no check reached.
            if (br.element_type is None or self.decodes_entries(br)
                    or self.empty_base_info(br) is not None):
                for *_, why in self.branch_baskets(br, data):
                    self.skip("ReadingEntries 8.5", why)
            return

        if not br.leaves:
            # A branch with no leaf at all. Two shapes reach here: the interior
            # nodes of TBranchElement.md 4, which have no basket either and so
            # cost nothing, and a TBranchSTL, which has baskets full of data and
            # still no leaf (Splitting.md 5). TLeaf 10.5 to 10.7 are about what a
            # branch's leaves say, so they have nothing to check.
            #
            base = self.empty_base_info(br)
            if base is not None:
                self.check_empty_base_entries(data, br, base)
                return
            if self.decodes_entries(br):
                return          # check_entry_decode accounts for it
            # A leafless branch that *does* have baskets must still be counted.
            # Returning silently once left a TBranchSTL's baskets out of both the
            # numerator and the denominator of the ENTRIES line, the same
            # mistake the embedded baskets exposed (AGENTS.md).
            for _, _, _, _, why in self.branch_baskets(br, data):
                self.skip("ReadingEntries 8.5", why or
                          "leafless branch: a TBranchSTL entry is one framed "
                          "TIndArray, Splitting.md 5.1")
            return

        variable = any(lf.count_slot >= 0 or lf.cls == "TLeafC"
                       for lf in br.leaves)
        fixed_width = None
        if not variable:
            widths = [lf.width for lf in br.leaves]
            if None not in widths:
                fixed_width = sum(w * lf.length
                                  for w, lf in zip(widths, br.leaves))
            elif br.element_type is not None:
                # A TLeafElement: check_entry_decode reads these entries and
                # accounts for them.
                return
            # Otherwise a TLeafObject, which has no fixed width either. TLeaf
            # 10.6 has no size to compare, and the entry check below reports
            # the basket as skipped. A TBranchObject's baskets used to leave
            # the ENTRIES line through an early return here.

        # One outcome per branch-basket, from check_entries. A TBranchElement
        # is accounted for by check_entry_decode instead.
        owner = br.element_type is None
        for i, basket_rec, payload, basket, why in self.branch_baskets(br, data):
            if why is not None:
                if owner:
                    self.skip("TLeaf 10.7", why)
                continue
            if i not in br.embedded:
                # A basket with its own record. TLeaf 10.5, 10.6 and 10.11
                # have only ever been checked on these; an embedded basket
                # is checked by the entry walk alone.
                if variable and not basket.has_offsets and not basket.generated:
                    self.bad("TLeaf 10.5",
                             f"{name}: basket {i} has no entry-offset array "
                             f"though a leaf is variable-size")
                if not variable and not br.entry_offset_len:
                    # fEntryOffsetLen is the writer's decision and the baskets
                    # follow it: g4tools leaves it at 1000 on a fixed-width
                    # branch and writes offsets anyway. TLeaf.md 10.6.
                    if basket.has_offsets:
                        self.bad("TLeaf 10.6",
                                 f"{name}: basket {i} has an entry-offset array "
                                 f"though every leaf is fixed-size and "
                                 f"fEntryOffsetLen is 0")
                    elif (fixed_width is not None
                          and basket.nev_buf_size != fixed_width):
                        self.bad("TLeaf 10.6",
                                 f"{name}: fNevBufSize {basket.nev_buf_size} != "
                                 f"the leaves' {fixed_width} bytes an entry")
                if len(br.leaves) == 1 and br.leaves[0].cls == "TLeafC":
                    self.check_leafc_strings(payload, basket_rec, basket, br,
                                             br.leaves[0])
            self.check_entries(payload, basket_rec, basket, br, leaves, i)

    def check_leafc(self, br, leaf) -> None:
        """TLeaf 10.9 and 10.10: what a `TLeafC` records about itself."""
        where = f"branch {br.name!r} leaf {leaf.name!r}"
        if leaf.len_type != 1:
            self.bad("TLeaf 10.9",
                     f"{where}: a TLeafC's fLenType is {leaf.len_type}, not 1")
        if leaf.minimum not in (None, 0):
            self.bad("TLeaf 10.9",
                     f"{where}: a TLeafC's fMinimum is {leaf.minimum}, not 0")
        if leaf.is_range:
            self.bad("TLeaf 10.9", f"{where}: fIsRange is set on a TLeafC")
        # fLen <= fMaximum once anything has been written. They are equal in a
        # tree filled the ordinary way and fLen is the smaller one in a
        # fast-cloned tree, which is the shape ROOT then misreads (TLeaf.md 9).
        if br.entries and leaf.maximum is not None:
            if not 1 <= leaf.length <= leaf.maximum:
                self.bad("TLeaf 10.10",
                         f"{where}: fLen {leaf.length} outside "
                         f"[1, fMaximum {leaf.maximum}]")

    def check_leafc_strings(self, payload, basket_rec, basket, br, leaf) -> None:
        """TLeaf 10.11: `fMaximum` covers every string the baskets hold.

        Only meaningful when the `TLeafC` is its branch's only leaf, because the
        entry offsets bound the whole entry rather than the string. `fLen` is
        *not* compared: it can be smaller, and then ROOT truncates on read while
        the bytes here are still correct (`TLeaf.md` 9).
        """
        offsets = basket.entry_offsets
        if not offsets or leaf.maximum is None:
            return
        longest = 0
        for e in range(min(basket.nev_buf, len(offsets))):
            start = basket_rec.offset + offsets[e]
            end = basket_rec.offset + (offsets[e + 1] if e + 1 < len(offsets)
                                       else basket.last)
            if end <= start:
                continue          # an empty string occupies no bytes at all
            n = payload[start]
            if n == 255:
                n = int.from_bytes(payload[start + 1:start + 5], "big",
                                   signed=True)
            if n < 0:
                self.bad("TLeaf 10.11",
                         f"branch {br.name!r}: entry {e} has a negative "
                         f"string length {n}")
                return
            longest = max(longest, n)
        if longest + 1 > leaf.maximum:
            self.bad("TLeaf 10.11",
                     f"branch {br.name!r}: a string of {longest} bytes needs "
                     f"fMaximum at least {longest + 1}, the leaf says "
                     f"{leaf.maximum}")

    def generated_offsets(self, basket, br, leaves, index):
        """TBasket.md 5.2.1: the offsets a flag-80 basket does not store."""
        if len(br.leaves) != 1:
            self.bad("TBasket 5.2.1",
                     f"branch {br.name!r}: flag 80 needs exactly one leaf, "
                     f"there are {len(br.leaves)}")
            return None
        leaf = br.leaves[0]
        if leaf.count_slot < 0:
            self.bad("TBasket 5.2.1",
                     f"branch {br.name!r}: flag 80 on a leaf with no fLeafCount")
            return None
        counter = rootfile.resolve_leaf_count(leaf, leaves)
        first = br.basket_entry[index]
        counts = []
        for e in range(basket.nev_buf):
            counts.append(self.leaf_counts(br, leaves, first + e)[counter.slot])
        header = 1 if leaf.cls == "TLeafElement" else 0
        return rootfile.generate_entry_offsets(
            basket.key_len, basket.nev_buf, leaf.len_type, counts, header)

    def check_entries(self, payload, basket_rec, basket, br, leaves, index) -> None:
        """TLeaf.md 10.7: the leaves account for each entry exactly.

        For a plain TBranch this is the ENTRIES line's check, and each call
        gives its basket exactly one outcome. For a TBranchElement it runs for
        the failures it can find, and check_entry_decode keeps the account.
        """
        owner = br.element_type is None
        if basket.generated:
            offsets = self.generated_offsets(basket, br, leaves, index)
            if offsets is None:
                if owner:
                    self.tally_failed("TBasket 5.2.1")
                return
            if offsets[-1] > basket.last:
                self.bad("TBasket 5.2.1",
                         f"branch {br.name!r}: generated offsets run to "
                         f"{offsets[-1]}, past fLast {basket.last}")
                if owner:
                    self.tally_failed("TBasket 5.2.1")
                return
            basket = dataclasses.replace(basket, entry_offsets=offsets,
                                         generated=False)
        for e in self.entry_sample(basket.nev_buf, basket_rec.offset):
            entry = br.basket_entry[index] + e
            try:
                counts = self.leaf_counts(br, leaves, entry)
                rootfile.entry_spans(payload, basket_rec, basket, br, e,
                                     counts, leaves)
            except rootfile.UnsupportedClass as exc:
                # Not a pass. The entry check cannot run here, and staying
                # silent would hide the split branches of PLAN.md 9.11 inside a
                # "0 failures" line. Counted and reported; the count should fall
                # as 04-ttree/ grows.
                if owner:
                    self.skip("TLeaf 10.7", str(exc))
                # A TBranchElement: entry_spans is leaf-driven and a
                # TLeafElement has no fixed width, but check_entry_decode
                # reads the entry properly and owns the accounting for it.
                return
            except (rootfile.FormatError, struct.error, IndexError,
                    ValueError) as exc:
                self.bad("TLeaf 10.7", f"branch {br.name!r}: {exc}")
                if owner:
                    self.tally_failed("TLeaf 10.7")
                return
        if owner:
            self.verified += 1

    # A basket with at most this many entries is checked entry by entry. Above
    # it, only the ends and a stride through the middle are, because the check
    # costs one entry_spans call per entry per branch and a 42 000-entry tree with
    # 32 branches is millions of them. Every reference file and almost every file
    # in gen/foreign/ is below the threshold, and both corpora give the same
    # result either way; `--all-entries` turns sampling off to confirm that.
    ENTRY_SAMPLE_ABOVE = 256
    ENTRY_SAMPLE_ENDS = 32

    def entry_sample(self, nev_buf: int, at: int | None = None) -> list[int]:
        """Which entries of a basket to check. TLeaf.md 10.7.

        `at` is the basket's record offset, or its raw block's for an embedded
        one, so that SAMPLED counts baskets rather than the checks that
        sampled them: several checks read one basket's entries.
        """
        if self.all_entries or nev_buf <= self.ENTRY_SAMPLE_ABOVE:
            return list(range(nev_buf))
        ends = self.ENTRY_SAMPLE_ENDS
        # The ends matter most: an offset array's first and last entry are where
        # the errors of TBasket.md 5 and TLeaf.md 9 showed up.
        picked = set(range(ends)) | set(range(nev_buf - ends, nev_buf))
        stride = max(1, nev_buf // ends)
        picked |= set(range(0, nev_buf, stride))
        if at is None or at not in self._sampled_at:
            self.sampled += 1
            if at is not None:
                self._sampled_at.add(at)
        return sorted(picked)

    def leaf_counts(self, br, leaves, entry) -> dict[int, int]:
        """The value, at `entry`, of every counter leaf this branch needs."""
        counts = {}
        for lf in br.leaves:
            if lf.count_slot < 0:
                continue
            counter = rootfile.resolve_leaf_count(lf, leaves)
            owner = self._owner_of(counter)
            if owner is None:
                raise rootfile.FormatError(
                    f"counter leaf {counter.name!r} belongs to no branch")
            i = rootfile.find_basket(owner, entry)
            rec = self.basket_record(owner.basket_seek[i])
            if rec is None:
                # No record: the counter branch kept this basket embedded in the
                # TTree record (TBranch.md 5), so it is in the payload the
                # branches themselves came out of, and its entry offsets are
                # relative to the raw block rather than to a key (TBasket.md 4.1).
                emb = owner.embedded.get(i)
                if emb is None or emb.block < 0 or self._tree_payload is None:
                    raise rootfile.UnsupportedClass(
                        f"counter basket {i} of branch {owner.name!r} is neither a "
                        f"record nor an embedded basket this reader can locate")
                rec = rootfile.Record(offset=emb.block, nbytes=0)
                payload, basket = self._tree_payload, emb.basket
            else:
                payload = self.data(rec)
                if payload is None:
                    raise rootfile.UnsupportedClass(
                        f"counter basket {i} of branch {owner.name!r} could not be "
                        f"decompressed")
                basket = self.basket(rec, payload)
            spans = rootfile.entry_spans(payload, rec, basket, owner,
                                         entry - owner.basket_entry[i], {}, leaves)
            start = next(s for lfx, s, _ in spans if lfx is counter)
            counts[counter.slot] = int.from_bytes(
                payload[start:start + counter.width], "big", signed=True)
        return counts

    def _owner_of(self, leaf):
        if leaf.slot in self._owners:
            return self._owners[leaf.slot]
        found = self._owner_scan(leaf)
        self._owners[leaf.slot] = found
        return found

    def _owner_scan(self, leaf):
        for branches in self._all_branches:
            for br in rootfile.walk_branches(branches):
                if leaf in br.leaves:
                    return br
        return None

    def run(self) -> list[str]:
        if self.records is None:
            # The chain could not be walked; report only what the header says.
            if self.header is not None:
                if self.header.end > len(self.buf):
                    self.bad("FileHeader 10.5",
                             f"fEND {self.header.end} past file size "
                             f"{len(self.buf)}: truncated")
            return self.failures
        self.check_header()
        self.check_records()
        self.check_compression()
        self.check_directories()
        self.check_free_list()
        self.check_buffer_framing()
        self.check_streamer_info()
        self.check_streamer_driven()
        self.check_references()
        self.check_schema_evolution()
        self.check_collections()
        self.check_tarray()
        self.check_containers()
        self.check_formula()
        self.check_canvas()
        self.check_histogram()
        self.check_graphs()
        self.check_matrix()
        self.check_roofit()
        self.check_basket()
        self.check_branches()
        self.check_entry_lists()
        self.check_rntuple()
        return self.failures


def load_ignores(path: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Per-file invariant skips and custom-streamer lists, from IGNORE.toml.

    `skip` is for files this project did not write and has diagnosed as the
    file's fault rather than the specification's. `custom_streamer` lists what a
    reader cannot get from a file: which of its classes have a hand-written
    Streamer, whose streamer info therefore cannot be trusted
    (StreamerDriven.md 7). See the header of that file.
    """
    import tomllib
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    return ({name: entry.get("skip", []) for name, entry in data.items()},
            {name: entry.get("custom_streamer", [])
             for name, entry in data.items()})


def main(argv: list[str]) -> int:
    ignores: dict[str, list[str]] = {}
    customs: dict[str, list[str]] = {}
    ignore_path = None
    if "--ignore" in argv:
        at = argv.index("--ignore")
        ignore_path = argv[at + 1]
        ignores, customs = load_ignores(Path(ignore_path))
        argv = argv[:at] + argv[at + 2:]
    all_entries = "--all-entries" in argv
    argv = [a for a in argv if a != "--all-entries"]
    paths = [Path(a) for a in argv] or sorted((REPO / "data").rglob("*.root"))
    failures = []
    no_codec: set[str] = set()
    sampled = 0
    verified = 0
    failed: dict[str, int] = {}
    skipped: dict[tuple[str, str, str], int] = {}
    for path in paths:
        checker = Checker(path, all_entries=all_entries,
                          custom=set(customs.get(path.name, [])))
        failures += checker.run()
        no_codec |= checker.no_codec
        sampled += checker.sampled
        verified += checker.verified
        for label, n in checker.failed.items():
            failed[label] = failed.get(label, 0) + n
        for reason, n in checker.skipped.items():
            skipped[reason] = skipped.get(reason, 0) + n

    suppressed: dict[tuple[str, str], int] = {}
    kept = []
    for f in failures:
        name, _, rest = f.partition(": ")
        rule = rest.split(":", 1)[0]
        if rule in ignores.get(name, []):
            suppressed[(name, rule)] = suppressed.get((name, rule), 0) + 1
        else:
            kept.append(f)
    failures = kept
    # Every entry for a file that was checked is reported, including one that
    # suppressed nothing. Such an entry is stale -- the file was fixed, or the
    # specification was -- or the check it names could not run, and either way
    # it must not sit there unseen. Until 2026-09-24 it printed nothing
    # (PLAN-review.md V32).
    checked = {p.name for p in paths}
    for name in sorted(set(ignores) & checked):
        for rule in ignores[name]:
            n = suppressed.get((name, rule), 0)
            print(f"IGNORED {n:4} x {rule} in {name} ({ignore_path})",
                  file=sys.stderr)
            if n == 0:
                failures.append(
                    f"{name}: {rule}: the {ignore_path} entry suppressed "
                    f"nothing; remove it, or find out why its check did not run")

    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    # Report unread records: a record nobody could read was not checked, and
    # omitting it would overstate the coverage. The reasons are a missing
    # codec, a class the file does not describe, and a class with a hand-written
    # streamer spec/ has not written up.
    for reason in sorted(no_codec):
        print(f"NOT CHECKED {reason}", file=sys.stderr)
    for reason, n in sorted(skipped.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"SKIPPED {n:5} {reason[2]}(s): {reason[0]} could not run -- "
              f"{reason[1]}", file=sys.stderr)
    # Every branch-basket that holds entries is in the denominator exactly
    # once: checked, failed or skipped. A failed one is not dropped, or the
    # ratio would rise when a check breaks. Failures of branch-baskets that an
    # IGNORE.toml entry suppressed are still counted here, as failed.
    nfailed = sum(failed.values())
    nskipped = sum(n for reason, n in skipped.items()
                   if reason[2] == "branch-basket")
    total = verified + nfailed + nskipped
    if total:
        detail = ", ".join(f"{n} {label}" for label, n in sorted(failed.items()))
        print(f"ENTRIES  {verified} of {total} branch-basket(s) had their "
              f"entries decoded and checked "
              f"({100 * verified / total:.1f}%); {nfailed} failed"
              f"{f' ({detail})' if detail else ''} and {nskipped} are the "
              f"SKIPPED lines above", file=sys.stderr)
    if sampled:
        print(f"SAMPLED {sampled} basket(s) held more than "
              f"{Checker.ENTRY_SAMPLE_ABOVE} entries, so TLeaf 10.7 checked the "
              f"ends and a stride rather than every entry; --all-entries forces "
              f"the exhaustive check", file=sys.stderr)
    print(f"invariants checked on {len(paths)} file(s), {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
