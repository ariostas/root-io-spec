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

Between the two lie the record's key and, for the root directory only, a second
copy of the file's name and title as counted strings. That copy is written by
`TFile::Init`, not by the directory streamer (`root/io/io/src/TFile.cxx:708`),
because the object stored at `fBEGIN` is the `TFile` itself: its image is a
`TNamed` part followed by a `TDirectoryFile` part.

> ROOT never reads that copy back. Every reader skips `fNbytesName` bytes from
> `fSeekDir`. `TFile::Init` reads the payload's class name and name into a
> throwaway `TString` (twice into the same variable, with the comment *"file may
> have been renamed"*) and keeps only `fTitle`
> (`root/io/io/src/TFile.cxx:836-839`). `fName` is never taken from the file: it
> stays the path the caller passed to `TFile::Open`, so a renamed file still
> opens.

A subdirectory record has no such prefix; its fields begin immediately after its
key. One rule covers both cases, because `fNbytesName` differs:

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

Written by `root/io/io/src/TDirectoryFile.cxx:748-787`. The total is 60 bytes in
both layouts, which is what the reserved bytes are for (§5).

The datime fields use the packing given in
[Records §3.7](Record.md#37-fdatime). `fDatimeC` is the directory's creation
time, set once; `fDatimeM` is refreshed on every header rewrite
(`root/io/io/src/TDirectoryFile.cxx:2175`).

## 3. Three independent large-file flags

> ROOT has three separate large-file switches, on three different structures,
> with three different conditions. Confusing them is a common cause of
> mis-parsing.

| Structure | Flag | Condition |
|---|---|---|
| File header | `fVersion >= 1000000` | `fEND > 2000000000` |
| Key | `fVersion > 1000` | the file's `fEND` when the key was built `> 2000000000`, or a non-zero `fPidOffset`; not the key's own offset ([Large files §1.1](LargeFiles.md#11-a-keys-width-is-not-decided-by-where-the-key-is)) |
| Directory record | version `> 1000` | any of `fSeekDir`, `fSeekParent`, `fSeekKeys` `> 2000000000` |

A reader MUST take the directory layout from the **directory record's own version
word**, never from the file header. All three of its offsets widen together;
there is one flag, not one per field.

`TDirectoryFile::Streamer` is a second writer of the same record, with a
different condition: `fEND`, not the three offsets
(`root/io/io/src/TDirectoryFile.cxx:1827`). This matters to a writer, not to a
reader. [Large files](LargeFiles.md) collects all five switches.

The flags are not equivalent. A file larger than 2 GB can still hold
small-layout directory records (the root directory's `fSeekDir` is `fBEGIN`,
normally 100), so the header flag tells a reader nothing about any given
directory. The converse does hold: a directory offset beyond 2 GB implies that
`fEND` is beyond 2 GB as well.

### 3.1 The version word carries two independent things

> **A directory record's class version and its offset width are separate axes,
> and the version word is their sum.** The width flag `1000` is added to the class
> version: `version = TDirectoryFile::Class_Version()`, then `version += 1000`
> (`root/io/io/src/TDirectoryFile.cxx:750`, `:759`). `version % 1000` is
> therefore the class version and `version > 1000` the width, and neither implies
> anything about the other.

ROOT's own files do not show this, because ROOT always writes the class version it
was compiled with. 6.40.04 emits 5 or 1005 and nothing else, and every wide record
ROOT has ever written is 1004 or 1005, so §7's history reads as though the wide
form arrived with class version 4. That is true of ROOT, but not of the format.

A third-party writer that uses an older class version with the flag produces a
combination ROOT never emits. Two files in the corpus do so:
`uproot-from-geant4.root` and `uproot-issue-250.root`, both written by g4tools,
have version 1001, which is class version 1 (no UUID) with three 8-byte offsets. A
reader that tests `version > 1` for the UUID instead of `version % 1000 > 1` reads
sixteen bytes from past the end of the record. ROOT reads these files correctly,
because both of its readers take the UUID from `version % 1000`
(`root/io/io/src/TFile.cxx:808`, `:823`;
`root/io/io/src/TDirectoryFile.cxx:1792-1796`).

The payload length therefore depends on both axes and on the file header's
version. §7.1 tabulates it, and invariant 15 checks it.

## 4. Fields

### 4.1 `fNbytesKeys`

The length of the **whole key-list record**, key header included: the `fNbytes`
of the key at `fSeekKeys` (`root/io/io/src/TDirectoryFile.cxx:2226`). It is used
as a raw read length. It is zero when there is no key list.

### 4.2 `fSeekDir`

The offset of this directory's own record. Being self-referential, it is a
useful corruption check. For the root directory it equals `fBEGIN`.

### 4.3 `fSeekParent` — do not use it for parentage

> **`fSeekParent` changed meaning in ROOT 6.38.** Before commit
> `06735e7655f` (2025-08-02, first released in 6.38.00) it held the top
> directory's offset for every nested directory, not the mother's. From 6.38 it
> holds the mother's (`root/io/io/src/TDirectoryFile.cxx:155`).
>
> A reader MUST NOT reconstruct the directory tree from `fSeekParent`. Use the
> key's `fSeekPdir`, or the containment implied by walking key lists. Files
> written before 6.38 are extremely common, and in them every directory appears
> to be a child of the root.

It is 0 for the root directory.

> In `container/directories`, written by 6.40.04, `beta`'s `fSeekParent` is 401,
> the offset of `alpha`'s record, as expected after 6.38. A pre-6.38 writer would
> have put 100 there.

### 4.4 `fSeekKeys`

The offset of the key-list record's key, or 0 when this directory has no key
list. Zero is normal, not a sign of corruption (§6).

### 4.5 UUID

A 2-byte version word, always 1, then 16 bytes in RFC 4122 wire layout, the same
encoding as the file header's UUID
([File header §6](FileHeader.md#6-uuid)).

Each directory has its own, distinct UUID. The root directory's matches the file
header's, because both are written from the same value at creation; each
subdirectory gets a fresh one.

Version 2 records are the exception: they store the 16 bytes with no version word
(§7).

## 5. The reserved bytes

In the small layout, 12 zero bytes follow the UUID. They are slack: at the
current class version they make the record 60 bytes whether or not the three
offsets are 64-bit, so ROOT can rewrite a directory header in place when a file
grows past 2 GB (`root/io/io/src/TDirectoryFile.cxx:2177-2181`).

A reader MUST NOT assume they are present or zero:

- in the large layout they are not padding but the high halves of the three
  offsets;
- whether they are written depends on the file header's version, not the
  record's: for a file written by ROOT 3 (`fVersion < 40000`) they are absent
  (`root/io/io/src/TDirectoryFile.cxx:785`), which is why a version-3 record is 48
  bytes, not 60;
- the equal length holds for class versions 4 and 5 only. At version 1 the small
  and wide forms are 30 and 42 bytes, and §7.1 has the rest.

The authoritative length is the record's `fObjlen`.

## 6. Key lists

A key list is a record whose payload is a count followed by that many key images:

| Offset | Field | Type |
|---|---|---|
| 0 | count | `i32` |
| 4 … | `count` key images | each a `TKey` header |

Each image is normally byte-identical to the first `fKeylen` bytes of the record
it describes, laid out as in [Records §2](Record.md#2-key-layout). **Each image
has its own `fVersion`**, so small and large images may be interleaved in one
list. A reader must size each entry individually by parsing it, not from its
`fKeylen`, which is a separate number that can disagree (§6.5).

### 6.1 The count is authoritative

> A reader MUST iterate exactly `count` times, and MUST NOT parse until the
> payload is exhausted. When `fEND > 2000000000`, ROOT allocates the payload 8
> bytes larger than it writes (`root/io/io/src/TDirectoryFile.cxx:2209`), and that
> slack is uninitialized heap. A length-driven parse will read garbage as an
> entry.

There is no trailing checksum and no terminator.

### 6.2 The key-list record cannot be identified from its key

Its key has the containing directory's name, title and class: `"TFile"` for the
root directory, `"TDirectory"` for a subdirectory
(`root/io/io/src/TDirectoryFile.cxx:2213`). It is therefore indistinguishable from
the directory record itself and from the free-segment record.

The only supported way to find it is `fSeekKeys` from the directory record.
`TFile::Recover` cannot recover it either, and deliberately skips anything whose
class inherits from `TFile` (`root/io/io/src/TFile.cxx:2171-2172`).

> In `container/directories`, three separate records carry the class name
> `"TFile"` and the file's own name: the root directory at 100, its key list at
> 1255, and the free list at 1755.

### 6.3 What is in the list

Present: object keys, and each subdirectory's key.

Absent: the directory's own record key, the key-list record's own key, the
free-segment record's key — none of which are ever appended — and the
`StreamerInfo` record, which is explicitly removed
(`root/io/io/src/TFile.cxx:3522`).

### 6.4 Empty and unsaved directories

A directory can be in either of two states, both legal:

| State | `fSeekKeys` | Key list |
|---|---|---|
| Saved, holds nothing | non-zero | a record whose payload is the 4-byte count `0` |
| Never saved | 0 | none at all |

A directory is in the second state when it was created but never written, since
`mkdir` writes only the directory record. A reader MUST treat `fSeekKeys == 0` as
"no keys", not as corruption.

> Demonstrated by `container/empty-directory`, which holds one of each:
> `saved` has `fSeekKeys = 421` pointing at a record with `fObjlen = 4` and a
> count of zero; `unsaved` has `fSeekKeys = 0` and `fNbytesKeys = 0`.

### 6.5 An image's length is what it parses to, never its `fKeylen`

> A reader MUST advance from one image to the next by the bytes the image
> occupies (18 or 26 fixed bytes, then three counted strings), and MUST NOT add
> `fKeylen` to the current offset. The two numbers can differ: `fKeylen`
> describes the record, and in one kind of file they are four bytes apart.

Both the key at the head of a record and the image of that key in a key list are
produced by `TKey::FillBuffer` (`root/io/io/src/TKey.cxx:647-684`). For the key
list the caller is `TDirectoryFile::WriteKeys`, which loops over the directory's
live keys (`root/io/io/src/TDirectoryFile.cxx:2221-2223`) and sizes its record
with `TKey::Sizeof` (`:2211`). The image is therefore a byte copy of the key as it
would be written when the list is written, not of what was written when the
record was created. For a directory these are not always the same bytes.

Four places decide how a directory key spells its class, and until 2012 they did
not agree:

| Where | Current ROOT | Before 5.34 |
|---|---|---|
| `TKey::Build`, at creation | sets the `kIsDirectoryFile` bit (`root/io/io/src/TKey.cxx:452`) | overwrote `fClassName` with `"TDirectory"` |
| `TKey::ReadKeyBuffer`, on the way in | sets `fClassName` to `"TDirectoryFile"` and the bit (`root/io/io/src/TKey.cxx:1290-1293`) | set `fClassName` only |
| `TKey::FillBuffer`, on the way out | writes `"TDirectory"` when the bit is set (`root/io/io/src/TKey.cxx:676-679`) | wrote `fClassName` verbatim |
| `TKey::Sizeof` | counts 11 for it, hard-coded (`root/io/io/src/TKey.cxx:1374-1375`) | counted `fClassName.Sizeof()` |

Commit `713f56ea03f` (2012-01-26, first released in 5.34/00) moved the
substitution from creation to the write, and that made the four agree. Before it,
the spelling a key had depended on where the key came from:

- **created** in this process by `TFile::mkdir`: `fClassName` was `"TDirectory"`,
  so every copy of it spelled `TDirectory`, in 11 bytes;
- **read back** from disk: `ReadKeyBuffer` changed it to `"TDirectoryFile"`
  while `fKeylen` kept the value on disk, sized for the short spelling. `Sizeof`
  then reserved 15 bytes for the name and `FillBuffer` wrote them, but `fKeylen`
  is written from the member as it stands (`root/io/io/src/TKey.cxx:658`), and
  nothing recomputed it.

A key list written by ROOT 5.32 or earlier can therefore hold a directory entry
that

- spells its class `TDirectoryFile`, where the record's own key (written once, at
  creation) spells it `TDirectory`;
- reports an `fKeylen` four bytes smaller than the image itself, because
  `sizeof("TDirectoryFile") - sizeof("TDirectory")` is 4.

The enclosing record is not short: `Sizeof` reserved the 15 bytes that were
written, so `fObjlen` covers the images exactly. Only `fKeylen` is stale. ROOT is
unaffected, because `ReadKeyBuffer` advances the buffer pointer past the strings
it has parsed. A reader that trusts `fKeylen` desynchronises at the next entry and
frames a key from the middle of one.

> `uproot-issue64.root` (ROOT 5.28/00) is the measured case, and it has both
> spellings. Of the root directory's five subdirectories, `macros` and `events`
> are listed as `TDirectoryFile` in 55 bytes with `fKeylen` 51, while `detector`,
> `physics` and `generator` are listed as `TDirectory` in the 55, 53 and 57 bytes
> their `fKeylen` reports. Parsing the images consumes the record's 544-byte
> `fObjlen` exactly; summing their `fKeylen` gives 536. The first two keys had
> been read back from disk by the time the list was written and the last three
> had not, which reflects the program that wrote the file rather than the format.

**The two spellings are one class name.** ROOT normalises either spelling to
`TDirectoryFile` in memory, so a reader comparing two keys' class names must treat
them as equal, and a reader looking for subdirectories must accept both (§8).

## 7. Version history

| Class version | ROOT | Change |
|---|---|---|
| 1 | ≤ 3.03/06 | No UUID at all |
| 2 | 3.03/07 only | UUID as raw 16 bytes, no version word |
| 3 | 3.03/08 – 3.10 | UUID gains its 2-byte version word |
| 4 | 4.00+ | The `> 1000` large layout, and the 12 reserved bytes |
| 5 | 5.15/02+, 5.16 in production | `TDirectory` split into `TDirectory`/`TDirectoryFile`; no layout change |

ROOT 6.40.04 writes 5, or 1005 in the large layout.

The boundaries are release tags, read from the submodule's history, which
reaches back to ROOT 1: `v3-03-06` has `ClassDef(TDirectory,1)`, `v3-03-07` has
2 and `v3-03-08` has 3. Version 2 arrived on the development trunk on
2002-07-09 (root commit `a84103dbe0d`, "Each directory has now a universal
unique id") and was replaced on 2002-08-02 (`ce1a652165b`), so exactly one
release, 3.03/07, wrote it, along with the development builds between those two
dates. The same commit series gave the file header its UUID (FileHeader §8).

> `root/roottest/root/io/arrayobject/Event.3.2.0.root`, written by ROOT 3.03/02,
> holds a version 1 root directory: 30 bytes, no UUID, and its file header's UUID
> bytes are zero.

Reading the UUID therefore depends on `version mod 1000`
(`root/io/io/src/TDirectoryFile.cxx:1792-1796`):

| `version mod 1000` | UUID |
|---|---|
| 1 | absent; read nothing |
| 2 | 16 bytes, no version word |
| ≥ 3 | 2-byte version word, then 16 bytes |

> A latent inconsistency in ROOT: `TFile::Init` reads the root directory's UUID
> under `if (versiondir > 1)` and always expects a version word
> (`root/io/io/src/TFile.cxx:823`), so it would misparse a version-2 root
> directory, which `TDirectoryFile::Streamer` handles correctly. This affects
> only files from ROOT 3.03/07.

### 7.1 Payload length per version *and* width

Because the two axes are independent (§3.1), the length depends on both, and on
one thing outside the record: whether the reserved bytes are present depends on
the file header's version, not the directory's
(`root/io/io/src/TDirectoryFile.cxx:1725-1735`, written at `:785-786`). The length
is the sum of:

| Contribution | Bytes |
|---|---|
| version word, `fNbytesKeys`, `fNbytesName`, `fDatimeC`, `fDatimeM` | 18 |
| the three offsets | 12 small, 24 wide |
| UUID: `version mod 1000` of 1 / 2 / ≥ 3 | 0 / 16 / 18 |
| reserved, only when `fVersion >= 40000` and the record is small | 12 |

which gives:

| `version mod 1000` | `fVersion` | Small | Wide |
|---|---|---|---|
| 1 | < 40000 | **30** | 42 |
| 1 | ≥ 40000 | 42 | **42** |
| 2 | < 40000 | 46 | 58 |
| 3 | < 40000 | **48** | 60 |
| 4, 5 | ≥ 40000 | **60** | **60** |

Bold entries are measured on real files; the rest are computed. The `fVersion`
column pairs as shown because ROOT's class version and its file version advanced
together. Only ROOT couples them: g4tools writes class version 1 with `fVersion`
40000, which is why the second row is needed. The wide column does not depend on
`fVersion`, because the reserved bytes are never written in the wide layout.

The 60-and-60 row is what the reserved bytes are for (§5): at the current class
version, and only there, the record is the same length in both layouts.

> `pippa.root` (ROOT 2.24/00) supplies the 30; `mlpHiggs.root` and
> `H1display.root` the 48, both with `fVersion` below 40000 and so without
> reserved bytes; and the two g4tools files the 42, the combination ROOT does not
> write. 475 records in `data/` and the corpora supply the 60. Over all 503
> directory records in `data/` and both corpora, the table predicts the payload
> exactly, with no exceptions (invariant 15).

## 8. Walking the tree

1. From the header, read `fBEGIN` and `fNbytesName`. Parse the directory fields at
   `fBEGIN + fNbytesName`.
2. If `fSeekKeys` is 0, the directory has no keys. Otherwise read the record at
   `fSeekKeys`, take the count, and parse that many key images.
3. For each entry whose class name is `"TDirectory"` or `"TDirectoryFile"`
   (one class either way; see [Records §3.9](Record.md#39-fclassname) and §6.5),
   seek to its `fSeekKey`, skip its `fKeylen` bytes, and parse the directory
   fields there. Recurse from step 2.
4. Resolve duplicate names by cycle; see [Records §4](Record.md#4-cycles).

Step 3 works because a subdirectory's `fNbytesName` equals its `fKeylen`, so
`fSeekKey + fKeylen` and `fSeekDir + fNbytesName` are the same byte.

Do not use `fSeekParent` in step 3 (§4.3).

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
11. Every key image agrees with the key of the record it points at: the same
    `fNbytes`, `fObjlen`, `fKeylen`, `fCycle`, `fClassName`, `fName` and `fTitle`,
    with `TDirectory` and `TDirectoryFile` counting as one class name (§6.5).
    A reader frames the payload with the image, so a disagreement makes the
    object unreadable in a file ROOT itself opens without complaint (the key list
    is the only copy ROOT consults, and ROOT never cross-checks the record's own
    key).
12. The key-list record's own key has, in `fSeekPdir`, the `fSeekDir` of the
    directory that owns the list, not that directory's parent
    (`root/io/io/src/TDirectoryFile.cxx:2213`). This is the only structural link
    from a key list back to its directory, since the record is otherwise
    indistinguishable from the directory record (§6.2).
13. Each image occupies exactly its own `fKeylen` bytes in the list, except a
    directory entry written before ROOT 5.34 that spells its class
    `TDirectoryFile`, which occupies exactly 4 bytes more (§6.5). No other
    difference is legitimate. A reader that adds `fKeylen` instead of parsing gets
    no warning in either case.
14. Images sharing a name have **distinct cycles, in descending order**, and no
    cycle is 0. `TDirectoryFile::AppendKey` puts each new key in front of the
    first key with its name (`root/io/io/src/TDirectoryFile.cxx:225-256`), and
    ROOT's lookups rely on this: `Get`, `GetKey` and `FindKeyAny` return the first
    match, not the highest cycle (`:1002`, `:1167`, `:829`). A list in ascending
    order resolves every unqualified name to the oldest copy, with no diagnostic,
    as measured in
    [Writing a file §8.1](../06-writing/WritingFiles.md#81-where-a-key-goes-in-the-list-and-what-cycle-it-gets).
    Real files rarely exercise this: across both corpora and `data/`, 502 key
    lists hold 2506 keys, and only 15 name groups have more than one cycle, all
    15 in descending order. `data/written/cycles-3.root` is the main
    test of the invariant. No corpus file has a negative `fCycle`, so none
    demonstrates the keep flag. A negative `fCycle` is the keep flag and counts as
    its magnitude (§3.8 of [Records](Record.md#38-fcycle)).
15. The payload, `fObjlen` less the `fNbytesName - fKeylen` prefix, is exactly the
    length §7.1 gives for its class version, its offset width and the file
    header's version. Measured on all 503 directory records of `data/` and both
    corpora.

    This invariant checks §3.1's class-version axis: a record whose version
    implies a different UUID framing from the one written is off by 16 or 18
    bytes, and no other check catches it. The width axis needs no invariant of its
    own, because a record with the wrong width flag fails invariant 1 first:
    reading the offsets at the wrong width leaves `fSeekDir` pointing somewhere
    other than the record itself, so the record is not recognised as a directory.
    Corrupting `container/directories` confirms this: changing the version word
    from 5 to 1005 reports five keys whose `fSeekPdir` no longer names a directory
    ([Records §8](Record.md#8-invariants)), and changing it from 5 to 1 reports
    this invariant.

Not safe to assume: that `fSeekParent` names the mother directory (§4.3), that the
12 reserved bytes are present or zero (§5), that the key-list payload contains
nothing after the last counted entry (§6.1), or that an image is exactly
`fKeylen` bytes long (§6.5).

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
| 10 | `keyslist.md`: the list is "probably not accessed by its key" | It is never accessed by its key, because its key is indistinguishable from two other records' keys (§6.2) |
| 11 | `keyslist.md` shows only the 3.02.06 layout | Missing the large variant, that each entry carries its own version so widths vary within one list, and that a large entry's `fSeekPdir` packs `fPidOffset` (§6) |
| 12 | — | Up to 8 bytes of uninitialized slack inside `fObjlen` when `fEND > 2 GB` (§6.1) |
| 13 | — | `fNbytesKeys` counts the whole record, key included (§4.1) |
| 14 | `keyslist.md` presents each entry as a copy of the record's key, so its length is `fKeylen` | A directory entry written before ROOT 5.34 is 4 bytes longer than the `fKeylen` it reports, and spells its class `TDirectoryFile` where the record spells it `TDirectory` (§6.5). Both spellings occur in one file |
| 15 | *This document, until 2026-09-22*: §7's table ended version 1 at 3.02 and began version 2 at 3.03/01 | Version 1 runs to 3.03/06 and version 2 is 3.03/07 only, by `ClassDef` at the release tags. `Event.3.2.0.root`, written by 3.03/02, has a version 1 root directory (§7) |

## 11. Reference files

| Case | Exercises |
|---|---|
| `container/file-minimal` | The root directory record, its fields at `fBEGIN + fNbytesName` |
| `container/directories` | Two nesting levels, per-directory key lists, distinct UUIDs, `fSeekParent` |
| `container/empty-directory` | A saved empty directory versus an unsaved one |
| `container/cycles` | Several entries in one key list sharing a name, newest first (invariant 14) |
| `container/reopened` | A key list rebuilt by a second session: keys copied verbatim, a new one inserted, and one removed by `WriteDelete` |
| `written/reopen-add` | The same file written here, and `fDatimeM` refreshed while `fDatimeC` is not |

No fixture covers a version 1, 2 or 3 directory record, and none can, because no
ROOT this project can run writes one; `data/` is version 5 throughout, 104 records
across 98 files. The legacy corpus supplies them instead, and §7.1 says which
file measures each payload size. `pippa.root` (ROOT 2.24/00) holds 24 version 1
records, 23 of them subdirectories of exactly 30 bytes. `mlpHiggs.root` (3.04/02) and
`H1display.root` (3.05/07) hold one version 3 record each, 48 bytes after the name
and title copy, with no reserved bytes. Five further files have version 4.

The smallest witnesses of each are in `root/roottest/`, which the pinned submodule
ships (`gen/cern/README.md` lists them): `Event.3.2.0.root` (9 227 bytes, ROOT
3.03/02) for version 1, `data_v3_05_07.root` (1 199 bytes) for version 3 and
`data_v4_00_02.root` (1 225 bytes) for version 4. The first is also what dates
§7's first row.

No file witnesses version 2: only ROOT 3.03/07 wrote it, and 0 of roottest's 273
files have it. Its UUID without a version word is therefore the only row of §7
that rests on the source alone. The two version 1001 records in `gen/foreign/`
cover the other axis: class version 1 in the wide layout, 42 bytes, no UUID
(§3.1).

For the same reason no fixture has §6.5's mismatched image. It is demonstrated
instead by `uproot-issue64.root` in the third-party corpus
(`gen/foreign/MANIFEST.sha256`), which `tools/check_invariants.py` reads and
accepts for the reason §6.5 gives.
