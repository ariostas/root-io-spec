# PLAN — ROOT I/O Specifications

Status: **draft for discussion**. Nothing below is implemented yet except the repo
skeleton and the pinned ROOT submodule.

## 1. Goal

Produce a complete, versioned, machine-checkable specification of the ROOT on-disk
formats, sufficient for a third party to implement a reader (and, where the format
allows, a writer) **without reading ROOT's C++ source**.

Non-goals: documenting ROOT's C++ API, its in-memory data structures, or its
build system. We document *bytes on disk* and the *algorithms* required to turn
those bytes into values.

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
root-io-specifications/
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
| `FileHeader.md` | The 64/100-byte header; `fVersion` encoding; the `+1000000` large-file flag and the field widening it implies |
| `Record.md` | `TKey` layout, `fNbytes`/`fObjLen`/`fKeyLen`, cycles, `fSeekKey` self-check, the "key of a key" for large files |
| `Directory.md` | `TFile`'s own record, `TDirectoryFile`, the keys list, `fSeekDir`/`fSeekParent`/`fSeekKeys`, nested directories |
| `FreeSegments.md` | `TFree` list, the sentinel free segment past EOF, gaps |
| `Compression.md` | The 9-byte block header, the `ZL`/`XZ`/`L4`/`ZS`/`CS` magics, multi-block payloads, the LZ4 XXH64 trailer, `fCompress` encoding (`100*algorithm + level`), and which records are never compressed |
| `LargeFiles.md` | Everything that changes past 2 GB, collected in one place |

`Compression.md` is called out separately because the old docs are actively wrong
here and every implementer has to rediscover the block header by hand.

### 2.3 `spec/02-serialization/` — the object layer

This is the core of the repo and the answer to "how do we handle custom classes".

| File | Contents |
|---|---|
| `Buffer.md` | Byte counts (`kByteCountMask = 0x40000000`), the version word and `kByteCountVMask = 0x4000`, `ReadVersion`'s "no byte count in old files" backup path, class tags (`kNewClassTag = 0xFFFFFFFF`, `kClassMask = 0x80000000`), the buffer object/class map and `kMapOffset = 2`, object deduplication, `kNullTag` |
| `StreamerInfo.md` | The `StreamerInfo` key, the `TList` of `TStreamerInfo`, and the byte layout of `TStreamerInfo` + every `TStreamerElement` subclass. **This is the bootstrap set: these classes cannot be read using streamer info, so a reader must hardcode them.** |
| `StreamerDriven.md` | The normative algorithm: given a `TStreamerInfo` and a byte range, produce a value tree |
| `ElementTypes.md` | The complete `EReadWrite` type-code table → exact on-disk bytes |
| `Collections.md` | STL containers, collection proxies, object-wise vs member-wise streaming |
| `SchemaEvolution.md` | Class version 0, checksums, `TSchemaRuleSet`, conversion/artificial/cache/skip elements, emulated classes |
| `References.md` | `TProcessID`, `TRef`, `TRefArray`, `TObject::kIsReferenced` and the extra `fPID` word |

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
immediately: a version-0 class is written with a **checksum instead of a version
number**, so a reader that assumes "version word is a version" breaks on `TH1L`
and not on `TH1D`. That rule is stated once in `SchemaEvolution.md` and cross-
referenced from every family table that has a version-0 row.

Planned families (initial pass, from `ClassDef` inventory of the pinned submodule):

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
| `TBranch.md` | v13, `fBasketBytes`/`fBasketEntry`/`fBasketSeek` arrays, the "one basket lives inside the TTree record" rule, branches in separate files |
| `TBranchElement.md` | `fID`, `fType` (−1,0,1,2,3,4,41…), `fStreamerType`, `fClassName`/`fParentName`/`fClonesName`, and how `fType` selects the read algorithm |
| `TLeaf.md` | `TLeaf` family, `fLen`/`fLenType`/`fOffset`/`fIsRange`/`fIsUnsigned`, leaf counts, `TLeafC` strings, `TLeafElement`, `TLeafD32`/`TLeafF16` |
| `TBasket.md` | The basket record, `fNevBufSize` sign trick → `fIOBits`, the `flag >= 80` "generate offsets" path, `flag % 10 == 2`, entry-offset arrays and the offset/size conversion, displacement arrays, `fLast` |
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

- `Bootstrap.md` — the minimal hardcoded class set, in dependency order.
- `ReaderChecklist.md` — an implementation checklist for a new reader.
- `Pitfalls.md` — a curated list of the things that have historically bitten
  implementers, each linking to the normative section.
- `Glossary.md`.
- `Bibliography.md` — the old ROOT docs, the user's guide, prior art
  (uproot, groot, UnROOT.jl, root-io, jsroot) with links.

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

One case = one file = one specific thing being exercised. Cases are named
`<class>-<variant>-<qualifier>`, e.g. `th1-th1d-basic`, `th1-th1d-varbins`,
`th1-th1l-v0checksum`, `ttree-branchelement-split2-vectorint`.

### 3.2 `case.yaml`

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

- Commit the generated files (each is 2–20 kB; the whole corpus should stay well
  under ~10 MB — no LFS needed).
- `tools/normalize.py` computes a digest over the file with the datime and UUID
  fields masked; CI regenerates and compares the *normalized* digest, so genuine
  format changes are caught while timestamps are not.
