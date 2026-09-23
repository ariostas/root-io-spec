#!/usr/bin/env python3
"""Verify the byte-level assertions in a fixture's `case.toml`.

Each `[[bytes]]` entry names an absolute file offset, a type, and the expected
value. The byte tables in `spec/` and these assertions are written from the same
reading, so a mistake in either shows up as a failure. It needs no ROOT
installation, so a third party can use the fixtures directly.
"""

from __future__ import annotations

import struct
import sys
import tomllib
from pathlib import Path

# Big-endian by default: the TFile container and the TBuffer object layers are
# big-endian regardless of host byte order (spec/00-conventions.md 3).
#
# The `le` suffix is for RNTuple, whose envelopes and pages are little-endian.
# Only its anchor, a TKey payload like any other, is big-endian, so one fixture
# needs both and must say which at every offset. See spec/05-rntuple/NOTES.md 3.
FORMATS = {
    "i8": ">b", "u8": ">B", "i16": ">h", "u16": ">H",
    "i32": ">i", "u32": ">I", "i64": ">q", "u64": ">Q",
    "f32": ">f", "f64": ">d",
    "i16le": "<h", "u16le": "<H",
    "i32le": "<i", "u32le": "<I", "i64le": "<q", "u64le": "<Q",
    "f32le": "<f", "f64le": "<d",
}


def check(buf: bytes, assertions: list[dict], label: str) -> list[str]:
    failures = []
    for a in assertions:
        off, want, name = a["offset"], a["value"], a.get("name", "")
        kind = a["type"]
        where = f"{label}: offset {off} ({name})" if name else f"{label}: offset {off}"
        if kind == "bytes":
            want = want.encode("latin-1") if isinstance(want, str) else bytes(want)
            got = buf[off : off + len(want)]
        elif kind == "string":
            # counted string: one length byte, then that many bytes
            n = buf[off]
            got, want = buf[off + 1 : off + 1 + n].decode("latin-1"), str(want)
        elif kind in FORMATS:
            got = struct.unpack_from(FORMATS[kind], buf, off)[0]
        else:
            failures.append(f"{where}: unknown type {kind!r}")
            continue
        if got != want:
            failures.append(f"{where}: expected {want!r}, got {got!r}")
    return failures


def main(case_dirs: list[str]) -> int:
    repo = Path(__file__).resolve().parent.parent
    failures, checked = [], 0
    for case_dir in case_dirs:
        case = tomllib.loads((Path(case_dir) / "case.toml").read_text())
        path = repo / case["file"]
        if not path.exists():
            failures.append(f"{case['id']}: {case['file']} missing; run tools/generate.py")
            continue
        buf = path.read_bytes()
        # `size` is optional: a case whose file length differs between platforms
        # cannot assert one. So far only serialization/pairs omits it; its
        # case.toml gives the reason.
        if "size" in case and len(buf) != case["size"]:
            failures.append(f"{case['id']}: size {len(buf)}, expected {case['size']}")
        assertions = case.get("bytes", [])
        failures += check(buf, assertions, case["id"])
        checked += len(assertions)
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    print(f"{checked} byte assertions checked across {len(case_dirs)} case(s), "
          f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    dirs = sys.argv[1:] or [str(p.parent) for p in
                            sorted((Path(__file__).resolve().parent.parent / "gen/cases")
                                   .rglob("case.toml"))]
    sys.exit(main(dirs))
