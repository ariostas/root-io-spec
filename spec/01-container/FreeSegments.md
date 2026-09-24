# Free segments

Byte ranges in the file that hold no live record. They arise when an object is
deleted or overwritten, and they are recorded twice: as a list in a dedicated
record, and in place at the start of each span.

Prerequisites: [Conventions](../00-conventions.md), [File header](FileHeader.md),
[Records and keys](Record.md). All integers are big-endian.

## 1. Why a reader cares

1. **Walking the record chain requires it.** A freed span begins with a negative
   `fNbytes`, and a reader advancing record by record MUST recognise and skip it
   rather than parse a key there (§4). Any file that has ever had an object
   deleted or rewritten contains one.
2. Reading the list itself is optional, and mostly useful for validation or for
   writing.

## 2. The free-segment record

Located from the file header: `fSeekFree` gives its offset and `fNbytesFree` its
total length including the key
([File header §5.4](FileHeader.md#54-fseekfree-fnbytesfree-nfree)).

Its key has the file's own name and title and the class `"TFile"`, the same as
the root directory record and the key-list record. As for the key list, `fSeekFree`
is therefore the only way to find it
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

An entry uses 8-byte bounds when its `fLast` exceeds 2000000000, and its version
word is then `1001` instead of `1` (`root/io/io/src/TFree.cxx:111`). Only `fLast`
is tested, and the comparison is strict.

Each entry is self-describing, so 10-byte and 18-byte entries may be interleaved
in one record. A reader MUST size each entry from its own version word.

This is a fourth large-file flag, independent of the three in
[Directory §3](Directory.md#3-three-independent-large-file-flags).

## 3. Reading the list

> **The list is terminated by a sentinel, not by a count or a length.** ROOT reads
> entries up to and including the first one whose `fLast > fEND`
> (`root/io/io/src/TFile.cxx:1978-1997`).

Neither of the other two apparent bounds is sufficient on its own:

- **`nfree` in the header is advisory.** It is written correctly, since the header
  is written after the free record, but ROOT never reads it back for this purpose
  (`root/io/io/src/TFile.cxx:743`). A reader MAY use it as a cross-check.
- **The payload length is not a reliable bound.** `WriteFree` may zero-fill the
  tail of the payload when allocating the record consumed one of the entries it had
  already counted (`root/io/io/src/TFile.cxx:2649-2658`). A length-driven parse can
  then produce a spurious all-zero entry.

A robust reader iterates while bytes remain within `fObjlen`, stops after the first
entry with `fLast > fEND`, and compares the count with `nfree`.

## 4. The in-place marker

Each freed span is also marked in place: its first four bytes are overwritten
with a negative `i32`, in the position where a live record's `fNbytes` would be
(`root/io/io/src/TFile.cxx:1496-1519`).

A live record always has `fNbytes > 0`, because `TKey` rejects a negative value
(`root/io/io/src/TKey.cxx:1229-1234`), so the sign alone tells the two apart.

Three properties of the magnitude are easy to get wrong:

- **It is the length of the merged span**, not of the record that was
  deleted. Adjacent free space is coalesced, so one marker can cover several
  formerly separate records.
- **It is written at the merged span's first byte**, which may precede the deleted
  record's own start.
- **It is clamped to 2000000000** (`root/io/io/src/TFile.cxx:1505`). For a span
  longer than that, the marker understates the length and only the free list is
  correct.

The rest of the span is not cleared. It holds stale bytes, often most of the
deleted record including a recognisable key. A reader MUST advance by the
magnitude and MUST NOT attempt to interpret what follows.

### 4.1 A second producer of markers

`TKey::Create` also writes one. When a new record is placed in a gap strictly
larger than it needs, the remainder gets its own negative marker at
`fSeekKey + fNbytes` (`root/io/io/src/TKey.cxx:554-563`).

### 4.2 The marker may be missing

The four-byte write is unchecked (`root/io/io/src/TFile.cxx:1512-1517`), and
ROOT's comment there notes that the marker may be absent on disk, in which case
only recovery suffers. A reader that walks the chain and finds a key where the free
list says there is a gap SHOULD trust the free list.

> **ROOT's writers do write it, with one historical exception.** In both corpora,
> 17 of 252 files have interior free space, 149 gaps in all: 4 bytes at the
> smallest, 64 at the median and 10908 at the largest. In 16 of the 17 files the
> markers and the free list agree on offset and on length; the seventeenth is the
> exception below. On the
> write side the marker is **fixed**
> ([Writing a file §2.3](../06-writing/WritingFiles.md#23-updating-the-free-list-and-the-three-outcomes)),
> and invariant 6 requires it rather than merely allowing it.

The exception is RNTuple's writer before ROOT 6.36. `TKey::Create` puts the
remainder's marker in the key's own buffer, four bytes past the key, and the
marker reaches the file only because `TKey::WriteFile` writes those four bytes as
well (`root/io/io/src/TKey.cxx:1501`). RNTuple writes its `RBlob` keys itself,
bypassing `TKey::WriteFile` ([RNTuple notes §1](../05-rntuple/NOTES.md)). When
its `TFile` writer placed a blob in a free slot larger than the blob, the
remainder therefore got no marker. ROOT fixed this in commit `d328b598b32`
(2025-01-29, *"properly write the free slot's nbytes"*), first released in
6.36.00; the pinned release writes the four bytes itself
(`root/tree/ntuple/src/RMiniFile.cxx:1177-1182`). The remainder is still in the
free list, so a reader that follows the SHOULD above reads such a file
correctly. A reader that walks markers alone loses the chain at the first
unmarked remainder.

> Witnessed by `uproot-physlite-rntuple_v1-0-0-0.root` of the foreign corpus
> (`gen/foreign/MANIFEST.sha256`), an ATLAS file written by ROOT 6.34/04 whose
> `RBlob` keys are the historical exception of
> [Records §3.6](Record.md#36-fseekpdir-and-the-packed-fpidoffset). Seven of its
> eight interior free entries are marked. The unmarked one, `(200897, 200923)`,
> begins where the 126-byte `RBlob` at 200771 ends: a 153-byte slot, a 126-byte
> blob and 27 bytes left over. The four bytes at 200897 are stale (`03 10 dc 00`), and a
> marker-only walk reads them as a 51 MB record.

### 4.3 Directories are never freed

`TKey::Delete` refuses to delete a key marked as a directory
(`root/io/io/src/TKey.cxx:584-594`), so a directory record never becomes a gap.

## 5. The trailing segment

The last entry is not a sentinel by design. It is the unallocated tail of the
address space, and `fEND` is derived from it:

```
fEND == (last entry).fFirst
```

`WriteHeader` sets `fEND` this way (`root/io/io/src/TFile.cxx:2671-2672`). As
records are appended, the entry's `fFirst` advances.

A new file starts with this entry alone, spanning `fBEGIN` to 2000000000
(`root/io/io/src/TFile.cxx:691`).

> **`fLast` does not jump straight to 4000000000 when a file passes 2 GB.** It
> grows in 1 GB steps (2000000000, then 3000000000, then 4000000000, and so on),
> one step each time a record no longer fits (`root/io/io/src/TKey.cxx:537-539`,
> `root/io/io/src/TFree.cxx:148-152`). `root/io/doc/TFile/freesegments.md` states
> otherwise.

Once `fLast` exceeds 2000000000, that entry alone switches to the 18-byte form
(§2.1).

## 6. Deleting the last record shrinks the file

If the freed span ends at `fEND - 1`, `fEND` is moved back to the span's start
(`root/io/io/src/TFile.cxx:1510`), so the space is reclaimed rather than recorded
as an interior gap.

ROOT does not truncate the file on disk, so `fEND` may be less than the physical
file size, and the bytes beyond `fEND` are stale. A reader MUST bound its record
walk by `fEND`, not by the file size.

The reverse, `fEND` greater than the file size, means the file is truncated, and
ROOT attempts recovery
(`root/io/io/src/TFile.cxx:889-905`).

## 7. Reading

To walk the chain, per [Records §1](Record.md#1-the-record-chain):

1. Start at `fBEGIN`, with the list already read (below). The list is located
   from the header, not from the chain.
2. If an interior entry of the list begins here, this is a free span whatever the
   four bytes hold: advance past `fLast` and repeat (§4.2).
3. Read an `i32`. If zero, the file is corrupt; stop.
4. If negative, this is a free span: advance by its magnitude and repeat.
5. Otherwise parse the key and advance by `fNbytes`.
6. Stop at `fEND`.

To read the list:

1. If `fSeekFree` is not greater than `fBEGIN`, there is no list to read; a value
   of 0 means the free list was never written (`FileHeader.md` §5.4). This is
   ROOT's own test (`root/io/io/src/TFile.cxx:771`). It is not a test for an
   unclosed file: a non-zero `fSeekFree` proves nothing about a clean close.
2. Read the record at `fSeekFree`, of `fNbytesFree` bytes.
3. From the payload start, read entries: a version word, then two bounds of 4 or 8
   bytes according to whether the version exceeds 1000.
4. Stop after the first entry whose `fLast > fEND`, or when the payload has no
   room for another entry (§3). ROOT has only the first test
   (`root/io/io/src/TFile.cxx:1989-1995`), so a list with no entry past `fEND`
   would run it off the payload.

## 8. Invariants

1. `fEND` equals the last entry's `fFirst`.
2. The last entry's `fLast > fEND`, and is at least 2000000000. Above that it is a
   multiple of 1000000000 (§5), except in a recovered file: `TFile::Recover` sets
   it to `fEND + 1000000000` once `fEND` has passed 2000000000
   (`root/io/io/src/TFile.cxx:2189-2191`), and the next `Write` persists that.
3. `nfree` in the header equals the number of entries. This is advisory only
   (`FileHeader.md` §5.4): every ROOT-written file available satisfies it, but
   g4tools writes 0 for a two-entry list.
4. `fSeekFree` equals the free record's own `fSeekKey`, and `fNbytesFree` its
   `fNbytes`.
5. Entries are in strictly ascending order, non-overlapping and non-adjacent;
   adjacent spans are always merged (`root/io/io/src/TFree.cxx:66-95`).
6. Every interior entry's `fFirst` holds a negative `i32` whose magnitude is
   `min(fLast - fFirst + 1, 2000000000)` — except, in a file written before ROOT
   6.36, an entry beginning where an `RBlob` key ends (§4.2).
7. Every negative marker found while walking the chain corresponds to an entry in
   the list.
8. Live records and free spans partition `[fBEGIN, fEND)` exactly.
9. `fEND <= physical file size`.
10. Every interior entry is at least four bytes long. ROOT's allocator takes a
    span only when it fits exactly or has more than three bytes to spare
    (`root/io/io/src/TFree.cxx:137`), so a remainder is never 1, 2 or 3 bytes.
    Four bytes is what the §4 marker needs. Measured over 159 interior segments
    across both corpora and `data/`, the smallest is four bytes.

Invariants 6 and 7 can legitimately fail, because a `MakeFree` write may have been
lost (§4.2). A recovered file's list is built by plain appends instead of the
merging insert, so it may violate 5 as well, and above 2 GB the multiple in 2.
Nothing on disk says a file was recovered (`kRecovered` is an in-memory bit), so
a reader that finds these violations on a file over 2 GB SHOULD suspect a
recovery rather than a corrupt list. No file available here is both recovered and
over 2 GB, so this is read from the source.

## 9. Errata

Against `root/io/doc/TFile/freesegments.md` and `gap.md`:

| # | Claim | Actually |
|---|---|---|
| 1 | `freesegments.md`: a final segment "beginning at file end and ending before 2000000000" | It begins at `fEND` (`fEND` is derived from it), and `fLast` is 2000000000, inclusive (§5) |
| 2 | `freesegments.md`: past 2 GB "the last segment ends with 4000000000" | `fLast` grows in 1 GB steps, so a 2.5 GB file has 3000000000 (§5) |
| 3 | — | No termination rule is given. ROOT stops at the first entry with `fLast > fEND`; `nfree` is written but never read back (§3) |
| 4 | — | The payload may carry zero-filled slack, so a length-driven parse can yield a bogus entry (§3) |
| 5 | — | The widening condition is `fLast > 2000000000`, tested on `fLast` alone, and each entry is self-describing (§2.1) |
| 6 | — | `fNbytesFree` counts the whole record, key included |
| 7 | `gap.md`: the first four bytes hold "the negative of the number of bytes in the segment" | True, but the magnitude is that of the whole **merged** span, clamped to 2000000000, and written at the merged span's start (§4) |
| 8 | — | A second producer exists: `TKey::Create` marks the remainder of a partially reused gap (§4.1) |
| 9 | — | Deleting the last record shrinks `fEND`; the marker write is unchecked and may be absent; the span's remaining bytes are stale, not cleared; directory records are never freed (§4.2, §4.3, §6) |
| 10 | *This document, until 2026-09-22*: "in practice it is never missing" | ROOT 6.34's RNTuple writer left it out after every `RBlob` it placed in a larger free slot, fixed in 6.36.00 (§4.2) |
| 11 | *This document, until 2026-09-23*: invariant 3 said ROOT 4.00 wrote `nfree` 0 | g4tools does; every ROOT-written file available has the right count (`FileHeader.md` §5.4) |

## 10. A suspected bug in recovery

`TFile::Recover`'s gap branch decrements its cursor *before* constructing the
`TFree`, so the registered span appears to be `[start + |n|, start + 2|n| - 1]`
rather than `[start, start + |n| - 1]`
(`root/io/io/src/TFile.cxx:2143-2144`).

The bug is apparent, not confirmed: this path has not been exercised here. It
affects only the recovery of a damaged file, not normal reading. It needs
verifying and, if real, reporting upstream.

## 11. Reference files

| Case | Exercises |
|---|---|
| `container/gap` | A deleted record: an interior entry and its in-place marker |
| `container/gap-reused` | The space being used again: an exact fit, a partial fit, and the remainder marked at its start |
| `container/file-minimal` | The trailing entry alone, `fFirst == fEND`, `fLast == 2000000000` |
| `container/reopen-gap` | A free list inherited by a second session: an entry the update fills exactly, and one it leaves |
| `written/reopen-reuse` | The same file written by this project, byte for byte |
| `written/reopen-add` | Three released spans coalescing into one 243-byte entry during a close |

No fixture covers the large entry form or an `fLast` above 2000000000, since both
need a file over 2 GB, which cannot be committed. Both are measured instead on
eight published files read by range request, including the interleaving of the two
entry widths in one record; see
[Large files §4](LargeFiles.md#4-the-wide-free-list-entry) and §6 there.
