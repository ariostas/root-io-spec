# PLAN — ROOT I/O Specification

Status: **phases 0–2 complete**, bar the two items in §5. The container and object
layers are written, checked and pushed. `spec/03-classes/` has `TArray` and its
index; `spec/04-ttree/` has `TBranch`, `TLeaf` and `TBasket`, which together cover
reading an entry out of an unsplit tree; `spec/05-rntuple/` is not started.

Throughout this document: **✅ done**, **◐ partly done**, **☐ not started**.
`§9` collects every gap the written documents record, so that they can be picked
up rather than rediscovered.

## 1. Goal

Produce a complete, versioned, machine-checkable specification of the ROOT on-disk
formats, sufficient for a third party to implement a reader **without reading
ROOT's C++ source**.

Reading is specified normatively. Writing is covered by **invariants** rather than
algorithms: each layer states what a conforming file must satisfy, so that a writer
can validate its own output without this document prescribing ROOT's particular
free-space allocation or key-placement strategy. See §2.8.

Non-goals: documenting ROOT's C++ API, its in-memory data structures, or its
build system. We document *bytes on disk* and the *algorithms* required to turn
those bytes into values.

This specification is **descriptive of ROOT 6.40.04**, not normative for ROOT. Where
the pinned submodule and this document disagree, the submodule wins and the
discrepancy is a bug in this document. Where ROOT's own behaviour looks like a bug,
it goes in an errata file and, where possible, an upstream issue or PR.

### 1.1 Why

`root/tree/ntuple/doc/BinaryFormatSpecification.md` is the only real specification
ROOT ships, and it only covers RNTuple. For TFile/TTree the situation is:

- `root/io/doc/TFile/*.md` — an honest attempt, but it documents **release 3.02.06**
  (one page was partially refreshed to 6.22.06). It still claims ZIP is the only
  compression algorithm and that there are "ten compression levels 0-9". It has no
  coverage of `TBranchElement`, member-wise STL streaming, `Double32_t`,
  schema evolution, or the 64-bit file layout beyond the header.
- `root/io/doc/v5xx/`, `v6xx/` — release notes, not specifications.
- Everything else is source code.

Third-party implementations (uproot, groot, UnROOT.jl, root-io in Rust, …) have been
reverse-engineered from that source. This repo is intended to be the shared,
authoritative artifact those projects can cite and test against, and — where it
finds real bugs or under-specification — to feed fixes back upstream.

### 1.2 Reference version

The `root/` submodule is pinned at `v6-40-04` (`1211eda9301`). That is the
**reference implementation** for this specification. When a statement is version
dependent we say so explicitly; the pinned submodule is what the consistency
checkers in `tools/` run against.

## 2. Repository layout

```
root-io-spec/
├── README.md
├── PLAN.md                       ← this file
├── LICENSE                       ← CC-BY-4.0 for spec/, BSD-3 for tools/ + gen/
├── CONTRIBUTING.md
├── root/                         ← submodule, pinned to v6-40-04
├── spec/
│   ├── 00-conventions.md
│   ├── 01-container/             ← the TFile container
│   ├── 02-serialization/         ← the object serialization layer
│   ├── 03-classes/               ← per-class layouts
│   ├── 04-ttree/                 ← TTree and friends
│   ├── 05-rntuple/               ← RNTuple (tracked copy of upstream + errata)
│   └── 99-appendix/
├── gen/                          ← generator scripts (one per test case)
├── data/                         ← generated reference files (committed, small)
└── tools/                        ← checkers, dumpers, CI helpers
```

Rationale for splitting `spec/` into layers rather than one document per class:
ROOT's format is genuinely layered, and ~90% of classes are described entirely by
layers 01+02 plus a `TStreamerInfo` read out of the file itself. Only the layer-03
"exceptions" need hand-written per-class text. Structuring the repo this way makes
the *size of the hand-written surface* explicit, which is exactly the thing
third-party implementers currently have to discover the hard way.

### 2.1 `spec/00-conventions.md`

Normative preliminaries, adopted once so every other document can be terse:

- RFC 2119 keywords (MUST / SHOULD / MAY).
- Endianness. **ROOT's TFile/TBuffer layer is big-endian; RNTuple payload is
  little-endian.** This trips up nearly every new implementer and belongs in the
  conventions, not buried in a subsection.
- Primitive type table: `Char_t`(1) `Short_t`(2) `Int_t`(4) `Long_t`(**8 on disk,
  even where it is 4 in memory**) `Long64_t`(8) `Float_t`(4) `Double_t`(8)
  `Bool_t`(1), and the unsigned variants.
- String encodings: the "counted string" (1 byte length, or `255` followed by a
  4-byte length) vs. `TString`'s own encoding vs. null-terminated C strings in
  class tags. These three coexist and are routinely confused.
- Notation: ASCII bit diagrams (borrowed from the RNTuple spec, which does this
  well) for fixed-layout records; member tables for streamer-driven layouts.
- How we cite the reference implementation: `root/io/io/src/TBufferFile.cxx:2751`
  style, always against the pinned submodule commit.

### 2.2 `spec/01-container/` — the TFile container

| File | Contents |
|---|---|
| ✅ `FileHeader.md` | The 64/100-byte header; `fVersion` encoding; the `+1000000` large-file flag and the field widening it implies |
| ✅ `Record.md` | `TKey` layout, `fNbytes`/`fObjLen`/`fKeyLen`, cycles, `fSeekKey` self-check, the "key of a key" for large files |
| ✅ `Directory.md` | `TFile`'s own record, `TDirectoryFile`, the keys list, `fSeekDir`/`fSeekParent`/`fSeekKeys`, nested directories |
| ✅ `FreeSegments.md` | `TFree` list, the sentinel free segment past EOF, gaps |
| ✅ `Compression.md` | The 9-byte block header, the `ZL`/`XZ`/`L4`/`ZS`/`CS` magics, multi-block payloads, the LZ4 XXH64 trailer, `fCompress` encoding (`100*algorithm + level`), and which records are never compressed |
| ☐ `LargeFiles.md` | Everything that changes past 2 GB, collected in one place |

`Compression.md` is called out separately because the old docs are actively wrong
here and every implementer has to rediscover the block header by hand.

`LargeFiles.md` was not written as a separate document. What changes past 2 GB is
instead stated where it arises — `FileHeader.md` §2 for the `+1000000` flag and
the widened fields, `Record.md` §3.5–3.6 for the large key layout and the packed
`fPidOffset`, `FreeSegments.md` §3 for the large `TFree` entry. **Decide whether
to keep it that way or collect it**; a single page is easier to hand to an
implementer, but it would duplicate rather than replace those sections. No fixture
exercises any of it (§9).

### 2.3 `spec/02-serialization/` — the object layer

This is the core of the repo and the answer to "how do we handle custom classes".

**All seven are written**, with 12 fixtures and 346 byte assertions between them.

| File | Contents |
|---|---|
| ✅ `Buffer.md` | Byte counts (`kByteCountMask = 0x40000000`), the version word and `kByteCountVMask = 0x4000`, `ReadVersion`'s "no byte count in old files" backup path, class tags (`kNewClassTag = 0xFFFFFFFF`, `kClassMask = 0x80000000`), the buffer object/class map and `kMapOffset = 2`, object deduplication, `kNullTag` |
| ✅ `StreamerInfo.md` | The `StreamerInfo` key, the `TList` of `TStreamerInfo`, and the byte layout of `TStreamerInfo` + every `TStreamerElement` subclass. **This is the bootstrap set: these classes cannot be read using streamer info, so a reader must hardcode them.** |
| ✅ `StreamerDriven.md` | The normative algorithm: given a `TStreamerInfo` and a byte range, produce a value tree |
| ✅ `ElementTypes.md` | The complete `EReadWrite` type-code table → exact on-disk bytes |
| ✅ `Collections.md` | STL containers, collection proxies, object-wise vs member-wise streaming |
| ✅ `SchemaEvolution.md` | Class version 0, checksums, `TSchemaRuleSet`, conversion/artificial/cache/skip elements, emulated classes |
| ✅ `References.md` | `TProcessID`, `TRef`, `TRefArray`, `TObject::kIsReferenced` and the extra `fPID` word |

#### The element-type table (`ElementTypes.md`)

The table is the single highest-value deliverable for third-party readers. It
enumerates every value of `TVirtualStreamerInfo::EReadWrite` and states the bytes
produced. Sketch:

