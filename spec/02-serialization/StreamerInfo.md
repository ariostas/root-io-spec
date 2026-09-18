# Streamer information

Every ROOT file carries a description of the classes it contains. That
description is what makes the format self-describing, and reading it is the one
part of a reader that cannot be driven by it.

Prerequisites: [Conventions](../00-conventions.md),
[Records and keys](../01-container/Record.md),
[Buffer framing](Buffer.md). All integers are big-endian.

## 1. The bootstrap problem

The streamer information is stored as ordinary objects of ordinary classes —
`TList`, `TObjArray`, `TStreamerInfo`, `TStreamerElement` and its subclasses. To
read the description of a class you must already be able to read those, and the
file does not reliably describe them.

> **A reader MUST hardcode the layouts in this document. There is no way to
> bootstrap them out of the file.**

Two things make this less bad than it sounds:

- The set is small: six classes, plus the eleven element subclasses that can
  appear in a file.
  [Bootstrap classes §3](../99-appendix/Bootstrap.md#3-group-a-needed-before-anything-can-be-read)
  lists it, and §4–§8 below give the layouts.
- Once parsed, it describes everything else, including classes the reader has
  never heard of.

A file *may* also contain streamer info for these classes — see §3.3 — but a
reader MUST NOT depend on that either way.

## 2. Finding the record

`fSeekInfo` gives the record's offset and `fNbytesInfo` its total length
including the key
([File header §5.5](../01-container/FileHeader.md#55-fseekinfo-fnbytesinfo)).
The record is read only when `fSeekInfo` is greater than `fBEGIN`
(`root/io/io/src/TFile.cxx:921`).

Its key has `fClassName` `"TList"`, `fName` `"StreamerInfo"` and `fTitle`
`"Doubly linked list"` — the last being `TList`'s class comment, not anything
chosen for this record.

> **The key is deliberately removed from the directory's key list.**
> `WriteStreamerInfo` constructs the key and then takes it straight back out
> (`root/io/io/src/TFile.cxx:3554-3555`), so it can never be found by name. A
> reader MUST locate the record through `fSeekInfo`.

The payload is compressed exactly like any other record — the file's algorithm
and level, and only when the level is non-zero and the payload exceeds 256 bytes
(`root/io/io/src/TKey.cxx:262-264`). It is not special-cased.

Rewriting the record frees the old one (`root/io/io/src/TFile.cxx:3552`), so a
reader walking the record chain of a file that has been updated will meet
deleted `StreamerInfo` records. They are ordinary free spans
([Free segments §4](../01-container/FreeSegments.md#4-the-in-place-marker)).

## 3. What the list contains

The payload is a `TList` (§4). Its entries are:

- one `TStreamerInfo` per described class, in no guaranteed order;
- optionally, **one `TList` named `listOfRules`** as the last entry.

### 3.1 `listOfRules`

Present only when the file has I/O customisation rules to record
(`root/io/io/src/TFile.cxx:3546-3549`). Its entries are `TObjString`s, each
holding one rule rendered as text.

A reader that does not implement schema-evolution rules MUST still skip this
entry correctly, which its byte count makes trivial: any entry whose class is not
`TStreamerInfo` is skipped by seeking past the object's byte count
([Buffer framing §8](Buffer.md#8-reading)). Dispatching on the class name rather
than on position is the robust approach, because the rules list is last only by
current convention.

ROOT itself currently ignores the rules it writes: the loop that would apply them
is inside `#if 0` (`root/io/io/src/TFile.cxx:3364-3373`).

The full shape, and why ROOT ignores it, is in
[Schema evolution §6](SchemaEvolution.md#6-rules-and-the-listofrules-entry).

> Demonstrated by `serialization/schema-rules`. A `#pragma read` needs a compiled
> dictionary, but `TClass::AddRule` produces the same entry from the interpreter.

### 3.2 An empty list is meaningful

ROOT writes an empty list on purpose, to record that the file needs no streamer
info at all (`root/io/io/src/TFile.cxx:3494-3500`). The payload is then 21 bytes:

```
40 00 00 11   byte count, 17
00 05         TList version 5
00 01         TObject version
00 00 00 00   fUniqueID
00 00 00 00   fBits
00            fName, empty
00 00 00 00   entry count, 0
```

A reader MUST treat this as "no classes described", not as a damaged record.

### 3.3 The bootstrap classes may describe themselves

`TagStreamerInfo` marks a class for inclusion whenever an object of it is written
through `WriteClassBuffer` (`root/io/io/src/TBufferIO.cxx:362-364`). If anything
is written to a file *after* a `StreamerInfo` record already exists, the next one
can therefore include `TList`, `TNamed`, `TStreamerElement` and the rest.

A reader MUST neither rely on those entries being present nor be confused by
them, and in particular MUST NOT use them in place of the hardcoded layouts: for
a class with a hand-written streamer the recorded info does **not** describe the
bytes. `TString`'s info, for instance, lists no members at all.

### 3.4 "In no guaranteed order" is stronger than it sounds

The order is not merely unspecified; **it is not a property of the file's content
at all.** `TFile::WriteStreamerInfo` iterates
`gROOT->GetListOfStreamerInfo()` (`root/io/io/src/TFile.cxx:3509`) and keeps the
entries `fClassIndex` has marked, so the order on disk is the order in which
`TStreamerInfo` objects were registered **in the writing process** — which follows
dictionary and shared-library initialisation, not anything about the objects being
written.

Demonstrated rather than asserted: `classes/canvas`, written by the same ROOT
6.40.04 from the same `gen.C`, holds the same fourteen infos with the same names,
versions, checksums and element counts, in a 14982-byte record on both platforms —
**in a different order** on libc++ and libstdc++. A canvas is the first fixture to
show it because it draws infos from libCore, libGraf and libGpad at once.

Two consequences:

- A reader MUST look entries up by name and version, never by position, and MUST
  NOT assume a base class's info precedes the class that uses it.
- The record cannot be normalised into a canonical order for comparison, because
  it carries class and object back-references as **byte positions** (§4,
  [Buffer framing §6](Buffer.md)). The same infos in a different order are
  different bytes throughout. `classes/canvas` therefore declares
  `digest = false`, which is the only fixture here whose reason is ordering rather
  than content.

## 4. `TList`

Hand-written (`root/core/cont/src/TList.cxx:1323`). Current version 5.

| Field | Type | Present |
|---|---|---|
| byte count | `u32` with `kByteCountMask` | always |
| version | `i16` | always |
| `TObject` base | 10 bytes, or 12 if referenced | version > 2 |
| `fName` | counted string | version > 1 |
| entry count | `i32` | always |
| entries | see below | always |

Each entry is an object slot ([Buffer framing §6](Buffer.md#6-object-slots))
followed, **for version > 3 only**, by an option string:

```
object slot   nch:u8   [nbig:i32 if nch == 255 and version > 4]   nch bytes
```

> **The option length byte is the single most common way to desynchronise on this
> record.** It is present after *every* entry, including when the option is
> empty, in which case it is one `0x00` byte. In a `StreamerInfo` record every
> option is empty, so the list is a sequence of `object slot, 0x00` pairs
> (`root/core/cont/src/TList.cxx:1343-1350`).

The `255` escape exists only for version > 4
(`root/core/cont/src/TList.cxx:1344-1348`); a version-4 list writes a bare length
byte, so an option longer than 254 characters cannot be represented there.

> Demonstrated by `serialization/object-tags`, a version-5 list with three empty
> options and one `"opt"`, and by `serialization/streamer-info`, whose single
> entry is followed by one zero byte.

## 5. `TObjArray`

Hand-written (`root/core/cont/src/TObjArray.cxx:448`). Current version 3. Used
for `TStreamerInfo::fElements`.

| Field | Type | Present |
|---|---|---|
| byte count | `u32` with `kByteCountMask` | always |
| version | `i16` | always |
| `TObject` base | 10 or 12 bytes | version > 2 |
| `fName` | counted string | version > 1 |
| entry count | `i32` | always |
| `fLowerBound` | `i32` | always |
| entries | object slots, no options | always |

Unlike `TList` there is **no per-entry option string**. The entry count is the
index of the last occupied slot plus one, so trailing empty slots are not
written; interior holes appear as null slots.

## 6. `TStreamerInfo`

Hand-written (`root/io/io/src/TStreamerInfo.cxx:5608`). Current version 10
(`root/io/io/inc/TStreamerInfo.h:256`).

| Field | Type | Notes |
|---|---|---|
| byte count | `u32` with `kByteCountMask` | |
| version | `i16` | 10 currently |
| `TNamed` base | nested record | `fName` is the **described class**; `fTitle` its comment |
| `fCheckSum` | `u32` | §10 |
| `fClassVersion` | `i32` | written as its absolute value |
| `fElements` | object slot | a `TObjArray` of elements |

**The layout is identical for every version from 1 to 10**
(`root/io/io/src/TStreamerInfo.cxx:5679-5707`). The version number is a semantic
marker, not a layout change, and a reader needs it only for the behaviours in
§6.1.

`fClassVersion` is written as `|fClassVersion|`
(`root/io/io/src/TStreamerInfo.cxx:5686`), so a negative in-memory version is not
recoverable from the file.

`fElements` is **not** the in-memory element array. A temporary array is built
first, dropping every `TStreamerArtificial`, every element with `kRepeat`, and
every element with `kCache` but not `kWrite`
(`root/io/io/src/TStreamerInfo.cxx:5694-5706`). It is written with
`cacheReuse = kFALSE` (`root/io/io/src/TStreamerInfo.cxx:5707`), so each info
carries its own full `TObjArray` record rather than a back-reference to a shared
one — though the *class* `TObjArray` is still back-referenced after the first.

`fBits` of the info is persisted and load-bearing:

| Bit | Name | Meaning |
|---|---|---|
| 13 | `kIgnoreTObjectStreamer` | objects of the described class carry **no** `TObject` bytes |
| 16 | `kIsCompiled` | an artefact of the writer; reset on read and ignorable |

Values at `root/core/meta/inc/TVirtualStreamerInfo.h:74`.

> Demonstrated by `serialization/streamer-info`: `fBits` at offset 521 is
> `0x00010000`, i.e. `kIsCompiled` alone.

A `FIXME` in ROOT claims these bits are never saved to the file
(`root/io/io/src/TStreamerInfo.cxx:1400-1405`). That comment is wrong; see §12,
erratum 9.

### 6.1 Version-dependent reader behaviour

The version does not change the layout, but it changes how *member data* of the
described classes must later be decoded:

| Version | Consequence |
|---|---|
| 1 | strict byte-count check; from 2 on, trailing bytes are tolerated (`root/io/io/src/TStreamerInfo.cxx:5628`) |
| < 3 | a legacy collection encoding applies to that class's STL members |
| < 6 | consecutive `Double32_t`/`Float16_t` members were merged regardless of their annotations |
| < 50000 (*file* version) | `TStreamerBasicType` elements with `fType` 61–65 must be reinterpreted as object elements (`root/io/io/src/TStreamerInfo.cxx:5633-5665`) |

The remembered value is the info's own on-file version
(`root/io/io/src/TStreamerInfo.cxx:5613`), so it is per class, not per file.

## 7. `TStreamerElement`

Hand-written read, streamer-info-driven write
(`root/core/meta/src/TStreamerElement.cxx:541`, write at
`root/core/meta/src/TStreamerElement.cxx:595`). Current version 4.

Only these members are persistent; `fOffset`, `fNewType`, `fXmin`, `fXmax` and
`fFactor` are all transient
(`root/core/meta/inc/TStreamerElement.h:36-46`).

| Field | Type | Notes |
|---|---|---|
| byte count | `u32` with `kByteCountMask` | |
| version | `i16` | of the **concrete subclass**, not of `TStreamerElement` |
| ... | | the subclass's own record opens first; see §8 |
| byte count | `u32` | of the `TStreamerElement` base |
| version | `i16` | 4 currently |
| `TNamed` base | nested record | `fName` is the member or base-class name; `fTitle` the declaration comment |
| `fType` | `i32` | see [Element types](ElementTypes.md) |
| `fSize` | `i32` | the **writer's in-memory size**, not the on-disk width |
| `fArrayLength` | `i32` | total element count of a C array |
| `fArrayDim` | `i32` | rank of a C array |
| `fMaxIndex[5]` | 5 × `i32` | extents — but see §9 |
| `fTypeName` | counted string | the declared type, as text |
| `fXmin`, `fXmax`, `fFactor` | 3 × `f64` | **version 3 only** |

> `fSize` is a trap. It is `sizeof` on the machine that wrote the file: 24 for a
> `TString`, 4 for an `Int_t*` counted array (the pointee), 8 for a `char*` (the
> pointer). A reader MUST derive on-disk widths from `fType`, never from `fSize`.
>
> Demonstrated by `serialization/streamer-info`: `fStr` has `fType` 65 and
> `fSize` 24, while its on-disk form is a counted string of 2 bytes.

**`fSize` makes a streamer info platform dependent.** Two ROOT builds of the same
version, on the same architecture, write byte-different streamer info for the same
class whenever `sizeof` differs between their standard libraries:
`sizeof(std::string)` is 24 with libc++ and 32 with libstdc++, and
`sizeof(std::map<int,int>)` is 24 and 48. Nothing else in the record varies, so
the difference is invisible to a reader — but **two files describing the same
class cannot be compared byte-for-byte across platforms**, and any tool that
digests a file must mask `fSize` first. `tools/normalize.py` in this repository
does, which is the only reason a fixture here can contain a `std::string` or
`std::map` member at all; the constraint was found when one drifted between macOS
and Linux CI while every byte assertion passed and the file size was identical.

### 7.1 The range fields moved out of the record

Version 3 stored `fXmin`, `fXmax` and `fFactor` as three doubles. **Version 4
does not store them at all.** Instead, when the `kHasRange` bit (`BIT(6)`,
`root/core/meta/inc/TStreamerElement.h:71`) is set in the element's own `fBits`,
they are recomputed by re-parsing `fTitle`
(`root/core/meta/src/TStreamerElement.cxx:579-586`).

> **So for a current file the `Double32_t`/`Float16_t` quantisation parameters
> are encoded in an element's comment string, and the on-disk width of such a
> member cannot be determined without parsing it.** The grammar and the
> arithmetic are in [Element types §5](ElementTypes.md#5-kdouble32-and-kfloat16).

Version 1 additionally differs in `fMaxIndex`: it was written as a **counted**
array — an `i32` count followed by that many values — rather than as exactly five
(`root/core/meta/src/TStreamerElement.cxx:562-563`).

| Version | `fMaxIndex` | Range fields |
|---|---|---|
| 1 | counted: `n:i32` then `n` × `i32` | absent |
| 2 | 5 × `i32` | absent |
| 3 | 5 × `i32` | **present**, 3 × `f64` |
| 4 | 5 × `i32` | absent; recovered from `fTitle` |

### 7.2 Read-time fixups

A reader MUST apply these after reading an element, because ROOT's own reader
does and the values it produces are what the rest of the format assumes:

| Condition | Action |
|---|---|
| `fType == 11` and `fTypeName` is `"Bool_t"` or `"bool"` | set `fType = 18` (`root/core/meta/src/TStreamerElement.cxx:566`) |
| version ≤ 2 and the class is `TStreamerBasicType` | `fSize` meant the *element* size, not the member size; recompute it (`root/core/meta/src/TStreamerElement.cxx:572-577`) |
| version == 3 and `fFactor > 0` | set `kHasRange` (`root/core/meta/src/TStreamerElement.cxx:583`) |
| version > 3 and `kHasRange` set | parse `fTitle` for the range (`root/core/meta/src/TStreamerElement.cxx:586`) |

## 8. The element subclasses

Each subclass opens its own record — byte count and version — then the
`TStreamerElement` base record, then its own members. Nesting is therefore
`TStreamerXxx` → `TStreamerElement` → `TNamed` → `TObject`, with a byte count at
each of the first three levels and only a version word at `TObject`.

| Class | Version | Members after the base |
|---|---|---|
| `TStreamerBase` | 3 | `fBaseVersion`: `i32`, **version > 2 only** |
| `TStreamerBasicType` | 2 | none |
| `TStreamerBasicPointer` | 2 | `fCountVersion`: `i32`, `fCountName`: string, `fCountClass`: string |
| `TStreamerLoop` | 2 | `fCountVersion`: `i32`, `fCountName`: string, `fCountClass`: string |
| `TStreamerObject` | 2 | none |
| `TStreamerObjectAny` | 2 | none |
| `TStreamerObjectPointer` | 2 | none |
| `TStreamerObjectAnyPointer` | 1 | none |
| `TStreamerString` | 2 | none |
| `TStreamerSTL` | 3 | `fSTLtype`: `i32`, `fCtype`: `i32` |
| `TStreamerSTLstring` | 2 | none, but nests a whole `TStreamerSTL` record |
| `TStreamerArtificial` | 0 | **never written**; its streamer is a no-op (`root/core/meta/src/TStreamerElement.cxx:2253`) |

`TStreamerSTLstring` is the only one that nests two element levels:
`TStreamerSTLstring` → `TStreamerSTL` → `TStreamerElement` → `TNamed` →
`TObject`.

`fCountVersion` is unused (`root/core/meta/inc/TStreamerElement.h:202`); the
length of a counted array comes from the value of the member named by
`fCountName`, read out of the object itself, and never appears in the stream.

> Demonstrated by `serialization/streamer-info`, which contains one each of
> `TStreamerBasicType`, `TStreamerString`, `TStreamerSTL` and
> `TStreamerBasicPointer`, with `fCountName` `"fN"` and `fCountClass` `"Members"`
> on the last.

## 9. `TStreamerBase`, and a checksum hidden in `fMaxIndex`

> **`fBaseCheckSum` is a reference bound to `fMaxIndex[1]`**
> (`root/core/meta/inc/TStreamerElement.h:154`,
> `root/core/meta/src/TStreamerElement.cxx:646`).

A base class's checksum therefore travels inside the `TStreamerElement` base's
extent array, in a slot that for any other element holds an array dimension. ROOT
acknowledges this as a wart: a comment in `TStreamerBase::Streamer` wishes for a
version that would store `fBaseCheckSum` directly
(`root/core/meta/src/TStreamerElement.cxx:866-868`).

`fMaxIndex` is declared `Int_t` but `fBaseCheckSum` is a `UInt_t`, so **a
checksum with its top bit set reads back negative** and must be reinterpreted as
unsigned. `TObject`'s checksum, `0x901bc02d`, is exactly such a value.

> Verified across the fixtures: every `TStreamerBase` whose base class also has an
> info in the same file has `fMaxIndex[1]` equal to that info's `fCheckSum` — 12
> such pairs, no exceptions. `tools/check_invariants.py` asserts it.

### 9.1 It is 0 on a file written by ROOT 5

**`fBaseCheckSum` did not exist before ROOT 6.** It was added by
`185b44f3d96`, "Add checksum value to TStreamerBase", on 2014-04-21, first
released in 6.00/00. Before that the slot was never filled, so every
`TStreamerBase` on a ROOT 5 file carries `fMaxIndex[1] == 0` — at the same
`TStreamerBase` class version 3, with no other difference. A reader MUST accept
0 and fall back to `fBaseVersion`.

> Measured across the version sweep in the foreign corpus of `PLAN.md` §9.8, which
> brackets the change exactly: `uproot-sample-5.23.02` through `5.30.00` have 23
> `TStreamerBase` elements each and **all 23 are 0**; `6.08.04` through `6.20.04`
> have 22 each and **none** is. The boundary lies between 5.30 and 6.08, where the
> commit puts it.

> This is also why the slot can be relied on at all. `fBaseCheckSum` is set in the
> constructor from `fBaseClass->GetCheckSum()`
> (`root/core/meta/src/TStreamerElement.cxx:677`), so it is 0 whenever the writing
> process did not have the base class loaded — an emulated class, for one — quite
> apart from the version question.

Two more `TStreamerBase` peculiarities:

- **`fType` is not `kBase`** for the two commonest bases. The constructor rewrites
  it by name: 66 (`kTObject`) for a `TObject` base, 67 (`kTNamed`) for a `TNamed`
  base (`root/core/meta/src/TStreamerElement.cxx:667-668`), and `-1` when the
  `TObject` base is suppressed (`root/io/io/src/TStreamerInfo.cxx:518-522`).
- **`fTypeName` is the literal string `"BASE"`**
  (`root/core/meta/src/TStreamerElement.cxx:657`), not the base class's name. The
  name is in `fName`.

`fBaseVersion` is `-1` when the base class declares no version
(`root/core/meta/src/TStreamerElement.cxx:672-674`).

## 10. `TStreamerSTL` stores a type code it does not mean

> **On disk, every `TStreamerSTL` and `TStreamerSTLstring` has
> `fType = 500` (`kStreamer`).** The real code is never written — on any file a
> ROOT 5 or ROOT 6 wrote. §10.1 is the exception.

The write path builds a default-constructed temporary, copies the fields it wants,
forces `fType = kStreamer`, and writes *that*, under a comment saying it is for
forward compatibility (`root/core/meta/src/TStreamerElement.cxx:2140-2155`). The
read path discards the stored value entirely
(`root/core/meta/src/TStreamerElement.cxx:2124-2128`):

```
fType = IsaPointer() ? kSTLp (71) : kSTL (300)
if (fArrayLength > 0) fType += kOffsetL (20)
```

where `IsaPointer()` means `fTypeName` ends in `*`. So `kSTL` (300), `kSTLp` (71)
and `kSTLstring` (365) **never appear as an `fType` in a file**, and a reader that
trusts the stored 500 will treat every STL member as an opaque custom streamer.

> Demonstrated by `serialization/streamer-info`: `fVec`, a `std::vector<int>`, has
> `fType` 500 at offset 841, with `fSTLtype` 1 and `fCtype` 3 identifying the real
> type. `TFile::ShowStreamerInfo` prints 300 for the same element.

Because the temporary is default-constructed, **the element's status bits are
lost**: `kHasRange` and `kDoNotDelete` never survive for an STL element.

Two further read-time reconstructions:

- If `fArrayDim == 0` and `fArrayLength > 0`, recover the rank by counting
  non-zero `fMaxIndex` entries
  (`root/core/meta/src/TStreamerElement.cxx:2106-2111`). ROOT before 6.24/02
  failed to copy `fArrayDim` into the temporary.
- `fSTLtype` values 5 and 6 are ambiguous across ROOT versions and must be
  re-derived from `fTypeName` (`root/core/meta/src/TStreamerElement.cxx:2112-2122`).
  Current numbering has **5 = multimap, 6 = set**
  (`root/core/foundation/inc/ESTLType.h:28-50`); older ROOT had them the other way
  round.

### 10.1 ROOT 4 wrote the real code

Older files carry the honest value: `fType` **300** (`kSTL`) for a
`TStreamerSTL`, and the other real codes where they apply. The masking as 500 is a
forward-compatibility measure that makes an older reader treat the member as
custom-streamed, and it was not always done.

Because the read path overwrites `fType` from `fSTLtype` and `fCtype` regardless
of what was stored, this costs a reader nothing — but an invariant that requires
500 will reject a valid file, and a reader that switches on the stored code will
take a different path on an old one.

> Measured across the foreign corpus of `PLAN.md` §9.8: the two ROOT 4.00/00 files
> carry nine `TStreamerSTL` elements each, all with `fType` **300**. Every one of
> the other 152 files, from ROOT 5.23/02 to 6.36/02, writes only 500.

## 11. Checksums

A checksum identifies a class layout when a version number cannot
([Buffer framing §4](Buffer.md#4-a-version-word-of-0-has-two-different-meanings)).
A reader that must match a version-0 or foreign object to an info needs to compute
it. The algorithm is unsigned 32-bit throughout, wrapping
(`root/io/io/src/TStreamerInfo.cxx:3574`), and is built from two steps:

```
acc_str(id, s):  for each byte c of s:  id = id*3 + c
acc_num(id, n):  id = id*3 + n
```

Then, for the current variant:

1. `id = 0`; `acc_str(id, class name)`.
2. **Bases.** Skipped entirely for a class with a collection proxy or a
   `std::pair` (`root/io/io/src/TStreamerInfo.cxx:3594`). Otherwise, for each
   element that is a base, in order: `acc_str(id, element name)`, then
   `acc_num(id, fBaseCheckSum)` — that is, `fMaxIndex[1]` (§9)
   (`root/io/io/src/TStreamerInfo.cxx:3596-3602`).
3. **Members.** Walk the elements again from the start, skipping bases. For each:
   - if the member is an enum, `acc_num(id, 1)`
     (`root/io/io/src/TStreamerInfo.cxx:3615-3620`);
   - `acc_str(id, member name)`;
   - `acc_str(id, resolved type name)` — typedefs resolved, `Long64_t` spellings
     normalised, STL default arguments dropped
     (`root/io/io/src/TStreamerInfo.cxx:3643-3656`);
   - for each of the first `fArrayDim` extents, `acc_num(id, fMaxIndex[i])`
     (`root/io/io/src/TStreamerInfo.cxx:3658-3660`);
   - the text between `[` and `]` in `fTitle`, if any, via `acc_str`
     (`root/io/io/src/TStreamerInfo.cxx:3664-3678`). **The `[` counts only when
     nothing but `/` and whitespace precedes it**, which is what
     `TVirtualStreamerInfo::GetElementCounterStart` enforces
     (`root/core/meta/src/TVirtualStreamerInfo.cxx:98-110`). A comment like
     `// x position [0, 1]` therefore folds **nothing**; only a leading
     `[fN]`-style counter does. Variants 6 and below use a plain search for `[`
     instead, and that is the one difference between variants 6 and 7.

**There are eight variants**, because the algorithm changed over time and old
files must still be matched (`root/core/meta/inc/TClass.h:111-122`):

**Each name describes what that variant lacks, but the tests in the code are
thresholds on the ordered value, not independent switches**, so a variant differs
from the current algorithm in every row whose threshold it fails — not only in the
one its name mentions. The five decisions, with the line that makes each:

| Decision | Applied when | Line |
|---|---|---|
| `+1` for an enum member | `code > kNoEnum`, so 2-8 | `:3620` |
| Type name **as recorded**, still sugared | `code <= kWithTypeDef`, so 1, 3, 4 | `:3632` |
| Type name **typedef-resolved**, `Long64_t` spelled out in full | `code` is 2 or 5 | `:3627-3630`, `:3646-3652` |
| Type name typedef-resolved and `Long64_t`-normalised | 6, 7, 8 | `:3641` |
| The comment text between `[` and `]` | `code > kNoRange`, so 4-8 | `:3664` |
| The strict `[` locator of step 3 rather than a plain search | `code > kNoRangeCheck`, so 7, 8 | `:3666-3669` |
| Each base's own checksum | `code > kNoBaseCheckSum`, so 8 only | `:3600-3602` |

| Value | Name | What it lacks relative to the current algorithm |
|---|---|---|
| 1 | `kNoEnum` | the enum `+1`, resolved type names, the comment text, the strict `[` locator, base checksums |
| 2 | `kReflexNoComment` | the comment text, `Long64_t` normalisation, the strict `[` locator, base checksums |
| 3 | `kNoRange` | resolved type names, the comment text, the strict `[` locator, base checksums |
| 4 | `kWithTypeDef` | resolved type names, the strict `[` locator, base checksums |
| 5 | `kReflex` | `Long64_t` normalisation, the strict `[` locator, base checksums |
| 6 | `kNoRangeCheck` | the strict `[` locator, base checksums |
| 7 | `kNoBaseCheckSum` | base checksums |
| 8 | `kLatestCheckSum` | nothing; this is the current algorithm |

Note that variants 2 and 5 **do** resolve typedefs — ROOT's header comment "has no
typedef at all" describes the resulting name, not the absence of resolution. What
they do instead of `GetLong64_Name` is substitute `unsigned long long`,
`long long` and `char` textually (`root/io/io/src/TStreamerInfo.cxx:3646-3652`).

A reader matching an old file SHOULD try variants 1 through 7 when the current
one does not match, which is what ROOT does
(`root/core/meta/src/TClass.cxx:6604-6609`).

> **The same class at the same version can carry two different checksums, and the
> layout is identical.** `TAttAxis` version 4 is `0x532a3b8c` in a ROOT 5.28 file
> and `0x5c6fff3e` in one 6.40.04 writes, with the same eleven members in the same
> order — the difference is that the old file's `fTypeName` spellings are `Int_t`
> and `Float_t` where the new one resolves them to `int` and `float`. So the
> variants are not only historical curiosities: they are why `BuildCheck` says
> nothing when it reads that file, and why a reader must not treat a checksum
> mismatch at equal version as evidence of a layout change.

Reference values, useful as test vectors:

| Class | Checksum |
|---|---|
| `TObject` | `0x901bc02d` |
| `TNamed` | `0xdfb74a3c` |
| `TString` | `0x00017419` |
| `TObjString` | `0x9c8e4800` |
| `TList` | `0x69c5c3bb` |
| `TObjArray` | `0xa99e6552` |
| `TStreamerInfo` | `0x90566883` |
| `TStreamerElement` | `0xdd0eb253` |
| `TStreamerBase` | `0x092715b0` |

### 11.1 An enum member is recognisable, and it changes the value

`TStreamerInfo::Build` stores every enum as an `Int_t` and gives it `fType` **3**
deliberately, to keep the file format unchanged across the introduction of
sized enums (`root/io/io/src/TStreamerInfo.cxx:675-689`) — so an enum member and an
`Int_t` member are indistinguishable by type code. They are distinguishable by
`fTypeName`, which keeps the enum's own qualified name: `TH1::EBinErrorOpt`, not
`int`.

That distinction decides the checksum, because an enum folds an extra `1` before
its name. **ROOT's own checksum code uses exactly that test** — `fType == 3` and a
type name `gROOT->GetType` does not resolve — under a comment asking whether it can
be done at all (`root/io/io/src/TStreamerInfo.cxx:3612-3620`). So the rule is not a
heuristic for a third party to invent; it is the rule, and a reader can apply it
with no dictionary by treating any `fType` 3 whose `fTypeName` is not a primitive
spelling as an enum.

`TH1`'s recorded `0x1c3740c4` is reproduced exactly when `fBinStatErrOpt` and
`fStatOverflows` are treated this way and not otherwise.

### 11.2 What cannot be recomputed

**The checksum is computed from the class definition, not from the streamer info**
(`root/core/meta/src/TClass.cxx:6604-6609`), and the two do not always contain the
same information. Measured over every streamer info in this repository's reference
files — **743 of them, of which 698 are reproduced exactly** by §11's algorithm
applied to the info's own elements, `tools/test_write.py` — the remainder fall into
three groups, and every one of them has a named cause:

| Cause | Classes | What the info lacks |
|---|---|---|
| **A version-0 class lists no members** | `THashList`, `TSeqCollection` | `TStreamerInfo::Build` skips every member of a class whose version is 0 (`root/io/io/src/TStreamerInfo.cxx:552-554`), but the checksum still folds them. `THashList`'s `0xcc7e49c1` is reproduced by adding `fTable`/`THashTable*` by hand |
| **A member ROOT rewrote for I/O** | `TF1`, `CollectionForms` | `std::array<Int_t,3>` is recorded as a fixed C array of `int` with `fArrayDim` 1, and `std::unique_ptr<T>` as `T*` — but the checksum folds the **declared** type name and no extents. `CollectionForms` is reproduced with `array<int,3>`; `TF1` with `unique_ptr<TFormula,default_delete<TFormula> >`, default template argument spelled out |
| **ROOT's own value is wrong** | three `pair<…>` instances | A `pair`'s checksum can be computed before its members are known and is then cached forever (`root/core/meta/src/TClass.cxx:6655-6666`); `data/serialization/pairs.root` has three distinct pairs all carrying `0x0b5fb752`, and the fourth pair in the same file is correct and recomputable |

**For a reader** the consequence is narrow: matching an object to an info by
checksum uses the value *in the file*, which is always self-consistent, so none of
this affects decoding. It matters when checking a file, or when writing one.

**For a writer** the consequence is that the checksum must be computed from the
class as declared — including the `+1` per enum member and the declared spelling of
a rewritten member — and not from the element list about to be emitted. See
[Writing an object §7.3](../06-writing/WritingObjects.md#73-the-checksum).
## 12. Reading

1. If `fSeekInfo` is 0 or not greater than `fBEGIN`, the file records no streamer
   information.
2. Read the record at `fSeekInfo`, of `fNbytesInfo` bytes, and decompress its
   payload if `fNbytes - fKeylen != fObjlen`.
3. Parse the payload as a `TList` (§4). Remember that buffer positions count from
   the start of the **key** ([Buffer framing §1](Buffer.md#1-what-a-buffer-is)).
4. For each entry, resolve its class from the class tag or class back-reference.
   If it is not `TStreamerInfo`, seek past it using its byte count and continue.
5. For a `TStreamerInfo`, read the `TNamed` base, `fCheckSum`, `fClassVersion`,
   then the `fElements` slot as a `TObjArray` (§5).
6. For each array entry, resolve its class — one of the subclasses in §8 — and
   read the subclass record, the `TStreamerElement` base (§7), and the subclass
   tail.
7. Apply the fixups of §7.2, and for an STL element the reconstruction of §10.
8. Index the results by class name and by `fClassVersion`, and by `fCheckSum` for
   the version-0 case.

## 13. Invariants

1. The `StreamerInfo` key has `fClassName` `"TList"` and `fName`
   `"StreamerInfo"`, and `fSeekInfo` equals its `fSeekKey`, `fNbytesInfo` its
   `fNbytes`.
2. Every entry of the outer list is either a `TStreamerInfo` or a `TList` named
   `listOfRules`.
3. Every `TStreamerInfo` has a non-empty `fName`, and `fClassVersion >= 0`.
4. No two infos share both a class name and an `fClassVersion`, **except** where
   `fClassVersion` is 1 and the checksums differ, which is legitimate.
5. Every element's concrete class is one of the eleven in §8 that can be written.
   `TStreamerArtificial` never appears.
6. Every element's `fType` is in the on-disk set of
   [Element types §1](ElementTypes.md#1-the-type-codes).
7. For a `TStreamerBase` whose base class also has an info in the same file,
   `fMaxIndex[1]` read as unsigned is **either 0 or** that info's `fCheckSum`. It
   is 0 on every file written before ROOT 6 (§9.1).
8. A `TStreamerBase` has `fTypeName` `"BASE"`, and `fType` is 0, 66, 67 or -1.
9. Every `TStreamerSTL` and `TStreamerSTLstring` has `fType == 500` on disk,
   on a file written by ROOT 5 or later. ROOT 4 wrote the real code (§10.1).
10. A `TStreamerBasicPointer` or `TStreamerLoop` has a non-empty `fCountName`,
    and the info named by its `fCountClass` — this one, or a base — has an element
    of that name. `TArrayD`'s `fArray` names `fN` in `TArray`, its base
    ([Streamer-driven reading §3.2](StreamerDriven.md#32-elements-are-not-independent)).
11. `fArrayDim` is between 0 and 5, and when it is non-zero the first `fArrayDim`
    entries of `fMaxIndex` are all positive and their product equals
    `fArrayLength`.
12. The bytes consumed by the outer list equal `fObjlen` exactly.

Invariant 11 is the one that legitimately fails: an STL element's `fArrayDim` was
not written at all before ROOT 6.24/02 (§10).

## 14. Errata

Against `root/io/doc/TFile/streamerinfo.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | The `StreamerInfo` list is "always compressed at level 1 (even if compression level 0)" | It uses the file's own algorithm and level, and is uncompressed when the level is 0. In `container/file-minimal` the record satisfies `fNbytes - fKeylen == fObjlen` (§2) |
| 2 | The list's elements are "sequentially, TStreamerInfo objects" | Each entry is followed by a `TList` option length byte. This was already true in 3.02.06, where `TList` was version 4, so the document is wrong even for its own release; a reader following it desynchronises after the first entry (§4) |
| 3 | The list holds only `TStreamerInfo` objects, one per class used in data records | It may end with a `TList` named `listOfRules`, and it may contain infos for the bootstrap classes themselves (§3.1, §3.3) |
| 4 | — | An empty list is written deliberately and means "no classes described" (§3.2) |
| 5 | `fMaxIndex` is "five integers" at a fixed offset | True from `TStreamerElement` version 2. Version 1 wrote a counted array (§7.1) |
| 6 | `TStreamerElement` ends after `fTypeName` | True for versions 2 and 4, wrong for version **3**, which appends `fXmin`, `fXmax` and `fFactor` (§7.1) |
| 7 | `fMaxIndex` holds array dimensions, 0 if not applicable | For a `TStreamerBase`, `fMaxIndex[1]` is the base class's **checksum** (§9) — or 0, on a file written by ROOT 5 (§9.1) |
| 8 | "For TStreamerInfoBase: fBaseVersion" | The class is `TStreamerBase`, and `fBaseVersion` is present only for version > 2 (§8) |
| 9 | — | `fBits` of both `TStreamerInfo` and `TStreamerElement` is persisted and load-bearing: `kIgnoreTObjectStreamer` removes the `TObject` base from every object of the class, and `kHasRange` is required to decode a `Double32_t`. A `FIXME` in ROOT asserting the info's bits are never saved (`root/io/io/src/TStreamerInfo.cxx:1400-1405`) is wrong — `serialization/streamer-info` has `fBits` `0x00010000` on disk |
| 10 | `TStreamerBasicPointer`'s third member is `fCountName` (listed twice) | The third member is `fCountClass` (§8) |
| 11 | `fSTLtype`: "5:set, 6:multimap" | Current numbering is **5 multimap, 6 set**, and ROOT carries a fixup for exactly this historical inversion (§10) |
| 12 | The `fSTLtype` list stops at 7 | It continues to 14: bitset, forward_list, the unordered containers, and `RVec` (§10) |
| 13 | `TStreamerSTL`/`TStreamerSTLstring` are "(not yet used??)" | Both are in constant use, and both store `fType = 500` rather than their real code (§10) |
| 14 | `fSize` is "size of built in type or of pointer to built in type, 0 otherwise" | It is non-zero for every element class and is the writer's `sizeof`: 24 for a `TString`, 16 for a `TObject` base (§7) |
| 15 | — | The key is removed from the directory's key list, so the record can only be found through `fSeekInfo` (§2) |
| 16 | — | No checksum algorithm is given, and the eight variants needed to match older files are not mentioned (§11) |

## 15. Reference files

| Case | Exercises |
|---|---|
| `serialization/streamer-info` | The whole chain: `TList`, `TStreamerInfo`, `TNamed`, `TObjArray`, and four element subclasses including `TStreamerSTL` |
| `serialization/object-tags` | `TStreamerBase` for a `TObject` base, and a class back-reference between two infos |
| `serialization/version-zero` | Fourteen infos and seventy-one elements, from `TH1L`'s whole class hierarchy |
| `serialization/schema-rules` | The optional `listOfRules` entry alongside a `TStreamerInfo` |
| `serialization/collections` | `TStreamerSTL` in seven shapes, and the only `TStreamerSTLstring` in the corpus |

No fixture covers `TStreamerLoop`, `TStreamerArtificial` (which cannot occur —
§14), or any `TStreamerElement` version below 4; the last needs a file written by
ROOT 3.
