# PLAN — ROOT I/O Specification

**Status: the reading side is specified end to end for files written by ROOT 4
and later, and 0.1.0 is released.** The container, the object layer, the divergent
classes and the whole `TTree` reading path are written, cited against the pinned
submodule and checked against bytes; RNTuple tracks ROOT's own specification plus
ten errata. The live work is **write support** — §2.9 and §8.4 — which extends the
project past the reading side it was scoped to.

Measured, 2026-09-18, by the checks in `tools/`:

| | |
|---|---|
| Specification documents | 41, plus the tracked RNTuple copy |
| Reference files / byte assertions | 71 / 1753, 0 failures |
| Source citations checked | 1149, 0 failures |
| Class versions checked against `ClassDef` | 25 |
| Invariants over the fixtures | 71 files, 0 failures |
| Invariants over both corpora | 226 files, ROOT 2.24/00 – 6.36/02, **0 failures** |
| Entries decoded and checked | 27969 of 28036 branch-baskets, 99.8% |

Throughout: **✅ done**, **◐ partly done**, **☐ not started**. §9 is the gap
register — every gap the written documents record, so they can be picked up
rather than rediscovered. The blow-by-blow of how each was found is in the git
log, not here; this document keeps only what is still live plus the measurements
the scope decisions rest on.

## 1. Goal

Produce a complete, versioned, machine-checkable specification of the ROOT
on-disk formats, sufficient for a third party to implement a reader **without
reading ROOT's C++ source**.

Reading is specified normatively for every layer. **Writing is specified two
ways** (decision 3, revised 2026-09-18): every layer states the invariants a
conforming file satisfies whatever wrote it, and `spec/06-writing/` gives
end-to-end *procedures* for producing one — the container, an object and its
streamer info, a histogram, and a flat `TTree` — at the current version of each
class only. Free-space reuse, basket sizing and key ordering stay unspecified:
they are ROOT's policy, not a requirement of the format. See §2.8 and §2.9.

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
├── README.md, PLAN.md, CLAUDE.md
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

`spec/` is split by **layer**, not by class, because ROOT's format is layered and
almost every class is described by the container plus the serialization layer plus
a `TStreamerInfo` read out of the file itself. Only the divergent classes need
hand-written text, and structuring the repo this way makes the *size of the
hand-written surface* explicit — the thing third-party implementers currently
have to discover the hard way.

`LICENSE`, `LICENSES/`, `CONTRIBUTING.md`, `CITATION.cff` and `CHANGELOG.md` are
in place as of 0.1.0 (§8 item M7).

### 2.1 `spec/00-conventions.md` ✅

RFC 2119 keywords; endianness (**TFile/TBuffer is big-endian; RNTuple payload is
little-endian** — the same file contains both); the primitive type table
including `Long_t` at **8 bytes on disk even where it is 4 in memory**; the four
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
| `delegating` | 32 | nothing — `ReadClassBuffer` with no version test and no reads after it |
| `guarded` | 89 | nothing for a current file: `ReadClassBuffer` above a version threshold, a legacy layout below. Those legacy layouts are §9.1 |
| `extending` | 3 | know the bytes that follow the streamer-info-driven ones, at every version — `TMatrixTSym`, `TPointSet3D`, `ROOT::RNTuple` |
| `custom` | 63 | know the layout; the streamer info describes the bytes at no version |

Of the 66 `custom` and `extending` — the two kinds a reader must know —
**36 specified**, 5 never objects in a file, 15 outside scope (RooFit, EVE,
SOFIE, the SQL backend), **10 gaps**: `TASImage`, `TClassTree`, `TMaterial`,
`TMixture`, `TPolyLine3D`, `TPolyMarker3D`, `TPointSet3D` and the three
`graf2d/gviz` wrappers. All of narrow reach; none is something a physics file is
likely to hold, and they are **not** in the MVP (§8).

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

`Double32.md` was dropped as already-written and distributed: the grammar and the
three encodings are `ElementTypes.md` §5.1–5.3, the leaf classes and the
3-versus-4-byte asymmetry are `TLeaf.md` §7.

The sub-plan that ordered this layer is discharged and deleted; §9.11 keeps its
residue — the corpus census it was written against, what the decoder still
cannot reach, and the questions it left open.

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
| ✅ `ForwardingStreamers.md` | The other half of the same question, from the same tool: the classes whose *generated* `Streamer` writes only their bases |
| ✅ `ReaderChecklist.md` | The whole specification as a work order: eight milestones, each with its documents, fixtures and checks |
| ✅ `Pitfalls.md` | Forty-five things that are true, unobvious and have cost somebody time, each linked to the section that specifies it |
| ✅ `Bibliography.md` | ROOT's own documentation and what each part of it is good for, the five other readers, and the two corpora |
| ☐ `WriterInvariants.md` | The collected index of §2.8, now with a second audience: §2.9's procedures state what a writer must *do*, and this is the list of what its output must *satisfy*. `tools/check_invariants.py` is already the executable form. §8.4 item M15 |

### 2.8 Write support, part one: invariants ✅

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

Invariants alone turned out to be **necessary and not sufficient**. They let a
writer check a file it has already produced; they do not tell it which bytes to
emit, and a reader-shaped document leaves a writer to infer the order of
operations — which is where ROOT's own writing code has rules that no file
records. §2.9 is the other half.

### 2.9 `spec/06-writing/` — write support, part two: procedures ◐

Added 2026-09-18, extending decision 3. The reading documents answer "what do
these bytes mean"; these answer "which bytes do I emit, in what order". Scoped by
what a writer actually needs rather than by symmetry with the reading side:

| File | State |
|---|---|
| ☐ `index.md` | What a writing procedure is here, the conformance test, and what is deliberately not specified |
| ☐ `WritingFiles.md` | The container in write order: the header, the root directory record, a key, the key list, the free list, and the end-of-file rewrite |
| ☐ `WritingObjects.md` | Framing an object, the version word, and the `StreamerInfo` record — including when a writer may omit it and what that costs |
| ☐ `WritingHistograms.md` | `TH1F`/`TH1D`/`TH2F`/`TProfile` at the current class version, member by member |
| ☐ `WritingTrees.md` | A `TTree` of flat branches at the current class version: the tree record, branches, leaves, baskets, and the fields that must agree with one another |

**Only the current version of each class.** A writer chooses what it emits, so
there is never a reason to write an old layout; the legacy layouts stay on the
reading side, where files force them.

**The conformance test is executable, and it is what makes these documents
checkable the way the reading side is.** `tools/rootwrite.py` is a pure-Python
writer built from these documents alone, and `tools/check_write.py` puts every
file it produces through three gates:

1. `rootfile.py` reads it and every applicable `Invariants` section holds — the
   two independent implementations meeting in the middle, which is the same
   discipline as §3.1 with the arrow reversed;
2. the bytes are reproduced **exactly**. A writer that fixes its own clock and
   UUID has no reason not to be deterministic, so `data/written/` carries a plain
   `sha256` and §3.3's normalization does not apply to it;
