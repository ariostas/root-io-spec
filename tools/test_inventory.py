#!/usr/bin/env python3
"""Tests for tools/inventory.py.

The tool runs against the pinned submodule, and that run is the check that
matters. These cover the source scanning, where a silent mis-parse would produce
a plausible-looking answer in the wrong direction — classifying a class as
needing no specification when it does. Three real cases already went that way
before the blanking and namespace passes existed, and each has a test here.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import inventory  # noqa: E402


def only(text: str) -> tuple[str, str]:
    """The single definition in `text`, as (qualified name, classification)."""
    code = inventory.blank(text)
    matches = list(inventory.DEFINITION.finditer(code))
    assert len(matches) == 1, f"{len(matches)} definitions, expected 1"
    match = matches[0]
    scope = inventory.enclosing(code, [match.start()])[match.start()]
    body = inventory.body(code, match.start())
    assert scope is not None and body is not None
    name = "::".join(scope + inventory.qualifier(match.group(1))
                     + [match.group(2)])
    return name, inventory.classify(body, {match.group(4) or "R__b"})


class Classification(unittest.TestCase):

    def test_unconditional_read_class_buffer_is_delegating(self):
        _, kind = only("""
            void X::Streamer(TBuffer &R__b) {
               if (R__b.IsReading()) {
                  R__b.ReadClassBuffer(X::Class(), this);
                  fixup();
               } else { R__b.WriteClassBuffer(X::Class(), this); }
            }
            """)
        self.assertEqual(kind, "delegating")

    def test_a_version_threshold_is_guarded(self):
        _, kind = only("""
            void X::Streamer(TBuffer &R__b) {
               Version_t R__v = R__b.ReadVersion(&R__s, &R__c);
               if (R__v > 2) { R__b.ReadClassBuffer(X::Class(), this); return; }
               R__b >> fOld;
            }
            """)
        self.assertEqual(kind, "guarded")

    def test_the_guard_variable_need_not_be_named_R__v(self):
        """`ROOT::v5::TFormula` and `ROOT::v5::TF1Data` call it `v`.

        Assuming `R__v` would call this `delegating` — "a reader needs nothing"
        — which is the wrong direction to be wrong in.
        """
        _, kind = only("""
            void X::Streamer(TBuffer &b) {
               Version_t v = b.ReadVersion(&R__s, &R__c);
               if (v > 3) { b.ReadClassBuffer(X::Class(), this); return; }
               b >> fOld;
            }
            """)
        self.assertEqual(kind, "guarded")

    def test_a_commented_out_read_class_buffer_does_not_count(self):
        """`TStreamerInfo::Streamer` is exactly this, and it is the bootstrap."""
        _, kind = only("""
            void X::Streamer(TBuffer &R__b) {
               Version_t R__v = R__b.ReadVersion(&R__s, &R__c);
               if (R__v > 1) {
                  //R__b.ReadClassBuffer(X::Class(), this, R__v, R__s, R__c);
                  R__b.ClassBegin(X::Class(), R__v);
               }
            }
            """)
        self.assertEqual(kind, "custom")

    def test_an_empty_streamer_is_custom(self):
        """`TQObject`: zero bytes in either direction."""
        _, kind = only("""
            void X::Streamer(TBuffer &R__b) {
               if (R__b.IsReading()) {
                  // nothing to read
               } else {
                  // nothing to write
               }
            }
            """)
        self.assertEqual(kind, "custom")


class Extending(unittest.TestCase):
    """Reads that follow `ReadClassBuffer`, which is the dangerous case.

    Before this category existed the three classes here were `delegating` --
    published as "a reader needs nothing" -- and the corpora had been reporting
    the consequence for months as a `TMatrixTSym` decoding 48 bytes of 3528.
    """

    def test_a_read_after_read_class_buffer_is_extending(self):
        """`TMatrixTSym`: the upper-right triangle follows the base's members."""
        _, kind = only("""
            void X::Streamer(TBuffer &R__b) {
               if (R__b.IsReading()) {
                  UInt_t R__s, R__c;
                  Version_t R__v = R__b.ReadVersion(&R__s, &R__c);
                  R__b.ReadClassBuffer(Base::Class(), this, R__v, R__s, R__c);
                  for (Int_t i = 0; i < fNrows; i++)
                     R__b.ReadFastArray(fElements + i * fNcols + i, fNcols - i);
               } else {
                  R__b.WriteClassBuffer(Base::Class(), this);
               }
            }
            """)
        self.assertEqual(kind, "extending")

    def test_the_buffer_parameter_need_not_be_named_R__b(self):
        """`ROOT::RNTuple` calls it `buf` and reads a checksum with `>>`."""
        _, kind = only("""
            void X::Streamer(TBuffer &buf) {
               if (buf.IsReading()) {
                  buf.ReadClassBuffer(X::Class(), this);
                  std::uint64_t onDiskChecksum;
                  buf >> onDiskChecksum;
               } else {
                  buf.WriteClassBuffer(X::Class(), this);
               }
            }
            """)
        self.assertEqual(kind, "extending")

    def test_the_writing_branch_does_not_count(self):
        """The window ends at the enclosing `}`, so an `else` is out of reach."""
        _, kind = only("""
            void X::Streamer(TBuffer &R__b) {
               if (R__b.IsReading()) {
                  R__b.ReadClassBuffer(X::Class(), this);
               } else {
                  R__b.WriteClassBuffer(X::Class(), this);
                  R__b << fExtra;
               }
            }
            """)
        self.assertEqual(kind, "delegating")

    def test_a_legacy_case_after_a_break_does_not_count(self):
        """`RooBinning` dispatches with a `switch`, and its version-1 decode is
        a sibling `case` of the one holding `ReadClassBuffer` -- so the reads are
        in the same block. Counted, the class would be `extending`; it is
        `guarded`, and the `switch` is what makes it so."""
        _, kind = only("""
            void X::Streamer(TBuffer &R__b) {
               Version_t R__v = R__b.ReadVersion(&R__s, &R__c);
               switch (R__v) {
                 case 3:
                 case 2:
                   R__b.ReadClassBuffer(X::Class(), this, R__v, R__s, R__c);
                   break;
                 case 1:
                   R__b >> _xlo;
                   R__b >> _xhi;
                   break;
               }
            }
            """)
        self.assertEqual(kind, "guarded")

    def test_extending_outranks_guarded(self):
        """A class that both guards and extends must come out `extending`: the
        guard only matters below its threshold, the extra bytes at every version.
        No class in ROOT is currently both, which is why the precedence is
        pinned here rather than left to be discovered by a submodule bump."""
        _, kind = only("""
            void X::Streamer(TBuffer &R__b) {
               Version_t R__v = R__b.ReadVersion(&R__s, &R__c);
               if (R__v > 2) {
                  R__b.ReadClassBuffer(X::Class(), this, R__v, R__s, R__c);
                  R__b.ReadFastArray(fElements, fN);
               }
            }
            """)
        self.assertEqual(kind, "extending")

    def test_a_second_read_class_buffer_is_not_extra_bytes(self):
        """Those bytes are described by an info like the first lot."""
        _, kind = only("""
            void X::Streamer(TBuffer &R__b) {
               if (R__b.IsReading()) {
                  R__b.ReadClassBuffer(A::Class(), this);
                  R__b.ReadClassBuffer(B::Class(), this);
               }
            }
            """)
        self.assertEqual(kind, "delegating")


