# Splitting

How one `TTree::Branch` call becomes a tree of branches, and what of that
arrangement survives into the file.

Prerequisites: [TBranch](TBranch.md), [TBranchElement](TBranchElement.md),
[TLeaf](TLeaf.md).

Splitting is a writer's decision, and under `PLAN.md` §2.8 this specification
does not prescribe writers' decisions. It still has to describe the result,
because the result is the only structure a reader has. A split object is not one
branch holding an object but a dozen branches holding one column each, and only
their nesting records that they belong together.

In short: **take the structure from `fBranches`, the meaning from
`fType`/`fID`/`fClassName`, and the counts from `fBranchCount`.** Names, titles
and `fSplitLevel` are all unreliable for structure, as §3 and §4 show.

## 1. The branch tree

An unsplit branch is a leaf of the tree in both senses: one `TBranch`, one
`TLeaf`, one column of entries that are whole serialised objects. A
split branch is an interior node whose `fBranches` holds the columns.

`ttree/split-nested` is the smallest case that has every shape. One call,
`t.Branch("nt", &p, 32000, 99)` on a class holding a class holding a
`std::vector`, produces seven branches:

```
nt                      fType 0, fID -2     the split node
  fDet                  fType 2             a class-typed member
    fDet.fNo            fType 0, fID 0
    fDet.fHits          fType 4             the collection count
      fDet.fHits.fId    fType 41
      fDet.fHits.fE     fType 41
  fRun                  fType 0, fID 1
```

Four of the seven hold data. The other three (`nt`, `fDet` and, in a different
way, `fDet.fHits`) are there to be walked through.

### 1.1 Interior nodes hold nothing, and say so twice

