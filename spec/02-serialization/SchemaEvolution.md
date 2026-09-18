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

## 8.1 A class may appear twice in one `StreamerInfo` record

ROOT does not deduplicate the list. A record can hold two entries for one class
with the same `fClassVersion`, the same `fCheckSum` and the same elements,
differing only in `fBits` — where the difference is `kIsCompiled` (`BIT(16)`,
`root/core/meta/inc/TVirtualStreamerInfo.h:82`), an in-memory flag that reaches
disk because `fBits` is written wholesale by the `TNamed` base.

A reader MUST tolerate the duplicate and may take either entry; they describe the
same layout. A reader that indexes the list by `(class, version)` and asserts
uniqueness will reject ordinary files.

> Seen in three files of the foreign corpus (`PLAN.md` §9.8), all for
> `ROOT::TIOFeatures`: `uproot-issue121.root` (ROOT 6.18/00) has 23 entries of
> which two are `ROOT::TIOFeatures` version 1, checksum `0x1aa12f10`, `fBits`
> `0x3000000` and `0x3010000`.

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

**There is deliberately no uniqueness invariant.** Two entries for one class may
share a `fClassVersion` and differ in `fCheckSum`, which §3 says is how an
unversioned class is disambiguated; and they may agree on *both*, which §8.1 shows
ROOT writing. A reader must index the list in a way that tolerates either.

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

No fixture covers two infos for one class distinguished by checksum, a
`type=readraw` rule, a negative in-memory class version reaching disk as 1, or a
file old enough to take the `BuildEmulated` path. The first three need two ROOT
sessions with different definitions of the same class; the last needs a ROOT
older than any that can still be built here.
