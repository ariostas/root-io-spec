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

> **`set` is 6 and `multimap` is 5.** They were the other way round for years,
> and `TStreamerSTL::Streamer` still repairs old files by re-reading `fTypeName`
> (`root/core/meta/src/TStreamerElement.cxx:2112-2122`). The table in
> `root/io/doc/TFile/streamerinfo.md` records the old, wrong order.

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
byteCount:u32   version:u16
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

## 3. Object-wise

```
byteCount  version(0x000A)   count:i32   <each element, in full>
```

`root/io/io/src/TGenCollectionStreamer.cxx:1429-1434`. The count is a plain
`Int_t`. How an element is written depends on what it is:

| Element | On disk | Cited |
|---|---|---|
| fundamental or enum | its natural width, back to back | `root/io/io/src/TGenCollectionStreamer.cxx:891` |
| a class | a **full framed object**: byte count, version, and a checksum if foreign | `root/io/io/src/TGenCollectionStreamer.cxx:976` |
| `std::string` | a bare counted string | `root/io/io/src/TGenCollectionStreamer.cxx:979` |
| pointer to a class | a full object slot, class record and all | `root/io/io/src/TGenCollectionStreamer.cxx:982` |
| a nested collection | a bare `count` and its elements — **no byte count, no version word** | §5 |
| a map entry | key then value, **interleaved** | `root/io/io/src/TGenCollectionStreamer.cxx:1024-1110` |

> Demonstrated by `serialization/collections`: `fInts` is `count 3` then three
> bare `i32`; `fWords` is `count 2` then `02 "pq" 02 "rs"`.

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
> — both `x` values, then both `y` values.

### 4.1 The columns are not uniformly framed

| Member kind | Framing inside the column |
|---|---|
| fundamental | none: the values are concatenated |
| a base class | none: the base's streamer runs once per element, back to back |
| an object member (61, 62) | **each element gets its own** byte count and version word |
| a collection member (500) | **one** byte count and version word for the *whole column* |

The last row is the surprising one and it follows from how the action is built:
a collection column falls through to `GenericWrite`, which calls the ordinary
member loop once with an array of `n` objects
(`root/io/io/src/TStreamerInfoActions.cxx:2214-2228`), and the frame is written
once inside that single call.

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

## 5. Which mode is used

Member-wise is chosen only if **all six** of these hold
(`root/io/io/src/TStreamerInfoActions.cxx:1183-1188`):

1. the buffer can handle it — true for a file, false for `TMessage` and for the
   text buffers (`root/core/base/inc/TBuffer.h:76`);
2. the collection has a proxy **and** a non-null value *class*;
3. the global `TVirtualStreamerInfo::GetStreamMemberWise()`, default true
   (`root/core/meta/src/TVirtualStreamerInfo.cxx:30`);
4. `TClass::CanSplit()` on the value class;
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

> **ROOT does not write a streamer info for `pair<K,V>`.** The member-wise frame
> names the pair's checksum, and the file contains no entry with that checksum. A
> reader MUST synthesise the layout — `first` then `second`, from the two
> template arguments — rather than look it up.
>
> Demonstrated by `serialization/collections`: `fMap`'s frame at 477 names
> checksum `0x95f86d56` and that record's `TList` contains only `Coll` and `Hit`.

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
array: the element is a `TStreamerBasicType` or `TStreamerObject` with
`kOffsetL` added, and the bytes are those of
[Element types §3](ElementTypes.md#3-koffsetl-t-20-t-fixed-size-array) — no
byte count, no version word, no count.

**Nested collections** are always object-wise (§5), and the inner ones are bare:
a count and its elements, with no framing of their own, at every depth.

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
3. Otherwise, if bit 14 of the version word is clear:
    1. Read `count:i32`.
    2. Read `count` elements as §3, dispatching on `fTypeName`, not on `fCtype`.
4. If bit 14 is set:
    1. Read a bare `Version_t` for the value class; if it is 0 or less, read a
       `u32` checksum and use it to select the value class's streamer info.
    2. Read `count:i32`.
    3. For each member of the value class, in order, read `count` values as a
       column, framed per §4.1.
5. Seek to the end the byte count implies, whatever was consumed.

The value class is `fTypeName`'s first template argument for a sequence, and
`pair<K,V>` for an associative container. If it is a `pair` and the file has no
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
   streamer info in the same file, unless it is a `pair`.

7. A `TClonesArray`'s `"<class>;<version>"` string names a class that has a
   streamer info in the same file, at that class version.
8. Parsing a `TClonesArray` body according to `fBits` bit 12 — bit 14 below class
   version 4 — consumes exactly the bytes its byte count delimits. Like
   [References §8](References.md#8-invariants) invariant 1, this is checked
   through consumption rather than directly: reading the wrong encoding
   desynchronises and the byte count catches it.

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
| 10 | — | Nothing states that a map is written two different ways, or that its value class is `pair<K,V>` whose streamer info is never in the file (§8) |
| 11 | — | Nothing states that a `std::string` member's version word is `TStreamerInfo`'s 10 and not `std::string`'s 2 (§10) |

## 16. Reference files

| Case | Exercises |
|---|---|
| `serialization/collections` | Object-wise and member-wise side by side; `vector<int>`, `vector<bool>`, `set<int>`, `vector<Hit>`, `vector<vector<int>>`, `vector<string>`, `map<int,int>`, `std::string`, and the missing `pair<int,int>` info |
| `serialization/clones-array` | Both `TClonesArray` encodings, an empty slot, and a versioned element class from a compiled dictionary |

No fixture covers `std::bitset`, `std::array`, a collection of pointers, a fixed
array of collections, a member-wise collection whose value class has a `ClassDef`
(and so a plain version word rather than a checksum), `TClonesArray` at class
version 3, or the pre-version-8 layouts.

The `ClassDef` case is no longer blocked: `serialization/clones-array` shows how a
case compiles a dictionary (`gen/common/README.md`), and the same mechanism would
produce a versioned value class for a `std::vector`.
