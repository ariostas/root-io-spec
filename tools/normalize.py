#!/usr/bin/env python3
"""Timestamp- and UUID-masked digests for reference files.

ROOT files cannot be reproduced byte-for-byte: every `TKey` records the wall
clock in `fDatime`, and every file gets a fresh `TUUID`. To still detect real
format changes, we digest a *normalized* copy in which those fields are
overwritten with zeros.

Masking strategy (deliberately blunt, and stated here because it is a tradeoff):

  * the file header's 16 UUID bytes, located by parsing the header;
  * every record's `fDatime`, located by walking the record chain;
  * every directory record's own UUID and its `fDatimeC`/`fDatimeM`, located by
    parsing the directory structure -- each directory carries a *distinct* UUID,
    so the file-level one is not enough;
  * every further occurrence, anywhere in the file, of any UUID or `fDatime`
    value found above;
  * every canonical UUID *string*, found by pattern. A `TProcessID` record
    carries its process UUID as 36 ASCII characters in both the key title and
    the payload, and that UUID is unrelated to the file's own.

The last rule catches further copies without this tool having to chase them. It
can in principle mask a coincidentally equal run of payload bytes; for the small,
hand-authored fixtures in `data/` that is acceptable, and a spurious mask is
stable across runs so it cannot cause a false digest mismatch.
"""

from __future__ import annotations

import hashlib
import re
import struct
import sys

import rootfile


# A TUUID rendered as text, e.g. "33f12151-b110-11f1-94cd-b10c080abeef".
UUID_TEXT = re.compile(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                       rb"[0-9a-f]{4}-[0-9a-f]{12}")


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

        directory = rootfile.read_directory(buf, rec)
        if directory is None:
            continue
        if directory.uuid:
            out[directory.uuid_offset : directory.uuid_offset + 16] = b"\0" * 16
            if any(directory.uuid):
                volatile.append(directory.uuid)
        out[directory.datime_offset : directory.datime_offset + 8] = b"\0" * 8
        for value in (directory.datime_c, directory.datime_m):
            if value:
                volatile.append(struct.pack(">I", value))

    for match in UUID_TEXT.finditer(buf):
        out[match.start() : match.end()] = b"0" * (match.end() - match.start())

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
