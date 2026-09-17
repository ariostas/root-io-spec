#!/usr/bin/env python3
"""Inventory the classes whose `Streamer` is hand-written, and what it does on disk.

`spec/02-serialization/StreamerDriven.md` is the specification for almost every
class in a ROOT file: the streamer info recorded *in the file* describes the
bytes, and a reader needs no per-class knowledge. The exception is a class that
replaces the `Streamer` its `ClassDef` would generate — and **nothing in the file
says which classes those are**. A reader that assumes the streamer info is
authoritative decodes such a class into garbage without any error.

So the set matters, and until now the specification asserted its size from a
spot-check. This extracts it from the pinned submodule instead, and sorts each
member by what its `Streamer` actually does when reading:

`delegating`
    The reading branch calls `ReadClassBuffer` with no version test around it,
    and reads nothing afterwards. The custom code runs *after* the bytes are
    consumed — fixups, caches, back-pointers — so on disk the class is
    indistinguishable from a generated one. **A reader needs nothing.**

`extending`
    The reading branch calls `ReadClassBuffer` and then **reads more bytes of
    its own**. The streamer info describes a prefix of the object and stops;
    what follows it is in no info anywhere, and it is usually outside the byte
    count as well, so `CheckByteCount` does not notice. `TMatrixTSym` is the
    case that forced this category out of `delegating`: it reads the upper-right
    triangle after the base class's members and reconstructs the lower one.
    **These need hand-written text**, like `custom`.

`guarded`
    The reading branch calls `ReadClassBuffer` above a version threshold and
    hand-decodes below it. Current files take the generated path; the custom
    layout is a legacy concern, tracked in `PLAN.md` §9.1.

`custom`
    The reading branch never calls `ReadClassBuffer`. The streamer info does not
    describe the bytes at *any* version. **These need hand-written text**, and a
    class here that the specification does not account for is a hole.

It answers a second question in the same pass, for
`spec/99-appendix/ForwardingStreamers.md`: **which classes write nothing of their
own even though their `Streamer` is generated?** For a `ClassDef` version `<= 0`
selected with a plain `#pragma link C++ class X;` — no `+`, no `-` — `rootcling`
emits a body that calls each base's `Streamer` and returns
(`root/core/dictgen/src/rootcling_impl.cxx:1332-1367`), chosen at
`root/core/clingutils/src/TClingUtils.cxx:3016`. Such a class writes no version
word, no byte count and none of its members, while still recording a streamer
info that lists them. Nothing in a file distinguishes it from a version-0 class
read through `ReadClassBuffer`, so the list has to be published; that is what the
second document is.

Every row carries a `path:line` citation, and every `custom` and `extending` row
must be resolved in `spec/99-appendix/streamers.toml` — to the document that specifies it, or
explicitly to a gap. A submodule bump that adds a hand-written `Streamer` fails
`--check` until someone says which it is, so the list cannot rot silently the way
`tools/test_bootstrap.py` exists to stop the bootstrap list rotting.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SUBMODULE = REPO / "root"
DOCUMENT = REPO / "spec/99-appendix/HandWrittenStreamers.md"
FORWARDING_DOCUMENT = REPO / "spec/99-appendix/ForwardingStreamers.md"
SIDECAR = REPO / "spec/99-appendix/streamers.toml"

#: A definition of `X::Streamer(TBuffer &)`. The class name may carry template
#: arguments (`TParameter<Long64_t>`), which are dropped: the sidecar and the
#: specification name the template, not each specialization. A second parameter
#: is allowed — `ROOT::v5::TFormula` takes an on-file `TClass*` as well.
#:
#: The name may also be **qualified**, as `void ROOT::RNTuple::Streamer` is: a
#: definition written that way is not inside a `namespace` block, so `enclosing`
#: cannot see the qualifier and it has to be read off the definition itself.
#: Without this the inventory silently missed `ROOT::RNTuple`, whose `Streamer`
#: reads a checksum outside the byte count, and `RooWorkspace::CodeRepo`.
#:
#: The buffer parameter's name is captured because `extending` is detected by
#: looking for I/O on *that* name after the `ReadClassBuffer` call; ROOT spells
#: it `R__b`, `b` or `buf` depending on the file.
DEFINITION = re.compile(
    r"\bvoid\s+((?:[A-Za-z_]\w*(?:<[^;{}()]*>)?\s*::\s*)*?)"
    r"([A-Za-z_]\w*)(<[^;{}()]*>)?\s*::\s*Streamer\s*\(\s*TBuffer\s*&\s*(\w+)?")

#: `namespace X {`, and the anonymous form. Classes in an anonymous namespace are
#: file-local and cannot be persisted, so they are dropped rather than reported
#: under a name no file can contain.
NAMESPACE = re.compile(r"\bnamespace\s+([A-Za-z_]\w*)?\s*\{")

#: The variable a hand-written `Streamer` reads its version word into. `rootcling`
#: spells it `R__v` and most hand-edited streamers keep that, but not all:
#: `ROOT::v5::TFormula` and `ROOT::v5::TF1Data` call it `v`. Taking the name from
#: the `ReadVersion` call instead of assuming one avoids classifying a version
#: guard as unconditional delegation, which is the error that would matter — it
#: understates what a reader has to know.
READ_VERSION = re.compile(
    r"\b(?:Version_t|Short_t|Int_t)\s+([A-Za-z_]\w*)\s*=\s*[^;]*\bReadVersion\s*\(")

#: Paths that define classes ROOT does not ship: its own test suite, the
#: tutorials, and generated dictionaries.
EXCLUDED = re.compile(r"/(test|tests|tutorials|roottest)/|Dict\.|\bG__")

SOURCES = ("*.cxx", "*.cc", "*.cu", "*.h", "*.hxx")

BEGIN = "<!-- BEGIN GENERATED: {} -->"
END = "<!-- END GENERATED -->"

KINDS = ("custom", "extending", "guarded", "delegating")

#: The kinds whose bytes a reader has to know, and which the sidecar must resolve.
RESOLVED = ("custom", "extending")


def blank(text: str) -> str:
    """`text` with comments and literals replaced by spaces, length preserved.

    Everything here is done by scanning source text, so a `{` inside a string and
    a `ReadClassBuffer` inside a comment both have to stop counting — the first
    would desynchronize the namespace tracking (`ROOT::v5::TFormula`'s file parses
    formula syntax and is full of braces in string literals), and the second would
    classify a class by code that does not run. Replacing rather than deleting
    keeps every offset and line number the same as in the original.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            out[i] = out[i + 1] = " "
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n
                                 and text[i + 1] == "/"):
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            for _ in range(2):
                if i < n:
                    out[i] = " "
                    i += 1
        elif c in "\"'":
            quote = c
            i += 1
            while i < n and text[i] != quote:
                if text[i] == "\\":
                    out[i] = " "
                    i += 1
                if i < n:
                    if text[i] != "\n":
                        out[i] = " "
                    i += 1
            if i < n:
                out[i] = " "
                i += 1
        else:
            i += 1
    return "".join(out)


