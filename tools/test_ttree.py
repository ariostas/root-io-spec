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
