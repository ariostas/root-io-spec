# `TLeaf`

`TLeafO`, `TLeafB`, `TLeafS`, `TLeafI`, `TLeafL`, `TLeafG`, `TLeafF`, `TLeafD`,
`TLeafF16`, `TLeafD32`, `TLeafC`, `TLeafObject`, `TLeafElement`.

A leaf is the only thing in a ROOT file that says what the bytes in a basket
mean. [`TBranch`](TBranch.md) says where they are; [`TBasket`](TBasket.md) says
where one entry stops; the leaf says how to read it.

Prerequisites: [Streamer-driven reading](../02-serialization/StreamerDriven.md),
[TBranch](TBranch.md), [TBasket](TBasket.md).

## 1. Two separate things

`TLeaf` is small and its record is dull; the interesting half of this document is
§5, the layout of a leaf's bytes **inside a basket**, which is not described by
any streamer info anywhere and is the part third-party readers get wrong.

Keep them apart while reading:

| | Where | Described by |
|---|---|---|
| The leaf *record* | inside a `TBranch`'s `fLeaves`, in the [`TTree` record](TTree.md) | the file's own streamer info |
| The leaf *data* | inside a basket | §5 of this document, and nothing else |

## 2. The leaf record

`TLeaf` is class version 2 (`root/tree/tree/inc/TLeaf.h:171`). `TLeaf::Streamer`
exists (`root/tree/tree/src/TLeaf.cxx:481`) and is a version guard: above 1 it
calls `ReadClassBuffer` (`root/tree/tree/src/TLeaf.cxx:486-487`). Every concrete
leaf is nested in a `fLeaves` `TObjArray`, so it is introduced by the object-slot
machinery of [Buffer §6](../02-serialization/Buffer.md#6-object-slots).

The base, in streamer-info order:

| # | Member | Code | Type | Meaning |
|---|---|---|---|---|
| 1 | `TNamed` | 67 | base | `fName` the leaf name, `fTitle` the dimension and range spec (§7) |
| 2 | `fLen` | 3 | `Int_t` | fixed element count per entry, §5.2 |
| 3 | `fLenType` | 3 | `Int_t` | **the writer's `sizeof`, not the on-disk width**, §4.1 |
| 4 | `fOffset` | 3 | `Int_t` | this leaf's position within one entry, §3.2 |
| 5 | `fIsRange` | 18 | `bool` | **means "this leaf is some other leaf's counter"**, §6 |
| 6 | `fIsUnsigned` | 18 | `bool` | how to interpret the bits; never changes them |
| 7 | `fLeafCount` | 64 | `TLeaf*` | the counter leaf, as an object reference, §3.1 |

Each concrete class adds two more members after that base — `fMinimum` and
`fMaximum` of its own element type — except `TLeafObject`, which adds `fVirtual`,
and `TLeafElement`, which adds `fID` and `fType` (§8).

Three transient members are reconstructed and are not on disk: `fNdata`,
`fBranch` and `fLeafCountValues` (`root/tree/tree/inc/TLeaf.h:74`,
`root/tree/tree/inc/TLeaf.h:81-82`). `TLeaf::Streamer` rebuilds `fNdata` after the
read as `(fLeafCount->GetMaximum() + 1) × fLen`, or `fLen`
(`root/tree/tree/src/TLeaf.cxx:444-449`).

> **A stored `fLen` of 0 means 1.** `TLeaf::Streamer` normalises it after reading,
> on both the modern and the legacy path (`root/tree/tree/src/TLeaf.cxx:499-501`).
> A reader must do the same or it will read zero elements per entry.

### 2.1 The classes

| Code | Class | Version | Extra members | On-disk width per value |
|---|---|---|---|---|
| `O` | `TLeafO` | 1 | `bool` ×2 | 1 |
| `B` | `TLeafB` | 1 | `Char_t` ×2 | 1 |
| `b` | `TLeafB` | 1 | `Char_t` ×2 | 1, unsigned |
| `S` | `TLeafS` | 1 | `Short_t` ×2 | 2 |
| `s` | `TLeafS` | 1 | `Short_t` ×2 | 2, unsigned |
| `I` | `TLeafI` | 1 | `Int_t` ×2 | 4 |
| `i` | `TLeafI` | 1 | `Int_t` ×2 | 4, unsigned |
| `L` | `TLeafL` | 1 | `Long64_t` ×2 | 8 |
| `l` | `TLeafL` | 1 | `Long64_t` ×2 | 8, unsigned |
| `G` | `TLeafG` | 1 | `Long_t` ×2 | **8 always**, §4.1 |
| `g` | `TLeafG` | 1 | `Long_t` ×2 | **8 always**, unsigned |
| `F` | `TLeafF` | 1 | `Float_t` ×2 | 4 |
| `D` | `TLeafD` | 1 | `Double_t` ×2 | 8 |
| `f` | `TLeafF16` | 2 | `Float16_t` ×2 (**3 bytes each**) | 3 or 4, §7 |
| `d` | `TLeafD32` | 2 | `Double32_t` ×2 (**4 bytes each**) | 3 or 4, §7 |
| `C` | `TLeafC` | 1 | `Int_t` ×2 | variable, §9 |
| — | `TLeafObject` | 4 | `bool fVirtual` | §8 |
| — | `TLeafElement` | 1 | `Int_t fID`, `Int_t fType` | §8 |

The "Code" column is the leaflist type character, and it is dispatched on
**`leaftype[0]` only** (`root/tree/tree/src/TBranch.cxx:362-399`). There is no
`F16` or `D32` code: `x/F16` yields a plain `TLeafF` and a warning about extra
characters (`root/tree/tree/src/TBranch.cxx:358-360`). The truncated types are the
lower-case `f` and `d`.

Only `TLeaf`, `TLeafF16`, `TLeafD32` and `TLeafObject` have a hand-written
`Streamer`; every other class in the family is read straight from the file's
streamer info.

## 3. Two fields that mean something other than they look like

### 3.1 `fLeafCount` is a buffer object reference

`fLeafCount` is element code 64, `kObjectP`
([Element types §7](../02-serialization/ElementTypes.md#7-object-valued-codes-61-to-71)),
so it is written by `WriteObjectAny` and reaches the file as one of three things:

* four zero bytes, for no counter;
* a full object slot — byte count, `0xFFFFFFFF`, class name, the leaf — if this is
  the first time that leaf appears in the buffer;
* **a bare reference tag**, if it has already been written, which is the usual
  case because the counter leaf belongs to an earlier branch.

Resolving the third needs the buffer's object map
([Buffer §6.1](../02-serialization/Buffer.md#61-object-references)), keyed by
`position + 2`. This is the only place in an ordinary `TTree` where two objects
point at each other across branches, and it is the single likeliest thing for a
third-party reader to get wrong.

> Demonstrated by `ttree/basket`. Leaf `a` has `fLeafCount` = 447, and the
> `TLeafI` for `n`, in a different branch, is the object slot at record offset
> 445 — 447 less `kMapOffset`. The tree's own `fLeaves` array holds the same two
> leaves again, as two more four-byte references.

### 3.2 `fOffset` is a position in the entry

For a branch built from a leaflist, `fOffset` is the cumulative *unpadded* size of
the leaves declared before this one: `TBranch::Init` accumulates
`fLenType × fLen` across the list (`root/tree/tree/src/TBranch.cxx:436`). It is
therefore where the leaf's bytes start within one entry — measured from the start
of the entry, not from the start of the basket.

It is not [`TBranch::fOffset`](TBranch.md#71-foffset-is-an-in-memory-offset),
which is an offset inside a C++ object. And `TLeaf.h`'s comment, "Offset in
ClonesArray object (if one)" (`root/tree/tree/inc/TLeaf.h:77`), describes a
*third* use — `TLeafI::Import` reads a `TClonesArray` element at that offset — so
the field is genuinely overloaded and the shipped comment names the rarest of its
three meanings.

**A reader should not use it.** It is exact only while every leaf before this one
has a fixed size; once a `TLeafC` or a counted array appears, the offsets after it
are the values they had at construction time and are wrong for every entry. §5's
sequential read does not need it.

> **Nor can such a branch be written correctly.** `fOffset` doubles as the
> *in-memory* offset a leaflist branch reads its member from, and a `TLeafC`
> contributes `fLen × fLenType` = 1 to it at construction. A struct
> `{ Char_t c[8]; Int_t x; }` declared as `c/C:x/I` therefore has `x` at
> `fOffset` 1, and ROOT reads it from the second byte of the string. The file that
> results is structurally valid and contains garbage. A `TLeafC` is usable only as
> the **last** leaf of a leaflist — which is also the only arrangement whose empty
> strings read back correctly (§9).

> Demonstrated by `ttree/leaf`, whose thirteen leaves have `fOffset` 0, 8, 16, 24,
> 48, 52, 56, 60, 62, 64, 65, 66 and 67 — the packed offsets of a 70-byte entry.
> The last of them, the `TLeafC`, is where the arithmetic stops being reliable:
> its `fLen × fLenType` is 3, but its second entry occupies no bytes at all.

## 4. `fLenType` and `fLen`

`fLenType` is the **writing machine's `sizeof`** for the element type
(`root/tree/tree/src/TLeafI.cxx:30` and the corresponding line in each class), and
`fLen` is the number of fixed-size elements per entry — the product of the
constant dimensions in the leaflist, so `a[5]/F` gives `fLen` 5 and `a[n][3]/F`
gives `fLen` 3 with a counter (`root/tree/tree/src/TLeaf.cxx:307-353`).

> **A leaf's rank is not recorded anywhere but its title.** `fLen` holds the
> product of the constant dimensions and `fLeafCount` names the variable one, so
> on disk `a[n][3]/F` and a flat `a[m]/F` with `m = 3n` are the same bytes. A
> reader that wants the shape must parse `fTitle`.
>
> Demonstrated by `ttree/leaf-forms`: `a` has `fTitle` `a[n][3]`, `fLen` 3 and a
> `fLeafCount` reference, and its two entries hold six and three floats.

**`fLen` on a `TLeafC` is not a size.** It is the longest string written so far
plus its terminator, updated as the branch is filled, so it bounds the entries
rather than describing them: in `ttree/leaf-forms` it is 301 while the first
entry occupies three bytes, and it is neither 1 nor the size of the buffer the
branch was given.

### 4.1 `fLenType` is not the on-disk width

For every fixed-width type the two agree, and for three classes they do not:

| Class | `fLenType` | On disk |
|---|---|---|
| `TLeafG` | `sizeof(Long_t)` — 4 on a 32-bit or Windows writer | **8 always** (`root/core/base/inc/Bytes.h:143-194`) |
| `TLeafF16` | 4 | 3, or 4 with a range (§7) |
| `TLeafD32` | 8 | 4, or 3 with `nbits` only (§7) |
| `TLeafC` | 1 | variable (§9) |

A reader MUST take the width from the leaf's class, not from `fLenType`.

> Demonstrated by `ttree/leaf-truncated`, whose four leaves have `fLenType` 4, 4,
> 8, 8 and occupy 3, 4, 4 and 3 bytes per entry — in that order, so neither the
> class nor `fLenType` predicts the width on its own.
>
> And by `ttree/leaf-forms`, whose `TLeafG` occupies 8 bytes per entry. Its
> `fLenType` is 8 here because the writer is 64-bit and not Windows; the payload
> would be the same 8 bytes if it were 4. `fMinimum` and `fMaximum` follow the
> same rule and take 8 bytes each in the leaf record, where a `TLeafC`'s take 4.

### 4.2 `fLen` can be −1

`fLen` comes from parsing the `[...]` in the leaf's title, and that parse has a
documented failure value. `TLeaf::GetLeafCounter` returns `countval = -1` when the
title has the form `var[...]` but the contents are neither a leaf name in this
tree nor a non-negative integer (`root/tree/tree/src/TLeaf.cxx:244-245`,
`root/tree/tree/src/TLeaf.cxx:334`).

That is the normal state for a `TLeafElement` on a split branch, where the
dimension names a data member rather than a leaf, and the count lives in the
`TBranchElement` (§8). A reader must not multiply by it.

> Seen on `uproot-issue431.root` and both `uproot-issue433-splitlevel*` files of
> the foreign corpus: leaf
> `vector<KM3NETDAQ::JDAQSuperFrame>.buffer[numberOfHits]` has `fLen` −1.

## 5. Reading one entry

A basket holds no type information and no per-leaf framing. Given the byte range
of entry *e* from [TBranch §10](TBranch.md#10-reading):

1. Set the cursor to the start of the range.
2. For each leaf of the branch **in `fLeaves` order**
   (`root/tree/tree/src/TBranch.cxx:2460-2466`):
   1. Determine `n`, the element count for this entry (§5.2).
   2. Read `n` values of this leaf's on-disk width (§4.1), big-endian,
      consecutively, with no byte count, version word, separator or padding.
   3. Advance the cursor by what was read.
3. The cursor is now at the end of the entry.

There is nothing else. A leaf contributes exactly the bytes its values occupy.

### 5.1 Two or more leaves share an entry

A leaflist branch can hold any number of leaves, and their values are simply
concatenated within each entry, in declaration order, once per entry — not
column-wise, and not with the leaves in separate baskets.

> Demonstrated by `ttree/leaf`: one branch, thirteen leaves, and each entry is the
> thirteen values back to back — `l`, `L`, `d`, three `v`, `i`, `I`, `f`, `s`,
> `S`, `b`, `B`, `o`, then the string.

### 5.2 The element count comes from another leaf

If `fLeafCount` is null, `n` is `fLen` and every entry is the same size.

If `fLeafCount` is not null, then for entry *e*:

```
n = (value of the counter leaf for entry e) × fLen
```

(`root/tree/tree/src/TLeaf.cxx:405-418`). **The count is not stored in this
leaf's data.** The counter is a different leaf, usually in a different branch, and
a reader must read *that* branch's entry *e* first
(`root/tree/tree/src/TLeafF.cxx:120-125`).

ROOT clamps `n` to the counter leaf's `fMaximum` and prints an error above it
(`root/tree/tree/src/TLeaf.cxx:410-413`). A reader need not, and arguably should
not: the entry-offset array in the basket gives the true extent independently, and
`fMaximum` can only be too small.

> Demonstrated by `ttree/basket`. Branch `a` is `a[n]/F` with `fLen` 1 and
> `fLeafCount` pointing at branch `n`'s leaf; its three entries hold 1, 2 and 3
> floats and nothing else — 4, 8 and 12 bytes — while the counts 1, 2 and 3 are in
> branch `n`'s basket.

### 5.3 A branch with a variable-size leaf always has an offset array

`TBranch::Init` forces `fEntryOffsetLen` to 1000 as soon as any leaf has a counter
or is a `TLeafC` (`root/tree/tree/src/TBranch.cxx:420-427`), so a basket of such a
branch normally carries an entry-offset array
([TBasket §5](TBasket.md#5-the-entry-offset-array)), and a reader can delimit an
entry without consulting the counter branch — though it still needs the counter to
split that entry into values when the branch has more than one leaf.

> **One exception, and it is not rare.** With `fIOBits` bit 0 set and a branch whose
> offsets can be recomputed, the array is deliberately **not written**: the basket's
> flag is 80 and the offsets must be regenerated from the counter branch
> ([TBasket §5.2.1](TBasket.md#521-regenerating-the-offsets)). `ttree/basket-iofeatures`
> is exactly that case, and `uproot-small-dy-nooffsets.root` in the foreign corpus is
> a real one. So a reader MUST NOT treat "variable-size leaf" as "offset array
> present"; invariant 5 carries the same caveat.

## 6. `fIsRange`, `fMinimum` and `fMaximum`

`fIsRange` does **not** mean "this leaf has a range". It means *this leaf is used
as another leaf's counter*, and `TLeaf::GetLeafCounter` sets it on the counter
(`root/tree/tree/src/TLeaf.cxx:309`). The header says so, in the clause after the
one the shipped documentation quotes (`root/tree/tree/inc/TLeaf.h:78`).

`fMaximum` is maintained only on integer leaves and only when `fIsRange` is set,
and only from element 0: `if (IsRange()) { if (fValue[0] > fMaximum) fMaximum = fValue[0]; }`
(`root/tree/tree/src/TLeafI.cxx:82-84`, and the same in `TLeafB`, `TLeafS`,
`TLeafL`, `TLeafG`, `TLeafO`). On a closed file it is the largest count seen.

`TLeafF`, `TLeafD`, `TLeafF16` and `TLeafD32` never touch either field
(`root/tree/tree/src/TLeafF.cxx:77-82`), and do not override `GetMaximum`, which
returns 0 (`root/tree/tree/inc/TLeaf.h:137-138`). A floating-point leaf therefore
cannot usefully be a counter — `GetLen` would clamp every count to 0.

**`fMinimum` is never computed from data by any class.** It is written only by
`IncludeRange` when trees are merged. Treat it as always 0.

`TLeafC` overloads both: `fIsRange` stays false, but `fLen` and `fMaximum` are
both raised to `strlen + 1` on every fill
(`root/tree/tree/src/TLeafC.cxx:80-82`), so a `TLeafC`'s `fLen` on a closed file
is the longest string written plus one — a high-water mark, not a declared size.

> Demonstrated by `ttree/basket`: leaf `n` has `fIsRange` 1, `fMinimum` 0 and
> `fMaximum` 3 after counts of 1, 2 and 3; leaf `a` has `fIsRange` 0. And by
> `ttree/leaf`, whose `TLeafC` has `fLen` 3 after writing `"ab"` and `""`.

## 7. `TLeafF16` and `TLeafD32`

Both store the packing parameters **in the leaf title**, as an annotation
`[xmin,xmax]` or `[xmin,xmax,nbits]` after the type character. `TLeafF16::Streamer`
re-parses it into a throw-away `TStreamerElement` after every read
(`root/tree/tree/src/TLeafF16.cxx:229-233`,
`root/tree/tree/src/TLeafD32.cxx:219-223`). Nothing else about the packing is on
disk: a reader must parse the title.

The grammar and the two encodings are the ones in
[Element types §5](../02-serialization/ElementTypes.md#5-kdouble32-and-kfloat16);
what is specific to leaves is which of them applies, and that **the two classes
disagree when there is no annotation at all**:

| Title annotation | Encoding | Bytes |
|---|---|---|
| none, `f` | truncated mantissa, `nbits` = 12 | **3** |
| none, `d` | a plain `Float_t` | **4** |
| `[xmin,xmax]`, `xmin < xmax` | scaled `UInt_t`, factor `0xffffffff / (xmax − xmin)` | 4 |
| `[xmin,xmax,nbits]`, `xmin < xmax`, `2 ≤ nbits ≤ 31` | scaled `UInt_t`, factor `(1 << nbits) / (xmax − xmin)` | 4 |
| `[0,0,nbits]`, `nbits < 15` | truncated mantissa, that `nbits` | **3** |
| `[0,0,nbits]`, `nbits ≥ 15` | as the "none" row for that class | 3 or 4 |

The `nbits < 15` row works because `GetRange` smuggles the bit count into `fXmin`
as `nbits + 0.1` when no real range was given
(`root/core/meta/src/TStreamerElement.cxx:184`), and `WriteFloat16` reads it back
out of `GetXmin()` (`root/io/io/src/TBufferFile.cxx:633-634`).

> **The same asymmetry is inside the leaf record.** `TLeafF16::fMinimum` and
> `fMaximum` are declared `Float16_t` with no annotation, so they occupy **3 bytes
> each**; `TLeafD32`'s are `Double32_t` with no annotation and occupy **4 bytes
> each** (`root/tree/tree/inc/TLeafF16.h:30-31`,
> `root/tree/tree/inc/TLeafD32.h:31-32`). A reader that assumes the two classes
> are shaped alike desynchronises by two bytes per leaf.

> Demonstrated by `ttree/leaf-truncated`: `a/f` is `7f 08 00`, `b/f[0,100,10]` is
> `00 00 02 00` (50.0 × 10.24 = 512), `c/d` is `40 20 00 00` (a plain float 2.5)
> and `d/d[0,0,8]` is `80 00 c0`.

> **Class version 2 of both is new in ROOT 6.40.** Below it the constructor
> overwrote the title with the type spec alone, so a version-1 leaf's title can be
> `f[0,100,10]` with no name, no dimensions and no leading `/`, and the counter
> information for a variable-size truncated array is simply lost. ROOT repairs the
> missing slash on read (`root/tree/tree/src/TLeafF16.cxx:226-228`); a reader
> should accept both forms.

## 8. `TLeafObject` and `TLeafElement`

`TLeafElement` (version 1) is metadata only. It adds `fID` and `fType`, and
defines no `ReadBasket` at all: a split branch's bytes are read by
`TBranchElement`, not by its leaf. `fType` is **not** `TBranchElement::fType` — it
is the branch's `fStreamerType` (`root/tree/tree/src/TBranchElement.cxx:551`),
which is an element-type code. `fID` mirrors `TBranchElement::fID`. Its `fLenType`
is derived from the streamer type and is used only for offset-array generation
(`root/tree/tree/src/TLeafElement.cxx:42-97`). `TBranchElement` is not specified
here; see `PLAN.md` §2.5.

`TLeafObject` (version 4) adds only `bool fVirtual`; its `fClass` is transient and
is rebuilt from `fTitle`, which holds the stored object's class name
(`root/tree/tree/src/TLeafObject.cxx:200`). Its streamer is hand-written and has
three legacy shapes: version 2 forces `fVirtual` true because it was transient
then, version 3 reads one extra byte, and version 1 sets it true without reading
(`root/tree/tree/src/TLeafObject.cxx:191-224`).

## 9. `TLeafC`

A string leaf writes a counted string per entry
(`root/tree/tree/src/TLeafC.cxx:83`,
`root/io/io/src/TBufferFile.cxx:2036-2060`): one length byte, then that many raw
bytes with no terminator; a length of 255 or more is written as the byte `0xFF`
followed by a big-endian `Int_t`. This is the counted string of
[Conventions §5.1](../00-conventions.md#51-counted-string).

> Demonstrated by `ttree/leaf-forms`, whose one `TLeafC` basket holds **both**
> forms: entry 0 is `02 "ab"` and entry 1 is `ff` then `0000012c` then 300
> bytes — 305 bytes for a 300-character string. A reader that implements only
> the short form desynchronises on the second entry, and the entry-offset array
> agrees: 65 and 68.

**An empty string occupies zero bytes** — `WriteFastArrayString` returns before
writing even the length byte (`root/io/io/src/TBufferFile.cxx:2038`) — while
`ReadFastArrayString` always reads one (`root/io/io/src/TBufferFile.cxx:1306`).
The two are not inverses, and ROOT closes the gap in the leaf rather than the
buffer: `TLeafC::ReadBasket` inspects the basket's entry offsets and yields `""`
without touching the buffer when the entry consumed no bytes
(`root/tree/tree/src/TLeafC.cxx:135-167`).

A reader must therefore not read a length byte unconditionally. The test is
whether the leaf has any bytes left in the entry at all: take the entry's end from
[TBasket §8](TBasket.md#8-reading), subtract what the leaves before this one
consumed, and read nothing if the remainder is zero.

> Demonstrated by `ttree/leaf`, whose entries are 70 and 67 bytes: the first ends
> with `02 61 62` for `"ab"` and the second ends at the `Bool_t` before it, with
> the empty string contributing nothing.

> **ROOT's own test is coarser than that, and gets this wrong.**
> `TLeafC::ReadBasket` compares **whole-entry** offsets — `offset[i]` against
> `offset[i+1]`, or against `fLast` for the last entry of a basket
> (`root/tree/tree/src/TLeafC.cxx:146-166`). That detects an entry that is
> entirely empty, which is only the same thing when the `TLeafC` is the branch's
> only leaf. In a branch with more than one leaf ROOT falls through and reads the
> next entry's first byte as the length.
>
> A branch `x/I:c/C` with `x` = `0x02414243` and the strings `"ab"`, `""`, `"cd"`
> makes ROOT return `"AB"` for the second entry — the first two bytes of the third
> entry's `x`. It is not always visible: a following byte of 0 yields the right
> answer by accident, and a large one is refused by a length check in
> `TBufferFile`, which is why the arrangement in `ttree/leaf` round-trips. See
> `PLAN.md` §7.1.

## 10. Invariants

1. `fLenType` is 0 or positive. `fLen` is positive after the zero-to-one
   normalisation of §2, **or −1**, which means the dimension in the title named
   something the writer could not resolve (§4.2).
2. `fIsRange` is true only on a leaf that some other leaf in the same tree names
   as its `fLeafCount`.
3. A leaf with `fIsRange` true is an integer leaf — `TLeafO`, `TLeafB`, `TLeafS`,
   `TLeafI`, `TLeafL`, `TLeafG` — or a `TLeafElement`, which keeps the range in
   its `TBranchElement` instead (`root/tree/tree/inc/TLeaf.h:78`).
4. `fLeafCount`, where non-null, resolves through the buffer object map to a
   `TLeaf` in the same `TTree` record.
5. A branch containing a leaf with a non-null `fLeafCount`, or any `TLeafC`, has
   `fEntryOffsetLen` non-zero, and every basket of that branch carries an
   entry-offset array **unless its flag is 80**, in which case the offsets are
   generated instead ([TBasket §5.2.1](TBasket.md#521-regenerating-the-offsets)).
6. For a branch every one of whose leaves has a null `fLeafCount` and none of
   which is a `TLeafC` **and whose `fEntryOffsetLen` is 0**, the sum of
   `width × fLen` over its leaves equals the basket's `fNevBufSize`, and the
   basket has no entry-offset array. `fEntryOffsetLen` is the writer's decision
   and it is what the baskets follow: a current writer sets it to 0 on such a
   branch, but a ROOT 4.00-era writer left it at the default 1000 and its baskets
   then **do** carry an offset array for fixed-width leaves —
   `uproot-issue-250.root`, whose `TLeafD` branches have `fEntryOffsetLen` 1000,
   `fNevBufSize` 1000 and offsets 8 bytes apart.
7. For any branch, the sum over its leaves of that entry's bytes equals the length
   of the entry's byte range, exactly.
8. `fOffset` of the first leaf of a branch is 0, **unless the branch stands under
   a `TBranchClones`** — see below.

**Invariant 8's exception is not a weakening.** A sub-branch of a
`TBranchClones` is one member of a `TClonesArray`, and its leaf's `fOffset` is that
member's offset inside the object: in `ttree/branch-clones` the four sub-branches
of `CHitC` carry 8, 12, 16 and 20 — `TObject`'s `fUniqueID` and `fBits`, then `fI`
and `fX`. ROOT writes those values and then **throws them away on read**, forcing
`fOffset` to −1 for every such leaf (`root/tree/tree/src/TBranchClones.cxx:413`).
So the field is written, is not 0, and is not used; a reader must neither require 0
nor trust the value. See
[TBranchElement §13](TBranchElement.md#13-tbranchclones-and-the-only-api-that-makes-one).

**Invariants 5 to 7 are about what a branch's leaves say, so a branch with no
leaf at all is outside them.** Two shapes reach that state, both added by the
split fixtures: the interior nodes of
[TBranchElement §4](TBranchElement.md#4-two-ftype-values-have-no-leaf-and-two-reach-theirs-only-by-reference),
which have no basket either and so are vacuous rather than exempt; and a
`TBranchSTL`, which has **baskets full of data and still no leaf**
(`ttree/split-ptr-collection`). A reader must not conclude from an empty leaf
list that a branch holds nothing.

Invariant 5's first half — that the branch declares `fEntryOffsetLen` — is the
testable one; its second half is not reachable in isolation, because a basket
whose offset array is removed fails
[TBasket §9](TBasket.md#9-invariants) invariant 4 first.

Invariant 6 is the one that ties the leaf layer to the basket layer arithmetically,
and invariant 7 is the general form of it — it is the whole of §5 stated as a
closure condition, and it is what a reader's own implementation should be checked
against.

## 11. Errata

Against `root/io/doc/TFile/ttree.md`, which documents release 3.02.06:

| # | Claim | Actually |
|---|---|---|
| 1 | `ttree.md:79-92` gives streamer infos for `TLeaf` and `TLeafElement` only | Twelve concrete leaf classes exist, and eleven of them add two members after the `TLeaf` base. A reader following the document mis-parses every leaf record by between 2 and 16 trailing bytes (§2.1) |
| 2 | `ttree.md:84-85`: `fIsRange` and `fIsUnsigned` are type 11 (`kUChar`) | They are type 18 (`kBool`) now. One byte either way, but a reader driven by type codes must accept both |
| 3 | `ttree.md:84`: `fIsRange` is "true if leaf has a range" | It means the leaf is another leaf's counter. Reading it the documented way suggests `fMinimum`/`fMaximum` are meaningful, and they are not (§6) |
| 4 | `ttree.md:86`: `fLeafCount` is a "Pointer to Leaf count", type 64 | True, and unexplained. Type 64 is an object reference resolved through the buffer's object map, and in a real file it is a bare back-reference tag to a leaf in a different branch (§3.1) |
| 5 | — | Nothing anywhere describes the layout of leaf data inside a basket: not that leaves are concatenated per entry, not that a counted array stores no count of its own, not that the count comes from a different branch (§5) |
| 6 | — | Nothing says that an empty `TLeafC` string occupies zero bytes, which cannot be recovered without the entry-offset array (§9) |
| 7 | `root/io/io/src/TBufferFile.cxx:588`: "if nbits is not specified, or nbits <2 or nbits>16 it is set to 16" | The shared parser uses **32**, not 16, in both places (`root/core/meta/src/TStreamerElement.cxx:141-148`). There is no `Float16`-specific parser |
| 8 | `root/tree/tree/inc/TLeafF16.h:54`: "A TLeaf for a 24 bit truncated floating point data type" | 24 bits is only the no-factor case; with a range the value is 32 bits, and a `Double32_t` with no annotation is 32 bits as a plain float (§7) |
| 9 | `root/tree/tree/inc/TLeafElement.h:37`: `fType` is the "leaf type" | It is the owning `TBranchElement`'s `fStreamerType`, a different enumeration from `TBranchElement::fType` (§8) |
| 10 | `root/tree/tree/src/TLeafC.cxx:137-138` implies the zero-byte empty string is historical | It is current behaviour: `WriteFastArrayString` still returns before writing when the length is 0 (§9) |
| 11 | `root/tree/tree/inc/TLeaf.h:77`: `fOffset` is the "Offset in ClonesArray object (if one)" | Its usual meaning is a position within a basket entry; the `TClonesArray` reading is the rarest of three (§3.2) |
| 12 | `root/tree/tree/src/TBranch.cxx:147-162` lists the leaflist codes | Accurate, but it never says only the first character is read, so `x/F16` silently produces a `TLeafF` (§2.1) |

One inconsistency inside ROOT itself, source-verified but not file-verified:
`TLeafC::ReadBasketExport` reads a bare `UChar_t` length with no 255-escape
(`root/tree/tree/src/TLeafC.cxx:177-182`) where `FillBasket` writes one, so a
`TBranchClones` branch holding a string of 255 characters or more should be
unreadable by ROOT through that path. No fixture demonstrates it; see `PLAN.md`
§7.1.

## 12. Class versions

| Class | Version | Note |
|---|---|---|
| `TLeaf` | 1 | pre-2.26; same field order, read by the hand-written path (`root/tree/tree/src/TLeaf.cxx:490-497`) |
| `TLeaf` | 2 | current; `fNdata` and `fBranch` became transient |
| `TLeafO`…`TLeafD`, `TLeafC` | 1 | never changed |
| `TLeafG` | 1 | the class did not exist before ROOT 6.24 |
| `TLeafF16`, `TLeafD32` | 1 | ROOT 6.18 to 6.38: the title held the type spec alone |
| `TLeafF16`, `TLeafD32` | 2 | **new in ROOT 6.40**; the title keeps the name and dimensions |
| `TLeafElement` | 1 | never changed |
| `TLeafObject` | 1, 2, 3, 4 | three legacy shapes; 3 was a private FNAL variant (§8) |

## 13. Reference files

| Case | Exercises |
|---|---|
| `ttree/leaf` | Thirteen leaves in one branch: every scalar code, a fixed-size array, `fOffset` across a packed entry, and a `TLeafC` whose second entry is the empty string |
| `ttree/leaf-truncated` | All four truncated-float encodings, and the 3-versus-4-byte asymmetry between `TLeafF16` and `TLeafD32` in both the data and the leaf record |
| `ttree/basket` | A counter leaf and a counted array in two different branches, with `fLeafCount` as a cross-branch object reference |
| `ttree/leaf-forms` | `TLeafG` at 8 bytes, `a[n][3]/F` with `fLen` 3, and a `TLeafC` with both string forms in one basket |

`TLeafObject` and `TLeafElement` are covered elsewhere: `ttree/tree-branchref`
has a `TLeafObject`, and the split cases hold 52 `TLeafElement`s between them.

No fixture covers a leaf class at a legacy version, which needs a legacy ROOT
(`PLAN.md` §9.1).
