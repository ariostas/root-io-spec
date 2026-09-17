# `TMap`, `TExMap` and `TBtree`

The three ROOT containers whose `Streamer` is hand-written at **every** class
version, so that no streamer info in any file describes their bytes. They are
grouped here because they share that property and nothing else: a `TMap` is a
hash table of object pairs, a `TExMap` is a table of integers with no objects at
all, and a `TBtree` is an ordered collection whose on-disk form is not a tree.

[Hand-written streamers](../99-appendix/HandWrittenStreamers.md) is the list they
come from. `TList`, `TObjArray` and `TClonesArray` are in the same category and
are specified elsewhere, per `PLAN.md` decision 6.

Prerequisites: [Conventions](../00-conventions.md),
[Buffer framing](../02-serialization/Buffer.md) — in particular §6, the object
tag, which all three depend on.

## 1. `TMap`

Class version **3** (`root/core/cont/inc/TMap.h:91`).

```
bc:u32  ver:i16=3  <TObject>  fName:string  n:i32  n x ( key:object  value:object )
```

| Offset | Field | Type | Notes |
|---|---|---|---|
| 0 | byte count | `u32` | with `kByteCountMask`; the frame `WriteVersion(..., kTRUE)` opened |
| 4 | version | `i16` | 3 |
| 6 | `TObject` | 10 bytes | the base, written bare — no frame of its own |
| 16 | `fName` | counted string | inherited from `TCollection`, and written by `TMap` itself |
| … | `n` | `i32` | the number of **pairs**, from `GetSize()` |
| … | pairs | | `2n` object references, key then value |

`root/core/cont/src/TMap.cxx:360-394`.

The version guards on the read side (`v > 2` for `TObject`, `v > 1` for `fName`)
describe versions 1 and 2, which need a pre-ROOT-4 file to test against and are
recorded as a gap in §8.

### 1.1 The pairs are object references, not objects

Each half of a pair is written with `TBuffer::operator<<(const TObject *)`, which
is the pointer form of [Buffer framing §6](../02-serialization/Buffer.md): a byte
count, then either a class tag and the object, or a four-byte reference to an
object already in the buffer. **The same object stored twice is written once.**

In `classes/containers` the two pairs share one value:

```
383  40 00 00 25                    byte count, 37 bytes follow
387  ff ff ff ff                    kNewClassTag
391  "TObjString\0"                 the class name, null-terminated
402  40 00 00 12 00 01 ...          the object: version 1, TObject, "alpha"
424  40 00 00 1b                    byte count
428  80 00 00 53                    class reference: the tag at 387
432  40 00 00 13 00 01 ...          the object: "shared"
...
484  00 00 00 78                    object reference: the object at 424
```

The last four bytes are the whole of the second pair's value. A reader that
expects an object at every slot reads a byte count that is not there, and the
remaining bytes of the record decode as noise.

> `TPair` never appears on disk. `TMap::Streamer` writes `a->Key()` and
> `a->Value()` and never the pair itself, so `TPair`'s class version 0 and its
> streamer info are both unreachable through a `TMap`.

A null key is dropped on read — `if (obj) Add(obj, value)`
(`root/core/cont/src/TMap.cxx:378`) — but its value has already been consumed, so
the pair count still governs how many references to read. **`n` is the number of
references divided by two, not the number of entries the reader ends up with.**

## 2. `TExMap`

Class version **3** (`root/core/cont/inc/TExMap.h:81`). It holds no objects:
every entry is three integers, and the container is a `TObject` rather than a
`TCollection`.

```
bc:u32  ver:i16=3  <TObject>  fSize:i32  fTally:i32
                              fTally x ( slot:i32  hash:u64  key:i64  value:i64 )
```

| Field | Type | Meaning |
|---|---|---|
| `fSize` | `i32` | the **capacity** of the hash table, in slots |
| `fTally` | `i32` | the **number of entries**, and never the capacity |
| `slot` | `i32` | where the entry sits in a table of `fSize` slots |
| `hash` | `u64` | the stored hash, which is not the hash that was given — §2.1 |
| `key` | `i64` | |
| `value` | `i64` | |

`root/core/cont/src/TExMap.cxx:305-382`. Exactly `fTally` records follow, not
`fSize`: the write loop walks all `fSize` slots and skips the free ones
(`root/core/cont/src/TExMap.cxx:375-380`).

Because that loop walks the table in slot order, **the records are in slot order,
which is not insertion order**. In `classes/containers` the entry added last is
the first on disk.

### 2.1 The stored hash has bit 0 forced

`Assoc_t::SetHash` is `fHash = (h | 1)`, and `InUse()` is `fHash & 1`
(`root/core/cont/inc/TExMap.h:44-46`): a zero hash marks a free slot, so bit 0 is
spent on that flag and the hash the caller supplied is not recoverable if it was
even. `classes/containers` adds hashes 3, 6, 9 and 10 and the file holds 3, 7, 9
and 11.