3. where ROOT is on `PATH`, ROOT opens the file, returns the values that went in,
   and prints **no warning**. This is the gate that finds errors, and the reason
   the layer is worth writing at all: a wrong streamer info or a wrong class
   version makes ROOT complain rather than fail silently.

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
| Container | ✅ all six documents |
| Serialization | ✅ all seven documents |
| Standard classes | ✅ the divergent set, bar ten narrow classes (§2.4) |
| `TTree` | ✅ records, branches, leaves, baskets, splitting, reading an entry — unsplit and split |
| RNTuple | ◐ upstream tracked, envelopes and the type mapping audited, ten errata; one form left (collection proxy) |
| Appendix | ✅ seven of eight; only `WriterInvariants.md` is left, and it is not MVP (§2.7) |
| Legacy reading (pre-ROOT 6) | ◐ `TBranch` 6–9 specified and read (M6); the rest specified where cited, unchecked where no file was available — §9.1, §9.10 |
| Release plumbing (licence, citation, version) | ✅ 0.1.0, §8 item M7 |
| Writing (`spec/06-writing/`) | ◐ scoped 2026-09-18, decision 3 revised; the work is §8.4 |

The phase numbering the earlier drafts used (0 skeleton, 1 foundations, 2 object
layer, 3 bootstrap classes, 4 standard classes, 5 `TTree`, 6 RNTuple, 7 legacy)
is retired: phases 0–3 and 5 are complete, 4 is complete bar the ten narrow
classes, and what is left of 6 and 7 is listed in §8 by value rather than by
phase.

## 6. Decisions

| # | Question | Decision |
|---|---|---|
| 1 | Scope of "every standard class" | **Revised 2026-09-17.** Not generated tables for ~440 classes: specify the classes whose streamer info does not describe their bytes, and let the generic algorithm cover the rest. The set comes from `inventory.py`, not from an estimate (§2.4) |
| 2 | Normative status | Descriptive of 6.40.04; the pinned submodule is the tiebreaker; errata for suspected ROOT bugs |
| 3 | Write support | **Revised 2026-09-18.** Reading normative. Writing gets both halves: per-layer invariants, which validate a file whatever wrote it (§2.8), and end-to-end **procedures** in `spec/06-writing/` for producing one — container, object, histogram, flat `TTree` — at the **current class version only**, with `tools/rootwrite.py` as the executable form and "ROOT reads it back and says nothing" as the conformance test (§2.9). Still unspecified: free-space reuse, updating an existing file, basket sizing, key ordering |
| 4 | Upstream relationship | Standalone repo, not blocking on review. RNTuple errata go upstream as PRs; open a conversation with the ROOT I/O team about eventually replacing `io/doc/TFile/` |
| 5 | Fixture distribution | Core corpus committed (<10 MB). Legacy-ROOT and >2 GB cases as release artifacts with a committed manifest — superseded in practice by the two corpora (§3.4, §3.5) |
| 6 | Where a divergent class is specified | **Cross-reference, do not re-home.** A class stays in the layer document where its behaviour arises; `03-classes/index.md` maps every divergent class to wherever that is. `TObject` belongs with buffer framing, `TList`/`TObjArray` with streamer information, `TClonesArray` with collections, `TRef` with references, `TStringLong` with the string encodings |
| 7 | **Version floor** (✅ stated 2026-09-17, `spec/index.md` §Scope) | The specification claims **reading** for files written by ROOT 4.00 and later, and M4 measured that it works back to **3.04/02**. The floor is not a release number but a property of the file: object decoding needs streamer infos, and a file old enough carries none. Exactly one corpus file is in that state — `pippa.root`, ROOT 2.24/00 — and for it the container layer applies alone: all 517 records are located, none of the 468 objects is decodable (§9.10) |
| 8 | **What is out of scope** (✅ stated 2026-09-17, `spec/index.md` §Scope) | Four groups: the frameworks inside ROOT that define their own persistent classes (RooFit, the SQL backend, PROOF, both event displays, SOFIE — 15 classes in `streamers.toml`, each with its reason); what `TGeo*` fields *mean*, its classes being streamer-info driven anyway; the compression algorithms themselves, as against ROOT's framing of them; and, on the write side, what decision 3 leaves out after its 2026-09-18 revision — earlier class versions, updating an existing file, writing a split `TBranchElement`, and ROOT's policy choices. GUI classes are not on this list after all — they are version 0 and forwarding-only, so `ForwardingStreamers.md` covers them |

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
5. **`TTree` sub-plan** — discharged, and its residue is §9.11.

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
7. **An object of an `extending` class cannot be skipped by its byte count.**
   `TBufferFile::SkipObjectAny` seeks to `start + count + 4`
   (`root/io/io/src/TBufferFile.cxx:2499-2503`), and for `TMatrixTSym`,
   `TPointSet3D` and `ROOT::RNTuple` the object continues past that point
   (`Matrix.md` §2.4, `Buffer.md` §2.4). A pointer member is safe, because the
   slot's own byte count covers the extra bytes; a **by-value** member is not.
   Reachable only when a schema change makes ROOT skip such a member, which is
   why this is source-verified and **not** demonstrated by a file. Verify before
   reporting.
8. **A `pair<K,V>`'s checksum can be computed before its members are known**, and
   `TClass::GetCheckSum` then caches it forever
   (`root/core/meta/src/TClass.cxx:6655-6666`), so several distinct pairs share
   one value. `data/serialization/pairs.root` has three pairs all carrying
   `0x0b5fb752`. Not data loss for ROOT, which resolves the value class by
   declared type name — but a hazard for every other reader, since the obvious
   checksum-to-info table decodes two of those three as the wrong type.
   `Collections.md` §8.2.
9. **`fBranchCount` can name another object's counter branch, and ROOT then
   loses the data silently.** The writer builds the counter's name from the
   branch's own name and looks it up with `TTree::GetBranch`
   (`root/tree/tree/src/TBranchElement.cxx:432-438`), which searches the **whole
   tree** and returns the first match. A tree holding two split objects of one
   class whose sub-branches carry no parent prefix therefore records the *first*
   object's counter on both, and the read path uses it as it stands (`:4649`).
   **Byte-verified, and the strongest candidate on this list**: in
   `alice_ESDs.root` (ROOT 5.34, published by the ROOT team) `PrimaryVertex`'s
   `fIndices` points at `SPDVertex`'s `fNIndices`, which is 0 for all 20 entries,
   while its own entries are 37, 45, 13 and 27 bytes — `1 + n × 2` for counts of
   18, 22, 6 and 13. ROOT reads no indices at all and reports nothing. The bytes
   are intact; only the pointer is wrong. `ReadingEntries.md` §4.1 and erratum 6.
10. **Writing a `std::map` field to an RNTuple aborts from the interpreter.**
    `Fill()` reaches `R__ASSERT(0)` in `TGenCollectionProxy__VectorNext`, a
    function whose comment is "Should not be used"
    (`root/io/io/src/TGenCollectionProxy.cxx:1528-1530`), with the field empty and
    never touched; assigning to it first segfaults earlier still. The model and the
    writer are built without complaint. Reproducer in
    `spec/05-rntuple/NOTES.md` §5. **Report with the caveat attached**: only the
    interpreted path was tested, because ACLiC cannot compile on this machine
    (`CLAUDE.md`), so a compiled comparison is the first thing to ask for.

## 8. MVP — what "done enough to publish" means, and the work to get there

The specification is already more complete than anything else available, and the
checks behind it are sound. What stops it being a book a third party can adopt is
a small, nameable set of things: one published claim that is **wrong**, three
missing on-ramp documents, an unstated scope, and no licence.

### 8.1 Release criteria

**All six are met as of 2026-09-17, and 0.1.0 is tagged.** What each one was, and
what satisfied it:

1. **No published claim is known to be wrong.** ✅ as of M1; the `delegating`
   claim was the violation, and M6 found four more in the `TBranch` and `TLeaf`
   invariants. Criterion 1 is not a state a project reaches once — it is what the
   two corpora keep testing.
2. **Scope is stated**: which ROOT releases the spec covers for reading, and what
   is deliberately out of scope (decisions 7 and 8). ✅ M4, as `spec/index.md`
   §Scope.