| Code | Name | On disk |
|---|---|---|
| 0 | `kBase` | Nested object of the base class (usually with byte count + version; `TObject`/`TNamed` bases are special-cased) |
| 1–19 | `kChar` … `kFloat16` | One fixed-width value; `kDouble32`/`kFloat16` depend on the element's `fFactor`/`fXmin`/`fXmax`/`fNbits` — see `Double32.md` |
| 6 | `kCounter` | An `Int_t` that *also* supplies the length for `kOffsetP` members naming it |
| 15 | `kBits` | `UInt_t`, with the `TObject::fBits` back-compat quirk |
| 20+n | `kOffsetL + n` | Fixed-size C array of `fArrayLength` elements, no prefix |
| 40+n | `kOffsetP + n` | Variable array: 1 leading `Char_t` "is present" byte, then `n` elements where `n` is the value of the `fCountName` member |
| 61–70 | `kObject`…`kAnyPnoVT` | Embedded object / pointer-to-object, with the `kObjectp` (`->`, never null) vs `kObjectP` distinction |
| 71 | `kSTLp` | Pointer to an STL collection |
| 300 / 365 | `kSTL` / `kSTLstring` | See `Collections.md` |
| 500 / 501 | `kStreamer` / `kStreamLoop` | Member handled by a custom `Streamer`; the reader must dispatch to a hardcoded implementation |
| 100+/200+/600+/1000 | `kSkip*` / `kConv*` / `kCache*` / `kArtificial` | Produced by schema evolution; **never appear in a file's own streamer info**, only in memory. Documented so implementers know to ignore them |

The last row matters: a lot of reverse-engineering time is wasted on codes that
cannot occur on disk. Saying so explicitly is a deliverable.

#### `Collections.md` — member-wise streaming

The known-hard part. Must cover:

- Object-wise: byte count, version, count, then each element in full.
- Member-wise: the `kStreamedMemberWise = 0x4000` bit set in the version word, the
  *second* version word for the value class (`ReadVersionForMemberWise`), and the
  transposed layout (all `m0` for every element, then all `m1`, …).
- Which writers produce which: split `TBranchElement` vs. unsplit, and the
  `TStreamerSTL::fSTLtype`/`fCtype` fields.
- `std::map` streamed as a pair-of-vectors vs. a vector-of-pairs, per version.
- `std::string` as `kSTLstring` vs. `TString` vs. `char*` (`kCharStar`).
- `std::bitset`, `std::array`, nested collections, `vector<bool>`.
- `TClonesArray`'s bespoke split-one-level format, which predates all of this.

### 2.4 `spec/03-classes/` — per-class layouts

#### Coverage, and how it is produced

**Decision: generate broadly, hand-write narrowly.**

The cost of this layer is not proportional to the number of classes. For a class
whose layout is streamer-info driven or whose hand-coded streamer agrees with its
streamer info, the entire document is a version matrix plus a member table — and
both are mechanically derivable from the pinned submodule:

- member tables and type codes from `TFile::ShowStreamerInfo()` / `TStreamerInfo`,
- per-version checksums from `TClass::GetCheckSum()`,
- version-to-release ranges from `git log -L` on the `ClassDef` line.

So coverage is generous and effort tracks the genuinely hard cases:

| Set | Count | Treatment |
|---|---|---|
| Persistable classes in core/cont/meta/hist/tree/matrix/physics/graf | 279 | Generated version matrix + member table for all |
| `geom/` (`TGeo*`) | 88 | Generated tables only; no hand-written analysis in the initial passes |
| `graf3d/` + `gui/` | 72 | Generated tables only; most never reach a file, but generating is cheap enough that we do not have to decide which |
| The divergent "bootstrap" classes | ~30 | Hand-written, normative byte layouts |
| `TTree` and friends | ~20 | Hand-written (layer 04) |

Classes with `ClassDef(X, 0)` — 130 of the 409 in the core modules — are *mostly*
transient (`TROOT`, `TClass`, `TSystem`, the iterators) and are excluded by default.
This is a heuristic, **not** a rule: `TH1L`, `TH2L` and `TH3L` are version 0 and
fully persistable, and are exactly the checksum-instead-of-version case. The
inventory tool therefore flags version-0 classes for review rather than dropping
them silently.

#### Generated and hand-written content in the same file

Each class document interleaves both, with explicit markers so a tool can refresh
the generated parts without touching the prose:

```markdown
<!-- BEGIN GENERATED: members TH1 -->
| Member | Type code | Since | Until | Notes |
...
<!-- END GENERATED -->
```

`tools/gen_tables.py` writes these blocks; CI fails if a block is stale with
respect to the pinned submodule. Anything outside the markers is hand-written and
never touched by tooling. Notes columns that need human judgement live in a
sidecar `<class>.notes.yaml` that the generator merges in, so they survive
regeneration.

This also gives us an honest coverage signal: a class with only generated blocks is
marked *mechanically covered*; one with hand-written analysis is marked *reviewed*.
`tools/coverage.py` renders both states in the index, so nobody mistakes a
generated table for a verified one.

#### Answering "how do we handle TH1D vs TH1F" — class *families*

One document per **streaming family**, not per class. A family is the set of
classes that share a single layout description parameterized by a small table.

`spec/03-classes/hist/TH1.md` covers the whole TH1 family. Its normative content is:

1. The layout of `TH1` itself (all class versions).
2. A **variants table**:

   | Class | Class version | Streamed content | Bin storage |
   |---|---|---|---|
   | `TH1C` | 3 | `TH1` base, `TArrayC` base | `Char_t` |
   | `TH1S` | 3 | `TH1` base, `TArrayS` base | `Short_t` |
   | `TH1I` | 3 | `TH1` base, `TArrayI` base | `Int_t` |
   | `TH1L` | **0** | `TH1` base, `TArrayL64` base | `Long64_t` |
   | `TH1F` | 3 | `TH1` base, `TArrayF` base | `Float_t` |
   | `TH1D` | 3 | `TH1` base, `TArrayD` base | `Double_t` |

The rule for when something gets its own file:

> A class gets its own document **iff** it declares streamed members of its own, or
> has a hand-coded `Streamer` whose output differs from what its streamer info
> implies. Otherwise it is a row in its family's variants table.

`TH1L`'s class version `0` is exactly the kind of thing this table surfaces
immediately: it writes a version **word** of 0, so a reader that assumes "version
word is a version" has nothing to look the layout up by, and breaks on `TH1L` and
not on `TH1D`.

Note that an earlier draft of this plan said such a class is written with a
"checksum instead of a version number". That is **wrong**, and the fixture
`serialization/version-zero` disproves it: no checksum follows. The checksum form
belongs to *foreign* classes — those with no `ClassDef` — which is a different set.
The distinction, and the rule a reader must use to tell them apart, is specified in
[Buffer framing](spec/02-serialization/Buffer.md) §4, and is cross-referenced from
every family table that has a version-0 row.

Families slated for **hand-written review** (the generated tables cover everything
persistable regardless), from the `ClassDef` inventory of the pinned submodule:

- **core/base**: `TObject`, `TNamed`, `TString`, `TDatime`, `TUUID`, `TAttLine`,
  `TAttFill`, `TAttMarker`, `TAttText`, `TAttAxis`, `TAttPad`, `TBits`, `TRef`,
  `TProcessID`, `TObjString`, `TParameter<T>`, `TTimeStamp`, `TMacro`
- **core/cont**: `TArray` family (`TArrayC/S/I/L/L64/F/D`), `TCollection`,
  `TList`/`THashList`/`TSortedList`, `TObjArray`, `TClonesArray`, `TMap`/`TPair`,
  `TOrdCollection`, `TBtree`, `TExMap`, `TRefArray`
- **hist**: `TAxis`, `TH1` family, `TH2` family, `TH3` family, `TProfile`,
  `TProfile2D`, `TProfile3D`, `THnSparse`/`THnBase`/`TNDArray`, `TH2Poly`,
  `THStack`, `TEfficiency`
- **graf**: `TGraph`, `TGraphErrors`, `TGraphAsymmErrors`, `TGraphBentErrors`,
  `TGraph2D` family, `TMultiGraph`, `TScatter`, `TPolyLine`, `TBox`/`TLine`/
  `TMarker`/`TEllipse`/`TText`/`TLatex`/`TPave` family, `TLegend`, `TPaveStats`
- **func**: `TF1`, `TF1Data`, `TF2`, `TF3`, `TFormula` (v14), `ROOT::v5::TFormula`
  (the pre-6.02 formula, still found in old files), `TSpline3`/`TSpline5`
- **math**: `TVector2`, `TVector3`, `TLorentzVector`, `TRotation`,
  `TLorentzRotation`, `TQuaternion`, `TMatrixT`/`TMatrixTSym`/`TMatrixTSparse`,
  `TVectorT`, `TDecomp*`, `TFitResult`
- **misc**: `TStyle` (v24!), `TCanvas`/`TPad`, `TFileInfo`/`TFileCollection`,
  `TGeo*` (probably a later phase — large and self-contained)