def enclosing(text: str, offsets: list[int]) -> dict[int, list[str] | None]:
    """The namespace path around each offset, or `None` inside an anonymous one.

    One linear pass over the braces, with a stack that records which of them
    opened a namespace. `text` must already have been through `blank`.
    """
    opens = {m.end() - 1: m.group(1) for m in NAMESPACE.finditer(text)}
    wanted = sorted(offsets)
    result: dict[int, list[str] | None] = {}
    #: A namespace name, `None` for the anonymous namespace, or `False` for an
    #: ordinary brace.
    stack: list[str | None | bool] = []
    at = 0

    def record(offset: int) -> None:
        if None in stack:
            result[offset] = None
        else:
            result[offset] = [n for n in stack if isinstance(n, str)]

    for i, c in enumerate(text):
        while at < len(wanted) and wanted[at] <= i:
            record(wanted[at])
            at += 1
        if c == "{":
            stack.append(opens[i] if i in opens else False)
        elif c == "}" and stack:
            stack.pop()
    while at < len(wanted):
        record(wanted[at])
        at += 1
    return result


def body(text: str, start: int) -> str | None:
    """The braced body of the definition whose match begins at `start`.

    Returns `None` for a declaration — `template <> void X::Streamer(TBuffer &);`
    — which has no body. Without that check the next unrelated `{` in the file is
    read as the function, which is how a header's forward declaration first came
    out classified as `custom`.
    """
    paren = text.find("(", start)
    if paren < 0:
        return None
    depth = 0
    for i in range(paren, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                rest = text[i + 1:]
                head = rest.lstrip()
                if not head.startswith("{"):
                    return None
                open_brace = len(rest) - len(head)
                break
    else:
        return None

    depth = 0
    for i in range(open_brace, len(rest)):
        if rest[i] == "{":
            depth += 1
        elif rest[i] == "}":
            depth -= 1
            if depth == 0:
                return rest[open_brace:i + 1]
    return None


def _enclosing_block(source: str, start: int) -> str:
    """`source` from `start` to the end of the block that encloses it.

    Stopping at the enclosing `}` is what keeps the *writing* branch out of the
    window: a `Streamer` is `if (R__b.IsReading()) { ... } else { ... }`, so the
    reads in the else-branch are on the far side of a closing brace and are not
    reached from inside the reading one.
    """
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            if depth == 0:
                return source[start:i]
            depth -= 1
    return source[start:]


def reads_after_class_buffer(source: str, buffers: set[str]) -> bool:
    """Does the reading branch consume bytes after `ReadClassBuffer` returns?

    Looked for in the same block as the call and before any `return`, on the
    buffer parameter's own name — so `R__b >> x` and `R__b.ReadFastArray(...)`
    count, and a `memcpy`, a `Clear()` or a `MakeValid()` do not. A second
    `ReadClassBuffer` does not count either: those bytes are described by an
    info like the first lot.

    The window is deliberately narrow. Reads that follow the *whole* if/else,
    rather than the `ReadClassBuffer` branch of it, are not seen — no class in
    the pinned submodule is written that way, and widening the window would
    start counting the legacy branch of every `guarded` streamer instead.

    It also ends at a `return`, a `break` or the next `case` label. `break` and
    `case` are there because of `RooBinning`, which dispatches on the version
    word with a `switch`: its `ReadClassBuffer` and its version-1 legacy decode
    are two cases of one block, so without those terminators the legacy reads
    look like reads after the call (`root/roofit/roofitcore/src/RooBinning.cxx:298`).
    """
    names = "|".join(re.escape(b) for b in sorted(buffers) if b) or "R__b"
    io = re.compile(r"\b(?:%s)\s*(?:>>|\.\s*Read(?!ClassBuffer)\w*\s*\()" % names)
    for call in re.finditer(r"\bReadClassBuffer\s*\(", source):
        semicolon = source.find(";", call.end())
        if semicolon < 0:
            continue
        window = _enclosing_block(source, semicolon + 1)
        stop = re.search(r"\breturn\b|\bbreak\b|\bcase\b[^;:]*:", window)
        if stop:
            window = window[:stop.start()]
        if io.search(window):
            return True
    return False


def classify(source: str, buffers: set[str]) -> str:
    """Which of the four kinds `source` is, most demanding on a reader first.

    `extending` outranks `guarded` because it is the stronger requirement: a
    reader must know the extra bytes at *every* version, where a guard only
    matters below its threshold. No class in the pinned submodule is both — the
    detector finds extra reads in three of the 35 otherwise-`delegating`
    streamers and in none of the 88 `guarded` ones — so the precedence has no
    effect today and is recorded here rather than left implicit.
    """
    if "ReadClassBuffer" not in source:
        return "custom"
    if reads_after_class_buffer(source, buffers):
        return "extending"
    names = "|".join(re.escape(n) for n in
                     sorted(set(READ_VERSION.findall(source)) | {"R__v"}))
    #: A version test: a comparison, or a `switch` on the version word.
    #: `RooBinning` is the reason for the second form — it hand-decodes its
    #: version 1 in a `case 1:` and nothing in it compares anything, so a
    #: comparison-only test called it `delegating`, i.e. "a reader needs
    #: nothing", for a class with a legacy layout on disk.
    guard = re.compile(r"\b(?:%s)\b\s*(?:[<>]=?|[!=]=)"
                       r"|\bswitch\s*\(\s*(?:%s)\s*\)" % (names, names))
    return "guarded" if guard.search(source) else "delegating"


def qualifier(prefix: str) -> list[str]:
    """The `A::B::` prefix of an out-of-line definition, as a list of names.

    Template arguments are dropped, matching how the class name itself is
    handled: the sidecar and the specification name the template.
    """
    prefix = re.sub(r"<[^<>]*>", "", prefix)
    return [part for part in (p.strip() for p in prefix.split("::")) if part]


def streamers() -> dict[str, dict]:
    """Every hand-written `Streamer` in the submodule, by class name.

    A class may define several overloads, and they are classified **together**
    rather than separately, because ROOT's multi-overload streamers are one
    streamer that dispatches between its own forms. `ROOT::v5::TFormula` is the
    case that forced this: its one- and two-argument forms read the version word
    and hand off to `Streamer(TBuffer&, Int_t, UInt_t, UInt_t, const TClass*)`,
    and *that* is where `ReadClassBuffer` is. Classified separately the class
    comes out `custom` -- "the streamer info describes the bytes at no version"
    -- when in fact every version a released ROOT ever wrote is streamer-info
    driven, and only versions 1 to 3 are hand-decoded.

    Three classes have more than one: `ROOT::v5::TFormula` (three),
    `ROOT::v5::TF1Data` and `TGenCollectionProxy`. All three were read before
    this rule was adopted; the last is `custom` either way.

    The citation kept is the first definition, in file and line order.
    """
    bodies: dict[str, list[str]] = {}
    cites: dict[str, str] = {}
    buffers: dict[str, set[str]] = {}
    for pattern in SOURCES:
        for path in sorted(SUBMODULE.rglob(pattern)):
            relative = str(path.relative_to(REPO))
            if EXCLUDED.search("/" + relative):
                continue
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            if "::Streamer" not in text:
                continue
            code = blank(text)
            matches = list(DEFINITION.finditer(code))
            if not matches:
                continue
            scopes = enclosing(code, [m.start() for m in matches])
            for match in matches:
                source = body(code, match.start())
                scope = scopes[match.start()]
                if source is None or scope is None:
                    continue
                name = "::".join(scope + qualifier(match.group(1))
                                 + [match.group(2)])
                bodies.setdefault(name, []).append(source)
                buffers.setdefault(name, set()).add(match.group(4) or "R__b")
                line = code.count("\n", 0, match.start()) + 1
                cites.setdefault(name, f"{relative}:{line}")
    return {name: {"kind": classify("\n".join(sources), buffers[name]),
                   "cite": cites[name]}
            for name, sources in bodies.items()}


#: `#pragma link C++ class X;`, with the trailing flag left in the name so that
#: `+` (request a streamer info, hence `ReadClassBuffer`), `-` (generate no
#: `Streamer` at all) and plain can be told apart. `options=...` may precede
#: `class`; `#pragma link off ...` deselects and must not match.
LINK = re.compile(
    r"^[ \t]*#pragma[ \t]+link[ \t]+C\+\+[ \t]+"
    r"(?:options[ \t]*=[ \t]*\S+[ \t]+)?class[ \t]+(.+?)[ \t]*;", re.M)

#: A `#pragma link C++ defined_in "header";` selects everything in a header, with
#: no per-class flag. Eight exist, all naming TMVA's GUI headers, and they are
#: reported rather than resolved -- see `ForwardingStreamers.md` §4.
DEFINED_IN = re.compile(
    r"^[ \t]*#pragma[ \t]+link[ \t]+C\+\+[ \t]+defined_in[ \t]+(\S+)[ \t]*;", re.M)


def selections() -> tuple[dict[str, set[str]], dict[str, str], list[str]]:
    """What every `#pragma link C++ class` in the submodule selects.

    Returns the set of flags seen per class (`""`, `"+"`, `"-"` or `"!"`), the
    LinkDef path each class was first seen in, and the `defined_in` selections,
    which carry no flag and so cannot be classified.

    Template selections are kept out: a `ClassDef` names the template and a
    pragma names the specialization, so `vector<TObject*>+` matches nothing this
    is compared against, and a line continued with a backslash would otherwise give a
    half-spelled name.
    """
    flags: dict[str, set[str]] = {}
    where: dict[str, str] = {}
    wildcards: list[str] = []
    for path in sorted(SUBMODULE.rglob("LinkDef*.h")):
        relative = str(path.relative_to(REPO))
        if EXCLUDED.search("/" + relative):
            continue
        try:
            text = blank(path.read_text(errors="ignore"))
        except OSError:
            continue
        for match in DEFINED_IN.finditer(text):
            wildcards.append(f"{relative}: defined_in {match.group(1)}")
        for match in LINK.finditer(text):
            name = match.group(1).strip()
            flag = ""
            if name[-1:] in "+-!":
                name, flag = name[:-1].strip(), name[-1]
            if "<" in name or ">" in name or "\\" in name or " " in name:
                continue        # a specialization, or a continued line
            flags.setdefault(name, set()).add(flag)
            where.setdefault(name, relative)
    return flags, where, wildcards


def forwarding() -> tuple[list[tuple[str, str]], list[str]]:
    """Classes whose generated `Streamer` writes only their bases, and the doubts.

    The rule is `ClassDef` version `<= 0` **and** a plain selection. Both halves
    matter: `+` routes the class through `ReadClassBuffer`, which writes a version
    word of 0 rather than nothing, and `-` means the class supplies its own
    `Streamer` -- `TCollection` is version 3 with a `-`, `TSeqCollection` is
    version 0 and plain, and the two sit four lines apart in the same LinkDef
    (`root/core/cont/inc/LinkDef.h:29`, `root/core/cont/inc/LinkDef.h:49`).

    A class selected both plainly and with `+`, or whose `ClassDef` version is
    ambiguous because ROOT's own tests declare a class of the same name, is
    reported rather than guessed at.
    """
    import check_versions

    versions = check_versions.class_versions()
    flags, where, _ = selections()
    rows: list[tuple[str, str]] = []
    doubts: list[str] = []
    for name in sorted(flags):
        seen = versions.get(name)
        if not seen:
            continue            # selected but no ClassDef: not a persistent class
        if flags[name] != {""}:
            if "" in flags[name] and max(seen) <= 0:
                doubts.append(
                    f"{name}: selected both plainly and with "
                    f"{sorted(flags[name] - {''})}, so which Streamer was "
                    f"generated depends on the dictionary")
            continue
        if max(seen) > 0:
            continue            # an old-style streamer, but a versioned one
        if min(seen) != max(seen):
            doubts.append(f"{name}: ClassDef versions {sorted(seen)} in the "
                          f"submodule, so the name is ambiguous")
            continue
        module = "/".join(where[name].split("/")[1:3])
        rows.append((name, module))
    return rows, doubts


def notes() -> dict[str, dict]:
    with SIDECAR.open("rb") as handle:
        return tomllib.load(handle).get("class", {})


def rows(names: list[str], found: dict[str, dict],
         annotations: dict[str, dict], resolved: bool) -> list[str]:
    if not resolved:
        return ["| Class | Defined |", "|---|---|"] + [
            f"| `{n}` | `{found[n]['cite']}` |" for n in names]
    out = ["| Class | Defined | Status | Where |", "|---|---|---|---|"]
    for name in names:
        note = annotations.get(name, {})
        where = note.get("spec") or note.get("note") or "—"
        out.append(f"| `{name}` | `{found[name]['cite']}` | "
                   f"{note.get('status', '?')} | {where} |")
    return out


def render(found: dict[str, dict], annotations: dict[str, dict],
           kind: str) -> list[str]:
    names = sorted(n for n, e in found.items() if e["kind"] == kind)
    return rows(names, found, annotations, resolved=(kind in RESOLVED))


def summary(found: dict[str, dict],
            annotations: dict[str, dict]) -> list[str]:
    counts = {k: sum(1 for e in found.values() if e["kind"] == k)
              for k in KINDS}
    out = ["| Classification | Count | What a reader has to do |", "|---|---|---|",
           f"| `delegating` | {counts['delegating']} | nothing — the bytes are "
           "streamer-info driven |",
           f"| `guarded` | {counts['guarded']} | nothing for a current file; the "
           "custom layout is below a version threshold |",
           f"| `extending` | {counts['extending']} | know the bytes that follow "
           "the streamer-info-driven ones, at every version |",
           f"| `custom` | {counts['custom']} | know the layout; the streamer info "
           "does not describe the bytes at any version |",
           "", "Of the `custom` and `extending` classes, which are the ones a "
           "reader must know:", "",
           "| Status | Count |", "|---|---|"]
    statuses: dict[str, int] = {}
    for name, entry in found.items():
        if entry["kind"] in RESOLVED:
            status = annotations.get(name, {}).get("status", "unclassified")
            statuses[status] = statuses.get(status, 0) + 1
    for status in ("specified", "gap", "not-persisted", "out-of-scope",
                   "unclassified"):
        if status in statuses:
            out.append(f"| `{status}` | {statuses[status]} |")
    return out


def render_forwarding(rows: list[tuple[str, str]]) -> list[str]:
    """The forwarding classes as a definition list, by ROOT module.

    534 names is too many for a table and the module is the useful grouping:
    almost every one of them is a GUI or graphics class that never reaches a
    file, and seeing that at a glance is part of the answer.
    """
    import textwrap

    modules: dict[str, list[str]] = {}
    for name, module in rows:
        modules.setdefault(module, []).append(name)
    out: list[str] = []
    for module in sorted(modules):
        names = ", ".join(f"`{n}`" for n in sorted(modules[module]))
        out.append(f"`{module}` ({len(modules[module])})")
        body = textwrap.wrap(names, width=76,
                             break_long_words=False, break_on_hyphens=False)
        for i, line in enumerate(body):
            out.append(f"{':   ' if i == 0 else '    '}{line}")
        out.append("")
    return out[:-1] if out else out


def block(lines: list[str], name: str,
          document: Path = DOCUMENT) -> tuple[int, int]:
    begin = BEGIN.format(name)
    try:
        start = lines.index(begin)
    except ValueError:
        sys.exit(f"{document}: no block {begin!r}")
    for i in range(start + 1, len(lines)):
        if lines[i] == END:
            return start, i
    sys.exit(f"{document}: block {name!r} is not closed")


def rebuild(found: dict[str, dict], annotations: dict[str, dict]) -> str:
    lines = DOCUMENT.read_text().splitlines()
    for kind in KINDS:
        start, stop = block(lines, kind)
        lines[start + 1:stop] = render(found, annotations, kind)
    start, stop = block(lines, "summary")
    lines[start + 1:stop] = summary(found, annotations)
    return "\n".join(lines) + "\n"


def rebuild_forwarding(rows: list[tuple[str, str]]) -> str:
    lines = FORWARDING_DOCUMENT.read_text().splitlines()
    start, stop = block(lines, "forwarding", FORWARDING_DOCUMENT)
    lines[start + 1:stop] = render_forwarding(rows)
    start, stop = block(lines, "forwarding-count", FORWARDING_DOCUMENT)
    modules = {module for _, module in rows}
    lines[start + 1:stop] = [
        f"**{len(rows)} classes**, in {len(modules)} of ROOT's modules."]
    return "\n".join(lines) + "\n"


def unresolved(found: dict[str, dict],
               annotations: dict[str, dict]) -> list[str]:
    """Classes the sidecar does not account for, and stale entries.

    Both `custom` and `extending` have to be resolved: in each case bytes reach
    the file that no streamer info describes, and the difference is only whether
    any of the object is described.
    """
    must = {n for n, e in found.items() if e["kind"] in RESOLVED}
    problems = [f"{n}: {found[n]['kind']} bytes no streamer info describes, "
                f"not in {SIDECAR.name}"
                for n in sorted(must - set(annotations))]
    problems += [f"{n}: in {SIDECAR.name} but its Streamer no longer writes "
                 "bytes outside its streamer info"
                 for n in sorted(set(annotations) - must)]
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if the document is stale (what CI runs)")
    args = parser.parse_args(argv)

    if not (SUBMODULE / "README").exists():
        sys.exit("root/ submodule is not checked out")

    found = streamers()
    annotations = notes()
    counts = {k: sum(1 for e in found.values() if e["kind"] == k)
              for k in KINDS}

    rows, doubts = forwarding()
    problems = unresolved(found, annotations)
    # A class cannot both supply a `Streamer` and have one generated for it: the
    # first needs a `-` and the second a plain selection. If the two lists ever
    # overlap, one of the two extractions is wrong.
    overlap = sorted({n for n, _ in rows} & set(found))
    problems += [f"{n}: both hand-written and generated-forwarding, which "
                 f"cannot both be true" for n in overlap]

    documents = ((DOCUMENT, rebuild(found, annotations)),
                 (FORWARDING_DOCUMENT, rebuild_forwarding(rows)))
    stale = [d for d, wanted in documents if wanted != d.read_text()]

    if args.check:
        for problem in problems + doubts:
            print(f"UNRESOLVED {problem}", file=sys.stderr)
        for document in stale:
            print(f"STALE {document.relative_to(REPO)} does not match the "
                  f"submodule; run tools/inventory.py", file=sys.stderr)
        if problems or stale:
            return 1
    else:
        for document, wanted in documents:
            document.write_text(wanted)
        for problem in problems + doubts:
            print(f"UNRESOLVED {problem}", file=sys.stderr)

    total = sum(counts.values())
    print(f"{total} hand-written Streamer(s): "
          + ", ".join(f"{counts[k]} {k}" for k in KINDS))
    print(f"{len(rows)} class(es) whose generated Streamer writes only their "
          f"bases")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
