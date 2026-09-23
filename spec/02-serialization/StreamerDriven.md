# Streamer-driven reading

The algorithm that turns a byte range into a value tree, given a streamer info.

[Buffer framing](Buffer.md) says how an object slot is delimited and how its class
is identified. [Streamer information](StreamerInfo.md) says how to obtain the
member list for that class, and [Element types](ElementTypes.md) says how many
bytes one member occupies. This document is the loop that joins them, plus the
three things that loop has to get right and that none of the other documents
own: recursion into base classes, the dependence of one element on another, and
what to do when the description and the bytes disagree.

It covers **every class whose streamer is generated from its member list**, which
is most of them, including all user-defined classes. The classes it does not
cover are the ones with a hand-written `Streamer`; those are §7 and
`03-classes/`.

## 1. Scope of the algorithm

Input:

- a byte range, delimited by a byte count or by the end of the record's object
  data;
- a class name and class version, obtained from the enclosing object slot;
- a streamer info for that class and version, read from the file's own
  `StreamerInfo` record.

Output: a sequence of named values, one per element of the streamer info, some of
which are themselves value trees.

> The algorithm needs **nothing that is not in the file**. A reader with no
> compiled knowledge of the class can execute it in full. This is the property
> that makes ROOT files self-describing, and it is the reason a third-party
> reader is possible at all.

## 2. Where the loop starts

The loop is entered at four places, and the difference between them is only what
framing was consumed first.

| Entry | Framing already consumed | Cited |
|---|---|---|
| A record's top-level object | key, then possibly a class record | `root/io/io/src/TKey.cxx:255-258` |
| An object slot reached through a pointer | byte count, class record, version word | `root/io/io/src/TBufferFile.cxx:3548-3570` |
| An embedded object member (61, 62, 63, 67, 68) | byte count, version word | `root/io/io/src/TStreamerInfoReadBuffer.cxx:1362-1379` |
| A base class element (0) | byte count, version word | `root/io/io/src/TStreamerInfoReadBuffer.cxx:1400-1412` |

In every case the version word has already been read, because the version is what
selects the streamer info. The loop therefore begins at the first content byte.

The two `ReadClassBuffer` overloads differ only in whether the caller already knew
the version (`root/io/io/src/TBufferFile.cxx:3455`,
`root/io/io/src/TBufferFile.cxx:3548`). Neither changes the byte layout.

## 3. The element loop

For each element of the streamer info, in the order the elements appear in
`fElements`, consume the bytes its `fType` specifies
([Element types](ElementTypes.md)). The order on disk is the order in the array;
there is no reordering, no alignment and no padding anywhere.

Three rules govern which elements participate.

**Every element participates.** Unlike ROOT, a reader building a value tree has no
notion of an element being suppressed. ROOT skips elements carrying the `kWrite`
bit (`root/io/io/src/TStreamerInfoReadBuffer.cxx:791`) and elements redirected to
a schema-evolution cache (`root/io/io/src/TStreamerInfoReadBuffer.cxx:794-806`),
but both bits are set by `BuildOld` at read time on an in-memory copy and neither
occurs in a file. No element of any streamer info in the reference corpus has
`fBits` other than `0x00000000` or `0x00000040` (`kHasRange`).

**An element with `fType` of -1 consumes nothing** (§4.2).

**No element is reordered by optimisation.** ROOT merges runs of adjacent
same-width members into a single array read and keeps the merged list in
`fCompOpt` alongside the full list in `fCompFull`
(`root/io/io/inc/TStreamerInfo.h:98-99`). This is a loop-count optimisation only;
the bytes are identical either way, and a reader SHOULD ignore it.

### 3.1 There is no offset to seek to

Nothing in the format gives a member's position. The position of element *n* is
the sum of the widths of elements 0 through *n*-1 and nothing else, so an element
whose width the reader cannot compute costs it every element after that one in
the same object.

`TStreamerElement::fOffset` is not an escape from this. It is the member's offset
**in memory on the writing machine**, and it is **transient** — declared `//!` and
absent from `TStreamerElement::Streamer`, which writes only `TNamed`, `fType`,
`fSize`, `fArrayLength`, `fArrayDim`, `fMaxIndex` and `fTypeName`
(`root/core/meta/inc/TStreamerElement.h:37`,
`root/core/meta/src/TStreamerElement.cxx:541-600`). It is not in the file at all.

> This is worth stating because ROOT *prints* it. `TClass::ShowStreamerInfo` and
> `TStreamerInfo::ls` put `offset=` on every line, and the member tables in the
> shipped documentation are captures of that output
> (`root/io/doc/TFile/ttree.md:44-56`). Every offset in them is 0, which is what
> an uncompiled info holds, not a fact about the file.

