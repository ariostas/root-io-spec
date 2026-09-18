# Splitting

How one `TTree::Branch` call becomes a tree of branches, and what of that
arrangement survives into the file.

Prerequisites: [TBranch](TBranch.md), [TBranchElement](TBranchElement.md),
[TLeaf](TLeaf.md).

Splitting is a writer's decision, and by `PLAN.md` §2.8 this specification does
not prescribe writers' decisions. It has to describe the *result* all the same,
because the result is the only structure a reader has: a split object is not one
branch holding an object, it is a dozen branches holding one column each, and
nothing in the file says "these twelve belong together" except the way they are
nested.

The short version for an implementer: **take the structure from `fBranches`, the
meaning from `fType`/`fID`/`fClassName`, and the counts from `fBranchCount`.
Names, titles and `fSplitLevel` are all unreliable for structure, in ways §4 and
§5 make precise.**

## 1. The branch tree

An unsplit branch is a leaf of the tree in both senses: one `TBranch`, one
`TLeaf`, one column of entries that happen to be whole serialised objects. A
split branch is an interior node whose `fBranches` holds the columns.

`ttree/split-nested` is the smallest case with every shape in it. One call —
`t.Branch("nt", &p, 32000, 99)` on a class holding a class holding a
`std::vector` — produces seven branches:

```
nt                      fType 0, fID -2     the split node
  fDet                  fType 2             a class-typed member
    fDet.fNo            fType 0, fID 0
    fDet.fHits          fType 4             the collection count
      fDet.fHits.fId    fType 41
      fDet.fHits.fE     fType 41
  fRun                  fType 0, fID 1
```

Four of those seven hold data. The other three — `nt`, `fDet` and, in a
different way, `fDet.fHits` — exist to be walked through.

### 1.1 Interior nodes hold nothing, and say so twice

