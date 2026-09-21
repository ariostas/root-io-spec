#!/usr/bin/env python3
"""Tests for spec/01-container/.

The byte-level checks live in check_invariants.py and run against the reference
files. These cover what a fixture cannot: a record whose payload is *longer* than
fObjlen, which no file this project writes contains, and a free list mixing the
10-byte and 18-byte TFree forms, which needs a file over 2 GB.
"""

import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_invariants  # noqa: E402
import rootfile  # noqa: E402


def record(nbytes: int, key_len: int, obj_len: int) -> rootfile.Record:
    return rootfile.Record(
        offset=0, nbytes=nbytes, key_version=4, obj_len=obj_len, datime=0,
        key_len=key_len, cycle=1, seek_key=0, seek_pdir=0,
        class_name="RBlob", name="", title="")


class CompressedTest(unittest.TestCase):
    """Compression.md 1.1. The test is `fObjlen > fNbytes - fKeylen`."""

    def test_a_shorter_payload_is_compressed(self):
        rec = record(nbytes=100, key_len=40, obj_len=200)   # payload 60 < 200
        self.assertTrue(rec.compressed)
        self.assertTrue(rootfile.is_compressed(rec))

    def test_an_exact_payload_is_raw(self):
        rec = record(nbytes=100, key_len=40, obj_len=60)
        self.assertFalse(rec.compressed)
        self.assertFalse(rootfile.is_compressed(rec))

    def test_a_longer_payload_is_raw(self):
        # The case the `!=` form got wrong. RNTuple.root's RBlob at offset 586:
        # fNbytes 789, fKeylen 34, fObjlen 723, so a 755-byte payload holding 723
        # bytes of object data. TFile::Map prints CX = 0.96 and TKey reads it raw.
        rec = record(nbytes=789, key_len=34, obj_len=723)
        self.assertEqual(rec.payload_nbytes, 755)
        self.assertFalse(rec.compressed)
        self.assertFalse(rootfile.is_compressed(rec))

    def test_the_reader_takes_only_fobjlen_bytes(self):
        rec = record(nbytes=789, key_len=34, obj_len=723)
        self.assertEqual(rootfile.payload_range(rec), (34, 757))


def free_record(entries: list[tuple[int, int]]) -> tuple[bytes, int, int]:
    """A synthetic free-segment record payload: (chunk, key_len, payload_nbytes).

    Each entry takes the large form when fLast exceeds 2000000000, exactly as
    TFree::FillBuffer decides (FreeSegments.md 2.1).
    """
    key_len = 8
    body = b""
    for first, last in entries:
        if last > 2000000000:
            body += struct.pack(">hqq", 1001, first, last)
        else:
            body += struct.pack(">hii", 1, first, last)
    return b"\x00" * key_len + body, key_len, len(body)


class FreeList(unittest.TestCase):
    """FreeSegments.md 2 and 2.1."""

    def roundtrip(self, entries):
        chunk, key_len, nbytes = free_record(entries)
        return rootfile.parse_free_list(chunk, key_len, nbytes)

    def test_all_small(self):
        entries = [(100, 200), (5000, 9999), (1338275841, 2000000000)]
        self.assertEqual(self.roundtrip(entries), entries)

    def test_all_large(self):
        entries = [(4947894760, 5000000000)]
        self.assertEqual(self.roundtrip(entries), entries)

    def test_the_two_forms_interleave(self):
        # volume.root's shape: 5.3 GB with both forms in one record. A reader that
        # sizes entries from the record rather than from each version word loses
        # sync at the first transition.
        entries = [(100, 200),                    # 10 bytes
                   (3000000000, 3000000100),      # 18 bytes
                   (400, 500),                    # 10 bytes
                   (5253395573, 6000000000)]      # 18 bytes
        self.assertEqual(self.roundtrip(entries), entries)

    def test_the_boundary_is_strictly_greater(self):
        # fLast exactly 2000000000 still fits the small form.
        chunk, key_len, nbytes = free_record([(0, 2000000000)])
        self.assertEqual(nbytes, 10)
        self.assertEqual(rootfile.parse_free_list(chunk, key_len, nbytes),
                         [(0, 2000000000)])

    def test_a_truncated_tail_is_not_a_spurious_entry(self):
        # WriteFree may zero-fill the tail of the payload (FreeSegments.md 3), and
        # a partial entry must be dropped rather than parsed.
        chunk, key_len, nbytes = free_record([(100, 200)])
        self.assertEqual(rootfile.parse_free_list(chunk + b"\x00" * 6,
                                                 key_len, nbytes + 6),
                         [(100, 200)])

    def test_an_empty_payload(self):
        self.assertEqual(rootfile.parse_free_list(b"\x00" * 8, 8, 0), [])


