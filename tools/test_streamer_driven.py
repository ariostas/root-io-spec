#!/usr/bin/env python3
"""Tests for the streamer-driven read of spec/02-serialization/StreamerDriven.md.

The byte-level checks live in check_invariants.py and run against the reference
files. These cover what a fixture cannot: the width of a quantised member,
whose encoding table is easier to state than to generate, and element lists
that no file ROOT wrote would contain.
"""

import struct
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_invariants  # noqa: E402
import rootfile  # noqa: E402


def element(name, cls="TStreamerBasicType", ftype=3, title="", count_name="",
            type_name="int"):
    tail = {"fCountName": count_name} if count_name else {}
    return rootfile.Element(cls=cls, version=4, name=name, title=title, bits=0,
                            ftype=ftype, fsize=4, array_length=0, array_dim=0,
                            max_index=[0] * 5, type_name=type_name, tail=tail)


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
        # ElementTypes.md 2.1; seen on the g4tools files and on TBits.
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
    """SchemaEvolution.md invariants 1 and 6."""

    def failures(self, infos):
        return [where for where, _ in check_invariants.info_list_failures(infos)]

    def test_a_conforming_list_passes(self):
        self.assertEqual(self.failures([info(name="A"), info(name="B")]), [])

    def test_two_identical_infos_are_allowed(self):
        # ROOT does not deduplicate the list, and writes such a pair for
        # ROOT::TIOFeatures: SchemaEvolution.md 8.1. There is deliberately no
        # uniqueness invariant, so neither this nor a checksum disagreement at
        # one version fails.
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

    def test_one_layout_twice_must_be_the_same_layout(self):
        # Invariant 6, on which 8.1's "take either entry" relies. Same class,
        # same version, same checksum, different elements: ROOT writes no such
        # pair, and a reader that took the wrong one would silently misdecode.
        # No fixture can hold it.
        a = info(element("fA"), name="A")
        b = info(element("fB"), name="A")
        self.assertEqual(self.failures([a, b]), ["SchemaEvolution 9.6"])

    def test_the_same_layout_twice_passes(self):
        # The ROOT::TIOFeatures pair: identical elements, and in three corpus
        # files only fBits differs (kIsCompiled in one, kBuildOldUsed in the
        # other two). fBits is not part of the comparison, so this passes.
        a, b = info(element("fA"), name="A"), info(element("fA"), name="A")
        b.bits = 0x3010000
        self.assertEqual(self.failures([a, b]), [])

    def test_two_versions_of_one_class_are_not_compared(self):
        # data/written/two-versions.root: Grown at versions 1 and 2 with
        # different checksums and different elements. This is legitimate: the
        # object's version word selects between them.
        a = info(element("fA"), name="Grown")
        b = info(element("fA"), element("fB"), name="Grown")
        b.class_version, b.checksum = 2, 0xEE119598
        self.assertEqual(self.failures([a, b]), [])


class CountedString(unittest.TestCase):
    """Conventions 5.1. The 255 escape gets its own test: no fixture had a
    string longer than 254 bytes until the compression cases were decompressed,
    and the reader had been getting it wrong without any error."""

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


class MemberWiseBase(unittest.TestCase):
    """Collections.md 4.1: in a member-wise column a base is one column per member.

    The shape of ATLAS's `vector<ElementLink<...>>` in `uproot-physlite-rntuple`:
    the value class has one element, a base with no ClassDef version
    (fBaseVersion -1) and two `unsigned int` members, so its info is found by
    checksum and its columns are all the keys, then all the indices.
    """

    def infos(self):
        base = rootfile.StreamerInfo(
            name="ElementLinkBase", title="", version=9, bits=0,
            checksum=0xFEB3DF9E, class_version=1,
            elements=[element("m_persKey", ftype=13),
                      element("m_persIndex", ftype=13)])
        link = rootfile.Element(
            cls="TStreamerBase", version=3, name="ElementLinkBase", title="",
            bits=0, ftype=0, fsize=0, array_length=0, array_dim=0,
            max_index=[0, 0xFEB3DF9E, 0, 0, 0], type_name="BASE",
            tail={"fBaseVersion": -1})
        value = rootfile.StreamerInfo(
            name="ElementLink<C>", title="", version=9, bits=0,
            checksum=0x69777553, class_version=1, elements=[link])
        return [base, value]

    def test_the_columns_are_per_member_of_the_base(self):
        buf = (b"\x00\x00\x69\x77\x75\x53"         # version 0, the value checksum
               b"\x00\x00\x00\x02"                  # two elements
               b"\x00\x00\x00\x07\x00\x00\x00\x08"  # m_persKey, m_persKey
               b"\xff\xff\xff\xff\xff\xff\xff\xff")  # m_persIndex, m_persIndex
        decoder = rootfile.Decoder(buf, 0, self.infos())
        self.assertEqual(decoder.read_member_wise("ElementLink<C>", 0, None),
                         len(buf))

    def test_a_base_checksum_matching_nothing_is_unsupported(self):
        infos = self.infos()
        infos[0].checksum = 0x12345678
        decoder = rootfile.Decoder(b"\x00\x00\x69\x77\x75\x53\x00\x00\x00\x01"
                                   + b"\x00" * 8, 0, infos)
        with self.assertRaises(rootfile.UnsupportedClass):
            decoder.read_member_wise("ElementLink<C>", 0, None)


