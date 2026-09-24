# Writing a file

How to produce a ROOT file that ROOT opens, lists and reads: the header, the root
directory record, a data record, the key list and the free list, in the order they
have to be written.

Prerequisites: [Conventions](../00-conventions.md), and the reading side of what
this produces: [File header](../01-container/FileHeader.md),
[Records and keys](../01-container/Record.md),
[Directories](../01-container/Directory.md),
[Free segments](../01-container/FreeSegments.md). This document does not repeat
their field tables; it says which value to put in each field and when.

Scope, per [the layer's index](index.md#4-what-is-not-specified): a file created
from nothing in the small-file layout, with any number of directories (§1 to §12),
and an existing file reopened and added to (§13), including an update that crosses
2 GB (§13.8). Two writers updating one file at once are out of scope (§13.10).

> **Notation: `sizeof(s)` is a counted string's size on disk, not its character
> count**: `len(s) + 1`, or `len(s) + 5` when `len(s) > 254`
> ([Conventions §5.1](../00-conventions.md#51-counted-string)). Every length formula
> below uses it, and ROOT's own arithmetic is `TString::Sizeof()`
> (`root/core/base/src/TString.cxx:1405-1410`). An off-by-one here is the error §4
> warns about: a reader then parses the directory record at the wrong offset with
> no complaint.

## 1. The shape of the problem

Three facts determine the order of everything else.

1. **The header depends on values known only at the end.** It holds `fEND`,
   `fSeekFree` and `fNbytesFree`, none of which is known until every record is
   placed. ROOT writes it at creation time anyway, with `fSeekFree = 0`
   (`root/io/io/src/TFile.cxx:704-706`), and rewrites it at close
   (`root/io/io/src/TFile.cxx:1027`). A writer that emits a file in one pass can
   reserve the first 100 bytes and fill them in at the end, as
   `tools/rootwrite.py` does.
2. **`fEND` is not the length of the file. It is the first byte of the last free
   segment**, and ROOT computes it that way on every header write:
   `fEND = lastfree->GetFirst()` (`root/io/io/src/TFile.cxx:2671-2672`). In a file
   that has only ever grown, the two coincide. Treating the free list, rather than
   a length counter, as the authority keeps them in agreement.
3. **Every record's address comes from the free list.** `TKey::Create` asks
   `TFree::GetBestFree` for a span, takes its `fFirst` as `fSeekKey`, and advances
   that span (`root/io/io/src/TKey.cxx:521-541`). A create-only writer has only
   one span, `[100, 2000000000]`, so allocating means taking `fFirst`, then adding
   the record's length to it.

## 2. Allocation

Every record in the file (a data record, a directory record, the `StreamerInfo`
record, each key list, and the free list itself) gets its offset from the same
procedure. A writer that only appends can reduce it to "the next free byte", which
is §2.1. §2.2 is the general case, which a writer needs as soon as anything in the
file is deleted or rewritten.

**The free list is the allocator's state.** It is written to the file at the end
([§9](#9-the-free-list)), but it exists throughout, and every placement both reads
and updates it.

### 2.1 The append-only case

A fresh file's free list holds a single entry from `fBEGIN` to `kStartBigFile`
(`root/io/io/src/TFile.cxx:691`), and `kStartBigFile` is 2000000000
(`root/io/io/inc/TFile.h:278`). Writing a record of `n` bytes at `fFirst` advances
`fFirst` by `n` and `fEND` with it, and raises `fLast` by 1000000000 whenever `fEND`
would otherwise pass it (`root/io/io/src/TKey.cxx:534-541`).

For a writer that never deletes anything:

| | |
|---|---|
| first record | at 100 |
| each subsequent record | immediately after the previous one, no alignment, no gap |
| the single free entry at the end | `fFirst = fEND`, `fLast = 2000000000` |
| `nfree` | 1 |

### 2.2 Choosing an offset

Given a record of `n` bytes (the key and its payload together, since the key is
what is being placed; `root/io/io/src/TKey.cxx:516`), walk the free list, which is
kept sorted ascending by `fFirst`:

1. If any entry's length is **exactly** `n`, take it and stop. An exact match
   wins from anywhere in the list, even after a longer entry that would also have
   served (`root/io/io/src/TFree.cxx:133-135`).
2. Otherwise take the **first** entry whose length is **strictly greater than
   `n + 3`** (`root/io/io/src/TFree.cxx:137`). The list is address-ordered, so
   this is the lowest-addressed segment with room to spare.
3. If neither matched, raise the last entry's `fLast` by 1000000000 and take that
   entry (`root/io/io/src/TFree.cxx:148-152`). This is unreachable in an ordinary
   file, because the last entry runs to `kStartBigFile` and step 2 has already
   taken it.

An entry's length is `fLast - fFirst + 1`: **`fLast` is inclusive**
([Free segments §2](../01-container/FreeSegments.md#2-the-free-segment-record)).

> **The `+ 3` is not rounding.** It guarantees that a partial fit leaves at least
> four bytes, the width of the marker that has to go there. A segment one, two or
> three bytes larger than the record is therefore **skipped** and stays unused.
> `container/gap-reused` was built around this rule: a 122-byte record was offered
> a 123-byte segment and was appended at the end of the file instead, three bytes
> short.

The record always starts at the chosen entry's `fFirst`
(`root/io/io/src/TKey.cxx:532`). There is no alignment and no offset within the
segment.

### 2.3 Updating the free list, and the three outcomes

Let `left = fLast - fFirst + 1 - n` be the chosen entry's remaining space.

| | What happens | What is written |
|---|---|---|
| **At the end of the file**: the chosen entry's `fFirst` is `fEND` | `fEND` becomes `fFirst + n`, and the entry's `fFirst` follows it. If `fEND` has passed `fLast`, raise `fLast` by 1000000000 (`root/io/io/src/TKey.cxx:534-539`) | nothing beyond the record |
| **Exact fit**: `left == 0` | the entry is **removed** from the list (`root/io/io/src/TKey.cxx:551-552`), so `nfree` falls | nothing beyond the record |
| **Partial fit**: `left >= 4` | the entry's `fFirst` becomes `fFirst + n`; `fLast` does not move | a **four-byte negative marker** at `fFirst + n`, holding `-left` |

`left` is never 1, 2 or 3, by §2.2 step 2.

**The marker is written together with the record.** ROOT puts it in the key's
buffer immediately after the payload (`root/io/io/src/TKey.cxx:559-561`) and
extends the write by four bytes to include it (`root/io/io/src/TKey.cxx:1501`), so
there is no second seek. A writer may write it separately, but it MUST write it: a
reader walking the record chain
([Records §1](../01-container/Record.md#1-the-record-chain)) has no other way to
know the gap is a gap, and will try to parse a key out of the stale bytes of
whatever was deleted.

> `container/gap-reused` shows all three: `exact` is restored into a segment of
> its own length, `lodger` takes the front of the 123 bytes `snug` released, and
> the remaining 19 bytes at 696 hold `-19` and appear in the free list as
> 696..714.

### 2.4 Releasing a record

This is the reverse operation. A writer needs it for anything it rewrites,
including its own key lists and free list, which are freed and reallocated rather
than edited in place.

Freeing the span `[first, last]` **merges it with its neighbours**
(`root/io/io/src/TFree.cxx:66-96`): if an existing entry ends at `first - 1` it is
extended, and if the entry *after* that one then begins at `last + 1` the two are
merged into one and the second is deleted; if an entry begins at `last + 1` its
`fFirst` moves back instead; otherwise a new entry is inserted in address order.

The marker is then written at the **merged** segment's first byte, not at
`first`. Freeing a record adjacent to an existing gap therefore **rewrites the
older gap's marker** and writes none of its own
(`root/io/io/src/TFile.cxx:1502-1518`). A writer must get two things right:

- the magnitude is the **whole merged length**, clamped to 2000000000
  ([Free segments §4](../01-container/FreeSegments.md#4-the-in-place-marker));
- if the freed span ends at `fEND - 1`, `fEND` moves back to the merged segment's
  first byte (`root/io/io/src/TFile.cxx:1510`). **The file is not truncated**,
  since ROOT has no call that shortens it, so `fEND` is then below the physical
  size and the bytes past it are stale.

A directory record is never freed
([§5.3](#53-the-record-never-moves-and-a-directory-key-is-never-freed)).

### 2.5 How much of this a writer must copy

The search in §2.2 is **ROOT's policy**, and a writer may allocate differently:
nothing on ROOT's read path consults the free list, and `nfree` is parsed into a
variable that is never used again (`root/io/io/src/TFile.cxx:681`, `:743`,
`:753`). The bookkeeping, however, is required: §2.3's marker, §2.4's merge, and
the trailing entry, whose `fLast` must exceed `fEND` because that is the condition
on which `TFile::ReadFree` ends its loop (`root/io/io/src/TFile.cxx:1990-1995`).
If a writer omits the trailing entry, ROOT reads the free list past its end.

Matching ROOT's search exactly is still useful, because it makes a byte comparison
against a ROOT-written file possible, and that comparison is how errors are found.

## 3. The procedure

For a file with one directory and `k` data records. §5 describes what changes when
the file has subdirectories. The steps below are numbered as if it does; a
one-directory writer has one directory to place at step 5 and one key list at
step 6.

1. **Reserve** bytes 0–99 and write nothing into 63–99. ROOT's
   `WriteHeader` emits 63 bytes in the small layout
   (`root/io/io/src/TFile.cxx:2707-2709`) and never touches the rest, so on a
   newly created file they are zero. They are, however, *unspecified*
   ([File header §7](../01-container/FileHeader.md#7-padding)), and on a file
   ROOT has updated they hold whatever was there before.
2. **Place the root directory record** at 100 (§4). Its payload needs
   `fNbytesKeys` and `fSeekKeys`, which are not known yet; compute its *length*
   now and fill the values in at step 8.
3. **Place each data record** (§6), in any order. This is where the objects are
   streamed: [Writing an object](WritingObjects.md).
4. **Place each subdirectory record** (§5) at the point in that order where the
   directory is created, which is before anything it contains. Two of its fields
   have to wait for step 6, as the root directory's do.
5. **Place the `StreamerInfo` record** (§7), if the writer emits one.
6. **Place one key list per saved directory** (§8, §5.4), the root's first: for
   each, a count and then a verbatim copy of the key of every record that
   directory owns.
7. **Place the free list** (§9). Its own length has to be known before its single
   entry can name `fEND`. For a file written once it is 10 bytes of payload plus
   a key, so this is simple arithmetic, not a fixed point. On an update it is
   not, and §9.1 says what ROOT does instead.
8. **Fill in** every directory payload (`fNbytesKeys`, `fSeekKeys`) and the
   header (`fEND`, `fSeekFree`, `fNbytesFree`, `nfree`, `fSeekInfo`,
   `fNbytesInfo`).

**ROOT uses a different order in two of its entry points, and neither is
canonical.** `TFile::Close` writes the streamer infos, then the key lists, then the
free list (`root/io/io/src/TFile.cxx:1000`, `:1019`, `:1024-1027`); `TFile::Write`
writes the key lists first and the streamer infos second
(`root/io/io/src/TFile.cxx:2507-2510`). Both orders appear in files ROOT has
written, and a reader cannot tell them apart, because both records are found by an
absolute offset, never by scanning. The order above follows `Close`.

## 4. The root directory record

It is a key whose payload is the file's name and title *again*, followed by the
directory's own fields. This repetition is the part to get right: it is why
`fNbytesName` is larger than the key.

| Field | Value | Kind |
|---|---|---|
| `fClassName` | `TFile`, the class of the object being written, which is the file itself (`root/io/io/src/TFile.cxx:701`) | fixed |
| `fName` | the file's name. ROOT stores the path string it was given, so this is normally the path as given | free |
| `fTitle` | the file's title, truncated to 32000 bytes (`root/io/io/src/TKey.cxx:459`) | free |
| `fSeekKey` | 100 | fixed |
| `fSeekPdir` | **0** | fixed, see §4.1 |
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
| `i32` | `fNbytesKeys`: the key-list record's total length, key included |
| `i32` | `fNbytesName`: the same value as in the header |
| `i32` | `fSeekDir` = 100 |
| `i32` | `fSeekParent` = 0 |
| `i32` | `fSeekKeys` |
| `u16` + 16 bytes | the directory's UUID, which for the root directory is the file's |
| 12 bytes | zero (`Directory.md` §5) |

`fNbytesName = fKeylen + sizeof(name) + sizeof(title)`
(`root/io/io/src/TFile.cxx:702`), and the payload after the two strings is 60
bytes (`root/io/io/src/TDirectoryFile.cxx:1725`). A reader uses those two numbers
to find the directory's fields: it seeks to `fSeekDir + fNbytesName`
(`root/io/io/src/TFile.cxx:804-805`), which is past the repeated strings. If
`fNbytesName` is off by one, a reader parses the record at the wrong offset with
no complaint, because ROOT checks only `10 <= fNbytesName <= 10000`
(`root/io/io/src/TFile.cxx:841-844`).

### 4.1 `fSeekPdir` is 0 here, and it is an artifact

Every other key in the file stores its directory's `fSeekDir` in `fSeekPdir`. The
root directory record stores 0. This is not because 0 means "no parent":
`TKey::Create` reads `fMotherDir->GetSeekDir()` (`root/io/io/src/TKey.cxx:565`)
during the constructor call at `root/io/io/src/TFile.cxx:701`, and `fSeekDir` is not
assigned until `:703`, two lines later. A writer should reproduce the 0: ROOT's
`TFile::Recover` selects candidate keys by `seekpdir == fSeekDir`
(`root/io/io/src/TFile.cxx:2171`), so a "corrected" 100 would put the file's own
key in the recovery list.

### 4.2 A subdirectory record is not the same shape

Its payload has **no name and title** (`root/io/io/src/TDirectoryFile.cxx:162`),
so its `fNbytesName` is `fKeylen` alone (`:158`); its key's `fSeekParent` is the
parent's `fSeekDir` (`:155`); and its key's class name on disk is the literal
string **`TDirectory`**, not `TDirectoryFile` (`root/io/io/src/TKey.cxx:676-679`,
with `Sizeof` hard-coding 11 for it at `:1374`). §5 gives the procedure and three
further differences.

## 5. A subdirectory

A subdirectory is a record with the same 60-byte fields as §4's, plus a key list of
its own, plus one entry in its parent's. It needs no new machinery, which makes it
easy to get wrong: six things in §4's record have a different value here, and a
writer that assumes symmetry with §4 gets all six wrong.

| | Root directory | Subdirectory |
|---|---|---|
| key `fClassName` | the file's class, `TFile` | **`TDirectory`** (5.2) |
| key `fName`, `fTitle` | the file's | **the directory's own** |
| payload prefix | the name and title, repeated | **none** |
| `fNbytesName` | `fKeylen` + both strings | **`fKeylen` alone** |
| `fSeekParent` | 0 | **the mother's `fSeekDir`** |
| key `fSeekPdir` | 0, an artifact (§4.1) | the mother's `fSeekDir` |

The last two are the same number, stored twice, in two structures, by two
different parts of ROOT. They are not interchangeable on read: a reader must use
`fSeekPdir` and never `fSeekParent`, for the version reason in
[Directories §4.3](../01-container/Directory.md#43-fseekparent-do-not-use-it-for-parentage).
A writer producing a current file writes the same value into both.

### 5.1 The record comes first, with two of its own fields still zero

ROOT writes a subdirectory's record when the directory is created, from
`TDirectoryFile::InitDirectoryFile` (`root/io/io/src/TDirectoryFile.cxx:147-164`):
it builds the key, takes `fSeekDir` from `key->GetSeekKey()` and `fNbytesName`
from `key->GetKeylen()` (`:158-159`), fills the payload and writes the record
(`:161-164`). At that point `fNbytesKeys` and `fSeekKeys` are **0**: they are
zeroed at construction (`:317`, `:320`) and nothing assigns them until the
directory is saved.

The record is therefore written twice, and the second write overwrites the first;
5.3 explains why that is safe. A writer that lays out a whole file in one pass does
not have to reproduce the two-phase write, but it does have to reproduce its
*consequence*:

> **A subdirectory's record is placed where the directory was created, before
> everything the directory contains**, while the `fSeekKeys` inside it points
> forward, past every data record in the file, to a key list written at the end.
> Its `fNbytesKeys` and `fSeekKeys` are the only fields of the record that a
> single-pass writer cannot fill in when it places the record.

This order also makes a byte comparison against a ROOT-written file possible, and
this project's writer follows it (5.6).

### 5.2 The record

| Field | Value | Kind |
|---|---|---|
| key `fClassName` | **`TDirectory`**, always. The class is `TDirectoryFile` and has been since 5.16; ROOT substitutes the shorter name when writing so that older releases can read the file (`root/io/io/src/TKey.cxx:676-679`), sizes the key to match with a hard-coded 11 (`:1374-1375`), and maps it back when reading (`:1290-1293`). Writing the real class name produces a key whose length disagrees with its `fKeylen`; [Directories §6.5](../01-container/Directory.md#65-an-images-length-is-what-it-parses-to-never-its-fkeylen) describes a file that did this | fixed |
| key `fName` | the directory's name. ROOT rejects one containing `/` (`root/io/io/src/TDirectoryFile.cxx:95-99`), an empty one (`:100-104`), and one the mother already has a key for (`:113-116`), and in each case creates nothing | free, with those three constraints |
| key `fTitle` | the directory's title. `mkdir` defaults it to the name (`root/io/io/src/TDirectoryFile.cxx:1275`), which is why a ROOT-written subdirectory almost always has `fName == fTitle` | free |
| key `fSeekPdir` | the mother's `fSeekDir`; `fBEGIN` for a directory at the top level | derived |
| key `fObjlen` | 60 | fixed |
| key `fKeylen` | 26 plus the three counted strings `"TDirectory"` (11 bytes), the name and the title, so `39 + len(name) + len(title)` when both are under 255 bytes; `alpha`/`alpha` in `nested-subdir.root` gives 49 | derived |
| payload | the 60 bytes below, and **nothing before them** | — |

The payload is `Directory.md` §2's field sequence, with no `TNamed` before it:

| Bytes | Value | Kind |
|---|---|---|
| `i16` | 5, `TDirectoryFile`'s class version (`root/io/io/inc/TDirectoryFile.h:131`) | fixed |
| `u32` | `fDatimeC`, set once when the directory is created | free |
| `u32` | `fDatimeM`, reset on every rewrite of these 60 bytes (`root/io/io/src/TDirectoryFile.cxx:2175`). Equal to `fDatimeC` in a single-pass write | free |
| `i32` | `fNbytesKeys`: the key-list record's total length, key included; **0 until the directory is saved** | derived |
| `i32` | `fNbytesName` = the key's `fKeylen`, and nothing more | derived |
| `i32` | `fSeekDir` = this record's own offset | derived |
| `i32` | `fSeekParent` = the mother's `fSeekDir` | derived |
| `i32` | `fSeekKeys`, or 0 (5.4) | derived |
| `u16` + 16 bytes | the directory's own UUID, distinct from the file's and from every other directory's | free |
| 12 bytes | zero | fixed |

**The payload is 60 bytes whether or not the offsets are 64-bit.**
`TDirectoryFile::Sizeof` counts 22 + 4 + 4 + 18 + 12 with no reference to the
large-file flag (`root/io/io/src/TDirectoryFile.cxx:1725-1735`), because in the
large layout the 12 trailing bytes are taken up by the high halves of the three
offsets rather than written as padding. This fixed size is what makes 5.3's
in-place rewrite possible, and it is why a writer must emit the 12 zero bytes
rather than stopping after the UUID.

> **`TDirectoryFile` has two writers of these 60 bytes, and they set the large-file
> flag under different conditions.** `FillBuffer`, which produces the record,
> tests the three stored offsets (`root/io/io/src/TDirectoryFile.cxx:751-760`);
> `Streamer`'s write branch tests the file's `fEND` (`:1827`). A writer follows
> `FillBuffer`: `Streamer` is reached only when a `TDirectoryFile` is streamed
> as an object, which the directory machinery never does.
> [Directories §3](../01-container/Directory.md#3-three-independent-large-file-flags)
> lists this flag with the other two.

### 5.3 The record never moves, and a directory key is never freed

Every later write of those 60 bytes overwrites them in place. `WriteDirHeader`
seeks to `fSeekDir + fNbytesName` and writes `Sizeof()` bytes
(`root/io/io/src/TDirectoryFile.cxx:2177-2180`); it allocates nothing, builds no
key, and does not touch the free list. `TKey::Delete` also refuses to free a
directory key, with this explanation in ROOT's source
(`root/io/io/src/TKey.cxx:586-594`):

> *"TDirectoryFile assumes that its location on file never change (for example
> updates are partial) and never checks if the space might have been released and
> thus over-write any data that might have been written there."*

For a writer this has two consequences:

1. **`nfree` stays 1.** A file created from nothing has one free entry however
   many directories it holds. Nothing in §5 produces a freed span, so §9's
   single-entry free list is still right.
2. **A re-save frees the key list, not the record.** `WriteKeys` marks
   the previous key-list record free before writing the new one
   (`root/io/io/src/TDirectoryFile.cxx:2201-2203`). A writer that never updates a
   file never reaches this, but a reader must be ready for it in files ROOT has
   updated.

> Measured on `data/written/nested-subdir.root`, which ROOT reopens in `UPDATE`
> mode in the case's `verify.C` to write one object into `alpha`. Afterwards
> `alpha`'s record is still at 401, `beta`'s still at 610, and `beta`'s key list,
> untouched because `beta` was not modified, is still at 1634. Everything else
> moved: `alpha`'s key list, the root's and the free-segment record were freed and
> written again further down, `alpha`'s new, longer list was allocated into the
> span the first two vacated, and the 13 bytes left over at the end of it are
> marked free. `nfree` is 3. The two directory records are the only records ROOT
> rewrote without moving.

### 5.4 One key list per directory, keyed by the directory's own name

A subdirectory's key list is §8's record with different values in three of its
key's fields:

| Field | Value |
|---|---|
| key `fClassName` | `TDirectory`, the same substitution as 5.2, so the key-list record and the directory record **cannot be told apart by their keys** |
| key `fName`, `fTitle` | the directory's own, not the file's and not a fixed string. Two records in the file therefore have the directory's name |
| key `fSeekPdir` | the directory's **own** `fSeekDir`, because `WriteKeys` passes `this` as the mother (`root/io/io/src/TDirectoryFile.cxx:2213`), not the mother's offset. This looks like a mistake but is correct |
| payload | `i32` count, then each of *this* directory's records' keys verbatim |

A subdirectory's key image goes in its **parent's** list, and its contents go in
its **own**. Nothing appears in both, so the top-level list of a file with one
subdirectory holding one object names two records, not three.

The lists are written after every data record, and **a parent's precedes its
children's**: `TDirectoryFile::Save` calls `SaveSelf` and then recurses
(`root/io/io/src/TDirectoryFile.cxx:1575-1587`). Nothing reads that order, since
every list is found by an absolute `fSeekKeys`, so the order is free; reproducing
it keeps a diff against a ROOT-written file short.

**A directory with no key list is legal.** `fSeekKeys` and `fNbytesKeys` stay 0
for a directory ROOT created and never saved, because the constructor clears
`fModified` (`root/io/io/src/TDirectoryFile.cxx:133`) and `SaveSelf` writes
nothing without it (`:1649`). A *saved* empty directory has a list whose payload
is the four-byte count `0`. The two states are described in
[Directories §6.4](../01-container/Directory.md#64-empty-and-unsaved-directories).
`tools/rootwrite.py` takes the choice as an argument, and refuses an unsaved
directory that holds anything, because its keys would be unreachable.

### 5.5 Cycles, and the one field whose meaning changed

`fCycle` is per directory, not per file: it counts keys of the same name **in the
same directory** (`root/io/io/src/TDirectoryFile.cxx:225-255`), so two objects
called `h` in two directories are both cycle 1. `AppendKey` inserts a repeated
name *before* the existing one, so a directory's key list holds higher cycles
first.

`fSeekParent` needs care, but only when reading: before ROOT 6.38 it held the
**top** directory's offset for a directory at any depth, not the mother's
([Directories §4.3](../01-container/Directory.md#43-fseekparent-do-not-use-it-for-parentage)).
A writer emits the mother's offset, which is what current ROOT writes and expects;
only a *reader* encounters the old value.

### 5.6 The check this section passes

`data/written/nested-subdir.root` holds two nested subdirectories and one
`TObjString` at each of three levels: the same content as the ROOT-written
fixture `data/container/directories.root`, with a file name chosen to be the same
length. The two files are **1854 bytes each, with identical record boundaries, and
every byte agrees except in three fields that this layer marks free**: each key's
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
| `fName`, `fTitle` | the key's name and title; ROOT uses the object's `GetName()`/`GetTitle()` unless the caller named it | free |

**There is no compression flag.** A reader decides that the payload is compressed
from `fObjlen > fNbytes - fKeylen` and nothing else (`root/io/io/src/TKey.cxx:827`).
The two fields are therefore not independent: `fObjlen` equal to
`fNbytes - fKeylen` *means* the payload is stored as-is. A writer that compresses
but does not leave `fObjlen` at the uncompressed length passes its zip stream to the
streamer as if it were object data. [Writing an object](WritingObjects.md) has the
block format; [Compression](../01-container/Compression.md) is the reading side.

ROOT only attempts compression when the file's level is above 0 **and** the payload
exceeds 256 bytes (`root/io/io/src/TKey.cxx:262-264`), which is why small records
in a compressed file are stored uncompressed. A writer may compress whatever it
likes; a reader cannot distinguish "too small to compress" from "the writer chose
not to".

## 7. The `StreamerInfo` record

A key whose class is **`TList`** and whose name is **`StreamerInfo`**
(`root/io/io/src/TFile.cxx:3554`), holding one `TStreamerInfo` per class the file's
objects were written with and, if any exist, a trailing `TList` of I/O rules
named `listOfRules` (`root/io/io/src/TFile.cxx:3527-3549`). Its offset and length
go in the header as `fSeekInfo` and `fNbytesInfo`, and **it is deliberately not in
the key list**: `WriteStreamerInfo` removes it (`root/io/io/src/TFile.cxx:3555`)
after the constructor has added it.

Its key's **`fTitle` is `"Doubly linked list"`**, fixed. The key takes the title
of the object it holds (`root/io/io/src/TKey.cxx:236`); a `TList` has no title of
its own, so `TObject::GetTitle` returns the class's, which is the comment on
`TList`'s `ClassDef` (`root/core/base/src/TObject.cxx:504-507`,
`root/core/cont/inc/TList.h:115`). With the short key layout that makes `fKeylen`
**64**: 26 fixed bytes, then `TList`, `StreamerInfo` and the title as counted
strings (6 + 13 + 19). A writer that leaves the title empty writes a key 18 bytes
shorter, and every offset after it moves.

Its contents are described in [Writing an object](WritingObjects.md). This section
covers whether a writer needs it at all.

### 7.1 ROOT does not need it, and will not say so

For a class ROOT has compiled in, the file's streamer info is **optional**.
`TKey::ReadObj` calls the object's own compiled `Streamer`
(`root/io/io/src/TKey.cxx:874`), and when the class has no info for the version on
disk, `TBufferFile::ReadClassBuffer` builds one from the dictionary, provided the
version word matches the compiled class or is 1
(`root/io/io/src/TBufferFile.cxx:3627-3651`). There is no warning: the diagnostic
on that path needs `gDebug > 0`.

Measured:

- `data/written/objstring.root` has `fSeekInfo = 0`, and ROOT reads its
  `TObjString` correctly and without a message.
- In a ROOT-written `TH1F` file with `fSeekInfo` and `fNbytesInfo` zeroed in the
  header, ROOT still reads the histogram correctly: same entries, same mean, same
  title.
- **`tools/coverage_probe.py` cannot read either file.** This project's reader is
  driven by streamer info, so with no info in the file it has nothing to decode
  with: it reports `no streamer info for TObjString` and gives up. Other
  third-party readers fail for the same reason.

There is one warning, and it fires on the wrong condition. `TFile::Init` prints
`no StreamerInfo found in %s therefore preventing schema evolution` only when the
file's `fVersion` differs from the running ROOT's and is above 30000, and the file
has keys (`root/io/io/src/TFile.cxx:928-941`). A writer that puts the current
release's version number in `fVersion` **suppresses it**. Both cases were confirmed
with `tools/rootwrite.py`: the same file with `fVersion = 64004` opens in ROOT
6.40.04 with no message, and with `fVersion = 63000` prints the warning; it reads
correctly either way.

### 7.2 So write one

A writer that wants its files read by anything other than ROOT has to emit the
record. There are two further reasons:

- **Schema evolution needs it.** Without an info the reader has only its own
  compiled layout, so a file written today is readable only by a ROOT whose classes
  still match.
- **An empty list is a legitimate value, and ROOT writes one for a file with
  no streamer-info-driven objects** (`root/io/io/src/TFile.cxx:3543-3544`). An
  empty `TList` record with a valid `fSeekInfo` means "nothing here";
  `fSeekInfo = 0` means "never closed".

`FileHeader.md` invariant 8 allows `fSeekInfo <= fBEGIN`, so a file without the
record is conforming, but fewer readers can read it.

## 8. The key list

A record whose payload is the count, then each data record's key **verbatim**
([Directory §6](../01-container/Directory.md#6-key-lists)):

| Field | Value |
|---|---|
| key `fClassName` | `TFile`, the same key shape as the root directory record, which is why neither can be identified by its key (`Directory.md` §6.2) |
| key `fName`, `fTitle` | the file's own, again |
| key `fSeekPdir` | 100 |
| `fObjlen` | `4 + Σ fKeylen` over the keys listed |
| payload | `i32` count, then the first `fKeylen` bytes of each record, unchanged |

The list does not include the root directory record's own key, the key list's own
key, the free list's, or the `StreamerInfo` record's. In a one-directory file with
`k` data records, the count is `k`.

The images are copies, not summaries. Each includes its own `fSeekKey`, which is
how a reader gets from the list to the record. ROOT validates only that the offset
is inside the file (`root/io/io/src/TDirectoryFile.cxx:1453-1465`), so if an image
disagrees with the record it points at, ROOT uses the image without any message.
Copy the bytes; do not re-derive them.

### 8.1 Where a key goes in the list, and what cycle it gets

`TDirectoryFile::AppendKey` (`root/io/io/src/TDirectoryFile.cxx:225-256`) answers
both questions:

```cpp
TKey *oldkey = (TKey*)fKeys->FindObject(key->GetName());
if (!oldkey) { fKeys->Add(key); return 1; }   // a new name: append, cycle 1
...                                            // else find the first of that name
fKeys->AddBefore(lnk, key);                    // and go in front of it
return oldkey->GetCycle() + 1;
```

| | |
|---|---|
| a name not already in the list | **appended at the end**, cycle **1** |
| a name already in the list | inserted **before the first key of that name**, cycle **that key's plus one** |

Writing a name that already exists therefore **adds** a record rather than
replacing one ([Records §4](../01-container/Record.md#4-cycles)); the earlier
record and its key both stay. Because every insertion goes to the front of its
name's run, the run is in **descending** cycle order and the first match is always
the highest.

> **A writer is more likely to violate this ordering than any other invariant, and
> ROOT depends on it.** ROOT never compares cycles to find the highest one. `Get`,
> `GetKey` and `FindKeyAny` all return the **first** match in list order
> (`root/io/io/src/TDirectoryFile.cxx:1002`, `:1167`, `:829`). The "highest cycle"
> behaviour described in [Records §4](../01-container/Record.md#4-cycles) comes
> from the order, not from the lookup.

Measured on `data/written/cycles-3.root` with its three key images reversed and
nothing else changed:

| Request | Correct order | Ascending order |
|---|---|---|
| `Get("str")` | `revision 3` | **`revision 1`** |
| `GetKey("str")` | cycle 3 | **cycle 1** |
| `GetKey("str", 2)` | cycle 2 | **cycle 1** |
| `Get("str;2")` | `revision 2` | `revision 2` |

There is no error or warning. `Get("str;2")` still works because it wants an exact
cycle, so it scans past the wrong first match. A writer that appends new cycles at
the end of the key list produces a file in which every unqualified lookup returns
the **oldest** copy.

For a writer, the order of **distinct names** is free, and the order **within
one name** is fixed. `TDirectoryFile::Purge` depends on the same ordering
(`root/io/io/src/TDirectoryFile.cxx:1316-1327`) and would delete the newest copy
of a mis-ordered run rather than the oldest.

### 8.2 Deleting, and what a key list does not say

Releasing a record ([§2.4](#24-releasing-a-record)) also removes its image from
the list. Nothing else changes: cycles are **not** renumbered and **not**
compacted, so deleting cycle 2 of three leaves 3 and 1, and the next write of that
name takes `3 + 1 = 4`. Cycles never decrease and can be sparse. After every cycle
of a name is deleted, writing it again starts at 1, and the key is appended at the
end, because the list no longer holds the name.

**`TDirectoryFile::Delete` also saves.** Before it returns it writes the key list,
the directory header **and** the free list
(`root/io/io/src/TDirectoryFile.cxx:736-738`), so a single delete costs three
record writes, and its effect on the layout depends on when in the session it
happened. Only the `"overwrite"` option frees through `TKey::Delete` alone. The
same method has another trap: `Delete("name")` with no cycle decodes to cycle
9999 (`root/core/base/src/TDirectory.cxx:1319`), which affects **memory only** and
leaves the file alone. `Delete("name;1")` deletes a key; `Delete("name;*")`
deletes every cycle of it.

**A negative `fCycle` is legitimate, and a writer should preserve it.** It marks
the key as "keep", exempting it from purging, and the cycle is its magnitude
([Records §3.8](../01-container/Record.md#38-fcycle)). Nothing in this procedure
produces one; a writer that copies keys from another file must not drop the sign.

## 9. The free list

One record, located from the header, holding the spans that are not live data
([Free segments](../01-container/FreeSegments.md)). For a file written once:

| Field | Value |
|---|---|
| key | the same `TFile`-classed shape again, `fSeekPdir` 100 |
| `fObjlen` | 10, one entry |
| entry version | `1`; `1001` only if the entry's `fLast` exceeds 2000000000 (`root/io/io/src/TFree.cxx:111`) |
| `fFirst` | `fEND` |
| `fLast` | 2000000000 |

**The last entry is a sentinel that ROOT relies on.** ROOT ignores `nfree` and
reads entries until one has `fLast > fEND`, including that one
(`root/io/io/src/TFile.cxx:1990-1995`). If the last entry's `fLast` does not exceed
`fEND`, ROOT keeps parsing past the end of the payload, into whatever follows.
With `fFirst = fEND` and `fLast = 2000000000` the condition holds for any file
smaller than 2 GB.

**ROOT reads the list only when the file is opened writable**
(`root/io/io/src/TFile.cxx:769-775`), which is why a `fSeekFree` of 0 produces
`file %s probably not closed, cannot read free segments` on an update and nothing
at all on a read. A read-only open therefore never validates this record; it is
first used by the next write.

This is the second reason to get it right: the *next* writer depends on it. ROOT's
allocator falls back to the last entry when nothing fits, and allocates at its
`fFirst` (`root/io/io/src/TFree.cxx:149-152`, `root/io/io/src/TKey.cxx:532`). If
the last entry's `fFirst` is below the end of the live data, the first object
anyone adds to the file overwrites a record, and `WriteHeader` then sets `fEND` to
that `fFirst` (`root/io/io/src/TFile.cxx:2671-2672`), truncating the file
logically. A file can therefore be fully readable and still break on the next
write.

### 9.1 On an update, placing the record can shorten it

The record's length depends on how many entries the list has, and placing the
record changes the list. ROOT sizes the payload first, from the entries as they
are, then places the key, and only then serializes the entries
(`root/io/io/src/TFile.cxx:2598-2657`). If the key took an interior gap **exactly**,
that entry is gone, the entries fill fewer bytes than were reserved, and ROOT
fills the rest with zeros (`root/io/io/src/TFile.cxx:2649-2654`). A key placed in
a larger gap only shrinks it, and at the tail only moves `fEND`, so the count is
unchanged in every other case, and always on a create.

A writer that imitates ROOT sizes first and pads, as `tools/rootwrite.py` does. One
that sizes after placing produces a record with no slack, which ROOT reads the
same way but whose `fNbytesFree` differs from ROOT's. Either way a reader stops at
the first entry with `fLast > fEND` and never reaches the zeros
([Free segments §3](../01-container/FreeSegments.md#3-reading-the-list)). No fixture has the padded
form; it is stated from the source.

## 10. The header

Written last. Every field, with the source of its value:

| Field | Value | Kind |
|---|---|---|
| magic | `root` | fixed |
| `fVersion` | the layout the file uses. ROOT writes its own release as an integer, 64004 for 6.40.04 (`root/io/io/src/TFile.cxx:423`), and adds 1000000 when `fEND` exceeds 2000000000 (`root/io/io/src/TFile.cxx:2679`) | free, with constraints (§10.1) |
| `fBEGIN` | 100. `TFile::Init` assigns `kBEGIN` unconditionally (`root/io/io/src/TFile.cxx:682`, `:204`) and nothing in ROOT writes another value | fixed |
| `fEND` | the first byte of the last free segment, which for a create-only writer is the file's length | derived |
| `fSeekFree`, `fNbytesFree` | the free record's offset and total length | derived |
| `nfree` | the number of entries in it: 1. Written from the live list (`root/io/io/src/TFile.cxx:2676`) and never read back for parsing (§9) | derived, advisory |
| `fNbytesName` | as in the root directory record, §4 | derived |
| `fUnits` | 4 in the small layout, and 8 with the large-file flag (`root/io/io/src/TFile.cxx:2679`). ROOT stores what it reads (`root/io/io/src/TFile.cxx:745`) but **never uses it**; `TFile::Init` decides the layout from `fVersion` alone | fixed by convention |
| `fCompress` | `algorithm × 100 + level` (`root/io/io/inc/TFile.h:477-485`), 0 for none | free |
| `fSeekInfo`, `fNbytesInfo` | the `StreamerInfo` record's offset and length, or 0 for none (§7) | derived |
| UUID | a `u16` 1 followed by 16 bytes (`root/io/io/src/TFile.cxx:2706`) | free |
| 63…99 | not written | — |

### 10.1 What `fVersion` commits a writer to

ROOT reads it as a feature gate, not as a record of provenance. Two thresholds
matter:

- `fVersion >= 1000000` selects the wide header, and 40000 selects the 60-byte
  directory record rather than the 48-byte one
  (`root/io/io/src/TDirectoryFile.cxx:785`). A writer emitting the layout this
  document describes must use a value at or above 40000 and below 1000000.
- `fVersion < 30000` makes `TBufferFile` force every version word to -1 and rebuild
  every class as emulated (`root/io/io/src/TBufferFile.cxx:3560-3565`).

Otherwise the value is the writer's choice, and it has one visible consequence:
§7.1's missing-streamer-info warning fires only when `fVersion` differs from the
running ROOT's. The accurate choice is the version of the ROOT release whose layout
is being emitted, and that is what `tools/rootwrite.py` writes.

## 11. Determinism, which ROOT also offers

Two fields default to values that change on every run: `fDatime` in each key
(`root/io/io/src/TKey.cxx:531`) and the UUID in the header and each directory
record. A writer has no reason to consult a clock, and `tools/rootwrite.py` takes
both as inputs. This is why `data/written/` is byte-reproducible and the rest of
`data/` is not.

ROOT has the same feature: opening a file with the URL option `?reproducible` sets
`TFile::kReproducible` (`root/io/io/src/TFile.cxx:417-418`), which writes an
all-zero UUID (`root/io/io/src/TFile.cxx:2703-2704`) and a fixed `TDatime(1)` in
every key (`root/io/io/src/TKey.cxx:652-655`). A reader must therefore treat both
fields as carrying no information: a zero UUID and a 1995 timestamp are normal.

The packed timestamp is six bit fields in one 32-bit word: year biased by 1995,
then month, day, hour, minute, second
(`root/core/base/src/TDatime.cxx:392`). Years below 1995 are rejected
(`root/core/base/src/TDatime.cxx:387-390`), so the earliest representable value is
in 1995 and the range ends in 2058.

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
| 190 | 58 | the name and title again (148 − 90) |
| 248 | 60 | the directory's fields: version 5, `fNbytesKeys` 160, `fNbytesName` 148, `fSeekDir` 100, `fSeekParent` 0, `fSeekKeys` 396, the UUID, 12 zero bytes |
| 308 | 66 | the data record's key: `TObjString`, `str`, `fSeekKey` 308, `fSeekPdir` 100 |
| 374 | 22 | the object: byte count `0x40000012`, version 1, a `TObject` base, `05 hello` |
| 396 | 90 | the key-list record's key: `TFile` again, `fObjlen` 70 |
| 486 | 70 | the count 1, then the 66 bytes at 308 verbatim |
| 556 | 90 | the free-list record's key: `TFile` again, `fObjlen` 10 |
| 646 | 10 | version 1, `fFirst` 656, `fLast` 2000000000 |

`fEND` is 656, which is both the file's length and the free entry's `fFirst`.
`data/container/file-minimal.root` has the same shape, written by ROOT: it is 1094
bytes, and the whole difference is the `StreamerInfo` record and the longer names.

## 13. Updating an existing file

Everything above produces a file in one pass. An **update** is the other case: a
file that already exists is opened, records are added to it, and it is closed
again. Nothing in the format distinguishes the result: a file ROOT updated
fourteen times and a file it wrote once are the same kind of file, and a reader
cannot tell them apart. The difference is in what the writer has to do, and that is
less than it might seem.

**No new allocation rule is needed.** [§2](#2-allocation) is the complete
allocator; the only difference is that an update inherits the free list instead of
starting one. **No record moves.** A directory record is rewritten in place and
never relocates
([§5.3](#53-the-record-never-moves-and-a-directory-key-is-never-freed)), which is
what makes an update possible: every `fSeekPdir` and `fSeekParent` in the file
stays valid.

### 13.1 What the file decides, and what the caller decides

Four fields are taken **from the file**, and whatever the caller requested is
ignored: `fVersion` (`root/io/io/src/TFile.cxx:734`), `fBEGIN` (`:737`), `fUnits`
(`:745`) and `fCompress` (`:746`). The title comes from the root directory record
(`:839`). The compression level passed to `TFile::Open` is silently ignored on
`UPDATE`, so a record added today is compressed as the original writer chose.
Because `fVersion` is kept, **a file updated by 6.40 can still declare it was
written by 5.28**: every inference a reader draws from `fVersion` is about the
*first* writer, not the last.

`fName` is the exception, and the source gives the reason on the line that skips
it: `// fName.ReadBuffer(buffer); file may have been renamed`
(`root/io/io/src/TFile.cxx:838`). See [§13.6](#136-what-an-update-rewrites-in-place).

The caller also does not decide this: `UPDATE` on a path that does not exist is
**not an error**, it becomes a create (`root/io/io/src/TFile.cxx:533-534`).

### 13.2 What an update reads

An update reads these five things and needs nothing else from the file:

| Read | From | For |
|---|---|---|
| the header | bytes 0..`fBEGIN` | `fEND`, `fSeekFree`, `fNbytesFree`, `fNbytesName`, `fSeekInfo`, `fNbytesInfo`, `fCompress`, `fVersion`, the UUID |
| the root directory record | `fBEGIN` | `fDatimeC`, `fSeekKeys`, `fNbytesKeys`, the title, the directory's own UUID |
| the key list | `fSeekKeys` | every key image, verbatim ([§13.3](#133-the-keys-already-there-are-copied-not-rebuilt)) |
| the free-segment record | `fSeekFree` | the allocator's state |
| **nothing** at `fSeekInfo` | — | the two numbers are copied forward unread ([§13.7](#137-the-streamerinfo-record-is-usually-not-rewritten)) |

**The free list is the only state passed from one session to the next.** A writer
is told which spans are free and nothing about the rest of the file; it does not
enumerate the live records, and neither does ROOT. Everything between `fBEGIN` and
`fEND` that the free list does not claim is live by definition, and that is
sufficient. `data/written/reopen-reuse.root` tests this: the base left a 95-byte
hole at 398, the update was given the bytes and nothing else, and the record it
placed there is 95 bytes, an exact fit across two sessions, found from the free
list alone.

**A subdirectory nobody opened is not touched.** ROOT loads a subdirectory's keys
only when something asks for them, so an update that writes only into the root
directory rewrites only the root directory's key list. The subdirectory's record
and its key list keep their bytes and their addresses.

### 13.3 The keys already there are copied, not rebuilt

The new key list contains the images of the keys that were already in it, **byte
for byte**, including each one's `fDatime` and `fCycle`. A writer that reopens a
file therefore has to *read* a key image, which a writer that creates a file never
does, and it must re-emit what it read rather than re-derive it, because
`fDatime` is the original write's timestamp and a negative `fCycle` is the keep
flag ([§8.2](#82-deleting-and-what-a-key-list-does-not-say)).

New keys are inserted by the rule of [§8.1](#81-where-a-key-goes-in-the-list-and-what-cycle-it-gets),
regardless of which session wrote the existing keys.

### 13.4 The close sequence

The same four steps as a create, in the same order, but each now releases an old
record first:

1. **the `StreamerInfo` record**, if it changed, which it usually has not
   ([§13.7](#137-the-streamerinfo-record-is-usually-not-rewritten));
2. **each directory's key list**, which **always reallocates**: `WriteKeys`
   frees its old record before it sizes the new one
   (`root/io/io/src/TDirectoryFile.cxx:2201-2203`);
3. **each directory's header**, rewritten **in place**
   ([§13.6](#136-what-an-update-rewrites-in-place));
4. **the free-segment record**, which also frees its own old span first
   (`root/io/io/src/TFile.cxx:2599-2600`) and may come out shorter than it was
   sized ([§9.1](#91-on-an-update-placing-the-record-can-shorten-it)), and then
   the header.

The order is visible in the bytes, because each step allocates out of what the
step before it released. In `data/written/reopen-add.root` the free record ends
up at **806**, where the base's key list was: step 2 freed 148 bytes there, step 4
asked for 98, and first fit gave it the front of them. The 243-byte gap at 904 is
the rest of that span, the base's own free record and a record the update freed,
coalesced into one entry.

A writer does not have to copy where each record lands, since that is ROOT's
choice, not the format's ([§2.5](#25-how-much-of-this-a-writer-must-copy)). It
must copy the *order*, because step 4 has to see what steps 1 to 3 did to the free
list.

### 13.5 The three ways to write a name that already exists

ROOT offers three. They differ only in when the old record is freed relative to
when the new one is allocated, and that determines three visible outcomes:

| | plain | `"overwrite"` | `"WriteDelete"` |
|---|---|---|---|
| the old record | stays live | freed **before** the write (`root/io/io/src/TDirectoryFile.cxx:1977-1985`) | freed **after** the write (`:1986`, `:2004-2007`) |
| the old key | stays in the list | removed before | removed after |
| the new record's address | cannot reuse the old one | **can**, and does when it fits | cannot |
| the new cycle | old + 1 | unchanged | old + 1 |
| keys of that name afterwards | one more | the same number | the same number |

Each fixture measures one column of this table. In
`data/written/reopen-reuse.root`, `overwrite` on `tail` put the replacement at
**493**, the address its first version had, with `fCycle` still **1** and a
13-byte remainder behind it. In
`data/written/reopen-add.root`, `WriteDelete` on `two` put the replacement at
1259, away from the 1042 it freed, with `fCycle` **2**.

In both cases the key replaced is the **newest** key of that name, which is the one
an unqualified lookup resolves to (`root/io/io/src/TDirectoryFile.cxx:1980`,
`:1987`), not the oldest.

None of this is a format rule either. A writer may use any of the three, and a
reader can tell which was used only by the shape of the result.

### 13.6 What an update rewrites in place

Only a directory's **60-byte header**, at `fSeekDir + fNbytesName`
(`root/io/io/src/TDirectoryFile.cxx:2161-2180`). Its key, and the repeated name
and title that follow the key in the root directory's record, are **not**
rewritten. Inside the header, `fDatimeM` is refreshed (`:2175`) and `fDatimeC` is
not, so a file records when its root directory was created and when it was last
changed, and after an update the two differ.

`fNbytesName` is not recomputed either: it measures the key that was not
rewritten, and the source says so on the line that computes where to write:
`// do not overwrite the name/title part`
(`root/io/io/src/TDirectoryFile.cxx:2177`). A writer that recomputed
`fNbytesName` from the name it was opened with would produce a header that
disagrees with the record, which
[§14](#14-invariants-a-writer-should-check-on-its-own-output) item 3 catches.

**As a result a file can record two different names for itself.** New keys carry
`fName`, which is the path the file was *opened as*; the directory record's key
still has the path it was *created as*; and ROOT deliberately does not restore one
from the other (`root/io/io/src/TFile.cxx:838`). If a file is copied and the copy
updated, the difference shows up in the bytes:

```
                        before the update     after
the record at 100       base.root             base.root
the key list's key      base.root             noop.root
the free record's key   base.root             noop.root
```

That is an entire no-op update: an eight-byte difference, four bytes in each of two
keys, caused only by the rename. **A reader must not assume the two agree**, and
must not take either as the file's location.

### 13.7 The `StreamerInfo` record is usually not rewritten

Nothing is written unless a class **new to the file** was used
(`root/io/io/src/TFile.cxx:3497-3503`). Adding a second `TObjString` to a file
that already describes `TObjString` leaves `fSeekInfo` and `fNbytesInfo`
unchanged (both fixtures here show it, at 372 and 619), while adding a `TNamed`
to the same file frees the old record, writes a bigger one at the end, and leaves
the old span for the key list to take.

An update therefore touches **three** records in the common case and four in the
uncommon one. A writer that rewrote the record unconditionally would be correct
but would leak a few kilobytes per session; one that never rewrote it would
produce a file nobody can read.

When the record *is* rewritten it must contain **every** info the file needs, not
just the new ones, because the record is replaced, not appended to. Merging the
file's existing infos with the session's belongs to
[Schema evolution](../02-serialization/SchemaEvolution.md) and is not specified
here; `tools/rootwrite.py` requires the caller to supply the complete list and
rewrites the record when it is given one.

### 13.8 Crossing 2 GB during an update

An update is the only way a file can acquire a **mixed** layout: records written
before the crossing have 4-byte offsets and records written after it have
8-byte ones, in one file. Nothing coordinates the change. Each field widens
independently, when its own value crosses:

| What | Widens when | Cited |
|---|---|---|
| a key | its own `fSeekKey` is past 2000000000, which its `fVersion` then records as `+ 1000` | [Records §3](../01-container/Record.md) |
| a free entry | its **`fLast`** is past 2000000000, not its `fFirst` | `root/io/io/src/TFree.cxx:186` |
| the header | **`fEND`** is past 2000000000, which adds 1000000 to `fVersion` and sets `fUnits` to 8 | `root/io/io/src/TFile.cxx:2679` |

`volume.root` in `gen/cern/LARGE.toml` confirms the middle row: 51 free entries,
32 of them 18 bytes and 19 of them 10, interleaved in one record.

**The last row has a hazard that a writer should refuse rather than reproduce.**
The large header is **75 bytes**: 57 of fields plus 18 of UUID. The small one
is 63. `TFile::WriteHeader` allocates `fBEGIN` bytes for it
(`root/io/io/src/TFile.cxx:2674`) and then writes however many it produced
(`:2709`). `fBEGIN` is read from the file (`:737`), and **files with an `fBEGIN`
of 64 exist**: four of them in the corpora this specification is checked against,
including `pippa.root` at ROOT 2.24/00 and `uproot-from-geant4.root`, which
g4tools wrote under a header claiming 4.00.
Updating one of those past 2 GB would write 75 bytes into a 64-byte buffer and
over the first eleven bytes of the file's first record. This is derived from the
source and the arithmetic, and has not been observed here, because observing it
means writing 2 GB into a file from 1997. A writer should decline to reopen a file
whose `fBEGIN` is below 75, and `tools/rootwrite.py` does.

### 13.9 A no-op update is not a no-op

Open for update, write nothing, close: the key list and the free-segment record
are still freed and rewritten, and the directory header still gets a new
timestamp. On a file opened at its own path, only three timestamps change:
`fDatimeM` in the directory header and the `fDatime` of the two recreated keys.
Every other byte, `fEND` and `fSeekFree` included, is identical, because both
records were freed, coalesced, and placed again at the same offsets.

Opening for **reading** changes nothing.

An update procedure therefore cannot skip writing when nothing changed, and a
reader cannot conclude from a recent `fDatime` on a key list that anything in the
file changed.

### 13.10 Two writers, one file

This is out of scope. ROOT takes no lock that a third party can see, and two
processes with the same file open for update will each write a header describing
its own value of `fEND`. Nothing in the format detects it. A writer that needs
safety has to arrange it outside the file.

## 14. Invariants a writer should check on its own output

The reading documents' `Invariants` sections are the full list, and
`tools/check_invariants.py` runs them. These are the ones a writer is most likely
to get wrong:

1. `fEND` equals the last free entry's `fFirst`, and does not exceed the file's
   length. For a writer that only appends, the two are equal; they differ once the
   last record is released, which moves `fEND` back without truncating
   ([§2.4](#24-releasing-a-record)).
2. The last free entry's `fLast` is strictly greater than `fEND` (§9).
3. `fNbytesName` equals the root directory record's `fKeylen` plus the two counted
   strings that follow it, and equals the copy inside the record.
4. `fSeekKeys` plus `fNbytesKeys` does not exceed `fEND`, and the record at
   `fSeekKeys` has exactly `fNbytesKeys` bytes.
5. Every key image in the key list agrees with the key of the record at its own
   `fSeekKey`: the same `fNbytes`, `fObjlen`, `fKeylen`, `fCycle` and strings,
   with `TDirectory` and `TDirectoryFile` counted as one class name
   ([Directories §9](../01-container/Directory.md#9-invariants) 11).
6. Every record's `fNbytes` equals `fKeylen` plus the stored payload, and
   `fObjlen == fNbytes - fKeylen` **iff** the payload is stored uncompressed (§6).
7. Walking from `fBEGIN` by `fNbytes` reaches exactly `fEND`, with no record
   overlapping another and no unclaimed bytes between them.
8. `fSeekPdir` is 0 in the root directory record's key and `fBEGIN` in every other
   key of that directory (§4.1).
9. Every subdirectory's `fNbytesName` equals its own record's `fKeylen`, and its
   fields therefore begin where its key ends (§5.2).
10. Every subdirectory's key spells its class `TDirectory`, and the key's
    `fKeylen` accounts for that spelling and not for `TDirectoryFile`. The two
    differ by four bytes, and ROOT does not notice the difference
    ([Directories §6.5](../01-container/Directory.md#65-an-images-length-is-what-it-parses-to-never-its-fkeylen)).
11. Every subdirectory appears in exactly one key list, its parent's, and its own
    key list holds only what it contains (§5.4).
12. A key-list record's key stores the `fSeekDir` of the directory that **owns**
    the list, not of that directory's parent (§5.4). Nothing else in the record
    identifies the directory it belongs to.
13. Every record placed in a span with bytes to spare is followed immediately by
    a four-byte negative marker whose magnitude is the remainder
    ([§2.3](#23-updating-the-free-list-and-the-three-outcomes)), and that
    remainder appears in the free list as the same span.
14. **No free segment is one, two or three bytes long.** A writer that takes a
    span with fewer than four bytes to spare has nowhere to put the marker, and
    produces a gap no reader can walk past
    ([Free segments §8](../01-container/FreeSegments.md#8-invariants) 10).
15. Within one directory, keys sharing a name have **distinct cycles in
    descending order**, and no cycle is 0 ([§8.1](#81-where-a-key-goes-in-the-list-and-what-cycle-it-gets)).
    ROOT resolves an unqualified name to the first match, so a run in the wrong
    order silently returns the oldest copy.
16. No two **live** records overlap. A record placed in released space lands on
    the bytes of the record that used to be there, which is correct and is how a
    gap is reused. Two records that are both reachable from a key list must not
    share a byte, and nothing downstream would detect it, because ROOT reads every
    record by its own offset.
17. `fBEGIN` is at least the length of the header the file's own `fVersion`
    selects: 63 bytes small, 75 large
    ([File header §10](../01-container/FileHeader.md#10-invariants) 11). A writer
    that only creates files satisfies this by construction; one that **updates**
    should check it before it starts, because the file it was given may not
    ([§13.8](#138-crossing-2-gb-during-an-update)).

The update of §13 adds no allocation obligations of its own: every invariant above
is checked the same way on a file that was written once and on a file that was
reopened eleven times, because nothing in the result records which it was.

Items 1, 2, 5, 6, 7 and 9 to 17 are the ones ROOT does not detect at all (§15).
Every item but 16 is checked by `tools/check_invariants.py`, which gate 2 runs on
every written file: 1 as [Free segments §8](../01-container/FreeSegments.md#8-invariants)
1 and 9, 2 as Free segments 2, 3 and 9 as
[Directories §9](../01-container/Directory.md#9-invariants) 3, 4 as Directories
5, 5 as Directories 11, 6 through every
[Compression](../01-container/Compression.md#9-invariants) check, 7 as
[Records and keys §8](../01-container/Record.md#8-invariants) 8, 8 in part as
Records and keys 6 (it requires `fSeekPdir` to name a directory, not the right
one), 10 as Records and keys 3 and Directories 13 (the length, not the spelling
itself), 11 as Directories 8, 12 as Directories 12, 13 as Free segments 6 and 7,
14 as Free segments 10, 15 as Directories 14, and 17 as
[File header §10](../01-container/FileHeader.md#10-invariants) 11.
Item 16 is checked in the writer itself: it is a property of the *act* of
writing rather than of the file, since a finished file cannot say which of two
overlapping records was meant to be live. The remaining obligation in
§5.4 is not a property of a file and so is not among them: a directory left with
`fSeekKeys` 0 while it owns records produces keys nothing can reach, and
`tools/rootwrite.py` refuses it rather than checking for it afterwards.

## 15. What ROOT does not check

Each row is a mistake that ROOT reads without complaint, so a writer that makes it
gets no feedback.

| Mistake | Why it is silent |
|---|---|
| `fObjlen` inconsistent with `fNbytes - fKeylen` | there is no codec flag; the inequality *is* the flag (`root/io/io/src/TKey.cxx:827`) |
| a key image in the key list disagreeing with the record's own key | the image frames the read; the record's own header is consulted only for its version word (`root/io/io/src/TKey.cxx:845-847`) |
| `fSeekKey` in an image pointing at the wrong record | validated only as an offset inside the file (`root/io/io/src/TDirectoryFile.cxx:1453-1465`) |
| `fSeekPdir` not matching the owning directory | never checked on the read path; only `TFile::Recover` filters on it (`root/io/io/src/TFile.cxx:2171`), so the file reads and is unrecoverable |
| `fUnits` disagreeing with the layout | read into the member and used for nothing (`root/io/io/src/TFile.cxx:739-759`) |
| `nfree` disagreeing with the free list | never read back (§9) |
| a last free entry whose `fFirst` is below the live data | reads fine; the next writer overwrites a record (§9) |
| `fNbytesName` off by a few | only range-checked, `10 <= fNbytesName <= 10000` (`root/io/io/src/TFile.cxx:841-844`) |
| a root directory record whose `fSeekDir` is not 100 | the record's value overwrites the one `Init` guessed (`root/io/io/src/TFile.cxx:767` then `:814`), and the next directory save writes the directory header there |
| a gap not preceded by a negative `fNbytes` | the record-chain walk reads a leading `i32` and treats a negative value as a gap; anything else ends the walk (`root/io/io/src/TFile.cxx:1675-1688`) |

The checks ROOT *does* make are all in `TFile::Init`: the magic and a minimum
length (`root/io/io/src/TFile.cxx:714-730`), `0 <= fBEGIN <= fEND`
(`:760-766`), that the directory record fits (`:781-788`), `fNbytesName`'s range
(`:841-844`), and `fEND <= filesize` (`:881-887`). Truncation is the only
condition under which it refuses to open the file.

## 16. Errata

Against ROOT's shipped documentation in `root/io/doc/TFile/`, on points specific to
writing. The reading-side errata are in the documents named in each row.

| # | Claim | Reality |
|---|---|---|
| 1 | `README.md`: "The file header is fixed length (64 bytes in the current release.)" | `fBEGIN` is 100 and the fields occupy 63 bytes (`root/io/io/src/TFile.cxx:204`, `:2707-2709`). The 64 was the 3.02.06 value; `header.md`'s own table disagrees with `README.md` |
| 2 | `README.md`: "A file always contains exactly one FreeSegments data record" | Zero is normal in a file that was created and not closed (`fSeekFree` is 0 at creation, `root/io/io/src/TFile.cxx:704`), and the record moves on every rewrite, the old copy becoming a gap (`root/io/io/src/TFile.cxx:2599-2601`) |
| 3 | Silent on the top-directory / subdirectory asymmetry | The top record's payload includes a `TNamed` and a subdirectory's does not, so `fNbytesName` means two different things (`root/io/io/src/TFile.cxx:702` against `root/io/io/src/TDirectoryFile.cxx:158`). §4.2 and §5.2 |
| 4 | Silent on `fSeekPdir = 0` in the file's own key | An artifact of the order of two statements (§4.1), and it affects `TFile::Recover` |
| 5 | Silent on write ordering | `TFile::Close` and `TFile::Write` put the `StreamerInfo` record on opposite sides of the key list (§3), and both orders occur in ROOT-written files |
| 6 | `freesegments.md` does not state the rule a writer needs | The last entry's `fLast` must exceed `fEND`, because that is the parse terminator (`root/io/io/src/TFile.cxx:1990-1995`), not because of any length |

## 17. Reference files

| File | What it demonstrates |
|---|---|
| `data/written/objstring.root` | all of §3, in 656 bytes (§12) |
| `data/container/file-minimal.root` | the same shape written by ROOT, with a `StreamerInfo` record |
| `data/container/gap.root` | a record deleted: an interior free entry and the negative marker in it |
| `data/container/gap-reused.root` | all of §2, written by ROOT: an exact fit, a partial fit by an unrelated record, and the remainder |
| `data/written/reused-space.root` | §2 written by this project: **the same 1747 bytes**, except each key's `fDatime`, the file's own name and the UUID |
| `data/container/cycles.root` | §8.1 written by ROOT: three cycles of one name, newest first in the list |
| `data/written/cycles-3.root` | §8.1 written here: **the same 1361 bytes** on the same terms |
| `data/container/directories.root` | the subdirectory shape of §5, and the file `data/written/nested-subdir.root` is compared against record for record |
| `data/written/nested-subdir.root` | §5 written: two nesting levels, three key lists, and ROOT writing into one of them (§5.3) |
| `data/container/reopened.root` | §13 written by ROOT: a file created, closed, reopened, and added to three ways (a new name, a second cycle, and `WriteDelete`) |
| `data/written/reopen-add.root` | §13 written here: **the same 1657 bytes**, except each key's `fDatime`, the file's own name and two UUIDs, including the two dead keys inside the 243-byte gap |
| `data/container/reopen-gap.root` | §13.2 written by ROOT: an update placing a record into a hole the base left, and `"overwrite"` reusing an address |
| `data/written/reopen-reuse.root` | the same **1928 bytes** written here, the exact fit at 398 included |

`tools/check_write.py --root` is the conformance test: it rebuilds each written
file, compares it byte for byte, runs `tools/check_invariants.py` over it, and has
ROOT open it and confirm the values.
