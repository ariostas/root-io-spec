#!/usr/bin/env python3
"""A corruption test for each checked invariant that has been wrong before.

`AGENTS.md` asks that every check be confirmed by corrupting a copy of a
fixture and watching it fire. About 150 of the 200 checked labels have no test
that does so (`gen/invariants.toml` says which), and a check that never fires
is indistinguishable from one that cannot: `Compression 9.7` was vacuous once
already (`PLAN-corpus.md` C7). A full sweep was not the ask. These are the
labels whose invariant or check was wrong at some point, in `PLAN.md` §8.13 to
§8.16 and in `PLAN-review.md` V5, V15, V36 and V42, and that had no such test
(PLAN-review.md V34).

Each test shows the fixture passing, then one corruption making the label
fire.
"""

import struct
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_invariants  # noqa: E402
import rootfile  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"


def checker(path: Path, patches=()) -> check_invariants.Checker:
    """A Checker over a copy of `path` with (offset, bytes) `patches` applied."""
    buf = bytearray(path.read_bytes())
    for offset, value in patches:
        buf[offset:offset + len(value)] = value
    tmp = Path(tempfile.mkdtemp()) / path.name
    tmp.write_bytes(bytes(buf))
    return check_invariants.Checker(tmp)


def fired(failures, label):
    return [f for f in failures if f": {label}:" in f]


class Container(unittest.TestCase):
    MINIMAL = DATA / "container/file-minimal.root"

    def test_the_fixture_passes(self):
        self.assertEqual(checker(self.MINIMAL).run(), [])

    def test_directory_9_4_the_top_directory_fnbytesname(self):
        # V42: once applied to every directory; ROOT range-checks the top one
        # only. Its fNbytesName is the fifth field of the directory record,
        # after fVersion, fDatimeC, fDatimeM and fNbytesKeys.
        buf, header, _ = rootfile.load(self.MINIMAL)
        at = header.begin + header.nbytes_name + 14
        self.assertEqual(struct.unpack_from(">i", buf, at)[0], header.nbytes_name)
        failures = checker(self.MINIMAL, [(at, struct.pack(">i", 5))]).run()
        self.assertTrue(fired(failures, "Directory 9.4"), failures)

    def test_freesegments_8_2_the_trailing_entry(self):
        # V15: stated as a multiple of 1e9 where TFile::Recover writes
        # fEND + 1e9. Here fLast is pulled down to fEND.
        buf, header, _ = rootfile.load(self.MINIMAL)
        sentinel = struct.pack(">i", 2000000000)
        at = buf.index(sentinel, header.seek_free)
        failures = checker(self.MINIMAL,
                           [(at, struct.pack(">i", header.end))]).run()
        self.assertTrue(fired(failures, "FreeSegments 8.2"), failures)

    def test_compression_9_7_a_raw_payload_that_looks_compressed(self):
        # C7: vacuous once. The TObjString at 310 is raw; its payload is made
        # to begin with a zlib block header whose sizes fit the record.
        start = 310 + 66
        header = b"ZL\x08" + (10).to_bytes(3, "little") + (10).to_bytes(3, "little")
        failures = checker(self.MINIMAL, [(start, header)]).run()
        self.assertTrue(fired(failures, "Compression 9.7"), failures)


class Compressed(unittest.TestCase):
    PATH = DATA / "ttree/basket-compressed.root"

    def test_the_fixture_passes(self):
        self.assertEqual(checker(self.PATH).run(), [])

    def test_compression_9_1_a_payload_that_does_not_decompress(self):
        # V36: reported under an unnumbered "Compression 9" until 2026-09-24.
        # The TTree record at 505 is one zlib block; its declared uncompressed
        # size is changed, so the chain no longer yields fObjlen bytes.
        start = 505 + 53
        self.assertEqual(self.PATH.read_bytes()[start:start + 2], b"ZL")
        failures = checker(self.PATH, [(start + 6, (1000).to_bytes(3, "little"))]).run()
        self.assertTrue(fired(failures, "Compression 9.1"), failures)


class MultiBlock(unittest.TestCase):
    """Compression 9.5 was checked as a block count until 2026-09-24, which a
    chain whose sizes are wrong but sum to fObjlen passed (V42)."""

    PATH = DATA / "ttree/basket-multiblock.root"

    def test_the_fixture_passes(self):
        self.assertEqual(checker(self.PATH).run(), [])

    def test_compression_9_5_every_block_but_the_last_is_full(self):
        # The basket at 302 is two blocks, 0xFFFFFF and 22797 bytes. Move one
        # byte from the first to the second: the count and the sum still hold.
        buf, _, records = rootfile.load(self.PATH)
        rec = next(r for r in records if r.offset == 302)
        first = rec.payload_offset
        comp = int.from_bytes(buf[first + 3:first + 6], "little")
        second = first + 9 + comp
        self.assertEqual(int.from_bytes(buf[first + 6:first + 9], "little"),
                         0xFFFFFF)
        last = int.from_bytes(buf[second + 6:second + 9], "little")
        failures = checker(self.PATH, [
            (first + 6, (0xFFFFFE).to_bytes(3, "little")),
            (second + 6, (last + 1).to_bytes(3, "little"))]).run()
        self.assertTrue(fired(failures, "Compression 9.5"), failures)
        self.assertFalse(fired(failures, "Compression 9.3"), failures)


