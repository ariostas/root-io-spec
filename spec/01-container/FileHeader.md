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
> **0**. They agree; the notation differs.

## 3. `fVersion` and the large-file flag

`fVersion` identifies the ROOT release that wrote the file:

```
fVersion mod 1000000 = 10000 * major + 100 * minor + patch
```

so 6.40.04 writes `64004`. A value `>= 1000000` additionally means the large-file
layout: subtract 1000000 to recover the release.

ROOT applies the flag in `root/io/io/src/TFile.cxx:2679`:

```cpp
if (version < 1000000 && fEND > kStartBigFile) { version += 1000000; fUnits = 8; }
```

with `kStartBigFile = 2000000000` (`root/io/io/inc/TFile.h:278`). Three consequences
a reader MUST account for:

1. The test is against **`fEND` alone**, strictly greater-than. It is not, as
   `root/io/doc/TFile/header.md` claims, a test on `fEND`, `fSeekFree` *or*
   `fSeekInfo`. The distinction is immaterial in practice because both offsets are
   below `fEND`, but the stated rule is not the implemented rule.
2. The flag is added to a **local copy**. `TFile::fVersion` in memory keeps the
   unflagged value for a file ROOT has just written, but takes the flagged value
   from disk for a file it has opened. `TFile::GetVersion()` returns whatever is
   current, unflagged or flagged.
3. `fUnits` is set to 8 as a side effect, but nothing reads it back (§5.7).

A reader MUST select the layout from `fVersion`, not from `fUnits`, because that is
what ROOT's own parser does (`root/io/io/src/TFile.cxx:738`).

## 4. Extent

`fBEGIN` bytes are reserved. `WriteHeader()` writes 63 bytes (small) or 75 bytes
(large) and stops; see §7 for what is in between.

ROOT 6.40.04 always writes `fBEGIN = 100`, fixed at `root/io/io/src/TFile.cxx:204`,
and `root/io/io/src/TFile.cxx:68-72` records that the value is fixed at 100 and that
**bytes 96-99 are reserved and MUST be zero**, a constraint from the file's
registered media type.

A reader MUST nevertheless take `fBEGIN` from the header rather than assume 100:
ROOT releases up to and including the 3.04 series used `fBEGIN = 64`. See §8.

## 5. Fields

### 5.1 magic

The four bytes `root`, written by `memcpy` with no terminator and no byte swapping.
A file whose first four bytes are not `root` MUST be rejected.

### 5.2 `fEND`

Offset of the first free byte at the end of the file. For a cleanly closed file it
equals the file size.

It does **not** equal the file size for a file that was never closed — the value on
disk is then whatever the last successful header write left. `fSeekFree == 0` is the
reliable signal for that case (§5.4), because ROOT writes the free list before the
header when closing (`root/io/io/src/TFile.cxx:1024-1025`). A reader SHOULD NOT
validate `fEND == filesize` unconditionally.

### 5.3 `fNbytesName`

The number of bytes, starting at `fBEGIN`, occupied by the root directory record's
key **plus a second serialized copy of its name and title** that follows the key.
The root directory's own payload therefore begins at:

```
fBEGIN + fNbytesName
```

which is how `TFile::Init()` locates it (`root/io/io/src/TFile.cxx:804`). It is the
only way to skip the variable-length prefix.

In `container/file-minimal`: the root directory's key is 91 bytes, its name is 32
bytes and its title 25, each with a 1-byte length prefix, giving
`91 + 33 + 26 = 150`.

ROOT rejects a file where the copy of this value inside the directory record is
outside `[10, 10000]` (`root/io/io/src/TFile.cxx:841-844`).

### 5.4 `fSeekFree`, `fNbytesFree`, `nfree`

`fSeekFree` is the absolute offset of the record holding the free-segment list.

`fNbytesFree` is that record's **total size including its key**, i.e. its
`TKey::fNbytes` and not its payload length. The same convention applies to
`fNbytesInfo`. Reading either as a payload length is the most common off-by-a-key
error in a reimplementation.

`nfree` is the number of `TFree` entries in the list. It is never zero for a cleanly
closed file: the list always ends with a sentinel segment running to `kStartBigFile`
(`root/io/io/src/TFile.cxx:691`), so an otherwise empty file has `nfree == 1`.

