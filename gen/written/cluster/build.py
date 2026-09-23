"""A multi-basket TTree with cluster ranges, from spec/06-writing/WritingTrees.md.

It reproduces `data/ttree/clusters.root`: one `Int_t` branch, nineteen entries,
five baskets, and two closed cluster ranges. All five basket records and the
`TTree` record are byte-identical to ROOT's, keys included, once the wall-clock
timestamp is masked.

ROOT reached those boundaries by policy, from `SetAutoFlush(4)`, then 3, then 5,
with `TTree::Fill` flushing whenever the watermark divided the entry count. This
writer is told where the boundaries are, because when to flush is the writer's
choice and only its consequences are specified (`PLAN.md` 2.8). Two of ROOT's
policy values are inputs here for the same reason, and the records compare byte
for byte only because of them:

- `basket_size=512` at the first flush. ROOT rewrites every branch's
  `fBasketSize` there, through `OptimizeBaskets`, whose floor is 512, so the
  first basket records the 100 the caller asked for and the rest record 512
  (`WritingTrees.md` 7.3).
- `auto_save=3703700`, which ROOT computed at the same moment from the bytes it
  had written: `4 * ((300000000 / 81) / 4)`, the largest multiple of `fAutoFlush`
  whose share of the file stays under the requested watermark (§7.5).

The file's name and title are chosen so the comparison is possible:
`len("data/written/cluster.root") + len("cluster range")` equals
`len("data/ttree/clusters.root") + len("cluster ranges")`, and both strings appear
twice in the root directory record, so it is the same length in both files and
every offset after it lines up. A branch stores its baskets' offsets, so one
byte of drift would change the `TTree` record.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402

#: The entry at which each basket was closed, and the cluster size in force.
#: ROOT's SetAutoFlush(4) / (3) / (5) produced exactly this.
FLUSHES = ((4, 4), (8, 4), (11, 3), (14, 3), (19, 5))


def build() -> bytes:
    f = rw.FileWriter("data/written/cluster.root", "cluster range")

    tree = rw.Tree("t", "a tree", auto_flush=4, auto_save=3703700)
    tree.branch("x", "I", basket_size=100)

    entry = 0
    for i, (upto, size) in enumerate(FLUSHES):
        # The watermark changes before the entries of the new range, and
        # changing it closes the previous range (WritingTrees.md 7.4).
        tree.set_auto_flush(size)
        while entry < upto:
            tree.fill({"x": entry})
            entry += 1
        # OptimizeBaskets runs at the first automatic flush and at no other.
        tree.flush(basket_size=512 if i == 0 else None)

    for record in tree.records():
        f.add(record)
    for info in rw.tree_infos(("I",)):
        f.add_info(info)
    return f.to_bytes()
