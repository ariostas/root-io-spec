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

> **Notation: `sizeof(s)` is a counted string's size on disk, not its character
> count** — `len(s) + 1`, or `len(s) + 5` when `len(s) > 254`
> ([Conventions §5.1](../00-conventions.md#51-counted-string)). Every length formula
> below uses it, and ROOT's own arithmetic is `TString::Sizeof()`
> (`root/core/base/src/TString.cxx:1405-1410`). Getting it wrong by one is the error
> §4 warns about: a reader then parses the directory record at the wrong offset with
> no complaint.

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
exact-size free span, then the first span **whose whole length exceeds
`nbytes + 3`** — that is, one with more than three bytes to spare — and only then
extends the last one (`root/io/io/src/TFree.cxx:132-152`). Partially
filling a span leaves a remainder that must be marked in place with a negative
`fNbytes` — [Free segments §4](../01-container/FreeSegments.md#4-the-in-place-marker)
— and getting that wrong corrupts the record chain for every reader. A writer that
only appends never has to.

## 3. The procedure

For a file with one directory and `k` data records. §5 says what changes when the
file has subdirectories; the steps below are numbered as if it does, and a
one-directory writer simply has one directory to place at step 5 and one key list
at step 6.

1. **Reserve** bytes 0–99 and write nothing into 63–99. ROOT's
   `WriteHeader` emits 63 bytes in the small layout
   (`root/io/io/src/TFile.cxx:2707-2709`) and never touches the rest, so on a
   freshly created file they are zero — but they are *unspecified*
   ([File header §7](../01-container/FileHeader.md#7-padding)), and on a file
   ROOT has updated they hold whatever was there before.
2. **Place the root directory record** at 100 (§4). Its payload needs
   `fNbytesKeys` and `fSeekKeys`, which are not known yet; compute its *length*
   now and fill the values in at step 8.
3. **Place each data record** (§6), in whatever order the writer likes. This is
   where the objects are streamed: [Writing an object](WritingObjects.md).
4. **Place each subdirectory record** (§5) at the point in that order where the
   directory is created, which is before anything it contains. Two of its fields
   have to wait for step 6, exactly as the root directory's do.
5. **Place the `StreamerInfo` record** (§7), if the writer emits one.
6. **Place one key list per saved directory** (§8, §5.4), the root's first: for
   each, a count and then a verbatim copy of the key of every record that
   directory owns.
7. **Place the free list** (§9). Its own length has to be known before its single
   entry can name `fEND` — it is 10 bytes of payload plus a key, so this is
   arithmetic, not a fixed point.
8. **Fill in** every directory payload (`fNbytesKeys`, `fSeekKeys`) and the
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
| `fObjlen` | `sizeof(name) + sizeof(title) + 60` | derived |
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

`fNbytesName = fKeylen + sizeof(name) + sizeof(title)`
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

Its payload carries **no name and title** (`root/io/io/src/TDirectoryFile.cxx:162`),
so its `fNbytesName` is `fKeylen` alone (`:158`); its key's `fSeekParent` is the
parent's `fSeekDir` (`:155`); and its key's class name on disk is the literal
string **`TDirectory`**, not `TDirectoryFile` (`root/io/io/src/TKey.cxx:676-679`,
with `Sizeof` hard-coding 11 for it at `:1374`). §5 is the procedure, and names
three more.

## 5. A subdirectory

A subdirectory is a record of the same 60-byte shape as §4's, plus a key list of
its own, plus one entry in its parent's. Nothing about it is new machinery — and
that is the trap: six things in §4's record mean something different here, and a
writer that reaches this section by symmetry from §4 gets all six wrong.

| | Root directory | Subdirectory |
|---|---|---|
| key `fClassName` | the file's class, `TFile` | **`TDirectory`** — 5.2 |
| key `fName`, `fTitle` | the file's | **the directory's own** |
| payload prefix | the name and title, repeated | **none** |
| `fNbytesName` | `fKeylen` + both strings | **`fKeylen` alone** |
| `fSeekParent` | 0 | **the mother's `fSeekDir`** |
| key `fSeekPdir` | 0, an artifact (§4.1) | the mother's `fSeekDir` |

The last two are the same number and are stored twice, in two structures, by two
different pieces of ROOT. They are not interchangeable on read — a reader must use
`fSeekPdir` and never `fSeekParent`, for the version reason in
[Directories §4.3](../01-container/Directory.md#43-fseekparent-do-not-use-it-for-parentage)
— but a writer producing a current file writes the same value into both.

### 5.1 The record comes first, with two of its own fields still zero

ROOT writes a subdirectory's record the moment the directory is created, from
`TDirectoryFile::InitDirectoryFile` (`root/io/io/src/TDirectoryFile.cxx:147-164`):
it builds the key, takes `fSeekDir` from `key->GetSeekKey()` and `fNbytesName`
from `key->GetKeylen()` (`:158-159`), fills the payload and writes the record
(`:161-164`). At that moment `fNbytesKeys` and `fSeekKeys` are **0** — they are
zeroed at construction (`:317`, `:320`) and nothing assigns them until the
directory is saved.

So the record is written twice and the second write is an overwrite; 5.3 is why
that is safe. A writer that lays out a whole file in one pass does not have to
reproduce the two-phase write, but it does have to reproduce its *consequence*:

> **A subdirectory's record is placed where the directory was created — before
> everything the directory contains** — while the `fSeekKeys` inside it points
> forward, past every data record in the file, to a key list written at the end.
> Its `fNbytesKeys` and `fSeekKeys` are the only fields of the record that a
> single-pass writer cannot fill in when it places the record.

That is also the order that makes a byte comparison against a ROOT-written file
possible, and this project's writer follows it (5.6).

### 5.2 The record

| Field | Value | Kind |
|---|---|---|
| key `fClassName` | **`TDirectory`**, always. The class is `TDirectoryFile` and has been since 5.16; ROOT substitutes the shorter name on the way out so that older releases can read the file (`root/io/io/src/TKey.cxx:676-679`), sizes the key to match with a hard-coded 11 (`:1374-1375`), and maps it back on the way in (`:1290-1293`). Writing the real class name produces a key whose length disagrees with its `fKeylen` — [Directories §6.5](../01-container/Directory.md#65-an-images-length-is-what-it-parses-to-never-its-fkeylen) is the file that did it | fixed |
| key `fName` | the directory's name. ROOT rejects one containing `/` (`root/io/io/src/TDirectoryFile.cxx:95-99`), an empty one (`:100-104`), and one the mother already has a key for (`:113-116`) — in each case creating nothing at all | free, with those three constraints |
| key `fTitle` | the directory's title. `mkdir` defaults it to the name (`root/io/io/src/TDirectoryFile.cxx:1275`), which is why a ROOT-written subdirectory almost always has `fName == fTitle` | free |
| key `fSeekPdir` | the mother's `fSeekDir` — `fBEGIN` for a directory at the top level | derived |
| key `fObjlen` | 60 | fixed |
| key `fKeylen` | `26 + sizeof("TDirectory") + sizeof(fName) + sizeof(fTitle)`, so `43 + len(name) + len(title)` for names under 255 bytes | derived |
| payload | the 60 bytes below, and **nothing before them** | — |

The payload is `Directory.md` §2's field sequence, with no `TNamed` ahead of it:

| Bytes | Value | Kind |
|---|---|---|
| `i16` | 5, `TDirectoryFile`'s class version (`root/io/io/inc/TDirectoryFile.h:131`) | fixed |
| `u32` | `fDatimeC`, set once when the directory is created | free |
| `u32` | `fDatimeM`, re-set on every rewrite of these 60 bytes (`root/io/io/src/TDirectoryFile.cxx:2175`). Equal to `fDatimeC` in a single-pass write | free |
| `i32` | `fNbytesKeys` — the whole key-list record, key included; **0 until the directory is saved** | derived |
| `i32` | `fNbytesName` = the key's `fKeylen`, and nothing more | derived |
| `i32` | `fSeekDir` = this record's own offset | derived |
| `i32` | `fSeekParent` = the mother's `fSeekDir` | derived |
| `i32` | `fSeekKeys`, or 0 (5.4) | derived |
| `u16` + 16 bytes | the directory's own UUID, distinct from the file's and from every other directory's | free |
| 12 bytes | zero | fixed |

**The payload is 60 bytes whether or not the offsets are 64-bit.**
`TDirectoryFile::Sizeof` counts 22 + 4 + 4 + 18 + 12 with no reference to the
large-file flag (`root/io/io/src/TDirectoryFile.cxx:1725-1735`), because in the
large layout the 12 trailing bytes are consumed by the high halves of the three
offsets rather than written as padding. That is not a curiosity: it is what makes
5.3's rewrite possible, and it is why a writer must emit the 12 zero bytes rather
than stopping after the UUID.

> **`TDirectoryFile` has two writers of these 60 bytes and they disagree about
> when to set the large-file flag.** `FillBuffer`, which produces the record,
> tests the three stored offsets (`root/io/io/src/TDirectoryFile.cxx:751-760`);
> `Streamer`'s write branch tests the file's `fEND` (`:1827`). A writer follows
> `FillBuffer` — `Streamer` is reached only when a `TDirectoryFile` is streamed
> as an object, which the directory machinery never does.
> [Directories §3](../01-container/Directory.md#3-three-independent-large-file-flags)
> collects the switch alongside the other two.

### 5.3 The record never moves, and a directory key is never freed

Every later write of those 60 bytes is an overwrite in place. `WriteDirHeader`
seeks `fSeekDir + fNbytesName` and writes `Sizeof()` bytes
(`root/io/io/src/TDirectoryFile.cxx:2177-2180`); it allocates nothing, builds no
key, and touches the free list not at all. And `TKey::Delete` refuses outright to
free a directory key, with ROOT's own explanation
(`root/io/io/src/TKey.cxx:586-594`):

> *"TDirectoryFile assumes that its location on file never change (for example
> updates are partial) and never checks if the space might have been released and
> thus over-write any data that might have been written there."*

Two consequences for a writer:

1. **`nfree` stays 1.** A file created from nothing has one free entry however
   many directories it holds. Nothing in §5 produces a freed span, so §9's
   single-entry free list is still right.
2. **What a *re-save* frees is the key list, not the record.** `WriteKeys` marks
   the previous key-list record free before writing the new one
   (`root/io/io/src/TDirectoryFile.cxx:2201-2203`). A writer that never updates a
   file never reaches this, and a reader must be ready for it in files ROOT has
   updated.

> Measured on `data/written/nested-subdir.root`, which ROOT reopens in `UPDATE`
> mode in the case's `verify.C` and writes one object into `alpha`. Afterwards
> `alpha`'s record is still at 401, `beta`'s still at 610, and `beta`'s key list —
> untouched, because `beta` was not modified — still at 1634. Everything else moved:
> `alpha`'s key list, the root's and the free-segment record were freed and written
> again further down, `alpha`'s new and longer list was allocated into the span the
> first two vacated, and the 13 bytes left over at the end of it are marked free.
> `nfree` is 3. The two directory records are the only records in the file ROOT
> rewrote without moving.

### 5.4 One key list per directory, keyed by the directory's own name

A subdirectory's key list is §8's record with three of its key's fields carrying a
different value:

| Field | Value |
|---|---|
| key `fClassName` | `TDirectory` — the same substitution as 5.2, so the key-list record and the directory record are **indistinguishable by their keys** |
| key `fName`, `fTitle` | the directory's own, not the file's and not a fixed string. Two records in the file therefore carry the directory's name |
| key `fSeekPdir` | the directory's **own** `fSeekDir`, because `WriteKeys` passes `this` as the mother (`root/io/io/src/TDirectoryFile.cxx:2213`) — not the mother's offset, which is the one thing about this record that looks like a mistake and is not |
| payload | `i32` count, then each of *this* directory's records' keys verbatim |

What goes in which list: a subdirectory's key image goes in its **parent's** list,
and its contents go in its **own**. Nothing appears in both. So the top-level list
of a file with one subdirectory holding one object names two records, not three.

The lists are written after every data record, and **a parent's precedes its
children's**: `TDirectoryFile::Save` calls `SaveSelf` and then recurses
(`root/io/io/src/TDirectoryFile.cxx:1575-1587`). Nothing reads that order — every
list is found by an absolute `fSeekKeys` — so it is free, and reproducing it is
what keeps a diff against a ROOT-written file short.

**A directory with no key list is legal.** `fSeekKeys` and `fNbytesKeys` stay 0
for a directory ROOT created and never saved, because the constructor clears
`fModified` (`root/io/io/src/TDirectoryFile.cxx:133`) and `SaveSelf` writes
nothing without it (`:1649`). A *saved* empty directory has a list whose payload
is the four-byte count `0`. The two states are
[Directories §6.4](../01-container/Directory.md#64-empty-and-unsaved-directories),
and `tools/rootwrite.py` takes the choice as an argument — an unsaved directory
that holds anything is refused, because its keys would be unreachable.

### 5.5 Cycles, and the one field whose meaning changed

`fCycle` is per directory, not per file: it counts keys of the same name **in the
same directory** (`root/io/io/src/TDirectoryFile.cxx:225-255`), so two objects
called `h` in two directories are both cycle 1. `AppendKey` inserts a repeated
name *before* the existing one, so a directory's key list holds higher cycles
first.

`fSeekParent` is the field to be careful about, and only on the reading side:
before ROOT 6.38 it held the **top** directory's offset for a directory at any
depth, not the mother's
([Directories §4.3](../01-container/Directory.md#43-fseekparent-do-not-use-it-for-parentage)).
A writer emits the mother's offset, which is what current ROOT writes and what
current ROOT expects; the old value is something a *reader* meets.

### 5.6 The check this section passes

`data/written/nested-subdir.root` holds two nested subdirectories and one
`TObjString` at each of three levels — the same content as the ROOT-written
fixture `data/container/directories.root`, with a file name chosen to be the same
length. The two files are **1854 bytes each, with identical record boundaries, and
every byte agrees except three fields that this layer marks free**: each key's
`fDatime`, the three UUIDs, and the file's own name where it is stored. Every
offset, every `fNbytesName`, every `fSeekParent` and every `fSeekKeys` in both
subdirectory records is therefore ROOT's own value, not this project's reading of
`TDirectoryFile.cxx`.

`tools/test_write.py` makes that comparison record by record, and `verify.C` adds
5.3's update test.

## 6. A data record

| Field | Value | Kind |
|---|---|---|
| `fNbytes` | `fKeylen` + the payload as stored | derived |
| `fVersion` | 4, `TKey`'s class version (`root/io/io/inc/TKey.h:118`); **+1000** if the file's `fEND` exceeded 2000000000 *before* this key was allocated (`root/io/io/src/TKey.cxx:456-457`) | derived |
| `fObjlen` | the payload's length **before** compression | derived |
| `fDatime` | any time; ROOT writes the wall clock (`root/io/io/src/TKey.cxx:531`) | free |
| `fKeylen` | `26 + sizeof(fClassName) + sizeof(fName) + sizeof(fTitle)` (`root/io/io/src/TKey.cxx:1370`) | derived |
| `fCycle` | 1 for the first key of a given name in the directory, then 2, 3 … (`root/io/io/src/TDirectoryFile.cxx:225-255`) | derived |
| `fSeekKey` | this record's own offset | derived |
| `fSeekPdir` | the owning directory's `fSeekDir`, so 100 here | derived |
| `fClassName` | the class of the object in the payload | fixed by the object |
| `fName`, `fTitle` | the key's name and title; what ROOT passes is the object's `GetName()`/`GetTitle()` unless the caller named it | free |

**There is no compression flag.** A reader decides that the payload is compressed
from `fObjlen > fNbytes - fKeylen` and nothing else (`root/io/io/src/TKey.cxx:827`).
So the two fields are not independent bookkeeping: `fObjlen` equal to
`fNbytes - fKeylen` *means* stored as-is. A writer that compresses and forgets to
leave `fObjlen` at the uncompressed length hands its zip stream to the streamer as
though it were object data. [Writing an object](WritingObjects.md) has the block format;
[Compression](../01-container/Compression.md) is the reading side.

ROOT only attempts compression when the file's level is above 0 **and** the payload
exceeds 256 bytes (`root/io/io/src/TKey.cxx:262-264`), which is why small records
in a compressed file are stored uncompressed. A writer may compress whatever it
likes; a reader cannot tell the difference between "too small to bother" and "the
writer chose not to".

## 7. The `StreamerInfo` record

A key whose class is **`TList`** and whose name is **`StreamerInfo`**
(`root/io/io/src/TFile.cxx:3554`), holding one `TStreamerInfo` per class the file's
objects were written with, and — if any exist — a trailing `TList` of I/O rules
named `listOfRules` (`root/io/io/src/TFile.cxx:3527-3549`). Its offset and length
go in the header as `fSeekInfo` and `fNbytesInfo`, and **it is deliberately not in
the key list**: `WriteStreamerInfo` removes it (`root/io/io/src/TFile.cxx:3555`)
after the constructor has added it.

What goes inside is [Writing an object](WritingObjects.md). The question this section
answers is whether a writer needs it at all.

### 7.1 ROOT does not need it, and will not say so

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

### 7.2 So write one

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

## 8. The key list

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

## 9. The free list

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
(`root/io/io/src/TFile.cxx:1990-1995`). A last entry whose `fLast` does not exceed
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

## 10. The header

Written last. Every field, with where the value comes from:

| Field | Value | Kind |
|---|---|---|
| magic | `root` | fixed |
| `fVersion` | the layout the file uses. ROOT writes its own release as an integer — 64004 for 6.40.04 (`root/io/io/src/TFile.cxx:423`) — and adds 1000000 when `fEND` exceeds 2000000000 (`root/io/io/src/TFile.cxx:2679`) | free, with constraints — §10.1 |
| `fBEGIN` | 100. `TFile::Init` assigns `kBEGIN` unconditionally (`root/io/io/src/TFile.cxx:682`, `:204`) and nothing in ROOT writes another value | fixed |
| `fEND` | the first byte of the last free segment, which for a create-only writer is the file's length | derived |
| `fSeekFree`, `fNbytesFree` | the free record's offset and total length | derived |
| `nfree` | the number of entries in it — 1. Written from the live list (`root/io/io/src/TFile.cxx:2676`) and never read back for parsing (§9) | derived, advisory |
| `fNbytesName` | as in the root directory record, §4 | derived |
| `fUnits` | 4 in the small layout, and 8 alongside the large-file flag (`root/io/io/src/TFile.cxx:2679`). ROOT stores what it reads (`root/io/io/src/TFile.cxx:745`) but **never acts on it** — `TFile::Init` decides the layout from `fVersion` alone | fixed by convention |
| `fCompress` | `algorithm × 100 + level` (`root/io/io/inc/TFile.h:477-485`), 0 for none | free |
| `fSeekInfo`, `fNbytesInfo` | the `StreamerInfo` record's offset and length, or 0 for none (§7) | derived |
| UUID | a `u16` 1 followed by 16 bytes (`root/io/io/src/TFile.cxx:2706`) | free |
| 63…100 | not written | — |

### 10.1 What `fVersion` commits a writer to

It is read as a feature gate, not as provenance, and two thresholds matter:

- `fVersion >= 1000000` selects the wide header, and 40000 selects the 60-byte
  directory record rather than the 48-byte one
  (`root/io/io/src/TDirectoryFile.cxx:785`). A writer emitting the layout this
  document describes must be at or above 40000 and below 1000000.
- `fVersion < 30000` makes `TBufferFile` force every version word to -1 and rebuild
  every class as emulated (`root/io/io/src/TBufferFile.cxx:3560-3565`).

Beyond that the value is the writer's to choose, and the choice has one visible
consequence: §7.1's missing-streamer-info warning fires only when `fVersion` differs
from the running ROOT's. Writing the version of the ROOT release whose layout is
being emitted is the honest choice, and it is what `tools/rootwrite.py` does.

## 11. Determinism, which ROOT also offers

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

## 12. One file, byte by byte

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

## 13. Invariants a writer should check on its own output

The reading documents' `Invariants` sections are the full list, and
`tools/check_invariants.py` runs them. These are the ones a writer gets wrong:

1. `fEND` equals the file's length, and equals the last free entry's `fFirst`.
2. The last free entry's `fLast` is strictly greater than `fEND` (§9).
3. `fNbytesName` equals the root directory record's `fKeylen` plus the two counted
   strings that follow it, and equals the copy inside the record.
4. `fSeekKeys` plus `fNbytesKeys` does not exceed `fEND`, and the record at
   `fSeekKeys` has exactly `fNbytesKeys` bytes.
5. Every key image in the key list is byte-identical to the first `fKeylen` bytes of
   the record at its own `fSeekKey`.
6. Every record's `fNbytes` equals `fKeylen` plus the stored payload, and
   `fObjlen == fNbytes - fKeylen` **iff** the payload is stored uncompressed (§6).
7. Walking from `fBEGIN` by `fNbytes` reaches exactly `fEND`, with no record
   overlapping another and no unclaimed bytes between them.
8. `fSeekPdir` is 0 in the root directory record's key and `fBEGIN` in every other
   key of that directory (§4.1).
9. Every subdirectory's `fNbytesName` equals its own record's `fKeylen`, and its
   fields therefore begin where its key ends (§5.2).
10. Every subdirectory's key spells its class `TDirectory`, and the key's
    `fKeylen` accounts for that spelling and not for `TDirectoryFile` — four bytes
    apart, and the difference is invisible to ROOT
    ([Directories §6.5](../01-container/Directory.md#65-an-images-length-is-what-it-parses-to-never-its-fkeylen)).
11. Every subdirectory appears in exactly one key list — its parent's — and its own
    key list holds only what it contains (§5.4).
12. A key-list record's key carries the `fSeekDir` of the directory that **owns**
    the list, not of that directory's parent (§5.4). It is the only thing in the
    record that says which directory it belongs to.

Items 1, 2, 5, 6, 7 and 9 to 12 are the ones with no detector on ROOT's side at
all (§14), and all four of the new ones are checked by
`tools/check_invariants.py` — as
[Directories §9](../01-container/Directory.md#9-invariants) 3, 11 and 13, 8, and
12 respectively. The remaining obligation in §5.4 is not a property of a file and
so is not among them: a directory left with `fSeekKeys` 0 while it owns records
produces keys nothing can reach, and `tools/rootwrite.py` refuses it rather than
checking for it afterwards.

## 14. What ROOT does not check

A writing specification has to say where the guard rails are missing, because the
absent check is what makes a bug permanent. Each row is a mistake ROOT reads
without complaint.

| Mistake | Why it is silent |
|---|---|
| `fObjlen` inconsistent with `fNbytes - fKeylen` | there is no codec flag; the inequality *is* the flag (`root/io/io/src/TKey.cxx:827`) |
| a key image in the key list disagreeing with the record's own key | the image is what frames the read; the record's own header is consulted only for its version word (`root/io/io/src/TKey.cxx:845-847`) |
| `fSeekKey` in an image pointing at the wrong record | validated only as an offset inside the file (`root/io/io/src/TDirectoryFile.cxx:1453-1465`) |
| `fSeekPdir` not matching the owning directory | never checked on the read path; only `TFile::Recover` filters on it (`root/io/io/src/TFile.cxx:2171`), so the file reads and is unrecoverable |
| `fUnits` disagreeing with the layout | read into the member and used for nothing (`root/io/io/src/TFile.cxx:739-759`) |
| `nfree` disagreeing with the free list | never read back (§9) |
| a last free entry whose `fFirst` is below the live data | reads fine; the next writer overwrites a record (§9) |
| `fNbytesName` off by a few | only range-checked, `10 <= fNbytesName <= 10000` (`root/io/io/src/TFile.cxx:841-844`) |
| a root directory record whose `fSeekDir` is not 100 | the record's value overwrites the one `Init` guessed (`root/io/io/src/TFile.cxx:767` then `:814`), and the next directory save writes the directory header there |
| a gap not preceded by a negative `fNbytes` | the record-chain walk reads a leading `i32` and treats a negative as a gap; anything else ends the walk (`root/io/io/src/TFile.cxx:1675-1688`) |

The checks ROOT *does* make are all in `TFile::Init`: the magic and a minimum
length (`root/io/io/src/TFile.cxx:714-730`), `0 <= fBEGIN <= fEND`
(`:760-766`), that the directory record fits (`:781-788`), `fNbytesName`'s range
(`:841-844`), and `fEND <= filesize` (`:881-887`) — truncation being the one
condition it refuses to open.

## 15. Errata

Against ROOT's shipped documentation in `root/io/doc/TFile/`, on points specific to
writing. The reading-side errata are in the documents named in each row.

| # | Claim | Reality |
|---|---|---|
| 1 | `README.md`: "The file header is fixed length (64 bytes in the current release.)" | `fBEGIN` is 100 and the fields occupy 63 bytes (`root/io/io/src/TFile.cxx:204`, `:2707-2709`). The 64 was the 3.02.06 value; `header.md`'s own table disagrees with `README.md` |
| 2 | `README.md`: "A file always contains exactly one FreeSegments data record" | Zero is normal in a file that was created and not closed — `fSeekFree` is 0 at creation (`root/io/io/src/TFile.cxx:704`) — and the record moves on every rewrite, the old copy becoming a gap (`root/io/io/src/TFile.cxx:2599-2601`) |
| 3 | Silent on the top-directory / subdirectory asymmetry | The top record's payload carries a `TNamed` and a subdirectory's does not, so `fNbytesName` means two different things (`root/io/io/src/TFile.cxx:702` against `root/io/io/src/TDirectoryFile.cxx:158`). §4.2 and §5.2 |
| 4 | Silent on `fSeekPdir = 0` in the file's own key | An artifact of the order of two statements (§4.1), and it affects `TFile::Recover` |
| 5 | Silent on write ordering | `TFile::Close` and `TFile::Write` put the `StreamerInfo` record on opposite sides of the key list (§3), and both orders occur in ROOT-written files |
| 6 | `freesegments.md` does not state the rule a writer needs | The last entry's `fLast` must exceed `fEND`, because that is the parse terminator (`root/io/io/src/TFile.cxx:1990-1995`), not because of any length |

## 16. Reference files

| File | What it demonstrates |
|---|---|
| `data/written/objstring.root` | the whole of §3, in 656 bytes (§12) |
| `data/container/file-minimal.root` | the same shape written by ROOT, with a `StreamerInfo` record |
| `data/container/gap.root` | what §2 avoids: a partially filled free span, and the negative marker in it |
| `data/container/directories.root` | the subdirectory shape of §5, and the file `data/written/nested-subdir.root` is compared against record for record |
| `data/written/nested-subdir.root` | §5 written: two nesting levels, three key lists, and ROOT writing into one of them (§5.3) |

`tools/check_write.py --root` is the conformance test: it rebuilds each written
file, compares it byte for byte, runs `tools/check_invariants.py` over it, and has
ROOT open it and confirm the values.