#### Answering "how do we handle class versions" — the version matrix

Every class document is organized around a **version matrix**, not prose. The
canonical section layout:

```markdown
## TH1 — version history

| Class version | ROOT releases | Layout |
|---|---|---|
| 1 | ≤ 2.25 | hand-coded, see §Legacy |
| 2 | 2.25 – 3.00 | hand-coded, see §Legacy |
| 3–8 | 3.00 – present | streamer-info driven, see §Members |

## Members (versions ≥ 3)

| Member | Type code | Since | Until | Notes |
|---|---|---|---|---|
| `TNamed`     | 67 kTNamed | 3 | — | base |
| `TAttLine`   |  0 kBase   | 3 | — | base |
| `fNcells`    |  3 kInt    | 3 | — | was `fNbins` before v3 |
| `fXaxis`     | 61 kObject | 3 | — | `TAxis` |
| `fTsumwx2`   |  8 kDouble | 3 | — | |
| `fBuffer`    | 48 kOffsetP+kDouble | 4 | — | length from `fBufferSize` |
| `fBinStatErrOpt` | 3 kInt | 7 | — | |
| `fStatOverflows` | 3 kInt | 8 | — | |

## Legacy layouts (versions ≤ 2)

<explicit byte-level layout, since no streamer info in those files is trustworthy>
```

Three distinct regimes, and the matrix makes clear which applies:

1. **Streamer-info driven** (the common case, e.g. `TH1` v ≥ 3, which calls
   `ReadClassBuffer`). The file carries its own `TStreamerInfo`; the normative
   reading procedure is `spec/02-serialization/StreamerDriven.md`. The per-version
   member table here is **informative** — a cross-check and a fallback for files
   with a missing or corrupt streamer info, not the primary source of truth. We say
   so explicitly, because conflating the two is a bug factory.
2. **Hand-coded and self-consistent** — the streamer writes exactly what the
   streamer info says (most `TAttXxx`). Table is informative, as above.
3. **Hand-coded and divergent** — `TObject`, `TString`, `TArray*`, `TList`,
   `TObjArray`, `TClonesArray`, `TMap`, `TKey`, `TBasket`, `TTree`'s bits, `TRef`,
   `TRefArray`, `TH1` v ≤ 2. Here the byte layout in this repo is **normative**,
   because the file's streamer info is present but does not describe what was
   actually written. The old ROOT docs flag this in one sentence and never follow
   up; we enumerate the full set and specify each one.

Regime 3 is the "bootstrap set" and gets its own index page
(`spec/03-classes/index.md#bootstrap`) listing exactly what an implementer must
hardcode before anything else works. Estimated size: ~30 classes.

Each class document also records, per class version:

- `TClass::GetCheckSum()` — needed to resolve version-0 and foreign classes.
- The ROOT release range in which that version was current, recovered from
  `git log -L` on the `ClassDef` line in the submodule. This is genuinely useful
  ("which ROOT wrote this file?") and nothing today publishes it.

### 2.5 `spec/04-ttree/`

`TTree` is large enough to be its own layer, and it is where third-party readers
spend most of their effort.

| File | Contents |
|---|---|
| `TTree.md` | The `TTree` record, v20 members, `fEntries`/`fTotBytes`, the branch list |
| ✅ `TBranch.md` | v13, `fBasketBytes`/`fBasketEntry`/`fBasketSeek` arrays, the "one basket lives inside the TTree record" rule, branches in separate files |
| `TBranchElement.md` | `fID`, `fType` (−1,0,1,2,3,4,41…), `fStreamerType`, `fClassName`/`fParentName`/`fClonesName`, and how `fType` selects the read algorithm |
| ✅ `TLeaf.md` | `TLeaf` family, `fLen`/`fLenType`/`fOffset`/`fIsRange`/`fIsUnsigned`, leaf counts, `TLeafC` strings, `TLeafElement`, `TLeafD32`/`TLeafF16` |
| ✅ `TBasket.md` | The basket record, `fNevBufSize` sign trick → `fIOBits`, the `flag >= 80` "generate offsets" path, `flag % 10 == 2`, entry-offset arrays and the offset/size conversion, displacement arrays, `fLast` |
| `Splitting.md` | Split levels, how a class becomes a branch tree, the naming convention for sub-branches, unsplit fallback |
| `ReadingEntries.md` | End-to-end normative procedure: entry number → basket → byte range → value |
| `Double32.md` | `Double32_t`/`Float16_t` title-comment grammar (`[min,max]`, `[min,max,nbits]`), the factor/offset encoding, and the `TLeafD32`/`TLeafF16` variants |
| `Auxiliary.md` | `TTreeIndex`, `TFriendElement`, `TBranchRef`/`TRefTable`, `TEntryList`, `TEventList`, `TNtuple`/`TNtupleD`, `TChain` |

`TBasket.md` is deliberately prominent: `TBasket` has **no streamer info at all**
(ROOT does not write one), its streamer is entirely hand-coded, and it contains at
least four undocumented encoding tricks. It is the single worst-documented
structure in ROOT I/O.

### 2.6 `spec/05-rntuple/`

RNTuple already has a real specification and we should not fork it.

```
spec/05-rntuple/
├── BinaryFormatSpecification.md   ← byte-identical copy of the upstream file
├── UPSTREAM.md                    ← source commit, sync procedure
├── ERRATA.md                      ← places where the spec and the code disagree
└── NOTES.md                       ← implementation notes the spec omits
```

- `BinaryFormatSpecification.md` is a **verbatim tracked copy** of
  `root/tree/ntuple/doc/BinaryFormatSpecification.md` at the pinned commit.
  `tools/sync_rntuple.py` re-copies it and CI fails if the tracked copy drifts from
  the submodule. We never edit it in place.
- Discrepancies go in `ERRATA.md`, and each entry SHOULD become an upstream PR
  against root-project/root. The repo tracks the PR link per entry.
- First erratum already found during this exploration: the document title says
  `RNTuple Binary Format Specification 1.0.2.1`, while
  `root/tree/ntuple/inc/ROOT/RNTuple.hxx:79-82` writes `kVersionPatch = 0`, i.e.
  anchors say `1.0.2.0`. Harmless (patch is "reporting only") but it means the
  version in the document is not the version in the files, which is worth a note.
- The spec-vs-implementation audit is a real work item, not a rubber stamp:
  newer features (linked attribute sets, low-precision floats, `std::atomic`,
  streamed types) landed recently and the corresponding spec sections need to be
  checked against `RNTupleSerialize.cxx` field by field.

### 2.7 `spec/99-appendix/`

**☐ None of these exist.** The directory has not been created. Two of them are
already referenced from written text as inline code and so are on the critical
path for tidiness rather than correctness:

- ☐ `Bootstrap.md` — the minimal hardcoded class set, in dependency order.
  Referenced from `00-conventions.md` §9. The content largely exists already as
  `02-serialization/StreamerInfo.md` §11; this would be the index.
- ☐ `Glossary.md` — referenced from `00-conventions.md` §9.
- ☐ `ReaderChecklist.md` — an implementation checklist for a new reader.
- ☐ `Pitfalls.md` — a curated list of the things that have historically bitten
  implementers, each linking to the normative section. There is now a lot of
  material for this: the version-0 ambiguity, `kIsReferenced` changing a fixed
  layout's length, `fType` 500, `fCtype` 61, `fOffset`/`fSize` being unusable.
- ☐ `Bibliography.md` — the old ROOT docs, the user's guide, prior art
  (uproot, groot, UnROOT.jl, root-io, jsroot) with links.
- ☐ `WriterInvariants.md` — the collected index of §2.8. Every layer now has an
  `Invariants` section, so this is a collation job, and `tools/check_invariants.py`
  is already its executable form.

### 2.8 Write support: invariants, not algorithms

**Decision: reading is normative; writing is specified as invariants.**

Each layer document ends with an `## Invariants` section stating what a conforming
file must satisfy. A writer can then validate its own output, and a reader knows
which consistency checks are worth making, without this document elevating ROOT's
incidental implementation choices to requirements. Examples of the intended shape:

- **Container**: `fEND` equals the file size. Every `TKey.fSeekKey` equals the
  offset at which that key begins. `fNbytes` spans key + payload exactly. The free
  list plus all key records partition `[fBEGIN, fEND)` with no overlap, and the
  final free segment extends to `kStartBigFile`. `fSeekPdir` points at the
  containing directory's record.
- **Serialization**: every byte count equals the number of bytes actually consumed
  by its object, so `CheckByteCount` succeeds. Every class-tag back-reference points
  at a `kNewClassTag` earlier *in the same buffer*, offset by `kMapOffset`. Byte
  counts stay below `kMaxMapCount`.
