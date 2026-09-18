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


def _child_name_claims(text: str) -> dict[str, str]:
    """Which subsections of *Stdlib Types and Collections* promise a `_0` child.

    Parsed rather than transcribed, for the same reason as the table above: the
    document moves on a submodule bump and a transcribed claim would not.
    """
    import re
    lines = text.splitlines()
    start = lines.index("### Stdlib Types and Collections")
    end = lines.index("### User-defined classes")
    section, claims = None, {}
    for line in lines[start:end]:
        if line.startswith("#### ") or line.startswith("### "):
            section = line.lstrip("# ").strip()
        elif section and "`_0`" in line:
            # Any mention is the claim: the wording varies -- "named `_0`", "the
            # name of the child field is `_0`", "their names are `_0`, `_1`, ...".
            claims[section] = line.strip()
    return claims


class StdlibTypeMapping(unittest.TestCase):
    """*Stdlib Types and Collections* against a file, type by type.

    The claims there are prose, not a table: how many fields a type becomes, what
    the parent's columns are, what the children are called. `rntuple/collections`
    is one field per type and this reads the decoded schema against them.
    """

    FIXTURE = REPO / "data/rntuple/collections.root"

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO / "tools"))
        import rootfile
        buf, _, recs = rootfile.load(cls.FIXTURE)
        rec = next(r for r in recs if r.class_name == "ROOT::RNTuple")
        _, schema = rootfile.read_rntuple(buf, rec)
        cls.schema = schema
        cls.by_id = {f.field_id: f for f in schema.fields}
        cls.top = {f.name: f for f in schema.fields
                   if f.parent_id == f.field_id}
        cls.columns = {}
        for c in schema.columns:
            cls.columns.setdefault(c.field_id, []).append(c)

    def children(self, field):
        return [f for f in self.schema.fields
                if f.parent_id == field.field_id and f is not field]

    def cols(self, field):
        return [c.type_name for c in self.columns.get(field.field_id, [])]

    def shape(self, name):
        """(role, columns, [(child name, child type, child columns)])."""
        field = self.top[name]
        return (field.role, self.cols(field),
                [(c.name, c.type_name, self.cols(c)) for c in self.children(field)])

    # -- one test per subsection of the document -------------------------

    def test_string_is_one_field_with_an_index_and_a_char_column(self):
        self.assertEqual(self.shape("fString"), ("plain", ["Index64", "Char"], []))

    def test_vector_is_a_collection_parent_and_a_child(self):
        self.assertEqual(self.shape("fVector"),
                         ("collection", ["Index64"], [("_0", "float", ["Real32"])]))

    def test_rvec_has_the_same_shape_and_a_fully_qualified_name(self):
        self.assertEqual(self.shape("fRVec"), self.shape("fVector"))
        self.assertEqual(self.top["fRVec"].type_name, "ROOT::VecOps::RVec<float>")

    def test_array_is_a_plain_field_with_a_repetition_and_no_columns(self):
        field = self.top["fArray"]
        self.assertEqual(self.shape("fArray"),
                         ("plain", [], [("_0", "std::int32_t", ["Int32"])]))
        self.assertEqual(field.array_size, 3)

    def test_variant_has_a_switch_column_and_one_child_per_alternative(self):
        self.assertEqual(
            self.shape("fVariant"),
            ("variant", ["Switch"],
             [("_0", "std::int32_t", ["Int32"]), ("_1", "float", ["Real32"])]))

    def test_pair_and_tuple_are_empty_record_parents(self):
        self.assertEqual(self.shape("fPair"),
                         ("record", [],
                          [("_0", "std::int32_t", ["Int32"]),
                           ("_1", "float", ["Real32"])]))
        role, cols, kids = self.shape("fTuple")
        self.assertEqual((role, cols), ("record", []))
        self.assertEqual([k[0] for k in kids], ["_0", "_1", "_2"])

    def test_bitset_is_a_plain_field_with_a_bit_column_and_a_repetition(self):
        self.assertEqual(self.shape("fBitset"), ("plain", ["Bit"], []))
        self.assertEqual(self.top["fBitset"].array_size, 8)

    def test_unique_ptr_and_optional_are_collections_of_zero_or_one(self):
        want = ("collection", ["Index64"], [("_0", "float", ["Real32"])])
        self.assertEqual(self.shape("fUnique"), want)
        self.assertEqual(self.shape("fOptional"), want)

    def test_set_has_the_same_shape_as_a_vector(self):
        self.assertEqual(
            self.shape("fSet"),
            ("collection", ["Index64"], [("_0", "std::int32_t", ["Int32"])]))

    def test_atomic_is_a_plain_parent_with_no_columns(self):
        self.assertEqual(self.shape("fAtomic"),
                         ("plain", [], [("_0", "std::int32_t", ["Int32"])]))

    def test_a_nested_collection_is_collections_all_the_way_down(self):
        outer = self.top["fNested"]
        self.assertEqual((outer.role, self.cols(outer)), ("collection", ["Index64"]))
        inner, = self.children(outer)
        self.assertEqual((inner.name, inner.role, self.cols(inner)),
                         ("_0", "collection", ["Index64"]))
        leaf, = self.children(inner)
        self.assertEqual((leaf.name, leaf.type_name, self.cols(leaf)),
                         ("_0", "std::int32_t", ["Int32"]))

    # -- the claims, parsed out of the tracked copy ----------------------

    def test_every_subsection_that_promises_a_zero_child_gets_one(self):
        claims = _child_name_claims(TRACKED.read_text())
        # The subsections the fixture covers, by the field that stands for each.
        covered = {
            "std::vector\\<T\\> and ROOT::RVec\\<T\\>": "fVector",
            "std::array<T, N> and array type of the form T[N]": "fArray",
            "std::variant<T1, T2, ..., Tn>": "fVariant",
            "std::pair<T1, T2>": "fPair",
            "std::tuple<T1, T2, ..., Tn>": "fTuple",
            "std::unique_ptr\\<T\\>, std::optional\\<T\\>": "fUnique",
            "std::set\\<T\\>, std::unordered_set\\<T\\>, std::multiset\\<T\\>, "
            "std::unordered_multiset\\<T\\>": "fSet",
            "std::atomic\\<T\\>": "fAtomic",
        }
        missing = [s for s in covered if s not in claims]
        self.assertEqual(missing, [], f"the document no longer promises `_0` in: "
                                     f"{missing}; parsed {sorted(claims)}")
        for section, field in covered.items():
            with self.subTest(section=section):
                self.assertEqual(self.children(self.top[field])[0].name, "_0")

    def test_double32_keeps_a_split_column_in_an_uncompressed_ntuple(self):
        # ERRATA 7. Every other column in this fixture is unsplit, because the
        # ntuple is uncompressed; Double32_t's override runs afterwards and wins.
        field = self.top["fDouble32"]
        self.assertEqual((field.type_name, field.type_alias), ("double", "Double32_t"))
        self.assertEqual(self.cols(field), ["SplitReal32"])
        others = {c.type_name for f in self.top.values() if f.name != "fDouble32"
                  for c in self.columns.get(f.field_id, [])}
        self.assertFalse([n for n in others if n.startswith("Split")], others)

    def test_normalization_reaches_inside_template_arguments(self):
        # "Type Name Normalization": int is spelled std::int32_t, and not only at
        # the top level.
        self.assertEqual(self.top["fArray"].type_name, "std::array<std::int32_t,3>")
        self.assertEqual(self.top["fSet"].type_name, "std::set<std::int32_t>")
        self.assertEqual(self.top["fVariant"].type_name,
                         "std::variant<std::int32_t,float>")


