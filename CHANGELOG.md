# Changelog

Releases are **CalVer**, `YYYY.MM.DD`, cut when the specification reaches a
milestone rather than on a schedule. The number is a date, not a compatibility
claim: the version that carries meaning is **ROOT's**, and each release says which
ROOT release it is descriptive of. Where the two disagree, ROOT is right and this
has a bug ([spec/index.md](spec/index.md)).

This file records what changed for a **reader**. The git log records how each fact
was established, which is the other half of the story.

## 2026.09.24

First release. Descriptive of **ROOT 6.40.04**, pinned as the `root/` submodule
at `v6-40-04`.

Enough to implement a reader: locate any object in a ROOT file, decompress it,
read the file's own streamer information, decode any class the generic algorithm
covers — including every ordinary user-defined class — handle the classes it does
not, and read an entry out of a split or an unsplit `TTree`. Enough, too, to
implement a writer whose files ROOT reads back.

### The specification

- **Container** — the file header and the large-file variants past 2 GB, records
  and keys, directories and key lists, the free-segment list, and compression
  including the five codecs and multi-block payloads.
- **Serialization** — buffer framing and the object map, streamer information,
  the 60-odd element type codes, the streamer-info-driven reading algorithm,
  collections, schema evolution, and references.
- **Standard classes** — the divergent set: the classes whose recorded streamer
  information does **not** describe their bytes. Twelve narrow ones remain, of
  which two (`TASImage` and `RooWorkspace::CodeRepo`) occur anywhere in the
  corpora.
- **`TTree`** — the tree record, `TBranch` including class versions 6 to 9,
  the `TLeaf` family, `TBasket` and its embedded form, splitting, and reading one
  entry out of a split or an unsplit tree.
- **Writing** — a file with subdirectories, reopening one to add to it, an object
  and its streamer info, `TH1F`, `TH1D`, `TH2F`, `TH2D`, `TProfile`, `TGraph`,
  `TGraphErrors`, and a flat `TTree` of any number of baskets per branch, all at
  the current version of each class; what a file must contain for a reader whose
  classes differ from the writer's; and the element lists of the thirty-five
  classes a writer has to describe.
- **RNTuple** — ROOT's own specification tracked byte for byte, plus thirteen
  errata from auditing every envelope, the linked attribute sets and the type
  mapping against ROOT's code.
- **Appendix** — a reader's checklist as a work order of eight milestones,
  forty-eight pitfalls, the bootstrap class set, the two class lists that cannot
  be derived from a file, the invariants a writer must satisfy, a glossary, and a
  bibliography of the prior art.

### What backs it

- **90 reference files** with **2330 byte-level assertions**, checkable with
  nothing but Python, and meant to be vendored as test vectors.
- **1861 source citations** across 49 documents, each checked to exist at the
  pinned commit; 64 class-version claims checked against `ClassDef` itself.
- **14 files this project wrote**, with 493 assertions of their own. Every record
  in them that has a ROOT-written counterpart is byte-identical to it, and five
  match a ROOT-written file in every byte but the timestamps, the file's name and
  the UUIDs. ROOT opens each one, finds the values that went in, and prints no
  diagnostics.
- Per-layer **invariants** run over **252 files this project did not write**, 180
  from uproot's regression corpus and 72 published by the ROOT team, from ROOT
  2.24/00 to 6.38/00, at **0 failures**. 95% of their records decode, and 99.5%
  of their 48501 branch-baskets have their entries decoded and checked; what the
  rest is, and why, is named file by file rather than averaged away. Eleven files
  of 1.3 GB to 15.9 GB are checked by range request.
- Every published invariant is checked by a tool, or has a stated reason in
  `gen/invariants.toml` why it is not.
- An independent reference reader, `tools/rootfile.py`, written from the
  specification rather than from ROOT's code, so that the two disagreeing is a
  detectable event. It reproduces `TFile::Map()` exactly.

### Notable facts a reader will not find in ROOT's own documentation

- A **byte count is a lower bound, not a length**: some classes read further
  bytes after `ReadClassBuffer`, outside their own count, so `TMatrixTSym` cannot
  be skipped by it.
- **534 classes have a generated `Streamer` that writes only their bases** — no
  version word, no byte count, no members — and nothing in a file distinguishes
  them from an ordinary class. The list has to be carried out of band.
- The **key width in a large file is not decided by the key's own offset** but by
  where the file ended when the key was built, so a wide key can hold a small
  offset.
- Below `TBranch` class version 10, `fEntries`, `fTotBytes` and `fZipBytes` are
  **doubles**, and `fBasketSeek`'s *is present* flag byte is a **width selector**.
- `fSeekParent` is unusable for parentage before ROOT 6.38, where it held the
  *top* directory's offset for every nested directory.
- ROOT itself **misreads a counted array** when a tree holds two split objects of
  one class without parent prefixes: in `alice_ESDs.root` it reads 0 indices for
  entries holding 18, 22, 6 and 13. A reader should resolve the counter among
  siblings.

### Known gaps

