#!/usr/bin/env python3
"""Tests for the streamer-driven read of spec/02-serialization/StreamerDriven.md.

The byte-level checks live in check_invariants.py and run against the reference
files. These cover the two things a fixture cannot: the width of a quantised
member, whose encoding table is easier to state than to generate, and element
lists that no file ROOT wrote would contain.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_invariants  # noqa: E402
import rootfile  # noqa: E402


def element(name, cls="TStreamerBasicType", ftype=3, title="", count_name=""):
    tail = {"fCountName": count_name} if count_name else {}
    return rootfile.Element(cls=cls, version=4, name=name, title=title, bits=0,
                            ftype=ftype, fsize=4, array_length=0, array_dim=0,
                            max_index=[0] * 5, type_name="int", tail=tail)


def info(*elements, name="C"):
    return rootfile.StreamerInfo(name=name, title="", version=10, bits=0,
                                 checksum=0, class_version=1,
                                 elements=list(elements))


class QuantisedWidth(unittest.TestCase):
    """ElementTypes.md 5.2, for kDouble32 (9) and kFloat16 (19)."""

    def test_plain(self):
        self.assertEqual(rootfile.quantised_width(9, ""), 4)
        self.assertEqual(rootfile.quantised_width(19, ""), 3)

    def test_range_is_always_four_bytes(self):
        self.assertEqual(rootfile.quantised_width(9, "[-1,1]"), 4)
        self.assertEqual(rootfile.quantised_width(9, "[-1,1,2]"), 4)
        self.assertEqual(rootfile.quantised_width(19, "[-1,1,2]"), 4)

    def test_truncated_mantissa(self):
        for nbits in range(2, 15):
            self.assertEqual(rootfile.quantised_width(9, f"[0,0,{nbits}]"), 3,
                             f"nbits={nbits}")

    def test_fifteen_bits_degrades_to_a_plain_float(self):
        # The cliff of ElementTypes.md 5.3: xmin is only set to the bit count
        # when nbits < 15, so a 15-bit request is wider than a 14-bit one.
        self.assertEqual(rootfile.quantised_width(9, "[0,0,14]"), 3)
        self.assertEqual(rootfile.quantised_width(9, "[0,0,15]"), 4)

    def test_pi_literals(self):
        self.assertEqual(rootfile.quantised_width(9, "[-pi,pi,10]"), 4)

    def test_array_dimension_is_not_a_range(self):
        # The first bracket may be an array dimension, which has no comma.
        self.assertEqual(rootfile.quantised_width(9, "[fN]"), 4)
        self.assertEqual(rootfile.quantised_width(9, "[fN][0,0,10]"), 3)

    def test_out_of_range_nbits_falls_back_to_32(self):
        self.assertEqual(rootfile.quantised_width(9, "[0,0,99]"), 4)


class ElementListInvariants(unittest.TestCase):
    """StreamerDriven.md invariants 3, 4 and 6."""

    def failures(self, si):
        return [where for where, _ in check_invariants.element_list_failures(si)]

    def test_a_conforming_list_passes(self):
        si = info(element("TObject", cls="TStreamerBase", ftype=66),
                  element("fN", ftype=6),
                  element("fVar", cls="TStreamerBasicPointer", ftype=43,
                          count_name="fN"))
        self.assertEqual(self.failures(si), [])

    def test_a_base_after_a_member_is_caught(self):
        si = info(element("fN", ftype=6),
                  element("TObject", cls="TStreamerBase", ftype=66))
        self.assertEqual(self.failures(si), ["StreamerDriven 10.4"])

    def test_a_forward_counter_reference_is_caught(self):
        si = info(element("fVar", cls="TStreamerBasicPointer", ftype=43,
                          count_name="fN"),
                  element("fN", ftype=6))
        self.assertEqual(self.failures(si), ["StreamerDriven 10.3"])

    def test_a_counter_that_is_not_kcounter_is_caught(self):
        si = info(element("fN", ftype=3),
                  element("fVar", cls="TStreamerBasicPointer", ftype=43,
                          count_name="fN"))
        self.assertEqual(self.failures(si), ["StreamerDriven 10.3"])

    def test_notype_on_a_non_base_is_caught(self):
        si = info(element("fN", ftype=-1))
        self.assertEqual(self.failures(si), ["StreamerDriven 10.6"])

    def test_notype_on_a_base_is_allowed(self):
        # A suppressed TObject base: StreamerDriven.md 4.2.
        si = info(element("TObject", cls="TStreamerBase", ftype=-1))
        self.assertEqual(self.failures(si), [])


if __name__ == "__main__":
    unittest.main()
