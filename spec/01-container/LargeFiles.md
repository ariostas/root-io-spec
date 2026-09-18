# Files larger than 2 GB

Every offset in a ROOT file starts life 4 bytes wide. Past a threshold the writer
widens some of them to 8, and it does so **structure by structure**, under five
different conditions, with no single flag that says the file is in the wide form.
This page collects everything that changes and states each condition once; the
layouts themselves stay in the documents that own them.

The threshold is `kStartBigFile` = **2000000000**
(`root/io/io/inc/TFile.h:278`) — two thousand million, not 2 GiB — and every
comparison against it is strictly greater-than.

## 1. Five switches, five conditions

| Structure | Flag | Widens when | Written by |
|---|---|---|---|
| File header | `fVersion >= 1000000` | `fEND > 2000000000` | `root/io/io/src/TFile.cxx:2679` |
| Key | `fVersion > 1000` | **the file's `fEND` when the key was built** exceeded it, or `fPidOffset != 0` | `root/io/io/src/TKey.cxx:456-457`, `root/io/io/src/TKey.cxx:139-141` |
| Directory record on disk | version `> 1000` | any of `fSeekDir`, `fSeekParent`, `fSeekKeys` exceeds it | `root/io/io/src/TDirectoryFile.cxx:751-759` |
| A streamed `TDirectoryFile` | version `> 1000` | `fEND` exceeds it | `root/io/io/src/TDirectoryFile.cxx:1827` |
| Free-list entry | version `1001` | **that entry's `fLast`** exceeds it | `root/io/io/src/TFree.cxx:111` |

Only the first is a property of the file. The other four are properties of the
individual structure, they disagree with each other routinely, and **each one
carries its own version word** — which is the only thing a reader should ever
size from.

> A file over 2 GB therefore contains a mixture. §5 walks one: a 5.25 GB file
> whose header is wide, whose first key and root directory record are narrow, and
> whose free list holds both entry widths interleaved.

### 1.1 A key's width is not decided by where the key is

Every writing constructor calls `TKey::Build` with `filepos == -1`
(`root/io/io/src/TKey.cxx:206`, `:222`, `:248`, `:338`), and `Build` then
substitutes **the file's current end**, not the key's eventual offset
(`root/io/io/src/TKey.cxx:456`). So in a file that has already grown past 2 GB,
a key written into a reused gap near the front of the file is in the wide form,
with an 8-byte `fSeekKey` holding a small number.

In `volume.root` the free-list record sits at offset **105 159 358** and its key
says `fVersion` = **1004**:

```
00 00 03 3a  03 ec  00 00 02 fe  35 32 d1 c9  00 3c  00 01
└─ fNbytes ┘ └ver ┘ └─ fObjlen ┘ └─ fDatime ┘ └keyl┘ └cyc ┘
00 00 00 00 06 44 9a be   00 00 00 00 00 00 00 64
└──── fSeekKey, 8 B ───┘  └─── fSeekPdir, 8 B ───┘
```

`fSeekKey` is 105 159 358 — nowhere near the threshold — in an 8-byte field,
because `fEND` was 5 253 395 573 when the key was built.

The converse also holds and matters more: a key written **before** the file
crossed the threshold stays narrow, however large the file later becomes. The
first key of that same file, at `fBEGIN`, is `fVersion` 4 with 4-byte offsets.

