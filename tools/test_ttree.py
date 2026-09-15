#!/usr/bin/env python3
"""Tests for spec/04-ttree/TBranch.md and TLeaf.md.

The byte-level checks live in check_invariants.py and run against the reference
files. These cover what a fixture cannot: the width table for a truncated
floating-point leaf, whose decision rule is easier to state than to generate a
file for, and the entry-to-basket search at its boundaries.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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


if __name__ == "__main__":
    unittest.main()


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
