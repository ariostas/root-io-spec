# ROOT I/O Specification

A specification of the [ROOT](https://root.cern) on-disk binary formats, written so
that a third party can implement a reader without reading ROOT's C++ source.

ROOT ships exactly one real format specification — the
[RNTuple binary format](root/tree/ntuple/doc/BinaryFormatSpecification.md). The
TFile/TTree documentation in `root/io/doc/TFile/` describes release 3.02.06 and is
substantially out of date. Everything else lives in the source code, which is why
third-party implementations (uproot, groot, UnROOT.jl, root-io, jsroot) have been
built largely by reverse engineering.

This repository aims to be the shared, testable artifact those projects can rely on.

## Status

The **container** and **object serialization** layers are written and checked:
enough to locate any object in a ROOT file and decode any user-defined class from
the file's own streamer info. `spec/03-classes/` has `TArray`; `spec/04-ttree/`
covers reading an entry out of an unsplit tree; `spec/05-rntuple/` is not
started.

| Layer | State |
|---|---|
| Conventions | written |
| Container — header, records, directories, compression, free list | written |
| Serialization — framing, streamer info, element types, reading algorithm | written |
| Serialization — collections, schema evolution, references | written |
| Standard classes — `TArray` | written |
| `TTree` — the tree record, `TBranch`, `TLeaf`, `TBasket` | written |
| Standard classes and `TTree` — everything else, RNTuple | not started |

29 reference files, 723 byte-level assertions, 583 checked source citations.
The invariants also run clean over 154 files written by other people and other
ROOT releases, from ROOT 4.00 to 6.36 — which is where eleven errors in this
specification were found and fixed (`PLAN.md` §9.8).
See [PLAN.md](PLAN.md) for the structure, phasing and decisions; §9 there lists
every known gap — in each case the behaviour is specified and cited, and what is
missing is a reference file proving it.

Scope in brief: reading is specified normatively; writing is covered by per-layer
invariants a conforming file must satisfy, rather than by prescribing ROOT's
allocation strategy. The document is descriptive of ROOT 6.40.04 — where it and the
pinned submodule disagree, the submodule wins.

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