class LegacyCodec(unittest.TestCase):
    """Compression.md 3.1. `CS` is raw DEFLATE; `ZL` is zlib-wrapped."""

    PAYLOAD = b"ROOT" * 64

    def test_a_cs_block_is_raw_deflate(self):
        import zlib
        raw = zlib.compressobj(6, zlib.DEFLATED, -zlib.MAX_WBITS)
        block = raw.compress(self.PAYLOAD) + raw.flush()
        self.assertEqual(rootfile._legacy(block, len(self.PAYLOAD)), self.PAYLOAD)

    def test_a_zlib_stream_is_not_a_cs_block(self):
        # The wrapper is the whole difference: feeding a ZL block to the CS
        # decoder must fail rather than quietly return the wrong bytes.
        import zlib
        with self.assertRaises(zlib.error):
            rootfile._legacy(zlib.compress(self.PAYLOAD), len(self.PAYLOAD))

    def test_the_two_codecs_are_registered_with_method_byte_8(self):
        for magic in (b"ZL", b"CS"):
            self.assertEqual(rootfile.CODECS[magic][0], 8, magic)

    def test_a_cs_block_no_longer_raises_missingcodec(self):
        import zlib
        raw = zlib.compressobj(6, zlib.DEFLATED, -zlib.MAX_WBITS)
        block = raw.compress(b"x" * 300) + raw.flush()
        self.assertEqual(len(rootfile.CODECS[b"CS"][1](block, 300)), 300)


class EntrySample(unittest.TestCase):
    """check_invariants' entry sampling: it must keep both ends."""

    def checker(self, all_entries=False):
        c = check_invariants.Checker.__new__(check_invariants.Checker)
        c.all_entries = all_entries
        c.sampled = 0
        return c

    def test_a_small_basket_is_exhaustive(self):
        c = self.checker()
        n = check_invariants.Checker.ENTRY_SAMPLE_ABOVE
        self.assertEqual(c.entry_sample(n), list(range(n)))
        self.assertEqual(c.sampled, 0)

    def test_a_large_basket_is_sampled_and_says_so(self):
        c = self.checker()
        picked = c.entry_sample(10000)
        self.assertEqual(c.sampled, 1)
        self.assertLess(len(picked), 200)
        self.assertEqual(picked, sorted(set(picked)))

    def test_both_ends_survive_sampling(self):
        c = self.checker()
        ends = check_invariants.Checker.ENTRY_SAMPLE_ENDS
        picked = set(c.entry_sample(10000))
        self.assertTrue(set(range(ends)) <= picked)
        self.assertTrue(set(range(10000 - ends, 10000)) <= picked)

    def test_all_entries_disables_sampling(self):
        c = self.checker(all_entries=True)
        self.assertEqual(c.entry_sample(10000), list(range(10000)))
        self.assertEqual(c.sampled, 0)

    def test_every_index_is_in_range(self):
        c = self.checker()
        for n in (257, 1000, 42549):
            picked = c.entry_sample(n)
            self.assertTrue(all(0 <= e < n for e in picked), n)


