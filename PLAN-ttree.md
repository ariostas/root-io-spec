# The `TTree` measurement record — formerly the phase 5 sub-plan

**This plan is discharged.** All four documents it ordered are written
(`TBranchElement.md`, `Splitting.md`, `ReadingEntries.md`, `Auxiliary.md`), all
fifteen fixtures exist, and `rootfile.TreeReader` decodes the split path.
`PLAN.md` §8 holds what is left of the project.

It is kept for three things that are still worth having: the **dispatch table**
(§2), the **measurement of both corpora** (§3) that the documents were written
against, the **open questions** of §8, and **what the decoder still cannot
reach** (§10). Sections 4, 6, 7 and 9 are consumed and are reduced to a line
each; the git log has them in full.

Written 2026-09-16 against the pinned submodule (`v6-40-04`) and measured over
178 corpus files — `gen/foreign/` (154) and `gen/cern/` (24 curated at the time).
Everything in §3 is a measurement, not an estimate.

## 1. Why this is the next thing

**6736 of 11157 branches in the two corpora are not `TBranch`.** They are spread
over 56 files. The specification covers the other 4422.

Every one of those 6736 carries a `TLeafElement`, which `TLeaf.md` §8 declines to
specify. So a reader built strictly from this specification today can walk a split
physics file, decode every record, and locate the right basket for an entry — and
cannot interpret a byte of it.

This also exposes a flaw in our own headline number. `coverage_probe.py` reports
99.9% of records decoded, but a split `TBranchElement` *decodes fine as a record*:
it is streamer-info driven like anything else (§3.1). The probe never reads values
out of a basket, so it has been structurally blind to exactly this gap. Fixing that
is §6, and it belongs to this work rather than before it.

## 2. What is actually being specified

Not a record layout — `TBranchElement::Streamer` reads through `ReadClassBuffer`
(`root/tree/tree/src/TBranchElement.cxx:6027-6028`), so the record is ordinary
streamer-driven data and `StreamerDriven.md` already covers it. What is unspecified
is **the dispatch**: which of nine procedures interprets the basket payload.

`root/tree/tree/src/TBranchElement.cxx:5772-5816` is the authority:

| Condition | Procedure | In corpus |
|---|---|---|
| `kDecomposedObj` set | `ReadLeavesMakeClass` | n/a — a reading mode, not on disk |
| `fType == 4` | `ReadLeavesCollection` | 84, in 16 files |
| `fType == 41` and `fSplitLevel >= 100` and the count branch is a `vector` | `ReadLeavesCollectionSplitVectorPtrMember` | **0** |
| `fType == 41` and `fSplitLevel >= 100` otherwise | `ReadLeavesCollectionSplitPtrMember` | **0** |
| `fType == 41` otherwise | `ReadLeavesCollectionMember` | 1503, in 16 files |
| `fType == 3` | `ReadLeavesClones` | 21, in 2 files |
| `fType == 31` | `ReadLeavesClonesMember` | 733, in 2 files |
| `fType < 0` | `ReadLeavesCustomStreamer` | 16, in 4 files |
| `fType == 0` and `fID == -1` | `ReadLeavesMember` | 216, in 25 files |
| `fType <= 2` and `fBranchCount` set | `ReadLeavesMemberBranchCount` | 16, in 2 files |
| `fType <= 2` and `fStreamerType == kCounter` (6) | `ReadLeavesMemberCounter` | 2, in 2 files |
| `fType <= 2` otherwise | `ReadLeavesMember` | 4143, in 31 files |
| anything else | `Fatal` | — |

`kSplitCollectionOfPointers` is 100 (`root/tree/tree/inc/TTree.h:310`); `kCounter`
is 6 (`root/core/meta/inc/TVirtualStreamerInfo.h:132`).

Two observations that shape everything below. First, the selector is *not* `fType`
alone: `fID`, `fSplitLevel`, `fStreamerType` and the presence of `fBranchCount` all
participate. Second, two of the eleven rows have **no coverage in 178 files**, so
they can only be reached by a fixture we write.

