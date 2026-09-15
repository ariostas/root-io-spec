#!/usr/bin/env python3
"""Regenerate the reference files in `data/` from the macros in `gen/cases/`.

Each case directory holds a `gen.C` defining `void gen(const char *out)` and a
`case.toml` describing what the resulting file should contain. It may also hold a
`classes.h`, which is compiled into a dictionary first; see `gen/common/README.md`.
Running this requires ROOT on PATH; checking the result afterwards does not.

  tools/generate.py              regenerate everything, then verify
  tools/generate.py --check      verify only, without regenerating
  tools/generate.py --accept     record digests that changed on purpose
  tools/generate.py <case-dir>   act on one case

A digest that differs from data/MANIFEST.sha256 is an error, because it means
either the format changed or a fixture stopped being reproducible. When the change
is intentional -- a case.toml or gen.C was edited -- re-record it with --accept,
which prints what changed and then writes the manifest.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import check_bytes  # noqa: E402
import normalize  # noqa: E402


def cases(selected: list[str]) -> list[Path]:
    if selected:
        return [Path(s).resolve() for s in selected]
    return [p.parent for p in sorted((REPO / "gen/cases").rglob("case.toml"))]


# Where ACLiC puts its build products. Gitignored; see gen/common/README.md.
BUILD_DIR = REPO / "build/aclic"


def run(case_dir: Path) -> Path:
    case = tomllib.loads((case_dir / "case.toml").read_text())
    out = REPO / case["file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    macro = case_dir / "gen.C"

    args = ["root", "-l", "-b", "-q"]
    # A case that needs real ClassDef classes declares them in classes.h, which is
    # compiled into a dictionary first. It has to be a separate step: the
    # interpreter parses gen.C in full before running any of it, so a macro that
    # compiled its own classes could not then mention them.
    classes = case_dir / "classes.h"
    if classes.exists():
        helper = REPO / "gen/common/aclic.C"
        args += ["-e", f".L {helper}",
                 "-e", f'aclic("{classes.relative_to(REPO)}", "{BUILD_DIR.relative_to(REPO)}");']

    # The output path is passed REPO-relative and ROOT is run from REPO, because
    # TFile stores the path it was given as the file's name and title. Passing an
    # absolute path would bake this checkout's location into the fixture and shift
    # every byte offset after the header.
    args += ["-e", f".L {macro}", "-e", f'gen("{case["file"]}");']

    result = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"{case['id']}: ROOT exited {result.returncode}\n"
            f"{result.stdout}\n{result.stderr}")
    if not out.exists():
        raise SystemExit(f"{case['id']}: {macro} did not produce {out}")
    return out


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    accept = "--accept" in argv
    unknown = [a for a in argv if a.startswith("--") and a not in ("--check", "--accept")]
    if unknown:
        raise SystemExit(f"unknown option(s): {' '.join(unknown)}")
    if check_only and accept:
        raise SystemExit("--check and --accept are mutually exclusive")
    selected = [a for a in argv if not a.startswith("--")]
    dirs = cases(selected)

    if not check_only:
        for case_dir in dirs:
            out = run(case_dir)
            print(f"generated {out.relative_to(REPO)}")

    manifest = REPO / "data/MANIFEST.sha256"
    known = {}
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                d, p = line.split(None, 1)
                known[p.strip()] = d

    lines, drift = [], []
    for case_dir in dirs:
        case = tomllib.loads((case_dir / "case.toml").read_text())
        rel = case["file"]
        d = normalize.digest(REPO / rel)
        lines.append(f"{d}  {rel}")
        if rel in known and known[rel] != d:
            drift.append(f"{rel}: normalized digest changed\n  was {known[rel]}\n  now {d}")

    for message in drift:
        label = "ACCEPTED" if accept else "DRIFT"
        print(f"{label} {message}", file=sys.stderr)
    if drift and not accept:
        # Say which record moved. Without this a cross-platform drift is a bare
        # pair of hashes, and the cause has to be guessed at.
        for message in drift:
            rel = message.split(":", 1)[0]
            print(f"  per-record digests for {rel}:", file=sys.stderr)
            data = normalize.normalize((REPO / rel).read_bytes())
            for offset, cls, name, d in normalize.record_digests(data):
                print(f"    {offset:9} {cls:14} {name[:24]:24} {d}", file=sys.stderr)

    if not check_only and (accept or not drift):
        # Merge rather than replace: running on a subset of the cases must not
        # drop the digests of the cases it was not asked about.
        merged = dict(known)
        for line in lines:
            d, p_ = line.split(None, 1)
            merged[p_] = d
        manifest.write_text(
            "# Normalized SHA-256 digests of the reference files.\n"
            "# Timestamps and UUIDs are masked first; see tools/normalize.py.\n"
            + "".join(f"{d}  {p_}\n" for p_, d in sorted(merged.items()))
        )

    rc = check_bytes.main([str(d) for d in dirs])
    return 1 if ((drift and not accept) or rc) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