class HeaderFitsBeforeTheFirstRecord(unittest.TestCase):
    """FileHeader 10.11, which is the invariant form of a hazard in ROOT.

    `TFile::WriteHeader` allocates `fBEGIN` bytes and writes however many the
    layout produced -- 63 small, 75 large (`root/io/io/src/TFile.cxx:2674`,
    `:2709`). Files with `fBEGIN` of 64 exist: four in the corpora, the oldest
    from ROOT 2.24/00. Pushing one of those past 2 GB would write over its own
    first record, so the floor is worth stating even though no conforming file
    can exhibit the violation -- which is why it is provoked here rather than by
    corrupting a fixture, where moving `fBEGIN` destroys the record walk before
    the check is reached.
    """

    PATH = Path(__file__).resolve().parents[1] / "data/container/reopened.root"

    def failures(self, begin, large=False):
        c = check_invariants.Checker.__new__(check_invariants.Checker)
        c.path = self.PATH
        c.failures = []
        c.check_header_floor(begin, large)
        return c.failures

    def test_the_real_files_fbegin_passes(self):
        header = rootfile.read_header(self.PATH.read_bytes())
        self.assertEqual(header.begin, 100)
        self.assertEqual(self.failures(header.begin, header.large), [])

    def test_a_begin_below_the_small_header_fails(self):
        bad = self.failures(50)
        self.assertEqual(len(bad), 1)
        self.assertIn("63-byte header", bad[0])

    def test_sixty_four_passes_small_with_one_byte_to_spare(self):
        """The four corpus files at fBEGIN 64 are legal, and only just."""
        self.assertEqual(self.failures(64), [])

    def test_sixty_four_fails_the_moment_the_file_goes_large(self):
        """The hazard itself: the same file pushed past 2 GB."""
        bad = self.failures(64, large=True)
        self.assertEqual(len(bad), 1)
        self.assertIn("75-byte header", bad[0])

SENTINEL = bytes(range(0x70, 0x90))
UUID = bytes(range(16))


def directory_record(version: int, uuid: bytes = b"",
                     *, offset: int = 100) -> tuple[bytes, rootfile.Record]:
    """A synthetic directory record, framed as `TDirectoryFile::Streamer` writes it.

    The two axes are independent: `version > 1000` widens the three offsets, and
    `version % 1000` decides whether a UUID follows and how -- absent at 1, raw
    16 bytes at 2, a version word first from 3 (Directory.md 7). The payload is
    followed by a sentinel standing in for the next record, so a reader that runs
    past the end of a UUID-less record picks up something recognisable.
    """
    large, class_version = version > 1000, version % 1000
    key_len = 40                            # a subdirectory: fNbytesName == fKeylen
    body = struct.pack(">hIIii", version, 1, 2, 0, key_len)
    body += (struct.pack(">qqq", offset, 0, 900) if large
             else struct.pack(">iii", offset, 0, 900))
    if class_version == 2:
        body += uuid
    elif class_version > 2:
        body += struct.pack(">h", 1) + uuid
    if class_version >= 4 and not large:
        body += b"\0" * 12                  # reserved, small layout only (5)
    buf = b"\0" * offset + b"K" * key_len + body + SENTINEL
    rec = rootfile.Record(
        offset=offset, nbytes=key_len + len(body), key_version=4,
        obj_len=len(body), datime=0, key_len=key_len, cycle=1,
        seek_key=offset, seek_pdir=0, class_name="TDirectory",
        name="alpha", title="alpha")
    return buf, rec


