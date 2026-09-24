# PLAN — ROOT I/O Specification

**Status:** the reading side is specified end to end for files written by ROOT 4
and later. The writing side covers the container with subdirectories, an object,
histograms and profiles, graphs, and a flat `TTree` with many baskets and with a
`TLeafC`. Everything is cited against the pinned submodule and checked against
bytes; RNTuple tracks ROOT's own specification plus thirteen errata. §2.9 and §8.4 are
the write support, which extends the project past the reading side it was scoped
to.

**The corpus survey, 2026-09-22/23 — discharged; §8.14.** Six external
resources were surveyed, and the sub-plan that ordered the work, `PLAN-corpus.md`,
was deleted once its nineteen items were done. Ten published claims turned out
wrong or under-scoped. All ten are fixed, so §8.1 release criterion 1, *no
published claim is known to be wrong*, holds again. The work also added
`root/roottest/` as a third listed source of ROOT-written files (it has shipped
inside the pinned submodule since ROOT merged it in April 2025), plus 23 RNTuple
files and three large Open Data files. Two gaps closed with new specification:
`StreamerDriven.md` §7.1, for an object with no byte count, and
`Collections.md` §11.2, for a class that is itself a collection.

**The second consistency review, 2026-09-24 — open; `PLAN-review.md`.** Seven
read-only reviewers went over every document, the front matter and `tools/` at
`385a3e2`. Nine published claims are wrong or produce wrong bytes when followed
literally (its V1–V9), and Phase B's contradictions (V10–V20) were fixed the
same day. §8.1 release criterion 1 does **not** hold until the stale figures of
its V27–V28 are corrected too; about thirty more statements are contradictory, stale or narrower
than the format, and none of it is caught by a check. The sub-plan orders the
response and adds the checks (a figures check, `check_versions.py` validating
the cited line, the unit tests run with the submodule in CI) so the three
patterns behind it cannot recur. §8.17 will be what it leaves behind.

Measured, 2026-09-23, by the checks in `tools/`; the fixture, citation, invariant
and unit-test rows again on 2026-09-24, after `rntuple/attributes`:

| | |
|---|---|
| Specification documents | 49, plus the tracked RNTuple copy |
| Reference files / byte assertions | 87 / 2290, 0 failures |
| Files this project wrote / assertions | 14 / 493, 0 failures |
| Source citations checked | 1808, 0 failures |
| Class versions checked against `ClassDef` | 63 |
| Element lists published / elements / sources | 35 / 194 / 7 |
| Invariants over the fixtures and the written files | 101 files, 0 failures |
| Invariants over both corpora | 252 files, ROOT 2.24/00 – 6.38/00, 0 failures |
| Entries decoded and checked | 48278 of 48501 branch-baskets, 99.5%, 0 failed |
| Unit tests | 645 |

Throughout: **✅ done**, **◐ partly done**, **☐ not started**, **⏸ set aside**:
narrow enough that it is not being worked on, recorded so it is not rediscovered,
and picked up only if a real file or reader needs it (2026-09-24). §9 is the gap
register: every gap the written documents record, so that each can be picked up
rather than rediscovered. How each was found is in the git log, not here; this
document keeps only what is still live, plus the measurements the scope decisions
rest on.

## 1. Goal

Produce a complete, versioned, machine-checkable specification of the ROOT
on-disk formats, sufficient for a third party to implement a reader **without
reading ROOT's C++ source**.

Reading is specified normatively for every layer. Writing is specified two ways
(decision 3, revised 2026-09-18). Every layer states the invariants a conforming
file satisfies whatever wrote it, and `spec/06-writing/` gives end-to-end
*procedures* for producing one — the container, an object and its streamer info,
a histogram, and a flat `TTree` — at the current version of each class only.
Free-space reuse, basket sizing and key ordering stay unspecified: they are ROOT's
policy, not a requirement of the format. See §2.8 and §2.9.

Non-goals: ROOT's C++ API, its in-memory data structures, its build system. We
document *bytes on disk* and the *algorithms* required to turn those bytes into
values.

This specification is descriptive of ROOT 6.40.04, not normative for ROOT. Where
the pinned submodule and this document disagree, the submodule wins and the
discrepancy is a bug in this document. Where ROOT's own behaviour looks like a
bug, it goes in an errata table and, where possible, upstream (§7.1).

### 1.1 Why

`root/tree/ntuple/doc/BinaryFormatSpecification.md` is the only real
specification ROOT ships, and it covers only RNTuple. For TFile/TTree:

- `root/io/doc/TFile/*.md` documents **release 3.02.06** (one page was partially
  refreshed to 6.22.06). It still claims ZIP is the only compression algorithm
  and that there are "ten compression levels 0-9". It does not cover
  `TBranchElement`, member-wise STL streaming, `Double32_t`, schema evolution, or
  the 64-bit layout beyond the header. Roughly 37 errata against it are recorded
  in the documents that replace it.
- `root/io/doc/v5xx/`, `v6xx/` — release notes, not specifications.
- Everything else is source code.

Third-party implementations (uproot, groot, UnROOT.jl, root-io, JSROOT) have been
reverse-engineered from that source. This repo is meant to be the shared,
testable artifact those projects can cite and test against, and to feed fixes
back upstream where it finds real bugs or under-specification.

### 1.2 Reference version

The `root/` submodule is pinned at `v6-40-04` (`1211eda9301`) and is the reference
implementation. When a statement is version dependent we say so; the pinned
submodule is what the checkers in `tools/` run against.

## 2. Repository layout

```
root-io-spec/
├── README.md, PLAN.md, AGENTS.md
├── root/                         ← submodule, pinned to v6-40-04
├── spec/                         ← the specification; also the site (docs_dir)
│   ├── 00-conventions.md
│   ├── 01-container/  02-serialization/  03-classes/  04-ttree/
│   ├── 05-rntuple/               ← tracked copy of upstream + errata
│   ├── 06-writing/               ← the write side: procedures, current versions
│   └── 99-appendix/
├── gen/                          ← one generator macro per reference file
├── data/                         ← generated reference files (committed)
└── tools/                        ← checkers, and an independent reader
```

`spec/` is split by layer rather than by class, because ROOT's format is layered
and almost every class is described by the container plus the serialization layer
plus a `TStreamerInfo` read out of the file itself. Only the divergent classes
need hand-written text. Structuring the repo this way makes the size of the
hand-written surface explicit, which third-party implementers currently have to
discover the hard way.

`LICENSE`, `LICENSES/`, `CONTRIBUTING.md`, `CHANGELOG.md` and `CITATION.cff` are in
place (§8 item M7); the changelog is scoped to releases (decision 9).

### 2.1 `spec/00-conventions.md` ✅

RFC 2119 keywords; endianness (TFile/TBuffer is big-endian and the RNTuple payload
is little-endian, so the same file contains both); the primitive type table,
including `Long_t` at 8 bytes on disk even where it is 4 in memory; the four
string encodings (counted string, `TString`, `TStringLong` §5.1.1, NUL-terminated
class tags); the notation for byte layouts; and how citations work.

### 2.2 `spec/01-container/` ✅

| File | Contents |
|---|---|
| ✅ `FileHeader.md` | The 64/100-byte header, `fVersion`, the `+1000000` large-file flag and the field widening it implies |
| ✅ `Record.md` | `TKey` layout, `fNbytes`/`fObjLen`/`fKeyLen`, cycles, the `fSeekKey` self-check, the key-of-a-key for large files, `fDatime` as a bare member |
| ✅ `Directory.md` | `TFile`'s own record, `TDirectoryFile`, the keys list, `fSeekDir`/`fSeekParent`/`fSeekKeys`, nested directories |
| ✅ `FreeSegments.md` | The `TFree` list, the sentinel segment past EOF, gaps, the interleaved 10-/18-byte forms |
| ✅ `Compression.md` | The 9-byte block header, the `ZL`/`XZ`/`L4`/`ZS`/`CS` magics, multi-block payloads, the LZ4 XXH64 trailer, `fCompress` as `100*algorithm + level`, which records are never compressed, and that `CS` is raw DEFLATE (§3.1) |
| ✅ `LargeFiles.md` | Everything that changes past 2 GB: the five independent switches and their five different conditions, the wide diagrams, one 5.25 GB file byte by byte, and six invariants checked by `fetch_cern.py --headers` |

### 2.3 `spec/02-serialization/` ✅

The core of the repo, and the answer to "how do we handle custom classes".

| File | Contents |
|---|---|
| ✅ `Buffer.md` | Byte counts (`kByteCountMask`), the version word and `kByteCountVMask`, `ReadVersion`'s no-byte-count path, class tags (`kNewClassTag`, `kClassMask`), the buffer map and `kMapOffset`, deduplication, `kNullTag`, the `TObject` base |
| ✅ `StreamerInfo.md` | The `StreamerInfo` key, the `TList` of `TStreamerInfo`, and the byte layout of `TStreamerInfo` plus every `TStreamerElement` subclass: the bootstrap set, which cannot be read using streamer info |
| ✅ `StreamerDriven.md` | The normative algorithm: given a `TStreamerInfo` and a byte range, produce a value tree. Also §7 on when the info does not describe the bytes, §4.4 a hand-written base, §4.5 a version-0 forwarding streamer |
| ✅ `ElementTypes.md` | The complete `EReadWrite` table → exact bytes, the `Double32_t`/`Float16_t` grammars, and §2.4–2.5: `fType` is not a stable property of a class, and a value can be `0x99` because nobody wrote one |
| ✅ `Collections.md` | STL containers, proxies, object-wise vs member-wise, `std::map` shapes, `TClonesArray`'s bespoke format |
| ✅ `SchemaEvolution.md` | Class version 0, checksums, `TSchemaRuleSet`, conversion/artificial/cache/skip elements, emulated classes |
| ✅ `References.md` | `TProcessID`, `TRef`, `TRefArray`, `kIsReferenced` and the extra `fPID` word |

### 2.4 `spec/03-classes/` — per-class layouts ✅

**Decision (settled, and now backed by measurement): specify only the classes
whose recorded streamer info does not describe their bytes.**

The original plan was generated version matrices and member tables for ~440
persistable classes. That aimed at the wrong target. A generated table restates
what the streamer info in the file already says, and `tools/rootfile.py` decodes
99.8% of branch-baskets across both corpora from the file's own infos, with no
per-class knowledge beyond the bootstrap set. `tools/gen_tables.py` is therefore
not planned.

What a reader cannot get from a file is which classes have streamer info that
does not describe their bytes. `tools/inventory.py` extracts that set from the
pinned submodule into `spec/99-appendix/HandWrittenStreamers.md`, CI-checked, with
every class resolved in `streamers.toml`. A submodule bump that adds or drops a
hand-written `Streamer` therefore fails until someone classifies it.

There are 187 hand-written `Streamer` definitions, sorted by what the reading
branch does:

| | Count | What a reader has to do |
|---|---|---|
| `delegating` | 35 | nothing — `ReadClassBuffer` with no version test and no reads after it |
| `guarded` | 86 | nothing for a current file: `ReadClassBuffer` above a version threshold, a legacy layout below. Those legacy layouts are §9.1 |
| `extending` | 3 | know the bytes that follow the streamer-info-driven ones, at every version — `TMatrixTSym`, `TPointSet3D`, `ROOT::RNTuple` |
| `custom` | 63 | know the layout; the streamer info describes the bytes at no version |

Of the 66 `custom` and `extending` classes, the two kinds a reader must know,
43 are specified, 5 are never objects in a file, 6 are outside scope (EVE, SOFIE,
the SQL backend) and 12 are gaps. Four of the specified ones moved from
out-of-scope on 2026-09-21, when RooFit came into scope (decision 8, §8.13):
`RooRealVar`, `RooLinkedList`, `RooAbsBinning` and `RooRefArray`, in
[`spec/03-classes/RooFit.md`](spec/03-classes/RooFit.md). Three more moved from
gap to specified on 2026-09-22 with no new layout to write: the `graf2d/gviz`
wrappers `TGraphEdge`, `TGraphNode` and `TGraphStruct` have `Streamer`s with
empty bodies, so each one's specification is "nothing", and `Buffer.md` §2.3
says so (`PLAN-corpus.md` C3). The gaps are `TASImage`, `TClassTree`,
`TMaterial`, `TMixture`, `TPolyLine3D`, `TPolyMarker3D`, `TPointSet3D`, and five
RooFit classes: `RooWorkspace::CodeRepo`, which leaves the one `RooWorkspace`
record in each `stressRooFit_*` file partly decoded, and the four
`RooCFunctionNRef`, which
nothing in either corpus reaches. All are of narrow reach. Only `CodeRepo` is
something a physics file is likely to hold, and none of them is in the MVP (§8).
**⏸ The twelve are set aside.**

Written so far: ✅ `TArray.md`, ✅ `Containers.md` (`TMap`, `TExMap`, `TBtree`),
✅ `Formula.md` (`ROOT::v5::TFormula`/`TF1Data` against the ROOT 6 classes),
✅ `Canvas.md` (`TCanvas`, `TQObject`, and the zero-byte base),
✅ `Matrix.md` (`TMatrixTSym` and the family around it), ✅ `index.md`
mapping every divergent class to wherever it is specified. `TStringLong` went to
Conventions §5.1.1 and `TBranchClones` to `TBranchElement.md` §13, per decision 6.

### 2.5 `spec/04-ttree/` ✅

| File | Contents |
|---|---|
| ✅ `TTree.md` | The record, v20 members, the branch list, `fLeaves` as back-references, cluster ranges, finding a tree through the base-class chain |
| ✅ `TBranch.md` | v13, the three basket arrays, the basket that lives inside the `TTree` record, branches in separate files, and §13 the legacy layouts |
| ✅ `TBranchElement.md` | `fID`, `fType`, `fStreamerType`, the name fields, `fBranchCount` as a back-reference, the eleven-row dispatch, and §13 `TBranchClones` |
| ✅ `TLeaf.md` | The family, `fLen`/`fLenType`/`fOffset`/`fIsRange`/`fIsUnsigned`, leaf counts, `TLeafC` strings, `TLeafElement`, `TLeafD32`/`TLeafF16` |
| ✅ `TBasket.md` | The record, the `fNevBufSize` sign trick → `fIOBits`, the `flag >= 80` generate-offsets path, `flag % 10 == 2`, entry offsets, displacement arrays, `fLast`, and §4.1 the embedded layout |
| ✅ `Splitting.md` | Split levels and what `fSplitLevel` does not mean, the trailing-dot divergence, the count-name convention, `kSplitCollectionOfPointers`, `TBranchSTL`, the unsplit fallback |
| ✅ `ReadingEntries.md` | End to end: entry number → basket → byte range → value, for the unsplit path and all eleven split procedures |
| ✅ `Auxiliary.md` | `TTreeIndex` (which publishes no streamer info), `TFriendElement`, `TBranchRef`/`TRefTable`, `TEntryList`, `TEventList`, `TNtuple`/`TNtupleD`, `TChain` |

`Double32.md` was dropped because its content is already written elsewhere: the
grammar and the three encodings are `ElementTypes.md` §5.1–5.3, the leaf classes
and the 3-versus-4-byte asymmetry are `TLeaf.md` §7.

The sub-plan that ordered this layer is discharged and deleted. §9.11 keeps what
is left of it: the corpus census it was written against, what the decoder still
cannot reach, and the questions it left open.

### 2.6 `spec/05-rntuple/` ✅

RNTuple already has a real specification and we do not fork it.

- ✅ `BinaryFormatSpecification.md` is a verbatim tracked copy of
  `root/tree/ntuple/doc/BinaryFormatSpecification.md` at the pinned commit.
  `tools/sync_rntuple.py --check` fails on drift, in CI, on every push, and also
  asserts that the commit `UPSTREAM.md` records is the pin. **Never edit it.**
- ✅ `UPSTREAM.md` provenance and sync procedure; ✅ `ERRATA.md` (thirteen entries);
  ✅ `NOTES.md` implementation notes, including the audit state table.
- ✅ The envelope audit, through every envelope, and a fixture of our own
  (`rntuple/anchor`, `rntuple/fundamental-types`), plus an independent reader in
  `tools/rootfile.py`.
- ✅ The type mapping (which columns a given C++ type produces), audited one
  fixture at a time across eight of them, with four errata (§8 item M9).
- ✅ *Linked Attribute Sets*, audited end to end on 2026-09-24 against
  `rntuple/attributes`, the first fixture with a non-empty attribute set list,
  with three errata (11 to 13) and a reader that follows each footer locator to
  the set's anchor, header, footer and page list (§8.3 item M9).
- ⏸ One form is left unaudited on purpose (2026-09-24): a class with an
  associated collection proxy, which needs a compiled `TCollectionProxyInfo` that
  is not ready for this use, and whose associative half ROOT does not implement
  at all. `NOTES.md` §4 records it.

### 2.7 `spec/99-appendix/` ✅

| File | State |
|---|---|
| ✅ `Bootstrap.md` | The minimal hardcoded class set, in dependency order; the only document organised as a work order rather than by layer. `tools/test_bootstrap.py` checks its lists against what `rootfile.py` hardcodes, in both directions |
| ✅ `Glossary.md` | Every term used with a meaning it does not have in ordinary English |
| ✅ `HandWrittenStreamers.md` | Generated from the submodule by `inventory.py`; §2.4 |
| ✅ `ForwardingStreamers.md` | The other half of the same question, from the same tool: the classes whose *generated* `Streamer` writes only their bases |
| ✅ `ReaderChecklist.md` | The whole specification as a work order: eight milestones, each with its documents, fixtures and checks |
| ✅ `Pitfalls.md` | Forty-eight things that are true, unobvious and have cost somebody time, each linked to the section that specifies it; §6 is the three that are ROOT's bugs rather than yours |
| ✅ `Bibliography.md` | ROOT's own documentation and what each part of it is good for, the five other readers, and the two corpora |
| ✅ `WriterInvariants.md` | The 259 `Invariants` entries of the whole specification, across 32 documents, re-sorted by the order a file is produced in, with a column the reading side does not need: who notices a violation (`tools/check_invariants.py`, ROOT, or nothing). §7 is the ten cases where nothing does |

### 2.8 Write support, part one: invariants ✅

Each layer document ends with an `## Invariants` section stating what a
conforming file must satisfy, so a writer can validate its own output and a
reader knows which consistency checks are worth making. The sections do not
elevate ROOT's incidental implementation choices to requirements.
`tools/check_invariants.py` is the executable form: every entry is checked, and
each was confirmed to catch a corruption of a fixture.

Where a write-side rule has no freedom (the compression block header, the
`Double32_t` factor encoding, the `fNevBufSize` sign trick) it is specified
exactly. Basket sizing and *which* free span a writer picks are deliberately not
specified. Free-space allocation and key ordering came into scope on 2026-09-21
(§8.12), once it turned out that ROOT's order within a key name is load-bearing
and its allocator's remainder rule is not optional. The choice stays free; what a
choice produces is specified.

Invariants alone turned out to be necessary but not sufficient. They let a writer
check a file it has already produced, but they do not tell it which bytes to
emit, and a reader-shaped document leaves a writer to infer the order of
operations. ROOT's writing code has rules there that no file records. §2.9 is the
other half.

### 2.9 `spec/06-writing/` — write support, part two: procedures ✅

Added 2026-09-18, extending decision 3. The reading documents answer "what do
these bytes mean"; these answer "which bytes do I emit, in what order". They are
scoped by what a writer needs rather than by symmetry with the reading side:

| File | State |
|---|---|
| ✅ `index.md` | What a writing procedure is here, the conformance test, and what is deliberately not specified |
| ✅ `WritingFiles.md` | The container in write order, subdirectories (§8.9), the allocator and key order (§8.12), updating an existing file (§8.12), and §15's mistakes ROOT reads without complaint |
| ✅ `WritingObjects.md` | Framing, the version word, the object map, compression, the `StreamerInfo` record down to each element subclass, and what a reader at another class version needs (§8.12) |
| ✅ `WritingHistograms.md` | `TH1F`, `TH1D`, `TH2F`, `TH2D` and `TProfile` member by member (§8.8) |
| ✅ `WritingTrees.md` | A flat `TTree`: the tree record, branches, leaves, baskets, the multi-basket and cluster-range case (§8.7), and a `TLeafC` branch (§8.10) |
| ✅ `WritingGraphs.md` | `TGraph` and `TGraphErrors`, and why a null `fHistogram` costs eighteen streamer infos (§8.11) |
| ✅ `ElementLists.md` | Not a procedure but the table every procedure needs: the element list of each of the thirty-five classes, read out of the fixtures rather than out of the writer (§8.6) |

**Only the current version of each class.** A writer chooses what it emits, so
there is never a reason to write an old layout; the legacy layouts stay on the
reading side, where files force them. Schema evolution is still covered: what a
file must carry so that a reader at a *different* version can read it is
specified (`WritingObjects.md` §8), and `data/written/two-versions.root` holds
one class at two versions to demonstrate it.

The conformance test is executable, so these documents are checkable the way the
reading side is. `tools/rootwrite.py` is a pure-Python writer built from these
documents alone, and `tools/check_write.py` puts every file it produces through
three gates:

1. `rootfile.py` reads it and every applicable `Invariants` section holds. This
   is §3.1's discipline with the arrow reversed: two independent implementations
   meeting in the middle;
2. the bytes are reproduced exactly. A writer that fixes its own clock and UUID
   has no reason not to be deterministic, so `data/written/` has a plain `sha256`
   and §3.3's normalization does not apply to it;
3. where ROOT is on `PATH`, ROOT opens the file, returns the values that went in,
   and prints no warning. This is the gate that finds errors, and the reason the
   layer is worth writing: a wrong streamer info or a wrong class version makes
   ROOT complain rather than fail silently.

## 3. Reference files

### 3.1 Layout

```
gen/cases/<group>/<case>/{gen.C, case.toml[, classes.h][, README.md]}
data/<group>/<case>.root            + data/MANIFEST.sha256
```

One case = one file = one specific thing exercised. 64 cases in five groups:
`container/`, `serialization/`, `classes/`, `ttree/`, `rntuple/`. A case with a
`classes.h` gets it compiled into a dictionary with ACLiC before the macro loads
(`gen/common/README.md`), so a generator can use a real `ClassDef`.

### 3.2 `case.toml`

