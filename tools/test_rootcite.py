"""Tests for the citation extension. Run: python3 -m unittest discover tools"""

import unittest

import markdown

from rootcite import citation_url

COMMIT = "1211eda93010f26710eafd527d1e66921bffdf8e"
BASE = "https://github.com/root-project/root"


def render(text):
    return markdown.markdown(
        text, extensions=["tables", f"rootcite"],
        extension_configs={"rootcite": {"commit": COMMIT}},
    )


class CitationURL(unittest.TestCase):
    def url(self, text):
        return citation_url(text, BASE, COMMIT)

    def test_path_and_line(self):
        self.assertEqual(
            self.url("root/io/io/src/TFile.cxx:2679"),
            f"{BASE}/blob/{COMMIT}/io/io/src/TFile.cxx#L2679")

    def test_line_range(self):
        self.assertEqual(
            self.url("root/io/io/src/TFile.cxx:2668-2712"),
            f"{BASE}/blob/{COMMIT}/io/io/src/TFile.cxx#L2668-L2712")

    def test_path_only(self):
        self.assertEqual(
            self.url("root/io/doc/TFile/header.md"),
            f"{BASE}/blob/{COMMIT}/io/doc/TFile/header.md")

    def test_header_file(self):
        self.assertEqual(
            self.url("root/io/io/inc/TFile.h:278"),
            f"{BASE}/blob/{COMMIT}/io/io/inc/TFile.h#L278")

    def test_non_citations(self):
        for text in ["TFile.cxx:2679", "root/io/io/src", "fNbytesName",
                     "kStartBigFile", "root", "spec/01-container/FileHeader.md"]:
            self.assertIsNone(self.url(text), text)


class Rendering(unittest.TestCase):
    def test_wraps_code_span(self):
        html = render("See `root/io/io/src/TFile.cxx:2679` for details.")
        self.assertIn('class="root-citation"', html)
        self.assertIn(f"#L2679", html)
        self.assertIn("<code>root/io/io/src/TFile.cxx:2679</code>", html)

    def test_leaves_other_code_alone(self):
        html = render("The field `fNbytesName` counts bytes.")
        self.assertNotIn("root-citation", html)

    def test_works_inside_tables(self):
        html = render(
            "| Field | Where |\n|---|---|\n"
            "| `fUnits` | `root/io/io/inc/TFile.h:170` |\n")
        self.assertIn("root-citation", html)
        self.assertIn("<code>fUnits</code>", html)

    def test_idempotent_single_wrap(self):
        """Regression: the walker must not re-wrap what it just wrapped."""
        html = render("`root/io/io/src/TFile.cxx:1`")
        self.assertEqual(html.count("root-citation"), 1)
        self.assertEqual(html.count("<code>"), 1)


if __name__ == "__main__":
    unittest.main()
