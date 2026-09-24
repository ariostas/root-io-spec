# Conventions

Conventions that every other document in `spec/` relies on. Read this first.

## 1. Status of this specification

This specification is **descriptive of ROOT 6.40.04**, the version pinned as the
`root/` submodule (commit `1211eda9301`). It is not normative for ROOT.

- Where this specification and the pinned submodule disagree, **the submodule is
  right** and this specification has a bug. Report it.
- Where ROOT's behaviour itself looks wrong, it is recorded in the relevant
  `ERRATA.md` and, where possible, raised upstream.

Statements about other ROOT versions are marked as such. An unmarked statement
describes 6.40.04.

## 2. Requirement levels

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**,
**SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY** and **OPTIONAL** are to be
interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

Their meaning depends on what they apply to:

- Applied to a **reader**, they describe what an implementation must do to read
  files ROOT writes.
- Applied to a **file**, they describe an invariant ROOT's own output satisfies.
  A reader MAY check these and reject files that violate them, but SHOULD prefer
  to be tolerant unless the violation makes the data ambiguous. Real files were
  written by many ROOT versions, some with known bugs.

Writing is not specified as an algorithm. Each layer ends with an `Invariants`
section listing what a conforming file satisfies. A writer can validate its own
output against it, and ROOT's incidental choices are not prescribed. See
`PLAN.md` §2.8.

## 3. Byte order

> **ROOT uses two different byte orders in the same file.**

| Layer | Byte order |
|---|---|
| File header, `TKey`, directory records, free list | **big-endian** |
| Everything serialized through `TBuffer` — i.e. all object data | **big-endian** |
| RNTuple envelopes and page payloads | **little-endian** |
| The `ROOT::RNTuple` anchor, because it is an ordinary `TKey` payload | **big-endian** |
| The two size fields of a **compression block header** — 24-bit, at block offsets 3-5 and 6-8 | **little-endian** |

Big-endian order does not depend on the host. The `tobuf`/`frombuf` helpers in
`root/core/base/inc/Bytes.h` apply it, byte-swapping on little-endian hosts. A
reader MUST NOT assume host order anywhere.

