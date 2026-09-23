"""Two nested subdirectories, written by `tools/rootwrite.py`.

The write side of `spec/06-writing/WritingFiles.md` 5 and the counterpart of the
reading-side fixture `gen/cases/container/directories`. It holds the same five
objects that fixture holds, in the same order, so that every record can be
compared byte for byte with the one ROOT wrote. That includes the subdirectory
records, and it is the only way to check `fNbytesName`, `fSeekParent` and the
in-place `fSeekKeys` against anything but this project's own reading of the
source.

Two choices exist only to make that comparison possible, and neither is a format
requirement:

* the file's name is 31 characters, as long as
  `data/container/directories.root`, so every record lands at the same offset.
  A directory record stores three offsets, so a shifted layout would differ in
  every field that matters;
* the title is the fixture's, because the root directory record repeats it and
  `fNbytesName` counts it.

After that only the three UUIDs differ, and they are free
(`spec/01-container/Directory.md` 4.5): `tools/test_write.py` asserts the rest of
the file is identical.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402

#: ROOT gives every directory its own random UUID. These are constant so the
#: file stays byte-reproducible, and distinct so the file has the property a
#: ROOT-written one has (`spec/01-container/Directory.md` 4.5).
UUID_ALPHA = bytes.fromhex("5ab0ffd1ab1e4000a000000000000001")
UUID_BETA = bytes.fromhex("5ab0ffd1ab1e4000a000000000000002")

#: TObjString's title comes from TObject::GetTitle, which returns the class
#: title, so a key ROOT writes for one stores this, not the string.
TITLE = "Collectable string class"


def build() -> bytes:
    f = rw.FileWriter("data/written/nested-subdir.root",
                      "nested directory fixture")
    f.add(rw.Obj("TObjString", "top", TITLE, rw.tobjstring("at top level")))

    alpha = f.mkdir("alpha", uuid=UUID_ALPHA)
    alpha.add(rw.Obj("TObjString", "in_alpha", TITLE,
                     rw.tobjstring("inside alpha")))

    beta = alpha.mkdir("beta", uuid=UUID_BETA)
    beta.add(rw.Obj("TObjString", "in_beta", TITLE,
                    rw.tobjstring("inside alpha/beta")))

    f.add_info(rw.objstring_info())
    return f.to_bytes()
