# PLAN — ROOT I/O Specification

**Status: the format is specified end to end for files written by ROOT 4 and
later.** The container, the object layer, the divergent classes and the whole
`TTree` reading path are written, cited against the pinned submodule and checked
against bytes; RNTuple tracks ROOT's own specification plus six errata. What
remains before this is a book a third party can pick up is in §8, which is the
part of this document to read first.

Measured, 2026-09-17, by the checks in `tools/`:

| | |
|---|---|
| Specification documents | 34, plus the tracked RNTuple copy |
| Reference files / byte assertions | 64 / 1515, 0 failures |
| Source citations checked | 1085, 0 failures |
| Class versions checked against `ClassDef` | 20 |
| Invariants over the fixtures | 64 files, 0 failures |
| Invariants over both corpora | 226 files, ROOT 2.24/00 – 6.36/02, **1 failure** (§9.9) |
| Entries decoded and checked | 25937 of 26011 branch-baskets, 99.7% |

Throughout: **✅ done**, **◐ partly done**, **☐ not started**. §9 is the gap
register — every gap the written documents record, so they can be picked up
rather than rediscovered. The blow-by-blow of how each was found is in the git
log, not here; this document keeps only what is still live plus the measurements
the scope decisions rest on.

## 1. Goal

Produce a complete, versioned, machine-checkable specification of the ROOT
on-disk formats, sufficient for a third party to implement a reader **without
reading ROOT's C++ source**.

Reading is specified normatively. Writing is covered by **invariants** rather
than algorithms: each layer states what a conforming file must satisfy, so a
writer can validate its own output without this document prescribing ROOT's
particular free-space allocation or key-placement strategy. See §2.8.

Non-goals: ROOT's C++ API, its in-memory data structures, its build system. We
document *bytes on disk* and the *algorithms* required to turn those bytes into
values.

This specification is **descriptive of ROOT 6.40.04**, not normative for ROOT.
Where the pinned submodule and this document disagree, the submodule wins and the
discrepancy is a bug in this document. Where ROOT's own behaviour looks like a
bug, it goes in an errata table and, where possible, upstream (§7.1).

### 1.1 Why

`root/tree/ntuple/doc/BinaryFormatSpecification.md` is the only real
specification ROOT ships, and it covers only RNTuple. For TFile/TTree:

- `root/io/doc/TFile/*.md` documents **release 3.02.06** (one page was partially
  refreshed to 6.22.06). It still claims ZIP is the only compression algorithm
  and that there are "ten compression levels 0-9". It has no coverage of
  `TBranchElement`, member-wise STL streaming, `Double32_t`, schema evolution, or
  the 64-bit layout beyond the header. Roughly 37 errata against it are recorded
  in the documents that replace it.
- `root/io/doc/v5xx/`, `v6xx/` — release notes, not specifications.
- Everything else is source code.

Third-party implementations (uproot, groot, UnROOT.jl, root-io, JSROOT) have been
reverse-engineered from that source. This repo is intended to be the shared,
testable artifact those projects can cite and test against, and — where it finds
real bugs or under-specification — to feed fixes back upstream.

### 1.2 Reference version

The `root/` submodule is pinned at `v6-40-04` (`1211eda9301`). That is the
**reference implementation**. When a statement is version dependent we say so
explicitly; the pinned submodule is what the checkers in `tools/` run against.

## 2. Repository layout

```
root-io-spec/
├── README.md, PLAN.md, PLAN-ttree.md, CLAUDE.md
├── root/                         ← submodule, pinned to v6-40-04
├── spec/                         ← the specification; also the site (docs_dir)
│   ├── 00-conventions.md
│   ├── 01-container/  02-serialization/  03-classes/  04-ttree/
│   ├── 05-rntuple/               ← tracked copy of upstream + errata
│   └── 99-appendix/
├── gen/                          ← one generator macro per reference file
├── data/                         ← generated reference files (committed)
└── tools/                        ← checkers, and an independent reader
```

`spec/` is split by **layer**, not by class, because ROOT's format is layered and
almost every class is described by the container plus the serialization layer plus
a `TStreamerInfo` read out of the file itself. Only the divergent classes need
hand-written text, and structuring the repo this way makes the *size of the
hand-written surface* explicit — the thing third-party implementers currently
have to discover the hard way.

Still missing from the layout, and required for release (§8):
`LICENSE`, `CONTRIBUTING.md`, `CITATION.cff`, `CHANGELOG.md`.

### 2.1 `spec/00-conventions.md` ✅

RFC 2119 keywords; endianness (**TFile/TBuffer is big-endian; RNTuple payload is
little-endian** — the same file contains both); the primitive type table
including `Long_t` at **8 bytes on disk even where it is 4 in memory**; the four
string encodings (counted string, `TString`, `TStringLong` §5.1.1, NUL-terminated
class tags); the notation for byte layouts; and how citations work.

### 2.2 `spec/01-container/` ✅ except `LargeFiles.md`

| File | Contents |
|---|---|
| ✅ `FileHeader.md` | The 64/100-byte header, `fVersion`, the `+1000000` large-file flag and the field widening it implies |
| ✅ `Record.md` | `TKey` layout, `fNbytes`/`fObjLen`/`fKeyLen`, cycles, the `fSeekKey` self-check, the key-of-a-key for large files, `fDatime` as a bare member |
| ✅ `Directory.md` | `TFile`'s own record, `TDirectoryFile`, the keys list, `fSeekDir`/`fSeekParent`/`fSeekKeys`, nested directories |
| ✅ `FreeSegments.md` | The `TFree` list, the sentinel segment past EOF, gaps, the interleaved 10-/18-byte forms |
| ✅ `Compression.md` | The 9-byte block header, the `ZL`/`XZ`/`L4`/`ZS`/`CS` magics, multi-block payloads, the LZ4 XXH64 trailer, `fCompress` as `100*algorithm + level`, which records are never compressed, and that `CS` is raw DEFLATE (§3.1) |
| ☐ `LargeFiles.md` | Everything that changes past 2 GB, collected in one place — **decided: write it**, §8 item M5 |