Unless a document says otherwise, every integer in `spec/01-container/`,
`spec/02-serialization/`, `spec/03-classes/` and `spec/04-ttree/` is big-endian.
`spec/05-rntuple/` states its own rules. Within the classic format the only
exception is the compression block header, whose two 24-bit sizes are
little-endian. [Compression §2](01-container/Compression.md#2-block-header) calls
this the most common mistake in a new implementation, so it is also listed in the
table above.

## 4. Primitive types

Widths are on-disk widths. Where the on-disk width differs from the in-memory
width, the table says so; this is a common source of bugs.

| Type | On disk | Notes |
|---|---|---|
| `Bool_t` | 1 | 0 = false, non-zero = true |
| `Char_t`, `UChar_t` | 1 | |
| `Short_t`, `UShort_t` | 2 | |
| `Int_t`, `UInt_t` | 4 | |
| `Long_t`, `ULong_t` | **8** | **4 bytes in memory on some platforms; always 8 on disk**, sign-extended |
| `Long64_t`, `ULong64_t` | 8 | |
| `Float_t` | 4 | binary32 bit pattern, big-endian — see note |
| `Double_t` | 8 | binary64 bit pattern, big-endian — see note |
| `Version_t` | 2 | signed |
| `Seek_t` / file offsets | 4 or 8 | width depends on the large-file flag; see `01-container/FileHeader.md` |

Floating-point values are written as the **host's bit pattern with the bytes
reversed**. `root/core/base/inc/Bytes.h` has no conversion step and does not check
the format. On every platform ROOT supports that pattern is IEEE 754, so in
practice the on-disk form is IEEE 754 big-endian, but this follows from the host
and is not enforced by the format.

`Long_t` has two traps:

- Scalar `ULong_t` is written through the **signed** helper
  (`root/io/io/inc/TBufferFile.h:339`), so on a platform where `long` is 4 bytes a
  value ≥ 2³¹ is written with `0xFFFFFFFF` in the high four bytes rather than
  zeros. Arrays of `ULong_t` zero-extend instead. On 64-bit hosts the two agree.
- Files written by ROOT older than 3.00/06 stored `Long_t` at the host's `sizeof(long)`
  rather than always 8. Readers handling such files must branch on the file version
  (`root/io/io/src/TBufferFile.cxx:173-181`).

`Double32_t` and `Float16_t` are **not** primitive types with fixed widths. They are
`Double_t`/`Float_t` in memory and a configurable number of bits on disk, set by an
annotation in the member's comment. See
[Element types §5](02-serialization/ElementTypes.md#5-kdouble32-and-kfloat16) for
the annotation grammar and the three encodings,
[Leaves §7](04-ttree/TLeaf.md#7-tleaff16-and-tleafd32) for the leaf classes that
hold them in a tree, and
[Reading entries §5.2](04-ttree/ReadingEntries.md#52-the-width-can-depend-on-a-title-the-branch-does-not-have)
for the trap that the width is recorded only on the streamer element.

## 5. String encodings

ROOT uses several distinct string encodings, and they are easily confused. Every
document MUST name which one it means, using the terms defined here.

### 5.1 Counted string

One length byte, then that many bytes. If the length is 255, a 4-byte big-endian
length follows the 255 and then that many bytes.

```
short form (n <= 254):   n:u8   payload:n bytes
long form  (n >= 255):   255:u8   n:u32   payload:n bytes
```

The escape applies at length **> 254**, so a leading `0xFF` never means "255
characters": a 255-character string is always written in the long form. An empty
string is a single `0x00` byte. The payload is uninterpreted bytes, not Unicode; a
reader SHOULD NOT assume UTF-8.

Used by `TString` and by the `TKey` name, title and class-name fields.

The counted string appears **bare**, with no preceding byte count or version
word, both in a `TKey` and when a `TString` is a data member. A byte count and a
class record appear only when a `TString` is written as a standalone object through
a pointer, not by value.

> Demonstrated by `container/file-minimal`: the `TObjString` payload ends with
> `05 68 65 6c 6c 6f` at offsets 392 to 397, the bare counted string for `hello`,
> immediately after the base `TObject` and with nothing in between.

### 5.1.1 `TStringLong` — the same idea with a four-byte count

`TStringLong` derives from `TString` and replaces the encoding entirely
(`root/core/base/src/TStringLong.cxx:131-147`):

```
n:i32   payload:n bytes
```

There is no length byte, no escape, and no version word or byte count. The
streamer writes only the count and the characters, so the form is bare wherever it
appears, like §5.1's. The count is signed. Each character is written one at a time
rather than as a block, which makes no difference on disk.

The two encodings differ in the length prefix at every length:

| Length | `TString` | `TStringLong` |
|---|---|---|
| 0 | `00` | `00 00 00 00` |
| 6 | `06` + 6 | `00 00 00 06` + 6 |
| 300 | `ff` + `00 00 01 2c` + 300 | `00 00 01 2c` + 300 |

Above 254 characters `TString` costs one byte more; below that, `TStringLong`
costs three more. The class exists because it predates the 255 escape in
`TString`.

**Nothing in ROOT uses it.** The only files naming `TStringLong` are its own
header and source and a `LinkDef`, so it reaches a file only through a
user-defined class, as in `serialization/stringlong`.

> `serialization/stringlong` puts both in one object: at offset 373 a
> `TStringLong` writes `00 00 00 06` for `abcdef` and at 383 a `TString` writes
> `06` for the same text. In the second object, 300 characters, the counts are
> `00 00 01 2c` at 443 and `ff 00 00 01 2c` at 747.

### 5.2 Null-terminated string

Bytes up to and including a `0x00` terminator. Its main use is the class name in a
`kNewClassTag` record (see [Buffer framing](02-serialization/Buffer.md#51-a-new-class)),
but it is not limited to that. A hand-written streamer that does
`buf << someCharPointer` also produces this form, because `WriteCharP` writes
`strlen + 1` bytes (`root/io/io/inc/TBufferFile.h:376`,
`root/io/io/src/TBufferFile.cxx:3404-3407`). §5.4 repeats this warning.

### 5.3 `std::string`

A counted string (§5.1) **wrapped in a byte count and a version word**, unlike a
`TString` member, which has neither:

```
byteCount:u32 (| 0x40000000)   version:i16   counted string
```

An empty `std::string` member is therefore 7 bytes, not 1. Details, including which
class the version word refers to, are in
[Collections](02-serialization/Collections.md).

### 5.4 `char*` members

A 4-byte signed length, then exactly that many bytes, with **no terminator and no
255 escape**:

```
n:i32   payload:n bytes
```

This is not the counted string of §5.1, and confusing the two is a common bug. A
null pointer and an empty string are indistinguishable: both are four zero bytes.
See [Element types](02-serialization/ElementTypes.md), type code 7 (`kCharStar`).

On the writing side, a hand-written streamer using `buf << someCharPointer`
produces the null-terminated form of §5.2, not this one.

## 6. Notation

### 6.1 Bit diagrams

Fixed-layout records use the diagram style of the RNTuple specification, so both
halves of this repository look alike. Bit 0 is the most significant bit of the
first byte, matching the big-endian byte order:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          fNbytes                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          fVersion             |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+          fObjlen              +
|                               |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### 6.2 Field tables

Sequential layouts use a table. Offsets are relative to the start of the structure
being described, never absolute in the file, and are given only where the layout is
fixed:

| Offset | Field | Type | Value / notes |
|---|---|---|---|

### 6.3 Member tables

Streamer-info-driven classes use a member table, with the type code from
`02-serialization/ElementTypes.md` and the class-version range in which the member
is present:

| Member | Type | Code | Since | Until | Notes |
|---|---|---|---|---|---|

`Since` and `Until` are **class versions**, not ROOT releases. `—` in `Until` means
"still present in 6.40.04".

### 6.4 Conditional layout

Where a layout branches, the condition is stated before the branch and each branch
is a separate table or diagram. Layouts are never described as "the same as above
but with X different".

### 6.5 Cross-references

A reference to another document in `spec/` is written as a **Markdown link** when
that document exists, so that it works in the published site and is checked by the
build:

```markdown
See [Buffer](../02-serialization/Buffer.md) for the byte-count encoding.
```

A reference to a document that has **not been written yet** is written as inline
code instead, because the site build treats a link to a missing page as an error:

```markdown
See `02-serialization/Buffer.md` for the byte-count encoding.
```

Such a reference MUST be converted to a link when its target is written. The
remaining forward references in inline code are therefore a list of what is still
missing.

### 6.6 Generated content

Blocks between these markers are produced by a tool and MUST NOT be hand-edited;
CI runs each tool with `--check` and fails when they are stale:

```
<!-- BEGIN GENERATED: <what> -->
<!-- END GENERATED -->
```

`tools/inventory.py` writes the blocks in `spec/99-appendix/` from the pinned
submodule, and `tools/element_lists.py` writes those in
`spec/06-writing/ElementLists.md` from the ROOT-written fixtures. Notes that need
human judgement go in a file the generator merges in, so that they survive
regeneration: for `inventory.py` that is `spec/99-appendix/streamers.toml`.
Everything outside the markers is hand-written.

## 7. Citing the reference implementation

Claims are cited as a path relative to the repository root plus a line number,
always at the pinned submodule commit:

> `root/io/io/src/TBufferFile.cxx:2751`

Citations are checked. `tools/check_citations.py` verifies that every cited file
exists in the pinned submodule and that every cited line number is within that
file, and CI fails otherwise. `tools/check_pin.py` checks that the commit the
published site links to is the commit the submodule is pinned at.

No tool checks that the cited lines still contain what the citing sentence claims.
Line numbers drift when the submodule is bumped even where the file and length
remain valid, so a citation whose content has moved should be reported as a bug.

In the published site these citations render as links into root-project/root at the
pinned commit, via `tools/rootcite.py`.

Where a fixture demonstrates a claim, it is cited by case ID:

> Demonstrated by `container/file-minimal`.

## 8. Reference files

`data/` holds small ROOT files generated by the macros in `gen/cases/`. Each case
has a `case.toml` giving its record layout and a list of byte-level assertions.
`tools/check_bytes.py` checks those assertions with Python alone, without ROOT or
third-party packages, so a third-party implementation can use them directly as
test vectors.

```sh
tools/generate.py --check     # verify fixtures against case.toml
tools/generate.py             # regenerate from gen/cases (needs ROOT)
```

Files cannot be reproduced byte-for-byte, because `TKey::fDatime` records the wall
clock and each file gets a fresh `TUUID`. `tools/normalize.py` masks those before
digesting, so `data/MANIFEST.sha256` detects format changes and ignores timestamps
and UUIDs.

## 9. Terminology

| Term | Meaning |
|---|---|
| **Record** | A `TKey` plus its payload, at one offset in the file. A file is a sequence of records. |
| **Key** | The fixed part of a record, describing where and what the payload is. |
| **Payload** | The bytes of a record after the key. Possibly compressed. |
| **Object data** | A payload after decompression, as consumed by the serialization layer. |
| **Streamer** | The routine that serializes one class. Either generated from a `TStreamerInfo` or hand-written in C++. |
| **Streamer info** | A `TStreamerInfo`: the recorded member list of one version of one class. Files carry their own. |
| **Class version** | The small integer in a class's `ClassDef`, identifying which member layout was written. Not a ROOT version. |
| **Bootstrap class** | A class a reader MUST hardcode, because its streamer info does not describe what is actually written, or because streamer infos are themselves made of it. Listed in [Bootstrap classes](99-appendix/Bootstrap.md). |
| **Free segment** | A byte range in the file occupied by no **live** record. A freed span still begins with a key-shaped header; see [Free segments](01-container/FreeSegments.md). |

See [Glossary](99-appendix/Glossary.md) for the full list. RNTuple's own
vocabulary is defined in ROOT's specification for that format and is not repeated
here; `PLAN.md` §2.6 records this project's audit of it.
