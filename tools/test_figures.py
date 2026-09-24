#!/usr/bin/env python3
"""Tests for tools/check_figures.py's rendering; the figures themselves are CI's."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_figures  # noqa: E402


class Rendering(unittest.TestCase):
    def test_numbers_as_words(self):
        self.assertEqual(check_figures.word(13), "thirteen")
        self.assertEqual(check_figures.word(40), "forty")
        self.assertEqual(check_figures.word(48), "forty-eight")
        self.assertEqual(check_figures.word(252), "252")

    def test_a_template_renders_each_form(self):
        values = {"n": 48}
        self.assertEqual(
            check_figures.render("{n} / {n:word} / {n:Word}", values),
            "48 / forty-eight / Forty-eight")

    def test_the_pattern_reports_what_a_page_says(self):
        found = check_figures.pattern("plus {n:word} errata").search(
            "and plus twelve errata here")
        self.assertEqual(found.group(1), "twelve")

    def test_every_listed_page_exists(self):
        import tomllib
        spec = tomllib.loads(check_figures.FIGURES.read_text())
        for at in spec["at"]:
            with self.subTest(file=at["file"]):
                self.assertTrue((check_figures.REPO / at["file"]).is_file())


if __name__ == "__main__":
    unittest.main()
