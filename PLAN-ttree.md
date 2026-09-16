# Phase 5 sub-plan — the split half of `spec/04-ttree/`

`PLAN.md` §7 item 5. Written 2026-09-16 against the pinned submodule (`v6-40-04`)
and measured against both corpora — `gen/foreign/` (§9.8, 154 files) and
`gen/cern/` (§9.9, 24 files), 178 files in total. Uncurated downloads left in
`build/cern/` are excluded: the 48 `TGeoManager` demos `gen/cern/README.md`
deliberately does not list hold one tree and one plain `TBranch` between them.

Phase 5 closed the unsplit reading path: `TTree.md` → `TBranch.md` → `TBasket.md`
→ `TLeaf.md`, checked end to end by `rootfile.entry_spans`. What is left is the
*split* path, and it is the larger half. This plan exists because "write
`TBranchElement.md`" is not a plan: `fType` alone selects nine different read
algorithms, and until they were counted there was no way to order the work or size
the fixture matrix.

Everything in §3 is a measurement over the 178 corpus files, not an estimate.

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
file's `StreamerInfo`. Whether they are still reachable from a current ROOT is an
open question (§8).

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

`PLAN.md` §2.5 listed five remaining documents. This drops one and re-scopes the
rest.

| Document | Status | Scope |
|---|---|---|
| ✅ `TBranchElement.md` | **written** | The member table, the `fType`/`fID` taxonomy (§3.2), the leaf bipartition (§3.3), `fBranchCount` as a back-reference (§3.4), the name fields (§3.5), and the dispatch table (§2) |
| ✅ `Splitting.md` | **written** | How a class becomes a branch tree, the `parent.child` rule, the `name_`/`[name_]` count convention, `fSplitLevel`'s two components, and what "unsplit fallback" means on disk |
| `ReadingEntries.md` | write | The end-to-end normative procedure, spanning the unsplit path already specified and the nine procedures of §2 |
| `Auxiliary.md` | write | `TTreeIndex`, `TFriendElement`, `TBranchRef`/`TRefTable`, `TEntryList`, `TEventList`, `TNtuple`/`TNtupleD`, `TChain` |
| ~~`Double32.md`~~ | **drop** | Already written, distributed. The annotation grammar and the three encodings are `ElementTypes.md` §5.1-5.3; the leaf classes and the 3-versus-4-byte asymmetry are `TLeaf.md` §7, with the `ttree/leaf-truncated` fixture. Per `PLAN.md` decision 6 this is a cross-reference from `TBranchElement.md`, not a fifth document |

`Auxiliary.md` is the one with a surprise in it: `TTreeIndex`, `TFriendElement`,
`TEntryList`, `TEventList`, `TNtuple`, `TNtupleD` and `TChain` appear in **no
`StreamerInfo` in either corpus**. Only `TBranchRef` and `TRefTable` do (136 files
each). Everything else there must be fixture-generated from scratch, with no
independent file to check against — so it should go last, and its invariants will
be weaker than the rest of the phase.

## 5. The fixture matrix

Ten cases for the split half, four for `Auxiliary.md`. Each exercises something no
existing fixture does; the "covers" column names the rows of §2 and the facts of §3.

| Case under `gen/cases/ttree/` | Covers |
|---|---|
| ✅ `split-object` | `fType` 0 with `fID == -2` (the split node) and `fID >= 0` (members), `fType` 1 (base class, no leaf, no basket), one leaf per member. 46 assertions |
| ✅ `split-naming` | The same class under a plain branch name and one ending in a dot. The dot renames every sub-branch **and changes `fParentName`**, which ROOT's own source calls "very annoying" (`root/tree/tree/src/TBranchElement.cxx:476-480`). 26 assertions |
| `split-unsplit` | The *same* class at split level 0: `fType` 0 with `fID == -1`, and `fType` −1 with a custom streamer. Gives a same-data comparison against `split-object` |
| `split-clones` | A split `TClonesArray`: `fType` 3 (count, no leaf, has baskets, `fClonesName` and `fMaximum` set) and `fType` 31 (`fBranchCount` back-reference, `parent.child`) |
| `split-stl` | A split `std::vector<T>` member: `fType` 4 with `fID >= 0` (`fClassName` = the *parent*), `fType` 41, the `name_` title and `x[name_]` leaf titles |
| `split-stl-toplevel` | A top-level `std::vector<T>` branch: `fType` 4 with `fID == -1`, where `fClassName` is the collection type — the second meaning of §3.5 |
| ✅ `split-nested` | Class inside class inside vector: `fType` 2 (no leaf, no basket), an `fType` 4 count branch with `fType` 41 members, the `name_`/`[name_]` convention, and the table showing `fSplitLevel` is not a depth counter. 23 assertions |
| ✅ `split-counter` | `Int_t n; Float_t x[n];` inside a split object: `ReadLeavesMemberBranchCount` (16 in corpus) and `ReadLeavesMemberCounter` (2), `fBranchCount` on an `fType == 0` branch, and `fMaximum` recorded on the *counter*. 15 assertions |
| ✅ `split-ptr-collection` | `std::vector<T*>` at `kSplitCollectionOfPointers + n`: the only source anywhere of `fSplitLevel >= 100`, the two zero-coverage procedures, **and the only `TBranchSTL`**. 22 assertions |
| `split-branch-object` | `TBranchObject` + `TLeafObject`, the legacy pair the corpus has exactly two of |
| `split-double32` | A `Double32_t` member inside a split object, producing a `TLeafD32` **in a tree** — the corpus has the class in one file |
| `tree-index` | `TTreeIndex` via `BuildIndex`, and `fIndexValues`/`fIndex` non-empty (`TTree.md` §8.1) |
| `tree-friend` | `TFriendElement` via `AddFriend` |
| `tree-entrylist` | `TEntryList` and `TEventList` |
| `tree-branchref` | `TBranchRef`/`TRefTable` via `BranchRef` |

