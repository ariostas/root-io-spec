# A writer's invariants

Every layer of this specification ends with an `Invariants` section — **224
entries across 30 documents**, counted as the numbered items in every section
titled `Invariants` — stating what a conforming file satisfies whatever wrote it. Those sections are organised for a reader, by layer. This one is the same
material organised for a writer, by the order in which a file is produced, and it
adds the column that matters most on the write side: **who notices when you get it
wrong.**

It is an index, not the normative text. Each row points at the document that owns
the rule.

## 1. How to use it

Three sources of enforcement, and they are very unequal:

| Column | Meaning |
|---|---|
| **checked** | `tools/check_invariants.py` verifies it over every file it is given, including the ones this project writes |
| **ROOT** | ROOT says something when it is violated — the message is in the linked document |
| **nothing** | ROOT reads the file without complaint and the damage is silent. §6 collects these |

```sh
tools/check_invariants.py <your-file.root>     # the checked column, on your output
tools/check_write.py --root                    # the same, plus ROOT reading it back
```

The invariant checker is usable on a file this project had nothing to do with; that
is what it was written for.

## 2. The file

From [File header](../01-container/FileHeader.md),
[Records and keys](../01-container/Record.md),
[Directories](../01-container/Directory.md),
[Free segments](../01-container/FreeSegments.md) and
[Writing a file §12](../06-writing/WritingFiles.md#12-invariants-a-writer-should-check-on-its-own-output).

| Invariant | Where | Who notices |
|---|---|---|
| Bytes 0-3 are `root`, and `0 <= fBEGIN <= fEND <= filesize` | FileHeader 1, 2, 5 | ROOT — it refuses to open |
| `fEND` equals the last free entry's `fFirst` | FreeSegments 8, WritingFiles 12.1 | checked |
| The last free entry's `fLast` is strictly greater than `fEND` | FreeSegments 8 | nothing — and the next writer overwrites data |
| `10 <= fNbytesName <= 10000`, and it equals the root directory record's `fKeylen` plus the two counted strings | FileHeader 10.4, Directory 9 | ROOT range-checks only |
| Walking from `fBEGIN` by `fNbytes` reaches exactly `fEND`, with no overlap and no unclaimed bytes | Record 8.8 | checked |
| A freed span begins with a negative `fNbytes` | FreeSegments 4 | nothing, until a reader walks the chain |
| `fSeekFree`, `fSeekInfo` and `fSeekKeys` each name a record whose `fNbytes` matches the header's or the directory's copy | FileHeader 10.6, 10.8, Directory 9 | checked |
| Every key image in the key list is byte-identical to the first `fKeylen` bytes of the record at its own `fSeekKey` | Directory 9 | nothing |
| `fSeekPdir` is 0 in the root directory record's key and `fBEGIN` in every other key of that directory | WritingFiles 4.1 | nothing — but `TFile::Recover` filters on it |
| `fVersion >= 1000000` **iff** `fEND` exceeded 2000000000 at the last header write, and every key, directory offset and free entry uses the width its own flag selects | LargeFiles 8 | checked |

## 3. Each object

From [Buffer framing](../02-serialization/Buffer.md),
[Streamer information](../02-serialization/StreamerInfo.md),
[Element types](../02-serialization/ElementTypes.md),
[Compression](../01-container/Compression.md) and
[Writing an object §9](../06-writing/WritingObjects.md#9-invariants).

| Invariant | Where | Who notices |
|---|---|---|
| A byte count equals the bytes that follow it, to the end of the object it frames | Buffer 9 | ROOT — `CheckByteCount`, unless there is no byte count at all |
| A class name appears in full once per record; later occurrences are `0x80000000 \| position` | Buffer 9 | nothing |
| Every map position is at least 2; a class is mapped at its tag word, an object at its byte count | Buffer 6.1, 6.2 | nothing |
| `fObjlen > fNbytes - fKeylen` **iff** the payload is compression blocks | Compression 1 | nothing — the inequality *is* the flag |
| For one block, `9 + compressed size == fNbytes - fKeylen` and `uncompressed size == fObjlen` | Compression 4 | ROOT — the unzip fails |
| A counted pointer is one flag byte and then exactly the count's worth of values | ElementTypes 4 | nothing |
| A version word is the class's own `ClassDef` version, or 0 followed by a checksum for a class with none | Buffer 3, 4 | ROOT — for a version it cannot resolve |
| An info's `fCheckSum` is what the algorithm produces for the class it describes | StreamerInfo 11 | ROOT — `BuildCheck` warns at equal version |
| Every `TList` entry in the `StreamerInfo` record is followed by one option byte; `TObjArray` entries by none | StreamerInfo 4, 5 | nothing |
| Every class whose version word is above 0 has an info in the file, or is one a reader knows out of band | WritingObjects 9.5 | nothing for ROOT; everything for every other reader |

## 4. A histogram

From [Writing histograms §9](../06-writing/WritingHistograms.md#9-invariants).

| Invariant | Who notices |
|---|---|
| `fNcells == fXaxis.fNbins + 2`, and the `TArray` base's `fN` equals `fNcells` | checked |
| `fSumw2` is empty or has exactly `fNcells` entries | checked |
| `fXbins` is empty or has `fNbins + 1` entries, whose first and last are `fXmin` and `fXmax` | checked |
| `fYaxis` and `fZaxis` are present, with `fNbins` 1 in a 1-D histogram | checked |
| `fBufferSize` is 0 **iff** `fBuffer`'s flag byte is 0 | checked |
| `fMaximum` and `fMinimum` are `-1111` unless a range was set | nothing — the histogram simply draws wrong |
| The statistics are consistent with each other: `fTsumw <= fEntries` for unit weights | nothing |

## 5. A tree

From [Writing trees §8](../06-writing/WritingTrees.md#8-invariants), and the
reading side's [TBranch](../04-ttree/TBranch.md),
[TBasket](../04-ttree/TBasket.md) and [TLeaf](../04-ttree/TLeaf.md).

| Invariant | Who notices |
|---|---|
| `fBasketSeek[i]` names a record whose key reports the same `fSeekKey` | **ROOT** — the one consistency check it makes on a tree |
| `fBasketEntry[0] == fFirstEntry` | ROOT — "no basket contains the entry" |
| `fBasketEntry[fWriteBasket] == fEntryNumber`, and the array increases | nothing: too small loses entries silently, too large reads stale values |
| `fMaxBaskets >= fWriteBasket + 1`, and the three counted arrays hold exactly `fMaxBaskets` values each | checked |
| A branch's `fEntryOffsetLen` is non-zero **iff** its baskets carry an offset array | checked |
| In a basket, `fLast == fKeylen +` the data length, and the offset array's first element is `fKeylen` — the latter only when the array holds offsets rather than `kGenerateOffsetMap` deltas | checked |
| A counter leaf has `fIsRange` set and an `fMaximum` at least every count in the file | nothing — ROOT clamps the read with a `printf` |
| A leaf's `fLeafCount` names a leaf written earlier in the same record | nothing |
| `fEntries` on the tree agrees with the branches, and no entry is reachable past it | checked |
| The key list contains no `TBasket` key | checked |
| `fMaxVirtualSize >= 0` | nothing |

## 6. The ones ROOT does not notice

The shortest useful list in this document: violations that produce a file ROOT
reads without a word, and that another reader may reject or misread. Each is
specified where the table above says. Several of them **are** caught by
`tools/check_invariants.py` — the column in §1 says which — so "nothing" here means
nothing in ROOT, not nothing at all.

1. **`fObjlen` inconsistent with the stored length.** There is no codec flag; the
   inequality is the flag. A compressed payload with `fObjlen` left equal to the
   stored length hands a zip stream to the streamer.
2. **A key image in the key list that disagrees with the record it points at.**
   The image is what frames the read.
3. **A last free entry whose `fFirst` is below the live data.** The file reads;
   the next writer overwrites a record and then truncates the file logically.
4. **A class back-reference with the wrong position.** Correct until the second
   occurrence of a class, so small records are fine and large ones are not.
5. **A wrong member order with the right total length.** `CheckByteCount` compares
   lengths, not contents.
6. **Anything inside a `TObject`, `TString` or `TArray`**, none of which carries a
   byte count at all.
7. **A `fBasketEntry` terminator that is too large**, which reads past the basket
   and leaves the destination untouched.
8. **A counter leaf's `fMaximum` set too low**, which clamps the read and
   desynchronises the rest of the entry.
9. **A missing streamer info.** ROOT reads a class it has compiled in without one,
   and the warning that would say so fires only when the file's `fVersion` differs
   from the running ROOT's — so a writer stamping the current release silences it.
   Every reader that is not ROOT needs the info.

Items 1, 2, 3, 4, 6 and 7 are checked by `tools/check_invariants.py`, which is why
running it over your own output is worth more than reading this list. Item 2 became
checkable on 2026-09-18, as
[Directories §9](../01-container/Directory.md#9-invariants) invariant 11: nothing had
compared a key image against the key of the record it points at, which is precisely
the comparison ROOT never makes either.

## 7. What is deliberately not constrained

A writer may choose freely, and ROOT's own choices are given in the writing
documents only so that a byte comparison against a ROOT-written file stays
readable: where records are placed within the file, basket and buffer sizes, how
many entries a cluster holds, which compression setting to use per record, key
ordering within a directory, the `fDatime` of a key and the UUID of a file, and
every attribute of `TAttLine`, `TAttFill`, `TAttMarker` and `TAttAxis`.

`spec/06-writing/` marks each field **fixed**, **derived** or **free** for exactly
this reason.
