# Errata against the upstream specification

Places where [the tracked copy](BinaryFormatSpecification.md) and ROOT's code
disagree. Same bar as the rest of this project: every entry is verified twice,
against the pinned submodule with a `path:line` citation **and** against real
bytes, and says what a reader that follows the document gets wrong.

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

Bytes come from two files.

**`rntuple/anchor`** is this project's own fixture, written by the **pinned**
ROOT 6.40.04 with compression off so the envelopes are readable in place. Its
anchor record is at 998 and its payload runs 1052 to 1130; its header envelope is
at 268 and its footer at 838. Every erratum that can be shown in bytes is
asserted there, which is what makes these claims checked rather than stated.

**`RNTuple.root`**, 2 514 bytes, written by ROOT 6.35/01 and published at
<https://root.cern/files/>; `gen/cern/README.md` lists it and
`tools/fetch_cern.py` fetches it. Its anchor record is at offset 1835 and its
payload runs 1889 to 1967. It is **older than the pinned release** and carries an
older format version — `Version Minor` 0 against 2 — so it is kept as a second,
independent witness rather than as the primary one.

---

## 1. The version in the title is not the version a writer stamps

> **The document** is titled *RNTuple Binary Format Specification **1.0.2.1***.

**The writer** stamps epoch 1, major 0, minor 2, patch **0**
(`root/tree/ntuple/inc/ROOT/RNTuple.hxx:79-82`), so an anchor written by the
pinned ROOT says **1.0.2.0**.

> Confirmed in bytes by `rntuple/anchor`, whose four version words at 1058, 1060,
> 1062 and 1064 are 1, 0, **2**, **0**.

Harmless in itself — the document says of the patch component that "the
versioning is for reporting only" — but it means **the version in the document is
not the version in the files**, which is a confusing thing for a format
specification to do. A reader comparing the two has no way to tell whether it is
looking at a stale file or a stale document.

**And it is about to matter.** The feature-flag table under *Feature Flags* says
flag bit 0, *Nested Deferred Columns*, was "Introduced in 1.0.2.1" — a version no
writer stamps. The flag is declared
(`root/tree/ntuple/inc/ROOT/RNTupleDescriptor.hxx:780`) and nothing sets it yet,
so no file carries it today; when one does, its anchor will say 1.0.2.0 while the
document says the feature belongs to 1.0.2.1. Either the constant or the table
has to move.

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
They are not an accident of the key: they are the first two members of the struct
that *is* the on-disk anchor
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
subsequent field is six bytes early.

> `rntuple/anchor` asserts the byte count at 1052 and `Version Epoch` at 1058,
> six bytes apart, so the gap the schema omits is pinned rather than described. It is not a hypothetical: the document is a
binary format specification, and this is the only description it gives of where
the anchor's first field is.

The two version words are also easy to confuse with each other. `fVersionClass`
is `ROOT::RNTuple`'s **class** version — 2, a TFile-level number that has nothing
to do with the format's 1.0.2.x — and the note in the source says it "must be
kept in sync with RNTuple.hxx"
(`root/tree/ntuple/src/RMiniFile.cxx:542-546`).

---

## 3. The anchor checksum does not cover "all the fields", and lies outside the byte count

> **The document**: "When serialized to disk, a 64 bit checksum is appended to
> the anchor, calculated as the XXH3 hash of all the (serialized) fields of the
> anchor object."

Two things are wrong with that sentence, and a reader that implements it
literally fails to validate a correct file.

**It is not all the fields.** The hash starts after the byte count and the class
version, which the source says in as many words
(`root/tree/ntuple/src/RMiniFile.cxx:580-583`):

```cpp
// The byte count and class version members are not checksummed
std::uint32_t GetOffsetCkData() { return sizeof(fByteCount) + sizeof(fVersionClass); }
```

Since §2 above means a reader may not know those fields are there at all, the
combination is worse than either half: the schema hides six bytes, and the
checksum rule then silently depends on knowing about them.

**The checksum is outside the byte count.** `fByteCount` covers
`sizeof(RTFNTuple) - 4`, and the checksum is appended *after* the struct —
`GetSizePlusChecksum()` is `sizeof(RTFNTuple) + sizeof(std::uint64_t)`
(`root/tree/ntuple/src/RMiniFile.cxx:562`). So the object is **eight bytes longer
than its own byte count says**.

Measured on `RNTuple.root`:

| | |
|---|---|
| payload | 1889 to 1967, **78 bytes** |
| byte count at 1889 | `40 00 00 42`, so 66, ending at 1959 |
| `sizeof(RTFNTuple)` | 4 + 2 + 4×2 + 7×8 = **70** |
| checksum | 1959 to 1967, `da 43 7b 17 d6 e1 04 e9` |
| checksummed range | 1895 to 1959, 64 bytes — `GetSizeCkData()` = 70 − 6 |

**A reader that trusts the byte count to delimit the anchor never sees the
checksum**, and one that checks the byte count against the payload length finds a
mismatch of exactly eight and may reject the file. Both are consequences of a
sentence that reads as a complete description and is not.

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

