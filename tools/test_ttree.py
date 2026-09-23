#!/usr/bin/env python3
"""Tests for spec/04-ttree/TBranch.md and TLeaf.md.

The byte-level checks live in check_invariants.py and run against the reference
files. These cover what a fixture cannot: the width table for a truncated
floating-point leaf, whose decision rule is easier to state than to generate a
file for, and the entry-to-basket search at its boundaries.
"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_invariants  # noqa: E402
import rootfile  # noqa: E402


class TruncatedLeafWidth(unittest.TestCase):
    """TLeaf.md section 7. The two classes disagree with no annotation."""

    def test_no_annotation(self):
        self.assertEqual(rootfile.truncated_width("TLeafF16", "a"), 3)
        self.assertEqual(rootfile.truncated_width("TLeafD32", "c"), 4)

    def test_a_range_is_always_four_bytes(self):
        self.assertEqual(
            rootfile.truncated_width("TLeafF16", "b/f[0,100]"), 4)
        self.assertEqual(
            rootfile.truncated_width("TLeafD32", "b/d[0,100,10]"), 4)

    def test_nbits_only_is_three_bytes(self):
        self.assertEqual(rootfile.truncated_width("TLeafD32", "d/d[0,0,8]"), 3)
        self.assertEqual(rootfile.truncated_width("TLeafF16", "d/f[0,0,8]"), 3)

    def test_fifteen_bits_falls_back_to_the_class_default(self):
        # nbits >= 15 with no range is not the mantissa form, so each class
        # reverts to what it does with no annotation at all.
        self.assertEqual(rootfile.truncated_width("TLeafF16", "d/f[0,0,15]"), 3)
        self.assertEqual(rootfile.truncated_width("TLeafD32", "d/d[0,0,15]"), 4)

    def test_dimensions_before_the_annotation_are_not_a_range(self):
        self.assertEqual(
            rootfile.truncated_width("TLeafD32", "v[n]/d[0,0,8]"), 3)

    def test_out_of_range_nbits_is_reset_to_32(self):
        # TStreamerElement.cxx:145-148 resets nbits, which then fails the
        # nbits < 15 test and lands on the class default.
        self.assertEqual(rootfile.truncated_width("TLeafD32", "d/d[0,0,99]"), 4)
        self.assertEqual(rootfile.truncated_width("TLeafF16", "d/f[0,0,1]"), 3)

    def test_pi_literals_are_a_range(self):
        self.assertEqual(rootfile.truncated_width("TLeafD32", "d/d[-pi,pi]"), 4)

    def test_the_class_version_1_title_has_no_leading_slash(self):
        # TLeafF16/TLeafD32 below class version 2 stored the type spec alone.
        # Seen on ROOT 6.20/04 files in the foreign corpus of PLAN.md 9.8.
        self.assertEqual(rootfile.truncated_width("TLeafF16", "f[-2.71,10,16]"), 4)
        self.assertEqual(rootfile.truncated_width("TLeafD32", "d[-2.71,10,30]"), 4)
        self.assertEqual(rootfile.truncated_width("TLeafF16", "f[0,0,8]"), 3)
        self.assertEqual(rootfile.truncated_width("TLeafD32", "d[0,0,8]"), 3)


def branch(**kw) -> rootfile.Branch:
    fields = dict(
        slot=0, name="b", title="b/I", compress=0, basket_size=32000,
        entry_offset_len=0, write_basket=0, entry_number=0, io_bits=0,
        offset=0, max_baskets=10, split_level=0, entries=0, first_entry=0,
        tot_bytes=0, zip_bytes=0, basket_slots=1, basket_objects=0,
        basket_bytes=[0] * 10, basket_entry=[0] * 10, basket_seek=[0] * 10,
        file_name="", leaves=[], leaf_refs=[], branches=[], embedded={})
    fields.update(kw)
    return rootfile.Branch(**fields)


class FindBasket(unittest.TestCase):
    """TBranch.md section 10. Three baskets of 8, 8 and 4 entries."""

    def setUp(self):
        self.br = branch(write_basket=3, entries=20, entry_number=20,
                         basket_entry=[0, 8, 16, 20, 0, 0, 0, 0, 0, 0])

    def test_first_and_last_of_each_basket(self):
        for entry, want in ((0, 0), (7, 0), (8, 1), (15, 1), (16, 2), (19, 2)):
            self.assertEqual(rootfile.find_basket(self.br, entry), want, entry)

    def test_the_terminator_is_never_returned(self):
        # fBasketEntry[3] is 20, which equals fEntryNumber, so the range check
        # rejects it before the search can land on basket 3.
        with self.assertRaises(rootfile.FormatError):
            rootfile.find_basket(self.br, 20)

    def test_below_the_first_entry(self):
        with self.assertRaises(rootfile.FormatError):
            rootfile.find_basket(self.br, -1)

    def test_a_branch_that_does_not_start_at_zero(self):
        br = branch(write_basket=2, first_entry=100, entries=10,
                    entry_number=110,
                    basket_entry=[100, 105, 110, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(rootfile.find_basket(br, 100), 0)
        self.assertEqual(rootfile.find_basket(br, 104), 0)
        self.assertEqual(rootfile.find_basket(br, 105), 1)
        self.assertEqual(rootfile.find_basket(br, 109), 1)
        with self.assertRaises(rootfile.FormatError):
            rootfile.find_basket(br, 99)


def leaf(**kw) -> rootfile.Leaf:
    fields = dict(cls="TLeafI", slot=0, counter=None, name="x", title="x",
                  length=1, len_type=4, offset=0, is_range=False,
                  is_unsigned=False, leaf_count=0, count_slot=-1)
    fields.update(kw)
    return rootfile.Leaf(**fields)


class LeafWidth(unittest.TestCase):
    """TLeaf.md section 4.1. fLenType is not the on-disk width."""

    def test_a_long_leaf_is_eight_bytes_whatever_flentype_says(self):
        self.assertEqual(leaf(cls="TLeafG", len_type=4).width, 8)

    def test_a_string_leaf_has_no_fixed_width(self):
        self.assertIsNone(leaf(cls="TLeafC").width)

    def test_an_element_leaf_has_no_fixed_width(self):
        self.assertIsNone(leaf(cls="TLeafElement").width)

    def test_a_truncated_leaf_takes_its_width_from_the_title(self):
        self.assertEqual(leaf(cls="TLeafD32", title="c").width, 4)
        self.assertEqual(leaf(cls="TLeafD32", title="d/d[0,0,8]").width, 3)


class ResolveLeafCount(unittest.TestCase):
    """TLeaf.md section 3.1. The tag is a map position, so it is off by two."""

    def test_the_tag_is_resolved_through_kmapoffset(self):
        counter = leaf(name="n", slot=899, is_range=True)
        counted = leaf(cls="TLeafF", name="a", slot=1387,
                       leaf_count=447, count_slot=899)
        self.assertIs(rootfile.resolve_leaf_count(counted, [counter, counted]),
                      counter)

    def test_a_tag_naming_nothing_is_an_error(self):
        counted = leaf(leaf_count=447, count_slot=42)
        with self.assertRaises(rootfile.FormatError):
            rootfile.resolve_leaf_count(counted, [counted])


class BranchCountReference(unittest.TestCase):
    """TBranchElement.md section 6. fBranchCount is a map position, not a branch."""

    @staticmethod
    def slot(raw: bytes, start: int = 0):
        return rootfile.Value(name="fBranchCount", ftype=64,
                              start=start, end=start + len(raw),
                              type_name="TBranchElement*")

    def test_a_null_slot_means_unset(self):
        buf = b"\x00\x00\x00\x00"
        self.assertEqual(rootfile._branch_ref(buf, self.slot(buf), 615), -1)

    def test_a_tag_is_resolved_through_kmapoffset(self):
        # The same off-by-two as fLeafCount: tag 447 in a record at 615 names
        # absolute position 615 + 447 - 2.
        buf = (447).to_bytes(4, "big")
        self.assertEqual(rootfile._branch_ref(buf, self.slot(buf), 615), 1060)

    def test_a_missing_member_is_unset(self):
        self.assertEqual(rootfile._branch_ref(b"", None, 615), -1)

    def test_a_byte_count_means_written_in_full_here(self):
        # No corpus file does this, but the position is still the identity.
        tag = (rootfile.BYTE_COUNT_MASK | 8).to_bytes(4, "big")
        buf = b"\x00" * 900 + tag
        self.assertEqual(rootfile._branch_ref(buf, self.slot(tag, 900), 615), 900)


class EmbeddedBasketFlag(unittest.TestCase):
    """TBasket.md 4.1. The composed flag, and what it does and does not imply."""

    def build(self, flag: int, nev_buf: int, offsets: bytes = b"",
              data: bytes = b"") -> bytes:
        # A minimal embedded basket: the large-key fixed part, three counted
        # strings, then the header. fKeylen must cover all of it.
        strings = b"\x07TBasket\x01n\x01t"
        key_len = 34 + len(strings) + 19
        last = key_len + len(data)
        return (
            b"\x00\x00\x00\x00"                      # fNbytes
            + b"\x03\xec"                            # fVersion 1004
            + b"\x00\x00\x00\x00"                    # fObjlen
            + b"\x00\x00\x00\x00"                    # fDatime
            + key_len.to_bytes(2, "big")             # fKeylen
            + b"\x00\x00"                            # fCycle
            + b"\x00" * 16                           # fSeekKey, fSeekPdir
            + strings
            + b"\x00\x03"                            # TBasket version 3
            + b"\x00\x00\x7d\x00"                    # fBufferSize 32000
            + b"\x00\x00\x00\x04"                    # fNevBufSize 4
            + nev_buf.to_bytes(4, "big")             # fNevBuf
            + last.to_bytes(4, "big")                # fLast
            + bytes([flag])
            + offsets + data)

    def test_flag_12_has_no_offset_array(self):
        emb = rootfile.read_embedded_basket(self.build(12, 3, data=b"\x00" * 12), 0)
        self.assertIsNone(emb.basket.entry_offsets)
        self.assertEqual(emb.basket.flag, 12)

    def test_flag_11_has_one_counted_by_fnevbuf(self):
        offsets = b"\x00\x00\x00\x02" + b"\x00\x00\x00A" + b"\x00\x00\x00E"
        emb = rootfile.read_embedded_basket(
            self.build(11, 2, offsets=offsets, data=b"\x00" * 8), 0)
        self.assertEqual(emb.basket.entry_offsets, [0x41, 0x45])

    def test_a_count_of_fnevbuf_plus_one_is_rejected(self):
        # The record form's extra element must not appear here.
        offsets = b"\x00\x00\x00\x03" + b"\x00\x00\x00A" * 3
        with self.assertRaises(rootfile.FormatError):
            rootfile.read_embedded_basket(
                self.build(11, 2, offsets=offsets, data=b"\x00" * 8), 0)

    def test_an_empty_basket_writes_no_array_whatever_the_flag_says(self):
        emb = rootfile.read_embedded_basket(self.build(11, 0, data=b""), 0)
        self.assertIsNone(emb.basket.entry_offsets)

    def test_flag_80_means_the_offsets_are_generated(self):
        emb = rootfile.read_embedded_basket(self.build(82, 3, data=b"\x00" * 12), 0)
        self.assertIsNone(emb.basket.entry_offsets)

    def test_the_header_must_end_at_fkeylen(self):
        buf = bytearray(self.build(12, 3, data=b"\x00" * 12))
        buf[14:16] = (99).to_bytes(2, "big")       # a wrong fKeylen
        with self.assertRaises(rootfile.FormatError):
            rootfile.read_embedded_basket(bytes(buf), 0)


def tree(**kw) -> rootfile.Tree:
    fields = dict(
        name="t", title="", version=20, entries=0, tot_bytes=0, zip_bytes=0,
        saved_bytes=0, flushed_bytes=0, default_entry_offset_len=1000,
        n_cluster_range=0, max_entries=10 ** 12, auto_save=-300000000,
        auto_flush=-30000000, estimate=10 ** 6, io_bits=0,
        cluster_range_end=[], cluster_size=[], cluster_present=(0, 0),
        index_values_n=0, index_n=0, leaf_slots=0, leaf_refs=[],
        leaf_objects=0, pointers={}, branches=[])
    fields.update(kw)
    return rootfile.Tree(**fields)


class Clusters(unittest.TestCase):
    """TTree.md section 6.2, on shapes no fixture in this corpus has."""

    def test_one_range_described_by_fautoflush(self):
        # fNClusterRange 0 and a positive fAutoFlush: the whole tree is one range.
        t = tree(entries=10, auto_flush=4)
        self.assertEqual(list(rootfile.clusters(t)),
                         [(0, 4), (4, 8), (8, 10)])

    def test_the_last_cluster_is_truncated_at_fentries(self):
        t = tree(entries=10, auto_flush=4)
        self.assertEqual(rootfile.cluster_of(t, 9), (8, 10))

    def test_a_negative_fautoflush_records_nothing(self):
        # The common case: the byte watermark was never reached, so the file does
        # not say where the boundaries are.
        self.assertIsNone(rootfile.cluster_of(tree(entries=10), 0))
        self.assertEqual(list(rootfile.clusters(tree(entries=10))), [])

    def test_two_ranges_and_an_open_one(self):
        # ttree/clusters' shape, checked against the fixture's baskets.
        t = tree(entries=19, n_cluster_range=2, cluster_range_end=[7, 13],
                 cluster_size=[4, 3], cluster_present=(1, 1), auto_flush=5)
        self.assertEqual(list(rootfile.clusters(t)),
                         [(0, 4), (4, 8), (8, 11), (11, 14), (14, 19)])

    def test_a_range_end_truncates_a_cluster(self):
        # Range 0 ends at entry 6, so its last cluster is short: the next range
        # starts at 7 whatever the size says.
        t = tree(entries=12, n_cluster_range=1, cluster_range_end=[6],
                 cluster_size=[4], cluster_present=(1, 1), auto_flush=5)
        self.assertEqual(rootfile.cluster_of(t, 5), (4, 7))
        self.assertEqual(rootfile.cluster_of(t, 7), (7, 12))

    def test_a_zero_cluster_size_records_nothing(self):
        # Fast-merging a tree whose fAutoFlush was negative writes 0 for that
        # range (TTree.cxx:6504-6508), so a real range can have no recorded
        # size. The ranges either side of it are still usable.
        t = tree(entries=12, n_cluster_range=2, cluster_range_end=[3, 7],
                 cluster_size=[2, 0], cluster_present=(1, 1), auto_flush=4)
        self.assertEqual(rootfile.cluster_of(t, 0), (0, 2))
        self.assertIsNone(rootfile.cluster_of(t, 5))
        self.assertEqual(rootfile.cluster_of(t, 8), (8, 12))
        # clusters() stops at the gap rather than guessing across it.
        self.assertEqual(list(rootfile.clusters(t)), [(0, 2), (2, 4)])

    def test_an_empty_range_is_skipped(self):
        # Two SetAutoFlush calls with no Fill between them close two ranges at
        # the same entry; the second is empty, so no entry lands in it.
        t = tree(entries=12, n_cluster_range=2, cluster_range_end=[5, 5],
                 cluster_size=[6, 0], cluster_present=(1, 1), auto_flush=6)
        self.assertEqual(rootfile.cluster_of(t, 0), (0, 6))
        self.assertEqual(rootfile.cluster_of(t, 6), (6, 12))

    def test_an_entry_in_the_open_range_uses_the_pedestal(self):
        # Cluster starts are counted from the range's first entry, not from 0.
        t = tree(entries=20, n_cluster_range=1, cluster_range_end=[6],
                 cluster_size=[7], cluster_present=(1, 1), auto_flush=5)
        self.assertEqual(rootfile.cluster_of(t, 7), (7, 12))
        self.assertEqual(rootfile.cluster_of(t, 13), (12, 17))


def info(name, *bases) -> rootfile.StreamerInfo:
    elements = [
        rootfile.Element(cls="TStreamerBase", version=4, name=b, title="",
                         bits=0, ftype=0, fsize=0, array_length=0, array_dim=0,
                         max_index=[0] * 5, type_name="BASE", tail={})
        for b in bases]
    return rootfile.StreamerInfo(name=name, title="", version=10, bits=0,
                                 checksum=0, class_version=1, elements=elements)


class DerivesFrom(unittest.TestCase):
    """TTree.md section 1. A tree's record may name any derived class."""

    INFOS = [info("TTree", "TNamed", "TAttLine"),
             info("TNtuple", "TTree"),
             info("TNtupleD", "TTree"),
             info("TChain", "TTree"),
             info("TBranch", "TNamed", "TAttFill"),
             info("TNamed", "TObject")]

    def derives(self, name):
        return rootfile.derives_from(self.INFOS, name, "TTree")

    def test_the_class_itself(self):
        self.assertTrue(self.derives("TTree"))

    def test_a_direct_subclass(self):
        for name in ("TNtuple", "TNtupleD", "TChain"):
            self.assertTrue(self.derives(name), name)

    def test_an_unrelated_class(self):
        for name in ("TBranch", "TNamed", "TH1F"):
            self.assertFalse(self.derives(name), name)

    def test_a_cycle_does_not_hang(self):
        # A malformed file could describe a class as its own base.
        infos = [info("A", "B"), info("B", "A")]
        self.assertFalse(rootfile.derives_from(infos, "A", "TTree"))

    def test_a_class_the_file_does_not_describe(self):
        self.assertFalse(self.derives("Unknown"))


