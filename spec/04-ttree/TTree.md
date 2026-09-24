# `TTree`

A `TTree` record is the root of a tree's index. Like a branch, it holds no data:
it holds the list of top-level [branches](TBranch.md), a flat list of references
to every leaf, and the count of entries and how they are grouped into clusters.

Prerequisites: [Streamer-driven reading](../02-serialization/StreamerDriven.md),
[TBranch](TBranch.md).

## 1. Finding the trees in a file

A tree is a record of its own, named by the tree's name, and its class name is
**not necessarily `TTree`**. `TNtuple`, `TNtupleD` and `TChain` all derive from
`TTree`, and a record written for one of them has that class name in its key,
with the complete `TTree` layout nested inside as a base class.

A reader therefore cannot find the trees by comparing a key's class name with
`TTree`. It has to follow the base-class chain in the file's own streamer infos:
a record is a tree when `TTree` appears, transitively, among the `TStreamerBase`
elements of its class.

> Demonstrated by `ttree/ntuple`. The key at 477 names the class `TNtuple`; the
> object data opens with `TNtuple`'s byte count and class version **2**
> (`40 00 06 ca 00 02`), and `TTree`'s own byte count and version 20 follow
> directly, six bytes in (`40 00 06 c0 00 14`). A reader that
> dispatched on the key's name and then applied `TTree`'s streamer info directly
> would be six bytes off.

`TNtuple` adds one persistent member, `fNvar`, after the `TTree`
base (`root/tree/tree/inc/TNtuple.h:31-32`, `root/tree/tree/inc/TNtuple.h:61`);
`fArgs` is transient and is rebuilt from it
(`root/tree/tree/src/TNtuple.cxx:262-267`).

### 1.1 The streamer is a version guard