class Overloads(unittest.TestCase):
    """A class's `Streamer` overloads are one streamer and classify together."""

    SOURCE = """
        namespace ROOT { namespace v5 {
        void TFormula::Streamer(TBuffer &b) {
           Version_t v = b.ReadVersion(&R__s, &R__c);
           Streamer(b, v, R__s, R__c, nullptr);
        }
        void TFormula::Streamer(TBuffer &b, Int_t v, UInt_t R__s, UInt_t R__c,
                                const TClass *onfile_class) {
           if (v > 3) {
              b.ReadClassBuffer(TFormula::Class(), this, v, R__s, R__c, onfile_class);
              return;
           }
           TNamed::Streamer(b);
        }
        } }
        """

    def kinds(self):
        code = inventory.blank(self.SOURCE)
        matches = list(inventory.DEFINITION.finditer(code))
        scopes = inventory.enclosing(code, [m.start() for m in matches])
        return [(("::".join(scopes[m.start()] + [m.group(2)])),
                 inventory.classify(inventory.body(code, m.start()),
                                    {m.group(4) or "R__b"}))
                for m in matches]

    def test_separately_both_halves_are_wrong(self):
        """Neither half classifies correctly on its own, and they are wrong in
        opposite directions: the dispatching form has no `ReadClassBuffer` and
        reads `custom`, while the form that has one takes its version as a
        parameter rather than from `ReadVersion` and reads `delegating`. The
        class is neither -- it is streamer-info driven above version 3."""
        self.assertEqual([k for _, k in self.kinds()], ["custom", "delegating"])

    def test_together_they_are_guarded(self):
        joined = "\n".join(inventory.body(inventory.blank(self.SOURCE), m.start())
                           for m in inventory.DEFINITION.finditer(
                               inventory.blank(self.SOURCE)))
        self.assertEqual(inventory.classify(joined, {"b"}), "guarded")


class Naming(unittest.TestCase):

    def test_a_namespace_qualifies_the_class(self):
        name, _ = only("""
            namespace ROOT { namespace v5 {
            void TFormula::Streamer(TBuffer &b, const TClass *onfile) {
               b >> fN;
            }
            } }
            """)
        self.assertEqual(name, "ROOT::v5::TFormula")

    def test_a_brace_in_a_string_does_not_move_the_namespace(self):
        """The file defining `ROOT::v5::TFormula` parses formula syntax."""
        name, _ = only("""
            namespace ROOT { namespace v5 {
            const char *kBrace = "{";
            void TFormula::Streamer(TBuffer &b) { b >> fN; }
            } }
            """)
        self.assertEqual(name, "ROOT::v5::TFormula")

    def test_an_anonymous_namespace_is_dropped(self):
        code = inventory.blank("""
            namespace {
            void X::Streamer(TBuffer &b) { b >> fN; }
            }
            """)
        match = next(inventory.DEFINITION.finditer(code))
        self.assertIsNone(
            inventory.enclosing(code, [match.start()])[match.start()])


