"""A file this project wrote, closed, and then reopened **into its own hole**.

The write side of `spec/06-writing/WritingFiles.md` 13.2, and the counterpart of
`data/container/reopen-gap.root`, which ROOT produced from the same sequence.
Both names are 30 characters, for the reason `reopen-add` gives.

The base leaves an interior `TFree` entry of 95 bytes behind: `big` is written
with a 120-character payload and overwritten with a short one. The update is
given nothing but the bytes, so the free list is the only thing that tells it
that hole exists -- and `fits` is 95 bytes, which fills it exactly and removes
the entry. `tail` is then overwritten in place, and `wide` fits nothing and is
appended.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402

NAME = "data/written/reopen-reuse.root"
BIG = ("0123456789abcdef" * 8)[:120]


def objstring(name: str, text: str) -> rw.Obj:
    return rw.Obj(class_name="TObjString", name=name,
                  title="Collectable string class", payload=rw.tobjstring(text))


def build() -> bytes:
    base = rw.FileWriter(NAME, "a hole to inherit")
    base.add(objstring("big", BIG))
    base.add(objstring("tail", "a record after it, so the hole is interior"))
    base.overwrite(objstring("big", "cut short, leaving a hole"))
    base.add_info(rw.objstring_info())

    f = rw.FileWriter.reopen(base.to_bytes(), NAME)

    # 95 bytes into 95 bytes: an exact fit, so the entry is removed (2.3).
    f.add(objstring("fits", "fills it up"))

    # overwrite frees before it allocates, so this lands at tail's own old
    # address and leaves a 13-byte remainder; the cycle stays 1 (13.5).
    f.overwrite(objstring("tail", "shorter than what it replaces"))

    # Nothing free is big enough for this one.
    f.add(objstring("wide", BIG))
    return f.to_bytes()
