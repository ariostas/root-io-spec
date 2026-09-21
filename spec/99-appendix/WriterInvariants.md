# A writer's invariants

Every layer of this specification ends with an `Invariants` section — **257
entries across 32 documents**, counted as the numbered items in every section
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
| **nothing** | ROOT reads the file without complaint and the damage is silent. §7 collects these |

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
[Writing a file §14](../06-writing/WritingFiles.md#14-invariants-a-writer-should-check-on-its-own-output).

| Invariant | Where | Who notices |
|---|---|---|
| Bytes 0-3 are `root`, and `0 <= fBEGIN <= fEND <= filesize` | FileHeader 1, 2, 5 | ROOT — it refuses to open |
| `fEND` equals the last free entry's `fFirst` | FreeSegments 8, WritingFiles 14.1 | checked |
| The last free entry's `fLast` is strictly greater than `fEND` | FreeSegments 8 | nothing — and the next writer overwrites data |
| `10 <= fNbytesName <= 10000`, and it equals the root directory record's `fKeylen` plus the two counted strings | FileHeader 10.4, Directory 9 | ROOT range-checks only |
| Walking from `fBEGIN` by `fNbytes` reaches exactly `fEND`, with no overlap and no unclaimed bytes | Record 8.8 | checked |
| A freed span begins with a negative `fNbytes` | FreeSegments 4 | nothing, until a reader walks the chain |
| A record placed in a span with bytes to spare is followed by a four-byte marker holding the remainder, and that remainder is in the free list | FreeSegments 8.6, WritingFiles 14.13 | checked |
| **No free segment is 1, 2 or 3 bytes long** — the allocator skips a span it cannot leave a marker in | FreeSegments 8.10, WritingFiles 14.14 | checked |
| Keys sharing a name carry **distinct cycles in descending order**, and none is 0 | Directory 9.14, WritingFiles 14.15 | checked — and nothing on ROOT's side: it takes the first match, so the wrong order returns the oldest copy |
| A **negative** `fCycle` is the keep flag, and its magnitude is the cycle — a writer copying keys must not normalise the sign away | Record 3.8, WritingFiles 8.2 | nothing |
| No two **live** records overlap. A record placed in released space lands on the bytes of the one that was there, which is correct | WritingFiles 14.16 | nothing — `tools/rootwrite.py` checks it as it writes, because a finished file cannot say which of two records was meant to be live |
| `fSeekFree`, `fSeekInfo` and `fSeekKeys` each name a record whose `fNbytes` matches the header's or the directory's copy | FileHeader 10.6, 10.8, Directory 9 | checked |
| Every key image in the key list is byte-identical to the first `fKeylen` bytes of the record at its own `fSeekKey` | Directory 9 | nothing |
| `fSeekPdir` is 0 in the root directory record's key and `fBEGIN` in every other key of that directory | WritingFiles 4.1 | nothing — but `TFile::Recover` filters on it |
| A subdirectory's `fNbytesName` is its own record's `fKeylen` alone, so its fields begin where its key ends | Directory 9.3, WritingFiles 5.2 | checked |
| A subdirectory's key spells its class `TDirectory`, and its `fKeylen` is sized for that spelling and not for `TDirectoryFile` | WritingFiles 5.2, Directory 6.5 | nothing — the four-byte difference is invisible to ROOT, which parses the strings rather than trusting `fKeylen` |
| Every key image occupies exactly its own `fKeylen` bytes in the list | Directory 9.13 | checked — with the one pre-5.34 exception the invariant names |
| A key-list record's key carries the `fSeekDir` of the directory that **owns** the list, not its parent's | Directory 9.12, WritingFiles 5.4 | checked |
| Each subdirectory appears in exactly one parent's key list, and its own list holds only what it contains | Directory 9.8, WritingFiles 5.4 | checked |
| A directory record is never freed and never relocated, so subdirectories add no free entries to a create-only file | WritingFiles 5.3 | nothing — but ROOT refuses to free one itself (`TKey::Delete`) |
| `fVersion >= 1000000` **iff** `fEND` exceeded 2000000000 at the last header write, and every key, directory offset and free entry uses the width its own flag selects | LargeFiles 8 | checked |
| `fBEGIN` is at least the header its own `fVersion` selects — 63 bytes small, **75** large | FileHeader 10.11, WritingFiles 14.17 | checked — and nothing on ROOT's side, which writes the header over the first record instead |

## 3. Each object

From [Buffer framing](../02-serialization/Buffer.md),
[Streamer information](../02-serialization/StreamerInfo.md),
[Element types](../02-serialization/ElementTypes.md),
[Compression](../01-container/Compression.md),
[Writing an object §10](../06-writing/WritingObjects.md#10-invariants) and
[Element lists §13](../06-writing/ElementLists.md#13-invariants).

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
| Every class whose version word is above 0 has an info in the file, or is one a reader knows out of band | WritingObjects 10.5 | nothing for ROOT; everything for every other reader |
| Two entries for one class at the same `fClassVersion` **and** `fCheckSum` have identical element lists | SchemaEvolution 9.6 | checked |
| **The transitive closure**: every base class and every contained class has an info too, unless its `Streamer` is hand-written or forwarding | WritingObjects 8.2 | ROOT — loudly, and only for a reader without the base compiled in: `BuildOld` skips the base, `CheckByteCount` reports the short read, and the class comes out the wrong size |
| A `TStreamerBase` element's `fBaseCheckSum` is the base info's `fCheckSum`, or 0 | StreamerInfo 13.7 | checked |
| `fBaseVersion` is the base version the derived class was **built against** — not necessarily the version of the base info beside it | StreamerInfo 9.2 | nothing, and it is not an invariant: five corpus files disagree with their own base infos and all five are correct |
| A writer whose info for a class disagrees with an existing file's **at the same version** bumps the version or refuses; it does not write anyway | WritingObjects 8.5 | ROOT warns at open and then silently truncates the object it writes |
| A `TStreamerBase` element's `fMaxIndex[1]` is the base class's own checksum, at the version its `fBaseVersion` gives | ElementLists 10.2 | nothing — it is folded into the derived class's checksum, which ROOT checks instead |
| A `TStreamerBasicPointer`'s counter exists in the class `fCountClass` names, and that member's `fType` is 6 `kCounter` | ElementLists 10.3 | nothing |
| Each element's `fTypeName` is the resolved spelling of its type, and exactly `BASE` for a base class | ElementLists 11.1 | ROOT — `CompareContent` compares type names when a checksum mismatches |

## 4. A histogram or a profile

From [Writing histograms §10](../06-writing/WritingHistograms.md#10-invariants).

| Invariant | Who notices |
|---|---|
| `fNcells` is `fXaxis.fNbins + 2`, or `(nx + 2) * (ny + 2)` for a `TH2`, and the `TArray` base's `fN` equals it | checked |
| `fSumw2` is empty or has exactly `fNcells` entries | checked |
| `fXbins` is empty or has `fNbins + 1` entries, whose first and last are `fXmin` and `fXmax` — on every axis | checked |
| `fYaxis` and `fZaxis` are present, and an axis past the histogram's dimension has `fNbins` 1 | checked |
| `fBufferSize` is 0 **iff** `fBuffer`'s flag byte is 0 | checked |
| `fMaximum` and `fMinimum` are `-1111` unless a range was set | nothing — the histogram simply draws wrong |
| The statistics are consistent with each other: `fTsumw <= fEntries` for unit weights | nothing |
| `fTsumw` is non-zero whenever `fEntries` is, or ROOT recomputes every sum from the bins | nothing — and the values it reports are then the bin-centre approximation |
| In a `TProfile`, `fBinEntries` holds exactly `fNcells` values and `fSumw2` is never empty | checked — and **ROOT segfaults** in `GetBinError` on an empty `fSumw2`, after reading the entries and the contents correctly |
| In a `TProfile`, `fBinSumw2` is empty or holds exactly `fNcells` values — a length between the two is dropped on the first call that reads it | checked |
| In a `TProfile`, `fYmin <= fYmax`, and `fErrorMode` is 0 to 3 | checked |

## 5. A graph

From [Writing a graph §6](../06-writing/WritingGraphs.md#6-invariants).

| Invariant | Who notices |
|---|---|
| `fNpoints >= 0`, and each counted array's flag byte is 1 with `fNpoints` doubles after it — or 0, and then `fNpoints` is 0 too | checked, in two halves: the flag byte here, the length by the byte count |
| `fMinimum` and `fMaximum` are both `-1111`, or `fMinimum <= fMaximum` | checked |
| A file holding a `TGraph` describes `TH1F` and everything `TH1F`'s info names, `fHistogram` being null or not | nothing for ROOT; everything for every other reader |
| `fFunctions` points at an empty `TList` rather than being null | nothing — a null reads back without a word, and ROOT never writes one |
| `fBits` is `0x400` with no `kMustCleanup`, and `fHistogram` is null | nothing — a graph that differs reads and draws identically, but a non-null `fHistogram` makes the record five times the size |

## 6. A tree

From [Writing trees §9](../06-writing/WritingTrees.md#9-invariants), and the
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
| Each basket's `fNevBuf` equals `fBasketEntry[i+1] - fBasketEntry[i]`, so the baskets partition the entries | checked |
| `fClusterRangeEnd` and `fClusterSize` hold exactly `fNClusterRange` values, and their is-present flag agrees with the count | checked — and a count that disagrees desynchronises the record, so nothing after `fBranches` parses |
| `0 <= fFlushedBytes <= fZipBytes`, and the same for `fSavedBytes` | checked |
| A recorded cluster range agrees with where the baskets actually end | nothing: ROOT's cluster iterator hands out ranges the baskets do not support |
| On a `TLeafC`: `fLenType` is 1, `fMinimum` is 0, `fIsRange` is 0 | checked |
| On a `TLeafC`, `fLen` and `fMaximum` are **equal** and are the longest string in the file plus one | checked as `fLen <= fMaximum`, and `fMaximum` is checked against every string in the baskets — the equality is the writer's half |
| A `TLeafC` is its branch's **only** leaf | nothing, and ROOT itself writes the other shape: an empty string then becomes unreadable and every later leaf gets the wrong address |
| A branch holding a `TLeafC` has `fEntryOffsetLen` non-zero and its baskets carry the offset array | checked |

## 7. The ones ROOT does not notice

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
9. **A `TLeafC`'s `fLen` smaller than its longest string.** ROOT sizes the read
   buffer from it and truncates the value, printing nothing, while the bytes in the
   basket are complete. A fast merge — `hadd`'s default — produces exactly this.
   [TLeaf §9.1](../04-ttree/TLeaf.md#91-flen-is-the-readers-buffer-size-and-it-can-be-too-small).
10. **A missing streamer info.** ROOT reads a class it has compiled in without one,
   and the warning that would say so fires only when the file's `fVersion` differs
   from the running ROOT's — so a writer stamping the current release silences it.
   Every reader that is not ROOT needs the info.

Items 1, 2, 3, 4, 6, 7 and 9 are checked by `tools/check_invariants.py`, which is why
running it over your own output is worth more than reading this list. Item 2 became
checkable on 2026-09-18, as
[Directories §9](../01-container/Directory.md#9-invariants) invariant 11: nothing had
compared a key image against the key of the record it points at, which is precisely
the comparison ROOT never makes either.

## 8. What is deliberately not constrained

A writer may choose freely, and ROOT's own choices are given in the writing
documents only so that a byte comparison against a ROOT-written file stays
readable: where records are placed within the file, basket and buffer sizes, how
many entries a cluster holds, which compression setting to use per record, key
ordering within a directory, the `fDatime` of a key and the UUID of a file, and
every attribute of `TAttLine`, `TAttFill`, `TAttMarker` and `TAttAxis`.

**A streamer info's `fBits` is on that list too, and a reader must not key on
it.** It is written wholesale through the `TNamed` base, so it carries the
writing session's in-memory status — including `kIsOnHeap` and `kNotDeleted`,
which say only that the object was on the heap and had not been destructed. The
three corpus files that hold one class twice differ in `kIsCompiled` in one case
and `kBuildOldUsed` in the other two
([Schema evolution §8.1](../02-serialization/SchemaEvolution.md#81-a-class-may-appear-twice-in-one-streamerinfo-record)).

**An update adds nothing to this page**, which is the useful thing to know about
it. A file that was reopened eleven times satisfies exactly the invariants above
and no others, because nothing in the result records that it was reopened —
[Writing a file §13](../06-writing/WritingFiles.md#13-updating-an-existing-file)
is a procedure, not a new set of rules. The one invariant an update *should*
check that a create need not is `fBEGIN`, above: a writer that creates files
satisfies it by construction and one that reopens them was handed the number.

`spec/06-writing/` marks each field **fixed**, **derived** or **free** for exactly
this reason.
