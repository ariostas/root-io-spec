# Records and keys

A ROOT file is a sequence of **records**. Each record is a `TKey` — a
self-describing header — followed by a payload. This document specifies the key
layout and how a reader walks from one record to the next.

Prerequisites: [Conventions](../00-conventions.md), [File header](FileHeader.md).
All integers are big-endian.

## 1. The record chain

Records begin at `fBEGIN` and run to `fEND`. They are contiguous but not
ordered: a record's position carries no meaning, and the only way to find a
specific object is through a directory's key list
(`spec/01-container/Directory.md`) or through an offset in the file header.

To walk the chain, read a 4-byte signed integer at the current offset:

| Value | Meaning | Advance by |
|---|---|---|
| `> 0` | A record. This is `fNbytes`, its total length including the key. | `fNbytes` |
| `< 0` | **Not a record.** A free span of `-value` bytes. | `-value` |
| `0` | Corrupt. Stop. | — |

> **A negative value is not an error condition.** It marks a span that has been
> freed — most often by deleting or overwriting an object — and a reader walking
> the chain MUST skip it rather than attempt to parse a key there. See
> `01-container/FreeSegments.md`. Demonstrated by `container/gap`, which has a
> `-187` span at offset 718 where a deleted record used to be.

## 2. Key layout

Two layouts, selected by the key's own `fVersion`:

- **small key**, `fVersion <= 1000`: `fSeekKey` and `fSeekPdir` are 4 bytes;
- **large key**, `fVersion > 1000`: both are 8 bytes.

The comparison is strictly greater-than
(`root/io/io/src/TKey.cxx:660`, `:1269`, `:1397`, `:1456`).

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           fNbytes                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          fVersion             |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+           fObjlen             +
|                               |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           fDatime                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          fKeylen              |            fCycle             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     fSeekKey (4 or 8 bytes)                   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    fSeekPdir (4 or 8 bytes)                   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  fClassName, fName, fTitle: three counted strings              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Type | Small offset | Large offset |
|---|---|---|---|
| `fNbytes` | `i32` | 0 | 0 |
| `fVersion` | `i16` | 4 | 4 |
| `fObjlen` | `i32` | 6 | 6 |
| `fDatime` | `u32` | 10 | 10 |
| `fKeylen` | `i16` | 14 | 14 |
| `fCycle` | `i16` | 16 | 16 |
| `fSeekKey` | `i32` / `i64` | 18 | 18 |
| `fSeekPdir` | `i32` / `i64` | 22 | 26 |
| `fClassName` | counted string | 26 | 34 |
| `fName` | counted string | — | — |
| `fTitle` | counted string | — | — |