class UnframedObject(unittest.TestCase):
    """StreamerDriven.md 7.1: an object of a TObject-derived class, no byte count.

    `Hold` is `skim.root`'s `HoldMuo` reduced to one member: a TObject base and
    an `Int_t`. Without its library ROOT reads it from the first byte with no
    version word; a class of ROOT's own is read version first.
    """

    TOBJECT = b"\x00\x01" + b"\x00\x00\x00\x00" + b"\x03\x00\x00\x00"

    def infos(self, version=1):
        base = element("TObject", cls="TStreamerBase", ftype=66,
                       type_name="BASE")
        base.tail = {"fBaseVersion": 1}
        hold = info(base, element("n"), name="Hold")
        hold.class_version = version
        return [hold]

    def test_no_version_word_is_read_from_the_first_byte(self):
        buf = self.TOBJECT + b"\x00\x00\x00\x07"
        decoder = rootfile.Decoder(buf, 0, self.infos())
        value = decoder.read_object("Hold", 0)
        self.assertEqual(value.end, len(buf))
        self.assertEqual(decoder.unframed, [("Hold", 0, "no version word")])

    def test_a_tobject_version_other_than_1_rejects_the_reading(self):
        # A version word first: read with no version word, the TObject base
        # would begin at 0 and carry version 2, which ROOT never writes.
        buf = b"\x00\x02" + self.TOBJECT + b"\x00\x00\x00\x07"
        decoder = rootfile.Decoder(buf, 0, self.infos(version=2))
        self.assertEqual(decoder.read_object("Hold", 0).end, len(buf))
        self.assertEqual(decoder.unframed, [("Hold", 0, "version-first")])

    def test_an_extent_decides_when_the_tobject_version_cannot(self):
        # Class version 1 makes both readings admissible on their own: the
        # no-version one ends 2 bytes short, and the extent rejects it.
        buf = b"\x00\x01" + self.TOBJECT + b"\x00\x00\x00\x07"
        decoder = rootfile.Decoder(buf, 0, self.infos())
        value = decoder.within_extent(lambda: decoder.read_object("Hold", 0),
                                      0, len(buf), lambda v: v.end)
        self.assertEqual(value.end, len(buf))
        self.assertEqual(decoder.versioned, set())

    def test_neither_reading_fitting_is_a_hand_written_streamer(self):
        # nEXO::SmartRef's shape: a TObject, the member, and two bytes its info
        # does not describe. The version-first reading also ends at the extent
        # here, and is rejected by its TObject version word of 0.
        buf = self.TOBJECT + b"\x00\x00\x00\x07" + b"\x00\x00"
        decoder = rootfile.Decoder(buf, 0, self.infos())
        with self.assertRaisesRegex(rootfile.UnsupportedClass, "hand-written"):
            decoder.within_extent(lambda: decoder.read_object("Hold", 0),
                                  0, len(buf), lambda v: v.end)


class ThisElement(unittest.TestCase):
    """Collections.md 11.2: a class that is a collection, read from its title.

    The shape of ATLAS's `xAOD::CutBookkeeperContainer_v1`: one `TStreamerSTL`
    named `This`, `fSTLtype` 2 (list), its own class as the type name, and the
    value class only in the title.
    """

    def this(self, title="<V> Used to call the proper TStreamerInfo case"):
        el = element("This", cls="TStreamerSTL", ftype=500, title=title,
                     type_name="Container_v1")
        el.tail = {"fSTLtype": 2, "fCtype": 61}
        return el

    def test_the_value_class_is_the_bracketed_title(self):
        self.assertEqual(rootfile.collection_value(self.this()),
                         ("V", rootfile.STL_VECTOR))
        nested = self.this("<pair<int,W<a> >*> Used to call the proper case")
        self.assertEqual(rootfile.collection_value(nested)[0],
                         "pair<int,W<a> >*")

    def test_an_stl_class_is_read_by_its_name_not_its_title(self):
        # uproot-issue243.root's map<string,double> branch: ROOT builds the
        # proxy from the name, and the title's pair would need an info the
        # file does not have.
        el = self.this("<pair<string,double> > Used to call the proper case")
        el.type_name = "map<string,double>"
        el.tail = {"fSTLtype": rootfile.STL_MAP, "fCtype": 61}
        self.assertEqual(rootfile.collection_value(el),
                         ("pair<string,double>", rootfile.STL_MAP))

    def test_a_title_without_the_value_class_reads_nothing(self):
        with self.assertRaises(rootfile.UnsupportedClass):
            rootfile.collection_value(
                self.this("Used to call the proper TStreamerInfo case"))

    def test_a_member_wise_entry_is_read_as_a_vector_of_the_title(self):
        value = info(element("n"), name="V")
        container = info(self.this(), name="Container_v1")
        body = (b"\x40\x09"                            # member-wise, version 9
                b"\x00\x01"                            # V's version
                b"\x00\x00\x00\x02"                    # two elements
                b"\x00\x00\x00\x05\x00\x00\x00\x06")   # the n column
        buf = struct.pack(">I", 0x40000000 | len(body)) + body
        decoder = rootfile.Decoder(buf, 0, [value, container])
        self.assertEqual(decoder.read_collection(self.this(), 0), len(buf))
        self.assertEqual(decoder.member_wise, [("This", "V", 0, 1)])

    def test_invariant_11(self):
        alone = info(self.this(), name="Container_v1")
        self.assertEqual(check_invariants.this_element_failures(alone), [])
        crowded = info(self.this(), element("n"), name="Container_v1")
        self.assertEqual([w for w, _ in
                          check_invariants.this_element_failures(crowded)],
                         ["Collections 14.11"])
        renamed = info(self.this(), name="Other")
        self.assertTrue(check_invariants.this_element_failures(renamed))


class TObjectVersionWord(unittest.TestCase):
    """Buffer.md invariant 10: a TObject base's version word is 1."""

    FIXTURE = Path(__file__).resolve().parents[1] / \
        "data/serialization/unframed-records.root"

    def test_a_tobject_record_with_version_2_fails(self):
        buf = bytearray(self.FIXTURE.read_bytes())
        at = 439 + 60                     # the TObject record's 10-byte payload
        self.assertEqual(buf[at:at + 2], b"\x00\x01")
        buf[at + 1] = 2
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unframed-records.root"
            path.write_bytes(bytes(buf))
            failures = check_invariants.Checker(path).run()
        self.assertTrue(any("Buffer 9.10" in f and "version word 2" in f
                            for f in failures), failures)


SKIM = Path(__file__).resolve().parents[1] / "root/roottest/root/io/evolution/skim.root"


@unittest.skipUnless(SKIM.is_file(), "root/ submodule is not checked out")
class SkimHoldMuo(unittest.TestCase):
    """StreamerDriven.md 7.1 on the file it came from: `Jpsi.jmu1`, entry 0."""

    def test_the_entry_is_read_with_no_version_word(self):
        checker = check_invariants.Checker(SKIM)
        _, _, infos = checker.streamer_infos()
        for data, _, tree in checker.trees():
            reader = rootfile.TreeReader(checker.buf, tree, infos,
                                         checker.fetch_basket, tree_payload=data)
            for br in rootfile.walk_branches(tree.branches):
                if br.name == "Jpsi.jmu1":
                    start, end, consumed = reader.entry_end(br, 0)
                    self.assertEqual((end - start, consumed), (122, end))
                    return
        self.fail("no Jpsi.jmu1 branch")


