# Buffer framing

How objects are delimited, identified and cross-referenced inside a record's
payload. This layer sits between the container and any knowledge of a particular
class: everything here can be parsed, and any object can be skipped, without
knowing what the class is.

Prerequisites: [Conventions](../00-conventions.md),
[Records and keys](../01-container/Record.md). All integers are big-endian.

## 1. What a buffer is

A buffer is the byte range ROOT serializes an object graph into. For data in a
file it is a record: a [`TKey`](../01-container/Record.md) followed by its
payload, decompressed if necessary.

> **Buffer position 0 is the start of the key, not the start of the payload.**

This matters because back-references (§6) are expressed as buffer positions, so
every one of them is offset by `fKeylen`. A reader that decompresses the payload
into a fresh array and counts from zero will compute every back-reference wrong,
by exactly `fKeylen` bytes.

> Demonstrated by `serialization/object-tags`, whose record starts at 308 with
> `fKeylen` 55: an object at file offset 387 is referenced as 81, which is
> `387 - 308 + 2`, not `387 - 363 + 2`.

ROOT corroborates this where it reads a payload without its key. RNTuple's mini
reader hands `TBufferFile` only the `StreamerInfo` payload and then subtracts the
key length back out, with a comment saying why
(`root/tree/ntuple/src/RMiniFile.cxx:749-754`). A reader that keeps the key in
the buffer needs no such correction.

The constants in this document are defined together at
`root/io/io/src/TBufferFile.cxx:50-56`:

| Name | Value | Role |
|---|---|---|
| `kNewClassTag` | `0xFFFFFFFF` | a class description follows |
| `kClassMask` | `0x80000000` | the tag is a reference to a class |
| `kByteCountMask` | `0x40000000` | the word is a byte count |
| `kMaxMapCount` | `0x3FFFFFFE` | largest byte count, and largest map position |
| `kMaxVersion` | `0x3FFF` | largest class version |
| `kByteCountVMask` | `0x4000` | `kByteCountMask` expressed on the high half |
| `kMapOffset` | `2` | positions 0 and 1 have fixed meanings; see §6.2 |
| `kNullTag` | `0` | the null pointer, `root/io/io/inc/TBufferIO.h:33` |

## 2. Byte counts

A byte count is a `u32` with `kByteCountMask` set. Its low 30 bits give **the
number of bytes that follow the byte-count word itself**; the word is not
included in its own count.

`CheckByteCount` states this as arithmetic: the object ends at
`startpos + bcnt + sizeof(UInt_t)`, where `startpos` is the position of the
byte-count word (`root/io/io/src/TBufferFile.cxx:371`).

> Demonstrated by `serialization/basic-types`: the byte count at payload offset
> 346 is 65, and the payload is 69 bytes.

Because `kMaxVersion` is `0x3FFF` (`root/io/io/src/TBufferFile.cxx:55`), a
version number can never reach `0x4000`, so a word whose top bits are `0x4000`
is unambiguously a byte count and never a version. This is the single invariant
the whole framing layer rests on.

### 2.1 A byte count is authoritative

When the bytes a streamer consumed disagree with the byte count, ROOT reports an
error and then **moves the cursor to where the byte count says the object ends**
(`root/io/io/src/TBufferFile.cxx:394-403`). The read continues.

A reader SHOULD do the same: treat the byte count, not member consumption, as the
definition of where an object ends. This is what makes a class whose layout is
unknown skippable, and it is how ROOT itself survives a `Streamer` that is out of
sync with the data.

A byte count larger than `kMaxMapCount` cannot be written
(`root/io/io/src/TBufferFile.cxx:351-354`), which caps a single serialized
object at just under 1 GiB.

### 2.2 Two code paths, one encoding

ROOT writes a byte count either as a plain `cnt | kByteCountMask` or, when the
count must be readable by `ReadVersion`, as two `Version_t` halves with
`kByteCountVMask` set on the high one (`root/io/io/src/TBufferFile.cxx:335-348`).

These produce **identical bytes**. There is one on-disk encoding; a reader need
not distinguish the two cases.

### 2.3 A record's object data does not always begin with one

Most record payloads open with a byte count, because most classes are written
through `WriteClassBuffer`, which asks for one. These do not, and **for ROOT
6.40.04 the list is complete**: every hand-written `Streamer` of a class ROOT
persists — the 55 that `spec/99-appendix/streamers.toml` marks `specified` or
`gap` — was read for what its write branch emits first, and these are all of
the ones that emit something other than a byte count.

