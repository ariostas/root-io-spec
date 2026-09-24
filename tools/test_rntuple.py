#!/usr/bin/env python3
"""Tests for tools/sync_rntuple.py, and for the properties of the tracked copy.

The tool's main check is `--check` against the pinned submodule, which CI runs.
These tests cover what that check cannot test about itself: that drift is
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

    It can in a checkout, with or without the submodule fetched. It cannot in a
    bare copy of the tree, such as the scratch directory the container
    regeneration mounts, and there the test should skip rather than error.
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
        # The failure mode the tool exists for: an edit in place. A single
        # appended newline must be detected.
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
        # Each section between two `## ` headings must have at least one
        # root/...:NN citation.
        import re
        sections = re.split(r"^## \d+\. ", self.TEXT, flags=re.M)[1:]
        for i, body in enumerate(sections, 1):
            with self.subTest(erratum=i):
                self.assertRegex(body, r"`root/[A-Za-z0-9_./+-]+\.(?:cxx|hxx|h):\d+")


class ByteOrderFormats(unittest.TestCase):
    """check_bytes.py gained little-endian formats for RNTuple's envelopes.

    A ROOT file with an RNTuple in it has both byte orders, with the boundary at
    the anchor's last byte, so a case has to say which at every offset, and
    getting it wrong must fail rather than read a plausible number. These are
    the two cases the first RNTuple fixture turned up.
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
        # type 1 in the low 16 bits, length 240 in the upper 48: the header
        # envelope of rntuple/anchor.
        buf = bytes([0x01, 0x00, 0xf0, 0x00, 0x00, 0x00, 0x00, 0x00])
        ok = [{"offset": 0, "type": "u64le", "value": (240 << 16) | 1, "name": "le"}]
        self.assertEqual(self.check_bytes.check(buf, ok, "x"), [])
        # The same bytes read big-endian are a different, plausible-looking
        # number, so the suffix has to be explicit.
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
    # `std::byte` is the only header the document namespaces; strip on both
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


class EveryAnchorReads(unittest.TestCase):
    """Every RNTuple in data/ reads through its anchor to its header schema.

    Every other test here names its fixture, and until 2026-09-22 all of them
    named uncompressed ones, so nothing in CI gave read_rntuple_anchor a
    compressed anchor, and it could not read one (PLAN-corpus.md C6). Walking
    every fixture instead of a list covers a new RNTuple case as soon as it is
    committed, whatever it was written to demonstrate.
    """

    def test_every_anchor_reads_and_one_is_compressed(self):
        sys.path.insert(0, str(REPO / "tools"))
        import rootfile
        read = compressed = 0
        for path in sorted((REPO / "data").rglob("*.root")):
            buf, _, recs = rootfile.load(path)
            for rec in recs:
                if rec.free or rec.class_name != "ROOT::RNTuple":
                    continue
                with self.subTest(file=path.name):
                    anchor, schema = rootfile.read_rntuple(buf, rec)
                    self.assertEqual((anchor.epoch, anchor.major), (1, 0))
                    self.assertTrue(schema.fields)
                read += 1
                compressed += rec.compressed
        self.assertGreater(read, 0)
        # Without this the test would pass vacuously if rntuple/compressed were
        # ever regenerated with compression off.
        self.assertGreater(compressed, 0)


class FundamentalTypeTable(unittest.TestCase):
    """The tracked table against a file, so the two cannot drift apart.

    The same idea as check_versions.py for class versions: a table of names can
    go stale without anything failing, and here both sides move, the document on
    a submodule bump and the file when ROOT changes a default.
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
            # Any mention counts as the claim, since the wording varies: "named
            # `_0`", "the name of the child field is `_0`", "their names are `_0`,
            # `_1`, ...".
            claims[section] = line.strip()
    return claims


class SchemaReading:
    """A fixture's decoded RNTuple schema, and the three views the tests use."""

    FIXTURE: Path

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


class StdlibTypeMapping(SchemaReading, unittest.TestCase):
    """*Stdlib Types and Collections* against a file, type by type.

    The claims there are prose, not a table: how many fields a type becomes, what
    the parent's columns are, what the children are called. `rntuple/collections`
    is one field per type and this reads the decoded schema against them.
    """

    FIXTURE = REPO / "data/rntuple/collections.root"

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


