# References

`TRef`, `TRefArray`, `TProcessID`, and the extra word a referenced `TObject`
carries.

A reference is ROOT's way of pointing at an object that lives in a *different*
record, possibly in a different file. It is not a byte offset. It is a pair — a
process identity and a 24-bit serial number — and resolving it means finding the
object that carries the same pair.

This is the only part of the serialization layer where reading one record is not
enough to interpret it, and the only part where a bit in `fBits` changes the
length of a fixed layout.

## 1. The extra word on a referenced `TObject`

[Buffer framing §7](Buffer.md#7-the-tobject-base) gives the `TObject` base as 10
bytes. When `kIsReferenced` is set it is **12**:

```
version:i16   fUniqueID:u32   fBits:u32   [ pidf:u16 ]
                                            ^ present iff fBits & 0x10
```

`kIsReferenced` is `BIT(4)` = `0x10` (`root/core/base/inc/TObject.h:74`). The
trailing `u16` is written at `root/core/base/src/TObject.cxx:1047-1048` and read
at `root/core/base/src/TObject.cxx:1005-1010`.

> **Nothing but the bit announces it.** The streamer info is identical either
> way, the byte count of the enclosing object absorbs the difference, and a
> reader that hardcodes 10 bytes desynchronises by two on the first referenced
> object and then reads plausible garbage. `fBits` must be inspected before the
> base's length is known.

`fUniqueID` is masked on write when the object is referenced:

| Case | Written | Cited |
|---|---|---|
| `kIsReferenced` clear | `fUniqueID` verbatim | `root/core/base/src/TObject.cxx:1029` |
| `kIsReferenced` set | `fUniqueID & 0x00FFFFFF` | `root/core/base/src/TObject.cxx:1036-1037` |

The masked-off byte is the writing session's index into its in-memory process-id
table (§5), which is meaningless in another process. The asymmetry matters
because `TRef` takes the *unmasked* branch — see §3.

> Demonstrated by `serialization/references`: the `TObjString` at 517 has `fBits`
> `0x00000018`, so its `TObject` base runs 523–535 and ends with `00 00`, and the
> counted string `a` starts at 535 rather than 533.

## 2. `pidf` and the `TProcessID` records

`pidf` is an index into the **file's own key namespace**. The process id it
denotes is the record keyed `ProcessID<pidf>` in the file's top-level directory
— `%d`, with no zero padding (`root/io/io/src/TFile.cxx:2016-2018`, written at
`root/io/io/src/TFile.cxx:3476-3477`).

```
process id for a reference = pidf + the record's key fPidOffset
```

`fPidOffset` is normally 0. It is non-zero only for a key copied verbatim from
another file, and it is packed into the top 16 bits of a large key's `fSeekPdir`
— see [Record §3.6](../01-container/Record.md#36-fseekpdir-and-the-packed-fpidoffset).
It is added at every site that reads a `pidf`
(`root/core/base/src/TObject.cxx:1009`, `root/core/base/src/TRef.cxx:502`,
`root/core/cont/src/TRefArray.cxx:530`).

`pidf` is a `UShort_t`, so a file holds at most 65536 process ids; ROOT warns at
65534 and aborts beyond (`root/core/base/src/TProcessID.cxx:119-125`).

### 2.1 The `TProcessID` record

**Every data member of `TProcessID` is transient or static**
(`root/core/base/inc/TProcessID.h:81-89`), so the payload is exactly a `TNamed`.
Class version 1 (`root/core/base/inc/TProcessID.h:118`), streamer-info-driven,
byte-counted.

| Offset | Field | Type | Value |
|---|---|---|---|
| 0 | byte count | `u32` | `kByteCountMask \| 66` |
| 4 | version | `i16` | 1 |
| 6 | `TNamed` base | nested record | byte count, version 1, `TObject`, name, title |

| `TNamed` field | Meaning |
|---|---|
| `fName` | `ProcessID<n>` as the **originating** file named it |
| `fTitle` | the process UUID, 36 ASCII characters |

Two traps:

- **`fName` is not authoritative.** `WriteTObject(pid, name)` names the *key*,
  not the object (`root/io/io/src/TFile.cxx:3477`), so after a file-to-file copy
  the payload can say `ProcessID3` in a record keyed `ProcessID0`. Only the key
  name indexes `pidf`.
- **`fUniqueID` of the `TProcessID` is not the `pidf`.** It is the writer's
  session-local table index (`root/core/base/src/TProcessID.cxx:142`). Ignore it.

The **UUID in `fTitle` is the only stable identity**, and it is also the key's
title, so a reader can obtain it without decompressing anything.

> Demonstrated by `serialization/references`: the record keyed `ProcessID0` has
> key title `5cad9593-b110-11f1-9a7a-b10c080abeef` and a payload of 70 bytes that
> is nothing but a `TNamed`, with `fUniqueID` and `fBits` both zero.

### 2.2 The record precedes what needs it

`TFile::WriteProcessID` appends the record the first time a reference is written
(`root/io/io/src/TFile.cxx:3468-3482`), so `ProcessID0` sits *before* the object
whose `pidf` names it. A reader MUST NOT assume references are resolvable in one
forward pass of the record chain; resolve them against the key list instead.

There is no count of process ids in the file header. ROOT recovers it by walking
the key list and counting keys whose class name is `TProcessID`
(`root/io/io/src/TFile.cxx:946-953`).

> A null `TRef` is enough to create a `ProcessID0` record:
> `TRef::Streamer` calls `WriteProcessID` unconditionally
> (`root/core/base/src/TRef.cxx:524`) and `TFile::WriteProcessID` substitutes the
> session's process id for a null argument (`root/io/io/src/TFile.cxx:3464-3465`).

## 3. `TRef`

> **`TRef` writes no byte count and no version word of its own.**

```
version:i16   fUniqueID:u32   fBits:u32   pidf:u16
```

Twelve bytes, fixed. The version word is `TObject`'s, written by the embedded
`TObject::Streamer` call (`root/core/base/src/TRef.cxx:489`), even though `TRef`
itself has a `ClassDef` version of 1 (`root/core/base/inc/TRef.h:64`). A reader
that expects a byte count, or that reads the version word as `TRef`'s, is wrong
about both.

The three fields:

- **`fUniqueID`** is the referenced object's id. A `TRef` is not itself
  referenced, so `kIsReferenced` is clear in *its* `fBits`, so `TObject::Streamer`
  takes the **unmasked** branch (`root/core/base/src/TObject.cxx:1029`) and the
  writing session's process-table index reaches the disk in the top byte.

  > **A reader MUST apply `& 0x00FFFFFF`.** The referenced object's own
  > `fUniqueID` *is* masked, so the two do not compare equal byte-for-byte
  > whenever the writing session held more than one process id. ROOT's own
  > masking is at `root/core/base/src/TProcessID.cxx:333`.

- **`fBits`** of the `TRef` carries `kHasUUID` (`BIT(5)`) and, in bits 16–23, a
  `TExec` index for action-on-demand (`root/core/base/src/TRef.cxx:436`).
- **`pidf`** resolves as §2.

### 3.1 The `kHasUUID` variant

If `fBits & 0x20` is set, the trailing `u16` is replaced by a **`TString`** —
a bare counted string holding a UUID (`root/core/base/src/TRef.cxx:490-499` read,
`root/core/base/src/TRef.cxx:517-522` write). The member's length is then
variable, and a reader MUST branch on the bit.

> Demonstrated by `serialization/references`: the `TRef` record's payload is 12
> bytes beginning at 571 with `00 01`, a version word — the following record's
> key starts at 583.

## 4. `TRefArray`

Unlike `TRef`, this one is framed: byte count and version word
(`root/core/cont/src/TRefArray.cxx:545`, `root/core/cont/src/TRefArray.cxx:562`).
Class version 1 (`root/core/cont/inc/TRefArray.h:104`), hand-written streamer.

| Offset | Field | Type | Notes |
|---|---|---|---|
| 0 | byte count | `u32` | |
| 4 | version | `i16` | 1 |
| 6 | `TObject` base | 10 or 12 | 12 if the array is itself referenced |
| … | `fName` | counted string | `TCollection::fName` |
| … | `nobjects` | `i32` | `GetAbsLast() + 1`, not the capacity |
| … | `fLowerBound` | `i32` | |
| … | `pidf` | `u16` | **one for the whole array** |
| … | `fUIDs` | `nobjects` × `u32` | |

`TSeqCollection` and `TCollection` are **not** streamed as base classes; only
`TObject` and then `fName` by hand
(`root/core/cont/src/TRefArray.cxx:546-556`). Every entry shares the one `pidf`,
so a `TRefArray` cannot span processes.

> **`fUIDs` has the same masking defect as `TRef`.**
> `TRefArray::GetObjectUID` stores the object's `fUniqueID` unmasked when the
> object was already referenced (`root/core/cont/src/TRefArray.cxx:216`) and
> masked when it assigns a fresh id (`root/core/cont/src/TRefArray.cxx:237`). A
> reader MUST apply `& 0x00FFFFFF` to every entry.

> Demonstrated by `serialization/references`: 27 payload bytes at 658, with an
> empty `fName` at 674, `nobjects` 1, and a single `pidf` at 683 ahead of the one
> `fUIDs` entry.

## 5. What `fUniqueID` means

In memory:

```
 31      24 23                        0
+----------+---------------------------+
| pid idx  |  serial, 1 .. 0xFFFFFF     |
+----------+---------------------------+
```

The serial comes from a per-session counter, and the top byte is the session's
index into its own process-id table, or `0xFF` as an escape when there are more
than 254 (`root/core/base/src/TProcessID.cxx:176-184`).

**Neither of those is what a file means.** On disk the top byte is either zeroed
(a referenced object, §1) or a stale session artefact (a `TRef`, §3), and the
process is named by `pidf`, which is a *file* index. A reader should therefore:

1. take the serial as `fUniqueID & 0x00FFFFFF`;
2. take the process from `pidf + fPidOffset`, never from `fUniqueID`;
3. never compare two `fUniqueID` words directly.

ROOT's own comment at `root/core/base/src/TRef.cxx:75` — "the pidf is stored in
the bits 24->31 of the fUniqueID of the TRef" — describes the in-memory encoding.
Read as a statement about the file it is wrong, and it is the most likely source
of a reader bug.

A session that exhausts the 24-bit serial space allocates a **new** `TProcessID`
and resets the counter (`root/core/base/src/TProcessID.cxx:164-174`), so more
than one `ProcessID<n>` record in a file does not imply more than one session.

## 6. Resolving a reference

The process half is self-contained; the object half is not.

**In the file:** `pidf` → key `ProcessID<pidf>` → the UUID in its title. The
serial is in the bytes. Together they name "object *N* in process *P*"
unambiguously.

**Not in the file:** where object *N* lives. A `TRef` stores no seek, no key
name, no branch name. ROOT resolves it only because reading the target object
registered it in an in-memory table keyed by id
(`root/core/base/src/TObject.cxx:1018`), which `TRef::GetObject` then looks up
(`root/core/base/src/TRef.cxx:392`). A third-party reader must build the same
index itself by scanning every record's `TObject` header, and the target is
explicitly permitted to be in another file.

Inside a `TTree` there is a shortcut: `TRefTable`, carried in the `TBranchRef`
baskets, maps a serial to the branch that holds it, and records the process UUIDs
it used in a persistent `fProcessGUIDs` (`root/core/cont/inc/TRefTable.h:49`).
Outside a `TTree` there is nothing.

## 7. Reading

At an object's `TObject` base:

1. Read the version word, `fUniqueID` and `fBits`.
2. If `fBits & 0x10`, read a further `u16` `pidf`. Otherwise the base is over.
3. The object's reference identity is
   `(process(pidf + fPidOffset), fUniqueID & 0x00FFFFFF)`.

At a `TRef` member (type code 61, class `TRef`):

1. Read 12 bytes as `version:i16 fUniqueID:u32 fBits:u32`, then either a `u16`
   `pidf` or, if `fBits & 0x20`, a counted string.
2. There is no byte count to resynchronise on. Getting this wrong is
   unrecoverable until the enclosing object ends.
3. The reference is `(process(pidf + fPidOffset), fUniqueID & 0x00FFFFFF)`.

To turn `pidf` into a process:

1. Add the enclosing record's key `fPidOffset`.
2. Look up the key named `ProcessID<that>` in the file's top-level directory.
3. The process UUID is that key's title.

## 8. Invariants

1. A `TObject` base with `fBits & 0x10` occupies 12 bytes; one without occupies
   10. This is checked indirectly, through the byte count of the enclosing
   object ([Streamer-driven reading §10](StreamerDriven.md#10-invariants)):
   getting the length wrong desynchronises everything after it.
2. Every `pidf` appearing in a file, plus its record's `fPidOffset`, names a key
   `ProcessID<n>` that exists in that file's top-level directory.
3. Every `TProcessID` record's payload is a `TNamed` whose `fTitle` is 36
   characters, and that `fTitle` equals the key's title.
4. No two `TProcessID` records in one file have the same `fTitle`.
5. A `TRefArray`'s payload length is
   `10 or 12 + |fName| + 1 + 4 + 4 + 2 + 4 × nobjects`, and `nobjects` is not
   negative.
6. The `fUniqueID` of an object whose `fBits & 0x10` is set has a zero top byte.
7. A `TRef` payload is exactly 12 bytes, unless its `fBits` carries `kHasUUID`.

Invariant 6 holds for objects but deliberately **not** for `TRef` or for
`TRefArray::fUIDs`, which is the whole point of §3 and §4.

## 9. Errata

Against `root/io/doc/TFile/*.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | `tobject.md`, `tref.md`: `fBits` `0x01000000` (on heap) and `0x02000000` (not deleted) are listed as values seen on disk | Both are stripped on write since 6.30 (`root/core/base/src/TObject.cxx:1033`). `serialization/references` has `fBits` `0x00000018` on the referenced object and `0x00000000` on the `TRef` |
| 2 | `tref.md`: "`fUniqueID` in the `TRef` object matches `fUniqueID` in the referenced object" | False whenever the writing session held more than one process id: the object's is masked to 24 bits and the `TRef`'s is not (§3). A reader that compares them directly loses the reference |
| 3 | `trefarray.md`: "if non-zero, it matches the Unique ID in the referenced object" | Same defect, in `fUIDs` (§4) |
| 4 | `tref.md`: describes only the `pidf` form | The `kHasUUID` form replaces the trailing `u16` with a counted string, changing the member's length (§3.1). Nothing mentions it, nor the `TExec` index in bits 16–23 |
| 5 | `tref.md`: "Version = Version of TObject Class (base class of TRef)" | Correct as far as it goes, but does not say the consequence: `TRef` emits **no** byte count and **no** version word of its own, so it is 12 bytes with no resynchronisation point (§3) |
| 6 | `tprocessid.md`: the payload `fName` is "'ProcessID' concatenated with a decimal integer", implicitly the key name | The payload name is the *originating* file's, and only the key name indexes `pidf` (§2.1) |
| 7 | `tprocessid.md`: "The TProcessID object is not itself referenced" | True, but it omits that the embedded `fUniqueID` is nonetheless usually non-zero — it is the writer's session index (§2.1) |
| 8 | `README.md`: "A ROOT file contains zero or more `TProcessID` records", implying one exists only if something is referenced | A null `TRef` is enough (§2.2) |
| 9 | — | Nothing states that `pidf` must have the record's `fPidOffset` added, or that `fPidOffset` exists at all (§2) |
| 10 | — | Nothing states that `kIsReferenced` changes the length of the `TObject` base, which is the single most damaging omission here (§1) |

## 10. Reference files

| Case | Exercises |
|---|---|
| `serialization/references` | A `TProcessID` record, a referenced `TObject` with a `pidf`, a `TRef`, and a `TRefArray` |

No fixture covers a non-zero `pidf`, a non-zero `fPidOffset`, the `kHasUUID`
form of `TRef`, a `TExec` index, or a `fUniqueID` whose top byte survives to
disk. The last three all need state from a second ROOT session or a second file,
which a single generator macro cannot produce.