class QualifiedNames(unittest.TestCase):
    """An out-of-line definition may spell the scope itself.

    Matching only an unqualified name dropped `ROOT::RNTuple` and
    `RooWorkspace::CodeRepo` from the inventory entirely -- and the first is an
    `extending` class, so the omission was in the direction of "nothing to do".
    """

    def test_a_namespace_qualified_definition_keeps_its_scope(self):
        name, _ = only("""
            void ROOT::RNTuple::Streamer(TBuffer &buf) { buf >> fSeekHeader; }
            """)
        self.assertEqual(name, "ROOT::RNTuple")

    def test_a_nested_class_keeps_its_enclosing_class(self):
        name, _ = only("""
            void RooWorkspace::CodeRepo::Streamer(TBuffer &R__b) { R__b >> fN; }
            """)
        self.assertEqual(name, "RooWorkspace::CodeRepo")

    def test_a_qualifier_and_a_namespace_block_compose(self):
        name, _ = only("""
            namespace Outer {
            void Inner::Nested::Streamer(TBuffer &b) { b >> fN; }
            }
            """)
        self.assertEqual(name, "Outer::Inner::Nested")

    def test_template_arguments_are_dropped_from_the_qualifier(self):
        self.assertEqual(inventory.qualifier("TMatrixTSym<Element>::"),
                         ["TMatrixTSym"])


class Declarations(unittest.TestCase):

    def test_a_forward_declaration_has_no_body(self):
        """`TParameter<Long64_t>` and `TNDArrayT<double>` are declared like this
        so a `-fmodules` build compiles; the definitions are generated."""
        code = inventory.blank(
            "template <> void TParameter<Long64_t>::Streamer(TBuffer &R__b);\n"
            "struct Unrelated { int x; };\n")
        match = next(inventory.DEFINITION.finditer(code))
        self.assertIsNone(inventory.body(code, match.start()))

    def test_a_commented_out_definition_is_not_a_definition(self):
        """`// void Roo1DTable::Streamer(TBuffer &R__b)` in RooLinkedList.cxx."""
        code = inventory.blank(
            "// void Roo1DTable::Streamer(TBuffer &R__b)\n"
            "// { b >> fN; }\n")
        self.assertEqual(list(inventory.DEFINITION.finditer(code)), [])


class AgainstTheSubmodule(unittest.TestCase):
    """Facts the document states in prose, checked against the real source."""

    @classmethod
    def setUpClass(cls):
        if not (inventory.SUBMODULE / "README").exists():
            raise unittest.SkipTest("root/ submodule is not checked out")
        cls.found = inventory.streamers()
        cls.notes = inventory.notes()

    def test_every_custom_class_is_resolved(self):
        self.assertEqual(inventory.unresolved(self.found, self.notes), [])

    def test_the_document_is_current(self):
        self.assertEqual(inventory.rebuild(self.found, self.notes),
                         inventory.DOCUMENT.read_text())

    def test_tqobject_streams_nothing(self):
        """§5 of the document turns on this, and on nothing else."""
        self.assertEqual(self.found["TQObject"]["kind"], "custom")

    def test_the_two_formulas_are_separate_classes(self):
        """Both are `guarded`, and they are still two entries: a namespace is
        part of the name. The on-disk class name for both is `TFormula`, which
        is what `03-classes/Formula.md` is about."""
        self.assertEqual(self.found["TFormula"]["kind"], "guarded")
        self.assertEqual(self.found["ROOT::v5::TFormula"]["kind"], "guarded")
        self.assertIn("TFormula_v5", self.found["ROOT::v5::TFormula"]["cite"])

    def test_the_three_extending_classes(self):
        """The whole set, and it is small. `TMatrixTSym` is the one a physics
        file is likely to hold; `HandWrittenStreamers.md` §3 and
        `check_invariants.EXTENDING` must agree with this list."""
        extending = {n for n, e in self.found.items()
                     if e["kind"] == "extending"}
        self.assertEqual(extending,
                         {"TMatrixTSym", "TPointSet3D", "ROOT::RNTuple"})

    def test_the_checker_knows_the_same_extending_set(self):
        """Buffer.md invariant 9.9 is waived for exactly these classes, and the
        waiver is a list in a second tool -- so the two are compared here."""
        import check_invariants
        extending = {n for n, e in self.found.items()
                     if e["kind"] == "extending"}
        self.assertEqual(set(check_invariants.Checker.EXTENDING), extending)

    def test_the_bootstrap_classes_are_all_custom(self):
        """If any of these ever became streamer-info driven, `rootfile.py`'s
        hardcoded readers would be dead code and nothing else would say so."""
        for name in ("TObject", "TString", "TList", "TObjArray", "TKey",
                     "TFile", "TDirectoryFile", "TStreamerInfo",
                     "TStreamerElement", "TBasket"):
            with self.subTest(name):
                self.assertEqual(self.found[name]["kind"], "custom")


if __name__ == "__main__":
    unittest.main()