class AssociativeMapping(SchemaReading, unittest.TestCase):
    """The `std::map` subsection, against `rntuple/map`: all four types it names.

    "An (unordered) (multi)map is stored using a collection parent field, whose
    principal column is of type `(Split)Index[64|32]` and a child field of type
    `std::pair<K, V>` named `_0`."
    """

    FIXTURE = REPO / "data/rntuple/map.root"
    PAIRS = {
        "fMap": ("std::map<std::string,std::int32_t>",
                 "std::pair<std::string,std::int32_t>"),
        "fUnordered": ("std::unordered_map<std::int32_t,std::int32_t>",
                       "std::pair<std::int32_t,std::int32_t>"),
        "fMulti": ("std::multimap<std::string,std::int32_t>",
                   "std::pair<std::string,std::int32_t>"),
        "fUnMulti": ("std::unordered_multimap<std::string,std::int32_t>",
                     "std::pair<std::string,std::int32_t>"),
    }

    def test_every_map_is_a_collection_parent_over_a_pair_named_0(self):
        for name, (map_type, pair_type) in self.PAIRS.items():
            with self.subTest(field=name):
                field = self.top[name]
                self.assertEqual((field.role, field.type_name, self.cols(field)),
                                 ("collection", map_type, ["Index64"]))
                child, = self.children(field)
                self.assertEqual((child.name, child.type_name), ("_0", pair_type))

    def test_the_pair_is_a_record_with_no_columns_and_two_children(self):
        for name in self.PAIRS:
            with self.subTest(field=name):
                pair, = self.children(self.top[name])
                self.assertEqual((pair.role, self.cols(pair)), ("record", []))
                self.assertEqual([c.name for c in self.children(pair)],
                                 ["_0", "_1"])

    def test_the_document_still_names_all_four(self):
        text = TRACKED.read_text()
        self.assertIn("#### std::map\\<K, V\\>, std::unordered_map\\<K, V\\>, "
                      "std::multimap\\<K, V\\>, std::unordered_multimap\\<K, V\\>",
                      text)


