# Element types

Every member of a streamer-info-driven class has a type code, and the code
determines exactly what bytes the member occupies. This document is the mapping.

Prerequisites: [Conventions](../00-conventions.md),
[Buffer framing](Buffer.md), [Streamer information](StreamerInfo.md). All
integers are big-endian.

Notation: `bc` is a byte count, a `u32` with `kByteCountMask` set; `ver` is an
`i16` version word; `n` is the element's `fArrayLength` (treated as 1 when 0);
`c` is the current value of the counter member named by `fCountName`.

## 1. The type codes

The codes are `TVirtualStreamerInfo::EReadWrite`
(`root/core/meta/inc/TVirtualStreamerInfo.h:124-174`). The offset families are
`kOffsetL = 20` for a fixed array and `kOffsetP = 40` for a counted pointer; both
are **added to** a base code.

> **Roughly half the enum can never appear in a file.** Time spent implementing
> those codes is wasted, so the third column is the most useful one here.

| Code | Name | On disk? |
|---|---|---|
| -3 | `kUnset` | no — a default-constructor value |
| -2 | `kUnsupportedConversion` | no — an `fNewType`, never an `fType` |
| **-1** | **`kNoType`** | **yes** — a suppressed `TObject` base; §6 |
| 0 | `kBase` | yes |
| 1–5 | `kChar` `kShort` `kInt` `kLong` `kFloat` | yes |
| 6 | `kCounter` | yes |
| 7 | `kCharStar` | yes |
| 8, 9 | `kDouble`, `kDouble32` | yes |
| 10 | `kLegacyChar` | no producer and no reader in 6.40.04 |
| 11–14 | `kUChar` `kUShort` `kUInt` `kULong` | yes |
| 15 | `kBits` | yes, but only in `TObject`'s own info |
| 16–19 | `kLong64` `kULong64` `kBool` `kFloat16` | yes |
| 61–67 | `kObject` `kAny` `kObjectp` `kObjectP` `kTString` `kTObject` `kTNamed` | yes |
| 68, 69 | `kAnyp`, `kAnyP` | yes |
| 70 | `kAnyPnoVT` | a write path exists but no reader; no producer |
| 71 | `kSTLp` | **no** — written as 500 |
| 100, 120, 140 | `kSkip`, `kSkipL`, `kSkipP` | no |
| 200, 220, 240 | `kConv`, `kConvL`, `kConvP` | no |
| 300 | `kSTL` | **no** — written as 500 |
| 365 | `kSTLstring` | **no** — never an `fType` at all |
| 500, 501 | `kStreamer`, `kStreamLoop` | yes |
| 600 | `kCache` | no |
| 1000–1002 | `kArtificial`, `kCacheNew`, `kCacheDelete` | no |
| 99997, 99999 | `kNeedObjectForVirtualBaseClass`, `kMissing` | no — offset sentinels, not types |

### 1.1 Why the in-memory-only codes cannot occur

- **`kSkip*` and `kConv*`** are added to a *compiled* per-member structure, not to
  an element, and only inside `TStreamerInfo::Compile`
  (`root/io/io/src/TStreamerInfoActions.cxx:4317`,
  `root/io/io/src/TStreamerInfoActions.cxx:4323`). That structure is transient
  (`root/io/io/inc/TStreamerInfo.h:97-99`). `kSkipL`, `kSkipP`, `kConvL` and
  `kConvP` are never used as addends anywhere in ROOT; those ranges arise only
  because the element's code already carried `kOffsetL` or `kOffsetP`.
- **`kArtificial`, `kCacheNew`, `kCacheDelete`** belong to `TStreamerArtificial`
  elements, which the write path filters out
  (`root/io/io/src/TStreamerInfo.cxx:5699`) and whose streamer is a no-op anyway
  (`root/core/meta/src/TStreamerElement.cxx:2253`).
- **`kCache`** has no assignment site in ROOT at all; caching is driven by a
  status bit instead.
