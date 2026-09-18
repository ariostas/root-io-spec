# Directories and key lists

A ROOT file has a tree of directories. Each is a record holding offsets to its
key list and its parent; each key list names the records the directory contains.
Together they are the file's index.

Prerequisites: [Conventions](../00-conventions.md), [File header](FileHeader.md),
[Records and keys](Record.md). All integers are big-endian.

## 1. Locating the root directory

The root directory's record begins at `fBEGIN`, and its **fields** begin at:

```
fBEGIN + fNbytesName
```

The gap between the two is the record's key followed, **for the root directory
only**, by a second copy of the file's name and title as counted strings. That
copy is written by `TFile::Init` rather than by the directory streamer
(`root/io/io/src/TFile.cxx:708`), because the object stored at `fBEGIN` is the
`TFile` itself — so its image is a `TNamed` part followed by a `TDirectoryFile`
part.

> ROOT never reads that copy back. Every reader jumps `fNbytesName` bytes from
> `fSeekDir`, and `TFile::Init` reads the payload's class name and name into a
> throwaway `TString` — twice into the same variable, with the comment *"file may
> have been renamed"* — keeping only `fTitle`
> (`root/io/io/src/TFile.cxx:836-839`). `fName` is never taken from the file at
> all: it stays the path the caller passed to `TFile::Open`, which is what lets a
> renamed file open.

A **subdirectory** record has no such prefix; its fields begin immediately after
its key. Both cases are covered by one rule, because `fNbytesName` differs:

| Directory | `fNbytesName` |
|---|---|
| root | `fKeylen` + the name and title counted strings |
| subdirectory | `fKeylen` |

> Demonstrated by `container/directories`: the root directory's fields start at
> 246 with `fNbytesName = 146`, while `alpha`'s start at 450 with
> `fNbytesName = 49`, equal to its `fKeylen`.

## 2. Layout

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           version             |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+          fDatimeC             +
|                               |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          fDatimeM                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        fNbytesKeys                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        fNbytesName                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                   fSeekDir     (4 or 8 bytes)                 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                  fSeekParent   (4 or 8 bytes)                 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                   fSeekKeys    (4 or 8 bytes)                 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|        TUUID version          |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+       UUID (16 bytes)         +
|                              ...                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|            12 reserved bytes, small layout only               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Type | Offset (small) |
|---|---|---|
| version | `i16` | 0 |
| `fDatimeC` | `u32` | 2 |
| `fDatimeM` | `u32` | 6 |
| `fNbytesKeys` | `i32` | 10 |
| `fNbytesName` | `i32` | 14 |
| `fSeekDir` | `i32` / `i64` | 18 |
| `fSeekParent` | `i32` / `i64` | 22 / 26 |
| `fSeekKeys` | `i32` / `i64` | 26 / 34 |
| TUUID version | `i16` | 30 / 42 |
| UUID | 16 bytes | 32 / 44 |
| reserved | 12 bytes | 48 / — |

Written by `root/io/io/src/TDirectoryFile.cxx:748-787`. The total is **60 bytes**
in both layouts, which is the point of the reserved bytes — see §5.

