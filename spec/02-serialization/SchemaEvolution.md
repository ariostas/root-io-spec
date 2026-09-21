# Schema evolution

What a reader does when the class it has and the class in the file are not the
same class.

Most of ROOT's schema evolution machinery exists to reconcile a file with a
*compiled* C++ class. A third-party reader has no compiled classes, so almost
none of that machinery applies to it: it reads what the file says and produces a
value tree. What it does need from this document is narrower and specific:

- how to pick the right streamer info when there is more than one for a class;
- what a class version of 0 means, and why the number in the file is not the
  number ROOT reports;
- which type codes it will never see, so it can stop looking for them;
- what the `listOfRules` entry in the `StreamerInfo` record is.

## 1. Two version numbers, and only one of them is in the file

| Name | On disk | Meaning |
|---|---|---|
| `fClassVersion` | **yes** | the described class's version, as written |
| `fOnFileClassVersion` | no | a copy of the above, kept because ROOT overwrites `fClassVersion` |
| `fOldVersion` | no | the version of the **`TStreamerInfo` record itself**, not of the described class |
| `fNVirtualInfoLoc` | no | emulated-object bookkeeping |

`fOnFileClassVersion` is set from `fClassVersion` immediately after reading it
(`root/io/io/src/TStreamerInfo.cxx:5624`) and then never changes. ROOT
*renumbers* `fClassVersion` in memory when it cannot match the info to a slot —
it becomes the array slot it was filed under
(`root/io/io/src/TStreamerInfo.cxx:1111`,
`root/io/io/src/TStreamerInfo.cxx:1123`).

> `TStreamerInfo::GetClassVersion()` therefore returns the **slot**, not the
> file's number, and a reader comparing its own parse against `ShowStreamerInfo`
> output can see a different version for the same bytes. The file's number is
> `GetOnFileClassVersion()`.