3. **A reader can find the path in**: an ordered implementation checklist and a
   pitfalls page, both linking into the normative text. ✅ M3.
4. **Zero unexplained failures over both corpora.** ✅ as of M2: the last one,
   `aod_flushed.root`, is cleared.
5. **Citable and reusable**: a licence for `spec/` and for `tools/`+`gen/`, a
   `CITATION.cff`, a version number, a changelog, a tagged release, and a
   published site. ✅ M7.
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
the streamer info describes". For three of the 35 that was false — the read
branch consumes **more bytes** after `ReadClassBuffer`, and in all three cases
outside the byte count, so `CheckByteCount` succeeds for a reader that stops
early:

| Class | What follows `ReadClassBuffer` | Cite |
|---|---|---|
| `TMatrixTSym<Element>` | the upper-right triangle, `fNcols-i` elements per row; the lower triangle is reconstructed, not read | `root/math/matrix/src/TMatrixTSym.cxx:2040` |
| `TPointSet3D` | when `fOwnIds` is set, an `Int_t` and then that many object references | `root/graf3d/g3d/src/TPointSet3D.cxx:156` |
| `ROOT::RNTuple` | an 8-byte XXH3-64 checksum | `root/tree/ntuple/src/RNTuple.cxx:25-49` |

`tools/inventory.py` now has a fourth kind, `extending`, detected by looking for
buffer I/O after the call in the same block and before any `return`, `break` or
`case` label; `custom` and `extending` are the two kinds the sidecar must
resolve. Three further things came out of building it, each a bug in the tool
rather than in ROOT:

- **A qualified out-of-line definition was invisible.** `DEFINITION` matched only
  an unqualified name, so `void ROOT::RNTuple::Streamer` and
  `void RooWorkspace::CodeRepo::Streamer`
  (`root/roofit/roofitcore/src/RooWorkspace.cxx:2427`) were not in the inventory
  at all — and the first is an `extending` class, so the omission was in the
  direction of "nothing to do". The count went 185 → 187.
- **A version dispatch need not be a comparison.** `RooBinning` switches on the
  version word and hand-decodes version 1 in a `case`
  (`root/roofit/roofitcore/src/RooBinning.cxx:298`). Tested for comparisons alone
  it read as `delegating`; it is `guarded`. It was also the one false positive of
  the extending detector, which is why the window stops at `break` and `case`.
- **No `guarded` class reads past `ReadClassBuffer`**, so that table's "nothing
  for a current file" stands. Checked over all 89, and pinned by a test.

Specified as `spec/03-classes/Matrix.md`, with `classes/matrix` (48 assertions:
a 3 × 3 `TMatrixDSym`, a 2 × 2 `TMatrixFSym` for the element width, an ordinary
`TMatrixD` and `TVectorD`, and a `TMatrixDSym` inside a `TObjArray` so both byte
counts are visible), seven invariants in `check_invariants.py`, and a reader in
`rootfile.py`. Three findings worth more than the fixture:

- **A `TMatrixTSym` has no streamer info of its own in any file.** Its `Streamer`
  hands `ReadClassBuffer` the `TClass` of `TMatrixTBase<Element>`, and recording
  an info is a side effect of `WriteClassBuffer`, so what the file carries is the
  base's info and the version word on disk is the base's class version, 5.
  `TMatrixTSym`'s own `ClassDef` version 2 never reaches a file. Confirmed over
  both corpora: **no file has such an info**, and five files carry
  `TMatrixTBase<double>`.
- **A byte count is a lower bound, not a length.** Now
  `Buffer.md` §2.4, with invariant 9.9 carrying the exception explicitly rather
  than the checker carrying it silently.
- **`uproot-issue-359.root` was the witness all along**: five `TMatrixTSym<double>`
  records written by ROOT 5.34/34, at 29 × 29 and 58 × 58, each reported as
  "consumed 48 of 3528" — which is exactly the framed prefix. They now decode,
  and the foreign corpus is at 0 failures with one more branch-basket reached.

**M2 — ✅ done 2026-09-17. The list a reader cannot derive from a file is
published.**
*It clears the last failure over either corpus and hands over the one piece of
out-of-band knowledge the format requires.*

For a class whose `ClassDef` version is `≤ 0` **and** which was selected with a
plain `#pragma link C++ class X;`, `rootcling` generates a `Streamer` that calls
each base's `Streamer` and **nothing else** — no version word, no byte count, no
members (`root/core/dictgen/src/rootcling_impl.cxx:1332-1367`, chosen at
`root/core/clingutils/src/TClingUtils.cxx:3016`). Both generators write a
streamer info and both record class version 0, so nothing in a file
distinguishes them.

`tools/inventory.py` now extracts that set too — the same tool, a second
CI-checked document, [`spec/99-appendix/ForwardingStreamers.md`](spec/99-appendix/ForwardingStreamers.md):
**534 classes across 46 modules**, listed by module because the shape of the set
is part of the answer. It also cross-checks the two lists against each other: a
class cannot both supply a `Streamer` and have one generated for it, and an
overlap fails `--check`.

What the measurement changed about the plan's own expectations:

- **The set is not only GUI classes.** ROOT's *pure-subclass containers* are in
  it — `THashList`, `TSortedList`, `TOrdCollection`, `THashTable`, `TPair`,
  `TSeqCollection` — version 0 precisely because they add no persistent state to
  their base. "Writes only its bases" is the design, not an accident.
- **Three of the 534 occur in the corpora**, not the two this plan predicted:
  `TSeqCollection` (a `kBase` of `TList` and `TObjArray`, 240 files),
  `THashList` (the type of `TAxis::fLabels` and `TGeoManager::fHashPNE`, so any
  labelled axis writes one, 38 files) and `TVirtualPerfStats` (1). No record in
  either corpus has one as its class.
- **The streamer info is not fiction here, only unframed.**
  `TStreamerInfo::Build` skips every data member of a version-0 class
  (`root/io/io/src/TStreamerInfo.cxx:552-554`), so a modern info lists exactly
  the bases the streamer writes. Two ROOT 4.00/00 files show the older
  behaviour, listing `TSeqCollection::fSorted` — a member no forwarding streamer
  has ever written.

`rootfile.py` carries the three and reads them by the published procedure, which
makes `aod_flushed.root`'s `TTreePerfStats` decode: its `TVirtualPerfStats` base
is ten bytes, a bare `TObject`, and `fReadaheadSize` lands on 256000 exactly
where §9.9's byte count said it would. **Both corpora are now at 0 failures.**

**M3 — ✅ done 2026-09-17. The on-ramp.**
*The difference between a correct specification and a usable one, and all three
pages are collation rather than research.*

- ✅ [`ReaderChecklist.md`](spec/99-appendix/ReaderChecklist.md) — the whole
  specification as a work order. Eight milestones, each one a state in which
  something works: list a file's contents, decompress, read the streamer infos,
  decode an arbitrary object, then the classes the info gets wrong, an unsplit
  tree, a split tree, the rest. Each names its documents, its fixtures and the
  checks worth running there, and it ends with two sections the layer documents
  cannot carry — how to know you are right, and what can be left out.
- ✅ [`Pitfalls.md`](spec/99-appendix/Pitfalls.md) — **forty-five** of them, in
  six groups, each a sentence or two and a link to the section that specifies it.
  Two are ROOT's bugs rather than a reader's and are labelled as such.