What changes past 2 GB is currently stated where it arises: `FileHeader.md` §2,
`Record.md` §3.5–3.6, `FreeSegments.md` §3. The measurements in §9.2 make a
single page writable against something real.

### 2.3 `spec/02-serialization/` ✅

The core of the repo, and the answer to "how do we handle custom classes".

| File | Contents |
|---|---|
| ✅ `Buffer.md` | Byte counts (`kByteCountMask`), the version word and `kByteCountVMask`, `ReadVersion`'s no-byte-count path, class tags (`kNewClassTag`, `kClassMask`), the buffer map and `kMapOffset`, deduplication, `kNullTag`, the `TObject` base |
| ✅ `StreamerInfo.md` | The `StreamerInfo` key, the `TList` of `TStreamerInfo`, and the byte layout of `TStreamerInfo` plus every `TStreamerElement` subclass — **the bootstrap set, which cannot be read using streamer info** |
| ✅ `StreamerDriven.md` | The normative algorithm: given a `TStreamerInfo` and a byte range, produce a value tree — plus §7 on when the info is fiction, §4.4 a hand-written base, §4.5 a version-0 forwarding streamer |
| ✅ `ElementTypes.md` | The complete `EReadWrite` table → exact bytes, the `Double32_t`/`Float16_t` grammars, and §2.4–2.5: `fType` is not a stable property of a class, and a value can be `0x99` because nobody wrote one |
| ✅ `Collections.md` | STL containers, proxies, object-wise vs member-wise, `std::map` shapes, `TClonesArray`'s bespoke format |
| ✅ `SchemaEvolution.md` | Class version 0, checksums, `TSchemaRuleSet`, conversion/artificial/cache/skip elements, emulated classes |
| ✅ `References.md` | `TProcessID`, `TRef`, `TRefArray`, `kIsReferenced` and the extra `fPID` word |

### 2.4 `spec/03-classes/` — per-class layouts ◐

**Decision (settled, and now measured rather than argued): specify only the
classes whose recorded streamer info does not describe their bytes.**

The original plan was generated version matrices and member tables for ~440
persistable classes. That aims at the wrong target: a generated table restates
what the streamer info in the file already says, and `tools/rootfile.py` decodes
**99.7% of branch-baskets across both corpora** from the file's own infos with no
per-class knowledge beyond the bootstrap set. `tools/gen_tables.py` is therefore
not planned.

What a reader cannot get from a file is **which classes the file is lying
about**. `tools/inventory.py` extracts that set from the pinned submodule into
`spec/99-appendix/HandWrittenStreamers.md`, CI-checked, with every class resolved
in `streamers.toml` — so a submodule bump that adds or drops a hand-written
`Streamer` fails until someone classifies it.

**185 hand-written `Streamer` definitions**, sorted by what the reading branch
does:

| | Count | What a reader has to do |
|---|---|---|
| `delegating` | 35 | nothing — `ReadClassBuffer` with no version test. **Except three that read more bytes afterwards; see §8 item M1, this is a published error** |
| `guarded` | 88 | nothing for a current file: `ReadClassBuffer` above a version threshold, a legacy layout below. Those legacy layouts are §9.1 |
| `custom` | 62 | know the layout; the streamer info describes the bytes at no version |

Of the 62 `custom`: **34 specified**, 5 never objects in a file, 14 outside scope
(RooFit, EVE, SOFIE, the SQL backend), **9 gaps** — `TASImage`, `TClassTree`,
`TMaterial`, `TMixture`, `TPolyLine3D`, `TPolyMarker3D` and the three
`graf2d/gviz` wrappers. All of narrow reach; none is something a physics file is
likely to hold, and they are **not** in the MVP (§8).

Written so far: ✅ `TArray.md`, ✅ `Containers.md` (`TMap`, `TExMap`, `TBtree`),
✅ `Formula.md` (`ROOT::v5::TFormula`/`TF1Data` against the ROOT 6 classes),
✅ `Canvas.md` (`TCanvas`, `TQObject`, and the zero-byte base), ✅ `index.md`
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

`Double32.md` was dropped as already-written and distributed: the grammar and the
three encodings are `ElementTypes.md` §5.1–5.3, the leaf classes and the
3-versus-4-byte asymmetry are `TLeaf.md` §7 (`PLAN-ttree.md` §4).

`PLAN-ttree.md` is the sub-plan that ordered this layer; it is kept for its
measurement of the corpora and for §10's list of what the decoder still cannot
reach.

### 2.6 `spec/05-rntuple/` ◐

RNTuple already has a real specification and we do not fork it.

- ✅ `BinaryFormatSpecification.md` is a **verbatim tracked copy** of
  `root/tree/ntuple/doc/BinaryFormatSpecification.md` at the pinned commit.
  `tools/sync_rntuple.py --check` fails on drift, in CI, on every push, and also
  asserts that the commit `UPSTREAM.md` records is the pin. **Never edit it.**
- ✅ `UPSTREAM.md` provenance and sync procedure; ✅ `ERRATA.md` (six entries);
  ✅ `NOTES.md` implementation notes, including the audit state table.
- ✅ The envelope audit, through every envelope, and a fixture of our own
  (`rntuple/anchor`, `rntuple/fundamental-types`), plus an independent reader in
  `tools/rootfile.py`.
- ◐ The **type mapping** — which columns a given C++ type produces — advances one
  fixture at a time and is the largest remaining piece here (§8 item M9).

### 2.7 `spec/99-appendix/` ◐

| File | State |
|---|---|
| ✅ `Bootstrap.md` | The minimal hardcoded class set, in dependency order; the only document organised as a work order rather than by layer. `tools/test_bootstrap.py` checks its lists against what `rootfile.py` hardcodes, in both directions |
| ✅ `Glossary.md` | Every term used with a meaning it does not have in ordinary English |
| ✅ `HandWrittenStreamers.md` | Generated from the submodule by `inventory.py`; §2.4 |
| ☐ `ReaderChecklist.md` | An implementation checklist for a new reader — **MVP**, §8 item M3 |
| ☐ `Pitfalls.md` | The things that have historically bitten implementers, each linking to the normative section — **MVP**, §8 item M3 |
| ☐ `Bibliography.md` | The old ROOT docs, the user's guide, prior art — **MVP**, §8 item M3 |
| ☐ `WriterInvariants.md` | The collected index of §2.8. A collation job; `tools/check_invariants.py` is already its executable form. Not MVP |