class DirectoryVersionAndOffsetWidthAreIndependent(unittest.TestCase):
    """R1: a version-1001 record is class version 1 in the wide layout.

    `rootfile.read_directory` used to decide the offset width from
    `version > 1000` and the UUID's presence from `version > 1`, so for 1001 both
    tests passed and it invented a UUID out of the bytes after the record. No
    fixture can cover this and no invariant compared a directory's UUID with
    anything, which is why it survived; the corpus cases below are the pin.
    """

    def parse(self, version, uuid=b""):
        buf, rec = directory_record(version, uuid)
        directory = rootfile.read_directory(buf, rec)
        self.assertIsNotNone(directory)
        self.buf = buf
        return directory, rec

    def test_version_1_has_no_uuid_and_a_30_byte_payload(self):
        directory, rec = self.parse(1)
        self.assertEqual(directory.uuid, b"")
        self.assertEqual(rec.obj_len, 30)

    def test_version_1001_has_no_uuid_either_and_42_bytes(self):
        directory, rec = self.parse(1001)
        self.assertEqual(directory.uuid, b"")
        self.assertEqual(rec.obj_len, 42)
        self.assertEqual(directory.seek_keys, 900)      # the wide layout is used
        self.assertEqual(directory.uuid_offset, rec.payload_offset + rec.obj_len)
        # The bug's signature: what the old test returned instead was these
        # sixteen bytes, which belong to the record after this one.
        self.assertEqual(self.buf[directory.uuid_offset:
                                  directory.uuid_offset + 16], SENTINEL[:16])

    def test_version_2_stores_the_uuid_with_no_version_word(self):
        directory, rec = self.parse(2, UUID)
        self.assertEqual(directory.uuid, UUID)
        self.assertEqual(directory.uuid_offset, directory.fields_offset + 30)
        self.assertEqual(rec.obj_len, 46)

    def test_version_3_puts_a_version_word_first(self):
        directory, rec = self.parse(3, UUID)
        self.assertEqual(directory.uuid, UUID)
        self.assertEqual(directory.uuid_offset, directory.fields_offset + 32)
        self.assertEqual(rec.obj_len, 48)

    def test_version_5_is_version_3_plus_the_reserved_bytes(self):
        directory, rec = self.parse(5, UUID)
        self.assertEqual(directory.uuid, UUID)
        self.assertEqual(directory.uuid_offset, directory.fields_offset + 32)
        self.assertEqual(rec.obj_len, 60)

    def test_version_1005_widens_the_offsets_and_keeps_the_uuid(self):
        directory, rec = self.parse(1005, UUID)
        self.assertEqual(directory.uuid, UUID)
        self.assertEqual(directory.uuid_offset, directory.fields_offset + 44)
        self.assertEqual(directory.seek_keys, 900)
        self.assertEqual(rec.obj_len, 60)


class PayloadLengthFollowsBothAxes(unittest.TestCase):
    """Directory 9.15, and R4: the length is a function of version and width.

    `directory_payload_length` is the arithmetic of Directory.md 7.1; these pin
    every row of that table, including the four rows no file in either corpus
    witnesses, and the corruption below shows which axis each invariant guards.
    """

    def length(self, version, file_version=64004):
        return check_invariants.directory_payload_length(version, file_version)

    def test_the_measured_rows(self):
        self.assertEqual(self.length(1, 22400), 30)      # pippa.root, ROOT 2.24/00
        self.assertEqual(self.length(3, 30402), 48)      # mlpHiggs.root
        self.assertEqual(self.length(1001), 42)          # the two g4tools files
        self.assertEqual(self.length(5), 60)             # everything modern
        self.assertEqual(self.length(1005), 60)

    def test_the_arithmetic_rows(self):
        self.assertEqual(self.length(2, 30301), 46)
        self.assertEqual(self.length(1002), 58)
        self.assertEqual(self.length(1003), 60)
        self.assertEqual(self.length(1, 64004), 42)      # no reserved bytes when wide

    def test_the_reserved_bytes_are_never_in_the_wide_form(self):
        """So the wide column does not depend on the file version at all."""
        for version in (1001, 1002, 1003, 1005):
            self.assertEqual(self.length(version, 30402),
                             self.length(version, 64004), version)

    def test_the_small_form_gains_twelve_bytes_from_root_4(self):
        for version in (1, 2, 3, 5):
            self.assertEqual(self.length(version, 64004) - self.length(version, 30402),
                             12, version)