class References(unittest.TestCase):
    PATH = DATA / "serialization/references.root"

    def test_the_fixture_passes(self):
        self.assertEqual(checker(self.PATH).run(), [])

    def test_references_8_5_the_trefarray_length(self):
        # V5: the published length formula omitted the byte count and the
        # version word. The check is by consumption: one more object than the
        # payload holds must not end where the payload does.
        buf = self.PATH.read_bytes()
        arr = rootfile.read_ref_array(buf, 658)
        at = arr.end - 4 * arr.nobjects - 10
        self.assertEqual(struct.unpack_from(">i", buf, at)[0], arr.nobjects)
        failures = checker(self.PATH,
                           [(at, struct.pack(">i", arr.nobjects + 1))]).run()
        self.assertTrue(fired(failures, "References 8.5"), failures)


class Elements(unittest.TestCase):
    """ElementTypes 11.3 and 11.4 were found wrong within an hour of being
    wired up (AGENTS.md); StreamerInfo 13.11's exemption covered nothing
    (V36). The streamer-info record of every fixture is compressed, so the
    elements are altered after the read rather than in the bytes."""

    PATH = DATA / "serialization/element-types.root"
    STL = DATA / "serialization/collections.root"

    def failures(self, change, path=PATH):
        c = check_invariants.Checker(path)
        a, b, infos = c.streamer_infos()
        infos = [replace(si, elements=[change(e) for e in si.elements])
                 for si in infos]
        c.streamer_infos = lambda: (a, b, infos)
        c.check_streamer_info()
        return c.failures

    def test_the_fixtures_pass(self):
        self.assertEqual(self.failures(lambda e: e), [])
        self.assertEqual(self.failures(lambda e: e, self.STL), [])

    def test_elementtypes_11_3_an_stl_code_on_a_basic_element(self):
        def change(e):
            return replace(e, ftype=500) if e.cls == "TStreamerBasicType" else e
        self.assertTrue(fired(self.failures(change), "ElementTypes 11.3"))

    def test_elementtypes_11_4_a_fixed_array_with_no_length(self):
        # V15: 81 and 82 are kOffsetL forms the published clause left out;
        # the fixture's fixed arrays of objects are exactly those.
        def change(e):
            return replace(e, array_length=0) if e.ftype in (81, 82) else e
        self.assertTrue(fired(self.failures(change), "ElementTypes 11.4"))

    def test_streamerinfo_13_11_extents_that_do_not_multiply_out(self):
        def change(e):
            if e.array_dim == 0:
                return e
            return replace(e, array_length=e.array_length + 1)
        self.assertTrue(fired(self.failures(change), "StreamerInfo 13.11"))

    def test_streamerinfo_13_11_now_covers_an_stl_element(self):
        # The exemption is gone: an STL element with fArrayDim set is held to
        # the product like any other.
        def change(e):
            if e.cls != "TStreamerSTL":
                return e
            return replace(e, array_dim=1, array_length=3,
                           max_index=[2] + list(e.max_index[1:]))
        self.assertTrue(fired(self.failures(change, self.STL),
                              "StreamerInfo 13.11"))


class Leaves(unittest.TestCase):
    PATH = DATA / "ttree/tree.root"

    def test_tleaf_10_6_offsets_on_a_fixed_width_branch(self):
        # PLAN.md 8.15: fEntryOffsetLen 1000 on a fixed-width branch was
        # attributed to ROOT 4 and was g4tools, so the check keys on
        # fEntryOffsetLen 0 rather than on the leaves alone. The baskets are
        # given an offset array after the read.
        c = check_invariants.Checker(self.PATH)
        self.assertEqual(c.run(), [])
        c = check_invariants.Checker(self.PATH)
        walk = c.branch_baskets

        def with_offsets(br, data):
            for i, rec, payload, basket, why in walk(br, data):
                if basket is not None and not br.entry_offset_len:
                    basket = replace(basket,
                                     entry_offsets=[0] * basket.nev_buf)
                yield i, rec, payload, basket, why
        c.branch_baskets = with_offsets
        self.assertTrue(fired(c.run(), "TLeaf 10.6"))


if __name__ == "__main__":
    unittest.main()
