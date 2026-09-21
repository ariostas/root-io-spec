#!/usr/bin/env python3
"""Tests for the streamer-driven read of spec/02-serialization/StreamerDriven.md.

The byte-level checks live in check_invariants.py and run against the reference
files. These cover the two things a fixture cannot: the width of a quantised
member, whose encoding table is easier to state than to generate, and element
lists that no file ROOT wrote would contain.
"""

import struct
import sys
import tempfile
import unittest
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
    """SchemaEvolution.md invariants 1 and 6."""

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

    def test_one_layout_twice_must_be_the_same_layout(self):
        # Invariant 6, which is what makes 8.1's "take either entry" safe. Same
        # class, same version, same checksum, different elements: ROOT writes no
        # such pair, and a reader that took the wrong one would decode silently
        # wrong. No fixture can hold it.
        a = info(element("fA"), name="A")
        b = info(element("fB"), name="A")
        self.assertEqual(self.failures([a, b]), ["SchemaEvolution 9.6"])

    def test_the_same_layout_twice_passes(self):
        # The ROOT::TIOFeatures pair: identical elements, and in three corpus
        # files only fBits differs -- kIsCompiled in one, kBuildOldUsed in the
        # other two. fBits is not part of the comparison, so this passes.
        a, b = info(element("fA"), name="A"), info(element("fA"), name="A")
        b.bits = 0x3010000
        self.assertEqual(self.failures([a, b]), [])

    def test_two_versions_of_one_class_are_not_compared(self):
        # data/written/two-versions.root: Grown at versions 1 and 2 with
        # different checksums and different elements. Legitimate, and the
        # object's version word chooses between them.
        a = info(element("fA"), name="Grown")
        b = info(element("fA"), element("fB"), name="Grown")
        b.class_version, b.checksum = 2, 0xEE119598
        self.assertEqual(self.failures([a, b]), [])


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


class WhichClassesMustBeDescribed(unittest.TestCase):
    """StreamerDriven.md invariant 5, restated.

    The published invariant used to say that every class named by a base element
    or by any object-valued member has an info in the same file, exempting only
    `TObject`, `TNamed` and `TString`. It was false in both directions and had
    never been wired into the checker: `data/classes/histogram.root`, which ROOT
    wrote, names `TArrayF` as a base of `TH1F` and carries no `TArrayF` info, and
    over the corpora 92 base elements and 489 inline members do the same. See
    §6.1; PLAN-review.md R2.
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
        # The four the review's counterexamples were: every histogram file ROOT
        # writes names them and describes none of them.
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
        # kObjectp and kAnyp cannot be null and carry no class record, so the
        # declared type is what was written. ElementTypes.md 7.
        for ftype in (63, 68):
            si = info(element("fThing", cls="TStreamerObjectPointer",
                              ftype=ftype, type_name="Thing*"))
            self.assertEqual(self.failures(si), ["StreamerDriven 10.5"],
                             f"fType {ftype}")

    def test_an_undescribed_nullable_pointer_is_allowed(self):
        # TTree::fTreeIndex is a TVirtualIndex* and 145 corpus files carry no
        # TVirtualIndex info: the class is abstract, and a null pointer writes
        # four zero bytes naming nothing.
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


class OneIdentityTwoLayoutsIsCaught(unittest.TestCase):
    """SchemaEvolution 9.6 against a real file, by forging a duplicate.

    `data/written/two-versions.root` holds `Grown` at versions 1 and 2 with
    different checksums and different element lists, which is legitimate. Making
    the second entry claim the first's version and checksum is the state ROOT
    never writes: one identity, two layouts, and a reader that takes the wrong
    entry decodes silently wrong. The record is uncompressed, so it is a byte
    patch.
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
        # 9.6 states it, and 10.1 is what it costs: the version-1 object is now
        # decoded through a two-element layout and over-runs its byte count.
        self.assertIn("SchemaEvolution 9.6", bad[1])
        self.assertIn("(1 and 2 elements)", bad[1])
        self.assertIn("StreamerDriven 10.1", bad[0])


class SetAndMultimapWereSwapped(unittest.TestCase):
    """Collections.md 1 and invariant 10: the repair `rootfile.py` lacked.

    `TStreamerSTL` numbered kSTLset 5 and kSTLmultimap 6 until 5.34/13, the
    reverse of every other use of the enum, and the read-side repair arrived only
    in 6.00/00. The element version is 3 on both sides, so `fTypeName` is the only
    thing that can decide -- and a reader that takes 5 at face value reads a set
    as a multimap and consumes two values per element.

    The corpus tests below drive the real parser, which is where the repair lives;
    they are the ones that fail without it.
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
        """uproot-issue283.root carries fSTLtype 5 on a set<long>."""
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
    tests are what stops the parse from silently widening or emptying -- an empty
    exemption set would make invariant 5 fire everywhere, and a set that
    swallowed the `guarded` and `delegating` tables would make it fire nowhere.
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
        # this number then move together.
        self.assertEqual(len(check_invariants.NO_INFO_OF_ITS_OWN), 597)


class RemovingAnInfoIsCaught(unittest.TestCase):
    """Invariant 5 against a real file, by taking an info out of one.

    `data/serialization/version-zero.root` has an uncompressed `StreamerInfo`
    record, so renaming a class inside it is a byte patch. Both halves of the
    same break are provoked: the info entry disappearing under a base element
    that still names it, and the base element naming a class that was never
    there.
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
        # What a reader that switches on the stored fType alone would do: the
        # code is 500 either way, and only fArrayLength says there are two.
        el = self.stl(0)
        decoder = rootfile.Decoder(self.BUF, 0, [info(el, name="C")])
        with self.assertRaises(rootfile.FormatError):
            decoder.read_collection(el, 0)


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