- **Streamer info**: every class appearing in any non-core record has a
  `TStreamerInfo` in the file's `StreamerInfo` list, at the version actually used.
  Recorded checksums match the described member list.
- **TTree**: `fBasketSeek[i]`/`fBasketBytes[i]` agree with the keys actually
  present; `fBasketEntry` is non-decreasing and its last element equals
  `fEntries`; the sum of per-basket `fNevBuf` equals `fEntries`.

Where a write-side rule genuinely has no freedom — the compression block header,
the `Double32_t` factor encoding, the `fNevBufSize` sign trick — it is specified
exactly, because there it costs nothing extra. What we deliberately do *not*
specify: free-space allocation policy, basket sizing, key ordering, or when ROOT
chooses to rewrite a directory.

## 3. Reference files and generator scripts

### 3.1 Layout

```
gen/
├── common/            helpers shared by cases (setup, deterministic fills)
├── cases/
│   └── <group>/<case-id>/
│       ├── gen.C          a short, self-contained ROOT macro
│       ├── case.yaml      metadata + expectations
│       └── README.md      what this file is meant to exercise (optional)
└── legacy/            recipes for producing the same cases with old ROOT
data/
└── <group>/<case-id>.root
```

One case = one file = one specific thing being exercised.

**As built** (21 cases): the file is `case.toml`, not `case.yaml`, and the groups
so far are `container/` and `serialization/`. Case names are
`<what-is-exercised>` rather than `<class>-<variant>-<qualifier>`, because these
layers are not per-class — `container/file-minimal`, `serialization/pointer-forms`.
The `<class>-<variant>` convention still applies from `03-classes/` onward.

### 3.2 `case.yaml` — superseded by `case.toml`

> **Changed in practice.** The sketch below assumes semantic assertions
> (`path`/`value`), which need a reader that resolves member paths. What was built
> instead asserts **byte offsets** — `{name, offset, type, value}` — checkable
> with stdlib Python alone and with no reader at all, which is what lets a
> third-party implementation in any language use the corpus as test vectors on day
> one. `tools/check_bytes.py` is ~70 lines as a result.
>
> The cost is that assertions are tied to absolute offsets, so any change to a
> `gen.C` renumbers them; in practice that has been cheap and has repeatedly
> caught errors (four hex-to-decimal slips in one session).
>
> `case.toml` also carries a prose `description`, a `[[records]]` table giving the
> record chain, and a `spec` list naming the documents the case supports.
> **Semantic `expect` assertions remain worth adding** once a reference reader
> exists (§7 item 4); they would complement the byte assertions, not replace them.

The original sketch:

```yaml
id: th1-th1d-basic
spec: spec/03-classes/hist/TH1.md
classes: [TH1D, TH1, TAxis, TArrayD, TNamed]
root_version: "6.40.04"
class_versions: {TH1D: 3, TH1: 8, TAxis: 10}
compression: {algorithm: zlib, level: 1}
expect:
  - {path: "h/fNcells", value: 12}
  - {path: "h/fXaxis/fXmin", value: 0.0}
  - {path: "h/fEntries", value: 3.0}
```

`expect` is what makes the fixtures useful to third parties: a reader can assert
against the values without owning a ROOT installation.

### 3.3 Determinism

Byte-exact reproducibility is **not** achievable: `TKey::fDatime` records wall-clock
time and `TFile` writes a fresh `TUUID` per file. Approach:

- Commit the core, current-version corpus (each file 2–20 kB; the whole committed
  corpus should stay well under ~10 MB — no LFS needed), so that `git clone` is
  enough to run a third-party test suite.
- `tools/normalize.py` computes a digest over the file with the datime and UUID
  fields masked; CI regenerates and compares the *normalized* digest, so genuine
  format changes are caught while timestamps are not.
- Fixed RNG seeds and fixed literal data in every `gen.C`. No `gRandom` without an
  explicit `SetSeed`.

**✅ Built, and two masks were added that this section did not anticipate:**

- the **process UUID as text**, 36 ASCII characters in a `TProcessID` record's key
  title and payload, unrelated to the file's own `TUUID`;
- every **`TStreamerElement::fSize`**, which is `sizeof` on the writing machine and
  differs between standard libraries (`std::string` 24 vs 32,
  `std::map<int,int>` 24 vs 48). Without this, no fixture containing a
  `std::string` or `std::map` member can have a stable digest across macOS and
  Linux, and the symptom is `DRIFT` with every byte assertion passing.

Masking `fSize` means the digest can no longer notice a change in *which* value
ROOT stores there, so a case should assert `fSize` directly for members whose
`sizeof` is standard-library independent.

### 3.4 Coverage targets

Per class family, generate at minimum:

- one file per concrete variant (`TH1C/S/I/L/F/D`),
- one per interesting structural option (fixed vs variable bins, with/without
  `fSumw2`, with attached functions),
- one uncompressed and one per compression algorithm (zlib, lzma, lz4, zstd),
- one large-file case (> 2 GB) generated on demand rather than committed.

Per `TTree`, the matrix is bigger and deserves its own plan section later:
split levels 0/1/99, each leaf type, `std::vector<T>`, `std::vector<std::vector<T>>`,
`std::map`, `std::string`, `TClonesArray`, member-wise vs object-wise, multi-basket
branches, branches in a separate file, `Double32_t` in all three grammars.

### 3.5 Historical versions

Most class versions cannot be produced by ROOT 6.40. To cover them:

- `gen/legacy/` holds a version matrix and per-version container recipes
  (conda-forge `root` packages back to ~6.06, and Docker images / CVMFS for ROOT 5).
  Both `docker` and `mamba` are available in this environment.
- **Legacy files are published as GitHub release artifacts**, not committed — one
  tarball per ROOT version, with a manifest mapping case IDs to files and a
  checksum list committed in `gen/legacy/manifest.yaml`. Same for the >2 GB
  large-file cases. This keeps the repo text-only as versions accumulate while
  still giving third parties a stable download URL.
- Where a version is unreachable, we say so explicitly in the class document rather
  than guessing, and fall back on the ROOT git history for the layout.
- We should also catalogue (not vendor) the existing public corpora —
  `scikit-hep-testdata`, `root.cern/files/` — and map them onto our case IDs.

## 4. Tooling and CI

| Tool | Purpose |
|---|---|
| ☐ `tools/inventory.py` | Parse every `ClassDef*` in the submodule → the authoritative class/version inventory. Feeds the coverage matrix. |
| ☐ `tools/check_versions.py` | Fail if a class document's version matrix disagrees with the submodule's `ClassDef`. This is what keeps the spec from rotting. |
| ☐ `tools/dump_streamerinfo.C` | ROOT macro wrapping `TFile::ShowStreamerInfo()` + `TClass::GetCheckSum()` into machine-readable JSON, used to generate and verify the member tables. |
| ☐ `tools/gen_tables.py` | Fill the `<!-- BEGIN GENERATED -->` blocks in `spec/03-classes/` from `dump_streamerinfo.C` output + `git log -L` release ranges + the `.notes.yaml` sidecars. CI fails on stale blocks. |
| ✅ `tools/check_invariants.py` | Verify the §2.8 invariants hold for every fixture. Doubles as a test that the invariants are stated correctly. |
| ☐ `tools/sync_rntuple.py` | Re-copy the upstream RNTuple spec; fail on drift. |
| ✅ `tools/normalize.py` | Timestamp/UUID-masked digests for fixtures. |
| ✅ `tools/generate.py` | Run every `gen.C`, produce `data/`, validate against `case.toml`. `--check` validates without ROOT; `--accept` re-records an intentional digest change. |
| ☐ `tools/coverage.py` | Render `spec/03-classes/index.md` coverage table from the inventory + what is actually documented. |
| ✅ `tools/check_bytes.py` | Evaluate the `[[bytes]]` assertions of a `case.toml`. Stdlib only, so third parties can run it. Not in the original plan. |
| ✅ `tools/check_citations.py` | Every cited `path:line` exists in the pinned submodule. Not in the original plan. |
| ✅ `tools/check_pin.py` | `zensical.toml`'s citation commit matches the submodule pin. Not in the original plan. |
| ✅ `tools/rootcite.py` | Markdown extension turning `path:line` into a link at the pinned commit. Not in the original plan. |
| ◐ `tools/rootfile.py` | Independent pure-Python reader: header, record chain, directories, key lists, decompression, buffer framing, streamer info, the streamer-driven read, collections, references, `TClonesArray`, `TList`/`TObjArray`. This is §7 item 4's reference reader arriving early and piecemeal; it has no `TTree` and no `TArray*`. |
| ✅ `tools/coverage_probe.py` | Measure how much of an arbitrary ROOT file the specification covers, and rank what blocks the rest. Not a CI check; see §9.7. Not in the original plan. |

