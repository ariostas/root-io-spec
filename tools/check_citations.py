#!/usr/bin/env python3
"""Verify every source citation in `spec/` against the pinned ROOT submodule.

`spec/00-conventions.md` §7 promises that citations refer to the pinned commit.
This checks that the promise holds: that each cited file exists in the submodule
and that each cited line number is within that file. It catches the failure mode
the convention is otherwise vulnerable to -- a citation that silently goes stale
when the submodule is bumped.

Requires the submodule to be checked out. Needs no third-party packages.

  tools/check_citations.py            check every document under spec/
  tools/check_citations.py <paths>    check specific files
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SUBMODULE = REPO / "root"

# Citations appear inside inline code spans; see tools/rootcite.py for the
# rendering side. Both must recognise the same shape.
CITATION = re.compile(
    r"`root/(?P<path>[A-Za-z0-9_./+-]+\.(?:cxx|cxx\.in|hxx|h|c|cpp|cu|py|md|txt|yml))"
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


def main(argv: list[str]) -> int:
    if not (SUBMODULE / "io/io/src/TFile.cxx").exists():
        print("root/ submodule is not checked out; run "
              "`git submodule update --init root`", file=sys.stderr)
        return 1
    paths = [Path(a).resolve() for a in argv] or sorted((REPO / "spec").rglob("*.md"))
    failures = check(paths)
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