class UserClassMapping(unittest.TestCase):
    """*User-defined classes* and *User-defined enums* against a file.

    `rntuple/user-class` is a struct with a base class, two enums, a vector of
    itself and a transient member, so the record shape is checked twice in one
    file -- at top level and inside a collection.
    """

    FIXTURE = REPO / "data/rntuple/user-class.root"

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO / "tools"))
        import rootfile
        buf, _, recs = rootfile.load(cls.FIXTURE)
        rec = next(r for r in recs if r.class_name == "ROOT::RNTuple")
        _, schema = cls.schema_of(rootfile, buf, rec)
        cls.schema = schema
        cls.by_id = {f.field_id: f for f in schema.fields}
        cls.columns = {}
        for c in schema.columns:
            cls.columns.setdefault(c.field_id, []).append(c)
        cls.by_path = {cls.path(f): f for f in schema.fields}

    @staticmethod
    def schema_of(rootfile, buf, rec):
        return rootfile.read_rntuple(buf, rec)

    @classmethod
    def path(cls, field):
        parts, f = [field.name], field
        while f.parent_id != f.field_id:
            f = cls.by_id[f.parent_id]
            parts.append(f.name)
        return ".".join(reversed(parts))

    def cols(self, path):
        return [c.type_name for c in self.columns.get(self.by_path[path].field_id, [])]

    def children(self, path):
        parent = self.by_path[path]
        return [f for f in self.schema.fields
                if f.parent_id == parent.field_id and f is not parent]

    def test_a_class_is_a_record_parent_with_no_columns(self):
        self.assertEqual(self.by_path["fHit"].role, "record")
        self.assertEqual(self.cols("fHit"), [])

    def test_members_keep_their_cxx_names(self):
        self.assertEqual([f.name for f in self.children("fHit")],
                         [":_0", "fEnergy", "fFlavour", "fCharge", "fSamples",
                          "fLabel"])

    def test_a_base_class_is_a_colon_numbered_subfield(self):
        base = self.by_path["fHit.:_0"]
        self.assertEqual((base.name, base.type_name, base.role),
                         (":_0", "RNBase", "record"))
        self.assertEqual([f.name for f in self.children("fHit.:_0")], ["fBaseId"])

    def test_a_transient_member_has_no_field(self):
        # fScratch is marked //! in classes.h. Its absence is the claim; that
        # nothing else shifted is what the byte assertions check.
        self.assertNotIn("fHit.fScratch", self.by_path)
        self.assertFalse([f for f in self.schema.fields if "Scratch" in f.name])

    def test_an_enum_is_a_plain_parent_over_its_underlying_integer(self):
        for path, underlying in (("fFlavour", "std::uint32_t"),
                                 ("fCharge", "std::int16_t"),
                                 ("fHit.fFlavour", "std::uint32_t"),
                                 ("fHit.fCharge", "std::int16_t")):
            with self.subTest(path=path):
                self.assertEqual(self.by_path[path].role, "plain")
                self.assertEqual(self.cols(path), [])
                child, = self.children(path)
                self.assertEqual((child.name, child.type_name), ("_0", underlying))

    def test_a_vector_of_the_class_repeats_the_whole_record(self):
        self.assertEqual(self.by_path["fHits"].role, "collection")
        self.assertEqual(self.cols("fHits"), ["Index64"])
        inner = self.by_path["fHits._0"]
        self.assertEqual((inner.name, inner.type_name, inner.role),
                         ("_0", "RNHit", "record"))
        self.assertEqual([f.name for f in self.children("fHits._0")],
                         [f.name for f in self.children("fHit")])
        self.assertEqual(inner.type_checksum, self.by_path["fHit"].type_checksum)

    def test_a_class_field_carries_a_checksum(self):
        for path in ("fHit", "fHit.:_0", "fHits._0"):
            with self.subTest(path=path):
                self.assertIsNotNone(self.by_path[path].type_checksum)
        # And a field whose type is not a class does not.
        self.assertIsNone(self.by_path["fHit.fEnergy"].type_checksum)

    def test_a_class_without_a_classdef_has_type_version_uint32_max(self):
        # ERRATA 8: TClass::GetClassVersion() is -1 for a class with no ClassDef
        # and the field record's Type Version is unsigned
        # (root/tree/ntuple/src/RFieldMeta.cxx:645).
        self.assertEqual(self.by_path["fHit"].type_version, 0xFFFFFFFF)
        self.assertEqual(self.by_path["fHit.:_0"].type_version, 0xFFFFFFFF)
        # Everything that is not a user class stays at 0.
        self.assertEqual(self.by_path["fHit.fEnergy"].type_version, 0)

    def test_the_document_still_only_calls_the_versions_schema_evolution(self):
        # If upstream ever documents the sentinel, this fails and ERRATA 8 can be
        # closed. Parsed rather than transcribed, like the other claim tests.
        text = TRACKED.read_text()
        self.assertIn("The field version and type version are used for schema "
                      "evolution.", text)
        for hint in ("0xFFFFFFFF", "UINT32_MAX", "unversioned"):
            self.assertNotIn(hint, text)
