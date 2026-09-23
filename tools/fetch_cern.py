#!/usr/bin/env python3
"""Fetch the ROOT files CERN publishes, to measure the specification against.

These are **not** reference files. `data/` holds files this project wrote and
asserts byte for byte; these are files CERN published, used only to test whether
the specification is enough for a file nobody designed around it. They are not
committed; `gen/cern/MANIFEST.sha256` records what was used.

Source: https://root.cern/files/ and its rootbench/ subdirectory.

**Every file here was written by ROOT itself.** This distinguishes it from
`gen/foreign/`, uproot's regression suite, which contains files uproot wrote:
there a failing invariant is a lead to be traced to a writer before it is
evidence. Here it is evidence.

  tools/fetch_cern.py                    the core tier: 24 files, 5.5 MB
  tools/fetch_cern.py --tier physics     real production trees, 27 MB more
  tools/fetch_cern.py --tier geometry    the TGeoManager sweep, 46 files, 19 MB
  tools/fetch_cern.py --tier all         all three
  tools/fetch_cern.py --check            verify what is already downloaded
  tools/fetch_cern.py --headers          check gen/cern/LARGE.toml by range request
  tools/fetch_cern.py --dir DIR          somewhere other than build/cern

`gen/cern/README.md` says why each file is listed.

The multi-gigabyte files are never downloaded. root.cern serves
`Accept-Ranges: bytes`, so `--headers` reads each one's header, free-segment
record, top directory record and key list (about 1.5 KB) and checks them
against the facts recorded in `gen/cern/LARGE.toml`. This is the only check of
the large-file layout of `spec/01-container/`; no fixture covers it.
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


def top_directory_problems(header, directory, list_key, keys) -> list[str]:
    """LargeFiles.md section 8, invariants 6 and 7, on the top directory.

    `directory` is the rootfile.Directory read out of the record at fBEGIN,
    `list_key` the key of its key-list record and `keys` the key images in that
    list. Invariant 6 is the free record's rule applied to every other wide key
    available; 7 is TDirectoryFile::FillBuffer's condition
    (root/io/io/src/TDirectoryFile.cxx:751-759).
    """
    out = []
    offsets = (directory.seek_dir, directory.seek_parent, directory.seek_keys)
    if (directory.version > 1000) != (max(offsets) > BIG):
        out.append(f"the top directory record has version {directory.version} "
                   f"and offsets {offsets} (LargeFiles 8.7)")
    named = [("the key list's own key", list_key)]
    named += [(f"key {k.name};{k.cycle}", k) for k in keys]
    for what, k in named:
        if k.key_version <= 1000:
            continue
        if k.seek_pdir != header.begin:
            out.append(f"{what} has fSeekPdir {k.seek_pdir}, not fBEGIN "
                       f"{header.begin} (LargeFiles 8.6)")
        if k.pid_offset:
            out.append(f"{what} has fPidOffset {k.pid_offset} (LargeFiles 8.6)")
    return out


def read_top_directory(url: str, header):
    """`(directory, list key, key images)` by two more range requests.

    The record at fBEGIN is read into a buffer padded with fBEGIN zero bytes, so
    that rootfile.read_directory's fSeekDir self-check sees true offsets; the key
    list is parsed where it lies, since only its count and images are needed.
    """
    head = fetch_range(url, header.begin, 1024)
    nbytes = struct.unpack_from(">i", head)[0]
    if nbytes > len(head):
        head = fetch_range(url, header.begin, nbytes)
    padded = bytes(header.begin) + head[:nbytes]
    record, _ = rootfile._read_key_at(padded, header.begin)
    directory = rootfile.read_directory(padded, record)
    if directory is None:
        raise rootfile.FormatError(f"no directory record at fBEGIN {header.begin}")
    chunk = fetch_range(url, directory.seek_keys, directory.nbytes_keys)
    list_key, _ = rootfile._read_key_at(chunk, 0)
    at = list_key.key_len
    count = struct.unpack_from(">i", chunk, at)[0]
    at += 4
    keys = []
    for _ in range(count):
        key, at = rootfile._read_key_at(chunk, at)
        keys.append(key)
    return directory, list_key, keys


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


def large_url(row: dict) -> str:
    """Where a LARGE.toml row is read from: `path` under root.cern, or `url`.

    Exactly one of the two. `url` is for files outside root.cern: CERN Open
    Data serves the same `Accept-Ranges: bytes` from `https://opendata.cern.ch`
    followed by the EOS path of a record's `root://eospublic.cern.ch/` URI.
    """
    if ("path" in row) == ("url" in row):
        raise ValueError(f"a LARGE.toml row needs exactly one of path and url: "
                         f"{row.get('path') or row.get('url')!r}")
    return row["url"] if "url" in row else BASE + row["path"]


def check_headers() -> int:
    """Verify every LARGE.toml entry with four range requests."""
    spec = tomllib.loads(LARGE.read_text())
    bad = 0
    for want in spec["file"]:
        url = large_url(want)
        name = url.rsplit("/", 1)[-1]
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
            directory, list_key, keys = read_top_directory(url, header)
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
            "dir_version": directory.version,
            "fseekkeys": directory.seek_keys,
            "nbyteskeys": directory.nbytes_keys,
            "nkeys": len(keys),
            "keys_large": sum(k.key_version > 1000 for k in keys),
            "max_seekkey": max((k.seek_key for k in keys), default=0),
        }
        for field, value in got.items():
            if want.get(field) != value:
                problems.append(f"{field}: recorded {want.get(field)!r}, "
                                f"measured {value!r}")
        # The invariants LargeFiles.md section 8 states, checked here because no
        # local file is large enough to exercise them.
        problems.extend(large_file_problems(header, record, triples))
        problems.extend(top_directory_problems(header, directory, list_key,
                                               keys))
        if problems:
            bad += 1
            for problem in problems:
                print(f"FAIL {name}: {problem}", file=sys.stderr)
        else:
            print(f"  ok  {name[:44]:44} {got['root']}  "
                  f"{'large' if header.version >= 1000000 else 'small'} format, "
                  f"fEND {header.end}, {header.nfree} free "
                  f"({got['free_large']} of them 18-byte), "
                  f"{len(keys)} top key(s) ({got['keys_large']} wide)")
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
    if tier not in ("core", "physics", "geometry", "all"):
        raise SystemExit(f"unknown tier {tier!r}: core, physics, geometry or all")
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