CI (GitHub Actions, ROOT from conda-forge) — two workflows, `ci.yml` and
`docs.yml`:

1. ✅ Regenerate all fixtures, compare normalized digests. (Linux job; this is what
   catches the `fSize` portability class of problem.)
2. ☐ `check_versions.py` against the pinned submodule.
3. ☐ `gen_tables.py --check` — generated blocks must be current.
4. ✅ `check_invariants.py` over every fixture.
5. ☐ `sync_rntuple.py` drift check.
6. ✅ Link and **anchor** check across `spec/`, via `zensical build --strict`.
7. ✅ `check_citations.py`, `check_pin.py`, and the `tools/test_*.py` unit tests.
   Not in the original list.
8. ◐ A pure-Python reference reader that implements only what the spec says and
   must read every fixture — the strongest possible completeness check. Partly
   arrived as `tools/rootfile.py`; see §7 item 4.

## 5. Phasing

**✅ Phase 0 — skeleton**
Repo initialized, ROOT pinned as a submodule at `v6-40-04`, this plan.

**◐ Phase 1 — foundations**
✅ `00-conventions.md`, ✅ all of `01-container/` except `LargeFiles.md` (§2.2),
✅ `02-serialization/Buffer.md` and `StreamerInfo.md`, ✅ the fixture harness and
10 container cases. ☐ `inventory.py` was not built.
Deliverable met, with one caveat: "locate and decompress any object" is specified,
but `tools/rootfile.py` does not itself decompress, so no checker looks inside a
compressed record. `Compression.md` is verified by byte assertions on the block
headers only.

**◐ Phase 2 — the generic object layer**
✅ `StreamerDriven.md`, `ElementTypes.md`, `Collections.md`, `SchemaEvolution.md`,
`References.md`, and 11 serialization cases. ☐ `99-appendix/Bootstrap.md` was not
written; its content exists as `StreamerInfo.md` §11 but is not collected.
Deliverable met: `tools/rootfile.py` reads every uncompressed non-`TTree` record in
the corpus from the specification alone.

**The two carried-over items are `inventory.py` and `99-appendix/`.** Neither
blocks phase 3; `inventory.py` should be built first inside phase 3, since that
phase's class list is exactly what it produces.

**◐ Phase 3 — the bootstrap classes and the table generator**
✅ `03-classes/TArray.md`, the first and — by the §9.7 measurement — the most
load-bearing of them. The ~30 regime-3 classes in `03-classes/`, hand-written. Plus
`dump_streamerinfo.C`, `gen_tables.py` and `check_versions.py`, since the generator
pays for itself from phase 4 onward.
Deliverable: enough to read `TFile` internals and the standard containers.

**☐ Phase 4 — standard classes**
Run the generator over everything persistable (~440 classes) in one pass, then
hand-review by family: hist → graf → func → math → misc. The generated pass is
mechanical and cheap; the review is where the time goes, and it can be
interleaved with later phases or accept contributions.

**◐ Phase 5 — TTree**
✅ `04-ttree/TBasket.md`, done early because the coverage probe named it the last
blocker on an ordinary file. ✅ `TBranch.md` and `TLeaf.md`, which together close
the unsplit reading path: entry number → basket → byte range → values, checked
end to end by `rootfile.entry_spans`. What remains is the split half —
`TTree.md`, `TBranchElement.md`, `Splitting.md`, `ReadingEntries.md`,
`Double32.md`, `Auxiliary.md` — with the full split/type matrix of fixtures.
Still the largest single phase, and it still wants its own sub-plan (§7 item 5),
which should now be written around what these three documents settle.

**☐ Phase 6 — RNTuple audit**
Import, sync tooling, and the field-by-field spec-vs-implementation audit;
upstream PRs for anything found.

**◐ Phase 7 — legacy versions and reference reader**
`gen/legacy/`, historical fixtures, and (optionally) the pure-Python reference
reader as the completeness check. The reader half started early and unplanned as
`tools/rootfile.py`, because an independent implementation turned out to be the
cheapest way to keep each new document honest. `gen/legacy/` does not exist, and
**a large share of the gaps in §9 need it.**

Phases 1–3 are sequential. Phase 4, 5 and 6 are independent of each other once
phase 2 is done.

## 6. Decisions

Settled 2026-09-14:

| # | Question | Decision | Where |
|---|---|---|---|
| 1 | Scope of "every standard class" | Generate broadly, hand-write narrowly. Generated version matrices and member tables for all ~440 persistable classes; hand-written prose for the ~30 divergent ones plus `TTree`. Version-0 classes excluded by default but flagged for review, never dropped silently. | §2.4 |
| 2 | Normative status | Descriptive of 6.40.04; pinned submodule is the tiebreaker; errata process for suspected ROOT bugs. | §1 |
| 3 | Write support | Reading normative. Writing specified as per-layer invariants, not algorithms. Free-space policy, basket sizing and key ordering deliberately unspecified. | §2.8 |
| 4 | Upstream relationship | Standalone repo, not blocking on review. RNTuple errata go upstream as PRs immediately. Open a conversation with the ROOT I/O team early about eventually replacing `io/doc/TFile/` wholesale. | §2.6, §7 |
| 5 | Fixture distribution | Core current-version corpus committed (<10 MB). Legacy-ROOT and >2 GB cases published as release artifacts with a committed manifest. | §3.3, §3.5 |
| 6 | Where a divergent class is specified | **Cross-reference, do not re-home.** A class stays in the layer document where its behaviour arises, and `03-classes/` points at it. `TObject` belongs with buffer framing because the framing layer cannot be explained without it; `TList` and `TObjArray` belong with streamer information because they *are* the bootstrap; `TClonesArray` belongs with collections because it is the comparison that makes member-wise streaming legible; `TRef` and friends belong in `References.md`. Moving them would separate each from the argument that motivates it, and would duplicate rather than replace. `03-classes/` therefore holds hand-written text only for classes with no natural home in layers 01–02 — `TArray.md` is the first — plus an index mapping every divergent class to wherever it is specified. Settled 2026-09-15. | §2.4, §9.7 |

## 7. Remaining open items

These do not block starting, but should be resolved before the phase they affect:

1. **When to approach the ROOT I/O team** (affects phase 6, and possibly the
   markup format if they ever want to absorb this). Proposal was: after phase 1
   exists, so the conversation is about a concrete artifact rather than an
   intention. **That condition is now met** — phases 1 and 2 are written, and §7.1
   holds two concrete bug reports that would be a natural opening. Still to decide.
2. **`TGeo*` hand-review** — 88 persistable classes, self-contained, genuinely
   present in real files (detector geometries). Generated tables are in scope by
   decision 1; whether it earns a hand-written pass is a phase-4 judgement call.
3. **Markup format if upstreaming happens.** `root/io/doc/` is doxygen with
   `\page`/`\ref`. Our tables and bit diagrams are better in plain Markdown. If the
   ROOT team wants to absorb this, we need a converter or a decision to diverge.
