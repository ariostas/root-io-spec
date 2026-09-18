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
        payload.tlist("", [i.write for i in rw.histogram_infos(("F", "D"))])
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
        ours = {i.name: i for i in rw.histogram_infos(("F", "D"))}
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


if __name__ == "__main__":
    unittest.main()
