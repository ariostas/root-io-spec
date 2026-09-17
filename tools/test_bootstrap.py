#!/usr/bin/env python3
"""spec/99-appendix/Bootstrap.md against tools/rootfile.py.

Two lists are compared: the classes whose `Streamer` is hand-written
(`CUSTOM_STREAMER`) and the classes whose generated `Streamer` writes only their
bases (`FORWARDING_STREAMER`). A reader has to carry both, for opposite reasons,
and the document has to name both.

The appendix lists the classes a reader must hardcode, and rootfile.py is a
reader that hardcodes them. A list like that rots quietly: the reader learns
about a divergent class and the document does not, or the document names one the
reader never special-cased. Neither shows up as a failing fixture, so it is
checked here instead.

The check is by class name, in both directions, with the groupings the document
uses stated explicitly rather than pattern-matched.
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rootfile  # noqa: E402

DOC = Path(__file__).resolve().parent.parent / "spec" / "99-appendix" / "Bootstrap.md"

#: Rows of the document that stand for more than one class name, and what they
#: cover. Spelled out so that a new TArray or a new std::string spelling has to
#: be considered rather than silently absorbed by a wildcard.
COVERS = {
    "TArray*": set(rootfile.TARRAY_WIDTH),
    "std::string": set(rootfile.STD_STRING_NAMES),
}

#: Classes rootfile.py hardcodes that the document deliberately does not list as
#: rows of its own, with why.
NOT_ROWS = {
    # Named in section 3 as the eleven subclasses of TStreamerElement, which the
    # document gives as one row pointing at StreamerInfo.md section 8.
    *rootfile._ELEMENT_TAILS,
    # The abstract base. TArray* covers the concrete classes a file contains.
    "TArray",
    # The container's own; the document's row is "TFile, TDirectoryFile".
    "TDirectory",
}


def doc_classes() -> set[str]:
    """Every class named in the first column of the section 3 and 5 tables."""
    text = DOC.read_text()
    names: set[str] = set()
    for heading in ("\n## 3.", "\n## 5."):
        start = text.index(heading)
        end = text.index("\n## ", start + 1)
        for line in text[start:end].splitlines():
            if not line.startswith("| `"):
                continue
            cell = line.split("|")[1]
            for name in re.findall(r"`([^`]+)`", cell):
                names |= COVERS.get(name, {name})
    return names


def reader_classes() -> set[str]:
    """Every class tools/rootfile.py hardcodes rather than reading from an info."""
    import inspect
    dispatched = set(re.findall(r'cls == "([^"]+)"',
                                inspect.getsource(rootfile.Decoder.read_object)))
    return (set(rootfile.CUSTOM_STREAMER)
            | set(rootfile.FORWARDING_STREAMER)
            | set(rootfile.Decoder.SEQUENCES)
            | set(rootfile.TARRAY_WIDTH)
            | set(rootfile.STD_STRING_NAMES)
            | dispatched)


class BootstrapList(unittest.TestCase):
    """Bootstrap.md section 8: the two lists must not drift apart."""

    def test_the_document_names_every_class_the_reader_hardcodes(self):
        missing = reader_classes() - doc_classes() - NOT_ROWS
        self.assertEqual(missing, set(),
                         "hardcoded in tools/rootfile.py but not listed in "
                         "spec/99-appendix/Bootstrap.md")

    def test_the_reader_hardcodes_every_class_the_document_names(self):
        # TBasket, TTreeIndex, TStreamerInfo and the rest are read by named
        # functions rather than through Decoder.read_object, so they are
        # allowed here; what must not happen is a row naming a class nothing
        # anywhere in the reader knows about.
        source = (Path(rootfile.__file__)).read_text()
        for name in sorted(doc_classes()):
            with self.subTest(name):
                self.assertIn(name, source,
                              f"{name} is listed in Bootstrap.md and appears "
                              f"nowhere in tools/rootfile.py")

    def test_the_groupings_are_not_empty(self):
        # A typo in COVERS would make the first check vacuous for that row.
        for row, covered in COVERS.items():
            self.assertTrue(covered, row)


if __name__ == "__main__":
    unittest.main()
