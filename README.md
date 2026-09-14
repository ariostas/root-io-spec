# ROOT I/O Specifications

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

Early. See [PLAN.md](PLAN.md) for the proposed structure, scope, and phasing.

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