Assertions are byte offsets, `{name, offset, type, value}`, checkable with stdlib
Python alone and with no reader at all. A third-party implementation in any
language can therefore use the corpus as test vectors on day one. The cost is
that assertions are tied to absolute offsets, so editing a `gen.C` renumbers
them; in practice that has been cheap and has repeatedly caught errors.

`case.toml` also has a prose `description`, a `[[records]]` table giving the
record chain, and a `spec` list naming the documents the case supports. Semantic
`path`/`value` assertions are still worth adding as a complement (§9.6); they are
not MVP.

### 3.3 Determinism

Byte-exact reproducibility is **not** achievable: every `TKey` records the wall
clock and every file *and every directory* gets its own `TUUID`.
`tools/normalize.py` computes a digest with those masked, and CI regenerates and
compares the normalized digest. Also masked, each for a reason that took time to
find:

- the process UUID as text, 36 ASCII characters in a `TProcessID` record;
- an embedded basket's `TKey::fDatime`, twice per basket, because the raw buffer
  copy begins with the key again;
- `TBranchElement::fCheckSum` when `fClassName` is an STL type, since a checksum
  folds in member type names that the two standard libraries spell differently;
- every `TStreamerElement::fSize`, which is `sizeof` on the writing machine
  (`sizeof(std::string)` 24 with libc++, 32 with libstdc++). Because the digest
  can no longer see `fSize`, a case SHOULD assert it directly for members whose
  `sizeof` is standard-library independent.

Three fixtures opt out with `digest = false` and a required `digest_reason`,
printed on every run as `NO DIGEST`, because the difference is a length change a
mask cannot undo:

- `serialization/pairs` and, since 2026-09-21, `classes/roofit`: libstdc++ has
  doc comments on `std::pair`'s members (`/**< The first member */`) and libc++
  does not, so a synthesised `pair<string,int>`'s two element titles are 35 bytes
  on one and 2 on the other;
- `rntuple/anchor`: `std::uint64_t` resolves to `unsigned long` on one platform
  and `unsigned long long` on the other, so the same member is `kULong` on one and
  `kULong64` on the other (the format fact is `ElementTypes.md` §2.4).

`classes/canvas` opts out for a third reason: the order of entries in the
`StreamerInfo` record is process registration order, not a property of the file
(`StreamerInfo.md` §3.4).

A fixture can inherit that exemption without containing a pair itself.
`classes/roofit` writes a `RooRealVar` and a `RooLinkedList` and no map at all.
The pair arrives because `RooAbsReal::_specIntegratorConfig` reaches
`RooNumIntConfig`, which holds `RooCategory`, whose `_stateNames` is a
`map<string,int>`, and a file records infos for its whole reachable class graph.
The portability of a fixture is therefore a property of that graph, not of what
the case writes.

**Every new case must go through the container loop in `AGENTS.md` before a
push**, not after a red build. The drift is libc++ against libstdc++, not
architecture, so an arm64 container reproduces the x86_64 CI digests byte for
byte.

### 3.4 The two corpora

Neither is committed; both are fetched, and each file is listed because it covers
something no fixture and no other listed file does.

| | Files | Reach | Provenance |
|---|---|---|---|
| `gen/cern/` | 72 — 24 core, 46 geometry, 2 physics (+11 more by range request, 3 of them from CERN Open Data) | ROOT 2.24/00 – 6.35/01 | published by the ROOT team at <https://root.cern/files/>, so a failure is evidence |
| `gen/foreign/` | 180 | ROOT 5.23/02 – 6.38/00, plus two g4tools files whose headers claim 4.00/00 | uproot's regression corpus, which includes files uproot wrote, so a failure is a lead |

A lead must be diagnosed against the pinned source and resolved to one of four
things: a spec error, a missing format fact, a reader gap, or a file at fault.
Only the last goes in `gen/foreign/IGNORE.toml`, per file and per invariant, with
a reason and with the suppressed count printed. **Never weaken an invariant
because a file disagrees with it.**

`tools/fetch_cern.py --headers` re-reads the header and free-segment record of
eleven files from 1.3 GB to 15.9 GB over HTTP range requests, about 11 KB of
traffic for 49 GB of files. It is the only thing exercising the large-file layout
at all (§9.2).

### 3.5 Historical versions

Most class versions cannot be produced by ROOT 6.40. The original plan was
`gen/legacy/`: per-version containers and release artifacts. It does not exist,
and §9.10 explains why it is no longer the blocker it was recorded as. The two
corpora already contain most of the legacy layouts §9.1 lists, written by ROOT.
That is evidence rather than a fixture, but it is enough to specify and check
against. `gen/legacy/` stays deferred; where a version is unreachable the document
says so rather than guessing.

## 4. Tooling and CI

All CI steps run on every push, in this order. There are no guarded steps: two
used to be wired behind `hashFiles(...) != ''` and therefore never ran.

| Tool | Purpose |
|---|---|
| `generate.py` | Run every `gen.C`, produce `data/`, validate `case.toml`. `--check` needs no ROOT; `--accept` re-records an intentional digest change |
| `check_bytes.py` | Evaluate a case's `[[bytes]]`. Stdlib only, so third parties can run it |
| `check_invariants.py` | The `Invariants` sections, over the fixtures and over both corpora. `--ignore`, `--all-entries` |
| `check_citations.py` | Every cited `path:line` exists in the pinned submodule |
| `check_versions.py` | Every class-version table matches `ClassDef`; prints `NARROWED` for a row it can only partly check |
| `check_pin.py` | `zensical.toml`'s citation commit matches the gitlink |
| `sync_rntuple.py` | The tracked RNTuple copy matches the submodule |
| `inventory.py` | The hand-written `Streamer` list matches the submodule, and every class is resolved in `streamers.toml` |
| `normalize.py` | Masked digests; `--members` and `--per-record` for diagnosing drift |
| `rootfile.py` | An independent pure-Python reader of everything `spec/` specifies, written from the specification rather than from ROOT's code, so a disagreement between the two is detectable. It reproduces `TFile::Map()` exactly |
| `coverage_probe.py` | Not a CI check: how much of an arbitrary file the specification covers, and what blocks the rest |
| `rootcite.py` | Markdown extension turning a citation into a link at the pinned commit |
| `fetch_cern.py`, `fetch_foreign.py` | The corpora; `--headers` for the large files |
| `test_*.py` | 495 unit tests, run in both workflows |

Dropped from the original plan: `dump_streamerinfo.C`, `gen_tables.py` and
`coverage.py`, all three in service of generated member tables (§2.4).

## 5. Status by layer

| Layer | State |
|---|---|
| Conventions | ✅ |
| Container | ✅ all six documents |
| Serialization | ✅ all seven documents |
| Standard classes | ✅ the divergent set; twelve narrow classes ⏸ set aside (§2.4) |
| `TTree` | ✅ records, branches, leaves, baskets, splitting, reading an entry — unsplit and split |
| RNTuple | ✅ upstream tracked, envelopes, linked attribute sets and the type mapping audited over eleven fixtures, thirteen errata; the collection-proxy form ⏸ set aside (§2.6) |
| Appendix | ✅ all eight, `WriterInvariants.md` included (§2.7) |
| Legacy reading (pre-ROOT 6) | ✅ `TBranch` 6–9 specified and read (M6), and every ROOT-written file in `root/roottest/` diagnosed (§8.16); the layouts no available file has ⏸ set aside (§9.1) |
| Release plumbing (licence, citation, changelog, releases) | ✅ §8 item M7; CalVer at milestones since 2026-09-22, decision 9 |
| Writing (`spec/06-writing/`) | ✅ container and subdirectories, object, histograms and profiles, graphs, flat `TTree` with many baskets and with a `TLeafC`, plus the element lists — every object-bearing record in `data/written/` byte-identical to ROOT's (§8.4) |

The phase numbering the earlier drafts used (0 skeleton, 1 foundations, 2 object
layer, 3 bootstrap classes, 4 standard classes, 5 `TTree`, 6 RNTuple, 7 legacy)
is retired. Phases 0–3 and 5 are complete, 4 is complete except the twelve narrow
classes, and what is left of 6 and 7 is listed in §8 by value rather than by
phase.

## 6. Decisions

| # | Question | Decision |
|---|---|---|
| 1 | Scope of "every standard class" | **Revised 2026-09-17.** Not generated tables for ~440 classes: specify the classes whose streamer info does not describe their bytes, and let the generic algorithm cover the rest. The set comes from `inventory.py`, not from an estimate (§2.4) |
| 2 | Normative status | Descriptive of 6.40.04; the pinned submodule is the tiebreaker; errata for suspected ROOT bugs |
| 3 | Write support | **Revised 2026-09-18, extended 2026-09-21.** Reading normative. Writing gets both halves: per-layer invariants, which validate a file whatever wrote it (§2.8), and end-to-end procedures in `spec/06-writing/` for producing one — container, object, histogram, flat `TTree` — at the current class version only, with `tools/rootwrite.py` as the executable form and "ROOT reads it back and says nothing" as the conformance test (§2.9). Free-space reuse, key ordering and updating an existing file are now specified too (§8.12). Still unspecified: basket sizing, and where within the file a record is placed |
| 4 | Upstream relationship | Standalone repo, not blocking on review. RNTuple errata go upstream as PRs; open a conversation with the ROOT I/O team about eventually replacing `io/doc/TFile/` |
| 5 | Fixture distribution | Core corpus committed (<10 MB). Legacy-ROOT and >2 GB cases as release artifacts with a committed manifest — superseded in practice by the two corpora (§3.4, §3.5) |
| 6 | Where a divergent class is specified | **Cross-reference, do not re-home.** A class stays in the layer document where its behaviour arises; `03-classes/index.md` maps every divergent class to wherever that is. `TObject` belongs with buffer framing, `TList`/`TObjArray` with streamer information, `TClonesArray` with collections, `TRef` with references, `TStringLong` with the string encodings |
| 7 | **Version floor** (✅ stated 2026-09-17, `spec/index.md` §Scope) | The specification claims reading for files written by ROOT 4.00 and later, and M4 measured that it works back to 3.04/02. The floor is a property of the file rather than a release number: object decoding needs streamer infos, and a file old enough has none. One corpus file is in that state, `pippa.root` (ROOT 2.24/00), and for it the container layer applies alone: all 517 records are located, none of the 468 objects is decodable (§9.10) |
| 8 | **What is out of scope** (✅ stated 2026-09-17, `spec/index.md` §Scope; **revised 2026-09-21: RooFit is in**) | Four groups. First, the frameworks inside ROOT that define their own persistent classes: the SQL backend, PROOF, both event displays, SOFIE, each with its reason in `streamers.toml`. RooFit was on that list and was removed on the demand argument of §8.13: rootfilespec asked for it rather than reverse-engineer it, the strongest signal this project has had about what to write next. Second, what `TGeo*` fields *mean*, its classes being streamer-info driven anyway. Third, the compression algorithms themselves, as against ROOT's framing of them. Fourth, on the write side, what decision 3 leaves out after its 2026-09-18 revision and its 2026-09-21 extension: earlier class versions, two writers on one file at once, writing a split `TBranchElement`, and ROOT's policy choices. GUI classes are not on this list after all: they are version 0 and forwarding-only, so `ForwardingStreamers.md` covers them |
| 9 | **Versioning and the changelog** (✅ decided 2026-09-22) | **CalVer at milestones, and a changelog scoped to releases.** A semantic version invites a reader to ask what changed *incompatibly*, which is the wrong question for a document that describes somebody else's format. The number that matters is ROOT's; it is stated on the front page and held to the submodule by `check_pin.py` and `check_citations.py`. Releases are therefore `YYYY.MM.DD`, tagged when the specification reaches a milestone. They exist so that the reference files can be vendored and cited from a fixed point, not to signal compatibility. `CHANGELOG.md` was deleted the same day and restored a few hours later, and the reason for the reversal is worth recording. The argument for deleting it was that the git log records what changed and also how each fact was established, so a changelog keeps only the weaker half. That holds for a per-commit changelog but not for this one: a commit body says what was *found*, a changelog entry says what a reader should now do differently, and the 69 entries under `## Unreleased` were the second kind. A dated tag also needs release notes, and generating them from 500 commit bodies at tag time is not the same as writing them when the change is fresh. The changelog stays, scoped to releases and to reader-facing changes only (`AGENTS.md` says which). One release exists under the old scheme, `v0.1.0`, and it stays where it is. |
| 10 | **Third-party files** (✅ decided 2026-09-23) | **Never committed.** roottest and rntuple-validation are LGPL-2.1, which `data/`'s BSD-3-Clause cannot include, and every other corpus is kept out for the same provenance reason: the corpora are read in place or fetched, and only manifests of digests are committed. A fact one of them teaches becomes a fixture by writing a generator that reproduces it. `LICENSE` states the rule and `tools/test_provenance.py` enforces it: a tracked `.root` with no case, or any tracked file identical to a roottest file, fails |

## 7. Open items

1. **When to approach the ROOT I/O team.** The condition (a concrete artifact
   rather than an intention) has been met for some time. The thirteen RNTuple errata
   are against a document the ROOT team owns and maintains, which makes them a
   friendlier first contact than §7.1's bug candidates, and they can bring those
   along. Deliberately deferred until the MVP is out (§8 item M10).
2. ⏸ **`TGeo*` hand-review** — 88 persistable classes, self-contained, present in
   real files. Out of scope by decision 8 unless a blocked record demands it;
   nothing in either corpus does.
3. ⏸ **Markup format if upstreaming happens.** `root/io/doc/` is doxygen with
   `\page`/`\ref`; our tables and bit diagrams are better in plain Markdown.
4. **Reference reader.** Resolved by accident: `tools/rootfile.py` grew into one,
   and it is the strongest completeness check the project has. It stays a
   checking tool that happens to be thorough.
5. **`TTree` sub-plan** — discharged, and its residue is §9.11.

### 7.1 Upstream bug candidates found while writing the spec

Verified against the pinned submodule and against real bytes; **not yet
reported** (§8 item M10).

0. **`TFormula::fAllParametersSetted` is written to file uninitialized.** A
   `TF1("g", "gaus", -3, 3)` never assigns it on any path taken, so what reaches
   the file is ROOT's heap fill pattern: `classes/formula` byte 665 is 0x99 for a
   `Bool_t`. It is deterministic rather than random, because
   `TStorage::ObjectAlloc` `memset`s new `TObject`s with `kObjectAllocMemValue`
   (`root/core/base/src/TStorage.cxx:291-295`). Worth reporting because it is
   silent, and the same mechanism writes any unassigned persistent member of any
   type (`ElementTypes.md` §2.5).
1. **A `std::vector<T>` of an interpreted class writes an unreadable file.**
   `T`'s streamer info is not recorded when the only reference to it is through a
   collection, and there is no warning on the write side; reopening gives
   `CheckByteCount ... read too few bytes`. The direct-member path does warn,
   so this is a bug rather than a limitation. `Collections.md` §9.
2. ~~**The two collection readers disagree on the `kSTLp` version threshold.**~~
   **Withdrawn 2026-09-23.** Only one reader ever sees `kSTLp`: the action-based
   reader has no case for it and hands it to `TStreamerInfo::ReadBuffer`, which
   uses `>= 9`; the `>= 8` belongs to a fixed array of `kSTL`
   (`Collections.md` §6, commit `d187a26`). Numbered in place so the other items
   keep their numbers.
3. **`kGenerateOffsetMap` cannot reach a `TBranchElement`.** Every constructor
   delegates to the default `TBranch()`, which does not copy the tree's
   `fIOFeatures` (`root/tree/tree/src/TBranchElement.cxx:168`), so
   `TTree::SetIOFeatures` silently has no effect on most branches in a real file.
   Source-verified; not yet confirmed by generating such a file.
4. **An empty `TLeafC` string is misread in a multi-leaf branch.** An empty
   string occupies zero bytes, and `TLeafC::ReadBasket` detects that by comparing
   whole-entry offsets (`root/tree/tree/src/TLeafC.cxx:146-166`), which is only the
   same test when the `TLeafC` is the branch's only leaf. Verified at byte level;
   a reproducer is written. `TLeaf.md` §9, and `WritingTrees.md` §4.6 now states
   the writer's side: do not emit the shape.
5. **A `TLeafC` cannot be followed by another leaf in a leaflist.** `fOffset`
   doubles as the in-memory offset, and a `TLeafC` contributes 1
   (`root/tree/tree/src/TBranch.cxx:436`), so `c/C:x/I` reads `x` from the second
   byte of the string. Silent, verified at byte level. `TLeaf.md` §3.2,
   `WritingTrees.md` §4.6.
6. **The suspected `TFile::Recover` gap bug** — banked, still unverified.
7. **An object of an `extending` class cannot be skipped by its byte count.**
   `TBufferFile::SkipObjectAny` seeks to `start + count + 4`
   (`root/io/io/src/TBufferFile.cxx:2499-2503`), and for `TMatrixTSym`,
   `TPointSet3D` and `ROOT::RNTuple` the object continues past that point
   (`Matrix.md` §2.4, `Buffer.md` §2.4). A pointer member is safe, because the
   slot's own byte count covers the extra bytes; a by-value member is not. This
   is reachable only when a schema change makes ROOT skip such a member, so it is
   source-verified and not demonstrated by a file. Verify before reporting.
8. **A `pair<K,V>`'s checksum can be computed before its members are known**, and
   `TClass::GetCheckSum` then caches it forever
   (`root/core/meta/src/TClass.cxx:6655-6666`), so several distinct pairs share
   one value. `data/serialization/pairs.root` has three pairs all with
   `0x0b5fb752`. This is not data loss for ROOT, which resolves the value class by
   declared type name, but it is a hazard for every other reader: the obvious
   checksum-to-info table decodes two of those three as the wrong type.
   `Collections.md` §8.2.
9. **`fBranchCount` can name another object's counter branch, and ROOT then
   loses the data silently.** The writer builds the counter's name from the
   branch's own name and looks it up with `TTree::GetBranch`
   (`root/tree/tree/src/TBranchElement.cxx:432-438`), which searches the whole
   tree and returns the first match. A tree holding two split objects of one
   class whose sub-branches carry no parent prefix therefore records the *first*
   object's counter on both, and the read path uses it as it stands (`:4649`).
   Byte-verified, and the strongest candidate on this list. In `alice_ESDs.root`
   (ROOT 5.16/00, published by the ROOT team) `PrimaryVertex`'s `fIndices` points at
   `SPDVertex`'s `fNIndices`, which is 0 for all 20 entries, while its own entries
   are 37, 45, 13 and 27 bytes: `1 + n × 2` for counts of 18, 22, 6 and 13. ROOT
   reads no indices at all and reports nothing. The bytes are intact; only the
   pointer is wrong. `ReadingEntries.md` §4.1 and erratum 6.
10. **Writing a `std::map` field to an RNTuple aborts — when the map has no
    compiled dictionary.** *Narrowed 2026-09-23 (`PLAN-corpus.md` C17).*
    `Fill()` reaches `R__ASSERT(0)` in `TGenCollectionProxy__VectorNext`, a
    function whose comment is "Should not be used"
    (`root/io/io/src/TGenCollectionProxy.cxx:1528-1530`), and assigning to the
    field first segfaults even earlier; the model and the writer are built
    without complaint. The cause is neither `std::map` as such nor the API. Over
    eleven instantiations, the ones that write are those whose class under
    RNTuple's normalised name has a dictionary: `map<int,int>`,
    `map<string,float>`, `map<string,int>`, `map<double,int>`, all in
    `libmapDict`/`libmap2Dict` (`root/core/clingutils/src/mapLinkdef.h`), and
    `map<int,float>` writes too once ACLiC compiles one. `MakeField` and
    `AddField(make_unique<RField<M>>)` behave alike, empty or filled.
    rntuple-validation's `map<std::string, std::int32_t>` works because it ships a
    dictionary. The clearest case is `map<long,float>`: it has a dictionary and
    still aborts, because RNTuple normalises it to `std::map<std::int64_t,float>`,
    which on macOS names `map<Long64_t,float>` and has none. The reportable bug is
    therefore narrower and clearer than before: RNTuple accepts a collection field
    whose proxy is emulated and then aborts in `Fill()`, instead of refusing it
    when the model is built. Reproducer in `spec/05-rntuple/NOTES.md` §5.
    `rntuple/map` is the fixture the finding made possible: all four map types,
    each an instantiation with a shipped dictionary.

11. **Writing an object of an emulated class does not complete.** `WriteObjectAny`
    with a `TClass` in the `kEmulated` state (`Head` read from
    `uproot-issue-214.root`, a class with no dictionary) segfaulted on one attempt
    and ran for over three minutes without finishing on another. Reading is fine:
    `TKey::ReadObjectAny(nullptr)` returns the object and the emulated `TClass`
    reports the file's own class version, 2, which is the fact
    `spec/06-writing/index.md` §3.1 needed. **Banked, not diagnosed.** The call may
    simply be unsupported for an emulated class, though nothing in its
    documentation says so, and the usage needs checking before this goes anywhere.
12. **`hadd` silently truncates strings.** *Reproduced 2026-09-18, with data loss;
    the strongest candidate on this list alongside item 9.* A fast clone raises a
    `TLeafC`'s `fMaximum` through `TLeafC::IncludeRange`
    (`root/tree/tree/src/TTreeCloner.cxx:343`,
    `root/tree/tree/src/TLeafC.cxx:98-109`) and never raises `fLen`. Baskets are
    copied wholesale, so `TLeafC::FillBasket`, the only thing that raises `fLen`
    (`root/tree/tree/src/TLeafC.cxx:82`), never runs. On read `fLen` *is* the
    buffer size: `ReadFastArrayString` clamps the copy to `fLen - 1` characters
    (`root/io/io/src/TBufferFile.cxx:1315`). Merging a file of short strings with a
    file of long ones therefore truncates every long string to the short file's
    length, silently, while the bytes on disk stay complete. Measured: `hadd -f`
    over two files whose `/C` branches hold 2- and 10-character strings gives
    `fLen` 3, `fMaximum` 11, and `"0123456789"` read back as `"01"` for every
    entry of the second input. `data/ttree/leafc-truncated.root` is the fixture,
    built with `CopyEntries(..., "fast")` rather than `hadd` so it is
    reproducible, and its `merged` tree's second basket holds a count byte of 10
    in front of all ten characters. Every reader that sizes a buffer from `fLen`
    inherits the bug. `TLeaf.md` §9.1 says to size from the counted string in the
    entry instead, and `tools/rootfile.py` does, so this project reads the file
    correctly where ROOT does not. Related to items 4 and 5, the other two ways a
    `TLeafC` loses data.
