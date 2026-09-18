# Compression

Record payloads may be compressed. This document specifies the compression block
format, how a reader decides whether a payload is compressed at all, and how a
payload larger than 16 MiB is split across several blocks.

Prerequisites: [Conventions](../00-conventions.md).

> **The compression block header is little-endian in part.** The two size fields
> are 24-bit little-endian, inside a file format that is otherwise big-endian.
> This is the single most common mistake in a new implementation.

## 1. Deciding whether a payload is compressed

There is **no flag**. A reader determines it arithmetically, from three
[key](Record.md) fields:

```
payload length = fNbytes - fKeylen
compressed     if  fObjlen >  payload length
stored raw     if  fObjlen <= payload length
```

`fObjlen` is always the uncompressed length. A record whose payload is at least
`fObjlen` bytes long is stored verbatim, with **no block header at all** — not a
header declaring zero compression. See §6.

### 1.1 Why the test is an inequality

The two differ only when the payload is **longer** than `fObjlen`, and such a
record is stored raw: a reader takes the first `fObjlen` bytes and ignores the
rest. ROOT's test is `fObjlen > fNbytes-fKeylen`, in all eight places `TKey` makes
the decision (`root/io/io/src/TKey.cxx:827`, `root/io/io/src/TKey.cxx:871`,
`root/io/io/src/TKey.cxx:948`, `root/io/io/src/TKey.cxx:983`,
`root/io/io/src/TKey.cxx:1056`, `root/io/io/src/TKey.cxx:1116`,
`root/io/io/src/TKey.cxx:1179`, `root/io/io/src/TKey.cxx:1191`).

`TFile::Map()` is where the confusion comes from: its `CX` column is printed
whenever the two are **unequal** (`root/io/io/src/TFile.cxx:1617`), so a record
with trailing slack is displayed with a compression ratio below 1 while being read
as raw. The display test and the read test are not the same test.

This is not hypothetical. An RNTuple page blob has exactly this shape, because
RNTuple's key writer takes the on-disk and in-memory lengths as independent
arguments — `fNbytes = fKeylen + szObjOnDisk` and `fObjlen = szObjInMem`
(`root/tree/ntuple/src/RMiniFile.cxx:230-235`) — and its own comment says the
object length is kept only "for seeing compression ratios in `TFile::Map()`"
(`root/tree/ntuple/src/RMiniFile.cxx:1437-1438`). For an `RBlob`, `fObjlen`
is decorative and a reader must not derive the payload length from it.

> Measured on `RNTuple.root` from the corpus of `PLAN.md` §9.9, written by ROOT
> 6.35/01: the `RBlob` at offset 586 has `fNbytes` 789, `fKeylen` 34 and `fObjlen`
> **723** — a 755-byte payload holding 723 bytes of object data. `TFile::Map()`
> prints `CX = 0.96` for it and `TFile::Open` reads the file without complaint. A
> reader using the `!=` test tries to decompress it, finds the magic `05 00`, and
> rejects the whole file.

> **`fCompress` in the file header does not tell you this.** It is the file's
> default setting at the time of writing, nothing more. Individual records may be
> uncompressed, or compressed with a different algorithm, and a reader MUST decide
> per record. Demonstrated by `container/compress-none-fallback`, whose header
> requests zlib while its data record is stored raw.

## 2. Block header

