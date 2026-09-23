#!/usr/bin/env python3
"""The invariants of spec/01-container/LargeFiles.md section 8.

They are checked over the network by `fetch_cern.py --headers`, against eleven
files this repository cannot commit. These tests do the other half of the
discipline `AGENTS.md` asks for: each invariant is shown to **catch** a
violation, using the measured reading of `volume.root` as the good case and one
mutation per invariant.
"""

import tomllib
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


# volume.root's top directory, as measured by --headers on 2026-09-23: a
# narrow record in a 5 GB file, because its three offsets are all small, and a
# key list whose own key and one image are wide.
DIRECTORY = rootfile.Directory(
    version=5, datime_c=0, datime_m=0, datime_offset=0, nbytes_keys=125,
    nbytes_name=72, seek_dir=100, seek_parent=0, seek_keys=105159233,
    uuid=b"", uuid_offset=0, fields_offset=0)
LIST_KEY = rootfile.Record(offset=105159233, nbytes=125, key_version=1004,
                           key_len=60, seek_key=105159233, seek_pdir=100,
                           pid_offset=0, class_name="TFile")
IMAGES = [rootfile.Record(offset=0, nbytes=0, key_version=1004, key_len=0,
                          seek_key=5252483583, seek_pdir=100, pid_offset=0,
                          name="volume", cycle=1)]


class TopDirectory(unittest.TestCase):
    """Invariants 6, on every wide key in reach, and 7, by the same method."""

    def problems(self, directory=None, list_key=None, images=None):
        return fetch_cern.top_directory_problems(
            HEADER, directory or DIRECTORY, list_key or LIST_KEY,
            IMAGES if images is None else images)

    def test_the_measured_file_passes(self):
        self.assertEqual(self.problems(), [])

    def test_7_a_wide_record_with_small_offsets(self):
        import dataclasses
        wide = dataclasses.replace(DIRECTORY, version=1005)
        self.assertIn("8.7", " ".join(self.problems(directory=wide)))

    def test_7_a_narrow_record_with_a_large_offset(self):
        import dataclasses
        far = dataclasses.replace(DIRECTORY, seek_keys=3000000000)
        self.assertIn("8.7", " ".join(self.problems(directory=far)))

    def test_6_an_unmasked_fseekpdir_on_a_key_image(self):
        import dataclasses
        unmasked = [dataclasses.replace(IMAGES[0], seek_pdir=(3 << 48) | 100)]
        self.assertIn("8.6", " ".join(self.problems(images=unmasked)))

    def test_6_a_pid_offset_on_the_key_list_key(self):
        import dataclasses
        pid = dataclasses.replace(LIST_KEY, pid_offset=1)
        self.assertIn("8.6", " ".join(self.problems(list_key=pid)))

    def test_6_is_not_applied_to_a_narrow_image(self):
        import dataclasses
        narrow = [dataclasses.replace(IMAGES[0], key_version=4, seek_pdir=7)]
        self.assertEqual(self.problems(images=narrow), [])


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


class WhereARowIsRead(unittest.TestCase):
    """LARGE.toml's `path` is under root.cern and `url` is absolute (C14)."""

    def test_path_is_under_root_cern(self):
        self.assertEqual(fetch_cern.large_url({"path": "volume.root"}),
                         "https://root.cern/files/volume.root")

    def test_url_is_taken_as_it_is(self):
        url = "https://opendata.cern.ch/eos/opendata/x/y.root"
        self.assertEqual(fetch_cern.large_url({"url": url}), url)

    def test_both_or_neither_is_an_error(self):
        for row in ({}, {"path": "a.root", "url": "https://b/a.root"}):
            with self.assertRaises(ValueError):
                fetch_cern.large_url(row)

    def test_every_row_resolves(self):
        rows = tomllib.loads(fetch_cern.LARGE.read_text())["file"]
        self.assertTrue(all(fetch_cern.large_url(r).startswith("https://")
                            for r in rows))


if __name__ == "__main__":
    unittest.main()
