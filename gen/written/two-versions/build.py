"""One class at two versions in one file, with an object at each.

The write side of `spec/06-writing/WritingObjects.md` 8.4. No file in either
corpus has a class at two versions, and no single ROOT session produces one: a
session has one definition of a class. Two sessions do. Reopen a file with a
class that has since gained a member and ROOT writes both infos, which is the
measurement in 8.4. This case is that file, written in one pass by this project.

`Grown` is deliberately not derived from `TObject`. `TKey::ReadObj` streams a
`TObject`-derived object through `tobj->Streamer()`, which for a class ROOT has
no dictionary for dispatches to `TObject::Streamer`, reads ten bytes and stops.
ROOT then returns a default-constructed object and reports nothing about the
data it dropped. 8.7 has the measurement and the citations. A non-`TObject`
class takes the `ReadObjectAny` path instead and reads correctly, so `verify.C`
can check the values.

The base is built here and reopened, so the second info arrives the way it
does in practice: a file that already describes `Grown` at version 1 is opened
again by a writer whose `Grown` has a second member.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402

NAME = "data/written/two-versions.root"


def info(version: int) -> rw.Info:
    """`Grown` at `version`: `fA` always, `fB` from version 2."""
    elements = [rw.Element("TStreamerBasicType", "fA", "present at every version",
                           3, 4, "Int_t")]
    if version >= 2:
        elements.append(rw.Element("TStreamerBasicType", "fB",
                                   "added at version 2", 8, 8, "Double_t"))
    out = rw.Info("Grown", version, elements)
    out.checksum = rw.checksum(out)
    return out


def grown(name: str, version: int, a: int, b: float | None = None) -> rw.Obj:
    """One `Grown` record. The version word is what selects the layout."""
    body = rw.i32(a)
    if b is not None:
        body += rw.f64(b)
    return rw.Obj(class_name="Grown", name=name, title="",
                  payload=rw.framed(version, body))


def build() -> bytes:
    base = rw.FileWriter(NAME, "one class, two layouts")
    base.add(grown("first", 1, 11))
    base.add_info(info(1))

    # The reopen. The StreamerInfo record is rewritten because a class new to
    # the file is used; the same class at a new version counts
    # (WritingFiles.md 13.7). The list must hold both infos, because the record
    # is replaced rather than appended to.
    f = rw.FileWriter.reopen(base.to_bytes(), NAME)
    f.add(grown("second", 2, 22, 3.5))
    f.add_info(info(1))
    f.add_info(info(2))
    return f.to_bytes()
