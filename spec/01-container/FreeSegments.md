# Free segments

Byte ranges in the file that hold no live record. They arise when an object is
deleted or overwritten, and they are recorded twice: as a list in a dedicated
record, and in place at the start of each span.

Prerequisites: [Conventions](../00-conventions.md), [File header](FileHeader.md),
[Records and keys](Record.md). All integers are big-endian.

## 1. Why a reader cares

Two reasons, one of which is mandatory:

1. **Walking the record chain requires it.** A freed span begins with a negative
   `fNbytes`, and a reader advancing record by record MUST recognise and skip it
   rather than parse a key there (§4). This is not optional — any file that has
   ever had an object deleted or rewritten contains one.
2. Reading the list itself is optional, and mostly useful for validation or for
   writing.

## 2. The free-segment record

Located from the file header: `fSeekFree` gives its offset and `fNbytesFree` its
total length including the key
([File header §5.4](FileHeader.md#54-fseekfree-fnbytesfree-nfree)).

Its key carries the file's own name, title and class `"TFile"`, making it
indistinguishable from the root directory record and the key-list record — so
`fSeekFree` is the only way to find it, exactly as for the key list
([Directory §6.2](Directory.md#62-the-key-list-record-cannot-be-identified-from-its-key)).

The payload is a sequence of entries, back to back:

| Field | Type | Width |
|---|---|---|
| version | `i16` | 2 |
| `fFirst` | `i32` / `i64` | 4 or 8 |
| `fLast` | `i32` / `i64` | 4 or 8 |

Each entry is 10 bytes, or 18 in the large form. Written by
`root/io/io/src/TFree.cxx:108-121`.

**Both bounds are inclusive.** A one-byte segment has `fFirst == fLast`, and a
segment's length is `fLast - fFirst + 1`.

> Demonstrated by `container/gap`: the interior entry is `(718, 904)`, which is
> 187 bytes, matching the `-187` marker written at offset 718.

### 2.1 The large form

An entry uses 8-byte bounds when its **`fLast` exceeds 2000000000**, and the
version word is then `1001` rather than `1`
(`root/io/io/src/TFree.cxx:111`). The test is on `fLast` only, strictly
greater-than.

Each entry is self-describing, so 10-byte and 18-byte entries may be interleaved
in one record. A reader MUST size each entry from its own version word.

This is a **fourth** large-file flag, independent of the three in
[Directory §3](Directory.md#3-three-independent-large-file-flags).

## 3. Reading the list

> **The list is terminated by a sentinel, not by a count or a length.** ROOT reads
> entries until it sees one whose `fLast > fEND`, and stops after including it
> (`root/io/io/src/TFile.cxx:1978-1997`).

Neither of the two apparent bounds is sufficient on its own:

- **`nfree` in the header is advisory.** It is written correctly — the header is
  written after the free record — but ROOT never reads it back for this purpose
  (`root/io/io/src/TFile.cxx:742`). A reader MAY use it as a cross-check.
- **The payload length is not a reliable bound.** `WriteFree` may zero-fill the
  tail of the payload when allocating the record consumed one of the entries it had
  already counted (`root/io/io/src/TFile.cxx:2649-2658`). A length-driven parse can
  therefore produce a spurious all-zero entry.

A robust reader iterates while bytes remain within `fObjlen`, stops after the first
entry with `fLast > fEND`, and compares the count with `nfree`.

## 4. The in-place marker

Each freed span also records itself, by overwriting its first four bytes with a
**negative** `i32` in the position where a live record's `fNbytes` would be
(`root/io/io/src/TFile.cxx:1496-1519`).

A live record always has `fNbytes > 0` — `TKey` rejects a negative value
(`root/io/io/src/TKey.cxx:1229-1234`) — so the sign is an unambiguous
discriminator.

Three properties of the magnitude that are easy to get wrong:

- **It is the length of the whole *merged* span**, not of the record that was
  deleted. Adjacent free space is coalesced, so one marker can cover several
  formerly separate records.
- **It is written at the merged span's first byte**, which may precede the deleted
  record's own start.
- **It is clamped to 2000000000** (`root/io/io/src/TFile.cxx:1505`). For a span
  longer than that, the marker understates the length and only the free list is
  correct.

The rest of the span is **not** cleared. It holds stale bytes — often most of the
deleted record, including a recognisable key. A reader MUST advance by the
magnitude and MUST NOT attempt to interpret what follows.

### 4.1 A second producer of markers

`TKey::Create` also writes one. When a new record is placed in a gap strictly
larger than it needs, the remainder gets its own negative marker at
`fSeekKey + fNbytes` (`root/io/io/src/TKey.cxx:554-563`).

### 4.2 The marker may be missing

The four-byte write is unchecked (`root/io/io/src/TFile.cxx:1512-1517`). ROOT's
own comment notes that the marker may therefore be absent on disk, in which case
only recovery suffers. A reader that walks the chain and finds a key where the free
list says there is a gap SHOULD trust the free list.

### 4.3 Directories are never freed

`TKey::Delete` refuses to delete a key marked as a directory
(`root/io/io/src/TKey.cxx:584-594`), so a directory record never becomes a gap.

## 5. The trailing segment

The last entry is not really a sentinel by construction — it is the unallocated
tail of the address space, and it is where `fEND` comes from:

```
fEND == (last entry).fFirst
```

`WriteHeader` literally assigns it (`root/io/io/src/TFile.cxx:2671-2672`). As
records are appended, the entry's `fFirst` advances.

A new file starts with this entry alone, spanning `fBEGIN` to 2000000000
(`root/io/io/src/TFile.cxx:691`).

> **`fLast` does not jump straight to 4000000000 when a file passes 2 GB.** It
> grows in 1 GB steps — 2000000000, then 3000000000, then 4000000000, and so on —
> each time a record no longer fits (`root/io/io/src/TKey.cxx:537-539`,
> `root/io/io/src/TFree.cxx:148-152`). `root/io/doc/TFile/freesegments.md` states
> otherwise.

Once `fLast` exceeds 2000000000, that entry alone switches to the 18-byte form
(§2.1).

## 6. Deleting the last record shrinks the file

If the freed span ends at `fEND - 1`, `fEND` is moved back to the span's start
(`root/io/io/src/TFile.cxx:1510`), so the space is reclaimed rather than recorded
as an interior gap.

ROOT does **not** truncate the file on disk. `fEND` may therefore be less than the
physical file size, and the bytes beyond `fEND` are stale. A reader MUST bound
its record walk by `fEND`, not by the file size.

Note that the reverse — `fEND` greater than the file size — means the file is
truncated, and ROOT attempts recovery
(`root/io/io/src/TFile.cxx:889-905`).

## 7. Reading

To walk the chain, per [Records §1](Record.md#1-the-record-chain):

1. Start at `fBEGIN`.
2. Read an `i32`. If zero, the file is corrupt; stop.
3. If negative, this is a free span: advance by its magnitude and repeat.
4. Otherwise parse the key and advance by `fNbytes`.
5. Stop at `fEND`.

To read the list:

1. If `fSeekFree` is 0, the file was never closed and there is no list.
2. Read the record at `fSeekFree`, of `fNbytesFree` bytes.
3. From the payload start, read entries: a version word, then two bounds of 4 or 8
   bytes according to whether the version exceeds 1000.
4. Stop after the first entry whose `fLast > fEND`.

## 8. Invariants

1. `fEND` equals the last entry's `fFirst`.
2. The last entry's `fLast > fEND`, and is at least 2000000000. Above that it is a
   multiple of 1000000000.
3. `nfree` in the header equals the number of entries.
4. `fSeekFree` equals the free record's own `fSeekKey`, and `fNbytesFree` its
   `fNbytes`.
5. Entries are in strictly ascending order, non-overlapping and **non-adjacent** —
   adjacent spans are always merged (`root/io/io/src/TFree.cxx:66-95`).
6. Every interior entry's `fFirst` holds a negative `i32` whose magnitude is
   `min(fLast - fFirst + 1, 2000000000)`.
7. Every negative marker found while walking the chain corresponds to an entry in
   the list.
8. Live records and free spans partition `[fBEGIN, fEND)` exactly.
9. `fEND <= physical file size`.

Invariants 6 and 7 are the ones that can legitimately fail: a `MakeFree` write may
have been lost (§4.2), and a recovered file's list is built by plain appends rather
than by the merging insert, so it may violate 5 as well.

## 9. Errata

Against `root/io/doc/TFile/freesegments.md` and `gap.md`:

| # | Claim | Actually |
|---|---|---|
| 1 | `freesegments.md`: a final segment "beginning at file end and ending before 2000000000" | It begins **at** `fEND` — indeed `fEND` is derived from it — and `fLast` **is** 2000000000, inclusive (§5) |
| 2 | `freesegments.md`: past 2 GB "the last segment ends with 4000000000" | `fLast` grows in 1 GB steps, so a 2.5 GB file has 3000000000 (§5) |
| 3 | — | No termination rule is given. ROOT stops at the first entry with `fLast > fEND`; `nfree` is written but never read back (§3) |
| 4 | — | The payload may carry zero-filled slack, so a length-driven parse can yield a bogus entry (§3) |
| 5 | — | The widening condition is `fLast > 2000000000`, tested on `fLast` alone, and each entry is self-describing (§2.1) |
| 6 | — | `fNbytesFree` counts the whole record, key included |
| 7 | `gap.md`: the first four bytes hold "the negative of the number of bytes in the segment" | True, but the magnitude is that of the whole **merged** span, clamped to 2000000000, and written at the merged span's start (§4) |
| 8 | — | A second producer exists: `TKey::Create` marks the remainder of a partially reused gap (§4.1) |
| 9 | — | Deleting the last record shrinks `fEND`; the marker write is unchecked and may be absent; the span's remaining bytes are stale, not cleared; directory records are never freed (§4.2, §4.3, §6) |

## 10. A suspected bug in recovery

`TFile::Recover`'s gap branch decrements its cursor *before* constructing the
`TFree`, so the registered span appears to be `[start + |n|, start + 2|n| - 1]`
rather than `[start, start + |n| - 1]`
(`root/io/io/src/TFile.cxx:2143-2144`).

This is flagged as **apparent, not confirmed** — the path has not been exercised
here. It affects only recovery of a damaged file, not normal reading. Worth
verifying and, if real, reporting upstream.

## 11. Reference files

| Case | Exercises |
|---|---|
| `container/gap` | A deleted record: an interior entry and its in-place marker |
| `container/file-minimal` | The trailing entry alone, `fFirst == fEND`, `fLast == 2000000000` |

No fixture covers the large entry form or a `fLast` above 2000000000; both need a
file over 2 GB, which belongs with the release artifacts rather than the committed
corpus.
