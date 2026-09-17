#!/usr/bin/env python3
"""Check the spec's class-version tables against `ClassDef` in the pinned submodule.

`tools/check_citations.py` verifies that every cited file and line exists. It
cannot verify that a cited line still says what the citing sentence claims, and
`spec/00-conventions.md` §7 says so explicitly. This closes one class of that
problem completely: a **class version** is a number in a `ClassDef` macro, so a
claim about one can be checked rather than merely cited.

The claim each table makes is that its highest version is the class's current
one. When the submodule is bumped and a class's version rises, that table is
silently stale; nothing else in the suite notices.

Two shapes of table are understood, told apart by the header row:

    | Version | Difference |          -- the class is the document's name
    | Class | Version | Note |        -- each row names its own class

A row whose text says "current" must carry that highest version, so the prose and
the table cannot disagree with each other either.

Deliberately **not** checked: `## N. Version history` sections in
`spec/01-container/`. Those tabulate ROOT *release* numbers and on-disk record
versions, which are not `ClassDef` versions and have no macro to compare against.
The tool lists what it checked so that a silent narrowing is visible.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SUBMODULE = REPO / "root"
SPEC = REPO / "spec"

#: Every spelling of the macro that declares a persistent class version.
CLASSDEF = re.compile(
    r"\bClassDef(?:Override|NV|Inline|InlineOverride|InlineNV)?"
    r"\s*\(\s*([A-Za-z_][\w:]*)\s*,\s*(\d+)\s*\)")

#: `## 13. Class versions`, and nothing else.
SECTION = re.compile(r"^## \d+\. Class versions\s*$")

#: A backticked identifier, for the class-per-row tables.
BACKTICKED = re.compile(r"`([A-Za-z_][\w:]*)`")

#: An elided range of class names, which cannot be expanded.
ELLIPSIS = re.compile(r"\u2026|\.\.\.")

#: One or more version numbers in a table cell: "10", "8, 9", "1, 2, 3, 4".
#: Backticked spans are removed first, so a citation's line number is not
#: mistaken for a version. A cell like "<= 5" contributes 5, which is harmless
#: because the comparison is against the highest version in the whole table.
VERSIONS = re.compile(r"(?<![\w.])(\d+)(?![\w.])")


def class_versions() -> dict[str, set[int]]:
    """Every `ClassDef` version in the submodule, by class name.

    A name may appear more than once: ROOT's own tests and tutorials define
    classes called `Event`, `Track` and `MyClass`, and a few real classes are
    declared twice. Such a name is returned with every version found and refused
    at the point of use rather than resolved by guessing.
    """
    found: dict[str, set[int]] = {}
    for header in SUBMODULE.rglob("*.h"):
        try:
            text = header.read_text(errors="ignore")
        except OSError:
            continue
        for match in CLASSDEF.finditer(text):
            found.setdefault(match.group(1), set()).add(int(match.group(2)))
    return found


def tables(lines: list[str]):
    """Every table in `lines`, up to the next heading, as (header, rows).

    A section may hold more than one: `TBranchElement.md` §12 tabulates its own
    versions and then the other branch classes, and both are claims.
    """
    header: list[str] = []
    rows: list[list[str]] = []
    for line in lines:
        if line.startswith("## "):
            break                      # the section ended
        if not line.startswith("|"):
            if header:
                yield header, rows
                header, rows = [], []
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue                   # the |---|---| separator
        if not header:
            header = cells
        else:
            rows.append(cells)
    if header:
        yield header, rows


def claims(path: Path,
           narrowed: list[str] | None = None
           ) -> list[tuple[str, list[int], bool, int]]:
    """`(class, versions, marked current, line number)` for one document.

    A class-per-row table may name several classes in one cell, and may give a
    class more than one row; every version found for a class is collected and the
    comparison is made against the highest.

    `narrowed` collects rows that name classes they do not spell, so that a row
    the tool cannot fully check is reported rather than passed over.
    """
    if narrowed is None:
        narrowed = []
    lines = path.read_text().splitlines()
    out: list[tuple[str, list[int], bool, int]] = []
    for start, line in enumerate(lines):
        if not SECTION.match(line):
            continue
        for header, rows in tables(lines[start + 1:]):
            if not rows or not header:
                continue
            first = header[0].lower()
            class_per_row = first.startswith("class") and "version" not in first
            for cells in rows:
                if class_per_row:
                    names = BACKTICKED.findall(cells[0])
                    version_cell = cells[1] if len(cells) > 1 else ""
                    if not names and "`" in cells[0]:
                        # A backticked cell that is not a bare identifier: a
                        # template specialization such as `TMatrixTBase<T>`, or
                        # a `pair<int,int>`. `ClassDef` names the template, so
                        # there is nothing to compare against — said out loud,
                        # because the alternative is a table that looks checked
                        # and is not. Spell the template in the table to fix it.
                        narrowed.append(
                            f"{path.relative_to(REPO)}:{start + 1}: "
                            f"{cells[0]} is not a name ClassDef declares; "
                            f"its version is not checked")
                    if ELLIPSIS.search(cells[0]):
                        # "`TLeafO`…`TLeafD`" names classes it does not spell,
                        # so only the endpoints can be checked. Said out loud
                        # rather than passed over.
                        narrowed.append(
                            f"{path.relative_to(REPO)}:{start + 1}: "
                            f"{cells[0]} names a range; only the classes it "
                            f"spells are checked")
                else:
                    names = [path.stem]
                    version_cell = cells[0]
                # Strip backticked spans first: a cell like
                # "1 (`root/tree/tree/inc/TBranchObject.h:71`)" carries a
                # citation whose line number is not a class version.
                bare = re.sub(r"`[^`]*`", " ", version_cell)
                versions = [int(v) for v in VERSIONS.findall(bare)]
                if not versions or not names:
                    continue
                current = "current" in " ".join(cells).lower()
                for name in names:
                    out.append((name, versions, current, start + 1))
    return out


def main(argv: list[str]) -> int:
    known = class_versions()
    if not known:
        print("no ClassDef macros found: is the submodule checked out?",
              file=sys.stderr)
        return 1

    failures: list[str] = []
    narrowed: list[str] = []
    checked: dict[str, tuple[int, int]] = {}   # class -> (claimed, actual)
    documents: set[str] = set()

    for path in sorted(SPEC.rglob("*.md")):
        # Per class: every version the table gives it, and separately the
        # versions on rows that say "current". The two must not be merged --
        # doing so made the "current" check vacuous, because the actual version
        # is in the table whichever row claims to be the current one.
        by_class: dict[str, tuple[list[int], list[int], int]] = {}
        for name, versions, current, line in claims(path, narrowed):
            seen, marked, first = by_class.get(name, ([], [], line))
            by_class[name] = (seen + versions,
                              marked + (versions if current else []), first)
        if by_class:
            documents.add(str(path.relative_to(REPO)))
        for name, (versions, marked, line) in sorted(by_class.items()):
            where = f"{path.relative_to(REPO)}:{line}"
            found = known.get(name)
            if found is None:
                failures.append(
                    f"{where}: {name} has no ClassDef in the submodule")
                continue
            if len(found) > 1:
                failures.append(
                    f"{where}: {name} has several ClassDef versions in the "
                    f"submodule ({sorted(found)}); the table cannot be checked")
                continue
            actual = next(iter(found))
            claimed = max(versions)
            checked[name] = (claimed, actual)
            if claimed != actual:
                failures.append(
                    f"{where}: the table's highest version for {name} is "
                    f"{claimed}, ClassDef says {actual}")
            elif marked and actual not in marked:
                failures.append(
                    f"{where}: the row for {name} marked \"current\" carries "
                    f"version {max(marked)}, ClassDef says {actual}")

    for name, (claimed, actual) in sorted(checked.items()):
        mark = "ok " if claimed == actual else "BAD"
        print(f"  {mark} {name:16} {actual}")
    for message in sorted(set(narrowed)):
        print(f"NARROWED {message}", file=sys.stderr)
    for message in failures:
        print(f"FAIL {message}", file=sys.stderr)
    print(f"{len(checked)} class version(s) checked across "
          f"{len(documents)} document(s), {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