class ConfusingTheAxesIsCaught(unittest.TestCase):
    """The two axes fail two different invariants, which is worth knowing.

    A record that lies about its **class version** is off by the UUID's 16 or 18
    bytes and nothing else notices, so that needs invariant 15. A record that lies
    about its **width** is caught earlier and harder: the offsets read at the wrong
    width leave `fSeekDir` pointing somewhere other than the record, so it is not
    recognised as a directory at all.
    """

    PATH = Path(__file__).resolve().parents[1] / "data/container/directories.root"
    FIELDS = 246                # the root directory's fields, at fBEGIN + fNbytesName

    def failures(self, version):
        buf = bytearray(self.PATH.read_bytes())
        self.assertEqual(struct.unpack_from(">h", buf, self.FIELDS)[0], 5)
        struct.pack_into(">h", buf, self.FIELDS, version)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corrupt.root"
            path.write_bytes(bytes(buf))
            checker = check_invariants.Checker(path)
            checker.run()
            return checker.failures

    def test_the_fixture_itself_passes(self):
        checker = check_invariants.Checker(self.PATH)
        checker.run()
        self.assertEqual(checker.failures, [])

    def test_a_class_version_that_implies_no_uuid(self):
        bad = self.failures(1)
        self.assertEqual(len(bad), 1)
        self.assertIn("Directory 9.15", bad[0])
        self.assertIn("writes 42", bad[0])

    def test_a_width_lie_is_caught_before_9_15(self):
        bad = self.failures(1005)
        self.assertTrue(bad)
        self.assertFalse([f for f in bad if "9.15" in f])
        self.assertTrue(all("Record 8.6" in f for f in bad), bad)


CORPUS = Path(__file__).resolve().parents[1] / "build"


class LegacyDirectoryRecordsInTheCorpora(unittest.TestCase):
    """The measured witnesses for Directory.md 7's payload table.

    Not committed files -- `tools/fetch_cern.py` and `tools/fetch_foreign.py`
    fetch them -- so these skip when the corpus is absent. They are the reason R1
    is a fix and not a guess: the two version-1001 records are real, and the
    reader read a UUID from two bytes past the end of each.
    """

    def directories(self, name):
        path = CORPUS / name
        if not path.exists():
            self.skipTest(f"{path} not fetched")
        buf, header, records = rootfile.load(path)
        return buf, [(r, d) for r in records
                     if (d := rootfile.read_directory(buf, r)) is not None]

    def test_g4tools_writes_version_1001_with_no_uuid(self):
        for name, end in (("foreign/uproot-from-geant4.root", 202),
                          ("foreign/uproot-issue-250.root", 156)):
            with self.subTest(name):
                buf, found = self.directories(name)
                self.assertEqual(len(found), 1)
                rec, directory = found[0]
                self.assertEqual(directory.version, 1001)
                self.assertEqual(rec.offset, 64)
                self.assertEqual(rec.offset + rec.nbytes, end)
                self.assertEqual(directory.uuid, b"")
                # 2 + 4 + 4 + 4 + 4 + 3*8, and nothing after it.
                self.assertEqual(directory.fields_offset + 42, end)
                self.assertEqual(directory.uuid_offset, end)

    def test_root_2_writes_version_1(self):
        buf, found = self.directories("cern/pippa.root")
        self.assertEqual(rootfile.read_header(buf).version, 22400)
        self.assertEqual(len(found), 24)
        self.assertEqual({d.version for _, d in found}, {1})
        self.assertEqual({d.uuid for _, d in found}, {b""})
        # 23 subdirectories at exactly the 30 bytes of the version-1 payload;
        # the root directory's record adds the name and title copy.
        self.assertEqual(sorted(r.obj_len for r, _ in found)[:23], [30] * 23)

    def test_root_3_04_and_3_05_write_version_3(self):
        for name, version in (("cern/mlpHiggs.root", 30402),
                              ("cern/H1display.root", 30507)):
            with self.subTest(name):
                buf, found = self.directories(name)
                self.assertEqual(rootfile.read_header(buf).version, version)
                rec, directory = found[0]
                self.assertEqual(directory.version, 3)
                self.assertEqual(directory.uuid_offset,
                                 directory.fields_offset + 32)
                # 48 bytes of payload after the name and title copy, and no
                # reserved bytes: those arrive with version 4.
                self.assertEqual(rec.obj_len - (directory.nbytes_name
                                                - rec.key_len), 48)


if __name__ == "__main__":
    unittest.main()
