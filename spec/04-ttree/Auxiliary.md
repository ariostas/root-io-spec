# Auxiliary classes

The objects a `TTree` points at that are not branches, leaves or baskets:
indices, friends, reference tables, entry selections, and the two `TTree`
subclasses.

Prerequisites: [TTree](TTree.md), [TBranch](TBranch.md).

They have one thing in common worth saying first. **Seven of the nine appear in
no file of either corpus** (`PLAN.md` §9.8 and §9.9, 178 files from ROOT 4.00 to
6.36); only `TBranchRef` and `TRefTable` do, and those only because every tree
file carries their *streamer info* whether or not an object exists. Everything
here is therefore specified from the source and from fixtures written for the
purpose, and the invariants are correspondingly weaker than elsewhere in this
layer.

## 1. Where they hang off the tree

All five pointers are at the end of the `TTree` member list
([TTree §8](TTree.md#8-the-five-object-pointers-and-the-index-root-throws-away)), written as object references:
a null one is four zero bytes.

| Member | Type | Points at |
|---|---|---|
| `fTreeIndex` | `TVirtualIndex*` | a `TTreeIndex` (§2), or a `TChainIndex` |
| `fFriends` | `TList*` | `TFriendElement`s (§3) |
| `fBranchRef` | `TBranchRef*` | a branch, and its `TRefTable` (§4) |
| `fAliases`, `fUserInfo` | `TList*` | user data; no fixed layout |

`TEntryList`, `TEntryListArray` and `TEventList` (§5) are **not** reached from
the tree at all: they are written as top-level keys and name their tree by
string.

## 2. `TTreeIndex` — the one class with no streamer info

`TTreeIndex` lives in `libTreePlayer` and its `Streamer` is fully hand-written
(`root/tree/treeplayer/src/TTreeIndex.cxx:631`). It never calls
`ReadClassBuffer` or `WriteClassBuffer`, and the consequence is the single most
important fact in this document:

> **No `TStreamerInfo` for `TTreeIndex` is ever written into a file.** Every
> other class here is discoverable from the file that contains it. This one has
> to be hard-coded from this specification.

Confirmed on `ttree/tree-index`, whose streamer info list contains
`TVirtualIndex` and not `TTreeIndex`.

Class version 2 (`root/tree/treeplayer/inc/TTreeIndex.h:73`). The layout, in
order:

| Field | Type | |
|---|---|---|
| `TVirtualIndex` base | | version 1, itself a `TNamed` with empty name and title |
| `fMajorName` | `TString` | a leaf name **or an expression** |
| `fMinorName` | `TString` | |
| `fN` | `Long64_t` | the number of entries indexed |
| `fIndexValues` | `Long64_t[fN]` | the major value of each entry, sorted |
| `fIndexValuesMinor` | `Long64_t[fN]` | the minor value; **class version 2 and above** |
| `fIndex` | `Long64_t[fN]` | the entry number each row refers to |

**The three arrays carry no is-present flag.** They are written with
`WriteFastArray` (`root/tree/treeplayer/src/TTreeIndex.cxx:657-659`), so `fN` is
followed immediately by the values. That is the opposite of a streamer-info
`[fN]` member, which is preceded by a one-byte flag — compare `TEventList`
in §5.3, in the same fixture, which has one.

From `ttree/tree-index`, a ten-entry tree indexed on `Run` and `Event`:

```
40 00 01 2f  ff ff ff ff  "TTreeIndex\0"     object header, byte count 303
40 00 01 1c  00 02                           TTreeIndex, version 2
  40 00 00 14  00 01                         TVirtualIndex, version 1
    40 00 00 0e  00 01                       TNamed, version 1
      00 01 00000000 00000000                TObject
      00 00                                  fName "", fTitle ""
  03 "Run"                                   fMajorName
  05 "Event"                                 fMinorName
  00 00 00 00 00 00 00 0a                    fN = 10
  <10 × Long64_t>                            fIndexValues
  <10 × Long64_t>                            fIndexValuesMinor
  <10 × Long64_t>                            fIndex
```

Class version 1 has no `fIndexValuesMinor`; a reader of one must split each
stored value as `minor = v & 0x7fffffff`, `major = v >> 31`
(`root/tree/treeplayer/src/TTreeIndex.cxx:356-367`).

`fTreeIndex` is not always a `TTreeIndex`: a `TChain`'s index is a `TChainIndex`,
which *is* streamer-info driven. No fixture covers one.

### 2.1 `fIndexValues` and `fIndex` on the tree are dead

[`TTree`](TTree.md#81-findexvalues-and-findex) also has members called
`fIndexValues` and `fIndex`, a `TArrayD` and a `TArrayI`. They are **not** a
projection of the `TTreeIndex`: they are the pre-4.00 index, they are still
serialised as empty arrays, and ROOT **discards them on read with a warning**
(`root/tree/tree/src/TTree.cxx:9840-9844`). A reader should ignore them and use
`fTreeIndex`.

## 3. `TFriendElement`

Class version 2 (`root/tree/tree/inc/TFriendElement.h:76`), streamer-info
driven. Two persistent members after the `TNamed` base: `fTreeName` (`TString`)
and `fOwnFile` (`bool`) (`root/tree/tree/inc/TFriendElement.h:39-40`).

The mapping from `TTree::AddFriend`'s arguments onto those fields is the whole
difficulty:

| Field | Holds |
|---|---|
| `fName` | the **alias**, or the tree name when there is no alias |
| `fTitle` | the **filename**, or `""` when the friend is in the same file |
| `fTreeName` | the real tree name |
| `fOwnFile` | false when the friend shares the parent's file (`root/tree/tree/src/TFriendElement.cxx:199-203`) |

A tree name containing `=` is split at it: the part before becomes `fName`, the
part after `fTreeName` (`root/tree/tree/src/TFriendElement.cxx:59-69`). That is
the only way `fName` and `fTreeName` differ, and `ttree/tree-friend` has one of
each:

```
40 00 00 1a  00 02                    TFriendElement, version 2
  40 00 00 10  00 01                  TNamed
    00 01 00000000 00000000
    02 "t2"                           fName
    00                                fTitle "" — same file
  02 "t2"                             fTreeName
  00                                  fOwnFile = false
```

**A friend is a file path in a file.** When `fTitle` is non-empty it is the
string passed to `AddFriend`, stored verbatim, and a reader resolving it is
following a path that may no longer exist. This specification describes what is
recorded, not how to resolve it.

## 4. `TBranchRef` and `TRefTable`

`TTree::BranchRef` creates a `TBranchRef`, a branch with a fixed identity — name
`"TRefTable"`, title `"List of branch numbers with referenced objects"`
(`root/tree/tree/src/TBranchRef.cxx:58-59`) — holding one persistent member, a
`TRefTable*` (`root/tree/tree/inc/TBranchRef.h:39`). Class version 1.

Three things about it are unlike any other branch.

**It is not in `fBranches`.** It hangs off `TTree::fBranchRef`, so every walk
over the branch tree misses it — including the byte-sum invariant of
[TTree §4](TTree.md#4-ftotbytes-and-fzipbytes-are-sums-over-every-branch), which
has to add it by name.

**It is compressed in an uncompressed file.** Its constructor hard-codes
`fCompress = 1` (`root/tree/tree/src/TBranchRef.cxx:62`). In
`ttree/tree-branchref`, written with compression off, it is the only branch whose
`fZipBytes` (124) is below its `fTotBytes` (181), and the only basket in the file
beginning `5a 4c` — a `ZL` block header
([Compression](../01-container/Compression.md)).

**Its basket is not written unless asked.** `TTree::FlushBasketsImpl` iterates
only `GetListOfBranches` (`root/tree/tree/src/TTree.cxx:5255-5265`), so
`TTree::Write` never flushes `fBranchRef`. An ordinary small file therefore has a
`TBranchRef` **with no basket at all**, and its references cannot be resolved.
The fixture calls `FlushBaskets()` explicitly to produce one.

### 4.1 `TRefTable`

Class version 3 (`root/core/cont/inc/TRefTable.h:93`). Its `Streamer` is
hand-written but delegates, so the object layout is streamer-info driven and the
info is in the file. Persistent members: `fSize` (a dummy kept for
compatibility), `fParents` (`TObjArray*`), `fOwner` (`TObject*`) and
`fProcessGUIDs` (`std::vector<std::string>`)
(`root/core/cont/inc/TRefTable.h:46-49`).

**The per-entry payload in its baskets is not that layout.** It is written by
`TRefTable::FillBuffer` (`root/core/cont/src/TRefTable.cxx:224-231`):

```
Int_t  -fNumPIDs                     negative: the multi-PID format
for each PID:
    Int_t  fN                        how many uids follow
    Int_t  fParentIDs[fN]            raw, no flag byte
```

A **non-negative** first `Int_t` means the older single-`TProcessID` format, in
which that value is itself the count
(`root/core/cont/src/TRefTable.cxx:307-339`).

Resolving a reference then goes: match the `TRef`'s `TProcessID` GUID against
`fProcessGUIDs` to get an internal index; mask the `TRef`'s `fUniqueID` with
`0xFFFFFF`, since the top byte is the process-ID number; index `fParentIDs` with
it; **subtract one**, because 0 means "no parent"; and use the result to index
`fParents`, which holds the `TBranch` objects themselves
(`root/core/cont/src/TRefTable.cxx:248-262`).

## 5. Entry selections

Three classes, none reached from the tree: each is a top-level key naming its
tree by string.

### 5.1 `TEntryList`

Class version 2 (`root/tree/tree/inc/TEntryList.h:125`). Members after the
`TNamed` base: `fLists`, `fNBlocks`, `fBlocks`, `fN`, `fEntriesToProcess`,
`fTreeName`, `fFileName`, `fReapply`
(`root/tree/tree/inc/TEntryList.h:31-49`). Exactly one of `fLists` and `fBlocks`
is set: `fLists` when the selection spans a chain, `fBlocks` for a single tree.

`fFileName` is a trap for anyone generating one. The three-argument constructor
takes the filename from the tree's open file and **prepends the process's working
directory** (`root/tree/tree/src/TEntryList.cxx:1311-1322`), so the absolute path
of the machine that wrote it ends up in the file. The four-argument form stores
the string verbatim; `ttree/tree-entrylist` uses it for that reason.

### 5.2 `TEntryListBlock` — two encodings

Each block covers 64000 entries. Class version 1
(`root/tree/tree/inc/TEntryListBlock.h:80`); members after the `TObject` base are
`fNPassed`, `fN`, `fIndices` (`UShort_t[fN]`), `fType` and `fPassing`
(`root/tree/tree/inc/TEntryListBlock.h:46-51`).

**`fType` 0 — a bit vector.** `fN` is always 4000. Entry *e* of the block is
selected iff bit `e % 16` of `fIndices[e / 16]` is set — **least significant bit
first** (`root/tree/tree/src/TEntryListBlock.cxx:203-205`). Each word is a
16-bit big-endian integer, so the bit order within a word runs opposite to the
byte order. `ttree/tree-entrylist`'s `dense` list, holding every third entry from
0 to 99, begins `92 49 49 24 24 92` — `0x9249` is bits 0, 3, 6, 9, 12 and 15.

**`fType` 1 — a sorted array.** `fN` equals `fNPassed` and `fIndices` holds local
entry numbers. If `fPassing` is true they are the entries **in** the selection;
if false they are the entries **absent** from it, and the number selected is
`64000 − fNPassed`.

The writer converts from bits to array only when fewer than 4000 or more than
60000 of the 64000 entries pass, flipping `fPassing` in the second case
(`root/tree/tree/src/TEntryListBlock.cxx:546-556`). A reader must handle both
encodings regardless: only the last block of a multi-block list is left in bit
form unless `OptimizeStorage` is called explicitly.

### 5.3 `TEventList`

The older and simpler form. Class version 4
(`root/tree/tree/inc/TEventList.h:77`); after the `TNamed` base come `fN`,
`fSize`, `fDelta`, `fReapply` and `fList` (`Long64_t[fN]`)
(`root/tree/tree/inc/TEventList.h:34-38`). `fSize` is the allocated size and can
exceed `fN`; only `fN` values are written.

Its `Streamer` is hand-written for one reason: class version 1 stored the entry
numbers as 32-bit `Int_t` and had no `fReapply`
(`root/tree/tree/src/TEventList.cxx:411-424`).

`fList` **does** carry the one-byte is-present flag of an ordinary `[fN]` member,
which is the contrast with `TTreeIndex` (§2). Both are in
`ttree/tree-entrylist` and `ttree/tree-index` respectively, three records apart.

## 6. `TNtuple` and `TNtupleD`

Each adds exactly one persistent `Int_t`, `fNvar`, after the `TTree` base
(`root/tree/tree/inc/TNtuple.h:31`, `root/tree/tree/inc/TNtupleD.h:31`); `fArgs`
is transient. Class versions 2 and 1
(`root/tree/tree/inc/TNtuple.h:61`, `root/tree/tree/inc/TNtupleD.h:58`).

Their branches are ordinary single-leaf `TBranch`es with `TLeafF` and `TLeafD`
leaves. On disk a `TNtuple` is a `TTree` record with one trailing `Int_t`, which
is why [TTree §1](TTree.md#1-finding-the-trees-in-a-file) insists that trees are
found through the base-class chain and not by comparing a key's class name
against `TTree`.

Both `Streamer`s are hand-written and differ from the generated one only on the
read side: `TNtuple`'s has a class-version-1 path, and both re-point the first
`fNvar` branches at their `fArgs` array after reading.

## 7. `TChain`

A `TChain` can be written to a file and read back. Class version 5
(`root/tree/tree/inc/TChain.h:175`). Members after the `TTree` base:
`fTreeOffsetLen`, `fNtrees`, `fTreeOffset` (`Long64_t[fTreeOffsetLen]`),
`fFiles` and `fStatus` (`root/tree/tree/inc/TChain.h:36-44`).

`fFiles` and `fStatus` are declared `->`, so they are streamed **inline** — a
byte count and version with no class tag — while their contents carry tags
normally. `fFiles` holds `TChainElement`s, class version 2, whose `fName` is the
**tree** name and `fTitle` the **file** name
(`root/tree/tree/inc/TChainElement.h:36-39`).

An entry count of `0x7FFFFFFFFFFFFFFF` in `fTreeOffset` or in a `TChainElement`'s
`fEntries` is the *unknown* sentinel: `TChain::Add` records it until something
forces the member files to be opened.

Class versions 1 and 2 have a different order and, in version 1, no `fStatus` and
no `fTreeOffset` at all (`root/tree/tree/src/TChain.cxx:3036-3048`). No fixture
covers a `TChain`; the shape above is from the source.

## 8. Invariants

1. A `TTreeIndex`'s three arrays each hold exactly `fN` values, and `fN` is not
   negative.
2. A `TTreeIndex`'s `fIndexValues` is non-decreasing — it is the sort key.
3. Every entry number in a `TTreeIndex`'s `fIndex` is in `[0, fEntries)` of the
   tree that points at it.
4. A `TFriendElement` has a non-empty `fTreeName`.
5. A `TBranchRef`'s name is `TRefTable`.
6. A `TEntryListBlock` with `fType` 0 has `fN` 4000; one with `fType` 1 has
   `fN == fNPassed`.
7. A `TEventList`'s `fList` holds `fN` values and `fN <= fSize`.

Invariants 1, 2, 3 and 5 are confirmed by corrupting `ttree/tree-index` and
`ttree/tree-branchref` and checking that the intended invariant is what rejects
the result.

Invariant 1 deserves a note, because it is the only redundancy a `TTreeIndex`
has. Its three arrays carry no count of their own, so a wrong `fN` is invisible
*inside* the object — the reader simply reads fewer values. What catches it is
the frame's byte count: the three arrays must fill the object exactly, and a
reader should check that they do. Nothing else in the object can.

Invariants 6 and 7 cannot be reached by corruption. `fN` in a
`TEntryListBlock` and in a `TEventList` is the length prefix of a streamer-info
`[fN]` member, so changing it desynchronises the record and the byte count of
[Buffer §6](../02-serialization/Buffer.md#6-object-slots) rejects the file
first. Invariant 4 is the same: `fTreeName` is a counted string.

## 9. Errata

| # | Claim | Correction |
|---|---|---|
| 1 | `root/io/doc/TFile/ttree.md:27-28` presents the tree index as `TArrayD fIndexValues` and `TArrayI fIndex` | Those members still exist and are still written, but they have been dead since ROOT 4 and are discarded on read with a warning (`root/tree/tree/src/TTree.cxx:9840-9844`). The live index is `fTreeIndex`, a class `ttree.md` does not mention (§2.1) |
| 2 | `root/io/doc/TFile/ttree.md:29` ends the `TTree` member list at `fFriends` | Three members follow it in class version 20, two of them pointers this document is about: `fTreeIndex` before it and `fUserInfo` and `fBranchRef` after ([TTree §2](TTree.md#2-layout)) |
| 3 | `root/io/doc/TFile/README.md:267-271`: "For each branch, exactly one TBasket object is contained in the TTree data record" | Wrong in both directions. `TTree::Write` flushes every branch's basket to its own record first, so the tree record usually contains none; and `fBranchRef` is skipped by that flush, so it can have zero baskets anywhere (§4) |
| 4 | Nothing in `root/io/doc/TFile/` documents any class in this document | `tref.md` describes the `TRef` object without naming the `TRefTable` that makes it resolvable inside a tree, so the shipped documentation says how to read a reference and not how to follow one |

## 10. Reference files

| Case | What it covers |
|---|---|
| `ttree/tree-index` | §2 in full: a `TTreeIndex` with a real permutation, and the absence of its streamer info from the same file |
| `ttree/tree-friend` | §3: two friends in the parent's own file, one plain and one with an alias, so `fName` and `fTreeName` differ |
| `ttree/tree-branchref` | §4: a `TBranchRef` with a flushed basket, its hard-coded compression, and the byte-sum it contributes outside `fBranches` |
| `ttree/tree-entrylist` | §5: both `TEntryListBlock` encodings and a `TEventList`, in one file |
| `ttree/tree-ntuple` | §6: a `TNtuple` and a `TNtupleD` side by side |

Not covered: `TChain` and `TChainElement` (§7), `TChainIndex`,
`TEntryListArray`, a cross-file `TFriendElement`, and a `TTreeIndex` of class
version 1. A cross-file friend and a `TChain` both record a path that must exist
when the file is read, which makes them awkward as committed fixtures; that is a
decision recorded in `PLAN.md` §9.11 rather than a gap in the format.
