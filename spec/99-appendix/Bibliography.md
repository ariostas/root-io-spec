# Bibliography

What else exists, and what each of it is good for. The short version: ROOT ships
one real format specification and it covers RNTuple; everything else is either
about the API, or out of date, or source code, or someone else's reverse
engineering.

## 1. ROOT's own documentation

**The RNTuple binary format specification** —
`root/tree/ntuple/doc/BinaryFormatSpecification.md`. A genuine specification,
maintained with the code, and the model this project follows. It is tracked here
verbatim as [`05-rntuple/BinaryFormatSpecification.md`](../05-rntuple/BinaryFormatSpecification.md)
with [errata](../05-rntuple/ERRATA.md) beside it; read the copy for the format
and the errata for the ten places it and ROOT's code disagree.

**`root/io/doc/TFile/*.md`** — the `TFile` and `TTree` documentation ROOT ships.
It describes **release 3.02.06**, with four of its pages partially refreshed to 6.22.06.
It still states that ZIP is the only compression algorithm and that there are
"ten compression levels 0-9"; it has no coverage of `TBranchElement`,
member-wise STL streaming, `Double32_t`, schema evolution, or the 64-bit layout
beyond the header. Roughly 37 errata against it are recorded in the `Errata`
sections of the documents here that replace it. **Treat it as a source of
questions, not answers** — but do read it, because its questions are good ones
and its diagrams are the origin of several conventions still in the format.

**The ROOT User's Guide**, chapters *Input/Output* and *Trees*
(<https://root.cern/manual/>). Conceptual and API-level: what a `TTree` is for,
what splitting does, what a basket is. No byte layouts. Useful for vocabulary
before reading anything here.

**The Reference Guide** (<https://root.cern/doc/master/>) — per-class
documentation generated from the source. The place to learn what a member
*means*; it says nothing about how one is written. Note that a member's
documentation comment is also its streamer-element title, so the strings in a
file's streamer info often come from exactly this text.

**Release notes**, `root/io/doc/v5xx/` and `root/io/doc/v6xx/`. Not
specifications, but the quickest way to date a behaviour change once you know
roughly when it happened.

**The source.** In the end every statement here is checked against it. This
project pins ROOT as a submodule and cites it as `path:line`, which the published
site turns into a link at the pinned commit —
[Conventions §7](../00-conventions.md#7-citing-the-reference-implementation)
explains the convention and its limits.

## 2. Readers built without a specification

Every one of these was reverse-engineered from ROOT's source, and each has solved
problems this document also solves. Reading two implementations that disagree is
a good way to find a format fact that neither documented.

| Project | Language | Scope |
|---|---|---|
| [uproot](https://github.com/scikit-hep/uproot5) | Python | `TTree` and RNTuple, read and write. The most complete third-party reader, and the source of this project's `gen/foreign/` corpus |
| [groot](https://github.com/go-hep/hep/tree/main/groot) | Go | `TFile`, `TTree`, read and write, with its own class-by-class layout knowledge |
| [UnROOT.jl](https://github.com/JuliaHEP/UnROOT.jl) | Julia | `TTree` reading, with an emphasis on lazy access |
| [root-io](https://github.com/cbourjau/alice-rs/tree/master/root-io) | Rust | `TFile` and `TTree` reading; a compact implementation worth reading end to end |
| [JSROOT](https://github.com/root-project/jsroot) | JavaScript | Reading and drawing in a browser. It ships *inside* ROOT's own repository, which is what makes it interesting: where it and ROOT's C++ disagree, both are ROOT — see [RNTuple erratum 6](../05-rntuple/ERRATA.md#6-column-type-0x17-does-not-exist-and-roots-own-javascript-reader-implements-it) |

## 3. Files to test against

**`scikit-hep-testdata`** (<https://github.com/scikit-hep/scikit-hep-testdata>) —
the corpus uproot regression-tests against, 155 files of which this project uses
all. Its provenance is mixed: it contains files uproot wrote, so a disagreement
is a lead rather than evidence (`PLAN.md` §3.4).

**`root.cern/files`** (<https://root.cern/files/>) — files published by the ROOT
team, written by ROOT, from release 2.24/00 to 6.35/01. This project curates **34**
of them — 26 downloaded and 8 multi-gigabyte files read by range request alone
(`gen/cern/LARGE.toml`); `gen/cern/README.md` says why each is listed. Because ROOT wrote them, a
failure there **is** evidence, which is what makes them worth the download.

**The reference files here.** `data/` holds 76 small files ROOT wrote, plus the 9
in `data/written/` that this project wrote, each with a
`case.toml` of byte-level assertions checkable with nothing but the standard
library, so they work as test vectors for an implementation in any language —
[Conventions §8](../00-conventions.md#8-reference-files).

## 4. This specification

[`PLAN.md`](https://github.com/ariostas/root-io-spec/blob/main/PLAN.md) in the
repository holds the structure, the scope decisions and the gap register: what is
specified, what is measured, and what is known to be missing. It is written for
contributors rather than implementers, but §9 is the honest list of what this
document does not yet cover.