`TTree::Streamer` exists (`root/tree/tree/src/TTree.cxx:9813`) but above class
version 4 it calls `ReadClassBuffer` and then only updates transient members
(`root/tree/tree/src/TTree.cxx:9827-9862`). The streamer-driven algorithm
therefore reads a tree correctly with no special knowledge, for every version a
reader is likely to meet. The hand-coded legacy path is for version 4 and below
(`root/tree/tree/src/TTree.cxx:9864-9896`), which is ROOT 3.x and older.
`TBranch`, by contrast, needs version knowledge up to 9; see
[§13](#13-class-versions).

> **What a reader must reconstruct.** After `ReadClassBuffer`,
> `TTree::Streamer` sets the owning tree on every branch and sub-branch
> (`root/tree/tree/src/TTree.cxx:9834`, and
> `root/tree/tree/src/TTree.cxx:9773-9792` for the recursion), on every friend
> element and on the tree index. None of those back-pointers is on disk. It also
> overwrites two persistent members it has just read: `fEstimate`, forced up to
> 10⁶ if it is at most 10⁴ (`root/tree/tree/src/TTree.cxx:9845-9847`), and
> `fMaxClusterRange`, set from `fNClusterRange`
> (`root/tree/tree/src/TTree.cxx:9849-9853`). The latter implies that the two
> cluster arrays on disk hold exactly `fNClusterRange` values, with no slack.

## 2. Layout

Class version 20 (`root/tree/tree/inc/TTree.h:757`). In streamer-info order:

| # | Member | Code | Type | Meaning |
|---|---|---|---|---|
| 1 | `TNamed` | 67 | base | `fName` is the tree name, `fTitle` its title |
| 2 | `TAttLine` | 0 | base | drawing attributes; no I/O meaning |
| 3 | `TAttFill` | 0 | base | " |
| 4 | `TAttMarker` | 0 | base | " |
| 5 | `fEntries` | 16 | `Long64_t` | entry count, maintained by `TTree::Fill` (§3) |
| 6 | `fTotBytes` | 16 | `Long64_t` | uncompressed size of every basket of every branch (§4) |
| 7 | `fZipBytes` | 16 | `Long64_t` | on-disk size of the same |
| 8 | `fSavedBytes` | 16 | `Long64_t` | `fZipBytes` as of the last `AutoSave`; `fTotBytes` before 5.27/02 (§6.3) |
| 9 | `fFlushedBytes` | 16 | `Long64_t` | `fZipBytes` as of the last automatic flush (§6.3) |
| 10 | `fWeight` | 8 | `Double_t` | a weight for `TTree::Draw`; no I/O meaning |
| 11 | `fTimerInterval` | 3 | `Int_t` | " |
| 12 | `fScanField` | 3 | `Int_t` | " |
| 13 | `fUpdate` | 3 | `Int_t` | " |
| 14 | `fDefaultEntryOffsetLen` | 3 | `Int_t` | the default for a *new* split branch's `fEntryOffsetLen` (§7) |
| 15 | `fNClusterRange` | 6 | `Int_t` | length of the two arrays below; `kCounter` (§6) |
| 16 | `fMaxEntries` | 16 | `Long64_t` | circular-buffer limit; write-time only (§9) |
| 17 | `fMaxEntryLoop` | 16 | `Long64_t` | no I/O meaning |
| 18 | `fMaxVirtualSize` | 16 | `Long64_t` | " |
| 19 | `fAutoSave` | 16 | `Long64_t` | the `AutoSave` watermark, rewritten by the writer (§6.3) |
| 20 | `fAutoFlush` | 16 | `Long64_t` | the flush watermark, and the size of the last cluster range (§6) |
| 21 | `fEstimate` | 16 | `Long64_t` | a `TTree::Draw` buffer length; no I/O meaning |
| 22 | `fClusterRangeEnd` | 56 | `Long64_t*` | `[fNClusterRange]`, counted pointer (§6.1) |
| 23 | `fClusterSize` | 56 | `Long64_t*` | `[fNClusterRange]`, counted pointer (§6.1) |
| 24 | `fIOFeatures` | 62 | `ROOT::TIOFeatures` | a version-0 class, as in [TBranch §8](TBranch.md#8-fiofeatures-is-a-version-0-class) |
| 25 | `fBranches` | 61 | `TObjArray` | the top-level branches |
| 26 | `fLeaves` | 61 | `TObjArray` | **references** to every leaf of every branch (§5) |
| 27 | `fAliases` | 64 | `TList*` | expression aliases, usually null (§8) |
| 28 | `fIndexValues` | 62 | `TArrayD` | the old-style index, which ROOT discards (§8.1) |
| 29 | `fIndex` | 62 | `TArrayI` | " |
| 30 | `fTreeIndex` | 64 | `TVirtualIndex*` | usually null (§8) |
| 31 | `fFriends` | 64 | `TList*` | " |
| 32 | `fUserInfo` | 64 | `TList*` | " |
| 33 | `fBranchRef` | 64 | `TBranchRef*` | " |

Codes 56 are `kOffsetP + kLong64`
([Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer)):
a one-byte *is present* flag followed by `fNClusterRange` values. Unlike
`TBranch`'s three arrays, these two are usually absent: `fNClusterRange` is 0 on
most trees, and the flag byte is then 0 (§6.1).

Codes 62 on members 28 and 29 are `kAny`, and `TArray`'s streamer is hand-written:
each is four bytes of `fN` and then that many values, with no frame and no version
word ([TArray §3.2](../03-classes/TArray.md#32-as-a-member-by-value)).

Nothing else in `TTree.h` reaches the file. Some forty members are marked `//!`,
including `fDirectory`, `fEventList`, `fEntryList`, `fCacheSize`, `fReadEntry`,
`fMaxClusterRange` and `fPlayer` (`root/tree/tree/inc/TTree.h:105-171`).

> Demonstrated by `ttree/tree`, which asserts every member of a two-branch tree
> from the opening byte count to `fBranchRef`.

## 3. `fEntries` is a counter, not a derived quantity

`fEntries` is incremented once per `TTree::Fill`
(`root/tree/tree/src/TTree.cxx:4726`) and set directly by `TTree::SetEntries`
(`root/tree/tree/src/TTree.cxx:9269-9271`). **Nothing keeps it consistent with
the branches.** Filling branches individually with `TBranch::Fill` advances each
branch's own counters and never touches the tree's.

`SetEntries(-1)` recomputes it as the maximum over the top-level branches and,
if they disagree, warns rather than refusing
(`root/tree/tree/src/TTree.cxx:9274-9295`), so ROOT itself allows them to differ.

A reader MUST NOT use the tree's `fEntries` as the entry bound for a branch.
The bounds are per branch, from `fFirstEntry` and `fEntryNumber`
([TBranch §10](TBranch.md#10-reading) step 1). `fEntries` is what
`TTree::GetEntries` returns and what a user-facing entry loop should use, and the
two can differ.

> Found in a file this project did not write: `string-example.root` in the
> foreign corpus of `PLAN.md` §9.8, an LHCb DST written by ROOT 6.30/02. Its
> tree `Refs` has `fEntries` 0, three branches with no entries, and a fourth,
> `Params`, with `fEntries` 2, one basket on disk and 157 bytes of data. A reader
> that trusted the tree's count would report the file as empty. The tree's
> `fTotBytes` is still 157, so §4 holds.

## 4. `fTotBytes` and `fZipBytes` are sums over every branch

Each time a basket is written, the branch adds the basket's sizes to its own
counters and to the tree's (`root/tree/tree/src/TBranch.cxx:606-611`, through
`root/tree/tree/inc/TTree.h:375-376`). The tree's counters are therefore sums
over every branch at every depth, not over the top-level branches: a split
branch's parent contributes nothing of its own, and its children contribute all
of it.

As in [TBranch §4.2](TBranch.md#42-ftotbytes-and-fzipbytes-count-keys), neither is
a payload size: `fZipBytes` sums record `fNbytes` and `fTotBytes` sums
`fObjlen + fKeylen`, so both include the basket keys, and on an uncompressed tree
the two are equal.

> Demonstrated by `ttree/tree`: two branches of 0x49 and 0x51 bytes give
> `fTotBytes = fZipBytes = 154`. Measured over the fixtures and the foreign
> corpus of `PLAN.md` §9.8 (201 tree records, 187 of them readable by this
> specification), the recursive sum is exact on every one, and the top-level sum
> is wrong on the 59 that have split branches.

> **`fBranchRef` counts too, and it is not in `fBranches`.** A tree created with
> `TTree::BranchRef` has a `TBranchRef` in its `fBranchRef` member (§8). It is an
> ordinary branch with baskets of its own, and its bytes are in the tree's
> counters, but a walk over `fBranches` never reaches it, so that sum comes out
> short. `ttree/tree-branchref` has `fTotBytes` 546 against 365 over `fBranches`,
> and the missing 181 are the `TBranchRef`'s.
>
> That branch is also compressed in an otherwise uncompressed file: its
> constructor hard-codes `fCompress = 1` (`root/tree/tree/src/TBranchRef.cxx:62`).
> It is therefore the only branch whose `fZipBytes` can be below its `fTotBytes`
> when nothing else in the file is compressed (124 against 181 in that fixture).

## 5. `fLeaves` holds references, not leaves

Every leaf belongs to a branch, and the tree keeps a flat list of all of them so
that a name lookup does not have to walk the branch hierarchy. The tree does not
own them, as a comment in `TTree`'s destructor states
(`root/tree/tree/src/TTree.cxx:976-977`), and each leaf is added to both lists
when its branch is built (`root/tree/tree/src/TBranch.cxx:429-430`).

On disk this is a `TObjArray` in which **every entry is a four-byte
back-reference** ([Buffer §6.1](../02-serialization/Buffer.md#61-object-references)).
This follows from the member order of §2: `fBranches` is member 25 and `fLeaves`
is member 26, so when `fLeaves` is written every leaf is already in the buffer's
object map. A reader may ignore the array, but it must consume its bytes, and it
must not expect to find leaf objects in it.

> Demonstrated by `ttree/tree`. `fLeaves` is 29 bytes: a `TObjArray` header,
> `nobjects` 2, and two words, 0x1bf and 0x3a4. Those are buffer positions 445 and
> 930, so absolute 867 and 1352 — the two `TLeaf` object slots inside the
> branches.

> Measured over the same 187 trees: none has an object in `fLeaves`, and in
> every one the references resolve to exactly the set of leaves the branches
> hold. In all of them the order is the depth-first order of a walk over
> `fBranches`, but that follows from branch creation order, not from anything
> the format enforces, so it is an observation and not
> [an invariant](#11-invariants).

## 6. Clusters

A **cluster** is a consecutive range of entries whose baskets, across all
branches, were flushed together and therefore lie near each other in the file.
It is the unit ROOT's read cache works in, and the only grouping above the basket
that a file records.

Clusters are not stored as a list. They are stored as a **piecewise-constant
cluster size**: `fClusterRangeEnd[i]` and `fClusterSize[i]` describe the ranges
of entries over which the size was constant, and the final, open-ended range's
size is `fAutoFlush` (`root/tree/tree/src/TTree.cxx:8419-8430`). ROOT stores
range *ends* rather than starts so that the arrays can be empty when
the size never changed (`root/tree/tree/src/TTree.cxx:8447-8449`).

### 6.1 The two arrays

For `0 <= i < fNClusterRange`:

| Array | Value |
|---|---|
| `fClusterRangeEnd[i]` | the **last** entry of range *i*, inclusive |
| `fClusterSize[i]` | the number of entries in each cluster of range *i* |

Range 0 starts at entry 0; range *i* > 0 starts at `fClusterRangeEnd[i-1] + 1`.
There is always one more range than the arrays describe: it starts at
`fClusterRangeEnd[fNClusterRange-1] + 1` — or at 0 when the count is 0 — runs to
`fEntries - 1`, and its cluster size is `fAutoFlush`.

An entry is written into the arrays only when the size *changes*, by
`TTree::MarkEventCluster` (`root/tree/tree/src/TTree.cxx:8465-8499`), which
`SetAutoFlush` calls when the setting changes after flushing has begun
(`root/tree/tree/src/TTree.cxx:8451-8458`). On a tree whose auto-flush setting
was never changed, `fNClusterRange` is 0 and both counted pointers have a clear
is-present flag, so each member is a single zero byte. This is where an ordinary
file first uses that form: `TBranch`'s three arrays always have at least ten
elements and their flag is always 1.

> Demonstrated by both fixtures. In `ttree/tree` the two members are one byte
> each, at 646 and 647, both zero. In `ttree/clusters` the flag is 1 and the
> arrays hold `fClusterRangeEnd = [7, 13]` and `fClusterSize = [4, 3]` with
> `fAutoFlush` 5 and `fEntries` 19 — three ranges: entries 0–7 in clusters of 4,
> 8–13 in clusters of 3, and 14–18 in clusters of 5.

> No tree in the 180-file foreign corpus of `PLAN.md` §9.8 or in `gen/cern/` has
> a non-zero `fNClusterRange` (232 of the former's 233 trees read, and all 30 of
> the latter's), which is why `ttree/clusters` exists. Variable cluster size is
> produced mainly by fast-merging trees with different settings
> (`TTree::ImportClusterRanges`, `root/tree/tree/src/TTree.cxx:6484-6516`), so a
> reader will most likely meet it in a merged production file.

### 6.2 Enumerating clusters

To find the cluster containing entry *e*
(`root/tree/tree/src/TTree.cxx:588-618` and
`root/tree/tree/src/TTree.cxx:678-717`):

1. Let *r* be the number of *i* with `fClusterRangeEnd[i] < e`; equivalently, the
   smallest *r* with `e <= fClusterRangeEnd[r]`, or `fNClusterRange` if there is
   none.
2. `pedestal = 0` if *r* is 0, else `fClusterRangeEnd[r-1] + 1`.
3. `size = fAutoFlush` if `r == fNClusterRange`, else `fClusterSize[r]`.
4. If `size <= 0` the cluster size **is not recorded**; see below.
5. `start = pedestal + ((e - pedestal) / size) * size`, integer division.
6. `end = start + size`, capped at `fClusterRangeEnd[r] + 1` when
   `r < fNClusterRange`, and at `fEntries` in any case. The cluster is
   `[start, end)`.

Step 4 is the common case, not a corner case. `fAutoFlush` stays negative on any
tree that never reached the byte watermark, which includes every tree written
with the default of −30000000 and less than 30 MB of compressed data. Of the 187
trees measured here, 173 have a negative `fAutoFlush`, two have 0 and six have a
positive one; the remaining six are below class version 18 and have no
`fAutoFlush` at all. For all but the six positive ones, **the file does not
record where the cluster boundaries are**, and ROOT falls back to an estimate
computed from the cache size (`root/tree/tree/src/TTree.cxx:639-672`).

A reader that wants real boundaries can take them from a branch's `fBasketEntry`
instead; a reader that wants ROOT's answer has to reproduce the estimate, which
depends on run-time cache settings and is therefore not a property of the file.

> When auto-flush is active, every cluster boundary is also a basket boundary
> in every branch that has data there, because a flush creates both. The
> converse does not hold: a basket that fills up mid-cluster is written early
> unless the tree was given the `kOnlyFlushAtCluster` bit
> (`root/tree/tree/inc/TTree.h:300`). `ttree/clusters` is small enough that the
> two coincide: five clusters and five baskets, with the branch's `fBasketEntry`
> holding 0, 4, 8, 11, 14, 19.

### 6.3 `fAutoFlush` and `fAutoSave` are not what the writer asked for

Both members are watermarks with a sign convention: **positive means a number of
entries, negative means a number of bytes**, and 0 disables the mechanism
(`root/tree/tree/src/TTree.cxx:8536-8548`). The constructor sets `fAutoSave` to
−300000000 and `fAutoFlush` to −30000000 (`root/tree/tree/src/TTree.cxx:785-786`).

On the **first** automatic flush, ROOT rewrites both in terms of entries and
keeps the rewritten values (`root/tree/tree/src/TTree.cxx:4738-4790`):

```
fAutoFlush = fEntries;                       // the entry count at the first flush
if (fAutoSave < 0) fAutoSave = max(fAutoFlush, fEntries * ((-fAutoSave / zipBytes) / fEntries));
else               fAutoSave = fAutoFlush * (fAutoSave / fAutoFlush);
```

with `fTotBytes`, and failing that the length of a trial `TTree` buffer, standing
in for `zipBytes` when it is 0.

A negative `fAutoFlush` on disk therefore means "the watermark was never reached, and no
cluster size is recorded"; a positive one is a cluster size in entries, whether or
not the writer ever expressed one that way. The same applies to `fAutoSave`, whose
stored value can be an arbitrary-looking number derived from the compression ratio
at that moment.

`fFlushedBytes` and `fSavedBytes` are `fZipBytes` as of the last flush and the last
`AutoSave` respectively (`root/tree/tree/src/TTree.cxx:4816`,
`root/tree/tree/src/TTree.cxx:1542`). `fFlushedBytes == 0` is the condition ROOT
tests for "nothing has been flushed yet"
(`root/tree/tree/src/TTree.cxx:4739-4742`), and it lets a reader tell a rewritten
`fAutoFlush` from an original one.

Before 5.27/02, `AutoSave` stored `fTotBytes` in `fSavedBytes` instead
(`tree/src/TTree.cxx` at tag `v4-04-02`, line 747; `tree/tree/src/TTree.cxx` at
tag `v5-26-00`, line 1003), and its trigger compared uncompressed bytes,
`fTotBytes-fSavedBytes > fAutoSave` (line 2540 at tag `v4-04-02`). Root commit
`fa3ad228d72` (2010-03-08) made it `fZipBytes`. Its first tag is `v5-27-02`, and
it was never backported to 5.26. The `TTree` class version does not mark the
change, because version 18 spans it, so only the release in the file header tells
a reader which meaning a file uses. The reading path of class version 4 and below
still sets `fSavedBytes = fTotBytes` in memory
(`root/tree/tree/src/TTree.cxx:9884`).

> Measured over the 634 `TTree` records of the fixtures, both corpora and
> `root/roottest/`: 28 records written before 5.27/02 have a non-zero
> `fSavedBytes`, all at most `fTotBytes` and 19 equal to it. 26 of them exceed
> `fZipBytes`, in twelve roottest files from 4.03/02 to 5.26/00, among them
> `RefTest.root` (`Events`: `fTotBytes` 72075, `fZipBytes` 6915, `fSavedBytes`
> 72075), `EDM.root` and `cmsursula.root`. The 41 non-zero values written from
> 5.27/02 on are all at most `fZipBytes`.

> `ttree/tree` has both defaults intact and `fFlushedBytes` 0. `ttree/clusters`
> has `fAutoFlush` 5, `fAutoSave` 3703700 and `fFlushedBytes` 401: the
> generator asked for `SetAutoFlush(4)`, then 3, then 5, and never set
> `fAutoSave`. In the foreign corpus, `uproot-mc10events.root` shows the same
> rewriting on a production file: `fAutoFlush` 6844 and `fAutoSave` 6759, values
> no caller would have chosen.

## 7. `fDefaultEntryOffsetLen` applies to split branches only

`fDefaultEntryOffsetLen` is the value a new branch's `fEntryOffsetLen`
([TBranch §6](TBranch.md#6-fentryoffsetlen)) is initialised from. It is 1000 at
construction (`root/tree/tree/src/TTree.cxx:779`) and floored at 10 by its setter
(`root/tree/tree/src/TTree.cxx:9197-9202`).

It is used in one place only, `TBranchElement`'s constructor
(`root/tree/tree/src/TBranchElement.cxx:363`). A plain `TBranch` built from a
leaflist ignores it and hardcodes 1000 instead
(`root/tree/tree/src/TBranch.cxx:420-427`). On an unsplit tree the member
therefore describes nothing that happened. Like `fEntryOffsetLen`, it applies to
branches not yet created rather than to anything already on disk.

## 8. The five object pointers, and the index ROOT throws away

Members 27 and 30 to 33 are object pointers, each a
[slot](../02-serialization/Buffer.md#6-object-slots) that is four zero bytes when
null:

| Member | Holds |
|---|---|
| `fAliases` | a `TList` of `TNamed`, name = alias, title = expression |
| `fTreeIndex` | a `TVirtualIndex`, in practice a `TTreeIndex` |
| `fFriends` | a `TList` of `TFriendElement` |
| `fUserInfo` | a `TList` of anything the writer attached |
| `fBranchRef` | a `TBranchRef`, the branch supporting a `TRefTable` |

None of them affects how the entries of this tree are decoded, and they are
rarely set. Over the fixtures, the foreign corpus of `PLAN.md` §9.8 and
`gen/cern/` (37, 232 and 30 readable trees), only five trees have one: the three
fixtures made for them (`fBranchRef` in `ttree/tree-branchref`, `fFriends` in
`ttree/tree-friend`, `fTreeIndex` in `ttree/tree-index`) and both trees of
`alice_ESDs.root`, which set `fUserInfo`. No tree has a non-null `fAliases`.
Their contents are left to `Auxiliary.md`. Here it is enough that the slots
exist, sit between `fLeaves` and the end of the record, and must be consumed.

### 8.1 `fIndexValues` and `fIndex`

These two are the pre-`TTreeIndex` sort index: parallel arrays of sort keys and
entry numbers, held by value as a `TArrayD` and a `TArrayI`. They are the only
persistent members that ROOT **reads and then destroys**: if `fIndex` is
non-empty, `TTree::Streamer` prints `Old style index in this tree is deleted.
Rebuild the index via TTree::BuildIndex` and clears both arrays
(`root/tree/tree/src/TTree.cxx:9840-9844`).

A reader should treat them the same way: parse them, because they are in the byte
stream, and then ignore them. An empty pair is four zero bytes each.

## 9. Members with no bearing on reading data

`fWeight`, `fTimerInterval`, `fScanField`, `fUpdate`, `fMaxEntryLoop`,
`fMaxVirtualSize` and `fEstimate` are presentation and resource settings. They are
persistent, they must be consumed, and nothing about the entries depends on them.
A reader that ignores their values is conforming; one that skips their bytes is
not.

`fMaxEntries` is the entry limit for a *circular* tree — one written with
`TTree::SetCircular`, which drops old entries as new ones arrive. The dropping
happens at write time, renumbering entries down from `fMaxEntries`
(`root/tree/tree/src/TTree.cxx:6527-6549`), so a circular tree on disk looks like
any other and `fMaxEntries` has no effect on reading. Its default is 10¹²
(`root/tree/tree/src/TTree.cxx:920-921`), which is also what `SetCircular(0)`
restores together with clearing `kCircular`
(`root/tree/tree/src/TTree.cxx:9149-9153`).

`TObject::fBits` in the `TNamed` base carries `TTree`'s own status bits
(`root/tree/tree/inc/TTree.h:294-306`). Two matter to a reader: `kCircular`,
bit 12, and `kEntriesReshuffled`, bit 19, which marks a tree whose entries are a
permutation of another's and which ROOT refuses to befriend
(`root/tree/tree/src/TTree.cxx:1268-1284`). Neither changes the layout.

## 10. Reading

To read a tree:

1. Find its record — a key whose class derives from `TTree` (§1) — and decode the
   object data with the streamer-driven algorithm. On a derived class, the `TTree`
   members are inside a base-class frame.
2. `fBranches` gives the top-level branches; each branch's own `fBranches` gives
   its children, recursively.
3. `fLeaves` gives nothing new: it is one back-reference per leaf already read in
   step 2 (§5). Consume it and move on.
4. The tree's entry count is `fEntries`, but the entry range of any individual
   branch is that branch's own (§3). Read an entry with
   [TBranch §10](TBranch.md#10-reading).
5. If cluster boundaries are wanted, derive them per §6.2. A tree with a
   negative `fAutoFlush` does not record them.

## 11. Invariants

1. `fEntries`, `fTotBytes` and `fZipBytes` are not negative, and `fTotBytes` and
   `fZipBytes` are the sums of the like-named members over every branch of the
   tree at every depth: `fBranches` recursively, **plus `fBranchRef` when the
   tree has one**, which is not in `fBranches` (§4).
2. `0 <= fFlushedBytes <= fZipBytes` and `0 <= fSavedBytes <= fTotBytes`. In a
   file whose header names 5.27/02 or later, also `fSavedBytes <= fZipBytes`
   (§6.3).
3. `fNClusterRange >= 0`; `fClusterRangeEnd` and `fClusterSize` each hold exactly
   `fNClusterRange` values; and each one's *is present* flag is set if and only if
   `fNClusterRange` is non-zero (§6.1).
4. `fClusterRangeEnd` is non-decreasing, its last element is below `fEntries`, and
   every `fClusterSize` element is at least 0.
5. `fLeaves` holds one entry per leaf of every branch of the tree, every entry is
   a back-reference, and the references resolve to exactly that set of leaves
   (§5).
6. `fIndexValues` and `fIndex` have the same length (§8.1).
7. `fEstimate` is positive and `fDefaultEntryOffsetLen`, where the class version
   has it, is at least 10 (§7).

There is deliberately no invariant relating `fEntries` to any branch's entry
count: §3 gives a file written by ROOT 6.30 where they disagree by design.
There is none on `fClusterRangeEnd` being strictly increasing: two `SetAutoFlush`
calls with no `Fill` between them close two ranges at the same entry, leaving an
empty range that no entry falls in
(`root/tree/tree/src/TTree.cxx:8486-8499`). Nor is there one on `fClusterSize`
being positive: fast-merging writes 0 for a range whose source `fAutoFlush` was
negative (`root/tree/tree/src/TTree.cxx:6504-6508`). That is a real range whose
cluster size the file does not record, and §6.2 step 4 covers it.

Invariant 6 is not corruption-testable in isolation: a `TArray`'s length is
redundant with the enclosing byte count, so changing one `fN` overruns the record
and [Streamer-driven reading §10](../02-serialization/StreamerDriven.md#10-invariants)
rejects the file first.

## 12. Errata

Against `root/io/doc/TFile/ttree.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | `ttree.md:9-29` gives the `TTree` member list at class version 6 | Version **20**, with thirteen members added since: `fFlushedBytes`, `fWeight`, `fDefaultEntryOffsetLen`, `fNClusterRange`, `fMaxEntries`, `fAutoFlush`, `fClusterRangeEnd`, `fClusterSize`, `fIOFeatures`, `fAliases`, `fTreeIndex`, `fUserInfo`, `fBranchRef` (§2) |
| 2 | `ttree.md:14-17`: `fEntries`, `fTotBytes`, `fZipBytes`, `fSavedBytes` are `Stat_t`, type 8 | All four are `Long64_t`, code 16, since class version 13. A reader following the old table reads them as IEEE doubles |
| 3 | `ttree.md:21-24`: `fMaxEntryLoop`, `fMaxVirtualSize`, `fAutoSave`, `fEstimate` are `Int_t` | All four are `Long64_t` since version 13 |
| 4 | — | Nothing says the record's class need not be `TTree`, so a reader that matches the key's class name misses every `TNtuple` in the file (§1) |
| 5 | `ttree.md:15`: `fTotBytes` is "Total number of bytes in all branches before compression" | It is a sum over every branch at every depth, and it counts basket keys as well as payloads, so it is larger than the data (§4). "All branches" also includes `fBranchRef`, which is not in `fBranches` and which a walk over the branch tree therefore misses |
| 6 | — | Nothing says `fLeaves` contains back-references rather than leaves. A reader that expects objects there fails on every tree (§5) |
| 7 | `ttree.md:23`: `fAutoSave` is "Autosave tree when fAutoSave bytes produced" | The sign selects bytes or entries, and the stored value is rewritten by the writer on the first flush, so it is often neither what the caller asked for nor a byte count (§6.3) |
| 8 | — | Clusters do not appear at all: not the two arrays, not the inclusive range ends, and not the fact that a negative `fAutoFlush` means the boundaries are unrecorded (§6) |
| 9 | — | Nothing says `fNClusterRange` being 0 makes the two counted pointers *absent*, one zero byte each rather than a flag and an array (§6.1) |
| 10 | — | Nothing says ROOT deletes `fIndex`/`fIndexValues` on read, with a warning (§8.1) |
| 11 | `ttree.md:27-29` lists `fIndexValues`, `fIndex` and `fFriends` consecutively | The three are separated in the current layout by `fAliases`, and `fTreeIndex` sits between `fIndex` and `fFriends`; the order in the old table cannot be used to locate them (§2) |
| 12 | *This document, until 2026-09-23*: ROOT 4.00/00 wrote `TTree` class version 11 | Version 10. Version 11 is first at tag `v4-00-02` (§13) |
| 13 | *This document, until 2026-09-23*: `fSavedBytes <= fZipBytes` (§11 invariant 2) | Only from 5.27/02. Before, `AutoSave` stored `fTotBytes`, so `fSavedBytes` is bounded by `fTotBytes` alone; twelve ROOT-written roottest files break the old bound (§6.3) |

## 13. Class versions

Measured from the streamer infos in the 180-file foreign corpus of `PLAN.md` §9.8,
cross-checked against the submodule's history:

| Version | Difference | First release |
|---|---|---|
| 10 | `fAliases` added | v3-05-06 |
| 11 | `fUserInfo` added | v4-00-02 |
| 12 | `fTreeIndex` added | v4-00-06 |
| 13 | the >2-billion-entry patch: `fEntries`, `fTotBytes`, `fZipBytes`, `fSavedBytes` `Stat_t` → `Long64_t`; `fMaxEntryLoop`, `fMaxVirtualSize`, `fAutoSave`, `fEstimate` `Int_t` → `Long64_t` | v4-01-02 |
| 14 | `fMaxEntries` added | v4-01-02 |
| 15 | `fBranchRef` added | v4-01-02 |
| 16 | the read-cache patch; no new persistent member | v5-12-00 |
| 17 | `fDefaultEntryOffsetLen` added | v5-25-02 |
| 18 | `fAutoFlush` and `fFlushedBytes` added | v5-25-04 |
| 19 | `fNClusterRange`, `fClusterRangeEnd`, `fClusterSize` added | v5-30-00 |
| 20 | `fIOFeatures` added; current | v6-12-02 |

Every one of those is read by `ReadClassBuffer` from the file's own streamer info,
so a reader that follows
[Streamer-driven reading](../02-serialization/StreamerDriven.md) needs no version
knowledge for any of them. The hand-coded legacy path is for version **4 and
below** (`root/tree/tree/src/TTree.cxx:9864-9896`), which this document does not
give; nothing in the corpus is below 5.

> **A version word of 5 does not prove the writer was ROOT.** Two files in the
> corpus, `uproot-from-geant4.root` and `uproot-issue-250.root`, have `TTree`
> records at class version 5 with a matching streamer info, and headers claiming
> ROOT 4.00/00. ROOT 4.00/00 wrote version 10, so no ROOT release produced that
> combination: g4tools, Geant4's own ROOT writer, wrote them. The layout is still
> readable, because the file's streamer info describes it.

## 14. Reference files

| Case | Exercises |
|---|---|
| `ttree/tree` | The whole member table of class version 20, the absent cluster arrays, the two by-value `TArray`s, the five null pointers, and `fLeaves` as back-references |
| `ttree/clusters` | Variable cluster size: `fNClusterRange` 2, both counted pointers present, the open-ended range described by `fAutoFlush`, and a rewritten `fAutoSave` |
| `ttree/ntuple` | A tree whose record is class `TNtuple`, with `TTree` as a base class and `fNvar` after it |
| `ttree/branch` | A tree whose `fTotBytes` sums three basket records of one branch |

A non-null `fBranchRef`, `fFriends` and `fTreeIndex` are covered by
`ttree/tree-branchref`, `ttree/tree-friend` and `ttree/tree-index`, which
`Auxiliary.md` describes. No fixture covers a non-null `fAliases` or `fUserInfo`,
a non-empty `fIndex`, a tree whose `fEntries` disagrees with its branches, or a
`TTree` at class version 4 or below. The foreign corpus of `PLAN.md` §9.8 has a
file for the disagreeing `fEntries`, `gen/cern/`'s `alice_ESDs.root` has a
non-null `fUserInfo`, and neither has any of the others.