All ten split cases need a `classes.h` and an ACLiC dictionary; `gen/common/README.md`
covers that, and on macOS the `SDKROOT` override in `CLAUDE.md` applies. Two
should be checked for round-trip readability by ROOT itself (`CLAUDE.md`, "a fixture
can also be one ROOT cannot read"): `split-ptr-collection`, because nothing in the
corpus is written that way, and `split-double32`.

Deliberately *not* in the matrix, pending §8: `TBranchClones`, `TBranchSTL`, a
non-null `fBranchCount2`, and a `fType == 0` branch with an empty `fLeaves`. Each
is unreachable from an ordinary current-ROOT write, so each needs a decision about
whether to specify it from source alone.

## 6. Tooling

In rough dependency order:

1. **`rootfile.py`: `Branch` grows the `TBranchElement` fields** — `fID`, `fType`,
   `fStreamerType`, `fClassName`, `fParentName`, `fClonesName`, `fCheckSum`,
   `fClassVersion`, `fMaximum`, and `fBranchCount` resolved as a back-reference.
   The decoder does not populate `Value.reference` for that slot today (§3.4); that
   is the first fix.
2. **`rootfile.py`: split entry reading.** `entry_spans` handles the leaf-driven
   path; the nine procedures of §2 need the equivalent, and four of the eight
   `fType` values have no leaf to drive it (§3.3).
3. **`coverage_probe.py`: an entry-reading mode.** Today it measures record
   decoding, which is why a split file scores 99.9% while being unreadable (§1).
   Until this exists the project has no honest number for the split path.
4. **`check_invariants.py`**: the new invariants, each corruption-tested against a
   fixture per `CLAUDE.md`. The measurements of §3 are the source — the leaf
   bipartition (§3.3), `fClonesName` iff `fType` ∈ {3, 4}, `fClassName` always
   non-empty, `fClassVersion >= 0`, `fBranchCount` set iff `fType` ∈ {31, 41} or a
   counted member, `parent.child` for `fType` 31 and 41.

Item 3 is the one that changes what we can claim. It should land with
`TBranchElement.md`, not after the phase.

## 7. Order

1. ✅ `TBranchElement.md`, with tooling 1 and the `split-object` fixture. The
   remaining fixtures of its row — `split-unsplit`, `split-clones`, `split-stl`,
   `split-stl-toplevel`, `split-branch-object` — are still to write, and each
   will extend rather than change the document; §13 there lists what they cover.
2. `Splitting.md`, with `split-nested`, `split-counter`, `split-ptr-collection`.
   It depends on `TBranchElement.md` for the vocabulary, and it is where the
   zero-coverage procedures get reached.
3. Tooling 2 and 3, then `split-double32`.
4. `ReadingEntries.md`. Last of the three, deliberately: written earlier it would
   duplicate `TBranch.md` §10 and `TLeaf.md` §5, and the §9.8 triage already showed
   what duplication costs.
5. `Auxiliary.md` and its four fixtures. Independent of 1–4 and separable if the
   phase needs to be cut short.

## 8. Questions to settle while writing

1. ~~**Is `TBranchSTL` reachable?**~~ **Resolved: yes.** A `std::vector<T*>`
   branched at `kSplitCollectionOfPointers + n` produces one, and
   `split-ptr-collection` is the fixture. `Splitting.md` §5 writes it up.
   `TBranchClones` is still open, still with zero occurrences in 178 files.
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

- The four documents written, each with Layout / Fields / Reading / Invariants /
  Errata / Reference files per `CLAUDE.md`.
- Every row of the §2 dispatch table reachable from at least one fixture, including
  the two with zero corpus coverage.
- `coverage_probe.py` reports an entry-reading figure, not only a record-decoding
  one, and the split path's number is stated honestly in `PLAN.md` §9.
- `rootfile.py` reads values out of a split branch for every `fType` in §3.2,
  checked against the fixtures' byte assertions.
- Every new invariant in `check_invariants.py`, each confirmed to catch a
  corruption, and both corpora still at 0 failures.
- `PLAN.md` §2.5 updated: `Double32.md` dropped with its cross-reference recorded,
  and §5 phase 5 marked complete.