- **`kSTL`, `kSTLp`, `kSTLstring`** are overwritten with 500 on the way out; see
  [Streamer information §10](StreamerInfo.md#10-tstreamerstl-stores-a-type-code-it-does-not-mean).

### 1.2 Optimisation does not change the bytes

`Compile` may merge several consecutive same-type scalars into one compiled entry,
adding 20 to its code (`root/io/io/src/TStreamerInfoActions.cxx:4250-4289`). This
affects only the transient compiled array; the bytes are identical either way.

> A specification, and a reader, must be written against the element list, never
> against the compiled list.

## 2. Scalars

Widths are fixed by the code, **not** by the element's `fSize`
(`root/io/io/src/TStreamerInfoReadBuffer.cxx:824-836`).

| Code | Name | On disk | Bytes |
|---|---|---|---|
| 1 | `kChar` | signed | 1 |
| 2 | `kShort` | signed | 2 |
| 3 | `kInt` | signed | 4 |
| 4 | `kLong` | signed, **always 8** | 8 |
| 5 | `kFloat` | binary32 | 4 |
| 6 | `kCounter` | signed | 4 |
| 8 | `kDouble` | binary64 | 8 |
| 11 | `kUChar` | unsigned | 1 |
| 12 | `kUShort` | unsigned | 2 |
| 13 | `kUInt` | unsigned | 4 |
| 14 | `kULong` | unsigned, **always 8** | 8 |
| 16 | `kLong64` | signed | 8 |
| 17 | `kULong64` | unsigned | 8 |
| 18 | `kBool` | 0 or 1 | 1 |

`kLong` and `kULong` are 8 bytes even where the writer's `long` was 4, with
sign-extension for the signed form
([Conventions §4](../00-conventions.md#4-primitive-types)).

> Demonstrated by `serialization/basic-types`, which contains one member of each
> of these and pins every offset.

> `fSize` is the writer's `sizeof`, not the on-disk width. A reader MUST size
> every member from its code. `serialization/streamer-info` shows `fStr` with
> `fSize` 24 and an on-disk form of 2 bytes.

### 2.1 `kCounter` (6)

An ordinary `i32`. It is marked `kCounter` because some other member's length
refers to it by name.

> **The counter's value is the only source of that length; no length is ever
> written for the member that uses it.** A reader MUST retain every counter value
> it has read in the current object.

### 2.2 `kCharStar` (7)

```
n:i32   n bytes
```

No terminator and no `255` escape — this is not the counted string of
[Conventions §5.1](../00-conventions.md#51-counted-string)
(`root/io/io/src/TBufferFile.cxx:285-317`). **A null pointer and an empty string
are both four zero bytes** and cannot be distinguished.

### 2.3 `kBits` (15)

```
fBits:u32   [pidf:u16 if fBits has kIsReferenced (BIT(4))]
```

`root/io/io/src/TStreamerInfoReadBuffer.cxx:1031-1055`. The writer masks off
`kIsOnHeap` and `kNotDeleted`
(`root/io/io/src/TStreamerInfoWriteBuffer.cxx:409-412`), exactly as
[Buffer framing §7](Buffer.md#7-the-tobject-base) describes for the `TObject`
base.

This code exists only because `Build` special-cases `TObject::fBits`
(`root/io/io/src/TStreamerInfo.cxx:668-670`), so it appears **only in `TObject`'s
own streamer info**.

## 3. `kOffsetL + T` (20 + T) — fixed-size array

```
n values of T, back to back
```

**No prefix, no count, no byte count** for a basic type
(`root/io/io/src/TStreamerInfoReadBuffer.cxx:877-897`). `n` is `fArrayLength` and
comes from the streamer info, never from the stream.

A multidimensional array is flat and row-major. `fArrayLength` is the product of
the extents, `fArrayDim` the rank, and `fMaxIndex[0..4]` the extents — so on disk
a `[2][2]` array is indistinguishable from a flat array of 4, and only the
streamer info recovers the shape.

> Demonstrated by `serialization/arrays`: `fFixed[3]` is three `i32` with nothing
> around them, and `fGrid[2][2]` is four `f64` in row-major order.

The object codes take `kOffsetL` too, but not uniformly — see §7.2.

## 4. `kOffsetP + T` (40 + T) — counted pointer

```
isArray:i8
if (isArray != 0)  n × c values of T
```

`root/io/io/src/TStreamerInfoReadBuffer.cxx:87-105`, written at
`root/io/io/src/TStreamerInfoWriteBuffer.cxx:64-75`.

Four things to get right:

- The flag is a **signed 1-byte value**, not a 4-byte bool.
- **When the flag is 0 the member is over** — one byte total, with no length and
  no payload. It is written as 0 when the pointer is null *or* the counter is 0.
- There is **exactly one flag byte** even when `fArrayLength > 1`: `kOffsetL` is
  not added for counted pointers
  (`root/core/meta/src/TStreamerElement.cxx:1022-1025`), so the total element
  count is `max(fArrayLength, 1) × c` — ROOT raises a zero `fArrayLength` to 1
  when it compiles the info (`root/io/io/src/TStreamerInfoActions.cxx:4332-4334`),
  and a scalar counted pointer has `fArrayLength` 0.
- The length comes from the counter, never from the stream (§2.1).

> Demonstrated by `serialization/arrays`: `fVar` has flag byte 1 followed by three
> `i32`, and `fMissing` has flag byte 0 followed by nothing at all — the record
> ends there.

## 5. `kDouble32` and `kFloat16`

> **These are the only members whose on-disk width cannot be determined from the
> streamer info's type fields alone. It depends on the element's comment string.**

`fXmin`, `fXmax` and `fFactor` are transient
(`root/core/meta/inc/TStreamerElement.h:44-46`) and are recomputed by parsing
`fTitle`, gated on the `kHasRange` bit (`BIT(6)`) of the element's own `fBits`
(`root/core/meta/src/TStreamerElement.cxx:586`). See
[Streamer information §7.1](StreamerInfo.md#71-the-range-fields-moved-out-of-the-record).

### 5.1 The annotation grammar

An annotation is `[xmin,xmax]` or `[xmin,xmax,nbits]`, parsed by
`root/core/meta/src/TStreamerElement.cxx:118-185`. `xmin` and `xmax` accept the
literals `pi`, `2pi`, `twopi`, `pi/2` and `pi/4`. Then:

```
if nbits is absent or outside [2, 32]:   nbits = 32
bigint = (nbits < 32) ? (1 << nbits) : 0xffffffff
if xmin < xmax:                          factor = bigint / (xmax - xmin)
if xmin >= xmax and nbits < 15:          xmin = nbits + 0.1
```

The last line is why `fXmin` doubles as the bit-count carrier when no real range
was given. Note that the first bracket in a comment may be an array dimension, in
which case the parser retries after it
(`root/core/meta/src/TStreamerElement.cxx:128-134`).

### 5.2 The three encodings

| Case | Condition | On disk | Bytes |
|---|---|---|---|
| Range | `factor != 0` | `aint:u32` | **4** |
| Truncated mantissa | `factor == 0` and `(int)fXmin != 0` | `theExp:u8`, `theMan:u16` | **3** |
| Plain `kDouble32` | `factor == 0` and `(int)fXmin == 0` | binary32 | **4** |
| Plain `kFloat16` | `factor == 0` and `(int)fXmin == 0` | `theExp:u8`, `theMan:u16` with `nbits = 12` | **3** |

Range path (`root/io/io/src/TBufferFile.cxx:492-498`,
`root/io/io/src/TBufferFile.cxx:527-533`):

```
read aint:u32       value = aint / factor + fXmin
write               aint  = u32(0.5 + factor * (clamp(value, fXmin, fXmax) - fXmin))
```

Mantissa path (`root/io/io/src/TBufferFile.cxx:504-521`,
`root/io/io/src/TBufferFile.cxx:539-556`), where `i` is the binary32 bit pattern:

```
read theExp:u8, theMan:u16
i  = theExp << 23
i |= (theMan & ((1 << (nbits + 1)) - 1)) << (23 - nbits)
value = bitcast<float>(i)
if (theMan & (1 << (nbits + 1)))  value = -value      // sign is bit nbits+1
```

### 5.3 Two traps

> **An annotation of `[0,0,15]` or higher silently produces a plain 4-byte
> float**, because `xmin` is only set to the bit count when `nbits < 15`
> (`root/core/meta/src/TStreamerElement.cxx:184`). So a 15-bit request is *wider*
> on disk than a 14-bit one, and the element does not even carry `kHasRange`.
>
> **The range path always costs 4 bytes**, whatever `nbits` says: `[-1,1,2]` is a
> `u32`, not two bits.

> Both are demonstrated by `serialization/double32`, where the six members occupy
> 4, 4, 3, 3, 4 and 3 bytes: `fBits15` is wider than `fBits14`, and `fRange` with
> a 32-bit factor is the same width as the unannotated `fPlain`. A trailing `i32`
> sentinel pins the last width.

## 6. `kBase` (0) and `kNoType` (-1)

```
kBase:    bc  ver  <the base class's own members>
kNoType:  nothing at all
```

A base class is read by recursing into it
(`root/io/io/src/TStreamerInfoReadBuffer.cxx:1400-1412`), which emits a byte count
and a version word of its own because it goes through the ordinary
streamer-info-driven path.

> **A `TObject` or `TNamed` base does not have code 0.** `TStreamerBase`'s
> constructor rewrites the code by name
> (`root/core/meta/src/TStreamerElement.cxx:667-668`).

| Base | Code | Byte count | Version word |
|---|---|---|---|
| `TObject` | 66 | **no** | yes |
| `TNamed` | 67 | yes | yes |
| anything else | 0 | yes | yes |
| `TObject`, suppressed | **-1** | — | — (nothing written) |

`kNoType` arises when the class sets `kIgnoreTObjectStreamer`, and a reader MUST
consume **nothing** for it rather than treating it as an error
(`root/io/io/src/TStreamerInfo.cxx:518-522`,
`root/io/io/src/TStreamerInfoReadBuffer.cxx:1702-1704`).

> Demonstrated by `serialization/version-zero`: `TH1L`'s `TH1` base has code 0
> with a byte count, and inside `TNamed` the `TObject` base has code 66 and only a
> version word.

## 7. Object-valued codes, 61 to 71

| Code | Name | Byte count | Version | Class record | Null form |
|---|---|---|---|---|---|
| 61 | `kObject` | yes | yes | no | n/a |
| 62 | `kAny` | yes | yes | no | n/a |
| 63 | `kObjectp` (`->`) | yes | yes | **no** | **never null** |
| 64 | `kObjectP` | yes | yes | **yes** | four zero bytes |
| 65 | `kTString` | **no** | **no** | no | n/a |
| 66 | `kTObject` | **no** | yes | no | n/a |
| 67 | `kTNamed` | yes | yes | no | n/a |
| 68 | `kAnyp` (`->`) | yes | yes | **no** | **never null** |
| 69 | `kAnyP` | yes | yes | **yes** | four zero bytes |
| 70 | `kAnyPnoVT` | no | yes | no | a 1-byte flag |
| 71 | `kSTLp` | yes | yes | no | n/a |

The `p`/`P` pairs differ only in nullability, and **only the comment string
decides which** (`root/core/meta/src/TStreamerElement.cxx:1527`,
`root/core/meta/src/TStreamerElement.cxx:1630`):

- `kObjectp` (63) and `kAnyp` (68) come from a `->` annotation. The pointer is
  promised non-null, so no class record and no null check are written and the
  object follows the byte count directly.
- `kObjectP` (64) and `kAnyP` (69) get the full object-slot protocol of
  [Buffer framing §6](Buffer.md#6-object-slots), including a class record, because
  the pointer may be null or may refer to a derived class.

The choice between `kObject`/`kObjectp`/`kObjectP` and `kAny`/`kAnyp`/`kAnyP` is
whether the member's class derives from `TObject`.

> Demonstrated by `serialization/pointer-forms`, whose `fArrow` and `fPlainP` have
> the same C++ type and differ only by the `->` comment: `fArrow` is 14 bytes with
> no class record, `fPlainP` is 26 bytes with one.
>
> `serialization/objects` demonstrates 62 (embedded, no class record), 69 and 64
> (class records), and a null pointer as four zero bytes.

### 7.1 The three fast paths

`kTString`, `kTObject` and `kTNamed` bypass the generic path, and **they do not
agree with each other** (`root/io/io/src/TStreamerInfoReadBuffer.cxx:1070-1072`):

- **`kTString` (65)** is a bare counted string — no byte count, no version word,
  no class record.
- **`kTObject` (66)** is `TObject::Streamer` alone: a version word and then 10 or
  12 bytes, with **no byte count**. A reader that assumes every object-valued
  member begins with a byte count desynchronises on the first `TObject` base.
- **`kTNamed` (67)** *does* have a byte count, because it is an ordinary
  streamer-info-driven read.

> Demonstrated by `serialization/objects` (`fStr` at 345 is a bare counted string)
> and `serialization/object-tags` (a `TObject` base at 369 with only a version
> word).

### 7.2 The array forms are not uniform

> **Adding `kOffsetL` to an object code does not simply repeat the scalar form.**

| Scalar | Array | Framing of the array form |
|---|---|---|
| 61 `kObject` | 81 | `n` objects back to back, **no outer framing** |
| 62 `kAny` | 82 | `n` objects back to back, **no outer framing** |
| 65 `kTString` | 85 | **`bc ver`**, then `n` strings |
| 66 `kTObject` | 86 | **`bc ver`**, then `n` `TObject`s |
| 67 `kTNamed` | 87 | **`bc ver`**, then `n` `TNamed`s |
| 63, 64, 68, 69 | unchanged | `kOffsetL` is **not** added; `fArrayLength > 1` instead |

`root/io/io/src/TStreamerInfoReadBuffer.cxx:1380-1397` for 81/82 and
`root/io/io/src/TStreamerInfoReadBuffer.cxx:1414-1433` for 85/86/87. The pointer
codes omit `kOffsetL` deliberately
(`root/core/meta/src/TStreamerElement.cxx:1578-1581`,
`root/core/meta/src/TStreamerElement.cxx:1681-1684`).

> **The version word in the 85/86/87 form is `TStreamerInfo`'s own class version,
> 10** — not the member class's version and not a count.
>
> Demonstrated by `serialization/pointer-forms`: `fS1` is code 65 and occupies 2
> bytes, while `fS2`, code 85 with two elements, is `40 00 00 06 00 0a` followed
> by the two strings. Treating 85 as "65, twice" loses six bytes.

## 8. `kStreamer` (500) and `kStreamLoop` (501)

Both are framed `bc ver`, where `ver` is `TStreamerInfo`'s class version 10.

**`kStreamer` (500)** marks a member serialized by C++ the reader does not have
(`root/io/io/src/TStreamerInfoReadBuffer.cxx:1436-1460`). The payload is opaque,
and the only correct action is to seek past it using the byte count.

> **On disk, code 500 usually means "STL container", not "custom streamer".**
> Every `TStreamerSTL` and `TStreamerSTLstring` stores 500
> ([Streamer information §10](StreamerInfo.md#10-tstreamerstl-stores-a-type-code-it-does-not-mean)).
> A reader MUST first check the element's concrete class: 500 on a `TStreamerSTL`
> is a collection, and 500 on anything else is a genuine custom streamer.

**`kStreamLoop` (501)** is a counted array of objects
(`root/io/io/src/TStreamerInfoReadBuffer.cxx:1462-1697`):

```
bc  ver
for each of fArrayLength blocks:  c objects, or c object references if
                                  fTypeName contains "**"
```

`c` comes from the counter member, and as with `kOffsetP` **no length is stored**
— the commented-out length write is still visible in ROOT's source
(`root/io/io/src/TStreamerInfoWriteBuffer.cxx:731`).

## 9. `kSTL` (300) and `kSTLstring` (365) — framing only

The contents belong in [Collections](Collections.md). The framing is:

```
bc  ver
```

read with the element's class in hand
(`root/io/io/src/TStreamerInfoReadBuffer.cxx:1151`,
`root/io/io/src/TStreamerInfoReadBuffer.cxx:1255`).

**The member-wise flag lives in that version word**: `kStreamedMemberWise`
(`0x4000`) as described in
[Buffer framing §3.1](Buffer.md#31-kbytecountvmask-and-kstreamedmemberwise-are-the-same-number).
When it is set, a *second* version word for the value class follows for
sufficiently recent `TStreamerInfo` versions
(`root/io/io/src/TStreamerInfoReadBuffer.cxx:1168`,
`root/io/io/src/TStreamerInfoReadBuffer.cxx:1273`). When it is clear, the
collection is written object-wise and `ver` is `TStreamerInfo`'s version 10.

Remember that the stored `fType` is 500, and that `fSTLtype` and `fCtype` are the
element's trailing members.

## 10. Reading

Given a streamer info and a buffer positioned at an object's first content byte:

1. Iterate the elements in order.
2. Skip any element whose `kWrite` bit is set
   (`root/io/io/src/TStreamerInfoReadBuffer.cxx:791`).
3. For each element, consume the bytes its code specifies, per §2 to §9. Retain
   the value of every `kCounter` member for later `kOffsetP` and `kStreamLoop`
   members.
4. For a code the reader does not implement, seek to the end of the enclosing byte
   count. Because every nested object carries one, each is a resynchronisation
   point ([Buffer framing §2.1](Buffer.md#21-a-byte-count-is-authoritative)).
5. At the end, seek to the object's own byte-count end regardless of how much was
   consumed.

A member present on file but absent in the reader's target is simply consumed and
discarded; a member absent on file is left at its default. ROOT implements those
two as separate skip and convert paths, but they change no bytes.

> Step 4 is what makes an unknown class survivable, and step 5 is what makes a
> disagreement survivable. A reader that omits either will fail on files ROOT
> reads without complaint.

## 11. Invariants

1. Every element's `fType` is in the on-disk set of §1.
2. No element has `fType` in the `kSkip`, `kConv`, `kCache` or `kArtificial`
   families, or equal to 71, 300 or 365.
3. An element with `fType` 500 or 501 is either a `TStreamerSTL`,
   a `TStreamerSTLstring`, or an element whose class carries a custom streamer.
4. `fArrayLength` is 0 for a scalar and positive for any code in `[20, 59]`.
5. An element with `fType` in `[40, 59]` is a `TStreamerBasicPointer` and names a
   counter in `fCountName`.
6. An element with `fType` -1 is a `TStreamerBase` named `TObject`.
7. An element with `fType` 66 or 67 is a `TStreamerBase`, or a member whose type is
   exactly `TObject` or `TNamed`.
8. `kHasRange` is set only on an element whose `fType` is 9 or 19, modulo
   `kOffsetL` and `kOffsetP`.

## 12. Errata

Against `root/io/doc/TFile/streamerinfo.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | The type list omits codes 7, 9, 10, 16, 17, 18, 19 | `kCharStar`, `kDouble32`, `kLegacyChar`, `kLong64`, `kULong64`, `kBool` and `kFloat16` all exist, and all but 10 are routine (§1) |
| 2 | The list omits 68, 69, 70, 71 | `kAnyp` and `kAnyP` are extremely common — any pointer to a non-`TObject` class (§7) |
| 3 | "Arrays: 20 + fType of array element", with no exceptions | `kOffsetL` is not added for counted pointers or for object pointers, and for 65/66/67 the array form gains a byte count and a version word the scalar form does not have (§4, §7.2) |
| 4 | "500: an STL string or container", listed beside 501 with no note | The byte is right but the meaning is not: a reader must discard the stored 500 and recompute the real code, and 500 is *also* the genuine custom-streamer code (§8) |
| 5 | "0: base class (other than TObject or TNamed)", without saying what those two use | A `TObject` base is 66 and a `TNamed` base is 67 (§6) |
| 6 | — | `fType` of -1 is legal and means "consume nothing" (§6) |
| 7 | `fSize` is "size of built in type or of pointer to built in type, 0 otherwise" | It is non-zero for every element class and is the writer's `sizeof` (§2) |
| 8 | "4: long" and "14: unsigned long" with no width given | Always 8 bytes on disk (§2) |
| 9 | "6: an array dimension (counter)" | Correct, but nothing says the counter's value is the *only* source of length for the members naming it, and that no length is ever written for them (§2.1, §4) |
| 10 | — | Nothing describes `kDouble32`/`kFloat16` at all: that their width is 3 or 4 bytes, that it depends on parsing the comment string, or that `[0,0,15]` silently degrades to a plain float (§5) |
| 11 | — | Nothing distinguishes `->` from an ordinary pointer, though the byte layouts differ completely (§7) |

## 13. Reference files

| Case | Exercises |
|---|---|
| `serialization/basic-types` | Every fixed-width scalar, codes 1–18 |
| `serialization/arrays` | `kCounter`, `kOffsetL` including two dimensions, and `kOffsetP` both present and absent |
| `serialization/objects` | 62, 64, 65, 69, and a null pointer |
| `serialization/pointer-forms` | 68 versus 69 by comment alone, and 65 versus 85 |
| `serialization/double32` | All three quantised encodings and the `nbits >= 15` cliff |
| `serialization/streamer-info` | The element records that carry these codes, and `fType` 500 on a collection |
| `serialization/version-zero` | `kBase` with a byte count, and code 66 without one |

No fixture covers `kCharStar` (7), `kBits` (15), `kStreamLoop` (501), the 81/82
array forms, or `kAnyPnoVT` (70).