The same caution applies to `fSize`, which *is* on disk and is equally not a
width ([Streamer information §7](StreamerInfo.md#7-tstreamerelement)).

### 3.2 Elements are not independent

Two element kinds take their length from another element rather than from the
stream, so the loop MUST retain values as it goes:

- **`kOffsetP + T` (40 + T)** takes its count from the `kCounter` element named in
  `fCountName` (`root/io/io/src/TStreamerInfoReadBuffer.cxx:87-105`).
- **`kStreamLoop` (501)** does the same
  (`root/io/io/src/TStreamerInfoReadBuffer.cxx:1462-1697`).

The counter always precedes the members that name it, because ROOT emits members
in declaration order and the `[n]` annotation can only name an already-declared
member. A reader MAY rely on this, but SHOULD fail loudly rather than guess if a
`fCountName` names an element it has not yet read.

**The counter is not necessarily in the same element list.** It may be declared in
a base class, in which case it is nowhere among the current class's elements at
all. `TStreamerBasicPointer` records where it is, in `fCountClass` and
`fCountVersion` alongside `fCountName`
(`root/core/meta/inc/TStreamerElement.h:202-204`), and a reader must therefore
carry counter values **down the whole base chain of one object**, not reset them
per class. `fCountClass` is always written, even when it names the element's own
class.

> `TGraphAsymmErrors` version 3 is the standard example: `fEXlow`, `fEXhigh`,
> `fEYlow` and `fEYhigh` all name `fNpoints` with `fCountClass` `TGraph`, which is
> its base. A reader that scopes counters per class reads the four arrays as
> length 0 and then desynchronises. Seen in the wild on `RooHist`, which reaches
> `TGraph` two bases up, and on `TF1::fParErrors`, which names `fNpar`.

> **There is no length prefix on a counted array.** The only bytes are the
> one-byte presence flag and the payload. A reader that loses the counter's value
> cannot recover the member's length from the stream, and because a counted array
> carries no byte count of its own, it cannot resynchronise until the *enclosing*
> object ends.

## 4. Base classes

A base class is an element like any other; its type code says how it is framed.

```
kBase (0):     bc  ver  <recursive element loop for the base class>
kTNamed (67):  bc  ver  <recursive element loop for TNamed>
kTObject (66):     ver  fUniqueID:u32  fBits:u32  [pidf:u16]
kNoType (-1):  nothing
```

For code 0 the recursion is usually literal: ROOT calls back into
`ReadClassBuffer` for the base class
(`root/core/meta/src/TStreamerElement.cxx:813-845`), which reads a version word
and runs this same loop. The version word belongs to the **base class**, not to
the derived class, and it is the version that selects the base's streamer info.

"Usually" because that is the *last* branch `TStreamerBase::ReadBuffer` tries,
and a base whose class has a `Streamer` of its own never reaches it — §4.4.

Bases come first. `TStreamerInfo::Build` collects base classes in a loop that
precedes the data-member loop (`root/io/io/src/TStreamerInfo.cxx:469`,
`root/io/io/src/TStreamerInfo.cxx:550`), so every `TStreamerBase` element sorts
ahead of every data member in `fElements`.

### 4.1 The base's version is on disk, except member-wise

Because the base is read through the ordinary path, its version word is in the
stream and a reader does not need `TStreamerBase::fBaseVersion` to interpret it.

That stops being true inside a member-wise collection, where the base contributes
its members inline with **no byte count and no version word**, and the base
version must be taken from the element record. ROOT flags this as a design defect
in a comment at the point where it happens
(`root/io/io/src/TStreamerInfoReadBuffer.cxx:1405-1409`). See
`02-serialization/Collections.md`.

### 4.2 A suppressed `TObject` base

A class that calls `IgnoreTObjectStreamer()` writes no `TObject` bytes at all
(`root/core/base/src/TObject.cxx:995-996`). Two things record this, and a reader
needs both:

1. The base element's `fType` is set to -1
   (`root/io/io/src/TStreamerInfo.cxx:518-522`), so the loop consumes nothing.
2. The info's own `fBits` carries `kIgnoreTObjectStreamer`, bit 13
   ([Streamer information §6](StreamerInfo.md#6-tstreamerinfo)).

> This is the one case where an element is present in the description and absent
> from the bytes. A reader that treats `fElements` as a one-to-one map onto the
> stream desynchronises here, and the failure is silent: the following member
> simply reads the wrong bytes.

### 4.3 A base class that is an STL container

A class may inherit from a collection, and ROOT does not write that base as a
`TStreamerBase`. It appears as a **`TStreamerSTL` whose `fName` is the container
type**, indistinguishable in class from an ordinary collection member except that
its `fName` and `fTypeName` are equal.

Its bytes are the collection's, framed as
[Collections §2](Collections.md#2-the-frame) describes, and a reader that treats it
as a member reads it correctly — so this matters for element *ordering* rather than
for decoding. It is why §3's "bases first" is a statement about `TStreamerBase`
elements only.

> Seen in both `uproot-issue433-splitlevel*` files of the foreign corpus
> (`PLAN.md` §9.8): `JTRIGGER::JPMTSelector` has two elements, a `TStreamerSTL`
> named `vector<JTRIGGER::JPMTIdentifier_t>` and then a `TStreamerBase` named
> `TObject` — the C++ being `class JPMTSelector : public
> std::vector<JPMTIdentifier_t>, public TObject`.

### 4.4 A base whose class has a hand-written `Streamer`

`TStreamerBase::ReadBuffer` does not begin with `ReadClassBuffer`. It begins with
the base class's own `Streamer`, taken from `TClass::GetStreamerFunc()` at
`root/core/meta/src/TStreamerElement.cxx:760` and called at
`root/core/meta/src/TStreamerElement.cxx:820`; then an adopted `TClassStreamer`
if the class has one (`root/core/meta/src/TStreamerElement.cxx:826`); and only
then `ReadClassBuffer` with the version word §4 describes.

So a `kBase` element contributes **whatever the base class's `Streamer` writes**,
which is the same rule as §7 applied one level down. For a class with a generated
`Streamer` the two branches agree and the distinction is invisible. For one with
a hand-written `Streamer` the streamer info recorded for the base is as much a
fiction as §7's, and reading it consumes bytes the writer never wrote.

The extreme case is `TQObject`, whose `Streamer` reads nothing and writes nothing
in either direction (`root/core/base/src/TQObject.cxx:1033-1040`). **A `TQObject`
base occupies zero bytes** — not a framed empty object, not a bare version word.
`TVirtualPad` derives from it (`root/core/base/inc/TVirtualPad.h:50-51`), so
every `TPad` and `TCanvas` in every file has a base element that is not there.

> A file will happily carry a `TQObject` streamer info alongside, with zero
> elements, because `TStreamerInfo::Build` records the class whether or not it
> writes anything. Following it reads a version word that belongs to the next
> member.

A reader cannot derive any of this from the file; the class name is the only
signal. The complete list for ROOT's own classes is
[Hand-written streamers](../99-appendix/HandWrittenStreamers.md).

> **Three empty bases, three byte counts.** `TQObject` writes 0 bytes,
> `TAttBBox2D` writes 6 — a byte count and a version word of 0 — and
> `TSeqCollection` writes 0 plus whatever *its* bases write. All three have no
> members of their own, and what decides between them is a `ClassDef` version and
> a `LinkDef` suffix. [TCanvas §3](../03-classes/Canvas.md) tabulates them and
> `classes/canvas` has the first two six bytes apart.

### 4.5 A base whose class is version 0

The other way a `kBase` element can contribute something other than what §4
describes, and it does not need a hand-written `Streamer` at all.

`rootcling` generates two different bodies. For a class selected with
`#pragma link C++ class X+;` it emits the `ReadClassBuffer` form §4 assumes. For
one selected **plainly**, as `class X;`, *and* whose `ClassDef` version is `≤ 0`,
it emits a body that calls each base class's `Streamer` **and nothing else** — no
version word, no byte count, and none of the class's own members
(`root/core/dictgen/src/rootcling_impl.cxx:1332-1367`; the choice is
`cl.RequestStreamerInfo()` at
`root/core/clingutils/src/TClingUtils.cxx:3016`).

So such a class is transparent on disk: its `kBase` element occupies exactly what
*its* bases occupy. `TSeqCollection` is one, and a `TBtree` is where that is
visible in bytes — see
[TMap, TExMap and TBtree §6](../03-classes/Containers.md), which also gives the
`TTreePerfStats` case where following §4 instead puts every member four bytes
late.

**The file does not record which generator ran.** Both write a streamer info,
both record class version 0, and the `+` suffix exists only in a `LinkDef.h`.
Class version 0 is therefore a *warning* to a reader rather than an answer.

So the class list has to come from outside the file, and it is published as
[Forwarding streamers](../99-appendix/ForwardingStreamers.md) — 534 classes,
extracted from the pinned submodule and CI-checked, of which three occur anywhere
in this project's two corpora. That page also gives the reading procedure and one
fact that makes the case less alarming than it sounds: for a version-0 class,
`TStreamerInfo::Build` records **no data members at all**
(`root/io/io/src/TStreamerInfo.cxx:552-554`), so the info lists the bases the
streamer actually writes and the only thing missing is the frame. Where the list
runs out, §8's resynchronisation is the fallback.

## 5. Nested objects

An object-valued member is read by running this same loop over the member's own
class. What differs between the codes is only the framing consumed first, and
whether a class record precedes it — see
[Element types §7](ElementTypes.md#7-object-valued-codes-61-to-71).

The class of a **pointer** member is not necessarily the class named in
`fTypeName`: codes 64 and 69 carry a class record precisely so that a derived
object can be stored through a base pointer
([Buffer framing §5](Buffer.md#5-class-records)). A reader MUST take the class
from the class record and MUST NOT assume `fTypeName`.

For codes 61, 62, 63, 67 and 68 there is no class record and `fTypeName` is the
only source of the class. For 63 and 68 (`->`) the pointer is additionally
promised non-null, so there is no null form to test for.

## 6. When there is no usable streamer info

A reader can find itself without a member list in three ways.

**The class is absent from the file's `StreamerInfo` record.** For a class whose
bytes are written inline this is a broken file, and a reader SHOULD report it
rather than guess — but the absence is legitimate for more classes than the
bootstrap set and the container's own records, and §6.1 is the boundary.

**The version on disk is not among the infos for that class.** ROOT reports an
error and skips the object using its byte count
(`root/io/io/src/TBufferFile.cxx:3663-3667`). A reader SHOULD do the same: the
enclosing byte count makes the object skippable without understanding it.

**The version on disk is 0.** ROOT skips the object silently — no error, no
warning, just `CheckByteCount` and return
(`root/io/io/src/TBufferFile.cxx:3656-3661`). A reader SHOULD NOT copy the
silence: a version of 0 with a matching streamer info is perfectly readable, and
the silent skip is only the fallback when no info was found.

In all three cases the recovery is the same and it is the reason every object
carries a byte count: **seek to the end of the byte count and continue**. Objects
nest, so an unreadable object costs exactly itself.

### 6.1 Which classes the file must describe

A missing info is not always a missing info. Only a class whose bytes are written
**inline** has to be described, because there the declared type is the only thing
that says what the bytes are; where the bytes carry their own class
identification, or may not exist at all, the declared type is not a promise.

| Where a class is named | Must the file describe it? |
|---|---|
| a `TStreamerBase` element | **yes** |
| a member of code `kObject` (61) or `kAny` (62), with or without `kOffsetL` | **yes** |
| a member of code `kObjectp` (63) or `kAnyp` (68) — the `->` forms, which cannot be null | **yes** |
| a member of code `kObjectP` (64) or `kAnyP` (69) | **no** — see below |
| `kTString` (65), `kTObject` (66), `kTNamed` (67) | no; read by hardcoded rules |
| a `TStreamerSTL` (500) | no; [Collections](Collections.md) describes it from the type name |

Three exemptions apply to the **yes** rows. The first two are properties of
ROOT's source rather than of the file, which is why they have to be published as
lists; the third is a property of the type:

- a class whose `Streamer` is **hand-written** records no info for itself. Writing
  an object marks its class so that the info is written
  ([Writing an object §7.2](../06-writing/WritingObjects.md#72-which-classes-need-an-info)),
  and a `Streamer` that never calls `WriteClassBuffer` never marks anything —
  which is why `TObject`, `TObjArray`, `TList` and the `TArray` family are absent
  as bases and as members from files that are perfectly well formed.
  [Hand-written streamers](../99-appendix/HandWrittenStreamers.md) is the list,
  and only its `custom` classes are exempt: a `guarded`, `extending` or
  `delegating` one does call `WriteClassBuffer`, so its info is there;
- a class whose generated `Streamer` **forwards** to its bases, for the same
  reason — [Forwarding streamers](../99-appendix/ForwardingStreamers.md);
- an **STL container** used as an inline member. `vector<double> twovectors[2]`
  reaches disk as a `TStreamerObjectAny` of code 82 rather than as a
  `TStreamerSTL`, and the `StreamerInfo` record of the ROOT 6.24/06 file that
  holds one has exactly one entry — the enclosing class. A reader loses nothing:
  [Collections](Collections.md) describes the bytes from the type name.

**Why a nullable pointer is different**, and this is the half worth carrying: a
`kObjectP` or `kAnyP` member is written as a class record and an object, or as
four zero bytes
([Element types §7](ElementTypes.md#7-object-valued-codes-61-to-71)), so the class
that was actually written names itself in the bytes
([Buffer framing §5](Buffer.md#5-class-records)). The declared type need not
appear in the file at all, and for an abstract one it usually does not: ROOT
records the info chain of a pointee's declared class where it can — an empty
`TGraph`'s null `TH1F*` still drags in `TH1F`, `TArrayF` and `TArray`
([Element lists §10](../06-writing/ElementLists.md)) — but an abstract class has
no layout to record. A reader MUST take such a member's class from the bytes and
MUST NOT require its declared type to be described.

> Measured over `data/` and both corpora — **306 files** carrying at least one
> streamer info, ROOT 2.24/00 to 6.36/02:
>
> - **92 `kBase` elements in 65 files** name a class with no info in the same
>   file, and every one is exempt except two: `TAtt3D` as a base of `TH3` in the
>   two files g4tools wrote. 48 files written by ROOT in the same corpora *do*
>   carry a `TAtt3D` info — `ClassDef(TAtt3D,1)`, an entry with no elements — and
>   of the six files that describe a `TH3` at all, those two are the only ones
>   without it. So the pair is the writer, not the rule, and
>   `gen/foreign/IGNORE.toml` says so;
> - **489 inline members** name a class with no info, every one exempt;
> - **289 nullable-pointer members** name a class with no info, which is why the
>   last row of the table is *no*. Five declared types account for them —
>   `TVirtualIndex` (`TTree::fTreeIndex`, 145 files), `TArray`,
>   `TGeoPatternFinder`, `TF1AbsComposition` and one user class — and the four of
>   ROOT's own are abstract (`root/tree/tree/inc/TVirtualIndex.h:38`,
>   `root/core/cont/inc/TArray.h:48`,
>   `root/geom/geom/inc/TGeoPatternFinder.h:67`,
>   `root/hist/hist/inc/TF1AbsComposition.h:21`).

### 6.2 A file can omit an info ROOT would have written

When the absent class is not exempt under §6.1, the writer is at fault — and that
is worth establishing rather than assuming, because the alternative reading is
that ROOT sometimes omits an info and the specification is wrong.

`uproot-issue-861.root` is the measured case. It holds two top-level `TTime`
records and no `TTime` info. `TTime` is `ClassDef(TTime,2)`, on neither published
list, so §6.1 says the file must describe it.

> **ROOT does describe it.** Writing two `TTime` objects with 6.40.04 produces a
> `StreamerInfo` record holding `TTime` version 2, checksum `0x839dbf90`, one
> member `fMilliSec` — and so does adding a `TTime` to an existing histogram file
> opened for **update**, which is the obvious way to reach this state by accident.
> That second test also reproduces the corpus file's info list exactly: the same
> fourteen entries, plus `TTime`.
>
> The object bytes are identical either way. Both writers frame it as
> `40 00 00 0a | 00 02 | Long64_t` — a byte count of 10, a version word of 2, and
> eight bytes — and `fObjlen` is 14 in both. The corpus file's records are 70
> bytes against ROOT's 50 only because its key carries a longer name and title.
> **Nothing about the object is unusual; only its description is missing.**
>
> The file is CAEN CoMPASS output — its own name is a Windows path,
> `C:/Users/…/HcompassF_226Ra_run_2_20231117_085722.root` — and it omits an info
> for its own `CalibrationCoefficient` class too, a 44-byte object nothing in the
> file describes. A reader that knows `TTime` out of band recovers the
> milliseconds; a reader driven by the file alone cannot, and `Collections.md` §9
> is the same situation one level down.

## 7. When the streamer info does not describe the bytes

> **A class with a hand-written `Streamer` still has a streamer info in the file,
> and that streamer info can be a complete fiction.**

`TStreamerInfo::Build` constructs elements from the class's data members
(`root/io/io/src/TStreamerInfo.cxx:469-560`) whether or not those members are
what the class actually writes. A `Streamer` written by hand may write the
members in a different order, write fewer of them, write extra values, or write a
different shape entirely.

It may also write a **prefix**: apply an info correctly and then keep reading.
There the info is not fiction, it is incomplete, and the failure is quieter than
a mismatch — the byte count agrees, every consistency check passes, and the
object is simply longer than the reader thinks
([Buffer framing §2.4](Buffer.md#24-an-object-may-be-longer-than-its-byte-count-says)).
`TMatrixTSym` goes further and hands `ReadClassBuffer` its **base class's**
`TClass`, so the info the file carries is the base's and none is recorded for the
class itself ([Matrices and vectors §2.2](../03-classes/Matrix.md)).

**Nothing in the file marks this.** `TClass::fStreamerType`, which is what ROOT
dispatches on, is a transient member (`root/core/meta/inc/TClass.h:285`,
`root/core/meta/inc/TClass.h:344`) computed from the compiled dictionary. A
reader therefore cannot detect a hand-written streamer; it has to know, from a
list, which classes have one.

For ROOT's own classes that list is
[Hand-written streamers](../99-appendix/HandWrittenStreamers.md), extracted from
ROOT's source and checked against it on every build. It is smaller than the count
of hand-written `Streamer` definitions suggests: most of them still call
`ReadClassBuffer`, either unconditionally or above a version threshold, and only
the ones that never do can diverge from their streamer info at a current
version.

**The list cannot be closed, though, because a user class can have one too.**
`ClassDef` generates a `Streamer` that calls `ReadClassBuffer`, so a class that
uses it is streamer-info driven whatever else it does — but a class may replace
that generated body, and experiment frameworks do. In `gen/foreign/`,
KM3NeT's Jpp DAQ classes are the case: `KM3NETDAQ::JDAQPreamble`'s recorded info
says a framed `JDAQAbstractPreamble` base and a `TObject` base, and its split
branch's entry is eight bytes — the base's two `Int_t`, raw, with no frame and no
`TObject`. Nothing distinguishes it from a class that does follow its info; the
control is a sibling `kBase` element in the same entry set, which *is* framed
three levels deep and decodes exactly.

So a reader that meets an unknown class has to accept that its info may be
fiction and report the mismatch rather than guess, which is §8. For the ordinary
case — a class with a generated `Streamer` — the streamer info is authoritative.

> The practical symptom of getting this wrong is a byte-count mismatch on the
> first object of the class, not corrupt values: the loop consumes the wrong
> number of bytes and §8 catches it.

**`TList` is the example to keep in mind.** Its recorded streamer info lists a
`TSeqCollection` base, which in turn lists a `TCollection` base holding `fName`
and `fSize`. `TList::Streamer` writes none of that: it writes a `TObject`, then
`fName`, then a count and the entries
([Streamer information §4](StreamerInfo.md#4-tlist)). A reader that follows the
info reads three nested objects that are not there.

> Observed in an ordinary ROOT file, not constructed: a `TGraph`'s `fFunctions`
> member is a `TList*`, and following the recorded info for it fails on the
> `TSeqCollection` base. `tools/coverage_probe.py` reports exactly that when the
> hand-written reader is bypassed.

### 7.1 An object with no byte count

A generated `Streamer` always writes a byte count
([Buffer framing §2.3](Buffer.md#23-a-records-object-data-does-not-always-begin-with-one)).
So an object of a class outside that section's list that has **no byte count at
all** was written by something else — in a ROOT-written file, by the class's own
hand-written `Streamer`. This is the one place where the file shows a trace of
§7, and it shows the trace without saying what to do about it: such an object
may or may not have a version word, and **what ROOT does depends on a dictionary
that is not in the file**.

- **With the class's library,** ROOT runs that `Streamer`, whatever it does.
- **Without it, for a class deriving from `TObject`,** there is **no version
  word** either. ROOT gives such a class the emulated `TObject` streamer
  (`root/core/meta/src/TClass.cxx:6223`, `root/core/meta/src/TClass.cxx:6287`,
  `root/core/meta/src/TClass.cxx:6342`), which calls `ReadClassEmulated`
  (`root/core/meta/src/TClass.cxx:6938-6942`). That reads the first two bytes as
  a version, to choose a streamer info, and then — *"We attempt to recover if a
  version count was not written"* — finds no byte count, **rewinds to the
  object's first byte**, and applies the info's elements from there
  (`root/io/io/src/TBufferFile.cxx:3412-3436`). The first two bytes are then read
  a second time, as the version word of the class's first base, which is
  normally `TObject`'s. The info chosen is the one at the version those two bytes
  give, and failing that the class's current version
  (`root/core/meta/src/TClass.cxx:4706-4714`), which for a class ROOT knows only
  from the file is the version of the first info the file gave for it
  (`root/io/io/src/TStreamerInfo.cxx:928`).
- **Without it, for any other class,** ROOT calls `ReadClassBuffer`
  (`root/core/meta/src/TClass.cxx:6336-6340`,
  `root/core/meta/src/TClass.cxx:6973-6976`), which takes the first two bytes as
  a version word and reads the elements after it.
- **For a class of ROOT's own,** there is always a dictionary, and its
  `Streamer` reads a version word first. That is how ROOT reads the g4tools
  records of [Buffer framing §2.3](Buffer.md#23-a-records-object-data-does-not-always-begin-with-one).

Two files in reach meet the second case, and ROOT 6.40.04, without either
library, reads one of them right and the other wrong:

> **`skim.root`** (`root/roottest/root/io/evolution/`, ROOT 4.03/05). In the
> split `TClonesArray` column `Jpsi.jmu1`, each entry is one `HoldMuo`, 122 bytes:
> `00 01 | 00 00 00 00 | 03 00 00 00`, the class's thirteen scalars, then a
> byte-counted `HoldPtl`. That is a `TObject` base, the members, and nothing
> before them. ROOT's reading gives `Jpsi.jmu1.ptl.pt` 3.425 in `TTree::Scan`,
> equal to the same muon's `Muo.ptl.pt`. The version-first reading ends at 120.
>
> **`uproot-issue475.root`** (`gen/foreign/`). `nEXO::SmartRef`'s info lists a
> `TObject` base and a `Long64_t` — 18 bytes — and every object is **20**. Read as
> an entry of `SimHeader`'s `m_event` branch, the first is
> `00 01 | 00 00 00 02 | 03 00 00 00 | 00 × 10`. ROOT, with no nEXO library, reads
> 18 of the 20 and says so on every pointer in `navigator`'s `m_refs`:
> `object of class nEXO::SmartRef read too few bytes: 37 instead of 39`. Two
> bytes that no element describes, as in `TRef`'s `pidf` — a hand-written
> `Streamer` that its info does not describe (§7), which **no reader can decode
> from the file**. The version-first reading *does* end at 20, and is wrong: it
> reads the `TObject` base's version word as `00 00`.

A reader has no dictionaries, so it is in ROOT's position without one for every
class that is not ROOT's own, and SHOULD read such an object as ROOT then does.
Where it cannot tell whether a class is ROOT's, the bytes can decide, and on
every file in reach they do. A reading of an object with no byte count is
**rejected** when

1. a `TObject` base inside it has a version word other than 1, which ROOT never
   writes ([Buffer framing §7](Buffer.md#7-the-tobject-base), invariant 10); or
2. it does not end where something enclosing it says it must — the entry's
   end in a basket, or the byte count of an object slot around it.

A reader SHOULD take ROOT's no-dictionary reading unless it is rejected, then the
version-first reading unless it is rejected, and otherwise report the object as a
hand-written `Streamer` its info does not describe. **Neither test is enough
alone**: `SmartRef`'s version-first reading passes the second and fails the
first, and a version word of 1 can pass the first as a `TObject`'s.

> **This project's reader passed `uproot-issue475.root` for the wrong reason
> until 2026-09-23.** It read every unframed object version first, which landed
> exactly on each `SmartRef`'s end, and failed `skim.root`, which ROOT reads
> correctly. `PLAN-corpus.md` C18 left it open for exactly that reason: applying
> ROOT's rule everywhere moved the failure from one file to the other, until the
> second file turned out not to be decodable at all. `tools/check_invariants.py`
> now reports its two `SimHeader`/`ElecHeader` baskets as skipped, by that name.

## 8. Resynchronisation

Two properties make a partial reader viable, and both come from the byte count.

**Every unknown thing is skippable.** Any element whose code the reader does not
implement can be stepped over if it carries a byte count, and every object-valued
code except 65, 66 and 70 does
([Element types §7](ElementTypes.md#7-object-valued-codes-61-to-71)).

**Every object ends where its byte count says.** After the element loop, a reader
MUST seek to the position the object's byte count implies, whatever the loop
consumed. ROOT does this unconditionally and reports the discrepancy as an error
without failing the read (`root/io/io/src/TBufferFile.cxx:365-397`).

A non-zero discrepancy means the description and the bytes disagree. It is not
necessarily a corrupt file — it is the routine symptom of a `Streamer` that is
out of step with its class, which ROOT reports as
`Streamer() not in sync with data on file` (`root/io/io/src/TBufferFile.cxx:387`)
and then reads past.

> The one case where the byte count is deliberately abandoned is a recovered
> streamer info, where ROOT sets the count to 0 to suppress the check entirely
> (`root/io/io/src/TBufferFile.cxx:3674`). A reader has no equivalent state and
> SHOULD always trust the count.

## 9. Reading

To read an object whose class, version and byte range are known:

1. Obtain the streamer info for that class and that class version from the
   file's `StreamerInfo` record. If there is none, go to step 8.
2. Let `elements` be that info's `fElements`, in array order.
3. For each element in turn:
    1. If `fType` is -1, consume nothing and continue.
    2. If `fType` is 0, 66 or 67, read the base class: consume the framing of
       [Element types §6](ElementTypes.md#6-kbase-0-and-knotype-1), then apply
       this procedure recursively with the base class and the version just read.
    3. If `fType` names an object-valued code (61 to 71), consume the framing of
       [Element types §7](ElementTypes.md#7-object-valued-codes-61-to-71),
       determine the class from the class record where one is present and from
       `fTypeName` otherwise, and apply this procedure recursively. If the
       object has no byte count and its class derives from `TObject`, choose
       between its two readings as §7.1 says.
    4. If `fType` is 500 or 501 on a `TStreamerSTL`, read a collection as
       specified in `02-serialization/Collections.md`.
    5. If `fType` is 500 on any other element, the member is opaque: seek to the
       end of its byte count.
    6. Otherwise consume the fixed number of bytes
       [Element types](ElementTypes.md) specifies, taking any count from the
       `kCounter` element named in `fCountName`.
    7. Record the value, and if the element is a `kCounter`, retain it for later
       elements.
4. Compare the position reached with the end implied by the object's byte count.
5. If they differ, the file and the description disagree; report it.
6. Seek to the end implied by the byte count regardless.
7. Done.
8. No streamer info: seek to the end implied by the byte count and record the
   object as unread. If there is no byte count, the read cannot continue and the
   reader MUST stop.

Step 8's final clause is the real constraint. A byte count is what bounds the
damage, so the codes that carry none — 65, 66, 70, and the scalars — must all be
implemented for any class the reader claims to support.

## 10. Invariants

1. Applying this procedure to a record's top-level object consumes exactly
   `fObjlen` bytes.
2. Applying it to any nested object consumes exactly the bytes its byte count
   delimits.
3. Every element's `fCountName`, where non-empty, names an element of an integer
   basic type — `kCounter` (6) usually, but `kInt` (3) or `kUInt` (13) are
   legitimate ([Element types §2.1](ElementTypes.md#21-kcounter-6)) — either
   earlier in the same list, or in the info named by its `fCountClass`, which is a
   base of this class (§3.2).
4. Every `TStreamerBase` element precedes every non-base element of the same
   streamer info — except that a base which is an **STL container** is written as
   a `TStreamerSTL` and may precede it (§4.3).
5. Every class named by a `TStreamerBase` element, and every class named in the
   `fTypeName` of a member whose bytes are written **inline** — codes 61, 62, 63
   and 68, with `kOffsetL` where it applies — has a streamer info in the same
   file, unless its `Streamer` is hand-written or forwarding, or it is an STL
   container (§6.1, which has the three lists and the measurement). A member of
   code 64 or 69 carries **no** such requirement: it may be null in every object
   the file holds, and a non-null one names its class in the bytes.
6. An element with `fType` of -1 is a `TStreamerBase` whose info carries
   `kIgnoreTObjectStreamer`.

Invariants 1 and 2 are the whole specification restated as a check: a reader that
satisfies them on a file has parsed every framing decision in it correctly.

## 11. Errata

Against `root/io/doc/TFile/*.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | — | No document states the order of operations at all: that bases precede members, that the order is `fElements` order, and that there is no padding (§3, §4) |
| 2 | `ttree.md` prints `offset=` for every member of every class it tabulates | `fOffset` is transient and not in the file. The printed zeros are an artefact of an uncompiled streamer info, and a reader that takes them for buffer positions gets a plausible-looking answer for the first member and nonsense after (§3.1) |
| 3 | — | Nothing says that a class with a hand-written `Streamer` still has a streamer info, and that the two need not agree (§7). This is the single largest trap for an implementer, because the file gives no warning |
| 4 | — | Nothing describes the counter dependency between elements, or that no length is written for a counted array (§3.2) |
| 5 | — | Nothing describes `fType` of -1, so a reader built from the shipped documentation desynchronises on any class that suppresses its `TObject` base (§4.2) |
| 6 | — | Nothing states that a byte-count mismatch is recoverable and routine rather than fatal (§8) |

## 12. Reference files

| Case | Exercises |
|---|---|
| `serialization/version-zero` | Base-class recursion two deep: `TH1L` → `TH1` → `TNamed` → `TObject` |
| `serialization/arrays` | The counter dependency, with the counted array both present and absent |
| `serialization/objects` | Nested objects through embedded members and through pointers |
| `serialization/streamer-info` | The element list the loop is driven by |
| `container/file-minimal` | The top-level entry point, and invariant 1 on a whole record |

`tools/rootfile.py` implements this procedure and `tools/check_invariants.py`
applies invariants 1 and 2 to every record of every reference file, and 3 to 6 to
every streamer info in it.
