"""A file this project wrote, closed, and then reopened and added to.

The write side of `spec/06-writing/WritingFiles.md` 13, and the counterpart of
`data/container/reopened.root`, which ROOT produced from the same sequence of
operations. The two file names are deliberately the same length, 28 characters,
because four records store the file's name and two store its offsets, so a name
one byte longer would shift the whole file and make the comparison useless.

The base is built here rather than read from `data/written/`, which makes the
check stronger: the base's bytes are `FileWriter.reopen`'s only input, so if the
two files agree then this writer reopened a file byte-identical to ROOT's and
reached ROOT's result from it.

Three writes follow the reopen, one for each way ROOT can write a name that may
already exist: plain under a new name, plain under an existing one, and
`WriteDelete`, which allocates before it frees and therefore advances the cycle.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402

NAME = "data/written/reopen-add.root"


def objstring(name: str, text: str) -> rw.Obj:
    return rw.Obj(class_name="TObjString", name=name,
                  title="Collectable string class", payload=rw.tobjstring(text))


def build() -> bytes:
    base = rw.FileWriter(NAME, "a file to reopen")
    base.add(objstring("str", "first"))
    base.add_info(rw.objstring_info())

    f = rw.FileWriter.reopen(base.to_bytes(), NAME)

    # A name new to the file: appended, cycle 1.
    f.add(objstring("two", "a name new to the file"))

    # The same name again: a second record, its key in front of the first.
    f.add(objstring("str", "the same name, a second cycle"))

    # WriteDelete: written first, freed afterwards, so the new record cannot
    # land on the old one and the cycle advances (13.5).
    f.write_delete(objstring("two", "written, and then the old one freed"))
    return f.to_bytes()
