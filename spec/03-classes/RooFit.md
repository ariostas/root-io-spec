# RooFit

Six RooFit classes replace the `Streamer` their `ClassDef` would generate, and a
file containing a workspace, a plot or a fit result holds all of them. They are
the reason the rest of a RooFit file cannot be read: every `RooAbsArg` has a
proxy list, every `RooRealVar` has a binning, and a reader that stops at one of
these stops at the object that contains it too.

They are also a compact catalogue of every way a streamer info can be wrong.
`RooRealVar` has **no info in the file at all**. `RooLinkedList` has one that
names a member it never writes and omits most of its bytes. `RooCategory` has
one that is right at class version 3 and wrong below it. `RooAbsBinning` writes
a base class its own declaration does not have, and `RooRefArray` writes a
different class entirely.

> **None of them is `extending`.** Every byte each one writes is inside its byte
> count, where it has one, so an object of any of these classes can still be
> *skipped* correctly — only decoding it needs this document. That is the
> distinction [Buffer framing §2.4](../02-serialization/Buffer.md#24-an-object-may-be-longer-than-its-byte-count-says)
> draws, and §7 erratum 2 is what happens when the two are confused.

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
ROOT's source rather than asserted here.

## 2. `RooRealVar`

### 2.1 Layout

```
byteCount   version   RooAbsRealLValue base   _error  _asymErrLo  _asymErrHi
┌─────────┬─────────┬──────────────────────┬────────┬───────────┬───────────┐
│   u32   │   i16   │   a framed object    │  f64   │    f64    │    f64    │
└─────────┴─────────┴──────────────────────┴────────┴───────────┴───────────┘

_binning                     _sharedProp
┌──────────────────────────┬────────────────────────────────────────────────┐
│ an object slot (§2.3)    │ a RooRealVarSharedProperties, in place (§2.2)  │
└──────────────────────────┴────────────────────────────────────────────────┘
```

`root/roofit/roofitcore/src/RooRealVar.cxx:1295-1306` is the writing branch and
`:1258-1290` the reading one. What appears after the base depends on the version
word:

| Version | After the `RooAbsRealLValue` base |
|---|---|
| 1 | `fitMin`, `fitMax` (`f64`) and `fitBins` (`i32`) **first**, then the three errors, and no binning and no shared properties |
| 2 | the three errors, then `_binning` as an object slot |
| 3 | the same, then `_sharedProp` as an **object slot** |
| 4 and above | the same, then `_sharedProp` written **in place** |

Nothing in the Streamer changed between 4 and 10, so every version from 4 on has
one layout.

> Measured on `classes/roofit`, whose `RooRealVar` is at version 10: the frame at
> 533 claims 440 bytes; the base runs 539 to 803; `_error` is `0.25` at 803;
> `_asymErrLo` is **1.0** and `_asymErrHi` **-1.0**, which is the "no asymmetric
> error" sentinel and not a measurement
> (`root/roofit/roofitcore/inc/RooRealVar.h:66`); `_binning` is an object slot at
> 827 naming `RooUniformBinning`; and the tail runs 917 to 977, which is where
> the byte count ends.

### 2.2 The tail is in no streamer info, and the byte count covers it

`_sharedProp` is a `std::shared_ptr`, which ROOT's I/O cannot write, so
`TStreamerInfo::Build` records no element for it. The `Streamer` writes the
object anyway, by calling its `Streamer` directly — `_sharedProp->Streamer(R__b)`
when there is one and `_nullProp().Streamer(R__b)` when there is not
(`root/roofit/roofitcore/src/RooRealVar.cxx:1301-1305`). So the last member of
every `RooRealVar` on disk is a framed `RooRealVarSharedProperties` that no
streamer info anywhere mentions.

**It is inside the byte count.** `SetByteCount(R__c, true)` runs after it
(`:1306`), so the count the frame opened with covers the whole object. A reader
that skips a `RooRealVar` by its byte count lands correctly; only a reader that
decodes it needs the tail.

> This is the difference between `RooRealVar` and an `extending` class, and it is
> worth being exact about because the first outside review of this specification
> reported `RooRealVar` as `extending` —
> [issue #1](https://github.com/ariostas/root-io-spec/issues/1) item 8, "followed
> by one more framed object past its own byte count". The frame is real and the
> object is real; it is not past the byte count. See §7 erratum 2.

`_nullProp()` is a singleton built from the all-zeros UUID string
(`root/roofit/roofitcore/src/RooRealVar.cxx:88`), so a `RooRealVar` that never
had a shared property installed writes sixteen zero bytes where the `TUUID`
goes. One that has been through a `RooDataSet` writes a real one.

### 2.3 No file describes `RooRealVar`

A class's streamer info reaches a file because `WriteClassBuffer` marks it
([Streamer information §13](../02-serialization/StreamerInfo.md)), and
`RooRealVar::Streamer` never calls it. So a file whose only object is a
`RooRealVar` records infos for `RooAbsRealLValue`, `RooRealVarSharedProperties`,
`RooSharedProperties`, `RooUniformBinning` and `TUUID` — and none for
`RooRealVar`.

> `classes/roofit` is that file: 21 streamer infos, no `RooRealVar` among them.
> `uproot-issue-350.root` and `stressRooFit_v534_ref.root` in the corpora are the
> same, and there `RooRealVar` objects are reached as the `_plotVarClone` of a
> `RooPlot`.

**A file may still carry one.** An info is written for every class ROOT touches
through the generated path, and a `RooRealVar` that also reaches a file as a
`RooVectorDataStore`'s `_nativeReal` does. So its absence is not a signal, and
its presence is not permission: the info describes the first four members and
stops, and following it consumes 369 of the 429 bytes a version-10 object claims.

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
(`:908-910`). A version-1 record has none — its info lists `TObject`,
`_hashThresh` and `_size` and no `_name`, which is the corroboration from the
other side.

> Measured on `classes/roofit`: the payload starts at 1071 with `00 03`, the
> `TObject` base runs to 1083, `_size` is 2, the two slots run 1087 to 1163 —
> the first with a `kNewClassTag`, the second with a class back-reference — and
> `_name` is the single zero byte at 1163, the last byte of the record.

### 3.2 The recorded info is wrong in two directions

Every file that contains a `RooLinkedList` carries an info for it, because other
classes reach it through the generated path. It says:

| Element | In the file's info | Written by the `Streamer` |
|---|---|---|
| `TObject` base | yes | yes |
| `_hashThresh` | `Int_t` | **never** |
| `_size` | `Int_t` | yes |
| the `_size` object slots | **absent** | yes, and they are most of the bytes |
| `_name` | `TString` (from version 2) | yes |

A reader that follows the info reads the version word and the first eight bytes
of the `TObject` base as `_hashThresh`, and then stops four bytes into a stream
of object slots. It desynchronises silently, because there is no byte count to
catch it.

> **The two errors nearly cancel.** The info's prefix — `TObject`, `_hashThresh`,
> `_size` — is 10 + 4 + 4 = 18 bytes, and the real prefix — version word,
> `TObject`, `_size` — is 2 + 10 + 4 = 16. A reader that starts two bytes early,
> by taking the version word for the start of the `TObject` base, lands on `_size`
> at exactly the right offset and reads the right count. That is what the layout
> quoted in [issue #1](https://github.com/ariostas/root-io-spec/issues/1) item 7
> does: `TObject` base, `Short_t _hashThresh`, `Int_t fSize`, then the slots. It
> works, and it names three fields that are not there. `_hashThresh` is not in
> the stream at any version.

## 4. Two classes reached from every `RooAbsArg`

Neither is ever the class of a record. Both are reached as members, and both
write no info of their own, so a file that contains any `RooRealVar` contains two
more classes it does not describe.

### 4.1 `RooAbsBinning` writes a `TNamed` it does not declare

`RooAbsBinning` derives from `TNamed` and `RooPrintable` in C++, and its
`Streamer` writes exactly that: a byte count, a version word, a `TNamed`, and
`RooPrintable`'s empty six-byte frame
(`root/roofit/roofitcore/src/RooAbsBinning.cxx:134-136`). At version **1** it
wrote a bare `TObject` in the `TNamed`'s place (`:125-129`), which is the schema
evolution the custom streamer exists for.

A concrete binning — `RooUniformBinning`, `RooRangeBinning`, `RooParamBinning` —
*is* streamer-info driven, and its info carries a `kBase` element naming
`RooAbsBinning`. So the base is described as present and not described at all,
which is the case
[Streamer-driven reading §10](../02-serialization/StreamerDriven.md) invariant 5
exempts for exactly this reason.

### 4.2 `RooRefArray` writes a `TRefArray`

`RooAbsArg::_proxyList` is a `RooRefArray`, which derives from `TObjArray`. Its
`Streamer` builds a temporary `TRefArray`, streams *that*, and closes its own
byte count around it (`root/roofit/roofitcore/src/RooAbsArg.cxx:2218-2227`). So
the bytes are:

```
byteCount   version=1   a whole TRefArray, framed (References §4)
```

and `TObjArray`, the class it actually derives from, never appears. A reader that
treats `RooRefArray` as a `TObjArray` reads the `TRefArray`'s frame as
`TObjArray`'s and desynchronises.

> **The member was declared `TRefArray` until ROOT 6.26 and `RooRefArray` after
> it**, so the same bytes appear under two element type names across the corpora:
> `_proxyList` is a `TRefArray` in `stressRooFit_v522_ref.root` (5.21/07) through
> `uproot-issue-350.root` (6.24/00), and a `RooRefArray` in files written by
> 6.26 and later. Both need the same out-of-band knowledge — `TRefArray`'s own
> `Streamer` is hand-written too — and neither is described by any info.

## 5. `RooCategory` below class version 3

From version 3 `RooCategory::Streamer` calls `ReadClassBuffer`
(`root/roofit/roofitcore/src/RooCategory.cxx:459`) and the class is ordinary.
Below it, the same tail problem as `RooRealVar`'s:

| Version | Layout |
|---|---|
| 1 | the `RooAbsCategoryLValue` base, then a `RooCategorySharedProperties` as an **object slot** |
| 2 | the base, then a `RooCategorySharedProperties` **in place** |
| 3 and above | streamer-info driven; the shared ranges are the `_rangesPointerForIO` member |

The tail is inside the byte count at both versions, and in no streamer info at
either.

> This is what
> [issue #1](https://github.com/ariostas/root-io-spec/issues/1) item 9 reports as
> "`RooAbsCategory` members behind one extra byte-count/version frame that the
> recorded info does not predict". The extra frame is real; it belongs to
> `RooCategory`, one level up, and it is the whole `RooCategorySharedProperties`
> object rather than a frame around `RooAbsCategory`'s members.
> `RooAbsCategory` itself is ordinary at every version, which is checkable
> rather than asserted: with §5 implemented, every `RooAbsCategory` in the corpora
> ends exactly where its byte count says. **17 records in
> `stressRooFit_v534_ref.root` and `stressRooFit_v522_ref.root` failed on exactly
> this and now decode**, each one short by 61 bytes — the size of the
> `RooCategorySharedProperties` object the info does not mention.

## 6. Reading

1. Read the object's class as usual. If it is one of the six in §1, do not look
   for a streamer info for it.
2. `RooRealVar`: take the byte count and version word, read the
   `RooAbsRealLValue` base through its own info, then the members §2.1 gives for
   that version. The object ends where the byte count says, tail included.
3. `RooLinkedList`: there is **no byte count**. Read the version word, the
   `TObject` base, an `i32` count, that many object slots, and — at version 2 or
   3 — a `TString`.
4. `RooAbsBinning` as a base: take the byte count and version word, then a
   `TNamed` (a bare `TObject` at version 1) and `RooPrintable`'s six bytes.
5. `RooRefArray`: take the byte count and version word, then read a `TRefArray`.
6. `RooCategory`: above version 2, follow its streamer info. At version 1 or 2,
   read the `RooAbsCategoryLValue` base and then the shared properties, as a slot
   at version 1 and in place at version 2.

## 7. Invariants

1. Every object of the six classes in §1 ends exactly where §6 says — and for
   the five that carry a byte count, exactly where that byte count says.
2. A `RooLinkedList`'s `_size` is not negative, and the `_size` object slots
   that follow it end inside the record that contains the list.
3. A `RooRefArray` holds exactly one `TRefArray`, and its byte count ends where
   that `TRefArray` does.
4. A `RooAbsBinning` frame holds a `TNamed` — a bare `TObject` at class version
   1 — and then `RooPrintable`'s six bytes, and nothing else.
5. Where a file carries a `RooLinkedList` streamer info, that info lists
   `_hashThresh`. Taken with invariant 1, which proves the bytes do not contain
   it, that is the recorded lie stated as a check rather than as prose (§3.2).

`tools/check_invariants.py` checks all five. Invariant 1 is checked through
consumption, which is the form
[Buffer framing §9](../02-serialization/Buffer.md#9-invariants) invariant 1
gives: reading any of these classes wrongly desynchronises, and the enclosing
byte count catches it.

## 8. Errata

| # | Was claimed | Actually |
|---|---|---|
| 1 | `PLAN.md` decision 8, until 2026-09-21: RooFit is out of scope | Revised. The classes here are six, not the fifteen the decision counted, and four of them are reached from any `RooAbsArg` |
| 2 | [Issue #1](https://github.com/ariostas/root-io-spec/issues/1) item 8: a `RooRealVar` is followed by a framed object **past its own byte count** | The object is there; the byte count covers it (§2.2). `RooRealVar` is `custom`, not `extending`, and the difference decides whether skipping it by its byte count works |
| 3 | Issue #1 item 9: the extra frame is around `RooAbsCategory`'s members | It is `RooCategory`'s, one level up, and only below class version 3 (§5) |
| 4 | Issue #1 item 7: `RooLinkedList` v3 is `TObject`, `Short_t _hashThresh`, `Int_t fSize`, then slots | The same bytes, three fields misnamed: the first two bytes are the version word, `_hashThresh` is never written, and a `TString` follows the slots (§3.2) |
| 5 | Issue #1 item 10: `RooVectorDataStore::RealVector::_vec` is preceded by two collection frames | One collection frame and one class frame; `RooVectorDataStore` is streamer-info driven throughout. [Collections §3.1](../02-serialization/Collections.md#31-pointer-content-puts-two-frames-in-a-row) |

## 9. Reference files

| Case | Exercises |
|---|---|
| `classes/roofit` | A version-10 `RooRealVar` with its tail, a version-3 `RooLinkedList` with two slots and no byte count, `RooAbsBinning` under a `RooUniformBinning`, and `RooRefArray` under the `RooAbsArg` base. 31 assertions |
| `serialization/pointer-collection` | The framing of §8 erratum 5, in isolation and without RooFit |

The corpora carry every version this document names except `RooRealVar` 1–3 and
`RooAbsBinning` 1: `stressRooFit_v522_ref.root` (ROOT 5.21/07) has
`RooLinkedList` at class version **1** and `RooCategory` at **2**,
`stressRooFit_v534_ref.root` (5.34/04) has `RooLinkedList` at **2**, and
`uproot-issue49.root` (6.04/16) and `uproot-issue-350.root` (6.24/00) have
`RooLinkedList` at **3**. Between them they hold **274 records of a RooFit
class, and 272 of them decode** — every one accounting to its byte count
exactly. The two that do not are the `RooWorkspace` records, and what stops them
is `RooWorkspace::CodeRepo` below.

`RooWorkspace::CodeRepo` is the one RooFit class with a hand-written `Streamer`
that this document does not describe; it is recorded as a gap in
`spec/99-appendix/streamers.toml` and blocks two records in
`stressRooFit_v534_ref.root`.
