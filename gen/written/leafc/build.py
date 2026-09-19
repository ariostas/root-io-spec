"""A `TLeafC` branch written by this project, from `WritingTrees.md` 4.5.

It reproduces `data/ttree/strings.root` -- one `Int_t` branch and one C-string
branch, three entries, one basket each -- and it reproduces it *exactly*: both
basket records and the `TTree` record are byte-identical to ROOT's, keys
included, once the fixed timestamp is masked.

Both paths are 23 characters, which is what makes that possible: a branch stores
its baskets' **offsets**, so a one-byte shift anywhere before them would change
the `TTree` record.

The three strings are the three cases: the short counted form, an **empty** one
that occupies no bytes at all, and one long enough to need the 255-escape. The
empty one is in the middle, so the offset array has two equal entries in it.

Only the `StreamerInfo` record differs, by the one `listOfRules` entry ROOT
appends for `TTree` and a file written at version 20 cannot use
(`WritingTrees.md` 8.1).
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402

#: The three entries' strings, in order.
STRINGS = ("ab", "", "x" * 300)


def build() -> bytes:
    f = rw.FileWriter("data/written/leafc.root", "string leaves")

    tree = rw.Tree("t", "a tree")
    tree.branch("n", "I")
    tree.branch("s", "C")
    for i, text in enumerate(STRINGS):
        tree.fill({"n": i + 1, "s": text})

    for record in tree.records():
        f.add(record)
    for info in rw.tree_infos(("I", "C")):
        f.add_info(info)
    return f.to_bytes()