def element(name="m", cls="TStreamerBasicType", ftype=3, type_name="int",
            title="", array_length=0, tail=None):
    return rootfile.Element(
        cls=cls, version=2, name=name, title=title, bits=0, ftype=ftype,
        fsize=0, array_length=array_length, array_dim=0, max_index=[0] * 5,
        type_name=type_name, tail=tail or {})


class MemberColumn(unittest.TestCase):
    """ReadingEntries.md 3.2 and 5.3. A column of n values of one member.

    The same reader serves a member-wise collection's column (Collections.md 4)
    and a split branch's, because ROOT reads them with the same action.
    """

    def column(self, el, count, buf, offset=0):
        return rootfile.Decoder(buf, 0, []).read_column(el, count, offset)

    def test_a_fixed_width_scalar_is_n_times_w(self):
        buf = b"\x00" * 64
        self.assertEqual(self.column(element(ftype=3), 5, buf), 20)
        self.assertEqual(self.column(element(ftype=8), 5, buf), 40)

    def test_an_empty_column_consumes_nothing(self):
        self.assertEqual(self.column(element(ftype=8), 0, b"\x00" * 8), 0)

    def test_a_double32_takes_its_width_from_the_element_title(self):
        # ReadingEntries.md 5.2: nothing on the branch or the leaf records it.
        el = element(ftype=9, title="x[0,0,8]", type_name="Double32_t")
        self.assertEqual(self.column(el, 4, b"\x00" * 64), 12)
        self.assertEqual(self.column(element(ftype=9), 4, b"\x00" * 64), 16)

    def test_a_fixed_c_array_multiplies_by_its_length(self):
        el = element(ftype=rootfile.OFFSET_L + 3, array_length=3)
        self.assertEqual(self.column(el, 5, b"\x00" * 128), 60)


