#!/usr/bin/env python3
"""Keep spec/05-rntuple/ in sync with RNTuple's own documentation upstream.

RNTuple is the one ROOT format that already has a real specification, written and
maintained by the ROOT team. This project does not fork it. `spec/05-rntuple/`
holds a **verbatim tracked copy** of the upstream documents, and everything this
project has to say about them lives beside the copy in ERRATA.md and NOTES.md, so
the two are never confused.

  tools/sync_rntuple.py            re-copy from the submodule
  tools/sync_rntuple.py --check    fail if the tracked copy has drifted

Drift means one of two things and they need opposite responses: the submodule was
bumped and the copy is stale (re-run without --check, then re-audit the diff), or
someone edited the copy in place (revert it -- corrections go in ERRATA.md).

The copy is byte-identical, newline for newline. That is the point: a diff against
a new upstream revision is then exactly the set of changes to audit, and nothing
in it is ours.

UPSTREAM.md records which commit the copy came from, and this tool checks that it
names the commit `root/` is pinned to -- the same pin tools/check_pin.py holds
zensical.toml to. Without that, a stale copy and a stale provenance note would
agree with each other and look correct.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UPSTREAM_DIR = REPO / "root" / "tree" / "ntuple" / "doc"
TRACKED_DIR = REPO / "spec" / "05-rntuple"

# Upstream name -> tracked name. Only the format specification is tracked
# verbatim: the others are design and tuning documents rather than a description
# of the bytes, and NOTES.md cites them where they are relevant.
DOCUMENTS = {
    "BinaryFormatSpecification.md": "BinaryFormatSpecification.md",
}

PROVENANCE = TRACKED_DIR / "UPSTREAM.md"


def pinned_commit() -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD:root"], cwd=REPO,
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def recorded_commit() -> str | None:
    if not PROVENANCE.exists():
        return None
    match = re.search(r"\b([0-9a-f]{40})\b", PROVENANCE.read_text())
    return match.group(1) if match else None


def main(argv: list[str]) -> int:
    check = "--check" in argv
    if not UPSTREAM_DIR.is_dir():
        print("FAIL the root/ submodule is not checked out, so there is nothing "
              "to sync from", file=sys.stderr)
        return 1

    failures: list[str] = []
    for upstream_name, tracked_name in DOCUMENTS.items():
        source = UPSTREAM_DIR / upstream_name
        target = TRACKED_DIR / tracked_name
        if not source.exists():
            failures.append(f"{upstream_name} is not in the submodule at this "
                            f"commit; DOCUMENTS needs updating")
            continue
        want = source.read_bytes()
        if check:
            if not target.exists():
                failures.append(f"{tracked_name} is not tracked yet")
            elif target.read_bytes() != want:
                failures.append(
                    f"{tracked_name} has drifted from the submodule. Either the "
                    f"pin moved -- re-run without --check and audit the diff -- "
                    f"or the copy was edited in place, which it must not be")
        else:
            TRACKED_DIR.mkdir(parents=True, exist_ok=True)
            target.write_bytes(want)
            print(f"copied {upstream_name} -> "
                  f"{target.relative_to(REPO)} ({len(want)} bytes)")

    pinned = pinned_commit()
    recorded = recorded_commit()
    if recorded is None:
        failures.append(f"{PROVENANCE.relative_to(REPO)} does not record a "
                        f"40-character source commit")
    elif recorded != pinned:
        failures.append(f"{PROVENANCE.relative_to(REPO)} records {recorded} but "
                        f"root/ is pinned at {pinned}")

    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    if failures:
        return 1
    print(f"{len(DOCUMENTS)} upstream document(s) match the submodule at {pinned}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
