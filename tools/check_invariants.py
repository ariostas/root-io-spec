#!/usr/bin/env python3
"""Check the `Invariants` sections of spec/ against every fixture.

Each layer document ends with a list of properties a conforming file satisfies
(see PLAN.md 2.8). This makes those lists executable, which serves two purposes:
it validates the reference files, and it validates the invariants themselves --
a property stated wrongly fails here against files ROOT actually wrote.

Each check names the document and section it comes from. Needs no third-party
packages; the one exception is noted where it arises.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import rootfile  # noqa: E402

KNOWN_KEY_VERSIONS = {1, 2, 3, 4, 1002, 1003, 1004}
BLOCK_MAGICS = {b"ZL": 8, b"XZ": 0, b"L4": None, b"ZS": 1, b"CS": 8}
KMAXZIPBUF = 0xFFFFFF
KSTART_BIG_FILE = 2000000000


def counted_string_len(buf: bytes, offset: int) -> int:
    n = buf[offset]
    return 1 + 4 + struct.unpack_from(">i", buf, offset + 1)[0] if n == 255 else 1 + n


def element_list_failures(info) -> list[tuple[str, str]]:
    """StreamerDriven.md invariants 3, 4 and 6, over one streamer info.

    Separate from Checker so that it can be exercised on element lists no
    fixture contains -- an out-of-order base class, for one.
    """
    failures: list[tuple[str, str]] = []
    names = [e.name for e in info.elements]
    bases_seen = 0
    for index, el in enumerate(info.elements):
        if el.cls == "TStreamerBase":
            if bases_seen != index:
                failures.append((
                    "StreamerDriven 10.4",
                    f"{info.name}: base {el.name!r} at index {index} follows a "
                    f"non-base element"))
            bases_seen += 1
        if el.count_name:
            if el.count_name not in names[:index]:
                failures.append((
                    "StreamerDriven 10.3",
                    f"{info.name}.{el.name} names counter {el.count_name!r}, "
                    f"which does not precede it"))
            else:
                counter = info.elements[names.index(el.count_name)]
                if counter.ftype != 6:
                    failures.append((
                        "StreamerDriven 10.3",
                        f"{info.name}.{el.name} names {el.count_name!r}, whose "
                        f"fType is {counter.ftype}, not 6"))
        if el.ftype == -1 and el.cls != "TStreamerBase":
            failures.append((
                "StreamerDriven 10.6",
                f"{info.name}.{el.name} has fType -1 but is a {el.cls}, not a "
                f"TStreamerBase"))
    return failures


def info_list_failures(infos) -> list[tuple[str, str]]:
    """SchemaEvolution.md invariants 1 and 2, over one StreamerInfo record.

    Separate from Checker so that invariant 2 can be exercised: no fixture can
    hold two identical infos, because ROOT would not write one.
    """
    failures: list[tuple[str, str]] = []
    seen: set[tuple[str, int, int]] = set()
    for info in infos:
        if not 0 <= info.class_version <= 65000:
            failures.append((
                "SchemaEvolution 9.1",
                f"{info.name} has fClassVersion {info.class_version}"))
        key = (info.name, info.class_version, info.checksum)
        if key in seen:
            failures.append((
                "SchemaEvolution 9.2",
                f"two infos for {info.name} share version {info.class_version} "
                f"and checksum {info.checksum:#010x}"))
        seen.add(key)
    return failures


class Checker:
    def __init__(self, path: Path):
        self.path = path
        self.failures: list[str] = []
        self.buf = path.read_bytes()
        self.header = self.records = None
        try:
            self.header = rootfile.read_header(self.buf)
            self.records = rootfile.read_records(self.buf, self.header)
        except rootfile.FormatError as exc:
            self.bad("structure", str(exc))

    def bad(self, where: str, message: str) -> None:
        self.failures.append(f"{self.path.name}: {where}: {message}")

    # -- FileHeader.md 10 ---------------------------------------------------
    def check_header(self) -> None:
        h, size = self.header, len(self.buf)
        if self.buf[:4] != b"root":
            self.bad("FileHeader 10.1", "magic is not 'root'")
        if not 0 <= h.begin <= h.end:
            self.bad("FileHeader 10.2", f"fBEGIN {h.begin}, fEND {h.end}")
        if not 10 <= h.nbytes_name <= 10000:
            self.bad("FileHeader 10.4", f"fNbytesName {h.nbytes_name} outside [10, 10000]")
        if h.end != size:
            self.bad("FileHeader 10.5", f"fEND {h.end} != file size {size}")

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

        if h.large != (h.end > KSTART_BIG_FILE):
            self.bad("FileHeader 10.9",
                     f"large flag {h.large} but fEND is {h.end}")
        if h.units != (8 if h.large else 4):
            self.bad("FileHeader 10.10", f"fUnits {h.units} disagrees with the version flag")

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
            if total != rec.key_len:
                self.bad("Record 8.3",
                         f"fKeylen {rec.key_len} != computed key length {total}")

            # 8.6: fSeekPdir is 0 only for the top-level record.
            if rec.seek_pdir == 0:
                if rec.offset != self.header.begin:
                    self.bad("Record 8.6", f"fSeekPdir 0 on a record at {rec.offset}")
            else:
                parent = self.at(rec.seek_pdir)
                if parent is None or rootfile.read_directory(self.buf, parent) is None:
                    self.bad("Record 8.6",
                             f"fSeekPdir {rec.seek_pdir} does not name a directory record")

        if cursor != self.header.end:
            self.bad("Record 8.8", f"chain ends at {cursor}, fEND is {self.header.end}")

    # -- Buffer.md 9 --------------------------------------------------------
    # Records whose class is TFile or TDirectory are the container's own
    # bookkeeping (root directory, key list, free list, subdirectory records).
    # They are not streamed objects and carry no frame.
    #
    # TRef is a streamed object that nonetheless carries none: its streamer is
    # TObject::Streamer plus a pidf, and TObject::Streamer asks WriteVersion for
    # no byte count. See Buffer.md 2.3; it is checked by check_references.
    UNFRAMED = {"TFile", "TDirectory", "TRef"}

    def check_buffer_framing(self) -> None:
        for rec in self.records:
            if rec.free or rec.class_name in self.UNFRAMED:
                continue
            if rootfile.is_compressed(rec):
                continue  # this checker does not decompress
            start, end = rootfile.payload_range(rec)
            if rec.obj_len < 6:
                self.bad("Buffer 9.2", f"payload of {rec.obj_len} bytes at {rec.offset} "
                                       f"is too short for a byte count and a version")
                continue

            frame = rootfile.read_frame(self.buf, start)

            # 9.9 and 9.2 at the outermost level: the leading byte count spans
            # the payload exactly.
            if frame.byte_count is None:
                self.bad("Buffer 9.9",
                         f"{rec.class_name} at {rec.offset} has no leading byte count")
                continue
            if start + 4 + frame.byte_count != end:
                self.bad("Buffer 9.9",
                         f"{rec.class_name} at {rec.offset}: byte count {frame.byte_count} "
                         f"ends at {start + 4 + frame.byte_count}, payload ends at {end}")
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
                self.check_tlist_references(rec)

    def check_tlist_references(self, rec) -> None:
        """Buffer.md 9.5 to 9.8, over the object slots of one TList."""
        try:
            slots = rootfile.read_tlist(self.buf, rec)
        except rootfile.FormatError as exc:
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
        if t == -1 or t in (500, 501):
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
        if rootfile.is_compressed(rec):
            return  # this checker does not decompress

        try:
            infos = rootfile.read_streamer_infos(self.buf, rec)
        except (rootfile.FormatError, struct.error, IndexError, ValueError) as exc:
            self.bad("StreamerInfo 13.12", f"could not parse the record: {exc}")
            return

        by_name = {i.name: i for i in infos}
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
                    target = by_name.get(e.name)
                    if target is not None and target.checksum != e.base_checksum:
                        self.bad("StreamerInfo 13.7",
                                 f"{where}: fMaxIndex[1] 0x{e.base_checksum:08x} != "
                                 f"the base info's fCheckSum 0x{target.checksum:08x}")
                    # 13.6 of ElementTypes: -1 only for a suppressed TObject base
                    if e.ftype == -1 and e.name != "TObject":
                        self.bad("ElementTypes 11.6",
                                 f"{where}: fType -1 on a base named {e.name!r}")

                if e.cls in ("TStreamerSTL", "TStreamerSTLstring") and e.ftype != 500:
                    self.bad("StreamerInfo 13.9",
                             f"{where}: STL element fType {e.ftype}, expected 500")

                if e.cls in ("TStreamerBasicPointer", "TStreamerLoop"):
                    counter = e.tail.get("fCountName", "")
                    if not counter:
                        self.bad("StreamerInfo 13.10", f"{where}: empty fCountName")
                    elif counter not in names:
                        self.bad("StreamerInfo 13.10",
                                 f"{where}: fCountName {counter!r} names no element "
                                 f"of {si.name}")

                # 13.11
                if not 0 <= e.array_dim <= 5:
                    self.bad("StreamerInfo 13.11", f"{where}: fArrayDim {e.array_dim}")
                elif e.array_dim > 0 and e.cls != "TStreamerSTL":
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

    # -- Compression.md 9 ---------------------------------------------------
    def check_streamer_driven(self) -> None:
        """StreamerDriven.md invariants 1-4: applying the streamer info to a
        record's object data consumes exactly its length, and to a nested object
        exactly its byte count.

        Records whose class has a hand-written Streamer are reported as skipped
        rather than as failures -- that divergence is StreamerDriven.md section 7
        and is the subject of spec/03-classes/.
        """
        rec = next((r for r in self.records
                    if not r.free and r.name == "StreamerInfo"), None)
        if rec is None or rootfile.is_compressed(rec):
            return
        try:
            infos = rootfile.read_streamer_infos(self.buf, rec)
        except (rootfile.FormatError, struct.error, IndexError, ValueError):
            return  # already reported by check_streamer_info

        for info in infos:
            for where, message in element_list_failures(info):
                self.bad(where, message)

        for target in self.records:
            if target.free or rootfile.is_compressed(target):
                continue
            if target.class_name in ("TFile", "TDirectory", "TDirectoryFile"):
                continue
            try:
                rootfile.decode_record(self.buf, target, infos)
            except rootfile.UnsupportedClass:
                continue    # a hand-written Streamer; StreamerDriven.md 7
            except (rootfile.FormatError, struct.error,
                    IndexError, ValueError) as exc:
                self.bad("StreamerDriven 10.1",
                         f"{target.class_name} {target.name!r} at "
                         f"{target.offset}: {exc}")

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
            if rootfile.is_compressed(rec):
                continue
            start, _ = rootfile.payload_range(rec)
            frame = rootfile.read_frame(self.buf, start)
            name, title, _, _ = rootfile._skip_named(self.buf, frame.body)
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
            if rec.free or rootfile.is_compressed(rec):
                continue

            if rec.class_name == "TRef":
                if rec.obj_len != 12:
                    self.bad("References 8.7",
                             f"TRef payload at {rec.offset} is {rec.obj_len} bytes, "
                             f"not 12")
                    continue
                start, _ = rootfile.payload_range(rec)
                ref = rootfile.read_ref(self.buf, start)
                if not process_exists(ref.pidf, rec):
                    self.bad("References 8.2",
                             f"TRef at {rec.offset} names pidf {ref.pidf}, and no "
                             f"ProcessID{ref.pidf + rec.pid_offset} record exists")

            if rec.class_name == "TRefArray":
                start, end = rootfile.payload_range(rec)
                arr = rootfile.read_ref_array(self.buf, start)
                if arr.nobjects < 0:
                    self.bad("References 8.5",
                             f"TRefArray at {rec.offset} has nobjects {arr.nobjects}")
                elif arr.end != end:
                    self.bad("References 8.5",
                             f"TRefArray at {rec.offset} ends at {arr.end}, payload "
                             f"ends at {end}")
                if not process_exists(arr.pidf, rec):
                    self.bad("References 8.2",
                             f"TRefArray at {rec.offset} names pidf {arr.pidf}, and "
                             f"no ProcessID{arr.pidf + rec.pid_offset} record exists")

        # 8.6, over every TObject base the streamer-driven read reached.
        #
        # 8.1 -- that kIsReferenced makes the base 12 bytes rather than 10 -- is
        # not checked here, because read_tobject derives the length from the bit
        # and comparing the two would be vacuous. It is checked instead by
        # StreamerDriven 10.1/10.2: mis-reading the length desynchronises the
        # enclosing object and its byte count catches it. Confirmed by clearing
        # kIsReferenced on serialization/references, which reports
        # "TObjString v1 consumed 11 bytes, byte count says 14".
        info_rec = next((r for r in self.records
                         if not r.free and r.name == "StreamerInfo"), None)
        if info_rec is None or rootfile.is_compressed(info_rec):
            return
        try:
            infos = rootfile.read_streamer_infos(self.buf, info_rec)
        except (rootfile.FormatError, struct.error, IndexError, ValueError):
            return
        for rec in self.records:
            if rec.free or rootfile.is_compressed(rec):
                continue
            if rec.class_name in ("TFile", "TDirectory", "TDirectoryFile", "TRef"):
                continue
            try:
                tree = rootfile.decode_record(self.buf, rec, infos)
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
        rec = next((r for r in self.records
                    if not r.free and r.name == "StreamerInfo"), None)
        if rec is None or rec.class_name != "TList" or rootfile.is_compressed(rec):
            return
        try:
            entries = rootfile.read_streamer_info_entries(self.buf, rec)
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
                name, rules = rootfile.read_rule_list(self.buf, rec, slot)
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

        try:
            infos = rootfile.read_streamer_infos(self.buf, rec)
        except (rootfile.FormatError, struct.error, IndexError, ValueError):
            return
        for where, message in info_list_failures(infos):
            self.bad(where, message)

    def check_collections(self) -> None:
        """Collections.md invariants 1, 2, 3, 4 and 6.

        Invariant 5 is StreamerDriven 10.2 applied inside a collection, and is
        checked by decode_record.
        """
        rec = next((r for r in self.records
                    if not r.free and r.name == "StreamerInfo"), None)
        if rec is None or rootfile.is_compressed(rec):
            return
        try:
            infos = rootfile.read_streamer_infos(self.buf, rec)
        except (rootfile.FormatError, struct.error, IndexError, ValueError):
            return
        known = {i.name for i in infos}

        for info in infos:
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

        for target in self.records:
            if target.free or rootfile.is_compressed(target):
                continue
            if target.class_name in ("TFile", "TDirectory", "TDirectoryFile"):
                continue
            try:
                decoder, _ = rootfile.decode_record_verbose(self.buf, target, infos)
            except (rootfile.UnsupportedClass, rootfile.FormatError,
                    struct.error, IndexError, ValueError):
                continue
            for name, value, offset in decoder.member_wise:
                frame = rootfile.read_frame(self.buf, offset)
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
                if not value.startswith("pair<") and value not in known:
                    self.bad("Collections 14.6",
                             f"{name} is a member-wise collection of {value!r}, "
                             f"which has no streamer info in this file")

    def check_compression(self) -> None:
        for rec in self.records:
            if rec.free:
                continue
            payload, end = rec.payload_offset, rec.offset + rec.nbytes
            if rec.payload_nbytes == rec.obj_len:
                continue                                   # stored raw, 9.1

            produced, o, blocks = 0, payload, 0
            while o < end:
                if o + 9 > end:
                    self.bad("Compression 9.2", f"truncated block header at {o}")
                    break
                magic = self.buf[o:o+2]
                if magic not in BLOCK_MAGICS:
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
                blocks += 1
                o += 9 + comp
                if produced >= rec.obj_len:
                    break

            if produced != rec.obj_len:
                self.bad("Compression 9.3",
                         f"blocks decode to {produced} bytes, fObjlen is {rec.obj_len}")
            if o != end:
                self.bad("Compression 9.2",
                         f"block chain ends at {o}, payload ends at {end}")
            # 9.5: every block but the last carries exactly kMAXZIPBUF bytes.
            if blocks > 1 and rec.obj_len > KMAXZIPBUF:
                expected = 1 + (rec.obj_len - 1) // KMAXZIPBUF
                if blocks != expected:
                    self.bad("Compression 9.5",
                             f"{blocks} blocks for fObjlen {rec.obj_len}, expected {expected}")

    # -- Directory.md 9 -----------------------------------------------------
    def check_directories(self) -> None:
        seen_subdirs: dict[int, int] = {}
        for rec in self.records:
            d = rootfile.read_directory(self.buf, rec)
            if d is None:
                continue
            # 9.1 is what read_directory validates to identify the record at all.
            if d.fields_offset != rec.offset + d.nbytes_name:
                self.bad("Directory 9.2",
                         f"fields at {d.fields_offset}, but fSeekDir + fNbytesName "
                         f"is {rec.offset + d.nbytes_name}")
            if rec.offset != self.header.begin and d.nbytes_name != rec.key_len:
                self.bad("Directory 9.3",
                         f"subdirectory {rec.name!r}: fNbytesName {d.nbytes_name} "
                         f"!= fKeylen {rec.key_len}")
            if not 10 <= d.nbytes_name <= 10000:
                self.bad("Directory 9.4", f"fNbytesName {d.nbytes_name} outside [10, 10000]")
            if not 1 <= d.version % 1000 <= 5:
                self.bad("Directory 9.9", f"directory version {d.version}")
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
            try:
                entries = rootfile.read_key_list(self.buf, d)
            except rootfile.FormatError as exc:
                self.bad("Directory 9.6", str(exc))
                continue
            consumed = 4 + sum(e.key_len for e in entries)
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
                if e.class_name in ("TDirectory", "TDirectoryFile"):
                    if e.seek_key in seen_subdirs:
                        self.bad("Directory 9.8",
                                 f"subdirectory at {e.seek_key} listed in two parents")
                    seen_subdirs[e.seek_key] = d.seek_dir

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
        if last > KSTART_BIG_FILE and last % 1000000000 != 0:
            self.bad("FreeSegments 8.2",
                     f"last entry fLast {last} is not a multiple of 1e9 above {KSTART_BIG_FILE}")

        previous_last = None
        for f, l in segments:
            if f > l:
                self.bad("FreeSegments 8.5", f"entry ({f}, {l}) is inverted")
            if previous_last is not None and f <= previous_last + 1:
                self.bad("FreeSegments 8.5",
                         f"entry starting {f} overlaps or abuts the previous ending {previous_last}")
            previous_last = l

        interior = [(f, l) for f, l in segments if l < self.header.end]
        for f, l in interior:
            marker = struct.unpack_from(">i", self.buf, f)[0]
            expected = -min(l - f + 1, KSTART_BIG_FILE)
            if marker != expected:
                self.bad("FreeSegments 8.6",
                         f"marker at {f} is {marker}, expected {expected}")

        walked = {(r.offset, r.offset - r.nbytes - 1) for r in self.records if r.free}
        if set(interior) != walked:
            self.bad("FreeSegments 8.7",
                     f"interior entries {sorted(interior)} do not match the spans "
                     f"walked in the chain {sorted(walked)}")

        if self.header.end > len(self.buf):
            self.bad("FreeSegments 8.9",
                     f"fEND {self.header.end} exceeds the file size {len(self.buf)}")

    def run(self) -> list[str]:
        if self.records is None:
            # The chain could not be walked; report only what the header says.
            if self.header is not None:
                if self.header.end != len(self.buf):
                    self.bad("FileHeader 10.5",
                             f"fEND {self.header.end} != file size {len(self.buf)}")
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
        return self.failures


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or sorted((REPO / "data").rglob("*.root"))
    failures = []
    for path in paths:
        failures += Checker(path).run()
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    print(f"invariants checked on {len(paths)} file(s), {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
