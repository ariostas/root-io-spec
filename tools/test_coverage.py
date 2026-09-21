#!/usr/bin/env python3
"""Tests for tools/check_coverage.py, the published-invariant audit.

The tool's whole value is that it fails, so these drive the three ways it can:
an entry with no check and no reason, a reason for something that is checked
after all, and a label a tool reports that no document publishes.
"""

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_coverage  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


class Parsing(unittest.TestCase):
    def setUp(self):
        self.entries = check_coverage.published()
        self.labels = {label for label, _, _ in self.entries}

    def test_it_finds_the_documents_with_invariants(self):
        # 32 documents, which WriterInvariants.md's own count is derived from.
        self.assertEqual(len({doc for _, doc, _ in self.entries}), 32)

    def test_a_dotted_heading_is_read(self):
        """WritingFiles' heading is "14. Invariants a writer should check ...". """
        self.assertIn("WritingFiles 14.1", self.labels)
        self.assertIn("WritingFiles 14.17", self.labels)

    def test_the_rntuple_copy_is_not_ours(self):
        self.assertFalse([label for label in self.labels
                          if label.startswith("BinaryFormatSpecification")])

    def test_entries_carry_their_text(self):
        first = {label: line for label, _, line in self.entries}
        self.assertEqual(first["FileHeader 10.1"], "Bytes 0-3 are `root`.")

    def test_the_checked_set_is_read_from_the_tools(self):
        labels = check_coverage.checked_labels()
        self.assertIn("check_invariants.py", labels["StreamerDriven 10.5"])
        self.assertIn("Directory 9.15", labels)

    def test_every_accounted_entry_still_exists(self):
        """A reason for a label no document publishes is itself a failure."""
        for label in check_coverage.accounted():
            self.assertIn(label, self.labels, label)


class TheToolFails(unittest.TestCase):
    """Run it as CI does, against a doctored copy of the repo's inputs."""

    def run_tool(self, spec=None, sidecar=None):
        original = {}
        try:
            for path, text in (spec or {}).items():
                original[path] = path.read_text()
                path.write_text(text)
            if sidecar is not None:
                original[check_coverage.SIDECAR] = check_coverage.SIDECAR.read_text()
                check_coverage.SIDECAR.write_text(sidecar)
            return subprocess.run([sys.executable, "tools/check_coverage.py", "--check"],
                                  cwd=REPO, capture_output=True, text=True)
        finally:
            for path, text in original.items():
                path.write_text(text)

    def test_the_repository_passes(self):
        self.assertEqual(self.run_tool().returncode, 0)

    def test_a_new_unchecked_entry_fails(self):
        """Adding an entry nothing checks is the case R2 was."""
        path = REPO / "spec/01-container/Compression.md"
        text = path.read_text()
        marker = "\n## 10. Errata"
        self.assertIn(marker, text)
        doctored = text.replace(
            marker, "\n8. Something nobody checks and nobody excused." + marker, 1)
        out = self.run_tool(spec={path: doctored})
        self.assertEqual(out.returncode, 1)
        self.assertIn("Compression 9.8", out.stderr)
        self.assertIn("unaccounted", out.stderr)

    def test_a_stale_reason_fails(self):
        """A reason for an entry that is checked after all."""
        sidecar = check_coverage.SIDECAR.read_text() + (
            '\n[invariant."FileHeader 10.1"]\nby = "alias"\nreason = "not true"\n')
        out = self.run_tool(sidecar=sidecar)
        self.assertEqual(out.returncode, 1)
        self.assertIn("FileHeader 10.1", out.stderr)
        self.assertIn("no longer applies", out.stderr)

    def test_a_label_no_document_publishes_fails(self):
        """The other direction: a check for an invariant that was deleted."""
        path = REPO / "spec/01-container/FileHeader.md"
        text = path.read_text()
        doctored = text.replace("\n11. `fBEGIN` is at least the length", "\n11x. moved", 1)
        out = self.run_tool(spec={path: doctored})
        self.assertEqual(out.returncode, 1)
        self.assertIn("FileHeader 10.11", out.stderr)


if __name__ == "__main__":
    unittest.main()
