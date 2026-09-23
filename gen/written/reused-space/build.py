"""Records placed into free space, written by this project rather than by ROOT.

The write side of `spec/06-writing/WritingFiles.md` 2, and the counterpart of
`data/container/gap-reused.root`, which ROOT wrote from the same sequence of
operations. The two file names are deliberately the same length, 30 characters,
because a key stores the file's name and a record stores its own offset, so a
name one byte longer would shift every record and make the comparison useless.

Three placements, the three of 2.3:

* `exact` is written long, overwritten short, then overwritten long again. The
  last overwrite frees a span that coalesces back to exactly what it needs, so
  the free entry is removed and the record lands at its original offset;
* `snug` is written long and overwritten short, releasing 123 bytes;
* `lodger` is 104 bytes and takes the front of those 123, leaving a 19-byte
  remainder with its own negative `fNbytes`.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402

BIG = "0123456789abcdef" * 8          # 128 characters, as in gen.C


def objstring(name: str, text: str) -> rw.Obj:
    return rw.Obj(class_name="TObjString", name=name, title="Collectable string class",
                  payload=rw.tobjstring(text))


def build() -> bytes:
    f = rw.FileWriter("data/written/reused-space.root", "reused free space")

    f.add(objstring("exact", BIG))
    f.add(objstring("snug", BIG))
    f.add(objstring("tail", "a record after both, so neither is at the end of the file"))

    # exact: shrink, then restore. The restore frees the short record's 125
    # bytes, which coalesce with the 88 already free into the original 213:
    # an exact fit, so the entry disappears.
    f.overwrite(objstring("exact", "short"))
    f.overwrite(objstring("exact", BIG))

    # snug: shrink and leave the remainder on the free list.
    f.overwrite(objstring("snug", "short"))

    # A record of its own, small enough for what snug released.
    f.add(objstring("lodger", "inside snug's span"))

    f.add_info(rw.objstring_info())
    return f.to_bytes()
