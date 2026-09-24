# Reading entries

The end-to-end procedure: entry number → basket → byte range → values, for an
unsplit branch and for every kind of split one.

Prerequisites: [TBranch](TBranch.md), [TBasket](TBasket.md), [TLeaf](TLeaf.md),
[TBranchElement](TBranchElement.md), [Splitting](Splitting.md).

The documents before this one describe where the bytes are; this one describes
what they mean. Locating an entry is the same arithmetic for every branch in every
file. Interpreting it depends on four fields of the branch and on a streamer
element the branch only points at.

## 1. Locating the entry

This is the procedure of [TBranch §10](TBranch.md#10-reading), restated because
the rest of this document assumes it. Given a branch and an entry number:

1. Find the basket index *i* with `fBasketEntry[i] <= entry < fBasketEntry[i+1]`.
2. Read that basket ([TBasket](TBasket.md)). **It need not be a record**: when
   slot *i* of `fBaskets` holds a basket, that basket is embedded in the `TTree`
   record itself
   ([TBranch §5](TBranch.md#5-fbaskets-is-written-and-is-usually-empty)), and its
   raw block takes the place of the record below: every offset in step 3 is
   relative to the block start. ROOT takes the slot first and consults
   `fBasketSeek[i]` only when the slot is empty
   (`root/tree/tree/src/TBranch.cxx:1234-1236`). `fBasketSeek[i]` is then
   usually 0, but not always: before 3.10/02 the `TBranchElement` constructors
   never assigned it (`v3-04-02:tree/src/TBranchElement.cxx:146-151`; fixed at
   `v3-10-02:tree/src/TBranchElement.cxx:151-155`), and `digi.root` in
   `root/roottest/` has uninitialised heap bytes there. A reader that can only
   fetch a basket by file offset cannot read such an entry, and in a file
   written by `TDirectory::WriteTObject` every entry is of this kind.
3. The entry's byte range within the basket payload is:

| | start | end |
|---|---|---|
| the basket has an entry-offset array, and *j* is not the last entry | `fEntryOffset[j]` | `fEntryOffset[j+1]` |
| the basket has an entry-offset array, and *j* = `fNevBuf - 1` | `fEntryOffset[j]` | **`fLast`** |
| it does not | `fKeylen + j × fNevBufSize` | start + `fNevBufSize` |

where *j* = `entry − fBasketEntry[i]`
(`root/tree/tree/src/TBranch.cxx:1738-1748`). The number of bytes the read then
consumes is exactly the width of that range
(`root/tree/tree/src/TBranch.cxx:1751-1752`).

**The last entry's end is `fLast`, not an array element.** The array has one slot
more than there are entries, and that extra slot is never written: `TBasket::Update`
stores `fEntryOffset[fNevBuf] = offset` and *then* increments `fNevBuf`
(`root/tree/tree/src/TBasket.cxx:1190-1203`), so after the final entry the slot at
`fNevBuf` still holds whatever it held before, which is 0 in a fresh buffer. A
reader taking `fEntryOffset[j+1]` for the last entry gets an end of 0 and a
negative width. [TBasket §5.1](TBasket.md#51-three-things-to-get-right) and
step 8 of [TBasket §8](TBasket.md#8-reading) say the same.

Which of the two cases applies is decided when the branch is created. For a
`TBranchElement`, `fEntryOffsetLen` is 0 (no offset array) unless `fType` is
non-zero, or `fStreamerType` is `kBase` or below, `kCharStar`, `kBits`, or above
`kFloat16` (`root/tree/tree/src/TBranchElement.cxx:361-363`, where `btype` is the
branch's `fType`). A top-level-object column of `Int_t` (`fType` 0) therefore has
no offset array, while the same `Int_t` as a member of a split collection
(`fType` 31 or 41) has one, because each entry holds a different number of
values; a column of `TString` has one either way, and `fBits` has one because a
referenced `TObject` writes two extra bytes.

> Demonstrated by `ttree/split-nested`: `fDet.fHits.fId`, an `Int_t` at `fType`
> 41, has `fNevBufSize` 1000 and entry offsets `78, 86, 86`.

## 2. Which branches hold data at all

A `TBranchElement` with sub-branches reads its own basket only when `fType` is 3
or 4 (`root/tree/tree/src/TBranchElement.cxx:2749-2752`). A `TBranchSTL` has
sub-branches too and also reads its own basket first, one `TIndArray` entry per
entry (`root/tree/tree/src/TBranchSTL.cxx:381`, then the element branches at
`:453`; [Splitting §7](Splitting.md#7-reading)). Every other interior node
(`fType` 1, `fType` 2, and `fType` 0 with `fID` −2) consumes **zero bytes** and
exists only to be descended through. ROOT's own test for a split node is at
`root/tree/tree/src/TBranchElement.cxx:5692`.

An `fType` 0, `fID` −2 branch with **no** sub-branches, the split node of a class
whose streamer info lists no element, is not a split node to ROOT, whose test requires a non-empty `fBranches`
(the same line). It reads its own baskets, and every entry in them is zero bytes
([Splitting §1.1](Splitting.md#11-interior-nodes-hold-nothing-and-say-so-twice)).
A reader may treat it as holding no data. So may it treat a split parent's
`fEntryNumber`, which fast cloning sets to `fEntries` although the branch holds
nothing ([TBranch §7](TBranch.md#7-the-entry-counters)).

## 3. What an entry contains

There are six shapes; the first four are short enough to give in full.

### 3.1 A count branch: one `Int_t` and nothing else

`fType` 3 and 4. The entry is a single four-byte big-endian `Int_t`, with no byte
count, no version word and no other framing
(`root/tree/tree/src/TBranchElement.cxx:4339` for `fType` 4,
`root/tree/tree/src/TBranchElement.cxx:4527` for `fType` 3).

From `ttree/split-nested`, whose three entries hold collections of 2, 0 and 1:

```
fDet.fHits   entry 0   00 00 00 02
             entry 1   00 00 00 00
             entry 2   00 00 00 01
```

### 3.2 A member of a split container: a bare packed column

`fType` 31 and 41. The entry is *n* values of the member's type, back to back,
with no count and no framing. *n* is not in this entry; it is the count branch's
value for the same entry (§4).

Same file, the two members of that collection:

```
fDet.fHits.fId   entry 0   00 00 00 64 00 00 00 65      100, 101
                 entry 1   (zero bytes)
                 entry 2   00 00 01 2c                  300

fDet.fHits.fE    entry 0   00 00 00 00 3f 00 00 00      0.0f, 0.5f
                 entry 1   (zero bytes)
                 entry 2   00 00 00 00                  0.0f
```

**An empty collection gives an empty entry**, not a zero or a marker. Entry 1
occupies no bytes, so a variable-length column needs the offset array of §1; its
entries cannot be located by multiplication.

That holds for members like these, whose column is the values and nothing else.
A member whose column has a header of its own (§5.3), such as a `std::vector` or
a `std::string`, depends on the release **and on `fType`**:

| Writer | `fType` 41, *n* = 0 | `fType` 31, *n* = 0 |
|---|---|---|
| before 5.32/00 | nothing | the header |
| 5.32/00 and later | the header, with no values after it | the header |

ROOT's reader for `fType` 41 returns before touching the buffer when *n* is 0
(`root/tree/tree/src/TBranchElement.cxx:4493-4496`), so it reads both forms. The
`fType` 31 reader has no such test and reads the header
(`root/tree/tree/src/TBranchElement.cxx:4566-4581`). Before 5.32/00 the
`fType` 41 writer went through `WriteBufferSTL`, which returned at once for an
empty collection (`v5-30-00:tree/tree/src/TBranchElement.cxx:1418`,
`v5-30-00:io/io/src/TStreamerInfoWriteBuffer.cxx:867`); root commit
`7de5e0a080f` (2011, first in 5.32/00) moved it to the write actions, which
write the column's header whatever *n* is
(`root/io/io/src/TStreamerInfoWriteBuffer.cxx:613-621`). For a `vector<float>`
member, ROOT 6.40.04 writes the six bytes `40 00 00 02 00 0a` (byte count 2, then
`TStreamerInfo`'s version 10) for each empty entry, and the same six for a
`std::string` member and for a `vector<float>` member of a `TClonesArray`'s class
(`fType` 31). A member-wise `vector<Sub>` member writes twelve: the frame with
`40 0a`, then `Sub`'s version word 0 and its checksum (§5.3). The cell for
`fType` 31 before 5.32/00 is from the source only: `WriteBufferClones` has no
early return (`v5-10-00:meta/src/TStreamerInfoWriteBuffer.cxx:642-648`), and
the `kSTL` case writes its header before its loop in both modes
(`v5-10-00:meta/src/TStreamerInfoWriteBuffer.cxx:461` and `:480`). No file of that age
with such a column has been examined.

`S_1_104_qgsjet_100_1.KGrec.root` in `root/roottest/` (5.10/00) has the old form:
the first 19 entries of `event.fSDEvent.fStations` are empty, and so are the
first 19 of its `vector<UShort_t>` member `fHighGainTrace1`. Entry 19 holds 26
stations, each with an empty trace, and occupies 110 bytes: the header and 26
counts of 0. A reader that decodes a header for an empty entry reads entry 19's
instead, and the byte count then says it stopped 104 bytes short. The same holds
for 350 `vector` and `string` members in `small_aod.pool.root` (5.22/00).

A column of `TObject::fBits` values (`kBits`, 15) is not fixed-width either. Each
value is 4 bytes, or 6 when it has `kIsReferenced` set and carries a `pidf`
([Element types §2.3](../02-serialization/ElementTypes.md#23-kbits-15)), so one
entry can mix both sizes. `mksm.root` in `root/roottest/` (4.00/08) has such
columns, because its file also has `TRef` branches: every `pv.fBits` entry is 6
bytes, and the `fType` 41 column `jet.fBits` mixes 4-byte and 6-byte values.

### 3.3 An unsplit object: no framing of its own, but its members have theirs

`fType` 0 with `fID` −1. The entry is the members' own serialisations,
concatenated. There is **no byte count and no version word for the branch's
class** (`root/tree/tree/src/TBranchElement.cxx:4619`, which applies the member
actions directly to the object).

This is easy to get wrong, because an entry often *starts* with something that
looks like a class header. From `ttree/split-unsplit`, whose `un` branch holds a
whole `UEv`, a class deriving from `UBase { Int_t fB; }` and adding `Int_t fI`
and `Double_t fD`:

```
40 00 00 06  00 01  00 00 00 0a   00 00 00 14   40 3e 00 00 00 00 00 00
└─ UBase's byte count and version, then fB ─┘   fI            fD
```

The leading `40 00 00 06` is a byte count of 6, covering the version word and
`fB` only. It belongs to the `UBase` base-class element, not to `UEv`. If `UEv`
had a header of its own the count would cover all 22 bytes. A reader that treats
the first four bytes of an unsplit entry as the object's byte count will be
right for some classes and wrong for others, with no way to tell which.

### 3.4 A counted array: a flag byte, then *n* values

`fType` ≤ 2 with `fBranchCount` set: the `Int_t n; Float_t *x; //[n]` shape.
The element type is `kOffsetP + T`, and its serialisation is **one leading byte
followed by *n* values of T**.

From `ttree/split-counter`, whose counts are 1, 3 and 2:

```
fN   entry 0   00 00 00 01              (no offset array: fNevBufSize is 4)
     entry 1   00 00 00 03
     entry 2   00 00 00 02

fX   entry 0   01 42 c8 00 00                             100.0f
     entry 1   01 43 48 00 00 43 49 00 00 43 4a 00 00     200, 201, 202
     entry 2   01 43 96 00 00 43 96 80 00                 300, 301
```

The counter branch `fN` is read first and its value is taken from memory, not
from `fX`'s entry (`root/tree/tree/src/TBranchElement.cxx:4649`).

### 3.5 A custom streamer

`fType` < 0. The entry is whatever the class's own `Streamer` writes
(`root/tree/tree/src/TBranchElement.cxx:4712`). By ROOT's convention it begins
with a four-byte byte count with bit 30 set and a two-byte version, but this
specification cannot say more: `fType` −1 means that the class does not follow
the streamer-info layout. No fixture covers it; see §10.

### 3.6 A `std::bitset`: an ordinary collection, or nothing at all

A `std::bitset<N>` member reaches a split branch as a `TStreamerSTL` with
`fSTLtype` 8 and `fCtype` 0, and its entry is the object-wise collection
[Collections §11](../02-serialization/Collections.md#11-other-containers)
describes: a byte count and version word, an `Int_t` count of N, then N
single-byte values, **bit 0 first**. The bits are not packed and the count is
written although the width is already in the type name. From
`ttree/split-bitset`, whose member is a `bitset<16>` holding `0xA5A5`:

```
40 00 00 16  00 0a  00 00 00 10  01 00 01 00 00 01 00 01 01 00 01 00 00 01 00 01
byte count   ver    count 16     sixteen bools, bit 0 first
```

Sixteen bits cost twenty-six bytes.

**Before ROOT 6.08/06 the entry is empty.** The collection proxy did not work in
this path, so ROOT created the branch and wrote no bytes into it: every entry is
zero-length, and the basket's `fLast` equals its `fKeylen`, so there is no
payload at all. The fix is ROOT-8574, root commit `2caaf15c2f0` of 2017-02-24,
released in 6.08/06 and backported to 5.34/38. `uproot-mc10events.root` in
`gen/foreign/` was written by 6.08/04, one patch release before the fix, and has
eleven such branches, in both the scalar and the `fType` 31 column form, all of
them empty.

A reader has to accept both, and **nothing on the branch distinguishes them**:
`fStreamerType`, `fEntryOffsetLen` and the leaf are identical in the two files.
Only the entry's own length does.

## 4. Where the count comes from

The count comes from one of three different places.

| Branch | Count source | Citation |
|---|---|---|
| `fType` 3, 4 | the entry itself, as §3.1 | `root/tree/tree/src/TBranchElement.cxx:4339` |
| `fType` 31 | the count branch's decoded value | `root/tree/tree/src/TBranchElement.cxx:4566` |
| `fType` 41 | the same | `root/tree/tree/src/TBranchElement.cxx:4493` |
| `fType` ≤ 2 with `fBranchCount` | the counter branch's decoded value | `root/tree/tree/src/TBranchElement.cxx:4649` |
| `fType` 0 whose element is `kStreamLoop` (501 or 521) | the counter branch's decoded value, the branch found by name (§4.1) | `root/tree/tree/src/TBranchElement.cxx:442-457` |

In every case but the first, the counter's branch
([TBranchElement §6](TBranchElement.md#6-fbranchcount-is-a-back-reference-and-fbranchcount2-is-never-set))
must be read for the same entry **before** this one, and a reader has to order
its work accordingly: a member column cannot be decoded in isolation.

The last row needs no `fBranchCount` in ROOT. The branch applies the element's
action to the object (`root/tree/tree/src/TBranchElement.cxx:4619`), and the
loop reads its count from the object
(`root/io/io/src/TStreamerInfoActions.cxx:1724-1725`), where the counter branch
has already stored it for this entry. `Init` has set `fBranchCount` on such a
branch only since root commit `6d10ac6c209` (2010-07-29, first in 5.27/06), so
in an older file it is -1 and the counter can be found only by name.

> Byte-verified on `root/roottest/root/tree/addresses/memleak.root` (ROOT
> 5.17/06). Branch `fPnts`, a `TArrayD *fPnts; //[fNrSrcs]`, has `fType` 0 and
> `fBranchCount` -1, and its counter is the sibling `fNrSrcs`, whose entries 0
> and 1 are 4 bytes each. With that count, `fPnts`'s entries 0 and 1, 16218
> bytes each, decode to exactly their length. `varyingArray_51508.root` (5.15/08)
> has the same shape in `A.fTable`, whose counter `A.fN` is 3.

### 4.1 Resolve the counter by name, not by `fBranchCount`

> **`fBranchCount` can name the wrong branch, and a reader that follows it loses
> data silently.** Resolve the counter by name among the branch's own siblings:
> take this branch's name up to and including its last `.`, append the count
> member's name (the name the element records as its counter and the leaf has in
> its title, as in `fAllBits[fNbytes]`), and use the sibling that matches.

ROOT's writer intends the same: it builds that name and calls `TTree::GetBranch`
on it (`root/tree/tree/src/TBranchElement.cxx:432-438`). `GetBranch`, however,
searches the **whole tree** and returns the first branch with that name. When a
tree holds two split objects of one class whose sub-branches have no parent
prefix, both objects' members get a pointer to the **first** object's counter, and
the read path uses it unchanged (`root/tree/tree/src/TBranchElement.cxx:4649`).

> **Observed.** `alice_ESDs.root` (ROOT 5.16/00) splits an `AliESDVertex` twice, as
> `SPDVertex` and `PrimaryVertex`. Both objects' sub-branches are named plainly
> `fNIndices` and `fIndices`, so both `fIndices` branches record the *same*
> `fBranchCount`, the one under `SPDVertex`, whose value is 0 for all 20 entries.
> `PrimaryVertex`'s own `fNIndices` holds 18, 22, 6, 13, … and its `fIndices`
> entries are 37, 45, 13 and 27 bytes, which is `1 + n × 2` for those counts. A
> reader following the recorded pointer reads no indices at all and gets no
> warning; ROOT is such a reader. See erratum 6.

The entry's byte range catches this: for a fixed-width *T* the length is
`1 + n × sizeof(T)`, so a count that disagrees with the span came from the wrong
branch.

### 4.2 A container's member needs one count per object

For `fType` 31 and 41 the element may itself be a counted array, such as
`UChar_t *x; //[n]` inside the class the container holds. Two counts are then
needed, and they come from different places:

- **how many objects** the entry has: the count branch, as in the table above;
- **how long each object's array is**: the sibling branch holding the count
  member, whose column for this entry has one value per object.

For each object, the column then has the ordinary
[§3.4](#34-a-counted-array-a-flag-byte-then-n-values) shape: one flag byte, then
that object's values:

```
Tracks                          entry 0   00 00 00 58          88 objects
Tracks.fTPCClusterMap.fNbytes   entry 0   352 bytes = 88 x 4, every value 20
Tracks.fTPCClusterMap.fAllBits  entry 0   1848 bytes = 88 x (1 + 20)
                                          01 ff ff ... 7f  01 ff ff ... 7f  ...
```

This is from `alice_ESDs.root`. Nothing in the file points from `fAllBits` to
`fNbytes`: `fBranchCount` on an `fType` 31 branch names the **master** branch, the
clones count. The per-object counter can be found only through the name in the
element and the leaf title, so §4.1's rule is the only one that works here.

## 5. What one member's bytes look like

For everything but §3.1 and §3.5, the bytes are produced by the streamer
elements the branch selects, and the encodings are those
[ElementTypes](../02-serialization/ElementTypes.md) specifies. Three
things are specific to trees.

### 5.1 `fID` selects the elements

`fID` ≥ 0 selects the single element with that index
(`root/io/io/src/TStreamerInfoActions.cxx:5503`); `fID` < 0 selects every element
of the class (`root/io/io/src/TStreamerInfoActions.cxx:5486-5495`). The class is
`fClassName`, resolved by `fClassVersion` or `fCheckSum`
([TBranchElement §5](TBranchElement.md#5-fclassname-names-the-class-fid-indexes)).

**The streamer info is chosen from the branch's fields, never from bytes in the
entry.** The entry has nothing to identify it by, which is why `fClassVersion`
and `fCheckSum` are on the branch.

### 5.2 The width can depend on a title the branch does not have

A `Double32_t` or `Float16_t` member's width comes from the **element's** title,
parsed as in
[ElementTypes §5](../02-serialization/ElementTypes.md#5-kdouble32-and-kfloat16).
Nothing on the branch records it: `ttree/split-double32` has five such members
with two distinct `fStreamerType` values, `TLeafElement` leaves that differ only
by that type, and identical `fEntryOffsetLen`, whose entries are 4, 4, 4, 4 and 3
bytes. A reader that sizes a member by its `fStreamerType` as an in-memory type,
8 bytes for `Double32_t` and 4 for `Float16_t`, gets four of the case's six
widths wrong: `fPlain`, `fRange`, `fBits` and `fHBits`. One that uses the leaf's
`fLenType`, which is 4 for `Double32_t` and 2 for `Float16_t` whatever the title
(`root/tree/tree/src/TLeafElement.cxx:69-76`), gets two wrong, `fHalf` and
`fHBits`. Applying ElementTypes §5 to an empty title, the most the branch
supports, gets only `fHalf`'s width wrong, but decodes `fRange` and `fBits` as
plain floats. The sixth member, an `Int_t`, is right every way.

### 5.3 A per-element header is sometimes per *entry*

For most element types, a column of *n* values is the scalar encoding repeated
*n* times. Two families are not:

- `kStreamer` (500): one version word is read for the whole column and one byte
  count checked at the end, outside the loop
  (`root/io/io/src/TStreamerInfoActions.cxx:2671-2675`).
- `kSTL` (300) and `kSTLstring` (365): the version is read once, outside the
  per-element loop (`root/io/io/src/TStreamerInfoReadBuffer.cxx:1251-1256`).
  So is `kSTLp` (71), a pointer to a collection, whose bytes are the
  collection's with no pointer tag
  (`root/io/io/src/TStreamerInfoReadBuffer.cxx:1147-1152`,
  [Collections §11.3](../02-serialization/Collections.md#113-a-pointer-to-a-collection-is-written-as-the-collection)).

For those two, an entry holding *n* values has **one** header, not *n*. A reader
that frames each element separately desynchronises on the second.

`kStreamLoop` (501), an `int n; T *p; //[n]` member whose count is another member
of the same class, is framed the same way: one byte count for the whole column.
Its *contents* are harder, because in a split tree the counting member is a
column on a sibling branch and the lengths differ per element, but the byte count
gives the column's extent without them. Byte-verified on
`uproot-issue433-splitlevel4.root`.

A column of `std::string` (`fSTLtype` 365) is the shared frame followed by *n*
bare counted strings, with no count of their own: the collection *is* the
string. Byte-verified on `uproot-issue-214.root`, where a 62-byte entry is the
six-byte header and 56 empty strings.

The version word of an STL member also carries a flag: bit 14,
`kStreamedMemberWise` (`root/io/io/inc/TBufferFile.h:70`), which selects the
member-wise body of [Collections](../02-serialization/Collections.md) and adds a
value-class version word after it. In a column that version word is also read
once, outside the loop (`root/io/io/src/TStreamerInfoReadBuffer.cxx:1271-1274`).
A column of *n* member-wise collections is therefore the shared frame, one
value-class version, then *n* times an `Int_t` count and that collection's
member-wise body.

A fixed array, `kOffsetL` added to any of these codes, multiplies the collections
under the same header: each value holds `fArrayLength` of them, the objects in
the outer loop and the array in the inner one
(`root/io/io/src/TStreamerInfoReadBuffer.cxx:1183-1187`). This applies to a
single member too, where *n* is 1: the branch `fArr[2]` of a `vector<T> fArr[2]`
member has one frame, one value-class version and two counts per entry
([Collections §11.1](../02-serialization/Collections.md#111-a-fixed-array-of-collections-shares-one-frame)).

## 6. `fMaximum` is a read-time bound, not a statistic

On a count branch the value just read is compared against `fMaximum`, and a count
that is negative or larger is **rejected**
(`root/tree/tree/src/TBranchElement.cxx:4340-4348`). ROOT then substitutes 0.

The two sub-cases consume different numbers of bytes:

- If the entry is zero-length (the `IsMissingCollection` test), the four bytes
  are rewound and the entry consumes nothing
  (`root/tree/tree/src/TBranchElement.cxx:4343`).
- Otherwise an error is printed and the four bytes stay consumed
  (`root/tree/tree/src/TBranchElement.cxx:4345-4346`).

A reader that ignores `fMaximum` will accept counts ROOT refuses, and will then
read a column ROOT would have left empty.

## 7. Reading

Normative, for one entry of one branch.

1. If the branch has sub-branches, is not a `TBranchSTL`, and `fType` is not 3
   or 4, it holds nothing: read its children and stop (§2).
2. If `fBranchCount` is set, or the element is a `kStreamLoop`, read the
   counter's branch's entry first and keep its value as *n* (§4).
3. Locate this entry's byte range (§1).
4. Select the read shape from `fType`, `fID`, `fSplitLevel` and `fStreamerType`
   ([TBranchElement §8](TBranchElement.md#8-the-read-procedure-is-selected-by-four-fields-not-one)).
5. Decode:
   - `fType` 3 or 4: one `Int_t`; check it against `fMaximum` (§6).
   - `fType` 31 or 41: *n* values of the selected element's type (§3.2, §5.3).
     For `fType` 41 with *n* 0 the byte range may be empty even where the
     column has a header, if the writer predates 5.32/00; then there is
     nothing to read (§3.2).
   - `fType` ≤ 2 with `fBranchCount`: a flag byte then *n* values (§3.4).
   - `fType` 0 with `fID` −1: every element of `fClassName`'s streamer info, in
     order, with no class-level framing (§3.3).
   - `fType` < 0: the class's own streamer (§3.5).
   - `fType` 1 with no sub-branches, the empty base class of
     [TBranchElement §4](TBranchElement.md#4-two-ftype-values-have-no-leaf-and-two-reach-theirs-only-by-reference):
     one framed object of that base class, which the single element `fID`
     selects as below.
   - a `std::bitset` member whose byte range is empty: nothing (§3.6).
   - otherwise: the single element `fID` selects.
6. The bytes consumed must equal the byte range from step 3. This equality is
   the check to implement; it is
   [TLeaf invariant 7](TLeaf.md#10-invariants) generalised to split branches.

## 8. Invariants

1. For a branch with `fType` 3 or 4, every entry is exactly four bytes.
2. For a branch with `fType` 1 or 2, or `fType` 0 with `fID` −2, there are no
   baskets and no entries, except on the empty-base-class branch of
   [TBranchElement §4](TBranchElement.md#4-two-ftype-values-have-no-leaf-and-two-reach-theirs-only-by-reference),
   an `fType` 1 branch with no sub-branches written before 5.34/20 and 6.02/00.
3. For a branch with `fType` 31 or 41 whose element has a fixed width *w*, the
   entry's length is *n* × *w*, where *n* is the count branch's value for that
   entry, and 0 when *n* is 0.
4. A count read from an `fType` 3 or 4 entry is between 0 and `fMaximum`
   inclusive.
5. The bytes a branch's entry occupies equal the bytes its decoding consumes.
6. A `std::bitset` member's entry is either empty or a complete object-wise
   collection; there is no partial form.

All six are checked over every fixture and both corpora, but only four have a
label of their own. Invariant 2 is checked as
[Splitting invariant 2](Splitting.md#8-invariants), the same fact seen from the
branch side, and invariant 6 through invariant 5, since a partial bitset entry
would not consume the bytes its span allows. `gen/invariants.toml` records both,
and `tools/check_coverage.py` checks that record.

Invariant 5 is the general statement of the others, and a third-party reader
should test itself against it. It cannot be checked by a rule, only by decoding,
which is what `tools/rootfile.py`'s `TreeReader` exists for. Over both corpora it
holds on **48 278 branch-baskets, 99.5% of them**, with none failing. The
remaining 223 are named individually in the checker's `SKIPPED` report, each with
a count and a reason. 153 of them **no reader could decode from the file**. Each
of those is either a collection whose value class
has no streamer info in the file
([Collections §9](../02-serialization/Collections.md#9-the-value-classs-streamer-info-can-be-missing-entirely)
says nobody can read those, ROOT included), or a class whose `Streamer` is
hand-written; two of those classes are recognised by their bytes alone, as
[Streamer-driven reading §7.1](../02-serialization/StreamerDriven.md#71-an-object-with-no-byte-count)
describes. The other 70 are 65 baskets written to another file, which no corpus
holds (`fFileName`, [TBranch](TBranch.md)), and 5 `TBranchObject` baskets, which
`rootfile.py` does not decode yet. Invariants 1, 3 and 4 are checked on embedded
baskets too; until 2026-09-24 they were not, and passed without reading anything
on a file whose baskets are all embedded.

> Neither reason is a defect, and neither can be resolved from inside the file. A
> class whose `Streamer` is hand-written has a streamer info that does not
> describe its bytes, and nothing marks it except, sometimes, a missing byte count
> ([Streamer-driven §7](../02-serialization/StreamerDriven.md#7-when-the-streamer-info-does-not-describe-the-bytes)).
> A collection whose value class has no streamer info in the file cannot be
> decoded at all. Both appear as skips rather than failures.

## 9. Errata

| # | Claim | Correction |
|---|---|---|
| 1 | `root/io/doc/TFile/README.md:247-287` — the whole `TTree` section | It never says what a basket entry contains. It ends at "The custom written TBasket streamer internally handles the packing of data into fixed size TBasket objects" (`root/io/doc/TFile/README.md:286-287`), which is the last word the shipped documentation has on the subject. Nothing in it would let a reader decode one branch value |
| 2 | `root/io/doc/TFile/tclonesarray.md:28-40` describes the member-wise layout of a `TClonesArray`, and is easily mistaken for the split-branch layout | None of the framing it lists — byte count, class info, version, `TObject`, `fName`, `"TXxx;1"`, `nObjects`, `fLowerBound` (`root/io/doc/TFile/tclonesarray.md:6-27`) — appears in a split branch. The master branch's entry is four bytes, each member lives in its own branch and basket, and `fLowerBound` never appears in an entry at all |
| 3 | `root/io/doc/TFile/ttree.md:75`: `fMaximum` is "Maximum entries for a TClonesArray or variable array" | Correct, but it is also a read-time bound that ROOT enforces (§6). A reader that treats it as a hint accepts entries ROOT rejects |
| 4 | — | Nothing anywhere states that the header of §5.3 is shared across a *column*. For `kStreamer`, `kSTL` and `kStreamLoop` an entry of *n* values carries one byte count and one version word between them, and a member-wise column carries one value-class version too. A reader that frames each value desynchronises on the second |
| 5 | — | Nothing states that a `std::bitset` member can be written as a branch with no bytes in it. Before ROOT 6.08/06 it always was (§3.6), and the branch looks identical to one that holds data |
| 6 | — | **A suspected ROOT bug that loses data.** `fBranchCount` is set from a name looked up over the whole tree (`root/tree/tree/src/TBranchElement.cxx:438`), so two split objects of one class whose sub-branches carry no parent prefix both point at the *first* object's counter. In `alice_ESDs.root` ROOT therefore reads 0 elements for `PrimaryVertex.fIndices`, whose entries hold 18, 22, 6 and 13 (§4.1). The bytes are intact and self-describing; only the pointer is wrong. Resolve the counter among siblings instead |

## 10. Reference files

| Case | What it shows |
|---|---|
| `ttree/split-nested` | §3.1 and §3.2: a count branch's three entries and the two member columns beneath them, including the empty entry |
| `ttree/split-unsplit` | §3.3: an unsplit object whose entry has no framing of its own but begins with its base class's |
| `ttree/split-counter` | §3.4: the flag byte, a counter branch with no offset array, and a member column with one |
| `ttree/split-double32` | §5.2: five members whose widths differ and are recorded nowhere but the streamer element |
| `ttree/split-clones` | The `TClonesArray` form of §3.1 and §3.2 |
| `ttree/split-tbits` | §3.4 and §4: a counted array whose counter branch has `fStreamerType` 13 rather than 6, and §3.3 on an unsplit `TBits` |
| `ttree/split-bitset` | §3.6: a `bitset<16>` as twenty-six bytes, and the bit order, which only its third entry fixes |
| `ttree/split-stl-pointer` | §5.3 on single members: a pointer to a collection, an array of them and an array of collections, each entry one member-wise frame |

Not covered by a fixture: §3.5, which needs a class with a hand-written
`Streamer`; the member-wise STL body of §5.3 inside a split branch, which needs
a collection of collections; and the pre-6.08/06 empty bitset of §3.6, which
needs a ROOT older than any this project builds against. The last two occur in
`gen/foreign/` (`uproot-issue433-splitlevel4.root` and `uproot-mc10events.root`)
and are checked there.
