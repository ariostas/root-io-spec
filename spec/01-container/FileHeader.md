# File header

The first bytes of every ROOT file. It identifies the file, states which layout
variant the rest of the file uses, and locates the three structures a reader needs
before it can do anything else: the root directory, the streamer-info record, and
the free-segment list.

Prerequisites: `spec/00-conventions.md`. All integers are big-endian.

## 1. Overview

The header occupies the first `fBEGIN` bytes of the file. ROOT reserves 100 bytes
and writes only the first 63 (or 75 — see §4); the remainder is padding whose
contents are **not** specified (§7).

Two layouts exist, selected by `fVersion`:

- the **small-file layout**, used when `fVersion < 1000000`;
- the **large-file layout**, used when `fVersion >= 1000000`, in which `fEND`,
  `fSeekFree` and `fSeekInfo` are 8 bytes rather than 4.

`fBEGIN` is 4 bytes in **both** layouts, despite being a 64-bit value in memory
(`root/io/io/src/TFile.cxx:2681`). Only the three fields named above widen.

## 2. Layout

### 2.1 Small-file layout (`fVersion < 1000000`)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                      "root" (0x726F6F74)                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           fVersion                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                            fBEGIN                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                             fEND                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           fSeekFree                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          fNbytesFree                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                             nfree                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          fNbytesName                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    fUnits     |                  fCompress                    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    fSeekInfo                  |               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+  fNbytesInfo  +
|                                               |               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         TUUID version         |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+          UUID (16 bytes)      +
|                              ...                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                 padding to fBEGIN, not specified              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

> **The rows are 4 bytes wide, but the header stops being 4-byte aligned at
> `fUnits`.** `fUnits` is a single byte at offset 32, so `fCompress`, `fSeekInfo`,
> `fNbytesInfo`, the `TUUID` version word and the UUID each straddle a row
> boundary. From that point the diagram shows the order of the fields, not their
> column positions. The offsets in §2.2 are authoritative, and a reader should
> implement against them.

