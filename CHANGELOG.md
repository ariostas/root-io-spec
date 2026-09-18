# Changelog

Versions are the *specification's*, not ROOT's. Each release says which ROOT
release it is descriptive of; where the two disagree, ROOT is right and this has a
bug ([spec/index.md](spec/index.md)).

This file records what changed for a **reader**. The git log records how each fact
was established, which is the other half of the story.

## Unreleased

- **A writing layer**, `spec/06-writing/`, which extends the project past the
  reading side it was scoped to: [an overview](spec/06-writing/index.md) of what a
  writing procedure is here and what is deliberately left out, and
  [Writing a file](spec/06-writing/WritingFiles.md) — the container in write order,
  with every field marked fixed, derived or free. What it adds that the reading
  documents could not: the **order** of operations, which is a property of no byte
  in the file; the ten container mistakes ROOT reads without complaint; and what
  omitting the `StreamerInfo` record costs. ROOT needs none for a class it has
  compiled in — measured, not assumed — and the warning that says so fires only
  when the file's `fVersion` differs from the running ROOT's, so a writer stamping
  the current release silences it.
- [Writing an object](spec/06-writing/WritingObjects.md): the two framings and the
  three classes that have neither, the version word of 0 a foreign class needs, the
  `TObject` base's masked `fBits`, the class and object maps with their two
  different mapping positions, ZLIB blocks, and the `StreamerInfo` record from
  `TList` down to each element subclass. `tools/test_write.py` builds that record
  for `TObjString` from the document and asserts it is **byte-identical** to the one
  ROOT wrote in `data/container/file-minimal.root`, checksum computed from scratch.
- **What "the current version" means**, new
  [Writing §3.1](spec/06-writing/index.md). ROOT writes one version per class and it
  is not a choice: both places a version word is emitted take the version compiled
  into the writing process, so a read-and-write **upgrades** — a ROOT 5.28 `TH1F`
  (`TH1` 6, `TAxis` 9) comes back out of 6.40.04 as `TH1` 8, `TAxis` 10. Four cases
  put something else in the word: a foreign class writes 0 and a checksum, a
  version-0 class writes its 0 (and a forwarding streamer writes nothing), a
  member-wise collection sets `0x4000`, and an **emulated** class carries the
  version the file it came from declared. And a copy is not a write: `hadd` moves
  basket records verbatim, so an older ROOT's records survive into a new file at
  their original versions.
- **The same class at the same version can carry two different checksums with an
  identical layout** ([StreamerInfo §11](spec/02-serialization/StreamerInfo.md)):
  `TAttAxis` 4 is `0x532a3b8c` in a ROOT 5.28 file and `0x5c6fff3e` today, because
  the old file spells its member types `Int_t` and `Float_t` where the new one
  resolves them. That is what the eight checksum variants are for, and why a
  mismatch at equal version is not evidence of a layout change.