`fType` 1 (a base class) and `fType` 2 (a class-typed member) are pure interior
nodes: `fWriteBasket` is 0, `fTotBytes` is 0, and `fLeaves` is an empty
`TObjArray`. That is measured over every such branch in both corpora —
[TBranchElement §4](TBranchElement.md#4-two-ftype-values-have-no-leaf-and-two-reach-theirs-only-by-reference)
— and asserted byte for byte in `ttree/split-object` and `ttree/split-nested`.

An empty `fLeaves` does **not** by itself mean a branch holds nothing; see §5.

## 2. Which classes are split

A reader never has to make this decision — the file records the outcome — but it
has to know that the outcome can be "not split" even when a high split level was
requested, which is §7. The rule is `TClass::CanSplit`
(`root/core/meta/src/TClass.cxx:2326`). A class is **not** split when any of
these holds:

| Condition | Where |
|---|---|
| It has a reference proxy (`TRef` and friends) | `root/core/meta/src/TClass.cxx:2341` |
| Its name begins `TVectorT<` or `TMatrixT<` | `root/core/meta/src/TClass.cxx:2342-2343` |
| It is `string` or `std::string` | `root/core/meta/src/TClass.cxx:2345` |
| It is a collection **of pointers** — unless §5 | `root/core/meta/src/TClass.cxx:2354` |
| It is a collection with no value class | `root/core/meta/src/TClass.cxx:2357` |
| It is a collection of `TString` or `std::string` | `root/core/meta/src/TClass.cxx:2359` |
| It is a collection whose value class cannot be split | `root/core/meta/src/TClass.cxx:2361` |
| It is a collection **of collections** | `root/core/meta/src/TClass.cxx:2362` |
| It has an external streamer or a custom member streamer | `root/core/meta/src/TClass.cxx:2369`, `root/core/meta/src/TClass.cxx:2376` |
| It is empty (`Size() == 1`) | `root/core/meta/src/TClass.cxx:2384` |
| One of its base classes forbids it | `root/core/meta/src/TClass.cxx:2391` |

`TObject` and `TClonesArray` are always splittable
(`root/core/meta/src/TClass.cxx:2339-2340`). `TRef`, `TRefArray`, `TArray`,
`TCollection` and `TTree` forbid it for anything deriving from them
(`root/core/meta/src/TClass.cxx:2267-2276`).

This list is the *writer's*, and it is recorded here because it explains files
rather than constrains them. A file that splits `std::string` is not invalid; it
is simply not one ROOT 6.40.04 would write.

## 3. Names

The names of the branches inside a split object are not a description of the
class. They depend on a string the user passed to `TTree::Branch`, and the same
class produces two different sets of names depending on its last character.

### 3.1 A trailing dot changes every name below

`ttree/split-naming` writes the same class twice into the same tree, once as
`Branch("plain", ...)` and once as `Branch("dotted.", ...)`. Everything about
the two halves is identical — the class, the split level, the data, and every
one of `fID`, `fType`, `fStreamerType`, `fClassName` and `fSplitLevel` on the
corresponding branches. The names are not:

| | `Branch("plain", …)` | `Branch("dotted.", …)` |
|---|---|---|
| the split node | `plain` | `dotted.` |
| the base-class node | `NBase` | `dotted.NBase` |
| a member of the base | `fB` | `dotted.NBase.fB` |
| a member of the class | `fI` | `dotted.fI` |
| **`fParentName` of `fB`** | **`NEv`** | **`NBase`** |

The last row is the one that costs a reader. `fParentName` on the same member of
the same class is the top class in one half and the declaring class in the
other. ROOT's source flags both divergences in a comment above the code that
causes them (`root/tree/tree/src/TBranchElement.cxx:476-480`): *"this is very
annoying. It is also very annoying that the naming conventions for the
sub-branch names are different as well."*

### 3.2 Base classes are elided, class-typed members are not

The mechanism behind the first four rows is one branch in `TBranchElement`'s
constructor. When a base-class node's name equals the base class's own name —
which happens exactly when the parent name has no trailing dot and no internal
dot — the name is **elided** and its members are unrolled under the grandparent's
name (`root/tree/tree/src/TBranchElement.cxx:481-493`). That is why `fB` in the
plain half is just `fB`.

A class-typed member is never elided: in `ttree/split-nested` the member `fDet`
has no trailing dot anywhere in play, and its sub-branches are still `fDet.fNo`
and `fDet.fHits`.

So a dot in a branch name means one of at least three things, and a reader
cannot tell which from the name alone.

### 3.3 The count-branch convention

Titles, unlike names, do carry one relationship reliably. A collection or
`TClonesArray` count branch's title is its name with an underscore appended, and
every member branch of its content has a title of the form `member[count_]`:

```
fDet.fHits          title  fDet.fHits_
fDet.fHits.fId      title  fId[fDet.fHits_]
fDet.fHits.fE       title  fE[fDet.fHits_]
```

`BuildTitle` builds both: it strips a trailing dot, appends `_`
(`root/tree/tree/src/TBranchElement.cxx:1186-1189`), and formats the bracketed
form for each member (`root/tree/tree/src/TBranchElement.cxx:1218`).

This is the human-readable form of the relationship. The machine-readable form
is the member branch's `fBranchCount`
([TBranchElement §6](TBranchElement.md#6-fbranchcount-is-a-back-reference-and-fbranchcount2-is-never-set)),
and a reader should use that: it is a byte offset rather than a string to parse,
and it does not have to be reconciled with §3.1.

### 3.4 Structure comes from `fBranches`

Given §3.1 to §3.3: the nesting in `fBranches` is the only description of the
object hierarchy that is always right. Names are advisory, and a reader that
reconstructs the hierarchy by splitting names on `.` will get the plain half of
`ttree/split-naming` wrong.

## 4. `fSplitLevel`

### 4.1 It packs two things

`fSplitLevel % 100` is the writer's remaining split budget at that node.
`fSplitLevel - (fSplitLevel % 100)` — the hundreds component — is the
`TTree::kSplitCollectionOfPointers` flag of §5
(`root/tree/tree/src/TBranchElement.cxx:6279-6280`;
`root/tree/tree/inc/TTree.h:310`).

### 4.2 It is not a depth counter

The budget is decremented on some paths, passed through unchanged on others, and
set to literal 0 on others still — `root/tree/tree/src/TBranchElement.cxx:6403-6408`
zeroes it for the sub-branches of a collection or `TClonesArray` and for any
element that cannot be split, and `root/tree/tree/src/TBranchElement.cxx:6444-6449`
does the same in a second place. `ttree/split-nested` shows the result:

| Branch | Depth | `fSplitLevel` |
|---|---|---|
| `nt` | 0 | 99 |
| `fDet` | 1 | 98 |
| `fRun` | 1 | 98 |
| `fDet.fHits` | 2 | 97 |
| `fDet.fNo` | 2 | **0** |
| `fDet.fHits.fId` | 3 | **0** |

Two branches at the same depth carry 97 and 0. A reader must not infer depth,
structure, or whether a branch has children from this field.

### 4.3 What it is needed for

One thing: the `>= 100` test that selects the pointer-collection read procedures
(`root/tree/tree/src/TBranchElement.cxx:5779`). That is §5.

## 5. Collections of pointers, and `TBranchSTL`

A `std::vector<T*>` is refused by `CanSplit` (§2). The exception is an explicit
request: adding `TTree::kSplitCollectionOfPointers` — 100 — to the split level
passed to `TTree::Branch` makes the writer split it anyway
(`root/tree/tree/src/TBranchElement.cxx:969-970`). The hundreds component then
rides down to every sub-branch instead of being decremented, which is what leaves
the members of the content at `fSplitLevel` 100 and selects
`ReadLeavesCollectionSplitVectorPtrMember` or
`ReadLeavesCollectionSplitPtrMember`
([TBranchElement §8](TBranchElement.md#8-the-read-procedure-is-selected-by-four-fields-not-one)).

**No file in either corpus does this.** Across the 178 files of `PLAN.md` §9.8
and §9.9, written by ROOT releases from 4.00 to 6.36, the maximum `fSplitLevel`
is 99. `ttree/split-ptr-collection` is the only evidence this specification has,
and everything in this section rests on it plus the source.

The arrangement it produces:

```
pc                      TBranchElement   fSplitLevel 199   fType 0, fID -2
  fHits                 TBranchSTL       fSplitLevel 198
    fHits.PHit          TBranchElement   fSplitLevel 197   fType 4, fID -1
      fHits.PHit.fId    TBranchElement   fSplitLevel 100   fType 41
      fHits.PHit.fE     TBranchElement   fSplitLevel 100   fType 41
```

Three things in it are new.

**`TBranchSTL` is reachable, and this is how.** It is the only branch class in
ROOT that appears in no file of either corpus, and this is the arrangement that
produces one. It is a `TBranch` with **five** added persistent members
(`root/tree/tree/inc/TBranchSTL.h:71-77`) and no `fType`, so nothing in
[TBranchElement](TBranchElement.md) applies to it:

| Member | Type | Value in `ttree/split-ptr-collection` |
|---|---|---|
| `fContName` | counted string | `vector<PHit*>` — the **collection's** class name, at offset 3455 |
| `fClassName` | counted string | `PEv`, the parent class, at 3469 |
| `fClassVersion` | `i32` | 1, at 3473 — a four-byte `Int_t`, not the `Version_t` of `TBranchElement` class version 10 |
| `fClCheckSum` | `u32` | `0x9838e2f7`, the collection class's checksum, at 3477 |
| `fID` | `i32` | 0, at 3481 |

`fContName` is the one that matters most to a reader: it names the collection type,
which is otherwise only inferable from the child branches.

**It has baskets full of data and no leaf at all.** `fLeaves` has `nobjects` 0
while `fWriteBasket` is 1. This is the one shape in a tree where an empty leaf
list does not mean an empty branch, and it is why
[TLeaf §10](TLeaf.md#10-invariants) scopes its invariants 5 to 7 to branches
that have leaves.

**The collection branch beneath it inserts the value class into the name.**
`fHits.PHit`, not `fHits`. Its `fID` is −1, so by the rule of
[TBranchElement §5](TBranchElement.md#5-fclassname-names-the-class-fid-indexes)
its `fClassName` is its own type — `vector<PHit*>` — and its `fClassVersion` 6
is the collection's version, not `PHit`'s.

### 5.1 What a `TBranchSTL`'s own basket holds

A `TBranchSTL` has no leaf, so nothing in [TLeaf](TLeaf.md) describes its entries.
Each entry is **one framed `TIndArray`**, written by `WriteClassBuffer` and read by
`ReadClassBuffer` (`root/tree/tree/src/TBranchSTL.cxx:645-648`), and `TIndArray` has
no `ClassDef` — so it is a **foreign** class and its version word is 0 followed by a
checksum ([Buffer §4](../02-serialization/Buffer.md#4-a-version-word-of-0-has-two-different-meanings)):

```
byteCount:u32   version:i16 = 0   checksum:u32   fElems:u32   flag:u8   fElems × u8
```

`fElems` is the number of indices and `fArr` is a counted pointer `[fElems]` of
`UChar_t`, so it carries the one-byte presence flag of
[Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer)
and is absent when `fElems` is 0.

> Demonstrated by `ttree/split-ptr-collection`, whose `fHits` basket at offset 328
> has a 68-byte payload holding three entries and then the offset array: at 397 a
> byte count of 13, version `00 00`, checksum `0xbe3836fa`, `fElems` 2, flag `01`
> and two index bytes; at 414 the same with `fElems` 0 and flag `00`, 11 bytes; at
> 429 `fElems` 1, 12 bytes. The offset array at 445 is `4, 69, 86, 101, 0` — the
> first element is `fKeylen` and the fourth is the never-written extra slot of
> [TBasket §5.1](TBasket.md#51-three-things-to-get-right).

**`tools/check_invariants.py` reports these baskets as `SKIPPED` rather than
decoding them**, so they are in the denominator of its `ENTRIES` line and named.
They are decodable from the file — the layout above is all that is needed — so this
is a gap in the checker, not in the specification. No file in either corpus contains
a `TBranchSTL`, so the corpus figure is unaffected.

## 6. The unsplit fallback

A high split level is a request, not a guarantee. When `CanSplit` refuses (§2),
`TTree::Branch` writes a single branch holding whole serialised objects, and the
split level it was given is still recorded in `fSplitLevel`.

The file says which happened, and not through `fSplitLevel`:

| On disk | Meaning |
|---|---|
| `fType` −1 | unsplit; the class had a custom streamer when written |
| `fType` 0 with `fID` −1 | unsplit; the default streamer was used |
| `fType` 0 with `fID` −2 | split; the columns are in `fBranches` |

So the test for "is this branch split" is `fID == -2` — or equivalently, and more
robustly, whether `fBranches` is non-empty. `fSplitLevel` answers a different
question and §4.2 shows it answering it badly.

## 7. Reading

Splitting adds nothing to the record-reading procedure. It changes what a reader
does with the result:

1. Walk `fBranches` recursively. The nesting is the structure (§3.4).
2. At each branch, read `fType` and `fID`
   ([TBranchElement §3](TBranchElement.md#3-ftype-and-fid)). `fType` 1 and 2 are
   interior nodes with nothing to read; descend.
3. A branch with `fBranches` non-empty *and* baskets of its own is a count
   branch (`fType` 3 or 4) or a `TBranchSTL`. Read its entries as well as
   descending.
4. For a member of a split container, resolve `fBranchCount` to find how many
   values this entry holds (§3.3).
5. Reassembling the columns into an object is the reader's own problem, and this
   specification deliberately says nothing about it: which member of which class
   a column is, is `fClassName` plus `fID`, and that is all the file records.

## 8. Invariants

1. A branch with `fID` −2 has a non-empty `fBranches`.
2. A branch with `fType` 1 or 2 has a non-empty `fBranches`: an interior node
   with no children would describe nothing.
3. A count branch's title is its name with a trailing dot removed and `_`
   appended.
4. Every member branch of a split container — `fType` 31 or 41 — has a title of
   the form `member[count_]`, where `count_` is its `fBranchCount` branch's
   title.
5. A `TBranchSTL` has no leaf.

## 9. Errata

| # | Claim | Correction |
|---|---|---|
| 1 | `root/io/doc/TFile/README.md:256-257`: "Each TBranch contains an array of zero or more leaves (class TLeaf), each corresponding to a basic variable type or a class object that has not been split" | The leaf array does not describe the branch's data in two of the shapes here. On a count branch its single entry is a back-reference rather than a leaf, so a reader that does not resolve it sees none ([TBranchElement §4](TBranchElement.md#4-two-ftype-values-have-no-leaf-and-two-reach-theirs-only-by-reference)); and a `TBranchSTL` has an empty leaf array *and* baskets full of data (§5) |
| 2 | That `fSplitLevel` records how deeply a branch is split — the natural reading of `root/io/doc/TFile/ttree.md:54`, "Branch split level" | It records the writer's remaining budget. It is 0 on branches that were split and on branches that were not, and differs between branches at the same depth (§4.2) |

## 10. Reference files

| Case | What it covers |
|---|---|
| `ttree/split-object` | The simplest split: `fType` 0 with `fID` −2, `fType` 1, and the elided base-class name of §3.2 |
| `ttree/split-naming` | §3.1 in full — the same class under a plain and a dotted branch name, 26 assertions, twelve of which are the pairs that differ and do not |
| `ttree/split-counter` | A counted array: `fBranchCount` on an `fType` 0 branch, `fMaximum` on the counter, and the `member[count]` title in its oldest form |
| `ttree/split-nested` | Three levels, `fType` 2, an `fType` 4 count branch with `fType` 41 members, the `name_`/`[name_]` convention, and the `fSplitLevel` table of §4.2 |
| `ttree/split-unsplit` | §6 in one file: the same class split and unsplit side by side, with `fID` −2 against −1 as the only field that separates them |
| `ttree/split-clones` | The `TClonesArray` half of the same shapes: `fType` 3 and 31, and a `TObject` base flattened into columns rather than becoming an `fType` 1 node |
| `ttree/split-stl-toplevel` | A collection as the branch itself: three branches, no split node above them, and the shortest arrangement ROOT produces |
| `ttree/split-ptr-collection` | All of §5: `fSplitLevel` above 100, a `TBranchSTL`, and an `fType` 4 branch with `fID` −1 |

Not covered: the `ReadLeavesCollectionSplitPtrMember` half of §5, which needs a
non-`vector` collection of pointers. `TBranchClones` used to be on this list as
having "no known way to produce one"; there is one —
[TBranchElement §13](TBranchElement.md#13-tbranchclones-and-the-only-api-that-makes-one),
and `ttree/branch-clones` is the fixture.

Invariants 1 to 4 are confirmed by corrupting a copy of `ttree/split-nested` and
checking that the intended invariant is what rejects it. Invariant 5 cannot be:
giving a `TBranchSTL` a leaf means lengthening its `fLeaves`, which breaks the
record's byte count first. It is exercised rather than corruption-tested — the
one `TBranchSTL` in the fixtures runs through it.

The same limit applies to the obvious corruptions for invariants 1 and 2 —
emptying an `fBranches` array desynchronises the framing — so those are tested
from the other side instead, by marking a childless branch as a split node.
