#!/usr/bin/env python3
"""Tests for spec/03-classes/RooFit.md, against `data/classes/roofit.root`.

Every invariant of §7 is confirmed the way `CLAUDE.md` requires: by corrupting a
copy of the fixture and checking that the corruption is caught, and under the
right label. The fixture is written with compression off, so each corruption is
a byte patch.
"""

import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_invariants  # noqa: E402
import rootfile  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "data/classes/roofit.root"

# Offsets, from gen/cases/classes/roofit/case.toml.
RRV_BYTE_COUNT = 533          # the RooRealVar frame
PROXY_BYTE_COUNT = 696        # RooAbsArg::_proxyList, a RooRefArray
BINNING_BYTE_COUNT = 859      # the RooAbsBinning base of RooUniformBinning
LIST_SIZE = 1083              # RooLinkedList::_size


def failures(data: bytes) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "roofit.root"
        path.write_bytes(data)
        checker = check_invariants.Checker(path)
        checker.run()
        return checker.failures


def patched(offset: int, value: int, fmt: str = ">I") -> bytes:
    buf = bytearray(FIXTURE.read_bytes())
    struct.pack_into(fmt, buf, offset, value)
    return bytes(buf)


def labels(bad: list[str]) -> set[str]:
    """The invariant labels in a run's failure lines, which read
    `<file>: <Doc N.M>: <message>`."""
    return {line.split(":")[1].strip() for line in bad if line.count(":") >= 2}


class TheFixtureItselfPasses(unittest.TestCase):
    def test_no_failures(self):
        self.assertEqual(failures(FIXTURE.read_bytes()), [])


class TheLayoutIsWhatSectionSixSays(unittest.TestCase):
    """That the readers agree with the document, on the bytes ROOT wrote."""

    @classmethod
    def setUpClass(cls):
        cls.buf, _, records = rootfile.load(FIXTURE)
        cls.records = records
        info_rec = next(r for r in records
                        if not r.free and r.name == "StreamerInfo")
        cls.infos = rootfile.read_streamer_infos(
            rootfile.object_data(cls.buf, info_rec), info_rec)

    def decoded(self, name):
        rec = next(r for r in self.records if not r.free and r.name == name)
        return rec, rootfile.decode_record(self.buf, rec, self.infos)

    def test_no_streamer_info_for_roorealvar(self):
        # RooFit.md 2.3: its Streamer never calls WriteClassBuffer, so nothing
        # tags the class's info for writing.
        self.assertNotIn("RooRealVar", {i.name for i in self.infos})
        self.assertIn("RooRealVarSharedProperties", {i.name for i in self.infos})

    def test_the_roorealvar_byte_count_covers_its_tail(self):
        rec, value = self.decoded("x")
        _, end = rootfile.payload_range(rec)
        frame = rootfile.read_frame(self.buf, value.start)
        self.assertEqual((value.end, frame.end), (end, end))
        tail = value.members[-1]
        self.assertEqual(tail.name, "_sharedProp")
        self.assertEqual(tail.type_name, "RooRealVarSharedProperties")
        self.assertEqual(tail.end, end)

    def test_the_asymmetric_errors_are_the_sentinel_not_a_measurement(self):
        _, value = self.decoded("x")
        by_name = {m.name: m for m in value.members}
        got = {n: struct.unpack_from(">d", self.buf, by_name[n].start)[0]
               for n in ("_error", "_asymErrLo", "_asymErrHi")}
        self.assertEqual(got, {"_error": 0.25, "_asymErrLo": 1.0,
                               "_asymErrHi": -1.0})

    def test_the_roolinkedlist_record_has_no_byte_count(self):
        # Buffer.md 2.3. The payload opens with a version word.
        rec, value = self.decoded("l")
        start, end = rootfile.payload_range(rec)
        self.assertEqual(struct.unpack_from(">h", self.buf, start)[0], 3)
        self.assertEqual(rootfile.read_frame(self.buf, start).byte_count, None)
        self.assertEqual(value.end, end)

    def test_the_roolinkedlist_slots_are_not_in_its_streamer_info(self):
        # RooFit.md 3.2: the info names _hashThresh and no slots.
        info = next(i for i in self.infos if i.name == "RooLinkedList")
        self.assertEqual([e.name for e in info.elements],
                         ["TObject", "_hashThresh", "_size", "_name"])
        _, value = self.decoded("l")
        self.assertEqual([m.name for m in value.members],
                         ["TObject", "_size", "element", "element", "_name"])

    def test_the_two_wrong_prefixes_are_the_same_length(self):
        # RooFit.md 3.2: the info's prefix is TObject + 4 + 4 = 18 bytes and the
        # real one is 2 + TObject + 4 = 16, so a reader that starts two bytes
        # early lands on _size at the right offset. That near-miss is why the
        # layout in issue #1 works while naming three fields that are not there.
        rec, value = self.decoded("l")
        start, _ = rootfile.payload_range(rec)
        size = next(m for m in value.members if m.name == "_size")
        self.assertEqual(size.start - start, 12)
        self.assertEqual(struct.unpack_from(">i", self.buf, size.start)[0], 2)
        # 2 (version) + 10 (TObject), and 10 (TObject) + 2 (the claimed Short_t)
        self.assertEqual(2 + 10, 10 + 2)

    def test_roorefarray_holds_a_trefarray_and_not_a_tobjarray(self):
        _, value = self.decoded("x")
        proxy = next(v for v in rootfile.walk(value)
                     if v.type_name == "RooRefArray")
        self.assertEqual([m.type_name for m in proxy.members], ["TRefArray"])
        self.assertEqual(proxy.members[0].end, proxy.end)

    def test_rooabsbinning_writes_a_tnamed_its_class_does_not_declare(self):
        _, value = self.decoded("x")
        binning = next(v for v in rootfile.walk(value)
                       if v.name == "RooAbsBinning")
        self.assertEqual([m.name for m in binning.members],
                         ["TNamed", "RooPrintable"])
        self.assertEqual(binning.members[1].end - binning.members[1].start, 6)