The datime fields use the packing given in
[Records §3.7](Record.md#37-fdatime). `fDatimeC` is the directory's creation
time, set once; `fDatimeM` is refreshed on every header rewrite
(`root/io/io/src/TDirectoryFile.cxx:2175`).

## 3. Three independent large-file flags

> ROOT has **three separate** large-file switches, on three different structures,
> with three different conditions. Confusing them is a reliable source of
> mis-parsing.

| Structure | Flag | Condition |
|---|---|---|
| File header | `fVersion >= 1000000` | `fEND > 2000000000` |
| Key | `fVersion > 1000` | the file's `fEND` **when the key was built** `> 2000000000`, or a non-zero `fPidOffset` — *not* the key's own offset ([Large files §1.1](LargeFiles.md#11-a-keys-width-is-not-decided-by-where-the-key-is)) |
| **Directory record** | **version `> 1000`** | **any of `fSeekDir`, `fSeekParent`, `fSeekKeys` `> 2000000000`** |

A reader MUST take the directory layout from the **directory record's own version
word**, never from the file header. All three of its offsets widen together; it
is one flag, not per-field.

`TDirectoryFile::Streamer` is a second writer of the same record with a
*different* condition — `fEND`, not the three offsets
(`root/io/io/src/TDirectoryFile.cxx:1827`) — which matters to a writer and not to
a reader. [Large files](LargeFiles.md) collects all five switches.

The combinations are not equivalent. A file larger than 2 GB can still hold
small-layout directory records — the root directory's `fSeekDir` is `fBEGIN`,
normally 100 — so the header flag being set tells you nothing about any given
directory. The converse does hold: a directory offset beyond 2 GB implies
`fEND` is too.

## 4. Fields

### 4.1 `fNbytesKeys`

The **whole key-list record**, key header included — that is, the `fNbytes` of the
key at `fSeekKeys` (`root/io/io/src/TDirectoryFile.cxx:2226`). It is used as a
raw read length. Zero when there is no key list.

### 4.2 `fSeekDir`

The offset of this directory's **own record**, so it is self-referential and a
useful corruption check. For the root directory it equals `fBEGIN`.

### 4.3 `fSeekParent` — do not use it for parentage

> **`fSeekParent` changed meaning in ROOT 6.38.** Before commit
> `06735e7655f` (2025-08-02, first released in 6.38.00) it held the **top**
> directory's offset for *every* nested directory, not the mother's. From 6.38 it
> holds the mother's (`root/io/io/src/TDirectoryFile.cxx:155`).
>
> A reader MUST NOT reconstruct the directory tree from `fSeekParent`. Use the
> key's `fSeekPdir`, or the containment implied by walking key lists. Files
> written before 6.38 are extremely common and will report every directory as a
> child of the root.

It is 0 for the root directory.

> In `container/directories`, written by 6.40.04, `beta`'s `fSeekParent` is 401 —
> `alpha`'s record — which is the post-6.38 behaviour. A pre-6.38 writer would
> have put 100 there.

### 4.4 `fSeekKeys`

The offset of the key-list record's key, or **0** when this directory has no key
list. Zero is normal, not corrupt; see §6.

### 4.5 UUID

A 2-byte version word, always 1, then 16 bytes in RFC 4122 wire layout — the same
encoding as the file header's UUID
([File header §6](FileHeader.md#6-uuid)).

**Each directory carries its own, distinct UUID.** The root directory's matches
the file header's, because both are written from the same value at creation, but
subdirectories get fresh ones.

Version 2 records are the exception: they store the 16 bytes with **no version
word** (§7).

## 5. The reserved bytes

In the small layout, 12 zero bytes follow the UUID. They are slack, so that the
record is 60 bytes whether or not the three offsets are 64-bit — which lets ROOT
rewrite a directory header in place when a file grows past 2 GB
(`root/io/io/src/TDirectoryFile.cxx:2177-2181`).

A reader MUST NOT assume they are present or zero:

- in the **large** layout they are not padding at all, they are the high halves of
  the three offsets;
- for a file written by ROOT 3 (`fVersion < 40000`), they are **absent entirely**
  and the record is 48 bytes (`root/io/io/src/TDirectoryFile.cxx:785`).

The authoritative length is the record's `fObjlen`.

## 6. Key lists

A key list is a record whose payload is a count followed by that many key images:

| Offset | Field | Type |
|---|---|---|
| 0 | count | `i32` |
| 4 … | `count` key images | each a `TKey` header |

Each image is byte-identical to the first `fKeylen` bytes of the record it
describes, laid out exactly as in [Records §2](Record.md#2-key-layout). **Each
image carries its own `fVersion`**, so small and large images may be interleaved
in one list, and a reader must size each entry individually.

### 6.1 The count is authoritative

> A reader MUST iterate exactly `count` times, and MUST NOT parse until the
> payload is exhausted. When `fEND > 2000000000`, ROOT allocates the payload 8
> bytes larger than it writes (`root/io/io/src/TDirectoryFile.cxx:2209`), and that
> slack is **uninitialized heap**. A length-driven parse will read garbage as an
> entry.

There is no trailing checksum and no terminator.

### 6.2 The key-list record cannot be identified from its key

Its key carries the **containing directory's** name, title and class — `"TFile"`
for the root directory, or `"TDirectory"` for a subdirectory
(`root/io/io/src/TDirectoryFile.cxx:2213`). That makes it indistinguishable from
the directory record itself and from the free-segment record.

The only supported way to find it is `fSeekKeys` from the directory record.
`TFile::Recover` cannot recover it either, and deliberately skips anything whose
class inherits from `TFile` (`root/io/io/src/TFile.cxx:2171-2172`).

> In `container/directories`, three separate records carry the class name
> `"TFile"` and the file's own name: the root directory at 100, its key list at
> 1255, and the free list at 1786.

### 6.3 What is in the list

Present: object keys, and each subdirectory's key.

Absent: the directory's own record key, the key-list record's own key, the
free-segment record's key — none of which are ever appended — and the
`StreamerInfo` record, which is explicitly removed
(`root/io/io/src/TFile.cxx:3522`).

### 6.4 Empty and unsaved directories

Two distinct states, both legal:

| State | `fSeekKeys` | Key list |
|---|---|---|
| Saved, holds nothing | non-zero | a record whose payload is the 4-byte count `0` |
| Never saved | **0** | none at all |

A directory reaches the second state when it was created but never written —
`mkdir` writes only the directory record. A reader MUST treat `fSeekKeys == 0` as
"no keys", not as corruption.

> Demonstrated by `container/empty-directory`, which holds one of each:
> `saved` has `fSeekKeys = 421` pointing at a record with `fObjlen = 4` and a
> count of zero; `unsaved` has `fSeekKeys = 0` and `fNbytesKeys = 0`.

## 7. Version history

| On-disk version | ROOT | Payload | Change |
|---|---|---|---|
| 1 | ≤ 3.02 | 30 B | **No UUID at all** |
| 2 | 3.03/01 – 3.03/07 | 46 B | UUID as raw 16 bytes, **no version word** |
| 3 | 3.03/09+ | 48 B | UUID gains its 2-byte version word |
| 4 | 4.00+ | 60 B | The `> 1000` large layout, and the 12 reserved bytes |
| 5 | 5.16+ | 60 B | `TDirectory` split into `TDirectory`/`TDirectoryFile`; **no layout change** |

ROOT 6.40.04 writes 5, or 1005 in the large layout.

Reading the UUID therefore depends on `version mod 1000`
(`root/io/io/src/TDirectoryFile.cxx:1792-1797`):

| `version mod 1000` | UUID |
|---|---|
| 1 | absent; read nothing |
| 2 | 16 bytes, no version word |
| ≥ 3 | 2-byte version word, then 16 bytes |

> A latent inconsistency in ROOT: `TFile::Init` reads the root directory's UUID
> with `if (versiondir > 1)`, unconditionally expecting a version word
> (`root/io/io/src/TFile.cxx:823`), so it would misparse a version-2 root
> directory — while `TDirectoryFile::Streamer` handles it correctly. This affects
> only files from ROOT 3.03/01 to 3.03/07.

## 8. Walking the tree

1. From the header, read `fBEGIN` and `fNbytesName`. Parse the directory fields at
   `fBEGIN + fNbytesName`.
2. If `fSeekKeys` is 0, the directory has no keys. Otherwise read the record at
   `fSeekKeys`, take the count, and parse that many key images.
3. For each entry whose class name is `"TDirectory"` — that is, a
   `TDirectoryFile`; see [Records §3.9](Record.md#39-fclassname) — seek to its
   `fSeekKey`, skip its `fKeylen` bytes, and parse the directory fields there.
   Recurse from step 2.
4. Resolve duplicate names by cycle; see [Records §4](Record.md#4-cycles).

Step 3 works because a subdirectory's `fNbytesName` equals its `fKeylen`, so
`fSeekKey + fKeylen` and `fSeekDir + fNbytesName` are the same byte.

Do **not** use `fSeekParent` in step 3; see §4.3.

## 9. Invariants

1. `fSeekDir` equals the offset of this directory's own record.
2. The directory fields begin at `fSeekDir + fNbytesName`.
3. `fNbytesName` equals `fKeylen` for a subdirectory, and `fKeylen` plus the
   name and title counted strings for the root directory.
4. `10 <= fNbytesName <= 10000` (`root/io/io/src/TFile.cxx:841`).
5. `fSeekKeys` is either 0, or the offset of a record whose `fNbytes` equals
   `fNbytesKeys`.
6. That record's payload begins with a count, and holds exactly that many key
   images; `4 + Σ image lengths <= fObjlen`, with any excess being at most 8
   bytes.
7. Every key image's `fSeekKey` is the offset of a record in the file, and its
   `fSeekPdir` equals this directory's `fSeekDir`.
8. Each subdirectory appears exactly once, as an entry in exactly one parent's
   key list.
9. The record's version, modulo 1000, is between 1 and 5.
10. `fDatimeC <= fDatimeM`, both decoding to valid dates.
11. Every key image **agrees with the key of the record it points at** — the same
    `fNbytes`, `fObjlen`, `fKeylen`, `fCycle`, `fClassName`, `fName` and `fTitle`.
    The image is what a reader frames the payload with, so a disagreement makes the
    object unreadable in a file ROOT itself opens without complaint (the key list is
    the only copy ROOT consults, and it never cross-checks the record's own key).

Not safe to assume: that `fSeekParent` names the mother directory (§4.3), that the
12 reserved bytes are present or zero (§5), or that the key-list payload contains
nothing after the last counted entry (§6.1).

## 10. Errata

Against `root/io/doc/TFile/tdirectory.md` and `keyslist.md`:

| # | Claim | Actually |
|---|---|---|
| 1 | `tdirectory.md` shows the payload starting at the version word | For the root directory it starts with the name and title (§1), and the page never distinguishes the root record from a subdirectory's |
| 2 | `tdirectory.md`: the record's key has `lname = 10`, class `"TDirectory"` | The first record in every file uses the `TFile`'s class: `lname = 5`, `"TFile"` (§6.2) |
| 3 | `tdirectory.md` gives large-file key offsets as `[33->33] lname`, `[34->..] ClassName` | They are `[34->34]` and `[35->..]`: `fSeekKey` occupies 18-25 and `fSeekPdir` 26-33 ([Records §2](Record.md#2-key-layout)) |
| 4 | `tdirectory.md`'s 3.02.06 table labels bytes 0-1 `fModified` / `fWritable` | Those bytes are the class version. `fModified` and `fWritable` were never written |
| 5 | `tdirectory.md`: the 12 "extra" bytes, unqualified | Present only in the small layout, and absent entirely for ROOT 3 files (§5) |
| 6 | `tdirectory.md`: `fSeekParent` is the parent's offset | Only from 6.38; before that it was the top directory's (§4.3) |
| 7 | — | Three independent large-file flags are never distinguished (§3) |
| 8 | — | Version 2 records store the UUID with no version word; version 1 has none (§7) |
| 9 | `keyslist.md`: one key list "per non-empty subdirectory" | Emptiness is not the criterion. A *saved* empty directory has a list with count 0; an *unsaved* one has none (§6.4) |
| 10 | `keyslist.md`: the list is "probably not accessed by its key" | Definitely not, and the reason is that its key is indistinguishable from two other records' (§6.2) |
| 11 | `keyslist.md` shows only the 3.02.06 layout | Missing the large variant, that each entry carries its own version so widths vary within one list, and that a large entry's `fSeekPdir` packs `fPidOffset` (§6) |
| 12 | — | Up to 8 bytes of uninitialized slack inside `fObjlen` when `fEND > 2 GB` (§6.1) |
| 13 | — | `fNbytesKeys` counts the whole record, key included (§4.1) |

## 11. Reference files

| Case | Exercises |
|---|---|
| `container/file-minimal` | The root directory record, its fields at `fBEGIN + fNbytesName` |
| `container/directories` | Two nesting levels, per-directory key lists, distinct UUIDs, `fSeekParent` |
| `container/empty-directory` | A saved empty directory versus an unsaved one |
| `container/cycles` | Several entries in one key list sharing a name |

No fixture yet covers a version 1, 2 or 3 directory record; those need files from
ROOT 3, and belong with the legacy corpus.
