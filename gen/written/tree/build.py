"""A flat TTree written by this project, from spec/06-writing/WritingTrees.md.

It reproduces `data/ttree/basket.root`: one `Int_t` branch and one counted
`Float_t` array, three entries, one basket each. Both basket records and the
`TTree` record are byte-identical to ROOT's, keys included, once the wall-clock
timestamp is masked.

The file's name and title are chosen to make the comparison possible. Both paths
are 22 characters, so the root directory record is the same length in both files
and every offset after it lines up. A branch stores its baskets' offsets, so a
shift of one byte would change the `TTree` record. `tools/test_write.py` asserts
the comparison.

Only the `StreamerInfo` record differs, by one entry: ROOT appends a
`listOfRules` holding two I/O customization rules for `TTree` versions <= 16 and
<= 18. A file written at version 20 cannot use them (`WritingTrees.md` 8.1).
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402


def build() -> bytes:
    f = rw.FileWriter("data/written/tree.root", "basket layouts")

    tree = rw.Tree("t", "a tree")
    n = tree.branch("n", "I")
    tree.branch("a", "F", counter=n)
    for i in range(3):
        tree.fill({"n": i + 1, "a": [float(i)] * (i + 1)})

    for record in tree.records():
        f.add(record)
    for info in rw.tree_infos(("I", "F")):
        f.add_info(info)
    return f.to_bytes()