class UserClassMapping(unittest.TestCase):
    """*User-defined classes* and *User-defined enums* against a file.

    `rntuple/user-class` is a struct with a base class, two enums, a vector of
    itself and a transient member, so the record shape is checked twice in one
    file: at top level and inside a collection.
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
        # fScratch is marked //! in classes.h. This checks its absence; the byte
        # assertions check that nothing else shifted.
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


class SchemaOnlyFields(unittest.TestCase):
    """Fields no C++ member produces: projected, untyped, streamed, SoA.

    One fixture each, and the claims are the prose of *Alias columns*,
    *RNTupleCardinality*, *ROOT streamed types*, *Untyped collections and records*
    and the SoA subsection.
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO / "tools"))
        import rootfile
        cls.rootfile = rootfile

    def schema(self, name):
        rootfile = self.rootfile
        buf, _, recs = rootfile.load(REPO / f"data/rntuple/{name}.root")
        rec = next(r for r in recs if r.class_name == "ROOT::RNTuple")
        anchor, schema = rootfile.read_rntuple(buf, rec)
        return buf, anchor, schema

    @staticmethod
    def columns_of(schema, field):
        return [c for c in schema.columns if c.field_id == field.field_id]

    # -- projected fields and alias columns ------------------------------

    def test_a_projected_field_has_no_column_of_its_own(self):
        _, _, s = self.schema("projected")
        by_name = {f.name: f for f in s.fields}
        for name in ("fEnergy", "fAlias", "fN32", "fN64"):
            with self.subTest(field=name):
                field = by_name[name]
                self.assertTrue(field.flags & 0x02, "the projected flag")
                self.assertIsNotNone(field.source_id)
                self.assertEqual(self.columns_of(s, field), [])

    def test_every_projected_field_has_an_alias_column(self):
        _, _, s = self.schema("projected")
        aliased = {a.field_id for a in s.alias_columns}
        projected = {f.field_id for f in s.fields if f.flags & 0x02}
        self.assertEqual(aliased, projected)

    def test_one_physical_column_backs_several_alias_columns(self):
        _, _, s = self.schema("projected")
        physical = [a.physical_id for a in s.alias_columns]
        self.assertEqual(physical.count(0), 3, physical)

    def test_cardinality_is_projected_from_a_collection(self):
        _, _, s = self.schema("projected")
        by_name = {f.name: f for f in s.fields}
        source = by_name["fVec"]
        for name, width in (("fN32", "std::uint32_t"), ("fN64", "std::uint64_t")):
            with self.subTest(field=name):
                field = by_name[name]
                self.assertEqual(field.type_name,
                                 f"ROOT::RNTupleCardinality<{width}>")
                self.assertEqual(field.source_id, source.field_id)
                self.assertEqual(source.role, "collection")

    # -- untyped ---------------------------------------------------------

    def test_an_untyped_field_has_an_empty_type_name(self):
        _, _, s = self.schema("untyped")
        by_name = {f.name: f for f in s.fields}
        self.assertEqual((by_name["fRecord"].role, by_name["fRecord"].type_name),
                         ("record", ""))
        self.assertEqual((by_name["fColl"].role, by_name["fColl"].type_name),
                         ("collection", ""))
        # Its members are ordinary typed fields, and the shapes are the typed ones.
        self.assertEqual(by_name["fX"].type_name, "float")
        self.assertEqual(self.columns_of(s, by_name["fRecord"]), [])
        self.assertEqual([c.type_name for c in
                          self.columns_of(s, by_name["fColl"])], ["Index64"])

    # -- streamed --------------------------------------------------------

    def test_a_streamed_field_is_role_4_with_an_index_and_a_byte_column(self):
        _, _, s = self.schema("streamed")
        field = next(f for f in s.fields if f.name == "fInner")
        self.assertEqual((field.structure, field.role), (0x04, "streamer"))
        self.assertEqual([c.type_name for c in self.columns_of(s, field)],
                         ["Index64", "Byte"])

    def test_the_streamer_info_is_not_in_the_header(self):
        # ERRATA 10. The header's list is empty; the record is in the footer's
        # schema extension, which test_the_streamer_info_is_in_the_footer reads.
        _, _, s = self.schema("streamed")
        self.assertEqual(s.type_info, [])

    def test_the_streamer_info_is_in_the_footer_and_is_length_prefixed(self):
        # ERRATA 9 and 10 together: walk the footer's schema extension by hand,
        # because this project's reader stops at the header.
        import struct
        rootfile = self.rootfile
        buf, anchor, _ = self.schema("streamed")
        env = rootfile.read_rn_envelope(buf, anchor.seek_footer)
        o = env.body
        _, o = rootfile.read_rn_feature_flags(buf, o)
        o += 8                                        # the header checksum
        ext = rootfile.read_rn_frame(buf, o)
        pos = ext.body
        for _ in range(3):                            # fields, columns, aliases
            pos = rootfile.read_rn_frame(buf, pos).end
        type_info = rootfile.read_rn_frame(buf, pos)
        self.assertEqual(type_info.items, 1)
        inner = rootfile.read_rn_frame(buf, type_info.body)
        content_id, type_version = struct.unpack_from("<II", buf, inner.body)
        name, after = rootfile.read_rn_string(buf, inner.body + 8)
        self.assertEqual((content_id, type_version, name), (0, 0, ""))
        # The content is a string: a length, and only then the streamed object.
        length = struct.unpack_from("<I", buf, after)[0]
        self.assertEqual(after + 4 + length, inner.end)
        count = struct.unpack_from(">I", buf, after + 4)[0]
        self.assertTrue(count & 0x40000000, "a ROOT byte count")
        self.assertEqual(count & ~0x40000000, length - 4)
        self.assertEqual(buf[after + 12:after + 17], b"TList")
        self.assertIn(b"RNStreamedInner", buf[after:inner.end])

    # -- SoA -------------------------------------------------------------

    def test_the_soa_flag_is_set_and_the_child_is_the_record(self):
        _, _, s = self.schema("soa")
        parent = next(f for f in s.fields if f.name == "fPoints")
        self.assertEqual(parent.role, "collection")
        self.assertTrue(parent.flags & 0x08, "the SoA flag")
        self.assertTrue(parent.flags & 0x04, "has a checksum")
        self.assertEqual(parent.type_name, "RNPointSoA")
        self.assertEqual([c.type_name for c in self.columns_of(s, parent)],
                         ["Index64"])
        child = next(f for f in s.fields
                     if f.parent_id == parent.field_id and f is not parent)
        self.assertEqual((child.name, child.type_name, child.role),
                         ("_0", "RNPointRecord", "record"))

    def test_both_classes_carry_the_same_version_because_root_requires_it(self):
        # root/tree/ntuple/src/RFieldMeta.cxx:707 refuses a mismatch, which the
        # document does not mention. The checksums still differ.
        _, _, s = self.schema("soa")
        parent = next(f for f in s.fields if f.name == "fPoints")
        child = next(f for f in s.fields
                     if f.parent_id == parent.field_id and f is not parent)
        self.assertEqual(parent.type_version, child.type_version)
        self.assertNotEqual(parent.type_checksum, child.type_checksum)


