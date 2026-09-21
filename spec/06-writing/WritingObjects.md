# Writing an object

What goes inside a record's payload: the framing an object carries, how a pointer
names its class, what the `TObject` base contributes, when to compress, and how to
build the `StreamerInfo` record that lets anything other than ROOT read the result.

Prerequisites: [Writing a file](WritingFiles.md), and the reading side —
[Buffer framing](../02-serialization/Buffer.md),
[Streamer information](../02-serialization/StreamerInfo.md),
[Element types](../02-serialization/ElementTypes.md),
[Compression](../01-container/Compression.md).

## 1. The two framings

Every object in a payload is one of two shapes, and choosing the wrong one is the
most common way to desynchronise a reader by a fixed number of bytes.

**An embedded object** — a base class, or a member held by value — is a byte count,
a version word, then its members:

```
(kByteCountMask | n):u32   version:i16   members...
```

where `n` counts the version word and the members and excludes its own four bytes.
`TBufferFile::WriteVersion(cl, kTRUE)` reserves the count and
`SetByteCount` fills it in (`root/io/io/src/TBufferFile.cxx:3719-3726`).

**A pointer member** is an object *slot*: the same thing preceded by a class
record, because a pointer may refer to a class derived from the declared one
([Buffer framing §5](../02-serialization/Buffer.md#5-class-records)):

```
(kByteCountMask | n):u32   class record   (kByteCountMask | m):u32   version:i16   members...
```

The outer count covers the class record **and** the inner framed object, so there
are two byte counts, nested. §4 has the class record.

> `TStreamerInfo::fElements` is the trap. It is a `TObjArray *`, so it takes the
> slot form — and a writer that emits the bare framed object is 18 bytes short: 4
> for the outer count, 4 for the tag, 10 for `TObjArray\0`. That was the last error
> in this project's own writer before its `StreamerInfo` record became
> byte-identical to ROOT's (§7.4).

### 1.1 Three exceptions, all of them classes with a hand-written `Streamer`

| Class | What it writes |
|---|---|
| `TObject` | a version word and **no byte count** (`root/core/base/src/TObject.cxx:1022`) |
| `TString` | a counted string, no version word, no byte count |
| `TArray` and its concrete subclasses | `fN` as an `i32` then the values — no version word, no byte count, no flag byte |

A reader is told these as facts about those classes
([Buffer framing §7](../02-serialization/Buffer.md#7-the-tobject-base),
[TArray](../03-classes/TArray.md)). A writer needs them as rules, and needs one
more: **`CheckByteCount` cannot check what has no byte count.** ROOT's length
validation returns immediately when the count is zero
(`root/io/io/src/TBufferFile.cxx:367`), so an error inside a `TObject`, a `TString`
or a `TArray` has no detector at all.

### 1.2 The version word has 14 usable bits

`kByteCountVMask` is 0x4000 and `kStreamedMemberWise` is the same number
([Buffer framing §3.1](../02-serialization/Buffer.md#31-kbytecountvmask-and-kstreamedmemberwise-are-the-same-number)),
so a class version above 0x3FFF cannot be written. Nothing in ROOT is close, but a
writer generating class versions must not use the high bits for its own purposes.

## 2. A version word of 0, and when a writer must emit one

A version word of 0 means "a checksum follows instead of a version", and ROOT
writes it for a **foreign** class — one with no `ClassDef` — whose version would
otherwise be 0 or 1 (`root/io/io/src/TBufferFile.cxx:3163-3166`):

```
(kByteCountMask | n):u32   0x0000:i16   checksum:u32   members...
```

A writer meets this in exactly one place in the classic format, and it is not
optional: **`TTree::fIOFeatures` is such a class.** `ROOT::TIOFeatures` has no
`ClassDef` (`root/tree/tree/inc/ROOT/TIOFeatures.hxx:100`), so its eleven bytes are
a byte count of 7, a version of 0, the checksum `0x1aa12f10`, and one `UChar_t`.
`06-writing/WritingTrees.md` uses it.

> **Its streamer info must record `fClassVersion` 1, not 0**, even though the object
> is written with a version word of 0. This looks like a contradiction and is
> load-bearing: a reader that meets a version word of 0 looks the class up in the
> file's info list and reads a checksum **only if** the recorded `fClassVersion` is
> not 0 ([Buffer §4](../02-serialization/Buffer.md#4-a-version-word-of-0-has-two-different-meanings)).
> A writer that records 0 to match the version word tells every conforming reader
> that no checksum follows, and each such object then desynchronises the buffer by
> four bytes. ROOT records 1 because that is the version its `TClass` reports for a
> class with no `ClassDef`; `tools/rootwrite.py` emits
> `Info("ROOT::TIOFeatures", 1, ...)` for the same reason.

## 3. Strings and the `TObject` base

**Strings.** A counted string is one length byte, or `0xFF` followed by an `i32`
length when the string is 255 bytes or longer
([Conventions §5.1](../00-conventions.md#51-counted-string)). ROOT's own rule is
`length + 1` bytes below 255 and `length + 5` at or above
(`root/core/base/src/TString.cxx:1407`). The **null-terminated** encoding appears
in exactly one place, a class record's name (§4).

**The `TObject` base** is ten bytes: a version word of 1, `fUniqueID`, `fBits`.
Two rules a writer needs:

- **`fBits` is masked on the way out.** ROOT writes
  `fBits & ~kIsOnHeap & ~kNotDeleted` (`root/core/base/src/TObject.cxx:1030-1033`),
  which is why the in-memory value never reaches the file. A writer with no bits to
  set writes 0. ROOT sets `kMustCleanup` (8) on anything a directory owns, so a
  histogram's `TObject` carries 8 and a `TObjString` written with `WriteObject`
  carries 0 — both are fine.
- **`kIsReferenced` adds two bytes.** When bit 4 is set the base is twelve bytes,
  the last two being a process-ID index (`root/core/base/src/TObject.cxx:1035+`,
  [References](../02-serialization/References.md)). A writer that does not
  participate in `TRef` must leave that bit clear.

> The exception to the masking is a file opened with `TFile.v630forwardCompatibility`,
> which writes `fBits` unmasked (`root/core/base/src/TObject.cxx:1029-1031`). A
> reader therefore cannot assume those two bits are clear, and a writer has no
> reason to set them.

## 4. Class records and the object map

A class record names a class, once per buffer, and is referred back to afterwards:

| Form | Bytes |
|---|---|
| first occurrence | `0xFFFFFFFF` then the class name, **null-terminated** |
| later occurrences | `0x80000000 \| position` |

**The positions are the part to get right**, because they are offsets into the
record — key included — and there are two different rules
([Buffer framing §5.1](../02-serialization/Buffer.md#51-a-new-class) and
[§6.1](../02-serialization/Buffer.md#61-object-references)):

| What | Mapped at |
|---|---|
| a class | the offset of its **tag** word, plus 2 |
| an object | the offset of its **byte count** word, plus 2 — four bytes earlier |

The `+ 2` is `kMapOffset`, and it exists so that a real position is never 0 or 1,
which mean the null object and the record's own top-level object.

Two consequences for a writer:

1. **Offsets include `fKeylen`.** A writer that builds the payload in a buffer of
   its own and measures from the start of *that* produces every class tag too small
   by the key's length. Since the first occurrence of each class is written as a
   name rather than a position, such a file reads correctly until the second
   occurrence — so the failure appears in the middle of a large record and not at
   all in a small one.
2. **A writer chooses whether to share objects.** ROOT writes the bare four-byte
   tag for an object already in the map (`root/io/io/src/TBufferFile.cxx:2680-2686`)
   and never a byte-counted reference, though its reader accepts one
   ([Buffer framing §6.1](../02-serialization/Buffer.md#61-object-references)).
   Writing the object twice instead is legal and produces two objects where ROOT
   would produce one — which matters only if something in the file points at
   identity rather than value.

## 5. Compression

A writer decides per record, and the decision is visible in the key rather than in
the payload: `fObjlen` is the uncompressed length and `fNbytes - fKeylen` the
stored length, and a reader concludes "compressed" from
`fObjlen > fNbytes - fKeylen` and nothing else
([Compression §1](../01-container/Compression.md#1-deciding-whether-a-payload-is-compressed)).

The block format is [Compression §2](../01-container/Compression.md#2-block-header),
and the two things a writer gets wrong are both in the header:

- the two size fields are **24-bit little-endian**, inside an otherwise big-endian
  format;
- the compressed size **excludes** the nine header bytes, so a single-block payload
  satisfies `9 + compressed size == fNbytes - fKeylen`.

Above `0xFFFFFF` uncompressed bytes the payload is split into blocks of exactly
that many uncompressed bytes each, the last holding the remainder, and the count is
stored nowhere ([Compression §7](../01-container/Compression.md#7-multi-block-payloads)).

ROOT's own policy, which a writer may but need not copy: compress only when the
file's level is above 0 **and** `fObjlen` exceeds 256, and fall back to storing raw
if the result is not smaller (`root/io/io/src/TKey.cxx:262-284`). The fallback is
worth copying — a compressed block that is larger than its input is legal and
pointless.

**The key header is never compressed**, only the payload
(`root/io/io/src/TKey.cxx:268-269`), and neither is the root directory record, the
key list or the free list: those go through a `TKey` constructor with no
compression path at all (`root/io/io/src/TKey.cxx:203-209`).

## 6. The record for one object, end to end

A `TObjString` holding `hello`, as `data/written/objstring.root` writes it:

| Bytes | Value | Why |
|---|---|---|
| `40 00 00 12` | byte count 18 | §1 |
| `00 01` | version 1 | `TObjString`'s class version |
| `00 01` | version 1 | the `TObject` base — no byte count of its own (§1.1) |
| `00 00 00 00` | `fUniqueID` | |
| `00 00 00 00` | `fBits` | masked (§3) |
| `05 68 65 6c 6c 6f` | `hello` | a counted string |

`fObjlen` is 22, `fKeylen` 66, `fNbytes` 88.

## 7. The `StreamerInfo` record

[Writing a file §7](WritingFiles.md#7-the-streamerinfo-record) places the record
and says why it is worth writing at all. This is what goes in it: a `TList`,
holding one `TStreamerInfo` per class, each holding a `TObjArray` of elements.
The element list of each class a histogram or a flat tree needs is
[Element lists](ElementLists.md); this section is the shape those lists go into.

### 7.1 The nesting

```
TList (version 5)
└── object slot per info, each followed by one option byte of 0x00
    └── TStreamerInfo (version 10)
        ├── TNamed base      fName = the described class, fTitle = its comment
        ├── fCheckSum:u32
        ├── fClassVersion:i32            written as |fClassVersion|
        └── object slot: TObjArray (version 3)
            └── object slot per element, no option byte
                └── TStreamerXxx (its own version, StreamerInfo.md 8)
                    ├── TStreamerElement (version 4)
                    │   ├── TNamed base   fName = member, fTitle = its comment
                    │   ├── fType:i32     ElementTypes.md
                    │   ├── fSize:i32     sizeof on the writing machine
                    │   ├── fArrayLength:i32, fArrayDim:i32
                    │   ├── fMaxIndex[5]:i32
                    │   └── fTypeName     counted string
                    └── the subclass's own members
```

The `TList`'s own `fName` is empty: the name `StreamerInfo` is on the **key**, not
on the object (`root/io/io/src/TFile.cxx:3554`).

Details that are not derivable from the reading side:

- **The option byte after every `TList` entry** is present even when empty, and in
  this record every option is empty — so the list is a sequence of
  *slot, `0x00`* pairs.
- **`fBits` of each info is `0x00010000`.** `kIsCompiled` is an artifact of ROOT's
  writer and is persisted
  ([StreamerInfo §6](../02-serialization/StreamerInfo.md#6-tstreamerinfo)). A
  reader ignores it; a writer that wants a byte-identical record emits it.
- **A base class's element carries the base's checksum in `fMaxIndex[1]`**
  ([StreamerInfo §9](../02-serialization/StreamerInfo.md#9-tstreamerbase-and-a-checksum-hidden-in-fmaxindex)),
  and it is written as an unsigned word: `TObject`'s `0x901bc02d` reads back as a
  negative `i32`.
- **Each info carries its own `TObjArray` record**, never a back-reference to a
  shared one, because ROOT writes the array with `cacheReuse = kFALSE`
  (`root/io/io/src/TStreamerInfo.cxx:5707`). The *class* `TObjArray` is
  back-referenced after the first info, as is each element class.

### 7.2 Which classes need an info

ROOT's rule is mechanical: an info is written for every class whose bytes went
through a streamer-info-driven write. `TBufferFile::WriteClassBuffer` marks the
class in the file's class index (`root/io/io/src/TBufferFile.cxx:3722`, marking at
`root/io/io/src/TBufferIO.cxx:349-366`), and `TFile::WriteStreamerInfo` collects
everything marked (`root/io/io/src/TFile.cxx:3507-3532`).

So a class with a hand-written `Streamer` is **absent** from the record, because
nothing marks it — `TBasket` is the cleanest example, and no ROOT-written file
contains an info for it. `TArray`, `TArrayF` and `TArrayD` are absent for the same
reason, which is why [TArray](../03-classes/TArray.md) has to be published as
prose.

A writer should follow the same rule: emit an info for each class whose layout a
reader must be told, and leave out the ones a reader has to know anyway. Writing
*more* is harmless; writing an info whose content disagrees with the bytes is worse
than writing none (§8).

### 7.3 The checksum

`fCheckSum` identifies a layout when a version number cannot, and the algorithm is
[StreamerInfo §11](../02-serialization/StreamerInfo.md#11-checksums). A writer has
the advantage here: it knows the class definition, so it can compute the value
exactly. Two rules are easy to miss:

- **An enum member folds an extra 1** before its name. Without it, `TH1`'s
  checksum is wrong, because `fBinStatErrOpt` and `fStatOverflows` are enums.
- **The type name is the resolved one.** `Bool_t` is folded as `bool`,
  `Double_t` as `double` — and `fTypeName` in the record is the resolved spelling
  too, so the two agree.

If the class is one ROOT has compiled in, the value must be **ROOT's**. For 614 of
the 653 streamer infos in this repository's reference files it can simply be
recomputed from the info's own elements; the exceptions, and why they exist, are
[StreamerInfo §11.2](../02-serialization/StreamerInfo.md#112-what-cannot-be-recomputed).

### 7.4 The check that this procedure passes

`tools/test_write.py` builds the `StreamerInfo` record for `TObjString` from this
document and asserts it is **byte-identical, all 370 bytes**, to the one ROOT wrote
in `data/container/file-minimal.root` — including the class tags, the option bytes,
`kIsCompiled`, the base checksum in `fMaxIndex[1]`, and a `fCheckSum` of
`0x9c8e4800` computed from scratch. That is the strongest available evidence that
§7 is right, and it is why the `TObjArray`-as-a-slot error in §1 is recorded rather
than quietly fixed.

## 8. Writing for a reader that is not you

§7 says to write a `StreamerInfo` record. This section answers the question that
makes it worth writing: **what has to be in the file so that a reader whose
version of a class is not the writer's can still read it?**

That is the whole of schema evolution from this side. It is deliberately *not*
"how to write an earlier version of a class" — ROOT has no mechanism for that
([§3.1](index.md#31-what-the-current-version-means)) and neither does this
document. A writer emits the layout it has, and describes it well enough that a
reader with a different one can cope.

The reader's engine is `TStreamerInfo::BuildOld`, and knowing one thing about it
collapses the problem: it walks the **on-disk** element list and matches each
element to a member of the in-memory class **by name and nothing else**
(`root/io/io/src/TStreamerInfo.cxx:2287`). Not by type, not by position, not by
size. So a writer's obligations are a short list, and most of what looks
load-bearing in a streamer info is not.

### 8.1 The obligations

| Obligation | Why it is one |
|---|---|
| An info for every class actually serialized, **plus the transitive closure** of its bases and the classes it contains | [§8.2](#82-the-closure-and-what-an-incomplete-one-costs) |
| `fClassVersion` written as an **absolute value**, between 0 and 65000 | a class version of `-1` in memory reaches disk as 1; [Schema evolution §1.1](../02-serialization/SchemaEvolution.md#11-the-version-is-written-as-an-absolute-value) |
| `fCheckSum` agreeing with the element list shipped beside it | it is the key a reader's rules and its version-0 lookups are selected by ([§7.3](#73-the-checksum)) |
| Element `fName` strings equal to the in-memory member names | the only thing evolution matches on |
| For every `TStreamerBase`: the base's checksum in `fMaxIndex[1]`, and `fBaseVersion` as the version actually built against | [Streamer information §9](../02-serialization/StreamerInfo.md#9-tstreamerbase-and-a-checksum-hidden-in-fmaxindex). The checksum is invariant 7 there; `fBaseVersion` is **not** an invariant, because it may legitimately name a version the file has no info for ([§9.2](../02-serialization/StreamerInfo.md#92-fbaseversion-may-name-a-version-the-file-does-not-contain)) |
| The object's **version word** matching one of the infos for its class | it is the only thing in a record that says which layout applies ([§1](#1-the-two-framings)) |

The last is what `data/written/two-versions.root` exists to show: one class, two
infos, two records, and nothing but the version word to tell them apart.

### 8.2 The closure, and what an incomplete one costs

**An info for a derived class without one for its base is the mistake worth
naming.** ROOT's reader builds the derived class's layout by recursing into the
base, and with no info and no dictionary for it there is nothing to recurse into.
Measured, on a file this project wrote with `Bottom`'s info removed and nothing
else changed:

```
Warning in <TStreamerInfo::BuildOld>: Missing base class: Bottom skipped
Error in <TClass::GetBaseClassOffsetRecurse>: Can not determine alignment for base class Bottom (got 0)
Error in <TStreamerInfo::BuildOld>: Cannot determine alignment for base class Bottom for element Top
Error in <TBufferFile::CheckByteCount>: object of class Bottom read too few bytes: 2 instead of 6
```

The class comes out 16 bytes instead of 24 — the base is simply absent from the
layout (`root/io/io/src/TStreamerInfo.cxx:2054`). Two things about the failure are
worth knowing:

- **it is loud**, and that is not luck. The base's bytes carry **their own byte
  count**, so `CheckByteCount` catches the short read and resynchronises from it;
  the members after the base still read correctly, and the record that follows in
  the file is untouched. A base whose bytes carry no byte count — `TObject`'s do
  not ([§3](#3-strings-and-the-tobject-base)) — would desynchronise silently
  instead;
- **it is diagnosable only by a reader with a dictionary for the derived class**
  or none at all. A reader that has the base compiled in will not notice, because
  it does not need the info.

**The closure has one exemption, and it is published rather than derivable.** A
class whose `Streamer` is hand-written gets no info, because nothing marks it
([§7.2](#72-which-classes-need-an-info)) — so `TObject`, `TArrayF`, `TArrayD` and
`TArrayL64` are missing as bases from every ROOT-written file in either corpus,
and that is correct. The two lists a reader has to know out of band are
[Hand-written streamers](../99-appendix/HandWrittenStreamers.md) and
[Forwarding streamers](../99-appendix/ForwardingStreamers.md), both generated from
the pinned submodule and CI-checked. Over the 89 files here that carry an info,
the bases with no info of their own are exactly five classes, every one of them on
the first list: `TObject`, `TArrayD`, `TArrayF`, `TArrayL64` and `TQObject`.

**The exemption is a property of ROOT's source, but it is a *published* property,
so the closure is checkable after all** — which is how it is now checked. It is
[Streamer-driven reading §10.5](../02-serialization/StreamerDriven.md#10-invariants),
and `tools/check_invariants.py` reads the exempt set out of those two appendix
documents rather than out of the submodule, so it runs without one. Over `data/`
and both corpora it holds on every file but two, and the two are g4tools' rather
than ROOT's — the earlier draft of this paragraph named `TAtt3D` as a sixth
legitimately-absent base on the strength of them, and that was wrong: `TAtt3D` is
`ClassDef(TAtt3D,1)`, on neither list, and 48 ROOT-written files in the corpora do
carry its info — including four of the six that describe a `TH3` at all. A file that is not ROOT's is a lead, not evidence.

The file-local companion is invariant 7 of
[Streamer information §13](../02-serialization/StreamerInfo.md#13-invariants):
when a base *does* have an info, the element's `fBaseCheckSum` is either that
info's `fCheckSum` or 0. That holds over the 731 base elements here whose base has
an info, all 731 of which record a non-zero checksum.

**Its companion does not, and the attempt is worth recording.** This document first
claimed the same of `fBaseVersion` and made it an invariant; five files in the two
corpora failed it within a minute, and all five are right —
[§9.2](../02-serialization/StreamerInfo.md#92-fbaseversion-may-name-a-version-the-file-does-not-contain)
has them. A writer should still emit the version it actually built against; a
*reader* must not rely on it.

### 8.3 Three things a writer does not have to get right

Each of these looks like it must matter and does not, for a reader that has the
class compiled in. Only an **emulated** class uses them, and then only to lay out
memory that nothing else sees.

- **`fSize` is discarded.** `BuildOld` recomputes it from the in-memory type and
  the on-disk `fArrayLength` (`root/io/io/src/TStreamerInfo.cxx:2337`). This is
  also why `tools/normalize.py` can mask it, and why it has to: `sizeof` differs
  between standard libraries for `std::string` and `std::map`.
- **`fArrayDim` and `fMaxIndex` are never compared** against the in-memory
  member. A disagreement is silent.
- **Artificial and cache elements cannot reach disk at all.** The write path does
  not stream `fElements`; it builds a filtered copy, dropping every
  `TStreamerArtificial`, every element with `kRepeat`, and every read-only
  `kCache` (`root/io/io/src/TStreamerInfo.cxx:5694-5707`). So an info that came
  *off* a file, went through `BuildOld`, and is written back out is stripped
  automatically — which is what makes
  [Element types §11](../02-serialization/ElementTypes.md#11-invariants)'s ban on
  those codes a property of files rather than a rule a writer has to follow.

### 8.4 One class, two versions in one file

**Legitimate, and a writer that evolves its own classes will produce it.** A
`TStreamerInfo`'s identity is per *instance*, not per class, so two infos for one
class occupy two slots and both are written. Four things produce it: a fast clone
carrying a source file's infos across, the dependency closure, writing an object
at a version the session had to rebuild, and **reopening a file** with a class
that has since changed
([Writing a file §13](WritingFiles.md#13-updating-an-existing-file)).

No single ROOT session can produce such a file, because a session has one
definition of a class. Two sessions can, and ROOT needs no persuading. Measured:
a file written with `Merged` at `ClassDef(Merged, 2)` — members `fA`, `fB` — then
reopened by a session whose `Merged` is at version 3 with a third member, and one
more object written. The result:

| | version | elements |
|---|---|---|
| info 1 | 2 | `fA`, `fB` |
| info 2 | 3 | `fA`, `fB`, `fC` |

and the two records are 54 and 58 bytes, each carrying the members its own
version has. **ROOT keeps both**, silently and correctly. `fSeekInfo` moved and
the record grew; nothing was discarded.

A reader picks between them by the object's version word
([Schema evolution §4](../02-serialization/SchemaEvolution.md#4-choosing-a-streamer-info)).
`data/written/two-versions.root` is that file written in one pass, and ROOT reads
its version-1 record through the version-2 layout — `fA` off the file, the member
version 1 does not have left at its default.

### 8.5 When the versions collide, the file wins and members are lost

The other half of the same experiment, and the destructive one. Same base file at
`Merged` version 2; the second session's `Merged` has three members but **still
says `ClassDef(Merged, 2)`**. ROOT warns at open, clearly:

```
Warning in <TStreamerInfo::BuildCheck>:
   The StreamerInfo of class Merged read from file .../collide.root
   has the same version (=2) as the active class but a different checksum.
   You should update the version to ClassDef(Merged,3).
   Do not try to write objects with the current class definition,
   the files will not be readable.
```

and then does exactly what it warned about, without a second word: the object
written after that is **54 bytes, not 58**. The session's info was discarded, the
file's was kept, and `fC` was dropped on the way to disk. The info list still has
one entry.

So the merge rule, stated for a writer: **on a version collision the incumbent
wins.** The consequences are worth separating, because only one of them is
recoverable:

- the objects already in the file are untouched and still readable;
- the object written *during* the colliding session is silently short, and no
  later reader can tell that anything is missing.

A writer following this document therefore has two honest choices when its own
info for a class disagrees with the file's at the same version: **bump the version
and write both infos** (§8.4), or **refuse the update**. `tools/rootwrite.py`
takes the second — it requires the caller to supply the complete list, so a
collision is the caller's to resolve — and reproducing ROOT's silent truncation is
not an option this document offers.

### 8.6 `listOfRules` is optional, and this is what it costs

`TFile::WriteStreamerInfo` appends one extra entry to the outer list when any
class being written has I/O rules: a nested `TList` named `listOfRules` whose
members are `TObjString`s, one per rule
(`root/io/io/src/TFile.cxx:3527-3549`; the shape is
[Schema evolution §6.1](../02-serialization/SchemaEvolution.md#61-the-shape-on-disk)).
Two facts make it optional:

- **ROOT never reads it back**
  ([§6.2](../02-serialization/SchemaEvolution.md#62-root-ignores-it)) — rules come
  from the reading session's dictionary, never from the file;
- **ROOT collects the rules of the *class*, with no reference to the version being
  written.** So a file written at `TTree` 20 ships two rules for source versions
  `[-16]` and `[-18]`, and a `TProfile` 7 file ships one for versions `[1-5]` —
  rules that can never match their own data.

A writer emitting only current versions may therefore omit the entry with **no
loss of information**. What emitting it buys is a byte comparison: with the entry,
the `StreamerInfo` record of every tree and profile file this project writes is
**byte-identical** to ROOT's — 14584, 14580, 14121 and 11789 bytes — where without
it the two differed by that one entry. `tools/rootwrite.py` emits it for the same
reason it reproduces `kIsCompiled`, and `FileWriter(emit_rules=False)` turns it
off.

One detail is only visible in a byte comparison: the rules list's own `fBits`
carries `kIsOwner`, `BIT(14)`
(`root/core/cont/inc/TCollection.h:144`), because ROOT builds an owning list and
`fBits` reaches disk through the `TObject` base. Nothing reads it.

### 8.7 Do not derive your own classes from `TObject`

This is a recommendation about the *class*, not the bytes, and it exists because
of a silent failure in ROOT.

`TKey::ReadObj` splits on whether the key's class is `TObject`-derived. If it is
not, the read goes through `ReadObjectAny` (`root/io/io/src/TKey.cxx:811-812`) and
thence through the class's streamer info — so an **emulated** class reads
correctly. If it is, ROOT allocates the object and streams it with
`tobj->Streamer(bufferRef)` (`root/io/io/src/TKey.cxx:883`). For a class ROOT has
no dictionary for there is no compiled `Streamer` to dispatch to, so that call
resolves to `TObject::Streamer`, which reads a version word, `fUniqueID` and
`fBits`, and stops.

**The result is a default-constructed object and no diagnostic about the data.**
Measured on a file ROOT wrote itself: a class `Marked : public TObject` with
`Int_t fA = 77` and `Double_t fB = 1.25`, read back in a session without the
dictionary, gives `fA = 0` and `fB = 0`. The only message is
`Warning in <TClass::Init>: no dictionary for class Marked is available`, which
says nothing about the members being dropped. This project's reader, driven by the
file's own streamer info, recovers 77 and 1.25 from the same bytes.

ROOT's source knows about the problem: four lines above that call, the
compressed-payload branch says *"Even-though we have a TObject, if the class is
emulated the virtual table may not be 'right', so let's go via the TClass"*
(`root/io/io/src/TKey.cxx:877-878`) — but only takes that branch when the unzip
fails.

Three consequences:

- **for a writer**: a class of your own that derives from `TObject` is readable by
  ROOT only when ROOT has its dictionary. A class that does not is readable from
  the file alone. `data/written/two-versions.root` is built on that;
- **it does not apply to members.** The same class nested inside another object
  reads correctly, because that path goes through
  `TStreamerInfo::ReadBuffer` rather than through `TKey`;
- **for a reader**: this is one of the cases where a third-party implementation is
  strictly better than ROOT, and it is recorded as an erratum against
  [Emulated classes](../02-serialization/SchemaEvolution.md#7-emulated-classes).

## 9. What ROOT checks, and what it does not

| Mistake | What ROOT says |
|---|---|
| a byte count longer or shorter than what the streamer consumed | `Error("CheckByteCount", "object of class %s read too few/too many bytes: %d instead of %d")` and `"%s::Streamer() not in sync with data on file %s"` (`root/io/io/src/TBufferFile.cxx:380-391`) |
| a byte count pointing past the record | `"Byte count probably corrupted around buffer position %d"` (`root/io/io/src/TBufferFile.cxx:396`) |
| an info whose checksum differs from the compiled class at the same version | `Warning("BuildCheck", "... has the same version (=%d) as the active class but a different checksum. You should update the version to ClassDef(%s,%d)")` (`root/io/io/src/TStreamerInfo.cxx:1368-1375`) |
| the same, when an info for that version was already loaded | `"... has a different checksum than the previously loaded StreamerInfo"` (`root/io/io/src/TStreamerInfo.cxx:1269-1276`) |
| a version word neither the compiled version nor 1, with no info in the file | `Error("ReadClassBuffer", "Could not find the StreamerInfo for version %d of the class %s, object skipped")` (`root/io/io/src/TBufferFile.cxx:3659-3663`) |

And what has no detector:

- **A wrong member order with the right total length.** `CheckByteCount` compares
  lengths, not contents, so two adjacent `Double_t`s in the wrong order are read
  silently and wrongly. With no info in the file nothing else looks either.
- **Anything inside a `TObject`, `TString` or `TArray`**, which carry no byte count
  (§1.1).
- **A checksum mismatch that `CompareContent` forgives.** After the warning above,
  ROOT compares "the same number of persistent data members with the same actual
  C++ type and the same name" (`root/io/io/src/TStreamerInfo.cxx:3103-3111`) and
  declares a match if that holds — so a *reordering* can pass, and the warning is
  printed at most once per class per process
  (`root/io/io/src/TStreamerInfo.cxx:1307-1308`).
- **An object written twice where ROOT would have written a reference.** Legal, and
  invisible unless something depends on identity.

The asymmetry is worth stating plainly: **a missing streamer info warns less than a
wrong one.** Emitting nothing is quieter than emitting something inconsistent, and
neither is as good as emitting the truth.

## 10. Invariants

1. Every byte count equals the number of bytes that follow it up to the end of the
   object it frames, excluding its own four bytes.
2. A class name appears in full at most once per record; every later occurrence is
   `0x80000000 | position`, and that position is the offset of the first
   occurrence's tag word from the start of the record, plus 2.
3. Every map position is at least 2, and no object reference names a position that
   is not the byte count of an object written earlier in the same record.
4. `fObjlen > fNbytes - fKeylen` **iff** the payload is a sequence of compression
   blocks, and for a single-block payload `9 + compressed size == fNbytes - fKeylen`
   and `uncompressed size == fObjlen`.
5. Every class named in a version word above 0 either has an info in this file or is
   one whose layout a reader is expected to know out of band.
6. An info's `fCheckSum` is the value the algorithm of
   [StreamerInfo §11](../02-serialization/StreamerInfo.md#11-checksums) produces for
   the class it describes.
7. Each `TList` entry in the `StreamerInfo` record is followed by exactly one option
   byte, and each `TObjArray` entry by none.

Items 1 to 4 are checked for every written file by `tools/check_write.py` through
`tools/rootfile.py`; item 6 is checked for every streamer info in `data/` by
`tools/test_write.py`.

## 11. Reference files

| File | What it demonstrates |
|---|---|
| `data/written/streamerinfo.root` | a compressed record and a `StreamerInfo` record this project wrote, which ROOT's `ShowStreamerInfo` prints |
| `data/container/file-minimal.root` | ROOT's own `StreamerInfo` record for the same class, the target of §7.4's byte comparison |
| `data/serialization/object-tags.root` | the class and object back-references of §4, from the reading side |
| `data/container/compress-zlib.root` | ROOT's block header, against which §5 is checked |
| `data/written/two-versions.root` | §8.4: one class at two versions, an object at each, and the version word as the only thing that selects between them — the only file in `data/` that carries a class twice |
| `data/written/tree.root` | §8.6: with the `listOfRules` entry, its `StreamerInfo` record is **byte-identical** to ROOT's in `data/ttree/basket.root`, all 14584 bytes |