- ✅ [`Bibliography.md`](spec/99-appendix/Bibliography.md) — ROOT's own
  documentation with what each part is good *for* (the RNTuple spec is real; the
  TFile docs are a source of questions; the reference guide tells you what a
  member means and nothing about how it is written), the five other readers built
  without a specification, and the two corpora.

`spec/index.md` now opens with the checklist, since "I am here to implement
something" is the common case, and two stale claims on that page went with it.

**M4 — ✅ done 2026-09-17. The scope is stated, and the front pages say what is
true.**
*A reader could not tell whether a gap was unknown or deliberate, and the README
still described the repository as it was at 29 fixtures.*

`spec/index.md` gained a **Scope** section: descriptive status, reading against
writing, how far back it reads, what is missing rather than excluded, and the
four out-of-scope groups. Writing it meant measuring the floor rather than
asserting it, and the measurement moved decision 7:

- **The floor is a property of the file, not a release number.** Object decoding
  needs streamer infos. `pippa.root` (2.24/00) carries none — all 517 of its
  records are located and framed, and not one of its 468 histograms is
  decodable — but `mlpHiggs.root` (3.04/02) and `H1display.root` (3.05/07)
  **do** carry them and do decode. Decision 7's "older files carry no streamer
  infos at all" was true of one file and wrong as a rule; the claim is now
  "specified for 4.00 and later, works in practice back to 3.04/02".
- **`TBranch` is the only class in 226 files below a hand-written threshold.**
  Every version of `TH1`, `TGraph`, `TFormula`, `TF1`, `TAxis`, `TTree` and
  `TLeafObject` that occurs anywhere in either corpus is above the version at
  which that class becomes streamer-info driven. That is what makes §9.1's
  legacy branches a low priority rather than a hole, and it is now said out loud
  on the front page.
- **Of the ten `gap` classes, exactly one occurs in either corpus**: `TASImage`,
  8 records in `galaxy.root` and `gallery.root`. The other nine are named but
  unwitnessed.
- **GUI classes are not an out-of-scope group.** Decision 8 listed them; the M2
  extraction shows why it did not need to — `gui/gui` alone contributes 197
  classes to `ForwardingStreamers.md`, and no `TG*` class has a hand-written
  `Streamer` at all. The four groups that remain are the frameworks with their
  own persistent classes, `TGeo*` semantics, the compression algorithms as
  against ROOT's framing of them, and writing.

The blocked-record census behind the new table, over both corpora — 31 628
records, **94% decoded**: 468 no-streamer-info (the floor), 216 RooFit (out of
scope), 137 an LZ4 payload with no `lz4` package here, 50 `TBranch` 7/8/9,
8 `TASImage`, and a tail of single records. Two of those six are the project's,
and both are named on the front page.

`README.md` was rewritten around the same numbers: 65 fixtures, 1563 assertions,
1111 citations across 39 documents, 226 corpus files at 0 failures, and the
reader's checklist as the first link rather than the last.

*Also corrected while checking M6's own claim*: directory record versions 1, 3
and 4 are **not** blocked — `rootfile.py` reads all 31, and `pippa.root`'s 24
version-1 records (no UUID at all) walk clean. What they lack is a fixture. The
one directory form nothing exercises is version 2, which occurs in neither
corpus, and it is the one where ROOT's own reader is suspect (`Directory.md`
§7).

**M5 — ✅ done 2026-09-17. `LargeFiles.md`.**
*The one layout in the container layer that no fixture can reach, and the last
document §2.2 was missing.*

[`spec/01-container/LargeFiles.md`](spec/01-container/LargeFiles.md): the five
switches and their conditions, wide diagrams for the header, the key and the
`TFree` entry, one 5.25 GB file walked byte by byte, and six invariants. Writing
it against real bytes rather than against the source alone found two things the
specification had wrong or missing, both about *which* condition widens *what*:

- **A key's width is not decided by the key's own offset**, which is what
  `Directory.md` §3 said. Every writing constructor calls `TKey::Build` with
  `filepos == -1` and `Build` substitutes the file's current `fEND`
  (`root/io/io/src/TKey.cxx:456`), so a key written into a reused gap near the
  front of a large file is **wide with a small offset in it**. `volume.root` has
  exactly that: `fVersion` 1004 at offset 105 159 358, while the key at `fBEGIN`
  in the same 5.25 GB file is `fVersion` 4 and narrow. A non-zero `fPidOffset`
  is the second, size-independent trigger.
- **The directory record has two writers with different conditions.**
  `FillBuffer` widens on the three offsets it is about to write
  (`root/io/io/src/TDirectoryFile.cxx:751-759`); `TDirectoryFile::Streamer`
  widens on `fEND` (`:1827`). Only the first produces the on-disk record — the
  root directory record of that same 5.25 GB file is version **5**, narrow —
  which is why the mismatch matters to a writer and not to a reader.

Two more things fell out of reading real bytes:

- **`Directory.md` §6.1's uninitialised slack is now witnessed, not just
  cited.** The key list of `volume.root` has `fObjlen` 65 for a count and one
  53-byte image, and the eight bytes past them read `00 04 00 62 00 04 00 62` —
  heap, and heap that looks like the start of a key. A length-driven parse takes
  it as a second entry.
- **The boundary from below is the strictly-greater-than test.** The trailing
  free entry's `fLast` is the next whole multiple of 1 000 000 000 above `fEND`,
  so a 1.997 GB file's sentinel is exactly 2 000 000 000 — not *greater than*
  the threshold, so that file has no wide entry anywhere.

The six invariants are checked by `tools/fetch_cern.py --headers`, which now
carries them as a pure function over its parsed reading, and each is shown to
catch a violation by `tools/test_large_files.py` — twelve mutation tests, since
`check_invariants.py` has no file large enough to corrupt. `rootfile.py` gained
`parse_free_entries`, which keeps each entry's version word so invariant 4 can be
stated at all.

**M6 — ✅ done 2026-09-17. The legacy layouts the corpora already contain.**
*The largest remaining in-scope blocked category over files ROOT wrote, and it
turned out to be half specification and half an overstated coverage number.*

`TBranch.md` gained §13.1, the member order below class version 10, and
`rootfile.py` reads it. The three reproducers all decode: `mlpHiggs.root`
(ROOT 3.04/02, version 7), `uproot-from-geant4.root` (4.00/00, version 8) and
`stock.root` (4.00/07, version 9) — 116 legacy branches, each parse ending exactly
on its byte count, and 17 tree records that had been `PARTIAL` since the corpora
were added. `coverage_probe.py` no longer names `TBranch` anywhere, which leaves
**`TASImage` as the only specification gap either corpus hits**.

What the legacy layout actually is, because it is not what the version table
suggested: `fEntries`, `fTotBytes` and `fZipBytes` are `Stat_t`, a **double**;
`fEntryNumber` and every element of `fBasketEntry` are 4 bytes; and the three
counted pointers are read in full, `fMaxBaskets` values each, whatever their flag
byte says. And the surprise:

- **The recorded streamer info is right, element for element, on all 116.** The
  hand-coded order and the info's order agree at versions 7, 8 and 9. The legacy
  layout was not missing from the files at all — what is missing is any way to
  *know* that without checking, which is why `rootfile.py` reads the order from
  the source and verifies the byte count rather than trusting the info. The one
  member where they disagree is `fBasketSeek` at version 9 (§13.3), which is
  exactly where a reader would most want to trust it.
- **No file in either corpus carries the flag byte 2** that makes `fBasketSeek`
  8 bytes wide. All 116 write 1. The width selector is specified from the source
  and unwitnessed; it needs a version-9 file with baskets past 2 GB.

Reading 116 branches nobody had read before broke four invariants, and each one
was the invariant's fault rather than the files':