- [A writer's invariants](spec/99-appendix/WriterInvariants.md): the 223
  `Invariants` entries of the whole specification re-sorted by the order a file is
  produced in, with one column the reading side never needed — **who notices a
  violation**: `tools/check_invariants.py`, ROOT, or nothing. §6 is the nine cases
  where the answer is nothing.
- The class-version tables of the two class-level writing documents are checked
  against `ClassDef`, taking `tools/check_versions.py` from 25 versions across 7
  documents to **40 across 9**.
- [Writing trees](spec/06-writing/WritingTrees.md): a flat `TTree` -- the basket
  records, the branch and leaf descriptions inside the tree record, and the fields
  that must agree with one another. **`data/written/tree.root` reproduces
  `data/ttree/basket.root` record for record**, both baskets and the `TTree`, keys
  included. Nine things a reader never needs: a basket's key version is **1004**
  whatever the file's size, and its `fKeylen` covers the 19-byte basket header; a
  basket is never in the key list; `fLeafCount` and `fLeaves` are **object
  references**, so the counter branch must be written first; a counter leaf's
  `fMaximum` must cover every count in the file or ROOT clamps the read;
  `fNevBufSize` means the entry stride or the offset array's capacity depending on
  the branch; `fBaskets` is `fWriteBasket + 1` slots of null; `fBranches` and
  `fLeaves` are member objects rather than pointers; `fMaxVirtualSize` must not be
  negative and `fWeight` must be 1.0; and `ROOT::TIOFeatures` has no `ClassDef`,
  so its version word is 0 and a checksum.
- [Writing histograms](spec/06-writing/WritingHistograms.md): `TH1F` and `TH1D`
  member by member at the current class version, with every field marked fixed,
  derived or free, and the fifteen `TStreamerInfo` records the chain needs.
  **Every object-bearing record in `data/written/histogram.root` is byte-identical
  to the one ROOT wrote in the new `data/classes/histogram.root`** — the `TH1F`'s
  596 bytes, the `TH1D`'s 651 and the `StreamerInfo` record's 9628. Four things a
  reader never has to know: the statistics are not derivable from the bin contents
  (`fEntries` counts fills, `fTsumw2` sums squared weights); `-1111` in `fMaximum`
  and `fMinimum` is a sentinel for "compute from the data"; `fFunctions` is
  streamed **in place** because it is declared `//->`; and the Y axis's
  `fTitleOffset` is 0 where X and Z carry 1.
- A new reading-side fixture, `classes/histogram`, with 73 assertions: the
  `TH1` -> `TAxis` -> `TAttAxis` hierarchy at byte level, a variable-bin-edge
  `fXbins`, and the statistics of five fills two of which went out of range.
  Nothing in the corpus carried the histogram chain before.
- **How far the checksum algorithm can be applied**, new
  [StreamerInfo §11.1 and §11.2](spec/02-serialization/StreamerInfo.md). Recomputing
  `fCheckSum` for every streamer info in every reference file gives 614 of 653
  exactly, and every failure has a named cause: an **enum** folds an extra 1 and is
  recognisable by `fType` 3 with a non-primitive `fTypeName` — which is the test
  ROOT's own checksum code uses; a **version-0 class** lists no members but folds
  them anyway; a member ROOT **rewrote for I/O** (`std::array`, `std::unique_ptr`)
  keeps its declared spelling in the checksum and not in the record; and three
  `pair` instances where ROOT's own value is wrong. This affects checking and
  writing a file, never decoding one.
- `tools/rootwrite.py`, a pure-Python writer built from those documents, and
  `tools/check_write.py`, which puts what it produces through three gates: this
  project's reader and every applicable invariant accept it; the bytes are
  reproduced exactly, since a writer has no reason to consult a clock; and ROOT
  opens it, returns the values that went in, and prints nothing. The third gate
  runs in CI. `data/written/objstring.root` is the first file in this repository
  that ROOT did not write — and ROOT reads it, appends to it and rewrites its free
  list without complaint.
- **The RNTuple type mapping is audited**, every form but one, with six fixtures
  and a test per subsection that parses each claim out of the tracked document
  rather than transcribing it: the stdlib types, user-defined classes and enums,
  projected fields and alias columns, `RNTupleCardinality`, untyped collections and
  records, ROOT streamed types, and the SoA layout — which sets the one field flag
  no fixture had reached. Only classes with an associated collection proxy are
  left. Four new errata: **7**, `Double32_t` keeps a `SplitReal32` column in an
  uncompressed ntuple where every other default drops to unsplit; **8**, the field
  record's `Type Version` is a signed class version in an unsigned word, so a class
  with no `ClassDef` arrives as 0xFFFFFFFF; **9**, the extra type information's
  content is a length-prefixed string, four bytes the record's layout does not
  show; **10**, that record lives in the **footer's** schema extension and never in
  the header where the document introduces it, so a reader looking there finds no
  streamer info on any file with a streamed field.
- `tools/rootfile.py` reads the header envelope's alias column and extra type
  information lists, and both version words of a field record.

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
