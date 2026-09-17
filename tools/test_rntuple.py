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


def _have_gitlink() -> bool:
    """Whether `git rev-parse HEAD:root` can run here.

    It can in a checkout, with or without the submodule fetched, which is the
    case that matters. It cannot in a bare copy of the tree -- the scratch
    directory the container regeneration mounts, say -- and a test that cannot
    run should skip rather than error.
    """
    try:
        sync_rntuple.pinned_commit()
    except Exception:
        return False
    return True


HAVE_GITLINK = _have_gitlink()


class TrackedCopy(unittest.TestCase):
    """Properties of the copy that hold with or without the submodule."""

    def test_the_copy_is_tracked(self):
        self.assertTrue(TRACKED.is_file())

    def test_provenance_records_a_full_commit(self):
        recorded = sync_rntuple.recorded_commit()
        self.assertIsNotNone(recorded)
        self.assertEqual(len(recorded), 40)

    @unittest.skipUnless(HAVE_GITLINK, "not a git checkout")
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


class ByteOrderFormats(unittest.TestCase):
    """check_bytes.py gained little-endian formats for RNTuple's envelopes.

    A ROOT file with an RNTuple in it has both byte orders, and the boundary is
    the anchor's last byte -- so a case has to say which at every offset, and
    getting it wrong has to fail rather than read a plausible number. These are
    the two the first RNTuple fixture actually turned up.
    """

    def setUp(self):
        sys.path.insert(0, str(REPO / "tools"))
        import check_bytes
        self.check_bytes = check_bytes

    def test_both_orders_are_available(self):
        f = self.check_bytes.FORMATS
        for name in ("u16", "u32", "i64", "f64"):
            self.assertTrue(f[name].startswith(">"), name)
            self.assertTrue(f[name + "le"].startswith("<"), name + "le")

    def test_a_little_endian_envelope_preamble(self):
        # type 1 in the low 16 bits, length 240 in the upper 48 -- the header
        # envelope of rntuple/anchor.
        buf = bytes([0x01, 0x00, 0xf0, 0x00, 0x00, 0x00, 0x00, 0x00])
        ok = [{"offset": 0, "type": "u64le", "value": (240 << 16) | 1, "name": "le"}]
        self.assertEqual(self.check_bytes.check(buf, ok, "x"), [])
        # The same bytes read big-endian are a different, plausible-looking
        # number, which is why the suffix has to be explicit.
        bad = [{"offset": 0, "type": "u64", "value": (240 << 16) | 1, "name": "be"}]
        self.assertEqual(len(self.check_bytes.check(buf, bad, "x")), 1)

    def test_a_negative_list_frame_size(self):
        # -12, the empty list frame that appears four times in that fixture.
        buf = (-12).to_bytes(8, "little", signed=True)
        good = [{"offset": 0, "type": "i64le", "value": -12, "name": "le"}]
        self.assertEqual(self.check_bytes.check(buf, good, "x"), [])


def _fundamental_table(text: str) -> dict[str, str]:
    """The `W*` cell of the tracked copy's Fundamental Types table.

    Returns {C++ type: default column name}, with the `(Split)` prefix kept so
    the caller can decide which half of the split rule it is testing.
    """
    import re
    lines = text.splitlines()
    start = lines.index("### Fundamental Types")
    head = next(i for i in range(start, len(lines))
                if lines[i].startswith("| Column Type / Fundamental C++ Type"))
    # `std::byte` is the one header the document namespaces; strip on both
    # sides rather than special-case it.
    types = [c.strip().strip("`").replace("std::", "")
             for c in lines[head].split("|")[2:-1]]
    defaults: dict[str, str] = {}
    for line in lines[head + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.split("|")[1:-1]]
        column, marks = cells[0], cells[1:]
        for cpp, mark in zip(types, marks):
            if mark == "W*":
                defaults[cpp] = column
    return defaults


class FundamentalTypeTable(unittest.TestCase):
    """The tracked table against a file, so the two cannot drift apart.

    The same idea as check_versions.py for class versions: a claim that is a
    table of names is exactly the kind that rots without anything failing, and
    here both sides move -- the document on a submodule bump, the file when ROOT
    changes a default.
    """

    FIXTURE = REPO / "data/rntuple/fundamental-types.root"

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO / "tools"))
        import rootfile
        cls.rootfile = rootfile
        cls.defaults = _fundamental_table(TRACKED.read_text())

    def decoded(self):
        rootfile = self.rootfile
        buf, _, recs = rootfile.load(self.FIXTURE)
        rec = next(r for r in recs if r.class_name == "ROOT::RNTuple")
        _, schema = rootfile.read_rntuple(buf, rec)
        by_field = {c.field_id: c for c in schema.columns}
        # The fixture's field names are the C++ types with std:: stripped, which
        # is how the document's table heads its columns.
        return {f.type_name.replace("std::", ""): by_field[f.field_id]
                for f in schema.fields}

    def test_the_table_marks_one_default_per_type(self):
        self.assertEqual(len(self.defaults), 13, self.defaults)

    def test_the_fixture_covers_every_type_in_the_table(self):
        self.assertEqual(set(self.decoded()), set(self.defaults))

    def test_every_default_matches_and_the_ntuple_is_uncompressed(self):
        # "If the ntuple is stored uncompressed, the default changes from split
        # encoding to non-split encoding where applicable" -- so the expected
        # column is the table's cell with any `(Split)` prefix removed.
        for cpp, column in self.decoded().items():
            want = self.defaults[cpp].replace("(Split)", "")
            with self.subTest(cpp=cpp):
                self.assertEqual(column.type_name, want)

    def test_each_is_a_plain_field_with_exactly_one_column(self):
        rootfile = self.rootfile
        buf, _, recs = rootfile.load(self.FIXTURE)
        rec = next(r for r in recs if r.class_name == "ROOT::RNTuple")
        _, schema = rootfile.read_rntuple(buf, rec)
        self.assertEqual(len(schema.columns), len(schema.fields))
        for f in schema.fields:
            with self.subTest(field=f.name):
                self.assertEqual(f.role, "plain")

    def test_split_columns_are_absent_from_an_uncompressed_ntuple(self):
        names = {c.type_name for c in self.decoded().values()}
        self.assertFalse([n for n in names if n.startswith("Split")], names)