`fType` 1 (a base class) and `fType` 2 (a class-typed member) are pure interior
nodes: `fWriteBasket` is 0, `fTotBytes` is 0, and `fLeaves` is an empty
`TObjArray`. This holds for every such branch in both corpora
([TBranchElement §4](TBranchElement.md#4-two-ftype-values-have-no-leaf-and-two-reach-theirs-only-by-reference))
and is asserted byte for byte in `ttree/split-object` and `ttree/split-nested`.

Files written before 5.34/20 and 6.02/00 have one exception: a base class with no
data members still got its own `fType` 1 branch, with no children and no leaf but
with a basket of framed, empty base-class objects
([TBranchElement §4](TBranchElement.md#4-two-ftype-values-have-no-leaf-and-two-reach-theirs-only-by-reference)).

An empty `fLeaves` does **not** by itself mean a branch holds nothing; see §5.

A split node (`fType` 0, `fID` −2) can also be childless, in files of any
release. `TTree::Bronch` gives a top-level branch `fID` −2 whenever it splits
(`root/tree/tree/src/TTree.cxx:2604-2608`) and then lets `Unroll` add one
sub-branch per element of the class's streamer info
(`root/tree/tree/src/TTree.cxx:2615-2617`). A class whose streamer info lists no
element, because every member is transient or there is none, gets no
sub-branch. `TClass::CanSplit` refuses only a class whose `sizeof` is 1
(`root/core/meta/src/TClass.cxx:2384-2388`), so a class with transient members
is still split. The branch keeps its one `TLeafElement`, fills through
`TBranch::Fill` because it has no sub-branch
(`root/tree/tree/src/TBranchElement.cxx:1297-1306`), and each entry is empty:
the fill writes the elements of an info that has none.

> Measured in `lhcb.root` of `root/roottest/` (5.17/07, written by LHCb's POOL
> layer): branch `DataObject`, whose `DataObject` streamer info lists no
> element, has `fID` −2, no sub-branch, one leaf and an embedded basket of 498
> entries whose offsets are all equal to `fKeylen` 79, so every entry is 0
> bytes. ROOT 6.40.04 writes the same shape for a class whose only members are
> marked `//!`: `fID` −2, split level 99 or 1, no sub-branch, and a basket
> record of 3 entries of 0 bytes.

## 2. Which classes are split

A reader never has to make this decision, because the file records the outcome.
It does have to know that the outcome can be "not split" even when a high split
level was requested, which is §6. The rule is `TClass::CanSplit`
(`root/core/meta/src/TClass.cxx:2326`). A class is **not** split when any of
these holds:

| Condition | Where |
|---|---|
| It has a reference proxy (`TRef` and friends) | `root/core/meta/src/TClass.cxx:2341` |
| Its name begins `TVectorT<` or `TMatrixT<` | `root/core/meta/src/TClass.cxx:2342-2343` |
| It is `string` or `std::string` | `root/core/meta/src/TClass.cxx:2345` |
| It is a collection of pointers, unless §5 applies | `root/core/meta/src/TClass.cxx:2354` |
| It is a collection with no value class | `root/core/meta/src/TClass.cxx:2357` |
| It is a collection of `TString` or `std::string` | `root/core/meta/src/TClass.cxx:2359` |
| It is a collection whose value class cannot be split | `root/core/meta/src/TClass.cxx:2361` |
| It is a collection of collections | `root/core/meta/src/TClass.cxx:2362` |
| It has an external streamer or a custom member streamer | `root/core/meta/src/TClass.cxx:2369`, `root/core/meta/src/TClass.cxx:2376` |
| It is empty (`Size() == 1`) | `root/core/meta/src/TClass.cxx:2384` |
| One of its base classes forbids it | `root/core/meta/src/TClass.cxx:2391` |

`TObject` and `TClonesArray` are always splittable
(`root/core/meta/src/TClass.cxx:2339-2340`). `TRef`, `TRefArray`, `TArray`,
`TCollection` and `TTree` forbid it for anything deriving from them
(`root/core/meta/src/TClass.cxx:2267-2276`).

This is the writer's rule. It is recorded here to explain files, not to
constrain them: a file that splits `std::string` is not invalid, only not one
ROOT 6.40.04 would write.

## 3. Names

The names of the branches inside a split object do not describe the class. They
depend on the string the user passed to `TTree::Branch`, and the same class
produces two different sets of names depending on that string's last character.

### 3.1 A trailing dot changes every name below a split object

`ttree/split-naming` writes the same class twice into the same tree, once as
`Branch("plain", ...)` and once as `Branch("dotted.", ...)`. The two halves have
the same class, split level and data, and the same `fID`, `fType`,
`fStreamerType`, `fClassName` and `fSplitLevel` on corresponding branches. The
names differ:

| | `Branch("plain", …)` | `Branch("dotted.", …)` |
|---|---|---|
| the split node | `plain` | `dotted.` |
| the base-class node | `NBase` | `dotted.NBase` |
| a member of the base | `fB` | `dotted.NBase.fB` |
| a member of the class | `fI` | `dotted.fI` |
| **`fParentName` of `fB`** | **`NEv`** | **`NBase`** |

The last row is the one a reader is most likely to get wrong. `fParentName` on
the same member of the same class is the top class in one half and the declaring
class in the other. ROOT's source notes both differences in a comment above the
code that causes them (`root/tree/tree/src/TBranchElement.cxx:476-480`): *"this is very
annoying. It is also very annoying that the naming conventions for the
sub-branch names are different as well."*

**Not below a top-level split collection.** There the dot never reaches a name:
`TBranchElement::Init` removes it before anything is named
(`root/tree/tree/src/TBranchElement.cxx:906-909`). `ttree/split-dotted-collection`
writes one `std::vector` of a split class as `Branch("v.", ...)` and as
`Branch("w", ...)`, and the two come out in the same shape: a count branch named
`v`, not `v.`, titled `v_`, and members `v.fId` titled `fId[v_]`, exactly as for
`w`. The members keep the dot as a separator either way.

**A writer that chooses the name should add the trailing dot.** This is a
recommendation, not a format rule; it is here because readers of this section
often also choose branch names. With no trailing dot the parent prefix is dropped
from every child (`root/tree/tree/src/TBranchElement.cxx:6217`; §3.2 describes the
mechanism). That is the condition under which the counter bug of
[Reading entries §4.1](ReadingEntries.md#41-resolve-the-counter-by-name-not-by-fbranchcount)
occurs. Two split objects of one class whose sub-branches have no parent prefix
have ambiguous member names, and ROOT resolves each counted array's counter by
looking the name up over the whole tree, so both objects point at the first
object's counter. In `alice_ESDs.root` this loses every element of
`PrimaryVertex.fIndices`. A trailing dot makes the names unambiguous and avoids
the bug, at the cost of a longer name.

### 3.2 Base classes are elided, class-typed members are not

The first four rows come from one branch of the code in `TBranchElement`'s
constructor. When a base-class node's name equals the base class's own name,
which happens exactly when the parent name has no trailing dot and no internal
dot, the name is **elided** and its members are unrolled under the grandparent's
name (`root/tree/tree/src/TBranchElement.cxx:481-493`). This is why `fB` in the
plain half is just `fB`.

A class-typed member is never elided: in `ttree/split-nested` no trailing dot is
involved for the member `fDet`, and its sub-branches are still `fDet.fNo` and
`fDet.fHits`.

A dot in a branch name can therefore mean at least three things, and a reader
cannot tell which from the name alone.

### 3.3 The count-branch convention

Titles, unlike names, record one relationship, fixed when the branches are
constructed. A collection or
`TClonesArray` count branch's title is the name it was constructed with, a
trailing dot removed and an underscore appended, and every member branch of its
content has a title of the form `member[count_]`:

```
fDet.fHits          title  fDet.fHits_
fDet.fHits.fId      title  fId[fDet.fHits_]
fDet.fHits.fE       title  fE[fDet.fHits_]
```

The constructor sets the count branch's title, and its leaf's name and title,
to that one string (`root/tree/tree/src/TBranchElement.cxx:818-825` for a
`TClonesArray`, `root/tree/tree/src/TBranchElement.cxx:985-989` for a
collection, whose name has already lost its dot at
`root/tree/tree/src/TBranchElement.cxx:906-909`, and `root/tree/tree/src/TBranchElement.cxx:579-585` and
`root/tree/tree/src/TBranchElement.cxx:633-639` for the same as a member).
`BuildTitle` derives the same string again from the same name
(`root/tree/tree/src/TBranchElement.cxx:1185-1189`) and gives each member the
bracketed form, on the member branch and on its leaf alike
(`root/tree/tree/src/TBranchElement.cxx:1217-1222`).

The relationship is fixed at construction and nothing re-derives it, so it holds
between the titles, not between a title and `fName`. A program may rename a
branch afterwards with `TNamed::SetName`, and then the count branch's name no
longer is its title's stem.

> Measured in `ship_ROOT_9674.root` of `root/roottest/` (6.17/01, FairShip).
> `TTree::Branch(foldername)` names a folder's branches after the folder path,
> `cbmroot.Stack.MCTrack` (`root/tree/tree/src/TTree.cxx:1927-1946`), and marks
> them `kBranchFolder`. The ten `TClonesArray` branches here have that bit set,
> titles such as `cbmroot.Stack.MCTrack_` and leaves named
> `cbmroot.Stack.MCTrack_` and `cbmroot.Stack.MCTrack.fPx`, but branch names
> `MCTrack` and `MCTrack.fPx`: the writer stripped the folder prefix from the
> branches and not from their titles or leaves. ROOT 6.40.04 reads the file,
> and `RDataFrame` reads `MCTrack.fPdgCode` from it, which is what the roottest
> test checks.
>
> `tlorentzvec.root` of `root/roottest/` (5.27/01) departs the other way. Its
> seven `vector<TLorentzVector>` count branches, such as `muon4mom`, have title
> `_` and a leaf named and titled `_`, while their members are titled
> `fP[muon4mom_]`. No constructor at `v5-26-00` or `v5-27-02` produces that:
> each sets the count's title and the members' brackets from one name. How the
> file was written is not known. ROOT 6.40.04 reads it, as does the
> `TTreeProxy` test it belongs to. Until its writer is known, the file fails
> invariant 4 rather than the invariant being widened to fit it (`PLAN.md`
> §8.16).

This is the human-readable form of the relationship. The machine-readable form
is the member branch's `fBranchCount`
([TBranchElement §6](TBranchElement.md#6-fbranchcount-is-a-back-reference-and-fbranchcount2-is-never-set)),
and a reader should use that: it is a byte offset rather than a string to parse,
and it need not be reconciled with §3.1.

### 3.4 Structure comes from `fBranches`

Given §3.1 to §3.3, the nesting in `fBranches` is the only description of the
object hierarchy that is always correct. Names are advisory. A reader that
reconstructs the hierarchy by splitting names on `.` gets the plain half of
`ttree/split-naming` wrong.

## 4. `fSplitLevel`

### 4.1 It packs two things

`fSplitLevel % 100` is the writer's remaining split budget at that node.
`fSplitLevel - (fSplitLevel % 100)`, the hundreds component, is the
`TTree::kSplitCollectionOfPointers` flag of §5
(`root/tree/tree/src/TBranchElement.cxx:6279-6280`;
`root/tree/tree/inc/TTree.h:310`).

### 4.2 It is not a depth counter

The budget is decremented on some paths, passed through unchanged on others, and
set to 0 on others. `root/tree/tree/src/TBranchElement.cxx:6403-6408` sets it to 0
for the sub-branches of a collection or `TClonesArray` and for any element that
cannot be split, and `root/tree/tree/src/TBranchElement.cxx:6444-6449` does the
same in a second place. `ttree/split-nested` shows the result:

| Branch | Depth | `fSplitLevel` |
|---|---|---|
| `nt` | 0 | 99 |
| `fDet` | 1 | 98 |
| `fRun` | 1 | 98 |
| `fDet.fHits` | 2 | 97 |
| `fDet.fNo` | 2 | **0** |
| `fDet.fHits.fId` | 3 | **0** |

Two branches at the same depth have 97 and 0. A reader must not infer depth,
structure, or whether a branch has children from this field.

### 4.3 What it is needed for

Only the `>= 100` test that selects the pointer-collection read procedures
(`root/tree/tree/src/TBranchElement.cxx:5779`), described in §5.

## 5. Collections of pointers, and `TBranchSTL`

`CanSplit` refuses a `std::vector<T*>` (§2). The exception is an explicit
request: adding `TTree::kSplitCollectionOfPointers` (100) to the split level
passed to `TTree::Branch` makes the writer split it anyway
(`root/tree/tree/src/TBranchElement.cxx:969-970`). The hundreds component is then
passed down to every sub-branch without being decremented. This leaves the
members of the content at `fSplitLevel` 100, which selects
`ReadLeavesCollectionSplitVectorPtrMember` or
`ReadLeavesCollectionSplitPtrMember`
([TBranchElement §8](TBranchElement.md#8-the-read-procedure-is-selected-by-four-fields-not-one)).

**No file in either corpus does this.** Across the 178 files of `PLAN.md` §9.8
and §9.9, written by ROOT releases from 2.24/00 to 6.36, the maximum `fSplitLevel`
is 99. `ttree/split-ptr-collection` is the only evidence this specification has;
everything in this section rests on it and the source.

The arrangement it produces:

```
pc                      TBranchElement   fSplitLevel 199   fType 0, fID -2
  fHits                 TBranchSTL       fSplitLevel 198
    fHits.PHit          TBranchElement   fSplitLevel 197   fType 4, fID -1
      fHits.PHit.fId    TBranchElement   fSplitLevel 100   fType 41
      fHits.PHit.fE     TBranchElement   fSplitLevel 100   fType 41
```

Three things in it are new.

**This arrangement produces a `TBranchSTL`.** It and `TBranchClones` are the
only branch classes in ROOT that appear in no file of either corpus, not even in
a streamer info. It is a `TBranch` with five added persistent members
(`root/tree/tree/inc/TBranchSTL.h:71-77`) and no `fType`, so nothing in
[TBranchElement](TBranchElement.md) applies to it:

| Member | Type | Value in `ttree/split-ptr-collection` |
|---|---|---|
| `fContName` | counted string | `vector<PHit*>`, the **collection's** class name, at offset 3455 |
| `fClassName` | counted string | `PEv`, the parent class, at 3469 |
| `fClassVersion` | `i32` | 1, at 3473; a four-byte `Int_t`, not the `Version_t` of `TBranchElement` class version 10 |
| `fClCheckSum` | `u32` | `0x9838e2f7`, the collection class's checksum, at 3477 |
| `fID` | `i32` | 0, at 3481 |

`fContName` matters most to a reader: it names the collection type, which can
otherwise only be inferred from the child branches.

**A `TBranchSTL` has baskets full of data and no leaf.** `fLeaves` has `nobjects`
0 while `fWriteBasket` is 1. This is the only shape current ROOT writes where an
empty leaf list does not mean an empty branch (the other, before 5.34/20 and
6.02/00, is the empty base class of §1.1), and it is why
[TLeaf §10](TLeaf.md#10-invariants) limits its invariants 5 to 7 to branches
that have leaves.

**The collection branch beneath it has the value class in its name:**
`fHits.PHit`, not `fHits`. Its `fID` is −1, so by the rule of
[TBranchElement §5](TBranchElement.md#5-fclassname-names-the-class-fid-indexes)
its `fClassName` is its own type, `vector<PHit*>`, and its `fClassVersion` 6 is
the collection's version, not `PHit`'s.

### 5.1 What a `TBranchSTL`'s own basket holds

A `TBranchSTL` has no leaf, so nothing in [TLeaf](TLeaf.md) describes its entries.
Each entry is **one framed `TIndArray`**, written by `WriteClassBuffer` and read by
`ReadClassBuffer` (`root/tree/tree/src/TBranchSTL.cxx:645-648`). `TIndArray` has no
`ClassDef`, so it is a foreign class, and its version word is 0 followed by a
checksum ([Buffer §4](../02-serialization/Buffer.md#4-a-version-word-of-0-has-two-different-meanings)):

```
byteCount:u32   version:i16 = 0   checksum:u32   fElems:u32   flag:u8   fElems × u8
```

`fElems` is the number of indices and `fArr` is a counted pointer `[fElems]` of
`UChar_t`, so it has the one-byte presence flag of
[Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer)
and is absent when `fElems` is 0.

> Demonstrated by `ttree/split-ptr-collection`, whose `fHits` basket at offset 328
> has a 68-byte payload holding three entries and then the offset array: at 397,
> 17 bytes: a byte count of 13, version `00 00`, checksum `0xbe3836fa`, `fElems` 2,
> flag `01` and two index bytes; at 414, 15 bytes (byte count 11), the same with
> `fElems` 0 and flag `00`; at 429, 16 bytes (byte count 12), `fElems` 1. The
> offset array at 445 is a count of 4 and then `69, 86, 101, 0`; the first value
> is `fKeylen` and the fourth is the never-written extra slot of
> [TBasket §5.1](TBasket.md#51-three-things-to-get-right).

`tools/check_invariants.py` reports these baskets as `SKIPPED` rather than
decoding them, so they are counted in the denominator of its `ENTRIES` line and
named. The layout above is all that is needed to decode them, so this is a gap in
the checker, not in the specification. No file in either corpus contains a
`TBranchSTL`, so the corpus figure is unaffected.

## 6. The unsplit fallback

A high split level is a request, not a guarantee. When `CanSplit` refuses (§2),
`TTree::Branch` writes a single branch holding whole serialised objects, and the
split level it was given is still recorded in `fSplitLevel`.

The file records which happened, but not in `fSplitLevel`:

| On disk | Meaning |
|---|---|
| `fType` −1 | unsplit; the class had a custom streamer when written |
| `fType` 0 with `fID` −1 | unsplit; the default streamer was used |
| `fType` 0 with `fID` −2 | split; the columns are in `fBranches` |

The test for "is this branch split" is therefore `fID == -2`, or equivalently and
more robustly, whether `fBranches` is non-empty. `fSplitLevel` answers a different
question, and §4.2 shows that it answers it poorly.

## 7. Reading

Splitting adds nothing to the record-reading procedure. It changes what a reader
does with the result:

1. Walk `fBranches` recursively. The nesting is the structure (§3.4).
2. At each branch, read `fType` and `fID`
   ([TBranchElement §3](TBranchElement.md#3-ftype-and-fid)). `fType` 1 and 2 are
   interior nodes with nothing to read; descend. A childless `fType` 1 branch
   with baskets is the empty base class of §1.1 and is read.
3. A branch with `fBranches` non-empty *and* baskets of its own is a count
   branch (`fType` 3 or 4) or a `TBranchSTL`. Read its entries as well as
   descending. A split parent from a 5.1x fast clone also keeps a basket, an
   embedded one of 0 entries ([TBranch §7](TBranch.md#7-the-entry-counters)),
   and holds no data
   ([Reading entries §2](ReadingEntries.md#2-which-branches-hold-data-at-all)).
4. For a member of a split container, resolve `fBranchCount` to find how many
   values this entry holds (§3.3).
5. Reassembling the columns into an object is left to the reader, and this
   specification deliberately does not describe it. A column's class and member
   are given by `fClassName` plus `fID`, and that is all the file records.

## 8. Invariants

1. A branch with `fID` −2 has a non-empty `fBranches`, unless it is a top-level
   branch (`fType` 0) of a class whose streamer info lists no element. That
   branch has one leaf and every entry in its baskets is 0 bytes (§1.1).
2. A branch with `fType` 1 or 2 has a non-empty `fBranches`: an interior node
   with no children would describe nothing. The exception is an `fType` 1 branch
   whose element is a base class whose streamer info lists no elements, which
   ROOT before 5.34/20 and 6.02/00 wrote as a childless branch with data (§1.1).
3. A count branch's title ends in `_` and equals its leaf's name and its
   leaf's title. ROOT constructs all three as the branch's construction name
   with a trailing dot removed and `_` appended, but a writer may rename the
   branch afterwards, so its current `fName` is not part of the invariant
   (§3.3).
4. Every member branch of a split container (`fType` 31 or 41) has a title of
   the form `member[count_]`, equal to its leaf's title, where `count_` is its
   `fBranchCount` branch's title.
5. A `TBranchSTL` has no leaf.

## 9. Errata

| # | Claim | Correction |
|---|---|---|
| 1 | `root/io/doc/TFile/README.md:256-257`: "Each TBranch contains an array of zero or more leaves (class TLeaf), each corresponding to a basic variable type or a class object that has not been split" | The leaf array does not describe the branch's data in two of the shapes here. On a count branch its single entry is a back-reference rather than a leaf, so a reader that does not resolve it sees none ([TBranchElement §4](TBranchElement.md#4-two-ftype-values-have-no-leaf-and-two-reach-theirs-only-by-reference)); and a `TBranchSTL` has an empty leaf array *and* baskets full of data (§5) |
| 2 | That `fSplitLevel` records how deeply a branch is split, the natural reading of `root/io/doc/TFile/ttree.md:54`, "Branch split level" | It records the writer's remaining budget. It is 0 on branches that were split and on branches that were not, and differs between branches at the same depth (§4.2) |
| 3 | *This document, until 2026-09-23*: a count branch's title is its name with `_` appended, and a split node always has children (invariants 1 and 3) | The title is its *construction* name with `_`, and a writer may rename the branch later (`ship_ROOT_9674.root`); a split node of a class with no streamer-info element has no children and fills empty entries, in current ROOT too (§1.1, §3.3) |

## 10. Reference files

| Case | What it covers |
|---|---|
| `ttree/split-object` | The simplest split: `fType` 0 with `fID` −2, `fType` 1, and the elided base-class name of §3.2 |
| `ttree/split-naming` | §3.1 in full: the same class under a plain and a dotted branch name, 26 assertions, twelve of which are the pairs that differ and do not |
| `ttree/split-counter` | A counted array: `fBranchCount` on an `fType` 0 branch, `fMaximum` on the counter, and the `member[count]` title in its oldest form |
| `ttree/split-nested` | Three levels, `fType` 2, an `fType` 4 count branch with `fType` 41 members, the `name_`/`[name_]` convention, and the `fSplitLevel` table of §4.2 |
| `ttree/split-unsplit` | §6 in one file: the same class split and unsplit side by side, with `fID` −2 against −1 as the only field that separates them |
| `ttree/split-clones` | The `TClonesArray` half of the same shapes: `fType` 3 and 31, and a `TObject` base flattened into columns rather than becoming an `fType` 1 node |
| `ttree/split-dotted-collection` | §3.1's exception: a top-level split collection under `v.` and under `w` has names of the same shape, and the dot survives nowhere |
| `ttree/split-stl-toplevel` | A collection as the branch itself: three branches, no split node above them, and the shortest arrangement ROOT produces |
| `ttree/split-ptr-collection` | All of §5: `fSplitLevel` above 100, a `TBranchSTL`, and an `fType` 4 branch with `fID` −1 |

Not covered: the `ReadLeavesCollectionSplitPtrMember` half of §5, which needs a
non-`vector` collection of pointers. `TBranchClones` is covered:
[TBranchElement §13](TBranchElement.md#13-tbranchclones-and-the-only-api-that-makes-one)
gives the only way to produce one, and `ttree/branch-clones` is the fixture.

Invariants 1 to 4 are confirmed by corrupting a copy of `ttree/split-nested` and
checking that the intended invariant is the one that rejects it. Invariant 5
cannot be: giving a `TBranchSTL` a leaf means lengthening its `fLeaves`, which
breaks the record's byte count first. It is exercised on the one `TBranchSTL` in
the fixtures, but not corruption-tested.

The obvious corruptions for invariants 1 and 2 hit the same limit, because
emptying an `fBranches` array desynchronises the framing. Those two are tested
from the other side instead, by marking a childless branch as a split node.
