#!/usr/bin/env python3
"""Publish the streamer-info element lists a writer has to emit.

`spec/06-writing/` specifies the `StreamerInfo` record exactly -- its nesting,
its option bytes, its checksum algorithm -- and each class document says *which*
classes a file needs an info for. What it did not say until now is what goes
*in* each of those infos: the member list, with every field of every
`TStreamerElement`. Those lists lived only in `tools/rootwrite.py`, which made
the writing layer unimplementable from the prose alone -- the one gap in it that
a third party could not work around without reading this project's code.

This extracts them from the **reference files ROOT wrote** and writes them into
`spec/06-writing/ElementLists.md`, so the published tables are evidence about
ROOT rather than a transcription of `rootwrite.py`. Six fixtures between them
carry every class:

    data/classes/histogram.root        the fifteen infos of a TH1F/TH1D file
    data/ttree/basket.root             the eighteen of a flat TTree file
    data/classes/th2-profile.root      TH2, TH2F, TH2D and TProfile, and TH1D
                                       for a second time
    data/classes/tarray-histogram.root TArray, TArrayF and TArrayD, which a
                                       histogram file does not describe at all
    data/container/file-minimal.root   TObjString, the one info a file holding a
                                       single object carries
    data/ttree/strings.root            TLeafC, which only a string branch pulls in

and every class the fixtures share is compared across them, so a table can only
be published when every file that carries the class agrees on it, field for
field.

Three checks run in the same pass, and each closes a hole that a published table
would otherwise open:

**Against the writer.** Every field of every element is compared with
`rootwrite.histogram_infos`, `rootwrite.tree_infos` and `rootwrite.InfoSet`.
That is stricter than the element-by-element comparison in
`tools/test_write.py`, which stops at the `TStreamerElement` base and does not
look at the subclass tail -- and the difference was not academic: it is what
hid four wrong values in `rootwrite.py` (a `vector<string>`'s `fCtype`, a
counter's promoted `fType`, a basic pointer's `fSize` and the class a counter is
declared in), all of them in fields the checksum does not fold.

**Against the checksum algorithm.** Each published element list is fed to
`StreamerInfo.md` §11 and the result compared with the `fCheckSum` beside it, so
a table is only published when it is *sufficient* to produce the checksum a
writer has to emit. Two classes cannot pass and are named: `THashList` and
`TSeqCollection` are class version 0, so their infos omit the members their
checksums fold (§11.2).

**Against the document.** `--check` fails if the tables in `spec/` have drifted
from the fixtures, which is what CI runs.

    tools/element_lists.py          # rewrite the generated blocks
    tools/element_lists.py --check  # fail if they are stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import rootfile                                            # noqa: E402
import rootwrite as rw                                     # noqa: E402

DOCUMENT = REPO / "spec/06-writing/ElementLists.md"

BEGIN = "<!-- BEGIN GENERATED: {} -->"
END = "<!-- END GENERATED -->"

#: The reference files the tables are read out of. Every one was written by
#: ROOT, which is what makes the published values evidence rather than a
#: restatement of `tools/rootwrite.py`.
SOURCES = (
    "data/classes/histogram.root",
    "data/ttree/basket.root",
    "data/classes/th2-profile.root",
    "data/classes/tarray-histogram.root",
    "data/container/file-minimal.root",
    "data/ttree/strings.root",
)

#: The six groups, each in bases-first order: a base's checksum is folded into
#: the checksum of every class that inherits it (`StreamerInfo.md` §11 step 2),
#: so this is the order a writer has to compute them in, and reading the tables
#: in it means never meeting a checksum before the table that produces it.
GROUPS = {
    "shared": ("TObject", "TNamed", "TString", "TAttLine", "TAttFill",
               "TAttMarker", "TCollection", "TSeqCollection", "TList"),
    "histogram": ("THashList", "TAttAxis", "TAxis", "TH1", "TH1F", "TH1D"),
    "derived": ("TH2", "TH2F", "TH2D", "TProfile"),
    "tree": ("TObjArray", "ROOT::TIOFeatures", "TLeaf", "TLeafI", "TLeafF",
             "TLeafC", "TBranch", "TRefTable", "TBranchRef", "TTree"),
    "arrays": ("TArray", "TArrayF", "TArrayD"),
    "objstring": ("TObjString",),
}

#: The infos a file of each kind carries, in the order ROOT writes them --
#: registration order, which is neither alphabetical nor dependency order. A
#: reader does not care; a writer that wants a byte-identical record does.
WRITE_ORDER = {
    "histogram": (
        "A histogram file", "data/classes/histogram.root",
        ("TH1F", "TH1", "TNamed", "TObject", "TAttLine", "TAttFill",
         "TAttMarker", "TAxis", "TAttAxis", "THashList", "TList",
         "TSeqCollection", "TCollection", "TString", "TH1D")),
    "th2-profile": (
        "A TH2 and TProfile file", "data/classes/th2-profile.root",
        ("TH2F", "TH2", "TH1", "TNamed", "TObject", "TAttLine", "TAttFill",
         "TAttMarker", "TAxis", "TAttAxis", "THashList", "TList",
         "TSeqCollection", "TCollection", "TString", "TH2D", "TProfile",
         "TH1D")),
    "tree": (
        "A flat tree file", "data/ttree/basket.root",
        ("TTree", "TNamed", "TObject", "TAttLine", "TAttFill", "TAttMarker",
         "ROOT::TIOFeatures", "TBranch", "TLeafI", "TLeaf", "TLeafF", "TList",
         "TSeqCollection", "TCollection", "TString", "TBranchRef", "TRefTable",
         "TObjArray")),
    "objstring": (
        "A file of one object", "data/container/file-minimal.root",
        ("TObjString",)),
    "strings": (
        "A tree with a string branch", "data/ttree/strings.root",
        ("TTree", "TNamed", "TObject", "TAttLine", "TAttFill", "TAttMarker",
         "ROOT::TIOFeatures", "TBranch", "TLeafI", "TLeaf", "TLeafC", "TList",
         "TSeqCollection", "TCollection", "TString", "TBranchRef", "TRefTable",
         "TObjArray")),
}

#: A class version 0 info lists no members while its checksum folds them
#: (`StreamerInfo.md` §11.2), so its element list cannot produce its checksum
#: and a writer has to carry the value as a constant.
NOT_RECOMPUTABLE = {"THashList", "TSeqCollection"}

#: `ClassDef` declares no version for these, so `tools/check_versions.py` has
#: nothing to compare against and the class-version table leaves them out. A
#: foreign class's info records version 1 and its objects carry a version word
#: of 0 (`WritingObjects.md` §2).
NO_CLASSDEF = {"ROOT::TIOFeatures"}

#: Element type codes below `kOffsetL`, for the `fType` column's mnemonic. The
#: table in `ElementTypes.md` §1 is the full list; this covers what the
#: the published classes use, and an unknown code is printed bare rather than
#: guessed at.
TYPE_NAMES = {
    0: "kBase", 1: "kChar", 2: "kShort", 3: "kInt", 4: "kLong", 5: "kFloat",
    6: "kCounter", 7: "kCharStar", 8: "kDouble", 9: "kDouble32",
    11: "kUChar", 12: "kUShort", 13: "kUInt", 14: "kULong", 15: "kBits",
    16: "kLong64", 17: "kULong64", 18: "kBool", 19: "kFloat16",
}

#: And the codes above it, which take no `kOffsetL`/`kOffsetP` suffix.
OBJECT_TYPE_NAMES = {
    61: "kObject", 62: "kAny", 63: "kObjectp", 64: "kObjectP", 65: "kTString",
    66: "kTObject", 67: "kTNamed", 68: "kAnyp", 69: "kAnyP", 500: "kStreamer",
    501: "kStreamLoop",
}

#: `fSTLtype`, ROOT's `ESTLType` (`root/core/foundation/inc/ESTLType.h`).
STL_TYPES = {
    1: "vector", 2: "list", 3: "deque", 4: "map", 5: "multimap", 6: "set",
    7: "multiset", 8: "unordered_set", 9: "unordered_multiset",
    10: "unordered_map", 11: "unordered_multimap", 12: "bitset",
    13: "forward_list",
}


def type_mnemonic(code: int) -> str:
    """`43` as `kInt + kOffsetP`, and `62` as `kAny`.

    `kOffsetL` (20) marks a fixed-length array and `kOffsetP` (40) a
    counted one; both are added to the element type, and only for the types
    below 20 (`ElementTypes.md` §1).
    """
    if code in OBJECT_TYPE_NAMES:
        return OBJECT_TYPE_NAMES[code]
    for offset, suffix in ((40, " + kOffsetP"), (20, " + kOffsetL")):
        if offset <= code < offset + 20 and code - offset in TYPE_NAMES:
            return TYPE_NAMES[code - offset] + suffix
    return TYPE_NAMES.get(code, "")


def infos_of(path: str) -> dict[str, rootfile.StreamerInfo]:
    """Every streamer info in one reference file, by class name."""
    buf, header, records = rootfile.load(REPO / path)
    at = [r for r in records if r.offset == header.seek_info]
    if not at:
        sys.exit(f"{path}: no StreamerInfo record")
    data = rootfile.object_data(buf, at[0])
    return {i.name: i for i in rootfile.read_streamer_infos(data, at[0])}


def fields(element) -> tuple:
    """Every field of one element that the tables publish.

    `fMaxIndex[1]` is masked to 32 bits unsigned: it carries a base class's
    checksum, which reads back negative when its top bit is set (`StreamerInfo.md`
    §9).
    """
    return (element.cls, element.version, element.name, element.title,
            element.ftype, element.fsize, element.array_length,
            element.array_dim,
            tuple(v & 0xFFFFFFFF for v in element.max_index),
            element.type_name, tuple(sorted(element.tail.items())),
            element.bits)


def collect() -> tuple[dict, list[str]]:
    """The infos to publish, and every disagreement between the fixtures.

    A class carried by more than one file is published only if all of them
    agree on it field for field. They are independent ROOT runs, so a difference
    would mean the value is not a property of the class.
    """
    published: dict[str, rootfile.StreamerInfo] = {}
    problems: list[str] = []
    for path in SOURCES:
        for name, info in infos_of(path).items():
            first = published.get(name)
            if first is None:
                published[name] = info
                continue
            mine = (info.class_version, info.checksum,
                    [fields(e) for e in info.elements])
            theirs = (first.class_version, first.checksum,
                      [fields(e) for e in first.elements])
            if mine != theirs:
                problems.append(f"{name}: {path} disagrees with the fixture "
                                f"the table was read from")
    wanted = {n for names in GROUPS.values() for n in names}
    for name in sorted(wanted - set(published)):
        problems.append(f"{name}: no reference file carries an info for it")
    return {n: published[n] for n in wanted if n in published}, problems


def writer_infos() -> dict[str, rw.Info]:
    """The same classes as `tools/rootwrite.py` builds them.

    `InfoSet` is used directly for the `TArray` family: no file describes those
    three, so the writer needs them for their checksums alone
    (`WritingObjects.md` §7.2) and never emits them.
    """
    arrays = rw.InfoSet()
    arrays.common()
    arrays.arrays()
    out: dict[str, rw.Info] = {}
    for info in (list(rw.histogram_infos(("TH1F", "TH1D")))
                 + list(rw.histogram_infos(("TH2F", "TH2D", "TProfile")))
                 + list(rw.tree_infos(("I", "F", "C")))
                 + [arrays.by_name[n] for n in GROUPS["arrays"]]
                 + [rw.objstring_info()]):
        out[info.name] = info
    return out


def writer_fields(element: rw.Element) -> tuple:
    """`fields()` for an element in the form `tools/rootwrite.py` holds it."""
    if element.cls == "TStreamerBase":
        tail = {"fBaseVersion": element.base_version or 0}
    elif element.cls in ("TStreamerBasicPointer", "TStreamerLoop"):
        tail = {"fCountVersion": element.count_version,
                "fCountName": element.count_name,
                "fCountClass": element.count_class}
    elif element.cls == "TStreamerSTL":
        tail = {"fSTLtype": element.stl_type, "fCtype": element.ctype}
    else:
        tail = {}
    return (element.cls, rw.ELEMENT_VERSIONS[element.cls], element.name,
            element.title, element.ftype, element.size, element.array_length,
            element.array_dim,
            tuple(v & 0xFFFFFFFF for v in element.indices()),
            element.type_name, tuple(sorted(tail.items())), 0)


def compare_with_writer(published: dict) -> list[str]:
    """Every field of every element, against `tools/rootwrite.py`.

    The writer is an independent implementation of the same tables, so a
    difference is a bug in one of them and has to be resolved before either can
    be published.
    """
    ours = writer_infos()
    problems = []
    for name, info in published.items():
        mine = ours.get(name)
        if mine is None:
            problems.append(f"{name}: rootwrite.py builds no info for it")
            continue
        if (mine.class_version, mine.checksum) != (info.class_version,
                                                   info.checksum):
            problems.append(
                f"{name}: rootwrite.py has version {mine.class_version} "
                f"checksum 0x{mine.checksum:08x}, the file has "
                f"{info.class_version} / 0x{info.checksum:08x}")
        if len(mine.elements) != len(info.elements):
            problems.append(f"{name}: rootwrite.py lists "
                            f"{len(mine.elements)} elements, the file "
                            f"{len(info.elements)}")
            continue
        for a, b in zip(mine.elements, info.elements):
            if writer_fields(a) != fields(b):
                for x, y, label in zip(writer_fields(a), fields(b), (
                        "element class", "element version", "fName", "fTitle",
                        "fType", "fSize", "fArrayLength", "fArrayDim",
                        "fMaxIndex", "fTypeName", "the subclass tail",
                        "fBits")):
                    if x != y:
                        problems.append(
                            f"{name}.{b.name}: rootwrite.py has {label} {x!r}, "
                            f"the file {y!r}")
    return problems


def check_checksums(published: dict) -> list[str]:
    """Is each published element list enough to produce its own checksum?

    `StreamerInfo.md` §11 applied to the table beside the value. A class that
    fails and is not in `NOT_RECOMPUTABLE` means the table is missing something
    a writer needs.
    """
    problems = []
    for name, info in sorted(published.items()):
        elements = [
            rw.Element(cls=e.cls, name=e.name, title=e.title, ftype=e.ftype,
                       size=e.fsize, type_name=e.type_name,
                       array_length=e.array_length, array_dim=e.array_dim,
                       max_index=tuple(e.max_index),
                       base_checksum=e.max_index[1] & 0xFFFFFFFF,
                       is_enum=rw.looks_like_enum(e.ftype, e.type_name))
            for e in info.elements]
        got = rw.checksum(rw.Info(name, info.class_version, elements))
        agrees = got == info.checksum
        if agrees and name in NOT_RECOMPUTABLE:
            problems.append(f"{name}: listed as not recomputable, but the "
                            f"table now produces 0x{got:08x}")
        elif not agrees and name not in NOT_RECOMPUTABLE:
            problems.append(f"{name}: the published elements produce "
                            f"0x{got:08x}, not 0x{info.checksum:08x}")
    return problems


def extra(element) -> str:
    """The `Extra` column: whatever the element's subclass adds to the base."""
    parts = []
    if element.cls == "TStreamerBase":
        parts.append(f"base version {element.tail.get('fBaseVersion', 0)}")
        parts.append(f"base checksum `0x{element.base_checksum:08x}`")
    elif element.cls in ("TStreamerBasicPointer", "TStreamerLoop"):
        parts.append(f"counter `{element.tail.get('fCountName', '')}` in "
                     f"`{element.tail.get('fCountClass', '')}` at version "
                     f"{element.tail.get('fCountVersion', 0)}")
    elif element.cls == "TStreamerSTL":
        stl = element.tail.get("fSTLtype", 0)
        name = STL_TYPES.get(stl)
        parts.append(f"`fSTLtype` {stl}" + (f" ({name})" if name else ""))
        ctype = element.tail.get("fCtype", 0)
        mnemonic = type_mnemonic(ctype)
        parts.append(f"`fCtype` {ctype}"
                     + (f" (`{mnemonic}`)" if mnemonic else ""))
    if element.array_length:
        extents = ", ".join(str(v) for v in
                            element.max_index[:element.array_dim])
        parts.append(f"`fArrayLength` {element.array_length}, `fArrayDim` "
                     f"{element.array_dim}, extents {extents}")
    if element.has_range:
        parts.append("`kHasRange`: the title carries a `Double32_t` range")
    return "; ".join(parts)