## 3. What the corpora contain

Measured by walking every record whose class derives from `TTree`, then every
`TBranch*` member at every depth.

### 3.1 Branch and leaf classes

| Class | Count | |
|---|---|---|
| `TBranch` | 4421 | specified |
| `TBranchElement` | 6734 | class version 10 (`root/tree/tree/inc/TBranchElement.h:255`) |
| `TBranchObject` | 2 | class version 1, carrying the only two `TLeafObject`s |
| `TBranchClones` | **0** | class version 2 |
| `TBranchSTL` | **0** | class version 1 |

Leaves on the 6736: `TLeafElement` 6472, `TLeafObject` 2. The remaining 262 have
**no leaf at all** — see §3.3.

`TBranchClones` and `TBranchSTL` appear in no file in either corpus and in no
file's `StreamerInfo`. **Both are reachable from a current ROOT** — resolved 2026-09-17
for the first and earlier for the second, see §10 — and each now has a fixture.

### 3.2 `fType`, and the two `fID` sentinels

| `fType` | Count | Meaning |
|---|---|---|
| 0 | 4220 | three different things — see below |
| 41 | 1503 | data member of a split STL collection's content |
| 31 | 733 | data member of a split `TClonesArray`'s content |
| 1 | 141 | base class of a split object |
| 4 | 84 | branch count of a split STL collection |
| 3 | 21 | branch count of a split `TClonesArray` |
| 2 | 16 | class-typed data member of a split object |
| −1 | 16 | unsplit object with a custom streamer when written |

`fType == 0` is overloaded, and `fID` disambiguates it:

| | Count | |
|---|---|---|
| `fID == -1` | 216 | unsplit top-level object; the data is in *this* branch's baskets |
| `fID == -2` | 170 | **split top-level node**; carries no data of its own |
| `fID >= 0` | 3834 | a data member of a split object; `fID` indexes the parent's streamer-info element list |

`fID == -2` also occurs on 6 of the 16 `fType == -1` branches. ROOT tests for it
directly (`root/tree/tree/src/TBranchElement.cxx:2279`,
`root/tree/tree/src/TBranchElement.cxx:3812`), but **the header's own note on
`fType` never mentions −2** (`root/tree/tree/inc/TBranchElement.h:67-78`, which
says only "`fID==-1` for the former"). That is an erratum for the document.

### 3.3 Two `fType` values have no leaf, and two reach theirs only by reference

No exceptions in 6736 branches:

| | `len(fLeaves)` | Has baskets |
|---|---|---|
| `fType` −1, 0, 31, 41 | exactly 1, written in place | yes |
| `fType` 1, 2 | **0** | **never** — 141/141 and 16/16 have `fWriteBasket == 0` |
| `fType` 3, 4 | exactly 1, **always a back-reference** | yes — 16/21 and 69/84 |

> **Corrected 2026-09-16.** The first version of this section said `fType` 3 and
> 4 have no leaf either. That came from a probe that counted only `fLeaves`
> entries written in full and silently dropped the ones that are references —
> which on a count branch is all of them. The invariant written from the wrong
> claim failed on 121 branches the first time it ran over the corpora, which is
> what caught it.

This is still the most consequential structural fact in the split half, and it is
why `ReadingEntries.md` cannot simply extend `TLeaf.md` §5:

- `fType` 1 and 2 are pure interior nodes. No leaf, no basket, no data.
- `fType` 3 and 4 are the count branches. Their single `fLeaves` entry is a
  four-byte back-reference to a copy inside a member leaf's `fLeafCount`, so a
  reader that ignores back-references sees no leaf at all. And the leaf is not
  how they are read anyway: `ReadLeavesClones`/`ReadLeavesCollection` take the
  count straight out of the basket payload.