> This is an erratum against this specification's own earlier text, which is now
> corrected in [Directories §3](Directory.md#3-three-independent-large-file-flags):
> the key flag was stated there as a test on the key's own offset.

### 1.2 The directory record has two writers that disagree

`TDirectoryFile::FillBuffer` — the path that produces the record on disk —
widens on the three offsets it is about to write
(`root/io/io/src/TDirectoryFile.cxx:751-759`).
`TDirectoryFile::Streamer`, which serialises the same class through a `TBuffer`,
widens on `fEND` instead (`root/io/io/src/TDirectoryFile.cxx:1827`). The two
conditions are independent: a 3 GB file whose directories all live below the
threshold gets narrow records from the first and wide records from the second.

Both produce the same *layout* for a given version word, so a reader that sizes
from the version word is unaffected. It is stated here because a **writer** that
picks one condition and applies it everywhere will not reproduce ROOT's bytes.

## 2. The file header

The wide header is 75 bytes rather than 63, and three fields double. Field
meanings and the narrow layout are [File header §2](FileHeader.md#2-layout);
this is the wide diagram, which that page gives only as a column of offsets.

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                      "root" (0x726F6F74)                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                  fVersion (>= 1000000)                        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     fBEGIN (never widens)                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                        fEND (8 bytes)                         +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                      fSeekFree (8 bytes)                      +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          fNbytesFree                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                             nfree                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          fNbytesName                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  fUnits = 8   |                  fCompress                    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                      fSeekInfo (8 bytes)                      +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          fNbytesInfo                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         TUUID version         |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+          UUID (16 bytes)      +
|                              ...                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                 padding to fBEGIN, not specified              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

> As in the small layout, the 4-byte grid stops being accurate at `fUnits` (offset
> 40), which is one byte: every field after it straddles a row boundary, so the
> rows below it show order rather than column position. The offset table in
> [FileHeader §2.2](FileHeader.md#22-field-offsets) is
> authoritative.

`fBEGIN` never widens, and neither do the three lengths — `fNbytesFree`,
`fNbytesName` and `fNbytesInfo` are record lengths, and
[Records §5](Record.md#5-payload-size-limits) bounds a record well below 2 GB.

`fUnits` is set to 8 alongside the flag and is **informational only**; a reader
MUST select the layout from `fVersion`
([File header §3](FileHeader.md#3-fversion-and-the-large-file-flag)).

## 3. The wide key

`fSeekKey` and `fSeekPdir` both become 8 bytes, moving `fClassName` from offset
26 to 34 ([Records §2](Record.md#2-key-layout)). Bytes 0-17 are unchanged —
`fNbytes` and `fObjlen` stay 4-byte signed, and [Records §5](Record.md#5-payload-size-limits)
keeps a record well below 2 GiB anyway, so no length in the key ever widens.
What changes is everything from byte 18:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                 fSeekKey, bytes 18-25 (8 bytes)               +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   fPidOffset, bytes 26-27     |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+   fSeekPdir, bytes 28-33      +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  fClassName, fName, fTitle: three counted strings, from 34     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

In the narrow key the same two fields are 4 bytes each at 18 and 22, and there is
nowhere for `fPidOffset` to live.

> **The top 16 bits of the `fSeekPdir` word are not address bits.** They hold
> `fPidOffset` (`root/io/io/src/TKey.cxx:670`, `root/io/io/src/TKey.cxx:1281-1282`),
> and a reader MUST mask before using the offset — see
> [Records §3.6](Record.md#36-fseekpdir-and-the-packed-fpidoffset). A non-zero
> `fPidOffset` is also the second thing that forces the wide key
> (`root/io/io/src/TKey.cxx:696-704`), independently of any file size, which is
> why a small file can contain one.

A key image inside a key list follows the same rule and carries its own version
word, so widths may vary within one list
([Directories §6](Directory.md#6-key-lists)).

## 4. The wide free-list entry

An entry is 18 bytes instead of 10, and its version word is 1001 rather than 1
([Free segments §2.1](FreeSegments.md#21-the-large-form)):

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|        version = 1001         |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+        fFirst (8 bytes)       +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                               |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+        fLast (8 bytes)        +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

The test is on `fLast` alone, so a segment that *starts* below the threshold and
ends above it is wide, and one entry's width says nothing about its neighbours'.
`volume.root` has 19 narrow and 32 wide entries in one record, ordered by
`fFirst`, so the two forms interleave in the middle of the list.

**The trailing sentinel is what usually crosses first.** The free list always
ends with an entry that begins at `fEND` and runs past it
([Free segments §5](FreeSegments.md#5-the-trailing-segment)), and its `fLast` is
the next whole multiple of 1 000 000 000 above `fEND` — 3 000 000 000 for a
2.24 GB file, 6 000 000 000 for a 5.25 GB one. That is why every large file in
§6 has at least one wide entry, and why a file just under the threshold has
none: `CMS_7250E9A5…root` ends at 1 997 354 026, its sentinel's `fLast` is
exactly 2 000 000 000, and 2 000 000 000 is not *greater than* 2 000 000 000.

## 5. One file, byte by byte

`volume.root` — ROOT 5.19/03, 5 253 395 573 bytes — read by two HTTP range
requests. The mixture is the point.

**The header** (bytes 0-74), wide:

```
  0  72 6f 6f 74 00 10 0c ff 00 00 00 64 00 00 00 01
 16  39 20 74 75 00 00 00 00 06 44 9a be 00 00 03 3a
 32  00 00 00 33 00 00 00 48 08 00 00 00 00 00 00 00
 48  00 06 45 19 5e 00 00 11 88 00 01 85 4f c9 25 12
 64  b2 11 dd 80 53 08 84 8d 80 be ef 00 00 00 00 00
```

| Field | Bytes | Value |
|---|---|---|
| `fVersion` | 4-7 | 1 051 903 — release 5.19/03 plus 1 000 000 |
| `fBEGIN` | 8-11 | 100 |
| `fEND` | 12-19 | 5 253 395 573 |
| `fSeekFree` | 20-27 | 105 159 358 |
| `nfree` | 32-35 | 51 |
| `fUnits` | 40 | 8 |
| `fSeekInfo` | 45-52 | 105 191 774 |

**The first key** (offset 100), narrow — `fVersion` 4, `fKeylen` 52, a 4-byte
`fSeekKey` of 100 and a 4-byte `fSeekPdir` of 0:

```
00 00 00 84 00 04 00 00 00 50 35 32 c7 6c 00 34 00 01
00 00 00 64 00 00 00 00 05 54 46 69 6c 65 ...
```

**The root directory record** (offset 172, after the repeated name and title),
narrow — version **5**, with `fSeekDir` 100, `fSeekParent` 0 and `fSeekKeys`
105 159 233 in 4-byte fields, and the twelve zero bytes the narrow form writes
after the UUID (`root/io/io/src/TDirectoryFile.cxx:786`).

**The key-list record** (offset 105 159 233): its own key is *wide*
(`fVersion` 1004, `fKeylen` 60) and the single key image inside it is wide too —
`fSeekKey` 5 252 483 583, an offset that no 4-byte field could hold:

```
00 00 00 01                                       nkeys = 1
00 0d ea 76  03 ec  00 0d ea 41  35 32 d1 c8  00 35  00 33
00 00 00 01 39 12 89 ff   00 00 00 00 00 00 00 64
05 "TTree" 01 "T" 0a "All slices"
00 04 00 62 00 04 00 62                           slack, not an entry
```

Those last eight bytes are the hazard
[Directories §6.1](Directory.md#61-the-count-is-authoritative) describes: past
the threshold ROOT allocates the key-list payload 8 bytes longer than it fills
(`root/io/io/src/TDirectoryFile.cxx:2209`), and the slack is uninitialised heap.
Here `fObjlen` is 65 while the count and the one image account for 57. A parser
driven by the payload length rather than by `nkeys` reads `00 04 00 62` as the
start of a second key — a plausible-looking `fNbytes`, and a version word of 4.

**The free-list record** (offset 105 159 358): a wide key over a payload of 51
entries, 19 narrow then 32 wide, ending in the sentinel
`(5 253 395 573, 6 000 000 000)`.

And from `lhcb2.root`, whose `fEND` is 4 947 894 760, the same structure with an
offset past 4 GB where even an unsigned 32-bit reader fails:

```
00 00 00 7b  03 ec  00 00 00 12  3c 8b 22 4d  00 69  00 01
00 00 00 01 26 ea e1 6d   00 00 00 00 00 00 00 64
                          └─ fPidOffset 0, fSeekPdir 100
```

`fSeekKey` = 4 947 894 637; its single free entry is
`(4 947 894 760, 5 000 000 000)`, version 1001.

## 6. Evidence, and how it is checked

No committed fixture is over 2 GB and none can be. The evidence is eight files
published by the ROOT team, read by HTTP range request — a few hundred bytes
each, nothing downloaded — with every field recorded in `gen/cern/LARGE.toml`
and re-measured by:

```sh
tools/fetch_cern.py --headers
```

which parses each file's header and its whole free-segment record with
`tools/rootfile.py` and fails if any recorded field, the entry-width counts, the
`nfree` agreement or the sentinel rule has drifted.

| File | ROOT | `fEND` | Free entries | Why it is listed |
|---|---|---|---|---|
| `lhcb2.root` | 5.26/00 | 4 947 894 760 | 1 wide | an offset past 4 GB |
| `volume.root` | 5.19/03 | 5 253 395 573 | 19 narrow + 32 wide | both widths interleaved; §5 |
| `Event100000.root` | 5.25/03 | 2 906 686 793 | 1 wide | the 2.9 GB `Event` benchmark |
| `h1huge.root` | 5.25/01 | 2 242 724 865 | 1 wide | the smallest wide file listed |
| `rootbench/h1analysis.root` | 6.23/01 | 2 670 464 440 | 1 narrow + 1 wide | written by a current ROOT |
| `rootbench/Run2012BC…Muons.root` | 6.17/01 | 2 244 449 133 | 66 narrow + 8 wide | CMS open data |
| `CMS_7250E9A5…root` | 5.22/00 | 1 997 354 026 | 2 narrow | 1.997 GB and **not** wide — the boundary from below |
| `AOD.067184.big.pool_4.root` | 5.22/00 | 1 338 275 841 | 1539 narrow | the most fragmented free list available |

The last two are the control: sub-threshold files whose every structure is
narrow, including the sentinel whose `fLast` is exactly 2 000 000 000.

## 7. Reading

1. Read the header's `fVersion`. If it is `>= 1000000`, the header is wide:
   `fEND`, `fSeekFree` and `fSeekInfo` are 8 bytes and the fixed part is 75 bytes.
   Subtract 1 000 000 to recover the release. Do **not** use `fUnits`.
2. Take every other width from the structure's own version word, never from the
   header's flag and never from an offset's magnitude:
   a key is wide when its `fVersion > 1000`, a directory record when its version
   word is `> 1000`, a free entry when its version word is `> 1000`.
3. In a wide key, mask `fSeekPdir`: the offset is the low 48 bits and the top 16
   are `fPidOffset`.
4. Size each key image in a key list and each entry in a free list
   individually, and iterate a key list exactly `nkeys` times.
5. Hold every offset in a 64-bit signed integer. `fEND` above 2³¹ is ordinary,
   above 2³² occurs, and `fLast` on the trailing free entry exceeds `fEND` by
   design.

## 8. Invariants

Checked by `tools/fetch_cern.py --headers` over the eight files of §6 rather
than by `tools/check_invariants.py`, which has no file large enough.

1. `fVersion >= 1000000` **if** `fEND > 2000000000`; the reverse holds on every
   known file but is not guaranteed, because the flag is never cleared once set
   (`root/io/io/src/TFile.cxx:2679`). See
   [FileHeader §10](FileHeader.md#10-invariants) invariant 9, which
   `tools/check_invariants.py` enforces as a strict `iff`.
2. The number of entries parsed out of the free record equals `nfree`.
3. The last free entry's `fLast` is greater than `fEND`.
4. An entry's version word is `> 1000` **iff** its `fLast > 2000000000`. A
   reader that sizes entries by comparing `fLast` with the threshold instead of
   by reading the version word desynchronises here and nowhere else.
5. Every entry satisfies `0 <= fFirst <= fLast <= fEND`, except the trailing
   entry, whose `fLast` passes `fEND` by design.
6. When the free-segment record's own key is wide, its `fSeekPdir` masked to 48
   bits is `fBEGIN` and its `fPidOffset` is 0 — the project's only measurement
   of the packed field on a file it did not write.

Each is a mutation test in `tools/test_large_files.py`, which takes the measured
reading of `volume.root` as the good case and breaks one invariant at a time, so
none of the six can pass vacuously.

## 9. Errata

| # | Claim | Correction |
|---|---|---|
| 1 | `root/io/doc/TFile/header.md`: widening is triggered when "END, SeekFree, or SeekInfo" exceed 2 000 000 000 | The header test is on `fEND` alone ([File header §3](FileHeader.md#3-fversion-and-the-large-file-flag)) |
| 2 | This specification, before 2026-09-17: a key is wide when "that key's own offset > 2000000000" | The condition is the file's `fEND` when the key was built, or a non-zero `fPidOffset` (§1.1). `volume.root` has a wide key at offset 105 159 358 |
| 3 | — | The directory record has two writers with different conditions; only `FillBuffer` produces the on-disk record (§1.2) |
| 4 | — | `fUnits` is written as 8 but is never read back; it is not the layout selector (`root/io/io/src/TFile.cxx:738`) |

## 10. Reference files

None committed: a fixture would have to be 2 GB. `gen/cern/LARGE.toml` records
the eight measured files of §6 and `tools/fetch_cern.py --headers` re-checks them
over the network; `gen/cern/README.md` says why each is listed.