class CorruptionIsCaught(unittest.TestCase):
    """One patch per invariant of §7."""

    def test_7_1_a_roorealvar_byte_count_that_does_not_cover_the_tail(self):
        # Shorten the frame so it ends where the streamer-info-described
        # members do -- which is what issue #1 item 8 describes as the real
        # layout, and what the bytes do not do.
        bad = failures(patched(RRV_BYTE_COUNT, 0x40000000 | 380))
        self.assertIn("RooFit 7.1", labels(bad))

    def test_7_2_a_negative_size(self):
        bad = failures(patched(LIST_SIZE, 0xFFFFFFFF))
        self.assertIn("RooFit 7.2", labels(bad))
        self.assertTrue(any("_size" in line for line in bad), bad)

    def test_7_2_one_slot_too_many_runs_past_the_record(self):
        bad = failures(patched(LIST_SIZE, 3))
        self.assertIn("RooFit 7.2", labels(bad))

    def test_7_3_a_roorefarray_that_does_not_end_where_its_trefarray_does(self):
        bad = failures(patched(PROXY_BYTE_COUNT, 0x40000000 | 33))
        self.assertIn("RooFit 7.3", labels(bad))

    def test_7_4_a_rooabsbinning_whose_frame_does_not_hold_the_two_bases(self):
        bad = failures(patched(BINNING_BYTE_COUNT, 0x40000000 | 24))
        self.assertIn("RooFit 7.4", labels(bad))

    def test_7_5_a_roolinkedlist_info_without_hashthresh(self):
        # The StreamerInfo record is uncompressed, so renaming the element is a
        # byte patch. Only the element's own name is changed; the info's claim
        # that the member exists is what invariant 5 is about.
        buf = bytearray(FIXTURE.read_bytes())
        name = b"\x0b_hashThresh"
        at = buf.index(name)
        self.assertEqual(buf.count(name), 1)
        buf[at + 1:at + 2] = b"X"          # _hashThresh -> XhashThresh
        bad = failures(bytes(buf))
        self.assertIn("RooFit 7.5", labels(bad))


if __name__ == "__main__":
    unittest.main()