`fSeekFree == 0` marks a file that was created but never closed. ROOT warns and
attempts recovery rather than failing (`root/io/io/src/TFile.cxx:771-775`).

### 5.5 `fSeekInfo`, `fNbytesInfo`

Absolute offset and total size (including key) of the record holding the
streamer-info list — a `TList` of `TStreamerInfo`, stored under the key name
`StreamerInfo`. See `spec/02-serialization/StreamerInfo.md`.

`fSeekInfo <= fBEGIN` means the file has no streamer-info record
(`root/io/io/src/TFile.cxx:921`). That is normal for a file containing only classes
ROOT does not write streamer info for, and abnormal otherwise.

### 5.6 Locating the keys list

The header does **not** contain the offset of the keys list. That offset,
`fSeekKeys`, lives in the root directory record; see
`spec/01-container/Directory.md`.

> **The keys-list and free-segment records cannot be identified from their keys.**
> Both carry `fClassName = "TFile"` and the file's own name and title, exactly like
> the root directory record. `TFile::Map()` labels them `KeysList` and
> `FreeSegments` by comparing offsets against `fSeekKeys` and `fSeekFree`, not by
> reading anything in the key. A reader MUST do the same. In
> `container/file-minimal`, three distinct records at offsets 100, 832 and 993 all
> have `fClassName = "TFile"` and the name `data/container/file-minimal.root`.

### 5.7 `fUnits`

The width in bytes of the file's offset fields: 4 in the small-file layout, 8 in the
large-file layout.

**ROOT never reads this field.** Every occurrence in `root/io/io/` is an
initialization, a write, or a read into the member that is then never consulted.
A reader MUST branch on `fVersion` (§3) and MAY use `fUnits` only as a cross-check.
Where the two disagree, `fVersion` is authoritative, because that is the one ROOT
acts on.

### 5.8 `fCompress`

The file's **default** compression setting:

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
> carries its own compressed and uncompressed lengths, and each may use a different
> algorithm — the algorithm of a given record is determined by the magic bytes of
> its compression block, never by `fCompress`. See
> `spec/01-container/Compression.md`.

Before ROOT ~5.30, `fCompress` was a bare ZLIB level with no algorithm component.
The modern decoding stays correct for those files: a level in 0-9 yields algorithm 0
("use global default"), which resolves to ZLIB.

## 6. UUID

A 2-byte class version, always `1`, followed by the 16-byte UUID.

The 16 bytes are the standard RFC 4122 big-endian wire layout — a 4-byte
`fTimeLow`, 2-byte `fTimeMid`, 2-byte `fTimeHiAndVersion`, 1-byte
`fClockSeqHiAndReserved`, 1-byte `fClockSeqLow`, and 6 bytes of `fNode` — so they
can be read directly as a UUID and formatted conventionally.

Two properties that surprise implementers:

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
allocates an uninitialized buffer of `fBEGIN` bytes and hands only the first 63 or
75 to the write call. On a newly created file the rest is a hole in the file, which
reads back as zero on any ordinary filesystem — which is what lets the media-type
registration require bytes 96-99 to be zero (§4).

On a file opened for update, `WriteHeader()` again rewrites only the first 63 or 75
bytes. Whatever was in the padding stays. In particular, a file that once exceeded
2 GB and later shrank below the threshold retains the stale tail of its large-file
fields there.

A reader MUST treat the padding as "don't care" and MUST NOT rely on it being zero.

## 8. Version history

| ROOT versions | Header |
|---|---|
| ≤ 3.02 | `fBEGIN = 64`. No UUID: bytes 45-63 are unwritten. |
| 3.03 – 3.04 | `fBEGIN = 64`, UUID present. |
| ≥ 3.05 | `fBEGIN = 100`. Large-file layout exists; `fVersion >= 1000000` is possible. |
| ≥ ~5.30 | `fCompress` gains its algorithm component (§5.8). |
| ≥ 6.x | Reproducible mode possible (§6). |

Field order, offsets, widths and byte order have been stable since 3.05. The
large-file layout cannot occur in a file older than 3.05, since the flag did not
exist.

## 9. Reading

A conforming reader performs the following steps.

