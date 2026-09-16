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
    the payload, and that UUID is unrelated to the file's own;
  * every `TStreamerElement::fSize` in an uncompressed `StreamerInfo` record.
    `fSize` is `sizeof` on the *writing* machine, and it differs between standard
    libraries for several ordinary types -- `sizeof(std::string)` is 24 with
    libc++ and 32 with libstdc++, `sizeof(std::map<int,int>)` 24 and 48. Without
    this, a fixture containing a `std::map` or `std::string` member drifts between
    macOS and Linux CI while every byte assertion passes and the file size is
    identical. A reader MUST NOT use `fSize` for anything, so masking it costs no
    coverage of the format -- but it does stop the digest noticing if ROOT ever
    changed *which* value it stores there, so cases SHOULD assert `fSize`
    directly for members whose `sizeof` is standard-library independent.

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

    info = next((r for r in rootfile.read_records(buf, header)
                 if not r.free and r.name == "StreamerInfo"
                 and r.class_name == "TList" and not rootfile.is_compressed(r)), None)
    if info is not None:
        try:
            for streamer in rootfile.read_streamer_infos(buf, info):
                for element in streamer.elements:
                    at = element.fsize_offset
                    if at >= 0:
                        out[at : at + 4] = b"\0" * 4
        except (rootfile.FormatError, struct.error, IndexError, ValueError):
            pass    # an unparseable record is a failure for check_invariants

    # Two further sources of drift between standard libraries, both inside a
    # TTree record, both found by diffing a Linux container's output against a
    # macOS one. PLAN.md section 9.6 records the diagnosis.
    if info is not None:
        try:
            infos = rootfile.read_streamer_infos(buf, info)
        except (rootfile.FormatError, struct.error, IndexError, ValueError):
            infos = []
        for rec in rootfile.read_records(buf, header):
            if (rec.free or not rec.key_len or rootfile.is_compressed(rec)
                    or not rootfile.derives_from(infos, rec.class_name or "", "TTree")):
                # A compressed record is skipped: the offsets a decode reports
                # are into the decompressed copy and would mask the wrong bytes.
                continue
            try:
                value = rootfile.decode_record(buf, rec, infos)
            except (rootfile.FormatError, rootfile.UnsupportedClass, struct.error,
                    IndexError, ValueError, KeyError):
                continue
            try:
                tree = rootfile.read_tree(buf, value, rec.offset)
            except (rootfile.FormatError, rootfile.UnsupportedClass, struct.error,
                    IndexError, ValueError, KeyError):
                tree = None
            for at, width in _tree_volatile(buf, value, tree):
                out[at : at + width] = b"\0" * width

    for match in UUID_TEXT.finditer(buf):
        out[match.start() : match.end()] = b"0" * (match.end() - match.start())

    for pattern in volatile:
        start = 0
        while (i := out.find(pattern, start)) != -1:
            out[i : i + len(pattern)] = b"\0" * len(pattern)
            start = i + len(pattern)
    return bytes(out)


def record_digests(buf: bytes) -> list[tuple[int, str, str, str]]:
    """A digest per record of an already-normalized buffer.

    Used to explain a drift: comparing these against another machine's tells you
    which record differs, which is otherwise guesswork.
    """
    header = rootfile.read_header(buf)
    out = []
    for rec in rootfile.read_records(buf, header):
        end = rec.offset + abs(rec.nbytes)
        d = hashlib.sha256(buf[rec.offset:end]).hexdigest()[:16]
        out.append((rec.offset, rec.class_name or "<free>", rec.name or "", d))
    return out


#: Offset of fDatime within a TKey: fNbytes, fVersion, fObjlen come first.
#: spec/01-container/Record.md section 2.
KEY_DATIME_OFFSET = 10