| Invariant | Was | Is, and the witness |
|---|---|---|
| `TBranch` 11.1 | `fMaxBaskets == max(fWriteBasket + 1, 10)` | `>=`, with equality from class version 8 on — 12 125 branches. At version 7 the writer allocated a flat **1000**: `mlpHiggs.root`, 12 003 bytes of arrays per branch |
| `TBranch` 11.3 | with an embedded basket, `fBasketEntry[fWriteBasket]` is **below** `fEntryNumber` | **at most**: an embedded basket may be empty, 92 branches in three files |
| `TBranch` 11.9 | `fBaskets` holds `fWriteBasket + 1` slots | the slot count is not fixed by `fWriteBasket` — a ROOT 4.00-era writer wrote `fMaxBaskets` slots (22 branches), `alice_ESDs.root` writes one *more* than `fWriteBasket + 1` and ROOT never reads it, and a trimmed trailing null makes it fewer |
| `TLeaf` 10.6 | a branch whose leaves are all fixed-size has no entry-offset array | only when its `fEntryOffsetLen` is 0. `uproot-issue-250.root` (ROOT 4.00) leaves it at the default 1000 on a `TLeafD` branch and its baskets carry offsets 8 bytes apart |

**And then the coverage number.** The four invariants above were reachable only
because refusing version 10 had also refused `alice_ESDs.root`, a ROOT 5.34 file
whose baskets are all embedded. Chasing that turned up something bigger: neither
entry check had ever looked at an **embedded** basket. The leaf-driven check
iterated the baskets *below* `fWriteBasket` and an embedded one sits *at* it, so
1266 branch-baskets were in neither the numerator nor the denominator of the
`ENTRIES` line. The published **99.7%** was measuring the wrong denominator.

Both halves are fixed: `check_invariants.py` now checks the embedded basket for
`TLeaf` 10.7, and `leaf_counts` reads an embedded **counter** basket out of the
`TTree` payload — which closes the four `ttree/branch-clones` skips that §8.3
called the one merely-unimplemented skip in the suite. The honest figures:

| | Before M6 | After |
|---|---|---|
| Fixtures | 85 of 91, with 5 plumbing skips | **94 of 96**, and neither remaining skip is plumbing |
| Both corpora | 25937 of 26011 (99.7%), embedded baskets invisible | **26948 of 27949 (96.4%)**, 0 failures |

The 1001 skips that remain are 920 embedded baskets that `TreeReader` cannot
fetch (M8, now the largest single item in the project), 48 collections whose value
class has no streamer info in the file, 18 hand-written streamers and 15 baskets
that could not be read here. Two of those four are plumbing and two are things no
reader could decode.

*Left from M6's original scope*: `TStreamerElement` at base version 2 and
`TStreamerInfo` record versions 2/4/5/6 are read and produce 0 failures, but
`StreamerInfo.md` still describes their shape only in passing; and the directory
record versions want a fixture rather than a reader (M4).

**M7 — ✅ done 2026-09-17. Release plumbing, and version 0.1.0.**
*Without it the reference files cannot legally be vendored as test vectors, which
is the main way a third party would use this.*

- **`LICENSE`** — CC-BY-4.0 for `spec/` and the prose, BSD-3-Clause for `tools/`,
  `gen/` and `data/`, with the full texts in `LICENSES/`. The BSD half is the
  point: a closed-source reader can vendor a fixture and its `case.toml` without
  asking. Two things the file has to say that §2 had not: the `root/` submodule is
  ROOT's under LGPL-2.1-or-later and is not content of this repository, and
  `spec/05-rntuple/BinaryFormatSpecification.md` is **not ours to licence** — it
  is ROOT's document, tracked verbatim, which is also why corrections to it go in
  `ERRATA.md`. It ends with a non-affiliation notice: where this specification and
  ROOT disagree, ROOT is right, which is a licensing statement as much as a
  technical one.
- **`CONTRIBUTING.md`** — the two-witness rule first, then the mechanics: adding
  a case, the `case.toml` format, the two traps (repo-relative output paths; that
  fixtures cannot be byte-reproducible and `--accept` is the only way to re-record
  a digest), the libc++/libstdc++ container loop for a cross-platform `DRIFT`, how
  to write a document, and what the two corpora mean — `gen/cern/` is evidence,
  `gen/foreign/` is a lead. It says out loud that **a correction is more welcome
  than an addition and needs no fixture**, which nothing in the repository had
  said.
- **`CITATION.cff`**, **`CHANGELOG.md`**, and the version in three places that
  cannot drift silently: `[project.extra]` in `zensical.toml`, the front page, and
  the citation file.
- **Pages already serves the current build** — `LargeFiles/` and
  `ReaderChecklist/`, both published today, answer 200 at
  <https://ariostas.github.io/root-io-spec/>. No deploy work was needed.

*One thing this nearly got wrong, worth remembering about `zensical.toml`*: TOML
tables are positional, so inserting `[project.extra]` above `nav` silently moved
`nav` **into** it. The strict build reported "No issues found" and quietly built an
auto-generated navigation. A config table has to go after every key of the table
it follows, and the check that catches it is grepping the built HTML for a nav
entry, not the build's own exit code.

### 8.3 Next tier, after the MVP

**M8 — ✅ done 2026-09-17. `TreeReader` and the embedded basket.**
*The largest coverage item in the project, and it paid for itself twice over.*

`TreeReader` now takes the `TTree` record's payload and reads a basket that was
never written as a record: `basket_for` consults `Branch.embedded` when
`fBasketSeek[i]` is 0, and the raw block start plays the part the record offset
plays for a basket of its own — including as the decoder's buffer base, since ROOT
reads the block into the basket's own buffer rather than sharing the `TTree`
record's object map. `ReadingEntries.md` §1 now says a basket need not be a record.

**Both corpora: 27969 of 28036 branch-baskets, 99.8%, 0 failures**, up from
26948 of 27949. The remaining 67 skips are of two kinds and **neither is
unimplemented**: a collection whose value class has no streamer info in the file,
and a class whose `Streamer` is hand-written. Over `gen/cern/` it is 1696 of 1696,
**100%**.

Decoding those 920 baskets for the first time turned up two facts, both now
specified and both byte-witnessed in `alice_ESDs.root`:

- **A ROOT bug, and a data-loss one** — §7.1 item 9, the strongest candidate on
  that list. `fBranchCount` is set from a counter name looked up over the whole
  tree, so two split objects of one class both point at the *first* object's
  counter; ROOT reads 0 indices for a branch whose entries hold 18, 22, 6 and 13.
  The fix for a reader is to resolve the counter **among the branch's siblings**,
  which is `ReadingEntries.md` §4.1, and the entry's byte span is the cross-check
  that catches the difference.
- **A container's member needs one count per object** (`ReadingEntries.md` §4.2).
  For `fType` 31 or 41 whose element is itself `T *x; //[n]`, the entry is, per
  object, one flag byte then that object's values, and the per-object counts are a
  column in the sibling branch carrying `n`. `Tracks.fTPCClusterMap.fAllBits` is
  1848 bytes = 88 × (1 + 20), against 88 objects and 88 counts of 20. Nothing in
  the file points from the member to its counter — `fBranchCount` on an `fType` 31
  branch names the *master* branch — so §4.1's name rule is the only way in.

**M9 — ✅ done 2026-09-18. The RNTuple type mapping is audited.**
*The one part of the RNTuple document that cannot be read against the serializer —
only against a file of that type — so it advanced one fixture at a time, six of
them.*