class BitsetColumn(unittest.TestCase):
    """ReadingEntries.md 3.6. Not packed, and shared framing across a column."""

    EL = staticmethod(lambda: element(
        name="fBits", cls="TStreamerSTL", ftype=500, type_name="bitset<4>",
        tail={"fSTLtype": rootfile.STL_BITSET, "fCtype": 0}))

    @staticmethod
    def one(bits):
        return (4).to_bytes(4, "big") + bytes(bits)

    def test_a_single_bitset_is_an_object_wise_collection_of_bool(self):
        body = self.one([1, 0, 1, 1])
        buf = (rootfile.BYTE_COUNT_MASK | (2 + len(body))).to_bytes(4, "big") \
            + (10).to_bytes(2, "big") + body
        self.assertEqual(
            rootfile.Decoder(buf, 0, []).read_collection(self.EL(), 0), len(buf))

    def test_a_column_shares_one_frame_for_every_bitset(self):
        body = self.one([1, 0, 1, 1]) + self.one([0, 0, 1, 0])
        framed = (rootfile.BYTE_COUNT_MASK | (2 + len(body))).to_bytes(4, "big") \
            + (10).to_bytes(2, "big") + body
        # Padded so a wrong count reads zeros rather than running off the end;
        # the byte count must catch it, not the buffer's length.
        decoder = rootfile.Decoder(framed + b"\x00" * 16, 0, [])
        self.assertEqual(decoder.read_column(self.EL(), 2, 0), len(framed))
        # The byte count covers the whole column, so a wrong count is caught by
        # it. A reader that framed each bitset separately would not notice.
        with self.assertRaises(rootfile.FormatError):
            decoder.read_column(self.EL(), 3, 0)
        with self.assertRaises(rootfile.FormatError):
            decoder.read_column(self.EL(), 1, 0)