There is also a writer-side wrinkle: ROOT synthesises a missing `TLeafElement` on
read when `fType == 0` and `fLeaves` is empty
(`root/tree/tree/src/TBranchElement.cxx:6037-6044`). No corpus file exercises it,
but a conforming reader has to, so it needs a hand-built fixture or an explicit
"unreachable in 6.40.04" note.

### 3.4 `fBranchCount` is a back-reference; `fBranchCount2` is always null

Both are declared `TBranchElement*` and both are persistent. Raw slot bytes across
all 6736:

| `fType` | `fBranchCount` | `fBranchCount2` |
|---|---|---|
| 31 | reference, 733/733 | null, 733/733 |
| 41 | reference, 1503/1503 | null, 1503/1503 |
| 0 | reference on 16, null on 4204 | null, 4220/4220 |
| −1, 1, 2, 3, 4 | null | null |

So `fBranchCount` is a **buffer back-reference tag**, the same mechanism as
`fLeaves` (`TTree.md` §5) and `fLeafCount` (`TLeaf.md` §3.1). That is now three
independent places where a `TTree` structure stores a four-byte map position rather
than an object, which makes it a pattern worth stating once and referring back to,
rather than a surprise in each document.

`fBranchCount2` is null in **all 6736**. The second-dimension path is unexercised
by 178 files and needs a fixture or a documented "writer never sets it" finding.

Note a tooling gap found here: `rootfile.py`'s decoder does not populate
`Value.reference` for this slot, so the reference has to be read from raw bytes
today (§6).

### 3.5 The name fields mean different things per `fType`

| Field | Non-empty when |
|---|---|
| `fClassName` | **always** — 6736/6736 |
| `fClonesName` | exactly `fType` 3 (21/21) and 4 (84/84); empty on all 6631 others |
| `fParentName` | empty on all 16 `fType == -1`, on all 386 `fType == 0` with `fID < 0`, on all 34 `fType == 4` with `fID < 0`, and on 16 of 21 `fType == 3` |
| `fMaximum` | non-zero on 19 of 21 `fType` 3, 42 of 84 `fType` 4, 2 of 4220 `fType` 0 |

`fClassName` is not one thing. On a `fType == 4` branch it depends on `fID`:

```
fID = -1   fClassName = vector<mu2e::TrkInfo>   fClonesName = mu2e::TrkInfo
           a top-level collection branch; fClassName is the collection type

fID = 11   fClassName = Evt                     fClonesName = Hit
           a collection *member* of a split parent; fClassName is the parent
           class, fID indexes `hits` within it, fClonesName is the value type
```

Both forms occur (34 and 50). A reader that assumes `fClassName` names the
branch's own type gets the second form wrong.

`fClassVersion` is non-negative on all 6734 — the writer stores its absolute value
(`root/tree/tree/src/TBranchElement.cxx:6053-6057`). 981 of them are **0**, meaning
the streamer info must be matched by `fCheckSum` instead; that hands off to
`StreamerInfo.md`.

### 3.6 Naming and titles

Sub-branch naming, measured against the parent's name:

| `fType` | `parent.child` | other prefix | unrelated |
|---|---|---|---|
| 41 | **1503 / 1503** | 0 | 0 |
| 31 | **733 / 733** | 0 | 0 |
| 0 | 1082 | 1978 | 774 |
| 1, 2, 3, 4 | ~0 | 40 | 171 |

So the `parent.child` rule is exact for collection and clones members and only a
tendency elsewhere. Branch names carry 1 dot (4096), 2 (1273) or 3 (75).

The count branch's title ends in `_` — `hits`, title `hits_` — and member leaves
name it in brackets: leaf titles like `x[hits_]`, `detector_id[vector<KM3NETDAQ::JDAQSuperFrame>_]`.
`BuildTitle` constructs both (`root/tree/tree/src/TBranchElement.cxx:1179`,
`:1189` appends the underscore, `:1218` writes the `[index]` form). This is the
link between a member branch and its count branch that survives in the file, and it
is what `Splitting.md` has to state.

