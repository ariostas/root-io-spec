# Writing a graph

How to produce a `TGraph` or a `TGraphErrors` that ROOT reads, draws and fits: the
four attribute bases, the two counted arrays that hold the points, and the three
members a writer is most likely to fill in wrongly.

Prerequisites: [Writing a file](WritingFiles.md),
[Writing an object](WritingObjects.md), and the reading side —
[Buffer framing](../02-serialization/Buffer.md),
[Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer),
[Streamer-driven reading](../02-serialization/StreamerDriven.md).
[Element lists §9](ElementLists.md#9-a-graph-file-the-other-two) is the streamer
info to emit for each class.

A graph is the simplest class in this layer: no axes, no bins, no statistics, and
every byte of it described by its own streamer info. The work is entirely in the
values, and §3 is where a writer's guesses turn out to be wrong.

## 1. The shape, and how far it is checked

`TGraph`'s `Streamer` is hand-written but **delegating above version 2**
(`root/hist/hist/src/TGraph.cxx:2561`): the write branch is a plain
`WriteClassBuffer` and the read branch calls `ReadClassBuffer` for anything at
version 3 or above and reads nothing after it. So a current file's bytes are
exactly what the streamer info describes, and a writer can emit one from the
element list alone. The same holds for `TGraphErrors`
(`root/hist/hist/src/TGraphErrors.cxx:820`).

What the read branch *does* do after `ReadClassBuffer` consumes no bytes and so
concerns a writer only as a description of what ROOT will make of its output
(`root/hist/hist/src/TGraph.cxx:2567-2578`): it detaches `fHistogram` from any
directory, re-parents every `TF1` in `fFunctions`, and sets `fMaxSize = fNpoints`.
By [Hand-written streamers](../99-appendix/HandWrittenStreamers.md)' taxonomy the
class is therefore `guarded` and not `extending` — nothing sits outside the byte
count.

**The worked example is a byte-for-byte pair, and so is the whole
`StreamerInfo` record.**

| This project's | ROOT's | What matches |
|---|---|---|
| `data/written/graph.root` | `data/classes/graph.root` | the `TGraph` record (198 bytes) and the `TGraphErrors` record (271), and the entire `StreamerInfo` record — **all 12169 bytes of nineteen infos**, with nothing to subtract |

Unlike the tree and profile pairs there is no `listOfRules` here, so the info
record matches completely; and unlike every other pair the file names did not have
to be the same length, because a graph stores no offsets. The class map is measured
from the start of the record
([Writing an object §4](WritingObjects.md#4-class-records-and-the-object-map)), so an equal **key
length** — the same class, key name and title — is all a record comparison needs.

## 2. The record

| Offset in `g`'s 198 bytes of object data | Bytes | What |
|---|---|---|
| 0 | 4 + 2 | `TGraph`'s byte count and class version **5** |
| 6 | 4 + 2 + 10 + `sizeof(fName)` + `sizeof(fTitle)` | the `TNamed` base: framed at version 1, a `TObject`, then the two counted strings |
| … | 4 + 2 + 6 | `TAttLine` framed at version 2: three `i16` |
| … | 4 + 2 + 4 | `TAttFill` framed at version 2: two `i16` |
| … | 4 + 2 + 8 | `TAttMarker` framed at version 3: two `i16` and an `f32` |
| … | 4 | `fNpoints` |
| … | 1 + 8·`fNpoints` | `fX`: a flag byte, then the values (§3.2) |
| … | 1 + 8·`fNpoints` | `fY`, the same |
| … | 4 + 11 + 4 + 2 + 15 | `fFunctions`: a pointer slot holding an empty `TList` (§3.5) |
| … | 4 | `fHistogram`: a null pointer (§3.4) |
| … | 8 + 8 | `fMinimum`, `fMaximum` (§3.3) |
| … | `sizeof(fOption)` | `fOption`, a counted string — empty in every graph ROOT writes |

> For `g` — name `g`, title `four points`, four points — those land at 0, 6, 36,
> 48, 58, 72, 76, 109, 142, 177, 181 and 197, and the record's object data begins
> at 301 in `data/classes/graph.root`. The case asserts each of them.

## 3. The fields

| Field | Value | Kind |
|---|---|---|
| `TNamed` | `fName` and `fTitle`. Every constructor that takes a point count sets **both to `Graph`** (`root/hist/hist/src/TGraph.cxx:202`); the default constructor leaves both **empty** (`:125`), which ROOT's own class documentation denies — erratum 1 | free |
| `TObject::fBits` | **`0x400`**, `TGraph::kClipFrame` — §3.1 | fixed by ROOT's constructor |
| `TAttLine` | 1, 1, 1 | free — §3.1 |
| `TAttFill` | 0, **1000** | free — §3.1 |
| `TAttMarker` | 1, 1, 1.0 | free — §3.1 |
| `fNpoints` | the number of points, and the length of every counted array in the record | derived |
| `fX`, `fY` | the points, in the order the writer supplies them (§3.2) | free |
| `fFunctions` | a pointer to an **empty `TList`**, never null (§3.5) | fixed |
| `fHistogram` | **null** (§3.4) | fixed, for a writer |
| `fMinimum`, `fMaximum` | the y range, or the `-1111` sentinel (§3.3) | free |
| `fOption` | an empty string. Nothing in ROOT ever assigns it for a `TGraph` | free |

### 3.1 The attribute values are not a histogram's

This is the one place a writer that has already done a histogram will get every
value wrong. Both classes fill their attribute bases at construction, and both
reach `gStyle` — but through different accessors, and a graph fixes its fill
attributes outright:

| | `TH1F` | `TGraph` |
|---|---|---|
| `fLineColor` | 602, from `gStyle` | **1** |
| `fFillColor`, `fFillStyle` | 0, 1001 | 0, **1000** |
| `fMarkerColor`, `fMarkerStyle`, `fMarkerSize` | 1, 1, 1.0 | 1, 1, 1.0 |
| `fBits` | `0x8`, `kMustCleanup` | **`0x400`**, `kClipFrame` |

`TAttFill` is **fixed**: every `TGraph` constructor carries the mem-initialiser
`TAttFill(0, 1000)` (`root/hist/hist/src/TGraph.cxx:125`, `:136`, `:147`, `:202`),
so 0 and 1000 do not depend on the style at all. `TAttLine` and `TAttMarker` are
default-constructed, and those constructors *do* read `gStyle` — but the general
accessors, `GetLineColor` and `GetMarkerColor`
(`root/core/base/src/TAttLine.cxx:142-148`,
`root/core/base/src/TAttMarker.cxx:210-216`), where `TH1` reads
`GetHistLineColor`. In ROOT's default `Modern` style the general pair is 1 and the
histogram one is 602, which is the whole of the difference. So the six line and
marker fields are **free** and style-dependent, and only the fill pair is fixed.
`TGraph::UseCurrentStyle` is the one path that would give a graph a histogram's
colours, and a user has to call it
(`root/hist/hist/src/TGraph.cxx:2671-2673`).

`fBits` is the other asymmetry: `TGraph::CtorAllocate` sets `kClipFrame`
(`root/hist/hist/src/TGraph.cxx:838`) and **nothing sets `kMustCleanup`**, which a
histogram in the same directory does carry. None of these five values is required
— they are drawing attributes — but reproducing them is what keeps a diff against
a ROOT-written file empty, and getting `fBits` wrong is the difference a byte
comparison finds first.

### 3.2 The points are two counted arrays, and nothing is sorted

`fX` and `fY` are `TStreamerBasicPointer` members declared `[fNpoints]`, so each
is one flag byte followed by exactly `fNpoints` big-endian doubles
([Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer)).
The flag is 1 for a non-null pointer and 0 for a null one, and `fNpoints == 0` is
written as the flag alone.

**ROOT stores the points in the order it is given.** The constructor `memcpy`s
both arrays straight in (`root/hist/hist/src/TGraph.cxx:210-212`), and nothing
sorts them; `TGraph::kIsSortedX` (`root/hist/hist/inc/TGraph.h:78`) is a *claim*
about the data that `Sort` sets, not an invariant of the class. A writer may emit
any order, including a non-monotonic x, and `data/classes/graph.root` has a
negative y in the middle for that reason.

`fNpoints` is `fType` **6 `kCounter`**, not 3 `kInt`, because `fX` and `fY` name
it — the promotion is done by whatever points at a member, not by its declaration
([Element lists §14](ElementLists.md#14-errata) erratum 1). And `fMaxSize`, the
allocated capacity, is `///<!` transient: the arrays on disk are exactly
`fNpoints` long however much room the writer had in memory.

### 3.3 `fMinimum` and `fMaximum` are the `TH1` sentinel in another class

Both are `-1111` when unset — `TGraph::CtorAllocate` assigns the literal
(`root/hist/hist/src/TGraph.cxx:836-837`) — which is the same sentinel `TH1`
uses for the same two field names
([Writing histograms §3](WritingHistograms.md#3-th1-at-version-8)). They bound the y
axis when the graph is drawn — `GetHistogram` applies each one when it is not the
sentinel (`root/hist/hist/src/TGraph.cxx:1496-1497`), and so does the painter
(`root/hist/histpainter/src/TGraphPainter.cxx:1373-1376`).

Two differences from `TH1` that a writer working from one will get wrong:

- **The order is reversed.** `TH1` declares `fMaximum` before `fMinimum`
  (`root/hist/hist/inc/TH1.h:161-162`) and a `TGraph` declares `fMinimum` first
  (`root/hist/hist/inc/TGraph.h:51-52`), so the two doubles appear in the opposite
  order in the two records.
- **The accessor does not compute.** `TGraph::GetMinimum` returns the field as
  stored (`root/hist/hist/inc/TGraph.h:150-151`), so a graph read back from a file
  reports `-1111` literally, where `TH1::GetMaximum` scans the bins when the field
  is unset and exposes the raw value as `GetMaximumStored`
  (`root/hist/hist/src/TH1.cxx:8700-8712`).

### 3.4 Leave `fHistogram` null — and ROOT's own API cannot

`fHistogram` is a `TH1F*` that exists only to carry the axes a graph is drawn
against. It is **null** in every graph that has never been drawn or fitted
(`root/hist/hist/src/TGraph.cxx:834`), and `TGraph::GetHistogram` builds one on
demand when something needs it. A writer should emit the null: the points and the
two range members are the data, and ROOT reconstructs the rest.

> **`TGraph::SetMinimum` materialises it, which multiplies the record by five.**
> The method assigns the field and then calls `GetHistogram()` unconditionally
> (`root/hist/hist/src/TGraph.cxx:2369-2382`), so a graph whose range was set
> through ROOT's API carries a whole `TH1F` inside its record. Measured on
> `data/classes/graph.root`: `g` and `gm` hold the same four points, and `g`'s
> record is **245 bytes** where `gm`'s is **1213** — 958 of them the histogram,
> which has 100 bins whatever `fNpoints` is
> (`root/hist/hist/src/TGraph.cxx:1520-1521`), the graph's own name and title, and
> `fBits` `0x200` for `TH1::kNoStats` (`:1533`).
>
> The two members are independent of the pointer on disk, and
> `data/written/graph.root` holds the object ROOT cannot produce: `gy`, with
> `fMinimum` −2, `fMaximum` 5 and `fHistogram` null, in 203 bytes. Its `verify.C`
> reads the range back from ROOT and then calls `GetHistogram()`, which builds one
> with those limits applied — so nothing at all is lost by leaving the pointer
> null.

### 3.5 `fFunctions` is an empty list, a pointer slot, and not a null

Every `TGraph` constructor does `fFunctions = new TList`
(`root/hist/hist/src/TGraph.cxx:839`), so ROOT never writes a null here and an
empty list costs 35 bytes of every graph record. A **null is nonetheless legal**:
every use of the member in `TGraph` is null-guarded
(`root/hist/hist/src/TGraph.cxx:1141`, `:1149`, `:2055-2057`, `:2482`) and `TIter`
tolerates a null collection
(`root/core/cont/inc/TCollection.h:246-247`), so a 167-byte record with four zero
bytes there reads back with no diagnostic and `fFunctions == nullptr`. This
project's writer emits the list, because matching ROOT is free and a reader of
someone else's file has to cope with either.

Two details about the list ROOT does write:

- **It is `fType` 64, where `TH1::fFunctions` is 63.** `TH1` declares its list
  `//->` and ROOT streams it in place, with no class record; `TGraph` declares a
  plain pointer, so the member is a full **pointer slot**: a byte count, a class
  record naming `TList`, then the framed object
  ([Writing an object §1](WritingObjects.md#1-the-two-framings)). That is 35 bytes for
  an empty list against `TH1`'s 21.
- **Its `fBits` are 0**, where the list inside a histogram carries `0x14000`. A
  graph's list is a bare `new TList` that nothing has adopted.

## 4. `TGraphErrors`, and how far this generalises

A `TGraphErrors` is class version **3**: the `TGraph` base at version 5, then two
more counted arrays of the same shape, `fEX` and `fEY`
(`root/hist/hist/inc/TGraphErrors.h`). Nothing else changes — no extra framing
beyond the outer byte count and version word, and the same delegating `Streamer`.

| Offset in `gr`'s 271 bytes | Bytes | What |
|---|---|---|
| 0 | 4 + 2 | `TGraphErrors`'s byte count and class version 3 |
| 6 | 199 | the whole `TGraph` block of §2, byte count and version word included |
| 205 | 1 + 8·`fNpoints` | `fEX` |
| 238 | 1 + 8·`fNpoints` | `fEY` |

**All four counted arrays name `TGraph` as their `fCountClass`**, `fEX` and `fEY`
included: `fNpoints` is declared two classes up from them, and the field names the
class the *counter* lives in rather than the class the array lives in
([Element lists §1](ElementLists.md#1-how-to-read-a-table)).

`TGraphAsymmErrors` (version 3) extends the same pattern with four arrays instead
of two, and `TGraphBentErrors` with eight; both are described entirely by their
streamer infos in the same way. Neither is specified here, and neither needs
anything this document does not already give — only its element list, which
[Element lists §2](ElementLists.md#2-what-the-tables-do-not-and-cannot-give-you)
says how to obtain.

> §6's checks run over anything deriving from `TGraph`, which the third-party corpus
> confirms reaches further than the two classes here: `uproot-issue-240.root` holds a
> `TGraphAsymmErrors` with its four counted arrays, and `uproot-issue-350.root` holds
> four RooFit graphs — a `RooHist` and three `RooCurve`s — that satisfy the same
> invariants. A reader written from this document handles all of them, because the
> only thing that changes is how many arrays `fNpoints` counts.

## 5. Nineteen streamer infos for a 198-byte object

A file holding **one** `TGraph` and nothing else carries **eighteen** streamer
infos and an 11708-byte `StreamerInfo` record. The cause is one null pointer:

```
TGraph  TNamed  TObject  TAttLine  TAttFill  TAttMarker
TH1F  TH1  TArrayF  TArray  TAxis  TAttAxis  TArrayD
TString  THashList  TList  TSeqCollection  TCollection
```

Everything from `TH1F` onwards is there because `fHistogram` is declared `TH1F*`
**and is null**. ROOT's own comment says so
(`root/io/io/src/TBufferFile.cxx:2456-2463`):

```cpp
//must write StreamerInfo if pointer is null
if (!strInfo && !start[j]) {
   ... ForceWriteInfo(info, kFALSE);
```

`ForceWriteInfo` then recurses over every non-transient element's class
(`root/io/io/src/TStreamerInfo.cxx:3507-3519`), which is where `TAxis`, `TAttAxis`,
`THashList` and the three `TArray` infos come from. A graph file therefore
describes `TH1F`, `TH1` and the whole axis chain **without containing a
histogram**, and describes `TArrayF`, `TArray` and `TArrayD`, which a file full of
histograms does not
([Element lists §10](ElementLists.md#10-three-classes-a-histogram-file-does-not-describe)).
It is the same rule as `TBranchRef` and `TRefTable` in a tree file
([Writing trees §8](WritingTrees.md#8-the-streamer-infos)), and far more expensive.

> **So a graph that has never been drawn carries streamer infos that a fitted one
> does not.** Measured on two files holding the same four points, written by the
> same ROOT in the same run:
>
> | | `TGraph` record | `StreamerInfo` record | `TArrayF`, `TArray`, `TArrayD` |
> |---|---|---|---|
> | never drawn, `fHistogram` null | 233 bytes | 11772 | **present** |
> | after `Fit("pol1")` | 2387 bytes | 16021 | **absent** |
>
> When the pointer is real the `TH1F` is streamed through its own path, which tags
> only the classes whose *generated* streamers run
> (`root/io/io/src/TBufferIO.cxx:349-366`) — and `TArrayF`'s is hand-written, so
> nothing tags it. The fitted file trades the three `TArray` infos for `TF1`,
> `TFormula` and `TF1Parameters`, and is 4 KB larger for it.

Two consequences for a writer:

1. **Write them all.** Leaving out the `TH1F` chain leaves the file readable by
   ROOT, which has those classes compiled in, and unreadable by anything driven by
   the file's own infos. [Element lists §9](ElementLists.md#9-a-graph-file-the-other-two)
   publishes `TGraph`'s and `TGraphErrors`'s; §4, §5 and §10 have the other
   seventeen.
2. **The order is not a property of the format.** It is the order the writing
   process happened to create its `TClass` objects in
   (`root/io/io/src/TFile.cxx:3509-3520`), and it is not even stable between two
   files from one ROOT: `TString` sits fourteenth in the plain file above and
   eighteenth in the fitted one. A reader must not depend on it.
   [Element lists §11](ElementLists.md#11-the-order-root-writes-them-in) records
   what `data/classes/graph.root` happens to have, because matching it is what
   makes the record comparison of §1 possible.

## 6. Invariants

1. `fNpoints >= 0`, and every counted array in the record — `fX`, `fY`, and `fEX`
   and `fEY` on a `TGraphErrors` — has a flag byte of **1** followed by exactly
   `fNpoints` doubles. A flag of 0 means the pointer was null and is legal, but
   only when `fNpoints` is 0; ROOT writes it in no other case.
2. `fMinimum` and `fMaximum` are both `-1111`, or `fMinimum <= fMaximum`.
3. A file containing a `TGraph` contains a streamer info for `TH1F` and for every
   class `TH1F`'s info names, whether or not `fHistogram` is null (§5).

Both halves of 1 are checked, by different things, and the division is worth
knowing because the obvious check is circular: a reader derives each array's extent
*from* `fNpoints`, so comparing the two can never fail. What
`tools/check_invariants.py` checks is the flag byte — a value other than 0 or 1, or
a 0 with points to write — and `fNpoints >= 0`. That there are exactly `fNpoints`
values is enforced one layer down, by the byte count: an array of the wrong length
makes the record's decoding end somewhere other than where its byte count says, and
that is [Streamer-driven reading §10](../02-serialization/StreamerDriven.md#10-invariants)
invariant 1. Invariant 2 is checked directly, and 3 is the general rule of
[Writing an object §9](WritingObjects.md#9-invariants), checked there.

**Two things a writer should reproduce and no file is required to.** `fFunctions`
is a pointer to an empty `TList` in every graph ROOT writes and a null is accepted
(§3.5); `fBits` is `0x400` with no `kMustCleanup` (§3.1). Neither is checked,
because a graph that differs reads and draws identically — they are ROOT's choices,
not the format's.

**What ROOT does not check.** Nothing in `TGraph`'s read path validates anything.
There is no diagnostic for a negative `fNpoints`, for `fMinimum` above `fMaximum`,
or for an `fHistogram` whose axis range does not contain the points; the byte
count is the only thing that has to add up, and it is checked by
`TBufferFile::CheckByteCount` like any other object's
([Writing an object §8](WritingObjects.md#8-what-root-checks-and-what-it-does-not)).

## 7. Class versions

| Class | Version | Cite |
|---|---|---|
| `TGraph` | 5 | `root/hist/hist/inc/TGraph.h:172` |
| `TGraphErrors` | 3 | `root/hist/hist/inc/TGraphErrors.h:78` |
| `TList` | 5 | `root/core/cont/inc/TList.h:80` |
| `TH1F` | 3 | `root/hist/hist/inc/TH1.h:672` |

The `TH1F` row is here because a graph file describes the class without containing
one (§5); [Writing histograms §11](WritingHistograms.md#11-class-versions) has the
rest of that chain.

## 8. Errata

| # | Claim | Actually |
|---|---|---|
| 1 | `root/hist/hist/src/TGraph.cxx:63-65`: "A TGraph has the default title and name `Graph`" | Only when a point count was given. `TGraph()` has no `TNamed` mem-initialiser (`root/hist/hist/src/TGraph.cxx:125`), so both are **empty** — and the key's name is taken from `GetName()` (`root/io/io/src/TDirectoryFile.cxx:1957-1960`), so a writer copying the documented behaviour names the key wrongly |
| 2 | `root/hist/hist/inc/TGraph.h:46`: `fNpoints` is the "Number of points <= fMaxSize" | True in memory and misleading on disk: `fMaxSize` is transient, so `fNpoints` is exactly the length of every array in the record, and a read assigns `fMaxSize = fNpoints` (§3.2) |
| 3 | `TGraph::SetMinimum`'s documentation does not mention `fHistogram` | It calls `GetHistogram()`, so setting a y range writes a whole `TH1F` into the record — 245 bytes becomes 1213 (§3.4) |
| 4 | — | Nothing anywhere says that a graph whose `fHistogram` is **null** writes *more* streamer infos than one whose `fHistogram` is real, or that a graph file is where the three `TArray` element lists are cheapest to obtain (§5) |
| 5 | — | Nothing says a `TGraph`'s line and marker attributes come from `gStyle`'s *general* accessors where a `TH1`'s come from its histogram ones, which is the one place a writer generalising from `TH1` gets five values wrong (§3.1) |
| 6 | `root/io/doc/TFile/` | Silent on `TGraph` altogether, and on the two encodings a graph record is mostly made of: the flag byte in front of a counted array and the four zero bytes of a null object pointer |

## 9. Reference files

| File | What it is |
|---|---|
| `data/classes/graph.root` | ROOT's own: a `TGraph`, a `TGraphErrors`, and a third graph whose `SetMinimum` built the histogram |
| `data/written/graph.root` | this project's: the first two byte-identical to ROOT's, plus a graph with a y range and **no** histogram, which ROOT's API cannot produce |