### 2.8 Write support: invariants, not algorithms ✅

Each layer document ends with an `## Invariants` section stating what a
conforming file must satisfy, so a writer can validate its own output and a
reader knows which consistency checks are worth making — without this document
elevating ROOT's incidental implementation choices to requirements.
`tools/check_invariants.py` is the executable form: every entry is checked, and
each was confirmed to catch a corruption of a fixture.

Where a write-side rule genuinely has no freedom — the compression block header,
the `Double32_t` factor encoding, the `fNevBufSize` sign trick — it is specified
exactly. Deliberately **not** specified: free-space allocation policy, basket
sizing, key ordering, when ROOT chooses to rewrite a directory.

## 3. Reference files

### 3.1 Layout

```
gen/cases/<group>/<case>/{gen.C, case.toml[, classes.h][, README.md]}
data/<group>/<case>.root            + data/MANIFEST.sha256
```

One case = one file = one specific thing exercised. 64 cases in five groups:
`container/`, `serialization/`, `classes/`, `ttree/`, `rntuple/`. A case with a
`classes.h` gets it compiled into a dictionary with ACLiC before the macro loads
(`gen/common/README.md`), which is what makes a real `ClassDef` reachable from a
generator.

### 3.2 `case.toml`

Assertions are **byte offsets** — `{name, offset, type, value}` — checkable with
stdlib Python alone and with no reader at all, which is what lets a third-party
implementation in any language use the corpus as test vectors on day one. The
cost is that assertions are tied to absolute offsets, so editing a `gen.C`
renumbers them; in practice that has been cheap and has repeatedly caught errors.

`case.toml` also carries a prose `description`, a `[[records]]` table giving the
record chain, and a `spec` list naming the documents the case supports. Semantic
`path`/`value` assertions remain worth adding as a complement (§9.6); they are
not MVP.

### 3.3 Determinism

Byte-exact reproducibility is **not** achievable: every `TKey` records the wall
clock and every file *and every directory* gets its own `TUUID`.
`tools/normalize.py` computes a digest with those masked, and CI regenerates and
compares the normalized digest. Also masked, each for a reason that cost time to
find:

- the **process UUID as text**, 36 ASCII characters in a `TProcessID` record;
- an **embedded basket's `TKey::fDatime`**, twice per basket, because the raw
  buffer copy begins with the key all over again;
- **`TBranchElement::fCheckSum` when `fClassName` is an STL type**, since a
  checksum folds in member type names the two standard libraries spell
  differently;
- every **`TStreamerElement::fSize`**, which is `sizeof` on the writing machine
  (`sizeof(std::string)` 24 with libc++, 32 with libstdc++). Because the digest
  can no longer see `fSize`, a case SHOULD assert it directly for members whose
  `sizeof` is standard-library independent.

Two fixtures opt out with `digest = false` and a required `digest_reason`,
printed on every run as `NO DIGEST`, because the difference is a **length**
change a mask cannot undo: `serialization/pairs` (libstdc++ carries doc comments
on `std::pair`'s members) and `rntuple/anchor` (`std::uint64_t` resolves to
`unsigned long` on one platform and `unsigned long long` on the other, so the
same member is `kULong` on one and `kULong64` on the other — the format fact is
`ElementTypes.md` §2.4). `classes/canvas` opts out for a third reason: the
order of entries in the `StreamerInfo` record is process registration order, not
a property of the file (`StreamerInfo.md` §3.4).

**Every new case must go through the container loop in `CLAUDE.md` before a
push**, not after a red build. The drift is libc++ against libstdc++, not
architecture, so an arm64 container reproduces the x86_64 CI digests byte for
byte.

### 3.4 The two corpora

Neither is committed; both are fetched, and each file earns its place by covering
something no fixture and no other listed file does.

| | Files | Reach | Provenance |
|---|---|---|---|
| `gen/cern/` | 72 (+8 by range request, +2 physics) | ROOT 2.24/00 – 6.35/01 | published by the ROOT team at <https://root.cern/files/>, so a failure **is** evidence |
| `gen/foreign/` | 154 | ROOT 4.00 – 6.36/02 | uproot's regression corpus, which includes files uproot wrote, so a failure is a **lead** |

A lead must be diagnosed against the pinned source and resolved to one of four
things — a spec error, a missing format fact, a reader gap, or a file at fault.
Only the last goes in `gen/foreign/IGNORE.toml`, per file and per invariant, with
a reason and with the suppressed count printed. **Never weaken an invariant
because a file disagrees with it.**

`tools/fetch_cern.py --headers` re-reads the header and free-segment record of
eight files from 1.3 GB to 5.3 GB over HTTP range requests — about 8 KB of
traffic for 20 GB of files. **It is the only thing exercising the large-file
layout at all** (§9.2).

### 3.5 Historical versions

Most class versions cannot be produced by ROOT 6.40. The original plan was
`gen/legacy/` — per-version containers and release artifacts. It does not exist,
and §9.10 is the reason it is no longer the blocker it was recorded as: **the two
corpora already contain most of the legacy layouts §9.1 lists**, written by ROOT,
which is evidence rather than a fixture but is enough to specify and check
against. `gen/legacy/` stays deferred; where a version is genuinely unreachable
we say so in the document rather than guessing.

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
| `rootfile.py` | An **independent** pure-Python reader of everything `spec/` specifies, written from the specification rather than from ROOT's code, so the two disagreeing is a detectable event. It reproduces `TFile::Map()` exactly |
| `coverage_probe.py` | Not a CI check: how much of an arbitrary file the specification covers, and what blocks the rest |
| `rootcite.py` | Markdown extension turning a citation into a link at the pinned commit |
| `fetch_cern.py`, `fetch_foreign.py` | The corpora; `--headers` for the large files |
| `test_*.py` | 187 unit tests, run in both workflows |

