#!/usr/bin/env python3
"""Timestamp- and UUID-masked digests for reference files.

ROOT files cannot be reproduced byte-for-byte: every `TKey` records the wall
clock in `fDatime`, and every file gets a fresh `TUUID`. To still detect real
format changes, we digest a *normalized* copy in which those fields are
overwritten with zeros.

Masking strategy (deliberately blunt, and stated here because it is a tradeoff):

  * the file header's 16 UUID bytes, located by parsing the header;
  * every record's `fDatime`, located by walking the record chain;
  * every further occurrence, anywhere in the file, of the UUID byte string or
    of any `fDatime` value observed in a key.

The last rule catches the copies that `TDirectory` keeps in its own record
(`fDatimeC`, `fDatimeM`, and the directory UUID) without this tool having to
parse directory payloads. It can in principle mask a coincidentally equal run
of payload bytes; for the small, hand-authored fixtures in `data/` that is
acceptable, and a spurious mask is stable across runs so it cannot cause a
false digest mismatch.
"""

from __future__ import annotations

import hashlib
import struct
import sys

import rootfile


def normalize(buf: bytes) -> bytes:
    header = rootfile.read_header(buf)
    out = bytearray(buf)
    volatile: list[bytes] = []

    out[header.uuid_offset : header.uuid_offset + 16] = b"\0" * 16
    if any(header.uuid):
        volatile.append(header.uuid)

    for rec in rootfile.read_records(buf, header):
        if rec.free:
            continue
        out[rec.datime_offset : rec.datime_offset + 4] = b"\0" * 4
        if rec.datime:
            volatile.append(struct.pack(">I", rec.datime))

    for pattern in volatile:
        start = 0
        while (i := out.find(pattern, start)) != -1:
            out[i : i + len(pattern)] = b"\0" * len(pattern)
            start = i + len(pattern)
    return bytes(out)


def digest(path) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(normalize(fh.read())).hexdigest()


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(f"{digest(path)}  {path}")