class BranchStreamerInfo(unittest.TestCase):
    """TBranchElement.md 5 / ReadingEntries.md 5.1. Chosen from the branch's
    own fields, because nothing in an entry identifies a class."""

    @staticmethod
    def info(version, checksum):
        return rootfile.StreamerInfo(name="C", title="", version=9, bits=0,
                                     checksum=checksum, class_version=version,
                                     elements=[])

    @staticmethod
    def branch(version=0, checksum=0, name="C"):
        br = object.__new__(rootfile.Branch)
        br.class_name, br.class_version, br.check_sum = name, version, checksum
        return br

    def test_the_version_selects(self):
        infos = [self.info(2, 0xaa), self.info(3, 0xbb)]
        got = rootfile.branch_streamer_info(infos, self.branch(version=3))
        self.assertEqual(got.class_version, 3)

    def test_a_version_of_zero_falls_back_to_the_checksum(self):
        infos = [self.info(0, 0xaa), self.info(0, 0xbb)]
        got = rootfile.branch_streamer_info(infos, self.branch(checksum=0xbb))
        self.assertEqual(got.checksum, 0xbb)

    def test_an_unknown_class_is_not_a_failure_of_the_file(self):
        with self.assertRaises(rootfile.UnsupportedClass):
            rootfile.branch_streamer_info([], self.branch(name="Missing"))


class InteriorNodes(unittest.TestCase):
    """ReadingEntries.md 2. Which branches hold bytes of their own."""

    @staticmethod
    def reader():
        return object.__new__(rootfile.TreeReader)

    @staticmethod
    def branch(ftype, fid=0):
        br = object.__new__(rootfile.Branch)
        br.element_type, br.element_id = ftype, fid
        return br

    def test_the_three_interior_shapes_hold_nothing(self):
        holds = rootfile.TreeReader.holds_data
        self.assertFalse(holds(self.reader(), self.branch(1)))
        self.assertFalse(holds(self.reader(), self.branch(2)))
        self.assertFalse(holds(self.reader(), self.branch(0, fid=-2)))

    def test_a_count_branch_and_a_member_do(self):
        holds = rootfile.TreeReader.holds_data
        for ftype in (0, 3, 4, 31, 41):
            self.assertTrue(holds(self.reader(), self.branch(ftype)), ftype)

    def test_a_plain_tbranch_always_does(self):
        self.assertTrue(
            rootfile.TreeReader.holds_data(self.reader(),
                                           self.branch(None, fid=None)))


class LegacyBranchLayout(unittest.TestCase):
    """TBranch.md 13.1: the member order below class version 10.

    No fixture can cover it (the writers are ROOT 3 and ROOT 4), so the
    evidence is the three corpus files, and these tests pin what the reader does
    with the version gates and the fBasketSeek width selector. The nested objects
    are stubbed, because the test is of the scalar layout around them.
    """

    STUB = 6                           # bytes each stubbed nested object takes

    class Stubbed(rootfile.Decoder):
        def read_object(self, cls, offset, counters=None):
            return rootfile.Value(name=cls, ftype=61, start=offset,
                                  end=offset + LegacyBranchLayout.STUB,
                                  type_name=cls)

    def branch_bytes(self, version, max_baskets, seek_flag=1):
        """A legacy TBranch's member area, with the nested objects stubbed."""
        import struct
        out = bytearray(b"\x00" * self.STUB)                 # TNamed
        if version > 7:
            out += b"\x00" * self.STUB                       # TAttFill
        scalars = [0, 32000, 0, 0, 7, 0, max_baskets]        # ... fMaxBaskets
        if version > 6:
            scalars.append(0)                                # fSplitLevel
        for v in scalars:
            out += struct.pack(">i", v)
        out += struct.pack(">ddd", 7.0, 0.0, 0.0)            # Stat_t x 3
        out += b"\x00" * (3 * self.STUB)                     # the three arrays
        for flag, width in ((1, 4), (1, 4), (seek_flag, 8 if seek_flag == 2 else 4)):
            out += bytes([flag]) + b"\x00" * (max_baskets * width)
        out += b"\x00"                                       # fFileName, empty
        return bytes(out)

    def members(self, version, max_baskets, seek_flag=1):
        buf = self.branch_bytes(version, max_baskets, seek_flag)
        decoder = self.Stubbed(buf, 0, [])
        return {v.name: v for v in
                decoder.read_legacy_branch(version, 0, len(buf))}

    def test_version_7_has_no_att_fill_and_a_split_level(self):
        m = self.members(7, 10)
        self.assertNotIn("TAttFill", m)
        self.assertIn("fSplitLevel", m)

    def test_version_6_has_neither(self):
        m = self.members(6, 10)
        self.assertNotIn("TAttFill", m)
        self.assertNotIn("fSplitLevel", m)

    def test_version_8_has_both(self):
        m = self.members(8, 10)
        self.assertIn("TAttFill", m)
        self.assertIn("fSplitLevel", m)

    def test_the_counters_are_doubles(self):
        m = self.members(9, 10)
        for name in ("fEntries", "fTotBytes", "fZipBytes"):
            self.assertEqual(m[name].ftype, 8, name)
            self.assertEqual(m[name].end - m[name].start, 8, name)
        self.assertEqual(rootfile._int_member(
            self.branch_bytes(9, 10), m["fEntries"]), 7)

    def test_fentrynumber_is_four_bytes(self):
        m = self.members(9, 10)
        self.assertEqual(m["fEntryNumber"].end - m["fEntryNumber"].start, 4)

    def test_the_arrays_are_fmaxbaskets_long(self):
        m = self.members(9, 1000)
        for name in ("fBasketBytes", "fBasketEntry", "fBasketSeek"):
            self.assertEqual(m[name].end - m[name].start, 1 + 1000 * 4, name)

    def test_flag_two_widens_fbasketseek_and_nothing_else(self):
        m = self.members(9, 10, seek_flag=2)
        self.assertEqual(m["fBasketSeek"].end - m["fBasketSeek"].start,
                         1 + 10 * 8)
        self.assertEqual(m["fBasketEntry"].end - m["fBasketEntry"].start,
                         1 + 10 * 4)

    def test_a_short_byte_count_is_an_error(self):
        buf = self.branch_bytes(9, 10)
        decoder = self.Stubbed(buf, 0, [])
        with self.assertRaises(rootfile.FormatError):
            decoder.read_legacy_branch(9, 0, len(buf) - 1)