Dropped from the original plan: `dump_streamerinfo.C`, `gen_tables.py` and
`coverage.py`, all three in service of generated member tables (§2.4).

## 5. Status by layer

| Layer | State |
|---|---|
| Conventions | ✅ |
| Container | ✅ except `LargeFiles.md` (§2.2) |
| Serialization | ✅ all seven documents |
| Standard classes | ✅ the divergent set, bar nine narrow classes (§2.4) |
| `TTree` | ✅ records, branches, leaves, baskets, splitting, reading an entry — unsplit and split |
| RNTuple | ◐ upstream tracked, envelopes audited, six errata; the type mapping is partial |
| Appendix | ◐ three of six documents |
| Legacy reading (pre-ROOT 6) | ◐ specified where cited, unchecked where no file was available — §9.1, §9.10 |
| Release plumbing (licence, citation, version) | ☐ §8 |

The phase numbering the earlier drafts used (0 skeleton, 1 foundations, 2 object
layer, 3 bootstrap classes, 4 standard classes, 5 `TTree`, 6 RNTuple, 7 legacy)
is retired: phases 0–3 and 5 are complete, 4 is complete bar the nine narrow
classes, and what is left of 6 and 7 is listed in §8 by value rather than by
phase.

## 6. Decisions

| # | Question | Decision |
|---|---|---|
| 1 | Scope of "every standard class" | **Revised 2026-09-17.** Not generated tables for ~440 classes: specify the classes whose streamer info does not describe their bytes, and let the generic algorithm cover the rest. The set comes from `inventory.py`, not from an estimate (§2.4) |
| 2 | Normative status | Descriptive of 6.40.04; the pinned submodule is the tiebreaker; errata for suspected ROOT bugs |
| 3 | Write support | Reading normative; writing specified as per-layer invariants, not algorithms (§2.8) |
| 4 | Upstream relationship | Standalone repo, not blocking on review. RNTuple errata go upstream as PRs; open a conversation with the ROOT I/O team about eventually replacing `io/doc/TFile/` |
| 5 | Fixture distribution | Core corpus committed (<10 MB). Legacy-ROOT and >2 GB cases as release artifacts with a committed manifest — superseded in practice by the two corpora (§3.4, §3.5) |
| 6 | Where a divergent class is specified | **Cross-reference, do not re-home.** A class stays in the layer document where its behaviour arises; `03-classes/index.md` maps every divergent class to wherever that is. `TObject` belongs with buffer framing, `TList`/`TObjArray` with streamer information, `TClonesArray` with collections, `TRef` with references, `TStringLong` with the string encodings |
| 7 | **Version floor** (new, §8 item M4) | The specification claims **reading** for files written by ROOT 4.00 and later. Older files are in scope for the container layer only — they carry no streamer infos at all, so their object layouts would have to be hardcoded per class and per version (§9.10). To be stated in `spec/index.md`, not left implicit |
| 8 | **What is out of scope** (new, §8 item M4) | RooFit's own classes, EVE, SOFIE, the SQL backend, GUI classes, and hand-written analysis of `TGeo*`. Recorded per class in `streamers.toml` so the list stays complete, and to be stated once in `spec/index.md` |

## 7. Open items

1. **When to approach the ROOT I/O team.** The condition — a concrete artifact
   rather than an intention — has been met for some time. The six RNTuple errata
   are against a document the ROOT team owns and maintains, which makes them a
   friendlier first contact than §7.1's bug candidates, and they can carry those.
   Deliberately deferred until the MVP is out (§8 item M10).
2. **`TGeo*` hand-review** — 88 persistable classes, self-contained, genuinely
   present in real files. Out of scope by decision 8 unless a blocked record
   demands it; nothing in either corpus does.
3. **Markup format if upstreaming happens.** `root/io/doc/` is doxygen with
   `\page`/`\ref`; our tables and bit diagrams are better in plain Markdown.
4. **Reference reader.** Resolved by accident: `tools/rootfile.py` grew into one,
   and it is the strongest completeness check the project has. It stays a
   checking tool that happens to be thorough.
5. **`TTree` sub-plan** — resolved: `PLAN-ttree.md`.

### 7.1 Upstream bug candidates found while writing the spec

Verified against the pinned submodule and against real bytes; **not yet
reported** (§8 item M10).

0. **`TFormula::fAllParametersSetted` is written to file uninitialized.** A
   `TF1("g", "gaus", -3, 3)` never assigns it on any path taken, so what reaches
   the file is ROOT's heap fill pattern: `classes/formula` byte 665 is **0x99**
   for a `Bool_t`. Deterministic rather than random —
   `TStorage::ObjectAlloc` `memset`s new `TObject`s with `kObjectAllocMemValue`
   (`root/core/base/src/TStorage.cxx:291-295`). Worth reporting because it is
   *silent*, and the same mechanism writes any unassigned persistent member of
   any type (`ElementTypes.md` §2.5).
1. **A `std::vector<T>` of an interpreted class writes an unreadable file.**
   `T`'s streamer info is not recorded when the only reference to it is through a
   collection, and there is **no warning on the write side**; reopening gives
   `CheckByteCount ... read too few bytes`. The direct-member path does warn,
   which is what makes this a bug rather than a limitation. `Collections.md` §9.
2. **The two collection readers disagree on the `kSTLp` version threshold.**
   `TStreamerInfoActions.cxx:845` uses `>= 8` where
   `TStreamerInfoReadBuffer.cxx:1167` uses `>= 9`. No such file has been
   constructed here; verify before reporting. `Collections.md` §6.
3. **`kGenerateOffsetMap` cannot reach a `TBranchElement`.** Every constructor
   delegates to the default `TBranch()`, which does not copy the tree's
   `fIOFeatures` (`root/tree/tree/src/TBranchElement.cxx:168`), so
   `TTree::SetIOFeatures` silently has no effect on most branches in a real file.
   Source-verified; not yet confirmed by generating such a file.
4. **An empty `TLeafC` string is misread in a multi-leaf branch.** An empty
   string occupies zero bytes and `TLeafC::ReadBasket` detects that by comparing
   **whole-entry** offsets (`root/tree/tree/src/TLeafC.cxx:146-166`), which is
   only the same test when the `TLeafC` is the branch's only leaf. Verified at
   byte level; a reproducer is written. `TLeaf.md` §9.
