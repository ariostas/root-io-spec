#!/usr/bin/env python3
"""Tests for tools/check_versions.py.

The tool itself runs against the pinned submodule and the real documents.
These tests cover the table parsing, whose irregular shapes make a silent
mis-parse the likely failure; one already happened, a citation's line number
read as a class version.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_versions  # noqa: E402


def claims(text, stem="TTree", tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / f"{stem}.md"
        path.write_text(text)
        return check_versions.claims(path)


class VersionFirstTable(unittest.TestCase):
    """`| Version | Difference |`, where the class is the document's name."""

    TEXT = """# x

## 13. Class versions

| Version | Difference |
|---|---|
| <= 5 | a legacy layout (`root/tree/tree/src/TBranch.cxx:3109`) |
| 6 | something |
| 20 | `fIOFeatures` added; current |

Trailing prose.
"""

    def test_the_class_comes_from_the_filename(self):
        self.assertEqual({c[0] for c in claims(self.TEXT)}, {"TTree"})

    def test_every_version_is_collected(self):
        versions = sorted(v for c in claims(self.TEXT) for v in c[1])
        self.assertEqual(versions, [5, 6, 20])

    def test_a_citation_line_number_is_not_a_version(self):
        # The first row cites :3109; it must not be read as version 3109.
        self.assertNotIn(3109, [v for c in claims(self.TEXT) for v in c[1]])

    def test_only_the_current_row_is_marked(self):
        marked = [c[1] for c in claims(self.TEXT) if c[2]]
        self.assertEqual(marked, [[20]])


class ClassPerRowTable(unittest.TestCase):
    """`| Class | Version | Note |`, where each row names its own class."""

    TEXT = """# x

## 12. Class versions

| Class | Version | Note |
|---|---|---|
| `TLeaf` | 2 | current |
| `TLeafF16`, `TLeafD32` | 1 | older |
| `TLeafObject` | 1, 2, 3, 4 | several |
"""

    def test_several_classes_in_one_cell(self):
        names = {c[0] for c in claims(self.TEXT, stem="TLeaf")}
        self.assertEqual(names, {"TLeaf", "TLeafF16", "TLeafD32", "TLeafObject"})

    def test_a_list_of_versions_in_one_cell(self):
        got = [c[1] for c in claims(self.TEXT, stem="TLeaf") if c[0] == "TLeafObject"]
        self.assertEqual(got, [[1, 2, 3, 4]])

    def test_current_attaches_to_its_own_row(self):
        marked = {c[0] for c in claims(self.TEXT, stem="TLeaf") if c[2]}
        self.assertEqual(marked, {"TLeaf"})


class SeveralTablesInOneSection(unittest.TestCase):
    """TBranchElement.md 12 tabulates its own versions and then other classes."""

    TEXT = """# x

## 12. Class versions

| Class version | Elements |
|---|---|
| 8, 9 | 12 |
| 10 | 12 |

Prose between the tables.

| Class | Class version | Count |
|---|---|---|
| `TBranchObject` | 1 (`root/tree/tree/inc/TBranchObject.h:71`) | 2 |
"""

    def test_both_tables_are_read(self):
        got = {c[0]: max(c[1]) for c in claims(self.TEXT, stem="TBranchElement")}
        self.assertEqual(got, {"TBranchElement": 10, "TBranchObject": 1})


class SectionBoundaries(unittest.TestCase):
    def test_a_table_in_another_section_is_ignored(self):
        text = """# x

## 12. Class versions

| Version | Difference |
|---|---|
| 3 | current |

## 13. Reference files

| Version | Difference |
|---|---|
| 99 | not a class version |
"""
        self.assertEqual(sorted(v for c in claims(text) for v in c[1]), [3])

    def test_a_document_with_no_such_section_claims_nothing(self):
        self.assertEqual(claims("# x\n\n## 1. Layout\n\ntext\n"), [])


#: A test that reads the pinned ROOT source skips without it. CI's tests job
#: checks the submodule out and fails on a skip that names it.
HAVE_SUBMODULE = (check_versions.SUBMODULE / "io" / "io" / "src").is_dir()


@unittest.skipUnless(HAVE_SUBMODULE, "the pinned submodule is not checked out")
class SubmoduleExtraction(unittest.TestCase):
    """The ClassDef side, against the real submodule."""

    @classmethod
    def setUpClass(cls):
        cls.known = check_versions.class_versions()

    def test_the_spellings_are_all_handled(self):
        # ClassDef, ClassDefOverride and ClassDefNV all appear in ROOT.
        for name, want in (("TTree", 20), ("TBranch", 13), ("TBasket", 3),
                           ("TKey", 4), ("TDirectoryFile", 5)):
            with self.subTest(name):
                self.assertEqual(self.known.get(name), {want})

    def test_an_ambiguous_name_keeps_every_version(self):
        # ROOT's tests and tutorials define classes called Event and Track, so a
        # lookup by bare name is unsafe and the tool must refuse rather than
        # pick. This asserts only that the ambiguity is visible.
        self.assertGreater(len(self.known.get("Event", set())), 1)


@unittest.skipUnless(HAVE_SUBMODULE, "the pinned submodule is not checked out")
class CitedLines(unittest.TestCase):
    """PLAN-review.md V35: a row's header citation must be its ClassDef line.
    WritingGraphs.md cited a blank line of TList.h and TH1.h's Smooth()."""

    TEXT = """# x

## 7. Class versions

| Class | Version | Cite |
|---|---|---|
| `TGraph` | 5 | `root/hist/hist/inc/TGraph.h:{line}` |
"""

    def bad(self, line):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = check_versions.REPO / "spec" / Path(d).name / "WritingX.md"
            path.parent.mkdir()
            try:
                path.write_text(self.TEXT.format(line=line))
                return check_versions.bad_citations(path)
            finally:
                path.unlink()
                path.parent.rmdir()

    def test_the_classdef_line_passes(self):
        self.assertEqual(self.bad(202), [])

    def test_a_range_containing_it_passes(self):
        self.assertEqual(self.bad("200-203"), [])

    def test_another_line_fails(self):
        (message,) = self.bad(172)
        self.assertIn("holds no ClassDef for it", message)

    def test_tkey_is_read_from_record_md(self):
        narrowed = []
        (path, name, versions, _), = check_versions.elsewhere(narrowed)
        self.assertEqual((path.name, name), ("Record.md", "TKey"))
        # 1002 to 1004 are the large layout, not class versions.
        self.assertEqual(max(versions), 4)
        self.assertEqual(narrowed, [])


if __name__ == "__main__":
    unittest.main()