class SynthesisedPair(unittest.TestCase):
    """Collections.md 8.1. A pair's members from the type name alone.

    The layouts are byte-verified in `serialization/pairs`; this checks the
    mapping from a template argument to the element that produces them, which is
    a rule rather than a byte pattern.
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
        # This gives its column the shared frame of section 4.1.
        first = self.members("pair<string,int>")[0]
        self.assertEqual(first[1:3], ("TStreamerSTLstring", 500))
        self.assertEqual(first[3], {"fSTLtype": rootfile.STL_STRING,
                                    "fCtype": rootfile.STL_STRING})

    def test_a_TString_is_not(self):
        # Unlike a std::string, a TString column has no frame at all.
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


class WhichClassesMustBeDescribed(unittest.TestCase):
    """StreamerDriven.md invariant 5, restated.

    The published invariant used to say that every class named by a base element
    or by any object-valued member has an info in the same file, exempting only
    `TObject`, `TNamed` and `TString`. It was false in both directions and had
    never been wired into the checker: `data/classes/histogram.root`, which ROOT
    wrote, names `TArrayF` as a base of `TH1F` and has no `TArrayF` info, and
    over the corpora 92 base elements and 489 inline members do the same. See
    §6.1; PLAN.md 8.13.
    """

    def failures(self, si, described=()):
        return [where for where, _ in
                check_invariants.undescribed_classes(si, set(described))]

    def test_a_described_base_passes(self):
        si = info(element("TAttLine", cls="TStreamerBase", ftype=0))
        self.assertEqual(self.failures(si, {"TAttLine"}), [])

    def test_an_undescribed_base_is_caught(self):
        si = info(element("TAttLine", cls="TStreamerBase", ftype=0))
        self.assertEqual(self.failures(si), ["StreamerDriven 10.5"])

    def test_a_hand_written_base_is_exempt(self):
        # The four classes in the review's counterexamples: every histogram file
        # ROOT writes names them and describes none of them.
        for name in ("TObject", "TArrayF", "TArrayD", "TArrayL64"):
            si = info(element(name, cls="TStreamerBase", ftype=0))
            self.assertEqual(self.failures(si), [], name)

    def test_a_forwarding_base_is_exempt(self):
        # TSeqCollection is a kBase of TList and TObjArray in 168 corpus files
        # and has an info in none of them.
        si = info(element("TSeqCollection", cls="TStreamerBase", ftype=0))
        self.assertEqual(self.failures(si), [])

    def test_a_delegating_or_extending_class_is_not_exempt(self):
        # The exemption is the `custom` list, not all of HandWrittenStreamers.md:
        # these three do call WriteClassBuffer, so their info is in the file.
        for name in ("TMatrixTSym", "RooWorkspace", "TAxis"):
            si = info(element(name, cls="TStreamerBase", ftype=0))
            self.assertEqual(self.failures(si), ["StreamerDriven 10.5"], name)

    def test_an_undescribed_inline_member_is_caught(self):
        for ftype in (61, 62, 81, 82):
            si = info(element("fThing", cls="TStreamerObjectAny", ftype=ftype,
                              type_name="Thing"))
            self.assertEqual(self.failures(si), ["StreamerDriven 10.5"],
                             f"fType {ftype}")

    def test_an_undescribed_arrow_pointer_is_caught(self):
        # kObjectp and kAnyp cannot be null and have no class record, so the
        # declared type is what was written. ElementTypes.md 7.
        for ftype in (63, 68):
            si = info(element("fThing", cls="TStreamerObjectPointer",
                              ftype=ftype, type_name="Thing*"))
            self.assertEqual(self.failures(si), ["StreamerDriven 10.5"],
                             f"fType {ftype}")

    def test_an_undescribed_nullable_pointer_is_allowed(self):
        # TTree::fTreeIndex is a TVirtualIndex* and 145 corpus files have no
        # TVirtualIndex info: the class is abstract, and a null pointer writes
        # four zero bytes naming no class.
        for ftype in (64, 69):
            si = info(element("fTreeIndex", cls="TStreamerObjectPointer",
                              ftype=ftype, type_name="TVirtualIndex*"))
            self.assertEqual(self.failures(si), [], f"fType {ftype}")

    def test_the_hardcoded_codes_are_not_checked(self):
        # kTString, kTObject and kTNamed are read by rule, not by an info.
        for ftype in (65, 66, 67):
            si = info(element("fName", ftype=ftype, type_name="TString"))
            self.assertEqual(self.failures(si), [], f"fType {ftype}")

    def test_an_stl_member_is_exempt(self):
        # `vector<double> twovectors[2]` reaches disk as code 82 and ROOT writes
        # no info for vector<double>: uproot-issue-586.root, 6.24/06.
        si = info(element("twovectors", cls="TStreamerObjectAny", ftype=82,
                          type_name="vector<double>"))
        self.assertEqual(self.failures(si), [])

    def test_a_specialization_matches_a_template_entry(self):
        si = info(element("fM", cls="TStreamerObjectAny", ftype=62,
                          type_name="TMatrixTSym<double>"))
        self.assertEqual(self.failures(si, {"TMatrixTSym"}), [])

    def test_an_element_may_spell_the_class_otherwise(self):
        # StreamerInfo.md 7.3. The info is named by the class's normalised
        # name; the element, before 6.00/00, by the member's declared spelling.
        # Each pair is from a roottest file ROOT wrote.
        cases = [
            # meta/evolution/checksum_v5.root, 5.34/18: a ROOT typedef
            ("UserTmplt<Int_t>", "UserTmplt<int>", "HasTypeDef"),
            # io/emulated/lariat-si.root, 6.11/01: long long is Long64_t
            ("artdaq::QuickVec<unsigned long long>",
             "artdaq::QuickVec<ULong64_t>", "artdaq::Fragment"),
            # meta/MakeProject/CMSSW_3_1_0_pre11-...root, 5.22/00: a default
            # template argument left out
            ("ROOT::Math::PositionVector3D<ROOT::Math::Cartesian3D<Double32_t> >",
             "ROOT::Math::PositionVector3D<ROOT::Math::Cartesian3D<Double32_t>,"
             "ROOT::Math::DefaultCoordinateSystemTag>", "reco::LeafCandidate"),
            # meta/evolution/version5/nestedColl.root, 5.34/33: the owner's
            # namespace left out
            ("OtherInner", "HepExp::OtherInner", "HepExp::Outer"),
        ]
        for spelled, recorded, owner in cases:
            si = info(element("fX", cls="TStreamerObjectAny", ftype=62,
                              type_name=spelled), name=owner)
            self.assertEqual(self.failures(si, {recorded}), [], spelled)

    def test_another_class_is_still_caught(self):
        # Double32_t is part of a normalised name, a user's typedef is not in
        # the file, and a name no class has stays unresolved.
        cases = [
            ("Cartesian3D<Double32_t>", {"Cartesian3D<double>"}),
            ("UserTmplt<Named_t>", {"UserTmplt<TNamed>"}),
            ("Belle2::ModuleStatistics::CalcMeanCov<2,value_type>",
             {"Belle2::CalcMeanCov<2,double>"}),
            ("A<int>", {"A<int,X>", "A<int,Y>"}),          # ambiguous
            ("A<int,X,Z>", {"A<int,X>"}),                  # longer, not shorter
            ("Inner", {"Other::Inner"}),                   # not an enclosing scope
        ]
        for spelled, described in cases:
            si = info(element("fX", cls="TStreamerObjectAny", ftype=62,
                              type_name=spelled), name="Outer::Holder")
            self.assertEqual(self.failures(si, described),
                             ["StreamerDriven 10.5"], spelled)


class RecordedClassName(unittest.TestCase):
    """rootfile.recorded_class_name and the checksum fallback of the Decoder."""

    def test_canonical_spelling(self):
        c = rootfile.canonical_class_name
        self.assertEqual(c("vector<pair<Char_t,UChar_t> >"),
                         "vector<pair<char,unsigned char> >")
        self.assertEqual(c("std::map<std::string, std::vector<Int_t>>"),
                         "map<string,vector<int> >")
        self.assertEqual(c("A<long long,unsigned long long>"),
                         "A<Long64_t,ULong64_t>")
        self.assertEqual(c("A<Double32_t,Float16_t>"), "A<Double32_t,Float16_t>")
        self.assertEqual(c("A<Int_t*>"), "A<int*>")

    def infos(self, *pairs):
        return [rootfile.StreamerInfo(name=n, title="", version=9, bits=0,
                                      checksum=k, class_version=1, elements=[])
                for n, k in pairs]

    def test_a_unique_checksum_names_the_class(self):
        d = rootfile.Decoder(b"", 0, self.infos(("HepExp::Inner", 0xCFDF7F18),
                                                ("HepExp::OtherInner", 0xF64AB7E0)))
        self.assertEqual(set(d.alias_by_checksum("Alias", 0xCFDF7F18)), {1})
        self.assertEqual(d.aliases["Alias"], "HepExp::Inner")
        self.assertEqual(d.infos_of("Alias")[1].name, "HepExp::Inner")

    def test_a_shared_checksum_names_nothing(self):
        d = rootfile.Decoder(b"", 0, self.infos(("A", 7), ("B", 7)))
        self.assertEqual(d.alias_by_checksum("C", 7), {})

    def test_never_for_a_pair_or_the_record_class(self):
        # A pair's checksum need not be unique (Collections.md 8.2), and a
        # TBasket's payload is not an object of its key's class.
        d = rootfile.Decoder(b"", 0, self.infos(("X", 7)))
        self.assertEqual(d.alias_by_checksum("pair<int,int>", 7), {})
        d.record_class = "TBasket"
        self.assertEqual(d.alias_by_checksum("TBasket", 7), {})


class OneIdentityTwoLayoutsIsCaught(unittest.TestCase):
    """SchemaEvolution 9.6 against a real file, by forging a duplicate.

    `data/written/two-versions.root` holds `Grown` at versions 1 and 2 with
    different checksums and different element lists, which is legitimate.
    Giving the second entry the first's version and checksum produces a state
    ROOT never writes: one identity, two layouts, and a reader that takes the
    wrong entry silently misdecodes. The record is uncompressed, so this is a
    byte patch.
    """

    PATH = Path(__file__).resolve().parents[1] / "data/written/two-versions.root"
    FIRST = struct.pack(">Ii", 0x0159165E, 1)       # fCheckSum, fClassVersion
    SECOND = struct.pack(">Ii", 0xEE119598, 2)

    def failures(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "forged.root"
            path.write_bytes(data)
            checker = check_invariants.Checker(path)
            checker.run()
            return checker.failures

    def test_the_fixture_itself_passes(self):
        self.assertEqual(self.failures(self.PATH.read_bytes()), [])

    def test_the_second_entry_claiming_the_first_identity(self):
        buf = bytearray(self.PATH.read_bytes())
        at = buf.find(self.SECOND)
        self.assertNotEqual(at, -1)
        self.assertEqual(buf.count(self.SECOND), 1)
        buf[at:at + 8] = self.FIRST
        bad = self.failures(bytes(buf))
        self.assertEqual(len(bad), 2)
        # 9.6 states the rule and 10.1 shows the consequence: the version-1
        # object is now decoded through a two-element layout and over-runs its
        # byte count.
        self.assertIn("SchemaEvolution 9.6", bad[1])
        self.assertIn("(1 and 2 elements)", bad[1])
        self.assertIn("StreamerDriven 10.1", bad[0])


class SetAndMultimapWereSwapped(unittest.TestCase):
    """Collections.md 1 and invariant 10: the repair `rootfile.py` lacked.

    `TStreamerSTL` numbered kSTLset 5 and kSTLmultimap 6 until 5.34/13, the
    reverse of every other use of the enum, and the read-side repair arrived only
    in 6.00/00. The element version is 3 on both sides, so only `fTypeName` can
    tell them apart. A reader that takes 5 at face value reads a set as a
    multimap and consumes two values per element.

    The corpus tests below drive the real parser, where the repair lives; they
    are the ones that fail without it.
    """

    BUILD = Path(__file__).resolve().parents[1] / "build"

    def find(self, name):
        for sub in ("foreign", "cern"):
            path = self.BUILD / sub / name
            if path.exists():
                return path
        return None

    def elements(self, name):
        path = self.find(name)
        if path is None:
            self.skipTest(f"{name} not fetched")
        _, _, infos = check_invariants.Checker(path).streamer_infos()
        return {(i.name, e.name): e for i in infos for e in i.elements}

    def test_a_pre_5_34_13_set_is_repaired(self):
        """uproot-issue283.root has fSTLtype 5 on a set<long>."""
        el = self.elements("uproot-issue283.root")[("I3Eval_t", "BadChannelIDSet")]
        self.assertEqual(el.type_name, "set<long>")
        self.assertEqual(el.tail["fSTLtype"], rootfile.STL_SET)
        self.assertEqual(el.version, 3)

    def test_the_same_member_from_both_eras_reads_the_same(self):
        """RooAbsArg._boolAttrib is a set<string> written as 5 and as 6."""
        seen = set()
        for name in ("stressRooFit_v534_ref.root", "uproot-issue49.root"):
            if self.find(name) is None:
                continue
            el = self.elements(name)[("RooAbsArg", "_boolAttrib")]
            self.assertEqual(el.type_name, "set<string>")
            seen.add(el.tail["fSTLtype"])
        if not seen:
            self.skipTest("neither RooFit file is fetched")
        # 5 on disk in the older file, 6 in the newer, and one value out here.
        self.assertEqual(seen, {rootfile.STL_SET})

    def test_a_pre_5_24_multimap_is_stored_as_a_map(self):
        """Collections.md 1: before 5.24/00 the name-parsing constructor tested
        "map" before "multimap". ROOT's repair covers 5 and 6 only, so the 4
        survives the parser, and invariant 10 is scoped by release."""
        path = (Path(__file__).resolve().parents[1] / "root/roottest/root/meta/"
                "MakeProject/CMSSW_3_1_0_pre11-RelValZTT-default-copy.root")
        if not path.exists():
            self.skipTest("root/roottest is not checked out")
        checker = check_invariants.Checker(path)
        self.assertEqual(checker.header.root_version, (5, 22, 0))
        _, _, infos = checker.streamer_infos()
        el = next(e for i in infos if i.name == "reco::IsoDeposit"
                  for e in i.elements if e.name == "theDeposits")
        self.assertTrue(el.type_name.startswith("multimap<"))
        self.assertEqual(el.tail["fSTLtype"], rootfile.STL_MAP)
        self.assertLess(checker.header.root_version,
                        check_invariants.STL_KIND_FROM_NAME_SINCE)

    def test_every_collection_element_agrees_with_its_type_name(self):
        """Invariant 10, over one file, through the real parser."""
        for (cls, member), el in self.elements("uproot-issue283.root").items():
            if el.cls != "TStreamerSTL":
                continue
            stl = el.tail["fSTLtype"]
            bare = stl - rootfile.OFFSET_P if 40 <= stl <= 54 else stl
            if bare in (300, 365):
                continue
            with self.subTest(f"{cls}.{member}"):
                self.assertEqual(bare, rootfile.stl_kind(el.type_name))

    def test_stl_kind_knows_the_published_table(self):
        for name, want in (("set<long>", 6), ("multimap<int,int>", 5),
                           ("map<int,int>", 4), ("vector<float>", 1),
                           ("std::unordered_map<int,int>", 12),
                           ("bitset<8>", 8)):
            self.assertEqual(rootfile.stl_kind(name), want, name)

    def test_rvec_is_a_known_container(self):
        # fSTLtype 14, published in Collections.md 1 and missing from the reader
        # until 2026-09-21.
        self.assertEqual(rootfile.stl_kind("ROOT::VecOps::RVec<float>"), 14)

    def test_a_const_qualified_name_resolves(self):
        self.assertEqual(rootfile.stl_kind("const vector<int>"), 1)


class PublishedExemptionLists(unittest.TestCase):
    """The two lists invariant 5 exempts, as `check_invariants` reads them.

    They are parsed out of the generated blocks of spec/99-appendix/ rather than
    extracted from the submodule, so that the checker runs without it. These
    tests stop the parse from silently widening or emptying: an empty exemption
    set would make invariant 5 fire everywhere, and a set that took in the
    `guarded` and `delegating` tables would make it fire nowhere.
    """

    def test_the_custom_classes_are_exempt(self):
        for name in ("TObject", "TArrayD", "TObjArray", "TList", "TQObject",
                     "TStringLong", "TDatime"):
            self.assertIn(name, check_invariants.NO_INFO_OF_ITS_OWN, name)

    def test_the_forwarding_classes_are_exempt(self):
        for name in ("TSeqCollection", "THashList", "TVirtualPerfStats"):
            self.assertIn(name, check_invariants.NO_INFO_OF_ITS_OWN, name)

    def test_the_other_three_tables_are_not_read(self):
        # extending, delegating and guarded, one each. TStreamerInfo would be a
        # bad example: its ReadClassBuffer call is commented out and replaced, so
        # inventory.py classifies it `custom` and it belongs in the set.
        for name in ("TMatrixTSym", "RooWorkspace", "TAxis"):
            self.assertNotIn(name, check_invariants.NO_INFO_OF_ITS_OWN, name)

    def test_an_ordinary_class_is_not_exempt(self):
        for name in ("TTree", "TH1", "TAttLine", "TH1F"):
            self.assertNotIn(name, check_invariants.NO_INFO_OF_ITS_OWN, name)

    def test_the_lists_are_the_published_sizes(self):
        # 63 custom + 534 forwarding, as the summary tables in those two
        # documents state. A submodule bump changes these, and the documents and
        # this number must then be updated together.
        self.assertEqual(len(check_invariants.NO_INFO_OF_ITS_OWN), 597)


class RemovingAnInfoIsCaught(unittest.TestCase):
    """Invariant 5 against a real file, by taking an info out of one.

    `data/serialization/version-zero.root` has an uncompressed `StreamerInfo`
    record, so renaming a class inside it is a byte patch. Both sides of the
    break are tested: an info entry removed while a base element still names it,
    and a base element naming a class that was never there.
    """

    PATH = Path(__file__).resolve().parents[1] / "data/serialization/version-zero.root"
    NAME = b"\x08TAttLine"

    def patched(self, which):
        """The fixture with one of the two `TAttLine` strings misspelt."""
        buf = bytearray(self.PATH.read_bytes())
        offsets = [i for i in range(len(buf))
                   if buf[i:i + len(self.NAME)] == self.NAME]
        self.assertEqual(len(offsets), 2)       # the element, then the info
        buf[offsets[which] + 8] = ord("f")      # TAttLine -> TAttLinf
        return bytes(buf)

    def failures(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corrupt.root"
            path.write_bytes(data)
            checker = check_invariants.Checker(path)
            checker.run()
            return checker.failures

    def test_the_fixture_itself_passes(self):
        self.assertEqual(self.failures(self.PATH.read_bytes()), [])

    def test_a_base_naming_a_class_that_is_not_there(self):
        bad = self.failures(self.patched(0))
        self.assertEqual(len(bad), 1)
        self.assertIn("StreamerDriven 10.5", bad[0])
        self.assertIn("TAttLinf", bad[0])

    def test_an_info_renamed_out_from_under_its_base_element(self):
        bad = self.failures(self.patched(1))
        self.assertEqual(len(bad), 1)
        self.assertIn("StreamerDriven 10.5", bad[0])
        self.assertIn("TH1: base class TAttLine", bad[0])


class StlElementStoresFiveHundred(unittest.TestCase):
    """StreamerInfo.md invariant 9 and ElementTypes.md invariants 1-2.

    Every ROOT-written file available stores 500 on an STL element, back to
    ROOT 3.04; the 300 that used to be exempted for "ROOT 4" came from two
    g4tools files, which are now in gen/foreign/IGNORE.toml instead
    (StreamerInfo.md 10.1). So 300 must fail on a file whose header names
    ROOT 6, and the checks must not depend on the header's version at all.
    `data/serialization/streamer-info.root` has `fVec`'s fType at 841,
    uncompressed.
    """

    PATH = Path(__file__).resolve().parents[1] / "data/serialization/streamer-info.root"
    FTYPE = 841

    def failures(self, ftype, version=None):
        buf = bytearray(self.PATH.read_bytes())
        self.assertEqual(struct.unpack_from(">i", buf, self.FTYPE)[0], 500)
        struct.pack_into(">i", buf, self.FTYPE, ftype)
        if version is not None:
            struct.pack_into(">i", buf, 4, version)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corrupt.root"
            path.write_bytes(bytes(buf))
            checker = check_invariants.Checker(path)
            checker.run()
            return sorted({f.split(": ")[1] for f in checker.failures})

    def test_the_fixture_itself_passes(self):
        self.assertEqual(self.failures(500), [])

    def test_the_real_code_is_caught(self):
        self.assertEqual(self.failures(300),
                         ["ElementTypes 11.1", "ElementTypes 11.2",
                          "StreamerInfo 13.9"])

    def test_a_header_claiming_root_4_exempts_nothing(self):
        self.assertEqual(self.failures(300, version=40000),
                         ["ElementTypes 11.1", "ElementTypes 11.2",
                          "StreamerInfo 13.9"])


class PointerContentIsNotADoubledFrame(unittest.TestCase):
    """Collections.md 3.1, against `data/serialization/pointer-collection.root`.

    The first outside review of this specification read the two consecutive
    frames before a pointer content's members as a *doubled collection frame*
    (issue #1 item 10). They are a collection frame and a class frame; this pins
    both, plus the three object-slot forms one collection holds.
    """

    PATH = (Path(__file__).resolve().parents[1]
            / "data/serialization/pointer-collection.root")

    @classmethod
    def setUpClass(cls):
        cls.buf, _, records = rootfile.load(cls.PATH)
        cls.rec = next(r for r in records
                       if not r.free and r.class_name == "PointerCollection")
        info_rec = next(r for r in records
                        if not r.free and r.name == "StreamerInfo")
        cls.infos = rootfile.read_streamer_infos(
            rootfile.object_data(cls.buf, info_rec), info_rec)

    def decoder(self):
        return rootfile.Decoder(self.buf, self.rec.offset, self.infos)

    def element(self, name):
        info = next(i for i in self.infos if i.name == "PointerCollection")
        return next(e for e in info.elements if e.name == name)

    def test_the_three_frames_nest(self):
        # 381 the collection frame, 391 the object slot, 407 the class frame,
        # 413 a second collection frame, inside the content class rather than
        # beside the first one.
        outer = rootfile.read_frame(self.buf, 381)
        self.assertEqual((outer.version, outer.end), (10, 475))
        inner = rootfile.read_frame(self.buf, 407)
        self.assertEqual((inner.version, inner.end), (1, 439))
        innermost = rootfile.read_frame(self.buf, 413)
        self.assertEqual((innermost.version, innermost.end), (10, 439))
        # The class frame's version word is PtrItem's ClassDef version. The two
        # kinds cannot be told apart by the version word alone.
        self.assertNotEqual(inner.version, innermost.version)

    def test_the_collection_consumes_exactly_its_byte_count(self):
        el = self.element("fPtrs")
        self.assertEqual(self.decoder().read_collection(el, 381), 475)
        self.assertEqual(struct.unpack_from(">i", self.buf, 475)[0],
                         0x7E7E7E7E)

    def test_the_three_slots_end_three_different_ways(self):
        # kNewClassTag, a null pointer, and a class back-reference, in one
        # collection: nothing in the collection frame says which is which.
        self.assertEqual(struct.unpack_from(">I", self.buf, 395)[0], 0xFFFFFFFF)
        self.assertEqual(struct.unpack_from(">I", self.buf, 439)[0], 0)
        self.assertEqual(struct.unpack_from(">I", self.buf, 447)[0], 0x80000045)

    def test_a_null_element_is_four_bytes_with_no_frame(self):
        # The slot at 439 is followed immediately by the third slot's byte
        # count, so the null occupied four bytes and nothing else.
        self.assertEqual(struct.unpack_from(">I", self.buf, 443)[0],
                         0x40000000 | 28)

    def test_taking_the_class_frame_for_a_collection_frame_is_caught(self):
        # The misreading: treat the frame at 407 as the collection's own and
        # read a count where PtrItem's members begin. `read_collection` is
        # pointed at 407 rather than 381, and the byte count no longer delimits
        # what it consumes.
        el = self.element("fPtrs")
        with self.assertRaises((rootfile.FormatError, struct.error)):
            self.decoder().read_collection(el, 407)


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
        # A file written before ROOT 6.36 has 9 here, not 10, so the word must
        # not be compared to 10. ElementTypes.md 8.1.
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


class FixedArrayOfCollections(unittest.TestCase):
    """Collections.md 11.1. One frame, then fArrayLength collections."""

    def stl(self, array_length):
        return rootfile.Element(
            cls="TStreamerSTL", version=4, name="fVecArr", title="", bits=0,
            ftype=500, fsize=24, array_length=array_length, array_dim=1,
            max_index=[array_length, 0, 0, 0, 0], type_name="vector<int>",
            tail={"fSTLtype": 1, "fCtype": 3})

    BUF = (b"\x40\x00\x00\x16\x00\x0a"                  # one shared frame
           b"\x00\x00\x00\x02\x00\x00\x00\x0b\x00\x00\x00\x0c"
           b"\x00\x00\x00\x01\x00\x00\x00\x0d")

    def test_both_collections_are_inside_the_one_frame(self):
        el = self.stl(2)
        decoder = rootfile.Decoder(self.BUF, 0, [info(el, name="C")])
        self.assertEqual(decoder.read_collection(el, 0), len(self.BUF))

    def test_reading_only_the_first_is_caught(self):
        # A reader that switches on the stored fType alone does this: the code
        # is 500 either way, and only fArrayLength says there are two.
        el = self.stl(0)
        decoder = rootfile.Decoder(self.BUF, 0, [info(el, name="C")])
        with self.assertRaises(rootfile.FormatError):
            decoder.read_collection(el, 0)


class PointerToCollection(unittest.TestCase):
    """Collections.md 11.1 and 11.3, against `ttree/split-stl-pointer`.

    A `vector<PItem>*` member (fSTLtype 41) is written as the collection it
    points to: no pointer tag, no null marker. An array of collections, of
    pointers or not, shares one frame and one value-class version. The bytes
    are the fixture's.
    """

    ITEM = info(element("fA", ftype=3), element("fB", ftype=5), name="PItem")

    @staticmethod
    def stl(type_name, stl, array_length=0):
        return replace(element("m", cls="TStreamerSTL", ftype=500,
                               type_name=type_name),
                       array_length=array_length,
                       tail={"fSTLtype": stl, "fCtype": 61})

    @staticmethod
    def framed(version, body):
        return (struct.pack(">IH", 0x40000000 | (2 + len(body)), version)
                + body)

    def read(self, el, buf):
        decoder = rootfile.Decoder(buf, 0, [self.ITEM, info(el, name="H")])
        return decoder.read_collection(el, 0), decoder

    def test_a_pointer_has_no_tag(self):
        # fPtr, entry 2: PItem v1, two elements, the fA column, the fB column.
        buf = self.framed(0x400a, bytes.fromhex(
            "0001 00000002 00000014 00000015 00000000 3f000000"))
        end, decoder = self.read(self.stl("vector<PItem>*", 41), buf)
        self.assertEqual(end, len(buf))
        self.assertEqual(decoder.member_wise, [("m", "PItem", 0, 1)])

    def test_an_array_of_pointers_shares_the_value_version(self):
        # fPtrArr[2], entry 1: one PItem version, then count 0 and count 1.
        buf = self.framed(0x400a, bytes.fromhex(
            "0001 00000000 00000001 00000014 3fc00000"))
        end, _ = self.read(self.stl("vector<PItem>*", 41, 2), buf)
        self.assertEqual(end, len(buf))

    def test_an_array_of_collections_shares_the_value_version(self):
        # fArr[2], entry 1. Reading a version per array element took the
        # second count's high half for a version of 0 and a checksum.
        buf = self.framed(0x400a, bytes.fromhex(
            "0001 00000001 0000001e 40200000 00000000"))
        end, _ = self.read(self.stl("vector<PItem>", 1, 2), buf)
        self.assertEqual(end, len(buf))

    def test_before_version_9_a_pointer_has_no_value_version(self):
        # TStreamerInfo 8 wrote the value version for a collection but not yet
        # for a pointer to one (root commit 40d8dd3552d).
        body = bytes.fromhex("00000001 00000007 3f800000")
        self.assertEqual(
            self.read(self.stl("vector<PItem>*", 41),
                      self.framed(0x4008, body))[0], 6 + len(body))
        self.assertEqual(
            self.read(self.stl("vector<PItem>", 1),
                      self.framed(0x4008, b"\x00\x01" + body))[0],
            8 + len(body))

    def test_an_object_wise_pointer_is_the_collection(self):
        # A `//||` member: count, then each PItem with its own frame.
        item = struct.pack(">IHif", 0x4000000a, 1, 80, 3.5)
        buf = self.framed(10, struct.pack(">i", 2) + item + item)
        self.assertEqual(self.read(self.stl("vector<PItem>*", 41), buf)[0],
                         len(buf))

    def test_empty_collections_need_no_value_info(self):
        # uproot-issue468.root: an empty member-wise collection of a class the
        # file has no info for. Nothing follows the counts, so nothing is
        # looked up.
        el = self.stl("vector<Missing>", 1, 2)
        buf = self.framed(0x400a, bytes.fromhex("0001 00000000 00000000"))
        decoder = rootfile.Decoder(buf, 0, [info(el, name="H")])
        self.assertEqual(decoder.read_collection(el, 0), len(buf))

    def test_a_pointer_to_a_set_is_read_by_its_name(self):
        # The set/multimap repair skips the pointer forms, so 45 can mean a
        # set; ROOT's proxy comes from the type name. Collections.md 1.
        self.assertEqual(rootfile.collection_value(self.stl("set<int>*", 45)),
                         ("int", rootfile.STL_SET))
        self.assertEqual(
            rootfile.collection_value(self.stl("vector<PItem>*", 41)),
            ("PItem", rootfile.STL_VECTOR))

    def test_an_array_of_strings_shares_one_frame(self):
        # std::string fStrArr[2]: two counted strings under one frame, as in
        # stringarray.old.root (roottest issue-8083).
        el = replace(self.stl("string", rootfile.STL_STRING, 2),
                     cls="TStreamerSTLstring")
        buf = self.framed(10, b"\x01x\x02yy")
        self.assertEqual(self.read(el, buf)[0], len(buf))


class RefVariants(unittest.TestCase):
    """References.md 3.1 and 3.2."""

    def test_the_plain_form_is_twelve_bytes(self):
        buf = b"\x00\x01" + b"\x00\x00\x00\x01" + b"\x00\x00\x00\x00" + b"\x00\x00"
        ref = rootfile.read_ref(buf, 0)
        self.assertEqual((ref.end, ref.pidf), (12, 0))

    def test_kHasUUID_replaces_the_pidf_with_a_counted_string(self):
        buf = b"\x00\x01" + b"\x00\x00\x00\x01" + b"\x00\x00\x00\x20" + b"\x03abc"
        ref = rootfile.read_ref(buf, 0)
        self.assertEqual(ref.end, 14)
        self.assertIsNone(ref.pidf)

    def test_the_exec_index_is_one_based_and_changes_nothing_else(self):
        buf = b"\x00\x01" + b"\x00\x00\x00\x01" + b"\x00\x02\x00\x00" + b"\x00\x00"
        ref = rootfile.read_ref(buf, 0)
        self.assertEqual(ref.end, 12)
        self.assertEqual(rootfile.ref_exec_id(ref.bits), 2)

    def test_no_action_is_zero(self):
        self.assertEqual(rootfile.ref_exec_id(0x00000020), 0)


class UnpromotedCounter(unittest.TestCase):
    """ElementTypes.md 2.1: a counter need not be kCounter.

    Only a counter whose code is below 6 is promoted to kCounter
    (root/core/meta/src/TStreamerElement.cxx:99), so a UInt_t counter keeps
    kUInt (13). TBits is the case in real files: fAllBits names fNbytes, which
    is fType 13 (uproot-issue213.root, alice_ESDs.root, ttree/split-tbits).
    """

    #: TBits v1 with fNbits 3 and fNbytes 2: the frame, then the members.
    BODY = (b"\x00\x00\x00\x03"             # fNbits = 3
            b"\x00\x00\x00\x02"             # fNbytes = 2
            b"\x01\x05\x00")                 # fAllBits: present, two bytes
    FRAMED = b"\x40\x00\x00\x0d\x00\x01" + BODY

    @staticmethod
    def tbits(counter_type):
        return info(element("fNbits", ftype=13, type_name="UInt_t"),
                    element("fNbytes", ftype=counter_type, type_name="UInt_t"),
                    element("fAllBits", cls="TStreamerBasicPointer", ftype=51,
                            count_name="fNbytes", type_name="UChar_t"),
                    name="TBits")

    def test_every_integer_counter_code_gives_the_count(self):
        for ftype in (3, 6, 13):
            decoder = rootfile.Decoder(self.FRAMED, 0, [self.tbits(ftype)])
            values = decoder.read_members("TBits", 1, 6, len(self.FRAMED))
            self.assertEqual(values[2].end - values[2].start, 3, f"fType {ftype}")

    def test_an_unframed_read_keeps_it_too(self):
        # read_elements serves an unsplit branch's entry, ReadingEntries.md 3.3.
        decoder = rootfile.Decoder(self.BODY, 0, [])
        self.assertEqual(decoder.read_elements(self.tbits(13), 0), len(self.BODY))


class RefArrayLength(unittest.TestCase):
    """References.md invariant 5, evaluated as published.

    Until 2026-09-24 the formula omitted the byte count and the version word,
    and the checker verified the record only by consumption, so the arithmetic
    was never exercised. The fixture's array has an empty fName, one entry and
    an unreferenced TObject.
    """

    PATH = Path(__file__).resolve().parent.parent / "data/serialization/references.root"

    def test_the_formula_gives_the_payload_length(self):
        buf = self.PATH.read_bytes()
        rec = next(r for r in rootfile.read_records(buf, rootfile.read_header(buf))
                   if r.class_name == "TRefArray")
        start, end = rootfile.payload_range(rec)
        arr = rootfile.read_ref_array(buf, start)
        self.assertEqual((arr.name, arr.nobjects, arr.tobject.referenced),
                         ("", 1, False))
        formula = 4 + 2 + 10 + (1 + 0) + 4 + 4 + 2 + 4 * 1
        self.assertEqual(end - start, formula)
        self.assertEqual(end - start, 31)


class ChoosingAnInfo(unittest.TestCase):
    """SchemaEvolution.md 4 step 1: a lone info stands in for version 1 only.

    ROOT reads a version 1 it has no info for with the class's current layout
    (TBufferFile.cxx:3505) and skips any other unmatched version. Taking the
    lone info for every version let two g4tools TH1D records read one frame off
    at every level and still land on their byte counts (erratum 7).
    """

    def decoder(self, class_version):
        si = replace(info(element("fX"), name="C"), class_version=class_version)
        return rootfile.Decoder(b"", 0, [si])

    def test_an_exact_match_is_taken(self):
        self.assertEqual(self.decoder(3).info_for("C", 3).class_version, 3)

    def test_version_1_borrows_the_only_info(self):
        self.assertEqual(self.decoder(2).info_for("C", 1).class_version, 2)

    def test_an_unknown_version_borrows_the_only_info(self):
        # A TStreamerBase with fBaseVersion -1 and no checksum.
        self.assertEqual(self.decoder(2).info_for("C", -1).class_version, 2)

    def test_any_other_version_is_not_readable(self):
        with self.assertRaises(rootfile.UnsupportedClass):
            self.decoder(1).info_for("C", 3)


class ThisElementInvariant(unittest.TestCase):
    """Collections.md invariant 11, which no file in data/ exercises.

    A class that is itself a collection gets a single `This` element whose type
    name is the class (TStreamerInfo.cxx:421-435). The only witness is a corpus
    file, uproot-physlite-rntuple_v1-0-0-0.root, which CI does not fetch, so
    these are what show the check can fail at all.
    """

    @staticmethod
    def this(type_name):
        return replace(element("This", cls="TStreamerSTL", ftype=500,
                               type_name=type_name),
                       tail={"fSTLtype": 1, "fCtype": 61})

    def failures(self, si):
        return [w for w, _ in check_invariants.this_element_failures(si)]

    def test_the_only_element_naming_its_class_passes(self):
        si = info(self.this("DataVector<xAOD::Jet>"), name="DataVector<xAOD::Jet>")
        self.assertEqual(self.failures(si), [])

    def test_a_this_element_beside_another_fails(self):
        si = info(self.this("C"), element("fX"), name="C")
        self.assertEqual(self.failures(si), ["Collections 14.11"])

    def test_a_this_element_naming_another_class_fails(self):
        si = info(self.this("vector<int>"), name="C")
        self.assertEqual(self.failures(si), ["Collections 14.11"])


if __name__ == "__main__":
    unittest.main()