5. **A `TLeafC` cannot be followed by another leaf in a leaflist.** `fOffset`
   doubles as the in-memory offset, and a `TLeafC` contributes 1
   (`root/tree/tree/src/TBranch.cxx:436`), so `c/C:x/I` reads `x` from the second
   byte of the string. Silent, verified at byte level. `TLeaf.md` §3.2.
6. **The suspected `TFile::Recover` gap bug** — banked, still unverified.
7. **A `pair<K,V>`'s checksum can be computed before its members are known**, and
   `TClass::GetCheckSum` then caches it forever
   (`root/core/meta/src/TClass.cxx:6655-6666`), so several distinct pairs share
   one value. `data/serialization/pairs.root` has three pairs all carrying
   `0x0b5fb752`. Not data loss for ROOT, which resolves the value class by
   declared type name — but a hazard for every other reader, since the obvious
   checksum-to-info table decodes two of those three as the wrong type.
   `Collections.md` §8.2.

## 8. MVP — what "done enough to publish" means, and the work to get there

The specification is already more complete than anything else available, and the
checks behind it are sound. What stops it being a book a third party can adopt is
a small, nameable set of things: one published claim that is **wrong**, three
missing on-ramp documents, an unstated scope, and no licence.

### 8.1 Release criteria

1. **No published claim is known to be wrong.** ← violated today, item M1.
2. **Scope is stated**: which ROOT releases the spec covers for reading, and what
   is deliberately out of scope (decisions 7 and 8).
3. **A reader can find the path in**: an ordered implementation checklist and a
   pitfalls page, both linking into the normative text.
4. **Zero unexplained failures over both corpora.** One failure remains
   (`aod_flushed.root`, §9.9), and it is explained but not cleared: item M2.
5. **Citable and reusable**: a licence for `spec/` and for `tools/`+`gen/`, a
   `CITATION.cff`, a version number, a changelog, a tagged release, and a
   published site.
6. **The front pages are accurate.** `README.md` and `spec/index.md` both still
   say RNTuple is not started and quote fixture counts from 29 files.

### 8.2 The work, in order

Each item says why it is in the MVP, what it touches, and what proves it done.
Items M1–M7 are the MVP; M8–M10 are the next tier and are listed so the order is
explicit.

**M1 — `delegating` is wrong for three classes, and the inventory misses two.**
*The only known-wrong published claim, and it mis-decodes a class that real
physics files contain.*

`HandWrittenStreamers.md` says of `delegating`: "the bytes themselves are exactly
what the streamer info describes". For three of the 35 that is false — the read
branch consumes **more bytes** after `ReadClassBuffer`, inside the same byte
count:

| Class | What follows `ReadClassBuffer` | Cite |
|---|---|---|
| `TMatrixTSym<Element>` | the upper-right triangle, `fNcols-i` elements per row, read with `ReadFastArray`; the lower triangle is reconstructed, not read | `root/math/matrix/src/TMatrixTSym.cxx:2030` |
| `TPointSet3D` | an `Int_t` and then an array | `root/graf3d/g3d/src/TPointSet3D.cxx:156` |
| `RooBinning` | four `operator>>` reads | `root/roofit/roofitcore/src/RooBinning.cxx:298` |

The same shape as `ROOT::RNTuple`, whose `Streamer` reads an 8-byte XXH3 checksum
after `ReadClassBuffer` and **outside** the byte count
(`root/tree/ntuple/src/RNTuple.cxx:25-49`) — and which `inventory.py` does not
list at all, because `DEFINITION` does not match an out-of-line definition
written with a qualified name. The two it misses are `ROOT::RNTuple` and
`RooWorkspace::CodeRepo` (`root/roofit/roofitcore/src/RooWorkspace.cxx:2427`).

The corpora have been saying so: `TMatrixTSym<double>` "consumed 48 of 3528
bytes" is five blocked records in `gen/foreign/` and more in `gen/cern/`, and it
was filed as a divergent class the specification had not written up rather than
as a contradiction of the `delegating` claim.

Work:
- `inventory.py`: match qualified out-of-line definitions; add a fourth kind for
  a read branch that does I/O after `ReadClassBuffer` in the same block (the
  scan that found these three is 30 lines and found **zero** such cases among
  the 88 `guarded`, so the `guarded` claim stands); tests for both.
- Re-word §1 of `HandWrittenStreamers.md` around four kinds.
- Specify `TMatrixTSym` — and with it `TMatrixT`'s modern path and `TVectorT`,
  which are the same family and are what a `TFitResult` holds — with a fixture
  and invariants. New `spec/03-classes/Matrix.md`.
- `rootfile.py` reads the triangle; the blocked records in both corpora clear.
- `TPointSet3D` and `RooBinning` get `streamers.toml` entries with the new kind.

*Done when*: `inventory.py --check` passes with four kinds, `Matrix.md` has a
fixture and invariants, and `coverage_probe.py` no longer reports
`TMatrixTSym<double>` as blocked in either corpus.

**M2 — publish the list a reader cannot derive from a file.**
*Clears the last corpus failure and hands over the one piece of out-of-band
knowledge the format requires.*

For a class whose `ClassDef` version is `≤ 0` **and** which was selected with a
plain `#pragma link C++ class X;` rather than `X+`, `rootcling` generates a
`Streamer` that calls each base's `Streamer` and **nothing else** — no version
word, no byte count, no members
(`root/core/dictgen/src/rootcling_impl.cxx:1332-1367`, the choice being
`root/core/clingutils/src/TClingUtils.cxx:3016`). Both generators write a
streamer info and both record class version 0, so **nothing in the file
distinguishes them**: `StreamerDriven.md` §4.5 states the rule and says a reader
needs the class list out of band.

Measured for this plan: 540 classes in the pinned submodule are version `≤ 0`
with a plain link, but only **two occur as a base class anywhere in the 226
corpus files** — `TSeqCollection` (348 occurrences) and `TVirtualPerfStats` (1).
So the table is cheap to publish and the carried set is tiny.