class WriterDefaults(unittest.TestCase):
    """*Defaults* against RNTupleWriteOptions, and *Naming* against the validator.

    Neither needs a file: both are claims about the writer, checked against its
    header. Parsed out of the tracked copy so the table cannot drift.
    """

    SOURCE = REPO / "root/tree/ntuple/inc/ROOT/RNTupleWriteOptions.hxx"

    @unittest.skipUnless(HAVE_SUBMODULE, "root/ submodule is not checked out")
    def test_the_three_documented_defaults_match_the_source(self):
        text = self.SOURCE.read_text()
        for member, expected in (
                ("fApproxZippedClusterSize", 128 * 1024 * 1024),      # 128 MiB
                ("fMaxUnzippedClusterSize", 10 * 128 * 1024 * 1024),  # 1280 MiB
                ("fMaxUnzippedPageSize", 1024 * 1024)):               # 1 MiB
            line = next(l for l in text.splitlines()
                        if l.strip().startswith(f"std::size_t {member} ="))
            value = line.split("=", 1)[1].strip().rstrip(";")
            with self.subTest(member=member):
                self.assertEqual(eval(value, {"fApproxZippedClusterSize":
                                              128 * 1024 * 1024}), expected)

    def test_the_documented_table_still_has_exactly_those_three_rows(self):
        lines = TRACKED.read_text().splitlines()
        start = lines.index("## Defaults")
        rows = [l for l in lines[start:start + 12]
                if l.startswith("|") and not set(l) <= set("|- ")]
        # The header row plus three defaults. A fourth would mean the document
        # started documenting more of RNTupleWriteOptions than it used to.
        self.assertEqual(len(rows), 4, rows)

    @unittest.skipUnless(HAVE_SUBMODULE, "root/ submodule is not checked out")
    def test_the_forbidden_characters_are_exactly_the_documented_ones(self):
        source = (REPO / "root/tree/ntuple/src/RNTupleUtils.cxx").read_text()
        for code in ("\\u002E", "\\u002F", "\\u0020", "\\u005C"):
            self.assertIn(code, source)
        self.assertIn("iscntrl", source)


def _section(text: str, heading: str) -> str:
    """The body of the tracked copy's section `heading`, up to the next heading
    of the same or a higher level."""
    import re
    lines = text.splitlines()
    start = lines.index(heading)
    level = len(heading) - len(heading.lstrip("#"))
    end = next((i for i in range(start + 1, len(lines))
                if re.match(rf"^#{{1,{level}}} ", lines[i])), len(lines))
    return "\n".join(lines[start + 1:end])


