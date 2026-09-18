# Writing a file

How to produce a ROOT file that ROOT opens, lists and reads: the header, the root
directory record, a data record, the key list and the free list, in the order they
have to be written.

Prerequisites: [Conventions](../00-conventions.md), and the reading side of what
this produces — [File header](../01-container/FileHeader.md),
[Records and keys](../01-container/Record.md),
[Directories](../01-container/Directory.md),
[Free segments](../01-container/FreeSegments.md). This document does not repeat
their field tables; it says which value to put in each field and when.

Scope, per [the layer's index](index.md#4-what-is-not-specified): a file created
from nothing, in the small-file layout, with one directory. Nothing here updates an
existing file.

## 1. The shape of the problem

Three facts decide the order of everything else.

1. **The header cannot be written last, and cannot be written first either.** It
   holds `fEND`, `fSeekFree` and `fNbytesFree`, none of which is known until every
   record is placed — but ROOT writes it at creation time anyway, with
   `fSeekFree = 0` (`root/io/io/src/TFile.cxx:704-706`), and rewrites it at close
   (`root/io/io/src/TFile.cxx:1027`). A writer that emits a file in one pass can
   simply reserve the first 100 bytes and fill them in at the end, which is what
   `tools/rootwrite.py` does.
2. **`fEND` is not "the length of the file". It is the first byte of the last free
   segment**, and ROOT computes it that way on every header write:
   `fEND = lastfree->GetFirst()` (`root/io/io/src/TFile.cxx:2671-2672`). In a file
   that has only ever grown, the two coincide. Keeping the free list as the
   authority — rather than a length counter — is what makes the two agree.
3. **Every record's address comes from the free list.** `TKey::Create` asks
   `TFree::GetBestFree` for a span, takes its `fFirst` as `fSeekKey`, and advances
   that span (`root/io/io/src/TKey.cxx:521-541`). A create-only writer has exactly
   one span, `[100, 2000000000]`, so "allocate" means "take `fFirst`, then add the
   record's length to it".

## 2. Allocation, in the one case that matters

A fresh file's free list holds a single entry from `fBEGIN` to `kStartBigFile`
(`root/io/io/src/TFile.cxx:691`), and `kStartBigFile` is 2000000000
(`root/io/io/inc/TFile.h:278`). Writing a record of `n` bytes at `fFirst` advances
`fFirst` by `n` and `fEND` with it, and raises `fLast` by 1000000000 whenever `fEND`
would otherwise pass it (`root/io/io/src/TKey.cxx:534-541`).

So for a writer that never deletes anything:

| | |
|---|---|
| first record | at 100 |
| each subsequent record | immediately after the previous one, no alignment, no gap |
| the single free entry at the end | `fFirst = fEND`, `fLast = 2000000000` |
| `nfree` | 1 |

**Gaps are the other case, and this layer avoids it.** ROOT's allocator prefers an
exact-size free span, then the first span with more than `nbytes + 3` spare, and
only then extends the last one (`root/io/io/src/TFree.cxx:133-152`). Partially
filling a span leaves a remainder that must be marked in place with a negative
`fNbytes` — [Free segments §4](../01-container/FreeSegments.md#4-the-in-place-marker)
— and getting that wrong corrupts the record chain for every reader. A writer that
only appends never has to.

## 3. The procedure

For a file with one directory and `k` data records:

1. **Reserve** bytes 0–99 and write nothing into 63–99. ROOT's
   `WriteHeader` emits 63 bytes in the small layout
   (`root/io/io/src/TFile.cxx:2707-2709`) and never touches the rest, so on a
   freshly created file they are zero — but they are *unspecified*
   ([File header §7](../01-container/FileHeader.md#7-padding)), and on a file
   ROOT has updated they hold whatever was there before.
2. **Place the root directory record** at 100 (§4). Its payload needs
   `fNbytesKeys` and `fSeekKeys`, which are not known yet; compute its *length*
   now and fill the values in at step 7.
3. **Place each data record** (§5), in whatever order the writer likes. This is
   where the objects are streamed: `06-writing/WritingObjects.md`.
4. **Place the `StreamerInfo` record** (§6), if the writer emits one.
5. **Place the key list** (§7): one entry per data record, by copying each key.
6. **Place the free list** (§8). Its own length has to be known before its single
   entry can name `fEND` — it is 10 bytes of payload plus a key, so this is
   arithmetic, not a fixed point.
7. **Fill in** the root directory payload (`fNbytesKeys`, `fSeekKeys`) and the
   header (`fEND`, `fSeekFree`, `fNbytesFree`, `nfree`, `fSeekInfo`,
   `fNbytesInfo`).

**ROOT's own order differs between two of its entry points, and neither is
canonical.** `TFile::Close` writes the streamer infos, then the key lists, then the
free list (`root/io/io/src/TFile.cxx:1000`, `:1019`, `:1024-1027`); `TFile::Write`
writes the key lists first and the streamer infos second
(`root/io/io/src/TFile.cxx:2507-2510`). Both appear in files ROOT has written, and
a reader cannot tell: both records are found by an absolute offset, never by
scanning. The order above follows `Close`.

## 4. The root directory record

It is a key whose payload is the file's name and title *again*, followed by the
directory's own fields. That repetition is the thing to get right: it is why
`fNbytesName` is larger than the key.

| Field | Value | Kind |
|---|---|---|
| `fClassName` | `TFile` — the class of the object being written, which is the file itself (`root/io/io/src/TFile.cxx:701`) | fixed |
| `fName` | the file's name. ROOT stores the path string it was handed, so this is normally the path as given | free |
| `fTitle` | the file's title, truncated to 32000 bytes (`root/io/io/src/TKey.cxx:459`) | free |
| `fSeekKey` | 100 | fixed |
| `fSeekPdir` | **0** | fixed — §4.1 |
| `fCycle` | 1 | fixed |
| `fObjlen` | `len(name) + len(title) + 60`, the counted-string lengths | derived |
| `fNbytes` | `fKeylen + fObjlen`; this record is never compressed (`root/io/io/src/TKey.cxx:203-209` has no zip path) | derived |

Its payload, in order:

| Bytes | Value |
|---|---|
| counted string | the name again |
| counted string | the title again |
| `i16` | 5, `TDirectoryFile`'s class version (`root/io/io/inc/TDirectoryFile.h:131`) |
| `u32` | `fDatimeC`, the creation time |
| `u32` | `fDatimeM`, the modification time |
| `i32` | `fNbytesKeys` — the whole key-list record, key included |
| `i32` | `fNbytesName` — the same value as in the header |
| `i32` | `fSeekDir` = 100 |
| `i32` | `fSeekParent` = 0 |
| `i32` | `fSeekKeys` |
| `u16` + 16 bytes | the directory's UUID, which for the root directory is the file's |
| 12 bytes | zero (`Directory.md` §5) |

`fNbytesName = fKeylen + len(name) + len(title)`
(`root/io/io/src/TFile.cxx:702`), and the payload after the two strings is exactly
60 bytes (`root/io/io/src/TDirectoryFile.cxx:1725`). Those two numbers are what a
reader uses to find the directory's fields: it seeks `fSeekDir + fNbytesName`
(`root/io/io/src/TFile.cxx:804-805`), which lands past the repeated strings. Get
`fNbytesName` wrong by one and a reader parses the record at the wrong offset with
no complaint — ROOT checks only `10 <= fNbytesName <= 10000`
(`root/io/io/src/TFile.cxx:841-844`).

### 4.1 `fSeekPdir` is 0 here, and it is an artifact

Every other key in the file carries its directory's `fSeekDir` in `fSeekPdir`. The
root directory record carries 0 — not because 0 means "no parent", but because
`TKey::Create` reads `fMotherDir->GetSeekDir()` (`root/io/io/src/TKey.cxx:565`)
during the constructor call at `root/io/io/src/TFile.cxx:701`, and `fSeekDir` is not
assigned until `:703`, two lines later. A writer should reproduce the 0: ROOT's
`TFile::Recover` selects candidate keys by `seekpdir == fSeekDir`
(`root/io/io/src/TFile.cxx:2171`), so a "corrected" 100 would put the file's own
key in the recovery list.

### 4.2 A subdirectory record is not the same shape

Out of scope here, and worth one paragraph because the differences are exactly the
ones a writer would get wrong by symmetry. A subdirectory's record payload carries
**no name and title** (`root/io/io/src/TDirectoryFile.cxx:162`), so its
`fNbytesName` is `fKeylen` alone (`:158`); its key's `fSeekParent` is the parent's
`fSeekDir` (`:155`); and its key's class name on disk is the literal string
**`TDirectory`**, not `TDirectoryFile` (`root/io/io/src/TKey.cxx:676-681`, with
`Sizeof` hard-coding 11 for it at `:1373`).

## 5. A data record

| Field | Value | Kind |
|---|---|---|
| `fNbytes` | `fKeylen` + the payload as stored | derived |
| `fVersion` | 4, `TKey`'s class version (`root/io/io/inc/TKey.h:118`); **+1000** if the file's `fEND` exceeded 2000000000 *before* this key was allocated (`root/io/io/src/TKey.cxx:456-457`) | derived |
| `fObjlen` | the payload's length **before** compression | derived |
| `fDatime` | any time; ROOT writes the wall clock (`root/io/io/src/TKey.cxx:531`) | free |
| `fKeylen` | `26 + len(fClassName) + len(fName) + len(fTitle)`, counted-string lengths (`root/io/io/src/TKey.cxx:1370`) | derived |
| `fCycle` | 1 for the first key of a given name in the directory, then 2, 3 … (`root/io/io/src/TDirectoryFile.cxx:225-255`) | derived |
| `fSeekKey` | this record's own offset | derived |
| `fSeekPdir` | the owning directory's `fSeekDir`, so 100 here | derived |
| `fClassName` | the class of the object in the payload | fixed by the object |
| `fName`, `fTitle` | the key's name and title; what ROOT passes is the object's `GetName()`/`GetTitle()` unless the caller named it | free |

**There is no compression flag.** A reader decides that the payload is compressed
from `fObjlen > fNbytes - fKeylen` and nothing else (`root/io/io/src/TKey.cxx:823`).
So the two fields are not independent bookkeeping: `fObjlen` equal to
`fNbytes - fKeylen` *means* stored as-is. A writer that compresses and forgets to
leave `fObjlen` at the uncompressed length hands its zip stream to the streamer as
though it were object data. `06-writing/WritingObjects.md` has the block format;
[Compression](../01-container/Compression.md) is the reading side.

ROOT only attempts compression when the file's level is above 0 **and** the payload
exceeds 256 bytes (`root/io/io/src/TKey.cxx:262-264`), which is why small records
in a compressed file are stored uncompressed. A writer may compress whatever it
likes; a reader cannot tell the difference between "too small to bother" and "the
writer chose not to".

## 6. The `StreamerInfo` record

A key whose class is **`TList`** and whose name is **`StreamerInfo`**
(`root/io/io/src/TFile.cxx:3554`), holding one `TStreamerInfo` per class the file's
objects were written with, and — if any exist — a trailing `TList` of I/O rules
named `listOfRules` (`root/io/io/src/TFile.cxx:3527-3549`). Its offset and length
go in the header as `fSeekInfo` and `fNbytesInfo`, and **it is deliberately not in
the key list**: `WriteStreamerInfo` removes it (`root/io/io/src/TFile.cxx:3555`)
after the constructor has added it.

What goes inside is `06-writing/WritingObjects.md`. The question this section
answers is whether a writer needs it at all.

### 6.1 ROOT does not need it, and will not say so

For a class ROOT has compiled in, the file's streamer info is **optional**.
`TKey::ReadObj` calls the object's own compiled `Streamer`
(`root/io/io/src/TKey.cxx:874`), and when the class has no info for the version on
disk, `TBufferFile::ReadClassBuffer` builds one from the dictionary provided the
version word matches the compiled class, or is 1
(`root/io/io/src/TBufferFile.cxx:3627-3651`). No warning: the diagnostic on that
path needs `gDebug > 0`.

Measured, and this is the part worth knowing:

- `data/written/objstring.root` has `fSeekInfo = 0` and ROOT reads its `TObjString`
  correctly and silently.
- Taking a ROOT-written `TH1F` file and zeroing `fSeekInfo` and `fNbytesInfo` in the
  header leaves ROOT reading the histogram correctly — same entries, same mean,
  same title.
- **`tools/coverage_probe.py` cannot read either file.** This project's reader is
  streamer-info-driven, so with no info in the file it has nothing to decode with:
  it reports `no streamer info for TObjString` and gives up. So do other
  third-party readers, for the same reason.

There is one warning, and it fires on the wrong condition. `TFile::Init` complains
`no StreamerInfo found in %s therefore preventing schema evolution` only when the
file's `fVersion` differs from the running ROOT's and is above 30000, and the file
has keys (`root/io/io/src/TFile.cxx:928-941`). A writer that stamps the current
release's version number into `fVersion` **silences it**. Both halves confirmed
with `tools/rootwrite.py`: the same file with `fVersion = 64004` opens in ROOT
6.40.04 in silence, and with `fVersion = 63000` prints the warning — and reads
correctly either way.

### 6.2 So write one

A writer that wants its files read by anything other than ROOT has to emit the
record. Two further reasons:

- **Schema evolution needs it.** Without an info the reader has only its own
  compiled layout, so a file written today is readable only by a ROOT whose classes
  still match.
- **An empty list is a legitimate value, and it is what ROOT writes for a file with
  no streamer-info-driven objects** (`root/io/io/src/TFile.cxx:3543-3544`). An
  empty `TList` record with a valid `fSeekInfo` says "nothing here"; `fSeekInfo = 0`
  says "never closed".

`FileHeader.md` invariant 8 allows `fSeekInfo <= fBEGIN`, so the file without one
is conforming. It is just less readable than it looks.

## 7. The key list

A record whose payload is the count, then each data record's key **verbatim**
([Directory §6](../01-container/Directory.md#6-key-lists)):

| Field | Value |
|---|---|
| key `fClassName` | `TFile` — the same key shape as the root directory record, which is why neither can be identified by its key (`Directory.md` §6.2) |
| key `fName`, `fTitle` | the file's own, again |
| key `fSeekPdir` | 100 |
| `fObjlen` | `4 + Σ fKeylen` over the keys listed |
| payload | `i32` count, then the first `fKeylen` bytes of each record, unchanged |

What is *not* in it: the root directory record's own key, the key list's own key,
the free list's, and the `StreamerInfo` record's. In a one-directory file with `k`
data records, the count is `k`.

The images are copies, not summaries. Each carries its own `fSeekKey`, and that is
how a reader gets from the list to the record. ROOT validates only that the offset
is inside the file (`root/io/io/src/TDirectoryFile.cxx:1453-1465`), so an image that
disagrees with the record it points at is read from the image — silently. Copy the
bytes; do not re-derive them.

## 8. The free list

One record, located from the header, holding the spans that are not live data
([Free segments](../01-container/FreeSegments.md)). For a file written once:

| Field | Value |
|---|---|
| key | the same `TFile`-classed shape again, `fSeekPdir` 100 |
| `fObjlen` | 10 — one entry |
| entry version | `1`; `1001` only if the entry's `fLast` exceeds 2000000000 (`root/io/io/src/TFree.cxx:111`) |
| `fFirst` | `fEND` |
| `fLast` | 2000000000 |

**The last entry is a sentinel, and it is load-bearing.** ROOT ignores `nfree` and
reads entries until one has `fLast > fEND`, including that one
(`root/io/io/src/TFile.cxx:801-808`). A last entry whose `fLast` does not exceed
`fEND` makes ROOT keep parsing past the end of the payload, into whatever follows.
With `fFirst = fEND` and `fLast = 2000000000` the condition holds for any file
smaller than 2 GB.

**ROOT reads the list only when the file is opened writable**
(`root/io/io/src/TFile.cxx:769-775`), which is why a `fSeekFree` of 0 draws
`file %s probably not closed, cannot read free segments` on an update and nothing
at all on a read. It also means a read-only open never validates this record: the
first thing to exercise it is the next write.

The second reason to get it right is therefore the *next* writer. ROOT's allocator falls back
to the last entry when nothing fits, and allocates at its `fFirst`
(`root/io/io/src/TFree.cxx:149-152`, `root/io/io/src/TKey.cxx:532`). A last entry
whose `fFirst` is below the end of the live data means the first object anyone adds
to the file overwrites a record — and then `WriteHeader` sets `fEND` to that
`fFirst` (`root/io/io/src/TFile.cxx:2671-2672`), truncating the file logically. A
file can therefore be perfectly readable and still be a trap.

## 9. The header

Written last. Every field, with where the value comes from:

| Field | Value | Kind |
|---|---|---|
| magic | `root` | fixed |
| `fVersion` | the layout the file uses. ROOT writes its own release as an integer — 64004 for 6.40.04 (`root/io/io/src/TFile.cxx:423`) — and adds 1000000 when `fEND` exceeds 2000000000 (`root/io/io/src/TFile.cxx:2679`) | free, with constraints — §9.1 |
| `fBEGIN` | 100. `TFile::Init` assigns `kBEGIN` unconditionally (`root/io/io/src/TFile.cxx:682`, `:204`) and nothing in ROOT writes another value | fixed |
| `fEND` | the first byte of the last free segment, which for a create-only writer is the file's length | derived |
| `fSeekFree`, `fNbytesFree` | the free record's offset and total length | derived |
| `nfree` | the number of entries in it — 1. Written from the live list (`root/io/io/src/TFile.cxx:2676`) and never read back for parsing (§8) | derived, advisory |
| `fNbytesName` | as in the root directory record, §4 | derived |
| `fUnits` | 4. Set once at construction (`root/io/io/src/TFile.cxx:424`) and **never read** — `TFile::Init` decides the layout from `fVersion` alone | fixed by convention |
| `fCompress` | `algorithm × 100 + level` (`root/io/io/inc/TFile.h:477-485`), 0 for none | free |
| `fSeekInfo`, `fNbytesInfo` | the `StreamerInfo` record's offset and length, or 0 for none (§6) | derived |
| UUID | a `u16` 1 followed by 16 bytes (`root/io/io/src/TFile.cxx:2706`) | free |
| 63…100 | not written | — |

### 9.1 What `fVersion` commits a writer to

It is read as a feature gate, not as provenance, and two thresholds matter:

- `fVersion >= 1000000` selects the wide header, and 40000 selects the 60-byte
  directory record rather than the 48-byte one
  (`root/io/io/src/TDirectoryFile.cxx:785`). A writer emitting the layout this
  document describes must be at or above 40000 and below 1000000.
- `fVersion < 30000` makes `TBufferFile` force every version word to -1 and rebuild
  every class as emulated (`root/io/io/src/TBufferFile.cxx:3560-3565`).

Beyond that the value is the writer's to choose, and the choice has one visible
consequence: §6.1's missing-streamer-info warning fires only when `fVersion` differs
from the running ROOT's. Writing the version of the ROOT release whose layout is
being emitted is the honest choice, and it is what `tools/rootwrite.py` does.

## 10. Determinism, which ROOT also offers

Two fields default to values that change on every run: `fDatime` in each key
(`root/io/io/src/TKey.cxx:531`) and the UUID in the header and each directory
record. A writer has no reason to consult a clock, and `tools/rootwrite.py` takes
both as inputs — which is what makes `data/written/` byte-reproducible where the
rest of `data/` cannot be.

ROOT has the same feature: opening a file with the URL option `?reproducible` sets
`TFile::kReproducible` (`root/io/io/src/TFile.cxx:417-418`), which writes an
all-zero UUID (`root/io/io/src/TFile.cxx:2703-2704`) and a fixed `TDatime(1)` in
every key (`root/io/io/src/TKey.cxx:652-655`). A reader must therefore treat both
fields as carrying no information: a zero UUID and a 1995 timestamp are normal.

The packed timestamp is six bit fields in one 32-bit word — year biased by 1995,
then month, day, hour, minute, second
(`root/core/base/src/TDatime.cxx:392`), and the year is rejected below 1995
(`root/core/base/src/TDatime.cxx:387-390`) — so the earliest representable value is
1995 and the range ends in 2058.

## 11. One file, byte by byte

`data/written/objstring.root`, 656 bytes, produced by
`gen/written/objstring/build.py`: one `TObjString` holding `hello`, no streamer
infos, the fixed timestamp and UUID. Every value below is asserted in
`gen/written/objstring/case.toml`.

| Offset | Length | Contents |
|---|---|---|
| 0 | 63 | the header: `fEND` 656, `fSeekFree` 556, `fNbytesFree` 100, `nfree` 1, `fNbytesName` 148, `fUnits` 4, `fCompress` 0, `fSeekInfo` 0 |
| 63 | 37 | not written |
| 100 | 90 | the root directory record's key: `TFile`, the file's name and title, `fSeekKey` 100, `fSeekPdir` 0 |
| 190 | 58 | the name and title again — 148 − 90 |
| 248 | 60 | the directory's fields: version 5, `fNbytesKeys` 160, `fNbytesName` 148, `fSeekDir` 100, `fSeekParent` 0, `fSeekKeys` 396, the UUID, 12 zero bytes |
| 308 | 66 | the data record's key: `TObjString`, `str`, `fSeekKey` 308, `fSeekPdir` 100 |
| 374 | 22 | the object: byte count `0x40000012`, version 1, a `TObject` base, `05 hello` |
| 396 | 90 | the key-list record's key: `TFile` again, `fObjlen` 70 |
| 486 | 70 | the count 1, then the 66 bytes at 308 verbatim |
| 556 | 90 | the free-list record's key: `TFile` again, `fObjlen` 10 |
| 646 | 10 | version 1, `fFirst` 656, `fLast` 2000000000 |

`fEND` is 656, which is the file's length and the free entry's `fFirst`. Compare
`data/container/file-minimal.root`, the same shape written by ROOT: it is 1094
bytes, and the difference is entirely the `StreamerInfo` record and the longer
names.

## 12. Invariants a writer should check on its own output

The reading documents' `Invariants` sections are the full list, and
`tools/check_invariants.py` runs them. These are the ones a writer gets wrong:

1. `fEND` equals the file's length, and equals the last free entry's `fFirst`.
2. The last free entry's `fLast` is strictly greater than `fEND` (§8).
3. `fNbytesName` equals the root directory record's `fKeylen` plus the two counted
   strings that follow it, and equals the copy inside the record.
4. `fSeekKeys` plus `fNbytesKeys` does not exceed `fEND`, and the record at
   `fSeekKeys` has exactly `fNbytesKeys` bytes.
5. Every key image in the key list is byte-identical to the first `fKeylen` bytes of
   the record at its own `fSeekKey`.
6. Every record's `fNbytes` equals `fKeylen` plus the stored payload, and
   `fObjlen == fNbytes - fKeylen` **iff** the payload is stored uncompressed (§5).
7. Walking from `fBEGIN` by `fNbytes` reaches exactly `fEND`, with no record
   overlapping another and no unclaimed bytes between them.
8. `fSeekPdir` is 0 in the root directory record's key and `fBEGIN` in every other
   key of that directory (§4.1).

Items 1, 2, 5, 6 and 7 are the ones with no detector on ROOT's side at all (§13).

## 13. What ROOT does not check

A writing specification has to say where the guard rails are missing, because the
absent check is what makes a bug permanent. Each row is a mistake ROOT reads
without complaint.

| Mistake | Why it is silent |
|---|---|
| `fObjlen` inconsistent with `fNbytes - fKeylen` | there is no codec flag; the inequality *is* the flag (`root/io/io/src/TKey.cxx:823`) |
| a key image in the key list disagreeing with the record's own key | the image is what frames the read; the record's own header is consulted only for its version word (`root/io/io/src/TKey.cxx:845-847`) |
| `fSeekKey` in an image pointing at the wrong record | validated only as an offset inside the file (`root/io/io/src/TDirectoryFile.cxx:1453-1465`) |
| `fSeekPdir` not matching the owning directory | never checked on the read path; only `TFile::Recover` filters on it (`root/io/io/src/TFile.cxx:2171`), so the file reads and is unrecoverable |
| `fUnits` disagreeing with the layout | read into the member and used for nothing (`root/io/io/src/TFile.cxx:739-759`) |
| `nfree` disagreeing with the free list | never read back (§8) |
| a last free entry whose `fFirst` is below the live data | reads fine; the next writer overwrites a record (§8) |
| `fNbytesName` off by a few | only range-checked, `10 <= fNbytesName <= 10000` (`root/io/io/src/TFile.cxx:841-844`) |
| a root directory record whose `fSeekDir` is not 100 | the record's value overwrites the one `Init` guessed (`root/io/io/src/TFile.cxx:767` then `:814`), and the next directory save writes the directory header there |
| a gap not preceded by a negative `fNbytes` | the record-chain walk reads a leading `i32` and treats a negative as a gap; anything else ends the walk (`root/io/io/src/TFile.cxx:1675-1688`) |

The checks ROOT *does* make are all in `TFile::Init`: the magic and a minimum
length (`root/io/io/src/TFile.cxx:714-730`), `0 <= fBEGIN <= fEND`
(`:760-766`), that the directory record fits (`:781-788`), `fNbytesName`'s range
(`:841-844`), and `fEND <= filesize` (`:881-887`) — truncation being the one
condition it refuses to open.

## 14. Errata

Against ROOT's shipped documentation in `root/io/doc/TFile/`, on points specific to
writing. The reading-side errata are in the documents named in each row.

| # | Claim | Reality |
|---|---|---|
| 1 | `README.md`: "The file header is fixed length (64 bytes in the current release.)" | `fBEGIN` is 100 and the fields occupy 63 bytes (`root/io/io/src/TFile.cxx:204`, `:2707-2709`). The 64 was the 3.02.06 value; `header.md`'s own table disagrees with `README.md` |
| 2 | `README.md`: "A file always contains exactly one FreeSegments data record" | Zero is normal in a file that was created and not closed — `fSeekFree` is 0 at creation (`root/io/io/src/TFile.cxx:704`) — and the record moves on every rewrite, the old copy becoming a gap (`root/io/io/src/TFile.cxx:2599-2601`) |
| 3 | Silent on the top-directory / subdirectory asymmetry | The top record's payload carries a `TNamed` and a subdirectory's does not, so `fNbytesName` means two different things (`root/io/io/src/TFile.cxx:702` against `root/io/io/src/TDirectoryFile.cxx:158`). §4.2 |
| 4 | Silent on `fSeekPdir = 0` in the file's own key | An artifact of the order of two statements (§4.1), and it affects `TFile::Recover` |
| 5 | Silent on write ordering | `TFile::Close` and `TFile::Write` put the `StreamerInfo` record on opposite sides of the key list (§3), and both orders occur in ROOT-written files |
| 6 | `freesegments.md` does not state the rule a writer needs | The last entry's `fLast` must exceed `fEND`, because that is the parse terminator (`root/io/io/src/TFile.cxx:801-808`), not because of any length |

## 15. Reference files

| File | What it demonstrates |
|---|---|
| `data/written/objstring.root` | the whole of §3, in 656 bytes (§11) |
| `data/container/file-minimal.root` | the same shape written by ROOT, with a `StreamerInfo` record |
| `data/container/gap.root` | what §2 avoids: a partially filled free span, and the negative marker in it |
| `data/container/directories.root` | the subdirectory shape of §4.2 |

`tools/check_write.py --root` is the conformance test: it rebuilds each written
file, compares it byte for byte, runs `tools/check_invariants.py` over it, and has
ROOT open it and confirm the values.
