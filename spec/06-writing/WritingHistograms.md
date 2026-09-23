# Writing histograms

A `TH1F`, `TH1D`, `TH2F`, `TH2D` or `TProfile`, member by member, at the current
class version: what each field has to contain for ROOT to report the right
entries, mean, bin contents and bin errors, and what is free.

Prerequisites: [Writing a file](WritingFiles.md),
[Writing an object](WritingObjects.md). The reading side is the generic algorithm
of [Streamer-driven reading](../02-serialization/StreamerDriven.md) — a histogram
needs no hand-written reader — plus [TArray](../03-classes/TArray.md) for its
last member.

## 1. Why this document exists, and how far it is checked

A histogram is the most common object in a ROOT file, and its streamer info
describes it almost completely: the generic algorithm reads one with no special
knowledge. A writer also needs the content of every field, including a dozen that
have no obvious value, and the streamer infos themselves, which a reader gets from
the file and a writer has to produce.

All of this document is checked by byte comparison against ROOT. Eight records,
in two pairs of files:

| What | Bytes | From |
|---|---|---|
| a `TH1F` record | 596 | `data/classes/histogram.root` |
| a `TH1D` record with variable bin edges | 651 | same |
| the `StreamerInfo` record — fifteen infos, every element and checksum | 9628 | same |
| a `TH2F` record | 817 | `data/classes/th2-profile.root` |
| a `TH2D` record with variable edges on **both** axes | 887 | same |
| a `TProfile` record | 708 | same |
| a `TProfile` with a Y range and a populated `fBinSumw2` | 713 | same |
| its `StreamerInfo` record — eighteen infos and the `listOfRules` ROOT appends ([§8.6](#86-root-appends-a-listofrules-a-writer-cannot-use)) | 11789 | same |

Each ROOT-written file has a counterpart this project produced —
`data/written/histogram.root` and `data/written/th2-profile.root` — and
`tools/test_write.py` asserts every comparison above. Outside those records the
files differ in the file's own name, title and UUIDs, in the key timestamps, and
in the offsets that a longer title shifts.

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

`TH1D` is the same with `TArrayD`, and **the same class version, 3**. A `TH2F`
inserts one more link and a `TProfile` sits a level lower:

```
TH2F            class version 4          TProfile        class version 7
├── TH2               5                  ├── TH1D              3
│   ├── TH1           8, as above        │   ├── TH1           8, as above
│   └── fScalefactor, fTsumwy,           │   └── TArrayD  sum(w*y) per cell
│       fTsumwy2, fTsumwxy   §7.2        ├── fBinEntries, fErrorMode, fYmin,
└── TArrayF      (nx+2)*(ny+2) cells         fYmax, fTsumwy, fTsumwy2,
                                             fBinSumw2            §8.1
```

Every class version in all three chains is tabulated in §11, where
`tools/check_versions.py` checks it against `ClassDef`.

**`TH1F` and `TH1D` have generated streamers; `TH1` does not.**
`TH1::Streamer` is hand-written and delegates above version 2
(`root/hist/hist/src/TH1.cxx:7083-7084`), so at version 8 the bytes are what the
streamer info describes. On the read side it then does fixups no generated
streamer would: it clears `kMustCleanup`, sets each axis's transient parent
pointer, and re-parents every `TF1` in `fFunctions`
(`root/hist/hist/src/TH1.cxx:7083-7091`). None of that is in the file, and none
of it concerns a writer: the write path is a plain `WriteClassBuffer`
(`root/hist/hist/src/TH1.cxx:7139`).

`TH2`, `TH2F`, `TH2D` and `TProfile` are hand-written in both directions too, and
all four delegate above the same version, 2; §7 and §8 have the citations. Each
of them inserts its own members after the `TH1` base rather than around it, which
is why they need procedures of their own.

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
| `fMaximum` | `f64` | **-1111** unless a ceiling was set explicitly | free, with constraints — the default is mandatory, §6 |
| `fMinimum` | `f64` | **-1111** likewise | free, with constraints — as `fMaximum` |
| `fNormFactor` | `f64` | 0 | free |
| `fContour` | `TArrayD` | empty: an `i32` 0 and nothing else | free |
| `fSumw2` | `TArrayD` | empty, or one entry per cell — §5.1 | derived |
| `fOption` | counted string | empty | free |
| `fFunctions` | `TList` | **streamed in place**, not as a pointer slot — §3.1 | **fixed** framing; an empty list is the ordinary case |
| `fBufferSize` | `i32` | 0 | free |
| `fBuffer` | counted pointer | a single `0x00` flag byte when absent | **fixed** |
| `fBinStatErrOpt` | `i32` | 0, `kNormal` | free |
| `fStatOverflows` | `i32` | 2, `kNeutral` | free |

Transient, and therefore not in the record at all: `fDirectory`, `fDimension`,
`fIntegral`, `fPainter` (`root/hist/hist/inc/TH1.h:170-173`). They sit between
`fBuffer` and `fBinStatErrOpt` in the declaration, so a writer walking the header
must skip them without disturbing the order of the rest.

`fBuffer` is easy to mistake for transient, but it is a counted array,
`Double_t *fBuffer; //[fBufferSize]` (`root/hist/hist/inc/TH1.h:169`), so it is
written as a flag byte and then `fBufferSize` doubles
([Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer)). A
histogram that has been filled normally has `fBufferSize` 0 and one zero byte.

### 3.1 `fFunctions` is streamed in place

It is declared `TList *fFunctions; //->` (`root/hist/hist/inc/TH1.h:167`), and the
`->` means "this pointer is never null, stream the object itself". There is
therefore **no class record and no pointer slot**, only a framed `TList` at
version 5: a byte count, the version, a `TObject` base, an empty `fName`, and a
count of 0, twenty-one bytes for an empty list. A writer that emits a pointer slot
instead adds a class record ROOT does not expect, and a writer that emits four
zero bytes for "null" makes ROOT read the `TList`'s version word out of the
following member.

ROOT leaves `fBits` of that list at `0x00014000`. A reader ignores it; a writer
matches it only to make the record byte-comparable with ROOT's.

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

`fParent` is transient (`root/hist/hist/inc/TAxis.h:44`) and `TH1::Streamer`
restores it on read, so it is not in the record.

`fXbins` is the only way to express a non-uniform axis, and it must hold exactly
`nbins + 1` edges. When it is present, `fXmin` and `fXmax` must agree with the
first and last edge.

### 4.1 `TAttAxis`, and why the three axes differ

One framed record of eleven members and thirty-four bytes, in declaration order
(`root/core/base/inc/TAttAxis.h:21-31`): `fNdivisions` (`i32`), `fAxisColor`,
`fLabelColor`, `fLabelFont` (`i16`), `fLabelOffset`, `fLabelSize`, `fTickLength`,
`fTitleOffset`, `fTitleSize` (`f32`), `fTitleColor`, `fTitleFont` (`i16`).

Everything in it comes from `gStyle` and nothing is required. ROOT's values are
510, 1, 1, 42, 0.005, 0.035, 0.03, 1.0, 0.035, 1, 42, **except that the Y axis's
`fTitleOffset` is 0** where X and Z have 1.0. The three attribute blocks in a
ROOT-written histogram are therefore not identical. A writer that copies one block
three times produces a file that differs from ROOT's in four bytes and is not
wrong.

## 5. The statistics are not derivable from the bin contents

`fEntries` and the four sums are what ROOT reports as the entry count, the mean
and the RMS. They are accumulated per **fill**, from the true x, and that
information is lost once the data is binned:

- `GetEntries()` returns `fEntries`, the number of fills, including those that
  landed outside the range. The sum of the bin contents differs from it whenever
  a fill went out of range or carried a weight.
- `GetMean()` is `fTsumwx / fTsumw`, so a writer that leaves the sums at 0 has a
  histogram with correct bins and a mean of nan.
- `fTsumw2` is Σ of squared **weights**, not Σ of squared bin contents.

A writer starting from binned data can only approximate, and should say so.
`tools/rootwrite.py` uses bin centres, takes `fTsumw2` from `fSumw2` when it has
it, and assumes unit weights otherwise. For the fixture's `TH1F` (unit weights,
fills at bin centres) that reproduces ROOT's five values exactly. For the `TH1D`,
filled at 0.5 with weight 2 and at 5.0 with weight 0.5 in bins of width 1 and 6,
it does not: `fEntries` comes out 2.5 rather than 2, and the x moments are the
bin-centre ones. Both records are byte-identical to ROOT's only because the case
supplies the statistics.

### 5.1 `fSumw2` is what bin errors come from

Empty, or exactly `fNcells` entries. `GetBinError(i)` is `sqrt(fSumw2[i])` when
the array is populated and `sqrt(fBinContent(i))` when it is not. An empty array
therefore means Poisson errors, not "no errors", which is right for unweighted
data and wrong for weighted.

ROOT populates it on the first **weighted** `Fill`, with no `Sumw2()` call. That
is why `data/classes/histogram.root`'s second histogram has it and the first
needed an explicit call.

## 6. `-1111` is a sentinel, not a value

`fMaximum` and `fMinimum` are **-1111** in every histogram whose plotting range
was not set by hand, the value `TH1`'s constructors assign
(`root/hist/hist/src/TH1.cxx:640-641`, `root/hist/hist/src/TH1.cxx:797-798`). It
means "compute it from the data", and ROOT tests for it by distance rather than
equality: `TMath::Abs(fMaximum + 1111) > 1e-3`
(`root/hist/hist/src/TH1.cxx:3230`). A writer that leaves the fields at 0 produces a
histogram ROOT draws with a ceiling and a floor of zero, and `GetMaximumStored()`
returns 0 rather than the sentinel.

ROOT uses the same number as a general "unset" marker for a `Double_t` whose
natural range includes 0: `TF1` uses it for `fXmin`, `fXmax`, `fMinimum` and `fMaximum`
(`root/hist/hist/inc/TF1.h:212-222`), and `TGraph`, `TGraph2D` and `TH2Poly` use it
too.

## 7. `TH2F` and `TH2D`

A `TH2F` record has three frames, not two: a byte count and a version word around
a `TH2`, which has its own around a `TH1`. `TH2`'s four members sit **between**
the end of the `TH1` frame and the start of the `TArray` base:

| Offset in `h2f`'s 817 bytes of object data | Bytes | What |
|---|---|---|
| 0 | 4 + 2 | `TH2F`'s byte count and class version 4 |
| 6 | 4 + 2 | `TH2`'s byte count and class version 5 |
| 12 | 4 + 2 | `TH1`'s byte count and class version 8 |
| 18 | 683 | the `TH1` block of §3, unchanged |
| 701 | 32 | `fScalefactor`, `fTsumwy`, `fTsumwy2`, `fTsumwxy` — §7.2 |
| 733 | 4 + 80 | the `TArrayF` base: `fN` and `fNcells` floats |

`TH2` and the concrete classes have hand-written `Streamer`s that delegate above
version 2 (`root/hist/hist/src/TH2.cxx:2823`, `:3982`, `:4255`), and the write
path of each is a plain `WriteClassBuffer`
(`root/hist/hist/src/TH2.cxx:2836`, `:4004`, `:4277`). The bytes are therefore
what the three streamer infos describe, and unlike `TH1` none of them does any
fixup on read. `TH2D` differs from `TH2F` only in the `TArray` base, and has
**the same class version, 4**.

### 7.1 `fNcells` is a rectangle, and so is the in-range region

`fNcells` is `(nx + 2) * (ny + 2)`: `TH1`'s constructor sets `nx + 2` and
`TH2`'s multiplies (`root/hist/hist/src/TH2.cxx:105`). The cell a bin occupies is

```
cell = binx + (nx + 2) * biny
```

with each index running from 0, the underflow, to `n + 1`, the overflow
(`root/hist/hist/src/TH2.cxx:1056-1065`; the inverse is
`root/hist/hist/src/TH1.cxx:5072-5094`). The array is therefore **row-major in
x**: the first `nx + 2` cells are the whole `biny = 0` row, the last `nx + 2` the
`biny = ny + 1` row, and `binx` 0 and `nx + 1` are the x flow cells *inside every
row*. The four corners are flow cells in both axes at once.

Because of this layout the statistics cover a **rectangle**, not "every cell but
the first and last". `TH2::Fill` increments `fEntries` before it knows where the
fill landed (`root/hist/hist/src/TH2.cxx:391`), and then skips all seven sums if
`binx` is 0 or above `nx` *or* `biny` is 0 or above `ny`
(`root/hist/hist/src/TH2.cxx:398-403`). `fEntries` therefore counts a fill that
is out of range in either axis and `fTsumw` does not, as in one dimension. A
writer computing the sums from cells has to iterate `1 <= binx <= nx` and
`1 <= biny <= ny`, which is what `rootwrite.stats_from_cells_2d` does.

`fZaxis` is still a one-bin placeholder, and `fDimension` is transient
(`root/hist/hist/inc/TH1.h:171`), so **nothing in the record says the histogram
is two-dimensional**. A reader gets that from the class name alone.

### 7.2 The four members `TH2` adds

| Member | Type | Value | Kind |
|---|---|---|---|
| `fScalefactor` | `f64` | **1.0** | free, and unused (below) |
| `fTsumwy` | `f64` | Σ w·y over in-range fills | derived |
| `fTsumwy2` | `f64` | Σ w·y² | derived |
| `fTsumwxy` | `f64` | Σ w·x·y | derived |

They are in declaration order (`root/hist/hist/inc/TH2.h:33-36`) and all four
are persistent. `TH2` adds no transient members and no enum, so its checksum
folds four plain doubles onto the `TH1` base's.

**`fScalefactor` is written by every constructor and read by nothing.** Six
constructors assign 1 (`root/hist/hist/src/TH2.cxx:75`, `:101`, `:130`, `:158`,
`:187`, `:217`), `Copy` copies it (`:354`) and the legacy streamer branches read
it back (`:2829`, `:3014`, `:3277`, `:3992`, `:4265`). There is no getter, no
setter and no arithmetic anywhere in ROOT, and JSROOT hardcodes the same 1 when it
synthesises a `TH2` (`root/js/modules/core.mjs:1444`). Write 1.0: nothing breaks
if you do not, but only 1.0 gives a record that compares byte for byte with
ROOT's.

`fTsumwxy` has one reader: `TH2::GetCovariance` is the only place `stats[6]` is
used (`root/hist/hist/src/TH2.cxx:1156`), and `GetCorrelationFactor` reaches it
through that. `fTsumwy` and `fTsumwy2` reach `GetMean(2)` and `GetStdDev(2)`,
which index the same statistics array with `ax[3] = {2,4,7}`
(`root/hist/hist/src/TH1.cxx:7674`, `:7746`), and a Y projection copies them into
the projection's x sums (`root/hist/hist/src/TH2.cxx:2344-2346`).

`Integral`, `GetBinContent` and `GetBinError` read none of the four.

### 7.3 A zero `fTsumw` throws all seven sums away

`TH2::GetStats` **recomputes** all seven sums from the cell contents and the bin
centres when `(fTsumw == 0 && fEntries > 0)` holds, or when either axis has
`kAxisRange` (`root/hist/hist/src/TH2.cxx:1230`). Only otherwise does it return
what the record says. A genuinely empty histogram is safe, because `fEntries` is
0 there too.

For a writer, the sums are therefore not optional in the way `fSumw2` is. Write
`fEntries` 6 and leave `fTsumw` at 0, and ROOT silently discards `fTsumwy`,
`fTsumwxy` and the rest and reports a mean computed from the bins: the bin-centre
approximation of §5, with no diagnostic. The same condition guards
`TProfile::GetStats`, with one difference (§8.5).

## 8. `TProfile`

A `TProfile` is a `TH1D` with **four parallel arrays per cell**, one of which is
the `TH1D`'s own `TArrayD` base. None of them holds a bin content:

```
fArray      (the TArrayD base)   sum(w * y)
fSumw2      (TH1::fSumw2)        sum(w * y * y)
fBinEntries                      sum(w)
fBinSumw2                        sum(w * w), or empty
```

The value ROOT reports for a bin, `fArray[i] / fBinEntries[i]`, is computed on
demand and stored nowhere (`root/hist/hist/src/TProfile.cxx:858`).

Like `TH2`, `TProfile::Streamer` is hand-written, delegates above version 2
(`root/hist/hist/src/TProfile.cxx:1825`) and writes through a plain
`WriteClassBuffer` (`:1847`) with no read fixups of its own.

### 8.1 The seven members, and the transient one in the middle

In streamed order, after the framed `TH1D` base:

| Member | Type | Value | Kind |
|---|---|---|---|
| `fBinEntries` | `TArrayD` | exactly `fNcells` entries, Σ w per cell | derived — the length is **fixed** |
| `fErrorMode` | `i32` | 0 `kERRORMEAN` unless set — §8.4 | free |
| `fYmin` | `f64` | 0 | free |
| `fYmax` | `f64` | 0 — equal to `fYmin` means "no range" | free |
| `fTsumwy` | `f64` | Σ w·y over in-range fills | derived |
| `fTsumwy2` | `f64` | Σ w·y² | derived |
| `fBinSumw2` | `TArrayD` | empty, or `fNcells` entries — §8.2 | derived |

Declaration order is `root/hist/hist/inc/TProfile.h:39-46`, and **`fScaling`
sits between `fYmax` and `fTsumwy` in the header** (`:43`). It is transient, so
`fTsumwy` follows `fYmax` directly on the wire and the member is in neither the
layout nor the checksum. This is the same trap as `TH1`'s four transient members
(§3), and easier to miss because it is a single `Bool_t` among doubles.

`fErrorMode` is the only enum in either chain besides `TH1`'s two. Its type is a
file-scope `EErrorType` rather than a nested one
(`root/hist/hist/inc/TProfile.h:28`), so its element records `fTypeName`
`EErrorType` and folds an extra 1 into `TProfile`'s checksum
([StreamerInfo §11.1](../02-serialization/StreamerInfo.md#111-an-enum-member-is-recognisable-and-it-changes-the-value)).
Treated as a plain `int`, it gives a checksum other than `0x4bedee54`, which ROOT
reports through `BuildCheck`.

`fgApproximate` is a `static Bool_t` whose comment does **not** mark it transient
(`root/hist/hist/inc/TProfile.h:48`); it is excluded only because a static has no
offset. A writer reading the header for the member list has to drop it anyway.

### 8.2 `fSumw2` is never absent, and `fBinSumw2` usually is

`TProfileHelper::BuildArray` sizes `fBinEntries` and `fSumw2` to `fNcells`
unconditionally at construction, and `fBinSumw2` only on request
(`root/hist/hist/src/TProfileHelper.h:138-140`). As a result:

- **`fSumw2` always has exactly `fNcells` entries** in a `TProfile`, whereas in a
  plain `TH1` it is empty until something asks for it (§5.1). This is the only
  invariant in the document that ROOT enforces by crashing: `GetBinError`
  indexes `fSumw2.fArray` with no length test
  (`root/hist/hist/src/TProfileHelper.h:715`), so an empty array is a null
  pointer. Measured on 6.40.04 with a file this project wrote for the purpose:
  `TFile::Open` succeeds, `GetEntries` returns 3, `GetBinEntries(1)` returns 2 and
  `GetBinContent(1)` returns 2, all correct, and the process then dies with
  `*** Break *** segmentation violation` inside `GetBinError(1)`.
- **`fBinSumw2` is empty until a weight other than 1 arrives.** `Fill` then calls
  `Sumw2()` itself (`root/hist/hist/src/TProfile.cxx:751`), and `Sumw2()`
  pre-fills it from `fBinEntries` (`root/hist/hist/src/TProfileHelper.h:553-557`),
  so a profile filled unweighted and then weighted has a consistent array rather
  than a hole.

A wrong **length** for `fBinSumw2` is worse than a wrong value.
`GetBinEffectiveEntries` tests `fBinSumw2.fN != fNcells` and, if they differ,
**truncates the array to zero in memory** and returns the plain weight sum
(`root/hist/hist/src/TProfileHelper.h:159-162`, whose comment says "this can
happen when reading an old file"). The file is accepted, the data is dropped, and
nothing is printed.

### 8.3 What a reader computes from the four arrays

With `cont = fArray[i]`, `sum = fBinEntries[i]`, `err2 = fSumw2[i]` and
`neff = sum² / fBinSumw2[i]` (`root/hist/hist/src/TProfileHelper.h:165`, and
`neff = sum` when `fBinSumw2` is empty, `:159-162`):

| What ROOT returns | From | Cite |
|---|---|---|
| `GetBinContent(i)` | `cont / sum`, and 0 when `sum` is 0 | `root/hist/hist/src/TProfile.cxx:851-859` |
| `GetBinEntries(i)` | `sum` verbatim | `:864-870` |
| `GetBinEffectiveEntries(i)` | `sum² / Σw²` | `root/hist/hist/src/TProfileHelper.h:165` |
| `GetBinError(i)`, `kERRORMEAN` | `eprim / √neff`, where `eprim` is `sqrt(abs(err2/sum − (cont/sum)²))` | `root/hist/hist/src/TProfileHelper.h:723-725`, `:764` |
| `GetBinError(i)`, `kERRORSPREAD` | `eprim` | `:759` |
| `GetBinError(i)`, `kERRORSPREADI` | `eprim / √neff`, or `1/√(12·neff)` when the spread is 0 | `:727-732` |
| `GetBinError(i)`, `kERRORSPREADG` | `1 / √sum`, reading neither `fSumw2` nor `fArray` | `:719-720` |

**`fBinEntries` is not a count**, whatever its comment says (§12). It is a sum of
weights and `GetBinContent` divides by it, so treating it as an integer count of
fills makes every weighted bin wrong. `GetBinError` also returns 0 whenever `sum`
is 0 (`:717`), as it does for an empty bin, so a cell that holds data with
`fBinEntries` 0 reads as empty rather than as an error.

### 8.4 `fErrorMode`, and why `fYmin == fYmax` means "no limits"

`fErrorMode` is one of `kERRORMEAN` 0, `kERRORSPREAD` 1, `kERRORSPREADI` 2 and
`kERRORSPREADG` 3 (`root/hist/hist/inc/TProfile.h:28`), set from the option
letters `s`, `i` and `g` in that order, so `"si"` yields `kERRORSPREADI`
(`root/hist/hist/src/TProfileHelper.h:695-703`). It changes every bin error and
nothing else.

`fYmin` and `fYmax` are the accepted range in y, and the filter is guarded by
`if (fYmin != fYmax)` (`root/hist/hist/src/TProfile.cxx:682`, `:742`, `:824`).
The ordinary constructors pass 0 and 0 (`root/hist/hist/src/TProfile.cxx:226-236`
via `BuildOptions`), so **equal limits are how "no range" is expressed**, and a
range of zero width cannot be stated. A writer that means "no range" must write
two equal values; 0 and 0 is ROOT's pair. A writer carrying a range over from
elsewhere has to check that its two limits differ, or the filter it believes it
recorded is off. The NaN rejection depends on the same guard, so a profile with no
range accepts a NaN `y` into `fArray`, `fSumw2`, `fTsumwy` and `fTsumwy2`.

When the filter does reject a fill, it returns **before `fEntries++`**
(`root/hist/hist/src/TProfile.cxx:682-686`). This is the opposite of `TH2`, where
an out-of-range fill still counts as an entry (§7.1).
`data/classes/th2-profile.root`'s `p2` has one of each: `fEntries` is 3 after
four `Fill` calls.

### 8.5 Only `fEntries` is unrecoverable

A profile is the only histogram whose statistics a writer can almost entirely
derive, because its per-cell arrays hold what a `TH1` throws away:

| Statistic | From the arrays | Exact? |
|---|---|---|
| `fTsumw` | Σ `fBinEntries` over in-range cells | yes |
| `fTsumw2` | Σ `fBinSumw2`, or `fTsumw` when it is empty | yes — an empty `fBinSumw2` means every weight was 1 |
| `fTsumwy` | Σ `fArray` over in-range cells | yes |
| `fTsumwy2` | Σ `fSumw2` over in-range cells | yes |
| `fTsumwx`, `fTsumwx2` | Σ `fBinEntries[i]` × the bin centre | only if every fill sat at one |
| `fEntries` | — | **no**: it counts fills, and a weighted fill moves `fBinEntries` by its weight |

`rootwrite.stats_from_profile` does this, and for both profiles in the reference
file it reproduces ROOT's six sums. Only `fEntries` is supplied, and only for
`p2`, where three fills of weight 3, 0.5 and 0.5 sum to 4.

Two repair paths in ROOT can make a writer's missing sums look correct.
`TProfile::GetStats` recomputes all six sums from the arrays when `fTsumw == 0`.
Its version of the condition has `&& fEntries > 0` **commented out in the
source** (`root/hist/hist/src/TProfile.cxx:958`), so unlike `TH2` (§7.3) a zero
`fTsumw` diverts even when `fEntries` is 0. On the fast path, if `fTsumwy` and
`fTsumwy2` are *both* 0, ROOT fills them in from `fArray` and `fSumw2` over the
displayed range, casting away `const` to do it (`:980-987`, whose comment blames
`TProfile` versions ≤ 3). A writer that leaves those two at 0 therefore gets
range-dependent values back, not zeros.

### 8.6 ROOT appends a `listOfRules` a writer cannot use

A file holding a `TProfile` gets **one entry in its `StreamerInfo` record that is
not an info**: a `TList` named `listOfRules` holding one `TObjString`, the I/O
customisation rule that resets `fBinSumw2` for `TProfile` versions 1 to 5
(`root/hist/hist/inc/LinkDef.h:362-364`). `TFile::WriteStreamerInfo` collects the
rules of every class in the list and appends that entry when there are any.

A file written at version 7 cannot use the rule, so a writer **may** omit it with
no loss of information; ROOT never reads the list back. `tools/rootwrite.py`
emits it anyway, so that `data/written/th2-profile.root`'s `StreamerInfo` record
is byte-identical to ROOT's, all 11789 bytes of its payload.
[Writing an object §8.6](WritingObjects.md#86-listofrules-is-optional-and-this-is-what-it-costs)
is the general treatment, and `TTree` has the same entry
([Writing trees §8.1](WritingTrees.md#81-root-appends-two-rules-that-a-new-file-cannot-use)).
A reader must tolerate it: it is a `TList`, not a `TStreamerInfo`, and a reader
that assumes every element of the record is an info will mis-decode it
([Schema evolution §6](../02-serialization/SchemaEvolution.md#6-rules-and-the-listofrules-entry)).

## 9. The streamer infos

Fifteen classes for a `TH1F`/`TH1D` file, and a writer that wants its histograms
readable by anything but ROOT has to emit all of them:

```
TH1F  TH1  TNamed  TObject  TAttLine  TAttFill  TAttMarker  TAxis  TAttAxis
THashList  TList  TSeqCollection  TCollection  TString  TH1D
```

Eighteen for a file of `TH2F`, `TH2D` and `TProfile`: the same set with three
more classes and the concrete ones changed:

```
TH2F  TH2  TH1  TNamed  TObject  TAttLine  TAttFill  TAttMarker  TAxis
TAttAxis  THashList  TList  TSeqCollection  TCollection  TString  TH2D
TProfile  TH1D
```

`TH1D` is there because it is `TProfile`'s base, and it comes **last** rather than
beside the other bases. The order is ROOT's registration order, not alphabetical:
the first object's chain leads and everything a later object adds follows.

[Element lists](ElementLists.md) publishes all twenty-two distinct classes,
member by member, with the checksum beside each. Some things in the lists are not
obvious:

- **`THashList`, `TList`, `TSeqCollection` and `TCollection` are present** although
  a histogram with no labels and no functions contains no collection data. A
  **null** object pointer still forces its class's info to be written
  (`root/io/io/src/TStreamerInfo.cxx:3448`, reached from
  `root/io/io/src/TBufferFile.cxx:2456-2463`), and `fLabels` is a `THashList *`.
- **`TString`'s info has zero elements.** It is written but tells a reader
  nothing; the encoding is
  [Conventions §5.1](../00-conventions.md#51-counted-string).
- **No `TArray` info is written**, for `TArrayF`, `TArrayD` or `TArray` itself,
  because their streamers are hand-written and nothing marks them
  ([Writing an object §7.2](WritingObjects.md#72-which-classes-need-an-info)).
  Their checksums are still needed, as the `fBaseCheckSum` of `TH1F` and `TH1D`,
  so a writer has to compute them from element lists it never emits; those three
  lists are in
  [Element lists §10](ElementLists.md#10-three-classes-a-histogram-file-does-not-describe).
  A `TH2F` and a `TH2D` need the same two, and a `TProfile` needs `TArrayD`
  through `TH1D`.
- **Two checksums cannot be computed from an element list at all.**
  `THashList` and `TSeqCollection` are class version 0, so their infos list only
  their bases while their checksums fold their members
  ([StreamerInfo §11.2](../02-serialization/StreamerInfo.md#112-what-cannot-be-recomputed)).
  A writer must carry `0xcc7e49c1` and `0xfc6c3bc6` as constants.
  `tools/rootwrite.py` has them in `KNOWN_CHECKSUMS`, and they are the only two
  magic numbers in the histogram path.
- **A `TProfile` brings a nineteenth entry that is not an info**, the
  `listOfRules` of §8.6. A writer may omit it, and a reader must tolerate it.

`TH1`'s own checksum, `0x1c3740c4`, *is* computable, but only with the enum rule:
`fBinStatErrOpt` and `fStatOverflows` each fold an extra 1
([StreamerInfo §11.1](../02-serialization/StreamerInfo.md#111-an-enum-member-is-recognisable-and-it-changes-the-value)).
`TProfile`'s `0x4bedee54` needs the same rule for `fErrorMode`. `TH2`'s
`0x0182347f` needs none, since it folds four plain doubles onto `TH1`'s.

## 10. Invariants

1. `fNcells == fXaxis.fNbins + 2` for a 1-D histogram and
   `(fXaxis.fNbins + 2) * (fYaxis.fNbins + 2)` for a `TH2`, and the `TArray`
   base's `fN` equals `fNcells` in both.
2. `fSumw2` is empty or has exactly `fNcells` entries; likewise `fBinSumw2` in a
   `TProfile`.
3. `fXbins` is empty or has exactly `fNbins + 1` entries, and when non-empty its
   first and last entries are `fXmin` and `fXmax`. This holds of a `TH2`'s Y axis
   as well as its X axis.
4. `fYaxis` and `fZaxis` are present, with `fNbins` 1 in a 1-D histogram, and
   `fZaxis.fNbins` is 1 in a `TH2` too.
5. `fEntries >= 0`, and `fTsumw <= fEntries` when every weight is 1.
6. `fBufferSize` is 0 **iff** `fBuffer`'s flag byte is 0.
7. Every class version word in the chain matches §11's table.
8. In a `TProfile`, `fBinEntries` has exactly `fNcells` entries and `fSumw2` is
   **never** empty. It is the only histogram class where an empty `fSumw2` is not
   a legal "use Poisson errors", and the only invariant here that ROOT enforces by
   segfaulting rather than by complaining (§8.2).
9. In a `TProfile`, `fYmin <= fYmax`, and `fErrorMode` is 0, 1, 2 or 3.

1, 2, 3, 4, 6, 8 and 9 are checked for the written files by
`tools/check_write.py` through `tools/rootfile.py`; 7 is checked against
`ClassDef` for every class in §11's table by `tools/check_versions.py`.

## 11. Class versions

Every class in the chain, with the version a writer emits. Checked against
`ClassDef` in the pinned submodule by `tools/check_versions.py`.

| Class | Version | Cite |
|---|---|---|
| `TH1F`, `TH1D` | 3 | `root/hist/hist/inc/TH1.h:902`, `:949` |
| `TH1` | 8 | `root/hist/hist/inc/TH1.h:693` |
| `TH2F`, `TH2D` | 4 | `root/hist/hist/inc/TH2.h:388`, `:442` |
| `TH2` | 5 | `root/hist/hist/inc/TH2.h:137` |
| `TProfile` | 7 | `root/hist/hist/inc/TProfile.h:139` |
| `TAxis` | 10 | `root/hist/hist/inc/TAxis.h:179` |
| `TAttAxis` | 4 | `root/core/base/inc/TAttAxis.h:68` |
| `TNamed` | 1 | `root/core/base/inc/TNamed.h:60` |
| `TAttLine` | 2 | `root/core/base/inc/TAttLine.h:51` |
| `TAttFill` | 2 | `root/core/base/inc/TAttFill.h:46` |
| `TAttMarker` | 3 | `root/core/base/inc/TAttMarker.h:55` |
| `TList` | 5 | `root/core/cont/inc/TList.h:115` |

## 12. Errata

Against comments in ROOT's own headers and source, each of which would mislead a
writer reading the class definition for its member list.

| # | Where | What it says | What is true |
|---|---|---|---|
| 1 | `root/hist/hist/inc/TProfile.h:39` | `fBinEntries` is the "number of entries per bin" | It is **Σ w**, a sum of weights. `Fill` adds the weight (`root/hist/hist/src/TProfile.cxx:753`) and `GetBinContent` divides by it (`:858`). A comment on the same array in `TProfileHelper` says "sum of bin weights" (`root/hist/hist/src/TProfileHelper.h:714`), so the header and the implementation contradict each other. `data/classes/th2-profile.root`'s `p2` has `fBinEntries[1]` of 3.5 |
| 2 | `root/hist/hist/inc/TProfile.h:43` | `fScaling` is "True when `TProfile::Scale` is called" | Nothing ever sets it true: it is assigned `kFALSE` in `BuildOptions` (`root/hist/hist/src/TProfile.cxx:235`), copied in `Copy` (`:464`), and `TProfileHelper::Scale` does not touch it (`root/hist/hist/src/TProfileHelper.h:513-527`). It is transient, so it never reaches a file either. The same stale comment is in `TProfile2D.h:38` and `TProfile3D.h:38` |
| 3 | `root/hist/hist/inc/TH2.h:33` | `fScalefactor` is a "Scale factor" | Nothing scales by it. Six constructors assign 1 and only the legacy streamer branches read it back; there is no getter and no arithmetic anywhere in ROOT (§7.2) |
| 4 | `root/hist/hist/inc/TProfile.h:48` | `fgApproximate` carries a persistent `///<` comment | It is `static`, so it has no offset and `TStreamerInfo::Build` drops it. The comment implies it is streamed; it is not. `TH1`'s statics are correctly marked `///<!` (`root/hist/hist/inc/TH1.h:176-179`) |
| 5 | `root/hist/hist/src/TProfile.cxx:938-947` | `GetStats` is "simply a copy of the statistics quantities computed at filling time" | It is not, in two ways: the `fTsumw == 0` branch recomputes all six from the arrays, and the fast path silently repairs `fTsumwy`/`fTsumwy2` through a cast-away `const` when both are 0 (§8.5) |
| 6 | `root/hist/hist/src/TProfile.cxx:889-913` | `GetBinError`'s history is dated "prior to version 3.00", "in version 3.05/06" | Those are ROOT *release* numbers, not `TProfile` class versions, which run 1 to 7. A reader has the class version and nothing else, so the block cannot be used to date a layout |

## 13. Reference files

| File | What it is |
|---|---|
| `data/classes/histogram.root` | ROOT's: a `TH1F` with fixed bins and `Sumw2`, a `TH1D` with variable edges and weighted fills, and the fifteen infos. 73 assertions |
| `data/written/histogram.root` | this project's, holding the same two histograms. Every object-bearing record is byte-identical to ROOT's |
| `data/classes/th2-profile.root` | ROOT's: a `TH2F` with a fill out of range in each axis, a `TH2D` with variable edges on both, and two `TProfile`s that differ in `fBinSumw2`, `fErrorMode` and the Y range. 71 assertions |
| `data/written/th2-profile.root` | this project's, holding the same four. All four data records are byte-identical to ROOT's, and so is the `StreamerInfo` record, `listOfRules` included |
| `data/classes/tarray-histogram.root` | a `TH2F` inside a `TTree` branch, which is what makes a concrete `TArray` info appear |
