# Changelog

Versions are the *specification's*, not ROOT's. Each release says which ROOT
release it is descriptive of; where the two disagree, ROOT is right and this has a
bug ([spec/index.md](spec/index.md)).

This file records what changed for a **reader**. The git log records how each fact
was established, which is the other half of the story.

## Unreleased

- **The RNTuple type mapping is audited for the stdlib types and for user-defined
  classes and enums**, with two new fixtures — `rntuple/collections` (fourteen
  stdlib types) and `rntuple/user-class` (a struct with a base class, two enums, a
  vector of itself and a transient member) — and a test per subsection of the
  tracked specification, parsing each claim out of the document rather than
  transcribing it. Two new errata: **7**, `Double32_t` keeps a `SplitReal32` column
  in an uncompressed ntuple where every other default drops to unsplit; **8**, the
  field record's `Type Version` is a signed class version in an unsigned word, so a
  class with no `ClassDef` arrives as 0xFFFFFFFF.

- **Every branch-basket in the two corpora that any reader could decode is now
  decoded and checked**: 27969 of 28036, 99.8%, and 1696 of 1696 over the files
  the ROOT team published. The entry decoder reads a basket kept inside the
  `TTree` record rather than written as its own key, which is most of a file
  written through `TDirectory::WriteTObject`. The 67 that remain are a collection
  whose value class has no streamer info in its file, and a class with a
  hand-written `Streamer` — neither is unimplemented.
- **`ReadingEntries.md` §4.1: resolve a counted array's counter branch by name
  among the branch's siblings**, not through the recorded `fBranchCount`. ROOT
  looks the name up over the whole tree, so a tree holding two split objects of
  one class records the first object's counter on both — and reads no data for the
  second. Erratum 6 has the witness: `alice_ESDs.root`, where ROOT reads 0 indices
  for entries holding 18, 22, 6 and 13.
- **`ReadingEntries.md` §4.2: a container's member needs one count per object.**
  For `fType` 31 or 41 whose element is `T *x; //[n]`, the entry is one flag byte
  then that object's values, per object, with the counts held as a column in the
  sibling branch. Nothing in the file points from the member to that branch.

## 0.1.0 — 2026-09-17

First release. Descriptive of **ROOT 6.40.04**, pinned as the `root/` submodule.

Enough to implement a reader: locate any object in a ROOT file, decompress it,
read the file's own streamer information, decode any class the generic algorithm
covers — including every ordinary user-defined class — handle the classes it does
not, and read an entry out of a split or an unsplit `TTree`.

### The specification

- **Container** — the file header and the large-file variants past 2 GB, records
  and keys, directories and key lists, the free-segment list, and compression
  including the five codecs and multi-block payloads.
- **Serialization** — buffer framing and the object map, streamer information,
  the 60-odd element type codes, the streamer-info-driven reading algorithm,
  collections, schema evolution, and references.
- **Standard classes** — the divergent set: the classes whose recorded streamer
  information does **not** describe their bytes. Ten narrow ones remain, of which
  one (`TASImage`) occurs anywhere in the corpora.
- **`TTree`** — the tree record, `TBranch` including class versions 6 to 9,
  the `TLeaf` family, `TBasket` and its embedded form, splitting, and reading one
  entry through all eleven split procedures.
- **RNTuple** — ROOT's own specification tracked byte for byte, plus six errata
  from auditing it. The type mapping is partly audited.
- **Appendix** — a reader's checklist as a work order, 45 pitfalls, the bootstrap
  class set, the two class lists that cannot be derived from a file, a glossary,
  and a bibliography of the prior art.

### What backs it

- **65 reference files** with **1563 byte-level assertions**, checkable with
  nothing but Python, and meant to be vendored as test vectors.
- **1134 source citations** across 40 documents, each checked to exist at the
  pinned commit; 25 class-version claims checked against `ClassDef` itself.
- Per-layer **invariants** run over **226 ROOT files this project did not write**,
  from ROOT 2.24/00 to 6.36/02, at **0 failures**. 94% of their records decode and
  96.4% of their branch-baskets have their entries decoded and checked; what the
  rest is, and why, is named file by file rather than averaged away.
- An independent reference reader, `tools/rootfile.py`, written from the
  specification rather than from ROOT's code, so that the two disagreeing is a
  detectable event. It reproduces `TFile::Map()` exactly.

### Notable facts a reader will not find in ROOT's own documentation

- A **byte count is a lower bound, not a length**: three classes read further
  bytes after `ReadClassBuffer`, outside their own count, so `TMatrixTSym` cannot
  be skipped by it.
- **534 classes have a generated `Streamer` that writes only their bases** — no
  version word, no byte count, no members — and nothing in a file distinguishes
  them from an ordinary class. The list has to be carried out of band, and three
  of them occur in real files.
- The **key width in a large file is not decided by the key's own offset** but by
  where the file ended when the key was built, so a wide key can hold a small
  offset.
- Below `TBranch` class version 10, `fEntries`, `fTotBytes` and `fZipBytes` are
  **doubles**, and `fBasketSeek`'s *is present* flag byte is a **width selector**.
- `fSeekParent` is unusable for parentage before ROOT 6.38, where it held the
  *top* directory's offset for every nested directory.

### Known gaps

`PLAN.md` §9 lists every one, and each is a missing witness rather than a missing
explanation. The largest: 920 branch-baskets whose basket is embedded in the
`TTree` record, which the entry decoder cannot yet fetch; `TASImage`; the RNTuple
type mapping; and the object layouts of files old enough to carry no streamer
information at all, which are out of scope by decision.