4. **Reference reader.** Strongest completeness check available (if it needs a fact
   that isn't written down, the spec has a hole), but a project in itself.
   **Partly resolved by accident**: `tools/rootfile.py` grew into one over phases 1
   and 2, because writing an independent implementation alongside each document was
   the cheapest way to catch errors — and it did, repeatedly. It covers everything
   through the object layer for uncompressed records, and has no decompression and
   no `TTree`. The open question is now narrower: whether to finish it deliberately
   as a completeness check, or leave it as a checking tool that happens to be
   thorough.
5. **`TTree` sub-plan.** Phase 5 is large enough that it wants its own plan document
   with the full split/leaf-type/collection fixture matrix enumerated.

### 7.1 Upstream bug candidates found while writing the spec

Verified against the pinned submodule and real bytes; not yet reported.

1. **A `std::vector<T>` of an interpreted class writes an unreadable file.**
   When `T` has no dictionary and the only reference to it in the written class
   is through a collection, `T`'s streamer info is not recorded. The bytes are
   written member-wise, naming `T`'s checksum, with **no warning on the write
   side**. Reopening gives
   `Error in <TBufferFile::CheckByteCount>: object of class vector<Hit3> read too
   few bytes: 6 instead of 20`. Adding any direct member of type `T` is enough to
   get the info written.

   ```cpp
   struct Hit3 { Int_t x; Float_t y; };
   struct C3   { std::vector<Hit3> fHits; };
   // f.WriteObjectAny(&a, "C3", "a");  -> silent; the file cannot be read back
   ```

   The contrast with the direct-member path, which warns "has no streamer or
   dictionary, data member will not be saved", is what makes this a bug rather
   than a limitation: silent data loss versus a diagnostic. Recorded as
   `spec/02-serialization/Collections.md` section 9.

2. **The two collection readers disagree on the `kSTLp` version threshold.**
   `TStreamerInfoActions.cxx:845` uses `>= 8` where
   `TStreamerInfoReadBuffer.cxx:1167` uses `>= 9`, so for a `kSTLp` member
   written at `TStreamerInfo` level 8 the two paths differ by one 2-byte word.
   No such file has been constructed here; verify before reporting.
   `Collections.md` section 6.

3. **`kGenerateOffsetMap` cannot reach a `TBranchElement`.** Every
   `TBranchElement` constructor delegates to the default `TBranch()`, which does
   not copy the tree's `fIOFeatures`
   (`root/tree/tree/src/TBranchElement.cxx:168`,
   `root/tree/tree/src/TBranchElement.cxx:213`), so a feature set with
   `TTree::SetIOFeatures` silently has no effect on any split or object branch —
   which is most branches in a real file. Verified by source reading; not yet
   confirmed by generating a file with the feature enabled on both branch kinds.

4. **An empty `TLeafC` string is misread in a multi-leaf branch.** An empty
   string occupies zero bytes (`TBufferFile::WriteFastArrayString` returns before
   writing the length byte, `root/io/io/src/TBufferFile.cxx:2038`), and
   `TLeafC::ReadBasket` detects that by comparing **whole-entry** offsets
   (`root/tree/tree/src/TLeafC.cxx:146-166`). That is only the same test when the
   `TLeafC` is the branch's only leaf. **Verified at byte level:** a branch
   `x/I:c/C` with `x` = `0x02414243` and the strings `"ab"`, `""`, `"cd"` makes
   ROOT return `"AB"` for the second entry, reading the third entry's `Int_t` as
   the string's length and first bytes. It hides itself well — a following byte of
   0 gives the right answer, and a large one is refused by
   `ShouldNotReadCollection` — which is why `ttree/leaf` round-trips and why this
   has presumably survived unnoticed. Reproducer worth attaching to the report.
   `spec/04-ttree/TLeaf.md` §9.

5. **A `TLeafC` cannot be followed by another leaf in a leaflist.** `TLeaf::fOffset`
   doubles as the in-memory offset a leaflist branch reads its member from, and a
   `TLeafC` contributes `fLen × fLenType` = 1 to the running total at construction
   (`root/tree/tree/src/TBranch.cxx:436`). So `{ Char_t c[8]; Int_t x; }` declared
   `c/C:x/I` reads `x` from the second byte of the string. **Verified at byte
   level:** the written values were stack garbage and ROOT read them back
   unchanged, with no warning at any point. Arguably a documentation bug rather
   than a code one, but it is silent, and item 4 is the same arrangement.
   `spec/04-ttree/TLeaf.md` §3.2.

6. **The suspected `TFile::Recover` gap bug** (banked earlier; still unverified).

## 8. Immediate next steps

Phases 0–2 are done (§5). The next things, in order:

1. **`99-appendix/Bootstrap.md` and `Glossary.md`.** Small, and they close the last
   two inline-code forward references in `00-conventions.md` §9 — which by the
   §6.5 convention are the working list of what is missing.
2. **`tools/inventory.py`.** Parses every `ClassDef*` in the submodule into the
   authoritative class/version list. It turns the phase-3 scope from an estimate
   into a checked-in file, and phase 3 cannot be planned properly without it.
3. **Continue phase 3.** `TArray*` is done. By the §9.7 measurement the classes
   that diverge at *every* version are `TObject`, `TString`, `TList`, `TObjArray`,
   `TClonesArray`, `TRef`, `TRefArray`, `TCollection` and `TArray*` — and all but
   `TCollection` are now specified. Per decision 6 below, `03-classes/` does not
   re-home them: it cross-references. What remains is `TCollection` and an
   `03-classes/index.md` that says where each divergent class is specified.
4. **Decide `LargeFiles.md`** (§2.2): keep the material distributed, or collect it.

Deferred deliberately: `gen/legacy/` (§3.5), which most of §9 depends on, and the
`TTree` sub-plan (§7 item 5).

## 9. Known gaps

Every gap the written documents record, collected so they can be picked up rather
than rediscovered. Most are stated in the `Reference files` section of the document
named; a few are derived from a version difference the document describes.

**None of them is a hole in the prose.** In every case the behaviour is specified
and cited against the submodule; what is missing is a fixture proving it, so each
is a claim verified once rather than twice (`CLAUDE.md`, "the central discipline").

### 9.1 Needs a legacy ROOT (blocked on `gen/legacy/`, §3.5)

| Gap | Document |
|---|---|
| Directory record versions 1, 2, 3 | `01-container/Directory.md` |
| A buffer written with no byte counts | `02-serialization/Buffer.md` |
| `TStreamerElement` versions below 4, including the version-3 `fXmin`/`fXmax`/`fFactor` form | `02-serialization/StreamerInfo.md` |
| A file old enough to take the `BuildEmulated` path | `02-serialization/SchemaEvolution.md` |
| Collection layouts below `TStreamerInfo` version 8 | `02-serialization/Collections.md` |
| `TClonesArray` class version 3, where `kBypassStreamer` is `BIT(14)` | `02-serialization/Collections.md` |

### 9.2 Needs a file over 2 GB (release artifact, §3.5)

| Gap | Document |
|---|---|
| The large `TFree` entry form, and `fLast` above 2000000000 | `01-container/FreeSegments.md` |
| ~~A large key~~ | ✅ `ttree/basket` — a basket always uses the large layout (`fVersion += 1000` unconditionally), so this closed as predicted |
| Everything else past 2 GB | §2.2, `LargeFiles.md` |

### 9.3 Needs a compiled dictionary — **✅ unblocked**

A `gen.C` runs in the interpreter, so a class with a real `ClassDef` was out of
reach. `gen/common/aclic.C` now compiles a case's optional `classes.h` into a
dictionary before the macro is loaded; see `gen/common/README.md`.

| Gap | Document | State |
|---|---|---|
| `TClonesArray` in either encoding | `02-serialization/Collections.md` | ✅ `serialization/clones-array` |
| A member-wise collection whose value class has a `ClassDef`, and so a plain version word instead of a checksum | `02-serialization/Collections.md` | ☐ mechanism exists, case not written |
| A `type=readraw` rule | `02-serialization/SchemaEvolution.md` | ☐ mechanism exists, case not written |

The same mechanism is what phase 4 will need for any class family whose fixtures
must carry real class versions, so it is worth having landed early.

### 9.4 Needs two ROOT sessions or two files

| Gap | Document |
|---|---|
| A non-zero `pidf`, a non-zero `fPidOffset`, and a `fUniqueID` whose top byte survives to disk | `02-serialization/References.md` |
| Two streamer infos for one class distinguished by checksum | `02-serialization/SchemaEvolution.md` |
| A negative in-memory class version reaching disk as 1 | `02-serialization/SchemaEvolution.md` |

`fPidOffset` specifically arises when a key is copied between files, so a
`TTreeCloner` or `TFile::Cp` case would produce several of these at once.

### 9.5 Reachable now, just not written

No external blocker; these are simply cases nobody has added yet.

| Gap | Document |
|---|---|
| A `TStreamerInfo` for a concrete `TArray`, which ROOT sometimes writes and which is wrong by one byte. A `TH2F` produces one; no reference file does | `03-classes/TArray.md` §2 |
| A compressed basket, a multi-block basket, a displacement array, and `fIOBits` in either form | `04-ttree/TBasket.md` §12 |
| ~~The embedded form of a basket~~ | ✅ `04-ttree/TBasket.md` §4.1, `ttree/basket-embedded` |
| A split branch, a non-empty `fFileName`, a non-zero `fIOBits`, a branch whose `fFirstEntry` is not 0, a `TBranch` at class version 9 or below | `04-ttree/TBranch.md` §14 |
| `TLeafObject`, `TLeafElement`, `TLeafG`, a two-dimensional leaf `a[n][3]/F`, a `TLeafC` needing the 255-escape, any leaf class at a legacy version | `04-ttree/TLeaf.md` §13 |
| `kCharStar` (7), `kBits` (15), `kStreamLoop` (501), the 81/82 array forms, `kAnyPnoVT` (70) | `02-serialization/ElementTypes.md` |
| `TStreamerLoop` | `02-serialization/StreamerInfo.md` |
| `std::bitset`, `std::array`, a collection of pointers, a fixed array of collections | `02-serialization/Collections.md` |
| The `kHasUUID` form of `TRef`, and a `TExec` index in a `TRef`'s `fBits` | `02-serialization/References.md` |

### 9.6 Structural, not a missing fixture

| Gap | Where | State |
|---|---|---|
| No checker decompresses, so nothing verifies a compressed payload's *contents* | `tools/rootfile.py` | ✅ done; zlib and lzma from the standard library, zstd on Python 3.14, LZ4 only with the `lz4` package, and a record whose codec is missing is reported as `NOT CHECKED` |
| `tools/rootfile.py` has no `TTree` support, so phase 5 fixtures will not be invariant-checked until it does | §4 | ✅ baskets, branches and leaves are read and checked, and `entry_spans` closes the entry → basket → byte range → value path |
| Semantic (`path`/`value`) assertions were dropped in favour of byte offsets; worth adding back as a complement | §3.2 | ☐ |
| **A `TTree` with a `TBranchElement` branch is not digest-portable.** A fixture with a `std::vector<float>` branch drifted between macOS and Linux CI while all 530 of its byte assertions passed on both, so the difference is in a region no case asserts — most likely the order of entries in the `StreamerInfo` record, which `02-serialization/StreamerInfo.md` §3 says is not guaranteed. Worked around by making `ttree/basket` leaflist-only. **Cause not identified.** `tools/generate.py` now prints per-record digests on drift, so the next occurrence names the record | §3.3, §9.7 | ◐ worked around, not understood |
| Five upstream bug candidates found and banked, not yet reported | §7.1 | ☐ |

### 9.7 What the coverage probe found

`tools/coverage_probe.py` applies the specification to a file it was not designed
around. On an ordinary file — `TH1D`, `TH2F`, `TGraph`, a `TTree` with three
branches, a `TNamed`, default compression — 12 records come out as 3 container,
3 decoded in full, 2 partial and 4 blocked, and the blockers rank like this:

| Blocker | Records | Note | State |
|---|---|---|---|
| `TArray*` | 7 | Every histogram embeds two: `TH1::fContour` and `fSumw2` are `TArrayD` by value, and `TH1D` has a `TArrayD` base | ✅ `03-classes/TArray.md` |
| `TBasket` | 3 | A basket has no streamer info in the file at all, and its own fields are inside `fKeylen` | ✅ `04-ttree/TBasket.md`, both shapes |

**What the probe cannot tell us** is now the important caveat. It checks that every
record's bytes are *accounted for*, not that the values are right, and it was run
on one file of our own construction. A split `TTree`, a `TProfile`, an `THnSparse`
or a file from another producer could still block on something. The next probe
should use a file this project did not write — §3.5's note about cataloguing
`scikit-hep-testdata` and `root.cern/files/` is the way to get one.

**`TArray*` was therefore the single highest-value thing left** — and it is now
done (`spec/03-classes/TArray.md`, `classes/tarray`), as is `TBasket`
(`spec/04-ttree/TBasket.md`, `ttree/basket`).

**The probe file now reads in full: 3 container, 9 decoded, 0 partial, 0
blocked.** Histograms, a graph, a `TTree` and its baskets — including the
compressed ones — are all readable from the specification alone. That is the
milestone the probe was built to measure, reached in two steps.

Since `TBranch.md` and `TLeaf.md`, the same file is more than *accounted for*: its
branches and leaves are invariant-checked, and `rootfile.entry_spans` closes each
entry against the leaves that make it up, so the entry → basket → byte range →
value path is exercised rather than assumed.

**The caveat above has now been discharged: see §9.8.**

### 9.8 The foreign-file probe

Run 2026-09-15 over **154 files this project did not write**, 20 MB, taken from
[scikit-hep-testdata](https://github.com/scikit-hep/scikit-hep-testdata) — uproot's
regression corpus, chosen because it spans **ROOT 4.00/00 to 6.36/02 on purpose**:
2 files from ROOT 4, 27 from ROOT 5 (5.23 to 5.34), 125 from ROOT 6, including a
sweep of `uproot-sample-<version>` files in four codecs. That sweep is the closest
thing available to the legacy corpus `gen/legacy/` was meant to provide, and it
cost nothing to obtain. `gen/foreign/MANIFEST.sha256` records exactly what was
used; `tools/fetch_foreign.py` reproduces it. The files are **not committed** —
they are not our fixtures.

**29 248 records. 28 509 decoded, 699 container, 20 partial, 19 blocked, 1 file
not walkable.** 99.87% of records read from the specification alone, on files
written by four major ROOT versions over sixteen years.

The first run was worse — 139 blocked — and two fixes account for the difference.
Both were real gaps, both are now specified:

| Found | Records | Fix |
|---|---|---|
| A `std::string` written as a whole object (a record, a `pair` half, a pointed-to object) has no frame at all, and no file carries a streamer info for `string` | 114 | `02-serialization/Collections.md` §10.1 |
| A counted pointer's `kCounter` may be declared in a **base class**, which `fCountClass` names. Counters must be carried down the base chain, not scoped per class | 10 | `02-serialization/StreamerDriven.md` §3.2, `ElementTypes.md` §4 |

#### What still blocks, and what it means

| Blocker | Records | Reading |
|---|---|---|
| ~~An embedded `TBasket` inside a `TTree` record~~ | ~~20 records, 1065 skipped members~~ | ✅ **Done.** The biggest finding of the run, now specified in `04-ttree/TBasket.md` §4.1 with the fixture `ttree/basket-embedded`. It is *common* — `uproot-issue327` (ROOT 5.34/30) has 80 in one tree, and both ROOT 4.00/00 files have several per tree |
| `TMatrixTSym<double>` | 5 | A divergent class with a hand-written streamer. Phase 4 material, now with a concrete demand |
| The file's own directory records written by a `TFile` **subclass** — here CMS's `TStorageFactoryFile` | 6 | Not an object gap: a reader must recognise the directory records structurally (`fBEGIN`, `fSeekDir`, `fSeekKeys`, `fSeekFree`) rather than by class name. Worth an erratum in `01-container/` |
| A class with **no streamer info in the file** — `StIOEvent`, `MGTRun`, `ND::TND280Output`, `CalibrationCoefficient`, `RooRealVar`, and ROOT's own `TTime` | 9 | Not a spec gap: `StreamerDriven.md` §6's case, and nobody can read these. That `TTime` is among them is the interesting part — a ROOT class for which ROOT writes no info |
| Member-wise `pair<string,string>` | 3 | Needs byte archaeology; `synthesise_pair` has no `string` case |
| A byte-count-wrapped object **reference** (`40 00 00 04` then a 4-byte tag) | 1 | `Buffer.md` §6 rejects this, and ROOT's reader accepts it. **Provenance unestablished** — `uproot-issue413.root` looks uproot-written (branch names `I32`/`F64`/`Str`/`ArrF64`, file "struct.root"). Settle the writer before changing `Buffer.md` |
| `TDatime` at version 0 with a checksum matching nothing; `RooAbsCollection` consuming −29 bytes; `vector<double>` version 0 with no info; a zero-length record at 10427 | 5 | One each, undiagnosed |

#### The triage, done

**10 047 failures became 0.** Every group was diagnosed against the pinned source,
and each resolved to exactly one of four outcomes: a specification error, a format
fact the specification lacked, a gap in `tools/rootfile.py`, or a defect in the
file. Nothing was weakened on a file's say-so, and everything still unexplained is
printed as `NOT CHECKED` with a reason rather than passed over.

**Eleven specification errors** in total, five below and six in the second pass —
each one published, wrong, and reader-facing.

**Five specification errors.** These are the return on the exercise: each is a
statement that was wrong, published, and would have misled a reader.

| Was wrong | Now | Evidence |
|---|---|---|
| `TBasket.md` §6 and §8: no offset array means fixed-length entries | Only when the flag is not 80. A `kGenerateOffsetMap` basket looks identical and is not, and §5.2.1 now gives the recurrence that regenerates its offsets | `uproot-small-dy-nooffsets.root`: `fNevBufSize` 1000, `fNevBuf` 200, `fObjlen` 3400. `77 + 4 × 850` is `fLast` exactly |
| `TBasket.md` invariant 5: the last offset is below `fLast` | At most `fLast` — an **empty last entry** puts it exactly there, which `TLeafC::ReadBasket` tests for | 1484 baskets across the `uproot-HZZ` family |
| `StreamerInfo.md` §9 and invariant 7: `fMaxIndex[1]` is the base's checksum | Or **0**, on every file ROOT 5 wrote. `fBaseCheckSum` arrived in 6.00/00 (`185b44f3d96`, 2014-04-21) | The version sweep brackets it: all 23 are 0 from 5.23 to 5.30, none is from 6.08 to 6.20 |
| `StreamerInfo.md` invariant 9: an STL element's `fType` is 500 | On ROOT 5 and later. **ROOT 4 wrote the real code**, 300 (§10.1) | The two ROOT 4.00/00 files, nine elements each |
| `StreamerInfo.md` invariant 10 and `StreamerDriven.md` invariant 3: a counter precedes its element in the same info | Or sits in the **base class** its `fCountClass` names | `TArrayD.fArray` names `fN` in `TArray` |

**Two format facts the spec did not have.**

| Fact | Where |
|---|---|
| The parent of a split branch counts `fEntries` but never `fEntryNumber`, which stays 0: its fill path is a bare `++fEntries` (`root/tree/tree/src/TBranchElement.cxx:1320`). So `fEntries != fEntryNumber − fFirstEntry` there, and the parent's counters are not the tree's | `TBranch.md` §7, invariant 8 |
| A slot may wrap an object **reference** in a byte count. ROOT never writes one but its reader accepts it (`root/io/io/src/TBufferFile.cxx:2751-2764`), and files in the wild have it | `Buffer.md` §6.1 |

**Four reader gaps, the spec already being right.** A counter leaf written *inline*
inside another leaf's `fLeafCount` rather than referenced; a branch's `fLeaves`
entry that is itself a reference to a leaf written elsewhere; the class-version-1
`TLeafF16`/`TLeafD32` title with no leading slash; and a directory record whose
class name is a `TFile` **subclass**, which `read_directory` gated on. Between them
these were 4 742 failures.

**One file ignored**, with the reason recorded per invariant in
`gen/foreign/IGNORE.toml`: `uproot-issue413.root` writes basket keys at `fVersion`
4 where ROOT adds 1000 unconditionally. ROOT reads the file, so it is not corrupt
— it is simply not written the way ROOT writes, and its 6 failures must not weaken
`TBasket.md` §1. `check_invariants.py --ignore` prints what each entry suppressed,
so an entry that stops mattering shows up as suppressing nothing.

#### The rest of the 250, also done

**Zero failures across all 154 files.** Six more specification errors, one more
format fact, two reader gaps, and one more file ignored.

| Was wrong | Now |
|---|---|
| `TBranch.md` invariant 10: `fLeaves` is not empty | An interior node of a split branch has no leaves at all — all 146 leafless branches in the corpus have sub-branches, `fWriteBasket` 0 and no baskets, and ROOT has a dedicated `ReadLeaves0Impl` for them (§9.1) |
| `ElementTypes.md` invariants 1 and 2: `fType` 300 and 365 cannot occur | They do, on ROOT 4 — the same finding as `StreamerInfo.md` §10.1, which the element-type invariants had missed |
| `StreamerDriven.md` invariant 3: a counter's `fType` is 6 | Any integer basic type. `kCounter` replaces `kInt` only when the class that *uses* the member is built, so the class "has no control over what the field type really use" (`root/io/io/src/TStreamerInfo.cxx:2967-2972`); and an unsigned counter keeps `kUInt` — `TBits::fNbytes` is one ([Element types §2.1](ElementTypes.md#21-kcounter-6)) |
| `StreamerDriven.md` invariant 4: bases precede members | A base that is an **STL container** is written as a `TStreamerSTL`, not a `TStreamerBase`, and may precede one. `JTRIGGER::JPMTSelector` inherits from `std::vector` and `TObject`, in that order (§4.3) |
| `SchemaEvolution.md` invariant 2: no two entries share a version and a checksum | Dropped. ROOT writes such a pair for `ROOT::TIOFeatures`, differing only in the transient `kIsCompiled` bit, and a differing checksum at one version was already legitimate — so there is no uniqueness invariant at all (§8.1) |
| `TLeaf.md` invariant 1: `fLen` is positive | Or **−1**, a documented parse failure when the title's dimension names neither a leaf nor an integer (`root/tree/tree/src/TLeaf.cxx:244-245`). Normal for a `TLeafElement` on a split branch (§4.2) |
| `TLeaf.md` invariant 3: `fIsRange` only on an integer leaf | Or a `TLeafElement`, which keeps the range in its `TBranchElement` — as `TLeaf.h:78` says |
| `FileHeader.md` invariant 7: `nfree` equals the free list's length | Advisory. ROOT reads it into a local and never uses it (`root/io/io/src/TFile.cxx:743`), rebuilding the list from `fSeekFree`; both ROOT 4 files write 0 against a list of two (§5.4) |

**One more format fact.** `TDatime` as a *member* is four bare bytes: its streamer
writes `fDatime` and nothing else, no version word and no byte count
(`root/core/base/src/TDatime.cxx:415-422`), so a `kAny` member of that type has no
frame where the generic algorithm expects one.
[Records and keys §3.7](spec/01-container/Record.md), and it is the tenth entry in
`03-classes/`'s index.

**Two reader gaps.** A branch's `fLeaves` entry that is a bare reference — 146
branches — and a counter leaf in the *same* branch as what it counts, which the
checker demanded up front instead of reading in order as §5 says.

**One more file ignored.** `uproot-issue261.root` has a 70-byte hole where a record
header should be. ROOT's own walker calls a zero `fNbytes` an error and abandons the
file (`root/io/io/src/TFile.cxx:1676-1680`), so it is a defect — but nothing in
`TFile::Open` walks the chain, so ROOT reads the file's `TTree` without a word.
[Records and keys §1](spec/01-container/Record.md#1-the-record-chain) now says
walking is optional.

**And what is deliberately *not* checked**, each named in the output rather than
passed over: a class the file carries no streamer info for (`StIOEvent`, `TTime`,
`MGTRun`, `CalibrationCoefficient`); a `TBranch` below class version 11, whose
layout `TBranch.md` §13 does not give; and `TMatrixT`, `TVectorT` and
`RooLinkedList`, whose hand-written streamers are real divergences this
specification has not written up — `RooLinkedList` writes `_size` and then that
many object pointers, while its info advertises a `_hashThresh` that is not on disk
(`root/roofit/roofitcore/src/RooLinkedList.cxx:891-924`).

#### The methodological catch

`check_invariants.py` over the same corpus reports **10 538 failures**, and
**that number means almost nothing yet.** Three different things produce it and
they have to be separated per file before any of it is evidence:

1. **Invariants stated too strongly.** Already confirmed for `TBranch` 11.9:
   `fBaskets`'s slot count on disk is *not* `fWriteBasket + 1` in general — it
   comes from `TObjArray`'s cached `fLast`, which `TBranch::Streamer`'s
   `fBaskets[i] = nullptr` does not update, so it can be 0. The invariant should
   not assert the count at all.
2. **Files not written by ROOT.** uproot's corpus contains files uproot wrote, and
   those fail invariants for reasons that say nothing about ROOT's format.
   `fEntries 1 != fEntryNumber − fFirstEntry (0 − 0)` is the signature.
   **No invariant may be weakened on the strength of such a file.**
3. **Genuine format facts we have wrong.** `TBranch` 11.3 failed on
   `uproot-issue431.root` (ROOT 5.34/38) with
   `fBasketEntry[fWriteBasket] 4 != fEntryNumber 10`, and that one is now
   **resolved**: the last basket is embedded, so the terminator was never written.
   The invariant was wrong, not the file. `ttree/basket-embedded` reproduces it.

Triaging the rest is a task in itself and is **not** done. Until it is, the
foreign corpus is a coverage measurement, not an invariant test.

#### Second run, after the embedded basket

**28 520 decoded, 699 container, 9 partial, 19 blocked, 1 not walkable.** Reading
embedded baskets removed every one of the 1065 skipped members and took `partial`
from 20 records to 9. It also turned up one more detail no fixture would have
shown: **when `fNevBuf` is 0 no offset array is written even though the flag says
there is one**, because both sides of the streamer guard the array on `fNevBuf`
independently of the flag. A reader that trusts the flag reads the reserved key
area as a count.

Two corrections the probe forced, both recorded where they belong:

- **The divergent-class set is much smaller than §2.4 assumes.** Many classes have
  a hand-written `Streamer` that is only a version guard delegating to
  `ReadClassBuffer` above a threshold — `TH1` and `TGraph` above class version 2,
  `TAxis` above 5, `TTree` above 4, `TLeaf` above 1, `TBranch` and
  `TBranchElement` unconditionally. All of those are streamer-info driven at every
  version a current file contains. The classes that diverge at *every* version are
  `TObject`, `TString`, `TList`, `TObjArray`, `TClonesArray`, `TRef`, `TRefArray`,
  `TCollection` and `TArray*` — and all but `TCollection` and `TArray*` are already
  specified. **Phase 3 should be scoped from this measurement, not from the
  estimate in §2.4.** The legacy layouts below each threshold remain, and belong
  with §9.1.
- **A hand-written streamer's recorded info can be pure fiction, and this is
  observable.** `TList`'s info lists a `TSeqCollection` base which lists a
  `TCollection` base; `TList::Streamer` writes none of them. Recorded as
  `02-serialization/StreamerDriven.md` §7, now with a real-file example rather
  than only the principle.