Work: extend `inventory.py` with a second generated table (version `≤ 0` + plain
link, CI-checked like the first); reference it from `StreamerDriven.md` §4.5 and
`Bootstrap.md`; carry it in `rootfile.py` as it already carries the bootstrap
classes.

*Done when*: `check_invariants.py` over `gen/cern/` reports **0 failures**
(`aod_flushed.root`'s `TTreePerfStats` record decodes), and the table is
CI-checked.

**M3 — the on-ramp: `ReaderChecklist.md`, `Pitfalls.md`, `Bibliography.md`.**
*The difference between a correct specification and a usable one. No new research
— all three are collation.*

- `ReaderChecklist.md`: the implementation order, with milestones a reader can
  stop at — open a file and list its keys; decompress; read the streamer infos;
  hardcode the bootstrap set; decode an arbitrary object; read an unsplit tree;
  read a split tree; RNTuple. Each step names the documents, the fixtures that
  prove it, and the invariants worth checking. `Bootstrap.md` is one section of
  this and is already written.
- `Pitfalls.md`: the traps, each one sentence plus a link — the two byte orders
  in one file; `Long_t` at 8 bytes on disk; `kIsReferenced` changing a fixed
  layout's length; version 0 versus a foreign class's checksum; `fType` 500;
  `fSize` and `fOffset` being unusable; `fType` not being stable across
  platforms; a `Bool_t` that is `0x99`; a streamer info that is fiction; the
  shared `pair` checksum; `flag >= 80` baskets with no offset array; the
  `!=`-versus-`>` compression test; `TStreamerInfo` order not being file content.
- `Bibliography.md`: ROOT's own docs (with what each is and is not good for), the
  user's guide, and the prior-art readers with a note on what each got right.

*Done when*: the three pages exist, the strict build passes, and every link in
them resolves to a section that actually says what the line claims.

**M4 — state the scope, and refresh the front pages.**
*A reader cannot currently tell whether a gap is unknown or deliberate.*

Write decisions 7 and 8 into `spec/index.md`: the version floor for reading
(ROOT 4.00 and later for objects; the container layer reaches 2.24/00), what a
pre-4 file needs that this document does not give, and the out-of-scope list.
Then bring `README.md` and `spec/index.md` up to date — both still say RNTuple is
not started and quote 29 fixtures and 723 assertions against today's 64 and 1515
— and replace the phase-by-phase status with the table in §5.

*Done when*: both front pages state the measured numbers, and the scope paragraph
names the four out-of-scope groups and the version floor.

**M5 — `LargeFiles.md`.** *Decided: collect it.*

Everything that changes past 2 GB, in one page: the `+1000000` `fVersion` flag
and `fUnits` 8, the widened header fields, the large key layout and the packed
`fPidOffset`, the 18-byte `TFree` entry interleaved with the 10-byte one, and
`fLast` above 2000000000. The sections it draws on stay where they are and it
links them, so nothing is duplicated as a second source of truth. The evidence
is the eight files measured by `fetch_cern.py --headers` (§9.2), including
`lhcb2.root` with `fEND` past 4 GB and `volume.root` with 32 large and 19 small
free entries in one record.

*Done when*: the page exists with a bit diagram per widened field, `--headers`
is cited as its check, and `zensical build --strict` resolves its links.

**M6 — the legacy layouts the corpora already contain.**
*The largest remaining in-scope blocked category over files ROOT wrote, and
§9.10 shows it is not blocked on `gen/legacy/` at all.*

| What | Records blocked | Reproducer |
|---|---|---|
| `TBranch` class versions 7, 8, 9 | 50 across both corpora | `mlpHiggs.root` 3.04/02 (v7), `uproot-from-geant4.root` 4.00/00 (v8), `stock.root` 4.00/07 (v9) |
| Directory record versions 1, 3, 4 | 31 directory records | `pippa.root` 2.24/00, and see §9.10 |
| `TStreamerElement` at base version 2 | 979 elements | 6 corpus files; `rootfile.py` already reads them, the spec describes the shape only in passing |
| `TStreamerInfo` record versions 2, 4, 5, 6 | 695 infos | same files; the collection layouts below info version 8 are the live question |

`TBranch.md` §13.1 already carries the fact that makes the generic algorithm
inapplicable at version 9 — the *is present* byte of `fBasketSeek` is a **width
selector** (`root/tree/tree/src/TBranch.cxx:3062-3066`) — byte-verified on
`stock.root`. What is missing is the full member order per version, and the
reader's refusal below version 10 turned into a decode.

*Done when*: `rootfile.py` reads `TBranch` 7–9 and directory versions 1–4, both
corpora still report 0 failures, and `coverage_probe.py` no longer names either
as a blocker.

**M7 — release plumbing.** *Without this the corpus cannot legally be vendored
as test vectors, which is the main way a third party would use it.*

`LICENSE` — CC-BY-4.0 for `spec/`, BSD-3 for `tools/` and `gen/`, as §2 has
promised since the first draft; `CONTRIBUTING.md` (how to add a case, the
two-witness discipline, the container loop); `CITATION.cff`; a spec version
number carried in `zensical.toml` and on the front page; `CHANGELOG.md`; a `v0.1`
tag; and a check that the Pages deploy actually serves the site.

*Done when*: the files exist, CI is green, and <https://ariostas.github.io/root-io-spec/>
serves the current build.

### 8.3 Next tier, after the MVP

**M8 — the embedded-counter-basket plumbing.** Four branch-baskets in
`ttree/branch-clones` skip because the counter branch keeps its basket embedded
in the `TTree` record and the counter lookup only knows how to fetch a basket
record. The bytes are in the file and `TBasket.md` §4.1 specifies them. It is the
one skip over the fixtures that is merely unimplemented, and closing it takes the
fixtures to 100%.

**M9 — the RNTuple type mapping.** Still unaudited: the rest of *Type Name
Normalization*, low-precision floats, the stdlib collections beyond
`std::string`, `std::atomic`, enums, user-defined classes, `RNTupleCardinality`,
streamed types, untyped collections, *Limits*, *Naming*, *Defaults* and the
compatibility notes. Each advances by one fixture plus a claim parsed out of the
tracked copy, the way `test_rntuple.py` already parses the *Fundamental Types*
table. `NOTES.md` §4 carries the same state table so it is visible in the
specification and not only here.

**M10 — report upstream.** Six RNTuple errata (lead with erratum 6: a column type
the document specifies, ROOT does not implement, and JSROOT does — two readers in
one repository disagreeing about the type set) plus §7.1's eight bug candidates.
Deferred to the end by standing decision, and the natural opening for open item 1.

**Not in the MVP, deliberately**: the nine narrow `custom` classes (§2.4);
`TGeo*` hand-review; `gen/legacy/`; the pre-ROOT-4 object layouts (decision 7);
semantic `case.toml` assertions; `WriterInvariants.md`; `TBranchSTL` entry
decoding and `kStreamLoop` values (`PLAN-ttree.md` §10).

## 9. Known gaps

Every gap the written documents record. **None is a hole in the prose**: in every
case the behaviour is specified and cited against the submodule, and what is
missing is a fixture proving it — a claim verified once rather than twice.

### 9.1 Legacy layouts

Reframed by §9.10: most of these are **not** blocked on `gen/legacy/` after all.
"Available" means a file in a corpus carries it; `gen/cern/` files are evidence,
`gen/foreign/` files are a lead until the writer is settled (§3.4).

| Gap | Document | Available in |
|---|---|---|
| Directory record versions 1, 3, 4 | `Directory.md` | ✅ 31 records, §9.10 — M6 |
| `TBranch` class versions 6–9 | `TBranch.md` §13 | ✅ `mlpHiggs.root` (7), `uproot-from-geant4.root` (8), `stock.root` (9) — M6 |
| `TStreamerElement` at base version 2 | `StreamerInfo.md` | ✅ 979 elements, §9.10 — M6 |
| Collection layouts below `TStreamerInfo` version 8 | `Collections.md` | ✅ info versions 2, 4, 5, 6 present — M6 |
| The version-3 `TStreamerElement` form with `fXmin`/`fXmax`/`fFactor` | `StreamerInfo.md` | ☐ not in either corpus (only 2 and 4 occur) |
| A buffer written with no byte counts | `Buffer.md` | ☐ needs a pre-ROOT-3 file; `pippa.root` is the candidate to check |
| A file old enough to take the `BuildEmulated` path | `SchemaEvolution.md` | ✅ `pippa.root`, ROOT 2.24/00, **zero streamer infos** — out of scope for objects by decision 7 |
| `TClonesArray` class version 3, where `kBypassStreamer` is `BIT(14)` | `Collections.md` | ☐ only version 4 occurs |
| `ROOT::v5::TFormula` 1–3 and `ROOT::v5::TF1Data` 1–4 | `Formula.md` §4 | ◐ v8/v7 in `uproot-issue-181.root` (ROOT 5.34/36); versions 1–4 in neither |
| A leaf class at a legacy version | `TLeaf.md` | ☐ `TLeaf` v2 and `TLeafObject` v4 are the current versions and are all that occur |

### 9.2 Needs a file over 2 GB

Discharged by range requests rather than by a fixture: `gen/cern/LARGE.toml`
records eight files from 1.3 GB to 5.3 GB and `fetch_cern.py --headers` checks
every recorded field on each run, downloading nothing.

| Confirmed | Evidence |
|---|---|
| The `+1000000` `fVersion` flag and `fUnits` 8 | six files, ROOT 5.19/03 – 6.23/01 |
| Offsets past 4 GB, where even an unsigned 32-bit reader fails | `lhcb2.root`, `fEND` 4 947 894 760 |
| The large `TFree` form **interleaved** with the small one in one record | `volume.root`: 51 entries, 32 large |
| `nfree` agrees with the parsed list; the last entry always passes `fEND` | all eight, counts 1 to 1539 |
| The boundary from below: over 1 GB and *not* large format | a CMS file at 1.997 GB with `units` 4 |
| A free record whose key class is a `TFile` subclass | the same file: `TStorageFactoryFile` |

Still not asserted by a committed fixture, and `fLast` above 2000000000 is still
unwitnessed. M5 writes this up.

### 9.3 Needs a compiled dictionary — ✅ unblocked

`gen/common/aclic.C` compiles a case's optional `classes.h` into a dictionary
before the macro loads, so a class with a real `ClassDef` is reachable from a
generator. Remaining: a member-wise collection whose value class has a `ClassDef`
(mechanism exists, case not written) and a `type=readraw` rule (same).

### 9.4 Needs two ROOT sessions or two files

| Gap | Document |
|---|---|
| A non-zero `pidf`, a non-zero `fPidOffset`, and a `fUniqueID` whose top byte survives to disk | `References.md` |
| Two streamer infos for one class distinguished by checksum | `SchemaEvolution.md` |
| A negative in-memory class version reaching disk as 1 | `SchemaEvolution.md` |
| A branch with a non-empty `fFileName`, naming the file its baskets went to | `TBranch.md` §14 |

`fPidOffset` arises when a key is copied between files, so one `TTreeCloner` or
`TFile::Cp` case would produce several of these at once.

### 9.5 Reachable now, just not written — ✅ closed 2026-09-16

Every row done, in seven cases. Eight of the twenty-odd items turned out to be
covered already or not to exist: `kAnyPnoVT` (70) **has no producer**, a `TH2F`
does **not** produce a concrete `TArray` info (a `TH2F` in a branch does), and
`kBits`, `TLeafObject`, `TLeafElement`, split branches, pointer collections and a
non-zero `fIOBits` were all already covered. Two findings came out of it: the
version word in a 500/501/85/86/87 frame is **not** the constant 10 but
`TStreamerInfo`'s class version in the writing ROOT (9 in practice, 10 only from
6.36.00), and a `kStreamLoop` of `TString` is **bare counted strings**.

