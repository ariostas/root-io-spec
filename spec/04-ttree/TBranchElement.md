# `TBranchElement`

The branch class a split tree is made of. A `TBranchElement` is a
[`TBranch`](TBranch.md) with eleven extra members that record which part of which
class the branch holds. Those eleven members, not the rest of the branch record,
are what a reader has to understand.

Prerequisites: [TBranch](TBranch.md), [TLeaf](TLeaf.md),
[Streamer information](../02-serialization/StreamerInfo.md),
[Element types](../02-serialization/ElementTypes.md).

In the two corpora of `PLAN.md` §9.8 and §9.9 (178 files written by ROOT
releases from 2.24/00 to 6.36), 6736 of 11157 branches are not a plain `TBranch`,
spread over 56 files: 6734 are `TBranchElement` and 2 are `TBranchObject`. A
reader that handles only `TBranch` can walk a physics file and find the right
basket for an entry, but cannot interpret any of its bytes.

## 1. The record needs no special reading

`TBranchElement::Streamer` exists, but its read path is a single
`ReadClassBuffer` call (`root/tree/tree/src/TBranchElement.cxx:6027-6028`)
followed by fixups that touch only transient members. Every file that uses the
class has an accurate streamer info for it, so
[the streamer-driven algorithm](../02-serialization/StreamerDriven.md) reads the
record correctly with no special knowledge, as for
[`TBranch`](TBranch.md#1-where-a-branch-lives).

This creates a trap in the other direction: a coverage measurement based on
decoding records will report a split file as fully covered while the reader
cannot produce a single value from it. The difficulty is entirely in the meaning
of the fields.

One fixup does affect the file format. When `fType` is 0 and `fLeaves` is empty,
ROOT synthesises a `TLeafElement` on read
(`root/tree/tree/src/TBranchElement.cxx:6037-6044`). No file in either corpus
needs this, so a reader may treat an empty `fLeaves` on an `fType` 0 branch as a
file it should reject, although upstream this is defensive code, not an error.

## 2. Layout

The eleven members follow the `TBranch` base in declaration order
(`root/tree/tree/inc/TBranchElement.h:60-84`). The class version is 10
(`root/tree/tree/inc/TBranchElement.h:255`).

| # | Member | `fType` | C++ | Meaning |
|---|---|---|---|---|
| 0 | `TBranch` | 0 | base | everything in [TBranch §2](TBranch.md#2-layout) |
| 1 | `fClassName` | 65 | `TString` | the class whose element list `fID` indexes (§5) |
| 2 | `fParentName` | 65 | `TString` | the class this branch was split out of |
| 3 | `fClonesName` | 65 | `TString` | the value type, on `fType` 3 and 4 only |
| 4 | `fCheckSum` | 13 | `UInt_t` | checksum of `fClassName`'s class |
| 5 | `fClassVersion` | 2 | `Version_t` | on-file version of `fClassName`'s class |
| 6 | `fID` | 3 | `Int_t` | element index, or a sentinel (§3) |
| 7 | `fType` | 3 | `Int_t` | which kind of node this is (§3) |
| 8 | `fStreamerType` | 3 | `Int_t` | the element type code, but not the one the file's streamer info records; see §5.2 |
| 9 | `fMaximum` | 3 | `Int_t` | upper bound on the collection count (§7) |
| 10 | `fBranchCount` | 64 | `TBranchElement*` | back-reference to the count branch (§6) |
| 11 | `fBranchCount2` | 64 | `TBranchElement*` | the second dimension; never set (§6) |

`fClassVersion` is a two-byte `Version_t` from class version 10 onward and a
four-byte `Int_t` below it (§12). It is always non-negative on disk: the writer
stores its absolute value (`root/tree/tree/src/TBranchElement.cxx:6053-6057`).

Members declared `//!` are transient and are not on disk: `fCollProxy`,
`fSTLtype`, `fNdata`, `fInfo`, `fObject`, `fOnfileObject`, the `TClassRef`s,
`fBranchOffset`, `fBranchID`, the action sequences and the iterators.

## 3. `fType` and `fID`

`fType` gives the kind of node the branch is. Eight values occur:

| `fType` | Meaning | Count in the corpora |
|---|---|---|
| −1 | unsplit object whose class had a custom streamer when written | 16 |
| 0 | three different things; `fID` disambiguates (§3.2) | 4220 |
| 1 | a base class of a split object | 141 |
| 2 | a class-typed data member of a split object | 16 |
| 3 | the count branch of a split `TClonesArray` | 21 |
| 4 | the count branch of a split STL collection | 84 |
| 31 | a data member of a split `TClonesArray`'s content | 733 |
| 41 | a data member of a split STL collection's content | 1503 |

The header lists these (`root/tree/tree/inc/TBranchElement.h:67-78`) and the
dispatch of §8 rejects anything else with a `Fatal`.

### 3.1 `fID` has two sentinels, and the header documents only one

| `fID` | Meaning |
|---|---|
| −2 | a **split node**: the branch has sub-branches and no data of its own |
| −1 | an **unsplit object**: the whole object is in this branch's baskets |
| ≥ 0 | an index into the element list of `fClassName`'s streamer info |

ROOT tests for −2 directly in several places
(`root/tree/tree/src/TBranchElement.cxx:2279`,
`root/tree/tree/src/TBranchElement.cxx:3812`), but the header's note on `fType`
mentions only −1 (§11 erratum 1). Both occur: across the corpora, `fID` is −1 on
250 branches and −2 on 176.

### 3.2 `fType` 0 is three different branches

`fType` 0 is the most common value and the least informative. `fID` separates
the cases:

| | Count | Data lives |
|---|---|---|
| `fType` 0, `fID` −1 | 216 | in this branch's baskets, as one whole object |
| `fType` 0, `fID` −2 | 170 | in the sub-branches; this node has none |
| `fType` 0, `fID` ≥ 0 | 3834 | in this branch's baskets, as one member's values |

A reader that treats `fType` 0 as a single case will try to read a whole object
out of a branch that holds one `Int_t` column, or out of a node that holds
nothing at all.

## 4. Two `fType` values have no leaf, and two reach theirs only by reference

Over all 6736 branches in the corpora, with no exceptions:

| `fType` | Leaves | Baskets |
|---|---|---|
| −1, 0, 31, 41 | exactly 1, written in place | yes |
| 1, 2 | **none** | **never** — 141/141 and 16/16 have `fWriteBasket` 0 |
| 3, 4 | exactly 1, **always a back-reference** | yes — 16/21 and 69/84 have baskets |

`fType` 1 and 2 are pure interior nodes: no leaf, no basket, no data. A reader
descends through them to their children.
[`TBranch` §9.1](TBranch.md#91-a-branch-may-have-no-leaves) already describes
this shape from the `TBranch` side.

**One exception, before 5.34/20 and 6.02/00: an empty base class.** `TTree::Bronch`
then gave every base class of a top-level split object its own sub-branch, empty
or not (`v4-04-02:tree/src/TTree.cxx:1480-1495`). A base class with no data
members becomes an `fType` 1 branch with no leaf and no sub-branches that still
has a basket, and each entry is element `fID` of the parent's info written as a
base: one framed object of the base class
(`v4-04-02:tree/src/TBranchElement.cxx:1092`). ROOT reads it with
`ReadLeavesMember`, as the `fType <= 2` rows of §8 select whatever `fNleaves` is
(`root/tree/tree/src/TBranchElement.cxx:5805-5812`). Root commit `6698d9213bb`
(first tag `v6-02-00`) and its backport `df455e9c8d5` (`v5-34-20`) stopped making
these branches (`root/tree/tree/src/TBranchElement.cxx:6187-6190`). Neither
corpus has one; `cmsursula.root` and `mcpool.root` in `root/roottest/` (4.04/02)
have 16 between them, all named `<top>.edm::EDProduct`.
[`TBranch` §9.2](TBranch.md#92-a-leafless-branch-may-still-hold-data) describes the entries. On those 16, `fWriteBasket`
and `fTotBytes` are 0 only because nothing was flushed: the basket is embedded
in the `TTree` record. So an `fType` 1 branch with no children is not
necessarily empty. The test is whether it has baskets holding entries.

The count branches need care. On all 105 `fType` 3 and 4 branches in the
corpora, `fLeaves` holds exactly one entry, and that entry is **not the leaf
itself**: it is a four-byte back-reference to a copy written in full inside a
member leaf's `fLeafCount`. This is the mechanism of
[TLeaf §3.1](TLeaf.md#31-fleafcount-is-a-buffer-object-reference), seen from the
other side. A reader that does not follow buffer back-references sees an empty
leaf list on every count branch in the file.

Following the reference helps little. The read procedures of §8 ignore the leaf:
`ReadLeavesCollection` and `ReadLeavesClones` take a single `Int_t` directly from
the entry and bound-check it against `fMaximum`
(`root/tree/tree/src/TBranchElement.cxx:4337-4340`,
`root/tree/tree/src/TBranchElement.cxx:4525-4528`). A count branch is not read
with the leaf-driven procedure of [TLeaf §5](TLeaf.md#5-reading-one-entry),
whether or not the leaf can be found.

## 5. `fClassName` names the class `fID` indexes

`fClassName` is **not** the branch's own type. It is the class whose
`TStreamerInfo` element list `fID` indexes, and `fCheckSum` and `fClassVersion`
describe that same class. One rule covers every case:

- `fID ≥ 0`: `fClassName` is the class that *declares* the member.
- `fID < 0`: there is no member to index, and `fClassName` is the class of the
  object the branch holds.

`ttree/split-object` shows both in five branches of one tree. The split node
`ev` has `fID` −2 and `fClassName` `Ev`, the class being split. The base-class
branch `Base` has `fID` 0 and `fClassName` `Ev`, because element 0 of `Ev` is
the base-class entry. The member branch `fBase` under it has `fID` 0 and
`fClassName` `Base`, because element 0 of *`Base`* is `fBase`. `fCheckSum`
follows the same rule: `0x85067d87` on the five `Ev` branches, `0x013b271d` on
`fBase`.

The same rule explains a shape that looks odd in real files. On an `fType` 4
branch:

```
fID = -1   fClassName = vector<mu2e::TrkInfo>   fClonesName = mu2e::TrkInfo
           a top-level collection: fClassName is the collection type

fID = 11   fClassName = Evt                     fClonesName = Hit
           a collection member of a split parent: fClassName is the parent,
           fID indexes `hits` within it, fClonesName is the value type
```

Both forms occur, 34 and 50 times.

### 5.1 The other name fields

| Field | Non-empty when |
|---|---|
| `fClassName` | always: 6736 of 6736 |
| `fClonesName` | exactly `fType` 3 (21/21) and 4 (84/84); empty on all 6631 others |
| `fParentName` | empty on every `fType` −1 branch, on every `fType` 0 or 4 branch with `fID < 0`, and on 16 of 21 `fType` 3 |

`fParentName` is the class the branch was split *out of*, which is not always
`fClassName`: on `ttree/split-object` the branch `fBase` has `fClassName` `Base`
and `fParentName` `Ev`. It also depends on something outside the class: a
trailing dot in the name passed to `TTree::Branch` changes it. `Splitting.md`
covers this, and ROOT's own source calls it "very annoying"
(`root/tree/tree/src/TBranchElement.cxx:476-480`).

`fClassVersion` is 0 on 981 of the 6734 `TBranchElement`s in the corpora. Zero
means the class had no version to record, and the streamer info must then be
matched by `fCheckSum`, the foreign-class path of
[Streamer information](../02-serialization/StreamerInfo.md).

### 5.2 `fStreamerType` disagrees with the streamer info, by design

`fStreamerType` is the element's type code, sampled when the branch was created
(`root/tree/tree/src/TBranchElement.cxx:351`). The streamer info in the same file
records a different code for the same member, and both are correct.

The cause is the write path of `TStreamerSTL::Streamer`. Instead of the element
it holds, it writes a temporary copy with `fType` set to `kStreamer`
(`root/core/meta/src/TStreamerElement.cxx:2140-2146`); the source comment reads
*"To enable forward compatibility we actually save with the old value"*. The
in-memory element, which the branch sampled, keeps `kSTL`.

For a `std::vector` member:

```
the branch's fStreamerType          300   kSTL
the streamer element's fType        500   kStreamer
```

Measured over both corpora, the two disagree on 2004 branches and no others, in
two groups:

| Branch `fStreamerType` | Element `fType` | Count | What it is |
|---|---|---|---|
| 300 (`kSTL`) | 500 (`kStreamer`) | 1988 | every STL member, at `fType` 0, 4, 31 and 41 alike |
| −1 (`kNoType`) | 0 (`kBase`) | 16 | top-level `TClonesArray` branches — `fType` 3 with `fClassName` `TClonesArray` |

Every other branch with `fID ≥ 0` agrees with its element.
`ttree/split-nested` asserts both halves of the first row: the branch
`fDet.fHits` at `fStreamerType` 300, and `NDet`'s element `fHits` at `fType` 500.

The second row is a different case. −1 is `kNoType`: the branch declares no
element type, so there is nothing to agree with. A reader should treat −1 as
"use `fType` instead", not as a type code.

Three more rows occur in ROOT's own test files (`root/roottest/`), which neither
corpus includes:

| Branch `fStreamerType` | Element `fType` | Count | What it is |
|---|---|---|---|
| 71 (`kSTLp`) | 500 (`kStreamer`) | 4 | an STL member declared as a pointer, `vector<T>*`: `RefTest.root` (4.04/02), two branches in each of two tree cycles |
| 320 (`kSTL + kOffsetL`) | 500 (`kStreamer`) | 3 | a fixed-size array of STL objects, `std::string[2]`: `stringarray.old.root` (6.25/01) |
| 11 (`kUChar`) | 11 on disk, 18 (`kBool`) after the fixup | 42 | a `Bool_t` or `bool` member written before 4.03/02: 5 files from 3.04/02 to 4.02/00, `mksm.root` among them |

The first two are the same mechanism as the 300 row. The code the branch samples
is the one `TStreamerSTL::Streamer` computes on read: `kSTLp` for a pointer,
otherwise `kSTL`, plus `kOffsetL` for an array
(`root/core/meta/src/TStreamerElement.cxx:2124-2128`). Neither is legacy: ROOT
6.40.04 writes 71 for a `std::vector<T>*` member and 320 for a `std::string[2]`
against a stored 500. `ttree/split-stl-pointer` has 71, 320 for a
`vector<T>[2]`, and a third code no corpus file has: 91 (`kSTLp + kOffsetL`)
for an array of pointers to a collection.

The third is not a divergence on disk. Before `kBool` existed, `Bool_t` was code
11 (`kBool_t = 11` at `v4-00-08:meta/inc/TDataType.h:37`; `bool` also mapped to
`kUChar_t`, `v4-00-08:meta/src/TDataType.cxx:223-225`), so the branch and the
element both stored 11. Code 18 first appears in 4.03/02
(`v4-03-02:meta/inc/TDataType.h:37`). The element's read-time fixup of
[Streamer information §7.2](../02-serialization/StreamerInfo.md#72-read-time-fixups)
turns its 11 into 18 (`root/core/meta/src/TStreamerElement.cxx:566`).
`TBranchElement::Streamer` has no matching fixup for `fStreamerType`
(`root/tree/tree/src/TBranchElement.cxx:6027-6044`), so in ROOT's memory too an
old branch says 11 while its element says 18. Both are one byte on disk, so the
difference is harmless. A branch at 11 is consistent only with an element that
*stored* 11, not with one that stored 18.

**`fStreamerType` cannot be looked up in the
[element-type table](../02-serialization/ElementTypes.md#1-the-type-codes)
without this caveat.** That table says code 300 never reaches a file, which is
true of a streamer element and false of a branch.

## 6. `fBranchCount` is a back-reference, and `fBranchCount2` is never set

Both are declared `TBranchElement*` and both are persistent. Neither holds an
object. `fBranchCount` holds a **four-byte buffer back-reference** to a branch
written earlier in the same record, resolved with the map machinery of
[Buffer §6](../02-serialization/Buffer.md#6-object-slots). This is the third
place in a `TTree` structure that does this, after
[`fLeaves`](TTree.md#5-fleaves-holds-references-not-leaves) and
[`fLeafCount`](TLeaf.md#31-fleafcount-is-a-buffer-object-reference).

Measured over all 6736:

| `fType` | `fBranchCount` | `fBranchCount2` |
|---|---|---|
| 31 | a reference, 733 / 733 | null, 733 / 733 |
| 41 | a reference, 1503 / 1503 | null, 1503 / 1503 |
| 0 | a reference on 16, null on 4204 | null, 4220 / 4220 |
| −1, 1, 2, 3, 4 | null | null |

`fBranchCount` has two kinds of target:

- On an `fType` 31 or 41 member it points at the `fType` 3 or 4 count branch of
  the container the member belongs to.
- On an `fType` ≤ 2 member it points at an ordinary counter branch, itself
  `fType` 0 but with `fStreamerType` 6, `kCounter`
  (`root/core/meta/inc/TVirtualStreamerInfo.h:132`). This is the classic
  `Int_t N; Short_t Slice[N];` shape, and the two dispatch rows
  `ReadLeavesMemberBranchCount` and `ReadLeavesMemberCounter` exist for it.
  An unsigned counter is not promoted and keeps `fStreamerType` 13, `kUInt`
  ([Element types §2.1](../02-serialization/ElementTypes.md#21-kcounter-6);
  `root/core/meta/src/TStreamerElement.cxx:99`); `TBits::fNbytes` is one. ROOT
  dispatches that counter branch to `ReadLeavesMember` rather than
  `ReadLeavesMemberCounter` (`root/tree/tree/src/TBranchElement.cxx:5807-5812`),
  and the counted branch still takes its count from `fBranchCount->GetValue`
  (`root/tree/tree/src/TBranchElement.cxx:4649`), whatever the counter's type.

In the second case the relationship is recorded twice. In
`uproot-small-evnt-tree-fullsplit.root` the branch `SliceI16` has
`fStreamerType` 42 (`kOffsetP + 2`), a title `SliceI16[N]`, an `fBranchCount`
pointing at the *branch* `N`, and a leaf whose `fLeafCount` points at the *leaf*
`N`. A reader may follow either chain. The leaf chain, described in
[TLeaf §3.1](TLeaf.md#31-fleafcount-is-a-buffer-object-reference), is enough on
its own.

`fBranchCount2` is null in all 6736. It exists for the second dimension of a
two-dimensional variable-size array. None of the 178 files uses it, and this
specification cannot state what a non-null one looks like.

## 7. `fMaximum` bounds the count

On an `fType` 3 or 4 branch, `fMaximum` is the largest collection size the writer
saw. It is used on read: the read procedure compares the count it just read
against it and treats `n < 0 || n > fMaximum` as corruption
(`root/tree/tree/src/TBranchElement.cxx:4340`,
`root/tree/tree/src/TBranchElement.cxx:4528`).

It is non-zero on 19 of 21 `fType` 3 branches and 42 of 84 `fType` 4, and on 2 of
the 4220 `fType` 0. A zero `fMaximum` on a count branch means every entry's
collection was empty, and the bound check then rejects any non-zero count. A
reader should therefore apply the check as ROOT does rather than as a hard
invariant.

On an `fType` 0 counter branch, only a `kCounter` (6) branch keeps `fMaximum`.
`FillLeavesMemberCounter` is the only fill procedure that updates it
(`root/tree/tree/src/TBranchElement.cxx:1758-1759`), and it is chosen only for
`fStreamerType` 6 (`root/tree/tree/src/TBranchElement.cxx:5900-5901`). An
unpromoted counter of code 3 or 13 (§6) has `fMaximum` 0 whatever it counted, as
in `ttree/split-tbits`.

## 8. The read procedure is selected by four fields, not one

The selection is made at `root/tree/tree/src/TBranchElement.cxx:5772-5816`.
`fType` decides most of it, but `fID`, `fSplitLevel`, `fStreamerType` and whether
`fBranchCount` is set also take part:

| Condition | Procedure | In the corpora |
|---|---|---|
| `fType == 4` | `ReadLeavesCollection` | 84, in 16 files |
| `fType == 41`, `fSplitLevel >= 100`, count branch is a `vector` | `ReadLeavesCollectionSplitVectorPtrMember` | **0** |
| `fType == 41`, `fSplitLevel >= 100`, otherwise | `ReadLeavesCollectionSplitPtrMember` | **0** |
| `fType == 41` otherwise | `ReadLeavesCollectionMember` | 1503, in 16 files |
| `fType == 3` | `ReadLeavesClones` | 21, in 2 files |
| `fType == 31` | `ReadLeavesClonesMember` | 733, in 2 files |
| `fType < 0` | `ReadLeavesCustomStreamer` | 16, in 4 files |
| `fType == 0` and `fID == -1` | `ReadLeavesMember` | 216, in 25 files |
| `fType <= 2` and `fBranchCount` set | `ReadLeavesMemberBranchCount` | 16, in 2 files |
| `fType <= 2` and `fStreamerType == 6` | `ReadLeavesMemberCounter` | 2, in 2 files |
| `fType <= 2` otherwise | `ReadLeavesMember` | 4143, in 31 files |

`fSplitLevel` packs two things: `fSplitLevel % 100` is a depth countdown, and the
hundreds component flags a split collection of pointers
(`root/tree/tree/src/TBranchElement.cxx:333-334`;
`kSplitCollectionOfPointers` is 100, `root/tree/tree/inc/TTree.h:310`).
`fSplitLevel` never exceeds 99 in either corpus, so none of the 178 files
reaches the two pointer-collection procedures; they are named here from the
source alone.

A twelfth row, `ReadLeavesMakeClass`, is selected by an in-memory bit and is a
reading *mode*, not a property of the file. It has no bearing on a reader that
produces values rather than filling a generated class.

## 9. Reading

A branch record is read as a [`TBranch`](TBranch.md#10-reading) is. The steps
below add what to do with the eleven fields.

1. Read the branch with the streamer-driven algorithm. The class is
   `TBranchElement`, or `TBranchObject` (see §12).
2. Read `fType` and `fID`. If `fType` is 0, use §3.2 to decide which of the three
   cases it is.
3. If `fType` is 1 or 2, the branch holds nothing. Descend into `fBranches`.
   The exception is an `fType` 1 branch with no sub-branches but with baskets,
   the empty base class of §4: each entry is one framed object of that base
   class.
4. Otherwise resolve `fClassName` to a streamer info, matching by
   `fClassVersion` when it is non-zero and by `fCheckSum` when it is 0.
   If `fID ≥ 0`, element `fID` of that info is the member this branch holds.
5. If `fBranchCount` is non-zero, resolve it as a buffer back-reference (§6) to
   find the count branch. The number of values in this branch's entry comes from
   that branch's entry, not from this one
   (`root/tree/tree/src/TBranchElement.cxx:4566`,
   `root/tree/tree/src/TBranchElement.cxx:4493`).
6. Select the read procedure with the table of §8.
7. For `fType` 3 and 4, the entry is a single `Int_t` count, and no leaf
   describes it. For `fType` −1 the entry is the whole object, read with the
   class's own streamer (`root/tree/tree/src/TBranchElement.cxx:4711-4712`).
   For everything else the entry is the member's value or values.

Locating the basket and the entry's byte range inside it is unchanged:
[`TBranch` §10](TBranch.md#10-reading) and [`TBasket`](TBasket.md). The byte-level
content of each procedure in step 7 is in `ReadingEntries.md`.

## 10. Invariants

1. `fType` ∈ {−1, 0, 1, 2, 3, 4, 31, 41}. Anything else is `Fatal` in ROOT
   (`root/tree/tree/src/TBranchElement.cxx:5815`).
2. `fClassName` is never empty.
3. `fClassVersion ≥ 0`; the writer records the absolute value
   (`root/tree/tree/src/TBranchElement.cxx:6053-6057`).
4. `fClonesName` is non-empty if and only if `fType` is 3 or 4.
5. A branch with `fType` 1 or 2 has no leaf; every other `fType` has exactly
   one. On `fType` 3 and 4 that leaf is always a back-reference, never written
   in place.
6. A branch with `fType` 1 or 2 has `fWriteBasket` 0 and `fTotBytes` 0.
7. `fBranchCount` is set if and only if `fType` is 31 or 41, or the branch is an
   `fType` ≤ 2 member with a counter in another branch.
8. If `fID ≥ 0`, it is a valid index into the element list of the streamer info
   named by `fClassName` and selected by `fClassVersion` or `fCheckSum`.
9. `fBranchCount`, when set, refers to a branch written earlier in the same
   record which is either `fType` 3 or 4, or `fType` ≤ 2 with `fStreamerType` 6
   (`kCounter`), 13 (`kUInt`) or 3 (`kInt`). A counter that was not promoted
   keeps 13 or 3 (§6; [Element types §2.1](../02-serialization/ElementTypes.md#21-kcounter-6)):
   an unsigned counter such as `TBits::fNbytes` always does.
10. If `fID ≥ 0` and `fStreamerType` is not −1, it equals the `fType` of the
    element it indexes, with two exceptions, both in-memory codes (§5.2).
    Against an STL element, whose `fType` is stored as 500, it is the code the
    element's read path computes: `kSTLp` (71) if `fTypeName` ends in `*`, else
    `kSTL` (300), plus `kOffsetL` (20) if `fArrayLength > 0`
    (`root/core/meta/src/TStreamerElement.cxx:2124-2128`). Against a `Bool_t`
    element that stored 11, it may be 11 though the fixup reads 18.

## 11. Errata

| # | Claim | Correction |
|---|---|---|
| 1 | `root/tree/tree/inc/TBranchElement.h:72`: "`fID==-1` for the former" | Incomplete. `fID` has two negative sentinels, and the one the header omits — −2, the split node — occurs on 176 branches in the corpora. ROOT's own code tests for it at `root/tree/tree/src/TBranchElement.cxx:2279` and `root/tree/tree/src/TBranchElement.cxx:3812` |
| 2 | `root/tree/tree/inc/TBranchElement.h:75-78`: `fType` 3 and 4 are "branch count of a split TClonesArray / STL Collection" | Correct but incomplete: those branches hold the count *in their own baskets*, and their one leaf is a back-reference that the read procedure does not use (§4). Every other data-bearing branch in a tree has its leaf written in place |
| 3 | The name `fBranchCount` suggests a pointer to a branch | It is a four-byte buffer back-reference, like `fLeaves` and `fLeafCount`. Nothing in the header says so |
| 4 | `root/tree/tree/inc/TBranchElement.h:79`: "branch streamer type" — implying the type code the file records | It is the code the element had **in memory**, which for an STL member differs from the one the same file's streamer info gives: 300, 71 or 320 against a stored 500 (§5.2). 1988 branches in the corpora disagree with their element this way, and none of them is an error |

## 12. Class versions

Measured across both corpora; the layout is taken from each file's own streamer
info, never from the version number.

| Class version | Elements | `fClassVersion` width | Writing ROOT |
|---|---|---|---|
| 1 | 6 | 4 bytes | 4.00 |
| 8, 9 | 12 | 4 bytes | 4.00.07 to 5.34.38 |
| 10 | 12 | **2 bytes** | 6.04.02 onward |

Version 1 has `TBranch`, `fClassName`, `fClassVersion`, `fID`, `fType` and
`fStreamerType` only: no `fParentName`, `fClonesName`, `fCheckSum`, `fMaximum` or
either `fBranchCount`. Versions 2 to 7 occur in neither corpus.

`fClassVersion` changed from `Int_t` to `Version_t` in the same commit that
bumped the class version to 10, so the width follows the version. However, two
different checksums occur at each of versions 9 and 10 with identical member-name
and type-code lists, because the recorded type *names* changed (`Int_t` to
`int`). A checksum identifies a declaration, not a layout.

Other branch classes seen in the corpora:

| Class | Class version | Count in the corpora |
|---|---|---|
| `TBranchObject` | 1 (`root/tree/tree/inc/TBranchObject.h:71`) | 2, carrying the only two `TLeafObject`s |
| `TBranchClones` | 2 (`root/tree/tree/inc/TBranchClones.h:66`) | **0** |
| `TBranchSTL` | 1 (`root/tree/tree/inc/TBranchSTL.h:42`) | **0** |

`TBranchClones` and `TBranchSTL` appear in no file of the 178 and in no file's
streamer info. Both can be produced on demand: §13 describes the first and
[Splitting §5](Splitting.md#5-collections-of-pointers-and-tbranchstl) the
second.

## 13. `TBranchClones`, and the only API that makes one

Nothing in ROOT's modern interface produces a `TBranchClones`. `TTree::Branch`
gives a `TBranchElement`; the only constructor call in the codebase is in
`TTree::BranchOld`, for a data member that is a pointer to a `TClonesArray`, at
a split level other than 2 (`root/tree/tree/src/TTree.cxx:2216-2227`). `BranchOld`
also makes the parent a `TBranchObject`, so one call produces both a
`TBranchClones`, which the corpora lack, and a `TBranchObject`, of which they
have two.

### 13.1 It derives from `TBranch` and does not stream a `TBranch` base

```
bc:u32  ver:i16=2
<TNamed>
fCompress:i32  fBasketSize:i32  fEntryOffsetLen:i32  fMaxBaskets:i32
fWriteBasket:i32
fEntryNumber:i64  fEntries:i64  fTotBytes:i64  fZipBytes:i64
fOffset:i32
fBranchCount:object        -- a whole TBranch, pointer-streamed
fClassName:string
<TObjArray>                -- fBranches
```

`root/tree/tree/src/TBranchClones.cxx:386-466`. The ten fields between the
`TNamed` and `fBranchCount` are **`TBranch`'s own members, written individually**.
The class inherits from `TBranch`, but its streamer never calls
`TBranch::Streamer` and emits no `kBase` element. A reader therefore cannot read
it with `TBranch`'s layout, and thirty-odd `TBranch` fields are absent:
`fLeaves`, `fBaskets`, `fBasketBytes`, `fBasketEntry`, `fBasketSeek`,
`fFileName`, `fIOFeatures` and the rest ([TBranch §2](TBranch.md)).

No file has a streamer info for it, because its `Streamer` never calls
`WriteClassBuffer`. `ttree/branch-clones` has 23 infos, `TBranchObject` and
`TBranch` among them, and no `TBranchClones`. This puts it with `TBasket` and
`TTreeIndex` in the category that
[Bootstrap classes §5](../99-appendix/Bootstrap.md) calls the better failure: a
reader cannot follow a wrong info, because there is none.

### 13.2 `fBranchCount` must be read, not skipped

`fBranchCount` is the branch holding the clones count, written as an object
pointer; in `ttree/branch-clones` it is a 673-byte `TBranch` named `fHits_`. A
reader that treats the slot as opaque and skips it by its byte count
**desynchronises later**. The classes that object declares, `TBranch` and `TLeafI`
among them, are referenced by *position* from the sub-branches in `fBranches`
([Buffer framing §5.2](../02-serialization/Buffer.md)), and a skipped body never
records them. `tools/rootfile.py` first got this wrong and failed with
`slot at 2458 references class position 760, which was not seen earlier`.

### 13.3 The sub-branch names lose the parent's prefix

`BranchOld` builds each sub-branch name as `parent.member` and then, unless the
parent's name ends in a dot, passes `&branchname.Data()[1]`, dropping the first
character on the assumption that it is a `*`
(`root/tree/tree/src/TTree.cxx:2224-2227`, where ROOT's own comment reads
`FIXME: This is wrong!  The asterisk is not usually in the front!`).

In `ttree/branch-clones` the parent is `ev` and the `TBranchClones` is named
`fHits`, not `ev.fHits`, and its children are `fHits.fI`, `fHits.fX`,
`fHits.fUniqueID` and `fHits.fBits`. A reader must not assume a sub-branch name
begins with its parent's.

## 14. Reference files

| Case | What it covers |
|---|---|
| `ttree/split-object` | `fType` 0 with `fID` −2 and with `fID` ≥ 0, `fType` 1, the empty `fLeaves` of an interior node, `fClassName`/`fCheckSum` following `fID` rather than the branch, and `fEntryOffsetLen` taken from `fDefaultEntryOffsetLen` on the interior nodes and reset to 0 on the members |
| `ttree/split-counter` | `fType` 0 with `fStreamerType` 6 (`kCounter`) and with an `fBranchCount`; `fMaximum` on the counter rather than the counted branch |
| `ttree/split-nested` | `fType` 2, `fType` 4 with `fID` ≥ 0, `fType` 41, and the `fStreamerType` 300-against-500 divergence of §5.2 on both sides |
| `ttree/split-clones` | `fType` 3 and `fType` 31, and a `TObject` base flattened into two member branches whose `fClassName` is `TObject` |
| `ttree/split-stl-toplevel` | `fType` 4 with `fID` −1, where `fClassName` is the collection type and `fStreamerType` is −1 |
| `ttree/split-ptr-collection` | `fSplitLevel` ≥ 100 and a `TBranchSTL`; see [Splitting §5](Splitting.md#5-collections-of-pointers-and-tbranchstl) |
| `ttree/split-double32` | Five truncated-float members behind identical `TLeafElement` leaves, whose widths differ and are recoverable only from the streamer element's title |
| `ttree/split-stl-pointer` | The §5.2 divergences a current ROOT writes: `fStreamerType` 71, 91 and 320 against a stored 500, with a `Bool_t` member at 18 on both sides as the control |
| `ttree/split-tbits` | §6's unpromoted counter: a split `TBits` whose `fNbytes` branch has `fStreamerType` 13 (`kUInt`), which invariant 9 accepts, and `fMaximum` 0 on it (§7) |
| `ttree/branch-clones` | §13 in full: the only `TBranchClones` here, under the only `TBranchObject`, with its ten hand-written `TBranch` fields, its pointer-streamed `fBranchCount`, and the lost name prefix of §13.3 |

Seven of the eight `fType` values have a fixture, and so do `TBranchClones` and
`TBranchObject`. Not covered, and tracked in `PLAN.md` §9.11: `fType` −1, which
needs a class with a hand-written `Streamer`, and a non-null `fBranchCount2`,
which none of the 178 files has.

Eight of the ten invariants of §10 were confirmed by corrupting a copy of
`ttree/split-object` and checking that the intended invariant is the one that
rejects it. The two exceptions:

- **Invariant 2 cannot be reached by corruption.** `fClassName` is a counted
  string, so its length is part of the record's framing: blanking it
  desynchronises everything after it and the byte count of
  [Buffer §6](../02-serialization/Buffer.md#6-object-slots) rejects the file
  first. The invariant is still stated because a writer can produce an empty
  `fClassName` without breaking the framing, but no fixture can demonstrate it.
- **The `fType` 3 and 4 half of invariant 5** has not been confirmed by
  corruption. The fixtures for it exist (`ttree/split-clones` has `fType` 3, and
  `ttree/split-stl-toplevel` and `ttree/split-nested` have `fType` 4, as §14's
  table records); what is missing is the corruption pass.