class MaxBasketsByClassVersion(unittest.TestCase):
    """TBranch.md invariant 11.1 and section 13.2.

    ROOT wrote a flat fMaxBaskets of 1000 at class versions 7 and 8, and
    max(fWriteBasket + 1, 10) from version 9 on. Version 8 used to be held to
    the current rule, on the evidence of a g4tools file; the nine roottest files
    ROOT 3.05-3.10 wrote at version 8 all have 1000.
    """

    def failures(self, class_version, max_baskets):
        c = check_invariants.Checker.__new__(check_invariants.Checker)
        c.path = Path("stub.root")
        c.failures = []
        c.branch_class_version = lambda: class_version
        br = SimpleNamespace(
            name="b", cls="TBranch", write_basket=0, max_baskets=max_baskets,
            basket_bytes=[0] * max_baskets, basket_entry=[0] * max_baskets,
            basket_seek=[0] * max_baskets, basket_slots=1, branches=[],
            embedded={}, entries=0, entry_number=0, first_entry=0,
            entry_offset_len=0, file_name="", leaves=[], tot_bytes=0,
            zip_bytes=0)
        c.check_branch(None, br)
        return [f for f in c.failures if "TBranch 11.1:" in f]

    def test_the_current_rule_passes_everywhere(self):
        for version in (7, 8, 9, 13):
            self.assertEqual(self.failures(version, 10), [], version)

    def test_a_flat_1000_passes_at_versions_7_and_8(self):
        self.assertEqual(self.failures(7, 1000), [])
        self.assertEqual(self.failures(8, 1000), [])

    def test_a_flat_1000_fails_from_version_9(self):
        bad = self.failures(9, 1000)
        self.assertEqual(len(bad), 1)
        self.assertIn("expected 10", bad[0])

    def test_below_the_floor_fails_at_any_version(self):
        self.assertEqual(len(self.failures(7, 5)), 1)


class CountedPointerWidth(unittest.TestCase):
    """TBranch.md 13.1: the width comes from the bytes, not the declared type."""

    def value(self, span):
        return rootfile.Value(name="fBasketSeek", ftype=56, start=0,
                              end=1 + span)

    def test_four_byte_values_under_an_eight_byte_declaration(self):
        buf = b"\x01" + b"\x00\x00\x00\x07" * 3
        self.assertEqual(
            rootfile._counted_pointer(buf, self.value(12), None, 3), [7, 7, 7])

    def test_eight_byte_values(self):
        buf = b"\x01" + b"\x00" * 7 + b"\x09"
        self.assertEqual(
            rootfile._counted_pointer(buf, self.value(8), None, 1), [9])

    def test_an_absent_array_is_empty(self):
        absent = rootfile.Value(name="fBasketSeek", ftype=56, start=0, end=1)
        self.assertEqual(
            rootfile._counted_pointer(b"\x00", absent, None, 10), [])


class CounterResolution(unittest.TestCase):
    """ReadingEntries.md 4.1: the counter is a sibling, not whatever
    fBranchCount names.

    The witness is alice_ESDs.root, which cannot be committed, so these build the
    shape by hand: two split objects of one class whose sub-branches have no
    parent prefix, which makes ROOT's by-name lookup ambiguous.
    """

    def branch(self, name, slot, count_slot=-1, children=()):
        return rootfile.Branch(
            slot=slot, name=name, title="", compress=0, basket_size=0,
            entry_offset_len=0, write_basket=0, entry_number=0, io_bits=0,
            offset=0, max_baskets=10, split_level=0, entries=0, first_entry=0,
            tot_bytes=0, zip_bytes=0, basket_slots=0, basket_objects=0,
            embedded={}, basket_bytes=[], basket_entry=[0], basket_seek=[0],
            file_name="", leaves=[], leaf_refs=[], branches=list(children),
            cls="TBranchElement", element_type=0, element_id=5,
            count_slot=count_slot)

    def reader(self, extra=()):
        first = [self.branch("fNIndices", 100), self.branch("fIndices", 101, 100)]
        # The second object's fIndices records the FIRST object's counter, which
        # is the bug: 100, not 200.
        second = [self.branch("fNIndices", 200), self.branch("fIndices", 201, 100)]
        top = [self.branch("SPDVertex", 10, children=first),
               self.branch("PrimaryVertex", 20, children=second)]
        top.extend(extra)
        return rootfile.TreeReader(b"", tree(branches=top), [])

    def test_the_sibling_wins_over_fbranchcount(self):
        reader = self.reader()
        second = reader.by_slot[201]
        self.assertEqual(reader.counter_branch(second, "fNIndices").slot, 200)

    def test_the_first_object_is_unaffected(self):
        reader = self.reader()
        first = reader.by_slot[101]
        self.assertEqual(reader.counter_branch(first, "fNIndices").slot, 100)

    def test_a_dotted_name_keeps_its_prefix(self):
        clones = self.branch("Tracks", 300, children=[
            self.branch("Tracks.fMap.fNbytes", 301),
            self.branch("Tracks.fMap.fAllBits", 302)])
        reader = self.reader(extra=[clones])
        self.assertEqual(
            reader.counter_branch(reader.by_slot[302], "fNbytes").slot, 301)

    def test_fbranchcount_is_the_fallback_when_no_name_matches(self):
        # With no sibling of that name, the recorded pointer is the best the
        # file offers, and it is what ROOT uses.
        reader = self.reader()
        self.assertEqual(
            reader.counter_branch(reader.by_slot[201], "fNothing").slot, 100)

    def test_nothing_to_resolve_with_is_named_not_guessed(self):
        lonely = self.branch("fIndices", 400)          # count_slot -1
        reader = self.reader(extra=[lonely])
        with self.assertRaises(rootfile.UnsupportedClass):
            reader.counter_branch(reader.by_slot[400], "fNothing")