Every compressed payload is a sequence of one or more **blocks**. Each block
begins with a 9-byte header:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   magic[0]    |   magic[1]    |    method     |    c0         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      c1       |      c2       |      u0       |      u1       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      u2       |   payload ...
+-+-+-+-+-+-+-+-+-
```

| Offset | Field | Width | Meaning |
|---|---|---|---|
| 0-1 | magic | 2 | Algorithm identifier, §3 |
| 2 | method | 1 | Algorithm-specific, §3 |
| 3-5 | compressed size | 3 | 24-bit **little-endian**, §4 |
| 6-8 | uncompressed size | 3 | 24-bit **little-endian**, §4 |
| 9 … | payload | | LZ4 inserts a checksum first, §5 |

## 3. Algorithms

| magic | Bytes | Algorithm | method byte |
|---|---|---|---|
| `ZL` | `5A 4C` | ZLIB (deflate) | `8` |
| `XZ` | `58 5A` | LZMA | `0` |
| `L4` | `4C 34` | LZ4 | LZ4 major version, currently `1` |
| `ZS` | `5A 53` | Zstandard | `1` |
| `CS` | `43 53` | Legacy ROOT algorithm | `8` |

Cited at `root/core/zip/src/RZip.cxx:226-228` (ZLIB),
`root/core/lzma/src/ZipLZMA.c:84-86`, `root/core/lz4/src/ZipLZ4.cxx:65-67`,
`root/core/zstd/src/ZipZSTD.cxx:50-52` and `root/core/zip/src/RZip.cxx:156-158`.

The algorithm is determined by the magic bytes **and, for four of the five, the
method byte as well**. ROOT's validators are
`root/core/zip/src/RZip.cxx:247-269`: `ZL` requires `src[2] == Z_DEFLATED` (8),
`CS` the same, `XZ` requires 0, `ZS` requires 1, and only `L4` looks at the magic
alone. A block whose magic matches but whose method byte does not is **rejected
outright** rather than decompressed — `R__unzip` refuses it at
`root/core/zip/src/RZip.cxx:354` — so a reader that switches on the magic alone is
more liberal than ROOT, not less.

ROOT probes the five in the order ZSTD, ZLIB, LZ4, LZMA, legacy
(`root/core/zip/src/RZip.cxx:278-295`); the order is irrelevant to a correct
reader, since the magics are distinct. Note that `ZL` and `ZS` differ in one byte,
as do `ZS` and `CS`.

`CS` is the original algorithm — the initials of its authors,
`root/core/zip/src/RZip.cxx:156` — and predates ROOT's use of the zlib library. It
is **not** a different algorithm from `ZL`; see §3.1.

### 3.1 `CS` is raw DEFLATE, and `ZL` is zlib-wrapped

Both carry method byte 8 and both hold a DEFLATE stream. They differ in one thing:
the **wrapper**.

| magic | Stream | Python |
|---|---|---|
| `ZL` | zlib (RFC 1950): a two-byte header, DEFLATE data, an Adler-32 trailer | `zlib.decompress(block)` |
| `CS` | raw DEFLATE (RFC 1951) and nothing else | `zlib.decompressobj(-zlib.MAX_WBITS).decompress(block)` |

ROOT's two paths say so directly. A `ZL` block goes to `R__unzipZLIB`, which calls
`inflateInit` — the zlib-wrapped entry point
(`root/core/zip/src/RZip.cxx:409-422`). A `CS` block falls past every named
algorithm to ROOT's own bundled inflate under the comment "Old zlib format"
(`root/core/zip/src/RZip.cxx:391-392`), and that function begins decoding blocks
immediately with an empty bit buffer, consuming no header and checking no trailer
(`root/core/zip/src/ZInflate.c:1048-1090`). Its tables are PKZIP's
(`root/core/zip/src/ZInflate.c:291-308`).

So a reader that already has zlib needs no new algorithm for `CS` — only the
`-MAX_WBITS` window size that selects the raw stream. A reader that treats `CS` as
zlib gets an "incorrect header check" and, if it concludes the algorithm is
unavailable, rejects every record of a file that is entirely readable.

> Demonstrated by `pippa.root` in the corpus of `PLAN.md` §9.9, written by ROOT
> 2.24/00: **all 468** of its compressed records decompress with raw DEFLATE, each
> producing exactly the block header's uncompressed size. Before this was
> understood, every one of them was reported as "no codec".

A reader encountering an unknown magic MUST NOT attempt to decompress. It cannot
skip the block either, since it cannot trust the sizes; it should reject the
record.

> Demonstrated by `container/compress-zlib`, `compress-lzma`, `compress-lz4` and
> `compress-zstd`, which assert the magic and method bytes of each.

## 4. The size fields

Both size fields are **24-bit little-endian**, written byte by byte
(`root/core/zip/src/RZip.cxx:230-238`):

```
compressed   = b[3] | (b[4] << 8) | (b[5] << 16)
uncompressed = b[6] | (b[7] << 8) | (b[8] << 16)
```

So byte 3 holds bits 0-7 of the compressed size, byte 4 bits 8-15, byte 5 bits
16-23; and likewise bytes 6, 7, 8 for the uncompressed size. This is the same in
every algorithm's writer.

Two properties follow, and both are load-bearing:

- **The compressed size excludes the 9-byte header.** The total size of a block on
  disk is `9 + compressed size`. ROOT's reader adds the header back explicitly
  (`root/core/zip/src/RZip.cxx:311-312`).
- **Both sizes are capped at `0xFFFFFF`**, 16 MiB − 1, because the fields are 24
  bits. This is what forces the block splitting of §7.

For a single-block payload:

```
9 + compressed size == fNbytes - fKeylen
uncompressed size   == fObjlen
```

Both relations are asserted for all four algorithms in the fixtures.

> The comment at `root/core/lz4/src/ZipLZ4.cxx:23-31` documents these two fields in
> the **wrong order**, listing uncompressed before compressed. The code writes
> compressed first, exactly like every other algorithm. Trust the code.

## 5. LZ4 and its checksum

LZ4 blocks alone carry an 8-byte checksum between the header and the payload, so
their total header is **17 bytes**:

```
0-8    the 9-byte header of §2
9-16   XXH64 checksum, 8 bytes, big-endian canonical form
17 …   LZ4 compressed payload
```

- The algorithm is **XXH64 with seed 0** (`root/core/lz4/src/ZipLZ4.cxx:63`).
- It covers **only the compressed payload**, the bytes from offset 17 to the end
  of the block. It does not cover the header and does not cover itself
  (`root/core/lz4/src/ZipLZ4.cxx:106-112`).
- **The compressed-size field includes the checksum**
  (`root/core/lz4/src/ZipLZ4.cxx:69`). So for an LZ4 block:

  ```
  payload length = compressed size - 8
  block length   = 9 + compressed size   (as for every algorithm)
  ```

  The `9 + compressed size` rule is therefore uniform; only the position where the
  compressed data starts differs.

A reader SHOULD verify the checksum and MUST reject the block on mismatch.

> Demonstrated by `container/compress-lz4`, which asserts the checksum bytes and
> pins the relation between the size field, the checksum and the payload start.

## 6. Uncompressed payloads

When compression would not shrink a payload, ROOT stores it **raw, with no block
header** (`root/io/io/src/TKey.cxx:276-284`). There is no "stored" method byte and
no degenerate block. The payload begins immediately with object data.

This happens when:

- compression is disabled for the file or the record, or
- `fObjlen <= 256` **for a record written through `TKey`**, since ROOT does not
  attempt compression below that threshold (`root/io/io/src/TKey.cxx:264`). This
  does **not** apply to a `TBasket`, which compresses at any size — see §8 — or
- the compressor produced output no smaller than the input.

The detection rule is the one in §1: `fObjlen <= fNbytes - fKeylen`.

> `container/compress-none-fallback` requests zlib on an incompressible payload.
> The record's payload is 533 bytes with `fObjlen` 533, and begins with the object
> byte-count word rather than any magic. `container/file-minimal` shows the
> `fObjlen <= 256` case.

Note that ROOT's incompressibility test compares a *single block's* output against
the *whole object's* length, which is a loose test for multi-block payloads. It
affects only which files ROOT produces, never how a reader interprets one.

### The StreamerInfo record is not special

`root/io/doc/TFile/README.md` states that the StreamerInfo record's payload is
"always compressed at level 1 … even if no compression is selected". **This is not
true in 6.40.04.** In `container/file-minimal`, written with compression disabled,
the StreamerInfo record has `fNbytes - fKeylen == fObjlen == 370` — uncompressed,
despite exceeding the 256-byte threshold. A reader MUST apply the same rule to the
StreamerInfo record as to any other.

## 7. Multi-block payloads

A payload larger than `kMAXZIPBUF = 0xFFFFFF` (16 MiB − 1,
`root/core/zip/inc/RZip.h:40`) is split into consecutive, independently compressed
blocks written back to back. Every block but the last holds exactly `kMAXZIPBUF`
**uncompressed** bytes; the last holds the remainder.

**The block count is not stored anywhere.** A reader walks the chain, using each
block's own header to find the next (`root/io/io/src/TKey.cxx:403-427`):

1. Let the input cursor be `fKeylen` and the output cursor 0.
2. While at least 9 bytes of payload remain and the output cursor is below
   `fObjlen`:
   1. Read the block header. Verify the magic.
   2. Let `nin = 9 + compressed size` and `nout = uncompressed size`.
   3. Reject if `nin` exceeds the remaining input or `nout` the remaining output.
   4. Decompress `nin - 9` bytes (`nin - 17` for LZ4, from offset 17) into `nout`
      bytes at the output cursor.
   5. Advance the input cursor by `nin` and the output cursor by `nout`.
3. Stop when the output cursor reaches `fObjlen`.

Equivalently, for a payload written by ROOT, the count is
`1 + (fObjlen - 1) / kMAXZIPBUF`. A reader MAY compute it that way, but MUST still
take each block's length from its own header, since compressed lengths vary.

Blocks are not padded and not aligned; they cannot be indexed arithmetically.

## 8. Where compression is and is not applied

Never compressed:

- The file header.
- The key portion of any record. `fKeylen` bytes are always plain.

Compressed according to the usual rules, `fObjlen > 256` and a compressor that
helps:

- Application data records, the keys list, the free-segment list and the
  StreamerInfo record — everything written through `TKey::WriteBuffer`.

**A `TBasket` is the exception, and it is the common case.** `TBasket::WriteBuffer`
has its own compression path whose only test is on the level —
`if (cxlevel > 0)` (`root/tree/tree/src/TBasket.cxx:1300`) — with **no size test at
all**, where `TKey` has `if (cxlevel > 0 && fObjlen > 256)`
(`root/io/io/src/TKey.cxx:264`). So a 40-byte basket in a compressed file *is*
compressed, and a reader that assumes a small payload must be raw will mis-parse
the baskets of any sparsely filled tree. The detection rule of §1 is unaffected: it
never consults the size.

> Witnessed by `ttree/tree-branchref`, written by ROOT with compression on: the
> basket at offset 457 has `fObjlen` **108** — well under the threshold — stored in
> **51** bytes, so `fObjlen > fNbytes - fKeylen` and the payload carries a `ZL`
> block. Under the `TKey` rule that record could not exist.

`TBasket` performs its own splitting with the same constants
(`root/tree/tree/src/TBasket.cxx:1300-1355`); see [TBasket](../04-ttree/TBasket.md).

## 9. Invariants

1. For every record, `fNbytes - fKeylen` is either at least `fObjlen` (raw) or
   the exact total length of a chain of compression blocks.
2. For each block, the total length is `9 + compressed size`, and the block lies
   entirely within the record's payload.
3. The sum of the blocks' uncompressed sizes equals `fObjlen`.
4. Every block's magic is one of the five in §3, and the method byte matches that
   algorithm.
5. No block declares an uncompressed size greater than `0xFFFFFF`, and every block
   but the last in a chain declares exactly `0xFFFFFF`.
6. For an LZ4 block, the XXH64 of the bytes from offset 17 to the end of the block
   equals the checksum at offsets 9-16, and `compressed size >= 8`.
7. A raw payload never begins with a valid block magic followed by sizes
   consistent with the record — but this is not guaranteed by construction, which
   is why §1 is arithmetic rather than a magic probe.

Invariant 7 is the reason a reader MUST NOT detect compression by sniffing for a
magic. Object data can begin with any bytes.

## 10. Errata

Against the pinned submodule:

| # | Claim | Actually |
|---|---|---|
| 1 | `root/io/doc/TFile/README.md`: there are "ten compression levels, 0-9" and the algorithm is "an in memory ZIP compression written for the DELPHI collaboration" | Five algorithms exist (§3); the setting is `100 * algorithm + level` (see [File header](FileHeader.md#58-fcompress)) |
| 2 | `root/io/doc/TFile/README.md`: the StreamerInfo payload is "always compressed at level 1 … even if no compression is selected" | Not in 6.40.04; disproved by `container/file-minimal` (§6) |
| 3 | `root/io/doc/TFile/README.md`: records "where the uncompressed size of the data portion is 256 bytes or less" are not compressed | True of `TKey` only, and strictly `fObjlen > 256`. A `TBasket` has no size test and compresses at any size (§8), which the shipped documentation does not mention |
| 4 | `root/core/lz4/src/ZipLZ4.cxx:23-31`, comment: the header holds "3 bytes of uncompressed size, 3 bytes of compressed size" | Reversed; the code writes compressed at 3-5 and uncompressed at 6-8, like every other algorithm (§4) |
| 5 | *This document, until 2026-09-15*: a payload is compressed when `fNbytes - fKeylen != fObjlen` | Compressed when `fObjlen > fNbytes - fKeylen`. The `!=` form is `TFile::Map()`'s display test, not `TKey`'s read test, and a reader using it rejects any file containing an RNTuple page blob (§1.1) |

## 11. Reference files

| Case | Exercises |
|---|---|
| `container/compress-zlib` | `ZL` magic, method 8, single block |
| `container/compress-lzma` | `XZ` magic, method 0 |
| `container/compress-lz4` | `L4` magic, the XXH64 checksum, the 17-byte header |
| `container/compress-zstd` | `ZS` magic, method 1 |
| `container/compress-none-fallback` | Raw storage despite `fCompress` requesting zlib |
| `container/file-minimal` | Raw storage via the `fObjlen <= 256` threshold |

All five compressed cases hold the same 8221-byte payload, so their block sizes
are directly comparable:

| Algorithm | Compressed size | Record `fNbytes` |
|---|---|---|
| ZSTD | 76 | 151 |
| LZ4 | 108 (including its 8-byte checksum) | 183 |
| ZLIB | 142 | 217 |
| LZMA | 156 | 231 |