- **The container's own bookkeeping** — the root directory record, the key
  lists, the free list — which is not a streamed object at all
  ([Record](../01-container/Record.md)).
- **A version word and no byte count.** `TObject` writes its version this way
  (`root/core/base/src/TObject.cxx:1022`), so a `TObject` stored as a record of
  its own is **the 10-byte base of §7 and nothing else** — one version word, not
  a version word for the class and another for its base. `TRef` adds only a
  `pidf`, so its record is 12 bytes whose first word is a version.
  `RooLinkedList` is the same choice around a whole object — a version word, a
  `TObject` base, a count, that many object slots and a `TString`, with nothing
  delimiting any of it (`root/roofit/roofitcore/src/RooLinkedList.cxx:913`).
  `TClassTree` too: a bare version word, then a framed `TNamed` and its own
  members (`root/graf2d/gpad/src/TClassTree.cxx:1143-1144`).
- **No version word either.** A `TArray` payload begins with its element
  **count** ([TArray §1](../03-classes/TArray.md#1-layout)). A `TDatime` is its
  packed `fDatime` and nothing else — **four bytes**
  (`root/core/base/src/TDatime.cxx:415-422`, layout in
  [Record §3.7](../01-container/Record.md#37-fdatime)). A `TString` is a bare
  counted string ([Conventions §5.1](../00-conventions.md#51-counted-string)),
  and a `TStringLong` an `i32` length and that many bytes
  (`root/core/base/src/TStringLong.cxx:131-147`). A `TKey` stored as an object
  is a key header written raw (`root/io/io/src/TKey.cxx:1387`); no fixture here
  has one.
- **Nothing at all.** `TQObject::Streamer` writes nothing in either direction
  (`root/core/base/src/TQObject.cxx:1033-1040`), so a `TQObject` stored as a
  record is a key whose `fObjlen` is **0** over an empty payload. The three
  graph-visualisation classes `TGraphEdge`, `TGraphNode` and `TGraphStruct` are
  the same (`root/graf2d/gviz/src/TGraphStruct.cxx:307`).
- **A `TBasket`**, whose payload is not a serialized object at all. It is the
  concatenated entry data of one branch, and what frames each entry — if
  anything — is decided by that branch. See [TBasket](../04-ttree/TBasket.md).

> **`TDatime` was missing from this list until 2026-09-22**, although
> [Record §3.7](../01-container/Record.md#37-fdatime) described its bytes and this
> project's reader already decoded it: a `TDatime` stored as a record in a
> ROOT-written file of go-hep's test corpus was rejected by the framing check for
> having no byte count. Reading every hand-written `Streamer` once, rather than
> adding the one name, found `TStringLong` and `TQObject` in the same position
> and `TObject` misread by the reader itself (`PLAN-corpus.md` C3).

> Demonstrated by `serialization/references`: the `TRef` record at 537 has
> `fObjlen` 12 and its payload begins `00 01` — the `TObject` version word —
> where every other object record in that file begins `40 00`. And by
> `classes/tarray`, whose eight records begin with an `i32` count. And by
> `classes/roofit`, whose `RooLinkedList` record at 977 begins `00 03` and runs
> 93 bytes with no byte count anywhere in it. And by
> `serialization/unframed-records`, which writes five of the others as records of
> their own: a `TDatime` of 4 bytes, a `TString` of 6, a `TStringLong` of 17, a
> `TObject` of 10 beginning `00 01`, and a `TQObject` of **0**.

**A writer other than ROOT may leave the byte count out of an ordinary class's
payload.** g4tools, Geant4's own ROOT writer, opens a `TH1D` record with the bare
version words of `TH1D` and then `TH1`, and only the `TNamed` base inside is
framed. ROOT reads that with its own `Streamer`s, because `ReadVersion` takes a
version word with or without a byte count in front of it
(`root/io/io/src/TBufferFile.cxx:2959-2962`).

> Measured on the two g4tools files of the foreign corpus, whose header claims
> ROOT 4.00/00 and whose keys were written in 2018–2020
> (`gen/foreign/IGNORE.toml`): **19** histogram records open with bare version
> words instead of a byte count, and they do not all open the same way —
>
> | Records | Class | First six bytes |
> |---|---|---|
> | 14 | `TH1D` | `00 01 00 03 40 00` — a version word, a version word, then a byte count |
> | 5 | `TH2D` | `00 03 00 03 00 03` — **three** version words, and no byte count among them |
>
> so the depth at which framing resumes is a property of the writer and the class
> chain, not of the file. A reader that recognises one prefix and not the other
> has hard-coded a class rather than implemented the rule.

**ROOT itself does not do this at the top of a record, at any release in reach.**
Until 2026-09-23 this paragraph said it did — "on a file older than ROOT 5" — on
the strength of those two files, which are not ROOT's. Over every record of every
ROOT-written file in reach, the 72 of `gen/cern/` and the 273 of
`root/roottest/`, **all 2 025 payloads of any other class open with a byte
count**: 472 of them written by ROOT 2, 61 by ROOT 3 and 324 by ROOT 4. (Not
counted: an STL collection stored as a record, which is bare, and an RNTuple
blob, which is not a streamed object.) And
ROOT 4.00's generated streamers already asked for one, exactly as today's do
(`TClass::WriteBuffer` calls `WriteVersion(this, kTRUE)` at tag `v4-00-08`).
*Inside* a record is another matter: ROOT 2 wrote bases as bare version words
(§11), and a class's own hand-written `Streamer` may write an object with no
frame at all ([Streamer-driven reading §7.1](StreamerDriven.md#71-an-object-with-no-byte-count)).

A reader MUST therefore decide from the class, not from the first word, whether
a payload is framed, and what the first word then means. Reading a `TArray`'s
`00 00 00 02` as a byte count gives 2; reading a `TRef`'s `00 01 00 00` as one
gives 65536. Neither is obviously wrong at the point of the mistake.

### 2.4 An object may be longer than its byte count says

A byte count is written by the `Streamer` that opens the frame, and a
hand-written `Streamer` may keep writing after `WriteClassBuffer` has closed it.
Three classes in ROOT do (`tools/inventory.py` calls them `extending`, and
[Hand-written streamers §3](../99-appendix/HandWrittenStreamers.md) lists them),
and the consequence is a rule a reader has to know:

> **A byte count is a lower bound on the length of the object, not the length of
> the object.** It is exact for every generated streamer and for most
> hand-written ones, and a reader may use it to *find the end* only for a class
> it knows does not extend past it.

`TMatrixTSym` is the case to test against: its byte count covers the members its
base class's streamer info describes, and the matrix elements follow outside it
([Matrices and vectors §2.4](../03-classes/Matrix.md)). Two consequences:

- **`CheckByteCount` cannot see the difference**, so nothing warns. ROOT's own
  reader goes on past the count because the class's `Streamer` tells it to.
- **Skipping such an object by its byte count lands short.**
  `TBufferFile::SkipObjectAny` seeks to `start + count + 4`
  (`root/io/io/src/TBufferFile.cxx:2499-2503`), which is correct for every other
  class and wrong for these.

An enclosing frame is unaffected: its own byte count is written after the whole
nested object has been streamed, so it covers the extra bytes. A file containing
one of these classes is therefore never internally inconsistent — the only thing
that goes wrong is a reader that trusts the inner count.

## 3. Version words

A version word is a signed 16-bit class version. It may or may not be preceded by
a byte count, and `ReadVersion` decides structurally rather than from any file
version (`root/io/io/src/TBufferFile.cxx:2933`):

1. Read a `u32`.
2. If `kByteCountMask` is **not** set, this was not a byte count: rewind 4 bytes
   and record "no byte count" (`root/io/io/src/TBufferFile.cxx:2959-2961`).
3. Read an `i16`: the version (`root/io/io/src/TBufferFile.cxx:2964`).

So `byteCount? version` — the byte count is optional, and its absence is detected
by inspection, not by knowing how old the file is. Files written before byte
counts existed are read by the same code.

### 3.1 `kByteCountVMask` and `kStreamedMemberWise` are the same number

Both are `0x4000`, and the collision is deliberate but confusing:

| Mask | Value | Applies to |
|---|---|---|
| `kByteCountVMask` | `0x4000` | the **high half of a byte-count word** |
| `kStreamedMemberWise` | `BIT(14)` = `0x4000` | a **version word** |

They never apply to the same bytes. `kByteCountVMask` is tested before the byte
count has been consumed; `kStreamedMemberWise` is a flag *inside* a version word,
set for a collection streamed member-wise
(`root/io/io/inc/TBufferFile.h:70`, `root/io/io/src/TBufferFile.cxx:3203`).

A reader MUST mask `0x4000` out of a version word before comparing it with a
class version. Collections are specified in [Collections](Collections.md).

## 4. A version word of 0 has two different meanings

> **This is the one place in the framing layer where the bytes are not
> self-describing.**

A version word of **0 or less** is followed by a 4-byte checksum in one case and
by nothing in the other, and which case applies depends on the *class*, not on
anything in the byte stream. The trigger is `version <= 0`, so a negative version
word takes the same path (`root/io/io/src/TBufferFile.cxx:2967`).

| Situation | Version word | Then |
|---|---|---|
| Class has no `ClassDef` (*foreign*) and its version is ≤ 1 | 0 | a `u32` checksum |
| Class declares version 0, e.g. `ClassDefOverride(TH1L,0)` | 0 | nothing; the next bytes are the class's own content |

The write side is `root/io/io/src/TBufferFile.cxx:3163-3165`: the checksum is
emitted only `if (version <= 1 && cl->IsForeign())`. A class that genuinely
declares version 0 is not foreign, so it takes the plain branch and no checksum
is written.

> Demonstrated by two fixtures that differ in exactly this way.
> `serialization/basic-types` is an interpreted class, so foreign: the version
> word at 350 is 0 and a checksum follows at 352. `serialization/version-zero`
> is a `TH1L`: the version word at 361 is 0 and the next four bytes are the
> **byte count of the embedded `TH1` base**, `0x40000200`.

> **And in the wild, by `uproot-issue-222.root`** of the foreign corpus
> (`PLAN.md` §9.8), a ROOT 6.20/04 file holding one `TH1F`. Five
> `TAttBBox2D` base objects inside it read `40 00 00 02 00 00` and nothing
> else — a byte count of 2 covering only the version word, which is 0, with no
> checksum and no content. `TAttBBox2D` is `ClassDef(TAttBBox2D,0)`
> (`root/core/base/inc/TAttBBox2D.h:33`), so it takes the right-hand row, and
> the file says so itself: its streamer info for the class carries
> `fClassVersion` 0 and an empty element list. One base is under a `TBox` and
> four under `TText`, so a reader meets the case five times in a file whose only
> object is a histogram.

ROOT resolves the ambiguity by consulting the compiled class
(`root/io/io/src/TBufferFile.cxx:2966-2975`). A third-party reader has no
compiled classes, and MUST use the file's own streamer info instead:

> On seeing a version word of 0, look up the class in the file's streamer info
> list. If an entry for it has `fClassVersion == 0`, no checksum follows.
> Otherwise a 4-byte checksum follows and selects which entry applies.

This works because a foreign class is recorded with `fClassVersion` 1 even
though it is written with a version word of 0 — the two fixtures above show both
halves of that.

### 4.1 ROOT's byte-count heuristic is not a substitute

When the version word is 0, ROOT gates the checksum read on the byte count: read a
checksum only if it is at least 6. The reasoning is that a version-0 class has
nothing to write, so its whole block is 6 bytes and the count is 2.

The guard is in **both** branches, not only the fallback: with a compiled class at
`root/io/io/src/TBufferFile.cxx:2970-2972`, and with no class at all at
`root/io/io/src/TBufferFile.cxx:3001-3006`. So it is not a last resort ROOT uses
only when it knows nothing — it is part of the normal path.

**That reasoning does not hold, and a reader MUST NOT adopt the heuristic.** The
version-0 skip in `TStreamerInfo::Build` is in the loop over *data members*
(`root/io/io/src/TStreamerInfo.cxx:550-553`); base classes are collected by a
separate earlier loop (`root/io/io/src/TStreamerInfo.cxx:469`) and are not
skipped. A version-0 class with base classes therefore writes a full payload.

> `serialization/version-zero` is exactly that case. `TH1L` declares version 0 and
> has two base classes, so its byte count is **554**, far above 6. The heuristic
> would read four bytes of the `TH1` base as a checksum.

The streamer-info rule above has no such failure mode, because it asks the file
what `fClassVersion` the class was written with rather than guessing from a length.

### 4.2 `SkipVersion` disagrees with `ReadVersion`

`SkipVersion` reads a checksum whenever the class version is non-zero and the
version word is ≤ 0, without `ReadVersion`'s additional "byte count ≥ 6" guard
(`root/io/io/src/TBufferFile.cxx:2875-2879` versus
`root/io/io/src/TBufferFile.cxx:2970-2975`).

The two therefore disagree for a version-0 word carrying a byte count below 6.
This is recorded as an **apparent** inconsistency: no such object has been
constructed here, and it may be unreachable. See §9, erratum 8.

## 5. Class records

Where a pointer is serialized, the class must be named, because a pointer may
refer to a class derived from the declared one. `ReadClass`
(`root/io/io/src/TBufferFile.cxx:2740`) reads:

1. A `u32`. If it has `kByteCountMask` set **and** is not `kNewClassTag`, it is a
   byte count and the tag is the next `u32`; otherwise it *is* the tag and there
   is no byte count (`root/io/io/src/TBufferFile.cxx:2751-2758`). The explicit
   `kNewClassTag` test is needed because `0xFFFFFFFF` also has
   `kByteCountMask` set.
2. Dispatch on the tag:

| Tag | Meaning |
|---|---|
| `kNewClassTag` (`0xFFFFFFFF`) | a class name follows; §5.1 |
| has `kClassMask` set | a reference to a class already named in this buffer; §5.2 |
| anything else | not a class at all — a reference to an **object**; §6 |

That third row is the subtle one: `ReadClass` returns no class and hands the tag
back to its caller as an object reference
(`root/io/io/src/TBufferFile.cxx:2761-2764`).

### 5.1 A new class

The class name is a **null-terminated** string — not a counted string — read by
`TClass::Load` (`root/core/meta/src/TClass.cxx:5817`). This is the only place the
null-terminated encoding of [Conventions §5.2](../00-conventions.md#52-null-terminated-string)
appears.

```
byteCount:u32   kNewClassTag:u32   name:bytes   0x00
```

The class is then recorded in the buffer's class map at **the position of the tag
word** plus `kMapOffset` (`root/io/io/src/TBufferFile.cxx:2756`,
`root/io/io/src/TBufferFile.cxx:2776-2778`).

### 5.2 A class back-reference

```
byteCount:u32   (kClassMask | position):u32
```

The position is the map position recorded in §5.1, so it is
`(offset of that earlier tag word from the start of the record) + 2`.

> Demonstrated by `serialization/object-tags`: the third entry is a second
> `TObjString`, written as `0x80000055` at offset 471. `0x55` is 85, and the
> `kNewClassTag` word of the first `TObjString` is at 391, which is 83 bytes into
> the record at 308.

## 6. Object slots

A slot holding an object or a pointer to one takes one of **five** forms. They are
distinguished by the first `u32`:

| First word | Form |
|---|---|
| `0x00000000` | a **null pointer**, and nothing follows |
| has `kByteCountMask` set | a byte count; a class record (§5) and then the object |
| `kNewClassTag` | a class name and then the object, with **no byte count** |
| has `kClassMask` set | a class back-reference and then the object, with **no byte count** |
| anything else | a **reference** to an object already read in this buffer |

The two no-byte-count forms arise from the same branch that makes the byte count
optional before a version word (`root/io/io/src/TBufferFile.cxx:2751-2758`): if
the first word is not a byte count it is taken as the tag itself. Such an object
cannot be skipped without understanding its class.

The last row is a bare buffer position with no mask of any kind — which is why
positions 0 and 1 are reserved and `kMapOffset` is 2
(`root/io/io/src/TBufferFile.cxx:56`): position 0 would be indistinguishable
from a null pointer.

> All four appear in the fixtures. `serialization/objects` has a null pointer at
> 407 (four zero bytes, nothing else) and byte-count-plus-class-record pointers
> at 371 and 411. `serialization/object-tags` has the object reference, `81` at
> offset 500.

### 6.1 Object references

An object is recorded in the buffer's object map at **the position of its
byte-count word** plus `kMapOffset` (`root/io/io/src/TBufferFile.cxx:2527`,
`root/io/io/src/TBufferFile.cxx:2638`).

> Note the asymmetry with §5.1, which is easy to get wrong: a **class** is mapped
> at the position of the tag word, an **object** at the position of the byte-count
> word four bytes earlier. Both then add `kMapOffset`. For the first entry of
> `serialization/object-tags` the two positions are 85 and 81 respectively, for
> one and the same record.

A reference means "the object I already built at that position", not "re-read the
bytes there". Two slots referring to one object are the same object, and a graph
with cycles round-trips. A reader that re-parses instead of sharing will still
produce correct values but will duplicate objects, and will not terminate on a
cyclic graph.

**A reference need not name something the reader has already parsed.** When the
position is not in the map, ROOT seeks to it and reads the object out of order
(`root/io/io/src/TBufferFile.cxx:3266`), which is how a reference into a region
skipped for an unknown class still resolves. The rewind differs by kind, and
mirrors §6.1 exactly: `position - 2` for an object, `position - 2 - 4` for a
class, because reading a class starts at the enclosing byte count
(`root/io/io/src/TBufferFile.cxx:3280`, `root/io/io/src/TBufferFile.cxx:3312`).
A reader MAY treat an unresolvable reference as a null.

**A reference may carry a byte count of its own.** ROOT never writes one —
`WriteObjectClass` emits the bare four-byte tag for an object already in the map
(`root/io/io/src/TBufferFile.cxx:2680-2686`) — but its **reader accepts it**:
`ReadClass` treats a leading word with `kByteCountMask` as a byte count, reads the
tag after it, and returns that tag as an object reference if `kClassMask` is clear
(`root/io/io/src/TBufferFile.cxx:2751-2764`). So a slot of `40 00 00 04` followed
by a four-byte tag is an eight-byte reference, and a reader that accepts only
the three object-bearing shapes of §6 — byte count, `kNewClassTag`, class
back-reference — rejects a file ROOT reads without complaint.

> Found in `uproot-issue413.root` from the foreign corpus of `PLAN.md` §9.8: a
> `TTree`'s `fLeaves` of six entries, each `40 00 00 04` and a tag, 48 bytes where
> 24 would do. The file was not written by ROOT — its basket keys use the small
> form, which ROOT has not written since 4.02 while the file's header names
> 6.18/04 ([TBasket §1](../04-ttree/TBasket.md)), and the branch names are Go
> type spellings, so most likely groot
> (`gen/foreign/IGNORE.toml`) — but ROOT reads it, so a reader of other people's
> files should too.

### 6.2 Positions 0 and 1, and why `kMapOffset` is 2

The first two map positions are not buffer offsets:

| Position | Meaning |
|---|---|
| 0 | the null object, so a reference of 0 and a null pointer coincide |
| 1 | **the top-level object of this record** |

Position 1 is real and referenceable: `TKey` registers the object it is about at
the default position of 1 before streaming it
(`root/io/io/src/TKey.cxx:255-258`, `root/io/io/inc/TBufferIO.h:92`), so a member
pointing back at its own containing object is stored as `1`. A reader MUST treat a
reference of 1 as the record's top-level object rather than as a buffer position,
and MUST NOT reject it.

Adding `kMapOffset` to every real offset is what keeps both meanings reachable and
guarantees a genuine position is never 0
(`root/io/io/src/TBufferFile.cxx:2710`, `root/io/io/src/TBufferFile.cxx:2852`).

### 6.3 The map is per buffer

The map is reset for each buffer, so a position is meaningless outside the record
it occurs in. A reader MUST NOT cache positions across records.

### 6.4 Legacy buffers key the map differently

A buffer only switches to offset-keyed positions when it first reads a byte count
before a class tag (`root/io/io/src/TBufferFile.cxx:2755`). Before that, tags are
**sequential counters** — the first class or object mapped is 1, the next 2, and so
on — and bounds are checked against the map size rather than the buffer length
(`root/io/io/src/TBufferFile.cxx:2597`, `root/io/io/src/TBufferFile.cxx:2791`).

No file written by ROOT 3 or later uses this mode, and no fixture here exercises
it. **Nor does the oldest ROOT-written file in reach**: `MC_uds_reco-1.root`, ROOT
2.23/12, has 11 new-class tags and a byte count in front of every one, so its
buffers switch to offset keys at the first object slot; `pippa.root` (2.24/00) has
no class tags at all. It is recorded because it is what the code implements.

## 7. The `TObject` base

`TObject` is the most common base class and it is framed unlike any other. Its
streamer writes a version word with **no byte count**, then two 32-bit words
(`root/core/base/src/TObject.cxx:994`):

```
version:i16   fUniqueID:u32   fBits:u32   [pidf:u16]
```

Four properties a reader needs:

- **The version word is ignored on reading, and it is always 1.**
  `TObject::Streamer` calls `SkipVersion` (`root/core/base/src/TObject.cxx:1000`),
  and writes `TObject::IsA()`'s version (`root/core/base/src/TObject.cxx:1022`),
  which is `ClassDef(TObject, 1)` (`root/core/base/inc/TObject.h:248`) and is
  the same at all 396 release tags from 3.00 to 6.40 that carry the header. Being ignored, it is no use for
  reading the base itself; it is the one fixed value a reader can test a
  **framing** decision against, which is what
  [Streamer-driven reading §7.1](StreamerDriven.md#71-an-object-with-no-byte-count)
  needs. Invariant 10.
- **`fBits` is masked when written.** `kIsOnHeap` (`0x01000000`) and
  `kNotDeleted` (`0x02000000`) are cleared
  (`root/core/base/src/TObject.cxx:1033`), so they never appear on disk even
  though they are always set in memory. The one exception is a file carrying
  `TFile::k630forwardCompatibility`, which writes `fBits` raw
  (`root/core/base/src/TObject.cxx:1030`); it is off unless explicitly enabled.
- **`kIsReferenced` (`BIT(4)`) adds a trailing `u16`.** When that bit is set in
  `fBits`, a `pidf` process-identifier index follows `fBits`
  (`root/core/base/src/TObject.cxx:1005-1008`,
  `root/core/base/src/TObject.cxx:1048`), and `fUniqueID` is written masked to
  its low 24 bits — the top byte is an in-memory process index and is not
  persisted (`root/core/base/src/TObject.cxx:1036`). So the base is **10 or 12
  bytes**, and the only signal is a bit of the `fBits` value just read. A reader
  MUST test it and consume the extra two bytes. See
  [References](References.md).
- **The base may be absent entirely.** If the owning class sets
  `kIgnoreTObjectStreamer`, `TObject::Streamer` returns immediately and writes
  nothing (`root/core/base/src/TObject.cxx:996-997`). The streamer info is what
  says whether to expect it.

> Demonstrated by `serialization/object-tags`: at offset 369 a `TObject` base
> begins with a bare version word, with no byte count, directly after the
> enclosing `TList`'s version word at 367.

## 8. Reading

To read one object slot at the current position:

1. Read a `u32`, *w*.
2. If *w* is 0, the slot is a null pointer. Done.
3. If *w* has `kByteCountMask` set and *w* is not `kNewClassTag`, it is a byte
   count; remember the end position as `here + 4 + (w & ~kByteCountMask)` where
   `here` is the position of *w*, and read the next `u32` as the tag. Otherwise
   *w* is the tag and there is no byte count.
4. If the tag has neither `kClassMask` set nor equals `kNewClassTag`, it is an
   object reference: return the object already recorded at map position *tag*.
5. If the tag is `kNewClassTag`, read a null-terminated class name and record the
   class at `(position of the tag) + 2`. Otherwise the tag is
   `kClassMask | p`; the class is the one recorded at map position *p*.
6. Record the object at `(position of w) + 2` before reading its content, so that
   a reference from inside the object itself resolves.
7. Read the object: a version word (§3), then the class's content as specified by
   [Streamer-driven reading](StreamerDriven.md).
8. If there was a byte count, seek to the remembered end position regardless of
   how many bytes step 7 consumed.

To read a version word at the current position:

1. Read a `u32`. If `kByteCountMask` is set, it is a byte count; otherwise rewind
   4 bytes and treat the byte count as absent.
2. Read an `i16`.
3. If it is 0, apply §4 to decide whether a `u32` checksum follows.
4. Mask off `kStreamedMemberWise` (`0x4000`) before comparing with a class
   version, and treat it as specified in [Collections](Collections.md).

## 9. Invariants

1. Every byte count is `< kMaxMapCount` (`0x3FFFFFFE`).
2. A byte count plus its own 4 bytes does not extend past the end of the
   enclosing byte count, or past the end of the payload at the outermost level.
3. Byte counts nest properly: they form a tree, never a partial overlap.
4. Every class version word, once `kStreamedMemberWise` is masked off, is in
   `[0, kMaxVersion]`.
5. Every class back-reference names a position at which a `kNewClassTag` word was
   read earlier **in the same buffer**, and the position equals that word's offset
   from the start of the record plus 2.
6. Every object reference names a position at which a byte-count word was read
   earlier in the same buffer, plus 2.
7. A back-reference of 1 names the record's top-level object (§6.2); any other
   back-reference is at least 2.
8. A class or object back-reference above 1 points **backwards**: its position is
   less than the position of the reference itself.
9. At the outermost level, the bytes consumed equal `fObjlen` exactly. For a
   class whose streamer emits a byte count, that count spans the payload
   exactly — **except** for the classes of §2.4, which write past their own byte
   count by design; for the classes of §2.3 there is no outermost count to check
   against.

10. Every `TObject` base's version word is 1 (§7).

> Invariant 10 holds on every record of every file in reach — the fixtures,
> `gen/cern/`, `gen/foreign/` and `root/roottest/` — and on every entry too. Over
> those same files, until 2026-09-23 the only `TObject` base any reading met with
> another value was a misreading: 20 in `uproot-issue475.root` and 2 in
> `skim.root`, each a version word taken for a `TObject` or the reverse
> ([Streamer-driven reading §7.1](StreamerDriven.md#71-an-object-with-no-byte-count)).

Invariant 9 is the one that legitimately fails in the wild: a class whose
hand-written `Streamer` is out of step with its data produces a byte-count
mismatch, which ROOT reports and recovers from (§2.1).

## 10. Errata

Against `root/io/doc/TFile/*.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | — | No document describes the byte-count word at all, so nothing states that the count excludes its own four bytes (§2) |
| 2 | — | Nothing states that a byte count is optional before a version word, or that its absence is detected structurally rather than from the file version (§3) |
| 3 | — | `kByteCountVMask` and `kStreamedMemberWise` are both `0x4000` and apply to different words (§3.1) |
| 4 | — | A version word of 0 is ambiguous: a checksum follows for a foreign class but not for a class that declares version 0 (§4). This is the single most consequential gap |
| 5 | — | Buffer positions are measured from the start of the **key**, so every back-reference includes `fKeylen` (§1) |
| 6 | — | A class is mapped at its tag word but an object at its byte-count word, four bytes apart (§6.1) |
| 7 | — | A class name in a `kNewClassTag` record is null-terminated, not a counted string — the only such string in the format (§5.1) |
| 8 | — | `TObject`'s version word is ignored on reading, `kIsReferenced` adds a trailing `u16`, `fUniqueID` is then truncated to 24 bits, and the whole base may be absent (§7) |
| 9 | `tobject.md`: inside the `StreamerInfo` record `fBits` "will be `0x03000000`" | It is `0x00000000`. `kIsOnHeap` and `kNotDeleted` are masked off on write (§7). `0x03000000` was correct before the masking was introduced |
| 10 | `dobject.md`: only the class back-reference is described | Neither the **object** back-reference nor the null pointer is documented at all, so a reader built from it cannot parse either (§6) |
| 11 | `dobject.md`: the two byte counts are given identical wording | They have different owners and different extents: the outer one spans the class record **and** the object, the inner one only the version and members (§2, §5) |
| 12 | — | Not every record's object data starts with a byte count: a `TRef` record's starts with a version word (§2.3) |
| 13 | `streamerinfo.md`: the `StreamerInfo` list is "always compressed at level 1 (even if compression level 0)" | Not so: in `container/file-minimal` the file is uncompressed and `fNbytes - fKeylen == fObjlen` for that record, so it is stored uncompressed |

## 11. Reference files

| Case | Exercises |
|---|---|
| `serialization/object-tags` | New-class records, a class back-reference, an object back-reference, and the `fKeylen` offset |
| `serialization/objects` | A null pointer, and byte-count-plus-class-record pointers |
| `serialization/basic-types` | A foreign class: version word 0 followed by a checksum |
| `serialization/version-zero` | A declared-version-0 class: version word 0 followed by no checksum |

No fixture covers a buffer written without byte counts, which needs a file older
than any ROOT release that can still be built here. The member-wise version word
is covered by `serialization/collections`.

The two ROOT 2 files in reach are the witnesses there are, and they show that
"before byte counts" was never all or nothing. In `pippa.root` (ROOT 2.24/00, in
`gen/cern/`) a `TH1F` opens `40 00 03 2e 00 01` and its `TH1` base `40 00 01 8c
00 01` — byte counts on both — while the `TNamed`, `TObject` and `TAttLine`
inside them are bare version words. `root/roottest/root/tree/friend/MC_uds_reco-1.root`
(ROOT 2.23/12) has the same shape in a `TTree`: `40 02 31 6e 00 04`, then `TNamed`,
`TObject`, `TAttLine`, `TAttFill` and `TAttMarker` with none. §3's structural test
is what reads both. Both also carry `fBits` as `0x03000000`, the unmasked value of
erratum 9. Neither file has a streamer info, so decision 7 of `PLAN.md` puts their
objects out of scope and this is a statement about framing only.
