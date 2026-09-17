# ROOT I/O Specification

A specification of the [ROOT](https://root.cern) on-disk binary formats, written so
that a third party can implement a reader without reading ROOT's C++ source.

ROOT ships exactly one real format specification — the RNTuple binary format,
[tracked here verbatim](spec/05-rntuple/BinaryFormatSpecification.md). The
TFile/TTree documentation in `root/io/doc/TFile/` describes release 3.02.06 and is
substantially out of date. Everything else lives in the source code, which is why
third-party implementations (uproot, groot, UnROOT.jl, root-io, JSROOT) have been
built largely by reverse engineering.

This repository aims to be the shared, testable artifact those projects can rely on.

## Status

All four layers of the classic format are written and checked: the **container**
(header, records, directories, compression, the free list), **object
serialization** (framing, streamer info, element types, collections, schema
evolution, references), the **standard classes** whose recorded streamer info does
not describe their bytes, and **`TTree`** — the tree record, branches, leaves,
baskets, splitting, and reading an entry out of a split or an unsplit tree.

| Layer | State |
|---|---|
| Conventions | written |
| Container — header, records, directories, compression, free list, the >2 GB layout | written |
| Serialization — framing, streamer info, element types, reading algorithm | written |
| Serialization — collections, schema evolution, references | written |
| Standard classes — the divergent set, bar ten narrow classes | written |
| `TTree` — the tree record, `TBranch`, `TLeaf`, `TBasket`, splitting, reading an entry | written |
| Appendix — reader's checklist, pitfalls, bootstrap, the two class lists, glossary, bibliography | written |
| RNTuple — ROOT's own specification tracked verbatim, plus six errata from auditing it | partly |

**65 reference files, 1563 byte-level assertions, and 1130 source citations
checked against the pinned submodule across 40 documents.** The invariants also
run over 226 files this project did not write — 154 from uproot's regression
corpus and 72 published by the ROOT team, spanning ROOT 2.24/00 to 6.36/02 —
with **0 failures**, and 94% of the records in them decode. Those files are where
fourteen errors in this specification were found and fixed — plus one compression
codec it had written off as unreadable (`PLAN.md` §9.8 and §9.9).

**Start at [spec/99-appendix/ReaderChecklist.md](spec/99-appendix/ReaderChecklist.md)**
if you are here to implement something: it is the whole specification as a work
order, eight milestones, each one a state in which something works.
[spec/index.md](spec/index.md) states the scope — which releases are covered for
reading, what is deliberately out of scope, and the two gaps a file in either
corpus still hits. See [PLAN.md](PLAN.md) for the structure, phasing and
decisions; §8 is the route to a first release and §9 lists every known gap.

Scope in brief: reading is specified normatively; writing is covered by per-layer
invariants a conforming file must satisfy, rather than by prescribing ROOT's
allocation strategy. The document is descriptive of ROOT 6.40.04 — where it and
the pinned submodule disagree, the submodule wins.

## Reference implementation

The `root/` submodule is pinned at `v6-40-04`. It is the tiebreaker for every
statement in `spec/`, and the consistency checkers in `tools/` run against it.

```sh
git clone --recurse-submodules <this repo>
```

## Layout

| Path | Contents |
|---|---|
| `spec/` | The specification itself, organized by layer |
| `gen/` | One small ROOT macro per reference file |
| `data/` | Generated reference files |
| `tools/` | Consistency checkers and dumpers |
| `root/` | ROOT source, pinned submodule |

## Building the site

The specification is published with [Zensical](https://zensical.org). Source files
under `spec/` are plain CommonMark, so they stay readable on GitHub; the site adds
navigation, search, and turns each `root/...:NN` source citation into a link into
root-project/root at the pinned commit.

```sh
pip install -r requirements-docs.txt
PYTHONPATH=. zensical serve            # live preview
PYTHONPATH=. zensical build --strict   # as CI builds it
```

`--strict` fails on warnings, including links to pages that do not exist yet.