The large-file layout, whose offsets are in the right-hand column below, is drawn
in [Large files §2](LargeFiles.md#2-the-file-header).

### 2.2 Field offsets

| Field | Type | Small offset | Large offset | Notes |
|---|---|---|---|---|
| magic | 4 bytes | 0 | 0 | literal `root`, no terminator |
| `fVersion` | `i32` | 4 | 4 | §3 |
| `fBEGIN` | `i32` | 8 | 8 | never widens |
| `fEND` | `i32` / `i64` | 12 | 12 | **widens** |
| `fSeekFree` | `i32` / `i64` | 16 | 20 | **widens** |
| `fNbytesFree` | `i32` | 20 | 28 | |
| `nfree` | `i32` | 24 | 32 | |
| `fNbytesName` | `i32` | 28 | 36 | |
| `fUnits` | `u8` | 32 | 40 | §5.7 — informational only |
| `fCompress` | `i32` | 33 | 41 | §5.8 |
| `fSeekInfo` | `i32` / `i64` | 37 | 45 | **widens** |
| `fNbytesInfo` | `i32` | 41 | 53 | |
| TUUID version | `i16` | 45 | 57 | always 1 |
| UUID | 16 bytes | 47 | 59 | §6 |
| padding | — | 63 … `fBEGIN` | 75 … `fBEGIN` | §7 |

Written by `TFile::WriteHeader()`, `root/io/io/src/TFile.cxx:2668-2712`; parsed by
`TFile::Init()`, `root/io/io/src/TFile.cxx:714-758`.

> The table in the ROOT source at `root/io/io/src/TFile.cxx:51-66` numbers bytes
> from **1**, while `root/io/doc/TFile/header.md` and this document number from
> **0**. The offsets agree once that is accounted for.

## 3. `fVersion` and the large-file flag

`fVersion` identifies the ROOT release that wrote the file:

```
fVersion mod 1000000 = 10000 * major + 100 * minor + patch
```

so 6.40.04 writes `64004`. A value `>= 1000000` also selects the large-file
layout; subtract 1000000 to recover the release.

ROOT applies the flag in `root/io/io/src/TFile.cxx:2679`:

```cpp
if (version < 1000000 && fEND > kStartBigFile) { version += 1000000; fUnits = 8; }
```

with `kStartBigFile = 2000000000` (`root/io/io/inc/TFile.h:278`). A reader MUST
account for three consequences:

1. The test is on **`fEND` alone**, strictly greater-than. It is not, as
   `root/io/doc/TFile/header.md` claims, a test on `fEND`, `fSeekFree` or
   `fSeekInfo`. In practice this makes no difference, because both offsets are
   below `fEND`, but the documented rule is not the implemented one.
2. The flag is added to a local copy. `TFile::fVersion` in memory keeps the
   unflagged value for a file ROOT has just written, but takes the flagged value
   from disk for a file it has opened. `TFile::GetVersion()` returns whatever is
   current, unflagged or flagged.
3. `fUnits` is set to 8 as a side effect, but nothing reads it back (§5.7).

A reader MUST select the layout from `fVersion`, not from `fUnits`, as ROOT's own
parser does (`root/io/io/src/TFile.cxx:738`).

## 4. Extent

`fBEGIN` bytes are reserved. `WriteHeader()` writes 63 bytes (small) or 75 bytes
(large) and stops; see §7 for what is in between.

ROOT 6.40.04 always writes `fBEGIN = 100`, set at `root/io/io/src/TFile.cxx:204`.
The comment at `root/io/io/src/TFile.cxx:68-72` states that the value is fixed at
100 and that **bytes 96-99 are reserved and MUST be zero**, a constraint from the
file's registered media type.

A reader MUST still take `fBEGIN` from the header rather than assume 100, and
MUST NOT derive it from `fVersion` either. ROOT releases up to and including the
3.04 series used `fBEGIN = 64`, and two files in the corpora pair that 64 with an
`fVersion` of 40000, for which ROOT would have written 100. See §8.1.

## 5. Fields

### 5.1 magic

The four bytes `root`, written by `memcpy` with no terminator and no byte swapping.
A file whose first four bytes are not `root` MUST be rejected.

### 5.2 `fEND`

Offset of the first free byte at the end of the file. A writer would append
there. It is **not** necessarily the file size.

`fEND > filesize` is the only bad case: the file is truncated, and ROOT reports it
and refuses to open the file unless recovery was requested
(`root/io/io/src/TFile.cxx:881-889`).

`fEND < filesize` is not an error, nor a sign of one. ROOT compares the two only to
detect truncation; trailing bytes past `fEND` are outside the format. There are two
causes:

- **A file that was never closed.** The value on disk is whatever the last
  successful header write left. `fSeekFree == 0` proves this case, because ROOT
  writes the free list before the header when closing
  (`root/io/io/src/TFile.cxx:1024-1025`). **The converse does not hold**: a
  non-zero `fSeekFree` is not evidence of a clean close, because `TFile::Write`
  also writes the free list and then the header (`root/io/io/src/TFile.cxx:2508-2510`),
  and `TTree::AutoSave` calls it. A job that wrote a tree and then crashed leaves a
  plausible-looking header behind (§5.4).
- **A cleanly closed file with trailing bytes anyway.** `pippa.root` in the corpus
  of `PLAN.md` §9.9 (ROOT 2.24/00, `fSeekFree` 391546, so closed by that test) is
  391 645 bytes long with `fEND` 391 641, leaving four unexplained trailing bytes.
  `TFile::Open` reads it without a warning and reports `GetEND()` 391641 and
  `GetSize()` 391645.

A reader MUST NOT validate `fEND == filesize`, in either direction, and MUST NOT
take a mismatch as evidence that the file was not closed.

### 5.3 `fNbytesName`

The number of bytes, starting at `fBEGIN`, occupied by the root directory record's
key **plus a second serialized copy of its name and title** that follows the key.

Two different offsets are involved, and confusing them is a common error:

| Offset | What starts there |
|---|---|
| `fBEGIN + fKeylen` | the record's payload, beginning with the duplicated name and title |
| `fBEGIN + fNbytesName` | the `TDirectoryFile` fields proper, starting with its class version |

`fNbytesName` gives the second offset, since the duplicated name and title have
variable length. `TFile::Init()` uses it that way
(`root/io/io/src/TFile.cxx:804`).

In `container/file-minimal`: `fKeylen` is 91, the name is 32 bytes and the title 25,
each with a 1-byte length prefix, so `fNbytesName = 91 + 33 + 26 = 150`. The payload
starts at 191 and the `TDirectoryFile` fields at 250.

ROOT rejects a file where the copy of this value inside the directory record is
outside `[10, 10000]` (`root/io/io/src/TFile.cxx:841-844`).

### 5.4 `fSeekFree`, `fNbytesFree`, `nfree`

`fSeekFree` is the absolute offset of the record holding the free-segment list.

`fNbytesFree` is that record's **total size including its key**: its
`TKey::fNbytes`, not its payload length. The same applies to `fNbytesInfo`.
Reading either as a payload length is the most common off-by-a-key error in a
reimplementation.

`nfree` is the number of `TFree` entries in the list. In a file written by ROOT
it is never zero: the list always ends with a sentinel segment running to
`kStartBigFile` (`root/io/io/src/TFile.cxx:691`), so an otherwise empty file has
`nfree == 1`.

> **It is advisory, and a reader should ignore it.** ROOT writes
> `fFree->GetSize()` (`root/io/io/src/TFile.cxx:2676`), but on reading it stores
> the value in a local variable and never uses it
> (`root/io/io/src/TFile.cxx:743`, `root/io/io/src/TFile.cxx:753`). The free list
> is rebuilt by walking from `fSeekFree` instead, so a file whose `nfree` disagrees
> with its list is read correctly.
>
> Every ROOT-written file available agrees with its list: 55 files older than
> ROOT 5 in `root/roottest/` and `gen/cern/`, from 2.23/12 to 4.04/02, and every
> later one. Third-party writers do not always. The two g4tools files in the
> foreign corpus of `PLAN.md` §9.8, whose headers claim ROOT 4.00/00 (§8.1), have
> `nfree` 0 with a free list of two entries, and ROOT opens them without
> complaint. A reader that uses `nfree` as a count instead of walking the list
> gets these files wrong.

`fSeekFree == 0` marks a file whose free list was never written: one created and
abandoned before any close or `TFile::Write`. The implication runs one way only. A
file that crashed after an `AutoSave` has a non-zero `fSeekFree` and was still
never closed, so no field proves a clean close (§5.2).

ROOT's handling is limited. It reads the free list only when the file is opened
writable; the test is `fSeekFree > fBEGIN` rather than non-zero; and on failure
it prints a warning and skips the list rather than starting recovery
(`root/io/io/src/TFile.cxx:769-776`):

```
file %s probably not closed, cannot read free segments
```

Recovery is a separate decision, based on `fSeekKeys` and `fEND`
(`root/io/io/src/TFile.cxx:869`, `root/io/io/src/TFile.cxx:899`). A reader that
only reads objects never needs the free list.

### 5.5 `fSeekInfo`, `fNbytesInfo`

Absolute offset and total size (including key) of the record holding the
streamer-info list — a `TList` of `TStreamerInfo`, stored under the key name
`StreamerInfo`. See `spec/02-serialization/StreamerInfo.md`.

`fSeekInfo <= fBEGIN` means the file has no streamer-info record
(`root/io/io/src/TFile.cxx:921`). This is normal for a file containing only classes
for which ROOT writes no streamer info, and abnormal otherwise.

### 5.6 Locating the keys list

The header does **not** contain the offset of the keys list. That offset,
`fSeekKeys`, lives in the root directory record; see
[Directories and key lists](Directory.md).

> **The keys-list and free-segment records cannot be identified from their keys.**
> Both have `fClassName = "TFile"` and the file's own name and title, like the root
> directory record. `TFile::Map()` labels them `KeysList` and `FreeSegments` by
> comparing their offsets with `fSeekKeys` and `fSeekFree`, not by reading anything
> in the key. A reader MUST do the same. In `container/file-minimal`, three
> distinct records at offsets 100, 832 and 993 all have `fClassName = "TFile"` and
> the name `data/container/file-minimal.root`.

### 5.7 `fUnits`

The width in bytes of the file's offset fields: 4 in the small-file layout, 8 in the
large-file layout.

**ROOT never uses this field.** Every occurrence in `root/io/io/` is an
initialization, a write, or a read into a member that nothing consults afterwards.
A reader MUST branch on `fVersion` (§3) and MAY use `fUnits` only as a cross-check.
Where the two disagree, `fVersion` is authoritative, since it is what ROOT uses.

### 5.8 `fCompress`

The file's default compression setting:

```
fCompress = 100 * algorithm + level
```

| Algorithm | Name | Notes |
|---|---|---|
| 0 | use global default | resolved when writing, from ROOT's global setting |
| 1 | ZLIB | |
| 2 | LZMA | |
| 3 | old ROOT algorithm | pre-ZLIB, still readable |
| 4 | LZ4 | |
| 5 | ZSTD | |

Level is clamped to `[0, 99]` when set through
`ROOT::CompressionSettings()`, though only 0-9 are meaningful; 0 means no
compression. `TFile::SetCompressionSettings()` assigns the value with no validation
at all (`root/io/io/src/TFile.cxx:2391-2394`), so a reader SHOULD tolerate
out-of-range and negative values rather than reject the file.

Typical composite values are `0`, `101` (ZLIB level 1), `207` (LZMA 7), `404`
(LZ4 4) and `505` (ZSTD 5).

> This field is a default, **not** a description of the file's contents. Each record
> has its own compressed and uncompressed lengths and may use a different
> algorithm. A record's algorithm is identified by the magic bytes of its
> compression block, never by `fCompress`. See [Compression](Compression.md).

Before ROOT ~5.30, `fCompress` was a bare ZLIB level with no algorithm component.
The current decoding still works for those files: a level in 0-9 gives algorithm 0
("use global default"), which resolves to ZLIB.

## 6. UUID

A 2-byte class version, always `1`, followed by the 16-byte UUID.

The 16 bytes use the standard RFC 4122 big-endian wire layout: a 4-byte
`fTimeLow`, 2-byte `fTimeMid`, 2-byte `fTimeHiAndVersion`, 1-byte
`fClockSeqHiAndReserved`, 1-byte `fClockSeqLow`, and 6 bytes of `fNode`. They can
be read directly as a UUID and formatted conventionally.

Two properties surprise implementers:

- **ROOT never reads the header UUID.** `TFile::Init()` does not parse these bytes.
  The `TFile`'s UUID is taken from the root directory record instead
  (`root/io/io/src/TFile.cxx:823`). The two agree in practice, because both are
  written from the same value during file creation, but ROOT does not check that
  they do, so a reader MUST NOT treat agreement as guaranteed.
- In **reproducible mode**, requested via the `reproducible` URL option, the UUID
  body is 16 zero bytes while the version word remains `1`
  (`root/io/io/src/TFile.cxx:2703-2704`). A validator that requires a well-formed
  RFC 4122 UUID will reject files that are deliberately reproducible.

## 7. Padding

Bytes from the end of the last field (63 small, 75 large) to `fBEGIN`.

**The contents are not specified, and ROOT does not write them.** `WriteHeader()`
allocates an uninitialized buffer of `fBEGIN` bytes and passes only the first 63 or
75 to the write call. In a newly created file the rest is a hole, which reads back
as zero on any ordinary filesystem. This is why the media-type registration can
require bytes 96-99 to be zero (§4).

In a file opened for update, `WriteHeader()` again rewrites only the first 63 or 75
bytes, and the padding keeps its old contents. In particular, a file that once
exceeded 2 GB and later shrank below the threshold keeps the stale tail of its
large-file fields there.

A reader MUST treat the padding as "don't care" and MUST NOT rely on it being zero.

## 8. Version history

| ROOT versions | Header |
|---|---|
| ≤ 3.03/06 | `fBEGIN = 64`. No UUID: bytes 45-63 are unwritten. |
| 3.03/07 – 3.04 | `fBEGIN = 64`, UUID present. |
| ≥ 3.05 | `fBEGIN = 100`. Large-file layout exists; `fVersion >= 1000000` is possible. |
| ≥ ~5.30 | `fCompress` gains its algorithm component (§5.8). |
| ≥ 6.x | Reproducible mode possible (§6). |

The UUID boundary is set by release tags: `TFile.cxx` has no `fUUID` at
`v3-03-06` and writes one at `v3-03-07`, the same release that added the UUID to
directories ([Directory §7](Directory.md#7-version-history)).
`root/roottest/root/io/arrayobject/Event.3.2.0.root`, written by 3.03/02, has
`fBEGIN` 64 and zeros at bytes 45-63.

Field order, offsets, widths and byte order have been stable since 3.05. The
large-file layout cannot occur in a file older than 3.05, since the flag did not
exist.

### 8.1 `fBEGIN` is not derivable from `fVersion`

> The table above says what **ROOT** wrote. It is not a lookup table for
> `fBEGIN`: a reader MUST take that from the header (§4), because a third-party
> writer can pair the two fields in any way.

Across `data/` and both corpora, four files have `fBEGIN = 64`, and only two of
them were written by an old ROOT:

| File | `fBEGIN` | `fVersion` | Header UUID |
|---|---|---|---|
| `pippa.root` | 64 | 22400 (2.24/00) | none — bytes 45-63 unwritten |
| `mlpHiggs.root` | 64 | 30402 (3.04/02) | present |
| `uproot-from-geant4.root` | 64 | **40000** | 16 zero bytes |
| `uproot-issue-250.root` | 64 | **40000** | 16 zero bytes |

The first two match the table. The last two were written by g4tools, Geant4's
own writer (their directory records have `fDatimeC` 2018-10-03 and 2021-01-20).
They declare `fVersion` 40000, for which the table gives `fBEGIN` 100. A reader
that computes `fBEGIN` from `fVersion` reads their first record 36 bytes late.

ROOT accepts these files. Its only check on the field is
`fBEGIN < 0 || fBEGIN > fEND` (`root/io/io/src/TFile.cxx:760-766`); it never
compares `fBEGIN` with 100, nor with the length of the header it is about to write.
Both files open and read normally.

They are also real instances of the hazard behind invariant 11. 64 is one byte more
than the 63-byte small header and eleven bytes short of the 75-byte large one,
so pushing either file past 2 GB would write the header over its own first record
([Writing a file §13.8](../06-writing/WritingFiles.md#138-crossing-2-gb-during-an-update)).
Neither file has a UUID anywhere: the header holds zeroes, and their directory
records are version 1001, which has no UUID field
([Directories §3.1](Directory.md#31-the-version-word-carries-two-independent-things)).
This does not matter, because ROOT never reads the header UUID (§6).

## 9. Reading

A conforming reader performs the following steps.

1. Read at least 100 bytes. Verify bytes 0-3 are `root`; otherwise reject.
2. Read `fVersion` at offset 4. If `fVersion >= 1000000`, use the large-file
   offsets from §2.2 and subtract 1000000 to recover the release.
3. Read `fBEGIN` at offset 8. Do not assume 100.
4. Read the remaining fields at the offsets for the selected layout.
5. Reject if `fBEGIN < 0` or `fBEGIN > fEND`.
6. The root directory record's key begins at `fBEGIN`. Its payload begins at
   `fBEGIN + fKeylen` with a duplicated name and title; the `TDirectoryFile` fields
   begin at `fBEGIN + fNbytesName` (§5.3). Continue with
   [Directories and key lists](Directory.md).

Everything else (the record chain, the keys list, the streamer info) is reached
from there or from `fSeekFree` / `fSeekInfo`.

## 10. Invariants

A conforming file satisfies the following. A reader MAY check them; per
`spec/00-conventions.md` §2 it SHOULD prefer tolerance where a violation does not
make the data ambiguous.

1. Bytes 0-3 are `root`.
2. `0 <= fBEGIN <= fEND`.
3. `fBEGIN + fNbytesName + sizeof(directory record) <= fEND`.
4. `10 <= fNbytesName <= 10000`.
5. `fEND <= filesize`. `fEND > filesize` means the file is truncated, and is
   the only direction ROOT rejects (`root/io/io/src/TFile.cxx:881-889`). A file
   longer than `fEND` has trailing bytes outside the format; ROOT ignores them and
   so should a reader (§5.2).
6. `fSeekFree == 0` **implies** the file was never closed; the converse does not
   hold, since `TFile::Write` writes the free list mid-job (§5.4). When it is
   non-zero, `fBEGIN < fSeekFree < fEND`, and `fNbytesFree` equals the `fNbytes`
   of the record at `fSeekFree`. `tools/check_invariants.py` checks this
   direction.
7. `nfree` equals the number of entries in the free list at `fSeekFree` and is
   at least 1. It is advisory (§5.4): g4tools writes 0.
8. `fSeekInfo` is either `<= fBEGIN` (no streamer info) or satisfies
   `fBEGIN < fSeekInfo < fEND` with `fNbytesInfo` equal to the `fNbytes` of the
   record there.
9. `fVersion >= 1000000` **if** `fEND > 2000000000`, and on every file seen so far
   the reverse holds too. The reverse is not guaranteed: the flag is set when `fEND`
   crosses the threshold (`root/io/io/src/TFile.cxx:2679`) and is never cleared, so
   a file that shrank below it again would keep the flag and still be readable.
   `tools/check_invariants.py` enforces the strict `iff`, which is slightly
   stricter than the format requires; no file in either corpus violates it. A
   reader MUST take the key width from the flag, never from `fEND`.
10. `fUnits` is 4 when `fVersion < 1000000` and 8 otherwise. ROOT does not enforce
    this and does not read the field.
11. `fBEGIN` is at least the length of the header its own `fVersion` selects:
    63 bytes for the small layout, 75 for the large one. The header is
    rewritten in place at every close, so it would overwrite a first record that
    began sooner. Four files in the corpora have `fBEGIN` of 64: two from ROOT
    2.24/00 and 3.04/02, and two that g4tools wrote with an `fVersion` of 40000
    (§8.1). All four would violate this invariant once pushed past 2 GB, since 64
    is one byte over the small header and eleven short of the large one. See
    [Writing a file §13.8](../06-writing/WritingFiles.md#138-crossing-2-gb-during-an-update).

ROOT does not validate the following, so they are not safe to assume: that
`fCompress` is in range, that the UUID is well-formed, and that the padding is
zero.

ROOT's own checks, which a reader can reuse, are at
`root/io/io/src/TFile.cxx:714-730` (magic and minimum length),
`:760-766` (`fBEGIN`/`fEND`), `:781-788` (directory record fits),
`:841-844` (`fNbytesName` range) and `:881-889` (truncation).

## 11. Errata

Against `root/io/doc/TFile/header.md` in the pinned submodule:

| # | Claim there | Actually |
|---|---|---|
| 1 | Widening is triggered when "END, SeekFree, or SeekInfo" exceed 2000000000 | The test is on `fEND` alone, strictly greater-than (§3) |
| 2 | *This document, until 2026-09-15*: invariant 5 required `fEND == filesize` for a cleanly closed file | `fEND <= filesize`. ROOT compares them only to detect truncation, and a cleanly closed ROOT 2.24/00 file in the corpus has four trailing bytes past `fEND` (§5.2) |
| 3 | `Compress` is a "Zip compression level (i.e. 0-9)" | `100 * algorithm + level` since ~5.30 (§5.8); typical values like `505` are unexplainable under the stated rule |
| 4 | `Units` is "Number of bytes for file pointers (4)" | Also 8; and ROOT never reads it (§5.7) |
| 5 | Padding is "extra space to allow END, SeekFree, or SeekInfo to become 64 bit" | True as intent, but the padding is never written and may hold stale data (§7) |
| 6 | `END` "will be == to file size in bytes" | Only for a cleanly closed file (§5.2) |
| 7 | `NbytesFree` / `NbytesInfo` are "Number of bytes in" the record | Specifically `TKey::fNbytes`, including the key (§5.4) |
| 8 | — | `fBEGIN` is not flagged as never widening despite being 64-bit in memory (§1) |
| 9 | *This document, until 2026-09-18*: invariant 6 made `fSeekFree == 0` an **iff** for "never closed" | One-way only. `TFile::Write` writes the free list and header mid-job, so a crashed job leaves a non-zero `fSeekFree` in a file that was never closed (§5.4) |
| 10 | — | No statement anywhere that the byte order is big-endian |
| 11 | — | Bytes 96-99 are required to be zero by the registered media type (§4) |
| 12 | — | Reproducible mode zeroes the UUID (§6) |
| 13 | — | The header UUID is write-only; the authoritative one is in the directory record (§6) |
| 14 | Two historical layouts are given (3.02.06 and 6.22.06) | A third exists: `fBEGIN = 64` **with** a UUID, from 3.03/07 to 3.04 (§8) |
| 15 | *This document, until 2026-09-22*: §8's table put the header UUID's first release at 3.03/00 | 3.03/07. `TFile.cxx` has no `fUUID` at `v3-03-06`, and `Event.3.2.0.root`, written by 3.03/02, has no UUID (§8) |
| 16 | *This document, until 2026-09-23*: ROOT 4 wrote `nfree` 0 | No available ROOT release does. The two files the claim rested on were written by g4tools, whose headers claim 4.00/00; every ROOT-written file available, back to 2.23/12, has `nfree` equal to its entry count (§5.4) |

## 12. Reference files

`container/file-minimal` — an uncompressed file with a single small object.
Its `case.toml` asserts every header field, and `tools/rootfile.py` implements §9.

| Field | Value |
|---|---|
| `fVersion` | 64004 |
| `fBEGIN` | 100 |
| `fEND` | 1094 (== file size) |
| `fSeekFree` | 993 |
| `fNbytesFree` | 101 |
| `nfree` | 1 |
| `fNbytesName` | 150 |
| `fUnits` | 4 |
| `fCompress` | 0 |
| `fSeekInfo` | 398 |
| `fNbytesInfo` | 434 |
