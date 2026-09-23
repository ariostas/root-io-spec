"""The smallest complete file: one object, written by tools/rootwrite.py.

Every record a ROOT file must have and nothing else: the header, the root
directory record, one data record, the key list and the free list. There is no
`StreamerInfo` record, which is legal (`FileHeader.md` invariant 8);
`spec/06-writing/WritingFiles.md` 8 measures the consequences.

The name is passed as the repo-relative path for the same reason
`tools/generate.py` does it: a key stores the file's name, so an absolute path
would bake this checkout's location into the reference file.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402


def build() -> bytes:
    f = rw.FileWriter("data/written/objstring.root",
                      "written by tools/rootwrite.py")
    f.add(rw.Obj("TObjString", "str", "Collectable string class",
                 rw.tobjstring("hello")))
    return f.to_bytes()
