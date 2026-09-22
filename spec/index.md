# ROOT I/O Specification

Descriptive of ROOT **6.40.04**, pinned as a submodule at `v6-40-04`. This is a
living document that tracks ROOT, and this line is where it says which release it
currently describes; its own releases are dated (`YYYY.MM.DD`) and cut at
milestones.

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
checked. On the other side, **[writing](06-writing/index.md)** is specified for the
container, an object and its streamer info, histograms and a flat `TTree` — at the
current version of each class, and checked by having ROOT read the result. The
repository's `PLAN.md` has the phasing, and its §9 every known gap.

| Layer | State |
|---|---|
| Conventions | written |
| Container — all of it, including the >2 GB layout | written |
| Serialization — framing, streamer info, element types, the reading algorithm | written |
| Serialization — collections, schema evolution, references | written |
| Standard classes — the divergent set, bar seven narrow classes | written |
| `TTree` — records, branches, leaves, baskets, splitting, reading an entry | written |
| Writing — the container, an object, `TH1`/`TH2`/`TProfile`, `TGraph`, a flat `TTree`, updating a file, schema evolution | [written](06-writing/index.md) |
| Appendix — the reader's checklist, pitfalls, bootstrap, the two class lists, glossary, bibliography | written |
| RNTuple — upstream specification tracked, every envelope and all but one type-mapping form audited | [partly](05-rntuple/index.md) |

Behind it: **83 reference files with 2102 byte-level assertions, 1629 source
citations checked against the pinned ROOT tree across 49 documents**, and the
invariants of every layer run over 252 files this project did not write — ROOT
2.24/00 to 6.38/00 — with **0 failures**.

The writing layer adds fourteen files this project *did* write, with 493
assertions of their own. Twelve of them are the strongest check here: **every object-bearing
record in them is byte-identical to the one ROOT wrote** — a `TH1F`, a `TH1D`, a
`TH2F`, a `TH2D`, two `TProfile`s, a `TGraph`, a `TGraphErrors`, three `TTree`s,
**nine** `TBasket`s, and **seven whole `StreamerInfo` records** — of one, fifteen,
seventeen, eighteen and nineteen class descriptions, every checksum computed from
scratch and, where ROOT appends one, the `listOfRules` entry reproduced verbatim.

**Five of the fourteen match a ROOT-written file for every byte of the file**, not
only its object records — bar each key's timestamp, the file's own name and the
UUIDs, which no writer can be expected to reproduce: nested subdirectories at
1854 bytes, records placed into **released space** at 1747, three cycles of one
key name at 1361, and, newest, the two that **reopen a file and add to it** — at
1657 and 1928 bytes, down to the dead keys still buried behind a gap marker,
which neither writer clears.

