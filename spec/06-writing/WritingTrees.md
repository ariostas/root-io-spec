# Writing trees

A `TTree` of flat branches: the basket records, the branch and leaf descriptions
inside the tree record, and the fields that have to agree with one another. At the
current class versions — `TTree` 20, `TBranch` 13, `TLeaf` 2, `TBasket` 3.

Prerequisites: [Writing a file](WritingFiles.md),
[Writing an object](WritingObjects.md). The reading side is
[The tree record](../04-ttree/TTree.md), [Branches](../04-ttree/TBranch.md),
[Leaves](../04-ttree/TLeaf.md), [TBasket](../04-ttree/TBasket.md) and
[Reading entries](../04-ttree/ReadingEntries.md).

Scope: **flat branches** — a scalar, a fixed-size array, or an array counted by
another branch — with as many baskets each as the writer chooses to flush (§7).
Producing a split `TBranchElement` is out of scope
([the layer's index](index.md#4-what-is-not-specified)).

## 1. The shape, and how far it is checked

A tree is not one record. It is:

- **one record per basket**, each a key in its own right, written *before* the
  tree record because the tree stores their offsets;
- **one record for the tree**, holding the branches, and inside them the leaves,
  as nested objects.

There are two worked examples, and each reproduces a ROOT-written file **byte for
byte in every record** — every basket and the tree, keys included, once the
wall-clock timestamp is masked. `tools/test_write.py` asserts both.

| This project's | ROOT's | What it adds |
|---|---|---|
| `data/written/tree.root` | `data/ttree/basket.root` | two branches, one of them counted, three entries, **one basket each** |
| `data/written/cluster.root` | `data/ttree/clusters.root` | one branch, nineteen entries, **five baskets** and two closed cluster ranges (§7) |

The only part of either pair that differs is the `StreamerInfo` record, by one
entry (§8.1).

Those comparisons are strict in a way the histogram one is not: a branch stores its
baskets' **offsets**, so a single byte's difference anywhere earlier in the file
changes the tree record. Each pair of file names is chosen to be the same total
length for that reason.

## 2. Order of operations

1. Accumulate each branch's entries into its basket buffer, recording an entry
   offset per entry if the branch needs one (§5.2).
2. Whenever the writer chooses, **flush**: close the open buffer of every branch
   into a basket and start a new one (§7). A tree with one basket per branch is
   the case where this happens exactly once, at the end.
3. Place each basket as a record (§5) and note its `fSeekKey`, `fNbytes` and
   `fObjlen`.
4. Build the tree record (§3, §4) with those three numbers **per basket**.
5. Write the `StreamerInfo` record, the key list — which contains the tree's key
   and **not** the baskets' (§6) — the free list and the header
   ([Writing a file §3](WritingFiles.md#3-the-procedure)).

ROOT's own order is the same and for the same reason: `TTree::Write` flushes every
basket and then writes the tree (`root/tree/tree/src/TTree.cxx:10012`). A basket
that is *not* flushed is streamed inside the tree record instead, which is the
embedded-basket case [TBranch §5](../04-ttree/TBranch.md#5-fbaskets-is-written-and-is-usually-empty) describes;
a writer has no reason to produce one.

## 3. The tree record

`TTree` at class version 20, framed like any object. In streamed order, with the
values a three-entry tree needs:

| Member | Type | Value | Kind |
|---|---|---|---|
| `TNamed` | framed | the tree's name and title; `fBits` carries `kMustCleanup` | free |
| `TAttLine`, `TAttFill`, `TAttMarker` | framed | 602/1/1, 0/1001, 1/1/1.0f | free |
| `fEntries` | `i64` | the entry count. **The only upper bound `TTree::GetEntry` checks** (`root/tree/tree/src/TTree.cxx:5725`) | **fixed** |
| `fTotBytes` | `i64` | Σ over **every basket** of `fKeylen + fObjlen` | derived |
| `fZipBytes` | `i64` | Σ of every basket's `fNbytes` | derived |
| `fSavedBytes` | `i64` | 0 unless the writer imitates `AutoSave`; §7.5 | free |
| `fFlushedBytes` | `i64` | 0 when every basket was flushed at the end, and `fZipBytes` as of the last *automatic* flush otherwise. **A reader uses the difference**: 0 means no cluster boundary was ever recorded ([TTree §6.1](../04-ttree/TTree.md#61-the-two-arrays)) | free, and §7.5 |
| `fWeight` | `f64` | **1.0**, unless a weight is meant: `Draw` multiplies every entry by it (`root/tree/treeplayer/src/TSelectorDraw.cxx:929`) | **fixed in practice** |
| `fTimerInterval`, `fUpdate` | `i32` | 0 | free |
| `fScanField` | `i32` | 25 — rows before `Scan` prompts | free |
| `fDefaultEntryOffsetLen` | `i32` | 1000; only affects branches created later | free |
| `fNClusterRange` | `i32` | the number of **closed** cluster ranges, 0 when the cluster size never changed; the two counted arrays below have exactly this many elements each (§7.4) | derived |
| `fMaxEntries`, `fMaxEntryLoop` | `i64` | 1000000000000 | free |
| `fMaxVirtualSize` | `i64` | **0 or above.** Negative diverts basket reading onto a whole-cluster path that walks `fBasketEntry` unbounded (`root/tree/tree/src/TBranch.cxx:1246-1247`) | free, with constraints — any non-negative value |
| `fAutoSave` | `i64` | -300000000 as constructed; ROOT rewrites it at the first automatic flush (§7.5). Nothing reads it back | free |
| `fAutoFlush` | `i64` | -30000000 as constructed. **A positive value is the size of the last, open-ended cluster range** and is read as such (§7.4); a negative one is a byte watermark and says nothing about clusters | free, with constraints — §7.4 |
| `fEstimate` | `i64` | 1000000. `TTree::Streamer` raises anything at or below 10000 to 1000000 on read (`root/tree/tree/src/TTree.cxx:9845-9847`), so the field is free in effect | free |
| `fClusterRangeEnd`, `fClusterSize` | counted pointers | `fNClusterRange` values each behind a `0x01` flag byte — or one `0x00` byte and nothing, when the count is 0 (§7.4) | derived |
| `fIOFeatures` | framed | §3.2 | **fixed** |
| `fBranches` | `TObjArray` **member object** | the branches, §4 | — |
| `fLeaves` | `TObjArray` member object | **references** to the leaves inside `fBranches`, §3.1 | **fixed** |
| `fAliases` | pointer slot | null | free |
| `fIndexValues` | `TArrayD` | empty: `fN` of 0 | free |
| `fIndex` | `TArrayI` | empty | free |
| `fTreeIndex`, `fFriends`, `fUserInfo`, `fBranchRef` | pointer slots | null | free |

**`fBranches` and `fLeaves` are member objects, not pointers** — `fType` 61 — so
each is a bare framed `TObjArray` with **no class record**. Emitting the pointer
form adds 18 bytes and desynchronises the reader
([Writing an object §1](WritingObjects.md#1-the-two-framings)). `fBranches` is
also the one `TObjArray` in the record whose `fBits` carries `kIsOwner`
(`0x4000`); nothing reads it.

### 3.1 `fLeaves` holds references, not copies

Each entry of `fLeaves` is a four-byte **object reference** to a leaf already
written inside `fBranches`
([Buffer framing §6.1](../02-serialization/Buffer.md#61-object-references)) — the
map position of that object's byte-count word, plus 2. So the order is a
constraint on the writer: every leaf must be written, inside its branch, before
`fLeaves` names it. `TTree::GetLeaf` iterates this array
(`root/tree/tree/src/TTree.cxx:6222`), which is how `Draw` and `Scan` find a leaf
by name.

### 3.2 `fIOFeatures` is the one foreign class a tree contains

`ROOT::TIOFeatures` has no `ClassDef` (`root/tree/tree/inc/ROOT/TIOFeatures.hxx:100`),
so its version word is **0** and a checksum follows
([Writing an object §2](WritingObjects.md#2-a-version-word-of-0-and-when-a-writer-must-emit-one)).
Eleven bytes, exactly:

```
40 00 00 07   00 00   1a a1 2f 10   00
byte count 7  ver 0   checksum      fIOBits
```

The checksum is the class's and is constant. `TBranch` carries one too.

**Its streamer info must record `fClassVersion` 1**, not the 0 in the version word;
§7 lists it that way, and
[Writing an object §2](WritingObjects.md#2-a-version-word-of-0-and-when-a-writer-must-emit-one)
says why getting it wrong costs every reader four bytes per tree and per branch.

## 4. A branch

`TBranch` at class version 13, as a pointer slot inside `fBranches`. In streamed
order:

| Member | Type | Value | Kind |
|---|---|---|---|
| `TNamed` | framed | `fName` the branch name; **`fTitle` the leaflist**, e.g. `n/I` or `a[n]/F`. `fBits` is `0x00400000` in a ROOT-written file | free, but see §4.2 |
| `TAttFill` | framed | 0, 1001 | free |
| `fCompress` | `i32` | the file's compression settings, or 0 | free |
| `fBasketSize` | `i32` | 32000 by default; the value **after** any rewriting at flush (§7.3) | free |
| `fEntryOffsetLen` | `i32` | **non-zero iff the baskets carry an offset array** (`root/tree/tree/src/TBasket.cxx:691`); the value itself is not used, and it is the one the **last** flush left (§5.2) | **fixed** (zero or not) |
| `fWriteBasket` | `i32` | the number of baskets on disk — one past the last real index | **fixed** |
| `fEntryNumber` | `i64` | `fFirstEntry + fEntries`; the per-branch upper bound on reading (`root/tree/tree/src/TBranch.cxx:1364-1366`) | **fixed** |
| `fIOFeatures` | framed | as §3.2 | **fixed** |
| `fOffset` | `i32` | 0 | free |
| `fMaxBaskets` | `i32` | the length of the three counted arrays; ROOT writes `max(fWriteBasket + 1, 10)` | derived |
| `fSplitLevel` | `i32` | 0 | free |
| `fEntries` | `i64` | the branch's entry count | **fixed** |
| `fFirstEntry` | `i64` | 0 for a tree written in one pass | **fixed** |
| `fTotBytes` | `i64` | Σ over this branch's baskets of `fKeylen + fObjlen` | derived |
| `fZipBytes` | `i64` | Σ of their `fNbytes` | derived |
| `fBranches` | `TObjArray` member | empty for a flat branch | **fixed** |
| `fLeaves` | `TObjArray` member | one leaf, §4.3 | **fixed** |
| `fBaskets` | `TObjArray` member | `fWriteBasket + 1` slots, **all null**, §4.1 | derived — the slot count from `fWriteBasket`, the contents always null |
| `fBasketBytes` | counted pointer, `i32` | element *i* is basket *i*'s `fNbytes`, then zeros to `fMaxBaskets` | derived — from the basket records |
| `fBasketEntry` | counted pointer, `i64` | element *i* is the first entry number of basket *i*, element `fWriteBasket` is the total entry count, and the rest is zero. **One element longer than there are baskets** | derived — §9 invariants 2 and 3 |
| `fBasketSeek` | counted pointer, `i64` | element *i* is basket *i*'s record offset, then zeros | derived — from where each basket was written |
| `fFileName` | counted string | empty — non-empty means the baskets are in another file | **fixed** |

**The three counted pointers have no length of their own**: each is one flag byte
and then exactly `fMaxBaskets` values
([Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer)).
`fMaxBaskets` is therefore load-bearing for parsing the record, not just
bookkeeping.

### 4.1 `fBaskets` is a `TObjArray` of nulls

Not empty: `fWriteBasket + 1` entries — six for a five-basket branch — every one
of them a null pointer.
`TBranch::Streamer` removes from the array every basket that is already on disk
before streaming (`root/tree/tree/src/TBranch.cxx:3195-3205`), but the array's
`fLast` still remembers how many slots it had, and `TObjArray::Streamer` writes
`fLast + 1` entries. So a one-basket branch writes a count of 2 and eight zero
bytes.

### 4.2 `fBasketSeek[0]` and the last `fBasketEntry` are the two that matter

Reading an entry is a binary search in `fBasketEntry` over `fWriteBasket + 1`
elements (`root/tree/tree/src/TBranch.cxx:1371`), then a read at
`fBasketSeek[fReadBasket]`, and **the one consistency check ROOT makes** is that
the basket found there reports the same `fSeekKey`
(`root/tree/tree/src/TBranch.cxx:1268`):

```
Error("GetBasket","File: %s at byte:%lld, branch:%s, entry:%lld, badread=%d, …")
```

Everything else fails silently:

- **`fBasketEntry[0]` must equal `fFirstEntry`.** It is the only value whose being
  wrong produces a message — `In the branch %s, no basket contains the entry %lld`
  (`root/tree/tree/src/TBranch.cxx:1374`) — because the binary search returns
  negative only when the entry is below the first element.
- **A terminator that is too small** makes high entries search to
  `fReadBasket == fWriteBasket`, where `GetBasketImpl` returns null with no
  message at all (`root/tree/tree/src/TBranch.cxx:1237`) and `GetEntry` returns
  -1.
- **A terminator that is too large** is not detected: the read runs past the
  basket's real extent and `ReadFastArray` returns without touching the
  destination, leaving stale values (`root/io/io/inc/TBufferFile.h:273-281`).
- **`fWriteBasket >= fMaxBaskets`** is silently repaired on read, by synthesising
  a terminator from `fEntries` (`root/tree/tree/src/TBranch.cxx:3010-3016`) —
  which is wrong for any branch whose `fFirstEntry` is not 0. Do not rely on it.

### 4.3 The leaf

`TLeafI`, `TLeafF`, `TLeafD`, … at class version **1**, each wrapping a `TLeaf`
base at version **2**:

| Member | Type | Value |
|---|---|---|
| `TNamed` | framed | `fName` the leaf name **without** dimensions; `fTitle` **with** them — `n`, `a[n]`, `v[3]` |
| `fLen` | `i32` | the fixed multiplicity: 1 for a scalar **and for a counted array**, `N` for `x[N]` |
| `fLenType` | `i32` | the width of one value: 4 for `TLeafI`/`TLeafF`, 8 for `TLeafD`, 1 for `TLeafC` |
| `fOffset` | `i32` | 0 for a single-leaf branch; otherwise the leaf's cumulative byte offset inside the entry (`root/tree/tree/src/TBranch.cxx:419`) |
| `fIsRange` | `u8` | **1 on a counter leaf**, 0 otherwise |
| `fIsUnsigned` | `u8` | 1 only for the lowercase type letters |
| `fLeafCount` | pointer slot | null, or an **object reference** to the counter leaf |
| `fMinimum`, `fMaximum` | the leaf's own type | 0, except `fMaximum` on a counter leaf — §4.4 |

**`fTitle` is load-bearing for `Draw` and `Scan` and nothing else.**
`TTreeFormula` parses the dimensions out of it
(`root/tree/treeplayer/src/TTreeFormula.cxx:600-641`): a fixed array whose title
lacks `[3]` reads as a scalar there, and a counted array whose title lacks `[n]`
loses its variable dimension. `GetEntry` never looks at it — it uses `fLen` and
`fLeafCount`.

**`fLeafCount` is an object reference, not a name.** It is not re-derived from the
title on read; the title parser runs only in ROOT's constructor
(`root/tree/tree/src/TLeaf.cxx:249`). So the counter leaf must be written earlier
in the same record — which for a counted branch means its **counter branch must
come first in `fBranches`**. That is a write-side ordering constraint with no
reading-side counterpart.

### 4.4 A counter leaf's `fMaximum` is a hard requirement

It must be at least the largest count anywhere in the file, because ROOT sizes the
value buffer from it — `(fLeafCount->GetMaximum() + 1) * fLen`
(`root/tree/tree/src/TLeaf.cxx:444-447`) — and then **clamps** the read:

```
printf("ERROR leaf:%s, len=%d and max=%d\n", …); len = fLeafCount->GetMaximum();
```

(`root/tree/tree/src/TLeafI.cxx:174-180`, and the same in every sibling.) That is
a raw `printf`, not an `Error`, and the clamp desynchronises the buffer for the
rest of the entry. So a writer has to know the maximum count **before** it writes
the tree record, which means a full pass over the data.

`fIsRange` is what makes the field meaningful: ROOT sets it on the counter as a
side effect of building the counted leaf (`root/tree/tree/src/TLeaf.cxx:309`), and
without it `GetLeafCountValues` returns nothing (`:367`).

## 5. A basket

A record of its own, and the most unusual key in the format.

| Field | Value |
|---|---|
| `fClassName` | `TBasket` |
| `fName` | the **branch's** name (`root/tree/tree/src/TTree.cxx:3772-3778`) |
| `fTitle` | the **tree's** name |
| key `fVersion` | **1004**. `TBasket`'s constructor adds 1000 unconditionally (`root/tree/tree/src/TBasket.cxx:71`), so `fSeekKey` and `fSeekPdir` are 8 bytes wide **in a file of any size** |
| `fCycle` | the basket number (`root/tree/tree/src/TBasket.cxx:1293`). Nothing reads it |
| `fKeylen` | 34 + the three counted strings + **19**, because the basket's own header sits inside the key. 19 assumes `fNevBufSize` is written positive — see §5.1 |
| `fObjlen` | the entry data, plus the offset array if there is one |
| `fNbytes` | `fKeylen` + the payload as stored |

The 19 bytes at the end of the key are the basket header:

| Bytes | Field | Value |
|---|---|---|
| `i16` | version | 3 |
| `i32` | `fBufferSize` | the branch's `fBasketSize` **when this basket was closed**, which is not the same for every basket of a branch (§7.3) |
| `i32` | `fNevBufSize` | §5.1 |
| `i32` | `fNevBuf` | the entry count in this basket |
| `i32` | `fLast` | `fKeylen +` the data length, measured from the **start of the record** |
| `u8` | flag | **0** in a basket written as its own record |

**A writer MUST write `fNevBufSize` positive**, which keeps the header at 19 bytes.
A *negative* `fNevBufSize` is a marker: ROOT then writes one extra `u8` of
`fIOBits` after it (`root/tree/tree/src/TBasket.cxx:997-1000`), making the header 20
and shifting `fKeylen` — see
[TBasket §2.2](../04-ttree/TBasket.md#22-the-sign-of-fnevbufsize-carries-fiobits).
Nothing in this procedure needs `fIOBits` on a basket, so nothing here needs the
20-byte form; a writer that wants `kGenerateOffsetMap` is outside §4 of
[the layer's index](index.md#4-what-is-not-specified), because it must also omit
the offset array and set the flag to 80 rather than 0.

### 5.1 `fNevBufSize` means two different things

It is the fixed per-entry byte size when the branch has no offset array, and the
offset array's capacity when it has one — the field is overloaded, and ROOT's own
header says so (`root/tree/tree/inc/TBasket.h:63`). Get the first case wrong and
every entry after the first is read at the wrong stride, with no message: the read
position is `fKeylen + (entry - first) * fNevBufSize`
(`root/tree/tree/src/TBranch.cxx:1747`).

### 5.2 The offset array

Written only when the branch's `fEntryOffsetLen` is non-zero, immediately after
`fLast`:

```
count:i32 = fNevBuf + 1   then   fNevBuf + 1 values of i32
```

The first `fNevBuf` values are each entry's offset **from the start of the
record**, so the first is `fKeylen`. The extra element is never read: it is
whatever ROOT's array happened to hold, which is 0
(`root/tree/tree/src/TBasket.cxx:95`, written at `:1269`).

> An **embedded** basket — one streamed inside the tree record — writes the array
> differently, with a count of `fNevBuf` and no extra element, and its flag byte
> is 1 or 2 rather than 0 (`root/tree/tree/src/TBasket.cxx:1140-1155`). ROOT
> checks that count on read and zombifies the basket if it disagrees (`:1057`).
> A writer that flushes every basket never meets this.

The branch's `fEntryOffsetLen` is then **adjusted** at flush, in two guarded
branches rather than one (`root/tree/tree/src/TBranch.cxx:3225-3231`):

| Condition | New `fEntryOffsetLen` |
|---|---|
| `fEntryOffsetLen > 10` and `4 × fNevBuf < fEntryOffsetLen` | `4 × fNevBuf`, or **10** when `fNevBuf < 3` |
| `fEntryOffsetLen` non-zero and `fNevBuf > fEntryOffsetLen` | `2 × fNevBuf` — it **grows** |
| otherwise | unchanged |

Nothing reads the value beyond "is it zero", so this matters only for matching ROOT
byte for byte. The default 1000 with three entries takes the first branch and
becomes 12, which is what `data/written/tree.root` carries.

## 6. A basket is not in the key list

`TKey(TDirectory*)`, the constructor `TBasket` uses, never calls `AppendKey`
(`root/io/io/src/TKey.cxx:109-117`), and `TBasket`'s destructor says why: *"A
basket is never in that list"* (`root/tree/tree/src/TBasket.cxx:118-121`). So the
directory's key list holds the `TTree` key alone, and a basket is reachable only
through `fBasketSeek`.

Its `fSeekPdir` is still the directory's `fSeekDir`, and nothing checks it.

## 7. More than one basket per branch

A **flush** closes the open buffer of every branch into a basket and starts a new
one. When to do it is the writer's choice — ROOT's own rule is a watermark, and
that rule is policy ([index §3](index.md#3-what-is-specified)) — but what a flush
*produces* is not: it lengthens the branch's three counted arrays, it may close a
cluster range, and it sets `fFlushedBytes`, which is the one field that tells a
reader any boundary was recorded at all.

Everything in §3 to §6 already holds per basket. What follows is what changes when
there is more than one.

### 7.1 What one flush changes

| Field | On the flush of basket *i* |
|---|---|
| a new basket record | written before the tree record, with `fCycle` = *i* and `fNevBuf` = the entries it holds |
| `fWriteBasket` | becomes *i* + 1: the count of baskets on disk |
| `fBasketBytes[i]`, `fBasketSeek[i]` | the new record's `fNbytes` and offset |
| `fBasketEntry[i]` | the first entry number in that basket — so `fBasketEntry[0]` is `fFirstEntry` |
| `fBasketEntry[i+1]` | the entry count so far, which the next flush overwrites and the last one leaves as the **terminator** (`root/tree/tree/src/TBranch.cxx:3274`) |
| `fMaxBaskets` | the length of all three arrays: `max(fWriteBasket + 1, 10)` (§7.2) |
| `fEntryOffsetLen` | rewritten from the entries this basket held, if the branch has an offset array (§5.2) |
| `fTotBytes`, `fZipBytes` | on the branch *and* on the tree, increased by this basket's contribution |

The order of the basket records is the writer's, but their **offsets** must match
`fBasketSeek`, so the tree record cannot be built until every basket is placed
(§2). Writing all of round 0 before any of round 1 is what ROOT's `FlushBaskets`
produces, and it puts a cluster's baskets next to each other on disk, which is the
whole point of a cluster.

### 7.2 `fMaxBaskets` is not the number of baskets

It is `max(fWriteBasket + 1, 10)`: `TBranch::Streamer` sets it to `fWriteBasket + 1`
for the duration of the write and then floors it at 10
(`root/tree/tree/src/TBranch.cxx:3190-3193`). Since the three counted pointers carry
exactly `fMaxBaskets` values each and have no length of their own, **a five-basket
branch writes ten elements per array**, five of them meaningful in `fBasketBytes`
and `fBasketSeek`, six in `fBasketEntry`, and the rest zero.

Getting the count wrong does not corrupt one field, it desynchronises everything
after it: the three arrays are read at the wrong length, and `fFileName` ends up
being read out of the middle of `fBasketSeek`. Lowering it by one in
`data/written/cluster.root` is caught as
`TBranch v13 consumed 323 bytes, byte count says 487` — a length complaint, not a
wrong value, which is what a bad `fMaxBaskets` looks like from the reader's side.

> A reader that finds `fWriteBasket >= fMaxBaskets` repairs the array silently
> (§4.2), which is worth knowing only so that a writer does not lean on it.

### 7.3 `fBasketSize` is rewritten at the first flush, and the baskets disagree

ROOT calls `TTree::OptimizeBaskets` the first time `Fill` reaches a watermark
(`root/tree/tree/src/TTree.cxx:4763`), which recomputes every branch's
`fBasketSize` from the bytes written so far, with a floor of **512**
(`root/tree/tree/src/TTree.cxx:7270`, set at `:7331`). A basket records the value
in force when it was closed, so in `data/ttree/clusters.root` basket 0 carries
`fBufferSize` 100 — the size the branch was created with — and baskets 1 to 4
carry 512, as does the branch's own `fBasketSize`.

**Nothing reads either field**: a basket's buffer is sized from `fLast` and
`fNbytes`. It is specified here because a writer comparing its bytes with ROOT's
will see the change and needs to know it is not a rule.

### 7.4 Cluster ranges

A **cluster** is a consecutive range of entries whose baskets, across all branches,
were flushed together and therefore lie near each other in the file — the unit
ROOT's read cache works in ([TTree §6](../04-ttree/TTree.md#6-clusters)). A tree
does not store a list of them. It stores a piecewise-constant cluster *size*, and
records a boundary only where that size **changes**:

| Field | Value |
|---|---|
| `fClusterRangeEnd[i]` | the **last** entry of range *i*, inclusive — `fEntries - 1` at the moment the range closed |
| `fClusterSize[i]` | the number of entries per cluster *within* range *i*, which is the watermark that was in force |
| `fAutoFlush` | the size of the final, **open-ended** range, which is in neither array |
| `fNClusterRange` | how many ranges closed |

Range 0 starts at entry 0 and range *i* > 0 at `fClusterRangeEnd[i-1] + 1`, so the
array of *ends* is enough. The rule for closing one is
`TTree::MarkEventCluster` (`root/tree/tree/src/TTree.cxx:8466-8499`), which
`SetAutoFlush` reaches under two conditions worth restating, because a writer that
imitates ROOT must reproduce both or its ranges will not line up with its baskets:

- **only after something has been flushed** — ROOT's test is `fFlushedBytes`, not
  the entry count (`root/tree/tree/src/TTree.cxx:8452`), so changing the watermark
  before the first flush changes nothing but the watermark;
- **the size recorded is the old one**, because `fAutoFlush` is assigned after the
  range is closed (`:8455-8457`).

Once a range is closed, the next boundary is measured from the start of the current
range and not from entry 0: ROOT's own flush test becomes
`(fEntries - (fClusterRangeEnd[fNClusterRange - 1] + 1)) % fAutoFlush == 0`
(`root/tree/tree/src/TTree.cxx:4799-4804`).

`data/written/cluster.root` is the worked example. Nineteen entries, flushed at 4,
8, 11, 14 and 19, with the watermark 4, then 3, then 5:

| Range | Entries | Cluster size | Baskets |
|---|---|---|---|
| 0 | 0–7 | 4 — `fClusterSize[0]`, ending at `fClusterRangeEnd[0]` = 7 | 0 and 1, four entries each |
| 1 | 8–13 | 3 — `fClusterSize[1]`, ending at `fClusterRangeEnd[1]` = 13 | 2 and 3, three entries each |
| 2 | 14–18 | 5 — `fAutoFlush`, recorded nowhere else | 4, five entries |

With one basket per cluster, `fBasketEntry` is `[0, 4, 8, 11, 14, 19, 0, 0, 0, 0]`
and every cluster boundary is a basket boundary. **The converse does not hold** and
a reader must not assume it: a basket that fills up mid-cluster is written early
([TTree §6.2](../04-ttree/TTree.md#62-enumerating-clusters)).

> **A writer is free to record no ranges at all**, and `data/written/tree.root` is
> that case: `fNClusterRange` 0 with a negative `fAutoFlush` says "no cluster size
> is recorded", and ROOT falls back to an estimate
> ([TTree §6.2](../04-ttree/TTree.md#62-enumerating-clusters)). Recording ranges
> that do not line up with the baskets is **legal and useless**: nothing checks the
> two against each other, ROOT itself produces the mismatch whenever `SetAutoFlush`
> is called mid-cluster, and the only cost is that the cache reads a "cluster"
> whose baskets are not where it expected. Recording the boundaries a writer
> actually flushed at is the whole value of the fields.

### 7.5 `fFlushedBytes`, `fSavedBytes` and the rewriting of `fAutoSave`

Three fields no reader needs in order to decode an entry. Two of them are read for
something else, and the third is read by nothing at all — which is worth knowing in
both directions.

- **`fFlushedBytes`** is `fZipBytes` as of the last *automatic* flush
  (`root/tree/tree/src/TTree.cxx:4816`). The flush `TTree::Write` does at the end
  leaves it alone, so **0 is meaningful**: it is exactly the condition ROOT tests
  for "nothing has been flushed yet" (`:4739-4742`), and a reader uses it to tell a
  rewritten `fAutoFlush` from an original one
  ([TTree §6.3](../04-ttree/TTree.md#63-fautoflush-and-fautosave-are-not-what-the-writer-asked-for)).
- **`fSavedBytes`** is `fZipBytes` as of the last `AutoSave`
  (`root/tree/tree/src/TTree.cxx:1542`), which rewrites the tree record mid-file.
  **Nothing reads it back** at the current class version — `TTree::Streamer`
  overwrites it with `fTotBytes`, and only on the pre-version-5 path
  (`root/tree/tree/src/TTree.cxx:9884`) — so a writer that produces its file in one
  pass puts 0 there and loses nothing.
- **`fAutoSave`** is rewritten at that same first flush into a multiple of
  `fAutoFlush` (`root/tree/tree/src/TTree.cxx:4770-4789`), which is why
  `data/ttree/clusters.root` carries **3703700** when nothing asked for it:
  `4 * ((300000000 / 81) / 4)`, from the constructor's -300000000 and the 81 bytes
  the file then held. `data/written/cluster.root` passes that value in as an input,
  because reproducing ROOT's arithmetic is not a requirement on a writer and
  matching its bytes is what the case is for.

## 8. The streamer infos

Eighteen, for a two-branch tree:

```
TTree  TNamed  TObject  TAttLine  TAttFill  TAttMarker  ROOT::TIOFeatures
TBranch  TLeafI  TLeaf  TLeafF  TList  TSeqCollection  TCollection  TString
TBranchRef  TRefTable  TObjArray
```

Three of them are there for reasons a writer would not guess:

- **`TBranchRef` and `TRefTable`**, because `TTree::fBranchRef` is a **null**
  pointer and a null still forces its class's info to be written — and
  `TRefTable` then drags in `TObjArray` the same way.
- **`TBasket` is absent**, although every basket in the file is one. Its streamer
  is hand-written, so nothing marks it
  ([Writing an object §7.2](WritingObjects.md#72-which-classes-need-an-info)) —
  which makes it the cleanest proof in the format that ROOT reads a class the file
  does not describe.

[Element lists](ElementLists.md) publishes all eighteen, member by member, with
the checksum beside each. A writer that emits them in the order above produces a
record **byte-identical** to ROOT's up to the one entry below
(`tools/test_write.py`).

### 8.1 ROOT appends two rules that a new file cannot use

ROOT's record has a nineteenth entry: a `TList` named `listOfRules` holding two
I/O customization rules
([Schema evolution](../02-serialization/SchemaEvolution.md)):

```
type=read sourceClass="TTree" version="[-16]" target="fDefaultEntryOffsetLen" …
type=read sourceClass="TTree" version="[-18]" target="fNClusterRange" …
```

Both apply to `TTree` versions at or below 18. A file written at version 20 can
never trigger them, so this writer omits the entry — and that is the **only**
difference between `data/written/tree.root` and `data/ttree/basket.root`. The
record's `TList` header therefore differs in two fields, its byte count and 18
entries against 19, and every byte after them is the same.

That equality is recent: until `tools/element_lists.py` compared an element's
**subclass tail** against ROOT's, `TRefTable::fProcessGUIDs` carried the wrong
`fCtype` here, and the record differed from ROOT's in that one field. The tail is in
no checksum and in no byte count, which is why nothing had noticed
([Element lists §11](ElementLists.md#11-errata)).

## 9. Invariants

1. `fEntries` on the tree equals `fEntries` on every branch (for a tree written in
   one pass), and `fEntryNumber == fFirstEntry + fEntries` on each branch.
2. `fBasketEntry[0] == fFirstEntry`, `fBasketEntry[fWriteBasket] == fEntryNumber`,
   and the array is strictly increasing in between.
3. `fBasketSeek[i]` points at a record whose key reports the same `fSeekKey`, and
   `fBasketBytes[i]` equals that key's `fNbytes`.
4. `fMaxBaskets >= fWriteBasket + 1`, and the three counted arrays each hold
   exactly `fMaxBaskets` values.
5. A branch's `fEntryOffsetLen` is non-zero **iff** its baskets carry an offset
   array.
6. In a basket, `fLast == fKeylen +` the data length, and the offset array's first
   element is `fKeylen` — **when the array is stored as offsets**, which is the
   only form this procedure writes. Under `kGenerateOffsetMap` ROOT stores deltas
   with a leading 0 instead (`root/tree/tree/src/TBasket.cxx:1263-1267`), so the
   claim is conditioned on `fIOBits == 0` (§5).
7. A leaf with a non-null `fLeafCount` names a leaf written earlier in the same
   record, and that leaf's `fIsRange` is set and its `fMaximum` is at least every
   count in the file.
8. The directory's key list does not contain a `TBasket` key.
9. `fMaxVirtualSize >= 0` and `fWeight` is the weight `Draw` should apply.
10. `fClusterRangeEnd` and `fClusterSize` hold exactly `fNClusterRange` values
    each, and each one's is-present flag is set **iff** the count is non-zero.
11. `0 <= fFlushedBytes <= fZipBytes`, and the same for `fSavedBytes`.
12. Each basket's `fNevBuf` equals `fBasketEntry[i+1] - fBasketEntry[i]`, so a
    branch's baskets partition its entries and none of them is empty.

1 to 6, 8 and 10 to 12 are checked for the written files by
`tools/check_write.py` through `tools/rootfile.py` — 10 and 11 as
[TTree invariants 3 and 2](../04-ttree/TTree.md#11-invariants), 12 as
[TBranch invariant 6](../04-ttree/TBranch.md#11-invariants) — and the entry
decoding of [Reading entries](../04-ttree/ReadingEntries.md) runs over them as
well: every basket of every written tree is decoded and its byte spans checked
like any ROOT-written fixture's.

**Two things a reader must tolerate and a writer should not produce.** The reading
side deliberately has no invariant that `fClusterRangeEnd` is *strictly* increasing
or that `fClusterSize` is positive ([TTree §11](../04-ttree/TTree.md#11-invariants)),
because ROOT produces both shapes: two `SetAutoFlush` calls with no `Fill` between
them close two ranges at the same entry, and fast-merging writes a cluster size of
**0** for a range whose source watermark was negative
(`root/tree/tree/src/TTree.cxx:6504-6508`). Neither carries information — an empty
range contains no entry, and a size of 0 means "not recorded" — so a writer has
nothing to gain by emitting either.

## 10. Class versions

Every class a flat tree writes, with the version a writer emits. Checked against
`ClassDef` in the pinned submodule by `tools/check_versions.py`.

| Class | Version | Cite |
|---|---|---|
| `TTree` | 20 | `root/tree/tree/inc/TTree.h:757` |
| `TBranch` | 13 | `root/tree/tree/inc/TBranch.h:304` |
| `TLeaf` | 2 | `root/tree/tree/inc/TLeaf.h:171` |
| `TLeafI` | 1 | `root/tree/tree/inc/TLeafI.h:59` |
| `TLeafF` | 1 | `root/tree/tree/inc/TLeafF.h:54` |
| `TLeafD` | 1 | `root/tree/tree/inc/TLeafD.h:54` |
| `TLeafC` | 1 | `root/tree/tree/inc/TLeafC.h:57` |
| `TBasket` | 3 | `root/tree/tree/inc/TBasket.h:156` |
| `TObjArray` | 3 | `root/core/cont/inc/TObjArray.h:105` |
| `TBranchRef` | 1 | `root/tree/tree/inc/TBranchRef.h:59` |
| `TRefTable` | 3 | `root/core/cont/inc/TRefTable.h:93` |

`ROOT::TIOFeatures` is the exception: it has no `ClassDef` at all, which is why
its version word is 0 and a checksum (§3.2).

## 11. Reference files

| File | What it is |
|---|---|
| `data/written/tree.root` | this project's: `n/I` and `a[n]/F`, three entries, one basket each. Every record byte-identical to ROOT's |
| `data/ttree/basket.root` | ROOT's own, the comparison target |
| `data/written/cluster.root` | this project's: `x/I`, nineteen entries, **five baskets** and two closed cluster ranges. Every record byte-identical to ROOT's |
| `data/ttree/clusters.root` | ROOT's own, the comparison target for §7 |
| `data/ttree/branch.root`, `data/ttree/leaf-forms.root` | the reading side's branch and leaf variety |