### 3.7 `fSplitLevel`

Values seen: 0 (5670), 1 (192), 2 (30), 3 (213), 4 (18), 97 (3), 98 (322), 99 (286).
**Maximum 99 across both corpora.**

The field packs two things: `splitlevel % 100` is the depth countdown, and the
hundreds component flags a split collection of pointers
(`root/tree/tree/src/TBranchElement.cxx:333-334`). Since nothing reaches 100, the
two `...SplitPtrMember` procedures of §2 have **zero coverage in 178 files**, and
the sub-branches of a pointer collection — which would carry `fSplitLevel` of 100+ —
have never been seen by this project.

## 4. Revised document breakdown

Consumed. It dropped `Double32.md` as already-written and distributed — the
annotation grammar and the three encodings are `ElementTypes.md` §5.1-5.3, the
leaf classes and the 3-versus-4-byte asymmetry are `TLeaf.md` §7 — and scoped the
other four documents, all of which are now written.

`Auxiliary.md` had the surprise in it: `TTreeIndex`, `TFriendElement`,
`TEntryList`, `TEventList`, `TNtuple`, `TNtupleD` and `TChain` appear in **no
`StreamerInfo` in either corpus**. Only `TBranchRef` and `TRefTable` do (136
files each), so everything else there is fixture-generated with no independent
file to check against, and its invariants are weaker than the rest of the layer.

## 5. The fixture matrix

Ten cases for the split half, four for `Auxiliary.md`, and one the decoder
added afterwards. Each exercises something no
existing fixture does; the "covers" column names the rows of §2 and the facts of §3.

| Case under `gen/cases/ttree/` | Covers |
|---|---|
| ✅ `split-object` | `fType` 0 with `fID == -2` (the split node) and `fID >= 0` (members), `fType` 1 (base class, no leaf, no basket), one leaf per member. 46 assertions |
| ✅ `split-naming` | The same class under a plain branch name and one ending in a dot. The dot renames every sub-branch **and changes `fParentName`**, which ROOT's own source calls "very annoying" (`root/tree/tree/src/TBranchElement.cxx:476-480`). 26 assertions |
| ✅ `split-unsplit` | The *same* class at split level 0: `fType` 0 with `fID == -1`, and `fType` −1 with a custom streamer. Gives a same-data comparison against `split-object` |
| ✅ `split-clones` | A split `TClonesArray`: `fType` 3 (count, no leaf, has baskets, `fClonesName` and `fMaximum` set) and `fType` 31 (`fBranchCount` back-reference, `parent.child`) |
| `split-stl` | A split `std::vector<T>` member: `fType` 4 with `fID >= 0` (`fClassName` = the *parent*), `fType` 41, the `name_` title and `x[name_]` leaf titles |
| ✅ `split-stl-toplevel` | A top-level `std::vector<T>` branch: `fType` 4 with `fID == -1`, where `fClassName` is the collection type — the second meaning of §3.5 |
| ✅ `split-nested` | Class inside class inside vector: `fType` 2 (no leaf, no basket), an `fType` 4 count branch with `fType` 41 members, the `name_`/`[name_]` convention, and the table showing `fSplitLevel` is not a depth counter. 23 assertions |
| ✅ `split-counter` | `Int_t n; Float_t x[n];` inside a split object: `ReadLeavesMemberBranchCount` (16 in corpus) and `ReadLeavesMemberCounter` (2), `fBranchCount` on an `fType == 0` branch, and `fMaximum` recorded on the *counter*. 15 assertions |
| ✅ `split-ptr-collection` | `std::vector<T*>` at `kSplitCollectionOfPointers + n`: the only source anywhere of `fSplitLevel >= 100`, the two zero-coverage procedures, **and the only `TBranchSTL`**. 22 assertions |
| `split-branch-object` | `TBranchObject` + `TLeafObject`, the legacy pair the corpus has exactly two of |
| ✅ `split-double32` | A `Double32_t` member inside a split object, producing a `TLeafD32` **in a tree** — the corpus has the class in one file |
| ✅ `tree-index` | `TTreeIndex` via `BuildIndex`, and `fIndexValues`/`fIndex` non-empty (`TTree.md` §8.1) |
| ✅ `tree-friend` | `TFriendElement` via `AddFriend` |
| ✅ `tree-entrylist` | `TEntryList` and `TEventList` |
| ✅ `tree-branchref` | `TBranchRef`/`TRefTable` via `BranchRef` |
| ✅ `split-bitset` | Added after the matrix, by the decoder: a `std::bitset` member, which is an ordinary object-wise collection of `bool` here and *no bytes at all* before ROOT 6.08/06. 12 assertions |