def _diagram_fields(section: str) -> list[tuple[str, int]]:
    """(name, bits) of each field of the first bit diagram in `section`.

    Rows are 32 bits wide and fields are separated by `+-+-` lines. A group of
    one row with n cells is n fields of 32/n bits. A wider field is drawn as
    several `|` rows with a `+ name +` line between them, which marks a word
    boundary inside the field rather than a row of its own, so it is 32 bits
    per `|` row.
    """
    body = section.split("```", 2)[1]
    rows = [line for line in body.splitlines() if line and line[0] in "|+"]
    groups: list[list[str]] = [[]]
    for row in rows:
        if row.startswith("+-"):
            groups.append([])
        else:
            groups[-1].append(row)
    fields: list[tuple[str, int]] = []
    for group in groups:
        if len(group) == 1:
            cells = [c.strip() for c in group[0].strip("|").split("|")]
            fields += [(c, 32 // len(cells)) for c in cells]
        elif group:
            name = " ".join(r.strip("|+").strip() for r in group).strip()
            fields.append((name, 32 * sum(r.startswith("|") for r in group)))
    return fields


class LinkedAttributeSets(unittest.TestCase):
    """*Linked Attribute Sets* and its record frame, against `rntuple/attributes`.

    Each claim is parsed out of the tracked copy, as for the type mapping, so a
    change on either side fails here: the document's on a submodule bump, or
    ROOT's writer. The fixture holds two sets, `runs` and `flags`; NOTES.md 8
    and ERRATA 11-13 are what the audit found.
    """

    FIXTURE = REPO / "data/rntuple/attributes.root"
    TEXT = TRACKED.read_text()

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO / "tools"))
        import rootfile
        cls.rootfile = rootfile
        cls.buf, cls.header, cls.recs = rootfile.load(cls.FIXTURE)
        main = next(r for r in cls.recs if r.name == "ntpl"
                    and r.class_name == "ROOT::RNTuple")
        cls.anchor, cls.schema = rootfile.read_rntuple(cls.buf, main)
        cls.footer = rootfile.read_rntuple_footer(cls.buf, cls.anchor, cls.schema)
        cls.sets = {link.name: rootfile.read_attribute_set(cls.buf, link)
                    for link in cls.footer.attribute_sets}

    # -- the claims, parsed ----------------------------------------------

    def schema_claims(self):
        """(major, minor) and [(field, type or None for untyped record)]."""
        import re
        section = _section(self.TEXT, "### Attribute Schema Version")
        version = re.search(r"The current Attribute Schema Version is \*\*(\d+)\.(\d+)\*\*",
                            section)
        fields = re.findall(r"^\s*\d+\. `(\w+)` \((?:type `([^`]+)`|(untyped record))\)",
                            section, re.M)
        return ((int(version.group(1)), int(version.group(2))),
                [(name, typ or None) for name, typ, _ in fields])

    def restrictions(self):
        import re
        section = _section(self.TEXT, "## Linked Attribute Sets")
        return re.findall(r"^(\d+)\. (.+)$", section.split("###", 1)[0], re.M)

    # -- the record frame --------------------------------------------------

    def test_the_diagram_gives_two_u16_versions_then_a_u32_size(self):
        section = _section(self.TEXT, "#### Linked Attribute Set Record Frame")
        self.assertEqual(_diagram_fields(section),
                         [("Schema Version Major", 16), ("Schema Version Minor", 16),
                          ("Attribute Anchor Uncompressed Size", 32)])
        # "followed a locator ... and a string": the locator comes first.
        text = " ".join(section.split())
        self.assertRegex(text, r"followed a locator to the linked RNTuple anchor "
                               r"and a string with the attribute set name")

    def test_every_record_is_the_diagram_then_a_locator_then_a_string(self):
        # Sizes add up only in this order: 8 for the frame, 2 + 2 + 4 for the
        # diagram, a 12-byte simple locator, and a u32-counted name.
        for name, aset in self.sets.items():
            link = aset.link
            with self.subTest(set=name):
                self.assertEqual(link.end - link.start,
                                 8 + 2 + 2 + 4 + 12 + 4 + len(name.encode()))
                self.assertEqual(link.locator.kind, "file")
                self.assertEqual(link.locator.start, link.start + 16)

    @unittest.skipUnless(HAVE_SUBMODULE, "root/ submodule is not checked out")
    def test_root_serializes_the_fields_in_the_documented_order(self):
        import re
        source = (REPO / "root/tree/ntuple/src/RNTupleSerialize.cxx").read_text()
        start = source.index("RNTupleSerializer::SerializeAttributeSet(")
        body = source[start:source.index("\n}\n", start)]
        calls = re.findall(r"Serialize(UInt16|UInt32|Locator|String)\(", body)
        self.assertEqual(calls, ["UInt16", "UInt16", "UInt32", "Locator", "String"])

    def test_the_version_in_each_record_is_the_documented_one(self):
        version, _ = self.schema_claims()
        for name, aset in self.sets.items():
            with self.subTest(set=name):
                self.assertEqual((aset.link.major, aset.link.minor), version)

    def test_the_anchor_size_is_the_whole_object(self):
        # ERRATA 12. The document's anchor schema is 4 x 16 + 7 x 64 bits; the
        # size "includes the 8 bytes of the checksum" -- and also the six bytes
        # of byte count and class version the schema does not draw (ERRATA 2).
        section = _section(self.TEXT, "### Anchor schema")
        schema_bytes = sum(bits for _, bits in _diagram_fields(section)) // 8
        self.assertEqual(schema_bytes, 64)
        self.assertIn("Note that the Attribute Anchor Uncompressed Size includes "
                      "the 8 bytes of the checksum.", self.TEXT)
        for name, aset in self.sets.items():
            with self.subTest(set=name):
                self.assertNotEqual(aset.link.anchor_length, schema_bytes + 8)
                self.assertEqual(aset.link.anchor_length, 6 + schema_bytes + 8)
                self.assertEqual(aset.link.anchor_length,
                                 aset.anchor.byte_count + 4 + 8)

    def test_the_locator_names_the_anchor_object_whose_key_is_unlisted(self):
        # NOTES 8: the offset is the anchor key's payload, the size its on-disk
        # size, the length its fObjLen; and no directory lists that key.
        rootfile = self.rootfile
        by_payload = {rootfile.payload_range(r)[0]: r for r in self.recs
                      if not r.free and r.class_name == "ROOT::RNTuple"}
        for name, aset in self.sets.items():
            with self.subTest(set=name):
                key = by_payload[aset.link.locator.offset]
                self.assertEqual(key.name, name)
                self.assertEqual(aset.link.locator.nbytes, key.payload_nbytes)
                self.assertEqual(aset.link.anchor_length, key.obj_len)
        top = rootfile.read_directory(self.buf, next(r for r in self.recs
                                                     if r.offset == self.header.begin))
        self.assertEqual([k.name for k in rootfile.read_key_list(self.buf, top)],
                         ["ntpl"])

    # -- the linked RNTuple ------------------------------------------------

    def test_the_schema_is_the_documented_fields_in_order(self):
        _, claimed = self.schema_claims()
        self.assertEqual(claimed, [("_rangeStart", "std::uint64_t"),
                                   ("_rangeLen", "std::uint64_t"),
                                   ("_userData", None)])
        for name, aset in self.sets.items():
            top = [f for f in aset.schema.fields if f.parent_id == f.field_id]
            with self.subTest(set=name):
                self.assertEqual([f.name for f in top], [n for n, _ in claimed])
                for field, (_, typ) in zip(top, claimed):
                    if typ is None:       # "untyped record": role and no type
                        self.assertEqual((field.role, field.type_name), ("record", ""))
                    else:
                        self.assertEqual((field.role, field.type_name), ("plain", typ))

    def test_the_users_fields_hang_under_user_data_unchanged(self):
        expect = {"runs": [("run", "std::int32_t"), ("weight", "float")],
                  "flags": [("flag", "std::uint16_t")]}
        for name, aset in self.sets.items():
            user = next(f for f in aset.schema.fields if f.name == "_userData")
            kids = [(f.name, f.type_name) for f in aset.schema.fields
                    if f.parent_id == user.field_id and f is not user]
            with self.subTest(set=name):
                self.assertEqual(kids, expect[name])

    def test_the_three_restrictions_hold(self):
        restrictions = self.restrictions()
        self.assertEqual([n for n, _ in restrictions], ["1", "2", "3"])
        self.assertIn("linked attribute RNTuples", restrictions[0][1])
        self.assertIn("alias columns", restrictions[1][1])
        self.assertIn("0x04", restrictions[2][1])
        for name, aset in self.sets.items():
            with self.subTest(set=name):
                self.assertEqual(aset.footer.attribute_sets, [])
                self.assertEqual(aset.schema.alias_columns, [])
                self.assertEqual(aset.footer.extension_alias_columns, [])
                self.assertFalse([f for f in aset.schema.fields if f.structure == 0x04])

    def test_names_are_non_empty_distinct_and_not_reserved(self):
        self.assertIn("All linked attribute sets must have a non-empty, distinct name.",
                      self.TEXT)
        names = [link.name for link in self.footer.attribute_sets]
        self.assertEqual(names, ["runs", "flags"])
        self.assertIn("starting with `__` (two underscores) are reserved", self.TEXT)
        self.assertFalse([n for n in names if n.startswith("__")])

    @unittest.skipUnless(HAVE_SUBMODULE, "root/ submodule is not checked out")
    def test_root_uses_the_documented_names_version_and_reserved_prefix(self):
        import re
        utils = (REPO / "root/tree/ntuple/inc/ROOT/RNTupleAttrUtils.hxx").read_text()
        version, claimed = self.schema_claims()
        self.assertEqual(
            (int(re.search(r"kSchemaVersionMajor = (\d+);", utils).group(1)),
             int(re.search(r"kSchemaVersionMinor = (\d+);", utils).group(1))), version)
        names = re.search(r"kMetaFieldNames\[\] = \{([^}]*)\}", utils).group(1)
        self.assertEqual(re.findall(r'"(\w+)"', names), [n for n, _ in claimed])
        writer = (REPO / "root/tree/ntuple/src/RNTupleWriter.cxx").read_text()
        self.assertIn('return ROOT::StartsWith(name, "__");', writer)

    def test_the_ranges_read_back_through_the_page_lists(self):
        # "`_rangeLen == 0` is valid and refers to an empty range"; flags' first
        # entry is one, and the entries are in commit order, not start order.
        self.assertIn("`_rangeLen == 0` is valid and refers to an empty range", self.TEXT)
        rootfile = self.rootfile
        values = {}
        for name, aset in self.sets.items():
            pages = rootfile.read_rntuple_page_lists(self.buf, aset.footer)
            values[name] = {aset.schema.fields[c.field_id].name:
                            rootfile.read_column_values(self.buf, pages, c)
                            for c in aset.schema.columns}
        self.assertEqual(values["runs"], {"_rangeStart": [0, 3], "_rangeLen": [3, 3],
                                          "run": [1, 2], "weight": [0.25, 0.75]})
        self.assertEqual(values["flags"], {"_rangeStart": [3, 1], "_rangeLen": [0, 4],
                                           "flag": [7, 9]})
        # And every range lies inside the main RNTuple's six entries.
        for name, cols in values.items():
            for start, length in zip(cols["_rangeStart"], cols["_rangeLen"]):
                self.assertLessEqual(start + length, 6, name)

    # -- the errata ----------------------------------------------------------

    def test_the_footer_list_is_absent_before_format_1_0_1_0(self):
        # ERRATA 11. The document lists it unconditionally; ROOT's reader knows
        # better (RNTupleSerialize.cxx:2015-2017).
        section = _section(self.TEXT, "### Footer Envelope")
        self.assertIn("- List frame of cluster group record frames\n"
                      "- List frame of linked attribute set record frames\n", section)
        # No version qualifier anywhere in the footer's description.
        self.assertNotIn("1.0.1", section)
        # Present, and empty, in a 1.0.2.0 footer with no attribute sets.
        rootfile = self.rootfile
        buf, _, recs = rootfile.load(REPO / "data/rntuple/anchor.root")
        anchor, schema = rootfile.read_rntuple(
            buf, next(r for r in recs if r.class_name == "ROOT::RNTuple"))
        self.assertEqual(anchor.version, "1.0.2.0")
        self.assertEqual(rootfile.read_rntuple_footer(buf, anchor, schema)
                         .attribute_sets, [])
        cern = REPO / "build/cern/RNTuple.root"
        if cern.exists():         # 1.0.0.0, by ROOT 6.35/01: no list at all
            buf, _, recs = rootfile.load(cern)
            anchor = rootfile.read_rntuple_anchor(
                buf, next(r for r in recs if r.class_name == "ROOT::RNTuple"))
            self.assertEqual(anchor.version, "1.0.0.0")
            self.assertIsNone(rootfile.read_rntuple_footer(buf, anchor).attribute_sets)

    @unittest.skipUnless(HAVE_SUBMODULE, "root/ submodule is not checked out")
    def test_root_refuses_any_field_beyond_the_three_whatever_the_minor(self):
        # ERRATA 13: the document says a new minor version only adds optional
        # fields that readers ignore; ROOT's reader counts them.
        self.assertIn("readers should\nstill be able to read the attribute set as "
                      "before, ignoring any new field.", self.TEXT)
        source = (REPO / "root/tree/ntuple/src/RNTupleAttrReading.cxx").read_text()
        self.assertIn("if (metaFieldIds.size() != kMetaFieldIndex_Count) {", source)
        self.assertIn("if (vSchemaMajor != kSchemaVersionMajor)", source)
        self.assertNotIn("Minor", source)


