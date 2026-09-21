#!/usr/bin/env python3
"""Tests for `tools/rootwrite.py`, the writer of `spec/06-writing/`.

Two of these are unusual and are the reason the file exists:

* `StreamerInfoBytes` builds a `StreamerInfo` record from the procedure in
  `spec/06-writing/WritingObjects.md` and asserts it is **byte-identical** to
  the one ROOT wrote in `data/container/file-minimal.root`. Every rule in that
  document is in the comparison: byte counts, version words, the class map's
  two mapping positions, `TList`'s option bytes, `TObjArray` as a pointer slot,
  the checksum in `fMaxIndex[1]`, and `kIsCompiled` in the info's own `fBits`.
* `Checksums` recomputes `fCheckSum` for every streamer info in every reference
  file and requires it to match, with a named exception list -- which is how the
  limits of recomputation in `spec/02-serialization/StreamerInfo.md` 11.2 are
  kept honest.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import rootfile  # noqa: E402
import rootwrite as rw  # noqa: E402

#: TObjString as ROOT records it, which is what file-minimal.root contains.
TOBJSTRING_INFO = rw.Info("TObjString", 1, [
    rw.Element("TStreamerBase", "TObject", "Basic ROOT object", 66, 0, "BASE",
               base_version=1, base_checksum=0x901BC02D),
    rw.Element("TStreamerString", "fString", "wrapped TString", 65, 24,
               "TString"),
])


def streamer_infos(path: pathlib.Path):
    """Every streamer info in a file, or an empty list if it has none.

    The record may be compressed, in which case `object_data` hands back a
    buffer with the payload decompressed in place. A record whose codec is not
    available in this environment is skipped rather than failing the test, the
    same convention `tools/check_invariants.py` uses.
    """
    buf, header, records = rootfile.load(path)
    if header.seek_info <= header.begin:
        return buf, None, []
    at = [r for r in records if r.offset == header.seek_info]
    if not at:
        return buf, None, []
    try:
        data = rootfile.object_data(buf, at[0])
    except rootfile.MissingCodec:
        return buf, None, []
    return data, at[0], rootfile.read_streamer_infos(data, at[0])


class StreamerInfoBytes(unittest.TestCase):
    def test_matches_root_byte_for_byte(self):
        path = REPO / "data/container/file-minimal.root"
        buf, record, infos = streamer_infos(path)
        self.assertEqual([i.name for i in infos], ["TObjString"])

        want = bytes(buf[record.offset + record.key_len:
                         record.offset + record.nbytes])
        # Map positions are measured from the start of the record, so the
        # writer needs ROOT's key length to reproduce the class tags.
        payload = rw.Payload(record.key_len)
        payload.tlist("", [TOBJSTRING_INFO.write])
        self.assertEqual(bytes(payload.buf), want)

    def test_class_map_positions(self):
        """A class is mapped at its tag, an object at its byte count."""
        payload = rw.Payload(0)
        payload.slot("TNamed", 1, lambda p: p.tnamed("a", "b"), key="first")
        payload.slot("TNamed", 1, lambda p: p.tnamed("c", "d"), key="second")
        # The first slot's byte count is at 0, so its tag is at 4 and the class
        # is mapped at 6; the object is mapped at 2.
        self.assertEqual(payload.classes["TNamed"], 6)
        self.assertEqual(payload.objects["first"], 2)
        # The second slot refers back with kClassMask | 6.
        self.assertIn(rw.u32(rw.CLASS_MASK | 6), bytes(payload.buf))


class Checksums(unittest.TestCase):
    """`fCheckSum` recomputed from each info's own elements.

    The exceptions are the substance of the test: they are the ways a checksum
    can fail to be recomputable from a record, each documented in
    `spec/02-serialization/StreamerInfo.md` 11.2 and each -- bar one --
    reproduced exactly by the tests below from the class definition instead.
    """

    #: A class-version-0 info lists only its bases, but the checksum still
    #: folds the members. test_omitted_member reproduces THashList's value.
    OMITTED_MEMBERS = {"THashList", "TSeqCollection"}
    #: Members ROOT rewrites for I/O -- std::array recorded as a fixed C array,
    #: std::unique_ptr as a plain pointer -- keep their *declared* type name in
    #: the checksum. test_transformed_type_name reproduces both values.
    TRANSFORMED = {"TF1", "CollectionForms"}
    #: ROOT's own value is wrong here: the checksum was computed before the
    #: members were known and cached forever (PLAN.md 7.1 item 8).
    PAIR_BUG = {"pair<TString,PHit*>", "pair<int,string>",
                "pair<int,vector<short> >"}
    #: Every mismatch now has a named cause. TPad used to be listed here; it
    #: was this project's own bug in the `[` locator, not ROOT's
    #: (`StreamerInfo.md` 11 step 3).
    UNEXPLAINED: set[str] = set()

    def elements_of(self, info):
        return [
            rw.Element(
                cls=e.cls, name=e.name, title=e.title, ftype=e.ftype,
                size=e.fsize, type_name=e.type_name,
                array_length=e.array_length, array_dim=e.array_dim,
                max_index=tuple(e.max_index),
                base_checksum=e.max_index[1] & 0xFFFFFFFF,
                is_enum=rw.looks_like_enum(e.ftype, e.type_name),
            )
            for e in info.elements
        ]

    def infos_named(self, path, name):
        _, _, infos = streamer_infos(REPO / path)
        return [i for i in infos if i.name == name]

    def test_every_info_in_every_reference_file(self):
        known = (self.OMITTED_MEMBERS | self.TRANSFORMED | self.PAIR_BUG
                 | self.UNEXPLAINED)
        matched, unexpected = 0, []
        for path in sorted((REPO / "data").rglob("*.root")):
            _, _, infos = streamer_infos(path)
            for info in infos:
                got = rw.checksum(rw.Info(info.name, info.class_version,
                                          self.elements_of(info)))
                if got == info.checksum:
                    matched += 1
                elif info.name not in known:
                    unexpected.append(
                        f"{path.name}: {info.name} computed 0x{got:08x}, "
                        f"file 0x{info.checksum:08x}")
        self.assertEqual(unexpected, [])
        # A floor, so adding a fixture cannot fail this; the exception list
        # above is what makes the test strict.
        self.assertGreater(matched, 690)

    def test_bracket_locator_is_strict(self):
        """Only a `[` preceded by `/` and whitespace folds into the checksum.

        `TPad` is the witness: four of its members carry a title like
        `X bottom left corner of pad in NDC [0,1]`. A plain search for `[` folds
        `0,1` and misses ROOT's value; ROOT's own locator folds nothing.
        `StreamerInfo.md` 11 step 3.
        """
        self.assertEqual(rw._counter_start("[fN] the count"), 0)
        self.assertEqual(rw._counter_start("/ [fN] after a comment slash"), 2)
        self.assertIsNone(rw._counter_start("x position [0, 1]"))
        self.assertIsNone(rw._counter_start("no brackets at all"))

        pads = self.infos_named("data/classes/canvas.root", "TPad")
        self.assertEqual(len(pads), 1)
        info = pads[0]
        self.assertTrue(any("[" in e.title for e in info.elements))
        got = rw.checksum(rw.Info(info.name, info.class_version,
                                  self.elements_of(info)))
        self.assertEqual(got, info.checksum)

    def test_reference_values(self):
        """StreamerInfo.md 11's published test vectors."""
        self.assertEqual(rw.checksum(TOBJSTRING_INFO), 0x9C8E4800)

    def test_enum_member_folds_an_extra_one(self):
        """TH1 is recomputable only because of the enum rule."""
        info = self.infos_named("data/classes/tarray-histogram.root", "TH1")[0]
        elements = self.elements_of(info)
        self.assertEqual([e.name for e in elements if e.is_enum],
                         ["fBinStatErrOpt", "fStatOverflows"])
        self.assertEqual(rw.checksum(rw.Info("TH1", 8, elements)),
                         info.checksum)
        for e in elements:
            e.is_enum = False
        self.assertNotEqual(rw.checksum(rw.Info("TH1", 8, elements)),
                            info.checksum)

    def test_omitted_member(self):
        """A version-0 class folds a member its info does not list."""
        info = self.infos_named("data/classes/tarray-histogram.root",
                                "THashList")[0]
        self.assertEqual([e.name for e in info.elements], ["TList"])
        elements = self.elements_of(info) + [
            rw.Element("TStreamerObjectPointer", "fTable", "", 64, 8,
                       "THashTable*"),
        ]
        self.assertEqual(rw.checksum(rw.Info("THashList", 0, elements)),
                         info.checksum)

    def test_transformed_type_name(self):
        """std::array and std::unique_ptr keep their declared spelling."""
        info = self.infos_named("data/serialization/collection-forms.root",
                                "CollectionForms")[0]
        elements = self.elements_of(info)
        for e in elements:
            if e.name == "fArrInt":
                e.type_name, e.array_dim = "array<int,3>", 0
            elif e.name == "fArrHit":
                e.type_name, e.array_dim = "array<CHit,2>", 0
        self.assertEqual(rw.checksum(rw.Info("CollectionForms", 1, elements)),
                         info.checksum)

        info = self.infos_named("data/classes/formula.root", "TF1")[0]
        elements = self.elements_of(info)
        for e in elements:
            if e.type_name.endswith("*") and e.name in (
                    "fFormula", "fParams", "fComposition"):
                inner = e.type_name[:-1]
                # The default template argument is spelled out, which is what
                # makes this unguessable from the record.
                e.type_name = f"unique_ptr<{inner},default_delete<{inner}> >"
        self.assertEqual(rw.checksum(rw.Info("TF1", 12, elements)),
                         info.checksum)

    def test_the_three_pairs_share_one_wrong_value(self):
        """PLAN.md 7.1 item 8, from the other direction."""
        _, _, infos = streamer_infos(REPO / "data/serialization/pairs.root")
        pairs = [i for i in infos if i.name.startswith("pair<")]
        self.assertEqual(len(pairs), 4)
        shared = [i for i in pairs if i.checksum == 0x0B5FB752]
        self.assertEqual(len(shared), 3)
        # Three distinct layouts, three distinct recomputed values, none of
        # them the one ROOT wrote -- and the fourth pair, which escaped the
        # caching, is recomputable like any other class.
        computed = {rw.checksum(rw.Info(i.name, 1, self.elements_of(i)))
                    for i in shared}
        self.assertEqual(len(computed), 3)
        self.assertNotIn(0x0B5FB752, computed)
        fourth = [i for i in pairs if i.checksum != 0x0B5FB752][0]
        self.assertEqual(
            rw.checksum(rw.Info(fourth.name, 1, self.elements_of(fourth))),
            fourth.checksum)