- Fixed RNG seeds and fixed literal data in every `gen.C`. No `gRandom` without an
  explicit `SetSeed`.

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
- The generated legacy files are committed under `data/legacy/<rootversion>/`.
- Where a version is unreachable, we say so explicitly in the class document rather
  than guessing, and fall back on the ROOT git history for the layout.
- We should also catalogue (not vendor) the existing public corpora —
  `scikit-hep-testdata`, `root.cern/files/` — and map them onto our case IDs.

## 4. Tooling and CI

| Tool | Purpose |
|---|---|
| `tools/inventory.py` | Parse every `ClassDef*` in the submodule → the authoritative class/version inventory. Feeds the coverage matrix. |
| `tools/check_versions.py` | Fail if a class document's version matrix disagrees with the submodule's `ClassDef`. This is what keeps the spec from rotting. |
| `tools/dump_streamerinfo.C` | ROOT macro wrapping `TFile::ShowStreamerInfo()` + `TClass::GetCheckSum()` into machine-readable JSON, used to generate and verify the member tables. |
| `tools/sync_rntuple.py` | Re-copy the upstream RNTuple spec; fail on drift. |
| `tools/normalize.py` | Timestamp/UUID-masked digests for fixtures. |
| `tools/generate.py` | Run every `gen.C`, produce `data/`, validate against `case.yaml`. |
| `tools/coverage.py` | Render `spec/03-classes/index.md` coverage table from the inventory + what is actually documented. |

CI (GitHub Actions, ROOT from conda-forge):

1. Regenerate all fixtures, compare normalized digests.
2. `check_versions.py` against the pinned submodule.
3. `sync_rntuple.py` drift check.
4. Markdown link check across `spec/`.
5. Optionally: a minimal pure-Python reference reader in `tools/refreader/` that
   implements only what the spec says and must read every fixture. This is the
   strongest possible check that the spec is complete — if the reference reader
   needs a fact that isn't written down, the spec has a hole. Worth doing, but
   scope it as a later phase.

## 5. Phasing

**Phase 0 — skeleton** (done in this session)
Repo initialized, ROOT pinned as a submodule at `v6-40-04`, this plan.

**Phase 1 — foundations**
`00-conventions.md`, all of `01-container/`, `02-serialization/Buffer.md` and
`StreamerInfo.md`. Fixture generator harness + first few cases. `inventory.py`.
Deliverable: enough to locate and decompress any object in any ROOT file.

**Phase 2 — the generic object layer**
`StreamerDriven.md`, `ElementTypes.md`, `Collections.md`, `SchemaEvolution.md`,
`References.md`, `99-appendix/Bootstrap.md`. Fixtures for every element type code
and every collection shape.
Deliverable: enough to read any user-defined class.

**Phase 3 — the bootstrap classes**
The ~30 regime-3 classes in `03-classes/`, with `check_versions.py` wired up.
Deliverable: enough to read `TFile` internals and the standard containers.

**Phase 4 — standard classes**
The rest of `03-classes/` by family: hist → graf → func → math → misc.

**Phase 5 — TTree**
All of `04-ttree/`, with the full split/type matrix of fixtures. Largest single
phase; likely to want its own sub-plan.

**Phase 6 — RNTuple audit**
Import, sync tooling, and the field-by-field spec-vs-implementation audit;
upstream PRs for anything found.

**Phase 7 — legacy versions and reference reader**
`gen/legacy/`, historical fixtures, and (optionally) the pure-Python reference
reader as the completeness check.

Phases 1–3 are sequential. Phase 4, 5 and 6 are independent of each other once
phase 2 is done.

## 6. Open questions

1. **Scope of "every standard class".** The `ClassDef` inventory of the modules we
   care about is ~400 classes, but many are GUI/painter classes that never appear in
   a file, or are transient. Proposal: define the scope as "classes reachable in a
   `TFile` written by a non-GUI ROOT session", seed it from the inventory, and mark
   the rest explicitly out of scope rather than silently omitting them. `TGeo*` is
   the biggest judgement call — large, self-contained, genuinely used in files.
2. **Normative status.** Do we claim to be normative, or descriptive-of-6.40.04?
   Proposal: descriptive, with the pinned submodule as the tiebreaker, and an
   explicit errata process for where ROOT's behaviour looks like a bug.
3. **Upstreaming.** How much of this should be PRs against `root/io/doc/`? The old
   docs are so stale that replacing them wholesale may be more welcome than
   patching. Worth asking the ROOT I/O team early — their buy-in changes whether
   this is *the* spec or *a* spec.
4. **Writer support.** Do we specify enough to *write* valid files, or only to read
   them? Writing requires the free-list algorithm, key placement, and streamer-info
   emission. Proposal: read is the requirement, write is documented where it is
   cheap to do so, and explicitly marked where it is not.
5. **Fixture corpus size.** Committing binaries to a spec repo is a tradeoff. The
   alternative is generating in CI and publishing as release artifacts. Proposal:
   commit the small core corpus, publish the large/legacy corpus as releases.

## 7. Immediate next steps

1. Agree on the layout in §2 and the three structural decisions (families,
   version matrices, the serialization-layer split).
2. Resolve open questions 1 and 4 — they change the size of the project.
3. Write `spec/00-conventions.md` and `spec/01-container/FileHeader.md` as the
   style prototype, with one fixture, and review the format before scaling out.
