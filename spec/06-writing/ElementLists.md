# Streamer-info element lists

[Writing an object §7](WritingObjects.md#7-the-streamerinfo-record) specifies the
`StreamerInfo` record — its nesting, its option bytes, the `fBits` each info
carries, the checksum algorithm — and
[§7.2](WritingObjects.md#72-which-classes-need-an-info) says which classes a file
needs an info for. Neither says what goes **inside** one: the member list, with
every field of every `TStreamerElement`. Without that a writer can build a
correctly framed record with nothing in it, so this document publishes the lists
themselves.

Thirty-two classes, which is every class a writer of histograms, profiles,
flat trees and a bare object has to describe:

<!-- BEGIN GENERATED: counts -->
**32 classes, 176 elements**, every one read out of a file ROOT wrote.
<!-- END GENERATED -->

Nothing here was transcribed from this project's writer. Every table is read out
of a reference file **ROOT wrote** by `tools/element_lists.py`, which also
compares each class across every fixture that carries it, compares every field
with `tools/rootwrite.py`, and recomputes each checksum from the table beside it.
`tools/element_lists.py --check` fails in CI if any of that stops holding.

## 1. How to read a table

One table is one info's `TObjArray` of elements, in the order they appear on
disk, which is declaration order with the bases first. That order is part of the
layout: it is the order the members are written in, and the order the checksum
folds them in
([StreamerInfo §11](../02-serialization/StreamerInfo.md#11-checksums)).

| Column | What it is |
|---|---|
| `#` | position in the array; not stored anywhere |
| Element class | the concrete `TStreamerXxx` whose class tag goes in the slot, with its own version from [StreamerInfo §8](../02-serialization/StreamerInfo.md#8-the-element-subclasses) |
| `fName` | the member's name, or the base class's name for a `TStreamerBase` |
| `fType` | the element type code, with its mnemonic ([Element types](../02-serialization/ElementTypes.md)) |
| `fSize` | `sizeof` on the writing machine — §3 |
| `fTypeName` | the **resolved** type spelling: `int`, not `Int_t`; `BASE` for a base class |
| Extra | whatever the element's subclass adds after the `TStreamerElement` base |
| `fTitle` | the member's declaration comment, verbatim |

The `Extra` column carries the subclass tail in one of three forms, and nothing
else in these thirty-one classes needs a fourth:

- `TStreamerBase` — `fBaseVersion`, and the base's own checksum, which travels in
  `fMaxIndex[1]`
  ([StreamerInfo §9](../02-serialization/StreamerInfo.md#9-tstreamerbase-and-a-checksum-hidden-in-fmaxindex)).
  It is written as an unsigned word, so a value with the top bit set reads back
  as a negative `i32`. A base's `fType` is not always 0: the tables show 66 for a
  `TObject` base and 67 for a `TNamed` one, because `TStreamerBase`'s constructor
  rewrites the code by name
  ([Element types §6](../02-serialization/ElementTypes.md#6-kbase-0-and-knotype-1)),
  and those two codes are what tell a reader that the base carries no byte count
  and that it does.
- `TStreamerBasicPointer` — the counter member, the class that **declares** it,
  and that class's version. The class is the one the member is declared in, not
  the one being described: `TArrayF::fArray` names `fN` in `TArray`.
- `TStreamerSTL` — `fSTLtype` and `fCtype`. A `vector<string>` has `fCtype`
  61 `kObject`, not `kSTLstring`: `std::string` has a dictionary, so the
  collection's value class is found and the element type follows from that
  (`root/core/meta/src/TStreamerElement.cxx:1810-1812`).

**Which subclass a member takes** is not stated anywhere as a rule, and the tables
are the specification of it by example: a primitive or an enum is a
`TStreamerBasicType`, a `TString` a `TStreamerString`, a counted array a
`TStreamerBasicPointer`, an embedded `TObject`-derived class a `TStreamerObject`,
an embedded class that is not a `TObject` a `TStreamerObjectAny`, a pointer to a
`TObject`-derived class a `TStreamerObjectPointer`, an STL container a
`TStreamerSTL`, and a base a `TStreamerBase`. Two of the eleven subclasses have no
example here: `TStreamerObjectAnyPointer`, for a pointer to a class that is not a
`TObject`, and `TStreamerLoop`, for a counted array of objects
([Element types §8](../02-serialization/ElementTypes.md#8-kstreamer-500-and-kstreamloop-501)). The subclass and
the `fType` agree in every row, and a reader uses the `fType`
([StreamerInfo §8](../02-serialization/StreamerInfo.md#8-the-element-subclasses)
is what each subclass adds to the record).

Two fields are absent from every row and are therefore not columns.
`fArrayLength` and `fArrayDim` are 0 throughout — no member of these classes is a
fixed-length C array, so `fMaxIndex[0]` is 0 as well and only `fMaxIndex[1]`
carries anything. And each element's own `fBits` is 0: `kHasRange` would appear
there for a `Double32_t` or `Float16_t` member with a range in its comment
([Element types §5](../02-serialization/ElementTypes.md#5-kdouble32-and-kfloat16)),
and none of these classes has one.

The info's own `fTitle` is empty in all thirty-one — and in all **743** streamer
infos in this repository's reference files, which is worth knowing because
[Writing an object §7.1](WritingObjects.md#71-the-nesting) describes it as the
class's comment and a writer will wonder what to put there. An empty string.

## 2. What the tables do not, and cannot, give you

**Two checksums cannot be recomputed from the list beside them.** `THashList` and
`TSeqCollection` are class version 0, and `TStreamerInfo::Build` skips every
member of a version-0 class (`root/io/io/src/TStreamerInfo.cxx:552-554`) while
the checksum still folds them. Their infos list only their bases, so a writer has
to carry `0xcc7e49c1` and `0xfc6c3bc6` as constants
([StreamerInfo §11.2](../02-serialization/StreamerInfo.md#112-what-cannot-be-recomputed)).
Every other checksum in §4 to §9 is reproduced exactly by §11's algorithm applied
to the table printed beside it, and `tools/element_lists.py` fails if that stops
being true in either direction.

**These lists are the current versions and nothing else.** They describe the
classes at the versions in §11, which are the versions the pinned ROOT compiles.
A file written with them is readable by older ROOT only as far as that ROOT's own
schema evolution reaches; producing an *older* layout is not something the format
offers a writer
([Overview §3.1](index.md#31-what-the-current-version-means)).

**And they are the classes these procedures need, not a general set.** A split
branch, a `TGraph`, a `TH3` or a user-defined class needs infos this document
does not carry — the element list for any of them is
obtainable from the file side with
[StreamerInfo §12](../02-serialization/StreamerInfo.md#12-reading), and
[Overview §4](index.md#4-what-is-not-specified) is the standing list of what the
writing layer does not cover.

## 3. `fSize` is a `sizeof`, and nothing reads it

`fSize` is the size of the member **on the machine that wrote the file**, and a
reader must never use it
([StreamerInfo §7](../02-serialization/StreamerInfo.md#7-tstreamerelement)).
The tables publish ROOT's values because a writer that wants a byte-identical
record needs them, not because they matter:

- **ROOT overwrites the value it just read.** `TStreamerBasicType::Streamer`
  recomputes `fSize` from `fType` for every basic member after
  `ReadClassBuffer` returns (`root/core/meta/src/TStreamerElement.cxx:1242-1269`),
  multiplying by the array length if there is one. Whatever the file said is
  discarded before anything can consult it.
- **A pointer element's field is not a pointer size either.** For
  `Float_t *fArray` the value is 4, because `TStreamerInfo::Build` takes the
  *element* type's size (`root/io/io/src/TStreamerInfo.cxx:645`,
  `:783`), while `TStreamerBasicPointer::GetSize` reports `sizeof(void *)`
  regardless of it (`root/core/meta/src/TStreamerElement.cxx:1002-1005`).
- **ROOT's own files disagree with each other.** Counting only the files ROOT
  published (`gen/cern/`, so provenance is not in question), `TNamed::fName` — a
  `TString`, ROOT's own class — is recorded with `fSize` **0, 8, 16 and 24**, and
  `TH1::fXaxis` with **0, 128, 184, 208 and 216**. A `TArrayD` member is 0, 12 or
  24 and every object pointer 0, 4 or 8. The zeros are ROOT 3.04/02 and 3.05/07
  (`mlpHiggs.root`, `H1display.root`), which wrote the field as 0 throughout; the
  rest is pointer width and class layout changing across releases. None of it
  changes a byte of any object.

The practical consequence for a writer is that this is the one column it can get
wrong without consequence — but also that `fSize` is why a fixture's normalized
digest is masked at all (`tools/normalize.py`), since `sizeof(std::string)` and
`sizeof(std::map<int,int>)` differ between standard libraries. No member of these
thirty-one classes is affected: the only STL member among them is
`TRefTable::fProcessGUIDs`, a `vector<string>`, and `sizeof(std::vector<T>)` is
24 with both.

## 4. The nine classes every set needs

Every file needs these, whichever of the procedures produced it. They are in
bases-first order, which is the order a writer has to compute the checksums in.

<!-- BEGIN GENERATED: shared -->
### `TObject`

Class version **1**, `fCheckSum` **`0x901bc02d`**. 2 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBasicType` | `fUniqueID` | 13 `kUInt` | 4 | `unsigned int` |  | `object unique identifier` |
| 2 | `TStreamerBasicType` | `fBits` | 15 `kBits` | 4 | `unsigned int` |  | `bit field status word` |

### `TNamed`

Class version **1**, `fCheckSum` **`0xdfb74a3c`**. 3 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TObject` | 66 `kTObject` | 0 | `BASE` | base version 1; base checksum `0x901bc02d` | `Basic ROOT object` |
| 2 | `TStreamerString` | `fName` | 65 `kTString` | 24 | `TString` |  | `object identifier` |
| 3 | `TStreamerString` | `fTitle` | 65 `kTString` | 24 | `TString` |  | `object title` |

### `TString`

Class version **2**, `fCheckSum` **`0x00017419`**. No elements at all.

### `TAttLine`

Class version **2**, `fCheckSum` **`0x94074549`**. 3 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBasicType` | `fLineColor` | 2 `kShort` | 2 | `short` |  | `Line color` |
| 2 | `TStreamerBasicType` | `fLineStyle` | 2 `kShort` | 2 | `short` |  | `Line style` |
| 3 | `TStreamerBasicType` | `fLineWidth` | 2 `kShort` | 2 | `short` |  | `Line width` |

### `TAttFill`

Class version **2**, `fCheckSum` **`0xffd92a92`**. 2 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBasicType` | `fFillColor` | 2 `kShort` | 2 | `short` |  | `Fill area color` |
| 2 | `TStreamerBasicType` | `fFillStyle` | 2 `kShort` | 2 | `short` |  | `Fill area style` |

### `TAttMarker`

Class version **3**, `fCheckSum` **`0x291d8bec`**. 3 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBasicType` | `fMarkerColor` | 2 `kShort` | 2 | `short` |  | `Marker color` |
| 2 | `TStreamerBasicType` | `fMarkerStyle` | 2 `kShort` | 2 | `short` |  | `Marker style` |
| 3 | `TStreamerBasicType` | `fMarkerSize` | 5 `kFloat` | 4 | `float` |  | `Marker size` |

### `TCollection`

Class version **3**, `fCheckSum` **`0x57e3cb9c`**. 3 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TObject` | 66 `kTObject` | 0 | `BASE` | base version 1; base checksum `0x901bc02d` | `Basic ROOT object` |
| 2 | `TStreamerString` | `fName` | 65 `kTString` | 24 | `TString` |  | `name of the collection` |
| 3 | `TStreamerBasicType` | `fSize` | 3 `kInt` | 4 | `int` |  | `number of elements in collection` |

### `TSeqCollection`

Class version **0**, `fCheckSum` **`0xfc6c3bc6`**, **not** reproducible from the table below ([§2](#2-what-the-tables-do-not-and-cannot-give-you)). 1 element.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TCollection` | 0 `kBase` | 0 | `BASE` | base version 3; base checksum `0x57e3cb9c` | `Collection abstract base class` |

### `TList`

Class version **5**, `fCheckSum` **`0x69c5c3bb`**. 1 element.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TSeqCollection` | 0 `kBase` | 0 | `BASE` | base version 0; base checksum `0xfc6c3bc6` | `Sequenceable collection ABC` |
<!-- END GENERATED -->

## 5. A histogram file: the other six

With §4 these are the fifteen of
[Writing histograms §9](WritingHistograms.md#9-the-streamer-infos). `THashList`
is here rather than in §4 because only a histogram reaches it — `TAxis::fLabels`
is a `THashList *`, and a null pointer still forces its class's info to be
written.

<!-- BEGIN GENERATED: histogram -->
### `THashList`

Class version **0**, `fCheckSum` **`0xcc7e49c1`**, **not** reproducible from the table below ([§2](#2-what-the-tables-do-not-and-cannot-give-you)). 1 element.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TList` | 0 `kBase` | 0 | `BASE` | base version 5; base checksum `0x69c5c3bb` | `Doubly linked list` |

### `TAttAxis`

Class version **4**, `fCheckSum` **`0x5c6fff3e`**. 11 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBasicType` | `fNdivisions` | 3 `kInt` | 4 | `int` |  | `Number of divisions(10000*n3 + 100*n2 + n1)` |
| 2 | `TStreamerBasicType` | `fAxisColor` | 2 `kShort` | 2 | `short` |  | `Color of the line axis` |
| 3 | `TStreamerBasicType` | `fLabelColor` | 2 `kShort` | 2 | `short` |  | `Color of labels` |
| 4 | `TStreamerBasicType` | `fLabelFont` | 2 `kShort` | 2 | `short` |  | `Font for labels` |
| 5 | `TStreamerBasicType` | `fLabelOffset` | 5 `kFloat` | 4 | `float` |  | `Offset of labels` |
| 6 | `TStreamerBasicType` | `fLabelSize` | 5 `kFloat` | 4 | `float` |  | `Size of labels` |
| 7 | `TStreamerBasicType` | `fTickLength` | 5 `kFloat` | 4 | `float` |  | `Length of tick marks` |
| 8 | `TStreamerBasicType` | `fTitleOffset` | 5 `kFloat` | 4 | `float` |  | `Offset of axis title` |
| 9 | `TStreamerBasicType` | `fTitleSize` | 5 `kFloat` | 4 | `float` |  | `Size of axis title` |
| 10 | `TStreamerBasicType` | `fTitleColor` | 2 `kShort` | 2 | `short` |  | `Color of axis title` |
| 11 | `TStreamerBasicType` | `fTitleFont` | 2 `kShort` | 2 | `short` |  | `Font for axis title` |

### `TAxis`

Class version **10**, `fCheckSum` **`0x5a496e70`**. 13 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TNamed` | 67 `kTNamed` | 0 | `BASE` | base version 1; base checksum `0xdfb74a3c` | `The basis for a named object (name, title)` |
| 2 | `TStreamerBase` | `TAttAxis` | 0 `kBase` | 0 | `BASE` | base version 4; base checksum `0x5c6fff3e` | `Axis attributes` |
| 3 | `TStreamerBasicType` | `fNbins` | 3 `kInt` | 4 | `int` |  | `Number of bins` |
| 4 | `TStreamerBasicType` | `fXmin` | 8 `kDouble` | 8 | `double` |  | `Low edge of first bin` |
| 5 | `TStreamerBasicType` | `fXmax` | 8 `kDouble` | 8 | `double` |  | `Upper edge of last bin` |
| 6 | `TStreamerObjectAny` | `fXbins` | 62 `kAny` | 24 | `TArrayD` |  | `Bin edges array in X` |
| 7 | `TStreamerBasicType` | `fFirst` | 3 `kInt` | 4 | `int` |  | `First bin to display` |
| 8 | `TStreamerBasicType` | `fLast` | 3 `kInt` | 4 | `int` |  | `Last bin to display` |
| 9 | `TStreamerBasicType` | `fBits2` | 12 `kUShort` | 2 | `unsigned short` |  | `Second bit status word` |
| 10 | `TStreamerBasicType` | `fTimeDisplay` | 18 `kBool` | 1 | `bool` |  | `On/off displaying time values instead of numerics` |
| 11 | `TStreamerString` | `fTimeFormat` | 65 `kTString` | 24 | `TString` |  | `Date&time format, ex: 09/12/99 12:34:00` |
| 12 | `TStreamerObjectPointer` | `fLabels` | 64 `kObjectP` | 8 | `THashList*` |  | `List of labels` |
| 13 | `TStreamerObjectPointer` | `fModLabs` | 64 `kObjectP` | 8 | `TList*` |  | `List of modified labels` |

### `TH1`

Class version **8**, `fCheckSum` **`0x1c3740c4`**. 26 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TNamed` | 67 `kTNamed` | 0 | `BASE` | base version 1; base checksum `0xdfb74a3c` | `The basis for a named object (name, title)` |
| 2 | `TStreamerBase` | `TAttLine` | 0 `kBase` | 0 | `BASE` | base version 2; base checksum `0x94074549` | `Line attributes` |
| 3 | `TStreamerBase` | `TAttFill` | 0 `kBase` | 0 | `BASE` | base version 2; base checksum `0xffd92a92` | `Fill area attributes` |
| 4 | `TStreamerBase` | `TAttMarker` | 0 `kBase` | 0 | `BASE` | base version 3; base checksum `0x291d8bec` | `Marker attributes` |
| 5 | `TStreamerBasicType` | `fNcells` | 3 `kInt` | 4 | `int` |  | `Number of bins(1D), cells (2D) +U/Overflows` |
| 6 | `TStreamerObject` | `fXaxis` | 61 `kObject` | 216 | `TAxis` |  | `X axis descriptor` |
| 7 | `TStreamerObject` | `fYaxis` | 61 `kObject` | 216 | `TAxis` |  | `Y axis descriptor` |
| 8 | `TStreamerObject` | `fZaxis` | 61 `kObject` | 216 | `TAxis` |  | `Z axis descriptor` |
| 9 | `TStreamerBasicType` | `fBarOffset` | 2 `kShort` | 2 | `short` |  | `(1000*offset) for bar charts or legos` |
| 10 | `TStreamerBasicType` | `fBarWidth` | 2 `kShort` | 2 | `short` |  | `(1000*width) for bar charts or legos` |
| 11 | `TStreamerBasicType` | `fEntries` | 8 `kDouble` | 8 | `double` |  | `Number of entries` |
| 12 | `TStreamerBasicType` | `fTsumw` | 8 `kDouble` | 8 | `double` |  | `Total Sum of weights` |
| 13 | `TStreamerBasicType` | `fTsumw2` | 8 `kDouble` | 8 | `double` |  | `Total Sum of squares of weights` |
| 14 | `TStreamerBasicType` | `fTsumwx` | 8 `kDouble` | 8 | `double` |  | `Total Sum of weight*X` |
| 15 | `TStreamerBasicType` | `fTsumwx2` | 8 `kDouble` | 8 | `double` |  | `Total Sum of weight*X*X` |
| 16 | `TStreamerBasicType` | `fMaximum` | 8 `kDouble` | 8 | `double` |  | `Maximum value for plotting` |
| 17 | `TStreamerBasicType` | `fMinimum` | 8 `kDouble` | 8 | `double` |  | `Minimum value for plotting` |
| 18 | `TStreamerBasicType` | `fNormFactor` | 8 `kDouble` | 8 | `double` |  | `Normalization factor` |
| 19 | `TStreamerObjectAny` | `fContour` | 62 `kAny` | 24 | `TArrayD` |  | `Array to display contour levels` |
| 20 | `TStreamerObjectAny` | `fSumw2` | 62 `kAny` | 24 | `TArrayD` |  | `Array of sum of squares of weights` |
| 21 | `TStreamerString` | `fOption` | 65 `kTString` | 24 | `TString` |  | `Histogram options` |
| 22 | `TStreamerObjectPointer` | `fFunctions` | 63 `kObjectp` | 8 | `TList*` |  | `->Pointer to list of functions (fits and user)` |
| 23 | `TStreamerBasicType` | `fBufferSize` | 6 `kCounter` | 4 | `int` |  | `fBuffer size` |
| 24 | `TStreamerBasicPointer` | `fBuffer` | 48 `kDouble + kOffsetP` | 8 | `double*` | counter `fBufferSize` in `TH1` at version 8 | `[fBufferSize] entry buffer` |
| 25 | `TStreamerBasicType` | `fBinStatErrOpt` | 3 `kInt` | 4 | `TH1::EBinErrorOpt` |  | `Option for bin statistical errors` |
| 26 | `TStreamerBasicType` | `fStatOverflows` | 3 `kInt` | 4 | `TH1::EStatOverflows` |  | `Per object flag to use under/overflows in statistics` |

### `TH1F`

Class version **3**, `fCheckSum` **`0xe2939644`**. 2 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TH1` | 0 `kBase` | 0 | `BASE` | base version 8; base checksum `0x1c3740c4` | `1-Dim histogram base class` |
| 2 | `TStreamerBase` | `TArrayF` | 0 `kBase` | 0 | `BASE` | base version 1; base checksum `0x5a0bf6f1` | `Array of floats` |

### `TH1D`

Class version **3**, `fCheckSum` **`0xf9b1569f`**. 2 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TH1` | 0 `kBase` | 0 | `BASE` | base version 8; base checksum `0x1c3740c4` | `1-Dim histogram base class` |
| 2 | `TStreamerBase` | `TArrayD` | 0 `kBase` | 0 | `BASE` | base version 1; base checksum `0x7139ef34` | `Array of doubles` |
<!-- END GENERATED -->

## 6. A `TH2` or `TProfile` file: the other four

With §4 and §5 these are the eighteen of
[Writing histograms §9](WritingHistograms.md#9-the-streamer-infos). `TH2` sits
between `TH1` and the concrete classes; `TProfile` sits **below** `TH1D`, so it
is the one class here whose base is itself a concrete histogram.

`TProfile` is also the only class in this document with an **enum** member
outside `TH1` — `fErrorMode`, whose `fTypeName` is the unqualified `EErrorType`
because the enum is declared at file scope
(`root/hist/hist/inc/TProfile.h:28`). An enum folds an extra 1 into the
checksum, so a writer that misses it cannot produce `0x4bedee54`
([StreamerInfo §11.1](../02-serialization/StreamerInfo.md#111-an-enum-member-is-recognisable-and-it-changes-the-value)).
`TH2`, by contrast, adds four plain doubles and nothing else.

<!-- BEGIN GENERATED: derived -->
### `TH2`

Class version **5**, `fCheckSum` **`0x0182347f`**. 5 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TH1` | 0 `kBase` | 0 | `BASE` | base version 8; base checksum `0x1c3740c4` | `1-Dim histogram base class` |
| 2 | `TStreamerBasicType` | `fScalefactor` | 8 `kDouble` | 8 | `double` |  | `Scale factor` |
| 3 | `TStreamerBasicType` | `fTsumwy` | 8 `kDouble` | 8 | `double` |  | `Total Sum of weight*Y` |
| 4 | `TStreamerBasicType` | `fTsumwy2` | 8 `kDouble` | 8 | `double` |  | `Total Sum of weight*Y*Y` |
| 5 | `TStreamerBasicType` | `fTsumwxy` | 8 `kDouble` | 8 | `double` |  | `Total Sum of weight*X*Y` |

### `TH2F`

Class version **4**, `fCheckSum` **`0x689cc295`**. 2 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TH2` | 0 `kBase` | 0 | `BASE` | base version 5; base checksum `0x0182347f` | `2-Dim histogram base class` |
| 2 | `TStreamerBase` | `TArrayF` | 0 `kBase` | 0 | `BASE` | base version 1; base checksum `0x5a0bf6f1` | `Array of floats` |

### `TH2D`

Class version **4**, `fCheckSum` **`0x7fba82f0`**. 2 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TH2` | 0 `kBase` | 0 | `BASE` | base version 5; base checksum `0x0182347f` | `2-Dim histogram base class` |
| 2 | `TStreamerBase` | `TArrayD` | 0 `kBase` | 0 | `BASE` | base version 1; base checksum `0x7139ef34` | `Array of doubles` |

### `TProfile`

Class version **7**, `fCheckSum` **`0x4bedee54`**. 8 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TH1D` | 0 `kBase` | 0 | `BASE` | base version 3; base checksum `0xf9b1569f` | `1-Dim histograms (one double per channel)` |
| 2 | `TStreamerObjectAny` | `fBinEntries` | 62 `kAny` | 24 | `TArrayD` |  | `number of entries per bin` |
| 3 | `TStreamerBasicType` | `fErrorMode` | 3 `kInt` | 4 | `EErrorType` |  | `Option to compute errors` |
| 4 | `TStreamerBasicType` | `fYmin` | 8 `kDouble` | 8 | `double` |  | `Lower limit in Y (if set)` |
| 5 | `TStreamerBasicType` | `fYmax` | 8 `kDouble` | 8 | `double` |  | `Upper limit in Y (if set)` |
| 6 | `TStreamerBasicType` | `fTsumwy` | 8 `kDouble` | 8 | `double` |  | `Total Sum of weight*Y` |
| 7 | `TStreamerBasicType` | `fTsumwy2` | 8 `kDouble` | 8 | `double` |  | `Total Sum of weight*Y*Y` |
| 8 | `TStreamerObjectAny` | `fBinSumw2` | 62 `kAny` | 24 | `TArrayD` |  | `Array of sum of squares of weights per bin` |
<!-- END GENERATED -->

## 7. A flat tree file: the other nine

With §4 these are the eighteen of
[Writing trees §8](WritingTrees.md#8-the-streamer-infos). `TBranchRef`,
`TRefTable` and `TObjArray` are all reached through null pointers the same way,
and `ROOT::TIOFeatures` is the one class here with no `ClassDef` at all — an
object of it carries a version word of 0 followed by a checksum
([Writing an object §2](WritingObjects.md#2-a-version-word-of-0-and-when-a-writer-must-emit-one)),
while its info records class version 1.

<!-- BEGIN GENERATED: tree -->
### `TObjArray`

Class version **3**, `fCheckSum` **`0xa99e6552`**. 3 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TSeqCollection` | 0 `kBase` | 0 | `BASE` | base version 0; base checksum `0xfc6c3bc6` | `Sequenceable collection ABC` |
| 2 | `TStreamerBasicType` | `fLowerBound` | 3 `kInt` | 4 | `int` |  | `Lower bound of the array` |
| 3 | `TStreamerBasicType` | `fLast` | 3 `kInt` | 4 | `int` |  | `Last element in array containing an object` |

### `ROOT::TIOFeatures`

Class version **1**, `fCheckSum` **`0x1aa12f10`**. 1 element.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBasicType` | `fIOBits` | 11 `kUChar` | 1 | `unsigned char` |  |  |

### `TLeaf`

Class version **2**, `fCheckSum` **`0x6d1e8152`**. 7 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TNamed` | 67 `kTNamed` | 0 | `BASE` | base version 1; base checksum `0xdfb74a3c` | `The basis for a named object (name, title)` |
| 2 | `TStreamerBasicType` | `fLen` | 3 `kInt` | 4 | `int` |  | `Number of fixed length elements in the leaf's data.` |
| 3 | `TStreamerBasicType` | `fLenType` | 3 `kInt` | 4 | `int` |  | `Number of bytes for this data type` |
| 4 | `TStreamerBasicType` | `fOffset` | 3 `kInt` | 4 | `int` |  | `Offset in ClonesArray object (if one)` |
| 5 | `TStreamerBasicType` | `fIsRange` | 18 `kBool` | 1 | `bool` |  | `(=true if leaf has a range, false otherwise).  This is equivalent to being a 'leafcount'.  For a TLeafElement the range information is actually store in the TBranchElement.` |
| 6 | `TStreamerBasicType` | `fIsUnsigned` | 18 `kBool` | 1 | `bool` |  | `(=true if unsigned, false otherwise)` |
| 7 | `TStreamerObjectPointer` | `fLeafCount` | 64 `kObjectP` | 8 | `TLeaf*` |  | `Pointer to Leaf count if variable length (we do not own the counter)` |

### `TLeafI`

Class version **1**, `fCheckSum` **`0x7e6aae19`**. 3 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TLeaf` | 0 `kBase` | 0 | `BASE` | base version 2; base checksum `0x6d1e8152` | `Leaf: description of a Branch data type` |
| 2 | `TStreamerBasicType` | `fMinimum` | 3 `kInt` | 4 | `int` |  | `Minimum value if leaf range is specified` |
| 3 | `TStreamerBasicType` | `fMaximum` | 3 `kInt` | 4 | `int` |  | `Maximum value if leaf range is specified` |

### `TLeafF`

Class version **1**, `fCheckSum` **`0x3add9d72`**. 3 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TLeaf` | 0 `kBase` | 0 | `BASE` | base version 2; base checksum `0x6d1e8152` | `Leaf: description of a Branch data type` |
| 2 | `TStreamerBasicType` | `fMinimum` | 5 `kFloat` | 4 | `float` |  | `Minimum value if leaf range is specified` |
| 3 | `TStreamerBasicType` | `fMaximum` | 5 `kFloat` | 4 | `float` |  | `Maximum value if leaf range is specified` |

### `TBranch`

Class version **13**, `fCheckSum` **`0x10978aac`**. 22 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TNamed` | 67 `kTNamed` | 0 | `BASE` | base version 1; base checksum `0xdfb74a3c` | `The basis for a named object (name, title)` |
| 2 | `TStreamerBase` | `TAttFill` | 0 `kBase` | 0 | `BASE` | base version 2; base checksum `0xffd92a92` | `Fill area attributes` |
| 3 | `TStreamerBasicType` | `fCompress` | 3 `kInt` | 4 | `int` |  | `Compression level and algorithm` |
| 4 | `TStreamerBasicType` | `fBasketSize` | 3 `kInt` | 4 | `int` |  | `Initial Size of  Basket Buffer` |
| 5 | `TStreamerBasicType` | `fEntryOffsetLen` | 3 `kInt` | 4 | `int` |  | `Initial Length of fEntryOffset table in the basket buffers` |
| 6 | `TStreamerBasicType` | `fWriteBasket` | 3 `kInt` | 4 | `int` |  | `Last basket number written` |
| 7 | `TStreamerBasicType` | `fEntryNumber` | 16 `kLong64` | 8 | `Long64_t` |  | `Current entry number (last one filled in this branch)` |
| 8 | `TStreamerObjectAny` | `fIOFeatures` | 62 `kAny` | 1 | `ROOT::TIOFeatures` |  | `IO features for newly-created baskets.` |
| 9 | `TStreamerBasicType` | `fOffset` | 3 `kInt` | 4 | `int` |  | `Offset of this branch` |
| 10 | `TStreamerBasicType` | `fMaxBaskets` | 6 `kCounter` | 4 | `int` |  | `Maximum number of Baskets so far` |
| 11 | `TStreamerBasicType` | `fSplitLevel` | 3 `kInt` | 4 | `int` |  | `Branch split level` |
| 12 | `TStreamerBasicType` | `fEntries` | 16 `kLong64` | 8 | `Long64_t` |  | `Number of entries` |
| 13 | `TStreamerBasicType` | `fFirstEntry` | 16 `kLong64` | 8 | `Long64_t` |  | `Number of the first entry in this branch` |
| 14 | `TStreamerBasicType` | `fTotBytes` | 16 `kLong64` | 8 | `Long64_t` |  | `Total number of bytes in all leaves before compression` |
| 15 | `TStreamerBasicType` | `fZipBytes` | 16 `kLong64` | 8 | `Long64_t` |  | `Total number of bytes in all leaves after compression` |
| 16 | `TStreamerObject` | `fBranches` | 61 `kObject` | 64 | `TObjArray` |  | `-> List of Branches of this branch` |
| 17 | `TStreamerObject` | `fLeaves` | 61 `kObject` | 64 | `TObjArray` |  | `-> List of leaves of this branch` |
| 18 | `TStreamerObject` | `fBaskets` | 61 `kObject` | 64 | `TObjArray` |  | `-> List of baskets of this branch` |
| 19 | `TStreamerBasicPointer` | `fBasketBytes` | 43 `kInt + kOffsetP` | 4 | `int*` | counter `fMaxBaskets` in `TBranch` at version 13 | `[fMaxBaskets] Length of baskets on file` |
| 20 | `TStreamerBasicPointer` | `fBasketEntry` | 56 `kLong64 + kOffsetP` | 8 | `Long64_t*` | counter `fMaxBaskets` in `TBranch` at version 13 | `[fMaxBaskets] Table of first entry in each basket` |
| 21 | `TStreamerBasicPointer` | `fBasketSeek` | 56 `kLong64 + kOffsetP` | 8 | `Long64_t*` | counter `fMaxBaskets` in `TBranch` at version 13 | `[fMaxBaskets] Addresses of baskets on file` |
| 22 | `TStreamerString` | `fFileName` | 65 `kTString` | 24 | `TString` |  | `Name of file where buffers are stored ("" if in same file as Tree header)` |

### `TRefTable`

Class version **3**, `fCheckSum` **`0x8c895b85`**. 5 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TObject` | 66 `kTObject` | 0 | `BASE` | base version 1; base checksum `0x901bc02d` | `Basic ROOT object` |
| 2 | `TStreamerBasicType` | `fSize` | 3 `kInt` | 4 | `int` |  | `dummy for backward compatibility` |
| 3 | `TStreamerObjectPointer` | `fParents` | 64 `kObjectP` | 8 | `TObjArray*` |  | `array of Parent objects  (eg TTree branch) holding the referenced objects` |
| 4 | `TStreamerObjectPointer` | `fOwner` | 64 `kObjectP` | 8 | `TObject*` |  | `Object owning this TRefTable` |
| 5 | `TStreamerSTL` | `fProcessGUIDs` | 500 `kStreamer` | 24 | `vector<string>` | `fSTLtype` 1 (vector); `fCtype` 61 (`kObject`) | `UUIDs of TProcessIDs used in fParentIDs` |

### `TBranchRef`

Class version **1**, `fCheckSum` **`0x2360b3fd`**. 2 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TBranch` | 0 `kBase` | 0 | `BASE` | base version 13; base checksum `0x10978aac` | `Branch descriptor` |
| 2 | `TStreamerObjectPointer` | `fRefTable` | 64 `kObjectP` | 8 | `TRefTable*` |  | `pointer to the TRefTable` |

### `TTree`

Class version **20**, `fCheckSum` **`0x7264e07f`**. 33 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TNamed` | 67 `kTNamed` | 0 | `BASE` | base version 1; base checksum `0xdfb74a3c` | `The basis for a named object (name, title)` |
| 2 | `TStreamerBase` | `TAttLine` | 0 `kBase` | 0 | `BASE` | base version 2; base checksum `0x94074549` | `Line attributes` |
| 3 | `TStreamerBase` | `TAttFill` | 0 `kBase` | 0 | `BASE` | base version 2; base checksum `0xffd92a92` | `Fill area attributes` |
| 4 | `TStreamerBase` | `TAttMarker` | 0 `kBase` | 0 | `BASE` | base version 3; base checksum `0x291d8bec` | `Marker attributes` |
| 5 | `TStreamerBasicType` | `fEntries` | 16 `kLong64` | 8 | `Long64_t` |  | `Number of entries` |
| 6 | `TStreamerBasicType` | `fTotBytes` | 16 `kLong64` | 8 | `Long64_t` |  | `Total number of bytes in all branches before compression` |
| 7 | `TStreamerBasicType` | `fZipBytes` | 16 `kLong64` | 8 | `Long64_t` |  | `Total number of bytes in all branches after compression` |
| 8 | `TStreamerBasicType` | `fSavedBytes` | 16 `kLong64` | 8 | `Long64_t` |  | `Number of autosaved bytes` |
| 9 | `TStreamerBasicType` | `fFlushedBytes` | 16 `kLong64` | 8 | `Long64_t` |  | `Number of auto-flushed bytes` |
| 10 | `TStreamerBasicType` | `fWeight` | 8 `kDouble` | 8 | `double` |  | `Tree weight (see TTree::SetWeight)` |
| 11 | `TStreamerBasicType` | `fTimerInterval` | 3 `kInt` | 4 | `int` |  | `Timer interval in milliseconds` |
| 12 | `TStreamerBasicType` | `fScanField` | 3 `kInt` | 4 | `int` |  | `Number of runs before prompting in Scan` |
| 13 | `TStreamerBasicType` | `fUpdate` | 3 `kInt` | 4 | `int` |  | `Update frequency for EntryLoop` |
| 14 | `TStreamerBasicType` | `fDefaultEntryOffsetLen` | 3 `kInt` | 4 | `int` |  | `Initial Length of fEntryOffset table in the basket buffers` |
| 15 | `TStreamerBasicType` | `fNClusterRange` | 6 `kCounter` | 4 | `int` |  | `Number of Cluster range in addition to the one defined by 'AutoFlush'` |
| 16 | `TStreamerBasicType` | `fMaxEntries` | 16 `kLong64` | 8 | `Long64_t` |  | `Maximum number of entries in case of circular buffers` |
| 17 | `TStreamerBasicType` | `fMaxEntryLoop` | 16 `kLong64` | 8 | `Long64_t` |  | `Maximum number of entries to process` |
| 18 | `TStreamerBasicType` | `fMaxVirtualSize` | 16 `kLong64` | 8 | `Long64_t` |  | `Maximum total size of buffers kept in memory` |
| 19 | `TStreamerBasicType` | `fAutoSave` | 16 `kLong64` | 8 | `Long64_t` |  | `Autosave tree when fAutoSave entries written or -fAutoSave (compressed) bytes produced` |
| 20 | `TStreamerBasicType` | `fAutoFlush` | 16 `kLong64` | 8 | `Long64_t` |  | `Auto-flush tree when fAutoFlush entries written or -fAutoFlush (compressed) bytes produced` |
| 21 | `TStreamerBasicType` | `fEstimate` | 16 `kLong64` | 8 | `Long64_t` |  | `Number of entries to estimate histogram limits` |
| 22 | `TStreamerBasicPointer` | `fClusterRangeEnd` | 56 `kLong64 + kOffsetP` | 8 | `Long64_t*` | counter `fNClusterRange` in `TTree` at version 20 | `[fNClusterRange] Last entry of a cluster range.` |
| 23 | `TStreamerBasicPointer` | `fClusterSize` | 56 `kLong64 + kOffsetP` | 8 | `Long64_t*` | counter `fNClusterRange` in `TTree` at version 20 | `[fNClusterRange] Number of entries in each cluster for a given range.` |
| 24 | `TStreamerObjectAny` | `fIOFeatures` | 62 `kAny` | 1 | `ROOT::TIOFeatures` |  | `IO features to define for newly-written baskets and branches.` |
| 25 | `TStreamerObject` | `fBranches` | 61 `kObject` | 64 | `TObjArray` |  | `List of Branches` |
| 26 | `TStreamerObject` | `fLeaves` | 61 `kObject` | 64 | `TObjArray` |  | `Direct pointers to individual branch leaves` |
| 27 | `TStreamerObjectPointer` | `fAliases` | 64 `kObjectP` | 8 | `TList*` |  | `List of aliases for expressions based on the tree branches.` |
| 28 | `TStreamerObjectAny` | `fIndexValues` | 62 `kAny` | 24 | `TArrayD` |  | `Sorted index values` |
| 29 | `TStreamerObjectAny` | `fIndex` | 62 `kAny` | 24 | `TArrayI` |  | `Index of sorted values` |
| 30 | `TStreamerObjectPointer` | `fTreeIndex` | 64 `kObjectP` | 8 | `TVirtualIndex*` |  | `Pointer to the tree Index (if any)` |
| 31 | `TStreamerObjectPointer` | `fFriends` | 64 `kObjectP` | 8 | `TList*` |  | `pointer to list of friend elements` |
| 32 | `TStreamerObjectPointer` | `fUserInfo` | 64 `kObjectP` | 8 | `TList*` |  | `pointer to a list of user objects associated to this Tree` |
| 33 | `TStreamerObjectPointer` | `fBranchRef` | 64 `kObjectP` | 8 | `TBranchRef*` |  | `Branch supporting the TRefTable (if any)` |
<!-- END GENERATED -->

## 8. A file of one object: `TObjString`

The smallest file that needs a `StreamerInfo` record at all. `TObjString` is a
`TObject` and a `TString`, so with §4's first three tables this is a complete set,
and it is the one this project's `StreamerInfo` record is compared against byte for
byte ([Writing an object §7.4](WritingObjects.md#74-the-check-that-this-procedure-passes)).

It is also what `data/written/nested-subdir.root` holds at each of its three
directory levels, which is what makes that file reproducible from this document
rather than from `tools/rootwrite.py`.

<!-- BEGIN GENERATED: objstring -->
<!-- END GENERATED -->

## 9. Three classes no file describes

`TArray`, `TArrayF` and `TArrayD` have hand-written streamers, so nothing marks
them and a histogram or profile file contains **no info for any of them**
([Writing an object §7.2](WritingObjects.md#72-which-classes-need-an-info)).
Their checksums are needed all the same, as the `fBaseCheckSum` of `TH1F`,
`TH1D`, `TH2F` and `TH2D`, so a writer has to build the element lists below
without ever emitting them. The tables are read from `data/classes/tarray-histogram.root`, where a
`TH2F` inside a `TTree` branch is streamed through a path that does mark them.

<!-- BEGIN GENERATED: arrays -->
### `TArray`

Class version **1**, `fCheckSum` **`0x007021b2`**. 1 element.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBasicType` | `fN` | 6 `kCounter` | 4 | `int` |  | `Number of array elements` |

### `TArrayF`

Class version **1**, `fCheckSum` **`0x5a0bf6f1`**. 2 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TArray` | 0 `kBase` | 0 | `BASE` | base version 1; base checksum `0x007021b2` | `Abstract array base class` |
| 2 | `TStreamerBasicPointer` | `fArray` | 45 `kFloat + kOffsetP` | 4 | `float*` | counter `fN` in `TArray` at version 1 | `[fN] Array of fN floats` |

### `TArrayD`

Class version **1**, `fCheckSum` **`0x7139ef34`**. 2 elements.

| # | Element class | `fName` | `fType` | `fSize` | `fTypeName` | Extra | `fTitle` |
|---|---|---|---|---|---|---|---|
| 1 | `TStreamerBase` | `TArray` | 0 `kBase` | 0 | `BASE` | base version 1; base checksum `0x007021b2` | `Abstract array base class` |
| 2 | `TStreamerBasicPointer` | `fArray` | 48 `kDouble + kOffsetP` | 8 | `double*` | counter `fN` in `TArray` at version 1 | `[fN] Array of fN doubles` |
<!-- END GENERATED -->

## 10. The order ROOT writes them in

Registration order, which is neither alphabetical nor dependency order. **A
reader does not care**, and a writer is free to choose its own — the order is
what makes a record byte-comparable with ROOT's, and that is all it is for.

<!-- BEGIN GENERATED: order -->
**A histogram file** — 15 infos, as `data/classes/histogram.root` carries them:

```
TH1F  TH1  TNamed  TObject  TAttLine  TAttFill  TAttMarker  TAxis  TAttAxis
THashList  TList  TSeqCollection  TCollection  TString  TH1D
```

**A TH2 and TProfile file** — 18 infos, as `data/classes/th2-profile.root` carries them:

```
TH2F  TH2  TH1  TNamed  TObject  TAttLine  TAttFill  TAttMarker  TAxis  TAttAxis
THashList  TList  TSeqCollection  TCollection  TString  TH2D  TProfile
TH1D
```

**A flat tree file** — 18 infos, as `data/ttree/basket.root` carries them:

```
TTree  TNamed  TObject  TAttLine  TAttFill  TAttMarker  ROOT::TIOFeatures
TBranch  TLeafI  TLeaf  TLeafF  TList  TSeqCollection  TCollection  TString
TBranchRef  TRefTable  TObjArray
```

**A file of one object** — 1 infos, as `data/container/file-minimal.root` carries them:

```
TObjString
```
<!-- END GENERATED -->

## 11. Class versions

The version each info records, which is also the version an object of that class
must carry in its version word. Checked against `ClassDef` in the pinned
submodule by `tools/check_versions.py`, so this table and §4 to §9 together say
that the fixtures' values *are* the current ones.

<!-- BEGIN GENERATED: versions -->
| Class | Version | Sets |
|---|---|---|
| `TArray` | 1 | neither: no info is written |
| `TArrayD` | 1 | neither: no info is written |
| `TArrayF` | 1 | neither: no info is written |
| `TAttAxis` | 4 | histogram, th2-profile |
| `TAttFill` | 2 | histogram, th2-profile, tree |
| `TAttLine` | 2 | histogram, th2-profile, tree |
| `TAttMarker` | 3 | histogram, th2-profile, tree |
| `TAxis` | 10 | histogram, th2-profile |
| `TBranch` | 13 | tree |
| `TBranchRef` | 1 | tree |
| `TCollection` | 3 | histogram, th2-profile, tree |
| `TH1` | 8 | histogram, th2-profile |
| `TH1D` | 3 | histogram, th2-profile |
| `TH1F` | 3 | histogram |
| `TH2` | 5 | th2-profile |
| `TH2D` | 4 | th2-profile |
| `TH2F` | 4 | th2-profile |
| `THashList` | 0 | histogram, th2-profile |
| `TLeaf` | 2 | tree |
| `TLeafF` | 1 | tree |
| `TLeafI` | 1 | tree |
| `TList` | 5 | histogram, th2-profile, tree |
| `TNamed` | 1 | histogram, th2-profile, tree |
| `TObjArray` | 3 | tree |
| `TObject` | 1 | histogram, th2-profile, tree |
| `TObjString` | 1 | objstring |
| `TProfile` | 7 | th2-profile |
| `TRefTable` | 3 | tree |
| `TSeqCollection` | 0 | histogram, th2-profile, tree |
| `TString` | 2 | histogram, th2-profile, tree |
| `TTree` | 20 | tree |
<!-- END GENERATED -->

`ROOT::TIOFeatures` is absent because it has no `ClassDef` to check: it is a
foreign class, and 1 is what its info records
([Writing trees §3.2](WritingTrees.md#32-fiofeatures-is-the-one-foreign-class-a-tree-contains)).

## 12. Invariants

1. Every element's `fTypeName` is the resolved spelling of its type, and for a
   `TStreamerBase` it is exactly `BASE`.
2. A `TStreamerBase` element's `fMaxIndex[1]` equals the `fCheckSum` of the info
   for the class it names, at the version its `fBaseVersion` gives.
3. A `TStreamerBasicPointer`'s counter names a member that exists in the class
   `fCountClass` names, and that member's `fType` is 6 `kCounter`.
4. Each info's checksum is what
   [StreamerInfo §11](../02-serialization/StreamerInfo.md#11-checksums) produces
   from its own element list, except for a class of version 0.
5. Each class version in §11 is the one `ClassDef` declares in the pinned
   submodule.

1 to 4 are checked by `tools/element_lists.py` over the five reference files; 4
is checked for every info in every reference file by `tools/test_write.py`, and 5
by `tools/check_versions.py`.

## 13. Errata

Not against ROOT's shipped documentation, which says nothing about element lists,
but against two claims a writer will otherwise make from the class definitions.
Both were wrong in *this project's* writer until the tables were published, and
both are invisible to every check that does not compare an element's subclass tail
byte for byte — the fields below are in no checksum and in no byte count.

| # | Claim | Correction |
|---|---|---|
| 1 | A counter member is declared with `fType` 6 `kCounter` | `kCounter` is not a property of the declaration: `TStreamerInfo::Build` gives the member `kInt`, and it is **promoted** to `kCounter` when some other element names it as a counter (`root/core/meta/src/TStreamerElement.cxx:99`). `TArray::fN` is 6 only because `TArrayF::fArray` points at it, and a member that nothing counts stays 3 — `TCollection::fSize` is the contrast in §4. ROOT's own comment records that the switch "might be triggered by a derived class" (`root/io/io/src/TStreamerInfo.cxx:2969-2970`) |
| 2 | A `vector<string>` member has `fCtype` 365 `kSTLstring` | 365 is what `TStreamerSTLstring` sets for itself (`root/core/meta/src/TStreamerElement.cxx:2194`). A `TStreamerSTL` for `vector<string>` records 61 `kObject`, because the value type has a dictionary (`:1810-1812`) — and `std::string` has one. This is the only one of the two that reaches a file: it is `TRefTable::fProcessGUIDs`, in every tree file |

## 14. Reference files

| File | What it supplies |
|---|---|
| `data/classes/histogram.root` | §4 and §5, and the histogram order in §10 — ROOT's own fifteen infos |
| `data/ttree/basket.root` | §4 and §7, and the tree order in §10 — ROOT's own eighteen |
| `data/classes/th2-profile.root` | §6, and a second copy of §4, §5's `TAxis` chain and `TH1D` — ROOT's own eighteen |
| `data/classes/tarray-histogram.root` | §9, plus a second independent copy of thirteen of the classes in §4 to §7 |
| `data/container/file-minimal.root` | §8, and a third copy of `TObject` and `TString`'s checksums |
| `data/written/histogram.root`, `data/written/th2-profile.root`, `data/written/tree.root` | the same infos written from these tables; the histogram file's whole `StreamerInfo` record is byte-identical to ROOT's, all 9628 bytes |
