# Streamer information

Every ROOT file contains a description of the classes stored in it, which makes
the format self-describing. The code that reads this description is the one part
of a reader the description cannot drive.

Prerequisites: [Conventions](../00-conventions.md),
[Records and keys](../01-container/Record.md),
[Buffer framing](Buffer.md). All integers are big-endian.

This document describes how to **read** an info. What a writer has to **put** in
one, for each class a histogram or a flat tree contains, is in
[Element lists](../06-writing/ElementLists.md).

## 1. The bootstrap problem

The streamer information is stored as ordinary objects of ordinary classes:
`TList`, `TObjArray`, `TStreamerInfo`, `TStreamerElement` and its subclasses. To
read the description of a class you must already be able to read those, and the
file does not reliably describe them.

> **A reader MUST hardcode the layouts in this document. There is no way to
> bootstrap them out of the file.**

This is less of a burden than it sounds:

- The set is small: six classes, plus the eleven element subclasses that can
  appear in a file.
  [Bootstrap classes §3](../99-appendix/Bootstrap.md#3-group-a-needed-before-anything-can-be-read)
  lists it, and §4–§8 below give the layouts.
- Once these are parsed, the streamer information describes everything else,
  including classes the reader has never heard of.

A file may also contain streamer info for these classes (§3.3), but a reader
MUST NOT depend on that either way.

## 2. Finding the record

`fSeekInfo` gives the record's offset and `fNbytesInfo` its total length
including the key
([File header §5.5](../01-container/FileHeader.md#55-fseekinfo-fnbytesinfo)).
The record is read only when `fSeekInfo` is greater than `fBEGIN`
(`root/io/io/src/TFile.cxx:921`).

Its key has `fClassName` `"TList"`, `fName` `"StreamerInfo"` and `fTitle`
`"Doubly linked list"`. The title is `TList`'s class comment, not something chosen
for this record.

> **The key is deliberately removed from the directory's key list.**
> `WriteStreamerInfo` creates the key and immediately removes it
> (`root/io/io/src/TFile.cxx:3554-3555`), so it cannot be found by name. A reader
> MUST locate the record through `fSeekInfo`.

The payload is compressed like any other record: with the file's algorithm and
level, and only when the level is non-zero and the payload exceeds 256 bytes
(`root/io/io/src/TKey.cxx:262-264`).

Rewriting the record frees the old one (`root/io/io/src/TFile.cxx:3552`), so a
reader walking the record chain of an updated file will find deleted
`StreamerInfo` records. They are ordinary free spans
([Free segments §4](../01-container/FreeSegments.md#4-the-in-place-marker)).

## 3. What the list contains

The payload is a `TList` (§4). Its entries are:

- one `TStreamerInfo` per described class, in no guaranteed order;
- optionally, one `TList` named `listOfRules` as the last entry.

### 3.1 `listOfRules`

Present only when the file has I/O customisation rules to record
(`root/io/io/src/TFile.cxx:3546-3549`). Its entries are `TObjString`s, each
holding one rule rendered as text.

A reader that does not implement schema-evolution rules MUST still skip this
entry correctly. The byte count makes that easy: any entry whose class is not
`TStreamerInfo` is skipped by seeking past the object's byte count
([Buffer framing §8](Buffer.md#8-reading)). It is safer to dispatch on the class
name than on position, because the rules list is last only by current convention.

ROOT itself currently ignores the rules it writes: the loop that would apply them
is inside `#if 0` (`root/io/io/src/TFile.cxx:3364-3373`).

[Schema evolution §6](SchemaEvolution.md#6-rules-and-the-listofrules-entry) gives
the full shape and the reason ROOT ignores it.

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
is written to a file after a `StreamerInfo` record already exists, the next record
can therefore include `TList`, `TNamed`, `TStreamerElement` and the rest.

A reader MUST neither rely on those entries being present nor be confused by
them. In particular it MUST NOT use them in place of the hardcoded layouts: for a
class with a hand-written streamer, the recorded info does **not** describe the
bytes. `TString`'s info, for example, lists no members at all.

### 3.4 "In no guaranteed order" is stronger than it sounds

The order is not merely unspecified; **it does not depend on the file's content
at all.** `TFile::WriteStreamerInfo` iterates `gROOT->GetListOfStreamerInfo()`
(`root/io/io/src/TFile.cxx:3509`) and keeps the entries `fClassIndex` has marked.
The order on disk is therefore the order in which `TStreamerInfo` objects were
registered in the writing process. That follows dictionary and shared-library
initialisation, not anything about the objects being written.

`classes/canvas` shows this. Written by the same ROOT 6.40.04 from the same
`gen.C`, it holds the same fourteen infos with the same names, versions,
checksums and element counts, in a 14982-byte record on both platforms, but in a
different order on libc++ and libstdc++. A canvas is the first fixture to show it
because it draws infos from libCore, libGraf and libGpad at once.

Consequences:

- A reader MUST look entries up by name and version, never by position, and MUST
  NOT assume a base class's info precedes the class that uses it.
- The record cannot be normalised into a canonical order for comparison, because
  it stores class and object back-references as byte positions (§4,
  [Buffer framing §6](Buffer.md)). The same infos in a different order differ
  throughout. `classes/canvas` therefore declares `digest = false`; it is the only
  fixture here that does so because of ordering rather than content.

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

> **The option length byte is the most common cause of desynchronising on this
> record.** It follows every entry, including when the option is empty, in which
> case it is a single `0x00` byte. In a `StreamerInfo` record every option is
> empty, so the list is a sequence of `object slot, 0x00` pairs
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

Unlike `TList`, there is no per-entry option string. The entry count is the index
of the last occupied slot plus one, so trailing empty slots are not written;
interior holes appear as null slots.

## 6. `TStreamerInfo`

Hand-written (`root/io/io/src/TStreamerInfo.cxx:5608`). Current version 10
(`root/io/io/inc/TStreamerInfo.h:256`).

| Field | Type | Notes |
|---|---|---|
| byte count | `u32` with `kByteCountMask` | |
| version | `i16` | 10 currently |
| `TNamed` base | nested record | `fName` is the **described class**; `fTitle` its comment |
| `fCheckSum` | `u32` | §11 |
| `fClassVersion` | `i32` | written as its absolute value |
| `fElements` | object slot | a `TObjArray` of elements |

**The layout is the same for every version from 1 to 10**
(`root/io/io/src/TStreamerInfo.cxx:5679-5707`). The version number marks a change
in semantics, not in layout, and a reader needs it only for the behaviours in
§6.1.

`fClassVersion` is written as `|fClassVersion|`
(`root/io/io/src/TStreamerInfo.cxx:5686`), so a negative in-memory version cannot
be recovered from the file.

`fElements` is not the in-memory element array. A temporary array is built first,
dropping every `TStreamerArtificial`, every element with `kRepeat`, and every
element with `kCache` but not `kWrite`
(`root/io/io/src/TStreamerInfo.cxx:5694-5706`). It is written with
`cacheReuse = kFALSE` (`root/io/io/src/TStreamerInfo.cxx:5707`), so each info has
its own complete `TObjArray` record rather than a back-reference to a shared one.
The class `TObjArray` is still back-referenced after the first occurrence.

The info's `fBits` is persisted, and one of its bits changes how objects are read:

| Bit | Name | Meaning |
|---|---|---|
| 13 | `kIgnoreTObjectStreamer` | objects of the described class carry **no** `TObject` bytes |
| 16 | `kIsCompiled` | an artefact of the writer; reset on read and ignorable |

Values at `root/core/meta/inc/TVirtualStreamerInfo.h:74`.

> Demonstrated by `serialization/streamer-info`: `fBits` at offset 521 is
> `0x00010000`, i.e. `kIsCompiled` alone.

A `FIXME` in ROOT claims these bits are never saved to the file
(`root/io/io/src/TStreamerInfo.cxx:1400-1405`). That comment is wrong; see §14,
erratum 9.

### 6.1 Version-dependent reader behaviour

The version does not change the layout, but it does change how member data of the
described classes must later be decoded:

| Version | Consequence |
|---|---|
| 1 | a record that does not end at its byte count is reported (`CheckByteCount`, `root/io/io/src/TStreamerInfo.cxx:5677`); from 2 on ROOT seeks to the byte count's end without a word (`:5628`). Both read on from the end |
| < 3 | a legacy collection encoding applies to that class's STL members; an 85, 86 or 87 element whose frame does not match is taken as not written ([Element types §7.2](ElementTypes.md#72-the-array-forms-are-not-uniform)) |
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

> `fSize` is `sizeof` on the machine that wrote the file: 24 for a `TString`, 4
> for an `Int_t*` counted array (the pointee), 8 for a `char*` (the pointer). A
> reader MUST derive on-disk widths from `fType`, never from `fSize`.
>
> Demonstrated by `serialization/streamer-info`: `fStr` has `fType` 65 and
> `fSize` 24, while its on-disk form is a counted string of 2 bytes.

**`fSize` makes a streamer info platform dependent.** Two ROOT builds of the same
version on the same architecture write different streamer info bytes for the same
class whenever `sizeof` differs between their standard libraries:
`sizeof(std::string)` is 24 with libc++ and 32 with libstdc++, and
`sizeof(std::map<int,int>)` is 24 and 48. Nothing else in the record varies, so a
reader does not see the difference. But two files describing the same class
cannot be compared byte for byte across platforms, and any tool that digests a
file must mask `fSize` first. `tools/normalize.py` in this repository does, and
that is the only reason a fixture here can contain a `std::string` or `std::map`
member. The problem was found when such a fixture drifted between macOS and Linux
CI while every byte assertion passed and the file size was identical.

### 7.1 The range fields moved out of the record

Version 3 stored `fXmin`, `fXmax` and `fFactor` as three doubles. Version 4 does
not store them at all. Instead, when the `kHasRange` bit (`BIT(6)`,
`root/core/meta/inc/TStreamerElement.h:71`) is set in the element's own `fBits`,
they are recomputed by re-parsing `fTitle`
(`root/core/meta/src/TStreamerElement.cxx:579-586`).

> **In a current file the `Double32_t`/`Float16_t` quantisation parameters are
> encoded in the element's comment string, and the on-disk width of such a member
> cannot be determined without parsing it.** The grammar and the arithmetic are in
> [Element types §5](ElementTypes.md#5-kdouble32-and-kfloat16).

Version 1 also differs in `fMaxIndex`, which it wrote as a counted array (an
`i32` count followed by that many values) rather than as exactly five
(`root/core/meta/src/TStreamerElement.cxx:562-563`).

| Version | `fMaxIndex` | Range fields |
|---|---|---|
| 1 | counted: `n:i32` then `n` × `i32` | absent |
| 2 | 5 × `i32` | absent |
| 3 | 5 × `i32` | **present**, 3 × `f64` |
| 4 | 5 × `i32` | absent; recovered from `fTitle` |

**Version 3 was never released.** It existed for three days on the development
trunk, all of them at version 4.03/05: root commit `ccca6c91c4a` (2005-04-18)
introduced it with the extended `Double32_t`, and `81aa9214fd3` (2005-04-21) made
the three fields transient again as version 4, *"so that files written by this
new version of ROOT are readable without any warning messages by older versions"*.
No release tag in the submodule has it; `v4-04-02` already has version 4. A file
with version-3 elements was therefore written by a development build.

> One such file is `root/roottest/root/io/evolution/skim.root`, from ROOT
> 4.03/05. Each of its 223 elements with a version-3 `TStreamerElement` base has
> 24 bytes after `fTypeName`: the three doubles, all zero here because no member
> declares a range. Those 223 are every version-3 element in `root/roottest/`,
> `gen/cern/` and `gen/foreign/` together, against 60 835 at version 4 and 8 364
> at version 2. The subclass version is a separate number: the file's
> `TStreamerBase` elements are at `TStreamerBase` version 3, the version that
> added `fBaseVersion` (§8), which says nothing about their `TStreamerElement`
> base.

### 7.2 Read-time fixups

A reader MUST apply these after reading an element. ROOT's own reader applies
them, and the rest of the format assumes the values they produce:

| Condition | Action |
|---|---|
| `fType == 11` and `fTypeName` is `"Bool_t"` or `"bool"` | set `fType = 18` (`root/core/meta/src/TStreamerElement.cxx:566`) |
| version ≤ 2 and the class is `TStreamerBasicType` | `fSize` meant the *element* size, not the member size; recompute it (`root/core/meta/src/TStreamerElement.cxx:572-577`) |
| version == 3 and `fFactor > 0` | set `kHasRange` (`root/core/meta/src/TStreamerElement.cxx:583`) |
| version > 3 and `kHasRange` set | parse `fTitle` for the range (`root/core/meta/src/TStreamerElement.cxx:586`) |

### 7.3 `fTypeName` is not always spelled as the info it names

An info is named by its class's normalised name: typedefs resolved, `long long`
spelled `Long64_t`, and `std::` and the STL's default template arguments dropped
(`TClassEdit::GetNormalizedName`,
`root/core/foundation/src/TClassEdit.cxx:924-925`). An element's `fTypeName`
need not be spelled the same way. Before 6.00/00 `Build` recorded the member's
declared spelling, `GetFullTypeName()`
(`v5-34-18:io/io/src/TStreamerInfo.cxx:325`). Root commit `452898f2b72`
(2014-05-21, first in 6.00/00) switched to `GetTrueTypeName()`
(`root/io/io/src/TStreamerInfo.cxx:573`), and its message gives the reason:
"With the typedef in the name, the ROOT file is not self describing". ROOT
joins the two spellings through its interpreter, in `TClass::GetClass`; a reader
with only the file has to do it by rule.

Measured over `data/`, both corpora and 271 files of `root/roottest/`. The
renamings a reader can resolve occur only in `root/roottest/`:

| Mechanism | Elements | Files (writer) | Example |
|---|---|---|---|
| a ROOT typedef of a fundamental type as a template argument | 4 | `checksum_v5.root`, `checksum_v53418.root` (5.34/18), `pairs_v5.root` (5.34/19), `checksum_v6.root` (5.99/06) | `UserTmplt<Int_t>`, info `UserTmplt<int>` |
| `unsigned long long` for `ULong64_t` | 1 | `lariat-si.root` (6.11/01) | `artdaq::QuickVec<unsigned long long>`, info `artdaq::QuickVec<ULong64_t>` |
| a default template argument of a non-STL class left out | 8 | `CMSSW_3_1_0_pre11-RelValZTT-default-copy.root` (5.22/00) | `PositionVector3D<Cartesian3D<Double32_t> >`, info `…,ROOT::Math::DefaultCoordinateSystemTag>` |
| the enclosing namespace left out | 1 | `nestedColl.root` (5.34/33) | `vector<OtherInner>` in `HepExp::Outer`, info `HepExp::OtherInner` |

ROOT 6.40.04 resolves `TClass::GetClass("UserTmplt<Int_t>")` to
`UserTmplt<int>`, and roottest's `io/emulated/execROOT8804.C` exists to check that
`artdaq::QuickVec<unsigned long long>` finds the `ULong64_t` info. It also writes
names that match: an interpreted class with members of `UserTmplt<Int_t>`,
`vector<Int_t>`, `vector<Named_t>` (a typedef of `TNamed`),
`UserTmplt<long long>` and `PositionVector3D<Cartesian3D<Double32_t> >` records
`UserTmplt<int>`, `vector<int>`, `vector<TNamed>`, `UserTmplt<Long64_t>` and the
name with `DefaultCoordinateSystemTag`, as the infos do. Without the classes' dictionaries,
ROOT 6.40.04 cannot read `nestedColl.root`'s collections of `OtherInner`
(`CheckByteCount … vector<OtherInner> read too few bytes: 6 instead of 20`).

**A reader MUST match a class name in an element to an info in this order,**
taking the first step that finds one:

1. The name as written.
2. The name with its spelling made uniform: ROOT's typedefs of fundamental
   types resolved wherever one stands as a whole template argument
   (`root/core/foundation/inc/RtypesCore.h:51-103`), except `Double32_t` and
   `Float16_t`, which change the bytes and so stay in the normalised name;
   `long long` and `unsigned long long` as `Long64_t` and `ULong64_t`; `std::`
   dropped and whitespace normalised. For an unqualified name, first try it
   qualified by each enclosing scope of the class that holds the element,
   innermost first, as C++ name lookup would. A user's typedef cannot be
   resolved, because the file does not record it
   ([Collections §9](Collections.md#9-the-value-classs-streamer-info-can-be-missing-entirely)).
3. The same, allowing trailing template arguments to be left out at any depth,
   provided exactly one info matches.
4. Where the bytes hold a version word of 0 and a checksum
   ([Buffer framing §4](Buffer.md#4-a-version-word-of-0-has-two-different-meanings)),
   the one class in the file whose info has that checksum, provided exactly one
   has it. Never for a `pair`, whose checksums collide
   ([Collections §8.2](Collections.md#82-the-checksum-does-not-identify-the-pair)),
   and never for the class the record's key names: a `TBasket` payload is not an
   object of its key's class, and it can begin with an object whose checksum is
   unique in the file.

Step 4 goes beyond ROOT, which looks a checksum up only among the infos of a
class it has already resolved by name
([Collections §11.2](Collections.md#112-a-class-that-is-a-collection-the-this-element)).
It is what reads the collections of `nestedColl.root`: `fValue`, a
`vector<OtherInner>`, is `40 09 | 00 00 f6 4a b7 e0 | …`, member-wise with
value-class version 0 and checksum `0xf64ab7e0`, `HepExp::OtherInner`'s, and
`fAlias`, a `vector<Alias>` with `typedef Inner Alias;`, carries
`HepExp::Inner`'s `0xcfdf7f18`. It is also the only step that resolves a name no
class has. In `output_Coulomb_LER_study_10.root`, ROOT 6.07/01 recorded the type
of `m_stats[6]` (code 82) as
`Belle2::ModuleStatistics::CalcMeanCov<2,value_type>`, and ROOT 6.40.04 reports
that it "Cannot determine alignment" for that type. Every object in the array is
`40 00 00 36 | 00 00 | b1 66 76 3d | …`, and `0xb166763d` is the checksum of
`Belle2::CalcMeanCov<2,double>`, whose info then reads each object's 54 bytes
exactly. The name is still the writer's fault, and
[Streamer-driven reading](StreamerDriven.md#10-invariants) invariant 5, which
takes steps 1 to 3 only, fails on that element.

## 8. The element subclasses

Each subclass record starts with its own byte count and version, followed by the
`TStreamerElement` base record and then the subclass's own members. The nesting is
therefore `TStreamerXxx` → `TStreamerElement` → `TNamed` → `TObject`, with a byte
count at each of the first three levels and only a version word at `TObject`.

| Class | Version | Members after the base |
|---|---|---|
| `TStreamerBase` | 3 | `fBaseVersion`: `i32`, **version > 2 only** |
| `TStreamerBasicType` | 2 | none |
| `TStreamerBasicPointer` | 2 | `fCountVersion`: `i32`, `fCountName`: counted string, `fCountClass`: counted string |
| `TStreamerLoop` | 2 | `fCountVersion`: `i32`, `fCountName`: counted string, `fCountClass`: counted string |
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

`fCountVersion` is unused (`root/core/meta/inc/TStreamerElement.h:202`). The
length of a counted array is the value of the member named by `fCountName`, read
from the object itself; it is never written separately in the stream.

> Demonstrated by `serialization/streamer-info`, which contains one each of
> `TStreamerBasicType`, `TStreamerString`, `TStreamerSTL` and
> `TStreamerBasicPointer`, with `fCountName` `"fN"` and `fCountClass` `"Members"`
> on the last.

## 9. `TStreamerBase`, and a checksum hidden in `fMaxIndex`

> **`fBaseCheckSum` is a reference bound to `fMaxIndex[1]`**
> (`root/core/meta/inc/TStreamerElement.h:154`,
> `root/core/meta/src/TStreamerElement.cxx:646`).

A base class's checksum is therefore stored in the `TStreamerElement` base's
extent array, in a slot that holds an array dimension for any other element. A
comment in `TStreamerBase::Streamer` asks for a version that would store
`fBaseCheckSum` directly (`root/core/meta/src/TStreamerElement.cxx:866-868`).

`fMaxIndex` is declared `Int_t` but `fBaseCheckSum` is a `UInt_t`, so **a
checksum with its top bit set reads back negative** and must be reinterpreted as
unsigned. `TObject`'s checksum, `0x901bc02d`, is one such value.

> Verified across the fixtures and both corpora: every `TStreamerBase` whose base
> class also has an info in the same file has `fMaxIndex[1]` equal to that info's
> `fCheckSum`, or 0. There are 787 such pairs and no exceptions, and
> `tools/check_invariants.py` asserts it. The corresponding claim about
> `fBaseVersion` does **not** hold (§9.2).

### 9.1 It is 0 on a file written before 5.34/19

**`fBaseCheckSum` did not exist before 5.34/19 and 6.00/00.** It was added by
`185b44f3d96`, "Add checksum value to TStreamerBase", on 2014-04-21, first
released in 6.00/00, and backported the same day as `6a41fa086cb`, first tagged
`v5-34-19`. Before that the slot was never filled, so every `TStreamerBase` in a
file from an earlier ROOT 5 release, or from the 5.99 development series before
5.99/07, has `fMaxIndex[1] == 0`, at the same `TStreamerBase` class version 3 and
with no other difference. ROOT's own reader encodes the same boundary: it fills
the checksum in only when the file's version is below 53419 or between 59900 and
59907 (`root/io/io/src/TFile.cxx:3322`), taking it from the first info of that
name in the file (`:3322-3345`). A reader MUST accept
0 and fall back to `fBaseVersion`, and must be prepared for that to fail too;
§9.2 shows it failing on four ROOT-published files.

> Measured across the version sweep in the foreign corpus of `PLAN.md` §9.8, which
> brackets the change: `uproot-sample-5.23.02` through `5.30.00` have 23
> `TStreamerBase` elements each and all 23 are 0; `6.08.04` through `6.20.04`
> have 22 each and none is. Files from 5.34/23 to 5.34/38 in roottest and the
> foreign corpus (`v5formula_clones.root`, `geodemo.root`, `uproot-issue431.root`
> and others) have the checksum, and 5.99/01 to 5.99/06 files do not, as the
> backport and `TFile.cxx:3322` predict.

> The slot can also be 0 for a reason unrelated to the ROOT version.
> `fBaseCheckSum` is set in the constructor from `fBaseClass->GetCheckSum()`
> (`root/core/meta/src/TStreamerElement.cxx:677`), so it is 0 whenever the writing
> process did not have the base class loaded, for example for an emulated class.

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

### 9.2 `fBaseVersion` may name a version the file does not contain

`fBaseCheckSum` identifies a layout. `fBaseVersion` records the base class's
version at the time the derived class's info was built
(`root/core/meta/src/TStreamerElement.cxx:672-674`), and the info can be reused
after that: carried into a later file by a fast clone, or read from an older file
and written out again. A record can therefore hold a base element giving version
*n* beside an info for that class at version *n + 1*, and both are correct.

Five files in the corpora contain such a mismatch. They fall into two cases, and
only the first is benign:

| File | ROOT | Element | `fBaseVersion` | The base info in the file | `fBaseCheckSum` |
|---|---|---|---|---|---|
| `uproot-mc10events.root` | 6.08/04 | `TTree`'s `TAttLine` | 1 | version 2 | `0x94074549` — **the version-2 info's checksum** |
| `uproot-mc10events.root` | 6.08/04 | `TTree`'s and `TBranch`'s `TAttFill` | 1 | version 2 | `0xffd92a92`, likewise |
| `aleph.root`, `atlas.root`, `cms.root` | 5.17/09 | `TGeoVolumeMulti`'s `TGeoVolume` | 4 | version 5 | **0** |
| `hades.root` | 5.17/09 | `TGeoMixture`'s `TGeoMaterial` | 4 | version 5 | **0** |

In the first case the checksum resolves the mismatch: it matches the version-2
info, the only one in the file, so a reader that prefers the checksum is right
and the version is merely stale.

**The second case breaks the fallback of §9.1.** These are ROOT 5 files, so
`fBaseCheckSum` is 0 and §9.1 falls back to `fBaseVersion`, which is 4 while the
file's only info for the base (`TGeoVolume` or `TGeoMaterial`) is version 5.
The fallback finds nothing, so §9.1's instruction needs a third step:

1. `fBaseCheckSum`, when it is non-zero;
2. otherwise `fBaseVersion`, when the file has an info for the base at that
   version;
3. **otherwise the info the file does have for that class**, which is the only
   description of the base available. These four files require this step.

A reader that stops after step 2 finds no layout for the base, and so cannot
decode a `TGeoVolumeMulti` in three files published by the ROOT team or a
`TGeoMixture` in the fourth. `tools/rootfile.py` reaches step 3 because it never
consults `fBaseVersion`, which is why it decodes the corpora. That is a side
effect of its design, not a recommendation; step 3 is the rule.

## 10. `TStreamerSTL` stores a type code it does not mean

> **On disk, every `TStreamerSTL` and `TStreamerSTLstring` has
> `fType = 500` (`kStreamer`).** Every ROOT-written file available stores 500
> there, back to ROOT 3.04. §10.1 covers the exceptions: releases before 4.00/01
> in one case, and third-party writers.

The write path builds a default-constructed temporary, copies the fields it needs,
sets `fType = kStreamer`, and writes the temporary; a comment says this is for
forward compatibility (`root/core/meta/src/TStreamerElement.cxx:2140-2155`). The
read path discards the stored value entirely
(`root/core/meta/src/TStreamerElement.cxx:2124-2128`):

```
fType = IsaPointer() ? kSTLp (71) : kSTL (300)
if (fArrayLength > 0) fType += kOffsetL (20)
```

`IsaPointer()` means `fTypeName` ends in `*`. As a result `kSTL` (300), `kSTLp`
(71) and `kSTLstring` (365) **never appear as an `fType` in a file**, and a reader
that trusts the stored 500 will treat every STL member as an opaque custom
streamer.

> Demonstrated by `serialization/streamer-info`: `fVec`, a `std::vector<int>`, has
> `fType` 500 at offset 841, with `fSTLtype` 1 and `fCtype` 3 identifying the real
> type. `TFile::ShowStreamerInfo` prints 300 for the same element.

Because the temporary is default-constructed, the element's status bits are lost:
`kHasRange` and `kDoNotDelete` never survive for an STL element.

The read path also reconstructs two fields:

- If `fArrayDim == 0` and `fArrayLength > 0`, recover the rank by counting
  non-zero `fMaxIndex` entries
  (`root/core/meta/src/TStreamerElement.cxx:2106-2111`). ROOT before 6.24/02
  did not copy `fArrayDim` into the temporary. On master the fix (commits
  `c7feb0e9cf7` and `43c17b87fe4`, 2021-05-05) was first tagged `v6-25-02`, so
  the development release 6.25/01 still has the old behaviour.
- `fSTLtype` values 5 and 6 are ambiguous across ROOT versions and must be
  re-derived from `fTypeName` (`root/core/meta/src/TStreamerElement.cxx:2112-2122`).
  Current numbering has **5 = multimap, 6 = set**
  (`root/core/foundation/inc/ESTLType.h:28-50`); older ROOT had them the other way
  round.

### 10.1 Where the stored code is not 500

The write path has stored 500 unconditionally since ROOT 4.00/01. Root commit
`2b412e44cbd` (2004-01-10), which introduced the current collection I/O, added the
override and its forward-compatibility comment to `TStreamerSTL::Streamer`; it is
at tag `v4-00-01` (`meta/src/TStreamerElement.cxx`, lines 1427-1433 there).

Before that the element was written as it stood in memory. The constructor set
`kSTL` (300), and `TStreamerSTL::SetStreamer` replaced it with 500 whenever the
class's dictionary supplied a streamer function for the member, which is the
usual case for a compiled class (`meta/src/TStreamerElement.cxx` at tag
`v3-10-02`, lines 1161 and 1283-1292). A release before 4.00/01 could therefore
store 300 for an STL member that had no such function. No available file shows
it.

Third-party writers do store the real code. g4tools, Geant4's own ROOT writer,
writes 300 for a `TStreamerSTL`
([Buffer framing §2.3](Buffer.md#23-a-records-object-data-does-not-always-begin-with-one) identifies its
files). The read path overwrites `fType` from `fSTLtype` and `fCtype` whatever was
stored, so a reader that follows it reads these files correctly. A reader that
switches on the stored code takes a different path on them, and SHOULD accept 300
here as meaning the same as 500.

> Measured over `root/roottest/`, `gen/foreign/` and `gen/cern/`: 134 STL
> elements in twelve files written by ROOT before 5, from 3.04/02 to 4.04/02, all
> store 500, as does every element written by ROOT 5 or 6. The only other value
> is 300, on 18 `TStreamerSTL` elements, nine each in `uproot-from-geant4.root`
> and `uproot-issue-250.root`. Their headers claim ROOT 4.00/00, but g4tools
> wrote them, with keys dated 2018-2020.

## 11. Checksums

A checksum identifies a class layout when a version number cannot
([Buffer framing §4](Buffer.md#4-a-version-word-of-0-has-two-different-meanings)).
A reader that must match a version-0 or foreign object to an info needs to compute
it. The algorithm uses wrapping unsigned 32-bit arithmetic throughout
(`root/io/io/src/TStreamerInfo.cxx:3574`) and is built from two operations:

```
acc_str(id, s):  for each byte c of s:  id = id*3 + c
acc_num(id, n):  id = id*3 + n
```

Then, for the current variant:

1. `id = 0`; `acc_str(id, class name)`.
2. **Bases.** Skipped entirely for a class with a collection proxy or a
   `std::pair` (`root/io/io/src/TStreamerInfo.cxx:3594`). Otherwise, for each
   element that is a base, in order: `acc_str(id, element name)`, then, **only
   if the element is a `TStreamerBase`**, `acc_num(id, fBaseCheckSum)`, where
   `fBaseCheckSum` is `fMaxIndex[1]` (§9)
   (`root/io/io/src/TStreamerInfo.cxx:3596-3602`). A base that is an STL
   collection is a `TStreamerSTL` whose `IsBase()` is true
   ([Streamer-driven reading §4.3](StreamerDriven.md#43-a-base-class-that-is-an-stl-container)) and folds its name alone;
   it has no `fBaseCheckSum`.
3. **Members.** Walk the elements again from the start, skipping bases. For each:
   - if the member is an enum, `acc_num(id, 1)`. The test, which ROOT itself uses,
     is `fType` **3** with an `fTypeName` that is not a primitive spelling (§11.1)
     (`root/io/io/src/TStreamerInfo.cxx:3615-3620`). An array of enums has
     `fType` 23 (`kOffsetL + 3`) and therefore folds **no** extra 1;
   - `acc_str(id, member name)`;
   - `acc_str(id, resolved type name)`, with typedefs resolved, `Long64_t`
     spellings normalised and STL default arguments dropped
     (`root/io/io/src/TStreamerInfo.cxx:3643-3656`);
   - for each of the first `fArrayDim` extents, `acc_num(id, fMaxIndex[i])`
     (`root/io/io/src/TStreamerInfo.cxx:3658-3660`);
   - the text between `[` and `]` in `fTitle`, if any, via `acc_str`
     (`root/io/io/src/TStreamerInfo.cxx:3664-3678`). **The `[` counts only when
     nothing but `/` and whitespace precedes it**, as
     `TVirtualStreamerInfo::GetElementCounterStart` enforces
     (`root/core/meta/src/TVirtualStreamerInfo.cxx:98-110`). A comment like
     `// x position [0, 1]` therefore folds nothing; only a leading `[fN]`-style
     counter does. Variants 6 and below search for `[` anywhere instead, and that
     is the only difference between variants 6 and 7.

There are eight variants, because the algorithm changed over time and old files
must still be matched (`root/core/meta/inc/TClass.h:111-122`).

Each variant's name describes something it lacks, but the tests in the code are
**thresholds on the ordered value, not independent switches**. A variant
therefore differs from the current algorithm in every row whose threshold it
fails, not only in the one its name mentions. The five decisions, with the line
that makes each:

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

Variants 2 and 5 **do** resolve typedefs. ROOT's header comment "has no typedef
at all" describes the resulting name, not an absence of resolution. Instead of
`GetLong64_Name`, they substitute `unsigned long long`, `long long` and `char`
textually (`root/io/io/src/TStreamerInfo.cxx:3646-3652`).

A reader matching an old file SHOULD try variants 1 through 7 when the current
one does not match, as ROOT does (`root/core/meta/src/TClass.cxx:6604-6609`).

> **The same class at the same version, with the same layout, can have two
> different checksums.** `TAttAxis` version 4 is `0x532a3b8c` in a ROOT 5.28 file
> and `0x5c6fff3e` in a file written by 6.40.04, with the same eleven members in
> the same order. The old file's `fTypeName` spellings are `Int_t` and `Float_t`,
> where the new one resolves them to `int` and `float`. The variants are why
> `BuildCheck` reports nothing when it reads that file, and they are why a reader
> must not treat a checksum mismatch at equal version as evidence of a layout
> change.

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

`TStreamerInfo::Build` stores every enum as an `Int_t` and gives it `fType` 3
deliberately, to keep the file format unchanged across the introduction of sized
enums (`root/io/io/src/TStreamerInfo.cxx:675-689`). An enum member and an `Int_t`
member therefore have the same type code. They differ in `fTypeName`, which keeps
the enum's own qualified name: `TH1::EBinErrorOpt`, not `int`.

The distinction affects the checksum, because an enum folds an extra `1` before
its name. ROOT's own checksum code uses this test (`fType == 3` and a type name
`gROOT->GetType` does not resolve), under a comment asking whether it can be done
at all (`root/io/io/src/TStreamerInfo.cxx:3612-3620`). A reader can apply the same
rule without a dictionary by treating any `fType` 3 whose `fTypeName` is not a
primitive spelling as an enum.

`TH1`'s recorded `0x1c3740c4` is reproduced when `fBinStatErrOpt` and
`fStatOverflows` are treated this way, and not otherwise.

### 11.2 What cannot be recomputed

**The checksum is computed from the class definition, not from the streamer info**
(`root/core/meta/src/TClass.cxx:6650-6653`), and the two do not always contain the
same information. This repository's reference files hold 1020 streamer infos,
and `tools/test_write.py` reproduces 956 of them by applying §11's algorithm to the
info's own elements. The rest fall into three groups, each with a known cause:

| Cause | Classes | What the info lacks |
|---|---|---|
| **A version-0 class lists no members** | `THashList`, `TSeqCollection` | `TStreamerInfo::Build` skips every member of a class whose version is 0 (`root/io/io/src/TStreamerInfo.cxx:552-554`), but the checksum still folds them. `THashList`'s `0xcc7e49c1` is reproduced by adding `fTable`/`THashTable*` by hand |
| **A member ROOT rewrote for I/O** | `TF1`, `CollectionForms`, `RooAbsReal` | `std::array<Int_t,3>` is recorded as a fixed C array of `int` with `fArrayDim` 1, and `std::unique_ptr<T>` as `T*`, but the checksum folds the **declared** type name and no extents. `CollectionForms` is reproduced with `array<int,3>`; `TF1` with `unique_ptr<TFormula,default_delete<TFormula> >`, default template argument spelled out, and `RooAbsReal` the same way with `RooNumIntConfig` |
| **ROOT's own value is wrong** | four `pair<…>` instances | A `pair`'s checksum can be computed before its members are known and is then cached forever (`root/core/meta/src/TClass.cxx:6655-6666`); `data/serialization/pairs.root` has three distinct pairs all carrying `0x0b5fb752`, and the fourth pair in the same file is correct and recomputable. `data/classes/roofit.root`, written by an unrelated program, has the same value on a fifth layout, `pair<string,vector<int> >`, so `0x0b5fb752` is a constant, not a property of one file |

For a reader the consequence is narrow: matching an object to an info by checksum
uses the value in the file, which is always self-consistent, so none of this
affects decoding. It matters when checking a file, or when writing one.

A writer must compute the checksum from the class as declared, including the `+1`
per enum member and the declared spelling of a rewritten member, and not from the
element list it is about to emit. See
[Writing an object §7.3](../06-writing/WritingObjects.md#73-the-checksum).

## 12. Reading

1. If `fSeekInfo` is 0 or not greater than `fBEGIN`, the file records no streamer
   information.
2. Read the record at `fSeekInfo`, of `fNbytesInfo` bytes, and decompress its
   payload if `fObjlen > fNbytes - fKeylen`, as for any record
   ([Records §3.2](../01-container/Record.md#32-fobjlen)).
3. Parse the payload as a `TList` (§4). Buffer positions count from the start of
   the **key** ([Buffer framing §1](Buffer.md#1-what-a-buffer-is)).
4. For each entry, resolve its class from the class tag or class back-reference.
   If it is not `TStreamerInfo`, seek past it using its byte count and continue.
5. For a `TStreamerInfo`, read the `TNamed` base, `fCheckSum`, `fClassVersion`,
   then the `fElements` slot as a `TObjArray` (§5).
6. For each array entry, resolve its class (one of the subclasses in §8) and read
   the subclass record, the `TStreamerElement` base (§7), and the subclass tail.
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
   `fMaxIndex[1]` read as unsigned is either 0 or the `fCheckSum` of **one of**
   that class's infos. A file may describe a class at several versions, and the
   checksum identifies which layout the derived class was built against (§9.2), so
   comparing it with whichever info a lookup by name returns is wrong. It is 0 on
   every file written before ROOT 6 (§9.1).
8. A `TStreamerBase` has `fTypeName` `"BASE"`, and `fType` is 0, 66, 67 or -1.
9. Every `TStreamerSTL` and `TStreamerSTLstring` has `fType == 500` on disk.
   This holds on every ROOT-written file available, from ROOT 3.04 on; a
   third-party writer may store the real code (§10.1).
10. A `TStreamerBasicPointer` or `TStreamerLoop` has a non-empty `fCountName`,
    and the info named by its `fCountClass` (this one, or a base) has an element
    of that name. `TArrayD`'s `fArray` names `fN` in `TArray`, its base
    ([Streamer-driven reading §3.2](StreamerDriven.md#32-elements-are-not-independent)).
11. `fArrayDim` is between 0 and 5, and when it is non-zero the first `fArrayDim`
    entries of `fMaxIndex` are all positive and their product equals
    `fArrayLength`.
12. The bytes consumed by the outer list equal `fObjlen` exactly.

There is deliberately no invariant on `fBaseVersion`. As §9.2 shows, it may
legitimately name a version the file has no info for, which invariant 7's
`fBaseCheckSum` never does.

Invariant 11 does not test the one field known to be written wrong. Before the
fix of ROOT 6.24/02, an array of STL containers or strings was stored with
`fArrayDim` 0 and a positive `fArrayLength` (§10), and invariant 11 constrains
`fMaxIndex` only when `fArrayDim` is non-zero, so such an element passes it. A
reader MUST NOT take `fArrayDim` 0 to mean a scalar without also checking
`fArrayLength`. `root/roottest/root/io/evolution/issue-8083/stringarray.old.root`,
written by 6.25/01, has one: `mystrarray::fOutputNames`, `fArrayLength` 4.

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
| 7 | `fMaxIndex` holds array dimensions, 0 if not applicable | For a `TStreamerBase`, `fMaxIndex[1]` is the base class's **checksum** (§9), or 0 on a file written before 5.34/19 (§9.1) |
| 8 | "For TStreamerInfoBase: fBaseVersion" | The class is `TStreamerBase`, and `fBaseVersion` is present only for version > 2 (§8) |
| 9 | — | `fBits` of both `TStreamerInfo` and `TStreamerElement` is persisted and needed for reading: `kIgnoreTObjectStreamer` removes the `TObject` base from every object of the class, and `kHasRange` is required to decode a `Double32_t`. A `FIXME` in ROOT asserting the info's bits are never saved (`root/io/io/src/TStreamerInfo.cxx:1400-1405`) is wrong: `serialization/streamer-info` has `fBits` `0x00010000` on disk |
| 10 | `TStreamerBasicPointer`'s third member is `fCountName` (listed twice) | The third member is `fCountClass` (§8) |
| 11 | `fSTLtype`: "5:set, 6:multimap" | Current numbering is **5 multimap, 6 set**, and ROOT has a fixup for this historical inversion (§10) |
| 12 | The `fSTLtype` list stops at 7 | It continues to 14: bitset, forward_list, the unordered containers, and `RVec` (§10) |
| 13 | `TStreamerSTL`/`TStreamerSTLstring` are "(not yet used??)" | Both are in constant use, and both store `fType = 500` rather than their real code (§10) |
| 14 | `fSize` is "size of built in type or of pointer to built in type, 0 otherwise" | It is non-zero for every element class and is the writer's `sizeof`: 24 for a `TString`, 16 for a `TObject` base (§7) |
| 15 | — | The key is removed from the directory's key list, so the record can only be found through `fSeekInfo` (§2) |
| 16 | — | No checksum algorithm is given, and the eight variants needed to match older files are not mentioned (§11) |
| 17 | *This document, until 2026-09-23*: ROOT 4 wrote the real code, 300, for an STL element | Every ROOT-written file available stores 500, from ROOT 3.04 on. The two files the claim rested on were written by g4tools, whose headers claim 4.00/00 (§10.1) |

## 15. Reference files

| Case | Exercises |
|---|---|
| `serialization/streamer-info` | The whole chain: `TList`, `TStreamerInfo`, `TNamed`, `TObjArray`, and four element subclasses including `TStreamerSTL` |
| `serialization/object-tags` | `TStreamerBase` for a `TObject` base, and a class back-reference between two infos |
| `serialization/version-zero` | Fourteen infos and seventy-one elements, from `TH1L`'s whole class hierarchy |
| `serialization/schema-rules` | The optional `listOfRules` entry alongside a `TStreamerInfo` |
| `serialization/collections` | `TStreamerSTL` in seven shapes, and the only `TStreamerSTLstring` in the corpus |

No fixture covers `TStreamerLoop`, `TStreamerArtificial` (which cannot occur;
§8, invariant 5), or any `TStreamerElement` version below 4, which needs a ROOT
this project cannot build. The corpora and `root/roottest/` cover the last:
version 2 in 41 files, from ROOT 3.03 to 4.03, and version 3 in only one,
`skim.root` (§7.1).