`PLAN.md` §9 lists every one, and each is a missing witness rather than a missing
explanation. The only two a file in either corpus reaches are `TASImage` and
`RooWorkspace::CodeRepo`. Files old enough to carry no streamer information at
all are out of scope by decision. The writing side is narrower than the reading
side; [Writing §4](spec/06-writing/index.md#4-what-is-not-specified) lists what
it does not cover.

### Changes since 2026-09-17

The site has been published from `main` throughout. If you read it or vendored a
reference file before this release, these entries say what a reader should now do
differently.

- **Every numbered reading procedure re-read against its own text and the
  source**; about fifty steps corrected. The ones a reader is most likely to act
  on:
  - [`Record.md`](spec/01-container/Record.md) §6: stop at `fEND`, and test for
    an unmarked free span before reading the word.
  - [`Compression.md`](spec/01-container/Compression.md) §8: the key list, the
    free list and directory records are **never** compressed.
  - [`Buffer.md`](spec/02-serialization/Buffer.md) §4.1: ROOT's "byte count at
    least 6" checksum guard in fact tests only that a byte count is present.
  - [`StreamerDriven.md`](spec/02-serialization/StreamerDriven.md) §9: codes 65
    and 66 are read by fixed rules, with no info; a class with a hand-written,
    forwarding or extending `Streamer` is read from its list, not its info.
  - [`Collections.md`](spec/02-serialization/Collections.md) §13: an empty
    member-wise collection has no columns; a set's value class is not a `pair`;
    an enum collection dispatches on `fCtype`.
  - [`References.md`](spec/02-serialization/References.md) §7: a `TRef` is 10
    bytes plus a `pidf` or a UUID string, and `fPidOffset` is added once.
  - [`StreamerInfo.md`](spec/02-serialization/StreamerInfo.md) §9.1: a base's
    checksum is in files from 5.34/19 on, not only ROOT 6.
  - [`ForwardingStreamers.md`](spec/99-appendix/ForwardingStreamers.md) §3:
    select bases by element class; a `TObject` base is code 66.
  - [`Containers.md`](spec/03-classes/Containers.md) §5: a `TExMap` has a bare
    `TObject` first, and a `TMap` at version 2 has `fName` but no `TObject`.
  - [`TBranchElement.md`](spec/04-ttree/TBranchElement.md) §9 and
    [`ReadingEntries.md`](spec/04-ttree/ReadingEntries.md) §7: find an `fType`
    ≤ 2 counter by name, not through `fBranchCount`; a counted member of a split
    container needs a second count per object.
  - [`TLeaf.md`](spec/04-ttree/TLeaf.md) §5: a `TLeafC` entry is one counted
    string, or nothing.

- **A split collection's leaf can be written in place.**
  [`TBranchElement.md`](spec/04-ttree/TBranchElement.md) invariant 5 said the leaf
  of an `fType` 3 or 4 branch is always a back-reference. It is one only because
  a sub-branch writes it first; a collection of a class with no data members has
  no sub-branch, and ROOT writes its leaf in place. A reader must accept both.
  New reference file `ttree/split-empty-collection`.
- [`WritingFiles.md`](spec/06-writing/WritingFiles.md) §7: the `StreamerInfo`
  key's `fTitle` is `"Doubly linked list"`, which makes its `fKeylen` 64.
- Wording a reader would act on: `FileHeader.md` §9 reads 75 bytes, not 100;
  `Directory.md` §8 says when selecting subdirectories by class name is safe;
  `-1111` in `fMinimum`/`fMaximum` is "fixed in practice" in
  `WritingHistograms.md` and `WritingGraphs.md`; `ElementLists.md`'s Extra column
  is not in disk order.

- **An STL array's `fArrayDim` of 0 does not mean a scalar.**
  [`StreamerInfo.md`](spec/02-serialization/StreamerInfo.md) §13 said invariant
  11 legitimately fails on files before ROOT 6.24/02. It does not: those files
  store `fArrayDim` 0 with a positive `fArrayLength`, which invariant 11 never
  tests. A reader must check `fArrayLength` too. The fix reached master only at
  6.25/02, so 6.25/01 files have the old form (§10).
- [`TBranch.md`](spec/04-ttree/TBranch.md) §13.1 is the layout of versions 6 to
  9, not of every version below 10; below 6 the order differs again.
- [`Record.md`](spec/01-container/Record.md) §3.4: the large-layout row of the
  key-version table (1002 to 1004) had been cut off from the table and did not
  render.

- **Ten more false statements corrected**, which the second review had filed as
  wording.
  - [`TLeaf.md`](spec/04-ttree/TLeaf.md) §7: `nbits` 32 is legal and uses the
    `0xffffffff` factor; a value outside `[2, 32]` is reset to 32.
  - [`Directory.md`](spec/01-container/Directory.md) invariant 4: only the top
    directory's `fNbytesName` is range-checked; a subdirectory's is its
    `fKeylen`, and a long title can take it past 10000.
  - [`Record.md`](spec/01-container/Record.md) §3.6: ROOT checks `fSeekPdir`
    only on key-list images, never on a record's own key.
  - [`Pitfalls.md`](spec/99-appendix/Pitfalls.md): `fType` 500 on a
    `TStreamerSTL` is in every ROOT-written file available, back to 3.04/02; 300
    comes from third-party writers.
  - [`StreamerDriven.md`](spec/02-serialization/StreamerDriven.md) §1: files
    before ROOT 6.30 have `0x03000000` in every element's `fBits`.
  - [`Buffer.md`](spec/02-serialization/Buffer.md) §2.1: an oversized byte count
    is written corrupt, and only then reported.
  - [`SchemaEvolution.md`](spec/02-serialization/SchemaEvolution.md) §3:
    checksum variants 4, 6 and 7 also cover 5.99/06.
  - [`ReadingEntries.md`](spec/04-ttree/ReadingEntries.md) §1: the unused last
    offset slot is not always 0.
  - [`References.md`](spec/02-serialization/References.md) §2.2: the process-id
    record comes first; the referenced object may not.
  - Smaller: `StreamerInfo.md` §6.1's version-1 row, `FileHeader.md`'s
    `fEND` comparison, `TBasket.md`'s constructor sentence, the Conventions
    definition of a free segment, and `RooFit.md`'s diagram reference.

- **Arithmetic and count slips corrected.**
  - [`ElementLists.md`](spec/06-writing/ElementLists.md) §4 and §8: a file of
    one `TObjString` carries that one info; §4's nine classes are needed by the
    histogram, tree and graph files, not by every file.
  - [`WritingObjects.md`](spec/06-writing/WritingObjects.md) §7.1: a
    `TStreamerInfo`'s `fTitle` is empty, not the class's comment.
  - [`WritingGraphs.md`](spec/06-writing/WritingGraphs.md): an empty
    `fFunctions` slot is 4 + 10 + 4 + 2 + 15 = 35 bytes (the class record is
    10); and the one-graph `StreamerInfo` record is 11708 bytes of payload,
    11772 with its key.
  - [`TTree.md`](spec/04-ttree/TTree.md) §1: in a `TNtuple`, `TTree`'s frame
    starts six bytes in, not four.
  - [`Splitting.md`](spec/04-ttree/Splitting.md) §5.1: the three `TIndArray`
    entries are 17, 15 and 16 bytes (byte counts 13, 11 and 12).

- **What the reader and writer code knew and the text did not**, from the second
  consistency review.
  - [`ReadingEntries.md`](spec/04-ttree/ReadingEntries.md) §3.7, new:
    back-references inside a basket entry. The object map starts afresh at every
    entry, and when a basket has a displacement array a reader MUST add the
    entry's `offset − displacement` to every class and object tag. ROOT does
    this correctly only for an entry a circular tree moved once; for one moved
    twice the file no longer records where it was written, and ROOT 6.40.04
    silently reads such an entry's object pointer as null. Report those entries
    as unreadable. New fixture `ttree/basket-displacement-refs`.
  - [`Splitting.md`](spec/04-ttree/Splitting.md) §3.1: a trailing dot changes
    the names below a split *object* but not below a top-level split
    *collection*, whose constructor drops it first: `Branch("v.", ...)` gives a
    count branch named `v`. New fixture `ttree/split-dotted-collection`.
  - [`WritingFiles.md`](spec/06-writing/WritingFiles.md) §9.1: on an update the
    free-segment record can come out shorter than it was sized, and ROOT pads
    it with zeros.
  - [`WritingTrees.md`](spec/06-writing/WritingTrees.md) §7.4: with a negative
    flush watermark, `fClusterSize` records one cluster per range.
  - [`ElementTypes.md`](spec/02-serialization/ElementTypes.md) §7.2: two
    legacy branches of ROOT's reader, code 81 before 3.02/08 and 85–87 in an
    info below version 3; no available file reaches either.

- **What the front pages and the appendix say about scope, corrected.**
  - [`ReaderChecklist.md`](spec/99-appendix/ReaderChecklist.md) §10: RooFit is
    in scope for anyone reading workspaces, plots or fit results, and `TBranch`
    versions 6 to 9 are specified; the page said to leave out both.
  - [`spec/index.md`](spec/index.md): the writing layer also covers graphs,
    subdirectories and updating a file, and ROOT's allocator and key order are
    specified (as ROOT's choice, marked free) rather than left out.
  - [`Pitfalls.md`](spec/99-appendix/Pitfalls.md): there are five string
    encodings, not four; `std::string` and `char*` members were missing.
  - Every count these pages quote is recomputed; several were stale, among them
    the reference files (87 and 14), the corpora (180, 72, and 273 in
    roottest), the RNTuple errata (thirteen) and the invariant entries (267).
    `tools/coverage_probe.py` now reads RNTuple anchors with the RNTuple reader.

- **Recorded late: the first outside review's corrections, and RooFit.** These
  landed on 2026-09-21 and 22 without an entry here; the second consistency
  review found the gap (`PLAN.md` §8.17).
  - [`RooFit.md`](spec/03-classes/RooFit.md), new: `RooRealVar`,
    `RooLinkedList`, `RooAbsBinning`, `RooRefArray` and `RooCategory` below class
    version 3, whose hand-written `Streamer`s their streamer infos do not
    describe. Without them a workspace, a plot or a fit result cannot be read.
  - [`SchemaEvolution.md`](spec/02-serialization/SchemaEvolution.md) §8.1: two
    infos for one class and checksum differ in `fBits` by session state
    (`kIsCompiled` or `kBuildOldUsed`), not by anything about the class. Ignore
    `fBits` when matching.
  - [`SchemaEvolution.md`](spec/02-serialization/SchemaEvolution.md) §3.1: an
    `fCheckSum` of 0 records a computation that failed. Treat the field as
    absent; never use it as a lookup key.
  - [`StreamerDriven.md`](spec/02-serialization/StreamerDriven.md) §6.2: a
    file whose `TTime` records have no `TTime` info was written wrongly, not by
    a ROOT that omits it: ROOT 6.40.04 writes the info, measured. A reader skips
    such a record by its byte count.
  - [`StreamerDriven.md`](spec/02-serialization/StreamerDriven.md) §6.1,
    replacing invariant 5: a class named as a base has an info in the same
    file, but an object-valued member's class need not, and whether it does
    depends on the member's framing, not on the class.
  - [`ElementTypes.md`](spec/02-serialization/ElementTypes.md) invariants 3 and
    4: 501 and 521 belong to `TStreamerLoop`, and `fArrayLength` is 0 on a
    counted pointer. Both invariants had said otherwise and neither was checked.
  - [`Collections.md`](spec/02-serialization/Collections.md) §3.1: a
    collection of pointers puts two frames in a row, the collection's and each
    object's class frame. It is not a doubled collection frame.

- **Procedures and invariants that contradicted their own documents**, from the
  second consistency review.
  - [`StreamerDriven.md`](spec/02-serialization/StreamerDriven.md) §9 step 3:
    501 is never on a `TStreamerSTL`, and the procedure now has the step for 501
    and 521 on a `TStreamerLoop` that it was missing.
  - [`SchemaEvolution.md`](spec/02-serialization/SchemaEvolution.md) §4,
    erratum 7: take a class's only streamer info for an unmatched version word
    **only when the word is 1**, as ROOT does. Any other unmatched version is
    skipped by its byte count. Taking the lone info for every version let two
    g4tools histograms read one frame off at every level and still end on their
    byte counts.
  - [`Collections.md`](spec/02-serialization/Collections.md) §13 step 5.1:
    there is no value-class version below `TStreamerInfo` version 8 (9 for a
    pointer to a collection), and at version 0 the checksum follows only when the
    value class is not itself version 0. §6 now cites both thresholds.
  - [`ReadingEntries.md`](spec/04-ttree/ReadingEntries.md) §1: every
    `TBranchElement` with a non-zero `fType` has an offset array, including an
    `Int_t` inside a split collection. The text said container nodes only.
  - [`ReadingEntries.md`](spec/04-ttree/ReadingEntries.md) §2 and §7, and
    [`TBranch.md`](spec/04-ttree/TBranch.md) §7: a `TBranchSTL` has
    sub-branches **and** reads its own baskets first.
  - [`StreamerInfo.md`](spec/02-serialization/StreamerInfo.md) §11: only a
    `TStreamerBase` folds `fBaseCheckSum` into the checksum; an STL base folds
    its name alone.
  - [`Buffer.md`](spec/02-serialization/Buffer.md) §4: a foreign class whose
    `Class_Version()` is 0 writes a checksum the version-0 rule does not expect.
  - [`ElementTypes.md`](spec/02-serialization/ElementTypes.md) invariant 4:
    `fArrayLength` is also positive for codes 81, 82 and 85 to 87, and on a
    `TStreamerSTL` counts the collections in the frame.
  - [`FreeSegments.md`](spec/01-container/FreeSegments.md) invariant 2: a
    recovered file's last `fLast` is `fEND + 1000000000`, not a multiple.
  - [`WritingTrees.md`](spec/06-writing/WritingTrees.md) invariant 4:
    `fMaxBaskets` is `max(fWriteBasket + 1, 10)`, as `TBranch.md` says.
  - Smaller corrections: `TMatrixTBase`'s `Streamer` is guarded
    ([`Matrix.md`](spec/03-classes/Matrix.md)); `TCollection` is a real frame
    that `TBtree` writes; a `TCanvas` has eight trailing bytes, not seven; nine
    RooFit classes have a hand-written `Streamer`, not five
    ([`RooFit.md`](spec/03-classes/RooFit.md)); `TClonesArray` version 3 is
    tested on two different bits (`Collections.md` erratum 14); the free list
    in `container/directories` is at 1755; a key image agrees with its record
    field by field, not byte for byte
    ([`WritingFiles.md`](spec/06-writing/WritingFiles.md) §14).

- **Nine wrong claims corrected, from the second consistency review.** Each is
  a statement a reader or writer following the text would act on.
  - [`Record.md`](spec/01-container/Record.md) §6 step 5: a payload is
    compressed if and only if `fObjlen > fNbytes - fKeylen`. The step said
    "if it differs", which rejects every RNTuple page longer than `fObjlen`.
  - [`Record.md`](spec/01-container/Record.md) §3.4 and §7: key version 2 is
    already in ROOT 2.24, version 3 runs from 4.00 to 5.06, and version 4 from
    5.08. Read the width from the key's own `fVersion`, not the release.
  - [`Record.md`](spec/01-container/Record.md) §3.11 and §7: a basket key is
    always in the large layout only from ROOT 4.02. Before, it follows the
    file's size like any other key.
  - [`WritingFiles.md`](spec/06-writing/WritingFiles.md) §5: a subdirectory
    key's `fKeylen` is `39 + len(name) + len(title)`, not 43.
  - [`WritingTrees.md`](spec/06-writing/WritingTrees.md) §3: the `TTree` members
    after `fWeight` are `fTimerInterval`, `fScanField`, `fUpdate`, in that
    order; the table had `fUpdate` before `fScanField`.
  - [`TBranch.md`](spec/04-ttree/TBranch.md) §2: the layout table had an
    erratum pasted in as a second row 16. There is no such member; it is
    erratum 17.
  - [`References.md`](spec/02-serialization/References.md) invariant 5: a
    `TRefArray` payload includes its byte count and version word, 6 bytes the
    formula left out.
  - [`RooFit.md`](spec/03-classes/RooFit.md) §4.2, erratum 6: `_proxyList` is a
    `TList` up to ROOT 5.30, a `TRefArray` in 5.32 – 5.34/05 and a `RooRefArray`
    from 5.34/06, not from 6.26; the `RooRefArray` form has one more frame. Key
    on the element's type name.
  - [`spec/index.md`](spec/index.md): RooFit is specified, and
    `RooWorkspace::CodeRepo` is the second specification gap a corpus file
    reaches, beside `TASImage`.

- **RNTuple linked attribute sets, audited.** The last section of the tracked
  RNTuple specification apart from the collection-proxy form, checked against a
  new fixture, `rntuple/attributes`, whose footer links two attribute sets.
  - [ERRATA 11](spec/05-rntuple/ERRATA.md): the footer's attribute set list
    exists only from format 1.0.1.0. An older footer ends after the cluster
    group list; read the list only when bytes remain before the checksum.
  - [ERRATA 12](spec/05-rntuple/ERRATA.md): a record's *Attribute Anchor
    Uncompressed Size* is 78, the whole anchor object: the byte count and class
    version of erratum 2 as well as the checksum. Do not compute 72 from the
    anchor schema.
  - [ERRATA 13](spec/05-rntuple/ERRATA.md): ROOT 6.40.04 refuses an attribute
    set with any field beyond `_rangeStart`, `_rangeLen` and `_userData`,
    whatever its minor version, although the document says such fields are to be
    ignored.
  - [NOTES 8](spec/05-rntuple/NOTES.md#8-linked-attribute-sets): the record's
    locator names the anchor key's payload, and that key is in no directory's key
    list, so the footer is the only way to a set. Entries are in commit order and
    may overlap; a zero-length range is stored. ROOT checks the three
    restrictions when writing and none of them when reading, so a reader that
    wants them checked must do it itself.

- **Layouts from ROOT's own test files, and a stricter entry figure.** Every
  failure the checks gave on `root/roottest/` was diagnosed; 32 remain, in 4
  files, three of them at fault.
  - [`ElementTypes.md`](spec/02-serialization/ElementTypes.md) §8.2, §8.3: `fType`
    521 (`kStreamLoop + kOffsetL`) is a real code for `T *m[N]; //[n]`, and
    before 5.16/00 a loop of pointers holds bare objects, not object slots.
  - [`Collections.md`](spec/02-serialization/Collections.md): in a member-wise
    block a counter is a column, one count per object (§4.1). Before 5.24/00 a
    multimap was stored as `fSTLtype` 4 and a multiset as 5; take the container
    from `fTypeName` (§1). A collection of an enum is read as the type `fCtype`
    names, and `Int_t` when it is 0, which it is before 6.36/00 (§7.1).
  - [`ReadingEntries.md`](spec/04-ttree/ReadingEntries.md): before 5.32/00 an
    empty entry of a split collection's member is 0 bytes (§3.2). A split
    `kStreamLoop` branch before 5.27/06 has no `fBranchCount`; find its counter
    by name (§4).
  - [`StreamerInfo.md`](spec/02-serialization/StreamerInfo.md) §7.3: before
    6.00/00 an element's `fTypeName` is spelled as declared, with typedefs, and
    can omit default template arguments or a namespace. The section gives the
    lookup order that resolves it.
  - [`TBranch.md`](spec/04-ttree/TBranch.md): a slot below `fWriteBasket` can hold
    a read-back copy of a written basket (§5.1); every basket is embedded when the
    tree had no file (§5); a fast-cloned split parent has `fEntryNumber` equal to
    `fEntries` (§7).
  - [`TBranchElement.md`](spec/04-ttree/TBranchElement.md) invariant 6 and
    [`Splitting.md`](spec/04-ttree/Splitting.md): an empty-base branch can be
    flushed; a split node of a class with no elements has no children and empty
    entries; a count branch's title need not match its name after a rename.
  - [`FileHeader.md`](spec/01-container/FileHeader.md) invariant 9: a large-file
    header can sit on a small file. Take the header layout from the flag and every
    other width from the structure's own version word.
  - [`Auxiliary.md`](spec/04-ttree/Auxiliary.md) §2.2: a copied `TTreeIndex` is
    not trimmed and can name entries the tree does not have; bounds-check them.
  - The entry figure counts every branch-basket once, failed or skipped included:
    48278 of 48501 over the corpora, 99.5%, where it was 99.8% of a smaller total.

- **Basket slots.**
  - [`TBranch.md`](spec/04-ttree/TBranch.md) §5.1: a slot of `fBaskets` below
    `fWriteBasket` may hold a basket that was read back from its record and
    streamed again, before 6.11/02. Its key's `fSeekKey` and `fNbytes` are the
    record's, and its data are the record's. A reader may use either copy;
    invariants 5 and 9 now allow it. [`TBasket.md`](spec/04-ttree/TBasket.md)
    §4.1: such a copy's key fields are not 0 and its `fObjlen` is not stale.
  - [`TBranch.md`](spec/04-ttree/TBranch.md) §5: a count branch of a tree made
    by `CloneTree`, `CopyTree` or `TChain::Merge` before 5.18/00 has one slot,
    not the two of the leafcount basket, because `TBranch::Reset` removes it.
  - [`TBranchElement.md`](spec/04-ttree/TBranchElement.md) invariant 6 exempts
    the empty-base branch of `TBranch.md` §9.2, which a writer flushes like any
    data branch: from 5.20/00 to 5.34/19 and in 6.00 and 6.01 it has
    `fWriteBasket` at least 1 and `fTotBytes` non-zero.

- **Smaller corrections.**
  - [`Collections.md`](spec/02-serialization/Collections.md) §11.3: a pointer to
    a collection (`vector<T>*`, `fSTLtype` 41) has no pointer tag and no null
    marker. It is written as the collection it points to, and a null pointer as
    an empty one. §11.1: a fixed array of collections carries the value class's
    version once, not once per element. The §6 note that ROOT's two readers
    disagree on `kSTLp` was wrong: `kSTLp` never reaches the action-based
    reader.
  - [`Compression.md`](spec/01-container/Compression.md) §9.1: a multi-page
    `RBlob` may open with a raw page, so its payload need not start with a block
    magic. Invariant 7 does not apply to an `RBlob`: a single page that
    compression shrank by 8 bytes or less stays compressed, and its checksum
    makes §1's test call it raw.
  - [`ElementLists.md`](spec/06-writing/ElementLists.md) invariant 3: a counter
    is 6 `kCounter` if it is an `Int_t`, and 13 if it is a `UInt_t`, which is
    never promoted.
  - [`Record.md`](spec/01-container/Record.md) §1: `uproot-issue261.root` breaks
    its chain with a key-list record whose `fNbytes` is too small, not with a
    hole between records.

- **Legacy layouts in ROOT's own old files, and four reader corrections.** Every
  failure the checks gave on ROOT-written files in `root/roottest/` older than
  ROOT 5, plus one in the foreign corpus, turned out to be a format fact the
  documents lacked or a claim scoped too widely. None was a fault in a file.
  - [`TBranch.md`](spec/04-ttree/TBranch.md): read an embedded basket from the
    `fBaskets` slot before looking at `fBasketSeek`, as ROOT does (§10 step 4,
    §5). Before 3.10/02, and before 5.21/02 for a top-level collection branch,
    `TBranchElement` left its three basket arrays unzeroed, so the elements above
    `fWriteBasket`, and `fBasketSeek` at an embedded slot, can hold heap garbage
    such as `0xBAADF00D` (new §13.4). The `fWriteBasket + 2` slot count is not a
    one-off: before 5.18/00 every split `TClonesArray` or collection count branch
    got a second, never-filled basket, which reaches disk while `fWriteBasket` is
    0 (§5, invariant 9). A basket in a slot above `fWriteBasket` holds no entries.
  - [`TBranch.md`](spec/04-ttree/TBranch.md) §9.2,
    [`TBranchElement.md`](spec/04-ttree/TBranchElement.md) §4,
    [`Splitting.md`](spec/04-ttree/Splitting.md) and
    [`ReadingEntries.md`](spec/04-ttree/ReadingEntries.md): before 6.02/00 and
    5.34/20, an empty base class of a top-level split object got a branch with no
    leaves and no children that still holds one framed object per entry. An
    `fType` 1 branch with no leaves is not necessarily empty.
  - [`TTree.md`](spec/04-ttree/TTree.md) §6.3: before 5.27/02, `fSavedBytes` was
    set from `fTotBytes`, not `fZipBytes`, so it can exceed `fZipBytes` in older
    files. The class version does not mark the change; only the file's release
    does.
  - [`TBranchElement.md`](spec/04-ttree/TBranchElement.md) §5.2: a branch's
    `fStreamerType` can also be 71, 91 or 320 against a stored 500 (a pointer to
    a collection, an array of such pointers, an array of collections), and
    current ROOT still writes them. Before 4.03/02 a `Bool_t` branch stores 11,
    which the element's read-time fixup turns into 18 and the branch's does not.
  - [`StreamerDriven.md`](spec/02-serialization/StreamerDriven.md) §3.2 and §9,
    [`ElementTypes.md`](spec/02-serialization/ElementTypes.md) §2.1 and §10, and
    [`TBranchElement.md`](spec/04-ttree/TBranchElement.md) §6: a counter is the
    element `fCountName` names, of code 3, 6 or 13, not only `kCounter`. An
    unsigned counter such as `TBits::fNbytes` is never promoted and keeps 13, and
    its branch has `fMaximum` 0.
  - [`TLeaf.md`](spec/04-ttree/TLeaf.md) §5.2 and §6: a counter can be an earlier
    leaf of the counted leaf's own branch, and need not have `fIsRange` set.
    Before 5.28 the counter lookup searched the whole tree. Find counters by
    following `fLeafCount`, as ROOT does.
  - [`Buffer.md`](spec/02-serialization/Buffer.md) §7,
    [`ElementTypes.md`](spec/02-serialization/ElementTypes.md) §2.3 and
    [`SchemaEvolution.md`](spec/02-serialization/SchemaEvolution.md):
    `kIsOnHeap` and `kNotDeleted` are masked out of a written `fBits` only since
    ROOT 6.30. Older files have them set.

- **Correction: six "ROOT 4" behaviours were g4tools.** Two files in the foreign
  corpus have headers claiming ROOT 4.00/00 but were written by g4tools, Geant4's
  own ROOT writer, and six claims rested on them alone. No ROOT-written file
  shows any of them, so each is now attributed to g4tools as something a reader
  should accept from a third-party writer: an STL element storing `fType` 300
  ([`StreamerInfo.md` §10.1](spec/02-serialization/StreamerInfo.md); ROOT has
  forced 500 on write since 4.00/01), `nfree` 0 in the header, `TArray` counters
  stored as `fType` 3, a `TSeqCollection` info listing `fSorted`,
  `fEntryOffsetLen` 1000 on a fixed-width branch, and `fBaskets` written at
  `fMaxBaskets` slots. Checking them found two more errors: `TBranch` invariant
  11.1 applies from class version 9, not 8, because ROOT 3.05 to 3.10 wrote
  version 8 with a flat `fMaxBaskets` of 1000; and ROOT 4.00/00 wrote `TTree`
  version 10, not 11.

- **Corrections from a consistency review of every document.** Each was checked
  against the pinned source and the bytes. Wrong section references and counts
  that disagreed with their own tables were also fixed, and are not listed.
  - [`Collections.md`](spec/02-serialization/Collections.md): a `TClonesArray`'s
    `nobjects` includes the empty slots before the last occupied one and excludes
    the free slots after it; the text had it the other way round. The set/multimap
    order changed while `TStreamerSTL` stayed at element version 3, so nothing in
    the element tells the two orders apart and the repair applies to every file.
  - [`ElementTypes.md`](spec/02-serialization/ElementTypes.md): a counter's
    `fType` is 6, 3 or 13, not any integer type, so a counter is always 4 bytes.
    `TStreamerInfo` class version 9 first shipped in 5.27/02, not 5.26, and the
    version word of a 500/501 frame reads 8 or less before that. No release writes
    365 as an `fType`. 500 on a `TStreamerSTLstring` is a collection, as on a
    `TStreamerSTL`.
  - [`StreamerInfo.md` §9.2](spec/02-serialization/StreamerInfo.md): in
    `hades.root` the base whose `fBaseVersion` fallback fails is `TGeoMaterial`,
    not `TGeoVolume`.
  - [`HandWrittenStreamers.md`](spec/99-appendix/HandWrittenStreamers.md),
    [`Bootstrap.md`](spec/99-appendix/Bootstrap.md) and
    [`StreamerDriven.md` §7](spec/02-serialization/StreamerDriven.md): a byte-count
    check does not always catch a class whose streamer info does not describe its
    bytes. `TArray*` and `TRef` write no byte count, an `extending` class's extra
    bytes lie outside it, and a mismatch may show on the enclosing object.
  - [`RooFit.md`](spec/03-classes/RooFit.md): five RooFit classes have a
    `Streamer` of their own, not six. `RooAbsBinning` does derive from `TNamed`
    and its streamer writes its declared bases; what most files lack is a
    `RooAbsBinning` info. It is reached from every `RooRealVar`, not every
    `RooAbsArg`. A `RooRealVar` info consumes 380 of the 440 bytes in
    `classes/roofit`, and following `RooLinkedList`'s info misreads `_size` as
    `_hashThresh`, not the `TObject` base. `RooWorkspace::CodeRepo` leaves a
    record partial rather than blocked.
  - [`TBasket.md`](spec/04-ttree/TBasket.md): a displacement array (`flag > 40`)
    does occur in files from current ROOT, from a circular tree
    (`MoveEntries`) or an object branch filled through `SetBufferAddress`, and
    shows in the flag only when embedded. `fIOBits` came with class version 3.
    With `kGenerateOffsetMap` a stored array reads as 0 followed by entry sizes.
  - [`TBranch.md`](spec/04-ttree/TBranch.md): `fBaskets` is all null only after
    `TTree::Write`; it can hold an embedded basket.
  - [`TBranchElement.md`](spec/04-ttree/TBranchElement.md): count branches of
    `fType` 3 and 4 have one leaf, a back-reference the read procedure ignores.
  - [`TLeaf.md`](spec/04-ttree/TLeaf.md): four leaf classes, not three, have an
    `fLenType` that differs from the on-disk width.
    [`ReadingEntries.md` §5.2](spec/04-ttree/ReadingEntries.md) now says how many
    members of `ttree/split-double32` each wrong width source misreads.
  - [`TTree.md`](spec/04-ttree/TTree.md): `fBranchRef`, `fFriends`, `fTreeIndex`
    and `fUserInfo` are not always null; three fixtures and `alice_ESDs.root`
    have them set.
  - [`Buffer.md` §6](spec/02-serialization/Buffer.md): ROOT 6.40.04 always writes
    a byte count before a new object in a slot; the two slot forms without one
    must still be accepted.
  - [`Conventions` §5.1.1](spec/00-conventions.md): `TString` and `TStringLong`
    differ in their length prefix at every length, not only below 255.
  - The writing documents: the `StreamerInfo` records of the histogram and tree
    cases now match ROOT's in full, `listOfRules` included. Emitting the rules
    stays optional. `WritingFiles.md`'s scope covers subdirectories and updating
    a file, and the unwritten header bytes are 63 to 99. `TGraph`'s `TAttFill`
    values are fixed by its constructor.
  - Corpus figures re-measured over the current corpora: free segments,
    directory records and cycles, the forwarding-streamer table, and
    `ElementTypes.md` invariant 3's counts.

- **Fix: `ElementLists.md` §8 and §9 were empty.** The element lists of
  `TObjString`, `TGraph` and `TGraphErrors` were counted but never rendered;
  they are published now ([`ElementLists.md`](spec/06-writing/ElementLists.md)).

- **Correction: ROOT does not write bare version words at the top of a record.**
  [`Buffer.md` §2.3](spec/02-serialization/Buffer.md) said a record from a file
  older than ROOT 5 may open an ordinary class with bare version words. Its only
  witnesses were two files written by g4tools, Geant4's own ROOT writer. Every
  record of every available ROOT-written file, back to ROOT 2, opens with a byte
  count. A reader still has to accept the g4tools shape, and the section now
  attributes it to g4tools.

- **New: an object with no byte count, and how to read it.**
  [`StreamerDriven.md` §7.1](spec/02-serialization/StreamerDriven.md) covers an
  object of a class deriving from `TObject` that has no byte count at all. Such an
  object was written by a hand-written `Streamer`. ROOT without the class's library
  assumes there is no version word either, and reads the elements from the first
  byte; its own classes it reads version first. The section gives the rule for
  choosing, which uses two tests: [`Buffer.md` §7](spec/02-serialization/Buffer.md)'s
  new invariant 10 (a `TObject` base's version word is always 1), and the extent
  that encloses the object. When neither reading passes both tests, no reader can
  decode the object.

- **New: a class that is itself a collection.**
  [`Collections.md` §11.2](spec/02-serialization/Collections.md) describes the
  one-element streamer info of a class with a collection proxy of its own, such as
  ATLAS's `DataVector`. The value class is in the `This` element's **title**, not
  in its type name. Read it as a `vector` of that type, whatever `fSTLtype` says,
  as ROOT does, and only when the type name is not an STL name. Invariant 10 no
  longer applies to such an element, and invariant 11 describes it. §5 also
  corrects which class `CanSplit` is asked about: the collection's, not the
  value's.

- **New: two large-file invariants cover ordinary keys and directories.**
  [`LargeFiles.md` §8](spec/01-container/LargeFiles.md) invariant 6 now covers
  every wide key: the key list's own key and each key image, not only the free
  record's. Invariant 7 states when a directory record is wide: if and only if one
  of its own three offsets passes 2 000 000 000. §6 adds what the eleven large
  files' top directories and key lists show:
  - keys with offsets past 4 GB;
  - narrow directory records in large files;
  - one key list mixing both key widths.

- **Correction: a `std::map` can be written to an RNTuple when it has a
  dictionary.** [`spec/05-rntuple/NOTES.md` §5](spec/05-rntuple/NOTES.md) said
  ROOT 6.40.04 cannot write one from the interpreter. It can, for the
  instantiations that have a compiled dictionary and only those, such as
  `map<string,int>` and `map<int,int>`. The others abort in `Fill()`. The
  `std::map` subsection's claim is now checked against bytes for all four types it
  names, `map`, `unordered_map`, `multimap` and `unordered_multimap`, in the new
  `rntuple/map` fixture.

- **New: two RNTuple page locators can name the same bytes.**
  [`spec/05-rntuple/NOTES.md` §7](spec/05-rntuple/NOTES.md): ROOT writes an
  identical page once and points every column that produced it at that copy.
  This is `EnableSamePageMerging`, on by default, and the tracked document never
  mentions it. A reader that goes through locators is unaffected, but nothing may
  assume that pages are disjoint.

- **Correction: a free span's marker can be missing in a file ROOT wrote.**
  [`FreeSegments.md` §4.2](spec/01-container/FreeSegments.md) said the marker is
  never missing in practice. RNTuple's `TFile` writer before ROOT 6.36 left it out
  whenever it put an `RBlob` in a free slot larger than the blob, and an ATLAS file
  written by 6.34/04 has one. A reader that walks the record chain by markers
  alone loses the chain there. The free list still has the span, so read the list
  first, from `fSeekFree`, and skip any span it names whatever the four bytes
  hold. §7 and [`Record.md` §6](spec/01-container/Record.md) now say so, and
  invariant 6 exempts that case and no other.

- **Correction: in a member-wise collection, a base class is one column per
  member.** [`Collections.md` §4.1](spec/02-serialization/Collections.md) said
  the base is read once per element. ROOT reads the base's own info over the whole
  array, so a base with members `a` and `b` is every `a`, then every `b`. The two
  readings disagree as soon as a base has two members, as ATLAS's `ElementLink`
  does. §4.2 also says how the base's info is chosen when its class has no
  version: by `fBaseCheckSum`.

- **Correction: three release boundaries were wrong.** Each is now read from the
  release tags in the pinned submodule, and each has a ROOT-written witness:
  - [`Directory.md` §7](spec/01-container/Directory.md): directory record version 1
    lasted until 3.03/06, version 2 was written by 3.03/07 alone, and version 3
    began at 3.03/08. The table said 3.02, 3.03/01–3.03/07 and 3.03/09. A reader
    that picks the UUID layout by ROOT release instead of by `version mod 1000`,
    as §7 requires, gets 3.03/01–3.03/06 wrong.
  - [`FileHeader.md` §8](spec/01-container/FileHeader.md): the header UUID arrived
    in 3.03/07, not 3.03/00. A 3.03/02 file has zeros there.
  - [`TLeaf.md` §7 and §12](spec/04-ttree/TLeaf.md): `TLeafF16` and `TLeafD32`
    version 2 is new in 6.38, not 6.40, so a 6.38 file's truncated leaves already
    carry the name and dimensions in the title.

- **Added: `TLeaf.md` §7 now says where a truncated leaf's counter comes from.**
  At version 1 the leaf title is the bare type spec even for a `[N]` array, so the
  counter survives only in `fLeafCount` and the branch title. A reader MUST take
  it from `fLeafCount`. Legacy leaf versions now have witnesses:
  `TLeaf` version 1 in a ROOT 2.23 file, which reads in version 2's field order as
  §12 says, and `TLeafF16`/`TLeafD32` version 1 in two corpus files.

- **Added: version 3 of `TStreamerElement` never shipped.**
  [`StreamerInfo.md` §7.1](spec/02-serialization/StreamerInfo.md): it existed for
  three days on the 4.03/05 development trunk in April 2005, so only a
  development build writes one. One such file is available, with 223 of them.

- **Added: what ROOT 2 files actually frame.**
  [`Buffer.md` §6.4 and §11](spec/02-serialization/Buffer.md): the two available
  ROOT 2 files byte-count their outer objects and write bases as bare version
  words, and neither ever reaches §6.4's legacy object map. That mode is still
  specified from the source alone, and the document now says no available file
  can test it.

- **Clarified: a base element's checksum may match any of its class's infos.**
  [`StreamerInfo.md`](spec/02-serialization/StreamerInfo.md) invariant 13.7 said a
  `TStreamerBase`'s `fMaxIndex[1]` is 0 or "that info's `fCheckSum`", as though a
  file held one info per class. It may hold several, at different versions, and
  the checksum identifies the one the derived class was built against (§9.2). A
  reader or checker that looks the base up by name and compares against whatever
  it finds rejects a correct file.

- **Correction: the list of records that do not open with a byte count was
  incomplete, and is now complete.**
  [`Buffer.md` §2.3](spec/02-serialization/Buffer.md) listed the container's
  bookkeeping, `TRef`, `RooLinkedList`, `TArray` and `TBasket`. It left out a
  `TDatime` stored as a record (four bytes: the packed date and nothing else),
  which a ROOT-written file in go-hep's test corpus contains, and which a reader
  following §2.3 rejects. Rather than add the one name, every hand-written
  `Streamer` of a class ROOT persists was read for what it writes first, and the
  list now includes all of them, grouped by shape:
  - a version word with no count: `TObject` and `TClassTree`, as well as those
    already listed;
  - no version word either: `TDatime`, `TString`, `TStringLong`, `TKey`;
  - nothing at all: `TQObject` and the three `graf2d/gviz` classes, whose record
    is a key with `fObjlen` 0.

  A `TObject` stored as a record is the 10-byte base alone, with one version word,
  not one for the class and another for a base.

- **Correction, for a reader of files from ROOT 6.34: an RNTuple blob key's
  `fSeekPdir` may name the key itself.**
  [`Record.md` §3.6](spec/01-container/Record.md) said `fSeekPdir` is 0 or a
  directory. RNTuple's writer for appending into an already-open `TFile` passed
  the key's own offset instead, until ROOT commit `5fe8a99942`, first released in
  6.36.00. A reader must accept such a key and must not follow the pointer. ROOT
  never does: it reaches RNTuple's bytes through the anchor and the page list.
  Files RNTuple wrote on its own were never affected.

- **Correction that changes what a correct reader does: a basket does not always
  use the large key layout.**
  [`TBasket.md` §1](spec/04-ttree/TBasket.md) said it always does, based on an
  unconditional `fVersion += 1000` in `TBasket`'s constructor. The line is real,
  but it arrived in ROOT 4.02 (commit `3970c0bead`, 2004-09-10, first production
  release 4.02/00). Before it, ROOT wrote small-form basket keys: 12 385 of them in
  19 files of `root/roottest/`, from 2.23/12 to 4.00/04. The error goes both ways.
  A reader that switches on file size reads `fSeekKey` four bytes short, and a
  reader that assumes the large form reads an older basket four bytes too wide.
  Take the width from the key's own `fVersion`, as
  [`Record.md` §2](spec/01-container/Record.md) requires of every other key. The
  commit message also gives the reason ROOT spends 8 bytes on every basket: a
  basket may be created long before a file passes 2 GB and written long after.

- **Correction, for a reader of RNTuple: a compressed page's block chain does not
  fill its record payload.** An `RBlob` does not hold one compressed object. It
  holds sealed pages, each `blocks || 8-byte XXH3-64 checksum`, and the checksum
  is appended after compression and counted outside `fObjLen`
  (`RPageStorage.cxx:751`). A page's chain therefore stops 8 bytes short, which
  [`Compression.md` §9](spec/01-container/Compression.md) invariant 1 as written
  forbade, and a blob holding several pages mixes raw with compressed data and
  cannot be walked from the container layer at all. The new
  [§9.1 *What an `RBlob` is not*](spec/01-container/Compression.md#91-what-an-rblob-is-not)
  describes this, and invariants 1, 3 and 5 are now scoped to say where they hold.
  An envelope still ends flush with its payload; only a page is short. The new
  `rntuple/compressed` fixture has both shapes in 1420 bytes. Page checksums are
  on by default, so this is the ordinary case. No fixture had seen it because all
  eight RNTuple generators wrote with compression off.

- **[Writing an object §8](spec/06-writing/WritingObjects.md) specifies schema
  evolution from the writing side**: what has to be in a file so that a reader
  whose version of a class is not the writer's can still read it. There is less to
  it than it seems, because `TStreamerInfo::BuildOld` matches each on-disk element
  to a member by name and nothing else. `fSize`, `fArrayDim` and `fMaxIndex` are
  never compared, and artificial and cache elements cannot reach disk at all. Six
  obligations remain, and §8.1 tabulates them.
- **The mistake to avoid is an incomplete closure**: an info for a derived class
  without one for its base. Measured: `BuildOld` skips the base, the class comes
  out 16 bytes instead of 24, and `CheckByteCount` reports the short read. The
  failure is reported only because the base's bytes carry their own byte count; a
  base whose bytes carry none, like `TObject`'s, would desynchronise without any
  message. The closure has one exemption: a class whose `Streamer` is hand-written
  or forwarding gets no info. Over the 90 files here that carry infos, the bases
  with no info are six classes, all on one of the two published lists.
- **One class may appear at two versions in one file, and ROOT produces such
  files itself.** Measured with two sessions: a file written at `ClassDef(C, 2)`
  and reopened by a session whose `C` is at version 3 ends up with both infos and
  two records of different lengths, silently and correctly. The plan for this work
  expected ROOT to discard one; it does not.
- **When the versions collide, the file wins and data is lost.** In the same
  experiment, the second session's class has a third member and still says
  `ClassDef(C, 2)`. ROOT warns at open ("Do not try to write objects with the
  current class definition") and then writes such an object anyway: it is 54
  bytes, not 58, and the third member never reaches the file. No later reader can
  tell. A writer should either bump the version or refuse to write.
- **ROOT cannot read an emulated class that derives from `TObject`**
  ([Schema evolution §7.1](spec/02-serialization/SchemaEvolution.md)). This is a
  silent data-loss path in ROOT, found by this project. `TKey::ReadObj` streams a
  `TObject`-derived object with `tobj->Streamer()`, which with no dictionary
  resolves to `TObject::Streamer`, reads ten bytes and stops. Measured on a file
  ROOT wrote itself: a class with `fA = 77` and `fB = 1.25` reads back as 0 and 0,
  and the only message is `no dictionary for class …`. This project's reader
  recovers both values from the same bytes. It affects only a top-level record
  (the same class as a *member* reads correctly), and it is why a writer should
  not derive its own persistent classes from `TObject`.
- **`listOfRules` is specified for writing, and emitting it completes the
  `StreamerInfo` comparison.** ROOT appends the rules of every class being written
  without regard to the version, so a `TTree` 20 file ships two rules for versions
  ≤ 16 and ≤ 18 that can never match its own data. ROOT never reads the list back,
  so a writer may omit it. This one emits it, and seven complete `StreamerInfo`
  records are now byte-identical to ROOT's (370, 9628, 11789, 12169, 14121, 14580
  and 14584 bytes), where four used to differ by that one entry.
  `FileWriter(emit_rules=False)` turns it off.
- **`fBaseVersion` may name a version the file has no info for**, so the fallback
  [Streamer information §9.1](spec/02-serialization/StreamerInfo.md) gives a
  reader is not enough. This was found by asserting the opposite as an invariant,
  which five files in the two corpora disproved at once. On
  `uproot-mc10events.root` (ROOT 6.08/04), `TTree`'s `TAttLine` base says version 1
  beside a version-2 info, and its `fBaseCheckSum` points at that version-2 info,
  so the checksum resolves it. On `aleph.root`, `atlas.root`, `cms.root` and
  `hades.root` (ROOT 5.17/09) the checksum is 0 and `fBaseVersion` is 4 where the
  file's only info for the base is version 5, so §9.1's fallback finds nothing.
  §9.2 adds the third step a reader needs: take the info the file does have for
  that class. A reader that stops earlier cannot decode a `TGeoVolumeMulti` in four
  files the ROOT team publishes.
- **New reference file** `data/written/two-versions.root`: one class at two
  versions with an object written at each, the only file in `data/` that contains
  a class twice. A single ROOT session cannot produce it.
- A case may now declare `expected_diagnostics` in its `case.toml`. Gate 3 still
  fails on every other ROOT diagnostic, and it also fails if a declared one stops
  appearing. The only use so far is the `no dictionary` warning that any class a
  writer invented produces, which is a fact about the session, not about the file.

- **[Writing a file §13](spec/06-writing/WritingFiles.md) specifies updating a
  file that already exists**, which was out of scope until now. It needs no new
  allocation rule: §2 is the whole allocator, and an update inherits the free list
  instead of starting one. No record moves, because a directory record is
  rewritten in place. What it does need is the close sequence, since each step
  allocates out of what the step before it released, and the five things an
  update reads: the header, the root directory record, the key list, the
  free-segment record, and, unread, the two numbers naming the `StreamerInfo`
  record.
- **Four fields are taken from the file, and the caller's settings discarded**, on
  reopen: `fVersion`, `fBEGIN`, `fUnits` and `fCompress`, plus the title. The
  compression level passed to `TFile::Open` is therefore ignored, and a file
  updated by 6.40 can still declare it was written by 5.28. Every inference a
  reader draws from `fVersion` is about the *first* writer.
- **A file can disagree with itself about its own name.** ROOT deliberately does
  not restore `fName`, so keys written by an update carry the path the file was
  *opened* as, while the root directory record still carries the path it was
  *created* as. Copy a file and update the copy, and the rename is the only
  difference: eight bytes, four in each of two keys. A reader must not assume the
  two agree.
- **An update that writes nothing still changes the file.** Opened at its own
  path, not written to at all, and closed, a file changes in three timestamps and
  nothing else: `fDatimeM` in the directory header, and the `fDatime` of the key
  list and of the free record, both of which are freed and rewritten at the same
  place. Opening for reading changes nothing.
- **The three ways to write a name that already exists are now tabulated**
  ([§13.5](spec/06-writing/WritingFiles.md)), because they differ in three visible
  ways. `"overwrite"` frees before it allocates, so the replacement can reuse the
  old address and the cycle does not advance; `"WriteDelete"` frees afterwards, so
  it cannot, and the cycle does. Both take the newest key of that name, not the
  oldest.
- **`TDirectoryFile::Delete` is a save, not a release**
  ([§8.2](spec/06-writing/WritingFiles.md)): it writes the key list, the directory
  header and the free list before returning. `Delete("name")` with no cycle
  touches memory only and leaves the file alone; removing a key takes
  `Delete("name;1")`.
- **New invariant, [File header §10](spec/01-container/FileHeader.md) 11:
  `fBEGIN` is at least the header its own `fVersion` selects**, 63 bytes small and
  75 large. Four files in the corpora have `fBEGIN` of 64, from ROOT 2.24/00 to
  4.00. `TFile::WriteHeader` allocates `fBEGIN` bytes and writes 75 when the file
  is large, so pushing one of those past 2 GB would overwrite its own first record.
  This is derived from the source and the arithmetic, not observed in a file, and
  [§13.8](spec/06-writing/WritingFiles.md) says so.
- **Two new reference files, each matching a ROOT-written one in every byte** of
  the file except the timestamps, the name and the UUIDs:
  `data/written/reopen-add.root` at 1657 bytes (a reopen that adds a new name, a
  second cycle and a `WriteDelete`) and `data/written/reopen-reuse.root` at 1928,
  whose update places a record into a 95-byte hole the base left, filling it
  exactly. The match includes the dead keys behind the gap markers, which neither
  writer clears.

- **[Writing a file §8.1](spec/06-writing/WritingFiles.md) specifies where a key
  goes in the key list, and what cycle it gets.** A name not already present is
  appended with cycle 1; a name that is present is inserted before the first key
  of that name and takes that key's cycle plus one. A run of keys is therefore in
  descending cycle order, and the order matters: ROOT never compares cycles to
  find the highest, it returns the first match. Measured by reversing three key
  images in a file and changing nothing else: `Get("str")` returns `revision 1`
  instead of `revision 3`, `GetKey("str", 2)` returns cycle 1 instead of 2, and
  nothing is printed. §8.2 adds what deletion leaves behind: cycles are never
  renumbered or compacted, so they can be sparse, and a negative `fCycle` is the
  keep flag and must not be normalised away.
- **New invariant, [Directories §9](spec/01-container/Directory.md) 14: keys
  sharing a name have distinct cycles in descending order, and none is 0.**
  Checked, and it fires on a fixture whose key images were reversed.
- **New reference file** `data/written/cycles-3.root`: three cycles of one name,
  the same 1361 bytes as `data/container/cycles.root` except for each key's
  `fDatime`, the file's own name and the UUID.

- **[Writing a file §2](spec/06-writing/WritingFiles.md) now specifies the
  allocator**, where it previously specified only the append-only case and said
  gaps were avoided. Given a record of `n` bytes, ROOT takes an exact match from
  anywhere in the free list, otherwise the first span strictly longer than
  `n + 3`, and otherwise extends the last one. The `+ 3` guarantees that a partial
  fit leaves at least the four bytes the gap marker needs, so a span one, two or
  three bytes too large is skipped and stays unused. The remainder marker is
  written as part of the new record's own key, not by a second seek. Releasing a
  record merges it with its neighbours and writes the marker at the merged span's
  start, which rewrites an older gap's marker rather than adding one. Freeing the
  last record moves `fEND` back and does not truncate the file, so `fEND` is a
  position, not a length.
- **New invariant, [Free segments §8](spec/01-container/FreeSegments.md) 10: no
  interior free segment is one, two or three bytes long.** It follows from the
  `+ 3` above, it is checked, and it holds over 142 interior segments in the
  corpora and `data/`.
- **Two new reference files.** `data/container/gap-reused.root`, written by ROOT,
  shows an exact fit, a partial fit by an unrelated record, and the remainder.
  `data/written/reused-space.root` is this project writing the same thing, and the
  two are the same 1747 bytes except for each key's `fDatime`, the file's own name
  and the UUID. That includes the stale payload left behind the marker, which
  neither writer clears.

- **New document: [Writing a graph](spec/06-writing/WritingGraphs.md)**: `TGraph`
  at class version 5 and `TGraphErrors` at 3, which completes the writing layer's
  stated scope. A graph is a `TNamed` and three attribute bases, then `fNpoints`
  and two counted arrays of doubles, then `fFunctions`, `fHistogram`, `fMinimum`,
  `fMaximum` and `fOption`. Points are stored in the order given and nothing is
  sorted. Three values that a writer generalising from `TH1` gets wrong:
  - `fBits` is `0x400` (`kClipFrame`) and has no `kMustCleanup`;
  - `TAttFill` is fixed at (0, 1000) by a constructor mem-initialiser, while the
    line and marker fields come from `gStyle`'s *general* accessors, so a graph's
    line colour is 1 where a histogram's is 602;
  - the empty `TList` in `fFunctions` has `fBits` 0 where a histogram's list has
    `0x14000`.

  `fMinimum`/`fMaximum` use `TH1`'s `-1111` sentinel but are declared in the
  opposite order and are returned raw.
- **New, for a reader and a writer: a null pointer writes *more* streamer infos
  than a real one**
  ([Writing a graph §5](spec/06-writing/WritingGraphs.md#5-nineteen-streamer-infos-for-a-198-byte-object)).
  A file holding one `TGraph` and nothing else has eighteen infos and an
  11772-byte `StreamerInfo` record, because `fHistogram` is a `TH1F*` that is null
  and ROOT force-writes a null pointee's whole info chain. A graph file therefore
  describes `TH1F`, `TH1`, `TAxis` and `TAttAxis` without containing a histogram,
  and also describes `TArrayF`, `TArray` and `TArrayD`, which no histogram file
  does. The same graph after `Fit("pol1")` describes fewer.
- **Leave `fHistogram` null.** `TGraph::SetMinimum` goes through `GetHistogram()`
  and writes a whole `TH1F` into the record, taking it from 245 bytes to 1213. The
  two range members are independent of the pointer on disk, and ROOT reads them
  back from a graph that has no histogram at all.
- **New reference files** `data/classes/graph.root` and `data/written/graph.root`,
  whose two graph records and whole `StreamerInfo` record are byte-identical.
  Element lists: 35 classes, 194 elements.

- **New: a `TLeafC` string branch, so a writer covers every leaf form a flat tree
  needs** ([Writing trees §4.5](spec/06-writing/WritingTrees.md#45-a-tleafc-the-one-leaf-whose-entries-are-not-all-the-same-length)).
  Each entry holds one value, as a counted string: one length byte then the
  characters with no terminator, or the byte 255 followed by a big-endian `i32`
  when the length reaches 255. An empty string is written as nothing at all, not
  even the length byte, and this is the case that matters most. A `TLeafC`
  therefore forces its branch's `fEntryOffsetLen` non-zero and its baskets to carry
  the offset array, where an empty value shows up as two equal entries. `fLen` and
  `fMaximum` are both the longest string in the file plus one, which a writer only
  knows after a full pass; `fLenType` is 1 even though the two range members are
  `Int_t`. A `TLeafC` must be its branch's only leaf, for two independent reasons
  ([§4.6](spec/06-writing/WritingTrees.md#46-a-tleafc-must-be-its-branchs-only-leaf)).
  `data/written/leafc.root` reproduces the new `data/ttree/strings.root` record for
  record.
- **New, and it changes what a correct reader does: a string's length comes from
  the entry, never from the leaf's `fLen`**
  ([TLeaf §9.1](spec/04-ttree/TLeaf.md#91-flen-is-the-readers-buffer-size-and-it-can-be-too-small)).
  `fLen` on a `TLeafC` is the size ROOT allocates for the value, and it can be
  smaller than the longest string in the leaf's own baskets: a fast clone raises
  `fMaximum` and leaves `fLen` alone, and `hadd` fast-merges by default. ROOT then
  truncates the value on read and prints nothing, while the bytes on disk are
  complete. Measured: merging 2-character strings with 10-character ones yields
  `fLen` 3, `fMaximum` 11, and `"0123456789"` read back as `"01"`.
  `data/ttree/leafc-truncated.root` is the new reference file. A reader that takes
  the length from the counted string reads it correctly; `fMaximum`, not `fLen`, is
  the number that always covers the data.
- **Also new: `TLeafC::ReadBasketExport`**, the `TClonesArray` read path, has no
  empty-string detection, does not implement the 255-escape, and desynchronises
  the buffer when it truncates (TLeaf §9). Source-verified; no fixture puts a
  string leaf under a `TBranchClones`.
- **New `TLeafC` element list**
  ([Element lists §7](spec/06-writing/ElementLists.md#7-a-flat-tree-file-the-other-ten)),
  bringing the published set to 33 classes, 179 elements.

- **New: subdirectories, so a writer can produce a tree of directories**
  ([Writing a file §5](spec/06-writing/WritingFiles.md#5-a-subdirectory)).
  - A subdirectory's record is the same 60 bytes as the root directory's, with no
    name and title in front of them, so its `fNbytesName` is its `fKeylen` alone
    and its fields begin where its key ends.
  - Its key spells its class `TDirectory`, even though ROOT has long called it
    `TDirectoryFile`.
  - `fSeekParent` and the key's `fSeekPdir` both name the mother.
  - Each directory gets a key-list record of its own, keyed by the directory's
    name, whose `fSeekPdir` is that directory's own `fSeekDir`. A subdirectory's
    key image goes in its parent's list and its contents go in its own.
  - The record is written before anything it holds, with `fSeekKeys` still 0, and
    every later write of it overwrites it in place, because ROOT refuses to free a
    directory key. Subdirectories therefore add no free entries to a file written
    once.

  `data/written/nested-subdir.root` is the new reference file, and it matches the
  ROOT-written `data/container/directories.root` in all 1854 bytes except for each
  key's `fDatime`, three UUIDs and the file's own name.
- **Correction, for every reader: a key-list entry's length is what it parses to,
  never its `fKeylen`**
  ([Directories §6.5](spec/01-container/Directory.md#65-an-images-length-is-what-it-parses-to-never-its-fkeylen)).
  This document said an image is byte-identical to the first `fKeylen` bytes of
  the record it describes. In files written by ROOT 5.32 and earlier, a directory
  entry can be four bytes longer than that: it spells its class `TDirectoryFile`
  where the record's own key spells it `TDirectory`, while reporting the `fKeylen`
  the short spelling produced. ROOT is unaffected because it advances past the
  strings it has parsed; a reader that adds `fKeylen` frames the *next* entry from
  the middle of this one. The two spellings are one class name (ROOT normalises to
  `TDirectoryFile` on read), so a reader must accept either when looking for
  subdirectories, and must not treat a difference between an image and a record as
  a disagreement. `uproot-issue64.root` (ROOT 5.28/00) holds both spellings at
  once.
- **New `TObjString` element list**
  ([Element lists §8](spec/06-writing/ElementLists.md#8-a-file-of-one-object-tobjstring)),
  bringing the published set to 32 classes, 176 elements. It is the only class
  that the smallest possible file needs and that no table described.

- **New: `TH2` and `TProfile`, so a writer covers the five histogram classes that
  matter** ([Writing histograms §7 and §8](spec/06-writing/WritingHistograms.md#7-th2f-and-th2d)).
  `TH2F` and `TH2D` are three nested frames rather than two, with `TH2`'s four own
  doubles between the `TH1` frame closing and the `TArray` base opening. `fNcells`
  is `(nx + 2) * (ny + 2)` and the cell index is `binx + (nx + 2) * biny`, so the
  in-range region the statistics cover is a rectangle. `TProfile` is a `TH1D` with
  four parallel arrays, none of which is a bin content:
  - `fArray` is sum(w*y);
  - `fSumw2` is sum(w*y*y), and unlike a `TH1`'s is never empty;
  - `fBinEntries` is sum(w), a weight sum, not the count its own comment claims;
  - `fBinSumw2` is sum(w²).

  What ROOT reports for a bin is `fArray[i] / fBinEntries[i]`, which is stored
  nowhere. An empty `fSumw2` makes ROOT crash: it opens the file, returns the right
  entries and the right bin content, and then segfaults in `GetBinError`, which
  indexes the array with no length test. `data/classes/th2-profile.root` is the new
  reference file (71 assertions), and `data/written/th2-profile.root` reproduces
  all four of its data records byte for byte, plus its `StreamerInfo` record up to
  the `listOfRules` that ROOT appends for `TProfile` and that a file written at
  version 7 cannot use.
- **New, for a writer of any histogram: a zero `fTsumw` silently discards the
  statistics.** `TH2::GetStats` and `TProfile::GetStats` recompute all their sums
  from the bin contents and the bin centres when `fTsumw` is 0, with no diagnostic
  ([§7.3](spec/06-writing/WritingHistograms.md#73-a-zero-ftsumw-throws-all-seven-sums-away),
  [§8.5](spec/06-writing/WritingHistograms.md#85-only-fentries-is-unrecoverable)),
  and a `TProfile` also repairs a zero `fTsumwy`/`fTsumwy2` pair in place. The sums
  are therefore not optional the way `fSumw2` is.
- **Checked: the histogram invariants, which had been stated but not verified.**
  `tools/check_invariants.py` now has a `check_histogram` pass covering
  `WritingHistograms.md` 10.1 to 10.9 over the `TH1x`, `TH2x`, `TH3x` and
  `TProfile` families: `fNcells` against the axes, every counted array against
  `fNcells`, `fXbins` against `fNbins` on each axis, `fErrorMode`'s range and the Y
  range. 0 failures over the fixtures and both corpora. Its skips are counted as
  records rather than branch-baskets, so they no longer enter the `ENTRIES`
  coverage ratio, which measures something else.
- **Six errata against ROOT's own comments**
  ([§12](spec/06-writing/WritingHistograms.md#12-errata)), each one a member
  definition that would mislead a writer: `fBinEntries` is not a count,
  `fScaling` is never true, `fScalefactor` scales nothing, `fgApproximate` is not
  streamed, `GetStats` is not a copy, and `GetBinError`'s history is dated by ROOT
  release inside a class whose versions run 1 to 7.

- **New: flushing, so a writer is no longer limited to one basket per branch**
  ([Writing trees §7](spec/06-writing/WritingTrees.md#7-more-than-one-basket-per-branch)).
  It specifies what a flush produces (`fWriteBasket`, the three counted arrays at
  any length, `fMaxBaskets` as `max(fWriteBasket + 1, 10)`, a basket's `fCycle`
  and `fBufferSize`, `fEntryOffsetLen` rewritten per flush) and the cluster ranges
  that come with it: `fClusterRangeEnd` inclusive, `fClusterSize` as the watermark
  in force, `fAutoFlush` as the size of the final open-ended range, and
  `fFlushedBytes` non-zero as the only sign that any boundary was recorded.
  Previously, any tree big enough to flush was beyond what the writing layer
  covered. `data/written/cluster.root` is the worked example and reproduces ROOT's
  `data/ttree/clusters.root` (five baskets, two ranges, nineteen entries) with
  every basket record and the whole `TTree` record byte-identical.
- **New: the streamer-info element lists a writer has to emit**
  ([Element lists](spec/06-writing/ElementLists.md)). 31 classes and 174 elements,
  everything a writer of the five histogram classes or a flat `TTree` must
  describe, with every field of every element, the two write orders, the class
  versions, and the two checksums that cannot be recomputed from a list. This was
  the only part of the writing layer that could not be implemented from the prose:
  the lists existed only in `tools/rootwrite.py`. They are now read out of the
  ROOT-written reference files by `tools/element_lists.py`, which fails CI if the
  tables drift, if the fixtures disagree with each other, if the writer disagrees
  with any of them, or if a published list stops producing its own checksum.
- **Corrected, in four element fields nothing had been comparing.** An element's
  subclass tail is in no checksum and in no byte count, so:
  - `TRefTable::fProcessGUIDs` had `fCtype` 365 where ROOT writes 61 `kObject`;
  - `TArray::fN` had `fType` 3 where a counted-array member promotes it to 6
    `kCounter`;
  - `TArrayF::fArray` had a pointer's `fSize` and the wrong `fCountClass`.

  A reader is unaffected, since all four are in fields it must ignore, but a
  writer emitting the first produced an info that disagreed with ROOT's. Fixing it
  made a tree file's whole `StreamerInfo` record byte-identical to ROOT's, except
  for the one `listOfRules` entry a new file cannot use.
- **A full self-consistency review**, which corrected the specification in more
  places than any previous change. The findings that matter most to a reader:
  - a `TBasket` ignores the 256-byte compression threshold that `TKey` applies,
    so a small basket in a compressed file *is* compressed, and a reader assuming
    otherwise mis-parses the baskets of any sparsely filled tree
    ([Compression §8](spec/01-container/Compression.md));
  - the last entry in a basket ends at `fLast`, not at `fEntryOffset[j+1]`, whose
    slot is never written ([Reading entries §1](spec/04-ttree/ReadingEntries.md));
  - a fixed array of collections holds `fArrayLength` collections in one frame,
    and the reading procedure read only the first
    ([Collections §13](spec/02-serialization/Collections.md));
  - `flag >= 80` in a basket header is terminal for the offset array
    ([TBasket §4](spec/04-ttree/TBasket.md));
  - a collection of `Double32_t` or `Float16_t` is 4 and 3 bytes per element
    rather than the declared width, because the element has no comment to parse;
  - `TBranchSTL` has five added members, not three, and `fContName`, the one
    naming the collection type, was one of the two missing
    ([Splitting §5](spec/04-ttree/Splitting.md));
  - no file carries a `TCanvas` streamer info at all, so a reader must dispatch
    on the class name ([Canvas §2.1](spec/03-classes/Canvas.md)).
- **The checksum's `[` locator is stricter than this specification said**
  ([Streamer information §11](spec/02-serialization/StreamerInfo.md)). ROOT accepts
  the bracket only when nothing but `/` and whitespace precedes it, so an ordinary
  comment like `// x position [0, 1]` folds nothing; the plain search this
  document specified is the rule of checksum variants 6 and below. `TPad` had been
  recorded as the only unexplained checksum mismatch in the whole corpus; the
  cause was this, not an inconsistency in ROOT. No mismatch is unexplained now,
  and 698 of 743 streamer infos recompute exactly. The eight variants had also
  been tabulated as one difference each, whereas every test in `GetCheckSum` is a
  threshold on an ordered code.
- **New: recovering a file whose key list was never written**
  ([Records §1.1](spec/01-container/Record.md)): the scan ROOT uses, and the one
  condition of it that a third-party reader should *not* copy, since ROOT requires
  a compiled dictionary and a reader without one recovers strictly more. Reading
  any ROOT file includes reading files nobody closed, and no document had covered
  them.
- **`fSeekFree == 0` is a one-way signal.** Three places treated it as
  equivalent to "never closed". `TFile::Write` writes the free list mid-job, so a
  crashed job leaves a plausible-looking header behind, and no field proves a
  clean close ([File header §5.4](spec/01-container/FileHeader.md)).
- **The two corpora are 180 files, not 226.** The published figure counted 48
  files on one machine that no manifest recorded, so `fetch_cern.py` never fetched
  them and the number could not be reproduced. Two of those files,
  `aod_flushed.root` and `gallery.root`, were cited by the specification as
  witnesses and are now in `gen/cern/MANIFEST.sha256` and its README; the other 46
  were never referenced. Re-measured over what the manifests record: 0 failures,
  95% of records decode, and 27968 of 28035 branch-baskets have their entries
  checked.
- **A `TBranchSTL`'s baskets were invisible to the entry checker**, in neither the
  numerator nor the denominator, the same mistake made earlier with embedded
  baskets. They are now named as skips, and
  [Splitting §5.1](spec/04-ttree/Splitting.md) specifies what they hold: one
  framed `TIndArray` per entry, with version word 0 and a checksum, since
  `TIndArray` is foreign.
- **A foreign class's streamer info must record `fClassVersion` 1** even though the
  object carries a version word of 0
  ([Writing an object §2](spec/06-writing/WritingObjects.md)). A writer that records
  0 to match tells every conforming reader that no checksum follows, and
  desynchronises by four bytes on every tree and every branch. The rule existed only
  in `tools/rootwrite.py`.
- **What the writing layer does not cover is now listed**
  ([Writing §4](spec/06-writing/index.md)): the streamer-info element lists
  themselves, which exist only in `tools/rootwrite.py` and are the largest
  obstacle between a third party and a writer; more than one basket per branch,
  and cluster ranges; subdirectories; and a `TLeafC` branch. Three ways to obtain
  the element lists are given, including copying a `StreamerInfo` record verbatim.
- **`TFormula` version 6 is refused by ROOT** and readable by this specification;
  **`TLeafObject` is streamer-info driven at version 2** as well as 4 and above;
  and **`kAnyPnoVT` (70) cannot occur on disk**, where two documents had disagreed.
- `tools/inventory.py` called three unconditionally delegating streamers `guarded`,
  which told a reader there was a legacy layout to implement when there is none.
  Fixing it needed a second pass: requiring the call inside the braces
  reclassified `RooCategory`, which delegates in a trailing `else`, in the
  direction that understates what a reader needs.
- New checked invariant: **a key image agrees with the key of the record it points
  at** ([Directories §9](spec/01-container/Directory.md) invariant 11). Nothing had
  compared them. ROOT never makes this comparison either, so a disagreement is
  invisible to ROOT and fatal to every other reader.
- **The RNTuple audit's own status was stale in three ways**: ten errata rather
  than six, the type mapping marked unaudited where `NOTES` §4 marks it audited,
  and two fixtures where there are eight. Erratum 1 now reports the actual
  disagreement: ROOT's source says the feature flag arrived in 1.1.0.0, where the
  document says 1.0.2.1.

- **A writing layer**, `spec/06-writing/`, which extends the project past the
  reading side it was scoped to: [an overview](spec/06-writing/index.md) of what a
  writing procedure is here and what is deliberately left out, and
  [Writing a file](spec/06-writing/WritingFiles.md), the container in write order,
  with every field marked fixed, derived or free. It adds what the reading
  documents could not: the order of operations, which no byte in the file
  records; the ten container mistakes ROOT reads without complaint; and what
  omitting the `StreamerInfo` record costs. ROOT needs no streamer info for a class
  it has compiled in (measured, not assumed), and the warning that says so fires
  only when the file's `fVersion` differs from the running ROOT's, so a writer
  stamping the current release silences it.
- [Writing an object](spec/06-writing/WritingObjects.md): the two framings and the
  three classes that have neither, the version word of 0 a foreign class needs, the
  `TObject` base's masked `fBits`, the class and object maps with their two
  different mapping positions, ZLIB blocks, and the `StreamerInfo` record from
  `TList` down to each element subclass. `tools/test_write.py` builds that record
  for `TObjString` from the document and asserts it is byte-identical to the one
  ROOT wrote in `data/container/file-minimal.root`, with the checksum computed from
  scratch.
- **What "the current version" means**, new
  [Writing §3.1](spec/06-writing/index.md). ROOT writes one version per class and
  it is not a choice: both places a version word is emitted take the version
  compiled into the writing process, so a read-and-write upgrades the object. A
  ROOT 5.28 `TH1F` (`TH1` 6, `TAxis` 9) comes back out of 6.40.04 as `TH1` 8,
  `TAxis` 10. Four cases put something else in the word:
  - a foreign class writes 0 and a checksum;
  - a version-0 class writes its 0 (and a forwarding streamer writes nothing);
  - a member-wise collection sets `0x4000`;
  - an emulated class has the version that the file it came from declared.

  Copying is not writing: `hadd` moves basket records verbatim, so an older ROOT's
  records survive into a new file at their original versions.
- **The same class at the same version can have two different checksums with an
  identical layout** ([StreamerInfo §11](spec/02-serialization/StreamerInfo.md)):
  `TAttAxis` 4 is `0x532a3b8c` in a ROOT 5.28 file and `0x5c6fff3e` today, because
  the old file spells its member types `Int_t` and `Float_t` where the new one
  resolves them. The eight checksum variants exist for this reason, and a mismatch
  at equal version is not evidence of a layout change.
- [A writer's invariants](spec/99-appendix/WriterInvariants.md): the 223
  `Invariants` entries of the whole specification re-sorted by the order a file is
  produced in, with one column the reading side never needed: who notices a
  violation (`tools/check_invariants.py`, ROOT, or nothing). §6 lists the nine
  cases where the answer is nothing.
- The class-version tables of the two class-level writing documents are checked
  against `ClassDef`, taking `tools/check_versions.py` from 25 versions across 7
  documents to 40 across 9.
- [Writing trees](spec/06-writing/WritingTrees.md): a flat `TTree`, covering the
  basket records, the branch and leaf descriptions inside the tree record, and the
  fields that must agree with one another. `data/written/tree.root` reproduces
  `data/ttree/basket.root` record for record, both baskets and the `TTree`, keys
  included. Nine things a reader never needs:
  - a basket's key version is 1004 whatever the file's size, and its `fKeylen`
    covers the 19-byte basket header;
  - a basket is never in the key list;
  - `fLeafCount` and `fLeaves` are object references, so the counter branch must
    be written first;
  - a counter leaf's `fMaximum` must cover every count in the file or ROOT clamps
    the read;
  - `fNevBufSize` means the entry stride or the offset array's capacity depending
    on the branch;
  - `fBaskets` is `fWriteBasket + 1` slots of null;
  - `fBranches` and `fLeaves` are member objects rather than pointers;
  - `fMaxVirtualSize` must not be negative and `fWeight` must be 1.0;
  - `ROOT::TIOFeatures` has no `ClassDef`, so its version word is 0 and a
    checksum.
- [Writing histograms](spec/06-writing/WritingHistograms.md): `TH1F` and `TH1D`
  member by member at the current class version, with every field marked fixed,
  derived or free, and the fifteen `TStreamerInfo` records the chain needs.
  **Every object-bearing record in `data/written/histogram.root` is byte-identical
  to the one ROOT wrote in the new `data/classes/histogram.root`**: the `TH1F`'s
  596 bytes, the `TH1D`'s 651 and the `StreamerInfo` record's 9628. Four things a
  reader never has to know: the statistics are not derivable from the bin
  contents (`fEntries` counts fills, `fTsumw2` sums squared weights); `-1111` in
  `fMaximum` and `fMinimum` is a sentinel for "compute from the data";
  `fFunctions` is streamed in place because it is declared `//->`; and the Y
  axis's `fTitleOffset` is 0 where X and Z have 1.
- A new reading-side fixture, `classes/histogram`, with 73 assertions: the
  `TH1` -> `TAxis` -> `TAttAxis` hierarchy at byte level, a variable-bin-edge
  `fXbins`, and the statistics of five fills, two of which went out of range.
  Nothing in the corpus contained the histogram chain before.
- **How far the checksum algorithm can be applied**, new
  [StreamerInfo §11.1 and §11.2](spec/02-serialization/StreamerInfo.md).
  Recomputing `fCheckSum` for every streamer info in every reference file gives
  614 of 653 exactly, and every failure has a named cause:
  - an enum folds an extra 1, and is recognisable by `fType` 3 with a
    non-primitive `fTypeName`, the test ROOT's own checksum code uses;
  - a version-0 class lists no members but folds them anyway;
  - a member ROOT rewrote for I/O (`std::array`, `std::unique_ptr`) keeps its
    declared spelling in the checksum and not in the record;
  - three `pair` instances where ROOT's own value is wrong.

  This affects checking and writing a file, never decoding one.
- `tools/rootwrite.py`, a pure-Python writer built from those documents, and
  `tools/check_write.py`, which puts what it produces through three gates: this
  project's reader and every applicable invariant accept it; the bytes are
  reproduced exactly, since a writer has no reason to consult a clock; and ROOT
  opens it, returns the values that went in, and prints nothing. The third gate
  runs in CI. `data/written/objstring.root` is the first file in this repository
  that ROOT did not write, and ROOT reads it, appends to it and rewrites its free
  list without complaint.
- **The RNTuple type mapping is audited**, every form but one, with six fixtures
  and a test per subsection that parses each claim out of the tracked document
  rather than transcribing it. The audit covers the stdlib types, user-defined
  classes and enums, projected fields and alias columns, `RNTupleCardinality`,
  untyped collections and records, ROOT streamed types, and the SoA layout, which
  sets the one field flag no fixture had reached. Only classes with an associated
  collection proxy are left. Four new errata:
  - **7**: `Double32_t` keeps a `SplitReal32` column in an uncompressed ntuple,
    where every other default drops to unsplit;
  - **8**: the field record's `Type Version` is a signed class version in an
    unsigned word, so a class with no `ClassDef` arrives as 0xFFFFFFFF;
  - **9**: the extra type information's content is a length-prefixed string, four
    bytes the record's layout does not show;
  - **10**: that record lives in the footer's schema extension and never in the
    header where the document introduces it, so a reader looking there finds no
    streamer info in any file with a streamed field.
- `tools/rootfile.py` reads the header envelope's alias column and extra type
  information lists, and both version words of a field record.

- **Every branch-basket in the two corpora that any reader could decode is now
  decoded and checked**: 27969 of 28036, 99.8%, and 1696 of 1696 over the files
  the ROOT team published. The entry decoder reads a basket kept inside the
  `TTree` record rather than written as its own key, which is most of a file
  written through `TDirectory::WriteTObject`. The 67 that remain are a collection
  whose value class has no streamer info in its file, and a class with a
  hand-written `Streamer`; neither is a gap in the reader.
- **`ReadingEntries.md` §4.1: resolve a counted array's counter branch by name
  among the branch's siblings**, not through the recorded `fBranchCount`. ROOT
  looks the name up over the whole tree, so a tree holding two split objects of
  one class records the first object's counter on both, and reads no data for the
  second. Erratum 6 has the witness: `alice_ESDs.root`, where ROOT reads 0 indices
  for entries holding 18, 22, 6 and 13.
- **`ReadingEntries.md` §4.2: a container's member needs one count per object.**
  For `fType` 31 or 41 whose element is `T *x; //[n]`, the entry is one flag byte
  then that object's values, per object, with the counts held as a column in the
  sibling branch. Nothing in the file points from the member to that branch.
