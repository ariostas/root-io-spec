# `TArray`

`TArrayC`, `TArrayS`, `TArrayI`, `TArrayL`, `TArrayL64`, `TArrayF`, `TArrayD`.

The shortest hand-written streamer in ROOT, and the first class in this
specification whose layout cannot be recovered from the file. It matters out of
all proportion to its size: every histogram contains at least three of them.

Prerequisites: [Conventions](../00-conventions.md),
[Element types](../02-serialization/ElementTypes.md).

## 1. Layout

```
fN:i32   fN values of the element type
```

That is the whole class. **No byte count, no version word, no class record**
(`root/core/cont/src/TArrayD.cxx:148-159`, and identically in the other six).
`TArray::fN` is not streamed separately by its base; the concrete class writes it.

| Class | Element | On-disk width |
|---|---|---|
| `TArrayC` | `Char_t` | 1 |
| `TArrayS` | `Short_t` | 2 |
| `TArrayI` | `Int_t` | 4 |
| `TArrayL` | `Long_t` | **8** |
| `TArrayL64` | `Long64_t` | 8 |
| `TArrayF` | `Float_t` | 4 |
| `TArrayD` | `Double_t` | 8 |

The total size is therefore `4 + fN × width`, exactly, in every context.

> **`TArrayL` is 8 bytes per element** whatever `sizeof(long)` was on the writing
> machine (`root/io/io/src/TBufferFile.cxx:2132-2146`), like every other `Long_t`
> on disk ([Conventions §4](../00-conventions.md#4-primitive-types)). `TArrayL`
> and `TArrayL64` are indistinguishable from their bytes alone.

> Demonstrated by `classes/tarray`, which writes all seven as standalone records:
> their `fObjLen` values are 6, 8, 12, 20, 20, 12 and 20 for two elements each.

## 2. The streamer info, where it exists, is wrong by one byte

Whether a file carries a `TStreamerInfo` for a concrete `TArray` is not
predictable, and **it does not follow from the file containing one**. A reader
MUST hardcode §1 either way.

What decides it is how the array reached the file, not what the file holds:

| The file has | Concrete `TArray` info |
|---|---|
| eight `TArray`s written directly | **none** — the `StreamerInfo` list is empty |
| a `TH2F` written with `Write()` | **none**, though `TH2F`'s own info names `TArrayF` as a base |
| a `TH2F` held in a `TObjArray` | **none** |
| a `TH2F` in a **`TTree` branch** | `TArrayF`, `TArrayD` **and** `TArray` |

`TH1`'s hand-written `Streamer` never asks for the info; creating a branch does,
because it builds the streamer info of every class in the hierarchy.

> Demonstrated by `classes/tarray`, whose `StreamerInfo` record is the 21-byte
> empty list ([Streamer information §3.2](../02-serialization/StreamerInfo.md#32-an-empty-list-is-meaningful))
> even though the file contains eight arrays; by `serialization/version-zero`,
> which has fourteen infos and none for `TArrayL64`, whose base it contains; and
> by `classes/tarray-histogram`, which is the `TTree` row.
>
> Measured across the two corpora: of the 39 files containing a histogram, **16
> carry a concrete `TArray` info and 23 do not**, from ROOT 3.05 to 6.26. It is
> not a version difference.

**When the info is present it is nearly right, which is worse than being absent.**
It lists two elements:

| Element | Code | Would read |
|---|---|---|
| `TArray` base | 0 | `fN` as an `i32`, via `TArray`'s own info |
| `fArray` | `kOffsetP + T` (44 or 45) | **one flag byte**, then `fN` values |

The flag byte is what a counted pointer always writes
([Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer)),
and `TArray::Streamer` does not write it. So following the recorded info reads
`5 + fN × width` bytes where there are `4 + fN × width`.

> Demonstrated by `classes/tarray-histogram`, whose `TArrayF` info lists exactly
> those two elements — `fArray` at code 45 with `fCountName` `fN` and
> `fCountClass` `TArray` — while the bytes of the `TH2F`'s `TArrayF` base are
> `fN` = 49 followed **immediately** by 49 floats: 200 bytes where the recorded
> info reads 201.
>
> This is the sharpest example in this specification of
> [Streamer-driven reading §7](../02-serialization/StreamerDriven.md#7-when-the-streamer-info-does-not-describe-the-bytes):
> the description is plausible, off by a single byte, and desynchronises
> everything after it. A reader that trusts it does not fail — it silently reads
> the next member from one byte late.

## 3. Where a `TArray` appears

Three ways, and **none of them adds framing**.

### 3.1 As a base class

`TH1C`, `TH1S`, `TH1I`, `TH1L`, `TH1F`, `TH1D` and their 2-D and 3-D
counterparts each derive from the matching `TArray`, which holds the bin
contents.

The element is `kBase` (0), and
[Element types §6](../02-serialization/ElementTypes.md#6-kbase-0-and-knotype-1)
gives `kBase` a byte count and a version word — **but that is the framing the
*base class's own streamer* writes, not framing the element adds.** `TArray`
writes none, so a `TArray` base is `fN` and the values, with nothing in front.

> **This is the trap.** A reader that emits a byte count and a version word for
> every `kBase` element desynchronises on the first histogram it meets, and does
> so eight bytes into a 500-byte object.
>
> Demonstrated by `serialization/version-zero`: `TH1L`'s `TArrayL64` base begins
> at offset 879 with `00 00 00 04` — `fN` = 4 — and the four `Long64_t` values run
> to 915, which is the end of the payload.

### 3.2 As a member by value

`TH1::fContour` and `TH1::fSumw2` are `TArrayD` members held by value. The element
code is `kAny` (62), and again the framing is whatever the member class writes:
nothing.

> Demonstrated by `serialization/version-zero`: `fContour` at 836 and `fSumw2` at
> 840 are each **four bytes** — `00 00 00 00`, an empty array — back to back.

### 3.3 As a standalone record

The record's object data is the array and nothing else, so
`fObjLen == 4 + fN × width`.

> Demonstrated by `classes/tarray`.

## 4. Reading

At a `TArray` of any concrete type:

1. Read `fN` as an `i32`. Reject a negative value.
2. Read `fN` values of the width in §1.

There is nothing to resynchronise on, in any of the three contexts: no byte count
delimits a `TArray`. Getting `fN` or the width wrong is unrecoverable until the
*enclosing* object's byte count ends.

## 5. Invariants

1. `fN` is not negative.
2. A `TArray` occupies exactly `4 + fN × width` bytes.
3. A standalone `TArray` record has `fObjLen == 4 + fN × width`.

Invariant 2 is checked through the enclosing object's byte count, as §4 explains:
a wrong width shifts everything after it and the enclosing count catches it.

There is deliberately no invariant about the recorded streamer info of §2. No
reference file contains one, so any such check would pass vacuously, and the
observation there is recorded as an erratum with its measurement instead.

## 6. Errata

| # | Claim | Actually |
|---|---|---|
| 1 | — | `root/io/doc/TFile/*.md` does not describe `TArray` at all, in any of its pages, despite `TH1` being its worked example elsewhere |
| 2 | — | Nothing says that a `kBase` element is unframed when the base has a hand-written streamer. `streamerinfo.md`'s "0: base class" entry implies uniform framing (§3.1) |
| 3 | — | Nothing warns that `TArrayL` is 8 bytes on disk, or that it is indistinguishable from `TArrayL64` (§1) |
| 4 | — | The `TStreamerInfo` ROOT sometimes writes for a concrete `TArray` describes a layout one byte longer than the bytes, because `fArray` is recorded as a counted pointer and a counted pointer writes a presence flag that `TArray::Streamer` does not (§2) |

## 7. Reference files

| Case | Exercises |
|---|---|
| `classes/tarray` | All seven widths, an empty array, and the empty `StreamerInfo` list |
| `serialization/version-zero` | A `TArrayL64` base and two `TArrayD` members by value, inside `TH1L` |
| `classes/tarray-histogram` | The `TStreamerInfo` for `TArrayF` that §2 is about, beside the 200 bytes it describes as 201 |