| Fixture | Audits |
|---|---|
| `rntuple/fundamental-types` | the default column per C++ type, and the uncompressed rule |
| `rntuple/collections` | fourteen stdlib types: `vector`, `RVec`, `array`, `variant`, `pair`, `tuple`, `bitset`, `unique_ptr`, `optional`, `set`, `atomic`, `string`, nested collections, `Double32_t` |
| `rntuple/user-class` | a class, its base class as `:_0`, two enums, a `//!` member, the type version and checksum |
| `rntuple/projected` | projected fields, alias columns, `RNTupleCardinality` in both widths |
| `rntuple/untyped` | untyped collections and records — a role with an empty type name |
| `rntuple/streamed` | structural role 0x04, its `Index64` + `Byte` columns, and the extra type information record |
| `rntuple/soa` | flag 0x08, the last flag bit no fixture reached |

Each claim is checked by a test that **parses it out of the tracked copy** rather
than transcribing it, so neither the document on a submodule bump nor ROOT on a
default change can move silently. Four errata came out of it:

- **7** — `Double32_t` keeps `SplitReal32` in an **uncompressed** ntuple, where
  every other default drops to unsplit, because its override runs after the
  uncompressed adjustment and ignores it (`RFieldBase.cxx:892-915`).
- **8** — the field record's `Type Version` is a signed class version in an
  unsigned word, so a class with no `ClassDef` arrives as **0xFFFFFFFF**
  (`RFieldMeta.cxx:645`).
- **9** — the extra type information's **content is a length-prefixed string**,
  which the record's layout does not show (`RNTupleSerialize.cxx:389-391`): there
  are four bytes between the type name and the first byte of the `TList`.
- **10** — and that record is in the **footer's** schema extension, never in the
  header where the document introduces it, because the set of streamed classes is
  only known at commit (`RPageStorage.cxx:1290-1310`). A reader that looks where
  the document points finds nothing, on every file with a streamed field.

Three more facts that are ROOT's rules rather than the document's, each hit while
building a fixture: a **top-level** field of a streamer-mode class is refused
outright (`RFieldMeta.cxx:95`), so the streamed form exists only under a native
field; an **SoA class and its record must carry the same class version**
(`RFieldMeta.cxx:707`); and `std::map` **cannot be written at all** from the
interpreter (§7.1 item 10).

The prose sections are audited too, and did not need fixtures. *Limits* is
arithmetic over encodings this project had already checked. *Naming* is clean from
both sides — the validator's four characters plus control codes, and the writer
refusing an empty name, which the validator itself does not check. *Defaults*
matches `RNTupleWriteOptions`, with one omission worth knowing: the undocumented
`fInitialUnzippedPageSize` of 256 is why a small ntuple's first page is 256 bytes.
*Notes on Backward and Forward Compatibility* is reader requirements, and ROOT
keeps the only MUST — it refuses an unknown feature flag
(`RNTupleSerialize.cxx:1869-1877`).

`rootfile.py` grew what the audit needed: the two version words of a field record,
the **alias column list** and the **extra type information list**, neither of which
it had parsed before.

*What is left, and it is one row*: **classes with an associated collection proxy**.
The document says the associative half is not implemented in ROOT at all, and the
sequential half needs `TClass::SetCollectionProxy` with a `TCollectionProxyInfo`,
which is a compiled template instantiation rather than the runtime attribute that
made the streamed and SoA fixtures possible. `NOTES.md` §4 records it as the only
unaudited form.

**M10 — report upstream.** Ten RNTuple errata against a document the ROOT team
owns, plus §7.1's eleven bug candidates. Lead with §7.1 item 9 — `fBranchCount`
naming another object's counter branch, byte-witnessed in a file the ROOT team
published, and data loss — and with erratum 6, a column type the document
specifies, ROOT does not implement and JSROOT does, so two readers in one
repository disagree about the type set. Deferred to the end by standing decision,
and the natural opening for open item 1.

**Not in the MVP, deliberately**: the ten narrow `custom`/`extending` classes (§2.4);
`TGeo*` hand-review; `gen/legacy/`; the pre-ROOT-4 object layouts (decision 7);
semantic `case.toml` assertions; `TBranchSTL` entry decoding and `kStreamLoop`
values (§9.11). `WriterInvariants.md` is no longer on this list — it has become
§8.4 item M15, because there is now a writer to point it at.

### 8.4 Write support, added 2026-09-18

The MVP was a reading specification and it is out. This is the extension, and the
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
`tools/check_write.py` and `gen/written/objstring/` — 59 byte assertions, all three
gates green, wired into both CI jobs. What the write side needed that the reading
documents did not have:

- **The order of operations**, which is a property of no byte in the file. It also
  turns out ROOT has **two** orders and neither is canonical: `TFile::Close` writes
  the streamer infos, then the key lists, then the free list
  (`root/io/io/src/TFile.cxx:1000`, `:1019`, `:1024`), while `TFile::Write` puts the
  key lists first (`:2507-2510`). Both occur in ROOT-written files, and a reader
  cannot tell, because both records are found by absolute offset.
- **`fEND` is not the file's length**; it is the first byte of the last free
  segment, recomputed as `lastfree->GetFirst()` on every header write
  (`root/io/io/src/TFile.cxx:2671-2672`). Keeping the free list as the authority is
  what makes the two agree.
- **The free list's last entry is a sentinel.** ROOT ignores `nfree` and reads until
  an entry has `fLast > fEND` (`:801-808`), so a last entry that does not exceed
  `fEND` makes it parse past the record. It is read **only on a writable open**
  (`:769-775`), so a read-only test never exercises it — which is why `verify.C`
  copies the file, opens it `UPDATE`, and appends an object. ROOT's allocator then
  takes our free entry's `fFirst`, and if it were wrong the append would overwrite
  live data.
- **§13, what ROOT does not check**: ten container mistakes it reads silently,
  including a key image in the key list that disagrees with the record it points at,
  and `fObjlen` inconsistent with `fNbytes - fKeylen`, which *is* the compression
  flag since there is no other.

And one measured answer to the question the milestone was scoped around:
**ROOT needs no streamer info for a class it has compiled in.** A `TObjString` file
with `fSeekInfo = 0` reads correctly and silently, as does a ROOT-written `TH1F`
file with the two header fields zeroed. `tools/coverage_probe.py` cannot read
either — this project's reader is streamer-info driven, like every third-party
reader. The warning that would say so
(`root/io/io/src/TFile.cxx:928-941`) fires only when the file's `fVersion` differs
from the running ROOT's: the same file at 64004 is silent and at 63000 warns, both
verified. So the record is optional for ROOT, mandatory in practice, and M12 writes
it.

**M12 — ✅ done 2026-09-18. The object layer, and a `StreamerInfo` record that is
byte-identical to ROOT's.**
*The strongest check in the project: 370 bytes built from the document alone, equal
to ROOT's own.*

`WritingObjects.md` (354 lines), `written/streamerinfo` (23 assertions, a
compressed record and a compressed `StreamerInfo` record), `tools/test_write.py`
(12 tests), and in `rootwrite.py`: the object map, ZLIB blocks, the streamer-info
serializer and the checksum algorithm.

The byte comparison is what makes it evidence rather than an account.
`tools/test_write.py` builds the `StreamerInfo` record for `TObjString` from
`WritingObjects.md` §7 and asserts equality with the record in
`data/container/file-minimal.root` — class tags, `TList` option bytes,
`kIsCompiled` in `fBits`, the base checksum in `fMaxIndex[1]`, and a `fCheckSum`
computed from scratch. The last error before it matched is recorded in the document
rather than quietly fixed: **`fElements` is a `TObjArray *` and takes the pointer
slot form**, so a writer that emits the bare framed object is 18 bytes short.