class AttributeSetChecks(unittest.TestCase):
    """The attribute set checks of check_invariants.py fire on corrupted copies.

    AGENTS.md: an invariant is confirmed by corrupting a copy of a fixture. The
    envelopes' checksums are not verified by this project's reader, so a byte
    can be changed in place; one corruption rebuilds a header instead.
    """

    FIXTURE = REPO / "data/rntuple/attributes.root"

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO / "tools"))
        import check_invariants
        import rootfile
        cls.check_invariants = check_invariants
        cls.rootfile = rootfile
        cls.src = cls.FIXTURE.read_bytes()
        _, _, recs = rootfile.load(cls.FIXTURE)
        cls.main = next(r for r in recs if r.name == "ntpl"
                        and r.class_name == "ROOT::RNTuple")
        anchor, schema = rootfile.read_rntuple(cls.src, cls.main)
        cls.anchor = anchor
        cls.footer = rootfile.read_rntuple_footer(cls.src, anchor, schema)
        cls.runs, cls.flags = cls.footer.attribute_sets

    def failures(self, buf: bytes) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corrupt.root"
            path.write_bytes(buf)
            checker = self.check_invariants.Checker(path)
            with contextlib.redirect_stderr(io.StringIO()):
                return [f.split(": ", 2)[1] for f in checker.run()]

    def edit(self, *edits) -> bytes:
        import struct
        b = bytearray(self.src)
        for offset, fmt, value in edits:
            if fmt == "raw":
                b[offset:offset + len(value)] = value
            else:
                struct.pack_into(fmt, b, offset, value)
        return bytes(b)

    def test_the_fixture_passes(self):
        self.assertEqual(self.failures(self.src), [])

    def test_an_empty_name(self):
        name_at = self.flags.locator.end
        self.assertIn("RNTuple attribute set, name",
                      self.failures(self.edit((name_at, "<I", 0))))

    def test_a_duplicate_name(self):
        name_at = self.flags.locator.end
        got = self.failures(self.edit((name_at, "<I", 4), (name_at + 4, "raw", b"runs")))
        self.assertEqual(got.count("RNTuple attribute set, name"), 1)

    def test_a_locator_that_misses_the_anchor(self):
        at = self.runs.locator.start + 4
        self.assertIn("RNTuple attribute set, locator",
                      self.failures(self.edit((at, "<Q", self.runs.locator.offset + 1))))

    def test_an_anchor_length_of_the_schema_plus_checksum(self):
        # ERRATA 12: 72 is what a reader of the document would write.
        self.assertIn("RNTuple attribute set, locator",
                      self.failures(self.edit((self.runs.start + 12, "<I", 72))))

    def test_a_nested_attribute_set(self):
        # Point `runs` at the main RNTuple's own anchor, which links two sets.
        main_payload = self.rootfile.payload_range(self.main)[0]
        got = self.failures(self.edit((self.runs.locator.start + 4, "<Q", main_payload)))
        self.assertIn("RNTuple attribute set, restriction 1", got)

    def test_an_alias_column(self):
        self.assertIn("RNTuple attribute set, restriction 2",
                      self.failures(self.with_alias_column()))

    def test_a_streamer_field(self):
        rootfile = self.rootfile
        aset = rootfile.read_attribute_set(self.src, self.runs)
        run = next(f for f in aset.schema.fields if f.name == "run")
        structure_at = run.start + 8 + 12
        self.assertIn("RNTuple attribute set, restriction 3",
                      self.failures(self.edit((structure_at, "<H", 0x04))))

    def test_a_misnamed_internal_field(self):
        aset = self.rootfile.read_attribute_set(self.src, self.runs)
        field = next(f for f in aset.schema.fields if f.name == "_rangeLen")
        name_at = field.start + 8 + 16 + 4
        self.assertIn("RNTuple attribute set, schema version",
                      self.failures(self.edit((name_at, "raw", b"_rangeEnd"))))

    def test_an_unknown_major_version_is_skipped_not_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "major.root"
            path.write_bytes(self.edit((self.runs.start + 8, "<H", 2)))
            checker = self.check_invariants.Checker(path)
            self.assertEqual(checker.run(), [])
            self.assertTrue([k for k in checker.skipped
                             if k[0] == "RNTuple attribute set, schema version"])

    def test_a_1_0_2_0_footer_without_the_list(self):
        # Shorten the main footer to end after its cluster groups, and the
        # anchor's two footer sizes with it.
        start = self.anchor.seek_footer
        length = self.footer.attribute_list_start + 8 - start
        anchor_at = self.rootfile.payload_range(self.main)[0]
        got = self.failures(self.edit((start, "<Q", (length << 16) | 2),
                                      (anchor_at + 14 + 32, ">Q", length),
                                      (anchor_at + 14 + 40, ">Q", length)))
        self.assertIn("RNTuple footer, attribute set list", got)

    def with_alias_column(self) -> bytes:
        """`flags` rebuilt with one alias column in its header, same length.

        The header is re-serialized with the name shortened to make room for
        the alias record frame, and the writer string sized to fill the rest,
        so no other byte of the file moves.
        """
        import struct
        rootfile = self.rootfile
        aset = rootfile.read_attribute_set(self.src, self.flags)
        env = rootfile.read_rn_envelope(self.src, aset.anchor.seek_header)
        o = env.body
        _, o = rootfile.read_rn_feature_flags(self.src, o)
        flags_bytes = self.src[env.body:o]
        for _ in range(3):                           # name, description, writer
            o = rootfile.read_rn_string(self.src, o)[1]
        fields = rootfile.read_rn_frame(self.src, o)
        columns = rootfile.read_rn_frame(self.src, fields.end)
        lists = self.src[fields.start:columns.end]
        alias = (struct.pack("<qI", -(12 + 16), 1) + struct.pack("<qII", 16, 0, 0))
        empty = struct.pack("<qI", -12, 0)

        def s(text: bytes) -> bytes:
            return struct.pack("<I", len(text)) + text
        fixed = flags_bytes + s(b"f") + s(b"") + lists + alias + empty
        room = (env.body_end - env.body) - len(fixed) - 4
        self.assertGreaterEqual(room, 0)
        body = flags_bytes + s(b"f") + s(b"") + s(b"R" * room) + lists + alias + empty
        self.assertEqual(len(body), env.body_end - env.body)
        return self.src[:env.body] + body + self.src[env.body_end:]
