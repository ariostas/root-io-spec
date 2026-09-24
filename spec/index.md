# ROOT I/O Specification

Descriptive of ROOT **6.40.04**, pinned as a submodule at `v6-40-04`. This
document tracks ROOT, and this line states which release it currently describes.
Its own releases are dated (`YYYY.MM.DD`) and cut at milestones.

A specification of the [ROOT](https://root.cern) on-disk binary formats, written so
that a third party can implement a reader without reading ROOT's C++ source.

## Why this exists

ROOT ships one real format specification, for the RNTuple binary format. For
`TFile` and `TTree`, the documentation in `root/io/doc/TFile/` describes release
**3.02.06**: it still states that ZIP is the only compression algorithm and that
there are "ten compression levels 0-9". Everything else is only in the source
code, so third-party implementations (uproot, groot, UnROOT.jl, root-io, JSROOT)
have been built largely by reverse engineering.

This specification is meant to be a shared, testable reference those projects can
rely on.

## Status

The container and object serialization layers are written and checked. They are
enough to locate any object in a ROOT file and to decode any user-defined class
from the file's own streamer info. Built on them, `TArray` and the full `TTree`
reading path (the tree record, branches, leaves, baskets, splitting and decoding
one entry) are written and checked. **[Writing](06-writing/index.md)** is
specified for the container, an object and its streamer info, histograms and a
flat `TTree`, at the current version of each class, and checked by having ROOT
read the result. The repository's `PLAN.md` has the phasing, and its §9 lists
every known gap.

| Layer | State |
|---|---|
| Conventions | written |
| Container — all of it, including the >2 GB layout | written |
| Serialization — framing, streamer info, element types, the reading algorithm | written |
| Serialization — collections, schema evolution, references | written |
| Standard classes — the divergent set, except twelve narrow classes | written |
| `TTree` — records, branches, leaves, baskets, splitting, reading an entry | written |
| Writing — the container, an object, `TH1`/`TH2`/`TProfile`, `TGraph`, a flat `TTree`, updating a file, schema evolution | [written](06-writing/index.md) |
| Appendix — the reader's checklist, pitfalls, bootstrap, the two class lists, glossary, bibliography | written |
| RNTuple — upstream specification tracked, every envelope, linked attribute sets and the type mapping audited | [audited](05-rntuple/index.md) |

The checks: **87 reference files with 2290 byte-level assertions, 1808 source
citations checked against the pinned ROOT tree across 49 documents**, and the
invariants of every layer run over 252 files this project did not write (ROOT
2.24/00 to 6.38/00) with **0 failures**.

The writing layer adds fourteen files this project *did* write, with 493
assertions of their own. In twelve of them, every object-bearing record is
**byte-identical to the one ROOT wrote**: a `TH1F`, a `TH1D`, a `TH2F`, a `TH2D`,
two `TProfile`s, a `TGraph`, a `TGraphErrors`, three `TTree`s, nine `TBasket`s,
and seven complete `StreamerInfo` records. Those records hold one, fifteen,
seventeen, eighteen and nineteen class descriptions; every checksum is computed
from scratch, and where ROOT appends a `listOfRules` entry it is reproduced
verbatim. This is the strongest check in the project.

Five of the fourteen match a ROOT-written file in every byte, not only in their
object records. The exceptions are each key's timestamp, the file's own name and
the UUIDs, which no writer can be expected to reproduce. The five are nested
subdirectories at 1854 bytes, records placed into released space at 1747, three
cycles of one key name at 1361, and two files that **reopen a file and add to
it**, at 1657 and 1928 bytes. The last two match down to the dead keys behind a
gap marker, which neither writer clears.

The fourteenth is a file ROOT cannot produce: **one class at two versions in one
file**, with an object written at each, so that only the version word says which
layout applies. A single ROOT session has one definition of a class, so this file
takes two sessions;
[Writing an object §8](06-writing/WritingObjects.md#8-writing-for-a-reader-that-is-not-you)
says what it must contain.

## How to read it

**To implement a reader**, start with
[Implementing a reader](99-appendix/ReaderChecklist.md). It arranges this material
as a work order: eight milestones, each ending in something that works, with the
documents, reference files and checks for each. Keep
[Pitfalls](99-appendix/Pitfalls.md) open beside it: forty-five facts that are
true, not obvious, and have cost somebody time.

To study the format rather than build on it, start with
[Conventions](00-conventions.md). It defines what every other document assumes:
byte order (ROOT uses **two** in the same file), the primitive type widths, the
four distinct string encodings, and the notation used for byte layouts.

Then read the layers in order, since each builds on the previous ones:

1. **Container** — the file as a sequence of records: the header, keys,
   directories, compression, and the free list.
2. **Serialization** — how an object becomes bytes: byte counts, version words,
   class tags, and the streamer-info-driven algorithm that covers most classes,
   including user-defined ones.
3. **Standard classes** — the layouts that the generic algorithm does not
   determine, because their streamers are hand-written and diverge from their
   recorded streamer info.
4. **`TTree`** — branches, leaves, baskets, splitting, and reading an entry.
5. **[Writing](06-writing/index.md)** — the same format from the writer's side:
   which bytes to emit, in what order, for the current version of each class.
   Four documents (the container, an object, histograms, a flat `TTree`) mark
   every field fixed, derived or free, and each is checked by having ROOT read
   what this project wrote.
6. **[RNTuple](05-rntuple/index.md)** — a **verbatim tracked copy** of ROOT's own
   RNTuple specification, which this project does not fork, plus the errata and
   implementation notes from its audit so far. Read the copy for the format and
   [ERRATA](05-rntuple/ERRATA.md) for where it and ROOT's code disagree. There
   are thirteen entries so far; one of them has already made two readers in ROOT's own
   repository diverge.

[Bootstrap classes](99-appendix/Bootstrap.md) cuts across all the layers and
answers the question "what do I have to implement before anything works?" The
layers are organised to describe the format; that appendix is organised as a work
order.
[Hand-written streamers](99-appendix/HandWrittenStreamers.md) and
[Forwarding streamers](99-appendix/ForwardingStreamers.md) are two lists that
cannot be derived from a file and so have to be published.
[A writer's invariants](99-appendix/WriterInvariants.md) re-sorts the 256
`Invariants` entries of every layer for a writer, adding a column the reading side
does not need: who notices when you get it wrong, including the nine cases where
nothing does.
[Glossary](99-appendix/Glossary.md) defines every term used with a meaning it does
not have in ordinary English, and
[Bibliography](99-appendix/Bibliography.md) lists other sources and what each is
good for.

## Scope

**It is descriptive, not normative.** It describes ROOT 6.40.04, pinned as a
submodule. Its own releases are dated rather than numbered (CalVer, tagged when
the document reaches a milestone), because the version that matters is ROOT's.
The repository's `CHANGELOG.md` says what changed for a reader at each release,
and its git log records how each fact was established. Where this specification
and the submodule disagree, the submodule is right and this specification has a
bug. Source citations link to that commit.

**It is written by an AI agent and checked by machine.** Every claim here has two
sources of evidence: a `path:line` citation into the submodule, and real bytes in
a committed reference file. Both are verified on every push, as is the rule that
no `Invariants` entry may be published without something checking it. Corrections
are more welcome than additions.

**Reading is specified; writing is specified where a writer has no freedom.** Each
layer ends with an `Invariants` section stating what a conforming file satisfies,
so a writer can validate its own output, and [Writing](06-writing/index.md) gives
the procedures (which bytes, in what order) for the current version of each class
a writer needs. Free-space reuse, basket sizing and key ordering are left
unspecified: they are ROOT's choices, not requirements of the format.

### How far back it reads

The two halves of the format reach back to different releases, and this is
measured: 252 files from ROOT releases 2.24/00 to 6.38/00 are read end to end
whenever the checks run.

**The container layer has no practical lower limit.** The oldest file available,
`pippa.root` from ROOT 2.24/00, can be walked completely: all 517 of its records
are located, framed and decompressed by the rules in
[Records and keys](01-container/Record.md) and
[Directories](01-container/Directory.md),
including its 24 version-1 directory records, which have no UUID.

**Decoding the objects requires streamer infos in the file**, and a file that old
has none. In `pippa.root`, the 468 histogram records are located but none can be
decoded. Nothing in the file describes what a `TH1F` looked like in 1997, and
reading it would mean hardcoding every class's layout at every version, which
this document does not attempt. The oldest files with streamer infos are from
ROOT 3.04/02, and they decode.

**Object reading is therefore specified for ROOT 4.00 and later, and works in
practice back to 3.04/02.** Below that, only the container layer applies.

### What is missing rather than excluded

Across both corpora 95% of records decode. Every record that does not has a
known cause, and `tools/coverage_probe.py` prints it per record:

| Cause | Reads | What it is |
|---|---|---|
| No streamer infos in the file | 468 | the version floor above |
| An LZ4 payload, when the `lz4` package is not installed | 0 here, 137 without it | the checker's environment, not the format |
| `TASImage` | 8 | **a gap** — one of twelve in [Hand-written streamers](99-appendix/HandWrittenStreamers.md) |
| `RooWorkspace::CodeRepo` | 2 | **a gap**, one partial `RooWorkspace` in each `stressRooFit` file. The five RooFit classes [RooFit](03-classes/RooFit.md) specifies decode |

`TASImage` and `RooWorkspace::CodeRepo` are the only **specification** gaps that
a file in either corpus reaches. The rest are single records of three kinds, none of them a gap in this
document: a class whose streamer info the file does not contain, so no reader
could decode it; entry offsets that the probe does not regenerate from the leaf,
which [TBasket §5.2.1](04-ttree/TBasket.md#521-regenerating-the-offsets)
specifies; and one file that ROOT itself refuses to open.

**No class in 252 files is below a hand-written version threshold except
`TBranch`, whose legacy layout is now specified**:
[TBranch §13.1](04-ttree/TBranch.md#131-the-layout-below-version-10) covers
versions 6 to 9. The other classes that keep a legacy layout below a threshold
(`TH1`, `TGraph`, `TFormula`, `TF1`, `TAxis`, `TTree`, `TLeafObject`,
[listed here](03-classes/index.md#how-small-that-set-is)) occur only at versions
above it, so those legacy layouts are a low priority rather than a gap a reader
will hit.

### What is deliberately out of scope

There are four groups. The first is recorded class by class in
[Hand-written streamers](99-appendix/HandWrittenStreamers.md), which is generated
from `spec/99-appendix/streamers.toml` and checked in CI, so the list cannot
change unnoticed:

- **Frameworks that ship inside ROOT and define their own persistent classes**:
  the SQL backend, where `TSQLFile` names a database rather than a ROOT file;
  PROOF's `TRemoteObject`; both event displays; and TMVA SOFIE. Each is listed
  with its reason.

    > **RooFit was on that list until 2026-09-21 and is now in scope**, because a
    > second independent reader asked for it rather than reverse-engineer it
    > ([issue #1](https://github.com/ariostas/root-io-spec/issues/1)). Its
    > workspaces are common in published files. [RooFit](03-classes/RooFit.md)
    > specifies the five classes a workspace needs; `RooWorkspace::CodeRepo` and
    > the four `RooCFunctionNRef` classes are recorded as gaps in
    > `HandWrittenStreamers.md`.
- **What `TGeo*` fields mean.** Its 88 persistable classes are streamer-info
  driven and decode by the generic algorithm like any other class. A hand-written
  account of the geometry they describe is out of scope.
- **The compression algorithms themselves.**
  [Compression](01-container/Compression.md) specifies ROOT's block header, how a
  payload over 16 MiB is split, which two-byte tag selects which algorithm, and
  the two common reader mistakes, but DEFLATE, LZMA, LZ4 and Zstandard are
  external standards.
- **On the write side**, everything [Writing §4](06-writing/index.md#4-what-is-not-specified)
  lists: earlier class versions, two writers on one file at once, producing a
  split `TBranchElement`, the element list of any class beyond the thirty-five
  [published](06-writing/ElementLists.md), and ROOT's policy choices. The largest
  policy choice is *when* to flush; its consequences are specified
  ([Writing trees §7](06-writing/WritingTrees.md#7-more-than-one-basket-per-branch)).
  The first three are out of scope by decision; the element lists are limited to
  what has been written so far. **Updating an existing file is specified**
  ([Writing a file §13](06-writing/WritingFiles.md#13-updating-an-existing-file)),
  as are subdirectories, `TH2F`, `TProfile`, `TGraph` and a `TLeafC` branch.

## Reference files

Every claim that can be demonstrated is demonstrated. `data/` holds small ROOT
files, each with a `case.toml` listing byte-level assertions (offset, type,
expected value) that can be checked with Python alone:

```sh
tools/generate.py --check
```

An implementation in any language can use them directly as test vectors, and
they are licensed for that: BSD-3-Clause for the reference files and the
generators, CC-BY-4.0 for this prose; the repository's `LICENSE` says which
applies where. Copy a fixture's `case.toml` along with it, since the assertions
say what the bytes mean.

The assertions and the byte tables in this specification are written from the
same reading, so an error in either shows up as a failing
assertion.

## Corrections are the most welcome contribution

A report that a sentence here is wrong about ROOT is worth more than an
addition, and it needs no fixture. `CONTRIBUTING.md` in the repository explains
how to contribute. Its central rule is that every claim needs two sources of
evidence: a `path:line` citation and real bytes.