Then the checksum, which turned into the substantive finding of the milestone.
`StreamerInfo.md` §11 had the algorithm; what it did not have is how far it can be
applied. Recomputing `fCheckSum` for **every streamer info in every reference
file** gives 614 of 653 exactly, and each of the 39 failures has a cause:

- **An enum folds an extra 1**, and an enum is recognisable: `TStreamerInfo::Build`
  stores every enum as an `Int_t` with `fType` 3 to keep the format stable
  (`root/io/io/src/TStreamerInfo.cxx:675-689`), but `fTypeName` keeps the enum's own
  name. **ROOT's checksum code uses exactly that test**, under a comment asking
  whether it can be done at all (`:3612-3620`) — so it is the rule, not a heuristic
  for a third party to invent. With it, `TH1` is reproduced exactly; new §11.1.
- **A version-0 class's info lists no members but its checksum folds them**
  (`:552-554`). `THashList`'s value is reproduced by adding `fTable`/`THashTable*`
  by hand.
- **A member ROOT rewrites for I/O keeps its declared spelling in the checksum.**
  `std::array<Int_t,3>` is recorded as a fixed C array of `int`; `std::unique_ptr<T>`
  as `T*`. `CollectionForms` is reproduced with `array<int,3>`, and `TF1` with
  `unique_ptr<TFormula,default_delete<TFormula> >` — default template argument
  spelled out, which is not guessable from the record.
- **Three `pair` instances where ROOT's own value is wrong**, which is §7.1 item 8
  arriving from a second direction: three distinct layouts all carrying
  `0x0b5fb752`, while the fourth pair in the same file is correct and recomputable.

`TPad` is the one mismatch with no explanation, and it is listed as such in the test
rather than left out of the count. All of this is new §11.2 of `StreamerInfo.md`,
which is a **reading**-side improvement that only the writing work would have found.

The milestone's other question is settled in `WritingFiles.md` §6.1 and the writer
emits the record.

**M13 — ✅ done 2026-09-18. Histograms, byte-identical to ROOT's.**
*Every object-bearing record in the written file equals the one ROOT wrote.*

`WritingHistograms.md` (298 lines), a new ROOT-written fixture
`classes/histogram` (73 assertions) and a written one `written/histogram` (35),
`TH1F`/`TH1D` in `rootwrite.py`, and the fifteen streamer infos the chain needs.