`fOldVersion` is a different thing wearing a similar name: it is the class
version of the `TStreamerInfo` *record*, currently 10
(`root/io/io/inc/TStreamerInfo.h:256`), and it gates the record's own layout —
see [Streamer information §6.1](StreamerInfo.md#61-version-dependent-reader-behaviour).

### 1.1 The version is written as an absolute value

```
R__b << ((fClassVersion > 0) ? fClassVersion : -fClassVersion);
```

`root/io/io/src/TStreamerInfo.cxx:5686`. An in-memory version of **-1** — which
is what ROOT assigns to a loaded foreign class
(`root/core/meta/src/TClass.cxx:6064-6074`) and to a conversion info
(`root/core/meta/src/TClass.cxx:7279`) — therefore appears on disk as **1**, and
is indistinguishable from a genuine version 1.

A reader MUST NOT treat `fClassVersion` as signed data, and MUST NOT expect a
file to distinguish "version 1" from "unversioned".

## 2. Class version 0, and foreign classes

These are two different things that produce the same version word, and telling
them apart is the single most consequential ambiguity in the format. The rule is
in [Buffer framing §4](Buffer.md#4-a-version-word-of-0-has-two-different-meanings);
this section says what the two situations *mean*.

| | Declares version 0 | Foreign |
|---|---|---|
| Source | `ClassDef(C, 0)` | no `ClassDef` at all |
| Intent | "this class is transient" | "I/O layout is identified by checksum" |
| Version word | 0 | 0 |
| Checksum after it | **no** | **yes** |
| `fClassVersion` in the streamer info | 0 | 1 |
| Cited | `root/core/meta/src/TClass.cxx:5736-5742` | `root/core/meta/src/TClass.cxx:6052-6058` |

**Version 0 really does mean transient — for data members only.**
`TStreamerInfo::Build` skips the data-member loop entirely when the class version
is 0 (`root/io/io/src/TStreamerInfo.cxx:548-550`). Base classes are collected by
a *separate, earlier* loop (`root/io/io/src/TStreamerInfo.cxx:469`) and are not
skipped, so a version-0 class with bases writes a full payload.

> `serialization/version-zero` is that case: `TH1L` declares version 0, has two
> base classes, and its byte count is 554.

**Foreign means "no `Streamer` method"** — `IsForeign` is literally a test for
that (`root/core/meta/src/TClass.cxx:6052-6058`). Every class defined in the
interpreter is foreign, which is why most fixtures in this repository are.

> `serialization/basic-types` and `serialization/schema-rules` are both foreign:
> version word 0 followed by a `u32` checksum.

## 3. Checksums

A checksum is a hash over the class's name, its base classes and its members.
There are **eight** of them (`root/core/meta/inc/TClass.h:111-122`), differing in
what they include:

| Value | Name | Era |
|---|---|---|
| 1 | `kNoEnum` | since 3.3 |
| 2 | `kReflexNoComment` | up to 5.34.18 |
| 3 | `kNoRange` | up to 5.17 |
| 4 | `kWithTypeDef` | up to 5.34.18 |
| 5 | `kReflex` | up to 5.34.18 |
| 6 | `kNoRangeCheck` | up to 5.34.18 |
| 7 | `kNoBaseCheckSum` | up to 5.34.18 |
| 8 | `kLatestCheckSum` | current |

**`TStreamerInfo::fCheckSum` on disk is always variant 8** as computed by the
writing ROOT (`root/io/io/src/TStreamerInfo.cxx:447`,
`root/core/meta/src/TClass.cxx:6676`). The other seven exist so that ROOT can
recognise a checksum written by an older release, which it does by brute force —
recomputing with every variant until one matches
(`root/io/io/src/TStreamerInfo.cxx:3546-3553`).

The algorithm itself is in
[Streamer information §11](StreamerInfo.md#11-checksums). Variant 8 differs from
7 in that it folds in each base class's own checksum
(`root/io/io/src/TStreamerInfo.cxx:3597-3600`).

> A reader that only ever reads files written by a recent ROOT needs one
> algorithm. A reader that verifies checksums on old files needs all eight, and
> SHOULD instead treat a checksum mismatch as a warning rather than an error —
> the checksum is a lookup key, not an integrity check.

### 3.1 `fCheckSum` of 0 means the writer could not compute one

**It is not a legitimate value and not a lookup key.** Every variant of the
algorithm begins by folding the class name (§11 of
[Streamer information](StreamerInfo.md#11-checksums)), so the least it can produce
is that fold — which is 0 only for an empty name, and a class has a name. A reader
that meets 0
MUST treat the field as **absent**: it cannot be used for §4 step 2, and it must
not be compared with a computed value, because a match would be an accident.

`TClass::GetCheckSum` has exactly one path that returns it — a base class whose
meta information is unavailable, where it prints
`Error("GetCheckSum", "Calculating the checksum for (%s) requires the base class
(%s) meta information to be available!")`, sets `isvalid` to `kFALSE` and returns
0 (`root/core/meta/src/TClass.cxx:6704-6710`). `TStreamerInfo::Build` then stores
that 0, because it calls the single-argument overload and never sees `isvalid`
(`root/io/io/src/TStreamerInfo.cxx:447`). So the file records a failure the
writing session was told about and a reader cannot see.

> Measured across `data/` and both corpora, 307 files carrying infos: **two**
> entries have `fCheckSum` 0, both in `uproot-issue283.root` (ROOT 5.28/00) —
> `Sni3DataArray` and `I3Eval_t::ChannelContainer_t`, class version 1, no
> elements.
>
> Their emptiness is not the explanation. **247 other infos across those files
> also have no elements, and every one carries the fold of its own class name**:
> `TString` `0x00017419`, `TAtt3D` `0x0000757a`, `TQObject` `0x00042e9c`,
> `TAttBBox2D` `0x002549fc`, `RooPrintable` `0x017097c5`, `RooDirItem`
> `0x0028c88e`, `KM3NETDAQ::JDAQHit` `0x530441c9`, `MGVMemoryCheckable`
> `0x752eeea5`. An empty element list is ordinary and its checksum is well
> defined. The two zeros would have been `0x04442992` and `0x4c1ebbfe`.
>
> It is therefore **not** a marker for a custom streamer, which is the natural
> guess: the 247 include classes whose `Streamer` is hand-written, and they carry
> proper checksums.

## 4. Choosing a streamer info

Given a class name and a version word, a reader picks an entry from the file's
`StreamerInfo` list:

1. If the version word is positive, take the entry whose `fClassVersion` equals
   it. If exactly one entry exists for the class, take it.
2. If the version word is 0 or negative, apply
   [Buffer framing §4](Buffer.md#4-a-version-word-of-0-has-two-different-meanings):
   no checksum if some entry has `fClassVersion == 0`, otherwise read a `u32`
   checksum and take the entry whose `fCheckSum` matches.
3. If no entry matches, the object is not readable. Skip it by its byte count
   ([Streamer-driven reading §6](StreamerDriven.md#6-when-there-is-no-usable-streamer-info)).

That is the whole algorithm for a reader with no compiled classes, and it is
simpler than ROOT's, which additionally has to decide whether to trust its own
compiled layout. ROOT's choice between matching by version and matching by
checksum is made at `root/io/io/src/TStreamerInfo.cxx:1043-1095`, and it matches
by **checksum** whenever the class is foreign or its on-file version is below 2.

> **A file can legitimately carry several infos for the same class with the same
> `fClassVersion`.** Foreign classes are all written as version 1, so two
> different layouts of the same interpreted class in one file are distinguished
> only by checksum. Step 1's "exactly one entry" shortcut is what makes step 2
> necessary rather than optional.

## 5. Codes that cannot appear in a file

`TVirtualStreamerInfo::EReadWrite` contains many values a file never holds. They
are produced by `TStreamerInfo::Compile` into the transient `fComp` table, or by
`BuildOld` into elements that `TStreamerInfo::Streamer` filters out before
writing:

| Value | Name | Produced by | Means, in memory |
|---|---|---|---|
| 100+T | `kSkip` | `root/io/io/src/TStreamerInfoActions.cxx:4323` | read the on-file member and discard it |
| 120+T, 140+T | `kSkipL`, `kSkipP` | same | the array and counted-pointer forms |
| 200+T | `kConv` | `root/io/io/src/TStreamerInfoActions.cxx:4317` | read as `T`, convert to a different in-memory type |
| 220+T, 240+T | `kConvL`, `kConvP` | same | the array forms |
| 600 | `kCache` | nothing — dead in 6.40.04 | — |
| 1000 | `kArtificial` | `root/io/io/src/TStreamerInfo.cxx:4917` | a member produced by a rule, not by the file |
| 1001, 1002 | `kCacheNew`, `kCacheDelete` | `root/io/io/src/TStreamerInfo.cxx:2857-2864` | brackets around a cached region |
| 99997 | `kNeedObjectForVirtualBaseClass` | `root/core/metacling/src/TCling.cxx:3117` | an *offset* sentinel |
| 99999 | `kMissing` | `root/io/io/src/TStreamerInfo.cxx:2694` | an *offset* sentinel: nowhere to put the value |
| -2 | `kUnsupportedConversion` | `root/io/io/src/TStreamerInfo.cxx:2817-2819` | an `fNewType`, not an `fType` |

Three of these are not type codes at all: `kMissing`, `kUnsupportedConversion`
and `kNeedObjectForVirtualBaseClass` live in `fOffset` or `fNewType`, both
transient.

The filtering on write is explicit: elements that are `TStreamerArtificial`, or
carry `kRepeat`, or carry `kCache` without `kWrite`, are not written
(`root/io/io/src/TStreamerInfo.cxx:5697-5706`). `TStreamerArtificial` is even
declared `ClassDefOverride(TStreamerArtificial, 0)` so that it cannot be
persisted by accident (`root/core/meta/inc/TStreamerElement.h:476`).

> **`kAnyPnoVT` (70) is not an exception, despite appearances.** There is a case
> for it in the write switch (`root/io/io/src/TStreamerInfoWriteBuffer.cxx:456-457`),
> which makes it look like a legitimate on-disk code, but nothing can reach it:
> `TStreamerObjectAnyPointer`'s constructor sets `kAnyP` (69), or `kAnyp` (68) when
> the title begins `->`, and never 70
> (`root/core/meta/src/TStreamerElement.cxx:1626-1632`), and that is the class
> `TStreamerInfo::Build` creates for every non-`TObject` pointer member
> (`root/io/io/src/TStreamerInfo.cxx:744`). It occurs in **no** streamer info in any
> of this project's reference files or either corpus, which is why
> [Element types §11](ElementTypes.md#11-invariants) excludes it from the on-disk
> set. Treat the write case as dead code.

[Element types §11](ElementTypes.md#11-invariants) states the on-disk set as a
checkable invariant.

## 6. Rules, and the `listOfRules` entry

A schema rule is a fragment of C++ that ROOT runs to fill a member the file does
not contain, or to convert one that changed shape. Rules come from `#pragma read`
in a dictionary, from a selection XML, or from `TClass::AddRule` at runtime; they
are **not** part of `ClassDef`.

> **They are written into the file, and ROOT never reads them back.**

### 6.1 The shape on disk

`TFile::WriteStreamerInfo` builds a `TList`, names it `listOfRules`, marks it
owner, fills it with a `TObjString` per rule, and appends it to the
`StreamerInfo` list (`root/io/io/src/TFile.cxx:3512-3514`,
`root/io/io/src/TFile.cxx:3530-3535`, `root/io/io/src/TFile.cxx:3546-3548`).

So the `StreamerInfo` record's `TList` is **not** a list of `TStreamerInfo`. It
is a list of `TStreamerInfo` plus, optionally, one nested `TList`:

```
StreamerInfo TList
├── TStreamerInfo            one per class
├── ...
└── TList  fName="listOfRules"     ← at most one, always last
    ├── TObjString   one rule, as text
    └── ...
```

The nested list is an ordinary object slot in the same list, so a reader that
assumes every entry is a `TStreamerInfo` will misread it. **Recognise it by the
nested list's `fName`**, not by its position or its class — `TList` is also a
plausible thing to find in a file.

Each rule is text of the form produced by `TSchemaRule::AsString`
(`root/core/meta/src/TSchemaRule.cxx:250-312`): space-separated `key="value"`
tokens, beginning with a bare `type=read` or `type=readraw`, in this order —
`type`, `sourceClass`, `targetClass`, `version`, `checksum`, `source`, `target`,
`include`, `attributes`, `code`. The compiled function pointers are not written,
necessarily.

> Demonstrated by `serialization/schema-rules`: the record's `TList` reports two
> entries; the second is a `TList` whose `fName` is `listOfRules`, whose `fBits`
> is `0x00004000` (`TCollection::kIsOwner`), and whose one `TObjString` holds
> 134 characters ending in a space.

### 6.2 ROOT ignores it

The code in `TFile::ReadStreamerInfo` that would apply the rules is inside an
`#if 0`, under the comment "Completely ignore the rules for now"
(`root/io/io/src/TFile.cxx:3363-3372`). The entry is recognised by name only so
that it does not trigger the warning the `else` branch emits
(`root/io/io/src/TFile.cxx:3375`).

A rule that matters must therefore come from the reader's own dictionary. For a
third-party reader the consequence is simple and slightly liberating: **the
`listOfRules` entry is documentation, not instruction.** It is worth surfacing to
a user, and it MUST be skipped rather than parsed as a streamer info, but nothing
about the bytes depends on it.

### 6.3 Rules do not change the streamer info

A class with rules is written exactly as a class without them. The rule in
`serialization/schema-rules` names `fOld` as a source and `fNew` as a target, and
the streamer info still carries both as ordinary `TStreamerBasicType` elements of
type 3. No `kConv`, `kSkip` or `kArtificial` element exists until `BuildOld` runs
in a reader that has the rule.

## 7. Emulated classes

When ROOT has no compiled class it builds one from the file's streamer info
(`root/io/io/src/TStreamerInfo.cxx:928`). A third-party reader is *always* in
this position, so it is worth saying what changes and what does not.

**The parse does not change.** The bytes consumed are governed by the on-file
`fType` of each element either way.

What changes is all in memory: object layout is synthesised with alignment
(`root/io/io/src/TStreamerInfo.cxx:2697-2726`), a hidden `TStreamerInfo*` slot is
added to each object (`root/io/io/src/TStreamerInfo.cxx:2253-2257`), and version
matching leans on the checksum (§4).

The one case where emulation *does* change the interpretation is a file written
before ROOT 3 (`file version < 30000`), where `BuildEmulated` demotes `kLong` and
`kULong` to `kInt` and `kUInt` and injects synthetic counter elements
(`root/io/io/src/TStreamerInfo.cxx:1455-1472`). That is a legacy path a modern
reader can decline to implement, but it should decline explicitly rather than
produce wrong numbers.

### 7.1 ROOT cannot read an emulated class that derives from `TObject`

A reader implementing this document is in a position ROOT is not: it reads every
class the same way. ROOT has a second path, and on it emulation **fails
silently**.

`TKey::ReadObj` splits on `cl->IsTObject()`. A class that is not `TObject`-derived
goes through `ReadObjectAny` (`root/io/io/src/TKey.cxx:811-812`) and thence through
the streamer info, so emulation works. A class that *is* gets
`tobj->Streamer(bufferRef)` (`root/io/io/src/TKey.cxx:883`) — and with no compiled
class there is no override to dispatch to, so that resolves to
`TObject::Streamer`, which reads a version word, `fUniqueID` and `fBits`, and
stops.

**Measured, on a file ROOT wrote itself.** A class `Marked : public TObject` with
`Int_t fA = 77` and `Double_t fB = 1.25`, written by a session with the
dictionary and read back by one without it: `TFile::Get` returns a
default-constructed object, `fA` and `fB` both 0. The only message is
`Warning in <TClass::Init>: no dictionary for class Marked is available`, which
says nothing about the members. `tools/rootfile.py`, reading the same bytes
through the same streamer info, recovers 77 and 1.25.

Three qualifications:

- **it applies only to a top-level record.** The same class as a *member* of
  another object reads correctly, because that path goes through
  `TStreamerInfo::ReadBuffer`;
- **ROOT's source knows.** The compressed-payload branch four lines above says
  *"Even-though we have a TObject, if the class is emulated the virtual table may
  not be 'right', so let's go via the TClass"*
  (`root/io/io/src/TKey.cxx:877-878`) — but only takes that branch when the unzip
  fails;
- **it is a reason not to derive persistent classes of your own from `TObject`**,
  which is where
  [Writing an object §8.7](../06-writing/WritingObjects.md#87-do-not-derive-your-own-classes-from-tobject)
  says it from the writing side.

## 8. Reading

For each entry of the `StreamerInfo` record's `TList`:

1. If the entry's class is `TStreamerInfo`, read it
   ([Streamer information §12](StreamerInfo.md#12-reading)).
2. If the entry's class is `TList` and its `fName` is `listOfRules`, its members
   are `TObjString`s holding rule text. Retain them or discard them; do not
   attempt to apply them.
3. Any other class is unexpected. Skip it by its byte count and report it — this
   is what ROOT does (`root/io/io/src/TFile.cxx:3375`).

To select an info for an object: §4.

To read a member the reader's target does not have, or to leave a target member
the file does not supply: nothing. Neither changes any bytes
([Streamer-driven reading §3](StreamerDriven.md#3-the-element-loop)).

### 8.1 A class may appear twice in one `StreamerInfo` record

ROOT does not deduplicate the list, because a `TStreamerInfo`'s identity is per
*instance* rather than per class: a session that read one info from an input file
and built another for the same class holds two, and writes both
([Writing an object §8.4](../06-writing/WritingObjects.md#84-one-class-two-versions-in-one-file)).

A reader MUST tolerate the duplicate. What it must *not* do is assume the two
entries are interchangeable, because two different things produce the pair:

- **the same layout twice.** Same `fClassVersion`, same `fCheckSum`, same
  elements, differing only in `fBits`. Either entry will do;
- **two layouts.** Different `fClassVersion`, or the same version with different
  checksums — which is the schema-evolution case of §3 and §4, and there the
  object's version word selects between them.

So a reader that indexes the list by `(class, version)` and asserts uniqueness
will reject ordinary files, and one that indexes by class alone and keeps the
last entry can silently decode objects with the wrong layout.

**Which `fBits` differ is not fixed, and a reader MUST NOT key on any of them.**
`fBits` is written wholesale through the `TNamed` base, so what reaches disk is
the writing session's in-memory status — including, in every case measured, the
`TObject` allocation bits `kIsOnHeap` and `kNotDeleted`
(`root/core/base/inc/TObject.h:90-91`), which say only that the object was on the
heap and had not been destructed.

> Measured across `data/` and both corpora: **three files carry a duplicate**,
> all of them `ROOT::TIOFeatures` version 1, checksum `0x1aa12f10`, and the
> differing bit is **not the same one**:
>
> | File | `fBits` | Differ in |
> |---|---|---|
> | `uproot-issue121.root` (6.18/00) | `0x3000000`, `0x3010000` | `kIsCompiled`, `BIT(16)` (`root/core/meta/inc/TVirtualStreamerInfo.h:82`) |
> | `uproot-issue243.root` | `0x3030000`, `0x3010000` | `kBuildOldUsed`, `BIT(17)` (`root/core/meta/inc/TVirtualStreamerInfo.h:86`) |
> | `uproot-issue-750.root` | `0x3030000`, `0x3010000` | `kBuildOldUsed` |
>
> In the second and third, **both** entries carry `kIsCompiled`; what separates
> them is that one had been through `BuildOld` in the writing session and the
> other had not (`root/io/io/src/TStreamerInfo.cxx:1885`). That is session state
> and nothing else — which is the point.
>
> The fourth duplicate in `data/` is the other kind: `data/written/two-versions.root`
> holds `Grown` at versions 1 and 2 with different checksums, where the two
> entries describe genuinely different layouts and the version word chooses.

## 9. Invariants

1. Every `fClassVersion` in a `StreamerInfo` record is non-negative and at most
   65000.
2. Every entry of the `StreamerInfo` `TList` is a `TStreamerInfo`, or a `TList`
   whose `fName` is `listOfRules`.
3. At most one `listOfRules` entry exists, and every member of it is a
   `TObjString`.
4. Every `TObjString` in a `listOfRules` begins with `type=read ` or
   `type=readraw `.
5. No element of any streamer info has an `fType` in the `kSkip`, `kConv` or
   `kCache` families, or equal to 1000, 1001, 1002, 99997, 99999 or -2. (Stated
   and checked as [Element types §11](ElementTypes.md#11-invariants).)
6. Two entries for one class that agree on **both** `fClassVersion` and
   `fCheckSum` have **identical element lists** — same count, and each element
   matching in class, `fName`, `fType`, `fTypeName`, array shape and `fTitle`.
   This is what makes §8.1's "take either entry" safe. Entries that disagree on
   either field describe different layouts and are selected by the object's
   version word (§4), not by position in the list.

**There is deliberately no uniqueness invariant.** Two entries for one class may
share a `fClassVersion` and differ in `fCheckSum`, which §3 says is how an
unversioned class is disambiguated; and they may agree on *both*, which §8.1 shows
ROOT writing. A reader must index the list in a way that tolerates either.
Invariant 6 is the weaker statement that replaces uniqueness.

Invariant 2 is the one that gives checksums their job: it is what makes §4 step 2
well defined.

## 10. Errata

Against `root/io/doc/TFile/streamerinfo.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | "a `TList` … containing elements of class `TStreamerInfo`" | The list can also hold a nested `TList` named `listOfRules` (§6). Nothing in the shipped documentation mentions it, and a reader built from that text will treat it as a corrupt streamer info |
| 2 | "This checksum … is computed by `TClass::GetCheckSum()`" | There are eight checksum algorithms; the written one is variant 8, and recognising an old file's checksum may require all seven others (§3) |
| 3 | "`fClassVersion` = Version of class" | What is written is the **absolute value**, so an in-memory -1 appears as 1 (§1.1). It also omits that the in-memory number is renumbered on read, so ROOT's own reports disagree with the file (§1) |
| 4 | The `fType` table lists neither the `kSkip`/`kConv`/`kCache`/`kArtificial` families nor the fact that they cannot occur | A great deal of reverse-engineering time is spent on codes that are unreachable from a file (§5) |
| 5 | — | Nothing says a file may hold several infos for one class with the same `fClassVersion`, which is routine for foreign classes and is why checksums exist (§4) |
| 6 | — | Nothing distinguishes a class that declares version 0 from a foreign class, though the two produce different bytes after the same version word (§2) |

## 11. Reference files

| Case | Exercises |
|---|---|
| `serialization/schema-rules` | The `listOfRules` entry: a nested `TList` of `TObjString`, and a class whose rules change nothing about its streamer info |
| `serialization/basic-types` | A foreign class: version word 0 followed by a checksum, with `fClassVersion` 1 in the streamer info |
| `serialization/version-zero` | A class that declares version 0: version word 0 with no checksum, and a full payload because it has base classes |

| `written/two-versions` | Two infos for one class at **different versions**, with an object at each, which §4 chooses between by the version word. Written by this project: no single ROOT session can produce such a file, though two can — [Writing an object §8.4](../06-writing/WritingObjects.md#84-one-class-two-versions-in-one-file) |

No fixture covers two infos for one class distinguished by **checksum** at the
same version, a `type=readraw` rule, a negative in-memory class version reaching
disk as 1, or a file old enough to take the `BuildEmulated` path. The first three
need two ROOT sessions with different definitions of the same class — measured for
this document and reported in
[Writing an object §8.5](../06-writing/WritingObjects.md#85-when-the-versions-collide-the-file-wins-and-members-are-lost),
where the collision turns out to cost data; the last needs a ROOT older than any
that can still be built here.