class SameBranchCounter(unittest.TestCase):
    """TLeaf.md 5.2 and 6: a counter in the counted leaf's own branch is read
    from the same entry, and fIsRange does not say which leaf that is.

    ROOT 3.05/07 wrote such counters without fIsRange (short0.root, 35 of
    them). Current ROOT cannot, so no fixture has one.
    """

    def spans(self, is_range: bool):
        n = leaf(name="n", slot=100, is_range=is_range)
        a = leaf(cls="TLeafF", name="a", title="a[n]", slot=200,
                 leaf_count=100 + 2, count_slot=100)
        br = SimpleNamespace(name="b", leaves=[n, a])
        data = (2).to_bytes(4, "big") + bytes.fromhex("3f800000 40000000")
        buf = b"\x00" * 10 + data               # one entry: n = 2, two floats
        rec = rootfile.Record(offset=0, nbytes=len(buf))
        basket = rootfile.Basket(
            version=2, buffer_size=0, nev_buf_size=1000, nev_buf=1, last=22,
            flag=0, io_bits=0, generated=False, key_len=10, header_offset=0,
            data_start=10, data_end=22, entry_offsets=[10])
        return rootfile.entry_spans(buf, rec, basket, br, 0, {}, [n, a])

    def test_a_counter_with_firange_set(self):
        self.assertEqual([(s, e) for _, s, e in self.spans(True)],
                         [(10, 14), (14, 22)])

    def test_a_counter_without_firange_as_root_3_05_wrote_it(self):
        self.assertEqual([(s, e) for _, s, e in self.spans(False)],
                         [(10, 14), (14, 22)])


class ReferencedBits(unittest.TestCase):
    """ElementTypes.md 2.3 and ReadingEntries.md 8.5: kBits (15) is fBits,
    then a two-byte pidf when kIsReferenced is set.

    A split TObject base gives an fBits sub-branch whose entries are 4 or 6
    bytes each. mksm.root (4.00/08) has them: pv.fBits entry 0 is
    03 00 00 18 00 00, kIsReferenced 0x10 set and pidf 0.
    """

    EL = staticmethod(lambda: element(name="fBits", ftype=15,
                                      type_name="UInt_t"))
    PLAIN = bytes.fromhex("03000008")
    REFERENCED = bytes.fromhex("03000018 0000")

    def value_end(self, buf):
        return rootfile.Decoder(buf, 0, []).read_element_value(
            self.EL(), 0, {}).end

    def test_unreferenced_is_four_bytes(self):
        self.assertEqual(self.value_end(self.PLAIN + b"\xff" * 4), 4)

    def test_referenced_is_six_bytes(self):
        self.assertEqual(self.value_end(self.REFERENCED + b"\xff" * 4), 6)

    def test_kbits_has_no_fixed_width(self):
        # So ReadingEntries 8.3, which is about fixed-width columns, does not
        # apply to it, and a column goes through the per-value path.
        self.assertIsNone(rootfile.element_width(self.EL()))

    def test_a_column_mixes_both_widths(self):
        # jet.fBits in mksm.root: 176 of 669 elements referenced.
        buf = self.PLAIN + self.REFERENCED + self.PLAIN + b"\xff" * 8
        decoder = rootfile.Decoder(buf, 0, [])
        self.assertEqual(decoder.read_column(self.EL(), 3, 0), 14)


def stub_checker(version=(6, 40, 4), infos=()):
    """A Checker with no file behind it: `version` is the header's release and
    `infos` the file's streamer infos."""
    c = check_invariants.Checker.__new__(check_invariants.Checker)
    c.path = Path("stub.root")
    c.failures = []
    c.skipped = {}
    c.verified = 0
    c.header = SimpleNamespace(root_version=version)
    c._infos = (None, None, list(infos))
    c._tree_payload = None
    return c


def labelled(c, label):
    return [f for f in c.failures if f": {label}:" in f]


def embedded(nev_buf, key_len=20, width=10):
    """An embedded basket of `nev_buf` entries of `width` bytes, at offset 0 of
    its buffer, with an offset array."""
    end = key_len + nev_buf * width
    basket = rootfile.Basket(
        version=2, buffer_size=32000, nev_buf_size=10, nev_buf=nev_buf,
        last=end, flag=11, io_bits=0, generated=False, key_len=key_len,
        header_offset=key_len - 9, data_start=key_len, data_end=end,
        entry_offsets=[key_len + i * width for i in range(nev_buf)] or None)
    return rootfile.EmbeddedBasket(start=0, end=end, key_len=key_len,
                                   basket=basket, block=0)


class SavedBytesBeforeRelease5_27_02(unittest.TestCase):
    """TTree.md 11.2 and 6.3: fSavedBytes was fTotBytes before 5.27/02.

    RefTest.root (4.04/02): fTotBytes 72075, fZipBytes 6915, fSavedBytes
    72075. Root commit fa3ad228d72 switched AutoSave to fZipBytes.
    """

    def failures(self, version, saved, flushed=0):
        c = stub_checker(version)
        c.check_tree(None, None, tree(tot_bytes=72075, zip_bytes=6915,
                                      saved_bytes=saved, flushed_bytes=flushed))
        return labelled(c, "TTree 11.2")

    def test_ftotbytes_passes_before_5_27_02(self):
        self.assertEqual(self.failures((4, 4, 2), 72075), [])
        self.assertEqual(self.failures((5, 26, 0), 72075), [])

    def test_ftotbytes_fails_from_5_27_02(self):
        bad = self.failures((5, 27, 2), 72075)
        self.assertEqual(len(bad), 1)
        self.assertIn("fZipBytes 6915", bad[0])

    def test_above_ftotbytes_fails_at_any_release(self):
        bad = self.failures((5, 26, 0), 72076)
        self.assertEqual(len(bad), 1)
        self.assertIn("fTotBytes 72075", bad[0])

    def test_fflushedbytes_is_bounded_by_fzipbytes_at_any_release(self):
        self.assertEqual(len(self.failures((4, 4, 2), 0, flushed=6916)), 1)


