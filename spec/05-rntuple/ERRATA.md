# Errata against the upstream specification

Places where [the tracked copy](BinaryFormatSpecification.md) and ROOT's code
disagree. As in the rest of this project, every entry is verified twice, against
the pinned submodule with a `path:line` citation and against real bytes, and says
what a reader that follows the document gets wrong.

Entries here are candidates for upstream pull requests against
`root-project/root`, and the table tracks the link per entry. Nothing is
corrected in the copy itself — see [UPSTREAM.md](UPSTREAM.md).

| # | Section | Status | Upstream PR |
|---|---|---|---|
| 1 | Title | open | — |
| 2 | Anchor schema | open | — |
| 3 | Anchor schema | open | — |
| 4 | Locators and Envelope Links | open | — |
| 5 | Envelopes | open | — |
| 6 | Header Envelope → Column Description | open | — |
| 7 | Low-precision Floating Points | open | — |
| 8 | Header Envelope → Field Description | open | — |
| 9 | Header Envelope → Extra type information | open | — |
| 10 | Header Envelope → Extra type information | open | — |
| 11 | Footer Envelope | open | — |
| 12 | Footer Envelope → Linked Attribute Set Record Frame | open | — |
| 13 | Linked Attribute Sets → Attribute Schema Version | open | — |

Bytes come from three files.

**`rntuple/anchor`** is this project's own fixture, written by the pinned ROOT
6.40.04 with compression off so the envelopes are readable in place. Its anchor
record is at 998 and its payload runs 1052 to 1130; its header envelope is at 268
and its footer at 838. Every erratum that can be shown in bytes is asserted
there.

**`rntuple/attributes`** is the fixture for errata 11 to 13: a main RNTuple
whose footer links two attribute sets, written the same way. Its footer is at
3684, the attribute set list at 3824, and the two sets' anchors at 2508 and
3451.

**`RNTuple.root`**, 2 514 bytes, written by ROOT 6.35/01 and published at
<https://root.cern/files/>; `gen/cern/README.md` lists it and
`tools/fetch_cern.py` fetches it. Its anchor record is at offset 1835 and its
payload runs 1889 to 1967. It is older than the pinned release and has an older
format version (`Version Minor` 0 against 2), so it is kept as a second,
independent witness rather than as the primary one.

---

## 1. The version in the title is not the version a writer stamps

> **The document** is titled *RNTuple Binary Format Specification **1.0.2.1***.

**The writer** stamps epoch 1, major 0, minor 2, patch **0**
(`root/tree/ntuple/inc/ROOT/RNTuple.hxx:79-82`), so an anchor written by the
pinned ROOT says **1.0.2.0**.

> Confirmed in bytes by `rntuple/anchor`, whose four version words at 1058, 1060,
> 1062 and 1064 are 1, 0, **2**, **0**.

This is harmless in itself, since the document says of the patch component that
"the versioning is for reporting only". But **the version in the document is not
the version in the files**, and a reader comparing the two cannot tell whether it
is looking at a stale file or a stale document.

The document and the source also disagree about a feature flag. The table under
*Feature Flags* says flag bit 0, *Nested Deferred Columns*, was "Introduced in
1.0.2.1". ROOT's own source gives a different version: the comment immediately
above the flag's declaration reads *"Added in version 1.1.0.0 of the binary
format"* (`root/tree/ntuple/inc/ROOT/RNTupleDescriptor.hxx:779`,
`root/tree/ntuple/inc/ROOT/RNTupleDescriptor.hxx:780`). The two disagree about
which format version introduces the flag, not only about a patch digit.

Nothing sets the flag yet (the symbol occurs at that one line in the whole
submodule), so no file has it today, and the disagreement is harmless until one
does. Either the comment or the table has to change.

Already noted in `PLAN.md` §2.6 when this directory was first planned.

---

## 2. The anchor schema omits the six bytes that begin it

> **The document**, under *ROOT File embedding → Anchor schema*, gives a schema
> that starts at `Version Epoch` and notes only that "since the anchor is
> serialized as a 'classic' TFile key, all integers in the anchor ... are encoded
> in **big-endian**".

