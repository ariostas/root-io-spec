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

Early. The structure and scope are settled; the specification text is being
written layer by layer. See the repository's `PLAN.md` for the phasing.

| Layer | State |
|---|---|
| Conventions | written |
| Container — all of it | written |
| Serialization — buffer framing, streamer info, element types, the reading algorithm | written |
| Serialization — collections, schema evolution, references | not yet written |
| Standard classes | not yet written |
| `TTree` | not yet written |
| RNTuple | not yet imported |

## How to read it

Start with [Conventions](00-conventions.md). It fixes the things every other
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
5. **RNTuple** — a tracked copy of the upstream specification, plus errata.

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