The fourteenth is the odd one out and the point of it is that ROOT cannot produce
it: **one class at two versions in one file**, with an object written at each, so
the version word is the only thing that says which layout applies. A single ROOT
session has one definition of a class; two sessions make this file, and
[Writing an object §8](06-writing/WritingObjects.md#8-writing-for-a-reader-that-is-not-you)
says what has to be in it.

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
5. **[Writing](06-writing/index.md)** — the same format from the other side: which
   bytes to emit, in what order, for the current version of each class. Four
   documents — the container, an object, histograms, a flat `TTree` — each with
   every field marked fixed, derived or free, and each checked by having ROOT read
   what this project wrote.
6. **[RNTuple](05-rntuple/index.md)** — a **verbatim tracked copy** of ROOT's own
   RNTuple specification, which this project does not fork, plus the errata and
   implementation notes its audit has produced so far. Read the copy for the
   format and [ERRATA](05-rntuple/ERRATA.md) for where it and ROOT's code
   disagree; ten entries so far, one of which has already made two readers in
   ROOT's own repository diverge.

[Bootstrap classes](99-appendix/Bootstrap.md) cuts across all of them, and is the
one to read if the question is "what do I have to implement before anything
works?" The layers are organised for describing the format; that appendix is
organised as a work order.
[Hand-written streamers](99-appendix/HandWrittenStreamers.md) and
[Forwarding streamers](99-appendix/ForwardingStreamers.md) are the two lists that
cannot be derived from a file and so have to be published.
[A writer's invariants](99-appendix/WriterInvariants.md) is the 256 `Invariants`
entries of every layer re-sorted for a writer, with the one column the reading side
does not need: who notices when you get it wrong — and the nine cases where nothing
does.
[Glossary](99-appendix/Glossary.md) defines every term used with a meaning it does
not have in ordinary English, and
[Bibliography](99-appendix/Bibliography.md) says what else exists and what each of
it is good for.

## Scope

**It is descriptive, not normative.** This describes ROOT 6.40.04, pinned as a
submodule. Its own releases are dated rather than numbered — CalVer, tagged when
the document reaches a milestone — because the version that carries meaning is
ROOT's and not this document's. The repository's `CHANGELOG.md` says what changed
for a reader at each release, and its git log how each fact was established.
Where this specification and that submodule disagree, the submodule is
right and this has a bug. Source citations link to that exact commit.

**It is written by an AI agent and checked by machine.** Every claim here carries
two witnesses — a `path:line` citation into that submodule, and real bytes in a
committed reference file — and both are verified on every push, as is the rule
that no `Invariants` entry may be published without something checking it. Read
it accordingly: a correction is more welcome than an addition.

**Reading is specified; writing is specified where a writer has no freedom.** Each
layer ends with an `Invariants` section stating what a conforming file satisfies,
so a writer can validate its own output, and [Writing](06-writing/index.md) gives
the procedures — which bytes, in what order — for the current version of each class
a writer needs. Free-space reuse, basket sizing and key ordering stay unspecified:
they are ROOT's choices, not requirements of the format.

### How far back it reads

The two halves of the format have different floors, and the difference is
measured rather than estimated: 252 files from ROOT releases 2.24/00 to 6.38/00
are read end to end whenever the checks run.

**The container layer has no practical floor.** The oldest file available,
`pippa.root` at ROOT 2.24/00, walks completely: all 517 of its records are
located, framed and decompressed by the rules in
[Records and keys](01-container/Record.md) and
[Directories](01-container/Directory.md),
including its 24 version-1 directory records, which carry no UUID at all.

**Decoding the objects inside needs the file to carry streamer infos**, and a
file that old carries none. `pippa.root` is such a file, so its 468 histogram
records are located and not one of them is decodable — nothing in the file says
what a `TH1F` looked like in 1997, and reading it would mean hardcoding every
class's layout at every version, which this document does not attempt. The
oldest files that do carry streamer infos are from ROOT 3.04/02, and they decode.

**Object reading is therefore specified for ROOT 4.00 and later, and works in
practice back to 3.04/02.** Below that, the container layer alone applies.

### What is missing rather than excluded

Across both corpora 95% of records decode. Everything that does not has a name,
and `tools/coverage_probe.py` prints the reason per record:

| Cause | Reads | What it is |
|---|---|---|
| No streamer infos in the file | 468 | the version floor above |
| RooFit's own classes | 190 | **being specified**; in scope from 2026-09-21, below |
| An LZ4 payload, when the `lz4` package is not installed | 0 here, 137 without it | the checker's environment, not the format |
| `TASImage` | 8 | **the only gap** — one of ten in [Hand-written streamers](99-appendix/HandWrittenStreamers.md) |

`TASImage` is the only **specification** gap a file in either corpus hits. The
remainder is a tail of single records of three kinds, none of them a hole in this
document: a class used by a file whose streamer info that file does not contain,
so no reader could decode it either; entry offsets the probe declines to
regenerate from the leaf, which
[TBasket §5.2.1](04-ttree/TBasket.md#521-regenerating-the-offsets) specifies;
and one file ROOT itself refuses to open.

**No class in 252 files is below a hand-written version threshold except
`TBranch`, whose legacy layout is now specified** —
[TBranch §13.1](04-ttree/TBranch.md#131-the-layout-below-version-10) covers
versions 6 to 9. The others that keep a legacy layout under a threshold — `TH1`,
`TGraph`, `TFormula`, `TF1`, `TAxis`, `TTree`, `TLeafObject`,
[listed here](03-classes/index.md#how-small-that-set-is) — occur only at versions
above it, which is why those branches are a low priority and not a hole
underneath the reader.

### What is deliberately out of scope

Four groups. The first is recorded class by class in
[Hand-written streamers](99-appendix/HandWrittenStreamers.md), which is generated
from `spec/99-appendix/streamers.toml` and CI-checked, so the list cannot quietly
drift:

- **Frameworks that ship inside ROOT and define their own persistent classes** —
  the SQL backend, where `TSQLFile` names a database rather than a ROOT file;
  PROOF's `TRemoteObject`; both event displays; and TMVA SOFIE. Each with its
  reason beside it.

    > **RooFit was on that list until 2026-09-21 and is now in scope**, because a
    > second independent reader asked for it rather than reverse-engineer it
    > ([issue #1](https://github.com/ariostas/root-io-spec/issues/1)). Its
    > workspaces are common in published files and a reader will meet them. The
    > classes are not written yet, so `HandWrittenStreamers.md` still records them
    > as `out-of-scope` until each is specified; that file is the list to watch,
    > and it is CI-checked so the change cannot go unrecorded.
- **What `TGeo*` fields mean.** Its 88 persistable classes are streamer-info
  driven and decode by the generic algorithm like anything else; what is out of
  scope is a hand-written account of the geometry they describe.
- **The compression algorithms themselves.**
  [Compression](01-container/Compression.md) specifies ROOT's block header, how a
  payload over 16 MiB is split, which two-byte tag selects which algorithm, and
  the two places that trip a reader up — but DEFLATE, LZMA, LZ4 and Zstandard are
  somebody else's standards.
- **On the write side**, everything [Writing §4](06-writing/index.md#4-what-is-not-specified)
  lists: earlier class versions, two writers on one file at once, producing a
  split `TBranchElement`, the element list of any class beyond the thirty-five
  [published](06-writing/ElementLists.md), and ROOT's policy choices — of which
  *when* to flush is the largest, its consequences being specified
  ([Writing trees §7](06-writing/WritingTrees.md#7-more-than-one-basket-per-branch)).
  The first three are out of scope by decision; the element lists are a limit of
  what has been written so far. **Updating a file that already exists is
  specified**
  ([Writing a file §13](06-writing/WritingFiles.md#13-updating-an-existing-file)),
  as are subdirectories, `TH2F`, `TProfile`, `TGraph` and a `TLeafC` branch.

## Reference files

Every claim that can be demonstrated is demonstrated. `data/` holds small ROOT
files, each with a `case.toml` listing byte-level assertions — offset, type,
expected value — checkable with nothing but Python:

```sh
tools/generate.py --check
```

They are usable directly as test vectors by an implementation in any language, and
are licensed for exactly that — BSD-3-Clause for the reference files and the
generators, CC-BY-4.0 for this prose; the repository's `LICENSE` says which is
which. Copy a fixture's `case.toml` along with it: the assertions are what make
the bytes useful.

This is also how the specification is kept honest: the assertions and the byte
tables here are written from the same reading, so an error in either shows up as a
failure.

## Corrections are the most welcome contribution

If a sentence here is wrong about ROOT, that is worth more than an addition, and
saying so needs no fixture. `CONTRIBUTING.md` in the repository has the mechanics,
and the one rule behind all of them: every claim carries two witnesses, a
`path:line` citation and real bytes.