def _tree_volatile(buf: bytes, value, tree=None) -> list[tuple[int, int]]:
    """Byte ranges inside a decoded TTree record that are not portable.

    Two of them, and neither is reachable by the record walk above:

    * **An embedded basket's `TKey::fDatime`.** A basket streamed into another
      buffer carries a whole key inside object data
      (spec/04-ttree/TBasket.md section 4.1), so its fDatime is the fDatime of no
      record. Its value depends on the writer's time zone -- it read
      `2033-12-31 19:00:00` at UTC-5 against `2034-01-01 00:00:00` in a
      container, which is one instant written two ways.

    * **`TBranchElement::fCheckSum`, but only when `fClassName` is an STL type.**
      A checksum folds in each member's resolved type name, and libc++ and
      libstdc++ spell those differently, so `vector<SHit>` hashes to 66eb45ed on
      one and 01c8a81d on the other. Masked for those classes alone: for an
      ordinary class the checksum is stable across both, and the digest should go
      on watching it.
    """
    spans: list[tuple[int, int]] = []

    def walk(val) -> None:
        for member in (val.members or []):
            if member.type_name == "TBranchElement":
                named = rootfile._named(buf, member.members or [])
                name_at = named.get("fClassName")
                sum_at = named.get("fCheckSum")
                if name_at is not None and sum_at is not None:
                    cls = rootfile._string_at(buf, name_at)
                    if rootfile.is_collection_name(cls) or cls.startswith("pair<"):
                        spans.append((sum_at.start, sum_at.end - sum_at.start))
            walk(member)

    walk(value)
    # The embedded baskets, through read_tree rather than by walking the value
    # tree: the Value that carries the note is the object *slot*, and the key
    # begins after the class record, which only the basket reader resolves.
    for branch in (rootfile.walk_branches(tree.branches) if tree else []):
        for embedded in (branch.embedded or {}).values():
            spans.append((embedded.start + KEY_DATIME_OFFSET, 4))
            if embedded.block >= 0:
                # And once more inside the raw buffer copy, which begins with
                # the key all over again (spec/04-ttree/TBasket.md 4.1). Two
                # fDatime per embedded basket, not one.
                spans.append((embedded.block + KEY_DATIME_OFFSET, 4))
    return spans


def member_lines(buf: bytes, want: str | None = None) -> list[str]:
    """One line per decoded member of every record, for explaining a drift.

    `record_digests` says which *record* differs; this says which member of it.
    CI cannot diff against the other machine's bytes -- it only has the file it
    just wrote -- so the report has to be a canonical dump that a human diffs
    against the same command run elsewhere.

    Offsets are deliberately absent: a member that grows shifts everything after
    it, and a diff full of shifted offsets hides the one line that matters. Each
    line carries the member's path, its type, its length, and its bytes when they
    are short enough to read.

    `want` limits the dump to records of one class. The buffer must already be
    normalized, so a masked field never shows up as a difference.
    """
    header = rootfile.read_header(buf)
    records = rootfile.read_records(buf, header)
    infos: list = []
    for rec in records:
        if not rec.free and rec.key_len and rec.name == "StreamerInfo":
            try:
                infos = rootfile.read_streamer_infos(rootfile.object_data(buf, rec), rec)
            except Exception:
                pass

    out: list[str] = []

    def walk(value, prefix: str) -> None:
        for n, member in enumerate(value.members or []):
            name = member.name or member.type_name or f"[{n}]"
            path = f"{prefix}.{name}" if prefix else name
            width = member.end - member.start
            raw = buf[member.start:member.end]
            shown = (raw.hex(" ") if 0 < width <= 16
                     else hashlib.sha256(raw).hexdigest()[:16])
            out.append(f"    {path:52} t{member.ftype:<4} {width:6} {shown}")
            walk(member, path)

    for rec in records:
        if rec.free or not rec.key_len:
            continue
        if want is not None and rec.class_name != want:
            continue
        if rec.class_name in ("TBasket",):
            continue                      # entry data, not a member tree
        try:
            data = rootfile.object_data(buf, rec)
            _, value = rootfile.decode_record_verbose(data, rec, infos,
                                                      tolerant=True)
        except Exception as exc:
            out.append(f"    <{rec.class_name} {rec.name!r}: {exc}>")
            continue
        if value is None:
            continue
        out.append(f"  {rec.class_name} {rec.name!r}:")
        walk(value, "")
    return out


def digest(path) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(normalize(fh.read())).hexdigest()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if any(a.startswith("--members") for a in sys.argv[1:]):
        want = None
        for a in sys.argv[1:]:
            if a.startswith("--members="):
                want = a.split("=", 1)[1]
        for path in args:
            print(path)
            with open(path, "rb") as fh:
                for line in member_lines(normalize(fh.read()), want):
                    print(line)
    elif "--per-record" in sys.argv:
        for path in args:
            print(path)
            with open(path, "rb") as fh:
                for offset, cls, name, d in record_digests(normalize(fh.read())):
                    print(f"  {offset:9} {cls:14} {name[:24]:24} {d}")
    else:
        for path in args:
            print(f"{digest(path)}  {path}")
