"""Three cycles of one key name, written by this project rather than by ROOT.

The write side of `spec/06-writing/WritingFiles.md` 8.1, and the counterpart of
`data/container/cycles.root`, which ROOT wrote from the same three calls. The two
file names are both 26 characters and the two titles both 17, because a key
carries each of them and a record carries its own offset -- one byte either way
and nothing would line up.

Writing a name that already exists does not replace anything. It adds a record,
and its key goes **in front of** the keys already under that name, taking the
first one's cycle plus one. The result is a key list in descending cycle order,
which is not decoration: ROOT's lookups take the first match and never compare
cycles.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402


def build() -> bytes:
    f = rw.FileWriter("data/written/cycles-3.root", "key cycle fixture")

    for i in (1, 2, 3):
        f.add(rw.Obj(class_name="TObjString", name="str",
                     title="Collectable string class",
                     payload=rw.tobjstring(f"revision {i}")))

    f.add_info(rw.objstring_info())
    return f.to_bytes()