**The check is byte equality, three times over.** `data/classes/histogram.root`
and `data/written/histogram.root` hold the same two histograms, one written by
ROOT and one from the document alone, and the `TH1F` record (596 bytes), the
`TH1D` record (651) and the `StreamerInfo` record (9628 — fifteen infos, every
element, every checksum, ROOT's own ordering) are identical. The files differ only
in the directory record, the key timestamps, and the offsets that follow.

What that took, and what it exposed:

- **The statistics are not derivable from the bin contents**, which is the point
  of the document. `fEntries` counts fills, `fTsumwx`/`fTsumwx2` remember the
  true x of each one, and `fTsumw2` is Σ of squared *weights*. A writer starting
  from binned data can only approximate with bin centres — which reproduces
  ROOT's values exactly for the `TH1F` (unit weights, fills at centres) and
  cannot for the `TH1D` (weighted, fills off-centre), so that case supplies them.
- **`-1111` is a sentinel.** `fMaximum` and `fMinimum` mean "compute from the
  data"; 0 gives a histogram ROOT draws with a ceiling of zero.
- **`fFunctions` is streamed in place**, not as a pointer slot, because it is
  declared `//->`. Four zero bytes for "null" makes ROOT read the `TList`'s
  version word out of the next member.
- **The Y axis's `fTitleOffset` is 0 where X and Z carry 1** — `gStyle`, not a
  rule, and the reason the three `TAttAxis` blocks in a ROOT-written histogram are
  not identical. It was the last difference before the records matched.
- **`fBuffer` is persistent**, a counted pointer with a flag byte, sitting just
  before four transient members that a writer walking the header must skip.
- **Two checksums cannot be computed and must be carried as constants**:
  `THashList` and `TSeqCollection`, both class version 0 — §11.2 of
  `StreamerInfo.md` arriving as a practical constraint. `TArray`, `TArrayF` and
  `TArrayD` get **no info at all** in a ROOT-written file, yet their checksums are
  needed as the base of `TH1F`/`TH1D`, so the writer computes them from element
  lists it never emits.
- **Fifteen infos, not the four a histogram seems to need.** `THashList`, `TList`,
  `TSeqCollection`, `TCollection` and `TString` arrive because a **null** object
  pointer forces its class's info to be written, and `TAxis::fLabels` is one.

**M14 — ✅ done 2026-09-18. A `TTree`, byte-identical to ROOT's in every
record.**
*The strongest check in the project, and the one that had the most to get right.*

`WritingTrees.md` (400 lines), `written/tree` (81 assertions), and in
`rootwrite.py`: leaves, branches, baskets, the tree record and the eighteen
streamer infos the chain needs.

**`data/written/tree.root` reproduces `data/ttree/basket.root` record for record**
— both baskets and the `TTree`, keys included, once the wall-clock timestamp is
masked. That is stricter than the histogram comparison, because a branch stores
its baskets' **offsets**: one byte's difference anywhere earlier in the file would
change the tree record. The two names are the same length for that reason, and
`tools/test_write.py` asserts the equality.

The only difference in the whole file is one `StreamerInfo` entry: ROOT appends a
`listOfRules` of two read rules for `TTree` versions ≤ 16 and ≤ 18, which a file
written at version 20 can never trigger.

What a writer needs that no reading document had reason to state:

- **A basket's key version is 1004 whatever the file's size.** `TBasket`'s
  constructor adds 1000 unconditionally (`root/tree/tree/src/TBasket.cxx:71`), so
  a 16 KB file has 8-byte offsets in those keys — and its `fKeylen` covers the
  19-byte basket header, which lives *inside* the key.
- **A basket is never in the directory's key list**, and ROOT's own destructor
  comment says so. The key list holds the `TTree` key alone.
- **`fLeafCount` is an object reference, not a name**, and `fLeaves` holds
  references to the same leaf objects `fBranches` holds. So the **counter branch
  must be written before the counted one** — a write-side ordering constraint
  with no reading-side counterpart.
- **A counter leaf's `fMaximum` must cover every count in the file** before the
  tree record can be written, so a writer needs a full pass over the data. Too
  small and ROOT **clamps** the read with a raw `printf`, desynchronising the rest
  of the entry (`root/tree/tree/src/TLeafI.cxx:174-180`).
- **`fNevBufSize` means two things** — the fixed entry stride, or the offset
  array's capacity — and the wrong one is read silently at the wrong stride.
- **`fBaskets` is `fWriteBasket + 1` slots of null**, not an empty array, because
  `TObjArray::Streamer` writes `fLast + 1` entries after `TBranch::Streamer` has
  removed every basket already on disk.
- **`fBranches` and `fLeaves` are member objects, not pointers** (`fType` 61), so
  no class record — the same 18-byte trap as `fElements` in M12, in the other
  direction.
- **`fMaxVirtualSize` must not be negative** and **`fWeight` must be 1.0**, two
  fields a reading spec would call decorative: the first diverts basket reading
  onto an unbounded cluster path, the second multiplies every `Draw`.
- **`fEntryOffsetLen` is shrunk at flush** to `4 × fNevBuf`, which is why ROOT
  writes 12 where the branch was created with 1000.
- **`ROOT::TIOFeatures` has no `ClassDef`**, so its eleven bytes are a version
  word of 0 and the checksum `0x1aa12f10` — the one foreign class in the classic
  format a writer cannot avoid.
- **`TBasket` gets no streamer info**, although every basket in the file is one:
  the cleanest proof in the format that ROOT reads a class the file does not
  describe. `TBranchRef` and `TRefTable` *do* get one, because `fBranchRef` is a
  null pointer and a null forces its class's info to be written.

ROOT reads the result through its own machinery: `Scan`, `GetEntry` returning 8,
12 and 16 bytes for the three entries, and `Draw` selecting six values from three
entries — which only works if the counted array's offsets and `fLeafCount`
resolved. And `check_invariants.py` decodes both baskets' entries and checks their
byte spans, exactly as it does for a ROOT-written fixture.

**M15 — `WriterInvariants.md`** and the front pages: the collected index of every
`Invariants` entry, organised for a writer rather than by layer, and the status
tables re-measured.

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
| Directory record versions 1, 3, 4 | `Directory.md` | ✅ read; no fixture, and version 2 occurs nowhere (M4) |
| `TBranch` class versions 6–9 | `TBranch.md` §13.1 | ✅ **closed by M6**: specified, read, and 116 legacy branches decoded in `mlpHiggs.root` (7), `uproot-from-geant4.root` (8) and `stock.root` (9) |
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
| A **wide key at a small offset**, which is what disproved the old rule | `volume.root`: `fVersion` 1004 at 105 159 358 (M5, §1.1 of the page) |
| An 8-byte `fSeekPdir` whose top 16 bits are `fPidOffset` and mask away cleanly | both large-format free records read; invariant 6 |
| The uninitialised slack past a key list, past the threshold | `volume.root`: `00 04 00 62 00 04 00 62` after the one image |
| `fLast` above 2000000000 | 32 entries of `volume.root`; the wide form **is** that condition |

Still not asserted by a committed fixture, and never will be: 2 GB cannot be
committed. `spec/01-container/LargeFiles.md` is the write-up (M5) and
`tools/fetch_cern.py --headers` is its check.

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
**eleven specification errors**, each one published, wrong and reader-facing —
M6 added a twelfth from here, `TLeaf` 10.6 on `uproot-issue-250.root`:

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

A twelfth was found in the same corpus without a new run: five
`TMatrixTSym<double>` records in `uproot-issue-359.root` had been reported as
"consumed 48 of 3528" and filed as a class the specification had not written up,
when they were the symptom of `HandWrittenStreamers.md`'s `delegating` claim
being wrong (§8 item M1). The lesson is about reading the output rather than
about the format: a `NOT CHECKED` line naming a class is a *diagnosis*, and this
one had been accepted without being made.

Plus two format facts (a split parent counts `fEntries` but never
`fEntryNumber`; a slot may wrap an object *reference* in a byte count, which ROOT
never writes and its reader accepts) and six reader gaps. Two files are ignored
with per-invariant reasons in `gen/foreign/IGNORE.toml`: one writes basket keys
without ROOT's unconditional `+1000`, the other has a 70-byte hole where a record
header should be.

### 9.9 Standing result over `gen/cern/`

72 files, ROOT 2.24/00 – 6.35/01, **0 failures** since 2026-09-17, and 154 files
(4.00/00 – 6.36/02) at 0 on the other side (§9.8). The probe: 1396 decoded, 264
container, 515 partial, 205 blocked. Of the blocked, 197 are RooFit classes in
two `stressRooFit_*` files (out of scope, decision 8) and the rest are RNTuple's
`RBlob` and anchor; of the partial, 468 are `pippa.root`, a ROOT 2.24 file with
**no streamer infos at all** (out of scope for objects, decision 7).

M6 added three more from here, all of them `TBranch` invariants that had only
ever been checked against files from ROOT 5.34 on: 11.1, 11.3 and 11.9, each
listed in §8.2. Before that, two came from here, both the same mistake in different
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

**The one open failure, closed 2026-09-17.** `aod_flushed.root` (ROOT 5.25/04)
failed `StreamerDriven 10.1` on its `TTreePerfStats` record, whose `kBase`
element for `TVirtualPerfStats` contributes a bare `TObject`, ten bytes, with
**no version word of its own** (`StreamerDriven.md` §4.5). The rule is not
derivable from a file, so clearing it meant publishing the class list, which is
M2 and `spec/99-appendix/ForwardingStreamers.md`. The record now decodes, with
`fReadaheadSize` on 256000 exactly where the byte count said it would be.

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

### 9.11 The `TTree` sub-plan's residue

`PLAN-ttree.md` ordered this layer and was deleted on 2026-09-17, its work done:
all four documents written, `rootfile.TreeReader` decoding the split path, and
every case in its fixture matrix built or absorbed — `split-stl` by
`ttree/split-nested`, `split-branch-object` by `ttree/branch-clones`. Its
dispatch table is now `TBranchElement.md` §8 and its structural findings are in
the four documents themselves; the git log has the sections that were consumed.
What had no other home is here.

**The census it was written against** — 178 corpus files, every record whose
class derives from `TTree`, every `TBranch*` member at every depth. Measured, not
estimated:

| Measured | Value |
|---|---|
| Branches that are not `TBranch` | 6736 of 11157, in 56 files |
| Branch classes | `TBranch` 4421, `TBranchElement` 6734, `TBranchObject` 2, `TBranchClones` 0, `TBranchSTL` 0 |
| `fType` | 0 (4220), 41 (1503), 31 (733), 1 (141), 4 (84), 3 (21), 2 (16), −1 (16) |
| `fID` where `fType == 0` | −1 (216, unsplit top level), −2 (170, split node, which ROOT's own header comment does not mention), ≥ 0 (3834, a member) |
| `fSplitLevel` | 0, 1, 2, 3, 4, 97, 98, 99 — **never 100**, so the two pointer-collection procedures have zero corpus coverage and `ttree/split-ptr-collection` is their only witness |
| `fBranchCount2` | null in **all 6736** |

**What the decoder still cannot reach**, largest first, re-measured after M6.
This is what the `SKIPPED` and `ENTRIES` lines of `check_invariants.py` count —
1001 of 27949 branch-baskets over the two corpora:

1. A collection whose value class has no streamer info in the file — and not a
   gap at all: `Collections.md` §9 says it is unreadable by anyone, ROOT
   included.
2. `fType` −1, a branch whose class writes its own `Streamer`, including the Jpp
   classes of `gen/foreign/IGNORE.toml`. It is the one `fType` value with no
   fixture, and needs a branch whose class has a hand-written `Streamer`.

Those two are all that is left — **67 branch-baskets of 28036** — and both are
things no reader could decode. The embedded basket that was item 1 here is closed
(M8), and so is the embedded **counter** basket (M6). What remains below is about
values rather than about reaching them:

3. `kStreamLoop` values — 4, all in one file. The column's *extent* is checked
   from its byte count; its values need the per-element counts held by a sibling
   branch's column.
4. `TBranchSTL` entries — `ttree/split-ptr-collection` has one with data in it,
   but it is not a `TBranchElement` and has no leaf, so neither entry check
   reaches it. `Splitting.md` §5 describes the branch; its entries stay
   undecoded.
5. A non-null `fBranchCount2`: no file in 178 has one, so the second-dimension
   path is unexercised and unwritten.

**Questions it left open.** Each is small, and each wants the submodule rather
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
  `check_invariants.py`'s `ENTRIES` line is the honest figure; moving it into the
  probe would make it per file rather than per run.
