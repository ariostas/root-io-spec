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

    def test_an_unmarked_integer_counter_is_allowed(self):
        # kCounter replaces kInt only when the class that USES the member as a
        # length is built, so a counter may be plain kInt or kUInt.
        # ElementTypes.md 2.1; seen on ROOT 4 files and on TBits.
        for ftype in (3, 6, 13):
            si = info(element("fN", ftype=ftype),
                      element("fVar", cls="TStreamerBasicPointer", ftype=43,
                              count_name="fN"))
            self.assertEqual(self.failures(si), [], f"fType {ftype}")

    def test_a_counter_of_a_non_integer_type_is_caught(self):
        si = info(element("fN", ftype=5),          # kFloat
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

    def test_two_identical_infos_are_allowed(self):
        # ROOT does not deduplicate the list, and writes such a pair for
        # ROOT::TIOFeatures: SchemaEvolution.md 8.1. There is deliberately no
        # uniqueness invariant, so neither this nor a checksum disagreement at
        # one version is a failure.
        self.assertEqual(self.failures([info(name="A"), info(name="A")]), [])

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


class SynthesisedPair(unittest.TestCase):
    """Collections.md 8.1. A pair's members from the type name alone.

    The layouts are byte-verified in `serialization/pairs`; what is checked here
    is the mapping from a template argument to the element that produces them,
    which is a rule rather than a byte pattern.
    """

    @staticmethod
    def members(name):
        return [(el.name, el.cls, el.ftype, el.tail)
                for el in rootfile.synthesise_pair(name).elements]

    def test_two_fundamentals(self):
        self.assertEqual(
            self.members("pair<int,double>"),
            [("first", "TStreamerBasicType", 3, {}),
             ("second", "TStreamerBasicType", 8, {})])

    def test_a_std_string_is_an_stl_string_element(self):
        # Which is what gives its column the shared frame of section 4.1.
        first = self.members("pair<string,int>")[0]
        self.assertEqual(first[1:3], ("TStreamerSTLstring", 500))
        self.assertEqual(first[3], {"fSTLtype": rootfile.STL_STRING,
                                    "fCtype": rootfile.STL_STRING})

    def test_a_TString_is_not(self):
        # The pair to keep straight: a TString column has no frame at all.
        self.assertEqual(self.members("pair<TString,int>")[0][1:3],
                         ("TStreamerString", 65))

    def test_a_collection_keeps_its_kind(self):
        second = self.members("pair<int,vector<short> >")[1]
        self.assertEqual(second[1:3], ("TStreamerSTL", 500))
        self.assertEqual(second[3]["fSTLtype"], rootfile.STL_VECTOR)
        self.assertEqual(
            self.members("pair<int,set<short> >")[1][3]["fSTLtype"],
            rootfile.STL_SET)

    def test_a_pointer_and_a_class_differ(self):
        self.assertEqual(self.members("pair<int,Hit*>")[1][1:3],
                         ("TStreamerObjectAnyPointer", 69))
        self.assertEqual(self.members("pair<int,Hit>")[1][1:3],
                         ("TStreamerObjectAny", 62))

    def test_a_nested_pair_is_a_class_like_any_other(self):
        # No special case: pair<int,pair<int,int>> synthesises the outer one and
        # the inner is read as a framed object.
        self.assertEqual(self.members("pair<int,pair<int,int> >")[1][2], 62)


class StlKind(unittest.TestCase):
    """Collections.md 1. A collection name to the fSTLtype it would carry."""

    def test_the_common_ones(self):
        for name, want in (("vector<int>", rootfile.STL_VECTOR),
                           ("std::map<int,int>", rootfile.STL_MAP),
                           ("multiset<float>", rootfile.STL_MULTISET),
                           ("unordered_map<int,int>", rootfile.STL_UNORDERED_MAP),
                           ("bitset<8>", rootfile.STL_BITSET)):
            with self.subTest(name):
                self.assertEqual(rootfile.stl_kind(name), want)

    def test_an_unknown_head_is_refused_rather_than_guessed(self):
        with self.assertRaises(rootfile.UnsupportedClass):
            rootfile.stl_kind("MyContainer<int>")


class PairInfoLookup(unittest.TestCase):
    """Collections.md 8.2. By name, not by checksum, and whitespace-insensitive."""

    @staticmethod
    def decoder(*infos):
        return rootfile.Decoder(b"", 0, list(infos))

    @staticmethod
    def info(name, checksum=0, version=1):
        return rootfile.StreamerInfo(name=name, title="", version=9, bits=0,
                                     checksum=checksum, class_version=version,
                                     elements=[])

    def test_whitespace_in_the_name_does_not_matter(self):
        d = self.decoder(self.info("pair<int,vector<short> >"))
        self.assertIsNotNone(d.pair_info("pair<int,vector<short>>"))

    def test_a_pair_the_file_does_not_describe_is_synthesised(self):
        d = self.decoder(self.info("pair<int,int>"))
        self.assertIsNone(d.pair_info("pair<int,float>"))
        # value_info falls back rather than failing.
        self.assertEqual(len(d.value_info("pair<int,float>", 0).elements), 2)

    def test_the_file_wins_when_it_has_one(self):
        recorded = self.info("pair<int,int>", checksum=0x95f86d56)
        d = self.decoder(recorded)
        self.assertIs(d.value_info("pair<int,int>", 0), recorded)

    def test_a_shared_checksum_does_not_confuse_it(self):
        # The three pairs of serialization/pairs all carry 0x0b5fb752.
        shared = 0x0b5fb752
        d = self.decoder(self.info("pair<int,string>", checksum=shared),
                         self.info("pair<int,vector<short> >", checksum=shared))
        self.assertEqual(d.pair_info("pair<int,string>").name, "pair<int,string>")
        self.assertEqual(d.pair_info("pair<int,vector<short>>").name,
                         "pair<int,vector<short> >")


if __name__ == "__main__":
    unittest.main()


def elem(name, ftype, cls="TStreamerElement", type_name="int",
         count_name="", array_length=0):
    tail = {"fCountName": count_name} if count_name else {}
    return rootfile.Element(cls=cls, version=4, name=name, title="", bits=0,
                            ftype=ftype, fsize=4, array_length=array_length,
                            array_dim=0, max_index=[0] * 5,
                            type_name=type_name, tail=tail)


class StreamLoop(unittest.TestCase):
    """ElementTypes.md 8. A counted array of objects, the count never stored."""

    POINT = info(elem("fI", 3), name="P")

    def decode(self, buf, el, count):
        decoder = rootfile.Decoder(buf, 0, [self.POINT, info(el, name="C")])
        return decoder.read_element_value(el, 0, {"fN": count})

    def test_one_star_is_bare_objects(self):
        el = elem("fLoop", 501, cls="TStreamerLoop", type_name="P*",
                  count_name="fN")
        buf = (b"\x40\x00\x00\x16\x00\x0a"                  # bc 22, version 10
               b"\x40\x00\x00\x06\x00\x01\x00\x00\x00\x01"  # P{1}
               b"\x40\x00\x00\x06\x00\x01\x00\x00\x00\x02")  # P{2}
        self.assertEqual(self.decode(buf, el, 2).end, len(buf))

    def test_a_count_of_zero_leaves_the_frame_alone(self):
        el = elem("fLoop", 501, cls="TStreamerLoop", type_name="P*",
                  count_name="fN")
        buf = b"\x40\x00\x00\x02\x00\x0a"
        self.assertEqual(self.decode(buf, el, 0).end, 6)

    def test_an_older_version_word_is_accepted(self):
        # A file written before ROOT 6.36 carries 9 here, not 10. Nothing may
        # compare the word to 10. ElementTypes.md 8.1.
        el = elem("fLoop", 501, cls="TStreamerLoop", type_name="P*",
                  count_name="fN")
        buf = b"\x40\x00\x00\x02\x00\x09"
        self.assertEqual(self.decode(buf, el, 0).end, 6)

    def test_a_byte_count_that_disagrees_is_an_error(self):
        el = elem("fLoop", 501, cls="TStreamerLoop", type_name="P*",
                  count_name="fN")
        buf = (b"\x40\x00\x00\x0d\x00\x0a"                  # one byte too many
               b"\x40\x00\x00\x06\x00\x01\x00\x00\x00\x01\x00")
        with self.assertRaises(rootfile.FormatError):
            self.decode(buf, el, 1)

    def test_a_missing_counter_is_an_error(self):
        el = elem("fLoop", 501, cls="TStreamerLoop", type_name="P*",
                  count_name="fNope")
        with self.assertRaises(rootfile.FormatError):
            self.decode(b"\x40\x00\x00\x02\x00\x0a", el, 0)

    def test_a_tstring_loop_is_bare_counted_strings(self):
        # TString::Streamer writes no frame of its own, so the loop is just the
        # strings back to back. ElementTypes.md 7.1, and the shape TFormula's
        # fExpr takes in a real file.
        el = elem("fExpr", 501, cls="TStreamerLoop", type_name="TString*",
                  count_name="fN")
        buf = b"\x40\x00\x00\x0a\x00\x09" + b"\x02ab" + b"\x04pol5"
        self.assertEqual(self.decode(buf, el, 2).end, len(buf))


class ArrayLengthWithoutOffsetL(unittest.TestCase):
    """ElementTypes.md 7.2. 63, 64, 68 and 69 never gain kOffsetL."""

    def test_two_slots_under_the_scalar_code_69(self):
        # EPoint *fPtrArr[2], the second one null: the code stays 69 and only
        # fArrayLength says there are two.
        el = elem("fPtrArr", 69, type_name="P*", array_length=2)
        buf = (b"\x40\x00\x00\x10\xff\xff\xff\xffP\x00"
               b"\x40\x00\x00\x06\x00\x01\x00\x00\x00\x01"
               b"\x00\x00\x00\x00")
        decoder = rootfile.Decoder(buf, 0, [info(elem("fI", 3), name="P"),
                                            info(el, name="C")])
        self.assertEqual(decoder.read_element_value(el, 0, {}).end, len(buf))

    def test_a_scalar_is_still_one_slot(self):
        el = elem("fPtr", 69, type_name="P*", array_length=0)
        buf = b"\x00\x00\x00\x00"
        decoder = rootfile.Decoder(buf, 0, [info(el, name="C")])
        self.assertEqual(decoder.read_element_value(el, 0, {}).end, 4)