13. **`RNTupleWriter::CloseAttributeSet` rejects every valid handle.** It locks
    the handle's `weak_ptr` and throws "Tried to close an invalid
    AttributeSetWriter" when the lock *succeeds*
    (`root/tree/ntuple/src/RNTupleWriter.cxx:213-216`); for an expired handle it
    would go on to dereference null. Reproduced on 6.40.04. Nothing is lost,
    because the writer's destructor commits the set anyway, but a set cannot be
    closed early, which is the function's only purpose. `spec/05-rntuple/NOTES.md`
    §8.
14. **A refused duplicate attribute set name leaves an orphan header in the
    file.** `CreateAttributeSet` checks for a duplicate only after cloning the
    sink and building the set's fill context, which writes the header envelope
    (`root/tree/ntuple/src/RNTupleWriter.cxx:189-199`,
    `root/tree/ntuple/src/RNTupleFillContext.cxx:33`). The exception is thrown,
    and a 431-byte `RBlob` nothing references stays in the file. Harmless to
    readers, but it is dead space ROOT never frees. The other two name checks run
    first and leave nothing.
15. **An attribute set with an untyped user field is written and cannot be
    read.** The writer accepts an untyped record in the user model; the reader
    rebuilds each user field with `RFieldBase::Create(name, typeName)`
    (`root/tree/ntuple/src/RNTupleAttrReading.cxx:51`), which refuses the empty
    type name: "no type name specified for field". Reproduced on 6.40.04. The
    writer should refuse it, or the reader rebuild it from the descriptor.

## 8. MVP — what "done enough to publish" means, and the work to get there

When this section was written, on 2026-09-17, the specification was already more
complete than anything else available, and the checks behind it were sound. What
stopped it being a book a third party could adopt was a small, nameable set of
things: one published claim that was wrong, three missing on-ramp documents, an
unstated scope, and no licence. All four were resolved the same day (§8.1).

### 8.1 Release criteria

**All six are met as of 2026-09-17, and 0.1.0 is tagged.** What each one was, and
what satisfied it:

1. **No published claim is known to be wrong.** ✅ as of M1; the `delegating`
   claim was the violation, and M6 found four more in the `TBranch` and `TLeaf`
   invariants. This criterion is not met once and for all; the two corpora keep
   testing it. §8.13 shows this: the first outside review broke it again on
   2026-09-21 with three defects, all three fixed the same day, and the worst of
   them had stood because an invariant was published without a check.

   The corpus survey of `PLAN-corpus.md` broke it again on 2026-09-22 with four
   more, for the same reason: all four were in populations nothing was checking.
   No fixture and no corpus file had a compressed RNTuple page, a basket written
   before ROOT 4.02, a `TDatime` stored as a record, or an RNTuple blob key from
   6.34/6.35. All four were fixed the same day, two with a new fixture.

   Three more were found by checking the §9.1 witnesses rather than by any failing
   check: a version-1 directory and no header UUID at ROOT 3.03/02, where
   `Directory.md` §7 and `FileHeader.md` §8 said 3.03/01 had moved on, and
   `TLeafF16`/`TLeafD32` version 2 dated to 6.40 when `v6-38-00` already has it.
   All three are release boundaries, and the submodule's tags settle each one:
   `git show v3-03-07:base/inc/TDirectory.h` reads a class version at a release
   directly, back to ROOT 1, and it is the check to run before writing one.

   Two more came from C13's RNTuple tier, found by a checker failing on a
   ROOT-written file: a free span's marker can be missing (6.34's RNTuple writer),
   and a member-wise base is one column per member, not one read per element.
   Both were fixed the same day, with the ROOT commit and line that explain them.
2. **Scope is stated**: which ROOT releases the spec covers for reading, and what
   is deliberately out of scope (decisions 7 and 8). ✅ M4, as `spec/index.md`
   §Scope.
3. **A reader can find the path in**: an ordered implementation checklist and a
   pitfalls page, both linking into the normative text. ✅ M3.
4. **Zero unexplained failures over both corpora.** ✅ as of M2: the last one,
   `aod_flushed.root`, is cleared.
5. **Citable and reusable**: a licence for `spec/` and for `tools/`+`gen/`, a
   `CITATION.cff`, a version number, a changelog, a tagged release, and a
   published site. ✅ M7. The version number was reconsidered on 2026-09-22
   (decision 9): the criterion wanted the work to be citable and the fixtures
   vendorable, and a dated tag does that without claiming a semantics the
   document does not have. The changelog was deleted the same day and restored;
   decision 9 records why.
6. **The front pages are accurate.** ✅ M4, and re-measured at M5 and M6; both
   quote the counts the checks print.

### 8.2 The work, in order

Each item says why it is in the MVP, what it touches, and what proves it done.
Items M1–M7 are the MVP; M8–M10 are the next tier and are listed so the order is
explicit.

**M1 — ✅ done 2026-09-17. `delegating` was wrong for three classes, and the
inventory missed two.**
*The only known-wrong published claim, and it mis-decoded a class real physics
files contain.*

`HandWrittenStreamers.md` said of `delegating` that the bytes are "exactly what
the streamer info describes". For three of the 35 that was false. The read branch
consumes more bytes after `ReadClassBuffer`, in all three cases outside the byte
count, so `CheckByteCount` succeeds for a reader that stops early:

| Class | What follows `ReadClassBuffer` | Cite |
|---|---|---|
| `TMatrixTSym<Element>` | the upper-right triangle, `fNcols-i` elements per row; the lower triangle is reconstructed, not read | `root/math/matrix/src/TMatrixTSym.cxx:2040` |
| `TPointSet3D` | when `fOwnIds` is set, an `Int_t` and then that many object references | `root/graf3d/g3d/src/TPointSet3D.cxx:156` |
| `ROOT::RNTuple` | an 8-byte XXH3-64 checksum | `root/tree/ntuple/src/RNTuple.cxx:25-49` |

`tools/inventory.py` now has a fourth kind, `extending`, detected by looking for
buffer I/O after the call in the same block and before any `return`, `break` or
`case` label; `custom` and `extending` are the two kinds the sidecar must
resolve. Building it found three further things, each a bug in the tool rather
than in ROOT:

- **A qualified out-of-line definition was invisible.** `DEFINITION` matched only
  an unqualified name, so `void ROOT::RNTuple::Streamer` and
  `void RooWorkspace::CodeRepo::Streamer`
  (`root/roofit/roofitcore/src/RooWorkspace.cxx:2427`) were not in the inventory
  at all. The first is an `extending` class, so the omission told a reader there
  was nothing to do. The count went 185 → 187.
- **A version dispatch need not be a comparison.** `RooBinning` switches on the
  version word and hand-decodes version 1 in a `case`
  (`root/roofit/roofitcore/src/RooBinning.cxx:298`). Tested for comparisons alone
  it looked `delegating`; it is `guarded`. It was also the only false positive of
  the extending detector, which is why the window stops at `break` and `case`.
- **No `guarded` class reads past `ReadClassBuffer`**, so that table's "nothing
  for a current file" stands. Checked over all 89, and pinned by a test.

Specified as `spec/03-classes/Matrix.md`, with `classes/matrix` (48 assertions:
a 3 × 3 `TMatrixDSym`, a 2 × 2 `TMatrixFSym` for the element width, an ordinary
`TMatrixD` and `TVectorD`, and a `TMatrixDSym` inside a `TObjArray` so both byte
counts are visible), seven invariants in `check_invariants.py`, and a reader in
`rootfile.py`. Three findings from the work:

- **A `TMatrixTSym` has no streamer info of its own in any file.** Its `Streamer`
  hands `ReadClassBuffer` the `TClass` of `TMatrixTBase<Element>`, and recording
  an info is a side effect of `WriteClassBuffer`. The file therefore has the
  base's info, and the version word on disk is the base's class version, 5.
  `TMatrixTSym`'s own `ClassDef` version 2 never reaches a file. Confirmed over
  both corpora: no file has such an info, and five files have
  `TMatrixTBase<double>`.
- **A byte count is a lower bound, not a length.** Now `Buffer.md` §2.4, with
  invariant 9.9 stating the exception explicitly instead of the checker applying
  it silently.
- **`uproot-issue-359.root` had been the witness all along**: five
  `TMatrixTSym<double>` records written by ROOT 5.34/34, at 29 × 29 and 58 × 58,
  each reported as "consumed 48 of 3528", which is the framed prefix. They now
  decode, and the foreign corpus is at 0 failures with one more branch-basket
  reached.

**M2 — ✅ done 2026-09-17. The list a reader cannot derive from a file is
published.**
*It clears the last failure over either corpus and supplies the one piece of
out-of-band knowledge the format requires.*

For a class whose `ClassDef` version is `≤ 0` **and** which was selected with a
plain `#pragma link C++ class X;`, `rootcling` generates a `Streamer` that calls
each base's `Streamer` and nothing else: no version word, no byte count, no
members (`root/core/dictgen/src/rootcling_impl.cxx:1332-1367`, chosen at
`root/core/clingutils/src/TClingUtils.cxx:3016`). Both generators write a
streamer info and both record class version 0, so nothing in a file
distinguishes them.

`tools/inventory.py` now extracts that set too, into a second CI-checked
document, [`spec/99-appendix/ForwardingStreamers.md`](spec/99-appendix/ForwardingStreamers.md):
534 classes across 46 modules, listed by module because the shape of the set is
part of the answer. It also cross-checks the two lists against each other: a
class cannot both supply a `Streamer` and have one generated for it, and an
overlap fails `--check`.

What the measurement changed about the plan's own expectations:

- **The set is not only GUI classes.** ROOT's pure-subclass containers are in
  it (`THashList`, `TSortedList`, `TOrdCollection`, `THashTable`, `TPair`,
  `TSeqCollection`), at version 0 because they add no persistent state to their
  base. Writing only the bases is the design, not an accident.
- **Three of the 534 occur in the corpora**, not the two this plan predicted:
  `TSeqCollection` (a `kBase` of `TList` and `TObjArray`, 214 of the 222
  corpus files that have a StreamerInfo record),
  `THashList` (the type of `TAxis::fLabels` and `TGeoManager::fHashPNE`, so any
  labelled axis writes one, 37) and `TVirtualPerfStats` (1). No record in
  either corpus has one as its class.
- **Here the streamer info is correct, only unframed.**
  `TStreamerInfo::Build` skips every data member of a version-0 class
  (`root/io/io/src/TStreamerInfo.cxx:552-554`), so a modern info lists exactly
  the bases the streamer writes. Two g4tools files whose headers claim ROOT
  4.00/00 list `TSeqCollection::fSorted`, a member no forwarding streamer has
  ever written; all 50 ROOT-written files older than ROOT 5 that carry the info
  list the base alone (corrected 2026-09-23, §8.15).

`rootfile.py` hardcodes the three and reads them by the published procedure, so
`aod_flushed.root`'s `TTreePerfStats` now decodes: its `TVirtualPerfStats` base
is ten bytes, a bare `TObject`, and `fReadaheadSize` lands on 256000 exactly
where §9.9's byte count put it. **Both corpora are now at 0 failures.**

**M3 — ✅ done 2026-09-17. The on-ramp.**
*The difference between a correct specification and a usable one; all three
pages are collation rather than research.*

- ✅ [`ReaderChecklist.md`](spec/99-appendix/ReaderChecklist.md) — the whole
  specification as a work order. Eight milestones, each one a state in which
  something works: list a file's contents, decompress, read the streamer infos,
  decode an arbitrary object, then the classes the info gets wrong, an unsplit
  tree, a split tree, the rest. Each names its documents, its fixtures and the
  checks worth running there. It ends with two sections the layer documents
  cannot hold: how to know you are right, and what can be left out.
- ✅ [`Pitfalls.md`](spec/99-appendix/Pitfalls.md) — forty-five of them, in six
  groups, each a sentence or two and a link to the section that specifies it.
  Two are ROOT's bugs rather than a reader's and are labelled as such.
- ✅ [`Bibliography.md`](spec/99-appendix/Bibliography.md) — ROOT's own
  documentation with what each part is good *for* (the RNTuple spec is real; the
  TFile docs are a source of questions; the reference guide tells you what a
  member means and nothing about how it is written), the five other readers built
  without a specification, and the two corpora.

`spec/index.md` now opens with the checklist, since "I am here to implement
something" is the common case, and two stale claims on that page were removed
along with it.

**M4 — ✅ done 2026-09-17. The scope is stated, and the front pages are
accurate.**
*A reader could not tell whether a gap was unknown or deliberate, and the README
still described the repository as it was at 29 fixtures.*

`spec/index.md` gained a **Scope** section: descriptive status, reading against
writing, how far back it reads, what is missing rather than excluded, and the
four out-of-scope groups. Writing it meant measuring the floor rather than
asserting it, and the measurement changed decision 7:

- **The floor is a property of the file, not a release number.** Object decoding
  needs streamer infos. `pippa.root` (2.24/00) has none: all 517 of its records
  are located and framed, and none of its 468 histograms is decodable. But
  `mlpHiggs.root` (3.04/02) and `H1display.root` (3.05/07) do have them and do
  decode. Decision 7's "older files carry no streamer infos at all" was true of
  one file and wrong as a rule; the claim is now "specified for 4.00 and later,
  works in practice back to 3.04/02".
- **`TBranch` is the only class in 252 files below a hand-written threshold.**
  Every version of `TH1`, `TGraph`, `TFormula`, `TF1`, `TAxis`, `TTree` and
  `TLeafObject` that occurs anywhere in either corpus is above the version at
  which that class becomes streamer-info driven. This makes §9.1's legacy
  branches a low priority rather than a hole, and the front page now says so.
- **Of the ten `gap` classes, only one occurs in either corpus**: `TASImage`,
  8 records in `galaxy.root` and `gallery.root`. The other nine are named but
  unwitnessed. *Seven since 2026-09-22*: the three `graf2d/gviz` wrappers write
  nothing at all and are specified as such (`Buffer.md` §2.3), so six remain
  unwitnessed.
- **GUI classes are not an out-of-scope group.** Decision 8 listed them; the M2
  extraction shows that it did not need to: `gui/gui` alone contributes 197
  classes to `ForwardingStreamers.md`, and no `TG*` class has a hand-written
  `Streamer` at all. The four groups that remain are the frameworks with their
  own persistent classes, `TGeo*` semantics, the compression algorithms as
  against ROOT's framing of them, and writing.

The blocked-record census behind the new table, over both corpora: 31 628
records, 94% decoded. The blocked ones are 468 with no streamer info (the floor),
216 RooFit (out of scope), 137 LZ4 payloads with no `lz4` package here, 50
`TBranch` 7/8/9, 8 `TASImage`, and a tail of single records. Two of those six
causes are the project's own, and both are named on the front page.

Re-measured 2026-09-21, after RooFit came into scope: 31 734 records, 94.9%
decoded, and RooFit no longer appears in the census. What is left is 463
no-streamer-info histograms (the floor), 132 LZ4 payloads with no `lz4` package
here, 8 `TASImage`, and a tail. The only class-shaped entry that remains is
`RooWorkspace::CodeRepo`, which is now a `gap` rather than out of scope.

`README.md` was rewritten around the same numbers: 65 fixtures, 1563 assertions,
1111 citations across 39 documents, 226 corpus files at 0 failures, and the
reader's checklist as the first link rather than the last.

*Also corrected while checking M6's own claim*: directory record versions 1, 3
and 4 are not blocked. `rootfile.py` reads all 31, and `pippa.root`'s 24
version-1 records (no UUID at all) walk clean. What they lack is a fixture. The
only directory form nothing exercises is version 2, which occurs in neither
corpus, and it is the one where ROOT's own reader is suspect (`Directory.md`
§7).

**M5 — ✅ done 2026-09-17. `LargeFiles.md`.**
*The only layout in the container layer that no fixture can reach, and the last
document §2.2 was missing.*

[`spec/01-container/LargeFiles.md`](spec/01-container/LargeFiles.md): the five
switches and their conditions, wide diagrams for the header, the key and the
`TFree` entry, one 5.25 GB file walked byte by byte, and six invariants. Writing
it against real bytes rather than against the source alone found two things the
specification had wrong or missing, both about which condition widens what:

- **A key's width is not decided by the key's own offset**, contrary to what
  `Directory.md` §3 said. Every writing constructor calls `TKey::Build` with
  `filepos == -1` and `Build` substitutes the file's current `fEND`
  (`root/io/io/src/TKey.cxx:456`), so a key written into a reused gap near the
  front of a large file is wide with a small offset in it. `volume.root` has
  exactly that: `fVersion` 1004 at offset 105 159 358, while the key at `fBEGIN`
  in the same 5.25 GB file is `fVersion` 4 and narrow. A non-zero `fPidOffset`
  is the second, size-independent trigger.
- **The directory record has two writers with different conditions.**
  `FillBuffer` widens on the three offsets it is about to write
  (`root/io/io/src/TDirectoryFile.cxx:751-759`); `TDirectoryFile::Streamer`
  widens on `fEND` (`:1827`). Only the first produces the on-disk record (the
  root directory record of that same 5.25 GB file is version 5, narrow), so the
  mismatch matters to a writer and not to a reader.

Reading real bytes also showed two more things:

- **`Directory.md` §6.1's uninitialised slack is now witnessed, not just
  cited.** The key list of `volume.root` has `fObjlen` 65 for a count and one
  53-byte image, and the eight bytes past them read `00 04 00 62 00 04 00 62`:
  heap, and heap that looks like the start of a key. A length-driven parse takes
  it as a second entry.
- **The boundary from below is the strictly-greater-than test.** The trailing
  free entry's `fLast` is the next whole multiple of 1 000 000 000 above `fEND`,
  so a 1.997 GB file's sentinel is exactly 2 000 000 000. That is not *greater
  than* the threshold, so the file has no wide entry anywhere.

The six invariants are checked by `tools/fetch_cern.py --headers`, which now
implements them as a pure function over its parsed reading, and
`tools/test_large_files.py` shows each one catching a violation: twelve mutation
tests, since `check_invariants.py` has no file large enough to corrupt.
`rootfile.py` gained `parse_free_entries`, which keeps each entry's version word
so that invariant 4 can be stated at all.

**M6 — ✅ done 2026-09-17. The legacy layouts the corpora already contain.**
*The largest remaining in-scope blocked category over files ROOT wrote. It turned
out to be half specification and half an overstated coverage number.*

`TBranch.md` gained §13.1, the member order below class version 10, and
`rootfile.py` reads it. The three reproducers all decode: `mlpHiggs.root`
(ROOT 3.04/02, version 7), `uproot-from-geant4.root` (g4tools, header 4.00/00,
version 8) and `stock.root` (4.00/07, version 9). That is 116 legacy branches, each parse ending
exactly on its byte count, and 17 tree records that had been `PARTIAL` since the
corpora were added. `coverage_probe.py` no longer names `TBranch` anywhere, which
leaves **`TASImage` as the only specification gap either corpus hits**, with
`RooWorkspace::CodeRepo` beside it once RooFit was specified on 2026-09-22.

The legacy layout differs from what the version table suggested: `fEntries`,
`fTotBytes` and `fZipBytes` are `Stat_t`, a double; `fEntryNumber` and every
element of `fBasketEntry` are 4 bytes; and the three counted pointers are read in
full, `fMaxBaskets` values each, whatever their flag byte says. Two further
findings:

- **The recorded streamer info is right, element for element, on all 116.** The
  hand-coded order and the info's order agree at versions 7, 8 and 9. The files
  did describe the legacy layout; what is missing is any way to know that without
  checking, which is why `rootfile.py` reads the order from the source and
  verifies the byte count rather than trusting the info. The only member where
  they disagree is `fBasketSeek` at version 9 (§13.3), which is where a reader
  would most want to trust it.
- **No file in either corpus has the flag byte 2** that makes `fBasketSeek` 8
  bytes wide. All 116 write 1. The width selector is specified from the source
  and unwitnessed; it needs a version-9 file with baskets past 2 GB.

Reading 116 branches nobody had read before broke four invariants, and in each
case the invariant was at fault, not the files:

| Invariant | Was | Is, and the witness |
|---|---|---|
| `TBranch` 11.1 | `fMaxBaskets == max(fWriteBasket + 1, 10)` | `>=`, with equality from class version 9 on. At version 7 the writer allocated a flat **1000**: `mlpHiggs.root`, 12 003 bytes of arrays per branch. Version 8 was first put with 9, on a g4tools file; ROOT writes 1000 there too (corrected 2026-09-23, §8.15) |
| `TBranch` 11.3 | with an embedded basket, `fBasketEntry[fWriteBasket]` is **below** `fEntryNumber` | **at most**: an embedded basket may be empty, 92 branches in three files |
| `TBranch` 11.9 | `fBaskets` holds `fWriteBasket + 1` slots | the slot count is not fixed by `fWriteBasket` — g4tools writes `fMaxBaskets` slots (22 branches), `alice_ESDs.root` writes one *more* than `fWriteBasket + 1` and ROOT never reads it, and a trimmed trailing null makes it fewer |
| `TLeaf` 10.6 | a branch whose leaves are all fixed-size has no entry-offset array | only when its `fEntryOffsetLen` is 0. `uproot-issue-250.root` (g4tools) leaves it at the default 1000 on a `TLeafD` branch and its baskets have offsets 8 bytes apart |

**The coverage number.** The four invariants above were reachable only because
refusing version 10 had also refused `alice_ESDs.root`, a ROOT 5.16/00 file whose
baskets are all embedded. Chasing that turned up a larger problem: neither entry
check had ever looked at an embedded basket. The leaf-driven check iterated the
baskets *below* `fWriteBasket` and an embedded one sits *at* it, so 1266
branch-baskets were in neither the numerator nor the denominator of the
`ENTRIES` line. The published 99.7% was measured over the wrong denominator.

