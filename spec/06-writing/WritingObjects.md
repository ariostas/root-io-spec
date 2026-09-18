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
   tag for an object already in the map (`root/io/io/src/TBufferFile.cxx:2680-2685`)
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

[Writing a file §6](WritingFiles.md#6-the-streamerinfo-record) places the record
and says why it is worth writing at all. This is what goes in it: a `TList`,
holding one `TStreamerInfo` per class, each holding a `TObjArray` of elements.

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

## 8. What ROOT checks, and what it does not

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

## 9. Invariants

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

## 10. Reference files

| File | What it demonstrates |
|---|---|
| `data/written/streamerinfo.root` | a compressed record and a `StreamerInfo` record this project wrote, which ROOT's `ShowStreamerInfo` prints |
| `data/container/file-minimal.root` | ROOT's own `StreamerInfo` record for the same class, the target of §7.4's byte comparison |
| `data/serialization/object-tags.root` | the class and object back-references of §4, from the reading side |
| `data/container/compress-zlib.root` | ROOT's block header, against which §5 is checked |
