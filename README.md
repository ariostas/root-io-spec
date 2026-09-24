# ROOT I/O Specification

[![ci](https://github.com/ariostas/root-io-spec/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ariostas/root-io-spec/actions/workflows/ci.yml?query=branch%3Amain) [![docs](https://github.com/ariostas/root-io-spec/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/ariostas/root-io-spec/actions/workflows/docs.yml?query=branch%3Amain) [![large files](https://github.com/ariostas/root-io-spec/actions/workflows/large-files.yml/badge.svg?branch=main)](https://github.com/ariostas/root-io-spec/actions/workflows/large-files.yml?query=branch%3Amain)

### 📖 [Read the specification →](https://ariostas.github.io/root-io-spec/)

A specification of the [ROOT](https://root.cern) on-disk binary formats, written so
that a third party can implement a reader without reading ROOT's C++ source.

**Descriptive of ROOT 6.40.04**, pinned as the `root/` submodule at `v6-40-04`.
That is the version number that matters here. It is stated on the front page and
the checkers keep it there: `check_pin.py` requires the site to cite the pinned
commit, and `check_citations.py` requires every cited line to exist at it. Where
this specification and that submodule disagree, the submodule is right and this
has a bug.

This is a living document that tracks ROOT, so it has no semantic version of its
own. Releases are CalVer, `YYYY.MM.DD`, tagged when the specification reaches a
milestone rather than on a schedule. `main` is always the current document, and a
tag is a point in it stable enough to cite or to vendor a fixture from.

ROOT ships one real format specification, the RNTuple binary format, which is
[tracked here verbatim](spec/05-rntuple/BinaryFormatSpecification.md). The
TFile/TTree documentation in `root/io/doc/TFile/` describes release 3.02.06 and is
substantially out of date. Everything else lives in the source code, so
third-party implementations (uproot, groot, UnROOT.jl, root-io, JSROOT) have been
built largely by reverse engineering.

This repository aims to be a shared, testable reference those projects can rely on.

## How it is written

**This is an AI-driven project.** The specification, the reference files, the
reference reader and writer, and the checkers were produced, and are still
maintained, by an AI agent working from ROOT's source under human direction.

Nothing here rests on the agent's word. Every claim has two witnesses, and a
machine verifies both on every push: a `path:line` citation into the pinned ROOT
release, and real bytes in a committed reference file. An invariant may not be
published unless something checks it; `tools/check_coverage.py` fails the build
otherwise. The invariants also run over 252 files this project did not write,
where a disagreement with real files is an ordinary outcome. Nineteen errors in
this specification were found that way (`PLAN.md` §9.8 and §9.9), eight more by
its first outside review (§8.13), and ten more by a survey of six external corpora
(§8.14). Each one is recorded rather than quietly fixed.

Read it as you would any reverse-engineered specification: **where it and ROOT
disagree, ROOT is right.** Corrections are more welcome than additions, and need
no fixture.

## Status

All four layers of the classic format are written and checked on the reading side:

- the container: header, records, directories, compression, the free list;
- object serialization: framing, streamer info, element types, collections,
  schema evolution, references;
- the standard classes whose recorded streamer info does not describe their bytes;
- `TTree`: the tree record, branches, leaves, baskets, splitting, and reading an
  entry out of a split or an unsplit tree.

A writing layer covers the other direction.
[spec/06-writing/](spec/06-writing/index.md) says which bytes to emit and in what
order for the container, an object and its streamer info, `TH1F`/`TH1D`,
`TH2F`/`TH2D`/`TProfile`, and a flat `TTree` of as many baskets per branch as the
writer flushes, all at the current version of each class. Since 2026-09-21 it also
covers reopening an existing file to add to it, and what a file must contain so
that a reader whose classes differ from the writer's can still read it.
`tools/rootwrite.py` is its executable form. The conformance test is that ROOT
opens what it wrote, finds the values that went in, and prints no diagnostics.

The results go beyond that test. Every record in `data/written/` that has a
ROOT-written counterpart is byte-identical to it: a `TH1F`, a `TH1D`, a `TH2F`, a `TH2D`, two
`TProfile`s, a `TGraph`, a `TGraphErrors`, three `TTree`s, nine `TBasket`s, and
seven complete `StreamerInfo` records. Those records hold up to nineteen class
descriptions each, with every checksum computed from scratch and, where ROOT
appends one, the `listOfRules` entry reproduced verbatim. Five of the fourteen
files match ROOT's byte for byte, except for each key's timestamp, the file's own
name and the UUIDs.

| Layer | State |
|---|---|
| Conventions | written |
| Container — header, records, directories, compression, free list, the >2 GB layout | written |
| Serialization — framing, streamer info, element types, reading algorithm | written |
| Serialization — collections, schema evolution, references | written |
| Standard classes — the divergent set, except twelve narrow classes | written |
| `TTree` — the tree record, `TBranch`, `TLeaf`, `TBasket`, splitting, reading an entry | written |
| Writing — the container, an object, `TH1`/`TH2`/`TProfile`, `TGraph`, a flat `TTree`, updating an existing file, writing for a reader at another class version | written |
| Appendix — reader's checklist, pitfalls, bootstrap, the two class lists, glossary, bibliography | written |
| RNTuple — ROOT's own specification tracked verbatim and audited, plus thirteen errata | audited |

**90 reference files, 2330 byte-level assertions, and 1861 source citations
checked against the pinned submodule across 49 documents**, plus 14 files this
project wrote with 493 assertions of their own. The invariants also run over 252
files this project did not write: 180 from uproot's regression corpus and 72
published by the ROOT team, spanning ROOT 2.24/00 to 6.38/00. They report 0
failures, and 95% of the records in those files decode. Those files are where
nineteen errors in this specification were found and fixed, along with one
compression codec it had written off as unreadable and one coverage figure it had
been overstating (`PLAN.md` §9.8 and §9.9). A survey that extended them to ROOT's
own test suite, 23 RNTuple files and three multi-gigabyte CERN Open Data files
found ten more (§8.14).

**Start at [spec/99-appendix/ReaderChecklist.md](spec/99-appendix/ReaderChecklist.md)**
if you are here to implement something. It presents the specification as a work
order of eight milestones, each ending in a state where something works.
[spec/index.md](spec/index.md) states the scope: which releases are covered for
reading, what is deliberately out of scope, and the two gaps that a file in either
corpus still hits. See [PLAN.md](PLAN.md) for the structure, phasing and
decisions; §8 records how it was built, item by item, and §9 lists every known gap.

In brief, reading is specified normatively, and writing in two ways. There are
per-layer invariants that a conforming file satisfies whatever wrote it, collected
for writers in
[spec/99-appendix/WriterInvariants.md](spec/99-appendix/WriterInvariants.md), and
there are procedures in `spec/06-writing/` for producing a file at the current
version of each class and for reopening one. Basket sizing and *where* a record is
placed are left unspecified, because they are ROOT's choices rather than part of
the format. The allocator and key ordering ROOT actually uses are specified as
well, because a byte comparison against a ROOT-written file needs them.

The writing side is deliberately narrower than the reading side. It covers a
file with subdirectories, reopening one to add to it, an object, the five
histogram classes `TH1F`, `TH1D`, `TH2F`, `TH2D` and `TProfile`, `TGraph` and
`TGraphErrors`, and a flat `TTree` of any number of baskets per branch with its
cluster ranges.
[Writing §4](spec/06-writing/index.md#4-what-is-not-specified) lists what it does
not cover, and `PLAN.md` §8.5 ranks that list by how much each item blocks a third
party; all seven items are now done:

- the element lists of all thirty-five classes a writer has to describe are
  published as [Element lists](spec/06-writing/ElementLists.md), read out of the
  ROOT-written fixtures rather than transcribed from this project's writer;
- [Writing trees §7](spec/06-writing/WritingTrees.md#7-more-than-one-basket-per-branch)
  specifies flushing;
- [Writing histograms §7 and §8](spec/06-writing/WritingHistograms.md#7-th2f-and-th2d)
  specify `TH2` and `TProfile`;
- [Writing a file §5](spec/06-writing/WritingFiles.md#5-a-subdirectory) specifies a
  tree of directories;
- [Writing trees §4.5](spec/06-writing/WritingTrees.md#45-a-tleafc-the-one-leaf-whose-entries-are-not-all-the-same-length)
  specifies a string branch;
- [Writing a graph](spec/06-writing/WritingGraphs.md) specifies `TGraph` and
  `TGraphErrors`.

The writing documents are descriptive of ROOT 6.40.04. Where they and the pinned
submodule disagree, the submodule wins.

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
| `gen/` | One small ROOT macro per reference file, the write-side cases, and the two corpus manifests |
| `data/` | Generated reference files; `data/written/` holds the ones this project wrote |
| `tools/` | Consistency checkers, the reference reader and writer, and the generators |
| `root/` | ROOT source, pinned submodule |

## Licence, citation, contributing

[LICENSE](LICENSE): **CC-BY-4.0** for `spec/` and the prose, **BSD-3-Clause** for
`tools/`, `gen/` and `data/`, so an implementation in any language, closed-source
included, can vendor the reference files as test vectors. One file is under
neither: `spec/05-rntuple/BinaryFormatSpecification.md` is a tracked copy of
ROOT's own document.

[CITATION.cff](CITATION.cff) has the machine-readable citation.
[CONTRIBUTING.md](CONTRIBUTING.md) has the mechanics, the most important of which
is the two-witness rule above. [CHANGELOG.md](CHANGELOG.md) records what changed
for a reader at each release; the git log records how each fact was established.

## Building the site

The specification is published with [Zensical](https://zensical.org). Source files
under `spec/` are plain CommonMark, so they stay readable on GitHub; the site adds
navigation and search, and turns each `root/...:NN` source citation into a link
into root-project/root at the pinned commit.

```sh
pip install -r requirements-docs.txt
PYTHONPATH=. zensical serve            # live preview
PYTHONPATH=. zensical build --strict   # as CI builds it
```

`--strict` fails on warnings, including links to pages that do not exist yet.
