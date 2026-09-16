# PLAN — ROOT I/O Specification

Status: **phases 0–2 complete**, bar the two items in §5. The container and object
layers are written, checked and pushed. `spec/03-classes/` has `TArray` and its
index; `spec/04-ttree/` has `TTree`, `TBranch`, `TLeaf` and `TBasket`, which
together cover reading an entry out of an unsplit tree; `spec/05-rntuple/` is not
started.

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
  (`std::bitset` is specified and has a fixture; the other three do not.)
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
| ✅ `TTree.md` | The `TTree` record, v20 members, `fEntries`/`fTotBytes`, the branch list, `fLeaves` as back-references, cluster ranges, finding a tree by derivation |
| ✅ `TBranch.md` | v13, `fBasketBytes`/`fBasketEntry`/`fBasketSeek` arrays, the "one basket lives inside the TTree record" rule, branches in separate files |
| ✅ `TBranchElement.md` | `fID`, `fType` (−1,0,1,2,3,4,31,41), `fStreamerType`, `fClassName`/`fParentName`/`fClonesName`, `fBranchCount` as a back-reference, and the eleven-row dispatch `fType` selects together with `fID`, `fSplitLevel` and `fStreamerType` |
| ✅ `TLeaf.md` | `TLeaf` family, `fLen`/`fLenType`/`fOffset`/`fIsRange`/`fIsUnsigned`, leaf counts, `TLeafC` strings, `TLeafElement`, `TLeafD32`/`TLeafF16` |
| ✅ `TBasket.md` | The basket record, `fNevBufSize` sign trick → `fIOBits`, the `flag >= 80` "generate offsets" path, `flag % 10 == 2`, entry-offset arrays and the offset/size conversion, displacement arrays, `fLast` |
| ✅ `Splitting.md` | Split levels and what `fSplitLevel` does not mean, how a class becomes a branch tree, the trailing-dot naming divergence, the `name_`/`[name_]` count convention, `kSplitCollectionOfPointers` and `TBranchSTL`, the unsplit fallback |
| ✅ `ReadingEntries.md` | End-to-end normative procedure: entry number → basket → byte range → value, for the unsplit path and all eleven split read procedures |
| ~~`Double32.md`~~ | **Dropped** — already written and distributed: the grammar and the three encodings are `02-serialization/ElementTypes.md` §5.1-5.3, the leaf classes and the 3-versus-4-byte asymmetry are `TLeaf.md` §7. Per decision 6, cross-referenced rather than re-homed (`PLAN-ttree.md` §4) |
| ✅ `Auxiliary.md` | `TTreeIndex` — which publishes no streamer info — `TFriendElement`, `TBranchRef`/`TRefTable`, `TEntryList`/`TEntryListBlock`, `TEventList`, `TNtuple`/`TNtupleD`, `TChain` |

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
| ◐ `tools/rootfile.py` | Independent pure-Python reader: header, record chain, directories, key lists, decompression, buffer framing, streamer info, the streamer-driven read, collections, references, `TClonesArray`, `TList`/`TObjArray`, and the unsplit `TTree` path — tree record, branches, leaves, baskets, entry spans. This is §7 item 4's reference reader arriving early and piecemeal. |
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
blocker on an ordinary file. ✅ `TBranch.md`, `TLeaf.md` and `TTree.md`, which
together close the unsplit reading path from the record down: tree → branch →
basket → byte range → values, checked end to end by `rootfile.entry_spans`. What
remains is the split half. The sub-plan §7 item 5 asked for is written:
[`PLAN-ttree.md`](PLAN-ttree.md). It measures the split half across both corpora
— 6736 of 11157 branches are `TBranchElement`, `fType` selects eleven read
procedures of which two have zero coverage in 178 files — and turns phase 5 into
four documents (not five) plus a fifteen-case fixture matrix.

**All four are written**: ✅ `TBranchElement.md`, ✅ `Splitting.md`,
✅ `ReadingEntries.md` and ✅ `Auxiliary.md`, with fifteen new fixtures and
twenty-seven new invariants, all clean over both corpora. `Double32.md` was
dropped as already-written and distributed (`PLAN-ttree.md` §4).

✅ **And the split-branch decoder**, `rootfile.TreeReader`, which closes
`ReadingEntries.md` invariant 5 — the one invariant in `04-ttree/` that could be
stated but not checked. With the `pair<K,V>` work that followed it, the entry
checks now reach **25937 of 26011 branch-baskets over both corpora, 99.7%, at 0
failures**, against 89.6% before. The 74 they cannot reach are named and counted
individually, and every one is something no reader could decode from the file —
there is no longer a category that is merely unimplemented.