The fixed part is 26 bytes (small) or 34 (large). The three strings are
**counted strings** as defined in [Conventions §5.1](../00-conventions.md#51-counted-string),
appearing bare with no byte count or version word.

Written by `root/io/io/src/TKey.cxx:647-684` (`FillBuffer`) and
`root/io/io/src/TKey.cxx:1444-1480` (`Streamer`), which produce identical bytes.

## 3. Fields

### 3.1 `fNbytes`

The **total length of the record, key included**. The payload therefore occupies
`fNbytes - fKeylen` bytes starting at `fSeekKey + fKeylen`.

A negative value at a record position is not a key at all; see §1.

### 3.2 `fObjlen`

The length of the payload **after decompression**, key excluded. Comparing it
with `fNbytes - fKeylen` is how a reader decides whether the payload is
compressed; see [Compression §1](Compression.md#1-deciding-whether-a-payload-is-compressed).

### 3.3 `fKeylen`

The length of the key itself, so the payload begins at `fSeekKey + fKeylen`.

It is **signed 16-bit**, capping a key header at 32767 bytes. ROOT does not check
for overflow when building a key, only when reading one back
(`root/io/io/src/TKey.cxx:1248-1253`).

For a `TBasket`, `fKeylen` covers the basket-specific fields streamed *after* the
ten fields above, not just the key (`root/tree/tree/src/TBasket.cxx:89`). See
`04-ttree/TBasket.md`.

### 3.4 `fVersion`

The `TKey` class version, plus 1000 for the large layout. In 6.40.04 the only
values written are **4** and **1004**.

| Value | ROOT | Meaning |
|---|---|---|
| 1 | 1.x – 2.x | No object-map registration for the payload; see §7 |
| 2 | 3.x | |
| 3 | 4.00+ | 64-bit offsets in memory |
| 4 | 5.08+ | `fPidOffset` packed into `fSeekPdir`; see §3.6 |
| 1002, 1003, 1004 | | the same, large layout |

### 3.5 `fSeekKey`

The absolute offset of **this key itself** — that is, of its own `fNbytes` word.
It is redundant with the position the reader is already at, which makes it a
useful corruption check.

ROOT itself does **not** verify it in `TKey`; the only place a comparable check
exists is `TBranch::GetBasket` (`root/tree/tree/src/TBranch.cxx:1268`). A reader
SHOULD check `fSeekKey` against the offset it read the key from and treat a
mismatch as corruption.

### 3.6 `fSeekPdir`, and the packed `fPidOffset`

The absolute offset of the **containing directory's own record** — never of that
directory's key list.

> **In a large key, the top 16 bits of the `fSeekPdir` word are not address
> bits.** They hold `fPidOffset`, a `TProcessID` table offset
> (`root/io/io/src/TKey.cxx:670`, `:1281-1282`). A reader MUST mask:
>
> ```
> fSeekPdir  = word & 0x0000FFFFFFFFFFFF
> fPidOffset = (word >> 48) & 0xFFFF
> ```
>
> Masking is always safe, since no file approaches 2⁴⁸ bytes. A non-zero
> `fPidOffset` also *forces* the large layout, because there is nowhere to put it
> otherwise (`root/io/io/src/TKey.cxx:696-704`). See
> `02-serialization/References.md`.

What it points at:

| Key | `fSeekPdir` |
|---|---|
| Object in the root directory | `fBEGIN`, normally 100 |
| Object in a subdirectory | that subdirectory's record offset |
| A subdirectory's own key | the *parent* directory's record offset |
| **The root directory's own key** | **0** |
| StreamerInfo, free list | `fBEGIN` |
| A directory's key-list record | that directory's record offset |

Zero is valid **only** for the top-level record, where it arises because the
file's `fSeekDir` is still unset when that key is created. Everywhere else ROOT
rejects a value below 64 or beyond the file size
(`root/io/io/src/TDirectoryFile.cxx:1460-1465`).

> Demonstrated by `container/directories`: the root key has `fSeekPdir = 0`;
> top-level keys have 100; keys inside `alpha` have 401, which is `alpha`'s own
> record offset; keys inside `alpha/beta` have 610.

### 3.7 `fDatime`

Local wall-clock time when the key was created, packed into 32 bits
(`root/core/base/src/TDatime.cxx:392`):

```
fDatime = (year - 1995) << 26 | month << 22 | day << 17
        | hour << 12 | minute << 6 | second
```

| Field | Bits | Width | Range |
|---|---|---|---|
| year − 1995 | 31-26 | 6 | 0-63 |
| month | 25-22 | 4 | 1-12 |
| day | 21-17 | 5 | 1-31 |
| hour | 16-12 | 5 | 0-23 |
| minute | 11-6 | 6 | 0-59 |
| second | 5-0 | 6 | 0-59 |

Three properties a reader must not assume away:

- **The epoch is 1995 and the year field is 6 bits**, so representable dates run
  1995-01-01 to 2058-12-31.
- **Out-of-range years wrap silently.** ROOT applies no validation on the paths
  that actually write keys; the shift truncates to the low 6 bits
  (`root/core/base/src/TDatime.cxx:311`, `:347`). A clock set to 2059 records as
  1995.
- **It is local time with no zone information** and is therefore not portable
  between timezones (`root/core/base/src/TDatime.cxx:19-24`).

In reproducible mode the value written is the encoding of local time 1 rather
than zero (`root/io/io/src/TKey.cxx:654-655`), which is itself timezone
dependent — so "reproducible" files are only byte-identical within one timezone.

### 3.8 `fCycle`

Which version of a name this record holds; see §4.

> **`fCycle` may be negative on disk.** A negative value marks the key as "keep",
> exempting it from purging; the cycle is its magnitude
> (`root/io/io/src/TKey.cxx:623-626`, `:731-734`). A reader MUST take the absolute
> value, and MAY expose the sign as a keep flag.

It is signed 16-bit, so the maximum cycle is 32767. ROOT does not check for
overflow when assigning cycles.

### 3.9 `fClassName`

The class of the payload object — with one substitution:

> **A directory key stores the class name `"TDirectory"`, never
> `"TDirectoryFile"`.** The substitution happens on write
> (`root/io/io/src/TKey.cxx:676-681`) and is reversed on read
> (`root/io/io/src/TKey.cxx:1288-1293`), for compatibility with ROOT versions
> predating the rename. A reader MUST treat on-disk `"TDirectory"` as
> `TDirectoryFile`.

For a key-list or free-list record, `fClassName` is the *containing directory's*
class. That is `"TFile"` for the root directory — or the name of a `TFile`
subclass such as `TMemFile` — and `"TDirectory"` for a subdirectory. It is
therefore not a reliable way to identify those records; see
`01-container/Directory.md`.

> Demonstrated by `container/directories`: `alpha`'s directory key carries
> class name `"TDirectory"` with length byte 10, and three distinct records carry
> the class name `"TFile"`.

### 3.10 `fTitle`

Truncated to `kTitleMax = 32000` characters when the key is built
(`root/io/io/src/TKey.cxx:71`, `:459`), before `fKeylen` is computed, so the
truncation is reflected in `fKeylen`. No truncation is applied on read.

## 4. Cycles

Writing an object under a name that already exists in a directory does not
replace the old record. It appends a new one with the next cycle number, and
both remain in the file until purged.

Cycles start at 1 and increment: the new key's cycle is the highest existing
cycle plus one (`root/io/io/src/TDirectoryFile.cxx:245-254`). A record is
addressed as `name;cycle`.

Resolution rules, which differ between ROOT's two lookup paths:

| Request | `TDirectoryFile::Get` | `TDirectoryFile::GetKey` |
|---|---|---|
| `name` with no cycle | highest cycle | highest cycle |
| `name;N` | **exact match** on N | highest cycle **≤ N** |

(`root/io/io/src/TDirectoryFile.cxx:1002` and `:1167`.) A reader SHOULD resolve a
bare name to the highest cycle; for an explicit cycle it SHOULD document which of
the two rules it implements, since ROOT is not self-consistent here.

Special values used when parsing a `name;cycle` string
(`root/core/base/src/TDirectory.cxx:1316-1372`): no `;` means 9999, `;*` means
10000, and a non-numeric suffix means 9999.

> Demonstrated by `container/cycles`: three records named `str` with cycles 1, 2
> and 3, all present.

## 5. Payload size limits

| Limit | Value | Source |
|---|---|---|
| `fNbytes`, `fObjlen` are signed 32-bit | < 2 GiB | `root/io/io/inc/TKey.h:42-43` |
| Buffer maximum | `0x7FFFFFFE` | `root/core/base/src/TBuffer.cxx:23` |
| **A single streamed object** | **`0x3FFFFFFE`, ~1 GiB** | `root/io/io/src/TBufferFile.cxx:53` |

The ~1 GiB limit is the practical one: every streamed object carries a 4-byte
byte count whose top bits are a tag, so the count cannot exceed `kMaxMapCount`
(`root/io/io/src/TBufferFile.cxx:351-354`). ROOT neither checks this when
building a key nor splits the object; it reports an error and writes a corrupt
byte count.

RNTuple's splitting of payloads across several keys is **self-imposed**, not a
`TKey` rule: its default maximum key size is 1 GiB, recorded in the RNTuple
anchor and enforced in `root/tree/ntuple/src/RMiniFile.cxx:1427-1490`. RNTuple
blobs are raw byte payloads and so are not subject to the byte-count limit at
all.

## 6. Reading

1. At the current offset, read `fNbytes` as `i32`. If negative, advance by its
   magnitude and repeat. If zero, stop.
2. Read `fVersion`. If `> 1000`, use the large offsets from §2.
3. Read the remaining fixed fields; mask `fSeekPdir` per §3.6; take
   `abs(fCycle)`.
4. Read the three counted strings. Map `fClassName == "TDirectory"` to
   `TDirectoryFile`.
5. The payload is `fNbytes - fKeylen` bytes at `fSeekKey + fKeylen`. Decompress
   per [Compression](Compression.md) if it differs from `fObjlen`.
6. Advance by `fNbytes`.

## 7. Version history

| Since | Change |
|---|---|
| 3.05 | The `fVersion > 1000` large layout exists at all |
| 4.00 | Key version 3 |
| 5.08 | Key version 4: `fPidOffset` packed into `fSeekPdir` (§3.6) |

For a key with `fVersion == 1` — ROOT 1.x and 2.x — the payload was written
without object-map registration, so back-references and class tags behave
differently (`root/io/io/src/TKey.cxx:868`, `:1174`). See
`02-serialization/Buffer.md`.

`TBasket` keys are **always** written in the large layout
(`root/tree/tree/src/TBasket.cxx:71`), regardless of file size. Since baskets are
the most numerous keys in a typical file, a reader that only implements the small
layout will fail on nearly every `TTree`.

Apart from the large layout, the fixed part of the key has not changed since
3.02.06.

## 8. Invariants

1. `fSeekKey` equals the offset at which the key was read.
2. `fNbytes >= fKeylen`, and both are positive.
3. `fKeylen` equals the actual length of the key: 26 or 34 plus the three counted
   strings, with the `"TDirectory"` substitution applied.
4. `fSeekKey + fNbytes <= fEND`.
5. `fObjlen >= 0` and `fKeylen <= INT_MAX - fObjlen`
   (`root/io/io/src/TKey.cxx:84-93`).
6. `fSeekPdir`, after masking, is either 0 — only for the top-level record — or
   the offset of a record that parses as a directory.
7. `fVersion` is one of 1, 2, 3, 4, 1002, 1003, 1004.
8. Consecutive records and free spans tile `[fBEGIN, fEND)` exactly, with no
   overlap and no unaccounted bytes.
9. Within one directory, no two keys share both a name and a cycle magnitude.

ROOT's own checks are at `root/io/io/src/TKey.cxx:1227-1297`. Note an asymmetry
worth knowing: the `Streamer` read path performs the same checks *except*
`fNbytes >= fKeylen`, which only `ReadKeyBuffer` enforces
(`root/io/io/src/TKey.cxx:1390-1443`).

## 9. Errata

| # | Claim | Actually |
|---|---|---|
| 1 | `root/io/doc/TFile/datarecord.md` and `keyslist.md` place `SeekKey` at 18-21 and `SeekPdir` at 22-25 | Both are 8 bytes, at 18 and 26, whenever `fVersion > 1000`, shifting everything after. Neither document mentions the variant (§2) |
| 2 | Both describe the string length as "number of bytes in the class name", one byte | Counted strings escape to a 4-byte length above 254 characters, and titles may be up to 32000 ([Conventions §5.1](../00-conventions.md#51-counted-string)) |
| 3 | Neither mentions `fPidOffset` | The top 16 bits of a large key's `fSeekPdir` are not address bits (§3.6) |
| 4 | `datarecord.md` describes records only | A negative `fNbytes` is a free span, not a record. A sequential reader built from that page fails on any file that has had a key deleted (§1) |
| 5 | `datarecord.md`: `fSeekPdir` is "pointer to the directory supporting this object" | It is 0 for the top-level record (§3.6) |
| 6 | Neither mentions the `"TDirectory"` substitution for `TDirectoryFile` | §3.9 |
| 7 | Neither states that `fCycle` may be negative | A negative cycle means "keep"; read the magnitude (§3.8) |
| 8 | The `fDatime` formula is given without qualification | The year field is 6 bits, valid 1995-2058, wrapping silently; and it is local time with no zone (§3.7) |
| 9 | `keyslist.md`: the class name is "'TFile' or 'TDirectory'", length 5 or 10 | It is the containing directory's class, so any `TFile` subclass name can appear (§3.9) |
| 10 | Neither states any payload size ceiling | ~1 GiB for a single streamed object (§5) |
| 11 | `datarecord.md` names the members `fObjLen` and `fKeyLen` | They are `fObjlen` and `fKeylen` — relevant when grepping the source |

One inconsistency inside ROOT itself: `TKey` tests `fVersion > 1000` everywhere,
while RNTuple's independent key parser uses `>= 1000`
(`root/tree/ntuple/src/RMiniFile.cxx:203`). The two disagree only for
`fVersion == 1000`, which ROOT never writes, since a class version of at least 1
makes the large form 1001 or higher. Harmless, but a reader should follow
`TKey`.

## 10. Reference files

| Case | Exercises |
|---|---|
| `container/file-minimal` | A single small key; every field asserted |
| `container/cycles` | Three cycles of one name |
| `container/directories` | `fSeekPdir` chains, the `"TDirectory"` class name |
| `container/gap` | A negative `fNbytes` free span in the chain |

No fixture yet covers a large key or a non-zero `fPidOffset`. A `TBasket` fixture
will supply the former, since baskets always use the large layout.
