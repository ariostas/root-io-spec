#!/usr/bin/env python3
"""Tests for tools/sync_rntuple.py, and for the properties of the tracked copy.

The tool's real check is `--check` against the pinned submodule, which CI runs.
These cover the two things that check cannot cover itself: that drift is actually
detected rather than reported as success, and that the promises
spec/05-rntuple/UPSTREAM.md makes about the copy hold.

The submodule-dependent tests are skipped when root/ is not checked out, because
the docs workflow runs the test suite without submodules.
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync_rntuple  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
HAVE_SUBMODULE = (REPO / "root/tree/ntuple/doc/BinaryFormatSpecification.md").is_file()
TRACKED = REPO / "spec/05-rntuple/BinaryFormatSpecification.md"


class TrackedCopy(unittest.TestCase):
    """Properties of the copy that hold with or without the submodule."""

    def test_the_copy_is_tracked(self):
        self.assertTrue(TRACKED.is_file())

    def test_provenance_records_a_full_commit(self):
        recorded = sync_rntuple.recorded_commit()
        self.assertIsNotNone(recorded)
        self.assertEqual(len(recorded), 40)

    def test_provenance_matches_the_pin(self):
        # Not guarded on the submodule: the gitlink is in the index, so this
        # works in a checkout that never fetched root/.
        self.assertEqual(sync_rntuple.recorded_commit(),
                         sync_rntuple.pinned_commit())

    def test_only_the_format_specification_is_tracked(self):
        # UPSTREAM.md's table says why the other five are not. If a document is
        # added to DOCUMENTS, that table needs a row.
        self.assertEqual(set(sync_rntuple.DOCUMENTS),
                         {"BinaryFormatSpecification.md"})


def quietly(*argv: str) -> int:
    """Run the tool without its progress line reaching the test output."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        return sync_rntuple.main(list(argv))


@unittest.skipUnless(HAVE_SUBMODULE, "root/ submodule is not checked out")
class SyncAgainstSubmodule(unittest.TestCase):

    def test_the_copy_is_byte_identical(self):
        upstream = REPO / "root/tree/ntuple/doc/BinaryFormatSpecification.md"
        self.assertEqual(TRACKED.read_bytes(), upstream.read_bytes())

    def test_check_passes_as_committed(self):
        self.assertEqual(quietly("--check"), 0)

    def test_a_single_appended_byte_is_detected(self):
        # The failure mode the tool exists for: an edit in place. One newline is
        # enough, and it must not be reported as success.
        original = TRACKED.read_bytes()
        backup = tempfile.NamedTemporaryFile(delete=False)
        backup.write(original)
        backup.close()
        try:
            TRACKED.write_bytes(original + b"\n")
            self.assertEqual(quietly("--check"), 1)
        finally:
            shutil.copyfile(backup.name, TRACKED)
            Path(backup.name).unlink()
        self.assertEqual(TRACKED.read_bytes(), original)
        self.assertEqual(quietly("--check"), 0)


class ErrataAreCitedAndTracked(unittest.TestCase):
    """spec/05-rntuple/ERRATA.md's own promises about its shape."""

    TEXT = (REPO / "spec/05-rntuple/ERRATA.md").read_text()

    def test_every_numbered_erratum_has_a_status_row(self):
        import re
        headings = re.findall(r"^## (\d+)\. ", self.TEXT, re.M)
        rows = re.findall(r"^\| (\d+) \| .* \| (open|fixed|withdrawn) \|",
                          self.TEXT, re.M)
        self.assertEqual(headings, [n for n, _ in rows])
        self.assertTrue(headings, "ERRATA.md has no entries")

    def test_every_erratum_cites_the_submodule(self):
        # An erratum without a citation is an opinion. Each section between two
        # `## ` headings must carry at least one root/...:NN citation.
        import re
        sections = re.split(r"^## \d+\. ", self.TEXT, flags=re.M)[1:]
        for i, body in enumerate(sections, 1):
            with self.subTest(erratum=i):
                self.assertRegex(body, r"`root/[A-Za-z0-9_./+-]+\.(?:cxx|hxx|h):\d+")
