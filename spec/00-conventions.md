# Conventions

Preliminaries adopted once, so that every other document in `spec/` can be terse.
Read this first.

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

They are used with a specific scope:

- Applied to a **reader**, they describe what an implementation must do to read
  files ROOT writes.
- Applied to a **file**, they describe an invariant ROOT's own output satisfies.
  A reader MAY check these and reject files that violate them, but SHOULD prefer
  to be tolerant unless the violation makes the data ambiguous — real files in the
  wild were written by a long tail of ROOT versions, some with known bugs.

Writing is not specified as an algorithm. Each layer instead ends with an
`Invariants` section listing what a conforming file satisfies, so that a writer can
validate its own output without this specification prescribing ROOT's incidental
choices. See `PLAN.md` §2.8.

## 3. Byte order

> **ROOT uses two different byte orders in the same file.**

| Layer | Byte order |
|---|---|
| File header, `TKey`, directory records, free list | **big-endian** |
| Everything serialized through `TBuffer` — i.e. all object data | **big-endian** |
| RNTuple envelopes and page payloads | **little-endian** |
| The `ROOT::RNTuple` anchor, because it is an ordinary `TKey` payload | **big-endian** |

Big-endian is unconditional and independent of the host: it is applied by the
`tobuf`/`frombuf` helpers in `root/core/base/inc/Bytes.h`, which byte-swap on
little-endian hosts. A reader MUST NOT assume host order anywhere.

Unless a document says otherwise, every integer in `spec/01-container/`,
`spec/02-serialization/`, `spec/03-classes/` and `spec/04-ttree/` is big-endian.
`spec/05-rntuple/` states its own rules.

## 4. Primitive types

Widths are on-disk widths. Where the on-disk width differs from the in-memory
width, that is called out — this is a live source of bugs.

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
reversed**; there is no conversion step and no assertion of a format anywhere in
`root/core/base/inc/Bytes.h`. On every platform ROOT supports that pattern is IEEE
754, so the on-disk form is IEEE 754 big-endian in practice — but it is an implicit
property of the host, not something the format enforces.

Two traps around `Long_t`:

- Scalar `ULong_t` is written through the **signed** helper
  (`root/io/io/inc/TBufferFile.h:339`), so on a platform where `long` is 4 bytes a
  value ≥ 2³¹ is written with `0xFFFFFFFF` in the high four bytes rather than
  zeros. Arrays of `ULong_t` zero-extend instead. On 64-bit hosts the two agree.
- Files written by ROOT older than 3.00/06 stored `Long_t` at the host's `sizeof(long)`
  rather than always 8. Readers handling such files must branch on the file version
  (`root/io/io/src/TBufferFile.cxx:173-181`).

`Double32_t` and `Float16_t` are **not** primitive types with fixed widths. They are
`Double_t`/`Float_t` in memory and a configurable number of bits on disk, controlled
by an annotation in the member's comment. See `04-ttree/Double32.md`.

## 5. String encodings

ROOT uses several distinct string encodings and they are routinely confused.
Every document MUST name which one it means, using the terms defined here.

### 5.1 Counted string

One length byte, then that many bytes. If the length is 255, a 4-byte big-endian
length follows the 255 and then that many bytes.

```
short form (n <= 254):   n:u8   payload:n bytes
long form  (n >= 255):   255:u8   n:u32   payload:n bytes
```

The escape triggers at length **> 254**, so a leading `0xFF` never means "255
characters" — a 255-character string is always written in the long form. An empty
string is a single `0x00` byte. Encoding is uninterpreted bytes, not Unicode: a
reader SHOULD NOT assume UTF-8.

Used by `TString` and by the `TKey` name, title and class-name fields.

The counted string appears **bare** — with no preceding byte count and no version
word — both in a `TKey` and when a `TString` is a data member. A byte count and a
class record appear only when a `TString` is written as a standalone object through
a pointer, not by value.

> Demonstrated by `container/file-minimal`: the `TObjString` payload ends at offset
> 392 with `05 68 65 6c 6c 6f`, the bare counted string for `hello`, immediately
> after the base `TObject` and with nothing in between.

### 5.2 Null-terminated string

