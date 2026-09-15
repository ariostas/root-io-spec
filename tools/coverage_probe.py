#!/usr/bin/env python3
"""Measure how much of a ROOT file the specification currently covers.

Reads every record of every file given, applies the streamer-driven read of
`spec/02-serialization/StreamerDriven.md` in tolerant mode, and reports what it
could not interpret and why. This is the complement to `check_invariants.py`:
that one asks whether the reference files satisfy the specification, this one asks
whether the specification is enough for a file nobody designed around it.

  tools/coverage_probe.py file.root [more.root ...]

A record is one of:

  container   TFile/TDirectory bookkeeping, spec/01-container/
  decoded     read in full from the file's own streamer info
  partial     read, but one or more nested objects were skipped by byte count
  blocked     not readable at all

`blocked` and the classes behind `partial` are the working list for
spec/03-classes/ and spec/04-ttree/, in the order a real file needs them.
"""

from __future__ import annotations

import collections
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import rootfile  # noqa: E402

CONTAINER = {"TFile", "TDirectory", "TDirectoryFile"}


def probe(path: Path) -> tuple[collections.Counter, collections.Counter]:
    """Returns (outcome tally, reason tally) for one file."""
    outcome: collections.Counter = collections.Counter()
    reasons: collections.Counter = collections.Counter()
    buf, header, records = rootfile.load(path)

    infos: list = []
    for rec in records:
        if rec.free or not rec.key_len or rec.name != "StreamerInfo":
            continue
        try:
            infos = rootfile.read_streamer_infos(rootfile.object_data(buf, rec), rec)
        except rootfile.FormatError as exc:
            print(f"  ! StreamerInfo record unreadable: {exc}")

    print(f"{path}: {len(records)} records, {len(infos)} streamer infos")
    for rec in records:
        if rec.free or not rec.key_len:
            continue
        label = f"  {rec.class_name:16} {str(rec.name)[:20]:20}"
        if rec.name == "StreamerInfo" and rec.class_name == "TList":
            # Read above, by the dedicated reader of StreamerInfo.md. Routing it
            # through the generic decoder would report every TStreamerInfo entry
            # as unreadable, since a file does not describe its own bootstrap
            # classes.
            outcome["decoded"] += 1
            print(f"{label} decoded (bootstrap reader)")
            continue
        if rec.class_name in CONTAINER:
            outcome["container"] += 1
            print(f"{label} container")
            continue
        try:
            data = rootfile.object_data(buf, rec)
        except rootfile.MissingCodec as exc:
            outcome["no codec"] += 1
            reasons[f"codec: {exc}"] += 1
            print(f"{label} NO CODEC  {exc}")
            continue
        start, end = rootfile.payload_range(rec)
        decoder = rootfile.Decoder(data, rec.offset, infos, tolerant=True)
        try:
            value = decoder.read_object(rec.class_name, start)
        except (rootfile.FormatError, IndexError, ValueError, struct.error) as exc:
            outcome["blocked"] += 1
            reasons[str(exc)] += 1
            print(f"{label} BLOCKED   {exc}")
            continue
        if value.end != end:
            outcome["blocked"] += 1
            reasons[f"{rec.class_name}: consumed {value.end - start} of "
                    f"{end - start} bytes"] += 1
            print(f"{label} BLOCKED   consumed {value.end - start} of {end - start}")
            continue
        if decoder.unread:
            outcome["partial"] += 1
            for reason, _ in decoder.unread:
                reasons[reason] += 1
            print(f"{label} PARTIAL   {len(decoder.unread)} skipped: "
                  f"{'; '.join(sorted({r for r, _ in decoder.unread}))}")
        else:
            outcome["decoded"] += 1
            print(f"{label} decoded")
    return outcome, reasons


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit(__doc__)
    total: collections.Counter = collections.Counter()
    reasons: collections.Counter = collections.Counter()
    for arg in argv:
        o, r = probe(Path(arg))
        total += o
        reasons += r
        print()
    print("outcome")
    for key in ("container", "decoded", "partial", "blocked", "no codec"):
        if total[key]:
            print(f"  {total[key]:4}  {key}")
    if reasons:
        print("\nwhat is missing, by how often it blocks a record")
        for reason, n in reasons.most_common():
            print(f"  {n:4}  {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
