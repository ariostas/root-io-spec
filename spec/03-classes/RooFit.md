# RooFit

Nine RooFit classes replace the `Streamer` their `ClassDef` would generate, and
`RooCategory` does so below class version 3. This document specifies the five
that a file containing a workspace, a plot or a fit result holds: `RooRealVar`,
`RooLinkedList`, `RooAbsBinning`, `RooRefArray` and `RooCategory`. The other five,
`RooWorkspace::CodeRepo` and the four `RooCFunctionNRef` classes, are gaps (§9).
Without them the rest of a RooFit file cannot be read: every `RooAbsArg` has a
proxy list, every `RooRealVar` has a binning, and a reader that stops at one of
these also stops at the object that contains it.

Between them they show every way a streamer info can be wrong.
`RooRealVar` has no info in the file at all. `RooLinkedList` has one that names
a member it never writes and omits most of its bytes. `RooCategory` has one that
is right at class version 3 and wrong below it. `RooAbsBinning` is named as a
base by the info of every concrete binning but usually has no info of its own,
and `RooRefArray` writes a different class entirely.

> **None of them is `extending`.** Every byte each one writes is inside its byte
> count, where it has one, so an object of any of these classes can still be
> *skipped* correctly; only decoding it needs this document. This is the
> distinction [Buffer framing §2.4](../02-serialization/Buffer.md#24-an-object-may-be-longer-than-its-byte-count-says)
> draws, and §7 erratum 2 shows what happens when the two are confused.

## 1. Class versions

| Class | Class version | `Streamer` | What a reader does |
|---|---|---|---|
| `RooRealVar` | 10 | `custom` (`root/roofit/roofitcore/src/RooRealVar.cxx:1252`) | **§2** |
| `RooLinkedList` | 3 | `custom` (`root/roofit/roofitcore/src/RooLinkedList.cxx:891`) | **§3** |
| `RooAbsBinning` | 2 | `custom` (`root/roofit/roofitcore/src/RooAbsBinning.cxx:117`) | **§4.1** |
| `RooRefArray` | 1 | `custom` (`root/roofit/roofitcore/src/RooAbsArg.cxx:2195`) | **§4.2** |
| `RooCategory` | 3 | `guarded` above version 2 (`root/roofit/roofitcore/src/RooCategory.cxx:431`) | **§5**, below version 3 only |
| `RooSharedProperties` | 1 | none of its own | nothing |
| `RooRealVarSharedProperties` | 2 | none of its own | nothing — but see §2.2 |
| `RooCategorySharedProperties` | 1 | none of its own | nothing — but see §5 |

Class versions are checked against the submodule by `tools/check_versions.py`.

Every other RooFit class in a file is streamer-info driven, including
`RooAbsArg`, `RooAbsReal`, `RooAbsCategory`, `RooArgSet`, `RooPlot`, `RooCurve`,
`RooHist`, `RooFitResult` and `RooVectorDataStore`. The complete list of
hand-written streamers is
[Hand-written streamers](../99-appendix/HandWrittenStreamers.md), extracted from
ROOT's source.

## 2. `RooRealVar`

### 2.1 Layout

```
byteCount   version   RooAbsRealLValue base   _error  _asymErrLo  _asymErrHi
┌─────────┬─────────┬──────────────────────┬────────┬───────────┬───────────┐
│   u32   │   i16   │   a framed object    │  f64   │    f64    │    f64    │
└─────────┴─────────┴──────────────────────┴────────┴───────────┴───────────┘

_binning                     _sharedProp
┌──────────────────────────┬────────────────────────────────────────────────┐
│ object slot (Buffer §6)  │ a RooRealVarSharedProperties, in place (§2.2)  │
└──────────────────────────┴────────────────────────────────────────────────┘
```

`root/roofit/roofitcore/src/RooRealVar.cxx:1295-1306` is the writing branch and
`:1258-1290` the reading one. What follows the base depends on the version word:

| Version | After the `RooAbsRealLValue` base |
|---|---|
| 1 | `fitMin`, `fitMax` (`f64`) and `fitBins` (`i32`) **first**, then the three errors, and no binning and no shared properties |
| 2 | the three errors, then `_binning` as an object slot |
| 3 | the same, then `_sharedProp` as an **object slot** |
| 4 and above | the same, then `_sharedProp` written **in place** |

The Streamer did not change between 4 and 10, so every version from 4 on has one
layout.

> Measured on `classes/roofit`, whose `RooRealVar` is at version 10: the frame at
> 533 claims 440 bytes; the base runs 539 to 803; `_error` is `0.25` at 803;
> `_asymErrLo` is 1.0 and `_asymErrHi` -1.0, which is the "no asymmetric error"
> sentinel, not a measurement (`root/roofit/roofitcore/inc/RooRealVar.h:66`);
> `_binning` is an object slot at 827 naming `RooUniformBinning`; and the tail
> runs 917 to 977, where the byte count ends.

### 2.2 The tail is in no streamer info, and the byte count covers it

`_sharedProp` is a `std::shared_ptr`, which ROOT's I/O cannot write, so
`TStreamerInfo::Build` records no element for it. The `Streamer` writes the
object anyway by calling its `Streamer` directly: `_sharedProp->Streamer(R__b)`
when there is one and `_nullProp().Streamer(R__b)` when there is not
(`root/roofit/roofitcore/src/RooRealVar.cxx:1301-1305`). The last member of every
`RooRealVar` on disk is therefore a framed `RooRealVarSharedProperties` that no
streamer info mentions.

**It is inside the byte count.** `SetByteCount(R__c, true)` runs after it
(`:1306`), so the count the frame opened with covers the whole object. A reader
that skips a `RooRealVar` by its byte count lands correctly; only a reader that
decodes it needs the tail.

> This is the difference between `RooRealVar` and an `extending` class. The first
> outside review of this specification reported `RooRealVar` as `extending`
> ([issue #1](https://github.com/ariostas/root-io-spec/issues/1) item 8,
> "followed by one more framed object past its own byte count"). The frame and
> the object are real, but the object is not past the byte count. See §7
> erratum 2.

`_nullProp()` is a singleton built from the all-zeros UUID string
(`root/roofit/roofitcore/src/RooRealVar.cxx:88`), so a `RooRealVar` that never
had a shared property installed writes sixteen zero bytes where the `TUUID`
goes. One that has been through a `RooDataSet` writes a real one.

### 2.3 No file describes `RooRealVar`

A class's streamer info reaches a file because `WriteClassBuffer` marks it
([Streamer information §13](../02-serialization/StreamerInfo.md)), and
`RooRealVar::Streamer` never calls it. A file whose only object is a
`RooRealVar` therefore records infos for `RooAbsRealLValue`,
`RooRealVarSharedProperties`, `RooSharedProperties`, `RooUniformBinning` and
`TUUID`, and none for `RooRealVar`.

> `classes/roofit` is that file: 21 streamer infos, no `RooRealVar` among them.
> `uproot-issue-350.root` and `stressRooFit_v534_ref.root` in the corpora are the
> same; there, `RooRealVar` objects are reached as the `_plotVarClone` of a
> `RooPlot`.

A file may still have one. An info is written for every class ROOT touches
through the generated path, and a `RooRealVar` that also reaches a file as a
`RooVectorDataStore`'s `_nativeReal` is such a class. Its absence therefore means
nothing, and its presence does not make it usable: the info describes the first
four members and stops. On `classes/roofit` following it stops at 917, 380
bytes into the 440 the byte count claims, and leaves the 60-byte tail of §2.2
unread.

## 3. `RooLinkedList`

### 3.1 Layout

```
version   TObject base   _size   _size object slots   _name
┌───────┬──────────────┬───────┬────────────────────┬────────────┐
│  i16  │   10 bytes   │  i32  │  Buffer framing §6 │  TString   │
└───────┴──────────────┴───────┴────────────────────┴────────────┘
```

**There is no byte count.** `RooLinkedList::Streamer` opens with
`WriteVersion(RooLinkedList::IsA())` and no `useBcnt` argument
(`root/roofit/roofitcore/src/RooLinkedList.cxx:913`), so the first two bytes of
the object are its version word. Nothing inside the object delimits it: as a
record payload it ends where the record does, and as a member it ends where the
enclosing frame's own byte count says.

`_name` is written at every version but read only when the version is 2 or 3
(`:908-910`). A version-1 record has none, and its info lists `TObject`,
`_hashThresh` and `_size` and no `_name`, which confirms this from the other
side.

> Measured on `classes/roofit`: the payload starts at 1071 with `00 03`, the
> `TObject` base runs to 1083, `_size` is 2, the two slots run 1087 to 1163 (the
> first with a `kNewClassTag`, the second with a class back-reference), and
> `_name` is the single zero byte at 1163, the last byte of the record.

### 3.2 The recorded info is wrong in two directions

Every file that contains a `RooLinkedList` has an info for it, because other
classes reach it through the generated path. The info says:

| Element | In the file's info | Written by the `Streamer` |
|---|---|---|
| `TObject` base | yes | yes |
| `_hashThresh` | `Int_t` | **never** |
| `_size` | `Int_t` | yes |
| the `_size` object slots | **absent** | yes, and they are most of the bytes |
| `_name` | `TString` (from version 2) | yes |

A reader that follows the info reads the version word and the `TObject` base
correctly, then takes `_size` for `_hashThresh` and the first four bytes of the
first object slot for `_size`, and reads `_name` from inside the slots. It
desynchronises without any error, because there is no byte count to catch it.

> The two errors nearly cancel. The info's prefix (`TObject`, `_hashThresh`,
> `_size`) is 10 + 4 + 4 = 18 bytes, and the real prefix (version word,
> `TObject`, `_size`) is 2 + 10 + 4 = 16. A reader that starts two bytes early,
> by taking the version word for the start of the `TObject` base, lands on `_size`
> at the right offset and reads the right count. The layout quoted in
> [issue #1](https://github.com/ariostas/root-io-spec/issues/1) item 7 does this:
> `TObject` base, `Short_t _hashThresh`, `Int_t fSize`, then the slots. It works,
> and it names three fields that are not there. `_hashThresh` is not in the
> stream at any version.

## 4. Two classes reached from every `RooRealVar`

Neither is ever the class of a record. Both are reached as members, and neither
`Streamer` writes an info, so a file that contains any `RooRealVar` usually
contains two more classes it does not describe.

### 4.1 `RooAbsBinning` writes its bases, and usually no info describes them

`RooAbsBinning` derives from `TNamed` and `RooPrintable`
(`root/roofit/roofitcore/inc/RooAbsBinning.h:33`), and its `Streamer` writes
that: a byte count, a version word, a `TNamed`, and `RooPrintable`'s empty
six-byte frame (`root/roofit/roofitcore/src/RooAbsBinning.cxx:134-136`). At
version 1 it wrote a bare `TObject` in place of the `TNamed` (`:125-129`);
handling that schema change is why the custom streamer exists.

A concrete binning (`RooUniformBinning`, `RooRangeBinning`, `RooParamBinning`)
is streamer-info driven, and its info has a `kBase` element naming
`RooAbsBinning`. The `Streamer` never calls `WriteClassBuffer`, so the base is
usually declared present but not described. Of the five files in the fixtures,
`gen/cern/` and `gen/foreign/` with an info for a concrete binning, only
`stressRooFit_v522_ref.root` also has one for `RooAbsBinning`, and it lists the
two bases correctly. That is the case
[Streamer-driven reading §10](../02-serialization/StreamerDriven.md) invariant 5
exempts for this reason.

### 4.2 `RooRefArray` writes a `TRefArray`

`RooAbsArg::_proxyList` is a `RooRefArray`, which derives from `TObjArray`. Its
`Streamer` builds a temporary `TRefArray`, streams that, and closes its own byte
count around it (`root/roofit/roofitcore/src/RooAbsArg.cxx:2218-2227`). The bytes
are:

```
byteCount   version=1   a whole TRefArray, framed (References §4)
```

`TObjArray`, the class it actually derives from, never appears. A reader that
treats `RooRefArray` as a `TObjArray` reads the `TRefArray`'s frame as
`TObjArray`'s and desynchronises.

> The member's type has changed twice, with `RooAbsArg`'s class version, so a
> reader keys on the element's type name and never on the release:
>
> | `RooAbsArg` | Releases | `_proxyList` | Bytes |
> |---|---|---|---|
> | 3, 4 | up to 5.30 | `TList` | an ordinary `TList` ([Containers](Containers.md)) |
> | 5 | 5.32 – 5.34/05 | `TRefArray` | a framed `TRefArray` ([References §4](../02-serialization/References.md#4-trefarray)) |
> | 6 and later | 5.34/06 on, and every 6.x | `RooRefArray` | one more frame around that `TRefArray` |
>
> The boundaries are read from `roofit/roofitcore/inc/RooAbsArg.h` at the tags;
> the `RooRefArray` change reached the 5.34 patch series at `v5-34-06` and master
> in commit `132f5917f47` (2013-09-20). The corpora agree:
> `stressRooFit_v522_ref.root` (5.21/07) has `RooAbsArg` 4 with a `TList`,
> `stressRooFit_v534_ref.root` (5.34/04) version 5 with a `TRefArray`, and
> `uproot-issue-350.root` (6.24/00) version 7 with a `RooRefArray`. *Until
> 2026-09-24 this note dated the `RooRefArray` change to 6.26 and said the last
> two forms were the same bytes; erratum 6.* Neither `TRefArray` nor
> `RooRefArray` is described by any info.

## 5. `RooCategory` below class version 3

From version 3 `RooCategory::Streamer` calls `ReadClassBuffer`
(`root/roofit/roofitcore/src/RooCategory.cxx:459`) and the class is ordinary.
Below it, it has the same tail problem as `RooRealVar`:

| Version | Layout |
|---|---|
| 1 | the `RooAbsCategoryLValue` base, then a `RooCategorySharedProperties` as an **object slot** |
| 2 | the base, then a `RooCategorySharedProperties` **in place** |
| 3 and above | streamer-info driven; the shared ranges are the `_rangesPointerForIO` member |

At both versions the tail is inside the byte count and in no streamer info.

> [Issue #1](https://github.com/ariostas/root-io-spec/issues/1) item 9 reports
> this as "`RooAbsCategory` members behind one extra byte-count/version frame
> that the recorded info does not predict". The extra frame is real, but it
> belongs to `RooCategory`, one level up, and it is the whole
> `RooCategorySharedProperties` object rather than a frame around
> `RooAbsCategory`'s members. `RooAbsCategory` itself is ordinary at every
> version, and this is checked: with §5 implemented, every `RooAbsCategory` in the
> corpora ends exactly where its byte count says. 17 records in
> `stressRooFit_v534_ref.root` and `stressRooFit_v522_ref.root` failed on this
> and now decode; each was short by 61 bytes, the size of the
> `RooCategorySharedProperties` object the info does not mention.

## 6. Reading

1. Read the object's class as usual. If it is one of the five in §1 with a
   `Streamer` of its own, do not look for a streamer info for it, except for a
   `RooCategory` above version 2, whose `Streamer` hands the read to its info
   (step 6).
2. `RooRealVar`: take the byte count and version word, read the
   `RooAbsRealLValue` base through its own info, then the members §2.1 gives for
   that version. The object ends where the byte count says, tail included.
3. `RooLinkedList`: there is **no byte count**. Read the version word, the
   `TObject` base, an `i32` count, that many object slots, and, at version 2 or
   3, a `TString`.
4. `RooAbsBinning` as a base: take the byte count and version word, then a
   `TNamed` (a bare `TObject` at version 1) and `RooPrintable`'s six bytes.
5. `RooRefArray`: take the byte count and version word, then read a `TRefArray`.
6. `RooCategory`: above version 2, follow its streamer info. At version 1 or 2,
   read the `RooAbsCategoryLValue` base and then the shared properties, as a slot
   at version 1 and in place at version 2.

## 7. Invariants

1. Every object of the five classes in §1 with a `Streamer` of their own ends
   exactly where §6 says, and for the four that have a byte count, exactly where
   that byte count says.
2. A `RooLinkedList`'s `_size` is not negative, and the `_size` object slots
   that follow it end inside the record that contains the list.
3. A `RooRefArray` holds exactly one `TRefArray`, and its byte count ends where
   that `TRefArray` does.
4. A `RooAbsBinning` frame holds a `TNamed` (a bare `TObject` at class version
   1), then `RooPrintable`'s six bytes, and nothing else.
5. Where a file has a `RooLinkedList` streamer info, that info lists
   `_hashThresh`. With invariant 1, which shows the bytes do not contain it, this
   states the incorrect info of §3.2 as a check.

`tools/check_invariants.py` checks all five. Invariant 1 is checked through
consumption, the form
[Buffer framing §9](../02-serialization/Buffer.md#9-invariants) invariant 1
gives: reading any of these classes wrongly desynchronises, and the enclosing
byte count catches it.

## 8. Errata

| # | Was claimed | Actually |
|---|---|---|
| 1 | `PLAN.md` decision 8, until 2026-09-21: RooFit is out of scope | Revised. The classes here are five, not the fifteen the decision counted, and two of them are reached from any `RooRealVar` (§4) |
| 2 | [Issue #1](https://github.com/ariostas/root-io-spec/issues/1) item 8: a `RooRealVar` is followed by a framed object **past its own byte count** | The object is there; the byte count covers it (§2.2). `RooRealVar` is `custom`, not `extending`, and the difference determines whether skipping it by its byte count works |
| 3 | Issue #1 item 9: the extra frame is around `RooAbsCategory`'s members | It is `RooCategory`'s, one level up, and only below class version 3 (§5) |
| 4 | Issue #1 item 7: `RooLinkedList` v3 is `TObject`, `Short_t _hashThresh`, `Int_t fSize`, then slots | The same bytes, three fields misnamed: the first two bytes are the version word, `_hashThresh` is never written, and a `TString` follows the slots (§3.2) |
| 5 | Issue #1 item 10: `RooVectorDataStore::RealVector::_vec` is preceded by two collection frames | One collection frame and one class frame; `RooVectorDataStore` is streamer-info driven throughout. [Collections §3.1](../02-serialization/Collections.md#31-pointer-content-puts-two-frames-in-a-row) |
| 6 | This document, until 2026-09-24: `_proxyList` was declared `TRefArray` until ROOT 6.26 and `RooRefArray` after, and the two forms are the same bytes | `TList` up to 5.30, `TRefArray` in 5.32 – 5.34/05, `RooRefArray` from 5.34/06, read at the tags; the `RooRefArray` form has one more frame than the `TRefArray` one (§4.2). The 6.24 corpus file it cited has a `RooRefArray` |

## 9. Reference files

| Case | Exercises |
|---|---|
| `classes/roofit` | A version-10 `RooRealVar` with its tail, a version-3 `RooLinkedList` with two slots and no byte count, `RooAbsBinning` under a `RooUniformBinning`, and `RooRefArray` under the `RooAbsArg` base. 31 assertions |
| `serialization/pointer-collection` | The framing of §8 erratum 5, in isolation and without RooFit |

The corpora cover every version this document names except `RooRealVar` 1–3 and
`RooAbsBinning` 1: `stressRooFit_v522_ref.root` (ROOT 5.21/07) has
`RooLinkedList` at class version **1** and `RooCategory` at **2**,
`stressRooFit_v534_ref.root` (5.34/04) has `RooLinkedList` at **2**, and
`uproot-issue49.root` (6.04/16) and `uproot-issue-350.root` (6.24/00) have
`RooLinkedList` at **3**. Between them they hold 274 records of a RooFit class,
and 272 of them decode, each accounting for exactly its byte count. The two that
do not are the `RooWorkspace` records, one in each stress file, which decode
except for their `RooWorkspace::CodeRepo` member.

`RooWorkspace::CodeRepo` and the four `RooCFunctionNRef` classes have
hand-written `Streamer`s that this document does not describe. They are recorded
as gaps in `spec/99-appendix/streamers.toml`. `CodeRepo` leaves one `RooWorkspace` record partial in each of the two
stress files, and no file in either corpus contains a
`RooCFunctionNRef`.
