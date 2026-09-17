#!/usr/bin/env python3
"""Fetch the ROOT files CERN publishes, to measure the specification against.

These are **not** reference files. `data/` holds files this project wrote and
asserts byte for byte; these are files CERN published, and their only job is to
answer "is the specification enough for a file nobody designed around it?". They
are not committed -- `gen/cern/MANIFEST.sha256` records what was used.

Source: https://root.cern/files/ and its rootbench/ subdirectory.

**Every file here was written by ROOT itself.** That is the point of this corpus
as against `gen/foreign/`, which is uproot's regression suite and contains files
uproot wrote: there, a failing invariant is a lead to be traced to a writer before
it is evidence. Here it is evidence.

  tools/fetch_cern.py                    the core tier: 22 files, 5 MB
  tools/fetch_cern.py --tier physics     real production trees, 27 MB more
  tools/fetch_cern.py --tier all         both
  tools/fetch_cern.py --check            verify what is already downloaded
  tools/fetch_cern.py --headers          check gen/cern/LARGE.toml by range request
  tools/fetch_cern.py --dir DIR          somewhere other than build/cern

`gen/cern/README.md` says why each file is listed.

The multi-gigabyte files are never downloaded. root.cern serves
`Accept-Ranges: bytes`, so `--headers` reads each one's header and free-segment
record -- a few hundred bytes -- and checks them against the facts recorded in
`gen/cern/LARGE.toml`. That is how the large-file layout of
`spec/01-container/` gets exercised at all; no fixture covers it.
"""

from __future__ import annotations

import hashlib
import struct
import sys
import tomllib
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import rootfile  # noqa: E402

MANIFEST = REPO / "gen/cern/MANIFEST.sha256"
LARGE = REPO / "gen/cern/LARGE.toml"
BASE = "https://root.cern/files/"
DEFAULT_DIR = REPO / "build/cern"


BIG = 2000000000          # TFile::kStartBigFile, root/io/io/inc/TFile.h:278


def large_file_problems(header, key, entries) -> list[str]:
    """The invariants of spec/01-container/LargeFiles.md section 8.

    Pure, so the unit tests can feed it a corrupted reading. `header` is a
    rootfile.FileHeader, `key` the free-segment record's own key, and `entries`
    the (version, fFirst, fLast) triples of its payload.
    """
    out = []
    if (header.version >= 1000000) != (header.end > BIG):
        out.append(f"fVersion {header.version} but fEND {header.end} "
                   f"(LargeFiles 8.1)")
    if len(entries) != header.nfree:
        out.append(f"nfree {header.nfree} but {len(entries)} entries parsed "
                   f"(LargeFiles 8.2, FreeSegments 6)")
    if entries and entries[-1][2] <= header.end:
        out.append(f"last entry ends at {entries[-1][2]}, not past fEND "
                   f"{header.end} (LargeFiles 8.3)")
    for i, (version, first, last) in enumerate(entries):
        if (version > 1000) != (last > BIG):
            out.append(f"entry {i} version {version} with fLast {last} "
                       f"(LargeFiles 8.4)")
        if not 0 <= first <= last:
            out.append(f"entry {i} spans ({first}, {last}) (LargeFiles 8.5)")
        elif first > header.end or (last > header.end
                                    and i != len(entries) - 1):
            out.append(f"entry {i} spans ({first}, {last}) past fEND "
                       f"{header.end} (LargeFiles 8.5)")
    if key.key_version > 1000:
        if key.seek_pdir != header.begin:
            out.append(f"the free record's key has fSeekPdir {key.seek_pdir}, "
                       f"not fBEGIN {header.begin} (LargeFiles 8.6)")
        if key.pid_offset:
            out.append(f"the free record's key has fPidOffset "
                       f"{key.pid_offset} (LargeFiles 8.6)")
    return out


def entries(tier: str) -> list[tuple[str, int, str]]:
    """(digest, size, remote path) for the requested tier."""
    out = []
    for line in MANIFEST.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        digest, size, _version, row_tier, path = line.split(None, 4)
        if tier not in ("all", row_tier):
            continue
        out.append((digest, int(size), path.strip()))
    return out


