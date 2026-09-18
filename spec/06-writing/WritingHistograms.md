# Writing histograms

A `TH1F` or `TH1D`, member by member, at the current class version: what each
field has to contain for ROOT to report the right entries, mean, bin contents and
bin errors, and what is free.

Prerequisites: [Writing a file](WritingFiles.md),
[Writing an object](WritingObjects.md). The reading side is the generic algorithm
of [Streamer-driven reading](../02-serialization/StreamerDriven.md) — a histogram
needs no hand-written reader — plus [TArray](../03-classes/TArray.md) for its
last member.

## 1. Why this document exists, and how far it is checked

A histogram is the most common object in a ROOT file, and it is *almost* fully
described by its streamer info: the generic algorithm reads one with no special
knowledge. What a writer needs beyond that is the **content** of every field,
including a dozen that have no obvious value, and the streamer infos themselves —
which a reader gets from the file and a writer has to produce.

The whole of this document is checked by byte comparison against ROOT:

| What | Bytes | Where |
|---|---|---|
| a `TH1F` record | 596 | `tools/test_write.py` |
| a `TH1D` record with variable bin edges | 651 | same |
| the `StreamerInfo` record — fifteen infos, every element and checksum | 9628 | same |

`data/classes/histogram.root` is the ROOT-written original and
`data/written/histogram.root` the copy this project produced; every
object-bearing record in the two is identical, and the files differ only in the
directory record, the key timestamps and the offsets that follow.

## 2. The chain

A `TH1F` is a `TH1` and a `TArrayF`, with nothing of its own:

```
TH1F            class version 3
├── TH1         class version 8
│   ├── TNamed        1
│   │   └── TObject   1
│   ├── TAttLine      2
│   ├── TAttFill      2
│   ├── TAttMarker    3
│   ├── fXaxis, fYaxis, fZaxis: TAxis   10
│   │   ├── TNamed    1
│   │   └── TAttAxis  4
│   ├── … TH1's own members, §3
│   └── fFunctions: TList   5
└── TArrayF      fN and the values, no version word
```

`TH1D` is the same with `TArrayD`, and **the same class version, 3**. Class
versions, all verified against `ClassDef` by `tools/check_versions.py`:

| Class | Version | Cite |
|---|---|---|
| `TH1F`, `TH1D` | 3 | `root/hist/hist/inc/TH1.h:902`, `:949` |
| `TH1` | 8 | `root/hist/hist/inc/TH1.h:693` |
| `TAxis` | 10 | `root/hist/hist/inc/TAxis.h:179` |
| `TAttAxis` | 4 | `root/core/base/inc/TAttAxis.h:68` |
| `TNamed` | 1 | `root/core/base/inc/TNamed.h:60` |
| `TAttLine` | 2 | `root/core/base/inc/TAttLine.h:51` |
| `TAttFill` | 2 | `root/core/base/inc/TAttFill.h:46` |
| `TAttMarker` | 3 | `root/core/base/inc/TAttMarker.h:55` |
| `TList` | 5 | `root/core/cont/inc/TList.h:115` |

**`TH1F` and `TH1D` have generated streamers; `TH1` does not.**
`TH1::Streamer` is hand-written and delegates above version 2
(`root/hist/hist/src/TH1.cxx:7081`), so at version 8 the bytes are exactly what
the streamer info describes — but on the read side it then does fixups no
generated streamer would: it clears `kMustCleanup`, sets each axis's transient
parent pointer, and re-parents every `TF1` in `fFunctions`
(`root/hist/hist/src/TH1.cxx:7083-7091`). None of that is in the file, and none
of it concerns a writer: the write path is a plain `WriteClassBuffer`
(`root/hist/hist/src/TH1.cxx:7137`).

`TH2F` and `TProfile` *are* hand-written in both directions
(`root/hist/hist/src/TH2.cxx:3977`, `root/hist/hist/src/TProfile.cxx:1820`) and
insert their own members after the `TH1` base; they are out of scope here and §7
says what they add.

## 3. `TH1` at version 8

