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


class InfoListInvariants(unittest.TestCase):
    """SchemaEvolution.md invariants 1 and 2."""

    def failures(self, infos):
        return [where for where, _ in check_invariants.info_list_failures(infos)]

    def test_a_conforming_list_passes(self):
        self.assertEqual(self.failures([info(name="A"), info(name="B")]), [])

    def test_two_identical_infos_are_caught(self):
        # Two layouts of one class are distinguished by checksum, so two entries
        # agreeing on both version and checksum make the choice ill defined.
        self.assertEqual(self.failures([info(name="A"), info(name="A")]),
                         ["SchemaEvolution 9.2"])

    def test_same_class_different_checksum_is_allowed(self):
        a, b = info(name="A"), info(name="A")
        b.checksum = 1
        self.assertEqual(self.failures([a, b]), [])

    def test_an_out_of_range_version_is_caught(self):
        a = info(name="A")
        a.class_version = 65001
        self.assertEqual(self.failures([a]), ["SchemaEvolution 9.1"])

    def test_a_negative_version_is_caught(self):
        # The streamer writes the absolute value, so a negative one cannot occur
        # in a file ROOT wrote (SchemaEvolution.md 1.1).
        a = info(name="A")
        a.class_version = -1
        self.assertEqual(self.failures([a]), ["SchemaEvolution 9.1"])


class CountedString(unittest.TestCase):
    """Conventions 5.1. The 255 escape is why this has its own test: no fixture
    had a string longer than 254 bytes until the compression cases were
    decompressed, and the reader had silently been getting it wrong."""

    def test_short(self):
        self.assertEqual(rootfile._counted_string(b"\x03abc", 0), ("abc", 4))

    def test_empty(self):
        self.assertEqual(rootfile._counted_string(b"\x00", 0), ("", 1))

    def test_longest_short_form(self):
        raw = bytes([254]) + b"x" * 254
        self.assertEqual(rootfile._counted_string(raw, 0), ("x" * 254, 255))

    def test_escape(self):
        raw = b"\xff\x00\x00\x00\x03abc"
        self.assertEqual(rootfile._counted_string(raw, 0), ("abc", 8))

    def test_a_255_byte_string_uses_the_long_form(self):
        # The escape triggers above 254, so 0xFF never means "255 characters".
        raw = b"\xff\x00\x00\x00\xff" + b"y" * 255
        text, end = rootfile._counted_string(raw, 0)
        self.assertEqual((len(text), end), (255, 260))


if __name__ == "__main__":
    unittest.main()


class StdStringObject(unittest.TestCase):
    """Collections.md 10.1. A std::string object has no frame at all."""

    def test_a_short_string(self):
        buf = b"\x03abc"
        value = rootfile.read_std_string(buf, 0)
        self.assertEqual((value.start, value.end), (0, 4))

    def test_an_empty_string_is_one_byte(self):
        # Unlike TLeafC, WriteStdString emits the zero length byte.
        self.assertEqual(rootfile.read_std_string(b"\x00", 0).end, 1)

    def test_the_escape(self):
        buf = b"\xff\x00\x00\x01\x04" + b"x" * 260
        self.assertEqual(rootfile.read_std_string(buf, 0).end, 265)

    def test_every_spelling_is_recognised(self):
        for name in ("string", "std::string"):
            self.assertIn(name, rootfile.STD_STRING_NAMES)


class BaseClassCounter(unittest.TestCase):
    """StreamerDriven.md 3.2. A counted pointer may name a counter in a base."""

    def test_a_counter_in_a_base_is_visible_to_a_derived_element(self):
        # TGraph holds fNpoints and fX; TGraphAsymmErrors adds fEXlow, which
        # names fNpoints with fCountClass "TGraph". Two i32 values, so the
        # derived array must consume 1 + 2 * 4 bytes.
        base = info(element("fNpoints", ftype=6),
                    name="TGraph")
        derived = info(element("TGraph", cls="TStreamerBase", ftype=0),
                       element("fEXlow", cls="TStreamerBasicPointer", ftype=43,
                               count_name="fNpoints"),
                       name="TGraphAsymmErrors")
        buf = (b"\x40\x00\x00\x06\x00\x01"          # TGraph frame, version 1
               b"\x00\x00\x00\x02"                  # fNpoints = 2
               b"\x01"                              # fEXlow is present
               b"\x00\x00\x00\x07\x00\x00\x00\x08")   # its two values
        decoder = rootfile.Decoder(buf, 0, [base, derived])
        values = decoder.read_members("TGraphAsymmErrors", 1, 0, None)
        self.assertEqual(values[0].name, "TGraph")
        self.assertEqual(values[1].name, "fEXlow")
        # 1 flag byte plus two i32: the count came from the base.
        self.assertEqual(values[1].end - values[1].start, 9)

    def test_a_counter_that_is_nowhere_is_still_an_error(self):
        derived = info(element("fEXlow", cls="TStreamerBasicPointer", ftype=43,
                               count_name="fNope"),
                       name="C")
        decoder = rootfile.Decoder(b"\x01\x00\x00\x00\x07", 0, [derived])
        with self.assertRaises(rootfile.FormatError):
            decoder.read_members("C", 1, 0, None)