Both halves are fixed. `check_invariants.py` now checks the embedded basket for
`TLeaf` 10.7, and `leaf_counts` reads an embedded counter basket out of the
`TTree` payload. That closes the four `ttree/branch-clones` skips that §8.3
called the only merely-unimplemented skip in the suite. The corrected figures:

| | Before M6 | After |
|---|---|---|
| Fixtures | 85 of 91, with 5 plumbing skips | **94 of 96**, and neither remaining skip is plumbing |
| Both corpora | 25937 of 26011 (99.7%), embedded baskets invisible | **26948 of 27949 (96.4%)**, 0 failures |

The 1001 skips that remain are 920 embedded baskets that `TreeReader` cannot
fetch (M8, now the largest single item in the project), 48 collections whose value
class has no streamer info in the file, 18 hand-written streamers and 15 baskets
that could not be read here. The first and last are plumbing; the middle two are
things no reader could decode.

*Left from M6's original scope*: `TStreamerElement` at base version 2 and
`TStreamerInfo` record versions 2/4/5/6 are read and produce 0 failures, but
`StreamerInfo.md` still describes their shape only in passing; and the directory
record versions need a fixture rather than a reader (M4).

**M7 — ✅ done 2026-09-17. Release plumbing, and version 0.1.0.**
*Without it the reference files cannot legally be vendored as test vectors, which
is the main way a third party would use this.*

- **`LICENSE`** — CC-BY-4.0 for `spec/` and the prose, BSD-3-Clause for `tools/`,
  `gen/` and `data/`, with the full texts in `LICENSES/`. The BSD half matters
  most: a closed-source reader can vendor a fixture and its `case.toml` without
  asking. The file also says two things §2 had not: the `root/` submodule is
  ROOT's under LGPL-2.1-or-later and is not content of this repository, and
  `spec/05-rntuple/BinaryFormatSpecification.md` is not ours to licence. It is
  ROOT's document, tracked verbatim, which is also why corrections to it go in
  `ERRATA.md`. It ends with a non-affiliation notice: where this specification
  and ROOT disagree, ROOT is right, as a licensing statement as much as a
  technical one.
- **`CONTRIBUTING.md`** — the two-witness rule first, then the mechanics: adding
  a case, the `case.toml` format, the two traps (repo-relative output paths; that
  fixtures cannot be byte-reproducible and `--accept` is the only way to re-record
  a digest), the libc++/libstdc++ container loop for a cross-platform `DRIFT`, how
  to write a document, and what the two corpora mean (`gen/cern/` is evidence,
  `gen/foreign/` is a lead). It states that a correction is more welcome than an
  addition and needs no fixture, which nothing in the repository had said.
- **`CITATION.cff`**, **`CHANGELOG.md`**, and the version in three places that
  cannot drift silently: `[project.extra]` in `zensical.toml`, the front page, and
  the citation file. Amended by decision 9 on 2026-09-22: of those three places
  only the citation file still has a version. The other two give the *ROOT*
  release instead, which is the number a reader needs and the one the checkers can
  hold in place. The changelog stays, scoped to releases.
- **Pages already serves the current build**: `LargeFiles/` and
  `ReaderChecklist/`, both published today, answer 200 at
  <https://ariostas.github.io/root-io-spec/>. No deploy work was needed.

*A near miss in `zensical.toml`*: TOML tables are positional, so inserting
`[project.extra]` above `nav` silently moved `nav` into it. The strict build
reported "No issues found" and built an auto-generated navigation instead. A
config table has to go after every key of the table it follows, and the check
that catches this is grepping the built HTML for a nav entry, not the build's own
exit code.

### 8.3 Next tier, after the MVP

**M8 — ✅ done 2026-09-17. `TreeReader` and the embedded basket.**
*The largest coverage item in the project, and it found two new facts as well.*

`TreeReader` now takes the `TTree` record's payload and reads a basket that was
never written as a record. `basket_for` consults `Branch.embedded` when
`fBasketSeek[i]` is 0, and the raw block start plays the part the record offset
plays for a basket of its own, including as the decoder's buffer base, since ROOT
reads the block into the basket's own buffer rather than sharing the `TTree`
record's object map. `ReadingEntries.md` §1 now says a basket need not be a record.

**Both corpora: 28059 of 28126 branch-baskets, 99.8%, 0 failures**, up from
26948 of 27949. The remaining 67 skips are of two kinds and neither is
unimplemented: a collection whose value class has no streamer info in the file,
and a class whose `Streamer` is hand-written. Over `gen/cern/` it is 1696 of 1696,
100%.

Decoding those 920 baskets for the first time turned up two facts, both now
specified and both byte-witnessed in `alice_ESDs.root`:

- **A ROOT bug that loses data** — §7.1 item 9, the strongest candidate on that
  list. `fBranchCount` is set from a counter name looked up over the whole tree,
  so two split objects of one class both point at the *first* object's counter;
  ROOT reads 0 indices for a branch whose entries hold 18, 22, 6 and 13. A reader
  should resolve the counter among the branch's siblings (`ReadingEntries.md`
  §4.1), and the entry's byte span is the cross-check that catches the
  difference.
- **A container's member needs one count per object** (`ReadingEntries.md` §4.2).
  For `fType` 31 or 41 whose element is itself `T *x; //[n]`, the entry is, per
  object, one flag byte then that object's values, and the per-object counts are a
  column in the sibling branch holding `n`. `Tracks.fTPCClusterMap.fAllBits` is
  1848 bytes = 88 × (1 + 20), against 88 objects and 88 counts of 20. Nothing in
  the file points from the member to its counter (`fBranchCount` on an `fType` 31
  branch names the *master* branch), so §4.1's name rule is the only way to find
  it.

**M9 — ✅ done 2026-09-18. The RNTuple type mapping is audited.**
*The only part of the RNTuple document that cannot be checked against the
serializer, only against a file of that type, so it advanced one fixture at a
time, six of them.*

| Fixture | Audits |
|---|---|
| `rntuple/fundamental-types` | the default column per C++ type, and the uncompressed rule |
| `rntuple/collections` | fourteen stdlib types: `vector`, `RVec`, `array`, `variant`, `pair`, `tuple`, `bitset`, `unique_ptr`, `optional`, `set`, `atomic`, `string`, nested collections, `Double32_t` |
| `rntuple/user-class` | a class, its base class as `:_0`, two enums, a `//!` member, the type version and checksum |
| `rntuple/projected` | projected fields, alias columns, `RNTupleCardinality` in both widths |
| `rntuple/untyped` | untyped collections and records — a role with an empty type name |
| `rntuple/streamed` | structural role 0x04, its `Index64` + `Byte` columns, and the extra type information record |
| `rntuple/soa` | flag 0x08, the last flag bit no fixture reached |
| `rntuple/map` | added 2026-09-23: `map`, `unordered_map`, `multimap`, `unordered_multimap` — and two page locators aliasing one page |

Each claim is checked by a test that parses it out of the tracked copy rather
than transcribing it, so neither a change to the document on a submodule bump nor
a change to ROOT's defaults can go unnoticed. Four errata came out of it:

- **7** — `Double32_t` keeps `SplitReal32` in an uncompressed ntuple, where
  every other default drops to unsplit, because its override runs after the
  uncompressed adjustment and ignores it (`RFieldBase.cxx:892-915`).
- **8** — the field record's `Type Version` is a signed class version in an
  unsigned word, so a class with no `ClassDef` arrives as 0xFFFFFFFF
  (`RFieldMeta.cxx:645`).
- **9** — the extra type information's content is a length-prefixed string,
  which the record's layout does not show (`RNTupleSerialize.cxx:389-391`): there
  are four bytes between the type name and the first byte of the `TList`.
- **10** — that record is in the footer's schema extension, never in the header
  where the document introduces it, because the set of streamed classes is only
  known at commit (`RPageStorage.cxx:1290-1310`). A reader that looks where the
  document points finds nothing, on every file with a streamed field.

Three more facts are ROOT's rules rather than the document's, each hit while
building a fixture: a top-level field of a streamer-mode class is refused
outright (`RFieldMeta.cxx:95`), so the streamed form exists only under a native
field; an SoA class and its record must have the same class version
(`RFieldMeta.cxx:707`); and a `std::map` whose instantiation has no compiled
dictionary aborts in `Fill()` (§7.1 item 10).

The prose sections are audited too, and did not need fixtures. *Limits* is
arithmetic over encodings this project had already checked. *Naming* is clean from
both sides: the validator's four characters plus control codes, and the writer
refusing an empty name, which the validator itself does not check. *Defaults*
matches `RNTupleWriteOptions`, with one omission worth knowing: the undocumented
`fInitialUnzippedPageSize` of 256 is why a small ntuple's first page is 256 bytes.
*Notes on Backward and Forward Compatibility* is reader requirements, and ROOT
follows the only MUST: it refuses an unknown feature flag
(`RNTupleSerialize.cxx:1869-1877`).

`rootfile.py` gained what the audit needed: the two version words of a field
record, the alias column list and the extra type information list, neither of
which it had parsed before.

*What is left is one row*: classes with an associated collection proxy. The
document says the associative half is not implemented in ROOT at all, and the
sequential half needs `TClass::SetCollectionProxy` with a `TCollectionProxyInfo`,
which is a compiled template instantiation rather than the runtime attribute that
made the streamed and SoA fixtures possible. `NOTES.md` §4 records it as the only
unaudited form.

**Added 2026-09-24: linked attribute sets.** Until then *Linked Attribute Sets*
was set aside beside the collection-proxy form, audited only as far as the
footer's record frame and only by reading `SerializeAttributeSet`.
`rntuple/attributes` is the fixture: a main RNTuple linking two sets, `runs` and
`flags`, with different user schemas, overlapping ranges and a range of length 0,
87 byte assertions. `rootfile.py` now reads a footer, a locator, a page list and
the values of a fixed-width column, and follows each attribute set record to its
anchor; `check_invariants.py` applies the three restrictions, the name rules and
schema 1.0's fields to every set it finds, and `test_rntuple.py` corrupts copies
of the fixture to show that each check fires. Three errata:

- **11** — the footer's attribute set list exists only from format 1.0.1.0;
  every older footer ends after the cluster groups, which ROOT's reader knows
  (`RNTupleSerialize.cxx:2015-2017`) and the document does not say. Found by
  reading footers across the corpus: all 26 anchors of 1.0.0.x in `gen/foreign/`,
  and `RNTuple.root`, have no list.
- **12** — "Attribute Anchor Uncompressed Size" is 78, the whole anchor object:
  the six bytes of erratum 2 as well as the checksum the document mentions
  (`RMiniFile.cxx:1359`). A reader of the document expects 72. Next to it, not an
  erratum but a trap: the locator names the anchor key's payload, and that key is
  in no directory's key list (`NOTES.md` §8).
- **13** — ROOT's reader refuses any fourth field, whatever the minor version,
  where the document says a newer minor version's fields are to be ignored
  (`RNTupleAttrReading.cxx:34-38`). Shown by probing with a footer patched to
  point at a four-field RNTuple ROOT wrote.

ROOT enforces restrictions 2 and 3 and the name rules on write and none of the
three restrictions on read. Building the fixture found three writer defects, §7.1
items 13 to 15, and one layout effect worth knowing: committing a set calls
`TFile::Write`, so the StreamerInfo record lands mid-file, and its length depends
on the standard library. `gen.C` holds it back to the end, which is what lets the
assertions after it hold on Linux; checked by regenerating in the arm64 container
of `AGENTS.md`, where the file is 28 bytes longer and all 87 assertions pass.
None of the 24 RNTuple files of `gen/foreign/` has an attribute set.

**M10 — report upstream.** Thirteen RNTuple errata against a document the ROOT team
owns, plus §7.1's fifteen bug candidates. Lead with §7.1 items 9 and 12:
`fBranchCount` naming another object's counter branch, byte-witnessed in a file
the ROOT team published, and data loss. Also lead with erratum 6, a column type
the document specifies, ROOT does not implement and JSROOT does, so two readers in
one repository disagree about the type set. Deferred to the end by standing
decision, and the natural opening for open item 1.

**Not in the MVP, deliberately**: the twelve narrow `custom`/`extending` classes (§2.4);
`TGeo*` hand-review; `gen/legacy/`; the pre-ROOT-4 object layouts (decision 7);
semantic `case.toml` assertions; `TBranchSTL` entry decoding and `kStreamLoop`
values (§9.11). `WriterInvariants.md` is no longer on this list: it became §8.4
item M15, because there is now a writer to point it at.

### 8.4 Write support, added 2026-09-18

The MVP was a reading specification and it is out. This is the extension. The
reason is not symmetry: every third-party project that *writes* ROOT files has had
to derive the write side from the same source the read side came from, and a
write-side mistake is silent for the writer and permanent in the file. A reader
that gets a field wrong shows a wrong number today; a writer that gets one wrong
produces files that some readers accept and others do not, for years.

Ordered so that every item ends with a file ROOT opens.

**M11 — ✅ done 2026-09-18. The container, and the harness the rest of this
depends on.**
*A 656-byte file this project wrote, which ROOT opens, reads, appends to and
rewrites.*

`06-writing/index.md` and `WritingFiles.md` (453 lines), `tools/rootwrite.py`,
`tools/check_write.py` and `gen/written/objstring/`: 59 byte assertions, all three
gates green, wired into both CI jobs. What the write side needed that the reading
documents did not have:

- **The order of operations**, which is a property of no byte in the file. ROOT
  has two orders and neither is canonical: `TFile::Close` writes the streamer
  infos, then the key lists, then the free list (`root/io/io/src/TFile.cxx:1000`,
  `:1019`, `:1024`), while `TFile::Write` puts the key lists first
  (`:2507-2510`). Both occur in ROOT-written files, and a reader cannot tell them
  apart, because both records are found by absolute offset.
- **`fEND` is not the file's length**; it is the first byte of the last free
  segment, recomputed as `lastfree->GetFirst()` on every header write
  (`root/io/io/src/TFile.cxx:2671-2672`). Keeping the free list as the authority
  keeps the two consistent.
- **The free list's last entry is a sentinel.** ROOT ignores `nfree` and reads until
  an entry has `fLast > fEND` (`:801-808`), so a last entry that does not exceed
  `fEND` makes it parse past the record. It is read only on a writable open
  (`:769-775`), so a read-only test never exercises it. `verify.C` therefore
  copies the file, opens it `UPDATE`, and appends an object. ROOT's allocator then
  takes our free entry's `fFirst`, and if it were wrong the append would overwrite
  live data.
- **§13, what ROOT does not check**: ten container mistakes it reads silently,
  including a key image in the key list that disagrees with the record it points
  at, and `fObjlen` inconsistent with `fNbytes - fKeylen`, which *is* the
  compression flag since there is no other.

The milestone was scoped around one question, now answered by measurement: ROOT
needs no streamer info for a class it has compiled in. A `TObjString` file with
`fSeekInfo = 0` reads correctly and silently, as does a ROOT-written `TH1F` file
with the two header fields zeroed. `tools/coverage_probe.py` cannot read either,
because this project's reader is streamer-info driven, like every third-party
reader. The warning that would report the missing record
(`root/io/io/src/TFile.cxx:928-941`) fires only when the file's `fVersion` differs
from the running ROOT's: the same file at 64004 is silent and at 63000 warns, both
verified. The record is therefore optional for ROOT, mandatory in practice, and
M12 writes it.

**M12 — ✅ done 2026-09-18. The object layer, and a `StreamerInfo` record that is
byte-identical to ROOT's.**
*The strongest check in the project: 370 bytes built from the document alone, equal
to ROOT's own.*

`WritingObjects.md` (354 lines), `written/streamerinfo` (23 assertions, a
compressed record and a compressed `StreamerInfo` record), `tools/test_write.py`
(12 tests), and in `rootwrite.py`: the object map, ZLIB blocks, the streamer-info
serializer and the checksum algorithm.

The byte comparison makes this evidence rather than an account.
`tools/test_write.py` builds the `StreamerInfo` record for `TObjString` from
`WritingObjects.md` §7 and asserts equality with the record in
`data/container/file-minimal.root`: class tags, `TList` option bytes,
`kIsCompiled` in `fBits`, the base checksum in `fMaxIndex[1]`, and a `fCheckSum`
computed from scratch. The last error before it matched is recorded in the
document rather than quietly fixed: **`fElements` is a `TObjArray *` and takes the
pointer slot form**, so a writer that emits the bare framed object is 18 bytes
short.

The main finding of the milestone was about the checksum. `StreamerInfo.md` §11
had the algorithm but not how far it can be applied. Recomputing `fCheckSum` for
every streamer info in every reference file gives 614 of 653 exactly, and each of
the 39 failures has a cause:

- **An enum folds an extra 1**, and an enum is recognisable: `TStreamerInfo::Build`
  stores every enum as an `Int_t` with `fType` 3 to keep the format stable
  (`root/io/io/src/TStreamerInfo.cxx:675-689`), but `fTypeName` keeps the enum's
  own name. ROOT's checksum code uses exactly that test, under a comment asking
  whether it can be done at all (`:3612-3620`), so it is the rule, not a heuristic
  for a third party to invent. With it, `TH1` is reproduced exactly; new §11.1.
- **A version-0 class's info lists no members but its checksum folds them**
  (`:552-554`). `THashList`'s value is reproduced by adding `fTable`/`THashTable*`
  by hand.
- **A member ROOT rewrites for I/O keeps its declared spelling in the checksum.**
  `std::array<Int_t,3>` is recorded as a fixed C array of `int`; `std::unique_ptr<T>`
  as `T*`. `CollectionForms` is reproduced with `array<int,3>`, and `TF1` with
  `unique_ptr<TFormula,default_delete<TFormula> >`, with the default template
  argument written out, which is not guessable from the record.
- **Three `pair` instances where ROOT's own value is wrong**, which is §7.1 item 8
  seen from a second direction: three distinct layouts all with `0x0b5fb752`,
  while the fourth pair in the same file is correct and recomputable.

`TPad` is the only mismatch with no explanation, and it is listed as such in the
test rather than left out of the count. All of this is new §11.2 of
`StreamerInfo.md`, a reading-side improvement that only the writing work would
have found.

The milestone's other question is settled in `WritingFiles.md` §6.1 and the writer
emits the record.

**M13 — ✅ done 2026-09-18. Histograms, byte-identical to ROOT's.**
*Every object-bearing record in the written file equals the one ROOT wrote.*

`WritingHistograms.md` (298 lines), a new ROOT-written fixture
`classes/histogram` (73 assertions) and a written one `written/histogram` (35),
`TH1F`/`TH1D` in `rootwrite.py`, and the fifteen streamer infos the chain needs.