The slot follows from the **stored** hash, so a reader recomputing a slot from a
hash it was given will not reproduce the file.

### 2.2 `Long_t` on disk is always eight bytes

Class versions 1 and 2 read `hash`, `key` and `value` as `ULong_t`/`Long_t`
rather than the version-3 `ULong64_t`/`Long64_t`
(`root/core/cont/src/TExMap.cxx:334-352`). That is **not** a width difference on
disk: `frombuf` consumes eight bytes for a `ULong_t` whatever `sizeof(ULong_t)`
is, and keeps only the low four when it is 4
(`root/core/base/inc/Bytes.h:324-350`). A 32-bit reader silently truncated; the
bytes did not move.

So versions 2 and 3 have the same layout and differ only in the value range.
Version 1 is a different layout — no slot index, and the table is rebuilt by
`Add` — and needs an old file to test (§8).

## 3. `TBtree`

Class version **0** (`root/core/cont/inc/TBtree.h:106`), and the version word on
disk is therefore `00 00`. That is a version word, not a checksum; the rule for
telling the two apart is [Buffer framing §4](../02-serialization/Buffer.md).

```
bc:u32  ver:i16=0
fOrder:i32  fOrder2:i32  fInnerLowWaterMark:i32  fLeafLowWaterMark:i32
fInnerMaxIndex:i32  fLeafMaxIndex:i32
<TCollection frame>
```

`root/core/cont/src/TBtree.cxx:459-484`.

**None of the tree structure is written.** The nodes, the keys and the ordering
all live in `fRoot`, which is not streamed; what reaches the file is six integers
describing the *shape parameters* and then the elements as a flat sequence. A
reader reconstructs nothing and needs nothing: the elements arrive in order.

### 3.1 Five of the six integers are derived

`TBtree::Init` computes all of them from `fOrder`
(`root/core/cont/src/TBtree.cxx:351-367`):

| Field | Value | Order 3 |
|---|---|---|
| `fOrder2` | `2 * (fOrder + 1)` | 8 |
| `fLeafMaxIndex` | `fOrder2 - 1` | 7 |
| `fInnerMaxIndex` | `fOrder` | 3 |
| `fLeafLowWaterMark` | `fLeafMaxIndex / 2 - 1` | 2 |
| `fInnerLowWaterMark` | `(fOrder - 1) / 2` | 1 |

They are redundant on disk and are checkable against each other, which is
invariant 3 in §7.

### 3.2 The elements come from `TCollection`, through a class that adds nothing

`TBtree::Streamer` ends with `TSeqCollection::Streamer(b)`, and what that emits is
**byte for byte what `TCollection::Streamer` emits** — one frame, version 3, with
no frame of its own around it:

```
bc:u32  ver:i16=3  <TObject>  fName:string  n:i32  n x object
```

`root/core/cont/src/TCollection.cxx:637-669`. In `classes/containers` the
`TCollection` frame opens at offset 756 and its version word is at 760,
immediately after `TBtree`'s sixth integer at 752.

Why an intermediate class contributes nothing at all is §6, and it is not
specific to `TBtree`.

## 4. None of the three writes a streamer info

`TStreamerInfo::ForceWriteInfo` is reached through `WriteClassBuffer`
(`root/io/io/src/TBufferFile.cxx:3722`), and none of these classes calls it.
So a file holding a `TMap`, a `TExMap` and a `TBtree` and nothing else carries
**one** streamer info — for the `TObjString`s inside them, whose `Streamer` is
generated.

That is the sharpest statement of
[Streamer-driven reading §7](../02-serialization/StreamerDriven.md) available in
the corpus: the presence of an info and the meaning of the bytes are independent.
`TBasket` is the other class with no info of its own
([TBasket §1](../04-ttree/TBasket.md)), and it reaches files the same way.

## 5. Reading

1. Read the frame: byte count and version word
   ([Buffer framing §2](../02-serialization/Buffer.md)).