def render_class(info) -> list[str]:
    """One class: a heading, its identity, and its element table."""
    mnemonic = ""
    if info.name in NOT_RECOMPUTABLE:
        mnemonic = (", **not** reproducible from the table below "
                    "([§2](#2-what-the-tables-do-not-and-cannot-give-you))")
    count = len(info.elements)
    lines = [
        f"### `{info.name}`",
        "",
        f"Class version **{info.class_version}**, `fCheckSum` "
        f"**`0x{info.checksum:08x}`**{mnemonic}. "
        + (f"{count} element{'s' if count != 1 else ''}."
           if count else "No elements at all."),
    ]
    if not count:
        return lines
    lines += [
        "",
        "| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` "
        "| Extra | `fTitle` |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, element in enumerate(info.elements, 1):
        mnemonic = type_mnemonic(element.ftype)
        code = f"{element.ftype}" + (f" `{mnemonic}`" if mnemonic else "")
        if "`" in element.title or "|" in element.title:
            # The column publishes the title verbatim as inline code, which
            # only works while no title contains a backtick or a pipe. None of
            # the 743 in the reference files does; say so rather than mangle
            # one silently.
            sys.exit(f"{info.name}.{element.name}: a title with a backtick or "
                     f"a pipe cannot be published verbatim")
        title = f"`{element.title}`" if element.title else ""
        lines.append(
            f"| {i} | `{element.cls}` | `{element.name}` | {code} "
            f"| {element.fsize} | `{element.type_name}` | {extra(element)} "
            f"| {title} |")
    return lines


def render_group(published: dict, group: str) -> list[str]:
    lines: list[str] = []
    for name in GROUPS[group]:
        if lines:
            lines.append("")
        lines += render_class(published[name])
    return lines


def render_order(published: dict) -> list[str]:
    lines = []
    for title, path, order in WRITE_ORDER.values():
        lines += [f"**{title}** — {len(order)} infos, as `{path}` carries them:",
                  "", "```"]
        row: list[str] = []
        for name in order:
            row.append(name)
            if len(" ".join(row)) > 62:
                lines.append("  ".join(row))
                row = []
        if row:
            lines.append("  ".join(row))
        lines += ["```", ""]
    return lines[:-1]


def render_versions(published: dict) -> list[str]:
    """A `| Class | Version |` table, which `check_versions.py` then checks.

    That is the point of publishing it separately from the per-class headings:
    the heading states what the file records, and this table is compared with
    `ClassDef` in the pinned submodule, so the two together say that the file's
    value *is* the current version.
    """
    lines = ["| Class | Version | Sets |", "|---|---|---|"]
    for name in sorted(published, key=str.lower):
        if name in NO_CLASSDEF:
            continue
        sets = [kind for kind, (_, _, order) in WRITE_ORDER.items()
                if name in order] or ["neither: no info is written"]
        lines.append(f"| `{name}` | {published[name].class_version} "
                     f"| {', '.join(sets)} |")
    return lines


def render_counts(published: dict) -> list[str]:
    elements = sum(len(i.elements) for i in published.values())
    return [f"**{len(published)} classes, {elements} elements**, every one read "
            f"out of a file ROOT wrote."]


def rebuild(published: dict) -> str:
    lines = DOCUMENT.read_text().splitlines()
    blocks = {
        "counts": render_counts(published),
        "shared": render_group(published, "shared"),
        "histogram": render_group(published, "histogram"),
        "derived": render_group(published, "derived"),
        "tree": render_group(published, "tree"),
        "arrays": render_group(published, "arrays"),
        "order": render_order(published),
        "versions": render_versions(published),
    }
    # Later blocks first, so replacing one does not move the next one's markers.
    found = []
    for name, body in blocks.items():
        begin = BEGIN.format(name)
        try:
            start = lines.index(begin)
        except ValueError:
            sys.exit(f"{DOCUMENT}: no block {begin!r}")
        stop = next((i for i in range(start + 1, len(lines))
                     if lines[i] == END), None)
        if stop is None:
            sys.exit(f"{DOCUMENT}: block {name!r} is not closed")
        found.append((start, stop, body))
    for start, stop, body in sorted(found, reverse=True):
        lines[start + 1:stop] = body
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if the document is stale (what CI runs)")
    args = parser.parse_args(argv)

    published, problems = collect()
    problems += compare_with_writer(published)
    problems += check_checksums(published)

    for problem in problems:
        print(f"UNRESOLVED {problem}", file=sys.stderr)

    wanted = rebuild(published)
    stale = wanted != DOCUMENT.read_text()
    if args.check:
        if stale:
            print(f"STALE {DOCUMENT.relative_to(REPO)} does not match the "
                  f"reference files; run tools/element_lists.py",
                  file=sys.stderr)
    elif not problems:
        DOCUMENT.write_text(wanted)

    elements = sum(len(i.elements) for i in published.values())
    print(f"{len(published)} class(es), {elements} element(s), "
          f"{len(SOURCES)} reference file(s)")
    return 1 if problems or (args.check and stale) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
