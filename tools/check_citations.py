#!/usr/bin/env python3
"""Verify every citation in `spec/`: source lines, and the files they measure.

`spec/00-conventions.md` §7 promises that citations refer to the pinned commit.
This checks that the promise holds: that each cited file exists in the submodule
and that each cited line number is within that file. It catches the failure mode
the convention is otherwise vulnerable to -- a citation that silently goes stale
when the submodule is bumped.

It also checks the other kind of citation, which went stale twice before anyone
noticed: a **file** the specification names as evidence must be a fixture in
`data/` or listed in a corpus manifest, so that `fetch_foreign.py` or
`fetch_cern.py` can fetch it and the measurement can be reproduced. On 2026-09-18
`aod_flushed.root` and `gallery.root` were cited and in no manifest; on 2026-09-21
so were the four `TGeoManager` files carrying `StreamerInfo.md` §9.2's whole
`fBaseVersion` table (`PLAN-review.md` §4.1). Both were fixed by hand. This is what
stops a third.

Requires the submodule to be checked out. Needs no third-party packages.

  tools/check_citations.py            check every document under spec/
  tools/check_citations.py <paths>    check specific files
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SUBMODULE = REPO / "root"

# Documents this project does not write and must not edit. `spec/05-rntuple/`
# holds a verbatim tracked copy of ROOT's own RNTuple specification; a citation
# inside it is upstream's text, so a stale one here would fail a check against a
# file nothing in this repository is allowed to change -- see
# spec/05-rntuple/UPSTREAM.md. tools/sync_rntuple.py is what keeps that file
# honest instead.
NOT_OURS = {REPO / "spec/05-rntuple/BinaryFormatSpecification.md"}

# Citations appear inside inline code spans; see tools/rootcite.py for the
# rendering side. Both must recognise the same shape.
CITATION = re.compile(
    r"`root/(?P<path>[A-Za-z0-9_./+-]+\.(?:cxx|cxx\.in|hxx|h|c|cpp|cu|py|js|mjs|md|txt|yml))"
    r"(?::(?P<line>\d+)(?:-(?P<end>\d+))?)?`"
)


def check(paths: list[Path]) -> list[str]:
    failures, count, lengths = [], 0, {}
    for doc in paths:
        for lineno, text in enumerate(doc.read_text().splitlines(), 1):
            for m in CITATION.finditer(text):
                count += 1
                rel = m["path"]
                try:
                    label = doc.relative_to(REPO)
                except ValueError:
                    label = doc
                where = f"{label}:{lineno}: root/{rel}"
                target = SUBMODULE / rel
                if not target.is_file():
                    failures.append(f"{where}: no such file in the submodule")
                    continue
                if not m["line"]:
                    continue
                if rel not in lengths:
                    lengths[rel] = sum(1 for _ in target.open("rb"))
                total = lengths[rel]
                for group in ("line", "end"):
                    if m[group] and int(m[group]) > total:
                        failures.append(
                            f"{where}: line {m[group]} is past end of file ({total} lines)")
    print(f"{count} citations checked across {len(paths)} document(s), "
          f"{len(failures)} failure(s)")
    return failures


#: The front pages quote the citation total, and it drifted three times in one
#: session of editing before this check existed. The number is cheap to verify and
#: a stale one undermines every other measurement beside it.
PUBLISHED = (
    ("README.md", r"(\d+) source citations"),
    ("spec/index.md", r"(\d+) source\ncitations"),
)


#: ROOT file names that appear in `spec/` and are deliberately not corpus files:
#: an illustration, a placeholder, a file an experiment wrote and threw away, or a
#: name quoted out of another file's header. Anything else must be fetchable.
NOT_CORPUS = {
    "your-file.root": "a placeholder in a command example",
    "map.root": "an illustration",
    "Muons.root": "an illustration",
    "base.root": "written and discarded by the update experiment of WritingFiles 13",
    "collide.root": "written and discarded by the version-collision experiment of WritingObjects 8.5",
    "noop.root": "written and discarded by the no-op update experiment of WritingFiles 13.9",
    "HcompassF_226Ra_run_2_20231117_085722.root":
        "the internal name uproot-issue-861.root carries in its own header, quoted",
    "uproot-issue243-new.root":
        "named by GitHub issue #1 as a fourth ROOT::TIOFeatures duplicate; it "
        "repeats a pattern two listed files already carry, so it is not in "
        "gen/foreign/ and SchemaEvolution.md 8.1 cites it as a report rather "
        "than as evidence",
}

ROOT_FILE = re.compile(r"`?([A-Za-z0-9_.\-]+\.root)`?")


def fetchable() -> set[str]:
    """Every file name a fixture or a manifest accounts for."""
    names = {p.name for p in (REPO / "data").rglob("*.root")}
    for manifest in ("gen/foreign/MANIFEST.sha256", "gen/cern/MANIFEST.sha256"):
        for line in (REPO / manifest).read_text().splitlines():
            if line[:1] and line[0] in "0123456789abcdef":
                names.add(line.split()[-1].rsplit("/", 1)[-1])
    large = tomllib.loads((REPO / "gen/cern/LARGE.toml").read_text())

    def walk(value):
        if isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, str) and value.endswith(".root"):
            names.add(value.rsplit("/", 1)[-1])

    walk(large)
    return names


def check_cited_files(paths: list[Path]) -> list[str]:
    """Every .root the specification names is a fixture or in a manifest."""
    known = fetchable()
    failures = []
    for path in paths:
        cited = set()
        for name in ROOT_FILE.findall(path.read_text()):
            if name in known or name in NOT_CORPUS:
                continue
            cited.add(name)
        for name in sorted(cited):
            failures.append(
                f"{path.relative_to(REPO)}: cites {name}, which is neither a "
                f"fixture in data/ nor listed in a corpus manifest, so nothing "
                f"can fetch it. Add it to a manifest, or to NOT_CORPUS in "
                f"tools/check_citations.py if it is not evidence")
    return failures


def check_published_count(paths: list[Path]) -> list[str]:
    """Whether the front pages quote the citation total they actually have."""
    total = sum(len(CITATION.findall(p.read_text())) for p in paths)
    failures = []
    for name, pattern in PUBLISHED:
        text = (REPO / name).read_text()
        m = re.search(pattern, text)
        if m is None:
            failures.append(f"{name}: no citation total to check against "
                            f"(expected a phrase matching {pattern!r})")
        elif int(m.group(1)) != total:
            failures.append(f"{name}: says {m.group(1)} source citations, "
                            f"actual {total}")
    return failures


def main(argv: list[str]) -> int:
    if not (SUBMODULE / "io/io/src/TFile.cxx").exists():
        print("root/ submodule is not checked out; run "
              "`git submodule update --init root`", file=sys.stderr)
        return 1
    paths = [Path(a).resolve() for a in argv] or [
        p for p in sorted((REPO / "spec").rglob("*.md")) if p not in NOT_OURS]
    failures = check(paths)
    failures += check_cited_files(paths)
    if not argv:
        failures += check_published_count(paths)
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