In streamed order. **Kind** is fixed (one value is correct), derived (from
something else) or free (ROOT's value given for reference).

| Member | Type | Value | Kind |
|---|---|---|---|
| `TNamed` | framed | the histogram's name and title; `fBits` carries `kMustCleanup` (8) in a ROOT-written file | free |
| `TAttLine` | framed | 602, 1, 1 | free |
| `TAttFill` | framed | 0, 1001 | free |
| `TAttMarker` | framed | 1, 1, 1.0f | free |
| `fNcells` | `i32` | `nbins + 2` | **fixed** |
| `fXaxis` | `TAxis` | §4 | — |
| `fYaxis`, `fZaxis` | `TAxis` | present even in a 1-D histogram, each with `fNbins` 1 and the range 0…1 | **fixed** |
| `fBarOffset` | `i16` | 0 | free |
| `fBarWidth` | `i16` | 1000 | free |
| `fEntries` | `f64` | the number of fills, out-of-range ones included | derived — §5 |
| `fTsumw` | `f64` | Σ w over in-range fills | derived |
| `fTsumw2` | `f64` | Σ w² over in-range fills | derived |
| `fTsumwx` | `f64` | Σ w·x | derived |
| `fTsumwx2` | `f64` | Σ w·x² | derived |
| `fMaximum` | `f64` | **-1111** unless a ceiling was set explicitly | **fixed** — §6 |
| `fMinimum` | `f64` | **-1111** likewise | **fixed** |
| `fNormFactor` | `f64` | 0 | free |
| `fContour` | `TArrayD` | empty: an `i32` 0 and nothing else | free |
| `fSumw2` | `TArrayD` | empty, or one entry per cell — §5.1 | derived |
| `fOption` | counted string | empty | free |
| `fFunctions` | `TList` | **streamed in place**, not as a pointer slot — §3.1 | **fixed** |
| `fBufferSize` | `i32` | 0 | free |
| `fBuffer` | counted pointer | a single `0x00` flag byte when absent | **fixed** |
| `fBinStatErrOpt` | `i32` | 0, `kNormal` | free |
| `fStatOverflows` | `i32` | 2, `kNeutral` | free |

Transient, and therefore not in the record at all: `fDirectory`, `fDimension`,
`fIntegral`, `fPainter` (`root/hist/hist/inc/TH1.h:170-173`). They sit **between**
`fBuffer` and `fBinStatErrOpt` in the declaration, so a writer walking the header
must skip them without disturbing the order of what remains.

`fBuffer` is not transient, which is easy to get wrong: it is a counted array,
`Double_t *fBuffer; //[fBufferSize]` (`root/hist/hist/inc/TH1.h:169`), so it is
written as a flag byte and then `fBufferSize` doubles
([Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer)). A
histogram that has been filled normally has `fBufferSize` 0 and one zero byte.

### 3.1 `fFunctions` is streamed in place

It is declared `TList *fFunctions; //->` (`root/hist/hist/inc/TH1.h:167`), and the
`->` means "this pointer is never null, stream the object itself". So there is
**no class record and no pointer slot** — just a framed `TList` at version 5:
a byte count, the version, a `TObject` base, an empty `fName`, and a count of 0.
Twenty-one bytes for an empty list. A writer that emits a pointer slot instead
adds a class record ROOT does not expect, and a writer that emits four zero bytes
for "null" makes ROOT read the `TList`'s version word out of the following
member.

ROOT leaves `fBits` of that list at `0x00014000`. A reader ignores it; matching it
is what makes the record comparable.

## 4. `TAxis` at version 10

| Member | Type | Value | Kind |
|---|---|---|---|
| `TNamed` | framed | `xaxis`, `yaxis` or `zaxis`, with an empty title | free, but ROOT always writes these three |
| `TAttAxis` | framed | §4.1 | free |
| `fNbins` | `i32` | the bin count, excluding under- and overflow | **fixed** |
| `fXmin`, `fXmax` | `f64` | the range; for a variable-width axis, the first and last edge | **fixed** |
| `fXbins` | `TArrayD` | empty for fixed-width bins, `nbins + 1` edges otherwise | **fixed** |
| `fFirst`, `fLast` | `i32` | 0, meaning "no display range" | free |
| `fBits2` | `u16` | 0 | free |
| `fTimeDisplay` | `u8` | 0 — **one byte**, not four | **fixed** |
| `fTimeFormat` | counted string | empty | free |
| `fLabels` | pointer slot | null: four zero bytes | free |
| `fModLabs` | pointer slot | null | free |

`fParent` is transient (`root/hist/hist/inc/TAxis.h:44`) and is restored by
`TH1::Streamer` on read, so it is not in the record.

**`fXbins` is the only way a non-uniform axis is expressible**, and it must hold
exactly `nbins + 1` edges. With it present, `fXmin` and `fXmax` must agree with
the first and last edge.

### 4.1 `TAttAxis`, and why the three axes differ

Eleven members inside one framed record: `fNdivisions` (`i32`), `fAxisColor`,
`fLabelColor`, `fLabelFont` (`i16`), `fLabelOffset`, `fLabelSize`, `fTickLength`,
`fTitleOffset`, `fTitleSize` (`f32`), `fTitleColor`, `fTitleFont` (`i16`) —
declaration order, `root/core/base/inc/TAttAxis.h:21-31`. Thirty-four bytes.

Everything in it comes from `gStyle` and nothing is required. ROOT's values are
510, 1, 1, 42, 0.005, 0.035, 0.03, 1.0, 0.035, 1, 42 — **except that the Y axis's
`fTitleOffset` is 0**, where X and Z carry 1.0. So the three attribute blocks in a
ROOT-written histogram are not identical, and a writer that copies one block three
times produces a file that differs from ROOT's in four bytes and is in no way
wrong.

## 5. The statistics are not derivable from the bin contents

This is the substantive point of the document. `fEntries` and the four sums are
what ROOT reports as the entry count, the mean and the RMS; they are accumulated
per **fill**, from the true x, and once the data is binned that information is
gone:

- `GetEntries()` returns `fEntries` — the number of fills, including the ones that
  landed outside the range. The sum of the bin contents is a different number
  whenever a fill went out of range or carried a weight.
- `GetMean()` is `fTsumwx / fTsumw`, so a writer that leaves the sums at 0 has a
  histogram with correct bins and a mean of nan.
- `fTsumw2` is Σ of squared **weights**, not Σ of squared bin contents.

A writer starting from binned data can only approximate, and should say so.
`tools/rootwrite.py` uses bin centres, takes `fTsumw2` from `fSumw2` when it has
it, and assumes unit weights otherwise. For the fixture's `TH1F` — unit weights,
fills at bin centres — that reproduces ROOT's five values exactly. For the `TH1D`,
filled at 0.5 with weight 2 and at 5.0 with weight 0.5 in bins of width 1 and 6,
it does not: `fEntries` comes out 2.5 rather than 2, and the x moments are the
bin-centre ones. Both records are byte-identical to ROOT's only because the case
supplies the statistics.

### 5.1 `fSumw2` is what bin errors come from

Empty, or exactly `fNcells` entries. `GetBinError(i)` is `sqrt(fSumw2[i])` when
the array is populated and `sqrt(fBinContent(i))` when it is not — so an empty
array is not "no errors", it is "Poisson errors", which is right for unweighted
data and wrong for weighted.

ROOT populates it on the first **weighted** `Fill`, with no `Sumw2()` call, which
is why `data/classes/histogram.root`'s second histogram has it and the first
needed an explicit call.

## 6. `-1111` is a sentinel, not a value

`fMaximum` and `fMinimum` are **-1111** in every histogram whose plotting range
was not set by hand. It means "compute it from the data"; a writer that leaves
them at 0 produces a histogram ROOT draws with a ceiling and a floor of zero, and
`GetMaximumStored()` returns 0 rather than the sentinel.

The same number appears in `TF1`'s `fXmin`/`fXmax`, and it is ROOT's general
"unset" marker for a `Double_t` whose natural range includes 0.

## 7. What `TH2F` and `TProfile` add

Out of scope, and one paragraph so the shape is known. Both have hand-written
streamers in both directions, and both delegate above version 2.

- **`TH2`** (version 5, `root/hist/hist/inc/TH2.h:137`) inserts four doubles after
  the `TH1` base — `fScalefactor`, `fTsumwy`, `fTsumwy2`, `fTsumwxy`
  (`root/hist/hist/inc/TH2.h:33-36`) — and `TH2F` (version 4) then carries a
  `TArrayF` of `(nx + 2) × (ny + 2)` cells.
- **`TProfile`** (version 7, `root/hist/hist/inc/TProfile.h:139`) sits on `TH1D`
  and adds `fBinEntries` (`TArrayD`), `fErrorMode` (`i32`), `fYmin`, `fYmax`,
  `fTsumwy`, `fTsumwy2` and `fBinSumw2` (`root/hist/hist/inc/TProfile.h:39-46`),
  with `fScaling` transient between `fYmax` and `fTsumwy`.

## 8. The streamer infos

Fifteen classes, and a writer that wants its histograms readable by anything but
ROOT has to emit every one:

```
TH1F  TH1  TNamed  TObject  TAttLine  TAttFill  TAttMarker  TAxis  TAttAxis
THashList  TList  TSeqCollection  TCollection  TString  TH1D
```

That is ROOT's own order — registration order, not alphabetical — and
`tools/rootwrite.py` reproduces it. Four things in the list are not obvious:

- **`THashList`, `TList`, `TSeqCollection` and `TCollection` are there** although
  a histogram with no labels and no functions contains no collection data. They
  arrive because a **null** object pointer still forces its class's info to be
  written (`root/io/io/src/TStreamerInfo.cxx:3448`, reached from
  `root/io/io/src/TBufferFile.cxx:2456-2463`), and `fLabels` is a `THashList *`.
- **`TString`'s info has zero elements.** It is written, and it teaches a reader
  nothing; the encoding is
  [Conventions §5.1](../00-conventions.md#51-counted-string).
- **No `TArray` info is written at all**, for `TArrayF`, `TArrayD` or `TArray`
  itself, because their streamers are hand-written and nothing marks them
  ([Writing an object §7.2](WritingObjects.md#72-which-classes-need-an-info)).
  Their **checksums** are still needed, as the `fBaseCheckSum` of `TH1F` and
  `TH1D`, so a writer has to compute them from element lists it never emits.
- **Two checksums cannot be computed from an element list at all.**
  `THashList` and `TSeqCollection` are class version 0, so their infos list only
  their bases while their checksums fold their members
  ([StreamerInfo §11.2](../02-serialization/StreamerInfo.md#112-what-cannot-be-recomputed)).
  A writer must carry `0xcc7e49c1` and `0xfc6c3bc6` as constants —
  `tools/rootwrite.py` has them in `KNOWN_CHECKSUMS`, and they are the only two
  magic numbers in the histogram path.

`TH1`'s own checksum, `0x1c3740c4`, *is* computable, but only with the enum rule:
`fBinStatErrOpt` and `fStatOverflows` each fold an extra 1
([StreamerInfo §11.1](../02-serialization/StreamerInfo.md#111-an-enum-member-is-recognisable-and-it-changes-the-value)).

## 9. Invariants

1. `fNcells == fXaxis.fNbins + 2` for a 1-D histogram, and the `TArray` base's
   `fN` equals `fNcells`.
2. `fSumw2` is empty or has exactly `fNcells` entries; likewise `fBinEntries` and
   `fBinSumw2` in a `TProfile`.
3. `fXbins` is empty or has exactly `fNbins + 1` entries, and when non-empty its
   first and last entries are `fXmin` and `fXmax`.
4. `fYaxis` and `fZaxis` are present, with `fNbins` 1 in a 1-D histogram.
5. `fEntries >= 0`, and `fTsumw <= fEntries` when every weight is 1.
6. `fBufferSize` is 0 **iff** `fBuffer`'s flag byte is 0.
7. Every class version word in the chain matches §2's table.

1, 2, 3, 4 and 6 are checked for the written files by `tools/check_write.py`
through `tools/rootfile.py`; 7 is checked against `ClassDef` for every class in
§2's table by `tools/check_versions.py`.

## 10. Reference files

| File | What it is |
|---|---|
| `data/classes/histogram.root` | ROOT's: a `TH1F` with fixed bins and `Sumw2`, a `TH1D` with variable edges and weighted fills, and the fifteen infos. 73 assertions |
| `data/written/histogram.root` | this project's, holding the same two histograms. Every object-bearing record is byte-identical to ROOT's |
| `data/classes/tarray-histogram.root` | a `TH2F` inside a `TTree` branch, which is what makes a concrete `TArray` info appear |