1. Read at least 100 bytes. Verify bytes 0-3 are `root`; otherwise reject.
2. Read `fVersion` at offset 4. If `fVersion >= 1000000`, use the large-file
   offsets from §2.2 and subtract 1000000 to recover the release.
3. Read `fBEGIN` at offset 8. Do not assume 100.
4. Read the remaining fields at the offsets for the selected layout.
5. Reject if `fBEGIN < 0` or `fBEGIN > fEND`.
6. The root directory record's key begins at `fBEGIN`; its payload begins at
   `fBEGIN + fNbytesName`. Continue with `spec/01-container/Directory.md`.

Everything else — the record chain, the keys list, the streamer info — is reached
from there or from `fSeekFree` / `fSeekInfo`.

## 10. Invariants

A conforming file satisfies the following. A reader MAY check them; per
`spec/00-conventions.md` §2 it SHOULD prefer tolerance where a violation does not
make the data ambiguous.

1. Bytes 0-3 are `root`.
2. `0 <= fBEGIN <= fEND`.
3. `fBEGIN + fNbytesName + sizeof(directory record) <= fEND`.
4. `10 <= fNbytesName <= 10000`.
5. `fEND == filesize`, **for a cleanly closed file only**. `fEND > filesize` means
   the file is truncated.
6. `fSeekFree == 0` **iff** the file was never closed. Otherwise
   `fBEGIN < fSeekFree < fEND`, and `fNbytesFree` equals the `fNbytes` of the
   record at `fSeekFree`.
7. `nfree` equals the number of entries in the free list at `fSeekFree`, and is
   at least 1.
8. `fSeekInfo` is either `<= fBEGIN` (no streamer info) or satisfies
   `fBEGIN < fSeekInfo < fEND` with `fNbytesInfo` equal to the `fNbytes` of the
   record there.
9. `fVersion >= 1000000` **iff** `fEND > 2000000000` at the time of the last header
   write. The converse does not hold: a file that shrank below the threshold keeps
   the flag.
10. `fUnits` is 4 when `fVersion < 1000000` and 8 otherwise. ROOT does not enforce
    this and does not read the field.

Not validated by ROOT, and therefore not safe to assume: `fCompress` is in range,
the UUID is well-formed, and the padding is zero.

ROOT's own checks, which a reader can reuse, are at
`root/io/io/src/TFile.cxx:714-730` (magic and minimum length),
`:760-766` (`fBEGIN`/`fEND`), `:781-788` (directory record fits),
`:841-844` (`fNbytesName` range) and `:881-887` (truncation).

## 11. Errata

Against `root/io/doc/TFile/header.md` in the pinned submodule:

| # | Claim there | Actually |
|---|---|---|
| 1 | Widening is triggered when "END, SeekFree, or SeekInfo" exceed 2000000000 | The test is on `fEND` alone, strictly greater-than (§3) |
| 2 | `Compress` is a "Zip compression level (i.e. 0-9)" | `100 * algorithm + level` since ~5.30 (§5.8); typical values like `505` are unexplainable under the stated rule |
| 3 | `Units` is "Number of bytes for file pointers (4)" | Also 8; and ROOT never reads it (§5.7) |
| 4 | Padding is "extra space to allow END, SeekFree, or SeekInfo to become 64 bit" | True as intent, but the padding is never written and may hold stale data (§7) |
| 5 | `END` "will be == to file size in bytes" | Only for a cleanly closed file (§5.2) |
| 6 | `NbytesFree` / `NbytesInfo` are "Number of bytes in" the record | Specifically `TKey::fNbytes`, including the key (§5.4) |
| 7 | — | `fBEGIN` is not flagged as never widening despite being 64-bit in memory (§1) |
| 8 | — | No statement anywhere that the byte order is big-endian |
| 9 | — | Bytes 96-99 are required to be zero by the registered media type (§4) |
| 10 | — | Reproducible mode zeroes the UUID (§6) |
| 11 | — | The header UUID is write-only; the authoritative one is in the directory record (§6) |
| 12 | Two historical layouts are given (3.02.06 and 6.22.06) | A third exists: `fBEGIN = 64` **with** a UUID, in the 3.03-3.04 line (§8) |

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
