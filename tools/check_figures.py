#!/usr/bin/env python3
"""Check the figures the project states about itself against the repository.

The front pages, the appendix and PLAN.md quote counts: reference files, byte
assertions, errata, invariant entries, corpus sizes. Each is hand-written, and
until 2026-09-24 only the citation total was checked (by check_citations.py),
so the rest drifted: a second consistency review found about fifteen stale
(PLAN-review.md V27-V30).

This recomputes every such count from the repository itself and requires each
page listed in gen/figures.toml to state it, in the words given there. A
template is literal text with placeholders: `{name}` renders the count in
digits, `{name:word}` in English, `{name:Word}` capitalised. Whitespace is
normalised, so a line break inside a template does not matter.

Only figures that describe the current state are listed. A measurement dated in
the text ("on 2026-09-21, 1696 of 1696") is a record of that run and is left
alone.

  tools/check_figures.py            check; exit 1 on any mismatch
  tools/check_figures.py --values   print the recomputed values
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

FIGURES = REPO / "gen/figures.toml"
ROOTTEST = REPO / "root/roottest"

WORDS = ("zero one two three four five six seven eight nine ten eleven twelve "
         "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def word(n: int) -> str:
    if n < 20:
        return WORDS[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return TENS[tens] + (f"-{WORDS[ones]}" if ones else "")
    return str(n)


def _cases(pattern: str) -> list[dict]:
    return [tomllib.loads(p.read_text()) for p in sorted(REPO.glob(pattern))]


def _manifest_lines(path: Path) -> int:
    return sum(1 for line in path.read_text().splitlines()
               if line.strip() and not line.startswith("#"))


def compute() -> dict[str, int | None]:
    """Every figure, from the repository. None when its source is absent."""
    import check_coverage

    cases = _cases("gen/cases/*/*/case.toml")
    written = _cases("gen/written/*/case.toml")
    entries = check_coverage.published()
    checked = check_coverage.checked_labels()
    errata = REPO / "spec/05-rntuple/ERRATA.md"
    streamers = tomllib.loads(
        (REPO / "spec/99-appendix/streamers.toml").read_text())
    pitfalls = (REPO / "spec/99-appendix/Pitfalls.md").read_text()
    writer = (REPO / "spec/99-appendix/WriterInvariants.md").read_text()
    silent = writer.split("## 7.", 1)[1].split("\n## ", 1)[0]
    large = tomllib.loads((REPO / "gen/cern/LARGE.toml").read_text())
    foreign = _manifest_lines(REPO / "gen/foreign/MANIFEST.sha256")
    cern = _manifest_lines(REPO / "gen/cern/MANIFEST.sha256")

    values: dict[str, int | None] = {
        "cases": len(cases),
        "bytes": sum(len(c.get("bytes", [])) for c in cases),
        "written": len(written),
        "written_bytes": sum(len(c.get("bytes", [])) for c in written),
        "invariants": len(entries),
        "invariant_docs": len({doc for _, doc, _ in entries}),
        "invariants_checked": sum(1 for label, _, _ in entries
                                  if label in checked),
        "rntuple_errata": len(re.findall(r"^\| \d+ \|", errata.read_text(),
                                         re.M)),
        "gap_classes": sum(1 for entry in streamers["class"].values()
                           if entry.get("status") == "gap"),
        "pitfalls": len(re.findall(r"^\*\*", pitfalls, re.M)),
        "silent": len(re.findall(r"^\d+\. \*\*", silent, re.M)),
        "foreign": foreign,
        "cern": cern,
        "corpus": foreign + cern,
        "large": sum(len(v) for v in large.values() if isinstance(v, list)),
        "roottest": None,
    }
    if ROOTTEST.is_dir():
        values["roottest"] = sum(1 for p in ROOTTEST.rglob("*.root")
                                 if p.is_file())
    return values


PLACEHOLDER = re.compile(r"\{(\w+)(?::(word|Word))?\}")


def render(template: str, values: dict) -> str:
    def one(m: re.Match) -> str:
        n = values[m.group(1)]
        if m.group(2) == "word":
            return word(n)
        if m.group(2) == "Word":
            return word(n).capitalize()
        return str(n)
    return PLACEHOLDER.sub(one, template)


def pattern(template: str) -> re.Pattern:
    """The template with each placeholder a wildcard, to report what a page says."""
    parts, at = [], 0
    for m in PLACEHOLDER.finditer(template):
        parts.append(re.escape(template[at:m.start()]))
        parts.append(r"([\w-]+)")
        at = m.end()
    parts.append(re.escape(template[at:]))
    return re.compile("".join(parts))


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def main(argv: list[str]) -> int:
    values = compute()
    if "--values" in argv:
        for name, n in values.items():
            print(f"{name:20} {n}")
        return 0

    spec = tomllib.loads(FIGURES.read_text())
    problems, checked, skipped = [], 0, 0
    for at in spec["at"]:
        template = normalise(at["text"])
        needs = {m.group(1) for m in PLACEHOLDER.finditer(template)}
        unknown = needs - set(values)
        if unknown:
            problems.append(f"{at['file']}: unknown figure {sorted(unknown)}")
            continue
        if any(values[n] is None for n in needs):
            skipped += 1
            continue
        page = normalise((REPO / at["file"]).read_text())
        want = render(template, values)
        checked += 1
        if want in page:
            continue
        found = pattern(template).search(page)
        says = f"says {found.group(0)!r}" if found else "has no such sentence"
        problems.append(f"{at['file']}: {says}; expected {want!r}")

    for problem in problems:
        print(f"FAIL {problem}", file=sys.stderr)
    if skipped:
        print(f"SKIPPED {skipped} figure(s): root/roottest is not checked out",
              file=sys.stderr)
    print(f"{checked} stated figure(s) checked, {len(problems)} failure(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
