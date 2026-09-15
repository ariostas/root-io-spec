# `TBranch`

The index of a tree. A `TBranch` holds no data: it holds the three parallel
arrays that say where the data is, and a list of [leaves](TLeaf.md) that say what
the data means.

Prerequisites: [Streamer-driven reading](../02-serialization/StreamerDriven.md),
[TBasket](TBasket.md).

## 1. Where a branch lives

A branch is never a record of its own. Every branch is inside the `TTree` record,
as an entry of the tree's `fBranches` `TObjArray`, or of another branch's — a
split branch nests. `TBranch` is therefore read with the object-slot machinery of
[Buffer §6](../02-serialization/Buffer.md#6-object-slots): a byte count, a class
record or back-reference, then `byteCount version`.

Unlike [`TBasket`](TBasket.md), `TBranch` has a streamer info in the file, it is
accurate, and **the streamer-driven algorithm reads a branch correctly with no
special knowledge at all**. `TBranch::Streamer` exists
(`root/tree/tree/src/TBranch.cxx:2968`) but above class version 9 it is a version
guard: it calls `ReadClassBuffer` and then does bookkeeping that touches only
transient members (`root/tree/tree/src/TBranch.cxx:2983-2984`).

This document is therefore not about *how* to get the bytes out. It is about what
the numbers mean, and every one of the traps is a semantic one.

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
| 18 | `fBaskets` | 61 | `TObjArray` | **always all null on a closed file** (§5) |
| 19 | `fBasketBytes` | 43 | `Int_t*` | `[fMaxBaskets]`, counted pointer |
| 20 | `fBasketEntry` | 56 | `Long64_t*` | `[fMaxBaskets]`, counted pointer |
| 21 | `fBasketSeek` | 56 | `Long64_t*` | `[fMaxBaskets]`, counted pointer |
| 22 | `fFileName` | 65 | `TString` | empty unless the baskets are in another file (§9) |

Codes 43 and 56 are `kOffsetP + kInt` and `kOffsetP + kLong64`
([Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer)):
each is a one-byte *is present* flag followed by `fMaxBaskets` values. The count
comes from member 10, which is `kCounter`, and which the reader must therefore
have retained — this is the worked example of
[Streamer-driven reading §3.2](../02-serialization/StreamerDriven.md#32-elements-are-not-independent).

Nothing else in `TBranch.h` reaches the file. Twenty-one of its members are
marked `//!`, including `fTree`, `fDirectory`, `fParent`, `fNleaves`,
`fReadBasket` and `fNBaskets` (`root/tree/tree/inc/TBranch.h:125-172`).

> **What a reader must reconstruct.** `TBranch::Streamer` rebuilds, after
> `ReadClassBuffer`: the back-pointer from each leaf to this branch, the
> back-pointer from each sub-branch to this one, `fNleaves` from `fLeaves`, and
> `fNBaskets` (`root/tree/tree/src/TBranch.cxx:2986-3009`). The owning tree is
> supplied later still, by `TTree::Streamer`
> (`root/tree/tree/src/TTree.cxx:9774-9793`). A reader that wants those
> relationships builds them the same way; none of them is on disk.

> **And one member that is on disk but must be corrected.** A `fSplitLevel` of 0
> on a branch whose `fBranches` is not empty means 1, not 0
> (`root/tree/tree/src/TBranch.cxx:3018`). ROOT applies that at every version,
> not only the legacy ones.

## 3. `fMaxBaskets` is a write-time array length, not a capacity

`fMaxBaskets` on disk is **not** the value the writing `TBranch` held. Immediately
before `WriteClassBuffer`, `TBranch::Streamer` overwrites it and restores it after
(`root/tree/tree/src/TBranch.cxx:3190-3214`):

```
fMaxBaskets = fWriteBasket + 1;
if (fMaxBaskets < 10) fMaxBaskets = 10;
```

So the value in the file is `max(fWriteBasket + 1, 10)`, and the three arrays have
exactly that many elements. Elements at index `fWriteBasket + 1` and above are
zero padding — the arrays are allocated zeroed and never written above
`fWriteBasket` (`root/tree/tree/src/TBranch.cxx:311-319`,
`root/tree/tree/src/TBranch.cxx:826-839`).

The floor of 10 is why a tree with one basket per branch still carries thirty
array slots per branch. It is not a hint about the number of baskets.

> Demonstrated by `ttree/branch`, whose single branch has `fWriteBasket` 3 and
> `fMaxBaskets` 10, with entries 4 to 9 of all three arrays zero. And by
> `ttree/basket`, where `fWriteBasket` is 1 and `fMaxBaskets` is 10 all the same.

## 4. The three arrays

For `0 <= i < fWriteBasket`, basket *i* of this branch is a record:

| Array | Value |
|---|---|
| `fBasketSeek[i]` | the absolute file offset of the basket's key — what a reader seeks to |
| `fBasketBytes[i]` | the basket record's `fNbytes`, key included |
| `fBasketEntry[i]` | the entry number of the basket's first entry |

`fBasketSeek[i]` is a byte offset into the file named by `fFileName`, or into the
file holding the tree when that is empty (§9). It addresses the *key*, so the
value read there must be a record whose class is `TBasket`; ROOT checks that the
basket's own `fSeekKey` agrees (`root/tree/tree/src/TBranch.cxx:1268`).

### 4.1 `fBasketEntry` has one more meaningful element than there are baskets

`fBasketEntry[fWriteBasket]` is not a basket's first entry — there is no basket
`fWriteBasket` on a closed file. It holds the branch's total entry count, so that
the array can be used as a half-open partition:

```
fBasketEntry = [0, 8, 16, 20, 0, 0, 0, 0, 0, 0]
                             ^ fWriteBasket = 3, and fEntries = 20
```

Basket *i* covers entries `[fBasketEntry[i], fBasketEntry[i+1])` for every
`i < fWriteBasket`, with the last basket ending at `fBasketEntry[fWriteBasket]`.

This is what makes the binary search of §10 work, and a reader that stops the
array at `fWriteBasket - 1` cannot determine the length of the last basket.

> **ROOT patches it in when it is missing.** If a file has
> `fWriteBasket >= fMaxBaskets` — which older writers could produce — the reader
> grows the arrays and sets `fBasketEntry[fWriteBasket] = fEntries` itself
> (`root/tree/tree/src/TBranch.cxx:3010-3015`). A third-party reader SHOULD do the
> same rather than reject the file.

> **The terminator is absent when the last basket is embedded.**
> `fBasketEntry[fWriteBasket] = fEntryNumber` is written when a basket is closed
> out (`root/tree/tree/src/TBranch.cxx:3274`), so a basket still in memory has not
> had it written: `fBasketEntry[fWriteBasket]` is then that basket's **first**
> entry, and the count is nowhere in the array. §10 covers both cases by taking
> the last basket's end from `fEntryNumber` rather than from the array.
>
> Demonstrated by `ttree/basket-embedded`: `fWriteBasket` 0,
> `fBasketEntry[0]` 0, `fEntryNumber` 3. `uproot-issue431.root` shows the same
> shape with real baskets behind it — `fBasketEntry[fWriteBasket]` 4 against
> `fEntryNumber` 10 — which `PLAN.md` §9.8 had recorded as an undiagnosed
> anomaly until this fixture explained it.

> Demonstrated by `ttree/branch`: three baskets of 8, 8 and 4 entries give
> `fBasketEntry` `[0, 8, 16, 20, 0…]` with `fEntries` and `fEntryNumber` both 20.

### 4.2 `fTotBytes` and `fZipBytes` count keys

`fZipBytes` is the sum of `fBasketBytes[0…fWriteBasket-1]`, and `fBasketBytes` is
a record's `fNbytes`, which includes the key. `fTotBytes` is the sum of
`fObjlen + fKeylen` over the same baskets
(`root/tree/tree/src/TBranch.cxx:3242`, `root/tree/tree/src/TBranch.cxx:3251-3252`). Neither is a payload size, and on
an uncompressed branch the two are equal.

> Demonstrated by `ttree/branch`: baskets of 97, 97 and 81 bytes give
> `fTotBytes = fZipBytes = 275`.

## 5. `fBaskets` is written, and is usually empty

`fBaskets` is declared `//->` rather than `//!`, so the streamer info lists it and
it is on disk. It holds `fWriteBasket + 1` slots, and on any file written by
`TTree::Write` every one of them is **null**.

That is not a property of the format but of two pieces of code acting in
sequence. `TTree::Write` flushes every basket before streaming anything
(`root/tree/tree/src/TTree.cxx:10012`), and then, immediately before
`WriteClassBuffer`, `TBranch::Streamer` replaces with null every slot holding a
basket that **is already on disk or is empty**, restoring them afterwards
(`root/tree/tree/src/TBranch.cxx:3195-3213`):

```
if (ba && (fBasketBytes[i] || ba->GetNevBuf()==0)) { stash[i] = ba; fBaskets[i] = nullptr; }
```

A basket that is neither — one holding entries that were never flushed — **is
written inside the `TBranch` record**, as a `TBasket` object rather than a record
of its own. `TDirectory::WriteTObject` bypasses `TTree::Write`'s flush and
produces exactly that. So a reader must handle both: null slots, which are four
zero bytes each ([Buffer §6](../02-serialization/Buffer.md#6-object-slots)), and
an embedded basket, which is the second form of
[TBasket §4](TBasket.md#4-the-flag-byte-and-the-two-shapes-of-a-basket).

An embedded basket is recognisable from the branch alone: it sits at index
`fWriteBasket`, and `fBasketSeek[fWriteBasket]` is 0 because it was never given a
file offset. Its layout is
[TBasket §4.1](TBasket.md#41-the-embedded-layout).

> Demonstrated by `ttree/basket-embedded`. Both its branches have `fWriteBasket`
> 0, `fBasketSeek` and `fBasketBytes` all zero, `fTotBytes` and `fZipBytes` 0, and
> one non-null slot in `fBaskets` holding the whole basket. The file contains no
> `TBasket` record at all.

> **Not a corner case.** The probe of `PLAN.md` §9.8 found embedded baskets in
> files written by ROOT 4.00 and 5.34, one of them with eighty in a single tree.
> A reader that cannot read one fails on real files.

> Not to be confused with [TBasket §10](TBasket.md#10-errata) erratum 8, which is
> about the shipped documentation claiming that one basket per branch is
> *normally* embedded. It was, before ROOT 5.20/00; it has not been since.

## 6. `fEntryOffsetLen`

`fEntryOffsetLen` is the length a *new* basket's entry-offset array is allocated
with. Zero means the branch's entries are all the same size and its baskets carry
no offset array.

It is set to 1000 at branch construction as soon as any leaf has a leaf count or
is a `TLeafC` (`root/tree/tree/src/TBranch.cxx:421-427`), and is re-tuned from the
entry count each time a basket is written
(`root/tree/tree/src/TBranch.cxx:3225-3231`). **Its value carries no information
about any basket already on disk** — it describes the next one.

It is, however, how ROOT itself decides whether to read an offset array out of a
basket (`root/tree/tree/src/TBasket.cxx:689-691`), which is why
[TBasket §8](TBasket.md#8-reading) notes that ROOT cannot interpret a basket
record without its branch. The arithmetic test given there needs only the basket,
and agrees.

> Demonstrated by `ttree/basket`: branch `n` is one `Int_t` per entry and has
> `fEntryOffsetLen` 0, while branch `a` is `a[n]/F` and has **12**. The 1000 it
> was constructed with survives in its basket, whose `fNevBufSize` is 1000; the
> branch's own copy was retuned to `4 × fNevBuf` when that basket was closed.
> The two numbers describing the same array differ, and only the basket's is
> about bytes that exist. `ttree/leaf` has `fEntryOffsetLen` 10, the floor, for
> the same reason with two entries rather than three.

## 7. The entry counters

| Member | Meaning |
|---|---|
| `fEntries` | how many entries this branch holds |
| `fEntryNumber` | one past the last entry number filled |
| `fFirstEntry` | the entry number of this branch's entry 0 |

On an ordinary tree all three agree with the tree's own `fEntries`, with
`fFirstEntry` 0 and `fEntryNumber == fEntries`. They diverge for a branch added
to a tree that already had entries, and for a friend tree. The entry-lookup
procedure of §10 uses `fFirstEntry` and `fEntryNumber` as the bounds and
`fBasketEntry` for the partition, so a reader should not substitute the tree's
count for any of them.

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
which is a position within an entry and is a different quantity entirely.

## 8. `fIOFeatures` is a version-0 class

`ROOT::TIOFeatures` has no `ClassDef` (`root/tree/tree/inc/ROOT/TIOFeatures.hxx:100`
declares its single member and nothing else), so it is written the way every
class without an assigned version is: a byte count, a **version word of 0**, then
a four-byte checksum, then the member.

```
40 00 00 07   byte count 7
00 00         version 0
1a a1 2f 10   checksum 0x1aa12f10
00            fIOBits
```

This is the case [Buffer §4](../02-serialization/Buffer.md#4-a-version-word-of-0-has-two-different-meanings)
describes, and `TBranch` is where an ordinary file meets it: every branch of every
tree written since ROOT 6.14 contains one. The checksum selects the streamer info,
which the file carries under the name `ROOT::TIOFeatures`.

`fIOBits` is the feature set new baskets are written with; bit 0 is
`kGenerateOffsetMap` ([TBasket §5.2](TBasket.md#52-with-kgenerateoffsetmap-the-array-holds-sizes)).
As with `fEntryOffsetLen`, it describes future baskets — a basket records its own
`fIOBits` in the sign of `fNevBufSize`.

## 9. `fFileName` — baskets in another file

When `fFileName` is non-empty, `fBasketSeek` addresses that file rather than the
one holding the tree (`root/tree/tree/src/TBranch.cxx:1852-1881`). The name is
resolved relative to the tree's own file's directory
(`root/tree/tree/src/TBranch.cxx:2067`).

A reader that ignores `fFileName` reads whatever happens to lie at that offset in
the wrong file. No fixture in this corpus exercises it.

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
branch whose baskets are all on disk, `fBasketEntry[fWriteBasket] == fEntryNumber`
and step 1 has already excluded every entry that could reach it; when the last
basket is still in memory there is no terminator, and index `fWriteBasket` is where
the remaining entries live.

## 11. Invariants

1. `fMaxBaskets == max(fWriteBasket + 1, 10)`, and the three counted pointers each
   have `fMaxBaskets` elements with their *is present* flag set.
2. `0 <= fWriteBasket < fMaxBaskets`.
3. `fBasketEntry[0] == fFirstEntry` and `fBasketEntry` is non-decreasing over
   `[0, fWriteBasket]`. `fBasketEntry[fWriteBasket] == fEntryNumber` **when slot
   `fWriteBasket` of `fBaskets` is null**; when it holds an embedded basket, that
   element is the embedded basket's first entry instead and is below
   `fEntryNumber`.
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
8. `fEntries == fEntryNumber - fFirstEntry`.
9. `fBaskets` holds `fWriteBasket + 1` slots, and none of them holds a `TBasket`
   for which `fBasketSeek` is non-zero.
10. `fLeaves` is not empty.
11. `fEntryOffsetLen` is 0 or at least 10, and is 0 only if no leaf of this branch
    has a leaf count and none is a `TLeafC`.

Invariants 5 to 7 hold only for a branch whose baskets are in the same file.

Invariants 9 and 10 are not corruption-testable in isolation: the slot count of a
`TObjArray` is redundant with its byte count, so changing it breaks the framing
layer first and the file is rejected by
[Streamer-driven reading §10](../02-serialization/StreamerDriven.md#10-invariants).
Invariant 9 is still reachable from the other side, by making `fWriteBasket`
disagree with a slot count that is intact.

## 12. Errata

Against `root/io/doc/TFile/ttree.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | `ttree.md:45-64` gives the `TBranch` member list at class version 7 | Version **13**. `fEntryNumber`, `fEntries`, `fTotBytes` and `fZipBytes` are `Long64_t` rather than `Int_t`/`Stat_t`; `fBasketEntry` and `fBasketSeek` are code 56, not 43; and `fIOFeatures`, `fFirstEntry` and the `TAttFill` base are missing from it entirely (§2) |
| 2 | — | Nothing says `fMaxBaskets` on disk is `max(fWriteBasket + 1, 10)` rather than the writer's value, so a reader that treats it as a basket count is wrong on every file (§3) |
| 3 | — | Nothing says `fBasketEntry[fWriteBasket]` is the total entry count rather than a basket's first entry. Without it the last basket's extent is unknown (§4.1) |
| 4 | — | Nothing says `fBaskets` is on disk, is always all-null, and must still be consumed (§5) |
| 5 | — | Nothing says `fEntryOffsetLen` describes the *next* basket, not the ones already written (§6) |
| 6 | `ttree.md` describes `fOffset` as "Offset of this branch" | It is an offset inside a C++ object, has no meaning in the file, and is 0 on every leaflist branch. `TLeaf` has an `fOffset` too, and that one *is* a file quantity (§7.1) |
| 7 | — | `fIOFeatures` is a class with no version, so it carries a checksum where a version word would be — the first place an ordinary file exercises that path (§8) |
| 8 | — | Nothing mentions `fFileName`, so a reader of a tree whose baskets are in another file silently reads garbage (§9) |
| 9 | `ttree.md:45-64`: `fCompress` is "(=1 branch is compressed, 0 otherwise)" | It is `100 × algorithm + level`, the same encoding as everywhere else (`root/tree/tree/inc/TBranch.h:308-323`), and −1 means "inherit from the file". It describes new baskets only; each basket's actual codec is in its own record header |
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
| 9 | `fBasketSeek` widened from `Seek_t` to `Long64_t`, marked by a flag byte of **2** rather than 1 on that member |
| 10 | `fEntryNumber` `Int_t` → `Long64_t`; `fEntries`, `fTotBytes`, `fZipBytes` `Stat_t` (a `double`) → `Long64_t`; `fBasketEntry` `Int_t*` → `Long64_t*`. First version read by the streamer info |
| 11 | `fFirstEntry` added |
| 12 | two transient members dropped; no change on disk |
| 13 | `fIOFeatures` added; current |

Everything above 9 is read by `ReadClassBuffer` from the file's own streamer
info, so a reader that follows [Streamer-driven reading](../02-serialization/StreamerDriven.md)
needs no version knowledge for those — including the difference between 10, 11
and 13, which the file's own streamer info states. A version at or below 9 needs
the legacy layouts, which this document does not give; see `PLAN.md` §9.1.

The threshold is 9 and not some other number because version 10 is where the
widths settled: below it the same member name has a different width, which is
the one thing schema evolution of that era could not express.

## 14. Reference files

| Case | Exercises |
|---|---|
| `ttree/branch` | Three baskets in one branch: `fWriteBasket` 3 against `fMaxBaskets` 10, the `fBasketEntry` terminator, and `fTotBytes`/`fZipBytes` as sums over records |
| `ttree/basket` | Two branches, one with `fEntryOffsetLen` 0 and one with 1000, and a leaf count spanning them |
| `ttree/leaf` | One branch with thirteen leaves, for `fLeaves` order |
| `ttree/basket-embedded` | A branch whose only basket is still in memory: `fWriteBasket` 0, the arrays and `fTotBytes`/`fZipBytes` all zero, a non-null `fBaskets` slot, and no terminator in `fBasketEntry` |

No fixture covers a split branch (`fBranches` non-empty), a non-empty
`fFileName`, a non-zero `fIOBits`, a branch whose `fFirstEntry` is not 0, or a
`TBranch` at class version 9 or below. The foreign corpus of `PLAN.md` §9.8 has
files for the last of those, and `tools/rootfile.py` refuses them explicitly
rather than guessing at the legacy layout.