class UnzeroedBasketArrays(unittest.TestCase):
    """TBranch.md 11.4 and 11.9: the arrays a TBranchElement constructor left
    unzeroed, before 3.10/02 for every constructor and before 5.21/02 for the
    top-level collection one.

    digi.root (3.04/02) holds 0xBAADF00D above fWriteBasket and in
    fBasketSeek at its embedded slot 0.
    """

    GARBAGE = -1163005939           # 0xBAADF00D, the Windows heap fill

    def failures(self, version, **kw):
        fields = dict(
            cls="TBranchElement", element_type=0, element_id=0,
            class_name="Event", leaves=[leaf()], entries=3, entry_number=3,
            basket_bytes=[0] + [self.GARBAGE] * 9,
            basket_entry=[0] + [self.GARBAGE] * 9,
            basket_seek=[self.GARBAGE] * 10,
            embedded={0: embedded(3)})
        fields.update(kw)
        c = stub_checker(version)
        c.check_branch(None, branch(**fields))
        return labelled(c, "TBranch 11.4") + labelled(c, "TBranch 11.9")

    def test_any_tbranchelement_before_3_10_02_is_exempt(self):
        self.assertEqual(self.failures((3, 4, 2)), [])

    def test_the_exemption_ends_at_3_10_02(self):
        # Three arrays nonzero above fWriteBasket, and the embedded slot's seek.
        self.assertEqual(len(self.failures((3, 10, 2))), 4)

    def test_a_plain_tbranch_is_never_exempt(self):
        self.assertEqual(
            len(self.failures((3, 4, 2), cls="TBranch", element_type=None,
                              element_id=None)), 4)

    def test_a_top_level_collection_is_exempt_before_5_21_02(self):
        top = dict(element_id=-1, class_name="vector<int>")
        self.assertEqual(self.failures((5, 14, 0), **top), [])
        self.assertEqual(len(self.failures((5, 21, 2), **top)), 4)

    def test_any_other_tbranchelement_is_not_exempt_after_3_10_02(self):
        self.assertEqual(len(self.failures((5, 14, 0))), 4)


class BasketAboveWriteBasket(unittest.TestCase):
    """TBranch.md 11.9 and 5: a basket in a slot above fWriteBasket is never
    read, so it holds no entries.

    Before 5.18/00 a split collection count branch carried a second,
    never-filled basket in slot 1 (alice_ESDs.root, 5.16/00).
    """

    def failures(self, above):
        c = stub_checker((5, 16, 0))
        c.check_branch(None, branch(
            cls="TBranchElement", element_type=3, element_id=-1,
            class_name="TClonesArray", leaves=[leaf()], entries=3,
            entry_number=3, basket_slots=2,
            embedded={0: embedded(3), 1: embedded(above)}))
        return labelled(c, "TBranch 11.9")

    def test_an_empty_basket_above_fwritebasket_passes(self):
        self.assertEqual(self.failures(0), [])

    def test_a_basket_with_entries_above_fwritebasket_fails(self):
        bad = self.failures(1)
        self.assertEqual(len(bad), 1)
        self.assertIn("slot 1, above fWriteBasket 0", bad[0])


class EmptyBaseBranch(unittest.TestCase):
    """TBranch.md 9.2: before 5.34/20 and 6.02/00 an empty base class of a
    top-level split object got an fType 1 branch with no leaf and no children,
    whose baskets still hold one framed base-class object per entry.

    cmsursula.root and mcpool.root (4.04/02): <top>.edm::EDProduct, each entry
    40 00 00 06 | 00 00 | 0e 3a fc b6, byte count 6, version 0, checksum.
    """

    CHECKSUM = 0x0E3AFCB6
    ENTRY = bytes.fromhex("40000006 0000 0e3afcb6")

    def infos(self, base_elements=()):
        parent = rootfile.StreamerInfo(
            name="edm::Wrapper<X>", title="", version=9, bits=0, checksum=1,
            class_version=3, elements=[element(
                name="edm::EDProduct", cls="TStreamerBase", ftype=0,
                type_name="BASE")])
        base = rootfile.StreamerInfo(
            name="edm::EDProduct", title="", version=9, bits=0,
            checksum=self.CHECKSUM, class_version=1,
            elements=list(base_elements))
        return [parent, base]

    def branch(self):
        return branch(
            name="W.edm::EDProduct", cls="TBranchElement", element_type=1,
            element_id=0, class_name="edm::Wrapper<X>", class_version=3,
            streamer_type=0, entries=2, entry_number=2,
            embedded={0: embedded(2)})

    def run_checks(self, entries=None, base_elements=()):
        c = stub_checker((4, 4, 2), self.infos(base_elements))
        br = self.branch()
        data = b"\x00" * 20 + (entries or self.ENTRY * 2)
        c.check_branch(data, br)
        c.check_splitting(br, {})
        c.check_leaves(data, br, [])
        return c

    def test_the_branch_is_exempt_from_the_interior_node_invariants(self):
        c = self.run_checks()
        self.assertEqual(labelled(c, "TBranch 11.10"), [])
        self.assertEqual(labelled(c, "Splitting 8.2"), [])

    def test_a_base_with_members_is_not_exempt(self):
        c = self.run_checks(base_elements=[element(name="fX")])
        self.assertEqual(len(labelled(c, "TBranch 11.10")), 1)
        self.assertEqual(len(labelled(c, "Splitting 8.2")), 1)

    def test_its_entries_are_decoded_not_skipped(self):
        c = self.run_checks()
        self.assertEqual(c.failures, [])
        self.assertEqual(c.verified, 1)
        self.assertFalse([k for k in c.skipped if k[0] == "ReadingEntries 8.5"])

    def test_a_wrong_checksum_fails(self):
        entry = bytes.fromhex("40000006 0000 0e3afcb7")
        bad = labelled(self.run_checks(self.ENTRY + entry), "ReadingEntries 8.5")
        self.assertEqual(len(bad), 1)
        self.assertIn("entry 1 checksum", bad[0])

    def test_a_byte_count_past_the_entry_fails(self):
        entry = bytes.fromhex("40000007 0000 0e3afcb6")
        bad = labelled(self.run_checks(entry + self.ENTRY), "ReadingEntries 8.5")
        self.assertEqual(len(bad), 1)
        self.assertIn("entry 0 spans 10 bytes", bad[0])