class Histograms(unittest.TestCase):
    """The writer's histograms against the ones ROOT wrote.

    `data/classes/histogram.root` and `data/written/histogram.root` hold the
    same two histograms, one written by ROOT and one by this project. Every
    object-bearing record in them is byte-identical, which is what
    `spec/06-writing/WritingHistograms.md` rests on.
    """

    def records(self, path):
        buf, header, records = rootfile.load(REPO / path)
        return buf, header, {r.name: r for r in records}

    def payload(self, buf, rec):
        return bytes(buf[rec.offset + rec.key_len: rec.offset + rec.nbytes])

    def test_th1f_record_is_identical(self):
        root_buf, _, root_recs = self.records("data/classes/histogram.root")
        axis = rw.Axis(nbins=3, xmin=0.0, xmax=3.0)
        cells = [1.0, 2.0, 1.0, 0.0, 1.0]
        sumw2 = [1.0, 2.0, 1.0, 0.0, 1.0]
        hist = rw.Hist1D("h1", "three bins", axis, cells,
                         rw.stats_from_cells(cells, axis, sumw2),
                         sumw2=sumw2, kind="F")
        rec = root_recs["h1"]
        self.assertEqual(hist.payload(rec.key_len), self.payload(root_buf, rec))

    def test_th1d_record_is_identical(self):
        root_buf, _, root_recs = self.records("data/classes/histogram.root")
        edges = [0.0, 1.0, 4.0, 10.0]
        axis = rw.Axis(nbins=3, xmin=0.0, xmax=10.0, edges=edges)
        cells = [0.0, 2.0, 0.0, 0.5, 0.0]
        sumw2 = [0.0, 4.0, 0.0, 0.25, 0.0]
        # Supplied, not derived: fEntries counts fills and the x moments
        # remember where inside a bin each fill landed.
        stats = rw.Stats(entries=2.0, tsumw=2.5, tsumw2=4.25, tsumwx=3.5,
                         tsumwx2=13.0)
        hist = rw.Hist1D("h2", "variable bins", axis, cells, stats,
                         sumw2=sumw2, kind="D")
        rec = root_recs["h2"]
        self.assertEqual(hist.payload(rec.key_len), self.payload(root_buf, rec))

    def test_statistics_from_bin_contents(self):
        """Derivable when the weights are 1 and the fills sit at bin centres."""
        axis = rw.Axis(nbins=3, xmin=0.0, xmax=3.0)
        cells = [1.0, 2.0, 1.0, 0.0, 1.0]
        sumw2 = [1.0, 2.0, 1.0, 0.0, 1.0]
        st = rw.stats_from_cells(cells, axis, sumw2)
        self.assertEqual((st.entries, st.tsumw, st.tsumw2, st.tsumwx,
                          st.tsumwx2), (5.0, 3.0, 3.0, 2.5, 2.75))
        # Without fSumw2, unit weights are assumed, so fTsumw2 equals fTsumw.
        self.assertEqual(rw.stats_from_cells(cells, axis).tsumw2, 3.0)

    def test_streamer_info_record_is_identical(self):
        """All fifteen infos, and ROOT's own order."""
        root_buf, header, _ = self.records("data/classes/histogram.root")
        _, _, records = rootfile.load(REPO / "data/classes/histogram.root")
        rec = [r for r in records if r.offset == header.seek_info][0]
        payload = rw.Payload(rec.key_len)
        payload.tlist("", [i.write for i in rw.histogram_infos(("TH1F", "TH1D"))])
        self.assertEqual(bytes(payload.buf), self.payload(root_buf, rec))

    def test_infos_match_roots_element_by_element(self):
        """Including fSize, which is deliberate.

        `fSize` is `sizeof` on the writing machine, so this is the assertion
        that would fail first if a standard library disagreed with the values
        `tools/rootwrite.py` hardcodes -- `sizeof(TAxis)` 216,
        `sizeof(TString)` 24. A reader must never use the field
        (`StreamerInfo.md` 7); a writer still has to put something in it, and
        putting ROOT's value there is what keeps the records comparable.
        """
        _, _, infos = streamer_infos(REPO / "data/classes/histogram.root")
        theirs = {i.name: i for i in infos}
        ours = {i.name: i for i in rw.histogram_infos(("TH1F", "TH1D"))}
        self.assertEqual(list(ours), [i.name for i in infos])
        for name, mine in ours.items():
            self.assertEqual(mine.checksum, theirs[name].checksum,
                             f"{name} checksum")
            self.assertEqual(len(mine.elements), len(theirs[name].elements),
                             f"{name} element count")
            for a, b in zip(mine.elements, theirs[name].elements):
                self.assertEqual(
                    (a.cls, a.name, a.title, a.ftype, a.type_name, a.size),
                    (b.cls, b.name, b.title, b.ftype, b.type_name, b.fsize),
                    f"{name}.{a.name}")

    def test_cell_count_is_checked(self):
        axis = rw.Axis(nbins=3, xmin=0.0, xmax=3.0)
        with self.assertRaises(rw.WriteError):
            rw.Hist1D("h", "", axis, [0.0] * 4, rw.Stats())
        with self.assertRaises(rw.WriteError):
            rw.Hist1D("h", "", axis, [0.0] * 5, rw.Stats(), sumw2=[0.0] * 3)


