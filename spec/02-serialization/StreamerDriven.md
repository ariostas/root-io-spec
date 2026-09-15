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

For code 0 the recursion is literal: ROOT calls back into `ReadClassBuffer` for
the base class (`root/core/meta/src/TStreamerElement.cxx:813-845`), which reads a
version word and runs this same loop. The version word belongs to the **base
class**, not to the derived class, and it is the version that selects the base's
streamer info.

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

**The class is absent from the file's `StreamerInfo` record.** This is a broken
file for every class except the bootstrap set and the classes written without a
streamer info at all (`TFile`, `TDirectory`, the free list). A reader SHOULD
report it rather than guess.

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

## 7. When the streamer info does not describe the bytes

> **A class with a hand-written `Streamer` still has a streamer info in the file,
> and that streamer info can be a complete fiction.**

`TStreamerInfo::Build` constructs elements from the class's data members
(`root/io/io/src/TStreamerInfo.cxx:469-560`) whether or not those members are
what the class actually writes. A `Streamer` written by hand may write the
members in a different order, write fewer of them, write extra values, or write a
different shape entirely.

**Nothing in the file marks this.** `TClass::fStreamerType`, which is what ROOT
dispatches on, is a transient member (`root/core/meta/inc/TClass.h:285`,
`root/core/meta/inc/TClass.h:344`) computed from the compiled dictionary. A
reader therefore cannot detect a hand-written streamer; it has to know, from a
list, which classes have one.

That list is the entire content of `spec/03-classes/`, and it is small: the
divergent classes are essentially `TFile`/`TDirectory`, the collections, the
reference types, and parts of `TTree`. For everything else — including every
class a user defines — the streamer info is authoritative.

> The practical symptom of getting this wrong is a byte-count mismatch on the
> first object of the class, not corrupt values: the loop consumes the wrong
> number of bytes and §8 catches it.

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
       `fTypeName` otherwise, and apply this procedure recursively.
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
   `fObjLen` bytes.
2. Applying it to any nested object consumes exactly the bytes its byte count
   delimits.
3. Every element's `fCountName`, where non-empty, names an element of the same
   streamer info that precedes it and whose `fType` is 6 (`kCounter`).
4. Every `TStreamerBase` element precedes every non-base element of the same
   streamer info.
5. Every class named by a `TStreamerBase` element, and every class named in the
   `fTypeName` of an element with an object-valued code, has a streamer info in
   the same file — unless it is `TObject`, `TNamed` or `TString`, which are read
   by hardcoded rules.
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
applies invariants 1 and 2 to every record of every reference file.