All ten split cases need a `classes.h` and an ACLiC dictionary; `gen/common/README.md`
covers that, and on macOS the `SDKROOT` override in `CLAUDE.md` applies. Two
should be checked for round-trip readability by ROOT itself (`CLAUDE.md`, "a fixture
can also be one ROOT cannot read"): `split-ptr-collection`, because nothing in the
corpus is written that way, and `split-double32`.

Deliberately *not* in the matrix, pending §8, and how each turned out:
`TBranchSTL` ✅ (`split-ptr-collection`), `TBranchClones` ✅
(`ttree/branch-clones`, via the one `TTree::BranchOld` call site), a non-null
`fBranchCount2` ☐ (no file in 178 has one), a `fType == 0` branch with an empty
`fLeaves` ☐ (possibly dead defensive code, §8 item 6), and `fType` −1 ☐ (needs a
branch whose class has a hand-written `Streamer`). The two open ones are what
`TBranchElement.md` points here for.

## 6. Tooling

Consumed. `rootfile.py` grew the `TBranchElement` fields and `TreeReader`, and
`check_invariants.py` gained the layer's invariants, each corruption-tested.
One item is still open: `coverage_probe.py` measures record decoding only, so it
reports a split file as almost fully covered while its values are undecoded.
`check_invariants.py`'s `ENTRIES` line is the honest figure; moving it into the
probe would make it per file rather than per run.

## 7. Order

Consumed; the documents were written in the order this section set.

## 8. Questions to settle while writing

1. ~~**Is `TBranchSTL` reachable?**~~ **Resolved: yes.** A `std::vector<T*>`
   branched at `kSplitCollectionOfPointers + n` produces one, and
   `split-ptr-collection` is the fixture. `Splitting.md` §5 writes it up.
   ~~`TBranchClones` is still open.~~ **Also resolved: yes.**
   `TTree::BranchOld` on a class with a `TClonesArray*` member produces one, and
   `ttree/branch-clones` is the fixture. It is the only call site in ROOT
   (`root/tree/tree/src/TTree.cxx:2223`), and it makes the parent a
   `TBranchObject`, so the same file closes that gap too.
   [`TBranchElement.md` §13](spec/04-ttree/TBranchElement.md) writes it up: no
   `TBranch` base, ten of `TBranch`'s fields written individually, no streamer
   info anywhere, an `fBranchCount` that must be *read* rather than skipped
   because the sub-branches reference the classes it declares, and sub-branch
   names that lose the parent's prefix to a `&name[1]` ROOT's own comment calls
   wrong.

   It left one thing unfinished, recorded here rather than in a commit message:
   the count branch keeps its basket **embedded in the `TTree` record**, and
   `check_invariants.py` can only fetch a basket *record*, so four branch-baskets
   report `counter basket unavailable`. The bytes are present and `TBranch.md` §5
   specifies them; it is the one merely-unimplemented skip in the suite.
2. **Why is `fParentName` empty on 16 of 21 `fType == 3` branches** when their
   `fID >= 0`? Everywhere else the empty case lines up with `fID < 0` (§3.5).
3. **Does `fBranchCount`'s back-reference use the same map-position convention as
   `fLeaves` and `fLeafCount`?** Near-certain, but it is a byte-level claim and
   `CLAUDE.md`'s discipline says verify it rather than infer it.
4. ~~**What does `fMaximum` mean on an `fType` 3 or 4 branch?**~~ **Resolved:**
   it is the largest count the writer saw, it is checked against on read
   (`root/tree/tree/src/TBranchElement.cxx:4340`), and it lives on whichever
   branch holds the count — which `split-counter` showed includes a `kCounter`
   branch, not only `fType` 3 and 4. Still open: why it is zero on half the
   `fType == 4` branches in the corpora.
5. **`fClassVersion == 0`** on 981 branches — confirm the `fCheckSum` fallback is
   exactly the `StreamerInfo.md` rule, and cross-reference rather than restate.
6. **Can a `fType == 0` branch with an empty `fLeaves` actually be written**, or is
   `root/tree/tree/src/TBranchElement.cxx:6037-6044` dead defensive code? If it is
   dead, that is an errata row; if not, it is a fixture.

## 9. Done criteria

Met, bar the one tooling item in §6. Every row of the §2 dispatch table is now
reachable from a fixture, including the two with zero corpus coverage.

## 10. What the decoder found, and what it left

Written after tooling 2 landed, because a reader is only a completeness check if
what it could not read is recorded as plainly as what it could.

**Found, and now specified:**

- The header of `ReadingEntries.md` §5.3 is shared across a whole *column*, not
  written per value — for `kStreamer`, `kSTL` and `kStreamLoop` alike, and a
  member-wise column shares its value-class version word too. Nothing anywhere
  said so; it is errata rows 4 and 5 there.
- A column of `std::string` is the shared frame and then *n* bare counted
  strings, with no count of their own.
- A `std::bitset` member is an ordinary object-wise collection of `bool` —
  except before ROOT 6.08/06, where the branch was written with no bytes in it
  at all. `ttree/split-bitset` pins the modern form and fixes the bit order,
  which its third entry is needed to settle; `uproot-mc10events.root` (ROOT
  6.08/04) is the empty form.
- `StreamerDriven.md` §7 claimed that for a user-defined class the streamer info
  is authoritative. That is false and is now corrected there: KM3NeT's Jpp DAQ
  classes have hand-written `Streamer`s and their recorded infos are fiction.
  `gen/foreign/IGNORE.toml` gained a `custom_streamer` key for exactly this — it
  supplies the out-of-band list §7 says a reader needs, and suppresses no
  invariant.

**Left, in order of how much of the corpora they account for:**

1. ~~**`pair<K,V>` whose members are not fundamental types**~~ ✅ Closed, 34
   branch-baskets to 0. The six member shapes are byte-verified in
   `serialization/pairs` and written up as `Collections.md` §8.1, and the reader
   now looks a pair up in the file before synthesising one — which §8 had said
   was never possible. It also turned up the empty member-wise collection
   (§4.3) and the shared pair checksum (§8.2).
2. **A collection whose value class has no streamer info in the file** — 49,
   the largest group and not a gap at all.
   `Collections.md` §9 already says this is unreadable by anyone, ROOT included.
   Nothing to fix; it stays a skip.
3. **`fType` −1**, a branch whose class writes its own `Streamer` — 9, plus 9
   more on the Jpp classes of `gen/foreign/IGNORE.toml`. Still no fixture; still
   needs a class with a hand-written `Streamer`.
4. **A basket whose record could not be read** — 7, all of them a missing
   codec or a counter branch whose own basket was unavailable.
5. **`kStreamLoop` contents.** The column's *extent* is checked from its byte
   count, but its values need the per-element counts from a sibling branch's
   column. 4 branch-baskets, all in one file.
6. **`TBranchSTL` entries.** `split-ptr-collection` has one and it holds data,
   but it is not a `TBranchElement` and has no leaf, so neither entry check
   reaches it. `Splitting.md` §5 describes the branch; its entries are undecoded.