### 9.6 Structural

| Gap | State |
|---|---|
| No checker decompresses | ✅ zlib, lzma and the legacy `CS` codec from the standard library; zstd on Python 3.14; LZ4 needs the `lz4` package, and a record whose codec is missing is reported as `NOT CHECKED` rather than passed |
| `rootfile.py` has no `TTree` support | ✅ tree, branches, leaves, baskets, entry spans, and the split decoder |
| Semantic (`path`/`value`) assertions were dropped in favour of byte offsets | ☐ worth adding as a complement; not MVP |
| Four fixtures were not digest-portable between macOS and Linux | ✅ three fixed by masks, one exempted with a reason; the causes are in §3.3 |
| Eight upstream bug candidates banked, not reported | ☐ §7.1, M10 |

### 9.7 What the coverage probe measures

`coverage_probe.py` applies the specification to a file it was not designed
around and ranks what blocked each record. It is how `TArray*` and `TBasket` were
identified as the highest-value documents to write, and how the two biggest
findings in the corpora surfaced — an embedded `TBasket` inside a `TTree` record
(20 records, 1065 skipped members) and a `std::string` written as a whole object
with no frame at all (114 records).

What it cannot tell us: it checks that a record's bytes are *accounted for*, not
that the values are right. `check_invariants.py` and `rootfile.entry_spans` are
what close that, and their coverage is the `ENTRIES` line.