Bytes up to and including a `0x00` terminator. Used **only** for the class name in a
`kNewClassTag` record. See [Buffer framing](02-serialization/Buffer.md#51-a-new-class).

### 5.3 `std::string`

A counted string (§5.1) **wrapped in a byte count and a version word**, unlike a
`TString` member, which has neither:

```
byteCount:u32 (| 0x40000000)   version:i16   counted string
```

An empty `std::string` member is therefore 7 bytes, not 1. Details, including which
class the version word actually refers to, are in
`02-serialization/Collections.md`.

### 5.4 `char*` members

A 4-byte signed length, then exactly that many bytes, with **no terminator and no
255 escape**:

```
n:i32   payload:n bytes
```

This is not the counted string of §5.1, and the difference is a live source of
bugs. A null pointer and an empty string are indistinguishable: both are four zero
bytes. See `02-serialization/ElementTypes.md`, type code 7 (`kCharStar`).

Note the related trap on the writing side: a hand-written streamer using
`buf << someCharPointer` produces the **null-terminated** form of §5.2, not this
one.

## 6. Notation

### 6.1 Bit diagrams

Fixed-layout records use the diagram style of the RNTuple specification, so the two
halves of this repository read alike. Bit 0 is the most significant bit of the first
byte, matching the big-endian byte order:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          fNbytes                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          fVersion             |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+          fObjLen              +
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
that document exists, so that it is navigable in the published site and checked by
the build:

```markdown
See [Buffer](../02-serialization/Buffer.md) for the byte-count encoding.
```

A reference to a document that has **not been written yet** is written as inline
code instead, because the site build treats a link to a missing page as an error:

```markdown
See [Buffer framing](02-serialization/Buffer.md) for the byte-count encoding.
```

Such a reference MUST be converted to a link when its target is written. Forward
references in inline code are therefore also the working list of what is still
missing.

### 6.6 Generated content

Blocks between these markers are produced by `tools/gen_tables.py` from the pinned
submodule and MUST NOT be hand-edited; CI fails when they are stale:

```
<!-- BEGIN GENERATED: <what> -->
<!-- END GENERATED -->
```

Notes that need human judgement go in the sibling `<class>.notes.yaml`, which the
generator merges in, so they survive regeneration. Everything outside the markers
is hand-written.

## 7. Citing the reference implementation

Claims are cited as a path relative to the repository root plus a line number, and
always refer to the pinned submodule commit:

> `root/io/io/src/TBufferFile.cxx:2751`

Citations are **checked**, not merely promised. `tools/check_citations.py` verifies
that every cited file exists in the pinned submodule and that every cited line
number is within that file, and CI fails otherwise. `tools/check_pin.py` separately
asserts that the commit the published site links to is the commit the submodule is
pinned at.

What is *not* checked is whether the cited lines still contain what the citing
sentence claims. Line numbers drift when the submodule is bumped even where the
file and length remain valid, so treat a citation whose content has moved as a bug
report.

In the published site these citations render as links into root-project/root at the
pinned commit, via `tools/rootcite.py`.

Where a fixture demonstrates a claim, it is cited by case ID:

> Demonstrated by `container/file-minimal`.

## 8. Reference files

`data/` holds small ROOT files generated by the macros in `gen/cases/`. Each case
has a `case.toml` giving its record layout and a list of byte-level assertions.
Those assertions are checkable with `tools/check_bytes.py`, which needs only Python
— no ROOT, and no third-party packages — so a third-party implementation can use
them directly as test vectors.

```sh
tools/generate.py --check     # verify fixtures against case.toml
tools/generate.py             # regenerate from gen/cases (needs ROOT)
```

Files cannot be reproduced byte-for-byte, because `TKey::fDatime` records the wall
clock and each file gets a fresh `TUUID`. `tools/normalize.py` masks those before
digesting, so `data/MANIFEST.sha256` detects genuine format changes but not the
passage of time.

## 9. Terminology

| Term | Meaning |
|---|---|
| **Record** | A `TKey` plus its payload, at one offset in the file. The unit the file is a sequence of. |
| **Key** | The fixed part of a record, describing where and what the payload is. |
| **Payload** | The bytes of a record after the key. Possibly compressed. |
| **Object data** | A payload after decompression, as consumed by the serialization layer. |
| **Streamer** | The routine that serializes one class. Either generated from a `TStreamerInfo` or hand-written in C++. |
| **Streamer info** | A `TStreamerInfo`: the recorded member list of one version of one class. Files carry their own. |
| **Class version** | The small integer in a class's `ClassDef`, identifying which member layout was written. Not a ROOT version. |
| **Bootstrap class** | A class a reader MUST hardcode, because its streamer info does not describe what is actually written. Listed in `99-appendix/Bootstrap.md`. |
| **Free segment** | A byte range in the file not occupied by any record. |

See `99-appendix/Glossary.md` for the full list, including RNTuple terms.
