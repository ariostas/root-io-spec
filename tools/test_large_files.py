#!/usr/bin/env python3
"""The invariants of spec/01-container/LargeFiles.md section 8.

They are checked over the network by `fetch_cern.py --headers`, against eight
files this repository cannot commit. These tests do the other half of the
discipline `CLAUDE.md` asks for: each invariant is shown to **catch** a
violation, using the measured reading of `volume.root` as the good case and one
mutation per invariant.
"""

import unittest

import fetch_cern
import rootfile

# volume.root, ROOT 5.19/03, as measured by --headers on 2026-09-17.
HEADER = rootfile.FileHeader(
    version=1051903, begin=100, end=5253395573, seek_free=105159358,
    nbytes_free=826, nfree=51, nbytes_name=72, units=8, compress=0,
    seek_info=105191774, nbytes_info=4488, uuid_version=1, uuid=b"\0" * 16,
    uuid_offset=59, large=True,
)
KEY = rootfile.Record(offset=105159358, nbytes=826, key_version=1004,
                      key_len=60, seek_key=105159358, seek_pdir=100,
                      pid_offset=0, class_name="TFile")
# 19 narrow entries, then 32 wide ones, the last of them the sentinel.
ENTRIES = ([(1, 105160184 + 10 * i, 105160184 + 10 * i + 4) for i in range(19)]
           + [(1001, 2101355722 + 10 * i, 2101355722 + 10 * i + 4)
              for i in range(31)]
           + [(1001, 5253395573, 6000000000)])


class Invariants(unittest.TestCase):
    def problems(self, header=None, key=None, entries=None):
        return fetch_cern.large_file_problems(header or HEADER, key or KEY,
                                              entries or ENTRIES)

    def test_the_measured_file_passes(self):
        self.assertEqual(self.problems(), [])
        self.assertEqual(len(ENTRIES), HEADER.nfree)

    def test_1_flag_without_the_size(self):
        import dataclasses
        small = dataclasses.replace(HEADER, version=51903)
        self.assertIn("8.1", " ".join(self.problems(header=small)))

    def test_2_nfree_disagrees_with_the_list(self):
        self.assertIn("8.2", " ".join(self.problems(entries=ENTRIES[:-1])))

    def test_3_the_last_entry_does_not_pass_fend(self):
        blunted = ENTRIES[:-1] + [(1001, 5253395573, 5253395573)]
        self.assertIn("8.3", " ".join(self.problems(entries=blunted)))

    def test_4_an_entry_whose_width_contradicts_its_flast(self):
        # A wide entry that ends below the threshold: ROOT would have written
        # it in ten bytes, so a reader sizing by fLast rather than by the
        # version word would desynchronise from here on.
        narrowed = [(1001, 100, 200)] + ENTRIES[1:]
        self.assertIn("8.4", " ".join(self.problems(entries=narrowed)))

    def test_4_the_other_direction(self):
        widened = [(1, 100, 3000000000)] + ENTRIES[1:]
        self.assertIn("8.4", " ".join(self.problems(entries=widened)))

    def test_5_an_interior_entry_past_fend(self):
        past = [(1001, 105160184, 6000000000)] + ENTRIES[1:]
        self.assertIn("8.5", " ".join(self.problems(entries=past)))

    def test_5_an_inverted_span(self):
        inverted = [(1, 500, 400)] + ENTRIES[1:]
        self.assertIn("8.5", " ".join(self.problems(entries=inverted)))

    def test_6_an_unmasked_fseekpdir(self):
        # What a reader that ignores the packed fPidOffset would compute.
        import dataclasses
        unmasked = dataclasses.replace(KEY, seek_pdir=(7 << 48) | 100)
        self.assertIn("8.6", " ".join(self.problems(key=unmasked)))

    def test_6_a_pid_offset_on_the_free_record(self):
        import dataclasses
        tagged = dataclasses.replace(KEY, pid_offset=3)
        self.assertIn("8.6", " ".join(self.problems(key=tagged)))

    def test_6_is_not_applied_to_a_narrow_key(self):
        import dataclasses
        narrow = dataclasses.replace(KEY, key_version=4, seek_pdir=999)
        self.assertEqual(self.problems(key=narrow), [])


class FreeEntryParsing(unittest.TestCase):
    """parse_free_entries sizes each entry from its own version word."""

    def test_widths_interleave(self):
        import struct
        payload = (struct.pack(">hii", 1, 10, 20)
                   + struct.pack(">hqq", 1001, 2100000000, 3000000000)
                   + struct.pack(">hii", 1, 30, 40))
        got = rootfile.parse_free_entries(b"K" * 8 + payload, 8, len(payload))
        self.assertEqual(got, [(1, 10, 20), (1001, 2100000000, 3000000000),
                               (1, 30, 40)])
        self.assertEqual(rootfile.parse_free_list(b"K" * 8 + payload, 8,
                                                  len(payload)),
                         [(10, 20), (2100000000, 3000000000), (30, 40)])


if __name__ == "__main__":
    unittest.main()
