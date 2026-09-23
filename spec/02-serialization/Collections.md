# Collections

STL containers, `std::string`, and `TClonesArray`.

This is the hardest part of the serialization layer, for one reason: **the same
C++ type is written in two entirely different ways depending on what its elements
are**, and the only thing that distinguishes them on disk is bit 14 of a version
word.

There is nothing about collections in the shipped ROOT documentation at all — the
word "STL" does not appear in `root/io/doc/TFile/README.md`. Everything here comes
from the source and from bytes.

## 1. Which element carries a collection

A collection member is a `TStreamerSTL` element, or a `TStreamerSTLstring` for a
`std::string`. Two of its fields matter and both are at the end of the element
record ([Streamer information §8](StreamerInfo.md#8-the-element-subclasses)):

| Field | Meaning |
|---|---|
| `fSTLtype` | which container, from `ROOT::ESTLType` |
| `fCtype` | a type code for the element, but see §7 |

```
kNotSTL 0   vector 1   list 2   deque 3   map 4   multimap 5   set 6
multiset 7   bitset 8   forward_list 9   unordered_set 10
unordered_multiset 11   unordered_map 12   unordered_multimap 13
RVec 14      kSTLany 300     kSTLstring 365
```

`root/core/foundation/inc/ESTLType.h:28-50`. A **pointer** to a collection adds
`kOffsetP` (40), so `vector<T>*` has `fSTLtype` 41
(`root/core/meta/src/TStreamerElement.cxx:1806`).

> **`set` is 6 and `multimap` is 5, and a reader MUST NOT trust either value.**
> `TStreamerSTL` numbered them the other way round — `kSTLset = 5`,
> `kSTLmultimap = 6` — while every other use of the enum had them as above. The
> declaration was standardised in **5.34/13** (`d1ffea01e01`, backported to the
> 5.34 series) and `TStreamerSTL::Streamer` gained the read-side repair only in
> **6.00/00** (`cf539483218`): when `fSTLtype` is 5 or 6 it takes the container
> from `fTypeName` instead (`root/core/meta/src/TStreamerElement.cxx:2112-2122`).
> The table in `root/io/doc/TFile/streamerinfo.md` records the old, wrong order.
>
> **Nothing in the element says which convention wrote it**, which is what makes
> the repair mandatory rather than a legacy nicety: the element version is 3 on
> both sides of the change. Measured on one member across four files —
> `RooAbsArg._boolAttrib`, a `set<string>`, at element version 3 throughout:
>
> | File | `fSTLtype` |
> |---|---|
> | `stressRooFit_v522_ref.root` | **5** |
> | `stressRooFit_v534_ref.root` | **5** |
> | `uproot-issue49.root` | 6 |
> | `uproot-issue-350.root` | 6 |
>
> `uproot-issue283.root` (ROOT 5.28/00) carries a third case, a `set<long>` at 5,
> and it is the one that matters: a reader that takes 5 at face value reads a set
> as a **multimap** and consumes two values per element. `tools/rootfile.py` did
> exactly that until 2026-09-21, on a rule this document already stated —
> invariant 10 now checks it. The pointer forms are **not** repaired: ROOT's test
> is on 5 and 6 exactly, so a `set<T>*` at 45 keeps whatever it was given.

Remember also that **`fType` on disk is always 500**
([Streamer information §10](StreamerInfo.md#10-tstreamerstl-stores-a-type-code-it-does-not-mean)),
written deliberately for forward compatibility
(`root/core/meta/src/TStreamerElement.cxx:2146`) and recomputed on read
(`root/core/meta/src/TStreamerElement.cxx:2124-2128`).

> Demonstrated by `serialization/collections`: eight collection members, all with
> `fType` 500, and `fSet` with `fSTLtype` 6.

## 2. The frame

Every collection member, both modes:

```
byteCount:u32   version:i16
```

The version is **`TStreamerInfo`'s own class version, currently 10**
(`root/io/io/inc/TStreamerInfo.h:256`) — not the collection's version, not the
element class's, and not a count. It is a *format capability level*: the reader
compares it against 7, 8 and 9 to decide what the older layouts looked like
(§6).

**Bit 14 of that word is `kStreamedMemberWise`** (`0x4000`,
`root/io/io/inc/TBufferFile.h:70`), set by `WriteVersionMemberWise`
(`root/io/io/src/TBufferFile.cxx:3203`). So:

| Version word | Mode |
|---|---|
| `0x000A` | object-wise |
| `0x400A` | member-wise |

This is the same bit that means "a byte count follows" in the *other* version-word
context; the two are told apart by position, as
[Buffer framing §3.1](Buffer.md#31-kbytecountvmask-and-kstreamedmemberwise-are-the-same-number)
explains.

> Demonstrated by `serialization/collections`: `fInts` at 342 reads `00 0a` and
> `fHits` at 395 reads `40 0a`.

> **The `0A` is not part of the format.** It is `TStreamerInfo`'s class version in
> the ROOT that wrote the file, and it was 9 from ROOT 5.26 until 6.35 and 8
> before that — so a frame written by any release before 6.36.00 reads `00 09` or
> `40 09`. **Mask `kStreamedMemberWise` and read the rest as a version number;
> never compare the word to 10.**
> [Element types §8.1](ElementTypes.md#81-the-version-word-is-not-a-constant)
> has the history and the corpus counts.

## 3. Object-wise

```
byteCount  version(0x000A)   count:i32   <each element, in full>
```

`root/io/io/src/TGenCollectionStreamer.cxx:1429-1434`. The count is a plain
`Int_t`. How an element is written depends on what it is:

| Element | On disk | Cited |
|---|---|---|
| fundamental or enum | its natural width, back to back | `root/io/io/src/TGenCollectionStreamer.cxx:891` |
| `Double32_t` or `Float16_t` | **not** its natural width: 4 bytes and 3 bytes respectively — see the note below | `root/io/io/src/TGenCollectionStreamer.cxx:931-933`, `:952-953` |
| a class | a **full framed object**: byte count, version, and a checksum if foreign | `root/io/io/src/TGenCollectionStreamer.cxx:976` |
| `std::string` | a bare counted string | `root/io/io/src/TGenCollectionStreamer.cxx:979` |
| pointer to a class | a full object slot, class record and all — §3.1 | `root/io/io/src/TGenCollectionStreamer.cxx:982` |
| a nested collection | a bare `count` and its elements — **no byte count, no version word** | §5 |
| a map entry | key then value, **interleaved** | `root/io/io/src/TGenCollectionStreamer.cxx:1024-1110` |

> Demonstrated by `serialization/collections`: `fInts` is `count 3` then three
> bare `i32`; `fWords` is `count 2` then `02 "pq" 02 "rs"`.

> **A collection of `Double32_t` or `Float16_t` cannot use the rules of
> [§5](ElementTypes.md#5-kdouble32-and-kfloat16), because there is no element to
> parse a comment from.** The collection streamer dispatches to
> `WriteFastArrayDouble32` / `WriteFastArrayFloat16` with the `TStreamerElement`
> argument left null (`root/io/io/src/TGenCollectionStreamer.cxx:931-933` and
> `:952-953`; read at `:275-276` and `:296-297`). With no element the bit count is
> 0, so a `Double32_t` element degrades to a plain **4-byte float**
> (`root/io/io/src/TBufferFile.cxx:703-706`) and a `Float16_t` element takes the
> default 12 bits and occupies **3 bytes**
> (`root/io/io/src/TBufferFile.cxx:631-634`). Neither is the declared type's width,
> and no annotation on the member can change it: the comment belongs to the
> collection, not to its elements.
>
> **No reference file exercises this**, and nothing in either corpus contains such
> a collection, so the claim rests on the source alone — recorded as a gap in
> `PLAN.md` §9.

### 3.1 Pointer content puts two frames in a row

The pointer row above is the one that does not look like the others, because an
object slot is not a member: it is byte count, class record, and *then* the
object — and the object carries the byte count and version word every
streamer-info-driven class carries. So a collection of pointers to a class whose
own members include a collection reads as three frames nested inside each other:

```
bc  ver=0x000A  count        the collection frame (§2)
  bc  tag                    the object slot (Buffer framing §6)
    bc  ver=0x0001           the content class's own frame
      bc  ver=0x000A  count  a collection *inside* the content class
```

**Only the outer and the innermost frames are collection frames.** The one
between them is a class frame, and its version word is the content class's
`ClassDef` version rather than `TStreamerInfo`'s 10. Telling them apart by the
version word alone fails as soon as a content class is at class version 10, so
read the nesting instead: a collection frame is the one a `TStreamerSTL` element
sent you to, and a class frame is the one an object slot sent you to.

> Demonstrated by `serialization/pointer-collection`: `fPtrs` is a
> `vector<PtrItem*>`, `PtrItem` holds a `vector<double>`, and the four frames
> above stand at 381, 391, 407 and 413.

**The elements of a pointer collection are not of uniform length**, and the same
three-element collection shows all three ways one can end:

| Slot | First `u32` | What follows |
|---|---|---|
| `fPtrs[0]` | `0x4000002C`, a byte count | `kNewClassTag`, the class name, then the object |
| `fPtrs[1]` | `0x00000000` | **nothing** — a null pointer is four bytes with no frame at all |
| `fPtrs[2]` | `0x4000001C`, a byte count | `0x80000045`, a class back-reference, then the object |

Nothing in the collection frame says which of the three any element is; only the
first `u32` of the element does, by [Buffer framing §6](Buffer.md#6-object-slots).

> This is the shape the first outside review of this specification read as a
> **doubled collection frame** — a frame whose version word is 1 followed by an
> ordinary collection frame, seen on `RooVectorDataStore::RealVector::_vec`
> ([issue #1](https://github.com/ariostas/root-io-spec/issues/1) item 10). It is
> not a second collection frame, and 1 is not a collection version: `RealVector`
> is `ClassDef(RealVector, 1)`
> (`root/roofit/roofitcore/inc/RooVectorDataStore.h:336`), reached through the
> pointer content of `vector<RooVectorDataStore::RealVector*>`.


## 4. Member-wise

```
byteCount  version(0x400A)   valueVersion   count:i32
    <member 0 for every element>
    <member 1 for every element>
    ...
```

The **second version word belongs to the collection's value class** — the element
type for a sequence, and the synthetic `pair<K,V>` for a map. It is read by
`ReadVersionForMemberWise` (`root/io/io/src/TBufferFile.cxx:3085`), which differs
from an ordinary version word in one way: **there is no byte count in front of
it**. Otherwise the rule of
[Buffer framing §4](Buffer.md#4-a-version-word-of-0-has-two-different-meanings)
applies unchanged — 0 or less is followed by a `u32` checksum for a foreign class,
and the checksum selects the info.

Then the count, and then the *transposed* body: `TBufferFile::ApplySequence` runs
actions on the outside and elements on the inside
(`root/io/io/src/TBufferFile.cxx:3796`), so each member of the value class
occupies one contiguous column.

> Demonstrated by `serialization/collections`: `fHits` is
> `40 0a | 00 00 | 040059d1 | 00000002 | 0000000a 00000014 | 3fc00000 40200000`
> — both `x` values, then both `y` values. Its `Hit` is interpreted, hence the
> `00 00` and the checksum.
>
> `serialization/collection-forms` is the other half: its `CHit` has a real
> `ClassDef`, so `fHits` reads `40 0a | 00 02 | 00000002 | ...` — **a plain
> version word, with no checksum after it.** Both forms are legal in the same
> position, and only the file's own streamer infos tell them apart.

### 4.1 The columns are not uniformly framed

| Member kind | Framing inside the column |
|---|---|
| fundamental | none: the values are concatenated |
| a base class | none, and **one column per member of the base** — the base's own info is read over the same *n* elements, not the base once per element |
| `TString` (65) | none: *n* counted strings, back to back |
| an object member (61, 62) | **each element gets its own** byte count and version word |
| a pointer member (64, 69) | each element is an [object slot](Buffer.md#6-object-slots) |
| a collection member (500), `std::string` included | **one** byte count and version word for the *whole column* |

The last row is the surprising one and it follows from how the action is built:
a collection column falls through to `GenericWrite`, which calls the ordinary
member loop once with an array of `n` objects
(`root/io/io/src/TStreamerInfoActions.cxx:2214-2228`), and the frame is written
once inside that single call.

> The `TString` row and the `std::string` row are the pair to keep straight. The
> data looks the same and the framing does not, and nothing but the member's
> element class says which it is. `serialization/pairs` has both, twelve bytes
> apart.

### 4.2 A base class loses its version word

Inside a member-wise column a base class contributes its members with **no byte
count and no version word**, so the base's version must be taken from
`TStreamerBase::fBaseVersion` in the element record. ROOT records this as a defect
in a comment at the point where it happens:

> "Rather than relying on the StreamerElement to contain the base class version
> information we should embed it in the bytestream even in the member-wise case."
> — `root/io/io/src/TStreamerInfoReadBuffer.cxx:1405-1409`

A `TObject` base is therefore exactly 10 or 12 bytes per element with nothing
around it ([References §1](References.md#1-the-extra-word-on-a-referenced-tobject)).

**Any other base is its members' columns.** The line after that comment reads the
base's info over the whole array in the same array mode
(`root/io/io/src/TStreamerInfoReadBuffer.cxx:1409-1410`), so a base with members
`a` and `b` is all *n* values of `a`, then all *n* of `b`. That differs from "the
base, once per element" as soon as the base has two members. Which info is read
is the one `TStreamerBase` selects: by `fBaseVersion`, or by `fBaseCheckSum`
when the version is negative and the checksum is not 0
(`root/core/meta/src/TStreamerElement.cxx:762-765`). That is how a base whose class
declares no version, `fBaseVersion` −1, is found at all.

> Witnessed by `uproot-physlite-rntuple_v1-0-0-0.root` of the foreign corpus, an
> ATLAS file written by ROOT 6.34/04. `vector<ElementLink<…>>` is written
> member-wise, and `ElementLink`'s one element is the base `ElementLinkBase`
> (`fBaseVersion` −1) with two `unsigned int` members. Four links read
> `40 00 00 2c | 40 09 | 00 00 69 77 75 53 | 00 00 00 04 | 00 00 00 00 ×4 | ff ff ff ff ×4`:
> every `m_persKey`, then every `m_persIndex`. Until 2026-09-22 the table above
> said "once per element", and a reader following it failed on 1 005 branch-baskets of
> that file.

### 4.3 An empty member-wise collection writes no columns at all

Not empty columns — **no columns**. After the count of 0 the collection ends, and
the columns' own headers are not written either
(`root/io/io/src/TStreamerInfoReadBuffer.cxx:1197-1199`, where ROOT does nothing
for `!nobjects`). The whole member is then the byte count, the two version words,
the checksum where there is one, and four zero bytes.

This is **version dependent**, and ROOT's comment at that line says so: at
`TStreamerInfo` version 6 and below the columns were written for an empty
collection. The version in question is the one on the collection's own frame, not
the value class's.

> Demonstrated by `serialization/pairs`, whose `fEmpty` is an empty
> `map<string,int>` in sixteen bytes: `40 00 00 0c | 40 0a | 00 00 | 3a 5a 65 72
> | 00 00 00 00`. The byte count of 12 leaves no room for a column header.

**A split branch is the opposite case and it is easy to conflate them.** There an
`fType` 31 or 41 column of *n* = 0 values still carries its shared frame — six
bytes, not zero — because the branch writes an entry whether or not the
collection has anything in it
([Reading entries §3.2](../04-ttree/ReadingEntries.md#32-a-member-of-a-split-container-a-bare-packed-column)).
A reader that always reads a column header desynchronises on `fEmpty`; one that
never does desynchronises on the split branch.

## 5. Which mode is used

Member-wise is chosen only if **all six** of these hold
(`root/io/io/src/TStreamerInfoActions.cxx:1183-1188`):

1. the buffer can handle it — true for a file, false for `TMessage` and for the
   text buffers (`root/core/base/inc/TBuffer.h:76`);
2. the collection has a proxy **and** a non-null value *class*;
3. the global `TVirtualStreamerInfo::GetStreamMemberWise()`, default true
   (`root/core/meta/src/TVirtualStreamerInfo.cxx:30`);
4. `TClass::CanSplit()` on the **collection's** class, which then tests the
   value class — the proxy is the collection's
   (`root/io/io/src/TStreamerInfoActions.cxx:1177-1180`);
5. the element's comment does not begin with exactly `||`;
6. the value class has no custom streamer member.

`CanSplit` is where most collections fall out
(`root/core/meta/src/TClass.cxx:2354-2362`): it refuses a collection of pointers,
one with no value class, one whose value class is `TString` or `std::string`, one
whose value class cannot split, and — the one that catches people —
**one whose value class is itself a collection**.

The practical table, for a file:

| Member | Mode | Because |
|---|---|---|
| `vector<int>`, `set<int>`, `vector<bool>` | object-wise | no value class |
| `vector<MyClass>`, `list<MyClass>` | **member-wise** | a splittable value class |
| `map<K,V>` | **member-wise** | the value class is `pair<K,V>` |
| `vector<vector<int>>` | object-wise | the value class is a collection |
| `vector<string>` | object-wise | `CanSplit` refuses `std::string` |
| `vector<MyClass*>` | object-wise | `HasPointers` |
| `bitset<N>` | object-wise | no value class |

> All seven rows are demonstrated by `serialization/collections`, which contains
> one member from each except the pointer and bitset rows.

## 6. Older files

The first version word, once `kStreamedMemberWise` is masked off, gates three
backward-compatibility branches:

| Condition | Difference |
|---|---|
| `version < 8` (`kSTL`), `< 9` (`kSTLp`) | **no second version word at all**; the value-class version is taken as 0 (`root/io/io/src/TStreamerInfoReadBuffer.cxx:1166-1169`) |
| `version < 7` | the body was written even when `count` was 0 (`root/io/io/src/TStreamerInfoReadBuffer.cxx:1197`) |
| `version < 9` (`kSTLp`), `< 8` (`kSTL`) | **schema evolution of the value class is refused**: ROOT reports that the old `TStreamerInfo` "did not record enough information to convert" and skips the member entirely (`root/io/io/src/TStreamerInfoReadBuffer.cxx:1160-1164` and `:1264-1268`). A reader with the file's own info does not need the conversion and can read the member as written |

> **ROOT's two readers disagree here.** The action-based reader uses `>= 8` for
> both `kSTL` and `kSTLp` (`root/io/io/src/TStreamerInfoActions.cxx:845`), while
> the legacy loop uses `>= 9` for `kSTLp`
> (`root/io/io/src/TStreamerInfoReadBuffer.cxx:1167`). For a `kSTLp` member
> written at level 8 the two differ by one 2-byte word. This is recorded as an
> apparent inconsistency; no such file has been constructed here.

## 7. `fCtype` does not determine the layout

`fCtype` is a type code for the element
(`root/core/meta/src/TStreamerElement.cxx:1808-1820`), and it is much less
informative than it looks:

- for a collection of class objects it is **61** (`kObject`) **even when the
  value class does not derive from `TObject`** — 62 never appears here;
- for a collection of pointers it is 63, again regardless of `TObject`;
- for `bitset` it is **0**;
- for `map<K,V>` it is 61, describing the `pair`, not the key or the value.

So `fCtype` 61 covers a nested collection, a `std::string`, a `pair`, and an
ordinary class — four completely different layouts. **Only `fTypeName`
distinguishes them**, and a reader must parse the type name.

> Demonstrated by `serialization/collections`: `fNested`, `fWords` and `fMap` all
> have `fCtype` 61, and are respectively a bare nested collection, a counted
> string, and a transposed pair.

## 8. `std::map`

Both layouts appear, and the mode decides which:

| Mode | Layout |
|---|---|
| object-wise | `count`, then `key, value, key, value, …` — a vector of pairs |
| member-wise | `count`, then all keys, then all values — a pair of vectors |

The member-wise case follows from the value class being the `pair<K,V>` `TClass`
(`root/io/io/src/TGenCollectionProxy.cxx:889-945`), whose two members are `first`
and `second`; the object-wise case is the explicit two-pass loop in `WriteMap`
(`root/io/io/src/TGenCollectionStreamer.cxx:1032`).

Note that `HasPointers()` deliberately returns false for a map even when the key
or value is a pointer (`root/io/io/src/TGenCollectionProxy.cxx:1035`), so a map
is not blocked from member-wise the way `vector<T*>` is.

> **A file may or may not contain a streamer info for `pair<K,V>`, and which it
> is cannot be predicted.** A reader MUST be able to synthesise the layout —
> `first` then `second`, from the two template arguments — and MUST look for a
> recorded info first, because when one is present it is the authority.
>
> Demonstrated both ways. In `serialization/collections`, `fMap`'s frame at 477
> names checksum `0x95f86d56` and that record's `TList` contains only `Coll` and
> `Hit`: no info for `pair<int,int>` at all. In `serialization/pairs`, four of
> six pairs have one and two do not.

Across `gen/foreign/` and `gen/cern/` it is 28 map members whose pair info is in
the file against 23 whose is not, and the split does not follow from the member
types: `pair<string,int>` appears both ways in different files. Treat presence as
a property of how the writing program's dictionaries were built, not of the
format.

### 8.1 What a synthesised pair's members look like

The two elements are `first` and `second` in that order, and each takes its shape
from its declared type — the same shapes §4.1 lists, because a pair is an ordinary
value class and its columns are ordinary columns:

| Template argument | Element | Column of *n* values |
|---|---|---|
| a fundamental type | `TStreamerBasicType` | *n* values, concatenated |
| `std::string` | `TStreamerSTLstring`, `fSTLtype` 365 | one shared frame, then *n* counted strings |
| `TString` | `TStreamerString` (65) | *n* counted strings, no frame |
| a collection | `TStreamerSTL` with that `fSTLtype` | one shared frame, then *n* collections |
| a pointer | `TStreamerObjectAnyPointer` (69) | *n* object slots |
| any other class | `TStreamerObjectAny` (62) | *n* framed objects |

> All six are demonstrated by `serialization/pairs`, one map each.

> **The element titles are the standard library's own doc comments**, so two
> files holding the same pair can differ in the bytes of its info. libstdc++
> declares `_T1 first;  ///< The first member` in `<bits/stl_pair.h>` and libc++
> declares no comment, so a `pair<string,int>` with a real dictionary carries
> `The first member` and `The second member` where one built against libc++
> carries two empty strings — 35 bytes against 2. An *emulated* pair, built with
> no dictionary at all, carries `Emulation` on both members instead, whichever
> library is in use. None of the three affects decoding, and all three are in
> the fixtures: `serialization/pairs` has the emulated form on three of its
> pairs and the dictionary form on `pair<string,int>`, which is why that case
> and `classes/roofit` are the two that cannot have a portable digest
> (`PLAN.md` §3.3).

### 8.2 The checksum does not identify the pair

> **Two different `pair<K,V>` in the same file can carry the same checksum.**

`serialization/pairs` has three: `pair<int,string>`, `pair<int,vector<short> >`
and `pair<TString,PHit*>` all carry `0x0b5fb752`, in their recorded streamer
infos and in their member-wise headers alike.

**And the same value is in another file, on a fourth layout.**
`classes/roofit` was generated from RooFit rather than from that case, and its
`pair<string,vector<int> >` — reached through `RooCategory::_rangesPointerForIO`
and `RooRealVarSharedProperties::_altBinning` — carries `0x0b5fb752` too. So the
number is a constant ROOT produces, not a coincidence of one fixture, and a
reader that keys a table by checksum will collide with it in files that have
nothing to do with each other.

ROOT reads such a file correctly because it never searches for the checksum
globally. `ReadVersionForMemberWise` is given the value class — already resolved
from the member's *declared type name* — and calls
`cl->FindStreamerInfo(checksum)` on that class alone
(`root/io/io/src/TBufferFile.cxx:3085-3100`), so the checksum only chooses among
one pair's own versions.

**A reader MUST do the same**: take the pair from the member's type name, and use
the checksum only to select a version within it. One that keeps a global
checksum → info table will decode two of those three maps as the wrong type.

> The mechanism is a caching artefact rather than anything in the format.
> `TClass::GetCheckSum` computes from the class's data-member list and caches the
> result in `fCheckSum`, which "once it has transition from a zero Value it never
> changes" (`root/core/meta/src/TClass.cxx:6655-6666`). A `pair<K,V>` whose
> `TClass` is still forward-declared has no data members yet, so a checksum taken
> at that moment is computed from almost nothing and then kept. Which pairs it
> happens to is a function of the order in which the writing program touched
> them; `PLAN.md` §7.1 banks it as an upstream report.

> **The usual case is the sound one**, which is why a reader must not infer the
> rule from the exception. `uproot-issue38c.root` of the foreign corpus
> (`PLAN.md` §9.8), written by ROOT 6.22/06, carries `pair<double,double>` at
> class version 1 with checksum **`0x00D7BED2`** — the value class of
> `TEfficiency::fBeta_bin_params`, a `vector<pair<double,double> >` — and that
> value **recomputes exactly** from the element list the same file records. So
> most pairs in most files are ordinary, and none of that helps: nothing in a
> file marks which pairs escaped the caching and which did not, so the rule above
> holds either way.

## 9. The value class's streamer info can be missing entirely

> **ROOT can write a `std::vector<T>` that nothing, including ROOT, can read.**

If `T` is a class known only to the interpreter — no dictionary — and the *only*
reference to `T` in the written class is through a collection, then `T`'s streamer
info is not recorded. The bytes are written member-wise, naming `T`'s checksum, and
there is no warning.

Reproduced with ROOT 6.40.04:

```cpp
struct Hit3 { Int_t x; Float_t y; };
struct C3   { std::vector<Hit3> fHits; };
// write C3 -> silence
// reopen   -> Error in <TBufferFile::CheckByteCount>:
//             object of class vector<Hit3> read too few bytes: 6 instead of 20
```

Adding any direct member of type `Hit3` to `C3` is enough to get the info written
and the file becomes readable. This is why `serialization/collections` carries the
otherwise pointless `fOne`.

The `pair<K,V>` omission of §8 is the same phenomenon with a happy ending: ROOT
survives it only because a pair's layout is recoverable from its name. For a
user's own class it is not, and the data is lost.

A reader SHOULD report a member-wise collection whose value class has no streamer
info, rather than guess.

## 10. `std::string`

A `std::string` **member** is a `TStreamerSTLstring`, and despite the name it is
not streamed as a collection:

```
byteCount   version(0x000A)   counted string
```

The counted string is the encoding of
[Conventions §5.1](../00-conventions.md#51-counted-string) — one length byte,
with a `0xFF` escape to a 4-byte length. There is **no element count and no
element loop**.

> The version word is `TStreamerInfo`'s 10, exactly as for any other collection
> member. It is **not** `std::string`'s own class version, which is 2
> (`root/core/base/src/String.cxx:39`), and not `TStreamerSTLstring`'s, which is
> 2 as well. Every reader that has guessed otherwise has guessed wrong.

An empty `std::string` member is therefore **7 bytes**, not 1.

A `std::string` *inside* a collection has no frame at all: it is the bare counted
string of §3.

> Demonstrated by `serialization/collections`: `fStr` is
> `40 00 00 06 | 00 0a | 03 "abc"`, and `fWords`'s two strings have no framing.

### 10.1 A `std::string` object has no frame either

The three-byte-different case that catches readers: when a `std::string` is the
*whole object* — a record of its own, or a member of a pointer-to-object type, or
one half of a `pair` — it is again the **bare counted string**, with no byte count
and no version word.

`std::string`'s `TClass` carries a hand-written streamer registered outside the
class (`root/core/base/src/String.cxx:36`), and that streamer is
`TBufferFile::WriteStdString` / `ReadStdString`
(`root/io/io/src/TBufferFile.cxx:261-280`, `root/io/io/src/TBufferFile.cxx:230-255`),
which writes nothing but the counted string. Its declared class version is 2
(`root/core/base/src/String.cxx:39`), and that number never reaches a file.

So the same `std::string` is written three different ways depending on where it
sits:

| Where | Bytes |
|---|---|
| A member (`TStreamerSTLstring`) | `byteCount version(10) counted-string` — §10 |
| An element of a collection | counted string |
| A whole object: a record, a `pair` half, a pointed-to object | counted string |

A reader MUST hardcode this: no file contains a streamer info for `string`, so the
streamer-driven algorithm has nothing to go on
([Streamer-driven reading §6](StreamerDriven.md#6-when-there-is-no-usable-streamer-info)).
The class name in the key or class record is spelled `string` — not
`std::string`, and not the fully expanded `basic_string<...>`.

> **Unlike `TLeafC`, an empty string does write its length byte.**
> `WriteStdString` emits the zero (`root/io/io/src/TBufferFile.cxx:275-277`) where
> `WriteFastArrayString` returns first
> ([TLeaf §9](../04-ttree/TLeaf.md#9-tleafc)). The two look alike and are not
> interchangeable.

> Found by the foreign-file probe, not by a fixture: 114 records across
> `uproot-issue485` and `uproot-issue486` are standalone `string` objects, and
> `string-example.root` holds one 127-byte record whose payload is
> `7e` followed by 126 bytes of JSON. `PLAN.md` §9.8 has the run.

## 11. Other containers

**`std::vector<bool>`** is special-cased in ROOT's code to work around the
bit-packed representation, but **not on disk**: it is object-wise, and each
element is **one byte** (`root/io/io/src/TBufferFile.cxx:1985-1997`). `fCtype` is
18.

**`std::bitset<N>`** is a real collection with `fSTLtype` 8 and `fCtype` 0. Its
count is the **number of bits**, and each bit is one byte, least significant
first (`root/io/io/src/TGenCollectionStreamer.cxx:1400-1402`). `fSize` is
`sizeof(std::bitset<N>)` and has nothing to do with the payload.

**`std::array<T,N>` is not a collection at all.** ROOT maps it to a fixed C
array: the element is a `TStreamerBasicType`, a `TStreamerObject` or a
`TStreamerObjectAny` with `kOffsetL` added, and the bytes are those of
[Element types §3](ElementTypes.md#3-koffsetl-t-20-t-fixed-size-array) and
[§7.2](ElementTypes.md#72-the-array-forms-are-not-uniform) — no byte count, no
version word, no count. **Nothing on disk distinguishes a `std::array<Int_t,3>`
from an `Int_t[3]`.**

> Demonstrated by `serialization/collection-forms`: `fArrInt`, a
> `std::array<Int_t,3>`, is code 23 and twelve bare bytes, and `fArrHit`, a
> `std::array<CHit,2>`, is code 82 — two self-framing objects with nothing
> around them.

**Nested collections** are always object-wise (§5), and the inner ones are bare:
a count and its elements, with no framing of their own, at every depth.

### 11.1 A fixed array of collections shares one frame

```
byteCount  version   <collection>  ×  fArrayLength
```

A member declared `std::vector<T> m[N]` is **one** `bc ver` followed by *N*
complete collections, each with its own count. Not *N* framed members, and not
one flattened collection.

> **`fArrayLength` is the only thing in the file that says so.** The stored
> `fType` is 500 like any other `TStreamerSTL`, and the `kOffsetL` that would
> mark it appears only after the read-time recompute of
> [Streamer information §10](StreamerInfo.md#10-tstreamerstl-stores-a-type-code-it-does-not-mean)
> (`root/core/meta/src/TStreamerElement.cxx:2124-2128`). A reader that switches
> on the stored code alone reads the first collection and stops eight bytes
> short of the byte count.
>
> Demonstrated by `serialization/collection-forms`: `fVecArr` is
> `std::vector<Int_t> fVecArr[2]`, one frame of 22 bytes holding `{11, 12}` and
> then `{13}`.

### 11.2 A class that is a collection: the `This` element

A class may *be* a collection rather than hold one: it has a collection proxy of
its own, supplied by its dictionary, while its name is no STL name at all.
ATLAS's `DataVector<T>` is the case in practice, and so is any class named after
one, such as `xAOD::CutBookkeeperContainer_v1`. Its streamer info then holds
**one element and nothing else**, built by `TStreamerInfo::Build` whenever the
class has a proxy (`root/io/io/src/TStreamerInfo.cxx:421-435`):

| Field | Value |
|---|---|
| `fName` | `This` |
| `fTypeName` | the class's own name — `xAOD::CutBookkeeperContainer_v1`, no template argument |
| `fTitle` | `<Value> Used to call the proper TStreamerInfo case`, or `<Value*> …` when the proxy holds pointers |
| `fSTLtype` | what the proxy reports, **not** what the name says (`root/core/meta/src/TStreamerElement.cxx:1803`) |
| `fCtype` | 61 for a value class without pointers (`root/core/meta/src/TStreamerElement.cxx:1810-1812`) |

**The value class is in the title**, between the leading `<` and its matching
`>`. `fTypeName` cannot give it, because it names the container class rather
than spelling a container. This is also what ROOT does with no dictionary: it
takes the title's bracketed type, prepends `vector`, and gives the class that
`vector`'s emulated proxy (`root/io/io/src/TStreamerInfo.cxx:1000-1024`). So
**a reader SHOULD read such a `This` element as a `vector` of the title's
type**, whatever `fSTLtype` says.

**An STL class's own info has a `This` element too**, and there the name
decides. A `map<string,double>` stored as a branch of its own has an info named
`map<string,double>` whose one element is `This`, titled
`<pair<string,double> > …`. ROOT builds a proxy from an STL name, and consults
the title only for a class that has none (`isstl && !fClass->GetCollectionProxy()`,
`root/io/io/src/TStreamerInfo.cxx:1002-1003`). A reader that takes the title there
reads the map as a `vector` of pairs — objects that need a `pair` info the file
does not carry. So the title applies exactly when `fTypeName` is not a container
name. The bytes are an ordinary collection member
(§2 to §4): the frame, then the count and elements object-wise, or the value
class's version and checksum, the count and the columns member-wise.

The title has recorded the value class since ROOT commit `e69180ee910`
(2013-07-30), first in 5.34/10 and in the 6 series. Before it, the title is
the bare `Used to call the proper TStreamerInfo case`. Then ROOT, without the
class's dictionary, warns that it *"will claim the content is a bool (i.e. no
data will be read)"* (`root/io/io/src/TStreamerInfo.cxx:1025-1030`), and a reader
has no better source.

**A member-wise frame's checksum is not a substitute.** It is present only when
the value class is foreign and at class version 1 or less
(`root/io/io/src/TBufferFile.cxx:3162-3172`), and ROOT uses it to choose among
the infos of a class it already knows by name (`TClass::FindStreamerInfo`,
`root/core/meta/src/TClass.cxx:7159-7184`). No code path in ROOT looks a checksum
up across classes, and §8.2 shows that doing so can find the wrong one.

> Measured on `uproot-physlite-rntuple_v1-0-0-0.root` (`gen/foreign/`, ATLAS,
> ROOT 6.34/04). Three classes in it have a `This` element, all with `fSTLtype` 2
> (`list`) and `fCtype` 61, and titles `<xAOD::CutBookkeeper_v1> …`,
> `<xAOD::TruthMetaData_v1> …` and `<xAOD::TriggerMenuJson_v1> …`. The `MetaData`
> tree stores them in 1 010 unsplit branches (`fType` 0, `fID` -1), every entry
> member-wise. In 970 of them the entry is
> `40 00 00 0c | 40 09 | 00 00 f1 3a 09 61 | 00 00 00 04` — `0xf13a0961` is
> `xAOD::CutBookkeeper_v1`'s checksum, and 4 is the count — with **no columns**,
> because that class's only member is a base whose own base has no elements. ROOT
> 6.40.04 without ATLAS's libraries reads the same 4 elements from it.
> Until 2026-09-23 this project's reader declined the 975 whose type name has no
> template argument, and read the other 35 by taking `DataVector<X>`'s first
> argument — right only because ATLAS's value class is that argument.

## 12. `TClonesArray`

A `TClonesArray` predates all of the above and has its own format. Class version
**4** (`root/core/cont/inc/TClonesArray.h:88`), hand-written streamer
(`root/core/cont/src/TClonesArray.cxx:744`).

| Offset | Field | Present |
|---|---|---|
| 0 | byte count | always |
| 4 | version | always |
| 6 | `TObject` base | version > 2 |
| … | `fName`, counted string | version > 1 |
| … | `"<class>;<classversion>"`, counted string | always |
| … | `nobjects:i32` | always |
| … | `fLowerBound:i32` | always |
| … | the objects | see below |

The element class and its version come from that one counted string — for example
`Pt;2`. There is no class record and no per-object version word.

**The mode is a bit in `fBits`.** `kBypassStreamer` is `BIT(12)`
(`root/core/cont/inc/TClonesArray.h:37`), and it is written into the `TObject`
base deliberately so that the encoding is self-describing
(`root/core/cont/src/TClonesArray.cxx:868-874`):

| `fBits & 0x1000` | Body |
|---|---|
| set (the default) | **transposed**, one column per member of the element class, exactly as §4 — but with **no second version word and no `kStreamedMemberWise` bit** (`root/io/io/src/TBufferIO.cxx:384-393`) |
| clear | per slot: a `Char_t` flag, 1 or 0, and if 1 the object written in full |

> **The bit moved.** In class version 3 it was `BIT(14)`
> (`root/core/cont/src/TClonesArray.cxx:757-758`); the version was bumped to 4
> for no other reason. A reader MUST branch on the class version before testing
> the bit.

> **Empty slots cost a byte each** in the non-bypass form, which ROOT's own
> header comment says (`root/core/cont/src/TClonesArray.cxx:740-742`) and the
> shipped documentation omits.
>
> Demonstrated by `serialization/clones-array`, which writes the same element
> class both ways. The bypass array's body at 417 is a `TObject` column, an `fX`
> column and an `fY` column; the other's at 557 is `00 01` — an empty slot's flag
> and then a present one — followed by one fully framed object.

`nobjects` is the last occupied index plus one, not the number of objects present,
so it counts trailing-free but not interior-empty slots
(`root/core/cont/src/TClonesArray.cxx:886`, `root/core/cont/inc/TObjArray.h:58-60`).

## 13. Reading

At a `TStreamerSTL` or `TStreamerSTLstring` element:

1. Read a byte count and a `u16` version word.
2. If `fSTLtype` is 365, read a counted string. Done; seek to the byte count's
   end.
3. **Repeat steps 4 and 5 `max(fArrayLength, 1)` times.** One frame holds
   `fArrayLength` complete collections when the member is declared
   `std::vector<T> m[N]`, and nothing but `fArrayLength` says so (§11.1). A reader
   that does this once stops short of the byte count.
4. If bit 14 of the version word is clear:
    1. Read `count:i32`.
    2. Read `count` elements as §3, dispatching on `fTypeName`, not on `fCtype`.
5. If bit 14 is set:
    1. Read a bare `Version_t` for the value class; if it is 0 or less, read a
       `u32` checksum and use it to select the value class's streamer info.
    2. Read `count:i32`.
    3. For each member of the value class, in order, read `count` values as a
       column, framed per §4.1.
6. Seek to the end the byte count implies, whatever was consumed.

The value class is `fTypeName`'s first template argument for a sequence, and
`pair<K,V>` for an associative container — except for an element named `This`,
where it is the bracketed type in the title, read as a `vector` (§11.2). If it is a `pair` and the file has no
info for it, synthesise one from the two arguments (§8). If it is anything else
and the file has no info for it, the collection is not readable (§9).

## 14. Invariants

1. Every `TStreamerSTL` element's `fSTLtype`, modulo `kOffsetP`, is in
   `[0, 14]`, or is 300 or 365.
2. A `TStreamerSTLstring` element has `fSTLtype` and `fCtype` both 365.
3. A collection member's version word, with bit 14 masked off, is 10 in a file
   written by 6.40.04, and never above `TStreamerInfo`'s current class version.
4. A member-wise collection's value class is not `TString`, `std::string`, a
   collection, or a pointer — the four cases `CanSplit` refuses.
5. Applying §13 to a collection member consumes exactly the bytes its byte count
   delimits.
6. Every class named as the value class of a member-wise collection has a
   streamer info in the same file, unless it is a `pair` — for which the file may
   have one or not (§8).

7. A `TClonesArray`'s `"<class>;<version>"` string names a class that has a
   streamer info in the same file, at that class version.
8. Parsing a `TClonesArray` body according to `fBits` bit 12 — bit 14 at class
   version **3** exactly, since at version 2 and below no `TObject` base is
   streamed and there is no `fBits` in the record at all
   (`root/core/cont/src/TClonesArray.cxx:756-760`) — consumes exactly the bytes its
   byte count delimits. Like
   [References §8](References.md#8-invariants) invariant 1, this is checked
   through consumption rather than directly: reading the wrong encoding
   desynchronises and the byte count catches it.
9. A member-wise collection whose count is 0, on a frame above version 6,
   occupies exactly the bytes of its two version words, its checksum if it has
   one, and the count — and nothing more (§4.3).
10. A `TStreamerSTL`'s `fSTLtype`, less `kOffsetP` where present, names the same
    container as the head of its `fTypeName`. It is checked on the value a reader
    **ends up with**, so it fails on a reader that skips §1's `set`/`multimap`
    repair — which is how the omission in `tools/rootfile.py` was found. Holds on
    all 1368 `TStreamerSTL` elements of `data/` and both corpora; three of them
    need the repair to pass. **It does not apply to an element named `This`
    whose `fTypeName` is no container name**, since its `fSTLtype` comes from the
    class's proxy (§11.2).
11. An element named `This` is the only element of its streamer info, and its
    `fTypeName` is the name of the class that info describes (§11.2).

Invariant 6 is the one that fails on a file ROOT wrote (§9), which is why it is
reported rather than assumed.

## 15. Errata

Against `root/io/doc/TFile/*.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | — | **Nothing in the shipped documentation describes STL streaming at all.** "STL" does not occur in `README.md`. No byte count, no version word, no `kStreamedMemberWise`, no transposition. This is the single largest gap in ROOT's documentation of its own format |
| 2 | `streamerinfo.md`: "`TStreamerSTL`: For an STL container (not yet used??)" | Used for every STL member of every class since long before 6.x (§1) |
| 3 | `streamerinfo.md`: the class is named `TStreamerSTLString` | It is `TStreamerSTLstring`, and that spelling is what appears in the class tag (§10) |
| 4 | `streamerinfo.md`: "`fSTLtype` … 5:set, 6:multimap, 7:multiset" | 5 is multimap and 6 is set. The order was standardised at element version 4 and ROOT still repairs old files (§1) |
| 5 | `streamerinfo.md`: the `fSTLtype` list stops at 7 | Missing 8 to 14, and missing the `+40` a pointer member adds (§1) |
| 6 | `streamerinfo.md`: "`fCtype` = same values as `fType`, plus 365" | It is 61 for a collection of any class, `TObject`-derived or not; 63 for pointers; 0 for `bitset`. And it does not determine the layout (§7) |
| 7 | `tclonesarray.md`: describes the non-bypass body as the objects streamed sequentially | Omits the one-byte presence flag before each object, including for empty slots (§12) |
| 8 | `tclonesarray.md`: "`kBypassStreamer` (0x1000)" | True for class version 4 only; in version 3 it was `0x4000` (§12) |
| 9 | `tclonesarray.md`: version, `TObject` and `fName` are shown unconditionally | `TObject` is present only above version 2 and `fName` only above version 1 (§12) |
| 10 | — | Nothing states that a map is written two different ways, or that its value class is `pair<K,V>` — whose streamer info the file may or may not carry, unpredictably (§8) |
| 11 | — | Nothing states that a `std::string` member's version word is `TStreamerInfo`'s 10 and not `std::string`'s 2 (§10) |
| 12 | — | Nothing states that a pair's checksum need not identify it. Three distinct pairs share one in `serialization/pairs`, so a reader that looks a pair up by checksum rather than by name decodes two of them as the wrong type (§8.2) |
| 13 | — | Nothing states that an empty member-wise collection writes no columns at all, nor that this changed at `TStreamerInfo` version 6 (§4.3) |
| 14 | — | Nothing states that at `TClonesArray` version 3 ROOT tests the bypass bit **before** `TObject::Streamer` overwrites `fBits`, so it tests its own in-memory bit rather than the file's (`root/core/cont/src/TClonesArray.cxx:756-761`). A reader MUST use the value in the record; ROOT's own behaviour at that version cannot be used as the reference (§12) |

## 16. Reference files

| Case | Exercises |
|---|---|
| `serialization/collections` | Object-wise and member-wise side by side; `vector<int>`, `vector<bool>`, `set<int>`, `vector<Hit>`, `vector<vector<int>>`, `vector<string>`, `map<int,int>`, `std::string`, and the missing `pair<int,int>` info |
| `serialization/clones-array` | Both `TClonesArray` encodings, an empty slot, and a versioned element class from a compiled dictionary |
| `serialization/pairs` | The six shapes a `pair<K,V>` member takes (§8.1), the empty member-wise collection (§4.3), and three distinct pairs sharing one checksum (§8.2) |
| `serialization/collection-forms` | `std::array` of a scalar and of a class (§11), a fixed array of collections (§11.1), and a member-wise collection whose value class has a `ClassDef` (§4) |
| `serialization/pointer-collection` | Pointer content (§3.1): the three frames in a row, and all three object-slot forms — a class name, a null pointer, and a class back-reference — in one collection |

Two more are covered from the `TTree` side: `ttree/split-bitset` has a
`std::bitset` as a member of a split branch, which is an ordinary object-wise
collection and confirms §11's byte-per-bit layout and its bit order against real
bytes, and `ttree/split-ptr-collection` has a `std::vector<PHit*>` — a collection
of pointers, which `serialization/pairs` also reaches through a map value.

No fixture covers `TClonesArray` at class version 3 or the pre-version-8 layouts;
both need a legacy ROOT (`PLAN.md` §9.1).
