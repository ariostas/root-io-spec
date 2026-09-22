#!/usr/bin/env python3
"""Which published `Invariants` entries are actually checked, and by what.

`CLAUDE.md` requires every numbered entry under an `Invariants` heading to be
added to `tools/check_invariants.py` and confirmed against a corrupted fixture.
Nothing enforced that, and `PLAN.md` §8.13 is why it matters: the one entry
found to be **false** was also one that had never been wired up. An invariant
nobody checks is a claim, and this project's whole method is that claims are
checked twice.

So this tool makes the rule enforceable. It reads every entry out of `spec/`,
matches it against the labels the tools actually report, and requires every
unmatched entry to be accounted for in `gen/invariants.toml` with a reason.

    tools/check_coverage.py            the report
    tools/check_coverage.py --check    what CI runs: fail on an unaccounted entry

An entry is **checked** when some tool contains its label as a literal string --
`self.bad("Directory 9.15", ...)` or the same label in a returned tuple. That is a
deliberately shallow test: it proves a check exists, not that the check is right.
Depth is what the corrupted-fixture rule is for, and this tool cannot see it.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = REPO / "spec"
SIDECAR = REPO / "gen/invariants.toml"

#: Files whose label strings count as a check. `check_invariants.py` is the main
#: one; the write side's invariants are checked by `check_write.py` through
#: `rootwrite.py`, and a few by unit tests that build what no fixture holds.
TOOLS = ("check_invariants.py", "check_write.py", "rootfile.py", "rootwrite.py",
         "element_lists.py", "test_container.py", "test_write.py",
         "test_streamer_driven.py", "test_ttree.py", "test_large_files.py",
         "test_bootstrap.py", "test_rntuple.py")

#: `spec/05-rntuple/BinaryFormatSpecification.md` is upstream's copy and not ours
#: to annotate (`CLAUDE.md`), so its numbered lists are not our invariants.
NOT_OURS = {SPEC / "05-rntuple/BinaryFormatSpecification.md"}

HEADING = re.compile(r"^#+\s+(\d+)\.\s+Invariants\b.*$", re.M)
ITEM = re.compile(r"^(\d+)\.\s", re.M)


def published() -> list[tuple[str, str, str]]:
    """(label, document path relative to the repo, the entry's first line)."""
    out = []
    for path in sorted(SPEC.rglob("*.md")):
        if path in NOT_OURS:
            continue
        text = path.read_text()
        match = HEADING.search(text)
        if match is None:
            continue
        section = match.group(1)
        rest = text[match.end():]
        nxt = re.search(r"^#+\s", rest, re.M)
        body = rest[:nxt.start()] if nxt else rest
        for item in ITEM.finditer(body):
            line = body[item.end():].split("\n", 1)[0].strip()
            out.append((f"{path.stem} {section}.{item.group(1)}",
                        str(path.relative_to(REPO)), line))
    return out


def checked_labels() -> dict[str, list[str]]:
    """Every `Doc N.M` label appearing literally in a tool, to the tools using it."""
    found: dict[str, list[str]] = {}
    pattern = re.compile(r'"([A-Z][A-Za-z]+ \d+\.\d+)"')
    for name in TOOLS:
        path = REPO / "tools" / name
        if not path.exists():
            continue
        for label in set(pattern.findall(path.read_text())):
            found.setdefault(label, []).append(name)
    return found


def accounted() -> dict[str, dict]:
    if not SIDECAR.exists():
        return {}
    return tomllib.loads(SIDECAR.read_text()).get("invariant", {})


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    entries = published()
    labels = checked_labels()
    notes = accounted()

    unchecked = [(label, doc, line) for label, doc, line in entries
                 if label not in labels]
    stale = [label for label in notes
             if label in labels or label not in {e[0] for e in entries}]
    missing_note = [(label, doc, line) for label, doc, line in unchecked
                    if label not in notes]
    orphan = sorted(set(labels) - {e[0] for e in entries})

    if not check_only:
        by_doc: dict[str, list[tuple[str, str]]] = {}
        for label, doc, line in unchecked:
            by_doc.setdefault(doc, []).append((label, line))
        for doc in sorted(by_doc):
            print(f"\n{doc}")
            for label, line in by_doc[doc]:
                why = notes.get(label, {}).get("reason", "").strip().split("\n")[0]
                mark = "accounted" if label in notes else "UNACCOUNTED"
                print(f"  {label:34s} {mark:12s} {line[:78]}")
                if why:
                    print(f"  {'':34s} {'':12s} -> {why[:78]}")
        for label in orphan:
            print(f"ORPHAN  {label}: a tool reports it, no document publishes it")

    print(f"\n{len(entries)} published entr{'y' if len(entries) == 1 else 'ies'} "
          f"across {len({e[1] for e in entries})} document(s); "
          f"{len(entries) - len(unchecked)} checked, {len(unchecked)} not, "
          f"of which {len(unchecked) - len(missing_note)} accounted for in "
          f"{SIDECAR.relative_to(REPO)}")

    failures = 0
    for label, doc, line in missing_note:
        print(f"FAIL {label} ({doc}) is published, unchecked and unaccounted: {line[:60]}",
              file=sys.stderr)
        failures += 1
    for label in stale:
        print(f"FAIL {label} has an entry in {SIDECAR.relative_to(REPO)} that no "
              f"longer applies", file=sys.stderr)
        failures += 1
    for label in orphan:
        print(f"FAIL {label} is reported by a tool but no document publishes it",
              file=sys.stderr)
        failures += 1
    if failures:
        print(f"{failures} failure(s)", file=sys.stderr)
        return 1
    print("every published invariant is checked or accounted for")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
