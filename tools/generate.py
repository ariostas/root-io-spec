"""Regenerate the reference files in `data/` from the macros in `gen/cases/`.

Each case directory holds a `gen.C` defining `void gen(const char *out)` and a
`case.toml` describing what the resulting file should contain. Running this
requires ROOT on PATH; checking the result afterwards does not.

  tools/generate.py              regenerate everything, then verify
  tools/generate.py --check      verify only, without regenerating
  tools/generate.py <case-dir>   act on one case
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


def run(case_dir: Path) -> Path:
    case = tomllib.loads((case_dir / "case.toml").read_text())
    out = REPO / case["file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    macro = case_dir / "gen.C"
    # The output path is passed REPO-relative and ROOT is run from REPO, because
    # TFile stores the path it was given as the file's name and title. Passing an
    # absolute path would bake this checkout's location into the fixture and shift
    # every byte offset after the header.
    subprocess.run(
        ["root", "-l", "-b", "-q", "-e", f'.L {macro}', "-e", f'gen("{case["file"]}");'],
        cwd=REPO, check=True, capture_output=True, text=True,
    )
    if not out.exists():
        raise SystemExit(f"{case['id']}: {macro} did not produce {out}")
    return out


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
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
        print(f"DRIFT {message}", file=sys.stderr)

    if not check_only and not drift:
        manifest.write_text(
            "# Normalized SHA-256 digests of the reference files.\n"
            "# Timestamps and UUIDs are masked first; see tools/normalize.py.\n"
            + "".join(f"{line}\n" for line in sorted(lines))
        )

    rc = check_bytes.main([str(d) for d in dirs])
    return 1 if (drift or rc) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