2. `TMap` and `TCollection` (and so `TBtree`'s tail): read a bare `TObject`
   (10 bytes, no frame), then `fName` as a counted string, then the count.
3. For each of the count (twice that for a `TMap`), read one object reference by
   [Buffer framing §6](../02-serialization/Buffer.md). Resolve a class reference
   and an object reference against the same buffer, whose origin is the start of
   the **record**, with `kMapOffset` 2 added.
4. `TExMap`: read `fSize` and `fTally`, then exactly `fTally` records of
   4 + 8 + 8 + 8 bytes. Mask bit 0 out of the hash if the original is wanted; it
   is not recoverable.
5. `TBtree`: read six `i32`, then go to step 1 for the `TCollection` frame.
6. Check the byte count.

## 6. A version-0 class can contribute nothing at all

This is the general rule behind §3.2, and it belongs here because `TBtree` is the
only fixture that witnesses it.

When `rootcling` generates a `Streamer` for a class whose `ClassDef` version is
**≤ 0**, and the class was selected with a plain `#pragma link C++ class X;`
rather than `X+`, it emits a body that calls each base class's `Streamer` **and
nothing else** — no version word, no byte count, no members
(`root/core/dictgen/src/rootcling_impl.cxx:1332-1367`). The choice between that
generator and the schema-evolution one is `cl.RequestStreamerInfo()`, which is the
`+` suffix (`root/core/clingutils/src/TClingUtils.cxx:3016`).

`TSeqCollection` is exactly this: version 0
(`root/core/cont/inc/TSeqCollection.h:73`), selected plainly
(`root/core/cont/inc/LinkDef.h:49`). Its `Streamer` forwards to `TCollection` and
adds nothing, which is why §3.2's frame is `TCollection`'s.

> Checked directly rather than inferred: streaming the same `TBtree` through
> `TSeqCollection::Streamer` and through `TCollection::Streamer` produces
> identical buffers, 59 bytes each. The generated definition is in the dictionary
> and not in the repository, so the source alone cannot answer this — a reading
> of `ClassDefOverride` and `WriteClassBuffer` predicts a frame that the bytes say
> is not there.

**A reader cannot tell the two generators apart from the file.** Both produce a
streamer info for the class, both record class version 0, and the `+` suffix is
not persisted anywhere. `TSeqCollection`'s recorded info has a single element, the
`TCollection` base, and following it — version word, then the base — is wrong by
six bytes.

This is the same shape as
[Streamer-driven reading §4.4](../02-serialization/StreamerDriven.md), which
covers a base class with a *hand-written* `Streamer`, and the two together
account for both of `PLAN.md` §9.9's open leads. The second of them,
`aod_flushed.root`, is this rule: `TTreePerfStats`'s first element is a `kBase`
for `TVirtualPerfStats`, which is version 0
(`root/core/base/inc/TVirtualPerfStats.h:93`) and plainly selected
(`root/core/base/inc/LinkDef3.h:173`). Its `Streamer` therefore contributes
exactly its own base, a bare `TObject`, and the record's bytes agree:

```
+0   40 00 86 60     byte count
+4   00 01           TTreePerfStats version 1
+6   00 01 00 00 00 00 03 00 00 00      the TVirtualPerfStats base: a TObject
+16  ...             fTreeCacheSize and the rest
+28  00 03 e8 00     fReadaheadSize = 256000
```

Ten bytes for the base, with no version word of its own. Reading it as a framed
object puts `fReadaheadSize` four bytes early and every later member with it.

## 7. Invariants

1. A `TMap`'s pair count `n` satisfies `4 + 2 + 10 + len(fName) + 1 + 4 + (bytes
   consumed by 2n references) = byte count + 4`. The references are
   variable-length, so this is a consumption check, not an arithmetic one.
2. A `TExMap`'s `fTally` records exactly exhaust its frame:
   `byte count + 4 = 4 + 2 + 10 + 4 + 4 + 28 * fTally`.
3. A `TExMap`'s `fTally` is at most its `fSize`, every `slot` is in
   `[0, fSize)`, the slots are strictly increasing, and every stored `hash` is
   odd.
4. A `TBtree`'s six integers satisfy the five identities of §3.1.
5. A `TBtree`'s `fOrder` is at least 3 (`root/core/cont/src/TBtree.cxx:345-347`).
6. A `TBtree`'s `TCollection` frame ends exactly where the `TBtree` frame's byte
   count says the object ends.

All six are checked by `tools/check_invariants.py` over every fixture and both
corpora.

## 8. Errata

| # | Claim | Correction |
|---|---|---|
| 1 | `TBtree.h:47` says `fOrder2` is `order*2+1` | `TBtree::Init` computes `2 * (fOrder + 1)` (`root/core/cont/src/TBtree.cxx:351`). For order 3 the comment gives 7 and the file holds 8. The comment has said this since the class was written; nothing reads it, so nothing has caught it |
| 2 | `TMap`'s streamer info describes a `TCollection` base holding `fName` and `fSize` | `TMap::Streamer` writes a bare `TObject` and then `fName` itself. `fSize` is never written; the pair count is `GetSize()` computed at write time. The same fiction as `TList`'s ([Streamer-driven reading §7](../02-serialization/StreamerDriven.md)) |

## 9. Gaps

| Gap | Needs |
|---|---|
| `TMap` versions 1 and 2 — no `TObject`, no `fName` | a pre-4.00 file (`PLAN.md` §9.1) |
| `TExMap` version 1 — no slot index | the same |
| A `TMap` with a null key | reachable now; not written |
| A `TBtree` whose elements are not all one class, so the class tag alternates | reachable now; not written |

## 10. Reference files

| File | What it pins |
|---|---|
| `classes/containers` | all three classes in one file: §1 including the shared value and its back-reference, §2 including the forced hash bit and the slot ordering, §3 including the version-0 word and the missing `TSeqCollection` frame, and §4 — the file carries one streamer info, for `TObjString` |