class LeaflessBasketCountedOnce(unittest.TestCase):
    """The ENTRIES denominator: a leafless TBranchSTL basket is one skipped
    branch-basket, not one per check that looks at it."""

    def test_one_basket_is_one_skip(self):
        c = stub_checker()
        br = branch(cls="TBranchSTL", entries=1, entry_number=1,
                    embedded={0: embedded(1)})
        data = b"\x00" * 30
        c.check_branch(data, br)
        c.check_leaves(data, br, [])
        self.assertEqual(
            sum(n for k, n in c.skipped.items() if k[0] == "ReadingEntries 8.5"),
            1)


class StreamerTypeDivergences(unittest.TestCase):
    """TBranchElement.md 10.10 and 5.2: the branch's fStreamerType is the
    in-memory code, which the element record does not always carry."""

    def failures(self, streamer_type, el):
        info = rootfile.StreamerInfo(name="Holder", title="", version=9, bits=0,
                                     checksum=0, class_version=1, elements=[el])
        c = stub_checker(infos=[info])
        c.check_branch_element(branch(
            cls="TBranchElement", element_type=0, element_id=0,
            class_name="Holder", class_version=1,
            streamer_type=streamer_type), {})
        return labelled(c, "TBranchElement 10.10")

    @staticmethod
    def stl(type_name, array_length=0, cls="TStreamerSTL"):
        return element(name="m", cls=cls, ftype=500, type_name=type_name,
                       array_length=array_length)

    def test_kstlp_against_a_pointer_to_a_collection(self):
        # RefTest.root (4.04/02) and ROOT 6.40.04 alike.
        self.assertEqual(self.failures(71, self.stl("vector<Item>*")), [])
        self.assertEqual(len(self.failures(300, self.stl("vector<Item>*"))), 1)

    def test_kstl_against_a_collection(self):
        self.assertEqual(self.failures(300, self.stl("vector<Item>")), [])
        self.assertEqual(len(self.failures(71, self.stl("vector<Item>"))), 1)

    def test_koffsetl_is_added_for_an_array(self):
        el = self.stl("string", array_length=2, cls="TStreamerSTLstring")
        self.assertEqual(self.failures(320, el), [])
        self.assertEqual(len(self.failures(300, el)), 1)

    def test_a_bool_that_stored_11_may_keep_11(self):
        # mksm.root (4.00/08): the element stored kUChar 11 and reads as 18.
        el = replace(element(name="ok", ftype=18, type_name="Bool_t"),
                     stored_ftype=11)
        self.assertEqual(self.failures(11, el), [])
        self.assertEqual(self.failures(18, el), [])

    def test_a_bool_that_stored_18_may_not_be_11(self):
        el = element(name="ok", ftype=18, type_name="Bool_t")
        self.assertEqual(len(self.failures(11, el)), 1)


class UnpromotedCounterBranch(unittest.TestCase):
    """TBranchElement.md 10.9: a counter branch has the counter's element
    code, 13 for an unsigned counter such as TBits::fNbytes, since only a code
    below 6 is promoted to kCounter (ElementTypes.md 2.1)."""

    def failures(self, counter_type):
        counter = branch(slot=100, name="fNbytes", cls="TBranchElement",
                         element_type=0, element_id=1, class_name="TBits",
                         streamer_type=counter_type)
        counted = branch(slot=200, name="fAllBits", cls="TBranchElement",
                         element_type=0, element_id=2, class_name="TBits",
                         streamer_type=51, count_slot=100)
        c = stub_checker()
        c.check_branch_element(counted, {100: counter, 200: counted})
        return labelled(c, "TBranchElement 10.9")

    def test_every_counter_code_is_a_counter_branch(self):
        for code in (3, 6, 13):
            self.assertEqual(self.failures(code), [], code)

    def test_a_float_is_not(self):
        self.assertEqual(len(self.failures(5)), 1)


class DecoderCacheIsBounded(unittest.TestCase):
    """TreeReader keeps a bounded number of basket decoders. Each one holds its
    buffer, which for a compressed basket is a copy of the file up to that
    basket, so keeping one per basket grew past 2.9 GB on a 15 MB file."""

    def test_old_decoders_are_dropped(self):
        reader = rootfile.TreeReader(b"", tree(branches=[]), [])
        n = rootfile.TreeReader.DECODER_CACHE
        for offset in range(3 * n):
            rec = rootfile.Record(offset=offset, nbytes=0, key_len=0)
            reader.decoder_for(rec, bytes(offset + 1))
        self.assertEqual(len(reader._decoders), n)

    def test_a_recent_decoder_is_reused(self):
        reader = rootfile.TreeReader(b"", tree(branches=[]), [])
        rec = rootfile.Record(offset=7, nbytes=0, key_len=0)
        first = reader.decoder_for(rec, bytes(8))
        self.assertIs(reader.decoder_for(rec, bytes(8)), first)



class PointerAndArrayCollectionColumns(unittest.TestCase):
    """ReadingEntries.md invariant 5 on `ttree/split-stl-pointer`: a pointer to
    a collection and an array of collections are read like the collection,
    under one frame (Collections.md 11.1 and 11.3)."""

    PATH = (Path(__file__).resolve().parents[1]
            / "data/ttree/split-stl-pointer.root")

    def test_every_entry_consumes_its_bytes(self):
        checker = check_invariants.Checker(self.PATH)
        _, _, infos = checker.streamer_infos()
        seen = {}
        for data, _, tree in checker.trees():
            reader = rootfile.TreeReader(checker.buf, tree, infos,
                                         checker.fetch_basket,
                                         tree_payload=data)
            for br in rootfile.walk_branches(tree.branches):
                if not reader.holds_data(br):
                    continue
                spans = [reader.entry_end(br, e) for e in range(3)]
                self.assertTrue(all(c == end for _, end, c in spans), br.name)
                seen[br.name] = [end - start for start, end, _ in spans]
        # Entry 0 of fPtr is a frame, PItem's version and a count of 0; of
        # fPtrArr[2] and fArr[2], the same with two counts.
        self.assertEqual(seen["fPtr"][0], 12)
        self.assertEqual(seen["fPtrArr[2]"][0], 16)
        self.assertEqual(seen["fArr[2]"][0], 16)
        self.assertEqual(set(seen), {"fPtr", "fPtrArr[2]", "fArr[2]", "fFlag"})

if __name__ == "__main__":
    unittest.main()
