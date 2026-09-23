"""A compressed record and a `StreamerInfo` record, both written by this project.

Exercises the second half of `spec/06-writing/WritingObjects.md`: the ZLIB block
header, the class map inside a record, and the `TList` of `TStreamerInfo` that
makes the file readable by something other than ROOT.

The `TObjString` payload is a repeating string so that it compresses. ROOT does
not attempt compression below 257 bytes and neither does `tools/rootwrite.py`.
The info for `TObjString` is the one ROOT itself records, checksum included, so
ROOT reads the file without a `BuildCheck` warning.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402

#: 600 bytes, and highly compressible.
TEXT = "hello " * 100


def build() -> bytes:
    f = rw.FileWriter("data/written/streamerinfo.root",
                      "written by tools/rootwrite.py",
                      compress=101)
    f.add(rw.Obj("TObjString", "str", "Collectable string class",
                 rw.tobjstring(TEXT)))
    f.add_info(rw.Info("TObjString", 1, [
        rw.Element("TStreamerBase", "TObject", "Basic ROOT object", 66, 0,
                   "BASE", base_version=1, base_checksum=0x901BC02D),
        rw.Element("TStreamerString", "fString", "wrapped TString", 65, 24,
                   "TString"),
    ]))
    return f.to_bytes()
