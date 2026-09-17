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
    return "::".join(scope + [match.group(1)]), inventory.classify(body)


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
        self.assertEqual(self.found["TFormula"]["kind"], "guarded")
        self.assertEqual(self.found["ROOT::v5::TFormula"]["kind"], "custom")

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
