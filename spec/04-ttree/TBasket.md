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
> other buffer.
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

- **`count` is `fNevBuf + 1`, not `fNevBuf`.** `WriteBuffer` writes one extra
  element (`root/tree/tree/src/TBasket.cxx:1269`), and the read side allocates for
  it with the comment "We need to allocate an extra element due to the offset/size
  conversion happening during writing"
  (`root/tree/tree/src/TBasket.cxx:1064-1065`). **The extra value is not an
  offset.** A reader MUST use only the first `fNevBuf`.
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
  flag is 80;
- they cannot, and the array is written as **differences** instead of offsets:
  `entryOffset[i] -= entryOffset[i-1]` for *i* descending, and `entryOffset[0]` set
  to 0. A reader recovers the offsets by accumulating from `fKeylen`.

> A reader that ignores `fIOBits` and reads the array as offsets gets a sequence
> beginning at 0 and rising by the entry sizes — plausible, monotonic, and wrong
> by `fKeylen` at every entry.

No reference file exercises either path; producing one needs a branch with the
IO feature enabled.

## 6. Fixed-length entries

When there is no entry-offset array, every entry is `fNevBufSize` bytes and entry
*i* begins at payload offset `i × fNevBufSize`. The whole payload is data:

```
fObjlen == fNevBuf × fNevBufSize
```

> Demonstrated by `ttree/basket`: branch `n` has `fNevBuf` 3, `fNevBufSize` 4 and
> `fObjlen` 12.

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
6. If `fObjlen == fLast - fKeylen`, there is no entry-offset array: entry *i* is
   `fNevBufSize` bytes at payload offset `i × fNevBufSize`. Done.
7. Otherwise read `count` and `count` `i32` values at record offset `fLast`. Use
   the first `fNevBuf`. If `fIOBits` bit 0 is set, they are sizes: accumulate from
   `fKeylen` to recover offsets. If the flag, after subtracting 80, is between 21
   and 39, mask each with `~0xFF000000`.
8. Entry *i* spans `[offset[i], offset[i+1])`, or `[offset[fNevBuf - 1], fLast)`
   for the last, as **record** offsets.

What those bytes then mean is the branch's business, not the basket's: a basket
carries no type information at all.

## 9. Invariants

1. `fKeylen` equals the ordinary key length plus 19, or plus 20 when `fIOBits` is
   present, and the header ends exactly at `fKeylen`.
2. The key's `fVersion` is above 1000.
3. `fNevBuf >= 0` and `fLast >= fKeylen`.
4. `fObjlen - (fLast - fKeylen)` is either 0 or `4 + 4 × (fNevBuf + 1)`.
5. Where an entry-offset array is present, its first element is `fKeylen`, the
   elements do not decrease, and the last of the first `fNevBuf` is below `fLast`.
6. Where none is present, `fObjlen == fNevBuf × fNevBufSize`.
7. Every entry's byte range lies within `[fKeylen, fLast)`.
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
| 7 | — | Nothing describes `kGenerateOffsetMap`, under which the array holds sizes or is absent entirely (§5.2) |

## 11. Reference files

| Case | Exercises |
|---|---|
| `ttree/basket` | Both shapes: a fixed-length basket with no offset array and a variable-length one with it, uncompressed and asserted byte for byte, plus the large key form |

No fixture covers a compressed basket, a multi-block basket, a displacement array,
`fIOBits` in either of its forms, or the embedded form of §4. The `fIOBits` paths
need a branch with the IO feature enabled; the embedded form needs a basket
streamed into a buffer rather than written as a record.