That payload — *Object64* — is **variable length**, which no locator payload in
the document is (`root/tree/ntuple/src/RNTupleSerialize.cxx:476-490`): the byte
count is serialized as a `uint32` when it fits and a `uint64` when it does not,
followed by a 64-bit location, so the payload is 12 or 16 bytes and the reader
tells them apart by the locator's own size field
(`root/tree/ntuple/src/RNTupleSerialize.cxx:493-500`).

**`0x7e` is taken too**, by a locator ROOT's own tests write
(`root/tree/ntuple/src/RNTupleSerialize.cxx:1094-1099`,
`root/tree/ntuple/inc/ROOT/RNTupleTypes.hxx:352`), using the Object64 payload
under a different type byte — which is the case the document's own note
anticipates when it says "locators having a different value for _Type_ may share
a given payload format".

The object store is in scope for the document, not an aside: its *Introduction*
says envelopes and pages "are meant to be embedded in a data container such as a
ROOT file **or a set of objects in an object store**", and the locator section
opens by saying a locator "can specify a certain object ID". Having set that up,
declaring the one type byte that does it "reserved for future use" is the
sentence to fix.

A reader is not corrupted by this — ROOT's own reader maps an unrecognised type
to `kTypeUnknown` and so would a reader following the document — but it will
treat a file it could have read as unreadable, and has no way to learn otherwise
from the specification.

---

## 5. "Envelope" means two different things two lines apart

> **The document**, under *Envelopes*, defines two fields of the same block:
>
> - "_Envelope length_: Uncompressed size of the envelope"
> - "_XxHash-3_: Checksum of the envelope and the payload bytes together"

The diagram directly above draws `XxHash-3` **inside** the envelope. Read that
way, the first sentence makes the length include the checksum — and the second
makes the checksum cover itself, which cannot be implemented. For the two
sentences to be consistent, "the envelope" has to mean the whole block in one and
the eight-byte preamble in the other.

**What the code does**, on both sides:

| | |
|---|---|
| Length written | `typeAndSize \|= (size + 8) << 16` — the payload size **plus the checksum** (`root/tree/ntuple/src/RNTupleSerialize.cxx:895`) |
| Checksum written over | `SerializeXxHash3(envelope, size, ...)` — bytes `[0, size)`, i.e. everything **before** itself (`root/tree/ntuple/src/RNTupleSerialize.cxx:898`) |
| Checksum verified over | `VerifyXxHash3(base, envelopeSize - 8, ...)` (`root/tree/ntuple/src/RNTupleSerialize.cxx:933`) |

So: **the length includes the checksum, and the checksum covers everything except
the checksum.** Both halves need saying, and the document says neither
unambiguously.

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
and then finds the next envelope eight bytes early; one that hashes the full
length never validates a correct file.

> `rntuple/anchor` asserts both ends of the same envelope: its preamble at 268 is
> `01 00 f0 00 00 00 00 00` — type 1, length 240 — and its checksum occupies
> 500 to 508, which is 268 + 240. The footer's *Header checksum* field at 854
> holds those same eight bytes, which is the only thing in the file that states
> the relation.

The same word is also doing double duty against the anchor, which is worth
stating in the fix: `Len Header` and `Len Footer` in the anchor are the envelope
length in **this** sense — 332 and 148 in the same file — so the two agree once
"envelope" is pinned down.

---

## 6. Column type `0x17` does not exist, and ROOT's own JavaScript reader implements it

> **The document**, in the column type table under *Header Envelope → Column
> Description*, lists thirty types. One of them is
>
> | Type | Bits | Name | Contents |
> |------|------|------|----------|
> | 0x17 |   16 | SplitReal16 | Like Real16 but in split encoding |

**There is no such column type in ROOT's C++ implementation.** Not in the
serializer, not in the deserializer, and not in the enumeration:

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

**The rest of the table is exact.** Comparing all thirty rows against
`SerializeColumnType` and `GetValidBitRange` mechanically, twenty-nine match on
both name and bit width — including the two variable-width types, `Real32Trunc`
at 10–31 and `Real32Quant` at 1–32. `0x17` is the single row with no counterpart.

> Two of those rows are also checked against bytes: `rntuple/anchor`'s two column
> records carry type `0x0C` with 32 bits on storage for a `float` and `0x07` with
> 32 bits for a `std::int32_t`.

### Why this one is not a documentation nit

**JSROOT implements it**, because the specification says it exists:

```js
kSplitUInt64 = 0x16,
kSplitReal16 = 0x17,
kSplitReal32 = 0x18,
```

`root/js/build/jsroot.js:179651`, with the decoder at
`root/js/build/jsroot.js:179792` treating it as a two-byte split-encoded column.

So two RNTuple readers **shipped in the same repository** disagree about the set
of column types, and the document is the reason. Nothing is corrupted today —
the C++ writer cannot emit `0x17`, so no file contains one — but the
specification is being treated as normative by ROOT's own developers, which is
exactly what it is for, and here it sent one of them somewhere the other will not
follow.

The fix is a choice upstream, not a correction here: implement `kSplitReal16` in
C++, or drop the row. The encoding is meaningful either way — `kSplitInt16` and
`kSplitUInt16` exist and split encoding on a two-byte type is well defined — so
this reads like a row written in anticipation that was never built.
