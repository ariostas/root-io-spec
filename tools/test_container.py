#!/usr/bin/env python3
"""Tests for spec/01-container/.

The byte-level checks live in check_invariants.py and run against the reference
files. These cover what a fixture cannot: a record whose payload is *longer* than
fObjlen, which no file this project writes contains, and a free list mixing the
10-byte and 18-byte TFree forms, which needs a file over 2 GB.
"""

import struct
import sys
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


if __name__ == "__main__":
    unittest.main()