Writing it found five things, listed in `PLAN-ttree.md` §10 — among them that the
§5.3 header is shared across a whole column rather than written per value, and
that `StreamerDriven.md` §7's claim that a user-defined class's streamer info is
authoritative is false.

Phase 5's deliverable is met: the reading path is specified end to end for both
the unsplit and the split case, and `tools/rootfile.py` implements it
independently. What remains of the phase is coverage rather than specification —
`fType` −1, `TBranchObject`, `TBranchClones`, `TChain`, and the five gaps in
`PLAN-ttree.md` §10.

**◐ Phase 6 — RNTuple audit**
✅ Import and sync tooling. `spec/05-rntuple/` holds a **verbatim tracked copy** of
`root/tree/ntuple/doc/BinaryFormatSpecification.md` (1271 lines, 73 872 bytes)
plus `UPSTREAM.md`, `ERRATA.md` and `NOTES.md`; `tools/sync_rntuple.py --check`
fails on drift and also asserts that the commit `UPSTREAM.md` records is the one
`root/` is pinned to, so a stale copy and a stale provenance note cannot agree
with each other. **The CI step for this existed but was guarded by
`hashFiles(...) != ''` and had therefore never run**; the guard is gone and the
step is real.

◐ The audit. **Three errata so far, all in the anchor and the ROOT file
embedding**, each verified against the pinned submodule *and* against the bytes of
`RNTuple.root` (ROOT 6.35/01, from §9.9's corpus):

| # | What |
|---|---|
| 1 | The title says format version **1.0.2.1**; the writer stamps **1.0.2.0** (`RNTuple.hxx:79-82`) |
| 2 | The anchor schema starts at `Version Epoch` and omits the **byte count and class version word** that precede it on disk — they are the first two members of `RTFNTuple` (`RMiniFile.cxx:548-549`). A reader following the schema is six bytes out from its first field |
| 3 | The checksum is "the XXH3 hash of all the (serialized) fields". It is not: the byte count and class version are excluded (`RMiniFile.cxx:580-583`), and the checksum sits **outside the byte count**, so the object is eight bytes longer than it claims |

Plus three implementation notes where the document is right but a reader arriving
from the TFile side goes wrong — chiefly that an `RBlob` key's `fObjLen` is
decorative, which is the same observation that produced the `Compression.md`
erratum in §9.9.

☐ **Everything from *Basic Types* onward is unaudited**: frames, locators and
envelope links, the header, footer and page list envelopes, the C++ type mapping,
and the limits. `spec/05-rntuple/NOTES.md` §4 says so in the document rather than
leaving the silence to be read as approval. Upstream PRs for the three open
errata are the next step, and are the natural opening for §7 item 1.

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
5. **`TTree` sub-plan.** ~~Phase 5 is large enough that it wants its own plan
   document with the full split/leaf-type/collection fixture matrix enumerated.~~
   **Resolved 2026-09-16: [`PLAN-ttree.md`](PLAN-ttree.md).** Built on a measurement
   of both corpora rather than an estimate, which changed three things — it dropped
   `Double32.md` as already-written, it found that four of the eight `fType` values
   carry no leaf at all (so `ReadingEntries.md` cannot just extend `TLeaf.md` §5),
   and it named the two read procedures no file in either corpus reaches.

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

7. **A `pair<K,V>`'s checksum can be computed before its members are known, and
   is then cached forever.** `TClass::GetCheckSum` derives the value from
   `GetListOfDataMembers()` and stores it in `fCheckSum`, which the source says
   "once it has transition from a zero Value it never changes"
   (`root/core/meta/src/TClass.cxx:6655-6666`). A `pair<K,V>` whose `TClass` is
   still forward-declared has no data members yet, so a checksum taken at that
   moment is computed from almost nothing — and several distinct pairs then share
   one value. **Verified at byte level and reproducible**:
   `data/serialization/pairs.root` has `pair<int,string>`,
   `pair<int,vector<short> >` and `pair<TString,PHit*>` all carrying
   `0x0b5fb752`, in their recorded streamer infos and in their member-wise
   headers alike. Which pairs it happens to depends on the order the writing
   program touched them — the same three came out differently in two ROOT
   sessions over the same header.

   **Not a data-loss bug**: ROOT reads the file back correctly, because
   `ReadVersionForMemberWise` is handed the value class resolved from the
   member's declared type name and calls `FindStreamerInfo(checksum)` on that
   class alone. It is a hazard for every *other* reader, since the obvious
   implementation — a checksum-to-info table — silently decodes two of those
   three maps as the wrong type. `spec/02-serialization/Collections.md` §8.2.
   Worth reporting as "the checksum should identify the class, and here it does
   not"; the fixture is the reproducer.

## 8. Immediate next steps

Phases 0–2 are done (§5). The next things, in order:

1. ~~**`99-appendix/Bootstrap.md` and `Glossary.md`.**~~ ✅ Both written, and with
   them **every inline-code forward reference to an unwritten document is gone** —
   by the §6.5 convention that was the working list of what is missing, and it is
   now empty. The third reference in `00-conventions.md` was to `Double32.md`,
   which §2.5 had dropped; it is repointed at the three places the material
   actually lives.

   `Bootstrap.md` turned out to be worth more than its size. It is the list
   `StreamerInfo.md` §1 promised and did not deliver — that section said "§11
   lists it" and §11 is Checksums — and it is the only document organised as a
   work order rather than by layer. `tools/test_bootstrap.py` checks its class
   lists against what `tools/rootfile.py` hardcodes, in both directions, because
   a list like that rots without anything failing.
2. ◐ **`tools/inventory.py`.** Parses every `ClassDef*` in the submodule into the
   authoritative class/version list. It turns the phase-3 scope from an estimate
   into a checked-in file, and phase 3 cannot be planned properly without it.

   Half of it exists: ✅ `tools/check_versions.py` does the extraction — **2166
   distinct classes across 8899 headers**, of which 24 names are ambiguous
   because ROOT's own tests and tutorials define classes called `Event`, `Track`
   and `MyClass` — and compares it against the spec's class-version tables. CI
   had a step wired for exactly this, guarded by `hashFiles(...)` so that it
   silently did nothing; the guard is gone. What is still missing is the
   *inventory as a checked-in artefact* for phase 4 to plan against. Note that
   2166 is not the ~440 of §2.4: that figure is persistable classes, and the gap
   between the two numbers is itself worth measuring before phase 4 is scoped.
3. **Continue phase 3.** `TArray*` is done. By the §9.7 measurement the classes
   that diverge at *every* version are `TObject`, `TString`, `TList`, `TObjArray`,
   `TClonesArray`, `TRef`, `TRefArray`, `TCollection` and `TArray*` — and all but
   `TCollection` are now specified. Per decision 6 below, `03-classes/` does not
   re-home them: it cross-references. What remains is `TCollection` and an
   `03-classes/index.md` that says where each divergent class is specified.
4. **Decide `LargeFiles.md`** (§2.2): keep the material distributed, or collect it.
5. **Report the three RNTuple errata upstream** (§5 phase 6). They are against a
   document the ROOT team owns and maintains, which makes them a friendlier first
   contact than §7.1's bug candidates — and they can carry those.

Deferred deliberately: `gen/legacy/` (§3.5), which most of §9 depends on.

The `TTree` sub-plan is no longer deferred — see [`PLAN-ttree.md`](PLAN-ttree.md),
which orders the split half of phase 5 and is the largest piece of remaining work.

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
| A file old enough to take the `BuildEmulated` path | `02-serialization/SchemaEvolution.md` — **✅ available**: `pippa.root` in §9.9, ROOT 2.24/00 with **zero streamer infos**, now fully decompressed (§9.9, the `CS` codec) |
| `TBranch` class versions 6 to 9 | `04-ttree/TBranch.md` §13 — **reproducer available**: `stock.root` in §9.9, ROOT 4.00/07, ten trees at v9. §13.1 now gives the one fact that makes the generic algorithm inapplicable, byte-verified |
| Collection layouts below `TStreamerInfo` version 8 | `02-serialization/Collections.md` |
| `TClonesArray` class version 3, where `kBypassStreamer` is `BIT(14)` | `02-serialization/Collections.md` |

### 9.2 Needs a file over 2 GB (release artifact, §3.5)

| Gap | Document |
|---|---|
| ~~The large `TFree` entry form, and `fLast` above 2000000000~~ | ◐ **Measured** on eight remote files, §9.9 — including 32 large and 19 small entries interleaved in one record. Not yet asserted by a committed fixture |
| ~~A large key~~ | ✅ `ttree/basket` — a basket always uses the large layout (`fVersion += 1000` unconditionally), so this closed as predicted |
| The `+1000000` `fVersion` flag and `fUnits` 8 | ◐ measured, §9.9: six files from ROOT 5.19 to 6.23, and `lhcb2.root` has `fEND` past **4 GB** |
| Everything else past 2 GB | §2.2, `LargeFiles.md` — now writable against something real |

The blocker here was "we cannot produce a 2 GB fixture". §9.9 routes around it: the
files exist at root.cern, `Accept-Ranges` works, and the header plus the
free-segment record is all that `01-container/` needs. `tools/fetch_cern.py
--headers` is a standing check over them and downloads nothing.

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
| A branch with a non-empty `fFileName`, which names the file its baskets went to | `04-ttree/TBranch.md` §14 |

`fPidOffset` specifically arises when a key is copied between files, so a
`TTreeCloner` or `TFile::Cp` case would produce several of these at once.

### 9.5 Reachable now, just not written — **closed 2026-09-16**

Every row is done. Seven new cases, and **eight of the twenty-odd items in the
list turned out to be covered already or not to exist at all** — which is the
second result of the exercise and the reason the list had drifted:

| Item | What it actually was |
|---|---|
| `kBits` (15) | Covered. A split branch turns a `TObject` base into `fUniqueID` and `fBits` sub-branches whose elements carry code 15 |
| `kAnyPnoVT` (70) | **Has no producer.** Nothing in ROOT constructs an element with `fType` 70 |
| `TLeafObject`, `TLeafElement` | Covered — one in `tree-branchref`, 52 in the split cases |
| a collection of pointers | Covered by `split-ptr-collection` and `pairs` |
| a split branch | Covered by every `split-*` case |
| a non-zero `fIOBits` | Covered by `basket-iofeatures` |
| "a `TH2F` produces one" (`TArray`) | **False.** A `TH2F` in a `TTree` branch does; a `TH2F` does not |
| a multi-block basket | Believed too large to commit. 16.8 MB of one repeated `Double_t` is 7 920 bytes under LZMA 9 |

Three items moved rather than closed: a non-empty `fFileName` to §9.4, and the
legacy leaf and `TBranch` versions stay under §9.1.

The original list follows, with the outcome of each row.

| Gap | Document |
|---|---|
| ~~A `TStreamerInfo` for a concrete `TArray`, which ROOT sometimes writes and which is wrong by one byte~~ | ✅ `classes/tarray-histogram`. **A `TH2F` does not produce one** — the row said it did. A `TH2F` in a `TTree` branch does, and 16 of the 39 histogram files across both corpora carry one |
| ~~A compressed basket, a multi-block basket, a displacement array~~ | ✅ `ttree/basket-compressed`, `ttree/basket-multiblock`, `ttree/basket-displacement`. `fIOBits` was already covered by `ttree/basket-iofeatures` and the row was stale. **A multi-block basket is committable after all** — 16.8 MB of one repeated `Double_t` is 7 920 bytes under LZMA 9 |
| ~~The embedded form of a basket~~ | ✅ `04-ttree/TBasket.md` §4.1, `ttree/basket-embedded` |
| ~~A branch whose `fFirstEntry` is not 0~~ | ✅ `ttree/branch-first-entry`. A split branch and a non-zero `fIOBits` were already covered by the `split-*` cases and `basket-iofeatures`; a non-empty `fFileName` moved to §9.4 (it needs a second file) and class version 9 or below stays under §9.1 |
| ~~`TLeafG`, a two-dimensional leaf `a[n][3]/F`, a `TLeafC` needing the 255-escape~~ | ✅ `ttree/leaf-forms`. `TLeafObject` and `TLeafElement` were already covered — `tree-branchref` has one and the split cases have 52 — so only the legacy versions remain, under §9.1 |
| ~~`kCharStar` (7), `kStreamLoop` (501), the 81/82 array forms~~ | ✅ `serialization/element-types`. `kBits` (15) was already covered from the tree side and the row was stale; `kAnyPnoVT` (70) has **no producer** and cannot be reached, now stated in `ElementTypes.md` §7.3 |
| ~~`TStreamerLoop`~~ | ✅ the same case, three forms of it |
| ~~`std::array`, a fixed array of collections~~ | ✅ `serialization/collection-forms`, which also closes the `ClassDef` value class of `Collections.md` §16 and found that a fixed array of collections shares **one** frame (§11.1) |
| ~~The `kHasUUID` form of `TRef`, and a `TExec` index in a `TRef`'s `fBits`~~ | ✅ `serialization/ref-variants`. `References.md` §10 had said both needed a second session or a second file; they do not, and the invariant 8.7 that named `kHasUUID` in its wording had never implemented it |

**Two findings came out of that case**, both from the independent reader
disagreeing with a real file once it stopped skipping 501 by byte count:

- **The version word in a 500/501/85/86/87 frame is not the constant 10.** It is
  `TStreamerInfo`'s class version in the writing ROOT, which was 8 before 5.26, 9
  until 6.35, and 10 only from 6.36.00 (`a5d03de7e67`, 2024-11-25). Of the 226
  files in the two corpora exactly **one** was written by 6.36 or later, so the
  real-world value is 9. `ElementTypes.md` §8.1 and `Collections.md` §2 now say
  so; the spec had hardcoded 10 in four places.
- **A `kStreamLoop` of `TString` is bare counted strings**, because
  `TString::Streamer` writes no frame wherever it appears. `TFormula::fExpr` is
  the real case, and `rootfile.py` was reading it as a framed object.

### 9.6 Structural, not a missing fixture

| Gap | Where | State |
|---|---|---|
| No checker decompresses, so nothing verifies a compressed payload's *contents* | `tools/rootfile.py` | ✅ done; zlib and lzma from the standard library, zstd on Python 3.14, LZ4 only with the `lz4` package, and a record whose codec is missing is reported as `NOT CHECKED` |
| `tools/rootfile.py` has no `TTree` support, so phase 5 fixtures will not be invariant-checked until it does | §4 | ✅ baskets, branches and leaves are read and checked, and `entry_spans` closes the entry → basket → byte range → value path |
| Semantic (`path`/`value`) assertions were dropped in favour of byte offsets; worth adding back as a complement | §3.2 | ☐ |
| **Four fixtures are not digest-portable between macOS and Linux**, and the causes are now identified — three of them, all different. Diagnosed by reproducing CI's exact digests in a `condaforge/miniforge3` container with ROOT 6.40.04 (the drift is libc++ vs libstdc++, **not** architecture: an arm64 container reproduced the x86_64 CI digests byte for byte) and diffing `tools/normalize.py --members` between the two. The standing guess — the order of entries in the `StreamerInfo` record — was **wrong**: that record is byte-identical in every case | §3.3, §9.7 | ✅ three of four fixed, the fourth exempted with a reason |

The three causes, each needing a different remedy:

| Fixture | The only field that differs | Why | Maskable? |
|---|---|---|---|
| `ttree/split-stl-toplevel`, `ttree/split-ptr-collection` | `TBranchElement::fCheckSum` — `66eb45ed` vs `01c8a81d`, and nothing else in the file | The branch's `fClassName` is an STL type (`vector<SHit>`, `vector<PHit*>`), and a checksum folds in each member's resolved type name, which the two standard libraries spell differently. No streamer info in the file records that checksum, so no other record moves with it | Yes — four fixed bytes |
| `serialization/pairs` | `TStreamerElement::fTitle` on the synthesised `pair<string,int>` members | libstdc++ carries doc comments on `std::pair`'s members and libc++ does not, so the titles are `"The first member"`/`"The second member"` on Linux and empty on macOS. Exactly the 33-byte growth: 35 bytes against 2 | **No** — it is a length change, and a mask cannot restore a length |
| `ttree/basket-embedded` | the embedded basket's `TKey::fDatime` at offset 859, four times over | `normalize.py` masks the `fDatime` of every *record* key. An embedded basket carries a whole `TKey` inside object data ([TBasket §4.1](spec/04-ttree/TBasket.md#41-the-embedded-layout)) and that one is not masked. Its value is a fixed instant rendered in **local time**: `2033-12-31 19:00:00` on a UTC−5 machine against `2034-01-01 00:00:00` in the container | Yes, and it should be: this is the existing datime mask not reaching far enough |

`fSize` also differs everywhere (`sizeof(std::map)` is 24 with libc++ and 48 with
libstdc++), which is what the existing mask is for, and it is not the cause of any
of these.

**Resolved as follows**, and verified by regenerating in the container and
comparing against the committed manifest:

- `tools/normalize.py` now masks an embedded basket's `fDatime` — **twice per
  basket**, because the raw buffer copy begins with the key all over again, which
  the first attempt missed and the byte diff caught.
- It also masks `TBranchElement::fCheckSum`, **but only when `fClassName` is an
  STL type**. For an ordinary class the checksum is stable across both standard
  libraries, and narrowing the mask that way costs no coverage: the recomputed
  manifest moved exactly three digests and left the other 44 untouched.
- `serialization/pairs` opts out of the digest with `digest = false` and a
  required `digest_reason`, printed on every run as `NO DIGEST`. It also has no
  `size`, for the same reason; `size` is now optional in `check_bytes.py`. Its 34
  byte assertions run everywhere and none of them touches `fTitle`.

The earlier workaround — making `ttree/basket` leaflist-only — is no longer
needed for this reason, though it has not been reverted; a split-branch `ttree/basket`
would now be portable.
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

#### What `TTree.md` added

Written 2026-09-15 with the corpus in hand rather than against it, so the
measurements above are what the document states. Three further findings:

| Found | Where |
|---|---|
| A tree's record need not be of class `TTree`. `TNtuple`, `TNtupleD` and `TChain` derive from it, and `check_invariants.py` was skipping such records outright because `trees()` compared the key's class name. Trees are now found through the base-class chain of the file's own streamer infos, and `ttree/ntuple` is the fixture | `TTree.md` §1, `rootfile.derives_from` |
| `fEntries` may disagree with the branches by design. `string-example.root`, an LHCb DST written by ROOT 6.30/02, has a tree with `fEntries` 0 and a branch holding 2 entries and 157 bytes. `TTree::SetEntries(-1)` warns about exactly this rather than refusing, so there is deliberately no invariant relating the two | `TTree.md` §3 |
| A reader gap: `Branch.io_bits` was always 0. `fIOFeatures` is a `kAny` member, not a base class, so `_named` does not flatten it and the lookup for `fIOBits` silently missed. Unused by any check, so it had gone unnoticed since `ttree/basket-iofeatures` was written | `rootfile._io_bits` |

**And one published number corrected.** `TBranch.md` §8 said `fIOFeatures` has been
in every branch "since ROOT 6.14". It is **6.12/02** — `be4f62946e3`, 2017-10-20,
first tagged `v6-12-02`, and the corpus has ROOT 6.12/04 files with `TBranch` v13
and `TTree` v20.

Nothing in the corpus has a non-zero `fNClusterRange`, a non-null `fAliases`,
`fTreeIndex`, `fFriends`, `fUserInfo` or `fBranchRef`, or a non-empty `fIndex`, so
`ttree/clusters` covers the first and the rest stay uncovered until
`Auxiliary.md`.

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

### 9.9 The CERN corpus — files ROOT wrote

Added 2026-09-15 from <https://root.cern/files/> and its `rootbench/`
subdirectory. `gen/cern/README.md` lists every file and why;
`tools/fetch_cern.py` fetches it; nothing is committed.

**Why a second corpus.** §9.8's weakness is provenance: uproot's regression suite
contains files uproot wrote, so a failure there is a lead that has to be traced to
a writer before it is evidence, and that ambiguity dominated the triage. Everything
here was written by ROOT and published by the ROOT team. It also reaches further
back — **ROOT 2.24/00 to 6.35/01**, about twenty-five years, where §9.8 starts at
4.00 and its two ROOT-4-labelled files turned out not to be ROOT's output at all.

Curated hard: the listing has ~40 near-identical `TGeoManager` geometry demos and
one is included. Tier `core` is **22 files, 5 MB**; tier `physics` adds two real
production trees, 27 MB. Each file covers something no fixture and no other listed
file does.

#### What it found

**Two more specification errors**, one on a file written by current ROOT and one on
the oldest file in the corpus. Both were the same mistake in different places:
stating an equality where ROOT tests an inequality.

| Was wrong | Now |
|---|---|
| `Compression.md` §1: a payload is compressed when `fNbytes - fKeyLen != fObjLen` | Compressed when `fObjLen > fNbytes - fKeyLen`. The `!=` form is `TFile::Map()`'s *display* test (`root/io/io/src/TFile.cxx:1616`); `TKey`'s *read* test is `>`, in all eight places it decides (`root/io/io/src/TKey.cxx:827` and seven more). A payload longer than `fObjLen` is stored raw and the reader takes the first `fObjLen` bytes (§1.1, erratum 5) |
| `FileHeader.md` invariant 5: `fEND == filesize` for a cleanly closed file | `fEND <= filesize`. ROOT compares the two only to detect truncation (`root/io/io/src/TFile.cxx:881-889`); bytes past `fEND` are outside the format and it never looks at them. `pippa.root` is cleanly closed by `FileHeader.md` §5.4's own signal — `fSeekFree` 391546 — and has **four** unexplained trailing bytes; `TFile::Open` reads it silently and reports `GetEND()` 391641 against `GetSize()` 391645 (§5.2, erratum 2) |

Found on `RNTuple.root`, 2.5 KB, ROOT 6.35/01: its `RBlob` at offset 586 has
`fNbytes` 789, `fKeylen` 34 and `fObjLen` **723**, so a 755-byte payload holds 723
bytes of data. `TFile::Map()` prints `CX = 0.96` and `TFile::Open` reads it without
complaint; a reader using `!=` finds the magic `05 00` and rejects the whole file.
The cause is in RNTuple's own key writer, which takes the on-disk and in-memory
lengths as independent arguments and says in a comment that the object length is
kept only "for seeing compression ratios in `TFile::Map()`"
(`root/tree/ntuple/src/RMiniFile.cxx:230-235`,
`root/tree/ntuple/src/RMiniFile.cxx:1437-1438`).

**Two reader gaps, the spec being right.**

- `coverage_probe.py` identified the container's own records by **class name**,
  where `check_invariants.py` had already been fixed to do it structurally. So
  every directory record written by a `TFile` subclass or by RNTuple's minimal
  writer — which leaves the class name of the keys list and the free list
  **empty** — was counted as blocked. Fixing it closed §9.8's
  `TStorageFactoryFile` row: container records over that corpus went 699 → 705,
  which is exactly the six it named.
- `needs_unspecified_streamer` walked the streamer-info graph with the raw
  `fTypeName`, so it dead-ended at the first object pointer: a `RooArgList*`
  member matches no info named `RooArgList`. That hid `RooAbsCollection` behind
  `RooFitResult` and produced 19 spurious failures.

**And a performance problem the corpus exposed.** `check_invariants.py` took
**675 s** on `SMHiggsToZZTo4L.root` — 42 549 entries across 32 branches — because
`TLeaf.md` 10.7 checks every entry, and per entry it re-decompressed the counter's
basket (copying the whole file buffer), re-parsed it, and linearly scanned every
record to find it. Caching those three brought it to ~250 s, and sampling large
baskets to **40 s**: above 256 entries the check now takes the first and last 32 and
a stride, printing `SAMPLED n basket(s)` so it is never silent. `--all-entries`
forces the exhaustive check, and both modes give 0 failures over the fixtures and
all 154 files of §9.8 — which is what justifies the default.

**Two more divergent classes, now named in the output rather than failing.**
`RooAbsCollection` (reached through `RooFitResult`) and `ROOT::RNTuple`, whose
`Streamer` calls `ReadClassBuffer` and then reads an 8-byte XXH3-64 checksum
*outside* the byte count (`root/tree/ntuple/src/RNTuple.cxx:25-49`) — which is
`spec/05-rntuple/` material and is why the anchor record has 8 bytes of slack.

#### The large files, without downloading them

root.cern serves `Accept-Ranges: bytes`. `gen/cern/LARGE.toml` records eight files
from 1.3 GB to 5.3 GB, and `tools/fetch_cern.py --headers` re-reads each one's
header and free-segment record — about 8 KB of traffic for 20 GB of files — and
checks every recorded field. **This is the only thing exercising the large-file
layout at all**, and it discharges most of §9.2:

| Confirmed | Evidence |
|---|---|
| The `+1000000` `fVersion` flag and `fUnits` 8 | six files, ROOT 5.19/03 to 6.23/01 |
| Offsets past 4 GB, where even an unsigned 32-bit reader fails | `lhcb2.root`, `fEND` 4 947 894 760 |
| The **large `TFree` form interleaved with the small one in one record**, which `FreeSegments.md` §2.1 requires per-entry sizing for | `volume.root`: 51 entries, **32** in the 18-byte form and 19 in the 10-byte form |
| `nfree` agrees with the parsed list, and the last entry always passes `fEND` | all eight, counts 1 to 1539 |
| The boundary from below: over 1 GB and *not* large format | `CMS_7250E9A5-….root` at 1.997 GB with `units` 4; `AOD.067184.big.pool_4.root` with **1539** small entries |
| A free record whose key class is a `TFile` subclass | `CMS_7250E9A5-….root`: `TStorageFactoryFile` |

`§9.2`'s first row — "the large `TFree` entry form, and `fLast` above 2000000000" —
is therefore **measured**, though still not asserted by a committed fixture, and
`LargeFiles.md` can now be written against something real.

#### One lead left open

`H1display.root` (ROOT 3.05/07) has a `TPad` whose `TVirtualPad` v2 base lists
**five** `kBase` elements, the last being `TQObject`. The file does carry a
`TQObject` streamer info — **with zero elements**, since every member of that class
is transient (`root/core/base/inc/TQObject.h:50-53`). Counting the bytes of the
`TVirtualPad` frame, `TObject` + `TAttLine` + `TAttFill` + `TAttPad` appear to
exhaust it, leaving `TQObject` contributing nothing at all, and the reader then
takes the following bytes for a version word.

So the open question is narrow: **what does a `kBase` element whose class has no
persistent members occupy on disk — nothing, or a bare framed version word?** If it
is nothing, that is a rule `StreamerDriven.md` should state, and it would follow
from the same place as §7's "a hand-written streamer's recorded info can be
fiction". Not diagnosed further; `TQObject` is named in the `NOT CHECKED` output
meanwhile, so nothing is hidden and nothing is assumed.

#### A second lead, found 2026-09-16

`aod_flushed.root` (ROOT 5.25/04) fails `StreamerDriven 10.1` on its
`TTreePerfStats` record: the decode runs off the end of the buffer, at an offset
of 3.2 GB in a 34 KB record, so it desynchronises early and never recovers. It is
**not** caused by anything in this session's work — confirmed by checking out the
previous commit and re-running.

What is established:

- The file carries its own `TTreePerfStats` info at **class version 1**, whose
  first element is a `kBase` for `TVirtualPerfStats`. That class declares
  `ClassDefOverride(TVirtualPerfStats, 0)`
  (`root/core/base/inc/TVirtualPerfStats.h:93`) and its info in the file has
  class version 0 with a single element, the `TObject` base at code 66.
- The class version really was 1 for years while the member list changed
  repeatedly — the omission ROOT fixed in `86728daacca` (2017-01-09, ROOT-8520),
  which jumped `ClassDef(TTreePerfStats, 1)` straight to 6. So a version-1 record
  may hold any of several schemas, which is precisely why the file carries its
  own info.
- Reading the payload from the byte count: `40 00 86 60 | 00 01` then the base.
  Taking `fReadaheadSize` to be the 256000 at offset 338 and working backwards,
  the base occupies **10 bytes** — exactly a `TObject` — with **no version word
  of its own**. Reading it with a version word puts `fTreeCacheSize` at
  −131072000, which is not a cache size.

So the narrow question is the same shape as the `H1display.root` lead above:
**what does a `kBase` element contribute when its class declares version 0?**
`Buffer.md` §4 predicts a version word of 0 followed by nothing; these bytes look
like nothing at all. `TStreamerBase::ReadBuffer` goes through `ReadClassBuffer`
(`root/core/meta/src/TStreamerElement.cxx`), which always reads a version word,
so if the ten-byte reading is right the write path must be diverging somewhere
this reading has not found. Not diagnosed further; the file is named in the
failure output, so nothing is hidden.

#### Standing result

`tools/check_invariants.py` over tier `all`: **24 files, 0 failures.** The probe:
1396 decoded, 264 container, 515 partial, 205 blocked, **0 no codec**. Of the
blocked, 197 are RooFit classes in the two `stressRooFit_*` files and the rest are
RNTuple's `RBlob` and anchor; the partial are overwhelmingly ROOT 2.x histogram
records in files that carry no streamer infos at all, which is
`StreamerDriven.md` §6's case rather than a gap. `--headers`: 8 files, 0 failures.

Both corpora together are now **178 files, 0 failures, ROOT 2.24/00 to 6.36/02.**

#### The `CS` codec, closed

The corpus initially reported **495 of 1759 non-container records** as "no codec" —
all of `pippa.root` and some of every file at ROOT 5.05 and below — because
`Compression.md` named the `CS` magic, called such files "rare but readable", and
never said what was inside a block. That looked like a research project into a
bespoke LZ77 and was written up here as a gap this project could not close cheaply.

**That was wrong, and by a wide margin.** `CS` is not a different algorithm from
`ZL`. Both are DEFLATE with method byte 8; they differ only in the **wrapper**.
`ZL` blocks go to `R__unzipZLIB`, which calls `inflateInit`, the zlib-wrapped entry
point (`root/core/zip/src/RZip.cxx:409-422`). `CS` blocks fall past every named
algorithm to ROOT's bundled inflate under the comment "Old zlib format"
(`root/core/zip/src/RZip.cxx:391-392`), and that function starts decoding blocks
with an empty bit buffer, consuming no header and checking no trailer
(`root/core/zip/src/ZInflate.c:1048-1090`). It is raw DEFLATE, RFC 1951.

In Python the whole codec is `zlib.decompressobj(-zlib.MAX_WBITS)`. All **468**
compressed records of `pippa.root` decompress with it, each producing exactly the
block header's declared size. Written up as `Compression.md` §3.1; the corpus now
reports **zero** "no codec" records.

The lesson is the cheaper one: the claim "rare but readable" was true, and had
been sitting in the document unverified for long enough that its cost was assumed
rather than measured.

#### And what that uncovered underneath

Decompressing `stock.root` (ROOT 4.00/07) exposed ten trees whose branches are
`TBranch` **class version 9**, and every one overran its byte count by exactly
`fMaxBaskets × 4`. The cause is a claim `TBranch.md` §13 had made since it was
written but nothing had ever demonstrated: at version 9 the *is present* flag byte
of `fBasketSeek` is a **width selector** — 2 means 8-byte values, any other
non-zero means 4-byte — regardless of the `Long64_t*` its streamer info declares
(`root/tree/tree/src/TBranch.cxx:3062-3066`). Reading it that way makes all ten
records parse to their byte count exactly.

Now byte-verified and written up as `TBranch.md` §13.1. `tools/rootfile.py` refuses
`TBranch` below version 10 rather than guessing, and says so by name. Writing the
legacy layouts is still §9.1's job, but it now has a reproducer instead of a
hypothesis.
