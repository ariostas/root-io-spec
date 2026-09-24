# Bibliography

Other sources, and what each is useful for. ROOT ships one real format
specification, for RNTuple. Everything else is API documentation, out of date,
source code, or someone else's reverse engineering.

## 1. ROOT's own documentation

**The RNTuple binary format specification** —
`root/tree/ntuple/doc/BinaryFormatSpecification.md`. A real specification,
maintained with the code, and the model this project follows. It is tracked here
verbatim as [`05-rntuple/BinaryFormatSpecification.md`](../05-rntuple/BinaryFormatSpecification.md)
with [errata](../05-rntuple/ERRATA.md) beside it. Read the copy for the format
and the errata for the thirteen places where it and ROOT's code disagree.

**`root/io/doc/TFile/*.md`** — the `TFile` and `TTree` documentation ROOT ships.
It describes **release 3.02.06**, with four of its pages partially updated to
6.22.06. It still states that ZIP is the only compression algorithm and that
there are "ten compression levels 0-9". It does not cover `TBranchElement`,
member-wise STL streaming, `Double32_t`, schema evolution, or the 64-bit layout
beyond the header. Roughly 37 errata against it are recorded in the `Errata`
sections of the documents here that replace it. **Treat it as a source of
questions, not answers.** It is still worth reading: its questions are good ones,
and several conventions still in the format originate in its diagrams.

**The ROOT User's Guide**, chapters *Input/Output* and *Trees*
(<https://root.cern/manual/>). Conceptual and API-level: what a `TTree` is for,
what splitting does, what a basket is. No byte layouts. Useful for vocabulary
before reading anything here.

**The Reference Guide** (<https://root.cern/doc/master/>) — per-class
documentation generated from the source. It explains what a member means, but
not how it is written. A member's documentation comment is also its
streamer-element title, so the strings in a file's streamer info often come from
this text.

**Release notes**, `root/io/doc/v5xx/` and `root/io/doc/v6xx/`. Not
specifications, but the quickest way to date a behaviour change once you know
roughly when it happened.

**The source.** Every statement here is checked against it. This project pins
ROOT as a submodule and cites it as `path:line`, which the published site turns
into a link at the pinned commit.
[Conventions §7](../00-conventions.md#7-citing-the-reference-implementation)
explains the convention and its limits.

## 2. Readers built without a specification

Each of these was reverse-engineered from ROOT's source and has solved problems
this document also solves. Where two implementations disagree, there is often a
format fact that neither documented.

| Project | Language | Scope |
|---|---|---|
| [uproot](https://github.com/scikit-hep/uproot5) | Python | `TTree` and RNTuple, read and write. The most complete third-party reader, and the source of this project's `gen/foreign/` corpus |
| [groot](https://github.com/go-hep/hep/tree/main/groot) | Go | `TFile`, `TTree`, read and write, with its own class-by-class layout knowledge |
| [UnROOT.jl](https://github.com/JuliaHEP/UnROOT.jl) | Julia | `TTree` reading, with an emphasis on lazy access |
| [root-io](https://github.com/cbourjau/alice-rs/tree/master/root-io) | Rust | `TFile` and `TTree` reading; a compact implementation worth reading end to end |
| [JSROOT](https://github.com/root-project/jsroot) | JavaScript | Reading and drawing in a browser. It ships inside ROOT's own repository, so where it and ROOT's C++ disagree, both are ROOT; see [RNTuple erratum 6](../05-rntuple/ERRATA.md#6-column-type-0x17-does-not-exist-and-roots-own-javascript-reader-implements-it) |

## 3. Files to test against

**`scikit-hep-testdata`** (<https://github.com/scikit-hep/scikit-hep-testdata>) —
the corpus uproot runs its regression tests against. This project uses a
selection of 179 of its files, 24 of them RNTuple, which with one file from
go-hep's `groot/testdata` make up the 180 of `gen/foreign/`. Its provenance is
mixed: it contains files uproot wrote, so a disagreement is a lead rather than
evidence (`PLAN.md` §3.4).

**`root.cern/files`** (<https://root.cern/files/>) — files published by the ROOT
team, written by ROOT, from release 2.24/00 to 6.35/01. This project downloads
72 of them and reads 8 more, of several gigabytes each, only by range request;
`gen/cern/LARGE.toml` lists those 8 and 3 more from CERN Open Data
(<https://opendata.cern.ch/>). `gen/cern/README.md` gives the reason for each.
Because ROOT wrote them, a failure there is evidence.

**`root/roottest/`** — ROOT's own test suite, inside the pinned submodule: 273
ROOT-written files from 2.23/12 to 6.41/01. The ones this specification cites are
listed in `gen/cern/README.md`. It is LGPL-2.1, so none of it is copied here.

**The reference files here.** `data/` holds 89 small files ROOT wrote, plus the
14 in `data/written/` that this project wrote. Each has a `case.toml` of
byte-level assertions that can be checked with only the standard library, so the
files work as test vectors for an implementation in any language
([Conventions §8](../00-conventions.md#8-reference-files)).

## 4. This specification

[`PLAN.md`](https://github.com/ariostas/root-io-spec/blob/main/PLAN.md) in the
repository holds the structure, the scope decisions and the gap register: what is
specified, what is measured, and what is known to be missing. It is written for
contributors rather than implementers, but its §9 lists what this document
does not yet cover.