class Derived(unittest.TestCase):
    """`TH2F`, `TH2D` and `TProfile` against the ones ROOT wrote.

    `data/classes/th2-profile.root` and `data/written/th2-profile.root` hold the
    same four objects. All four data records are byte-identical; the
    `StreamerInfo` record is identical up to the `listOfRules` ROOT appends for
    `TProfile` (`WritingHistograms.md` 8.6), which is the one entry a file
    written at version 7 cannot use.
    """

    #: The axes and arrays of each object, built the way the case builds them.
    def objects(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "th2_profile_build", REPO / "gen/written/th2-profile/build.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def payload(self, buf, rec):
        return bytes(buf[rec.offset + rec.key_len: rec.offset + rec.nbytes])

    def records(self, path):
        buf, _, records = rootfile.load(REPO / path)
        return buf, {r.name: r for r in records}

    def test_records_are_identical_to_roots(self):
        """All four, in one pass, so a name that vanishes fails rather than passes."""
        root_buf, root_recs = self.records("data/classes/th2-profile.root")
        mine_buf, mine_recs = self.records("data/written/th2-profile.root")
        # The two directory records differ in name, which is the whole
        # difference between the files.
        self.assertEqual(sorted(k for k in root_recs if not k.endswith(".root")),
                         sorted(k for k in mine_recs if not k.endswith(".root")))
        for name in ("h2f", "h2d", "p1", "p2"):
            with self.subTest(name):
                self.assertEqual(self.payload(mine_buf, mine_recs[name]),
                                 self.payload(root_buf, root_recs[name]))

    def test_streamer_info_record_matches_up_to_the_rules(self):
        root_data, root_rec, theirs = streamer_infos(
            REPO / "data/classes/th2-profile.root")
        mine_data, mine_rec, ours = streamer_infos(
            REPO / "data/written/th2-profile.root")
        # Eighteen infos against eighteen; ROOT's record holds a nineteenth
        # entry that is not an info.
        self.assertEqual([i.name for i in ours], [i.name for i in theirs])
        self.assertEqual(len(ours), 18)
        mine = self.payload(mine_data, mine_rec)
        theirs_bytes = self.payload(root_data, root_rec)
        self.assertLess(len(mine), len(theirs_bytes))
        # The first 21 bytes carry the entry count, which differs by one.
        self.assertEqual(mine[21:], theirs_bytes[21:len(mine)])

    def test_infos_match_roots_element_by_element(self):
        _, _, infos = streamer_infos(REPO / "data/classes/th2-profile.root")
        theirs = {i.name: i for i in infos}
        ours = {i.name: i
                for i in rw.histogram_infos(("TH2F", "TH2D", "TProfile"))}
        self.assertEqual(list(ours), [i.name for i in infos])
        for name, mine in ours.items():
            self.assertEqual(mine.checksum, theirs[name].checksum,
                             f"{name} checksum")
            self.assertEqual(len(mine.elements), len(theirs[name].elements),
                             f"{name} element count")
            for a, b in zip(mine.elements, theirs[name].elements):
                self.assertEqual(
                    (a.cls, a.name, a.title, a.ftype, a.type_name, a.size),
                    (b.cls, b.name, b.title, b.ftype, b.type_name, b.fsize),
                    f"{name}.{a.name}")

    def test_error_mode_is_an_enum_in_the_checksum(self):
        """Drop the enum rule and TProfile's checksum stops being ROOT's."""
        profile = {i.name: i
                   for i in rw.histogram_infos(("TProfile",))}["TProfile"]
        self.assertEqual(profile.checksum, 0x4BEDEE54)
        mode = [e for e in profile.elements if e.name == "fErrorMode"][0]
        self.assertTrue(rw.looks_like_enum(mode.ftype, mode.type_name))
        plain = rw.Info(profile.name, profile.class_version, profile.elements)
        mode.type_name = "int"
        self.assertNotEqual(rw.checksum(plain), 0x4BEDEE54)
        mode.type_name = "EErrorType"

    def test_two_dimensional_statistics_are_derived_from_the_cells(self):
        """The in-range region is a rectangle, not "all but the ends"."""
        module = self.objects()
        xaxis = rw.Axis(nbins=3, xmin=0.0, xmax=3.0)
        yaxis = rw.Axis(name="yaxis", nbins=2, xmin=0.0, xmax=2.0)
        cells = module.cells(3, 2, {(1, 1): 2.0, (3, 1): 1.0, (2, 2): 1.0,
                                   (0, 1): 1.0, (1, 3): 1.0})
        st = rw.stats_from_cells_2d(cells, xaxis, yaxis, cells)
        # ROOT's own values for the same six fills.
        self.assertEqual(
            (st.entries, st.tsumw, st.tsumw2, st.tsumwx, st.tsumwx2,
             st.tsumwy, st.tsumwy2, st.tsumwxy),
            (6.0, 4.0, 4.0, 5.0, 9.0, 3.0, 3.0, 4.0))

    def test_a_profiles_statistics_are_derivable_but_its_entries_are_not(self):
        axis = rw.Axis(nbins=2, xmin=0.0, xmax=2.0)
        sumwy = [0.0, 9.0, 2.0, 0.0]
        sumwy2 = [0.0, 30.0, 8.0, 0.0]
        entries = [0.0, 3.5, 0.5, 0.0]
        bin_sumw2 = [0.0, 9.25, 0.25, 0.0]
        st = rw.stats_from_profile(sumwy, sumwy2, entries, axis,
                                   bin_sumw2=bin_sumw2)
        # Five of the six are exact, because a profile stores sum(w*y) and
        # sum(w*y*y) per cell rather than throwing them away.
        self.assertEqual((st.tsumw, st.tsumw2, st.tsumwx, st.tsumwx2,
                          st.tsumwy, st.tsumwy2),
                         (4.0, 9.5, 2.5, 2.0, 11.0, 38.0))
        # fEntries counts fills, and three weighted fills sum to 4.
        self.assertEqual(st.entries, 4.0)

    def test_the_cell_index_is_x_major(self):
        self.assertEqual(rw.cell_index(0, 0, 3), 0)
        self.assertEqual(rw.cell_index(4, 0, 3), 4)   # the x overflow of row 0
        self.assertEqual(rw.cell_index(1, 1, 3), 6)
        self.assertEqual(rw.cell_index(1, 3, 3), 16)  # the y overflow row
        with self.assertRaises(rw.WriteError):
            rw.cell_index(5, 0, 3)

    def test_shapes_are_checked(self):
        xaxis = rw.Axis(nbins=3, xmin=0.0, xmax=3.0)
        yaxis = rw.Axis(name="yaxis", nbins=2, xmin=0.0, xmax=2.0)
        with self.assertRaises(rw.WriteError):
            # 5 + 2 rather than (3 + 2) * (2 + 2).
            rw.Hist2D("h", "", xaxis, [0.0] * 7, rw.Stats(), yaxis=yaxis)
        with self.assertRaises(rw.WriteError):
            rw.Hist2D("h", "", xaxis, [0.0] * 20, rw.Stats())
        with self.assertRaises(rw.WriteError):
            # A profile's fSumw2 and fBinEntries are never absent.
            rw.Profile("p", "", xaxis, [0.0] * 5, rw.Stats())

    def test_the_y_axis_title_offset_is_zero_by_name(self):
        """gStyle's per-axis default, and the one asymmetry in the three blocks."""
        self.assertEqual(rw.Axis(name="xaxis").title_offset, 1.0)
        self.assertEqual(rw.Axis(name="yaxis").title_offset, 0.0)
        self.assertEqual(rw.Axis(name="zaxis").title_offset, 1.0)
        self.assertEqual(rw.Axis(name="yaxis", title_offset=1.0).title_offset,
                         1.0)


class Trees(unittest.TestCase):
    """The writer's tree against the one ROOT wrote.

    `data/ttree/basket.root` and `data/written/tree.root` hold the same tree,
    and both basket records and the `TTree` record are byte-identical -- keys
    included, once the wall-clock timestamp is masked. The file names are the
    same length on purpose, because a branch stores its baskets' offsets.
    """

    def build(self):
        tree = rw.Tree("t", "a tree")
        n = tree.branch("n", "I")
        tree.branch("a", "F", counter=n)
        for i in range(3):
            tree.fill({"n": i + 1, "a": [float(i)] * (i + 1)})
        return tree

    def written(self):
        f = rw.FileWriter("data/written/tree.root", "basket layouts")
        for record in self.build().records():
            f.add(record)
        for info in rw.tree_infos(("I", "F")):
            f.add_info(info)
        return f.to_bytes()

    @staticmethod
    def mask_datime(record: bytes) -> bytes:
        """A key's fDatime is four bytes at offset 10 (`Record.md` 2)."""
        return record[:10] + b"\x00" * 4 + record[14:]

    def test_records_are_identical_to_roots(self):
        ours = self.written()
        root_buf, _, root_recs = rootfile.load(REPO / "data/ttree/basket.root")
        header = rootfile.read_header(ours)
        our_recs = rootfile.read_records(ours, header)
        wanted = [(r.class_name, r.name) for r in root_recs
                  if r.class_name in ("TBasket", "TTree")]
        self.assertEqual(
            [(r.class_name, r.name) for r in our_recs
             if r.class_name in ("TBasket", "TTree")], wanted)
        for cls, name in wanted:
            a = [r for r in root_recs
                 if r.class_name == cls and r.name == name][0]
            b = [r for r in our_recs
                 if r.class_name == cls and r.name == name][0]
            self.assertEqual(a.offset, b.offset, f"{cls} {name} offset")
            self.assertEqual(
                self.mask_datime(bytes(root_buf[a.offset:a.offset + a.nbytes])),
                self.mask_datime(bytes(ours[b.offset:b.offset + b.nbytes])),
                f"{cls} {name} record")

    def test_basket_key_is_the_large_form(self):
        basket = self.build().branches[0].basket()
        self.assertEqual(basket.key_version, 1004)
        self.assertEqual(len(basket.key_extra), 19)
        # fCycle is the basket number, and nothing reads it.
        self.assertEqual(basket.cycle, 0)
        # And a basket is never in the directory's key list.
        self.assertFalse(basket.in_key_list)

    def test_offset_array_only_when_entries_vary(self):
        tree = self.build()
        n, a = tree.branches
        self.assertFalse(n.variable)
        self.assertTrue(a.variable)
        # The count is fNevBuf + 1 and the last element is never read.
        payload = a.basket().payload
        self.assertEqual(len(payload), 24 + 4 + 16)
        self.assertEqual(payload[24:28], rw.i32(4))
        self.assertEqual(payload[-4:], rw.i32(0))

    def test_entry_offset_len_is_shrunk_at_flush(self):
        tree = self.build()
        a = tree.branches[1]
        self.assertEqual(a.entry_offset_len, 1000)
        self.assertEqual(a.flushed_entry_offset_len(), 12)

    def test_counter_leaf_carries_is_range_and_the_maximum(self):
        tree = self.build()
        n, a = tree.branches
        self.assertTrue(n.leaf.is_range)
        self.assertFalse(a.leaf.is_range)
        self.assertEqual(n.leaf.maximum, 3)
        self.assertIs(a.leaf.counter, n.leaf)

    def test_a_count_mismatch_is_refused(self):
        tree = self.build()
        with self.assertRaises(rw.WriteError):
            tree.fill({"n": 2, "a": [1.0]})
        with self.assertRaises(rw.WriteError):
            tree.fill({"n": 1})

    def test_infos_match_roots(self):
        _, _, infos = streamer_infos(REPO / "data/ttree/basket.root")
        theirs = {i.name: i for i in infos}
        ours = {i.name: i for i in rw.tree_infos(("I", "F"))}
        self.assertEqual(list(ours), [i.name for i in infos])
        for name, mine in ours.items():
            self.assertEqual(mine.checksum, theirs[name].checksum,
                             f"{name} checksum")
            self.assertEqual(
                [(e.cls, e.name, e.title, e.ftype, e.type_name, e.size)
                 for e in mine.elements],
                [(e.cls, e.name, e.title, e.ftype, e.type_name, e.fsize)
                 for e in theirs[name].elements], name)

    def test_streamer_info_entries_are_identical(self):
        """All eighteen infos, byte for byte, against ROOT's own record.

        The two records cannot be compared whole: ROOT's carries a nineteenth
        entry of I/O rules that a file written at version 20 cannot use
        (below). Everything before it is identical -- which is a stricter claim
        than the element-by-element comparison above, because it also covers the
        subclass tail of every element, and `tools/element_lists.py` found four
        wrong values there that nothing else looked at.
        """
        ours = self.written()
        root_buf, _, root_recs = rootfile.load(REPO / "data/ttree/basket.root")
        header = rootfile.read_header(root_buf)
        rec = [r for r in root_recs if r.offset == header.seek_info][0]
        data = rootfile.object_data(root_buf, rec)
        theirs = bytes(data[rec.offset + rec.key_len:rec.offset + rec.nbytes])
        payload = rw.Payload(rec.key_len)
        payload.tlist("", [i.write for i in rw.tree_infos(("I", "F"))])
        mine = bytes(payload.buf)
        # The TList's own header differs in two fields and nothing else: its
        # byte count, and 18 entries against 19.
        self.assertEqual(mine[21:], theirs[21:len(mine)])
        self.assertEqual(rw.i32(18), mine[17:21])
        self.assertEqual(rw.i32(19), theirs[17:21])

    def test_root_appends_two_obsolete_io_rules(self):
        """The one difference between the two StreamerInfo records.

        ROOT's list has a nineteenth entry, a `listOfRules` of two read rules
        for `TTree` versions <= 16 and <= 18. A file written at version 20
        cannot use them, so the writer omits them -- which is why only this
        record differs between the two files.
        """
        buf, _, records = rootfile.load(REPO / "data/ttree/basket.root")
        header = rootfile.read_header(buf)
        rec = [r for r in records if r.offset == header.seek_info][0]
        slots = rootfile.read_tlist(buf, rec)
        self.assertEqual(len(slots), 19)
        name, rules = rootfile.read_rule_list(buf, rec, slots[-1])
        self.assertEqual(name, "listOfRules")
        self.assertEqual(len(rules), 2)
        for rule in rules:
            self.assertIn('sourceClass="TTree"', rule)


class Clusters(unittest.TestCase):
    """Five baskets in one branch, against the five ROOT wrote.

    `data/ttree/clusters.root` and `data/written/cluster.root` hold the same
    nineteen entries in the same five baskets with the same two cluster ranges,
    and every basket record and the `TTree` record is byte-identical. That is
    what covers the three counted arrays at a length other than 1 -- five
    `fBasketSeek` values, five `fBasketBytes`, six `fBasketEntry` and the zero
    padding to `fMaxBaskets` -- and both cluster arrays.
    """

    def written(self) -> bytes:
        import importlib.util
        path = REPO / "gen/written/cluster/build.py"
        spec = importlib.util.spec_from_file_location("cluster_build", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.build()

    @staticmethod
    def mask_datime(record: bytes) -> bytes:
        return record[:10] + b"\x00" * 4 + record[14:]

    def test_records_are_identical_to_roots(self):
        ours = self.written()
        root_buf, _, root_recs = rootfile.load(REPO / "data/ttree/clusters.root")
        header = rootfile.read_header(ours)
        our_recs = rootfile.read_records(ours, header)
        wanted = [(r.class_name, r.offset, r.nbytes) for r in root_recs
                  if r.class_name in ("TBasket", "TTree")]
        self.assertEqual(
            [(r.class_name, r.offset, r.nbytes) for r in our_recs
             if r.class_name in ("TBasket", "TTree")], wanted)
        self.assertEqual(len(wanted), 6)
        for cls, offset, nbytes in wanted:
            self.assertEqual(
                self.mask_datime(bytes(root_buf[offset:offset + nbytes])),
                self.mask_datime(bytes(ours[offset:offset + nbytes])),
                f"{cls} at {offset}")

    def test_cluster_ranges_close_on_a_changed_watermark(self):
        """And only when a flush has already happened."""
        tree = rw.Tree("t", "", auto_flush=4)
        tree.branch("x", "I")
        # Before any flush, changing the watermark records nothing: ROOT's
        # condition is fFlushedBytes, not fEntries (TTree.cxx:8452).
        for i in range(4):
            tree.fill({"x": i})
        tree.set_auto_flush(3)
        self.assertEqual(tree.cluster_range_end, [])
        self.assertEqual(tree.auto_flush, 3)
        tree.flush()
        for i in range(4, 7):
            tree.fill({"x": i})
        tree.set_auto_flush(5)
        # fEntries is 7, so the range ends at 6, and its size is the *old*
        # watermark.
        self.assertEqual(tree.cluster_range_end, [6])
        self.assertEqual(tree.cluster_size, [3])

    def branch_of(self, baskets: int):
        """Read back the branch of a tree written with `baskets` baskets."""
        tree = rw.Tree("t", "")
        tree.branch("x", "I")
        for i in range(baskets):
            tree.fill({"x": i})
            tree.flush()
        records = tree.records()
        self.assertEqual(len([r for r in records
                              if r.class_name == "TBasket"]), baskets)
        f = rw.FileWriter("data/written/x.root")
        for record in records:
            f.add(record)
        for info in rw.tree_infos(("I",)):
            f.add_info(info)
        buf = f.to_bytes()
        header = rootfile.read_header(buf)
        recs = rootfile.read_records(buf, header)
        rec = [r for r in recs if r.class_name == "TTree"][0]
        at = [r for r in recs if r.offset == header.seek_info][0]
        all_infos = rootfile.read_streamer_infos(
            rootfile.object_data(buf, at), at)
        value = rootfile.decode_record(buf, rec, all_infos)
        return rootfile.read_tree(buf, value, rec.offset).branches[0]

    def test_max_baskets_is_the_floor_or_one_past_the_last(self):
        """10 until there are ten baskets, then fWriteBasket + 1.

        The three arrays are that long whichever it is, and the count is what a
        reader parses the record with, so getting it wrong desynchronises
        everything after `fBaskets` (`WritingTrees.md` 4).
        """
        few = self.branch_of(3)
        self.assertEqual((few.write_basket, few.max_baskets), (3, 10))
        self.assertEqual(len(few.basket_entry), 10)
        # One element past the last basket is the terminator; the rest is zero.
        self.assertEqual(few.basket_entry[:5], [0, 1, 2, 3, 0])
        self.assertEqual(few.basket_bytes[3:], [0] * 7)

        many = self.branch_of(12)
        self.assertEqual((many.write_basket, many.max_baskets), (12, 13))
        self.assertEqual(len(many.basket_entry), 13)
        self.assertEqual(many.basket_entry[12], 12)
        self.assertEqual(many.basket_bytes[12], 0)


class Compression(unittest.TestCase):
    def test_block_round_trips_through_the_reader(self):
        data = b"hello " * 400
        blocks = rw.zlib_blocks(data, 1)
        self.assertIsNotNone(blocks)
        self.assertEqual(blocks[:3], b"ZL\x08")
        # The compressed size excludes the 9-byte header (Compression.md 4).
        self.assertEqual(9 + int.from_bytes(blocks[3:6], "little"), len(blocks))
        self.assertEqual(int.from_bytes(blocks[6:9], "little"), len(data))
        self.assertEqual(
            rootfile.decompress_blocks(blocks, 0, len(blocks), len(data),
                                       "test"),
            data)

    def test_incompressible_payload_is_declined(self):
        import os
        self.assertIsNone(rw.zlib_blocks(os.urandom(4096), 9))


class Graphs(unittest.TestCase):
    """`TGraph` and `TGraphErrors` against the ones ROOT wrote.

    `data/written/graph.root` and `data/classes/graph.root` hold the same two
    objects under the same names, and both records are byte-identical -- as is the
    **whole** `StreamerInfo` record, all 12169 bytes of nineteen infos, which no
    other written case can say: the tree and profile files differ by the
    `listOfRules` entry ROOT appends and this one has none.
    """

    ROOTS = "data/classes/graph.root"
    MINE = "data/written/graph.root"

    X = [0.0, 1.0, 2.0, 3.0]
    Y = [0.5, 2.5, -1.0, 4.0]
    EX = [0.1, 0.1, 0.2, 0.2]
    EY = [0.25, 0.5, 0.25, 0.5]

    def objects(self):
        return {"g": rw.Graph("g", "four points", self.X, self.Y),
                "gr": rw.Graph("gr", "with errors", self.X, self.Y,
                               ex=self.EX, ey=self.EY)}

    def test_records_are_identical_to_roots(self):
        """A graph stores no offsets, so only the key length has to match."""
        root_buf, _, root_recs = rootfile.load(REPO / self.ROOTS)
        by_name = {r.name: r for r in root_recs}
        for name, graph in self.objects().items():
            with self.subTest(name):
                rec = by_name[name]
                key_len = rw.Key(class_name=graph.class_name, name=graph.name,
                                 title=graph.title, obj_len=0, nbytes=0,
                                 seek_key=0, seek_pdir=rw.BEGIN).key_len
                self.assertEqual(key_len, rec.key_len)
                self.assertEqual(
                    graph.payload(key_len),
                    bytes(root_buf[rec.offset + rec.key_len:
                                   rec.offset + rec.nbytes]))

    def test_the_whole_streamer_info_record_is_identical(self):
        root_data, root_rec, theirs = streamer_infos(REPO / self.ROOTS)
        mine_data, mine_rec, ours = streamer_infos(REPO / self.MINE)
        self.assertEqual([i.name for i in ours], [i.name for i in theirs])
        self.assertEqual(len(ours), 19)
        payload = lambda d, r: bytes(d[r.offset + r.key_len:
                                      r.offset + r.nbytes])
        self.assertEqual(payload(mine_data, mine_rec),
                         payload(root_data, root_rec))

    def test_infos_match_roots_element_by_element(self):
        _, _, infos = streamer_infos(REPO / self.ROOTS)
        theirs = {i.name: i for i in infos}
        ours = {i.name: i
                for i in rw.graph_infos(("TGraph", "TGraphErrors"))}
        self.assertEqual(list(ours), [i.name for i in infos])
        for name, mine in ours.items():
            with self.subTest(name):
                self.assertEqual(mine.checksum, theirs[name].checksum)
                self.assertEqual(mine.class_version,
                                 theirs[name].class_version)

    def test_a_graph_file_describes_the_tarray_family(self):
        """Which a histogram file does not (`WritingGraphs.md` 5)."""
        names = [i.name for i in rw.graph_infos()]
        for cls in ("TArray", "TArrayF", "TArrayD", "TH1F", "TH1"):
            self.assertIn(cls, names, cls)
        hist = [i.name for i in rw.histogram_infos(("TH1F",))]
        for cls in ("TArray", "TArrayF", "TArrayD"):
            self.assertNotIn(cls, hist, cls)

    def test_the_attribute_defaults_are_not_a_histograms(self):
        self.assertEqual(rw.GRAPH_LINE_DEFAULTS, (1, 1, 1))
        self.assertEqual(rw.LINE_DEFAULTS, (602, 1, 1))
        self.assertEqual(rw.GRAPH_FILL_DEFAULTS, (0, 1000))
        self.assertEqual(rw.FILL_DEFAULTS, (0, 1001))
        # kClipFrame, and no kMustCleanup.
        self.assertEqual(rw.GRAPH_BITS, 0x400)
        self.assertEqual(rw.GRAPH_BITS & rw.K_MUST_CLEANUP, 0)

    def test_the_sentinel_is_th1s(self):
        g = rw.Graph("g", "", [], [])
        self.assertEqual(g.minimum, -1111.0)
        self.assertEqual(g.maximum, -1111.0)
        self.assertEqual(rw.GRAPH_UNSET, rw.NO_LIMIT)

    def test_an_empty_graph_writes_the_flag_alone(self):
        g = rw.Graph("g", "", [], [])
        self.assertEqual(rw.counted_pointer([]), b"\x01")
        payload = g.payload(47)
        # fNpoints 0, then two flag bytes and no values.
        self.assertIn(b"\x00\x00\x00\x00\x01\x01", payload)

    def test_mismatched_arrays_are_refused(self):
        with self.assertRaises(rw.WriteError):
            rw.Graph("g", "", [1.0, 2.0], [1.0])
        with self.assertRaises(rw.WriteError):
            rw.Graph("g", "", [1.0], [1.0], ex=[0.1])          # ey missing
        with self.assertRaises(rw.WriteError):
            rw.Graph("g", "", [1.0], [1.0], ex=[0.1, 0.2], ey=[0.1, 0.2])
        with self.assertRaises(rw.WriteError):
            rw.Graph("g", "", [1.0], [1.0], minimum=5.0, maximum=-5.0)

    def test_a_tgrapherrors_is_a_tgraph_plus_two_arrays(self):
        plain = rw.Graph("g", "t", self.X, self.Y)
        errors = rw.Graph("g", "t", self.X, self.Y, ex=self.EX, ey=self.EY)
        self.assertEqual(plain.class_name, "TGraph")
        self.assertEqual(errors.class_name, "TGraphErrors")
        # The TGraph block is unchanged; the frame and two arrays are added.
        self.assertEqual(len(errors.payload(47)),
                         len(plain.payload(47)) + 6 + 2 * (1 + 32))


class LeafC(unittest.TestCase):
    """A `TLeafC` branch against `data/ttree/strings.root`.

    `data/written/leafc.root` holds the same two branches and the same three
    strings -- `"ab"`, the empty one, and 300 characters -- and both basket
    records and the whole `TTree` record are byte-identical to ROOT's, keys
    included, once the timestamp is masked. The two file names are the same
    length because a branch stores its baskets' offsets.
    """

    ROOTS = "data/ttree/strings.root"
    MINE = "data/written/leafc.root"

    def build(self):
        tree = rw.Tree("t", "a tree")
        tree.branch("n", "I")
        tree.branch("s", "C")
        for i, text in enumerate(("ab", "", "x" * 300)):
            tree.fill({"n": i + 1, "s": text})
        return tree

    def written(self):
        f = rw.FileWriter("data/written/leafc.root", "string leaves")
        for record in self.build().records():
            f.add(record)
        for info in rw.tree_infos(("I", "C")):
            f.add_info(info)
        return f.to_bytes()

    def test_records_are_identical_to_roots(self):
        ours = self.written()
        root_buf, _, root_recs = rootfile.load(REPO / self.ROOTS)
        our_recs = rootfile.read_records(ours, rootfile.read_header(ours))
        wanted = [(r.class_name, r.name) for r in root_recs
                  if r.class_name in ("TBasket", "TTree")]
        self.assertEqual([(r.class_name, r.name) for r in our_recs
                          if r.class_name in ("TBasket", "TTree")], wanted)
        self.assertEqual(wanted, [("TBasket", "n"), ("TBasket", "s"),
                                  ("TTree", "t")])
        for cls, name in wanted:
            a = [r for r in root_recs
                 if r.class_name == cls and r.name == name][0]
            b = [r for r in our_recs
                 if r.class_name == cls and r.name == name][0]
            self.assertEqual(a.offset, b.offset, f"{cls} {name} offset")
            self.assertEqual(
                Trees.mask_datime(bytes(root_buf[a.offset:a.offset + a.nbytes])),
                Trees.mask_datime(bytes(ours[b.offset:b.offset + b.nbytes])),
                f"{cls} {name} record")

    def test_streamer_info_matches_up_to_the_rules(self):
        """Eighteen infos against eighteen, TLeafC's checksum included."""
        root_data, root_rec, theirs = streamer_infos(REPO / self.ROOTS)
        mine_data, mine_rec, ours = streamer_infos(REPO / self.MINE)
        self.assertEqual([i.name for i in ours], [i.name for i in theirs])
        self.assertIn("TLeafC", [i.name for i in ours])
        payload = lambda d, r: bytes(d[r.offset + r.key_len:
                                      r.offset + r.nbytes])
        mine, theirs_bytes = payload(mine_data, mine_rec), payload(root_data,
                                                                  root_rec)
        self.assertLess(len(mine), len(theirs_bytes))
        # The first 21 bytes carry the byte count and the entry count, which
        # differs by the one listOfRules entry ROOT appends.
        self.assertEqual(mine[21:], theirs_bytes[21:len(mine)])

    def test_tleafc_checksum_is_roots(self):
        _, _, infos = streamer_infos(REPO / self.ROOTS)
        theirs = {i.name: i for i in infos}["TLeafC"]
        mine = {i.name: i for i in rw.tree_infos(("C",))}["TLeafC"]
        self.assertEqual(mine.checksum, theirs.checksum)
        self.assertEqual(mine.checksum, rw.checksum(mine))

    # -- the three entry forms -------------------------------------------

    def test_an_empty_string_writes_no_bytes(self):
        leaf = rw.Leaf(name="s", kind="C")
        self.assertEqual(leaf.pack(""), b"")
        self.assertEqual(leaf.pack("ab"), b"\x02ab")

    def test_the_long_form_uses_the_255_escape(self):
        leaf = rw.Leaf(name="s", kind="C")
        packed = leaf.pack("x" * 300)
        self.assertEqual(len(packed), 305)
        self.assertEqual(packed[0], 255)
        self.assertEqual(int.from_bytes(packed[1:5], "big"), 300)
        self.assertEqual(packed[5:], b"x" * 300)
        # 254 is still the short form; 255 is the first that is not.
        self.assertEqual(len(leaf.pack("y" * 254)), 255)
        self.assertEqual(len(leaf.pack("y" * 255)), 260)

    def test_the_offset_array_repeats_for_an_empty_entry(self):
        """Read out of the finished file, where a reader would find it."""
        buf, _, records = rootfile.load(REPO / self.MINE)
        rec = [r for r in records
               if r.class_name == "TBasket" and r.name == "s"][0]
        basket = rootfile.read_basket(buf, rec)
        self.assertEqual(basket.nev_buf, 3)
        # Entries 1 and 2 start at the same byte: entry 1 wrote nothing.
        self.assertEqual(basket.entry_offsets, [65, 68, 68])
        self.assertEqual(basket.last, 65 + 3 + 0 + 305)

    # -- what the leaf and the branch record -----------------------------

    def test_a_tleafc_forces_an_offset_array(self):
        tree = self.build()
        n, s = tree.branches
        self.assertEqual(n.entry_offset_len, 0)
        self.assertFalse(n.variable)
        # 1000 to start with, shrunk to 4 x fNevBuf when the basket closes.
        self.assertTrue(s.variable)
        s.flush()
        self.assertEqual(s.entry_offset_len, 12)
        self.assertEqual(s.flushed[0].nev_buf_size, 1000)

    def test_flen_and_fmaximum_are_the_longest_string_plus_one(self):
        leaf = self.build().branches[1].leaf
        self.assertEqual(leaf.length, 301)
        self.assertEqual(leaf.maximum, 301)
        self.assertEqual(leaf.minimum, 0)
        self.assertEqual(leaf.len_type, 1)
        self.assertFalse(leaf.is_range)
        # fTitle carries no dimensions: a TLeafC has none to carry.
        self.assertEqual(leaf.title, "s")

    def test_flen_never_falls_back(self):
        """A later shorter string does not lower the high-water mark."""
        tree = rw.Tree("t", "")
        tree.branch("s", "C")
        tree.fill({"s": "abcd"})
        tree.fill({"s": "x"})
        self.assertEqual(tree.branches[0].leaf.length, 5)
        self.assertEqual(tree.branches[0].leaf.maximum, 5)

    def test_a_non_string_is_refused(self):
        leaf = rw.Leaf(name="s", kind="C")
        with self.assertRaises(rw.WriteError):
            leaf.pack(3)


class Subdirectories(unittest.TestCase):
    """`data/written/nested-subdir.root` against `data/container/directories.root`.

    The two files hold the same five objects at the same three levels, and the
    written one's name was chosen to be the same length, so they have the same
    length and the same record boundaries. Everything else is the assertion: the
    whole 1854 bytes agree once the three fields `spec/06-writing/WritingFiles.md`
    marks free are set aside -- each key's `fDatime`, the three UUIDs, and the
    file's own name.

    That makes every offset, `fNbytesName`, `fSeekParent` and `fSeekKeys` in both
    subdirectory records ROOT's own value rather than this project's reading of
    `TDirectoryFile.cxx`.
    """

    ROOTS = "data/container/directories.root"
    MINE = "data/written/nested-subdir.root"

    def load(self, path):
        buf, header, records = rootfile.load(REPO / path)
        return bytes(buf), header, records

    def normalised(self, path):
        """The file with every free field blanked, and the name made ours.

        The name substitution is a straight `replace`: the two names are the same
        31 bytes long, so nothing moves. Every other span comes from parsing the
        file, not from a hard-coded offset, so a record that moved would be
        compared at its new place and fail.
        """
        buf, header, records = self.load(path)
        buf = bytearray(buf.replace(b"data/container/directories.root",
                                    b"data/written/nested-subdir.root"))
        blank = [(header.uuid_offset, 16)]
        for rec in records:
            blank.append((rec.offset + 10, 4))          # the key's fDatime
            d = rootfile.read_directory(bytes(buf), rec)
            if d is not None:
                blank.append((d.datime_offset, 8))      # fDatimeC and fDatimeM
                blank.append((d.uuid_offset, 16))
                if d.seek_keys:
                    for e in rootfile.read_key_list(bytes(buf), d):
                        blank.append((e.datime_offset, 4))
        for off, n in blank:
            buf[off:off + n] = b"\x00" * n
        return bytes(buf)

    def test_every_byte_but_the_free_fields_is_roots(self):
        mine, theirs = self.normalised(self.MINE), self.normalised(self.ROOTS)
        self.assertEqual(len(mine), 1854)
        self.assertEqual(mine, theirs)

    def test_the_layout_is_roots(self):
        """Stated separately, so a failure says *what* moved."""
        _, _, mine = self.load(self.MINE)
        _, _, theirs = self.load(self.ROOTS)
        shape = lambda rs: [(r.offset, r.nbytes, r.key_len, r.obj_len,
                             r.class_name, r.seek_pdir,
                             None if r.name.endswith(".root") else r.name)
                            for r in rs]
        self.assertEqual(shape(mine), shape(theirs))

    def test_a_subdirectory_records_fnbytesname_is_its_keylen(self):
        buf, _, records = self.load(self.MINE)
        subs = [r for r in records if r.class_name == "TDirectory"
                and r.obj_len == rw.DIR_RECORD_LEN]
        self.assertEqual([r.name for r in subs], ["alpha", "beta"])
        for rec in subs:
            d = rootfile.read_directory(buf, rec)
            self.assertEqual(d.nbytes_name, rec.key_len, rec.name)
            # And therefore the fields start where the key ends.
            self.assertEqual(d.fields_offset, rec.offset + rec.key_len)

    def test_a_subdirectory_key_spells_its_class_tdirectory(self):
        buf, _, records = self.load(self.MINE)
        for rec in records:
            if rec.name in ("alpha", "beta"):
                self.assertEqual(rec.class_name, "TDirectory")
        # And the key length accounts for that spelling, not TDirectoryFile's.
        alpha = next(r for r in records if r.offset == 401)
        self.assertEqual(alpha.key_len,
                         26 + rw.string_len("TDirectory")
                         + rw.string_len("alpha") * 2)

    def test_the_parent_chain_is_in_fseekpdir_and_fseekparent(self):
        buf, _, records = self.load(self.MINE)
        by_name = {r.name: r for r in records if r.class_name == "TDirectory"
                   and r.obj_len == rw.DIR_RECORD_LEN}
        for name, parent in (("alpha", 100), ("beta", 401)):
            rec = by_name[name]
            d = rootfile.read_directory(buf, rec)
            self.assertEqual(rec.seek_pdir, parent, name)
            self.assertEqual(d.seek_parent, parent, name)

    def test_each_directory_has_its_own_key_list(self):
        buf, _, records = self.load(self.MINE)
        listed = {}
        for rec in records:
            d = rootfile.read_directory(buf, rec)
            if d is None:
                continue
            klist = next(r for r in records if r.offset == d.seek_keys)
            # The key-list record's key names the directory that owns it.
            self.assertEqual(klist.seek_pdir, d.seek_dir, rec.name)
            listed[rec.name] = [e.name for e in
                                rootfile.read_key_list(buf, d)]
        self.assertEqual(listed["alpha"], ["in_alpha", "beta"])
        self.assertEqual(listed["beta"], ["in_beta"])
        self.assertEqual(listed[self.MINE], ["top", "alpha"])

    def test_an_unsaved_directory_gets_no_key_list(self):
        f = rw.FileWriter("data/written/x.root")
        f.mkdir("saved")
        f.mkdir("unsaved", saved=False)
        data = f.to_bytes()
        header = rootfile.read_header(data)
        records = rootfile.read_records(data, header)
        # A key-list record's key is class TDirectory too, so the directory
        # records are the ones whose payload is exactly the 60 fields.
        dirs = {r.name: rootfile.read_directory(data, r)
                for r in records if r.class_name == "TDirectory"
                and r.obj_len == rw.DIR_RECORD_LEN}
        self.assertEqual(dirs["saved"].nbytes_keys,
                         next(r.nbytes for r in records
                              if r.offset == dirs["saved"].seek_keys))
        self.assertEqual(dirs["unsaved"].seek_keys, 0)
        self.assertEqual(dirs["unsaved"].nbytes_keys, 0)

    def test_an_unsaved_directory_cannot_hold_anything(self):
        f = rw.FileWriter("data/written/x.root")
        d = f.mkdir("unsaved", saved=False)
        d.add(rw.Obj("TObjString", "s", "", rw.tobjstring("x")))
        with self.assertRaises(rw.WriteError):
            f.to_bytes()

    def test_the_payload_is_sixty_bytes_whatever_the_offsets(self):
        """Which is what lets ROOT rewrite a directory record in place."""
        f = rw.FileWriter("data/written/x.root")
        f.mkdir("a")
        data = f.to_bytes()
        records = rootfile.read_records(data, rootfile.read_header(data))
        sub = next(r for r in records if r.class_name == "TDirectory")
        self.assertEqual(sub.obj_len, 60)
        self.assertEqual(sub.obj_len, rw.DIR_RECORD_LEN)


class Determinism(unittest.TestCase):
    def test_two_builds_are_identical(self):
        def build():
            f = rw.FileWriter("data/written/objstring.root", "t")
            f.add(rw.Obj("TObjString", "str", "", rw.tobjstring("hello")))
            return f.to_bytes()
        self.assertEqual(build(), build())

    def test_datime_packing(self):
        # 2000-01-01 00:00:00, the writer's default.
        self.assertEqual(rw.pack_datime(2000, 1, 1, 0, 0, 0), 339869696)
        with self.assertRaises(rw.WriteError):
            rw.pack_datime(1994, 1, 1, 0, 0, 0)



class Allocation(unittest.TestCase):
    """The free list, spec/06-writing/WritingFiles.md 2."""

    def test_fresh_list_is_one_entry(self):
        f = rw.FreeList()
        self.assertEqual(f.entries, [[100, rw.BIG]])
        self.assertEqual(f.end, 100)

    def test_append_advances_end(self):
        f = rw.FreeList()
        self.assertEqual(f.place(50), (100, -1))
        self.assertEqual(f.end, 150)
        self.assertEqual(f.entries, [[150, rw.BIG]])

    def test_exact_fit_removes_the_entry(self):
        f = rw.FreeList()
        f.place(100)                      # 100..199
        f.place(100)                      # 200..299
        f.release(100, 199)
        self.assertEqual(len(f.entries), 2)
        self.assertEqual(f.place(100), (100, 0))
        self.assertEqual(len(f.entries), 1)

    def test_partial_fit_leaves_a_remainder(self):
        f = rw.FreeList()
        f.place(200)
        f.place(100)
        f.release(100, 299)
        off, left = f.place(150)
        self.assertEqual((off, left), (100, 50))
        self.assertEqual(f.entries[0], [250, 299])

    def test_a_span_with_three_to_spare_is_skipped(self):
        """2.2: the test is `> n + 3`, so a remainder is never 1, 2 or 3."""
        f = rw.FreeList()
        f.place(200)
        f.place(100)
        f.release(100, 299)               # a 200-byte hole
        off, left = f.place(197)          # 197 + 3 == 200, not greater
        self.assertEqual(off, 400)        # appended instead
        self.assertEqual(left, -1)
        self.assertEqual(f.entries[0], [100, 299])

    def test_a_span_with_four_to_spare_is_taken(self):
        f = rw.FreeList()
        f.place(200)
        f.place(100)
        f.release(100, 299)
        off, left = f.place(196)
        self.assertEqual((off, left), (100, 4))

    def test_release_merges_on_both_sides(self):
        f = rw.FreeList()
        for _ in range(4):
            f.place(100)                  # 100, 200, 300, 400
        f.place(100)                      # 500, so nothing is at the tail
        f.release(100, 199)
        f.release(300, 399)
        self.assertEqual(f.entries[:2], [[100, 199], [300, 399]])
        f.release(200, 299)               # bridges the two
        self.assertEqual(f.entries[0], [100, 399])
        self.assertEqual(len(f.entries), 2)

    def test_releasing_the_tail_moves_end_back(self):
        """2.4: fEND falls, and ROOT does not truncate the file."""
        f = rw.FreeList()
        f.place(100)
        f.place(100)
        self.assertEqual(f.end, 300)
        f.release(200, 299)
        self.assertEqual(f.end, 200)
        self.assertEqual(f.entries, [[200, rw.BIG]])

    def test_marker_is_the_negative_length(self):
        f = rw.FreeList()
        self.assertEqual(f.marker(696, 714), rw.i32(-19))

    def test_marker_is_clamped(self):
        f = rw.FreeList()
        self.assertEqual(f.marker(100, 3_000_000_000), rw.i32(-rw.BIG))


class ReusedSpace(unittest.TestCase):
    """data/written/reused-space.root against data/container/gap-reused.root."""

    @classmethod
    def setUpClass(cls):
        cls.ours = (REPO / "data/written/reused-space.root").read_bytes()
        cls.root = (REPO / "data/container/gap-reused.root").read_bytes()

    def test_same_length(self):
        self.assertEqual(len(self.ours), len(self.root))

    def test_records_line_up(self):
        mine = rootfile.read_records(self.ours, rootfile.read_header(self.ours))
        theirs = rootfile.read_records(self.root, rootfile.read_header(self.root))
        self.assertEqual([(r.offset, r.nbytes) for r in mine],
                         [(r.offset, r.nbytes) for r in theirs])

    def test_only_datime_name_and_uuid_differ(self):
        """Every differing byte is a timestamp, the file's name, or the UUID."""
        a, b = bytearray(self.root), bytearray(self.ours)
        for buf in (a, b):
            buf[47:63] = bytes(16)                      # the header UUID
        for buf, name in ((a, b"data/container/gap-reused.root"),
                          (b, b"data/written/reused-space.root")):
            while name in buf:
                i = buf.index(name)
                buf[i:i + len(name)] = b"*" * len(name)
        for buf in (a, b):
            header = rootfile.read_header(bytes(buf))
            blank = []
            for r in rootfile.read_records(bytes(buf), header):
                if r.free:
                    continue
                blank.append((r.offset + 10, 4))            # the key's fDatime
                d = rootfile.read_directory(bytes(buf), r)
                if d is not None:
                    blank.append((d.datime_offset, 8))      # fDatimeC, fDatimeM
                    blank.append((d.uuid_offset, 16))
                    if d.seek_keys:
                        for e in rootfile.read_key_list(bytes(buf), d):
                            blank.append((e.datime_offset, 4))
            for off, n in blank:
                buf[off:off + n] = bytes(n)
        self.assertEqual(bytes(a), bytes(b))

    def test_the_stale_bytes_behind_the_marker_match(self):
        """Releasing a record writes four bytes and clears nothing else."""
        self.assertEqual(self.ours[696:715], self.root[696:715])
        self.assertEqual(self.ours[700:715], b"123456789abcdef")


if __name__ == "__main__":
    unittest.main()
