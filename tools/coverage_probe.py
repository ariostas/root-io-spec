#!/usr/bin/env python3
"""Measure how much of a ROOT file the specification currently covers.

Reads every record of every file given, applies the streamer-driven read of
`spec/02-serialization/StreamerDriven.md` in tolerant mode, and reports what it
could not interpret and why. This is the complement to `check_invariants.py`:
that one asks whether the reference files satisfy the specification, this one asks
whether the specification is enough for a file nobody designed around it.

  tools/coverage_probe.py file.root [more.root ...]
  tools/coverage_probe.py --summary corpus/*.root     one line per file

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


def probe(path: Path, quiet: bool = False
          ) -> tuple[collections.Counter, collections.Counter]:
    """Returns (outcome tally, reason tally) for one file."""
    outcome: collections.Counter = collections.Counter()
    reasons: collections.Counter = collections.Counter()

    def show(line: str) -> None:
        if not quiet:
            print(line)

    buf, header, records = rootfile.load(path)

    infos: list = []
    for rec in records:
        if rec.free or not rec.key_len or rec.name != "StreamerInfo":
            continue
        try:
            infos = rootfile.read_streamer_infos(rootfile.object_data(buf, rec), rec)
        except (rootfile.FormatError, struct.error, IndexError,
                ValueError) as exc:
            reasons[f"StreamerInfo record unreadable: {exc}"] += 1
            show(f"  ! StreamerInfo record unreadable: {exc}")

    major, minor, patch = header.root_version
    show(f"{path}: {len(records)} records, {len(infos)} streamer infos, "
         f"written by ROOT {major}.{minor:02d}/{patch:02d}")
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
            show(f"{label} decoded (bootstrap reader)")
            continue
        if rec.class_name in CONTAINER:
            outcome["container"] += 1
            show(f"{label} container")
            continue
        try:
            data = rootfile.object_data(buf, rec)
        except rootfile.MissingCodec as exc:
            outcome["no codec"] += 1
            reasons[f"codec: {exc}"] += 1
            show(f"{label} NO CODEC  {exc}")
            continue
        start, end = rootfile.payload_range(rec)
        decoder = rootfile.Decoder(data, rec.offset, infos, tolerant=True)
        try:
            # A basket is not a serialized object; it has its own reader.
            if rec.class_name == "TBasket":
                value = rootfile.basket_value(buf, rec, data)
            else:
                value = decoder.read_object(rec.class_name, start)
        except (rootfile.FormatError, IndexError, ValueError, struct.error) as exc:
            outcome["blocked"] += 1
            reasons[str(exc)] += 1
            show(f"{label} BLOCKED   {exc}")
            continue
        if value.end != end:
            outcome["blocked"] += 1
            reasons[f"{rec.class_name}: consumed {value.end - start} of "
                    f"{end - start} bytes"] += 1
            show(f"{label} BLOCKED   consumed {value.end - start} of "
                 f"{end - start}")
            continue
        if decoder.unread:
            outcome["partial"] += 1
            for reason, _ in decoder.unread:
                reasons[reason] += 1
            show(f"{label} PARTIAL   {len(decoder.unread)} skipped: "
                 f"{'; '.join(sorted({r for r, _ in decoder.unread}))}")
        else:
            outcome["decoded"] += 1
            show(f"{label} decoded")
    return outcome, reasons


def version_of(path: Path) -> str:
    try:
        with open(path, "rb") as fh:
            header = rootfile.read_header(fh.read(512))
        major, minor, patch = header.root_version
        return f"{major}.{minor:02d}/{patch:02d}"
    except (rootfile.FormatError, struct.error, IndexError, ValueError, OSError):
        return "?"


def main(argv: list[str]) -> int:
    quiet = "--summary" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        raise SystemExit(__doc__)
    total: collections.Counter = collections.Counter()
    reasons: collections.Counter = collections.Counter()
    if quiet:
        print(f"{'file':44} {'ROOT':10} {'dec':>4} {'part':>5} {'blk':>4} "
              f"{'cont':>5} {'ncod':>5}")
    for arg in paths:
        path = Path(arg)
        try:
            o, r = probe(path, quiet)
        except (rootfile.FormatError, struct.error, IndexError, ValueError,
                OSError, RecursionError) as exc:
            # A file the container layer itself cannot walk. Worth knowing
            # about, and it must not stop the rest of the corpus.
            total["unreadable"] += 1
            reasons[f"file not walkable: {type(exc).__name__}: {exc}"] += 1
            print(f"{path.name[:44]:44} {version_of(path):10} "
                  f"UNREADABLE {exc}")
            continue
        total += o
        reasons += r
        if quiet:
            print(f"{path.name[:44]:44} {version_of(path):10} "
                  f"{o['decoded']:4} {o['partial']:5} {o['blocked']:4} "
                  f"{o['container']:5} {o['no codec']:5}")
        else:
            print()
    print("\noutcome")
    for key in ("container", "decoded", "partial", "blocked", "no codec",
                "unreadable"):
        if total[key]:
            print(f"  {total[key]:4}  {key}")
    if reasons:
        print("\nwhat is missing, by how often it blocks a record")
        for reason, n in reasons.most_common():
            print(f"  {n:4}  {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
