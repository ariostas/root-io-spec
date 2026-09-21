#!/usr/bin/env python3
"""Check the files `tools/rootwrite.py` produces, per `spec/06-writing/`.

Three gates, in increasing strength (`spec/06-writing/index.md` 2):

1. the bytes match the committed copy in `data/written/`, and every `[[bytes]]`
   assertion in the case's `case.toml` holds;
2. `tools/rootfile.py` reads the file and `tools/check_invariants.py` accepts it
   -- this project's reader and the specification's own invariants, applied to
   bytes this project wrote rather than bytes ROOT wrote;
3. with `--root`, ROOT opens the file, its `verify.C` finds the values that went
   in, and **nothing** on either stream looks like a ROOT diagnostic.

  tools/check_write.py                 gates 1 and 2 over every case
  tools/check_write.py --root          all three
  tools/check_write.py --accept        rewrite data/written/ after a deliberate change
  tools/check_write.py gen/written/objstring

Unlike `data/`'s other files these are byte-reproducible, because a writer has no
reason to consult a clock: `tools/rootwrite.py` takes the timestamp and the UUID
as inputs. So the digest here is a plain sha256 of the file, not the normalized
digest `tools/normalize.py` computes for the ROOT-written fixtures.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import check_bytes  # noqa: E402
import rootfile  # noqa: E402

MANIFEST = REPO / "data/written/MANIFEST.sha256"

#: Any of these in ROOT's output fails gate 3. The point of the gate is that a
#: wrong class version or a wrong byte count makes ROOT talk, and a writer that
#: ignores what it says has not been checked at all.
ROOT_DIAGNOSTICS = ("Error in <", "Warning in <", "Fatal in <", "SysError in <",
                    "Break in <", "R__unzip", "CheckByteCount")


def cases(selected: list[str]) -> list[Path]:
    if selected:
        return [Path(s).resolve() for s in selected]
    return [p.parent for p in sorted((REPO / "gen/written").rglob("case.toml"))]


def build(case_dir: Path) -> bytes:
    """Run the case's `build.py`, which must define `build() -> bytes`."""
    path = case_dir / "build.py"
    spec = importlib.util.spec_from_file_location(
        f"written_{case_dir.name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build()


def read_back(buf: bytes, case: dict) -> list[str]:
    """Gate 2's first half: this project's reader agrees about the structure."""
    out = []
    try:
        header = rootfile.read_header(buf)
        records = rootfile.read_records(buf, header)
        directory = rootfile.read_directory(buf, records[0])
        if directory is None:
            return [f"{case['id']}: the first record is not a directory record"]
        keys = rootfile.read_key_list(buf, directory)
    except rootfile.FormatError as exc:
        return [f"{case['id']}: rootfile.py rejected it: {exc}"]

    expected = [r for r in case.get("records", [])]
    if expected and len(records) != len(expected):
        out.append(f"{case['id']}: {len(records)} records, "
                   f"case.toml lists {len(expected)}")
    for rec, want in zip(records, expected):
        if rec.offset != want["offset"]:
            out.append(f"{case['id']}: record at {rec.offset}, "
                       f"case.toml says {want['offset']}")
        if rec.nbytes != want["nbytes"]:
            out.append(f"{case['id']}: record at {rec.offset} is {rec.nbytes} "
                       f"bytes, case.toml says {want['nbytes']}")
        # A free segment has no key to name a class with, so `class` is
        # optional and its absence is the assertion that the record is a gap
        # (spec/01-container/FreeSegments.md 4).
        if "class" not in want:
            if not rec.free:
                out.append(f"{case['id']}: record at {rec.offset} is live, "
                           f"case.toml lists it as a free segment")
        elif rec.class_name != want["class"]:
            out.append(f"{case['id']}: record at {rec.offset} is "
                       f"{rec.class_name}, case.toml says {want['class']}")
    want_keys = case.get("keys", [])
    if want_keys and [k.name for k in keys] != [k["name"] for k in want_keys]:
        out.append(f"{case['id']}: key list holds "
                   f"{[k.name for k in keys]}, case.toml says "
                   f"{[k['name'] for k in want_keys]}")
    return out


def verify_with_root(case_dir: Path, path: Path) -> list[str]:
    """Gate 3: ROOT opens it, agrees about the values, and says nothing."""
    macro = case_dir / "verify.C"
    if not macro.exists():
        return [f"{case_dir.name}: no verify.C"]
    result = subprocess.run(
        ["root", "-l", "-b", "-q",
         "-e", f".L {macro.relative_to(REPO)}",
         "-e", f'verify("{path.relative_to(REPO)}");'],
        cwd=REPO, capture_output=True, text=True)
    stream = result.stdout + result.stderr
    out = []
    if result.returncode != 0:
        out.append(f"{case_dir.name}: ROOT exited {result.returncode}")
    for line in stream.splitlines():
        if line.startswith("FAIL"):
            out.append(f"{case_dir.name}: {line}")
        elif any(d in line for d in ROOT_DIAGNOSTICS):
            out.append(f"{case_dir.name}: ROOT said: {line.strip()}")
    if "VERIFY OK" not in stream:
        out.append(f"{case_dir.name}: verify.C did not reach VERIFY OK")
    return out


def main(argv: list[str]) -> int:
    accept = "--accept" in argv
    with_root = "--root" in argv
    unknown = [a for a in argv
               if a.startswith("--") and a not in ("--accept", "--root")]
    if unknown:
        raise SystemExit(f"unknown option(s): {' '.join(unknown)}")
    dirs = cases([a for a in argv if not a.startswith("--")])
    if not dirs:
        raise SystemExit("no cases under gen/written/")

    known = {}
    if MANIFEST.exists():
        for line in MANIFEST.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                d, p = line.split(None, 1)
                known[p.strip()] = d

    failures, digests, files = [], dict(known), []
    for case_dir in dirs:
        case = tomllib.loads((case_dir / "case.toml").read_text())
        rel = case["file"]
        out = REPO / rel
        buf = build(case_dir)

        # Gate 1. A writer is deterministic, so the committed file is a plain
        # copy and any difference is a change in behaviour worth looking at.
        digest = hashlib.sha256(buf).hexdigest()
        if accept:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(buf)
            if known.get(rel) not in (None, digest):
                print(f"ACCEPTED {rel}: {known[rel]} -> {digest}",
                      file=sys.stderr)
        elif not out.exists():
            failures.append(f"{case['id']}: {rel} missing; "
                            "run tools/check_write.py --accept")
        elif out.read_bytes() != buf:
            failures.append(
                f"{case['id']}: tools/rootwrite.py no longer reproduces {rel}\n"
                f"  committed {hashlib.sha256(out.read_bytes()).hexdigest()}\n"
                f"  produced  {digest}\n"
                f"  manifest  {known.get(rel, '(absent)')}")
        digests[rel] = digest
        files.append(out)

        if "size" in case and len(buf) != case["size"]:
            failures.append(f"{case['id']}: size {len(buf)}, "
                            f"case.toml says {case['size']}")
        failures += check_bytes.check(buf, case.get("bytes", []), case["id"])

        # Gate 2.
        failures += read_back(buf, case)

        # Gate 3.
        if with_root:
            failures += verify_with_root(case_dir, out)

    if accept:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(
            "# SHA-256 digests of the files tools/rootwrite.py produces.\n"
            "# Not normalized: a writer fixes its own timestamp and UUID, so\n"
            "# these files are byte-reproducible. See tools/check_write.py.\n"
            + "".join(f"{d}  {p}\n" for p, d in sorted(digests.items())))

    # Gate 2's second half, over every written file at once, so the count it
    # prints is the specification's own invariants applied to our bytes.
    if files:
        inv = subprocess.run(
            [sys.executable, str(REPO / "tools/check_invariants.py")]
            + [str(f) for f in files if f.exists()],
            cwd=REPO, capture_output=True, text=True)
        sys.stdout.write(inv.stdout)
        sys.stderr.write(inv.stderr)
        if inv.returncode != 0:
            failures.append("check_invariants.py rejected a written file")

    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    total = sum(len(tomllib.loads((d / "case.toml").read_text()).get("bytes", []))
                for d in dirs)
    print(f"{total} byte assertions checked across {len(dirs)} written case(s), "
          f"{len(failures)} failure(s)"
          + ("" if with_root else "; --root adds the ROOT read-back gate"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