**On disk the anchor object begins with a byte count and a class version word**,
the ordinary object framing of
[Buffer framing §2](../02-serialization/Buffer.md#2-byte-counts) and [§3](../02-serialization/Buffer.md#3-version-words).
They belong to the object, not to the key: they are the first two members of the
struct that is the on-disk anchor
(`root/tree/ntuple/src/RMiniFile.cxx:548-549`):

```cpp
struct RTFNTuple {
   RUInt32BE fByteCount{0x40000000 | (sizeof(RTFNTuple) - sizeof(fByteCount))};
   RUInt16BE fVersionClass{2};
   RUInt16BE fVersionEpoch{0};
   ...
```

In `RNTuple.root` the payload begins:

```
40 00 00 42   byte count, 66
00 02         class version 2 of ROOT::RNTuple
00 01         Version Epoch   <- where the document's schema starts
00 00         Version Major
00 00         Version Minor
00 00         Version Patch
```

**A reader that positions itself at the anchor payload and follows the schema
reads `0x4000` as Version Epoch and `0x0042` as Version Major**, and every
subsequent field is six bytes early. The schema is the only description the
document gives of where the anchor's first field is.

> `rntuple/anchor` asserts the byte count at 1052 and `Version Epoch` at 1058,
> six bytes apart, so the gap the schema omits is pinned rather than described.

The two version words are also easy to confuse. `fVersionClass` is
`ROOT::RNTuple`'s **class** version, 2, a TFile-level number unrelated to the
format's 1.0.2.x, and the note in the source says it "must be kept in sync with
RNTuple.hxx"
(`root/tree/ntuple/src/RMiniFile.cxx:542-546`).

---

## 3. The anchor checksum does not cover "all the fields", and lies outside the byte count

> **The document**: "When serialized to disk, a 64 bit checksum is appended to
> the anchor, calculated as the XXH3 hash of all the (serialized) fields of the
> anchor object."

The sentence is wrong in two ways, and a reader that implements it literally
fails to validate a correct file.

**It is not all the fields.** The hash starts after the byte count and the class
version, as the source states (`root/tree/ntuple/src/RMiniFile.cxx:580-583`):

```cpp
// The byte count and class version members are not checksummed
std::uint32_t GetOffsetCkData() { return sizeof(fByteCount) + sizeof(fVersionClass); }
```

Combined with §2 above, a reader may not know those fields are there at all: the
schema omits six bytes, and the checksum rule depends on knowing about them.

**The checksum is outside the byte count.** `fByteCount` covers
`sizeof(RTFNTuple) - 4`, and the checksum is appended after the struct:
`GetSizePlusChecksum()` is `sizeof(RTFNTuple) + sizeof(std::uint64_t)`
(`root/tree/ntuple/src/RMiniFile.cxx:562`). The object is therefore **eight bytes
longer than its own byte count**.

Measured on `RNTuple.root`:

| | |
|---|---|
| payload | 1889 to 1967, **78 bytes** |
| byte count at 1889 | `40 00 00 42`, so 66, ending at 1959 |
| `sizeof(RTFNTuple)` | 4 + 2 + 4×2 + 7×8 = **70** |
| checksum | 1959 to 1967, `da 43 7b 17 d6 e1 04 e9` |
| checksummed range | 1895 to 1959, 64 bytes — `GetSizeCkData()` = 70 − 6 |

A reader that trusts the byte count to delimit the anchor never sees the
checksum, and one that checks the byte count against the payload length finds a
mismatch of eight and may reject the file.

> `rntuple/anchor` pins the same gap on the pinned release: its byte count of 66
> at 1052 ends the object at 1122, its record payload ends at 1130, and the eight
> bytes between are asserted as the checksum.

---

## 4. Locator type `0x02` is assigned and implemented, not reserved

> **The document**, under *Locators and Envelope Links*, gives one locator type
> and then closes the range:
>
> | Type | Meaning | Payload format |
> |------|---------|----------------|
> | 0x01 | Large locator | 64bit size followed by 64bit offset |
>
> "The range 0x02 - 0x7f is reserved for future use."

**`0x02` is not reserved.** ROOT writes it for a DAOS object-store locator
(`root/tree/ntuple/src/RNTupleSerialize.cxx:1089-1091`) and reads it back
(`root/tree/ntuple/src/RNTupleSerialize.cxx:1137-1140`), with a payload format of
its own that the *Well-known Payload Formats* section does not describe:

```cpp
case RNTupleLocator::kTypeDAOS:
   size += SerializeLocatorPayloadObject64(locator, payloadp);
   locatorType = 0x02;
```

That payload, *Object64*, is **variable length**, which no locator payload in
the document is (`root/tree/ntuple/src/RNTupleSerialize.cxx:476-490`). The byte
count is serialized as a `uint32` when it fits and a `uint64` when it does not,
followed by a 64-bit location, so the payload is 12 or 16 bytes and the reader
tells them apart by the locator's own size field
(`root/tree/ntuple/src/RNTupleSerialize.cxx:493-500`).

**`0x7e` is taken too**, by a locator ROOT's own tests write
(`root/tree/ntuple/src/RNTupleSerialize.cxx:1094-1099`,
`root/tree/ntuple/inc/ROOT/RNTupleTypes.hxx:352`). It uses the Object64 payload
under a different type byte, the case the document's own note anticipates when it
says "locators having a different value for _Type_ may share a given payload
format".

The object store is within the document's scope: its *Introduction* says
envelopes and pages "are meant to be embedded in a data container such as a
ROOT file **or a set of objects in an object store**", and the locator section
opens by saying a locator "can specify a certain object ID". The sentence to fix
is the one declaring the type byte for that case "reserved for future use".

This does not corrupt a reader: ROOT's own reader maps an unrecognised type to
`kTypeUnknown`, and so would a reader following the document. But such a reader
treats a file it could have read as unreadable, and the specification gives it no
way to learn otherwise.

---

## 5. "Envelope" means two different things two lines apart

> **The document**, under *Envelopes*, defines two fields of the same block:
>
> - "_Envelope length_: Uncompressed size of the envelope"
> - "_XxHash-3_: Checksum of the envelope and the payload bytes together"

The diagram directly above draws `XxHash-3` **inside** the envelope. Read that
way, the first sentence makes the length include the checksum, and the second
makes the checksum cover itself, which cannot be implemented. For the two
sentences to be consistent, "the envelope" has to mean the whole block in one and
the eight-byte preamble in the other.

What the code does, on both sides:

| | |
|---|---|
| Length written | `typeAndSize \|= (size + 8) << 16`, where `size` is **everything written so far** — the 8-byte preamble and the payload — and the `+ 8` is the checksum still to come (`root/tree/ntuple/src/RNTupleSerialize.cxx:895`; the preamble is one `uint64`, `root/tree/ntuple/src/RNTupleSerialize.cxx:873-882`) |
| Checksum written over | `SerializeXxHash3(envelope, size, ...)` — bytes `[0, size)`, i.e. everything **before** itself (`root/tree/ntuple/src/RNTupleSerialize.cxx:898`) |
| Checksum verified over | `VerifyXxHash3(base, envelopeSize - 8, ...)` (`root/tree/ntuple/src/RNTupleSerialize.cxx:934`) |

**The length includes the checksum, and the checksum covers everything except
the checksum.** The document states neither half unambiguously.

Verified against `RNTuple.root` — its header envelope is at offset 254 with the
anchor's `Len Header` 332, and its first eight bytes are
`01 00 4c 01 00 00 00 00`, giving type 1 and length **332**, which is the whole
block including the trailing hash. Running ROOT's own
`RNTupleSerializer::VerifyXxHash3` over the bytes:

| Range | Result |
|---|---|
| `[0, 332 - 8)` | **OK** |
| `[0, 332)` | mismatch |

A reader that takes the length to exclude the checksum reads eight bytes too few
and then looks for the next envelope eight bytes early; one that hashes the full
length never validates a correct file.

> `rntuple/anchor` asserts both ends of the same envelope: its preamble at 268 is
> `01 00 f0 00 00 00 00 00` — type 1, length 240 — and its checksum occupies
> 500 to 508, which is 268 + 240. The footer's *Header checksum* field at 854
> holds the same eight bytes, the only place in the file where the relation is
> recorded.

The fix should also cover the anchor: `Len Header` and `Len Footer` in the anchor
are the envelope length in this sense (332 and 148 in the same file), so the two
agree once "envelope" is pinned down.

---

## 6. Column type `0x17` does not exist, and ROOT's own JavaScript reader implements it

> **The document**, in the column type table under *Header Envelope → Column
> Description*, lists thirty types. One of them is
>
> | Type | Bits | Name | Contents |
> |------|------|------|----------|
> | 0x17 |   16 | SplitReal16 | Like Real16 but in split encoding |

**There is no such column type in ROOT's C++ implementation**, in the
serializer, the deserializer or the enumeration:

- `SerializeColumnType` goes from `kSplitUInt64` → `0x16` straight to
  `kSplitReal32` → `0x18` (`root/tree/ntuple/src/RNTupleSerialize.cxx:756-757`);
- `DeserializeColumnType` has no `case 0x17`, so the value falls through to
  `kUnknown` (`root/tree/ntuple/src/RNTupleSerialize.cxx:799-800`);
- `ENTupleColumnType` has `kSplitReal64`, `kSplitReal32`, `kSplitInt16` and
  `kSplitUInt16` but **no `kSplitReal16`**
  (`root/tree/ntuple/inc/ROOT/RNTupleTypes.hxx:86-96`);
- `RColumnElementBase::GetValidBitRange` has no entry for it either
  (`root/tree/ntuple/src/RColumnElement.cxx:29-67`).

The string `kSplitReal16` does not occur anywhere under `root/tree/ntuple/`.

**The rest of the table is correct.** Compared mechanically against
`SerializeColumnType` and `GetValidBitRange`, twenty-nine of the thirty rows match
on both name and bit width, including the two variable-width types, `Real32Trunc`
at 10–31 and `Real32Quant` at 1–32. `0x17` is the only row with no counterpart.

> Two of those rows are also checked against bytes: `rntuple/anchor`'s two column
> records carry type `0x0C` with 32 bits on storage for a `float` and `0x07` with
> 32 bits for a `std::int32_t`.

### Why this one is not a documentation nit

JSROOT implements it, because the specification says it exists:

```js
kSplitUInt64 = 0x16,
kSplitReal16 = 0x17,
kSplitReal32 = 0x18,
```

`root/js/build/jsroot.js:179651`, with the decoder at
`root/js/build/jsroot.js:179792` treating it as a two-byte split-encoded column.

Two RNTuple readers **shipped in the same repository** therefore disagree about
the set of column types, because of the document. Nothing is corrupted today,
since the C++ writer cannot emit `0x17` and so no file contains one. But ROOT's
own developers treat the specification as normative, as intended, and one of
them implemented a column type the other implementation does not have.

The fix is a choice upstream, not a correction here: implement `kSplitReal16` in
C++, or drop the row. The encoding is meaningful either way, since `kSplitInt16`
and `kSplitUInt16` exist and split encoding on a two-byte type is well defined.
The row looks like one written in anticipation of a type that was never built.

---

## 7. `Double32_t` is the one exception to the uncompressed-default rule

Two sections state a default and neither mentions the other.

*Fundamental Types* ends with:

> If the ntuple is stored uncompressed, the default changes from split encoding
> to non-split encoding where applicable.

*Low-precision Floating Points* says, unconditionally:

> The ROOT type `Double32_t` is stored on disk as a `double` field with a
> `SplitReal32` column representation.

A reader cannot tell from the document which wins. **The `Double32_t` sentence
does**: both rules live in one function, and the `Double32_t` override runs
last.

```cpp
void RFieldBase::AutoAdjustColumnTypes(const RNTupleWriteOptions &options)
{
   if ((options.GetCompression() == 0) && HasDefaultColumnRepresentative()) {
      ...                                    // every Split* becomes unsplit
      SetColumnRepresentatives({rep});
   }

   if (fTypeAlias == "Double32_t")
      SetColumnRepresentatives({{ROOT::ENTupleColumnType::kSplitReal32}});
}
```

`root/tree/ntuple/src/RFieldBase.cxx:892-915`. The second `if` has no compression
test and overwrites whatever the first one decided.

> **Bytes.** `rntuple/collections` is written with compression 0. Every one of its
> 26 other columns is unsplit (`Index64`, `Real32`, `Int32`, `Char`, `Bit`,
> `Switch`), and `fDouble32` is **`SplitReal32`**, type `double`, type alias
> `Double32_t`. `tools/test_rntuple.py` asserts both halves, so neither the
> exception nor the rule can change silently.

Split encoding on a single-element page is a no-op in practice, so nothing is
corrupted. What a reader gets wrong is the **column type it expects**: a reader
that hardcodes "uncompressed means unsplit" rejects the one column that is not.

The fix upstream is a sentence, not code: say that the `Double32_t`
representation is not subject to the uncompressed adjustment. Whether the
behaviour itself is intended is a question for the RNTuple authors; the override
looks as if it was written before the uncompressed rule existed.

---

## 8. `Type Version` is a signed class version in an unsigned field

*Field Description* gives the field record's second word as

```
|                          Type Version                         |
```

and says of it, in full:

> The field version and type version are used for schema evolution.

A writer puts `TClass::GetClassVersion()` there
(`root/tree/ntuple/src/RFieldMeta.cxx:645`), returned through a
`std::uint32_t`-valued virtual
(`root/tree/ntuple/inc/ROOT/RFieldBase.hxx:668`). That function returns a signed
`Version_t`, and it is **−1 for a class with no `ClassDef`**: every class whose
dictionary ROOT generated for it, which includes every class in a `classes.h`
compiled by ACLiC and most user structs.

The word on disk is therefore **0xFFFFFFFF**. A reader that compares type versions
numerically, the obvious way to implement the schema evolution the document says
the field is for, treats it as newer than every version ever written.

> **Bytes.** In `rntuple/user-class`, `RNHit` and `RNBase` both have `Type
> Version` 0xFFFFFFFF and a `TClass` checksum; the non-class fields beside them
> have 0. Both words are asserted.

ROOT's own code allows for a negative value and guards one use of it:
`R__ASSERT(fSoAClass->GetClassVersion() >= 0)`
(`root/tree/ntuple/src/RFieldMeta.cxx:706`) for the SoA form, which is the case
the document does describe. The regular-class path has no such check.

The fix upstream is a sentence: say that 0xFFFFFFFF means the class has no
version, and that the type checksum is then its only identity. A reader today
should treat 0xFFFFFFFF as "unversioned" rather than as a number, and fall back to
the checksum, which is what the checksum flag is for.

---

## 9. The extra type information's content is a length-prefixed string

*Extra type information* draws the record frame as two 32-bit integers and then
says:

> The type information record frame has the following contents followed by a
> string containing the type name.

and, of content identifier 0:

> The format of the content is a ROOT streamed `TList` of `TStreamerInfo` objects.

The document does not say that the content is itself a **string**, which it is.
The serializer writes four values, and the last two are both strings:

```cpp
pos += RNTupleSerializer::SerializeUInt32(desc.GetTypeVersion(), *where);
pos += RNTupleSerializer::SerializeString(desc.GetTypeName(), *where);
pos += RNTupleSerializer::SerializeString(desc.GetContent(), *where);
```

`root/tree/ntuple/src/RNTupleSerialize.cxx:389-391`. An RNTuple string is a 32-bit
little-endian length followed by the bytes, so there are **four bytes between the
type name and the first byte of the `TList`**.

> **Bytes.** In `rntuple/streamed` the record's content length is 438 at offset
> 1236, and the streamed object starts at 1240 with `40 00 01 b2` — a ROOT byte
> count of 434 with the 0x40000000 flag — then `ff ff ff ff` and `TList`. Both
> words are asserted, on either side of the boundary.

A reader that takes "the rest of the frame" as the object starts four bytes early
and fails on the first byte count. The fix upstream is one clause: say that the
content is a string, like the type name before it.

---

## 10. The streamer info is in the footer, not where the document introduces it

*Extra type information* is a subsection of **Header Envelope**, and content
identifier 0, "Serialized ROOT streamer info", is described there. A reader that
looks for it there finds **nothing**, on every file that has a streamed field.

It cannot be in the header. The set of classes serialized by the ROOT streamer is
not known until the dataset is committed, and that is where ROOT builds the
record:

```cpp
ROOT::Internal::RNTupleLink RPagePersistentSink::CommitDatasetImpl()
{
   if (!fInfosOfStreamerFields.empty()) {
      ...
      RExtraTypeInfoDescriptorBuilder extraInfoBuilder;
      extraInfoBuilder.ContentId(EExtraTypeInfoIds::kStreamerInfo)
         .Content(RNTupleSerializer::SerializeStreamerInfos(fInfosOfStreamerFields));
      fDescriptorBuilder.ReplaceExtraTypeInfo(...);
   }
   ... SerializeFooter(...)
}
```

`root/tree/ntuple/src/RPageStorage.cxx:1290-1310`. The record therefore goes in
the **footer envelope's schema extension**, whose four lists the document says are
"identical to the last four fields in Header Envelope" and are to be interpreted
"as if it was found directly at the end of the header". The format permits both
places and ROOT uses only one, which the document never says.

> **Bytes.** `rntuple/streamed`'s header envelope has an **empty** extra type
> information list; the footer's schema extension has one record, content
> identifier 0, type version 0, empty type name, holding a `TList` whose
> `TStreamerInfo` names `RNStreamedInner`. Asserted on both sides.

The streamer info is what a reader needs to decode a streamed field at all, and
the document places it in the wrong envelope. The fix is a sentence in *Extra type
information* saying that a writer emits `kStreamerInfo` in the footer's schema
extension, because its content is only complete at commit time.

---

## 11. The footer's attribute set list does not exist before format 1.0.1.0

> **The document**, under *Footer Envelope*, gives the footer's structure as
> five items, the last of them "List frame of linked attribute set record
> frames", with no version attached. Under *Notes on Backward and Forward
> Compatibility* it asks that "readers supporting a certain version of the
> specification should support reading files that were written according to
> previous versions of the same epoch."

**A footer written before format 1.0.1.0 ends after the cluster groups.** The
list arrived with that version: root commit `feccdda5a99` (2025-09-16) added its
serialization and raised the anchor's minor version from 0 to 1. ROOT's reader
says so and reads the list only when there is something left to read:

```cpp
// NOTE: Attributes were introduced in v1.0.1.0, so this section may be missing.
// Testing for > 8 because bufSize includes the checksum.
if (fnBufSizeLeft() > 8) {
```

`root/tree/ntuple/src/RNTupleSerialize.cxx:2015-2017`.

The document gives a reader no way to know this. It does version one other late
addition, in the *Introduced in* column of the feature flag table, but the footer
structure has no such note, and a reader that implements it as written and then
reads an older file, as the compatibility notes require, takes the envelope's
checksum for the size of a list frame.

> **Bytes.** `RNTuple.root` (format 1.0.0.0, ROOT 6.35/01): the footer at 1687 is
> 148 bytes, its cluster group list ends at 1827, and the checksum starts there.
> `rntuple/anchor` (1.0.2.0), which links no attribute set, has a footer of 160
> bytes: the same shape plus the empty list, `-12` and a count of 0, at 978, and
> the checksum at 990. Over the RNTuple files of `gen/foreign/`, all 26 anchors of
> format 1.0.0.x have no list and both of 1.0.1.0 have an empty one.
> `tools/test_rntuple.py` asserts the two sides, and `check_invariants.py` fails a
> footer of 1.0.1.0 or later without the list.

The fix upstream is a clause: the list is present from 1.0.1.0 on, and a footer of
an earlier version ends after the cluster group list.

---

## 12. "Attribute Anchor Uncompressed Size" counts six bytes the anchor schema does not show

> **The document**, under *Linked Attribute Set Record Frame*: "Note that the
> Attribute Anchor Uncompressed Size includes the 8 bytes of the checksum."

**It also includes the byte count and the class version** that begin the anchor
object and that the document's anchor schema omits (erratum 2). The writer
records the size of the whole on-disk struct plus the checksum:

```cpp
// NOTE: checksum length is included in the uncompressed len
anchorInfo.fLength = RTFNTuple{}.GetSize() + sizeof(std::uint64_t);
```

`root/tree/ntuple/src/RMiniFile.cxx:1358-1359`, where `GetSize()` is
`sizeof(RTFNTuple)` (`root/tree/ntuple/src/RMiniFile.cxx:579`) and `RTFNTuple`
opens with `fByteCount` and `fVersionClass`
(`root/tree/ntuple/src/RMiniFile.cxx:547-549`): 70 + 8 = **78**. The reader takes
the value as the uncompressed length of that same object and finds the checksum
in its last eight bytes (`root/tree/ntuple/src/RMiniFile.cxx:846-850`).

A reader that follows the document adds the checksum to the schema it was given,
4 × 16 + 7 × 64 bits, and expects **72**. It then decompresses to the wrong
length or looks for the checksum six bytes early.

> **Bytes.** In `rntuple/attributes` both records give 78, at 3848 and 3884. The
> anchors they locate begin with a byte count of 66 at 2508 and 3451, which is
> 66 + 4 + 8 = 78 with the count's own word and the checksum, and each anchor
> key's `fObjLen` is 78 (at 2468 and 3410).

The locator next to it points at the same object: its offset is the anchor key's
payload, `GetSeekKey() + GetKeylen()`, and its size the payload's size on storage
(`root/tree/ntuple/src/RMiniFile.cxx:1368-1369`). That agrees with the document,
which calls the `ROOT::RNTuple` object the anchor, but a reader coming from the
TFile side will look for a key there; [NOTES 8](NOTES.md#8-linked-attribute-sets)
says what else it needs.

The fix upstream is a sentence: the size is the uncompressed length of the whole
anchor object, byte count, class version and checksum included, which is the
anchor key's `fObjLen`.

---

## 13. ROOT refuses an attribute set with a field the document says to ignore

> **The document**, under *Attribute Schema Version*: "A change in Minor version
> number indicates the presence of optional additional fields in the schema:
> readers should still be able to read the attribute set as before, ignoring any
> new field."

**ROOT's reader never sees the minor version, and requires exactly three
fields.** `OpenAttributeSet` passes on only the major version
(`root/tree/ntuple/src/RNTupleReader.cxx:384`), which the reader checks, and it
then counts the attribute RNTuple's top-level fields:

```cpp
if (metaFieldIds.size() != kMetaFieldIndex_Count) {
   throw ROOT::RException(R__FAIL("invalid number of attribute meta-fields: expected " +
```

`root/tree/ntuple/src/RNTupleAttrReading.cxx:34-38`, with `kMetaFieldIndex_Count`
3 (`root/tree/ntuple/inc/ROOT/RNTupleAttrUtils.hxx:42-48`). A version 1.1 that
adds an optional field is therefore unreadable by 6.40.04, which is the case the
minor version exists for.

> **Bytes**, by probing ROOT 6.40.04 on 2026-09-24. A file holding an RNTuple of
> four top-level fields, `_rangeStart`, `_rangeLen`, `_userData` and `_extra`,
> written by ROOT, with a main footer's attribute set record pointed at its anchor
> and its checksum recomputed with `RNTupleSerializer::SerializeXxHash3`:
> `OpenAttributeSet` fails with "invalid number of attribute meta-fields: expected
> 3, got 4" whether the record says minor 0 or minor 1. The same record pointed at
> a three-field set and marked minor 1 opens and returns its ranges, and a copy of
> `rntuple/attributes` whose `runs` record says major 2 fails with "unsupported
> attribute schema version: 2" while the main RNTuple still reads, as the
> document asks. None of these files is committed; `tools/test_rntuple.py` pins
> the three source lines instead, and `check_invariants.py` accepts extra fields
> after the three when the minor version is above 0, as the document does.

The document does not say where a new field goes. It can only be at the top
level: "the order and name of the meta Model's fields is defined by the schema
version" (`root/tree/ntuple/inc/ROOT/RNTupleAttrUtils.hxx:36`), and everything
below `_userData` is the user's. I am unsure whether the ROOT authors mean to
relax the reader or to tighten the sentence; attribute sets are marked
experimental, and both serializer and deserializer warn that they "are not
guaranteed to be readable back in the future"
(`root/tree/ntuple/src/RNTupleSerialize.cxx:1816-1817`). Either way, one of the two
has to change.