### 9.8 Standing result over `gen/foreign/`

154 files, **0 failures**. The probe: 28374 decoded, 705 container, 12 partial,
24 blocked, 1 not walkable, plus 132 records whose LZ4 codec is unavailable
locally. The triage that got there turned **10 047 failures into 0** and found
**eleven specification errors**, each one published, wrong and reader-facing:

- a basket with no offset array is **not** fixed-length when its flag is 80;
- the last offset may equal `fLast` exactly, on an empty last entry;
- `fMaxIndex[1]` is the base checksum **or 0**, on every file ROOT 5 wrote;
- an STL element's `fType` is 500 on ROOT 5 and later but **300 on ROOT 4**;
- a counter may sit in the **base class** its `fCountClass` names;
- a counter's `fType` is any integer basic type, not only 6;
- a base that is an STL container is a `TStreamerSTL` and may **precede** a base;
- no two streamer infos for one class need differ in version and checksum;
- a `TLeaf`'s `fLen` may be **−1**, a documented parse failure;
- `fIsRange` may be set on a `TLeafElement`;
- `nfree` in the header is advisory and ROOT never uses it.

Plus two format facts (a split parent counts `fEntries` but never
`fEntryNumber`; a slot may wrap an object *reference* in a byte count, which ROOT
never writes and its reader accepts) and six reader gaps. Two files are ignored
with per-invariant reasons in `gen/foreign/IGNORE.toml`: one writes basket keys
without ROOT's unconditional `+1000`, the other has a 70-byte hole where a record
header should be.

### 9.9 Standing result over `gen/cern/`

72 files, ROOT 2.24/00 – 6.35/01, **1 failure**. The probe: 1396 decoded, 264
container, 515 partial, 205 blocked. Of the blocked, 197 are RooFit classes in
two `stressRooFit_*` files (out of scope, decision 8) and the rest are RNTuple's
`RBlob` and anchor; of the partial, 468 are `pippa.root`, a ROOT 2.24 file with
**no streamer infos at all** (out of scope for objects, decision 7).

Two specification errors came from here, both the same mistake in different
places — stating an equality where ROOT tests an inequality:

- a payload is compressed when `fObjLen > fNbytes - fKeyLen`, **not** when the
  two differ. The `!=` form is `TFile::Map()`'s display test; `TKey`'s read test
  is `>` in all eight places it decides. An RNTuple `RBlob` is the case that
  tells them apart, and a reader using `!=` rejects the whole file;
- `fEND <= filesize` for a cleanly closed file, not `==`. Bytes past `fEND` are
  outside the format and ROOT never looks at them.

And the `CS` codec, which this document had written off as a research project:
`CS` is **raw DEFLATE**, RFC 1951 — the same algorithm as `ZL` without the zlib
wrapper (`root/core/zip/src/RZip.cxx:391-392`, `ZInflate.c:1048-1090`). In Python
the whole codec is `zlib.decompressobj(-zlib.MAX_WBITS)`, and all 468 compressed
records of `pippa.root` decompress with it. The lesson is the cheaper one: a
claim in the document — "rare but readable" — had sat unverified long enough that
its cost was assumed rather than measured.

**The one open failure.** `aod_flushed.root` (ROOT 5.25/04) fails
`StreamerDriven 10.1` on its `TTreePerfStats` record: the `kBase` element for
`TVirtualPerfStats` contributes a bare `TObject`, ten bytes, with **no version
word of its own**. The rule behind it is understood and written up
(`StreamerDriven.md` §4.5): a version-0 class selected with a plain
`#pragma link` gets a forwarding-only `Streamer`. It is not derivable from the
file, which is why clearing this failure means publishing the class list — M2.

### 9.10 What the corpora already contain — measured 2026-09-17

The census that reframes §9.1 and §3.5. Taken over all 226 corpus files by
walking every `StreamerInfo` record and every directory record.

**Directory record versions**: 5 (339), 1 (24), 4 (5), 3 (2), 1001 (2 — the large
form). Version 2 does not occur. §9.1 had this as "needs a legacy ROOT".

**`TStreamerInfo` record versions**: 9 (3408), 8 (1498), 6 (407), 2 (149),
5 (75), 4 (64), 10 (19 — ROOT 6.36 and later). **695 infos below version 8**,
which is the threshold the collection layouts turn on.

**`TStreamerElement` base versions**: 4 (31186) and **2 (979)**. Version 3, the
form that persists `fXmin`/`fXmax`/`fFactor`, does not occur.

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

The histogram, graph and profile rows cost nothing — those classes are
streamer-info driven at every version present (`03-classes/index.md`). The
`TBranch`, `TFormula`/`TF1` and `TPad` rows are the ones that carry hand-written
legacy layouts, and they are M6 and §9.1.

**Forwarding-only base classes** (M2): of the 540 classes in the submodule with
`ClassDef` version `≤ 0` and a plain `#pragma link`, exactly **two** appear as a
`kBase` element anywhere in the corpora — `TSeqCollection` (348) and
`TVirtualPerfStats` (1). 117 distinct base-class names occur in total.
