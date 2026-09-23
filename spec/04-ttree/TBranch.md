# `TBranch`

A `TBranch` is the index of a tree's data. It holds no data itself: it holds the
three parallel arrays that locate the data, and a list of [leaves](TLeaf.md) that
describe what the data means.

Prerequisites: [Streamer-driven reading](../02-serialization/StreamerDriven.md),
[TTree](TTree.md), [TBasket](TBasket.md).

## 1. Where a branch lives

A branch is never a record of its own. Every branch is inside the
[`TTree` record](TTree.md),
as an entry of the tree's `fBranches` `TObjArray` or, since split branches nest,
of another branch's. `TBranch` is therefore read with the object-slot machinery of
[Buffer §6](../02-serialization/Buffer.md#6-object-slots): a byte count, a class
record or back-reference, then `byteCount version`.

Unlike [`TBasket`](TBasket.md), `TBranch` has an accurate streamer info in the
file, and the streamer-driven algorithm reads a branch correctly with no special
knowledge. `TBranch::Streamer` exists
(`root/tree/tree/src/TBranch.cxx:2968`) but above class version 9 it is a version
guard: it calls `ReadClassBuffer` and then only updates transient members
(`root/tree/tree/src/TBranch.cxx:2983-2984`).

This document is therefore about what the numbers mean rather than how to decode
them, and all of its traps are semantic.

## 2. Layout

Class version 13 (`root/tree/tree/inc/TBranch.h:304`). In streamer-info order:

| # | Member | Code | Type | Meaning |
|---|---|---|---|---|
| 1 | `TNamed` | 67 | base | `fName` is the branch name, `fTitle` the leaflist or the class name |
| 2 | `TAttFill` | 0 | base | drawing attributes; no I/O meaning |
| 3 | `fCompress` | 3 | `Int_t` | compression settings for **new** baskets |
| 4 | `fBasketSize` | 3 | `Int_t` | buffer size for **new** baskets |
| 5 | `fEntryOffsetLen` | 3 | `Int_t` | whether and how large an entry-offset array new baskets get (§6) |
| 6 | `fWriteBasket` | 3 | `Int_t` | number of baskets written; also the index one past the last (§4) |
| 7 | `fEntryNumber` | 16 | `Long64_t` | one past the last entry filled |
| 8 | `fIOFeatures` | 62 | `ROOT::TIOFeatures` | nested object, §8 |
| 9 | `fOffset` | 3 | `Int_t` | an **in-memory** offset, §7.1; 0 on a leaflist branch |
| 10 | `fMaxBaskets` | 6 | `Int_t` | the **array length on disk**, and nothing else (§3) |
| 11 | `fSplitLevel` | 3 | `Int_t` | how far the writer split the branch |
| 12 | `fEntries` | 16 | `Long64_t` | number of entries in this branch |
| 13 | `fFirstEntry` | 16 | `Long64_t` | entry number of this branch's first entry |
| 14 | `fTotBytes` | 16 | `Long64_t` | uncompressed size of all baskets, keys included |
| 15 | `fZipBytes` | 16 | `Long64_t` | on-disk size of all baskets |
| 16 | `fBranches` | 61 | `TObjArray` | sub-branches, empty unless split |
| 17 | `fLeaves` | 61 | `TObjArray` | the leaves, at least one |
| 18 | `fBaskets` | 61 | `TObjArray` | **all null** after `TTree::Write`; may hold an embedded basket (§5) |
| 19 | `fBasketBytes` | 43 | `Int_t*` | `[fMaxBaskets]`, counted pointer |
| 20 | `fBasketEntry` | 56 | `Long64_t*` | `[fMaxBaskets]`, counted pointer |
| 21 | `fBasketSeek` | 56 | `Long64_t*` | `[fMaxBaskets]`, counted pointer |
| 22 | `fFileName` | 65 | `TString` | empty unless the baskets are in another file (§9) |

Codes 43 and 56 are `kOffsetP + kInt` and `kOffsetP + kLong64`
([Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer)):
each is a one-byte *is present* flag followed by `fMaxBaskets` values. The count
comes from member 10, which is `kCounter`, so the reader must have retained it.
This is the worked example of
[Streamer-driven reading §3.2](../02-serialization/StreamerDriven.md#32-elements-are-not-independent).

Nothing else in `TBranch.h` reaches the file. Twenty-one of its members are
marked `//!`, including `fTree`, `fDirectory`, `fParent`, `fNleaves`,
`fReadBasket` and `fNBaskets` (`root/tree/tree/inc/TBranch.h:125-172`).

> **What a reader must reconstruct.** `TBranch::Streamer` rebuilds, after
> `ReadClassBuffer`: the back-pointer from each leaf to this branch, the
> back-pointer from each sub-branch to this one, `fNleaves` from `fLeaves`, and
> `fNBaskets` (`root/tree/tree/src/TBranch.cxx:2986-3009`). The owning tree is
> supplied later still, by `TTree::Streamer`
> (`root/tree/tree/src/TTree.cxx:9773-9792`). None of these is on disk; a reader
> that wants those relationships builds them the same way.

> **One member on disk must be corrected.** A `fSplitLevel` of 0 on a branch
> whose `fBranches` is not empty means 1, not 0
> (`root/tree/tree/src/TBranch.cxx:3018`). ROOT applies that at every version,
> not only the legacy ones.

## 3. `fMaxBaskets` is a write-time array length, not a capacity

`fMaxBaskets` on disk is **not** the value the writing `TBranch` held. Just
before `WriteClassBuffer`, `TBranch::Streamer` overwrites it, and restores it
afterwards (`root/tree/tree/src/TBranch.cxx:3190-3214`):

```
fMaxBaskets = fWriteBasket + 1;
if (fMaxBaskets < 10) fMaxBaskets = 10;
```

The value in the file is therefore `max(fWriteBasket + 1, 10)`, and the three
arrays have exactly that many elements. Elements at index `fWriteBasket + 1` and
above are zero padding: the arrays are allocated zeroed and never written above
`fWriteBasket` (`root/tree/tree/src/TBranch.cxx:311-319`,
`root/tree/tree/src/TBranch.cxx:826-839`).

Because of the floor of 10, a tree with one basket per branch still has thirty
array slots per branch. The value is not a hint about the number of baskets.
Below class version 9, ROOT wrote a flat 1000 instead (§13.2).

> Demonstrated by `ttree/branch`, whose single branch has `fWriteBasket` 3 and
> `fMaxBaskets` 10, with entries 4 to 9 of all three arrays zero. Also by
> `ttree/basket`, where `fWriteBasket` is 1 and `fMaxBaskets` is still 10.

## 4. The three arrays

For `0 <= i < fWriteBasket`, basket *i* of this branch is a record:

| Array | Value |
|---|---|
| `fBasketSeek[i]` | the absolute file offset of the basket's key, where a reader seeks to |
| `fBasketBytes[i]` | the basket record's `fNbytes`, key included |
| `fBasketEntry[i]` | the entry number of the basket's first entry |

`fBasketSeek[i]` is a byte offset into the file named by `fFileName`, or into the
file holding the tree when that is empty (§9). It addresses the *key*, so the
record found there must have class `TBasket`; ROOT checks that the basket's own
`fSeekKey` agrees (`root/tree/tree/src/TBranch.cxx:1268`).

### 4.1 `fBasketEntry` has one more meaningful element than there are baskets

`fBasketEntry[fWriteBasket]` is not a basket's first entry, because on a closed
file there is no basket `fWriteBasket`. It holds the branch's total entry count,
so that the array can be used as a half-open partition:

```
fBasketEntry = [0, 8, 16, 20, 0, 0, 0, 0, 0, 0]
                             ^ fWriteBasket = 3, and fEntries = 20
```

Basket *i* covers entries `[fBasketEntry[i], fBasketEntry[i+1])` for every
`i < fWriteBasket`, with the last basket ending at `fBasketEntry[fWriteBasket]`.

The binary search of §10 relies on this. A reader that stops the array at
`fWriteBasket - 1` cannot determine the length of the last basket.

> **ROOT patches it in when it is missing.** If a file has
> `fWriteBasket >= fMaxBaskets`, which older writers could produce, the reader
> grows the arrays and sets `fBasketEntry[fWriteBasket] = fEntries` itself
> (`root/tree/tree/src/TBranch.cxx:3010-3015`). A third-party reader SHOULD do the
> same rather than reject the file.

> **The terminator is absent when the last basket is embedded.**
> `fBasketEntry[fWriteBasket] = fEntryNumber` is written when a basket is closed
> out (`root/tree/tree/src/TBranch.cxx:3274`), so for a basket still in memory it
> has not been written. `fBasketEntry[fWriteBasket]` is then that basket's first
> entry, and the count is not in the array. §10 covers both cases by taking the
> last basket's end from `fEntryNumber` rather than from the array.
>
> Demonstrated by `ttree/basket-embedded`: `fWriteBasket` 0,
> `fBasketEntry[0]` 0, `fEntryNumber` 3. `uproot-issue431.root` shows the same
> shape with real baskets behind it: `fBasketEntry[fWriteBasket]` 4 against
> `fEntryNumber` 10. `PLAN.md` §9.8 had recorded that as an undiagnosed
> anomaly; this fixture explains it.

> Demonstrated by `ttree/branch`: three baskets of 8, 8 and 4 entries give
> `fBasketEntry` `[0, 8, 16, 20, 0…]` with `fEntries` and `fEntryNumber` both 20.

### 4.2 `fTotBytes` and `fZipBytes` count keys

`fZipBytes` is the sum of `fBasketBytes[0…fWriteBasket-1]`, and `fBasketBytes` is
a record's `fNbytes`, which includes the key. `fTotBytes` is the sum of
`fObjlen + fKeylen` over the same baskets
(`root/tree/tree/src/TBranch.cxx:3242`,
`root/tree/tree/src/TBranch.cxx:3251-3252`). Neither is a payload size, and on
an uncompressed branch the two are equal.

> Demonstrated by `ttree/branch`: baskets of 97, 97 and 81 bytes give
> `fTotBytes = fZipBytes = 275`.

## 5. `fBaskets` is written, and is usually empty

`fBaskets` is declared `//->` rather than `//!`, so the streamer info lists it and
it is on disk. It usually holds `fWriteBasket + 1` slots, and on any file written
by `TTree::Write` every one of them is **null**.

This follows from two pieces of code acting in sequence, not from the format.
`TTree::Write` flushes every basket before streaming anything
(`root/tree/tree/src/TTree.cxx:10012`). Then, just before `WriteClassBuffer`,
`TBranch::Streamer` sets to null every slot holding a basket that is already on
disk or is empty, and restores them afterwards
(`root/tree/tree/src/TBranch.cxx:3195-3213`):

```
if (ba && (fBasketBytes[i] || ba->GetNevBuf()==0)) { stash[i] = ba; fBaskets[i] = nullptr; }
```

A basket that is neither, one holding entries that were never flushed, **is
written inside the `TBranch` record** as a `TBasket` object rather than as a
record of its own. `TDirectory::WriteTObject` bypasses `TTree::Write`'s flush and
produces this. A reader must therefore handle both: null slots, which are four
zero bytes each ([Buffer §6](../02-serialization/Buffer.md#6-object-slots)), and
an embedded basket, which is the second form of
[TBasket §4](TBasket.md#4-the-flag-byte-and-the-two-shapes-of-a-basket).

An embedded basket is recognisable from the branch alone: it sits at index
`fWriteBasket`, and `fBasketSeek[fWriteBasket]` is 0 because it was never given a
file offset. Its layout is
[TBasket §4.1](TBasket.md#41-the-embedded-layout).

> Demonstrated by `ttree/basket-embedded`. Both its branches have `fWriteBasket`
> 0, `fBasketSeek` and `fBasketBytes` all zero, `fTotBytes` and `fZipBytes` 0, and
> one non-null slot in `fBaskets` holding the basket. The file contains no
> `TBasket` record.

> **Not a corner case.** The probes of `PLAN.md` §9.8 and §9.9 found embedded
> baskets in files written by ROOT 3.04/02 (`mlpHiggs.root`), 4.00/07
> (`stock.root`, eighty of them) and 5.34.

> This is distinct from [TBasket §10](TBasket.md#10-errata) erratum 8, where the
> shipped documentation claims that one basket per branch is *normally*
> embedded. That was true before ROOT 5.20/00 and has not been since.

Two further points about the array, both measured over the two corpora of
`PLAN.md` §9.8 and §9.9:

- **An embedded basket may be empty.** 92 branches in three files have an
  embedded basket at `fWriteBasket` whose first entry equals `fEntryNumber`, so
  it holds no entries: the branch was flushed and then written without another
  entry arriving. Its `fNevBuf` is 0 and invariant 6 still holds.
- **A slot above `fWriteBasket` may hold a basket, and must be ignored.**
  `alice_ESDs.root` (ROOT 5.34) writes two embedded baskets on each of its 19
  collection count branches while `fWriteBasket` is 0. ROOT reads index
  `fWriteBasket` down to 0 and never looks higher
  (`root/tree/tree/src/TBranch.cxx:3002-3009`), so the second one is unreachable
  by design, not corrupt. g4tools, Geant4's own ROOT writer, instead writes all
  `fMaxBaskets` slots, with the unused ones null. No ROOT-written file available
  does.

## 6. `fEntryOffsetLen`

`fEntryOffsetLen` is the length a *new* basket's entry-offset array is allocated
with. Zero means the branch's entries are all the same size and its baskets have
no offset array.

It is set to 1000 at branch construction as soon as any leaf has a leaf count or
is a `TLeafC` (`root/tree/tree/src/TBranch.cxx:421-427`), and is re-tuned from the
entry count each time a basket is written
(`root/tree/tree/src/TBranch.cxx:3225-3231`). **Its value says nothing about any
basket already on disk**; it describes the next one.

ROOT does, however, use it to decide whether to read an offset array out of a
basket (`root/tree/tree/src/TBasket.cxx:689-691`). For that reason
[TBasket §8](TBasket.md#8-reading) notes that ROOT cannot interpret a basket
record without its branch. The arithmetic test given there needs only the basket,
and gives the same answer.

> Demonstrated by `ttree/basket`: branch `n` is one `Int_t` per entry and has
> `fEntryOffsetLen` 0, while branch `a` is `a[n]/F` and has 12. The 1000 it was
> constructed with survives in its basket, whose `fNevBufSize` is 1000; the
> branch's own copy was retuned to `4 × fNevBuf` when that basket was closed.
> The two numbers describing the same array differ, and only the basket's
> describes bytes that exist. `ttree/leaf` has `fEntryOffsetLen` 10, the floor,
> for the same reason with two entries rather than three.

## 7. The entry counters

| Member | Meaning |
|---|---|
| `fEntries` | how many entries this branch holds |
| `fEntryNumber` | one past the last entry number filled |
| `fFirstEntry` | the entry number of this branch's entry 0 |

On an ordinary tree all three agree with
[the tree's own `fEntries`](TTree.md#3-fentries-is-a-counter-not-a-derived-quantity), with
`fFirstEntry` 0 and `fEntryNumber == fEntries`. They diverge for a branch added
to a tree that already had entries, and for a friend tree.

**A branch can start part way through the tree without the user asking for it.**
Apart from a user calling `TBranch::SetFirstEntry`, ROOT sets `fFirstEntry` in
one place only: `TBranchSTL::Fill` creates a sub-branch the first time it meets a
new object class in the collection, and gives it the entry number at which it was
created (`root/tree/tree/src/TBranchSTL.cxx:281-285`). Such a branch holds fewer
entries than the tree, and its entry 0 is not the tree's.

> A reader that maps basket entry *i* to tree entry *i* gets every entry of such
> a branch wrong. Nothing in the basket shows this; only `fFirstEntry` does.
>
> Demonstrated by `ttree/branch-first-entry`: the tree has 4 entries, the
> top-level `v` has `fEntries` 4 and `fFirstEntry` 0, and its sub-branch
> `v.FHit` has `fEntries` 2 and `fFirstEntry` 2, because the first two entries
> held an empty vector. §10 step 1 correctly rejects entries 0 and 1 for it.

The counters also diverge on the parent of a split branch, which is the common
case in real files. When a `TBranchElement` has sub-branches and is not a
collection counter (`fType` 3 or 4), its fill path is a bare `++fEntries`
(`root/tree/tree/src/TBranchElement.cxx:1320`). It never reaches
`TBranch::FillImpl`, which is what increments `fEntryNumber`
(`root/tree/tree/src/TBranch.cxx:890-891`). Such a parent therefore ends with
`fEntries` counted and **`fEntryNumber` still 0**, and `fEntries` is not
`fEntryNumber − fFirstEntry`.

This is consistent: the parent holds no data of its own, since all of it is in
the sub-branches, and §10 step 1 rejects every entry number for it. A reader must
not take such a branch's `fEntryNumber` for the tree's entry count.

> Found in files this project did not write: 227 branches across the foreign
> corpus of `PLAN.md` §9.8, including `Header.` in `uproot-issue404.root`
> (ROOT 6.18/04, thirteen sub-branches) and `Foo` in `uproot-issue-1043.root`.

The entry-lookup procedure of §10 uses `fFirstEntry` and `fEntryNumber` as the
bounds and `fBasketEntry` for the partition, so a reader should not substitute
the tree's count for any of them.

### 7.1 `fOffset` is an in-memory offset

`fOffset` is where this branch's datum sits **inside its containing C++ object**,
not anywhere in the file. It is 0 on every leaflist branch
(`root/tree/tree/src/TBranch.cxx:95`, `root/tree/tree/src/TBranch.cxx:208`,
`root/tree/tree/src/TBranch.cxx:262`), set from a member's offset when a branch is
built the old way (`root/tree/tree/src/TTree.cxx:2336`), and adjusted by
`TBranchElement::SetOffset` when a split branch is bound to an address
(`root/tree/tree/src/TBranchElement.cxx:5647-5665`). It can also hold the sentinel
`TVirtualStreamerInfo::kMissing`.

A reader that decodes basket payloads rather than filling C++ objects does not
need it, and MUST NOT confuse it with [`TLeaf::fOffset`](TLeaf.md#32-foffset-is-a-position-in-the-entry),
which is a position within an entry and a different quantity.

## 8. `fIOFeatures` is a version-0 class

`ROOT::TIOFeatures` has no `ClassDef` (`root/tree/tree/inc/ROOT/TIOFeatures.hxx:100`
declares its single member and nothing else). It is therefore written like every
class without an assigned version: a byte count, a **version word of 0**, a
four-byte checksum, then the member.

```
40 00 00 07   byte count 7
00 00         version 0
1a a1 2f 10   checksum 0x1aa12f10
00            fIOBits
```

This is the case [Buffer §4](../02-serialization/Buffer.md#4-a-version-word-of-0-has-two-different-meanings)
describes, and `TBranch` is where an ordinary file contains it: every branch of
every tree written since ROOT 6.12/02 has one
(`root/tree/tree/inc/TBranch.h:304` and the measurement in
[TTree §13](TTree.md#13-class-versions)). The checksum selects the streamer info,
which the file stores under the name `ROOT::TIOFeatures`.

`fIOBits` is the feature set new baskets are written with; bit 0 is
`kGenerateOffsetMap` ([TBasket §5.2](TBasket.md#52-with-kgenerateoffsetmap-the-array-holds-sizes)).
As with `fEntryOffsetLen`, it describes future baskets. A basket records its own
`fIOBits` in the sign of `fNevBufSize`.

## 9. `fFileName` — baskets in another file

When `fFileName` is non-empty, `fBasketSeek` addresses that file rather than the
one holding the tree (`root/tree/tree/src/TBranch.cxx:1852-1881`). The name is
resolved relative to the directory of the tree's own file
(`root/tree/tree/src/TBranch.cxx:2067`).

A reader that ignores `fFileName` reads whatever happens to lie at that offset in
the wrong file. No fixture in this corpus exercises it.

### 9.1 A branch may have no leaves

A split branch's interior nodes hold no data of their own; all of it is in their
sub-branches. Such a node has an **empty `fLeaves`**, `fWriteBasket` 0 and no
baskets, and exists only to give the sub-branches a parent and a name prefix.

ROOT provides for this explicitly: `TBranch::Streamer` selects
`TBranch::ReadLeaves0Impl` when `fNleaves` is 0
(`root/tree/tree/src/TBranch.cxx:3021-3022`), and that function's body is empty
(`root/tree/tree/src/TBranch.cxx:2471-2473`).

> Measured across the foreign corpus of `PLAN.md` §9.8: all 146 leafless
> branches have sub-branches, `fWriteBasket` 0 and no unresolved leaf references.
> `TObject` in `uproot-issue-1229.root` is the smallest: two sub-branches,
> `fUniqueID` and `fBits`, and nothing of its own.

Together with §7 this is the shape of a split interior node: `fEntries` counted,
`fEntryNumber` 0, `fLeaves` empty, `fBaskets` empty, and all the data one level
down.

## 10. Reading

To read entry *e* of a branch:

1. If `e < fFirstEntry` or `e >= fEntryNumber`, the branch has no such entry
   (`root/tree/tree/src/TBranch.cxx:1364-1366`).
2. Find the largest `i` in `[0, fWriteBasket]` with `fBasketEntry[i] <= e`. ROOT
   binary-searches `fWriteBasket + 1` elements
   (`root/tree/tree/src/TBranch.cxx:1371`); the array is non-decreasing over that
   range, so any equivalent search is conforming.
3. `first = fBasketEntry[i]`. The basket's last entry is `fBasketEntry[i+1] - 1`,
   except when `i == fWriteBasket`, where it is `fEntryNumber - 1`
   (`root/tree/tree/src/TBranch.cxx:1377-1383`).
4. If `fBasketSeek[i]` is non-zero, read the record there, of `fBasketBytes[i]`
   bytes, from the file named by `fFileName` or the tree's own, and decode it per
   [TBasket §8](TBasket.md#8-reading). If it is 0, basket *i* was never written to
   disk: it is the object in slot *i* of `fBaskets`, in the embedded form of
   [TBasket §4.1](TBasket.md#41-the-embedded-layout).
5. Entry *e* is the basket's entry `e - first`.
6. Hand the resulting byte range to the leaves, in `fLeaves` order, per
   [TLeaf §5](TLeaf.md#5-reading-one-entry).

Step 2 lands on `i == fWriteBasket` exactly when that basket is **embedded**. On a
branch whose baskets are all on disk, `fBasketEntry[fWriteBasket] == fEntryNumber`,
and step 1 has already excluded every entry that could reach it. When the last
basket is still in memory there is no terminator, and the remaining entries are
at index `fWriteBasket`.

## 11. Invariants

1. `fMaxBaskets >= max(fWriteBasket + 1, 10)`, and the three counted pointers each
   have `fMaxBaskets` elements with their *is present* flag set. Equality holds
   at class version 9 and above, but not below: at versions 7 and 8 ROOT wrote
   a flat 1000 however few baskets it filled (§13.2).
2. `0 <= fWriteBasket < fMaxBaskets`.
3. `fBasketEntry[0] == fFirstEntry` and `fBasketEntry` is non-decreasing over
   `[0, fWriteBasket]`. `fBasketEntry[fWriteBasket] == fEntryNumber` **when slot
   `fWriteBasket` of `fBaskets` is null**. When it holds an embedded basket, that
   element is the embedded basket's first entry instead and is at most
   `fEntryNumber`. It is equal when the embedded basket is empty, which happens
   when the branch was flushed and then written without another entry (92
   branches measured, §5). Invariant 6 fixes the difference exactly.
4. `fBasketBytes[i]`, `fBasketEntry[i]` and `fBasketSeek[i]` are 0 for every
   `i > fWriteBasket`.
5. For `i < fWriteBasket` with `fFileName` empty: `fBasketSeek[i]` is the offset
   of a record whose class name is `TBasket`, and that record's `fNbytes` equals
   `fBasketBytes[i]`. `fBasketSeek[i]` is 0 exactly when slot *i* of `fBaskets`
   holds an embedded basket.
6. For the same `i`, that basket's `fNevBuf` equals
   `fBasketEntry[i+1] - fBasketEntry[i]`, and for an embedded basket at index
   `fWriteBasket` it equals `fEntryNumber - fBasketEntry[fWriteBasket]`.
7. `fZipBytes` is the sum of `fBasketBytes[i]` over `i < fWriteBasket`, and
   `fTotBytes` the sum of `fObjlen + fKeylen` over the same baskets.
8. `fEntries == fEntryNumber - fFirstEntry`, **unless the branch has
   sub-branches**, where `fEntryNumber` may be 0 while `fEntries` counts (§7).
9. No slot of `fBaskets` holds a `TBasket` for which `fBasketSeek` is non-zero,
   and no slot above `fWriteBasket` holds anything a reader may use: ROOT walks
   indices `fWriteBasket` down to 0 and no further
   (`root/tree/tree/src/TBranch.cxx:3002-3009`). The slot count is not fixed
   by `fWriteBasket`. It is `fWriteBasket + 1` for 11 028 branches measured; one
   or more less when the trailing slots are null and the writer's `TObjArray`
   trimmed them; `fMaxBaskets` in the two g4tools files; and `fWriteBasket + 2`
   in one ROOT 5 file that left a second embedded basket above the write index
   (§5).
10. `fLeaves` is not empty, **unless the branch has sub-branches**, where it may
    hold nothing at all (§9.1).
11. `fEntryOffsetLen` is 0 or at least 10, and is 0 only if no leaf of this branch
    has a leaf count and none is a `TLeafC`.

Invariants 5 to 7 hold only for a branch whose baskets are in the same file.

Invariants 9 and 10 are not corruption-testable in isolation: the slot count of a
`TObjArray` is redundant with its byte count, so changing it breaks the framing
layer first and the file is rejected by
[Streamer-driven reading §10](../02-serialization/StreamerDriven.md#10-invariants).
Invariant 9 can still be tested from the other side, by making `fWriteBasket`
disagree with an intact slot count.

## 12. Errata

Against `root/io/doc/TFile/ttree.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | `ttree.md:45-64` gives the `TBranch` member list at class version 7 | Version **13**. `fEntryNumber`, `fEntries`, `fTotBytes` and `fZipBytes` are `Long64_t` rather than `Int_t`/`Stat_t`; `fBasketEntry` and `fBasketSeek` are code 56, not 43; and `fIOFeatures`, `fFirstEntry` and the `TAttFill` base are missing from it (§2) |
| 2 | — | Nothing says `fMaxBaskets` on disk is `max(fWriteBasket + 1, 10)` rather than the writer's value, so a reader that treats it as a basket count is wrong on every file (§3) |
| 3 | — | Nothing says `fBasketEntry[fWriteBasket]` is the total entry count rather than a basket's first entry. Without it the last basket's extent is unknown (§4.1) |
| 4 | — | Nothing says `fBaskets` is on disk, is normally all null but may hold an embedded basket, and must still be consumed (§5) |
| 5 | — | Nothing says `fEntryOffsetLen` describes the *next* basket, not the ones already written (§6) |
| 6 | `ttree.md` describes `fOffset` as "Offset of this branch" | It is an offset inside a C++ object, has no meaning in the file, and is 0 on every leaflist branch. `TLeaf` has an `fOffset` too, and that one *is* a file quantity (§7.1) |
| 7 | — | `fIOFeatures` is a class with no version, so it has a checksum where a version word would be; this is the first place an ordinary file uses that path (§8) |
| 8 | — | Nothing mentions `fFileName`, so a reader of a tree whose baskets are in another file silently reads garbage (§9) |
| 9 | `ttree.md:45-64`: `fCompress` is "(=1 branch is compressed, 0 otherwise)" | It is `100 × algorithm + level`, the same encoding as everywhere else (`root/tree/tree/inc/TBranch.h:308-323`), and −1 means "inherit from the file". It describes new baskets only; each basket's actual codec is in its own record header |
| 10 | *This document, until 2026-09-23*: `fMaxBaskets == max(fWriteBasket + 1, 10)` from class version 8, and a version-8 writer wrote all `fMaxBaskets` slots of `fBaskets` | ROOT wrote a flat 1000 at version 8, and `fWriteBasket + 1` slots. Both claims rested on two g4tools files, whose headers claim ROOT 4.00/00 (§13.2) |
| 11 | *This document, until 2026-09-23*: a ROOT 4.00-era writer left `fBaskets` at `fMaxBaskets` slots (§5, invariant 9) | g4tools does; no ROOT-written file available does |
| 10 | — | Nothing says a stored `fSplitLevel` of 0 means 1 when the branch has sub-branches (§2) |

The `TLeaf::fOffset` comment, "Offset in ClonesArray object (if one)"
(`root/tree/tree/inc/TLeaf.h:77`), is misleading in the same way from the other
side; see [TLeaf §3.2](TLeaf.md#32-foffset-is-a-position-in-the-entry).

## 13. Class versions

| Version | Difference |
|---|---|
| ≤ 5 | a different member order again — `fMaxBaskets` before `fWriteBasket`, `fOffset` last, `fBasketBytes` absent below 5, `fFileName` absent below 3 (`root/tree/tree/src/TBranch.cxx:3109-3176`) |
| 6 | the oldest version the `v > 5` legacy path reads (`root/tree/tree/src/TBranch.cxx:3035-3108`) |
| 7 | `fSplitLevel` added |
| 8 | the `TAttFill` base added |
| 9 | `fBasketSeek` widened from `Seek_t` to `Long64_t`, marked by a flag byte of **2** rather than 1 on that member (§13.3) |
| 10 | `fEntryNumber` `Int_t` → `Long64_t`; `fEntries`, `fTotBytes`, `fZipBytes` `Stat_t` (a `double`) → `Long64_t`; `fBasketEntry` `Int_t*` → `Long64_t*`. First version read by the streamer info |
| 11 | `fFirstEntry` added |
| 12 | two transient members dropped; no change on disk |
| 13 | `fIOFeatures` added; current |

Everything above 9 is read by `ReadClassBuffer` from the file's own streamer
info, so a reader that follows [Streamer-driven reading](../02-serialization/StreamerDriven.md)
needs no version knowledge for those, including the differences between 10, 11
and 13, which the streamer info states.

The threshold is 9 because version 10 is where the widths settled: below it, the
same member name has a different width, which schema evolution of that era could
not express. §13.1 gives the layout for 6 to 9.

### 13.1 The layout below version 10

`TBranch::Streamer` hand-codes the read for every version at or below 9
(`root/tree/tree/src/TBranch.cxx:3035-3108`). In order, with no framing of its
own beyond the branch's byte count and version word:

| Member | On disk | Present |
|---|---|---|
| `TNamed` base | a framed object: byte count, version word, `TObject`, `fName`, `fTitle` | always |
| `TAttFill` base | a framed object, 2 bytes of payload | **version 8 and above** |
| `fCompress` | `i32` | always |
| `fBasketSize` | `i32` | always |
| `fEntryOffsetLen` | `i32` | always |
| `fWriteBasket` | `i32` | always |
| `fEntryNumber` | **`i32`** — `Long64_t` from version 10 | always |
| `fOffset` | `i32` | always |
| `fMaxBaskets` | `i32`, the counter for the three arrays below | always |
| `fSplitLevel` | `i32` | **version 7 and above** |
| `fEntries` | **`f64`** — `Stat_t` is a `double`; `Long64_t` from version 10 | always |
| `fTotBytes` | **`f64`** | always |
| `fZipBytes` | **`f64`** | always |
| `fBranches` | a `TObjArray` | always |
| `fLeaves` | a `TObjArray` | always |
| `fBaskets` | a `TObjArray` | always |
| `fBasketBytes` | a flag byte, then **`fMaxBaskets`** `i32` | always |
| `fBasketEntry` | a flag byte, then **`fMaxBaskets`** `i32` — `i64` from version 10 | always |
| `fBasketSeek` | a flag byte, then `fMaxBaskets` values **4 or 8 bytes wide, chosen by the flag** (§13.3) | always |
| `fFileName` | a bare counted string | always |

Three entries in that table differ from what a modern reader expects, and each
one desynchronises the parse rather than producing a wrong value:

- **`fEntries`, `fTotBytes` and `fZipBytes` are doubles.** `Stat_t` was a
  `double` until version 10 made all three `Long64_t`. The width is the same;
  the interpretation is not.
- **`fEntryNumber` and every element of `fBasketEntry` are 4 bytes**, not 8.
- **The three arrays are always read in full**, `fMaxBaskets` values each. The
  flag byte in front of each is read and, for two of them, discarded: unlike the
  generated streamer's *is present* byte, a zero here does not mean the values
  are absent (`root/tree/tree/src/TBranch.cxx:3055-3066`). Every legacy branch
  measured writes 1 there.

The recorded streamer info agrees with this element for element on all 116
legacy branches in the two corpora: `mlpHiggs.root` at version 7,
`uproot-from-geant4.root` at 8 (written by g4tools, not ROOT) and `stock.root` at
9. That is a measurement, not
a rule. The two can disagree on one member (§13.3), at version 9, where a reader
is most likely to trust the info.

> `tools/rootfile.py` reads these versions from the order above rather than from
> the info, and checks that the parse ends on the branch's byte count. All 116
> do. No reference file covers this section, and none can, because the writers
> are ROOT 3.04 and 4.00/07 and g4tools. The evidence is the three corpus files
> named above, and nine files in `root/roottest/` that ROOT 3.05 to 3.10 wrote
> at version 8, and
> `tools/test_ttree.py` pins the version gates and the width selector against a
> synthetic buffer.

### 13.2 What the legacy writers did differently

Invariant §11.1 states a writer convention for current files that does not hold
for the older versions:

| Version | Convention | Measured |
|---|---|---|
| 7 and 8 | `fMaxBaskets` is a flat **1000**, whatever `fWriteBasket` is, so the three arrays are 1000 elements long and all but the first few are zero | version 7: `mlpHiggs.root`, 14 branches, `fWriteBasket` 0 and 12 003 bytes of arrays each. Version 8: 1 303 branches in nine `root/roottest/` files from ROOT 3.05/05 to 3.10/02 |
| 9 and above | `fMaxBaskets == max(fWriteBasket + 1, 10)` | every branch at version 9 to 13 in both corpora |

The write path has recomputed `fMaxBaskets` from the number of slots in
`fBaskets`, with a floor of 10, since root commit `aa25e85cb34` (2004-01-07),
during 4.00/00 development and after class version 9; at tag `v4-00-01` it is
`fMaxBaskets = fBaskets.GetEntriesFast(); if (fMaxBaskets < 10) fMaxBaskets=10;`
in `TBranch::Streamer`. Before that the in-memory capacity was written, and the
constructor sets it to 1000.

g4tools writes version 8 with the current conventions: `fMaxBaskets` of 10, and
all ten slots of `fBaskets` present with the unused ones null
(`uproot-from-geant4.root`, 22 branches with one basket each). A reader MUST NOT
use `fMaxBaskets` or the slot count to tell the writer's release.

### 13.3 At version 9 the streamer info is not authoritative

A `TBranch` at class version 9 has a streamer info declaring `fBasketSeek` as
`Long64_t*`, element code 56. **The values on disk may still be four bytes each.**
The *is present* flag byte of that member doubles as a width selector
(`root/tree/tree/src/TBranch.cxx:3062-3066`):

```
b >> isArray;
for (i = 0; i < fMaxBaskets; i++) {
   if (isArray == 2) b >> fBasketSeek[i];                       // 8 bytes
   else              { Int_t bsize; b >> bsize; ... }            // 4 bytes
}
```

A flag of 2 means 8-byte values and anything else means 4-byte ones, whatever
the info says. This is why the generic algorithm cannot be used below version 10,
and why `TBranch::Streamer` hand-codes the read: the recorded info describes the
class, whose member is `Long64_t*`, and not the width of the values in the file.

**No file measured has a flag of 2.** All 116 legacy branches in the two corpora
write 1, so every legacy `fBasketSeek` seen is four bytes wide. A flag of 2 needs
a version-9 file whose baskets lie past 2 GB, and no such file has been
published. The width selector is therefore specified from the source alone,
without a file to confirm it, and a reader that always assumes 4 bytes will
misread such a file.

> Measured on `stock.root` in the corpus of `PLAN.md` §9.9, ROOT 4.00/07: its ten
> trees all have `TBranch` v9 with `fBasketSeek`'s flag byte 1. Reading that
> member as the declared `Long64_t*` overruns every branch by `fMaxBaskets × 4`
> bytes; reading it as four-byte values makes all ten records end exactly at
> their byte count.

`tools/rootfile.py` takes the width from the flag byte for every version below
10, and §13.1 is the layout it reads.

## 14. Reference files

| Case | Exercises |
|---|---|
| `ttree/branch` | Three baskets in one branch: `fWriteBasket` 3 against `fMaxBaskets` 10, the `fBasketEntry` terminator, and `fTotBytes`/`fZipBytes` as sums over records |
| `ttree/basket` | Two branches, one with `fEntryOffsetLen` 0 and one with 12, constructed with 1000 and retuned at flush (§6), and a leaf count spanning them |
| `ttree/leaf` | One branch with thirteen leaves, for `fLeaves` order |
| `ttree/basket-embedded` | A branch whose only basket is still in memory: `fWriteBasket` 0, the arrays and `fTotBytes`/`fZipBytes` all zero, a non-null `fBaskets` slot, and no terminator in `fBasketEntry` |
| `ttree/branch-first-entry` | A sub-branch created part way through the tree: `fFirstEntry` 2 against the tree's 4 entries (§7), and `fSplitLevel` decrementing across a `TBranchSTL` |

A split branch (`fBranches` non-empty) is covered by every `ttree/split-*` case,
and a non-zero `fIOBits` by `ttree/basket-iofeatures`.

No fixture covers a non-empty `fFileName`, which needs a second file
(`PLAN.md` §9.4), or a `TBranch` at class version 9 or below. The foreign corpus
of `PLAN.md` §9.8 has files for the latter. `tools/rootfile.py` reads them by the
member order of §13.1 in `read_legacy_branch`, which is dispatched for every
`TBranch` below class version 10. The legacy layout is therefore implemented and
exercised by the corpus, but not pinned by a fixture of this project's own.
