#!/usr/bin/env python3
"""Fetch the third-party ROOT files that `coverage_probe.py` measures against.

These are **not** reference files. `data/` holds files this project wrote and
asserts byte for byte; these are files written by other people and other ROOT
releases, and their only job is to answer "is the specification enough for a file
nobody designed around it?". They are not committed -- `gen/foreign/MANIFEST.sha256`
records what was used, so a run can be reproduced.

The source is scikit-hep-testdata, which is uproot's regression corpus. That is a
deliberate choice: it spans ROOT 4.00 to 6.30 on purpose, including a sweep of
`uproot-sample-<version>` files in four codecs, which is the closest thing to the
legacy corpus `gen/legacy/` was meant to provide.

  tools/fetch_foreign.py                 fetch everything in the manifest
  tools/fetch_foreign.py --check         verify what is already downloaded
  tools/fetch_foreign.py --dir DIR       somewhere other than the default

**Their provenance is mixed.** uproot's corpus contains files uproot itself wrote,
so a file failing an invariant is not evidence about ROOT's format until its writer
is established. See `PLAN.md` §9.8.

A manifest name with a `<source>/` prefix comes from another corpus in `SOURCES`,
pinned to a commit, and lands in the same directory under its bare name. The first
is go-hep's `groot/testdata`, whose files are written by ROOT from macros committed
beside them (`PLAN-corpus.md` C9).
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "gen/foreign/MANIFEST.sha256"
BASE = ("https://raw.githubusercontent.com/scikit-hep/scikit-hep-testdata/"
        "main/src/skhep_testdata/data/")
#: Other corpora, each pinned to a commit so a manifest digest stays meaningful.
SOURCES = {
    "go-hep": ("https://codeberg.org/go-hep/hep/raw/commit/"
               "8d0fccd8a3b52da108d9f446122ba494b240d6fa/groot/testdata/"),
}
DEFAULT_DIR = REPO / "build/foreign"


def url(name: str) -> str:
    """Where a manifest name is fetched from."""
    source, _, bare = name.rpartition("/")
    return SOURCES[source] + bare if source else BASE + name


def entries() -> list[tuple[str, int, str]]:
    out = []
    for line in MANIFEST.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        digest, size, _version, name = line.split(None, 3)
        out.append((digest, int(size), name.strip()))
    return out


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    target = DEFAULT_DIR
    if "--dir" in argv:
        target = Path(argv[argv.index("--dir") + 1])
    target.mkdir(parents=True, exist_ok=True)

    bad = missing = fetched = 0
    for digest, size, name in entries():
        path = target / name.rsplit("/", 1)[-1]
        if not path.exists():
            if check_only:
                missing += 1
                continue
            urllib.request.urlretrieve(url(name), path)
            fetched += 1
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != digest:
            print(f"DIGEST {name}: manifest {digest}, file {got}", file=sys.stderr)
            bad += 1
    print(f"{len(entries())} file(s) in the manifest, {fetched} fetched, "
          f"{missing} missing, {bad} with the wrong digest -> {target}")
    return 1 if bad or (check_only and missing) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