The check is byte equality, three times over. `data/classes/histogram.root` and
`data/written/histogram.root` hold the same two histograms, one written by ROOT
and one from the document alone, and the `TH1F` record (596 bytes), the `TH1D`
record (651) and the `StreamerInfo` record (9628 — fifteen infos, every element,
every checksum, ROOT's own ordering) are identical. The files differ only in the
directory record, the key timestamps, and the offsets that follow.

What that took, and what it exposed:

- **The statistics are not derivable from the bin contents**, which is why the
  document is needed. `fEntries` counts fills, `fTsumwx`/`fTsumwx2` remember the
  true x of each one, and `fTsumw2` is Σ of squared *weights*. A writer starting
  from binned data can only approximate with bin centres. That reproduces ROOT's
  values exactly for the `TH1F` (unit weights, fills at centres) and cannot for
  the `TH1D` (weighted, fills off-centre), so that case supplies them.
- **`-1111` is a sentinel.** `fMaximum` and `fMinimum` mean "compute from the
  data"; 0 gives a histogram ROOT draws with a ceiling of zero.
- **`fFunctions` is streamed in place**, not as a pointer slot, because it is
  declared `//->`. Four zero bytes for "null" makes ROOT read the `TList`'s
  version word out of the next member.
- **The Y axis's `fTitleOffset` is 0 where X and Z have 1.** This comes from
  `gStyle`, not a rule, and is why the three `TAttAxis` blocks in a ROOT-written
  histogram are not identical. It was the last difference before the records
  matched.
- **`fBuffer` is persistent**, a counted pointer with a flag byte, just before
  four transient members that a writer walking the header must skip.
- **Two checksums cannot be computed and must be carried as constants**:
  `THashList` and `TSeqCollection`, both class version 0. This is §11.2 of
  `StreamerInfo.md` as a practical constraint. `TArray`, `TArrayF` and `TArrayD`
  get no info at all in a ROOT-written file, yet their checksums are needed as the
  base of `TH1F`/`TH1D`, so the writer computes them from element lists it never
  emits.
- **Fifteen infos, not the four a histogram seems to need.** `THashList`, `TList`,
  `TSeqCollection`, `TCollection` and `TString` are included because a null
  object pointer forces its class's info to be written, and `TAxis::fLabels` is
  one.

**M14 — ✅ done 2026-09-18. A `TTree`, byte-identical to ROOT's in every
record.**
*The strongest check in the project, and the one with the most to get right.*

`WritingTrees.md` (400 lines), `written/tree` (81 assertions), and in
`rootwrite.py`: leaves, branches, baskets, the tree record and the eighteen
streamer infos the chain needs.

**`data/written/tree.root` reproduces `data/ttree/basket.root` record for
record**: both baskets and the `TTree`, keys included, once the wall-clock
timestamp is masked. That is stricter than the histogram comparison, because a
branch stores its baskets' offsets, so one byte's difference anywhere earlier in
the file would change the tree record. The two names are the same length for that
reason, and `tools/test_write.py` asserts the equality.

The only difference in the whole file is one `StreamerInfo` entry: ROOT appends a
`listOfRules` of two read rules for `TTree` versions ≤ 16 and ≤ 18, which a file
written at version 20 can never trigger.

What a writer needs that no reading document had reason to state:

- **A basket's key version is 1004 whatever the file's size.** `TBasket`'s
  constructor adds 1000 unconditionally (`root/tree/tree/src/TBasket.cxx:71`), so
  a 16 KB file has 8-byte offsets in those keys, and its `fKeylen` covers the
  19-byte basket header, which lives *inside* the key.
- **A basket is never in the directory's key list**, as ROOT's own destructor
  comment states. The key list holds the `TTree` key alone.
- **`fLeafCount` is an object reference, not a name**, and `fLeaves` holds
  references to the same leaf objects `fBranches` holds. The counter branch
  therefore must be written before the counted one, a write-side ordering
  constraint with no reading-side counterpart.
- **A counter leaf's `fMaximum` must cover every count in the file** before the
  tree record can be written, so a writer needs a full pass over the data. If it
  is too small, ROOT clamps the read with a raw `printf`, desynchronising the rest
  of the entry (`root/tree/tree/src/TLeafI.cxx:174-180`).
- **`fNevBufSize` means two things**, the fixed entry stride or the offset
  array's capacity, and the wrong one is read silently at the wrong stride.
- **`fBaskets` is `fWriteBasket + 1` slots of null**, not an empty array, because
  `TObjArray::Streamer` writes `fLast + 1` entries after `TBranch::Streamer` has
  removed every basket already on disk.
- **`fBranches` and `fLeaves` are member objects, not pointers** (`fType` 61), so
  there is no class record: the same 18-byte trap as `fElements` in M12, in the
  other direction.
- **`fMaxVirtualSize` must not be negative** and **`fWeight` must be 1.0**, two
  fields a reading spec would call decorative: the first diverts basket reading
  onto an unbounded cluster path, the second multiplies every `Draw`.
- **`fEntryOffsetLen` is shrunk at flush** to `4 × fNevBuf`, which is why ROOT
  writes 12 where the branch was created with 1000.
- **`ROOT::TIOFeatures` has no `ClassDef`**, so its eleven bytes are a version
  word of 0 and the checksum `0x1aa12f10`, the only foreign class in the classic
  format a writer cannot avoid.
- **`TBasket` gets no streamer info**, although every basket in the file is one.
  It is the clearest proof in the format that ROOT reads a class the file does not
  describe. `TBranchRef` and `TRefTable` *do* get one, because `fBranchRef` is a
  null pointer and a null forces its class's info to be written.

ROOT reads the result through its own machinery: `Scan`, `GetEntry` returning 8,
12 and 16 bytes for the three entries, and `Draw` selecting six values from three
entries, which only works if the counted array's offsets and `fLeafCount`
resolved. `check_invariants.py` also decodes both baskets' entries and checks
their byte spans, as it does for a ROOT-written fixture.

**M15 — ✅ done 2026-09-18. `WriterInvariants.md`, and the front pages
re-measured.**

The 223 `Invariants` entries of 30 documents, re-sorted by the order a file is
produced in (the file, each object, a histogram, a tree), with one column the
reading side never needed: who notices a violation. It has three very unequal
values: `check_invariants.py`, ROOT, or nothing. §6 lists the nine where the
answer is nothing, and is the shortest useful page in the appendix.

M15 also added the class-version tables of the two class-level writing
documents, which brought `check_versions.py` from 25 versions across 7 documents
to 40 across 9. `TH1F` 3, `TH1` 8, `TAxis` 10, `TBranch` 13, `TBasket` 3 and the
rest are now checked against `ClassDef` rather than asserted.

**What write support is still not.** `TH2F` and `TProfile` are outlined and not
specified; a split `TBranchElement`, an update to an existing file, and a
user-defined class with a streamer info of its own are out of scope by decision 3.
The four documents cover what a writer of histograms and flat trees needs, which is
what the extension was asked for.

### 8.5 Distance to "writes the latest versions of the most common types"

The stated scope is a specification a third party can use to implement a library
that reads any ROOT file and writes the latest versions of the most common
types. The reading half is met, as far as the corpora can show. The writing half
is not yet, and the review of 2026-09-18 made every shortfall explicit in
[Writing §4](spec/06-writing/index.md#4-what-is-not-specified) rather than leaving
it implied. Ordered by how much it blocks a third party:

1. ~~**The streamer-info element lists are not in `spec/`.**~~ **Done, 2026-09-18**
   — §8.6.
2. ~~**More than one basket per branch.**~~ **Done, 2026-09-18** — §8.7.
3. ~~**Cluster ranges.**~~ **Done, 2026-09-18** — the same work, §8.7.
4. ~~**`TH2F` and `TProfile`**, outlined in `WritingHistograms.md` §7.~~ **Done,
   2026-09-18** — §8.8.
5. ~~**Subdirectories.**~~ **Done, 2026-09-18** — §8.9.
6. ~~**A `TLeafC` branch.**~~ **Done, 2026-09-18** — §8.10.
7. ~~**`TGraph`.**~~ **Done, 2026-09-18** — §8.11.

All seven are done. The writing half of the stated scope is met as far as this
project can show it: a third party following `spec/06-writing/` can write a file of
histograms, profiles, graphs and flat trees at the current class versions, and nine
worked examples check each procedure against bytes ROOT wrote. What remains is the
standing scope in
[Writing §4](spec/06-writing/index.md#4-what-is-not-specified): earlier class
versions, two writers on one file, split branches, RNTuple, and the element list
of any class beyond the thirty-five published. None of those is a gap in the
prose; each is a limit the layer states.

### 8.6 The element lists, published (2026-09-18)

[`spec/06-writing/ElementLists.md`](spec/06-writing/ElementLists.md): the streamer
info of each of the 27 classes, 157 elements, that a writer of histograms and flat
trees has to describe, with every field of every element (the element subclass and
its version, `fType`, `fSize`, `fTypeName`, the subclass tail, and the declaration
comment), plus the write order of each set, the class versions, and the two
checksums that cannot be recomputed.

**It is generated from the fixtures, not from the writer.** `tools/element_lists.py`
reads the `StreamerInfo` records of `data/classes/histogram.root`,
`data/ttree/basket.root` and `data/classes/tarray-histogram.root`, so the published
tables are evidence about ROOT rather than a transcription of `tools/rootwrite.py`.
The third fixture is what makes `TArray`, `TArrayF` and `TArrayD` publishable at
all: no histogram file describes them, but a `TH2F` inside a `TTree` branch does.
Four checks run in the same pass:

1. every class present in more than one fixture agrees across them, field for
   field — 13 of the 27 are checked twice this way;
2. every field of every element agrees with `tools/rootwrite.py`;
3. every published element list reproduces the `fCheckSum` beside it through
   `StreamerInfo.md` §11, except the two version-0 classes, which must fail and are
   named;
4. `--check` fails in CI if the document drifts.

**Check 2 found four errors in `tools/rootwrite.py`.** They had survived because
all four are in an element's subclass tail (the members after the
`TStreamerElement` base), which is in no checksum and in no byte count, and the
element-by-element comparison in `test_write.py` stopped at the base:

| Class | Field | Was | ROOT |
|---|---|---|---|
| `TRefTable` | `fProcessGUIDs`'s `fCtype` | 365 `kSTLstring` | 61 `kObject` — a `vector<string>`'s value class has a dictionary (`root/core/meta/src/TStreamerElement.cxx:1810-1812`) |
| `TArray` | `fN`'s `fType` | 3 `kInt` | 6 `kCounter` — promoted by whatever *points* at the member, not by its own declaration (`:99`) |
| `TArrayF` | `fArray`'s `fSize` | 8 | 4 — the element type's size, not a pointer's (`root/io/io/src/TStreamerInfo.cxx:645`, `:783`) |
| `TArrayF`, `TArrayD` | `fArray`'s `fCountClass` | the concrete class | `TArray`, which is where `fN` is declared |

Only the first reaches a file. Fixing it made the tree file's `StreamerInfo`
record byte-identical to ROOT's except for the one `listOfRules` entry a file
written at `TTree` version 20 cannot use; that equality did not hold before, and
`tools/test_write.py` now asserts it. The other three are in infos a writer
computes checksums from and never emits, which is why nothing had compared them.

Two facts worth keeping, both from writing §3 of the document:

- **`TStreamerBasicType::Streamer` recomputes `fSize` from `fType` on read**
  (`root/core/meta/src/TStreamerElement.cxx:1242-1269`), so for a basic member the
  value in the file is discarded before anything can consult it. ROOT's own files
  have 0, 8, 16 and 24 for `TNamed::fName` across releases and pointer widths.
- **An info's own `fTitle` is empty** in all 743 streamer infos in `data/`, which
  answers a question `WritingObjects.md` §7.1 leaves open for a writer.

`check_versions.py` went from 40 versions across 9 documents to 48 across 10,
because §9 of the new document is a class-version table and is therefore compared
with `ClassDef` like every other.

### 8.7 Flushing: many baskets and cluster ranges (2026-09-18)

[`WritingTrees.md` §7](spec/06-writing/WritingTrees.md#7-more-than-one-basket-per-branch),
items 2 and 3 of §8.5 in one piece of work, because a tree big enough to flush has
both. Five subsections: what one flush changes, why `fMaxBaskets` is not the number
of baskets, the rewriting of `fBasketSize`, cluster ranges, and
`fFlushedBytes`/`fSavedBytes`/`fAutoSave`.

**The worked example is a second byte-identical tree.** `data/written/cluster.root`
reproduces `data/ttree/clusters.root` (nineteen entries, five baskets, two closed
cluster ranges), and all five basket records plus the whole 860-byte `TTree`
record are byte-identical to ROOT's. This took the three counted arrays past
length 1: five `fBasketBytes`, five `fBasketSeek`, six `fBasketEntry`, the zero
padding to `fMaxBaskets`, and both cluster arrays. It matched on the first run,
the only case in this project where a procedure written from the source needed
no correction from the bytes.

What the work had to establish, none of it derivable from the reading side alone:

| Fact | Why a writer cannot guess it |
|---|---|
| `fMaxBaskets` on disk is `max(fWriteBasket + 1, 10)` (`root/tree/tree/src/TBranch.cxx:3190-3193`) | it is not the in-memory capacity, and the three arrays are that long — a five-basket branch writes ten elements each |
| `fBasketEntry` is one element longer than there are baskets | the extra element is the terminator, rewritten by every flush and left by the last |
| A basket's `fBufferSize` is the branch's `fBasketSize` when it closed | ROOT rewrites `fBasketSize` at the first automatic flush through `OptimizeBaskets`, whose floor is 512, so basket 0 of `clusters.root` says 100 and the rest say 512 |
| `fClusterRangeEnd[i]` is the last entry of the range, and `fClusterSize[i]` the old watermark | `SetAutoFlush` closes the range before assigning the new value (`root/tree/tree/src/TTree.cxx:8451-8458`), and only once something has been flushed |
| `fAutoSave` 3703700 | `4 * ((300000000 / 81) / 4)` — ROOT's own arithmetic at the first flush, from the constructor's default and the bytes then written |
| `fFlushedBytes` is set by an *automatic* flush and not by `Write`'s | so 0 means "no cluster boundary was ever recorded" |

§9 of the document now states two things a reader must tolerate and a writer
should not produce: a non-strictly-increasing `fClusterRangeEnd` (two
`SetAutoFlush` calls with no `Fill` between them) and an `fClusterSize` of 0 (from
fast-merging). The reading side deliberately has no invariant against either, and
saying so on the write side keeps the two halves from appearing to disagree.

Policy stayed out of the writer: `rootwrite.Tree` gained `flush()`,
`set_auto_flush()` and `mark_cluster()`, and the case calls them at the boundaries
ROOT's watermark happened to produce. `fBasketSize` and `fAutoSave` are inputs for
the same reason: reproducing ROOT's arithmetic is not a requirement on a writer,
and matching its bytes is what the case is for.

### 8.8 `TH2` and `TProfile` (2026-09-18)

[`WritingHistograms.md` §7 and §8](spec/06-writing/WritingHistograms.md#7-th2f-and-th2d),
item 4 of §8.5. The writing layer now covers five histogram classes rather than
two, which is the set ROOT users actually write.

**The worked example is a fourth byte-identical pair.** `data/classes/th2-profile.root`
is new (a `TH2F`, a `TH2D` and two `TProfile`s, 71 assertions), and
`data/written/th2-profile.root` reproduces all four of its data records byte for
byte, 817, 887, 708 and 713 bytes, plus its `StreamerInfo` record up to the
nineteenth entry. Like the cluster case it matched on the first run.

What the work had to establish, none of it in the class definitions:

| Fact | Why a writer cannot guess it |
|---|---|
| A `TH2F` is three nested frames, and `TH2`'s four doubles sit between the `TH1` frame closing and the `TArray` base opening | `TH2` has a hand-written `Streamer` that delegates above version 2 (`root/hist/hist/src/TH2.cxx:2823`), so it contributes its own byte count and version word as a base |
| The in-range region of a `TH2` is a rectangle | `Fill` skips all seven sums when either index is a flow bin (`root/hist/hist/src/TH2.cxx:398-403`) but increments `fEntries` first (`:391`), so cells outside it hold data that no statistic saw |
| `fScalefactor` is 1.0 and nothing reads it | six constructors assign it, `Copy` copies it, the legacy streamer branches read it, and there is no getter and no arithmetic anywhere in ROOT |
| `fTsumwxy` has exactly one reader | `TH2::GetCovariance` (`root/hist/hist/src/TH2.cxx:1156`); `Integral`, `GetBinContent` and `GetBinError` read none of the four |
| **A zero `fTsumw` throws all the sums away** | `GetStats` recomputes from the bins when `fTsumw` is 0 (`root/hist/hist/src/TH2.cxx:1230`, and `root/hist/hist/src/TProfile.cxx:958` where the `&& fEntries > 0` half is commented out). It does so silently, so a writer that fills `fEntries` and not `fTsumw` gets the bin-centre approximation with no warning |
| A `TProfile` has four parallel arrays and no bin contents | `fArray` is sum(w*y), `fSumw2` sum(w*y*y), `fBinEntries` sum(w), `fBinSumw2` sum(w²); the content is a division done on demand (`root/hist/hist/src/TProfile.cxx:858`) |
| **A `TProfile`'s `fSumw2` is never empty** | its constructor allocates it unconditionally (`root/hist/hist/src/TProfileHelper.h:139`), unlike a `TH1`'s, and `GetBinError` indexes it with no length test (`:715`). A file with an empty one opens, returns the right entries and the right bin content, and then segfaults. Measured with a file written deliberately for it |
| A wrong `fBinSumw2` length is worse than a wrong value | `GetBinEffectiveEntries` truncates the array to zero in memory and carries on (`root/hist/hist/src/TProfileHelper.h:159-162`) |
| `fYmin == fYmax` means "no Y range" | the filter is guarded by `if (fYmin != fYmax)` (`root/hist/hist/src/TProfile.cxx:682`), and a rejected fill returns before `fEntries++`, the opposite of `TH2` |
| `fErrorMode` is an enum and folds an extra 1 into the checksum | it is a file-scope `EErrorType` (`root/hist/hist/inc/TProfile.h:28`), so its `fTypeName` is unqualified and `looks_like_enum` fires; without it `0x4bedee54` is unreachable |

A profile is the only histogram whose statistics are almost fully derivable,
because the per-cell arrays already hold what a `TH1` throws away: five of the six
sums come out of them exactly, and only `fEntries`, the count of fills, does not.
In the 1-D case, by contrast, only bin centres are available.

§12 of the document records six errata against ROOT's own comments. The largest
is `fBinEntries`, documented as "number of entries per bin" and holding a sum of
weights; the header and `TProfileHelper`'s comment on the same array contradict
each other, and a writer that believes the header produces wrong contents for
every weighted profile.

The histogram invariants are now checked rather than only stated.
`WritingHistograms.md` §10 had claimed seven entries were verified by
`check_write.py`, but nothing in `check_invariants.py` looked at a histogram. A
new `check_histogram` pass covers 10.1 to 10.9 over the `TH1x`, `TH2x`, `TH3x`
and `TProfile` families, confirmed by corrupting twelve fields of
`data/written/th2-profile.root` one at a time: five land on a named invariant and
the rest desynchronise the decode first. The pass also avoided a measurement
error it would otherwise have introduced. Skips from record-level checks used to
feed the `ENTRIES` branch-basket ratio, and 468 histogram records in `pippa.root`
would have dropped the published figure from 100% to 78% while measuring nothing
about entries. `skip()` now takes a unit.

### 8.9 Subdirectories, and a bug the new invariant found (2026-09-18)

[`WritingFiles.md` §5](spec/06-writing/WritingFiles.md#5-a-subdirectory), item 5 of
§8.5. The layer could write a file with one directory; it can now write a tree of
them, and the one-paragraph placeholder at §4.2 is a six-part procedure.

**The worked example is the closest byte comparison in the project.**
`data/written/nested-subdir.root` holds two nested subdirectories and a
`TObjString` at each of three levels: the same content as the reading-side
fixture `data/container/directories.root`, with a file name chosen to be the same
31 characters. The two files are 1854 bytes each with identical record
boundaries, and every byte agrees except each key's `fDatime`, the three UUIDs
and the file's own name. It matched on the first run. Every offset, every
`fNbytesName`, every `fSeekParent` and every `fSeekKeys` in both subdirectory
records is therefore ROOT's own value rather than this project's reading of
`TDirectoryFile.cxx`.

What the work had to establish:

| Fact | Why a writer cannot guess it |
|---|---|
| A subdirectory's record is placed before everything it contains, with `fNbytesKeys` and `fSeekKeys` still 0 | ROOT writes it at creation (`root/io/io/src/TDirectoryFile.cxx:147-164`) and fills those two in later; they are the only fields a single-pass writer cannot compute where it places the record |
| The payload is 60 bytes whether or not the offsets are 64-bit | `TDirectoryFile::Sizeof` never tests the large-file flag (`root/io/io/src/TDirectoryFile.cxx:1725-1735`): in the large layout the 12 trailing bytes *are* the high halves. This is what makes the second write an overwrite |
| **A directory record never moves and is never freed** | `WriteDirHeader` seeks `fSeekDir + fNbytesName` and overwrites in place (`:2177-2180`), and `TKey::Delete` refuses a directory key outright, with ROOT's own comment about it (`root/io/io/src/TKey.cxx:586-594`). So `nfree` stays 1 however many directories a create-only file has |
| A key-list record's key names the directory that owns the list | `WriteKeys` passes `this` as the mother (`root/io/io/src/TDirectoryFile.cxx:2213`), so `fSeekPdir` is that directory's own `fSeekDir`. It is the only structural link back from a key list, since the record is otherwise indistinguishable from the directory record |
| `TDirectoryFile` has two writers of the same 60 bytes with different large-file predicates | `FillBuffer` tests the three stored offsets (`:751-760`), `Streamer` tests the file's `fEND` (`:1827`). `FillBuffer` is the one that produces the record |
| A parent's key list precedes its children's | `Save` does `SaveSelf` then recurses (`:1575-1587`). Nothing reads the order, so it is free, but reproducing it keeps the byte comparison possible |

Gate 3 includes ROOT writing into a directory this project created. The case's
`verify.C` reopens a copy in `UPDATE` mode and writes an object into `alpha`:
`alpha` is still at 401 and `beta` at 610 afterwards, while the two old key lists
and the old free-segment record have become freed spans and `nfree` is 3. That
measures the in-place claim rather than citing it.

Four new writer invariants were added, all four checked, plus one that is not a
property of a file and is refused by the writer instead (a directory left unsaved
while it owns records). One of the four, `Directory` 9.12 on the key-list
record's `fSeekPdir`, is new to the container layer as well; nothing had looked at
that field before.

`TObjString`'s element list is now published, as
[`ElementLists.md` §8](spec/06-writing/ElementLists.md#8-a-file-of-one-object-tobjstring):
32 classes, 176 elements. It was the only class that three written cases already
used and no table described, so those files were not reproducible from `spec/`
alone. Its checksum recomputes from the published table.

The same work found the fourteenth format error in `gen/foreign/`, which §9.8
records: the invariant added that morning failed on a pre-5.34 file, and the
specification was wrong.

### 8.10 A `TLeafC` branch, and a `hadd` bug (2026-09-18)

[`WritingTrees.md` §4.5 and §4.6](spec/06-writing/WritingTrees.md#45-a-tleafc-the-one-leaf-whose-entries-are-not-all-the-same-length),
item 6 of §8.5. A writer can now emit a string branch, the last leaf form a flat
tree needs and the only one whose entries differ in length.

**A third byte-identical tree pair.** `data/written/leafc.root` against the new
`data/ttree/strings.root`: `n/I` and `s/C`, three entries, both basket records and
the whole 1301-byte `TTree` record identical, keys included, and the
`StreamerInfo` record identical except for the `listOfRules` entry. It matched on
the first run, and `TLeafC`'s checksum `0xfbe3b2f3` came out right from the
published element list the first time it was computed.

The three strings are the three forms, and the empty one is in the middle so the
offset array has two equal entries:

| Fact | Why a writer cannot guess it |
|---|---|
| An empty string writes no bytes at all, not even the length byte | `WriteFastArrayString` returns before writing (`root/io/io/src/TBufferFile.cxx:2038`), and nothing but the entry-offset array records that the value was there |
| `fLen` is the longest string plus one, not a multiplicity | `TLeafC::FillBasket` raises it on every fill (`root/tree/tree/src/TLeafC.cxx:82`) and `fMaximum` beside it, so both need a full pass over the data before the tree record is written |
| `fLenType` is 1 while `fMinimum`/`fMaximum` are `Int_t` | the leaf's own values are bytes; its range members are not, so the two numbers a writer reads off "the leaf's type" are different |
| `fEntryOffsetLen` is forced to a hard-coded 1000 | `root/tree/tree/src/TBranch.cxx:424-427` is a literal, not `fTree->GetDefaultEntryOffsetLen()`, so `TTree::SetDefaultEntryOffsetLen` has no effect on a leaflist `/C` branch at all |
| A `TLeafC` must be its branch's only leaf | two independent reasons, §4.6: the empty-string test compares whole-entry offsets, and a `TLeafC` advances the leaflist's running `fOffset` by 1 whatever its strings are |

**The work also turned up a ROOT bug with silent data loss, which `hadd` reaches
by default.** §7.1 item 12: a fast clone raises a `TLeafC`'s `fMaximum` and never
its `fLen`, and `fLen` is what sizes the read buffer. Merging a file of
2-character strings with a file of 10-character ones gives `fLen` 3 and
`fMaximum` 11, and ROOT returns `"01"` for every long string. The bytes are
complete (the count byte in front of each is 10), so the file is right and ROOT's
reader is wrong. `data/ttree/leafc-truncated.root` is the fixture, and
[TLeaf §9.1](spec/04-ttree/TLeaf.md#91-flen-is-the-readers-buffer-size-and-it-can-be-too-small)
states the reader's rule that avoids it: a string's length comes from the counted
string in the entry, never from `fLen`.

Three new leaf invariants were added, all three checked over all 24 `TLeafC`
leaves in the fixtures and both corpora, and each confirmed by corrupting a
field. The third, `TLeaf` 10.11, decodes every entry's counted string and
compares the longest with `fMaximum`. `fLen` does not satisfy this invariant,
and it is the one a reader can size a buffer from. `tools/rootfile.py` now
exposes a `TLeafC`'s `fMinimum` and `fMaximum`, which nothing had read before.

`TLeafC`'s element list is published with the rest
([`ElementLists.md` §7](spec/06-writing/ElementLists.md#7-a-flat-tree-file-the-other-ten)):
33 classes, 179 elements.

### 8.11 `TGraph`, and a null pointer that costs eighteen streamer infos (2026-09-18)

[`WritingGraphs.md`](spec/06-writing/WritingGraphs.md), item 7 of §8.5 and the last
of them. `TGraph` is as common in real files as `TH1` and no writing document had
mentioned it.

**The strongest pair in the layer.** `data/written/graph.root` against the new
`data/classes/graph.root`: the `TGraph` record (198 bytes) and the `TGraphErrors`
record (271) are byte-identical, and so is the entire `StreamerInfo` record, all
12169 bytes of nineteen infos, with no `listOfRules` to subtract. Only the
histogram file had matched a whole info record before. All nineteen checksums
came out right the first time they were computed.

It also needed no matching file-name length. A graph stores no offsets, so the
class map, which is measured from the start of the record, lines up as soon as
the key length does, and that needs only the same class, key name and title.

Three of the six findings came from the byte comparison failing:

| Fact | How it was found |
|---|---|
| `fBits` is `0x400`, `TGraph::kClipFrame`, and a graph has no `kMustCleanup` where a histogram in the same directory does | the first diff, at `+20` |
| `TAttFill` is fixed at (0, 1000) by a mem-initialiser in every constructor, and the line and marker fields come from `gStyle`'s *general* accessors where a `TH1`'s come from its histogram ones, so a graph's line colour is 1 where a histogram's is 602 | the second diff |
| The empty `TList` in `fFunctions` has `fBits` 0, where a histogram's list has `0x14000` | the third diff |
| `fFunctions` is `fType` 64 where `TH1::fFunctions` is 63, so it is a pointer slot with a class record rather than streamed in place — 35 bytes against 21 | the element list |
| `fMinimum` and `fMaximum` use `TH1`'s `-1111` sentinel, are declared in the opposite order to `TH1`'s, and are returned *raw* by `GetMinimum` where `TH1` computes | source, then the fixture |
| `SetMinimum` materialises `fHistogram`, taking the record from 245 bytes to 1213 | `gm` in the fixture, written to show it |

**The main finding of the item: a null pointer writes more streamer infos than a
real one.** A file holding one `TGraph` and nothing else has eighteen infos and
an 11772-byte `StreamerInfo` record, because `fHistogram` is a `TH1F*` and is
null. `TBufferFile::WriteFastArray` force-writes the pointee's info in that case,
with ROOT's own comment *"must write StreamerInfo if pointer is null"*
(`root/io/io/src/TBufferFile.cxx:2456-2463`), and `ForceWriteInfo` recurses over
its elements' classes. A graph file therefore describes `TH1F`, `TH1`, `TAxis`
and `TAttAxis` without containing a histogram, and also describes `TArrayF`,
`TArray` and `TArrayD`, which no histogram file does.

Measured, on two files written by the same ROOT in one run:

| | `TGraph` record | `StreamerInfo` | the `TArray` trio |
|---|---|---|---|
| never drawn, `fHistogram` null | 233 bytes | 11772 | **present** |
| after `Fit("pol1")` | 2387 bytes | 16021 | **absent** |

When the pointer is real the histogram is streamed through its own path, which tags
only classes whose *generated* streamers run, and `TArrayF`'s is hand-written. A
plain `TGraph` file is therefore the cheapest available source for the three
`TArray` element lists, which until now came from a `TH2F` inside a `TTree`
branch. §10 of `ElementLists.md` now reads both and compares them, and its title
no longer claims no file describes them.

Two new invariants were added, both checked. The obvious check on a counted
array, its extent against `fNpoints`, is circular, because a reader derives the
extent from the counter. What is checked is the flag byte and `fNpoints >= 0`;
that there are exactly `fNpoints` values is enforced one layer down by the byte
count, as `StreamerDriven` 10.1. Both were confirmed by corrupting
`data/written/graph.root`.

Element lists: 35 classes, 194 elements, `TGraph` and `TGraphErrors` published
with the rest.

### 8.12 Extending the write side ✅ done 2026-09-21

§8.5 closed the scope the writing layer was first given: the current versions of
the most common types, created from nothing. A sub-plan, `PLAN-writing.md`, ordered
the extension and was deleted when discharged the same day, as `PLAN-ttree.md`
was. The git log holds its four items and `CHANGELOG.md` holds what each changed
for a reader; what follows is the part worth keeping in one place.

All four items landed. They were one feature seen from four angles: a writer that
can reopen its own output.

| | Added | Ends with |
|---|---|---|
| W1 | free-space reuse: the allocator, `WritingFiles.md` §2 | `written/reused-space`, the same 1747 bytes as ROOT's `container/gap-reused` |
| W2 | key order, cycles and deletion, §8.1–§8.2 | `written/cycles-3`, the same 1361 |
| W3 | updating an existing file, §13 | `written/reopen-add` and `written/reopen-reuse`, the same 1657 and 1928 |
| W4 | schema evolution from the writing side, `WritingObjects.md` §8 | `written/two-versions` — one class at two versions, a file no single ROOT session can produce |

Each "the same N bytes" is a whole-file comparison against a ROOT-written fixture,
differing only in the timestamps, the file's own name and the UUIDs. W4 has no twin
because no one session can write one; it is checked by ROOT reading it instead.

**What the four found.** Five of these are corrections or defect reports rather
than additions:

- **the order within a key name is load-bearing.** ROOT never compares cycles:
  `Get`, `GetKey` and `FindKeyAny` return the *first* match. A writer that appends
  a new cycle therefore makes every unqualified lookup return the oldest copy,
  silently. Measured by reversing three key images. `Directory 9.14`;
- **the allocator's `+ 3` is not optional**: a span one, two or three bytes too
  large is skipped and stays unused, because a partial fit must leave room for the
  four-byte marker. `FreeSegments 8.10`;
- **a file can disagree with itself about its own name.** ROOT does not restore
  `fName` on update, so keys written by an update record the path it was *opened*
  as while the directory record has the path it was *created* as;
- **the large file header is 75 bytes and `TFile::WriteHeader` allocates `fBEGIN`
  of them**, and four corpus files have `fBEGIN` of 64, two from ROOT 2.24/00
  and 3.04/02 and two from g4tools. Updating one past 2 GB writes over its own first record. `FileHeader 10.11`;
- **ROOT silently reads nothing for a top-level object of a `TObject`-derived class
  it has no dictionary for.** `TKey::ReadObj` streams it with `tobj->Streamer()`,
  which resolves to `TObject::Streamer`: ten bytes and stop. Witnessed on a file
  ROOT wrote itself: `fA = 77`, `fB = 1.25` read back as 0 and 0, while this
  project's reader recovers both. `SchemaEvolution.md` §7.1;
- **one invariant was written, committed and withdrawn the same day.** W4
  claimed a `TStreamerBase`'s `fBaseVersion` matches the base info beside it; five
  corpus files disproved it on the first run and all five are right. Withdrawing
  it found something more useful: on four files the ROOT team publishes,
  `fBaseCheckSum` is 0 *and* `fBaseVersion` names a version the file has no info
  for, so the fallback `StreamerInfo.md` §9.1 gave a reader as a MUST had nothing
  to land on. §9.2 is the correction. This last item is the most useful in the
  batch.

The last two are for M10. The fourth and fifth are why this project runs its
invariants over files it did not write.

**A fifth item was drafted and cut: writing a split `TBranchElement`.** Its
reasoning is now in [Writing §4](spec/06-writing/index.md#4-what-is-not-specified),
where a reader will find it. Jagged data does not need splitting and this layer
already writes it. A split file is only fully usable by a reader that has the
class, since `InitializeOffsets` rebuilds every member offset from the branch name
plus a dictionary lookup. An unsplit branch is never wrong, only slower to read.
The two format facts that came out of scoping it are placed too: *the shape is
policy, the names are format*, and the recommendation that a top-level branch
name have a trailing dot, which is in
[Splitting §3.1](spec/04-ttree/Splitting.md#31-a-trailing-dot-changes-every-name-below)
because that is where someone choosing a name will be reading.

Decision 3, §2.8, §2.9, §9.4 and Writing §4 are all updated.

### 8.13 The first outside review (2026-09-21)

[Issue #1](https://github.com/ariostas/root-io-spec/issues/1):
[rootfilespec](https://github.com/nsmith-/rootfilespec), a pure-Python ROOT
reader, vendored `spec/` as a submodule, checked its own bootstrap layer against
it, and sent back ten findings and six corroborations.
Every item was re-checked here, against the corpora and against our own
reference files, before it was planned, and that is how three of them turned out
to be defects rather than gaps. The response was ordered by a sub-plan,
`PLAN-review.md`, discharged and deleted on 2026-09-22; this section is what it
left behind.

The findings were not six gaps and four RooFit items but three defects and the
rest. All three were fixed on 2026-09-21, which put release criterion 1 of §8.1,
"no published claim is known to be wrong", back in force. Each turned out to be
larger than the review could see from outside:

- **`tools/rootfile.py` mis-read a version-1001 directory record.** Class version
  and offset width are independent axes. The reader tested `version > 1` for the
  UUID, so for 1001 it invented sixteen bytes from past the end of the record: on
  `uproot-from-geant4.root`, whose record ends at 202, from offset 204. The same
  line was also wrong for a version-2 record, which stores the UUID with no
  `TUUID` version word, so two of the five class versions were mis-read. Fixed,
  with a synthetic record in all six framings. `gen/cern/` turns out to witness
  versions 1, 3 and 4 after all, so every row of `Directory.md` §7's payload
  table is now measured on a ROOT-written file except version 2.
- **`StreamerDriven.md` invariant 5 was false.** `data/classes/histogram.root`
  contradicts it (`TH1F` names `TArrayF` as a `kBase` and no `TArrayF` info
  exists in the file), and it had never been added to `check_invariants.py`, so
  nothing noticed. Its member half was wrong in a way the review did not reach:
  778 object-valued members across the corpora name a class their file does not
  describe. The rule depends on the framing, not the class. Inline codes (`kBase`,
  61, 62, 63, 68) must be described; nullable pointers (64, 69) need not be, since
  the pointer may be null everywhere and a non-null one names its class in the
  bytes. Restated as §6.1 and wired in; the two remaining failures over 227 files
  are g4tools', not ROOT's. Wiring it up corrected a claim published the same
  morning. `WritingObjects.md` §8.2, written for W4, named `TAtt3D` as one of six
  bases legitimately absent from files, resting on those same two g4tools files
  (five of the six were right), and said the closure was not checkable because
  the exemption is a property of ROOT's source. It is checkable, because that
  property is *published*: the checker reads the exempt set out of
  `spec/99-appendix/` rather than out of the submodule.
- **`SchemaEvolution.md` §8.1 generalised from one file.** It said two duplicate
  infos differ in `kIsCompiled`; in two of the three corpus files with the
  duplicate, both entries have `kIsCompiled` and they differ in `kBuildOldUsed`
  (`BIT(17)`). It also conflated two different duplicates: same identity, where
  either entry will do, and two versions of one class, where the object's version
  word chooses. The half that is true is now invariant 9.6 and is checked.

The remaining item expected to yield the most was the fourth: an audit of which
of the 259 published `Invariants` entries are wired into `check_invariants.py` at
all, since the false one had been an unchecked one, and wiring it up caught a
second claim within minutes.

R4 through R6 landed the same day: `Directory.md` §3.1 and §7.1 with invariant 15,
`FileHeader.md` §8.1, and R6's three findings. A `fCheckSum` of 0 is a *failed*
computation rather than a value (`SchemaEvolution.md` §3.1); `TTime`'s missing
info is the writer's, and ROOT was asked to prove it (`StreamerDriven.md` §6.2);
and the file fetched for the first of those caught a reader bug. `TStreamerSTL`
numbered `set` 5 and `multimap` 6 until 5.34/13, `Collections.md` §1 already said
so, and `rootfile.py` did not implement it. That was the third time in this review
that the documents were right and the tooling was not, which is the argument for
R7.

**R7 is done and justified the expectation.** `tools/check_coverage.py` reads
every numbered entry under every `Invariants` heading, matches it against the
labels the tools report, and requires the rest to be accounted for in
`gen/invariants.toml`; it runs in CI. There were 259 entries, 183 with a check
when it first ran, and wiring up part of the remainder found two more false
invariants, both in `ElementTypes.md`. Invariant 4 said `fArrayLength` is positive
for all of `[20, 59]` where 2229 `kOffsetP` elements have 0, and invariant 3
omitted `TStreamerLoop` while allowing a case no file contains. It also caught
`ReadingEntries.md` §8 claiming "all six are checked" when two had no check of
their own. Eight entries gained one; the other 68 are accounted for, 44 of them
write-side entries that `check_write.py` enforces on our own output. Two remain
unchecked and say so.

At that point the tally was five false or incomplete published claims, and every
one was in the population nothing was checking. That lesson is now enforced by a
check rather than remembered. The final count is below; it went up by three, and
how each of those three was found is recorded there.

**A corpus discrepancy came out of R6, and was resolved the same day.**
`build/cern/` held 72 files where `gen/cern/MANIFEST.sha256` listed 26, and the 46
extras (the `TGeoManager` demo sweep) were already evidence in
`StreamerInfo.md` §9.2. They are now a `geometry` tier, every row verified against
a `HEAD` request to root.cern, and the counts that rested on them re-measured: 227
files in both corpora, 219 with a `StreamerInfo` record. The lasting fix is a
check rather than the files: this had already happened once, on 2026-09-18, so
`check_citations.py` now fails on any `.root` the specification names that no
fixture and no manifest accounts for.

**RooFit is in scope from 2026-09-21** (their items 7–10), which revises decision
8. The sub-plan had argued for a middle course; the decision taken instead is the
one they asked for, and the reason is demand. A second independent reader is
willing to extend its own scope only once these classes are specified here rather
than reverse-engineered downstream, the strongest signal this project has had
about what to write next. `Formula.md` and `Matrix.md` are the same kind of work
and are done.

Checked against `inventory.py`'s classification, the four items are less work
than "specify RooFit" suggests:

| Item | The class's `Streamer` | So the work is |
|---|---|---|
| 9 `RooAbsCategory` | in no hand-written list: generated | a framing rule, in `Buffer.md`/`Collections.md` — generated bytes are streamer-info driven |
| 10 `RooVectorDataStore` | `delegating` | `Collections.md` §2: a doubled collection frame, which no document describes |
| 8 `RooRealVar` | `custom` | an `inventory.py` question first: `custom` is already a *stronger* warning than `extending`, so the classification is not wrong in the dangerous direction |
| 7 `RooLinkedList` | `custom`, no layout published | the only real class layout, and the one that needs a fixture |

Two of the four are container-layer facts that happen to have been found in RooFit
files, so they are worth doing first and are useful whatever happens to the rest.

**Done 2026-09-21, and the cost decision 8 named turned out to be nothing**:
conda-forge `root` 6.40.04, the pinned release, reports `--has-roofit` yes, so
`gen/` builds a RooFit fixture with the toolchain already in use.

What the four turned into:

| Item | Outcome |
|---|---|
| 10 `RooVectorDataStore` | **a misreading, not a gap.** The frame whose version word is 1 is `RealVector`'s own class frame, reached through pointer content; `Collections.md` §3.1 and `serialization/pointer-collection` |
| 9 `RooAbsCategory` | **the wrong class.** The extra frame belongs to `RooCategory` below class version 3 and is a whole `RooCategorySharedProperties`; `RooFit.md` §5 |
| 8 `RooRealVar` | **`custom`, not `extending`.** The tail is real and is *inside* the byte count, so the object is still skippable; `RooFit.md` §2.2 |
| 7 `RooLinkedList` | **confirmed, and worse.** No byte count at all, and the info names a member that is not on disk; `RooFit.md` §3 |

Two classes the review did not mention had to be specified with them, because
every `RooRealVar` reaches both: `RooAbsBinning` through its `_binning` member,
and `RooRefArray` as the `_proxyList` of every `RooAbsArg` (`RooFit.md` §4). `spec/03-classes/RooFit.md`, `gen/cases/classes/roofit` and
`tools/test_roofit.py` are the result; 272 of the 274 RooFit records in the two
corpora now decode. The reader can now decode six classes it could not before:
`RooRealVar`, `RooLinkedList`, `RooAbsBinning`, `RooRefArray`, `RooCategory`
below version 3, and `TRefArray` as a *member*, which had no reader here and
blocked 392 objects on its own.

**Building that fixture produced three findings, none of them about RooFit.**
In all three an exception list was one entry short.

- `StreamerInfo.md` §11.2's "a member ROOT rewrote for I/O" named `TF1` and
  `CollectionForms`; `RooAbsReal` is a third, folding
  `unique_ptr<RooNumIntConfig,default_delete<RooNumIntConfig> >` where the info
  records `RooNumIntConfig*`.
- The same section's pair row said three instances in one fixture shared
  `0x0b5fb752`. `classes/roofit`'s `pair<string,vector<int> >` has it too, in a
  different file, from a different program, with a fourth layout. The value is
  therefore a constant ROOT produces rather than one fixture's accident, and a
  global checksum → info table collides on it across unrelated files.
- A synthesised pair's element titles have three forms, not two: libstdc++'s doc
  comments, libc++'s absence of them, and `Emulation` on both members when the
  pair has no dictionary at all (`Collections.md` §8.1). That is a length
  difference, which is why `classes/roofit` joined `serialization/pairs` in
  having no portable digest; see §3.3, and §9.6 for what skipping the container
  loop cost.

**The corroborations all landed.** `uproot-issue-222.root` is `Buffer.md` §4's
field witness: five `TAttBBox2D` bases, each a byte count of 2 over a version
word of 0 with no checksum, on a class that really does declare version 0.
`0x00D7BED2` is in `Collections.md` §8.2 and turned out to be the *opposite*
witness to the one expected. It recomputes exactly, so it is evidence that the
usual pair is sound, which makes the rule necessary rather than optional.
`uproot-issue-407.root` had already landed with R6. On the `ROOT::TIOFeatures`
count, the review finds four files and this project measured three, and both are
right: their fourth is not in `gen/foreign/` and does not merit a place, which
§8.1 now says.

**One correction was found by neither a check nor the review.** `Buffer.md`
§2.3 said the nineteen unframed ROOT 4 records all "begin `00 01 00 03 40 00`".
Re-measuring before quoting the number back to the reviewer showed that only the
14 `TH1D` do; the 5 `TH2D` begin `00 03 00 03 00 03`, three bare version words
with no byte count among them. The count and the shape were right, but the bytes
were one instance quoted as if it were all of them. The fact that replaced it is
more useful than the correction itself: the depth at which framing resumes
follows the class chain, so a reader that matches one prefix has hard-coded a
class rather than implemented the rule.

**The final tally**, from an issue that offered six gaps and four observations:
eight false or incomplete published claims of our own, two reader bugs, six
classes the reader could not decode, and three of the review's own four RooFit
claims corrected. How each of the eight was found:

| Found by | Count | Which |
|---|---|---|
| the review itself | 3 | `Directory.md` §7's history row, `SchemaEvolution.md` §8.1's over-generalisation, `StreamerDriven.md` invariant 5 |
| wiring up an invariant nothing checked | 2 | `ElementTypes.md` invariants 3 and 4 — plus `ReadingEntries.md` §8, which claimed a check it did not have |
| re-measuring a number before quoting it back | 1 | `Buffer.md` §2.3's nineteen records |
| a test failing on a new fixture | 2 | both of `StreamerInfo.md` §11.2's exception lists, each one entry short |

Only the first row is what a reviewer can provide. `tools/check_coverage.py` now
prevents the second; the third and fourth are habits, and the fourth is the
argument for building a fixture even when the corpora already witness the thing.

Two replies on the issue:
[the first](https://github.com/ariostas/root-io-spec/issues/1#issuecomment-5767722107)
covering items 1–6 and the RooFit scope decision, and
[the follow-up](https://github.com/ariostas/root-io-spec/issues/1#issuecomment-5779518620)
covering items 7–10, the two classes the review did not raise, and the three
findings above. The second exists because the first predates the RooFit work and
told them item 10 would come first; in the event none of the bytes it asked for
were needed.

### 8.14 The corpus survey (2026-09-22/23)

Six external resources were surveyed on 2026-09-22, one subagent each, each
instructed to probe with this project's own tools rather than describe what it
found:

| Resource | Licence | What it is |
|---|---|---|
| [root-project/roottest](https://github.com/root-project/roottest) | LGPL-2.1 | ROOT's own regression suite — already inside the pinned submodule |
| [root-project/rntuple-validation](https://github.com/root-project/rntuple-validation) | LGPL-2.1 | ROOT's RNTuple conformance suite; 50 files in a release asset |
| [go-hep/hep `groot/testdata`](https://codeberg.org/go-hep/hep/src/branch/main/groot/testdata) | BSD-3 | groot's corpus; generating ROOT macros committed alongside |
| [KM3NeT/km3net-testdata](https://github.com/KM3NeT/km3net-testdata) | MIT | a neutrino telescope's production output, 38 files |
| [UnROOT.jl `test/samples`](https://github.com/JuliaHEP/UnROOT.jl/tree/main/test/samples) | MIT | UnROOT's corpus, 94 files |
| [opendata.cern.ch](http://opendata.cern.ch/) | CC0 | real LHC production files, multi-GB, range-readable |

The work was ordered by a sub-plan, `PLAN-corpus.md`, whose nineteen items
C1–C19 were all worked by 2026-09-23 and which was then deleted; this section is
what it left behind. The item numbers are still cited across the repository, and
the file itself is in git history, last at commit `d0d1bad`. Its §1 kept one
distinction worth keeping: a claim **confirmed here**, with this project's tools,
against one a survey agent merely **reported**. Five reported claims did not
survive re-measurement as stated: C7 was not a bug, C8's count was 223 rather
than 426, C10's witness was narrower, C15's files added nothing, and C19's
premise was false.

Ten published claims were wrong or under-scoped. How each was found:

| Claim | Found by |
|---|---|
| `Compression.md` §9 had no `RBlob` carve-out (C1) | the survey: a ROOT-written file failing an invariant |
| `TBasket.md` §1's "always the large key layout" is true only from 4.02 (C2) | the survey, then a census of 12 385 roottest basket keys |
| `Buffer.md` §2.3 omitted `TDatime`, and two more classes (C3) | the survey, then reading every persisted hand-written `Streamer` |
| `Record.md` §8.6 needed a 6.34/6.35 RNTuple exception (C4) | the survey |
| `Directory.md` §7 and `FileHeader.md` §8 release boundaries (C11) | re-measuring a witness before quoting it |
| `TLeaf.md` §7/§12's `TLeafF16`/`TLeafD32` v2 was 6.38, not 6.40 (C9) | reading the class at the release tags |
| `FreeSegments.md` §4.2's "never missing" marker (C13) | a checker crash on a newly added file |
| `Collections.md` §4.1's member-wise base (C13) | the same file |
| `Buffer.md` §2.3's "ROOT 4 records open with bare version words" (C18) | checking a new reader rule against the g4tools files it rested on |

Four of the ten came from the survey as reported. The other six came from
following up a lead carefully: re-measuring, reading tags, and adding a file that
then failed. Two passes were also wrong. `uproot-issue475.root`'s `SmartRef`
passed because a wrong reading happened to land on the right length
(`StreamerDriven.md` §7.1). A first version of C19's fix passed every check while
quietly removing 113 branch-baskets from the entry denominator; that was found by
comparing per-file `ENTRIES` lines with the previous commit, not by any failure.

The reader and checker bugs, for the record: a compressed RNTuple anchor read as
raw (C6); a base-class lookup by name that should have been by checksum (C5); a
`Compression` 9.7 check that read the wrong bytes and had never checked anything;
three reader gaps behind C13; and C18 and C19's two decoders, which are now
`StreamerDriven.md` §7.1 and `Collections.md` §11.2.

#### Confirmed negatives — do not re-investigate

Each was measured across a named population, not assumed. They are recorded so
that nobody repeats these searches.

| Question | Answer | Where measured |
|---|---|---|
| A file with more free segments than `volume.root`'s 1539 | **No, and there will not be one.** Production writers open, fill and close once; `nfree` is 1, 2, 9–19 or 74 across six writers | Open Data, six file families |
| A non-zero `pidf` / `fPidOffset` / a surviving `fUniqueID` top byte | None anywhere — 0 of 273 in roottest, 0 in km3net, 0 in go-hep, 0 in every Open Data key list decoded. §9.4 stays open | all six |
| A branch with a non-empty `fFileName` | zero across 5425 km3net branches and every go-hep tree; **unchecked in roottest** (the agent's proxy scan was unsound) | km3net, go-hep |
| `TClonesArray` class version 3 | only version 4 occurs | roottest, go-hep, km3net |
| `ROOT::v5::TFormula` 1–3 / `TF1Data` 1–4 | nowhere, roottest included. v4/v5/v7 do occur in roottest and would advance the row without closing it | all |
| Two streamer infos for one class at the same version, different checksums | none | roottest, km3net, go-hep |
| A `type=readraw` rule | none; the only `ReadRaw` hit in 5602 tracked files is an unrelated ALICE method | roottest |
| A new compression codec | none — zlib, LZMA, LZ4, ZSTD and the legacy codec are all that occur | all six |
| go-hep's `issue-1063.root`, `embedded-tbox.root`, `tefficiency.root` (C15) | nothing new: ROOT-written and clean, but every class, version and checksum is already in a listed file | `gen/foreign/`, `gen/cern/` |
| `TRef` in a production experiment corpus | no. aanet uses index members, not references; the hypothesis behind part of the km3net brief was wrong | km3net |

Two near-misses, named so they are not re-chased. go-hep's `pid.root` looks like
the `fPidOffset` witness but is groot-written: its `TProcessID` key is named
`type-TProcessID` with `fName` `my-pid`, where ROOT writes `ProcessID<n>` for both
(`root/io/io/src/TFile.cxx:2017`). roottest's `foreignVec.root` has the
large-file flag on a 7 KB file with `fUnits` 4, which is exactly the shape
`FileHeader.md` §10.9 predicted and said nothing witnessed. But the write path is
not identified, and `TFile::WriteHeader` sets `fUnits = 8` whenever it adds the
flag. It is a lead until that is traced, and it is the only candidate the survey
found for the large layout at committable size.

#### External verification banked, no action needed

Worth citing, not acting on. Three independent reimplementations agree with this
specification on points it derived from ROOT's source alone:

- **groot's `rvers/versions_gen.go`**, an independently generated table of 119
  class versions pinned to ROOT 6.40/00, cross-checked mechanically against every
  `ClassDef*` in the pinned headers: 118/118 agree, 0 disagreements.
- **UnROOT's `test/issues.jl:92`** comment describes `TBranch` v8's layout member
  for member as `TBranch.md` §13.1 does (`fEntryNumber` as Int32, `fBasketEntry`
  as Int32, `fEntries`/`fTotBytes`/`fZipBytes` as Float64), arrived at
  independently, from bytes.
- **groot falls into `Collections.md` §12's trap**: it defines
  `BypassStreamer = 1<<12` with no class-version branch, and then cannot read the
  bypass file at all (its test is commented out, *"FIXME: needs member-wise
  streaming"*). §12 says a reader MUST branch on the class version before testing
  the bit; this is a working implementation that did not.
- **ERRATA 6** (`0x17 SplitReal16` does not exist) is confirmed in the ROOT team's
  own words: `types/fundamental/real/write.C` has `// NB there is no kSplitReal16`,
  and a suite whose stated goal is covering every part of the format produces every
  column code except `0x17`.
- **ERRATA 8** (Type Version is a signed version in an unsigned field) is
  strengthened: rntuple-validation stamps `0xFFFFFFFF` for classes with a compiled
  `rootcling` dictionary, where this project's witness was interpreted classes only.
  That rules out an interpreter artifact.

Upstream issues open at rntuple-validation that this project already covers:
#21 (streamed types), #22 (anchor tests), #23 (checksum tests) — the last two are
exactly what ERRATA 1/2/3/5 and `gen/cases/rntuple/anchor` cover.

#### Still open from the survey

1. ~~**The licence question.**~~ Decided 2026-09-23: **no file of theirs is
   ever committed**, and no third-party corpus file at all — decision 10.
2. **When to cut the first CalVer release.** The survey's corrections landed
   under `## Unreleased`; cutting now makes them part of the first release.

### 8.15 "ROOT 4" was g4tools (2026-09-23)

Six claims attributed behaviour to ROOT 4 on the evidence of two files,
`uproot-from-geant4.root` and `uproot-issue-250.root`. Their headers say
`fVersion` 40000, but g4tools wrote them, with keys dated 2018-2020, which
`Buffer.md` §2.3 and `gen/foreign/IGNORE.toml` already said. No ROOT-written file
in `root/roottest/` or `gen/cern/` shows any of the six:

| Claim | ROOT-written files older than ROOT 5 |
|---|---|
| an STL element stores 300 (`StreamerInfo.md` §10.1) | 134 elements in twelve files, 3.04/02 to 4.04/02, all 500. The write path forces 500 from tag `v4-00-01` |
| `nfree` is 0 (`FileHeader.md` §5.4) | 55 files, 2.23/12 to 4.04/02, all equal to the entry count |
| a `TArray` counter is `fType` 3 (`ElementTypes.md` §2.1) | 417 counters, all 6 or 13 |
| a `TSeqCollection` info lists `fSorted` (`ForwardingStreamers.md` §1.2) | 50 files, all list the base alone |
| `fEntryOffsetLen` 1000 on a fixed-width branch (`TLeaf.md` 10.6) | 867 branches in fifteen files, all 0 |
| `fBaskets` holds `fMaxBaskets` slots at `TBranch` version 8 (`TBranch.md` §13.2) | none; 1 303 version-8 branches in nine files hold `fWriteBasket + 1` |

The two release exemptions in `check_invariants.py` (`root_version < 5` for the
STL codes and for `nfree`) became per-file entries in `gen/foreign/IGNORE.toml`.

Measuring the version-8 branches found one more error, the other way round:
`TBranch` 11.1 required `fMaxBaskets == max(fWriteBasket + 1, 10)` from class
version 8, on the strength of the same g4tools file. ROOT wrote a flat 1000 at
version 8 as at 7; the recomputation arrived in root commit `aa25e85cb34`
(2004-01-07), after version 9. The check was never run on a ROOT-written
version-8 file, because none is in either corpus; all nine are in
`root/roottest/`.

Also corrected on the way: `TTree.md` said ROOT 4.00/00 wrote `TTree` version 11.
It wrote 10.

### 8.16 A consistency review (2026-09-23)

Rewriting every document for plain language (commit `a02c012`) meant reading
all of it closely, and the agents doing it listed about 130 statements that
disagreed with a neighbouring statement, a table, a fixture or the source. Each
was then checked against the submodule and the bytes. Most were real, and all of
those are fixed. They fall into four kinds:

- **Cross-references to the wrong section**, several dozen, many wrong since the
  file was created: a section renumbered and the "§n" pointing at it not.
- **Counts that disagree with the list beside them**: "seven records" over an
  eight-row table, "thirty-one classes" for thirty-five, "six RooFit classes"
  for five.
- **Claims that went stale when something else landed**: the `listOfRules` entry
  the writer now emits, fixtures that now exist, corpus figures from a smaller
  corpus, a module docstring from before `rootfile.py` decoded objects.
- **Claims that were wrong**, which are what the review was for. Among them:
  `TClonesArray`'s `nobjects` described backwards; count branches said to have
  no leaf; a displacement array said to be impossible in current ROOT when a
  fixture of current ROOT has one; `fType` 365 said to occur on disk; the
  `TStreamerInfo` version-9 boundary one release early; §8.15 in full.

Two tool defects surfaced too. `element_lists.py` never rendered two of its
blocks, so `ElementLists.md` §8 and §9 were published empty while `--check`
passed; blocks are now built from the group list, and a group without a block
fails. And four test classes in `test_streamer_driven.py` sat after the
`__main__` guard.

The lesson for the tooling: nothing checks a "§n" reference against the heading
it names, or a spelled-out count against the list it introduces, and those were
the largest group.

**The leads, resolved.** Running `check_invariants.py` on the pre-ROOT-5 files of
`root/roottest/` for §8.15 gave failures on eight more labels, and `lz4` exposed
one in the foreign corpus. Each was diagnosed against the source at the old
release tags. None is a fault in a file, and no `IGNORE.toml` entry was added:

- `TTree` 11.2 (12 files): `AutoSave` stored `fTotBytes` in `fSavedBytes` until
  5.27/02 (`TTree.md` §6.3). The bound is now scoped by the header's release.
- `TBranch` 11.4 and 11.9 (`digi.root`, six `tree/friend/Event*` files,
  `AthenaCrossSection.root`): `TBranchElement` left its basket arrays unzeroed
  before 3.10/02, and for a top-level collection before 5.21/02 (`TBranch.md`
  §13.4). The reader also looked at `fBasketSeek` before the `fBaskets` slot,
  the reverse of ROOT's order.
- `TBranch` invariant 9: the `+2` slots are not one ROOT 5 file but 344 branch
  records in 23 files from 3.03/06 to 5.16/00, the second "leafcount" basket
  that `TBranchElement` gave every count branch before 5.18/00 (`TBranch.md`
  §5). The "53" first written here was not reproducible.
- `TBranch` 11.10 and `Splitting` 8.2 (`cmsursula`, `mcpool`): empty base classes
  got a leafless branch that holds data before 6.02/00 and 5.34/20 (`TBranch.md`
  §9.2). The checker now decodes those entries rather than skipping them.
- `TBranchElement` 10.10 (`mksm`, `RefTest`, `digi`): a branch samples the
  in-memory code, 71, 91 or 320 for STL pointers and arrays, which current ROOT
  still writes, and 11 for `Bool_t` before 4.03/02 (`TBranchElement.md` §5.2).
- `ReadingEntries` 8.5 on `mksm`: the reader took `kBits` as 4 bytes, ignoring
  the `pidf` that `kIsReferenced` adds. `ElementTypes.md` §2.3 was already right.
- `TLeaf` 10.7 (`short0.root` and its byte-identical copy `short1.root`): the
  reader found a same-branch counter by `fIsRange`, which a pre-5.28 file need
  not set; it now follows `fLeafCount` (`TLeaf.md` §5.2, §6).
- `ReadingEntries` 8.5 on `uproot-issue213.root` (ROOT 6.14/00, readable only
  with `lz4`): `TBits::fNbytes` is a `UInt_t` counter, which ROOT never promotes
  to `kCounter`, and the reader kept only code 6 (`StreamerDriven.md` §3.2).

Two new fixtures cover what current ROOT still writes: `ttree/split-tbits` and
`ttree/split-stl-pointer`. The quoted entry figures had been measured without
`lz4`, which drops eight files' 2158 branch-baskets from both sides of the ratio;
they are now measured with it: 48295 of 48399, 0 failures.

Two checker defects surfaced as well. Every basket of a leafless branch was
counted twice in the `ENTRIES` denominator (the fixtures read 109 of 115, not 109
of 113). And `Checker.check_branch` returns early for a leafless branch, so
`TBranch` 11.5 to 11.7 are never checked on one, `TBranchSTL` included; that
one is fixed in the second round below.

**The second round (2026-09-24).** A sweep of all 272 roottest files, one process
each, gave 590 failures in 27 files. Six agents diagnosed them. None of the files
is at fault except the three noted below, and nothing was added to
`gen/foreign/IGNORE.toml`, which covers only the foreign corpus.

- *Counters the reader never found.* A member-wise `TClonesArray` stores its
  counter as a column, one count per object (`Event1-3.root`, `Event_2.root`;
  `Collections.md` §4.1). A split `kStreamLoop` branch before 5.27/06 has no
  `fBranchCount`, so its counter is found by name (`memleak.root`,
  `varyingArray_51508.root`; `ReadingEntries.md` §4). `fType` 521,
  `kStreamLoop + kOffsetL`, is a real code that 6.40.04 still writes, and before
  5.16/00 a loop of pointers held bare objects, which a byte-span check cannot
  tell from slots (`ElementTypes.md` §8.2, §8.3).
- *Empty collection entries.* Before 5.32/00 an empty entry of a split
  collection's member was 0 bytes, not a 6-byte header (`small_aod.pool.root`,
  the `S_1_*KGrec.root` files; `ReadingEntries.md` §3.2). A collection of an enum
  is read as the type `fCtype` names, `Int_t` when it is 0, and `fCtype` holds the
  underlying type only from 6.36/00 (`Collections.md` §7.1).
- *Basket slots.* `dat_00x.root` holds a basket read back from its record and
  streamed again, identical to the record (`TBranch.md` §5.1). `skim.root`'s one
  slot is `CloneTree`'s `Reset`: 55 branches carry an `fEntryOffsetLen` of 2000
  that a 10-entry tree cannot produce. An empty-base branch could have been
  flushed from 5.20/00 to 5.34/19 and 6.00 to 6.01, so `TBranchElement`
  invariant 6 now exempts it; no file has one.
- *Tree structure.* A split node of a class with no elements (`lhcb.root`), split
  parents after fast cloning (`bigFile.root`, `lhcb.root`, the Coulomb file), a
  tree written with no file behind it (`v5formula_clones.root`), and folder
  branches renamed after construction (`ship_ROOT_9674.root`); `Splitting.md` §1.1
  and §3.3, `TBranch.md` §5 and §7.
- *Serialization.* Before 6.00/00 an element's `fTypeName` is spelled as declared,
  not normalised (`StreamerInfo.md` §7.3). Before 5.24/00 a multimap was stored
  as 4 and a multiset as 5 (`Collections.md` §1). A large-file header can sit on
  a small file (`foreignVec.root`; `FileHeader.md` invariant 9). A copied
  `TTreeIndex` is not trimmed, so a reader must bounds-check it
  (`Auxiliary.md` §2.2).
- *The checker checked less than it reported.* `TBranch` 11.5 to 11.7 now run on
  leafless branches, and `ReadingEntries` 8.1, 8.3 and 8.4 on embedded baskets
  (on `mksm.root` they read 0 entries before and 1410 count entries now). The
  `ENTRIES` ratio counts every branch-basket once, failed or skipped included,
  which moves the corpus figure from 48295 of 48399 to 48278 of 48501, 99.5%.

Roottest now gives 32 failures in 4 files. Three are the files' fault:
`checksum_v5.root` and `checksum_v53418.root` record a class-scoped typedef
nothing resolves, and `output_Coulomb_LER_study_10.root` records a class name no
class has. ROOT 6.40.04, without a dictionary, fails on all three.

**Parked, not pursued.** What is left looks like writer bugs or corners too
obscure to matter to a reader. Each is recorded so that it is not rediscovered,
and none is being worked on; pick one up only if a real file or reader needs it.

- `tlorentzvec.root` (5.27/01): count branches titled `_` whose members say
  `[muon4mom_]`. No ROOT constructor produces it and the writer is unknown, so
  `Splitting` 8.4 was not widened; the file fails it 28 times.
- `output_Coulomb_LER_study_10.root`: a `TGlobal` info whose base `TDictionary`
  has no info (`StreamerDriven` 10.5). Nothing in the file uses `TGlobal`, and
  6.40.04 does not reproduce the omission.
- How `foreignVec.root`'s flagged header with `fUnits` 4 was written.
- A possible ROOT bug: for a file of version 51508 or below, the write action for
  `kStreamLoop` calls a read function
  (`root/io/io/src/TStreamerInfoActions.cxx:1699-1708`). Untested.
- Whether any split parent was fast-cloned and then filled entry by entry, which
  would leave `0 < fEntryNumber < fEntries`.

**Side findings followed up.**

- *Pointers to collections.* The reader refused every `vector<T>*` member
  (`fSTLtype` 41) as a pointer it could not follow. ROOT writes no pointer tag:
  the bytes are the collection's, and a null pointer is an empty one
  (`Collections.md` §11.3). A fixed array of collections carries the value
  class's version once, not once per element (§11.1); reading it per element
  was the `std::string[2]` failure in `stringarray.old.root` and the misleading
  checksum skip on `fArr[2]`. Fixtures now reach 119 of 123 branch-baskets, up
  from 116, and three roottest files gained decoded baskets; the corpora have no
  such member and are unchanged.
- *Compression markers.* 34 `RBlob`s in `gen/foreign/` hold a chain that stops at
  something other than a block magic. All are multi-page blobs
  (`Compression.md` §9.1): the bytes after the first chain are a page checksum or
  a raw page, and 4 open with a raw page, which is what a first-block scan saw.
  Every one splits into sealed pages whose XXH3 checksums match. No other record
  in any corpus has an unknown magic. The checker reported them only as one
  `NOT CHECKED` line with no count; it now counts them as `SKIPPED` RBlobs, and it
  no longer applies `Compression` 9.7 to an `RBlob`, where a single page that
  shrank by 8 bytes or less would have been a false failure.
- *`uproot-issue261.root` was misdiagnosed.* There is no 70-byte hole: its
  key-list record has `fNbytes` 58 against `fNbytesKeys` 106, and a walk that
  trusts it lands inside the key list (`Record.md` §1).
- *Codecs in CI.* Without `lz4` and `zstandard`, CI's Python 3.12 never
  decompressed the LZ4 and zstd fixtures. Both jobs now install
  `requirements-codecs.txt`.
- *`ElementLists` 13.3* said a counter is 6. That holds for an `Int_t`, as every
  counter in the published lists is; a `UInt_t` counter keeps 13.
  `WriterInvariants.md` cited it, and two neighbours, by stale numbers.

## 9. Known gaps

Every gap the written documents record. None is a hole in the prose: in every
case the behaviour is specified and cited against the submodule, and what is
missing is a fixture demonstrating it, so the claim is verified once rather than
twice.

**⏸ Everything still open in this section is set aside (2026-09-24):** the
legacy layouts no available file has (§9.1), the dictionary cases not yet
written (§9.3), the cases that need two sessions or two files (§9.4), semantic
assertions (§9.6), and the decoder residue and small questions of §9.11. Each is
narrow. The one open item outside it is reporting upstream (§8.3, M10).

### 9.1 Legacy layouts

Reframed by §9.10: most of these are not blocked on `gen/legacy/` after all.
"Available" means a file in a corpus has it; `gen/cern/` files are evidence,
`gen/foreign/` files are a lead until the writer is settled (§3.4).

| Gap | Document | Available in |
|---|---|---|
| Directory record versions 1, 3, 4 | `Directory.md` | ✅ read; no fixture, and version 2 occurs nowhere (M4), nor in `root/roottest/`'s 273 files, whose smallest witnesses of 1, 3 and 4 (9 227, 1 199 and 1 225 bytes) are now listed in `gen/cern/README.md`. The 3.03/02 one refuted §7's release boundaries, now read from tags (`PLAN-corpus.md` C11) |
| `TBranch` class versions 6–9 | `TBranch.md` §13.1 | ✅ closed by M6: specified, read, and 116 legacy branches decoded in `mlpHiggs.root` (7), `uproot-from-geant4.root` (8, g4tools) and `stock.root` (9); ROOT-written version 8 is in nine `root/roottest/` files |
| `TStreamerElement` at base version 2 | `StreamerInfo.md` | ✅ 979 elements, §9.10 — M6 |
| Collection layouts below `TStreamerInfo` version 8 | `Collections.md` | ✅ info versions 2, 4, 5, 6 present — M6 |
| The version-3 `TStreamerElement` form with `fXmin`/`fXmax`/`fFactor` | `StreamerInfo.md` | ✅ `root/roottest/root/io/evolution/skim.root`, ROOT 4.03/05: 223 elements, 24 bytes each, all of them available. **No release wrote this version**; it lived three days on the 4.03/05 trunk (C8) |
| A buffer written with no byte counts | `Buffer.md` | ◐, the rest ⏸: checked, and "no byte counts" was never all or nothing: `pippa.root` (2.24/00) and roottest's `MC_uds_reco-1.root` (2.23/12) byte-count their outer objects and write their `TNamed`/`TObject`/`TAtt*` bases as bare version words. §6.4's sequential map needs a class tag with no byte count before it, and no available file has one — the 2.23/12 file's 11 all do (C10) |
| A file old enough to take the `BuildEmulated` path | `SchemaEvolution.md` | ✅ `pippa.root`, ROOT 2.24/00, zero streamer infos — out of scope for objects by decision 7 |
| `TClonesArray` class version 3, where `kBypassStreamer` is `BIT(14)` | `Collections.md` | ⏸ only version 4 occurs |
| `ROOT::v5::TFormula` 1–3 and `ROOT::v5::TF1Data` 1–4 | `Formula.md` §4 | ◐, the rest ⏸: v8/v7 in `uproot-issue-181.root` (ROOT 5.34/36); versions 1–4 in neither |
| A leaf class at a legacy version | `TLeaf.md` | ◐, the rest ⏸: `TLeaf` v1 in roottest's `MC_uds_reco-1.root`, byte-verified: version 2's field order ends on its byte count. `TLeafF16`/`TLeafD32` v1 in go-hep's `leaves.root` and in `uproot-double32-float16.root`, which had been in `gen/foreign/` all along and which the census missed by looking at `TLeaf` and `TLeafObject` only. `TLeafObject` 1–3 in no available file (C9) |

### 9.2 Needs a file over 2 GB

Discharged by range requests rather than by a fixture: `gen/cern/LARGE.toml`
records eleven files from 1.3 GB to 15.9 GB and `fetch_cern.py --headers` checks
every recorded field on each run, downloading nothing.

| Confirmed | Evidence |
|---|---|
| The `+1000000` `fVersion` flag and `fUnits` 8 | six files, ROOT 5.19/03 – 6.23/01 |
| Offsets past 4 GB, where even an unsigned 32-bit reader fails | `lhcb2.root`, `fEND` 4 947 894 760 |
| The large `TFree` form interleaved with the small one in one record | `volume.root`: 51 entries, 32 large |
| `nfree` agrees with the parsed list; the last entry always passes `fEND` | all eight, counts 1 to 1539 |
| The boundary from below: over 1 GB and *not* large format | a CMS file at 1.997 GB with `units` 4 |
| A free record whose key class is a `TFile` subclass | the same file: `TStorageFactoryFile` |
| A wide key at a small offset, which disproved the old rule | `volume.root`: `fVersion` 1004 at 105 159 358 (M5, §1.1 of the page) — and, it turned out, every key of every 6.40 fixture: `rntuple/compressed` asserts one at 385 |
| An 8-byte `fSeekPdir` whose top 16 bits are `fPidOffset` and mask away cleanly | both large-format free records read; invariant 6 |
| The uninitialised slack past a key list, past the threshold | `volume.root`: `00 04 00 62 00 04 00 62` after the one image |
| `fLast` above 2000000000 | 32 entries of `volume.root`; the wide form *is* that condition |
| Offsets past 8 GB | `Run2012C_TauPlusX.root`, 15.9 GB, from CERN Open Data by `url` (C14) |
| One writer on both sides of the boundary | CMS's `TStorageFactoryFile`: all narrow at 1.997 GB under 5.22/00, all wide at 3.27 GB under 6.30/03 (C14) |

Still not asserted by a committed fixture, and never will be: 2 GB cannot be
committed. `spec/01-container/LargeFiles.md` is the write-up (M5) and
`tools/fetch_cern.py --headers` is its check.

### 9.3 Needs a compiled dictionary — ✅ unblocked, the rest ⏸

`gen/common/aclic.C` compiles a case's optional `classes.h` into a dictionary
before the macro loads, so a generator can use a class with a real `ClassDef`.
Remaining: a member-wise collection whose value class has a `ClassDef`
(mechanism exists, case not written) and a `type=readraw` rule (same).

### 9.4 Needs two ROOT sessions or two files ⏸

| Gap | Document |
|---|---|
| A non-zero `pidf`, a non-zero `fPidOffset`, and a `fUniqueID` whose top byte survives to disk | `References.md` |
| Two streamer infos for one class distinguished by checksum at the same version | `SchemaEvolution.md` |
| A negative in-memory class version reaching disk as 1 | `SchemaEvolution.md` |
| A branch with a non-empty `fFileName`, naming the file its baskets went to | `TBranch.md` §14 |

`fPidOffset` arises when a key is copied between files, so one `TTreeCloner` or
`TFile::Cp` case would produce several of these at once.

**Two infos for one class at *different* versions is closed** (2026-09-21):
`written/two-versions` is that file, written by this project, and W4 measured what
ROOT does with both cases. The same-version collision stays here, and is worse
than a gap in coverage: ROOT keeps the file's info and silently truncates the
object it writes ([Writing an object §8.5](spec/06-writing/WritingObjects.md)), so
a fixture for it would be a fixture of data loss.

### 9.5 Reachable now, just not written — ✅ closed 2026-09-16

Every row done, in seven cases. Eight of the twenty-odd items turned out to be
covered already or not to exist: `kAnyPnoVT` (70) has no producer, a `TH2F` does
not produce a concrete `TArray` info (a `TH2F` in a branch does), and `kBits`,
`TLeafObject`, `TLeafElement`, split branches, pointer collections and a non-zero
`fIOBits` were all already covered. Two findings came out of it: the version word
in a 500/501/85/86/87 frame is not the constant 10 but `TStreamerInfo`'s class
version in the writing ROOT (9 in practice, 10 only from 6.36.00), and a
`kStreamLoop` of `TString` is bare counted strings.

### 9.6 Structural

| Gap | State |
|---|---|
| No checker decompresses | ✅ zlib, lzma and the legacy `CS` codec from the standard library; zstd on Python 3.14; LZ4 needs the `lz4` package, and a record whose codec is missing is reported as `NOT CHECKED` rather than passed |
| `rootfile.py` has no `TTree` support | ✅ tree, branches, leaves, baskets, entry spans, and the split decoder |
| Semantic (`path`/`value`) assertions were dropped in favour of byte offsets | ⏸ worth adding as a complement; set aside |
| Four fixtures were not digest-portable between macOS and Linux | ✅ three fixed by masks, one exempted with a reason; the causes are in §3.3 |
| `classes/roofit` was pushed without the container loop of §3.3 and CI caught it | ✅ 2026-09-21. `generate.py --check` cannot see a cross-platform drift, because it does not regenerate; only the ROOT-having job can, so a green local suite is not evidence about a **new** case |
| Twelve upstream bug candidates banked, not reported | ☐ §7.1, M10 |

### 9.7 What the coverage probe measures

`coverage_probe.py` applies the specification to a file it was not designed
around and ranks what blocked each record. It identified `TArray*` and `TBasket`
as the highest-value documents to write, and surfaced the two biggest findings in
the corpora: an embedded `TBasket` inside a `TTree` record (20 records, 1065
skipped members) and a `std::string` written as a whole object with no frame at
all (114 records).

It checks that a record's bytes are *accounted for*, not that the values are
right. `check_invariants.py` and `rootfile.entry_spans` close that gap, and their
coverage is the `ENTRIES` line.

### 9.8 Standing result over `gen/foreign/`

180 files, **0 failures**, as of 2026-09-23. The probe: 32200 decoded, 785
container, 6 partial, 178 blocked, 1 not walkable, plus 132 records whose LZ4
codec is unavailable locally. Entries, with `lz4` installed: 46599 of 46703
branch-baskets, 99.8% (44441 of 44545 without it, §8.16).

Re-measured 2026-09-22 for `PLAN-corpus.md` C13, which added the 23-file RNTuple
tier. The change comes from those files alone: the 157 files before it give 26410
of 26477 and 0 failures both before and after the three reader changes C13 made.
All 155 new blocked records are RNTuple's own: `RBlob`s, which have no streamer
info by design, and anchors, which `read_rntuple` reads instead and which every
new file's anchor passes. Of the 1010 new skips, 975 are one ATLAS file's `This`
element (C19) and 35 are hand-written streamers.

Re-measured 2026-09-23 after C18 and C19: entries 44441 of 44545, 99.8%, up from
43468 (97.6%), and the probe unchanged. The whole change is two files. The ATLAS
file's 975 now decode (`Collections.md` §11.2), and `uproot-issue475.root`'s two
`nEXO::SmartRef` baskets, which had passed by a coincidence of lengths, are
skipped by name (`StreamerDriven.md` §7.1).

Earlier that day, for C9: go-hep's `leaves.root`, the manifest's first file
from outside scikit-hep-testdata, gave +49 decoded, +3 container and +47
branch-baskets, which is that file's whole contribution; nothing else moved.

Earlier the same day, two changes, measured separately. `5d6a95b`'s RooFit
readers decoded two records here as well as in `gen/cern/` (+2 decoded, −1
partial, −1 blocked; the tools as they were before that commit reproduce the old
figures exactly), which nobody had re-measured on this side. `PLAN-corpus.md` C4
added a first RNTuple file, the only witness to `Record.md` §3.6's self-parented
`RBlob` keys. Its nine records are 3 container, 1 decoded and 5 blocked: three
`RBlob`s with no streamer info, one holding several sealed pages
(`Compression.md` §9.1), and the anchor's checksum. Adding it also fixed
`coverage_probe.py`, which had written the whole file off as not walkable because
one record could not be decompressed.

Previously re-measured 2026-09-21 after R6 added `uproot-issue283.root` and fixed
the `set`/`multimap` `fSTLtype` repair in `rootfile.py`: the added file accounts
for the extra decoded records, and the repair for five that were partial or
blocked before it. The triage that got there turned 10 047 failures into 0 and
found eleven specification errors, each one published, wrong and reader-facing
(M6 added a twelfth from here, `TLeaf` 10.6 on `uproot-issue-250.root`):

- a basket with no offset array is not fixed-length when its flag is 80;
- the last offset may equal `fLast` exactly, on an empty last entry;
- `fMaxIndex[1]` is the base checksum or 0, on every file ROOT 5 wrote;
- an STL element's `fType` is 500 on ROOT 5 and later but 300 on ROOT 4
  (itself wrong: the 300s are g4tools', §8.15);
- a counter may sit in the base class its `fCountClass` names;
- a counter's `fType` is any integer basic type, not only 6;
- a base that is an STL container is a `TStreamerSTL` and may precede a base;
- no two streamer infos for one class need differ in version and checksum;
- a `TLeaf`'s `fLen` may be −1, a documented parse failure;
- `fIsRange` may be set on a `TLeafElement`;
- `nfree` in the header is advisory and ROOT never uses it.

A thirteenth was found in the same corpus without a new run: five
`TMatrixTSym<double>` records in `uproot-issue-359.root` had been reported as
"consumed 48 of 3528" and filed as a class the specification had not written up,
when they were the symptom of `HandWrittenStreamers.md`'s `delegating` claim
being wrong (§8 item M1). The lesson is about reading the output: a `NOT CHECKED`
line naming a class calls for a diagnosis, and this one had been accepted without
one.

**A fourteenth, 2026-09-18, the first one a new invariant found.** `Directory`
9.11, added that morning, compares each key image against the key of the record
it points at. It failed twice on `uproot-issue64.root` (ROOT 5.28/00), whose key
list spells two of its five subdirectories `TDirectoryFile` where their records
spell them `TDirectory`. The file is right and two published claims were wrong:
that an image is a byte copy of the first `fKeylen` bytes of its record, and that
a reader can size an entry from its `fKeylen`. ROOT before commit `713f56ea03f`
(2012-01-26, first released in 5.34/00) substituted the short spelling at key
*creation* rather than at the write, and `TKey::ReadKeyBuffer` undoes the
substitution on the way in. Any directory key that reached a key list after being
read back from disk was therefore written four bytes longer than the `fKeylen` it
still reported. ROOT never notices, because it advances by the strings it parses.
`Directory.md` §6.5 now specifies it, invariant 9.13 checks it, and 9.6 is
computed from the parsed lengths rather than from `fKeylen`, as it always should
have been; that is why the two failures had slipped past the 8-byte slack
allowance instead of being caught. The invariant was three hours old and the
corpus found its error immediately.

Plus two format facts (a split parent counts `fEntries` but never
`fEntryNumber`; a slot may wrap an object *reference* in a byte count, which ROOT
never writes and its reader accepts) and six reader gaps. Two files are ignored
with per-invariant reasons in `gen/foreign/IGNORE.toml`: one writes basket keys
without ROOT's unconditional `+1000`, the other has a key-list record whose
`fNbytes` is 48 bytes short, which sends a chain walk into the middle of a record
(`Record.md` §1).

### 9.9 Standing result over `gen/cern/`

72 files, ROOT 2.24/00 – 6.35/01, **0 failures** since 2026-09-17, and 180 files
(5.23/02 – 6.38/00, and two g4tools files) at 0 on the other side (§9.8). The probe, as of 2026-09-23:
1623 decoded, 264 container, 480 partial, 13 blocked. Of the partial, 468 are
`pippa.root`, a ROOT 2.24 file with no streamer infos at all (out of scope for
objects, decision 7).

Before `spec/03-classes/RooFit.md` (2026-09-21) the probe gave 1396 decoded, 264
container, 515 partial and 205 blocked, and 197 of the blocked were RooFit
classes in two `stressRooFit_*` files, then out of scope (decision 8). Every one
of them now decodes. What is left blocked is RNTuple's four `RBlob` records and its
anchor, seven collections whose value class has no streamer info in the file
(`Collections.md` §9), and one slot referencing a class position that is not in
its buffer.

M6 added three more from here, all of them `TBranch` invariants that had only
ever been checked against files from ROOT 5.34 on: 11.1, 11.3 and 11.9, each
listed in §8.2. Before that, two came from here, both the same mistake in
different places, stating an equality where ROOT tests an inequality:

- a payload is compressed when `fObjLen > fNbytes - fKeyLen`, not when the two
  differ. The `!=` form is `TFile::Map()`'s display test; `TKey`'s read test is
  `>` in all eight places it decides. An RNTuple `RBlob` is the case that
  distinguishes them, and a reader using `!=` rejects the whole file;
- `fEND <= filesize` for a cleanly closed file, not `==`. Bytes past `fEND` are
  outside the format and ROOT never looks at them.

The `CS` codec had been written off in this document as a research project. `CS`
is raw DEFLATE, RFC 1951: the same algorithm as `ZL` without the zlib wrapper
(`root/core/zip/src/RZip.cxx:391-392`, `ZInflate.c:1048-1090`). In Python the
whole codec is `zlib.decompressobj(-zlib.MAX_WBITS)`, and all 468 compressed
records of `pippa.root` decompress with it. A claim in the document ("rare but
readable") had gone unverified long enough that its cost was assumed rather than
measured.

**The one open failure, closed 2026-09-17.** `aod_flushed.root` (ROOT 5.25/04)
failed `StreamerDriven 10.1` on its `TTreePerfStats` record, whose `kBase`
element for `TVirtualPerfStats` contributes a bare `TObject`, ten bytes, with no
version word of its own (`StreamerDriven.md` §4.5). The rule is not derivable
from a file, so clearing it meant publishing the class list, which is M2 and
`spec/99-appendix/ForwardingStreamers.md`. The record now decodes, with
`fReadaheadSize` on 256000 exactly where the byte count put it.

### 9.10 What the corpora already contain — measured 2026-09-17

The census that reframes §9.1 and §3.5, taken over all corpus files by walking
every `StreamerInfo` record and every directory record.

**Directory record versions**: 5 (339), 1 (24), 4 (5), 3 (2), 1001 (2 — the large
form). Version 2 does not occur. §9.1 had this as "needs a legacy ROOT".

**`TStreamerInfo` record versions**: 9 (3408), 8 (1498), 6 (407), 2 (149),
5 (75), 4 (64), 10 (19 — ROOT 6.36 and later). 695 infos are below version 8,
the threshold the collection layouts turn on.

**`TStreamerElement` base versions**: 4 (31186) and 2 (979). Version 3, the form
that persists `fXmin`/`fXmax`/`fFactor`, does not occur.

> Re-measured 2026-09-22 with `root/roottest/` added, whose 273 files the pinned
> submodule ships: 4 (60 835), 2 (8 364) and **3 (223, all in `skim.root`)**.
> Directory version 2 still occurs nowhere. `PLAN-corpus.md` C8–C11.

**Class versions present, against the pinned submodule's current version**:

| Class | In the corpora | Current |
|---|---|---|
| `TBranch` | 7, 8, 9, 10, 11, 12, 13 | 13 |
| `TTree` | 5, 9, 11, 16, 17, 18, 19, 20 | 20 |
| `TBranchElement` | 1, 8, 9, 10 | 10 |
| `TH1` | 3, 4, 5, 6, 7, 8 | 8 |
| `TAxis` | 6, 7, 9, 10 | 10 |
| `TProfile` | 4, 5, 6, 7 | 7 |
| `TGraph` | 3, 4 | 5 |
| `TFormula` | 8, 10 | 14 |
| `TF1` | 7, 9 | 12 |
| `TPad` | 7 | 13 |
| `TList` | 4, 5 | 5 |

The histogram, graph and profile rows cost nothing: those classes are
streamer-info driven at every version present (`03-classes/index.md`). The
`TBranch`, `TFormula`/`TF1` and `TPad` rows are the ones with hand-written
legacy layouts, and they are M6 and §9.1.

**Forwarding-only base classes** (M2): of the 540 classes in the submodule with
`ClassDef` version `≤ 0` and a plain `#pragma link`, only two appear as a `kBase`
element anywhere in the corpora: `TSeqCollection` (348) and `TVirtualPerfStats`
(1). 117 distinct base-class names occur in total.

### 9.11 The `TTree` sub-plan's residue ⏸

`PLAN-ttree.md` ordered this layer and was deleted on 2026-09-17, its work done:
all four documents written, `rootfile.TreeReader` decoding the split path, and
every case in its fixture matrix built or absorbed (`split-stl` by
`ttree/split-nested`, `split-branch-object` by `ttree/branch-clones`). Its
dispatch table is now `TBranchElement.md` §8 and its structural findings are in
the four documents themselves; the git log has the sections that were consumed.
What had no other home is here.

**The census it was written against**: the 178 corpus files recorded at the time
(180 now), every record whose class derives from `TTree`, every `TBranch*` member
at every depth. Measured, not estimated:

| Measured | Value |
|---|---|
| Branches that are not `TBranch` | 6736 of 11157, in 56 files |
| Branch classes | `TBranch` 4421, `TBranchElement` 6734, `TBranchObject` 2, `TBranchClones` 0, `TBranchSTL` 0 |
| `fType` | 0 (4220), 41 (1503), 31 (733), 1 (141), 4 (84), 3 (21), 2 (16), −1 (16) |
| `fID` where `fType == 0` | −1 (216, unsplit top level), −2 (170, split node, which ROOT's own header comment does not mention), ≥ 0 (3834, a member) |
| `fSplitLevel` | 0, 1, 2, 3, 4, 97, 98, 99 — never 100, so the two pointer-collection procedures have zero corpus coverage and `ttree/split-ptr-collection` is their only witness |
| `fBranchCount2` | null in all 6736 |

**What the decoder still cannot reach**, largest first, re-measured after M6.
This is what the `SKIPPED` and `ENTRIES` lines of `check_invariants.py` count:
1001 of 27949 branch-baskets over the two corpora.

1. A collection whose value class has no streamer info in the file. This is not a
   gap at all: `Collections.md` §9 says it is unreadable by anyone, ROOT
   included.
2. `fType` −1, a branch whose class writes its own `Streamer`, including the Jpp
   classes of `gen/foreign/IGNORE.toml`. It is the only `fType` value with no
   fixture, and needs a branch whose class has a hand-written `Streamer`.

Those two are all that is left, 67 branch-baskets of 28036, and both are things
no reader could decode. The embedded basket that was item 1 here is closed (M8),
and so is the embedded counter basket (M6). What remains below is about values
rather than about reaching them:

3. `kStreamLoop` values — 4, all in one file. The column's *extent* is checked
   from its byte count; its values need the per-element counts held by a sibling
   branch's column.
4. `TBranchSTL` entries — `ttree/split-ptr-collection` has one with data in it,
   but it is not a `TBranchElement` and has no leaf, so neither entry check
   reaches it. `Splitting.md` §5 describes the branch; its entries stay
   undecoded.
5. A non-null `fBranchCount2`: no file in 178 has one, so the second-dimension
   path is unexercised and unwritten.
6. `TBranchObject` entries. Its `TLeafObject` has no fixed width, so the
   leaf-driven check cannot walk it, and since 2026-09-24 its baskets are counted
   as skipped rather than left out: 5 in the corpora, 1 in the fixtures, 8 in
   roottest's `v5formula_clones.root`.

**Questions it left open.** Each is small, and each needs the submodule rather
than a file:

- Why `fParentName` is empty on 16 of 21 `fType == 3` branches whose `fID >= 0`,
  when everywhere else the empty case lines up with `fID < 0`.
- Why `fMaximum` is zero on half the `fType == 4` branches.
- Whether `fBranchCount`'s back-reference uses the same map-position convention
  as `fLeaves` and `fLeafCount`. Near-certain, and unverified at byte level.
- Whether a `fType == 0` branch with an empty `fLeaves` can be written at all, or
  whether `root/tree/tree/src/TBranchElement.cxx:6037-6044` is dead defensive
  code. An errata row if it is dead, a fixture if it is not.

**Two decisions recorded there and nowhere else:**

- **A cross-file `TFriendElement` and a `TChain` are not committed fixtures.**
  Both record a path that must exist when the file is read, which makes them
  awkward to ship and their absence a decision rather than a gap;
  `Auxiliary.md` §7 points here.
- **`coverage_probe.py` measures record decoding only**, so it reports a split
  file as almost fully covered while none of its values is decoded.
  `check_invariants.py`'s `ENTRIES` line is the accurate figure; moving it into
  the probe would make it per file rather than per run.