def fetch_range(url: str, start: int, length: int) -> bytes:
    request = urllib.request.Request(
        url, headers={"Range": f"bytes={start}-{start + length - 1}"})
    with urllib.request.urlopen(request) as response:
        if response.status != 206:
            raise OSError(f"{url}: expected 206 Partial Content, got "
                          f"{response.status}; the server ignored the range")
        return response.read()


def check_headers() -> int:
    """Verify every LARGE.toml entry with two range requests."""
    spec = tomllib.loads(LARGE.read_text())
    bad = 0
    for want in spec["file"]:
        url = BASE + want["path"]
        name = want["path"].rsplit("/", 1)[-1]
        problems: list[str] = []
        try:
            header = rootfile.read_header(fetch_range(url, 0, 512))
            chunk = fetch_range(url, want["fseekfree"], want["nbytesfree"])
            # The free record's key starts at chunk[0], so every offset this
            # parse uses is local to the chunk.
            record, _ = rootfile._read_key_at(chunk, 0)
            triples = rootfile.parse_free_entries(chunk, record.key_len,
                                                  record.payload_nbytes)
            free = [(first, last) for _, first, last in triples]
        except (OSError, rootfile.FormatError, struct.error, IndexError,
                ValueError) as exc:
            print(f"FAIL {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            bad += 1
            continue

        major, minor, patch = header.root_version
        large = [entry for entry in free if entry[1] > 2000000000]
        got = {
            "root": f"{major}.{minor:02d}/{patch:02d}",
            "fversion": header.version,
            "units": header.units,
            "fbegin": header.begin,
            "fend": header.end,
            "fseekfree": header.seek_free,
            "nbytesfree": header.nbytes_free,
            "nfree": header.nfree,
            "free_keylen": record.key_len,
            "free_class": record.class_name,
            "free_small": len(free) - len(large),
            "free_large": len(large),
            "sentinel": list(free[-1]) if free else None,
        }
        for field, value in got.items():
            if want[field] != value:
                problems.append(f"{field}: recorded {want[field]!r}, "
                                f"measured {value!r}")
        # The invariants LargeFiles.md section 8 states, checked here because no
        # local file is large enough to exercise them.
        problems.extend(large_file_problems(header, record, triples))
        if problems:
            bad += 1
            for problem in problems:
                print(f"FAIL {name}: {problem}", file=sys.stderr)
        else:
            print(f"  ok  {name[:44]:44} {got['root']}  "
                  f"{'large' if header.version >= 1000000 else 'small'} format, "
                  f"fEND {header.end}, {header.nfree} free "
                  f"({got['free_large']} of them 18-byte)")
    print(f"{len(spec['file'])} large file(s) checked by range request, "
          f"{bad} failure(s)")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    unknown = [a for a in argv
               if a.startswith("--") and a not in ("--check", "--headers",
                                                   "--tier", "--dir")]
    if unknown:
        raise SystemExit(f"unknown option(s): {' '.join(unknown)}")
    if "--headers" in argv:
        return check_headers()

    check_only = "--check" in argv
    tier = argv[argv.index("--tier") + 1] if "--tier" in argv else "core"
    if tier not in ("core", "physics", "all"):
        raise SystemExit(f"unknown tier {tier!r}: core, physics or all")
    target = Path(argv[argv.index("--dir") + 1]) if "--dir" in argv else DEFAULT_DIR
    target.mkdir(parents=True, exist_ok=True)

    rows = entries(tier)
    bad = missing = fetched = 0
    for digest, size, path in rows:
        # The manifest carries the remote path; files land flat, by basename.
        local = target / path.rsplit("/", 1)[-1]
        if not local.exists():
            if check_only:
                missing += 1
                continue
            urllib.request.urlretrieve(BASE + path, local)
            fetched += 1
        raw = local.read_bytes()
        got = hashlib.sha256(raw).hexdigest()
        if got != digest or len(raw) != size:
            print(f"DIGEST {local.name}: manifest {digest} ({size} bytes), "
                  f"file {got} ({len(raw)} bytes)", file=sys.stderr)
            bad += 1
    print(f"{len(rows)} file(s) in tier {tier}, {fetched} fetched, "
          f"{missing} missing, {bad} with the wrong digest -> {target}")
    return 1 if bad or (check_only and missing) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
