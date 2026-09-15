# `TBasket`

A basket holds the data of one branch for a range of entries. It is where the
actual contents of a `TTree` live, and it is the worst-documented structure in
ROOT I/O: it has **no streamer info at all**, its streamer is entirely
hand-written, its own fields sit inside the key rather than the payload, and its
flag byte means different things depending on how it was written.

Prerequisites: [Records and keys](../01-container/Record.md),
[Compression](../01-container/Compression.md).

> This document specifies the basket *record*. How a reader finds basket *i* of a
> branch, and which entries it holds, is `04-ttree/TBranch.md`.

## 1. A basket is a key with extra fields

`TBasket` derives from `TKey`, and its `Streamer` calls `TKey::Streamer` first and
then writes more (`root/tree/tree/src/TBasket.cxx:987-988`). Because `fKeylen` is
measured *after* the key has been written
([Record §3.7](../01-container/Record.md#37-a-key-can-be-longer-than-its-strings)),
those extra fields land inside the key:

```
| ---------------- fKeylen ---------------- | ------ fObjlen ------ |
| ordinary TKey fields | 3 strings | header | entry data | offsets? |
```

> **A reader MUST take `fKeylen` from the key and MUST NOT compute it from the
> three strings.** Computing it puts the payload 19 bytes early on every basket in
> the file.

**A basket always uses the large key layout.** Its constructor does
`fVersion += 1000` unconditionally (`root/tree/tree/src/TBasket.cxx:71`), so
`fSeekKey` and `fSeekPdir` are 8 bytes each however small the file is. This is the
only place in ROOT where the large form appears in a file under 2 GB.

Two other key fields carry basket-specific meanings:

| Field | In a basket |
|---|---|
| `fName` | the **branch** name |
| `fTitle` | the **tree** name (`root/tree/tree/src/TTree.cxx:3777`) |
| `fCycle` | the **basket number**, not a cycle |

> **`fCycle` is not a cycle.** It is set to `fBranch->GetWriteBasket()`
> (`root/tree/tree/src/TBasket.cxx:1293`), so basket 0 has `fCycle` 0 — a value no
> other key in a ROOT file carries, since `TKey` treats a cycle of 0 or less as
> "keep" (`root/io/io/src/TKey.cxx:640-642`). A reader that de-duplicates keys by
> `(name, cycle)`, as
> [Record §8](../01-container/Record.md#8-invariants) invariant 9 allows for
> ordinary keys, must exclude baskets.

> Demonstrated by `ttree/basket`: both basket keys have `fVersion` 1004 and
> `fKeylen` 65, where the fixed part plus their three strings is 46.

## 2. The header

Written at `root/tree/tree/src/TBasket.cxx:1110-1140`, read at
`root/tree/tree/src/TBasket.cxx:986-1026`. Class version 3
(`root/tree/tree/inc/TBasket.h:156`).

| Offset | Field | Type | Notes |
|---|---|---|---|
| 0 | version | `i16` | 3. **No byte count precedes it** |
| 2 | `fBufferSize` | `i32` | the writer's buffer size; a hint, not a length |
| 6 | `fNevBufSize` | `i32` | see §2.1, and **the sign is a flag** |
| … | `fIOBits` | `u8` | **only if `fNevBufSize` was negative**; §2.2 |
| … | `fNevBuf` | `i32` | the number of entries in this basket |
| … | `fLast` | `i32` | §3 |
| … | `flag` | `i8` | §4 |

So the header is **19 bytes, or 20 when `fIOBits` is present**, and that is the
only thing that varies in it.

### 2.1 `fNevBufSize` means two different things

`root/tree/tree/inc/TBasket.h:63` states it exactly: "Length in `Int_t` of
`fEntryOffset` OR fixed length of each entry if `fEntryOffset` is null".

| Basket | `fNevBufSize` is |
|---|---|
| no entry-offset array | the **byte width of one entry** |
| with an entry-offset array | the **allocated length** of that array, in `Int_t` |

The second is a writer's capacity, unrelated to `fNevBuf`, and a reader needs it
only for the first case.

> Demonstrated by `ttree/basket`: branch `n` is one `Int_t` per entry and has
> `fNevBufSize` 4; branch `a` is a counted array and has 1000, which is the
> branch's default `fEntryOffsetLen`.

### 2.2 The sign of `fNevBufSize` carries `fIOBits`

> **This is how ROOT added a field without bumping the class version.**

If the `fNevBufSize` read is negative, negate it and read a `u8` `fIOBits`
(`root/tree/tree/src/TBasket.cxx:997-1000`). Otherwise `fIOBits` is 0 and no byte
is consumed.

| `fIOBits` bit | Name | Meaning |
|---|---|---|
| 0 | `kGenerateOffsetMap` | the entry-offset array is absent or stored as sizes; §5.2 |
| 7 | — | **reserved, and must be 0** |

`root/tree/tree/inc/TBasket.h:97-102`. ROOT rejects a basket outright — marking it
a zombie — if `fIOBits` is zero after the negative marker, if bit 7 is set, or if
any bit outside the supported set is set
(`root/tree/tree/src/TBasket.cxx:1001-1019`). A reader SHOULD do the same: an
unknown bit means the basket was written by a newer ROOT using a feature that
changes the layout.

> The reserved bit 7 exists so that the field can be widened the same way later,
> which the comment at `root/tree/tree/src/TBasket.cxx:990-996` spells out.

## 3. `fLast`

**`fLast` is measured from the start of the record, not the payload.** It is
`fBufferRef->Length()` at the moment the data was finished
(`root/tree/tree/src/TBasket.cxx:1255`), and that buffer begins with the key.

```
entry data occupies   [fKeylen, fLast)      as record offsets
                      [0, fLast - fKeylen)  as payload offsets
```

Everything from `fLast` to the end of the payload is the entry-offset array, if
there is one:

```
fObjlen == (fLast - fKeylen) + size of the offset array
```

> Demonstrated by `ttree/basket`: branch `n`'s basket is at 268 with `fLast` 77,
> so its data ends at 345 — which is exactly where the next record begins, and
> `fObjlen` is 12. Branch `a`'s basket is at 345 with `fLast` 89, so its data
> ends at 434 and the remaining 20 bytes of its 44-byte payload are the array.

## 4. The flag byte, and the two shapes of a basket

> **A basket written as a record and a basket streamed into another buffer are
> different layouts, and the flag byte is what distinguishes them.**

On writing, `fHeaderOnly` decides
(`root/tree/tree/src/TBasket.cxx:1134-1155`):

| Case | `flag` | What follows the header |
|---|---|---|
| **a record** (`fHeaderOnly`) | 0, or **80** if offsets are to be generated | nothing — the payload is written separately by `WriteBuffer` |
| **streamed in full** | composed, see below | the arrays and the data, inline |

For the streamed form the flag is built up:

```
flag  = 1                       if fNevBuf and an entry-offset array exists
flag  = 2                       otherwise
flag += 10                      if the entry data follows
flag += 40                      if a displacement array follows
flag += 80                      if the offsets are to be generated
```

and read back by decomposition (`root/tree/tree/src/TBasket.cxx:1027-1098`):

| Test | Meaning |
|---|---|
| `flag >= 80` | generate the offsets; subtract 80 and continue |
| `flag == 0` | nothing follows the header |
| `flag % 10 == 2` | there is no entry-offset array |
| otherwise | an entry-offset array follows, as `count` then `count` × `i32` |
| `20 < flag < 40` | mask each offset with `~0xFF000000` — the top byte is a displacement, not part of the offset (`root/tree/tree/src/TBasket.cxx:32`) |
| `flag > 40` | a displacement array follows, in the same `count`-prefixed form |
| `flag == 1 or flag > 10` | the entry data follows, `fLast` bytes of it |

> **The consequence for a reader of files:** in a basket *record* the flag is 0 or
> 80, and it tells you nothing about whether an offset array is present — §3's
> arithmetic does. Every other flag value belongs to a basket embedded in some
> other buffer, and §4.1 gives that layout.

### 4.1 The embedded layout

An embedded basket is an ordinary object slot
([Buffer §6](../02-serialization/Buffer.md#6-object-slots)) whose class is
`TBasket`, and it occurs in exactly one place: an entry of a branch's `fBaskets`
([TBranch §5](TBranch.md#5-fbaskets-is-written-and-is-usually-empty)).

`TBasket::Streamer` writes **the whole `TKey` first**
(`root/tree/tree/src/TBasket.cxx:1111`), so the object body begins with the key
fields and the three counted strings — there is no byte count and no version word
of its own in front of them. Then:

```
TKey fixed fields   fClassName fName fTitle        ┐
version:i16                                        │ fKeylen bytes
fBufferSize:i32  fNevBufSize:i32  fNevBuf:i32      │ from the start
fLast:i32  flag:u8                                 ┘ of the body
if an entry-offset array:   count:i32 (= fNevBuf)   count × i32
if flag > 40:               count:i32               count × i32   (displacements)
if flag == 1 or flag > 10:  fLast bytes of the basket's own buffer
```

Four things differ from a record, and three of them will mislead a reader that
assumes otherwise:

- **The leading count of the entry-offset array is `fNevBuf`, not `fNevBuf + 1`**
  (`root/tree/tree/src/TBasket.cxx:1154`, checked on read at
  `root/tree/tree/src/TBasket.cxx:1053-1060`). §5.1's extra trailing element is a
  property of the record form alone, produced by `WriteBuffer`'s
  offset-to-size conversion.
- **The raw block is `fLast` bytes taken from the start of the basket's own
  buffer**, so its first `fKeylen` bytes are the *reserved key area* — stale bytes,
  not entry data. Entry offsets index that block from its start, which is why the
  first is `fKeylen` exactly as in a record.
- **`fNbytes`, `fSeekKey` and `fSeekPdir` are 0**, because the key was never placed
  in a file, and **`fObjlen` is stale** — it holds the buffer's capacity, not a
  length. A reader MUST NOT use `fObjlen` here; §3's arithmetic test does not apply
  and the flag is what says what follows.
- **Nothing is compressed.** The basket sits inside whatever compression the
  enclosing record uses.

And one trap that is not a difference so much as an omission: **when `fNevBuf` is
0 no offset array is written even if the flag says there is one.** Both sides are
guarded by `fNevBuf` independently of the flag
(`root/tree/tree/src/TBasket.cxx:1153`, `root/tree/tree/src/TBasket.cxx:1046-1071`),
so an empty basket can carry flag 1 or 11 with the raw block following the header
directly. A reader that trusts the flag alone reads the first four bytes of the
reserved key area as a count.

`fKeylen` still covers the key *and* the header, exactly as in a record, so the
data offsets line up between the two forms.

> Demonstrated by `ttree/basket-embedded`, which writes the same two branches as
> `ttree/basket` but with `TDirectory::WriteTObject` instead of `TTree::Write`,
> so no basket reaches a record. Branch `n` has flag **12** (no offset array, data
> follows) and branch `a` flag **11** (offset array, data follows), and the entry
> offsets are `65, 69, 77` — the same three values the record form writes. Both
> have `fObjlen` 31935, which is `fBufferSize − fKeylen` and means nothing.

Two of the flag ranges cannot occur in a file written by a current ROOT:

- **`20 < flag < 40`** is the pre-2000 packing, where each entry offset carried a
  displacement in its top byte. Nothing writes it any more, and the read path
  masks those bits off and discards them
  (`root/tree/tree/src/TBasket.cxx:1073-1077`) rather than recovering the
  displacement.
- **`flag > 40`**, a displacement array, requires `TBasket::Update` to be called
  with a skip count, which happens only for a branch filled entry-by-entry out of
  order or for a circular tree (`root/tree/tree/src/TBasket.cxx:311-352`). An
  ordinary `TBranch::Fill` never produces one.
>
> Demonstrated by `ttree/basket`, where **both** baskets have `flag` 0 and only
> one has an offset array.

## 5. The entry-offset array

Present when a branch's entries are not all the same length. It sits **after** the
entry data, at `fLast`, inside the same payload and under the same compression.

```
count:i32   count × i32
```

### 5.1 Three things to get right

- **`count` is `fNevBuf + 1`, not `fNevBuf`** — in a record. `WriteBuffer` writes one extra
  element (`root/tree/tree/src/TBasket.cxx:1269`), and the read side allocates for
  it with the comment "We need to allocate an extra element due to the offset/size
  conversion happening during writing"
  (`root/tree/tree/src/TBasket.cxx:1064-1065`). **The extra value is not an
  offset.** A reader MUST use only the first `fNevBuf`. An *embedded* basket
  writes `fNevBuf` and no extra element (§4.1) — the one place the two forms
  disagree on a count.
- **The offsets are record-relative**, like `fLast`. The first is always `fKeylen`.
- **The last entry's end is `fLast`**, not an array element. Entry *i* spans
  `[offset[i], offset[i+1])` for *i* < `fNevBuf` − 1, and entry `fNevBuf` − 1 spans
  `[offset[fNevBuf - 1], fLast)`.

> Demonstrated by `ttree/basket`: branch `a`'s array is `4` then `65, 69, 77, 0`.
> `fNevBuf` is 3, `fKeylen` is 65, and the fourth value is 0 — a reader that
> treats it as an offset places a fourth entry at the start of the file. The three
> entries are 4, 8 and 12 bytes, and the last ends at `fLast` = 89.

Note that the embedded form of §4 writes `count == fNevBuf` instead
(`root/tree/tree/src/TBasket.cxx:1155`), and the read path there asserts exactly
that (`root/tree/tree/src/TBasket.cxx:1053-1061`). The two forms disagree by one
element, which is the sort of thing only a byte-level reading reveals.

### 5.2 With `kGenerateOffsetMap`, the array holds sizes

When `fIOBits` bit 0 is set, one of two things is true
(`root/tree/tree/src/TBasket.cxx:1257-1283`):

- the offsets can be regenerated from the branch's type, and **no array is written
  at all** — the record's `fObjlen` then equals `fLast - fKeylen`, and the header's
  flag is 80. §5.2.1 says how to regenerate them, and **§6's arithmetic must not be
  applied**: a basket in this state looks exactly like a fixed-length one and is
  not;
- they cannot, and the array is written as **differences** instead of offsets:
  `entryOffset[i] -= entryOffset[i-1]` for *i* descending, and `entryOffset[0]` set
  to 0. A reader recovers the offsets by accumulating from `fKeylen`.

> A reader that ignores `fIOBits` and reads the array as offsets gets a sequence
> beginning at 0 and rising by the entry sizes — plausible, monotonic, and wrong
> by `fKeylen` at every entry.

#### 5.2.1 Regenerating the offsets

When no array was written, a reader must compute one. The recurrence is
(`root/tree/tree/src/TLeaf.cxx:210-216`):

```
offset[0]   = fKeylen
offset[i+1] = offset[i] + fLenType × count[i] + header
```

where `count[i]` is the value, at entry *i*, of the leaf named by this leaf's
`fLeafCount` — read from **its** branch, exactly as in
[TLeaf §5.2](TLeaf.md#52-the-element-count-comes-from-another-leaf) — and `header`
is 0 for every leaf class except `TLeafElement`, where it is 1
(`root/tree/tree/inc/TLeafElement.h:42`).

Two preconditions, both enforced by ROOT and both worth checking:

- **the branch has exactly one leaf**, or the offsets cannot be generated at all
  (`root/tree/tree/src/TBasket.cxx:206-209`);
- **that leaf has a `fLeafCount`** (`root/tree/tree/inc/TLeaf.h:115`), since a
  fixed-size leaf would not need generated offsets in the first place.

> Note `fLenType`, not the on-disk width. For `TLeafF16`, `TLeafD32` and `TLeafG`
> the two differ ([TLeaf §4.1](TLeaf.md#41-flentype-is-not-the-on-disk-width)), so
> this recurrence is wrong for those three. ROOT has the same problem; whether the
> combination can arise is recorded in `PLAN.md` §7.1.

> Demonstrated by `ttree/basket-iofeatures`, whose branch `a` has flag 80 and no
> array: the offsets a reader must compute are 66, 70 and 78, and they land on the
> same floats `ttree/basket` stores explicitly.

> Verified against a file nobody here wrote as well —
> `uproot-small-dy-nooffsets.root` from the foreign corpus of `PLAN.md` §9.8:
> branch `Jet_jetId`, `fNevBufSize` 1000, `fNevBuf` 200, `fKeylen` 77, `fLast`
> 3477, flag 80, `fIOBits` 1, and no array. The 200 counts in branch `nJet` sum to
> 850; `77 + 4 × 850` is 3477 exactly.

> **`kGenerateOffsetMap` never applies to a `TBranchElement`.** Demonstrated the
> other way round by `ttree/basket-iofeatures`, which is leaflist-only for exactly
> this reason. Every
> `TBranchElement` constructor delegates to the default `TBranch()` constructor,
> which does not copy the tree's IO features
> (`root/tree/tree/src/TBranchElement.cxx:168`,
> `root/tree/tree/src/TBranchElement.cxx:213`). So in 6.40.04 only leaflist
> branches ever carry a non-zero `fIOBits`, and a reader will meet the feature
> only on those. Recorded as a probable defect in `PLAN.md` §7.1.

## 6. Fixed-length entries

When there is no entry-offset array **and the flag is not 80**, every entry is
`fNevBufSize` bytes and entry *i* begins at payload offset `i × fNevBufSize`. The
whole payload is data:

```
fObjlen == fNevBuf × fNevBufSize
```

> **The flag condition is not optional.** A basket with flag 80 also has no array
> and also has `fObjlen == fLast - fKeylen`, and its entries are *not*
> fixed-length: `fNevBufSize` is the array capacity there, typically 1000, and
> multiplying it out overruns the payload by orders of magnitude. §5.2.1 is what
> applies.
>
> **`fIOBits` alone is not the test.** A branch with the feature enabled sets it
> on *every* basket, including those whose entries really are fixed-length and
> which keep flag 0 — `ttree/basket-iofeatures` has one of each. It is the flag
> that says the offsets were dropped.

> Demonstrated by `ttree/basket`: branch `n` has `fNevBuf` 3, `fNevBufSize` 4 and
> `fObjlen` 12. And from the other side by `uproot-small-dy-nooffsets.root`
> (`PLAN.md` §9.8), whose `Jet_jetId` basket has `fNevBuf` 200 and `fNevBufSize`
> 1000 against an `fObjlen` of 3400.

## 7. Compression

A basket's payload is compressed by the ordinary rules of
[Compression](../01-container/Compression.md) — the key is not, which is why the
header is always readable without decompressing anything.

**The entry data and the entry-offset array are compressed together**, as one
payload: the array is appended to the same buffer before the buffer is compressed
(`root/tree/tree/src/TBasket.cxx:1254-1269`). A reader cannot read the array
without decompressing the whole basket.

`TBasket` performs its own multi-block splitting with the same constants as the
container layer (`root/tree/tree/src/TBasket.cxx:1300-1355`), so nothing about the
block format differs.

**Compression is all or nothing for the whole basket.** If any chunk compresses to
zero bytes or to no less than `fObjlen`, ROOT abandons compression for the entire
basket and writes it raw (`root/tree/tree/src/TBasket.cxx:1334`,
`root/tree/tree/src/TBasket.cxx:1347`) — giving `fNbytes == fKeylen + fObjlen`,
which is the ordinary "stored raw" case of
[Compression §1](../01-container/Compression.md#1-deciding-whether-a-payload-is-compressed).
Note that the test compares one *chunk's* output against the *whole* object's
length, which is a loose test for a multi-block basket.

## 8. Reading

To read entry *i* of a basket record:

1. Read the key. Take `fKeylen`, `fObjlen` and `fNbytes` from it.
2. Skip the ordinary key — the fixed part plus three counted strings — to reach
   the basket header.
3. Read `version`, `fBufferSize`, `fNevBufSize`. If `fNevBufSize` is negative,
   negate it and read a `u8` `fIOBits`; reject the basket if `fIOBits` is 0, has
   bit 7 set, or has any bit outside the supported set.
4. Read `fNevBuf`, `fLast` and the flag byte.
5. Decompress the payload if `fNbytes - fKeylen != fObjlen`.
6. If `fObjlen == fLast - fKeylen` there is no entry-offset array, and the flag
   says which of two cases it is. **Flag 80**: the offsets must be generated from
   the branch's leaf by §5.2.1. **Flag 0**: entry *i* is `fNevBufSize` bytes at
   payload offset `i × fNevBufSize`. Done either way.
7. Otherwise read `count` and `count` `i32` values at record offset `fLast`. Use
   the first `fNevBuf`. If `fIOBits` bit 0 is set, they are sizes: accumulate from
   `fKeylen` to recover offsets. If the flag, after subtracting 80, is between 21
   and 39, mask each with `~0xFF000000`.
8. Entry *i* spans `[offset[i], offset[i+1])`, or `[offset[fNevBuf - 1], fLast)`
   for the last, as **record** offsets.

What those bytes then mean is the branch's business, not the basket's: a basket
carries no type information at all.

> **Step 6's test is not the one ROOT uses.** `TBasket::ReadBasketBuffers` decides
> whether to read an offset array from `fBranch->GetEntryOffsetLen()`, a field of
> the *branch* (`root/tree/tree/src/TBasket.cxx:689-691`) — so ROOT cannot
> interpret a basket record without its branch. The arithmetic test above needs
> only the basket, and agrees with ROOT on every file it writes: the array is
> present exactly when there are bytes between `fLast` and the end of the payload.

## 9. Invariants

These are the invariants of a basket **record**. An embedded basket satisfies 1,
3, 5, 7 and 8 with its own start in place of the record's, and satisfies neither
4 nor 6: its `fObjlen` is stale (§4.1).

1. `fKeylen` equals the ordinary key length plus 19, or plus 20 when `fIOBits` is
   present, and the header ends exactly at `fKeylen`.
2. The key's `fVersion` is above 1000.
3. `fNevBuf >= 0` and `fLast >= fKeylen`.
4. `fObjlen - (fLast - fKeylen)` is either 0 or `4 + 4 × (fNevBuf + 1)`.
5. Where an entry-offset array is present, its first element is `fKeylen`, the
   elements do not decrease, and the last of the first `fNevBuf` is **at most**
   `fLast` — equal when the last entry is empty, which `TLeafC::ReadBasket` tests
   for explicitly (`root/tree/tree/src/TLeafC.cxx:151`).
6. Where none is present **and the flag is not 80**,
   `fObjlen == fNevBuf × fNevBufSize`. With flag 80 there is no relation between
   `fNevBufSize` and the entry size at all (§5.2).
7. Every entry's byte range lies within `[fKeylen, fLast]`. An entry may be
   **empty**, so a range may start at `fLast`.
8. `fIOBits`, where present, is non-zero and has neither bit 7 nor any
   unsupported bit set.

Invariant 2 is not corruption-testable in isolation: lowering the key version
shifts `fSeekKey` and `fSeekPdir` by eight bytes, so the record chain breaks and
the file is rejected by [Record §8](../01-container/Record.md#8-invariants) before
this check is reached.

## 10. Errata

Against `root/io/doc/TFile/ttree.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | — | Nothing says a basket's own fields are inside `fKeylen`, which is the single most damaging omission: a reader that computes the key length from the strings misplaces every payload in the tree (§1) |
| 2 | — | Nothing says a basket always uses the large key layout, so a reader that switches on file size reads `fSeekKey` four bytes short (§1) |
| 3 | — | `fNevBufSize` is documented nowhere, including that it means two different things and that its **sign** carries `fIOBits` (§2.1, §2.2) |
| 4 | — | Nothing says `fLast` is record-relative, nor that the entry offsets are (§3, §5.1) |
| 5 | — | Nothing says the offset array's count is `fNevBuf + 1` with a meaningless final element (§5.1) |
| 6 | — | Nothing describes the flag byte, or that a basket record's flag is always 0 or 80 and says nothing about whether an offset array is present (§4) |
| 7 | — | Nothing describes `kGenerateOffsetMap`, under which the array holds sizes or is absent entirely (§5.2), nor how to regenerate the offsets when it is (§5.2.1) |
| 7a | — | Nothing gives the embedded layout at all: that the key is streamed in full ahead of the header, that the offset array's count drops to `fNevBuf`, that the raw block's first `fKeylen` bytes are a reserved key area, or that `fObjlen` is stale there (§4.1) |
| 8 | `README.md`: "For each branch, exactly one `TBasket` object is contained in the `TTree` data record. If the data on a given branch fits in one basket, then all the data for that branch will be in the `TTree` record itself" | **Not true of current ROOT.** `TTree::Write` flushes every basket first (`root/tree/tree/src/TTree.cxx:10012`), and `TBranch::Streamer` removes from `fBaskets` every basket that is on disk or empty (`root/tree/tree/src/TBranch.cxx:3195-3205`). `ttree/basket` has three entries in one basket per branch and still writes both as standalone records, with none embedded. Embedding happens only when a tree is streamed without flushing |
| 9 | `ttree.md:45-64`: the `TBranch` member list is version 7 | `TBranch` is at version **13** (`root/tree/tree/inc/TBranch.h:304`), `fEntryNumber`, `fEntries`, `fTotBytes` and `fZipBytes` are `Long64_t` rather than `Int_t`/`Stat_t`, `fBasketEntry` and `fBasketSeek` are type 56 rather than 43, and `fIOFeatures`, `fFirstEntry` and the `TAttFill` base are missing entirely |
| 10 | `README.md`: "the custom written `TBasket` streamer internally handles the packing of data into fixed size `TBasket` objects" | Baskets are not fixed size, and the streamer writes only the header — the record framing and the compression are `TBasket::WriteBuffer`'s doing. The neighbouring claim that there is no streamer info for `TBasket` is correct |

## 11. Class versions

| Version | Difference |
|---|---|
| 1 | the embedded raw buffer was written as a **counted** array, so a reader must use `ReadArray` rather than a bare `fLast` bytes (`root/tree/tree/src/TBasket.cxx:1102-1103`) |
| 2 | the form this document describes, minus `fIOBits` |
| 3 | current: the negated-`fNevBufSize` extension of §2.2 |

A version-3 basket with no IO features set is byte-identical to a version-2 one,
and **the version is not how a reader detects `fIOBits`** — the sign of
`fNevBufSize` is (§2.2).

## 12. Reference files

| Case | Exercises |
|---|---|
| `ttree/basket` | Both record shapes: a fixed-length basket with no offset array and a variable-length one with it, uncompressed and asserted byte for byte, plus the large key form |
| `ttree/basket-embedded` | The embedded form of §4.1, for the same two branches: flag 12 and flag 11, an offset array counted by `fNevBuf`, a stale `fObjlen`, and no `TBasket` record in the file |
| `ttree/basket-iofeatures` | `fIOBits` in both of its consequences: the negated `fNevBufSize` and 20-byte header of §2.2, and the flag-80 basket of §5.2 that stores no offsets at all |

No fixture covers a compressed basket, a multi-block basket, or a displacement
array. A displacement array needs an out-of-order fill or a circular tree.
