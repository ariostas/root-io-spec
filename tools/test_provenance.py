#!/usr/bin/env python3
"""No third-party file is ever committed. LICENSE, "Third-party corpora".

The corpora this project measures itself against are read where they are --
`root/roottest/` inside the pinned submodule -- or fetched into `build/`, and
only manifests of their digests are committed. Two of the sources are under
LGPL-2.1, roottest and rntuple-validation, which the BSD-3-Clause licence of
`data/` could not carry; the others would muddy a provenance that the reference
files depend on. These tests are what makes the rule more than a sentence:

- every tracked ROOT file is the output of a case in this repository, so a file
  copied in from anywhere has no generator and fails;
- no tracked file is byte-identical to a file in `root/roottest/`, which catches
  a macro or a reference output copied in as well as a ROOT file.

rntuple-validation's files are not on disk to compare against, and the first
test is what covers them: none of them has a generator here.
"""

import hashlib
import subprocess
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOTTEST = REPO / "root" / "roottest"
HAVE_ROOTTEST = (ROOTTEST / "root").is_dir()

#: Below this, identical bytes say nothing about where a file came from.
MIN_SIZE = 64


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, check=True,
                         capture_output=True).stdout
    return [p for p in out.decode().split("\0") if p]


def generated() -> set[str]:
    """Every `file =` a case declares: gen/cases/ and gen/written/."""
    files = set()
    for case in REPO.glob("gen/*/**/case.toml"):
        declared = tomllib.loads(case.read_text()).get("file")
        if declared:
            files.add(declared)
    return files


@unittest.skipUnless((REPO / ".git").exists(), "not a git checkout")
class NothingThirdParty(unittest.TestCase):

    def test_every_tracked_root_file_has_a_case(self):
        roots = {p for p in tracked() if p.endswith(".root")}
        self.assertTrue(roots, "no tracked .root file at all")
        self.assertEqual(sorted(roots - generated()), [],
                         "tracked ROOT files with no case that generates them")

    def test_every_case_file_is_tracked(self):
        # The converse, so that the set above is not trivially a superset.
        self.assertEqual(sorted(generated() - set(tracked())), [])

    @unittest.skipUnless(HAVE_ROOTTEST, "root/ submodule is not checked out")
    def test_no_tracked_file_is_a_roottest_file(self):
        digests = {}
        for path in ROOTTEST.rglob("*"):
            if path.is_file() and not path.is_symlink():
                data = path.read_bytes()
                if len(data) >= MIN_SIZE:
                    digests[hashlib.sha256(data).hexdigest()] = path
        self.assertGreater(len(digests), 1000, "roottest looks empty")
        copies = []
        for name in tracked():
            path = REPO / name
            if name == "root" or not path.is_file():
                continue
            data = path.read_bytes()
            if len(data) >= MIN_SIZE:
                twin = digests.get(hashlib.sha256(data).hexdigest())
                if twin is not None:
                    copies.append(f"{name} = {twin.relative_to(REPO)}")
        self.assertEqual(copies, [], "committed copies of roottest files")


if __name__ == "__main__":
    unittest.main()
