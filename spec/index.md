# ROOT I/O Specification

A specification of the [ROOT](https://root.cern) on-disk binary formats, written so
that a third party can implement a reader without reading ROOT's C++ source.

## Why this exists

ROOT ships exactly one real format specification — the RNTuple binary format. For
`TFile` and `TTree`, the documentation in `root/io/doc/TFile/` describes release
**3.02.06**: it still states that ZIP is the only compression algorithm and that
there are "ten compression levels 0-9". Everything else lives in the source code,
which is why third-party implementations — uproot, groot, UnROOT.jl, root-io,
JSROOT — have been built largely by reverse engineering.

This is intended to be the shared, testable artifact those projects can rely on.

## Status

The container and object serialization layers are written and checked — enough to
locate any object in a ROOT file and decode any user-defined class from the file's
own streamer info. On top of them, `TArray` and the whole `TTree` reading path — the tree record,
branches, leaves, baskets, splitting and decoding one entry — are written and
checked. See the repository's `PLAN.md` for the phasing, and its §9 for every
known gap.

| Layer | State |
|---|---|
| Conventions | written |
| Container — all of it | written |
| Serialization — framing, streamer info, element types, the reading algorithm | written |
| Serialization — collections, schema evolution, references | written |
| Standard classes — the divergent set, bar nine narrow classes | written |
| `TTree` — records, branches, leaves, baskets, splitting, reading an entry | written |
| Appendix — the reader's checklist, pitfalls, bootstrap, the two class lists, glossary, bibliography | written |
| RNTuple — upstream specification tracked, anchor and file embedding audited | [partly](05-rntuple/index.md) |

## How to read it

**If you are here to implement something**, start with
[Implementing a reader](99-appendix/ReaderChecklist.md). It is this material as a
work order: eight milestones, each a state in which something works, with the
documents, the reference files and the checks for each one. Keep
[Pitfalls](99-appendix/Pitfalls.md) open beside it — forty-five things that are
true, unobvious, and have cost somebody time.

To read the format rather than build on it, start with
[Conventions](00-conventions.md). It fixes the things every other
document assumes: byte order — ROOT uses **two** in the same file — the primitive
type widths, the four distinct string encodings, and the notation used for byte
layouts.

Then the layers, in order. They build on each other:

1. **Container** — the file as a sequence of records: the header, keys,
   directories, compression, and the free list.
2. **Serialization** — how an object becomes bytes: byte counts, version words,
   class tags, and the streamer-info-driven algorithm that covers most classes,
   including user-defined ones.
3. **Standard classes** — the layouts that the generic algorithm does not
   determine, because their streamers are hand-written and diverge from their
   recorded streamer info.
4. **`TTree`** — branches, leaves, baskets, splitting, and reading an entry.
5. **[RNTuple](05-rntuple/index.md)** — a **verbatim tracked copy** of ROOT's own
   RNTuple specification, which this project does not fork, plus the errata and
   implementation notes its audit has produced so far. Read the copy for the
   format and [ERRATA](05-rntuple/ERRATA.md) for where it and ROOT's code
   disagree; six entries so far, one of which has already made two readers in
   ROOT's own repository diverge.

[Bootstrap classes](99-appendix/Bootstrap.md) cuts across all of them, and is the
one to read if the question is "what do I have to implement before anything
works?" The layers are organised for describing the format; that appendix is
organised as a work order.
[Hand-written streamers](99-appendix/HandWrittenStreamers.md) and
[Forwarding streamers](99-appendix/ForwardingStreamers.md) are the two lists that
cannot be derived from a file and so have to be published.
[Glossary](99-appendix/Glossary.md) defines every term used with a meaning it does
not have in ordinary English, and
[Bibliography](99-appendix/Bibliography.md) says what else exists and what each of
it is good for.

## Two things to know before implementing

**It is descriptive, not normative.** This describes ROOT 6.40.04, pinned as a
submodule. Where this specification and that submodule disagree, the submodule is
right and this has a bug. Source citations link to that exact commit.

**Reading is specified; writing is constrained.** Each layer ends with an
`Invariants` section stating what a conforming file satisfies, so a writer can
validate its own output. Free-space allocation, basket sizing and key ordering are
deliberately left unspecified — they are ROOT's choices, not requirements of the
format.

## Reference files

Every claim that can be demonstrated is demonstrated. `data/` holds small ROOT
files, each with a `case.toml` listing byte-level assertions — offset, type,
expected value — checkable with nothing but Python:

```sh
tools/generate.py --check
```

They are usable directly as test vectors by an implementation in any language. This
is also how the specification is kept honest: the assertions and the byte tables
here are written from the same reading, so an error in either shows up as a
failure.
