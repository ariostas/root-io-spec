#!/usr/bin/env python3
"""Tests for the two checks that keep this project's own claims checkable.

`tools/check_coverage.py` is the published-invariant audit, and its whole value is
that it fails, so these drive the three ways it can: an entry with no check and no
reason, a reason for something that is checked after all, and a label a tool
reports that no document publishes.

`check_citations.check_cited_files` is the same idea for evidence rather than
rules: a `.root` the specification names must be fetchable, or the measurement
resting on it cannot be reproduced. That went unnoticed twice before it was a
check.
"""

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_citations  # noqa: E402
import check_coverage  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


class Parsing(unittest.TestCase):
    def setUp(self):
        self.entries = check_coverage.published()
        self.labels = {label for label, _, _ in self.entries}

    def test_it_finds_the_documents_with_invariants(self):
        # 32 documents, which WriterInvariants.md's own count is derived from.
        self.assertEqual(len({doc for _, doc, _ in self.entries}), 33)

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


class EveryCitedFileIsFetchable(unittest.TestCase):
    """check_citations.check_cited_files, added after PLAN.md 8.13's corpus gap."""

    SPEC = REPO / "spec"

    def paths(self):
        return [p for p in sorted(self.SPEC.rglob("*.md"))
                if p not in check_citations.NOT_OURS]

    def test_the_repository_passes(self):
        self.assertEqual(check_citations.check_cited_files(self.paths()), [])

    def test_the_fixtures_and_both_manifests_are_read(self):
        known = check_citations.fetchable()
        for name in ("file-minimal.root",            # data/
                     "uproot-issue283.root",         # gen/foreign, added by R6
                     "aleph.root",                   # gen/cern geometry tier
                     "pippa.root"):                  # gen/cern core tier
            self.assertIn(name, known, name)

    def test_a_cited_file_in_no_manifest_fails(self):
        """The case that went unnoticed twice: evidence nothing can fetch."""
        path = self.SPEC / "01-container" / "FileHeader.md"
        original = path.read_text()
        try:
            path.write_text(original + "\n> Measured on `not-a-corpus-file.root`.\n")
            bad = check_citations.check_cited_files([path])
            self.assertEqual(len(bad), 1)
            self.assertIn("not-a-corpus-file.root", bad[0])
            self.assertIn("nothing", bad[0])
        finally:
            path.write_text(original)

    def test_the_illustrative_names_are_named(self):
        """NOT_CORPUS is an allowlist, so each entry carries its reason."""
        self.assertIn("your-file.root", check_citations.NOT_CORPUS)
        for name, why in check_citations.NOT_CORPUS.items():
            self.assertTrue(why.strip(), name)


if __name__ == "__main__":
    unittest.main()
