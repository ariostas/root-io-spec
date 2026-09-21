# Changelog

Versions are the *specification's*, not ROOT's. Each release says which ROOT
release it is descriptive of; where the two disagree, ROOT is right and this has a
bug ([spec/index.md](spec/index.md)).

This file records what changed for a **reader**. The git log records how each fact
was established, which is the other half of the story.

## Unreleased

- **[Writing an object §8](spec/06-writing/WritingObjects.md) specifies schema
  evolution from the writing side**: what has to be in a file so that a reader
  whose version of a class is not the writer's can still read it. It is smaller
  than it looks, because `TStreamerInfo::BuildOld` matches each on-disk element to
  a member **by name and nothing else** — so `fSize`, `fArrayDim` and `fMaxIndex`
  are never compared, and artificial and cache elements cannot reach disk at all.
  Six obligations remain, and §8.1 tabulates them.
- **The mistake worth naming is an incomplete closure**: an info for a derived
  class without one for its base. Measured — `BuildOld` skips the base, the class
  comes out 16 bytes instead of 24, and `CheckByteCount` reports the short read.
  It is **loud** rather than silent, and only because the base's bytes carry their
  own byte count; a base whose bytes carry none, like `TObject`'s, would
  desynchronise quietly. The closure has one exemption — a class whose `Streamer`
  is hand-written or forwarding gets no info — and over the 90 files here that
  carry infos, the bases with no info are exactly six classes, all on one of the
  two published lists.
- **One class may appear at two versions in one file, and ROOT produces such
  files itself.** Measured with two sessions: a file written at `ClassDef(C, 2)`
  and reopened by a session whose `C` is at version 3 comes out with **both**
  infos and two records of different lengths, silently and correctly. The plan for
  this work expected ROOT to discard one; it does not.
- **When the versions *collide*, the file wins and data is lost.** Same
  experiment, but the second session's class has a third member and still says
  `ClassDef(C, 2)`. ROOT warns at open — "Do not try to write objects with the
  current class definition" — and then does exactly that: the object it writes is
  54 bytes, not 58, and the third member never reaches the file. No later reader
  can tell. A writer's two honest responses are to bump the version or to refuse.
- **ROOT cannot read an emulated class that derives from `TObject`**
  ([Schema evolution §7.1](spec/02-serialization/SchemaEvolution.md)), and this is
  a **silent data-loss path in ROOT**, found here. `TKey::ReadObj` streams a
  `TObject`-derived object with `tobj->Streamer()`, which with no dictionary
  resolves to `TObject::Streamer` and reads ten bytes and stops. Measured on a
  file ROOT wrote itself: a class with `fA = 77` and `fB = 1.25` reads back as
  0 and 0, the only message being `no dictionary for class …`. This project's
  reader recovers both values from the same bytes. It affects only a top-level
  record — the same class as a *member* reads correctly — and it is why a writer
  should not derive its own persistent classes from `TObject`.
- **`listOfRules` is specified for writing, and emitting it closes the last gap
  in the `StreamerInfo` comparison.** ROOT appends the rules of every class being
  written with no reference to the version, so a `TTree` 20 file ships two rules
  for versions ≤ 16 and ≤ 18 that can never match its own data — and ROOT never
  reads the list back, so a writer may omit it. This one emits it, and **seven
  whole `StreamerInfo` records are now byte-identical** to ROOT's — 370, 9628,
  11789, 12169, 14121, 14580 and 14584 bytes — where four used to differ by that
  one entry. `FileWriter(emit_rules=False)` turns it off.
- **`fBaseVersion` may name a version the file has no info for**, and the
  fallback [Streamer information §9.1](spec/02-serialization/StreamerInfo.md)
  tells a reader to use is therefore not enough. Found by asserting the opposite
  as an invariant, which five files in the two corpora disproved at once. On
  `uproot-mc10events.root` (ROOT 6.08/04) `TTree`'s `TAttLine` base says version 1
  beside a version-2 info, and its `fBaseCheckSum` points at that version-2 info,
  so the checksum resolves it. On `aleph.root`, `atlas.root`, `cms.root` and
  `hades.root` (ROOT 5.17/09) the checksum is 0 and `fBaseVersion` is 4 where the
  file's only info for the base is version 5 — **so there is nothing for §9.1's
  fallback to land on**. §9.2 adds the third step a reader needs: take the info the
  file does have for that class. A reader that stops earlier cannot decode a
  `TGeoVolumeMulti` on four files the ROOT team publishes.
- **New reference file** `data/written/two-versions.root`: one class at two
  versions with an object written at each, the only file in `data/` that carries a
  class twice. A single ROOT session cannot produce it.
- A case may now declare `expected_diagnostics` in its `case.toml`. Gate 3 still
  fails on every other ROOT diagnostic, and it also fails if a declared one stops
  appearing. The only use so far is the `no dictionary` warning that any class a
  writer invented produces — a fact about the session, not about the file.

- **[Writing a file §13](spec/06-writing/WritingFiles.md) specifies updating a
  file that already exists**, which was out of scope until now. It needs no new
  allocation rule — §2 is the whole allocator, and an update inherits the free
  list instead of starting one — and no record moves, because a directory record
  is rewritten in place. What it does need is the **close sequence**, since each
  step allocates out of what the step before it released, and the five things an
  update reads: the header, the root directory record, the key list, the
  free-segment record, and, unread, the two numbers naming the `StreamerInfo`
  record.
- **Four fields are taken from the file and the caller's wishes discarded** on
  reopen: `fVersion`, `fBEGIN`, `fUnits` and `fCompress`, plus the title. So the
  compression level passed to `TFile::Open` is ignored, and **a file updated by
  6.40 can still declare it was written by 5.28** — every inference a reader
  draws from `fVersion` is about the *first* writer.
- **A file can disagree with itself about its own name.** ROOT deliberately does
  not restore `fName`, so keys written by an update carry the path the file was
  *opened* as while the root directory record still carries the path it was
  *created* as. Copy a file, update the copy, and that rename is the **entire**
  difference — eight bytes, four in each of two keys. A reader must not assume
  the two agree.
- **A no-op update is not a no-op.** Opened at its own path, written to not at
  all, and closed, a file changes exactly **three** timestamps: `fDatimeM` in the
  directory header, and the `fDatime` of the key list and the free record, both
  of which are freed and refitted exactly where they were. Opening for reading
  changes nothing.
- **The three ways to write a name that already exists are now tabulated**
  ([§13.5](spec/06-writing/WritingFiles.md)), because they differ in three
  visible ways and not one: `"overwrite"` frees before it allocates, so the
  replacement can reuse the old address and the cycle does **not** advance;
  `"WriteDelete"` frees afterwards, so it cannot, and the cycle does. Both take
  the **newest** key of that name, not the oldest.
- **`TDirectoryFile::Delete` is a save, not a release**
  ([§8.2](spec/06-writing/WritingFiles.md)): it writes the key list, the
  directory header and the free list before returning. And `Delete("name")` with
  no cycle touches memory only and leaves the file alone — it takes
  `Delete("name;1")` to remove a key.
- **New invariant, [File header §10](spec/01-container/FileHeader.md) 11:
  `fBEGIN` is at least the header its own `fVersion` selects** — 63 bytes small,
  **75** large. Four files in the corpora have `fBEGIN` of 64, from ROOT 2.24/00
  to 4.00; `TFile::WriteHeader` allocates `fBEGIN` bytes and writes 75 when the
  file is large, so pushing one of those past 2 GB would write over its own first
  record. Derived from the source and the arithmetic, not witnessed —
  [§13.8](spec/06-writing/WritingFiles.md) says so.
- **Two new reference files, each matching a ROOT-written one for every byte** of
  the file bar the timestamps, the name and the UUIDs:
  `data/written/reopen-add.root` at **1657 bytes** — a reopen that adds a new
  name, a second cycle and a `WriteDelete` — and
  `data/written/reopen-reuse.root` at **1928**, whose update places a record into
  a 95-byte hole the base left, filling it exactly. The agreement extends to the
  dead keys buried behind the gap markers, which neither writer clears.

- **[Writing a file §8.1](spec/06-writing/WritingFiles.md) specifies where a key
  goes in the key list, and what cycle it gets.** A name not already present is
  appended with cycle 1; a name that is present is inserted **before the first
  key of that name** and takes that key's cycle plus one. So a key run is in
  **descending** cycle order — and that is not decoration: ROOT never compares
  cycles to find the highest, it returns the **first** match. Measured by
  reversing three key images in a file and changing nothing else: `Get("str")`
  returns `revision 1` instead of `revision 3`, `GetKey("str", 2)` returns cycle
  1 instead of 2, and nothing is printed. §8.2 adds what deletion leaves behind —
  cycles are never renumbered or compacted, so they can be sparse — and that a
  **negative** `fCycle` is the keep flag and must not be normalised away.
- **New invariant, [Directories §9](spec/01-container/Directory.md) 14: keys
  sharing a name have distinct cycles in descending order, and none is 0.**
  Checked, and it fires on a fixture whose key images were reversed.
- **New reference file** `data/written/cycles-3.root`: three cycles of one name,
  **the same 1361 bytes** as `data/container/cycles.root` bar each key's
  `fDatime`, the file's own name and the UUID.

- **[Writing a file §2](spec/06-writing/WritingFiles.md) now specifies the
  allocator**, where it previously specified only the append-only case and said
  gaps were avoided. Given a record of `n` bytes, ROOT takes an **exact** match
  from anywhere in the free list, otherwise the **first** span strictly longer
  than `n + 3`, and otherwise extends the last one. The `+ 3` is not a rounding:
  it guarantees a partial fit leaves at least the four bytes the gap marker
  needs, so a span one, two or three bytes too large is **skipped and stays
  unused**. The remainder marker is written as part of the new record's own key,
  not by a second seek; releasing a record merges with its neighbours and writes
  the marker at the **merged** span's start, which rewrites an older gap's marker
  rather than adding one. Freeing the last record moves `fEND` back and does not
  truncate the file, so `fEND` is a position, not a length.
- **New invariant, [Free segments §8](spec/01-container/FreeSegments.md) 10: no
  interior free segment is one, two or three bytes long.** It follows from the
  `+ 3` above, it is checked, and it holds over 142 interior segments in the
  corpora and `data/`.
- **Two new reference files.** `data/container/gap-reused.root`, written by ROOT,
  shows an exact fit, a partial fit by an unrelated record, and the remainder;
  `data/written/reused-space.root` is this project writing the same thing, and
  the two are **the same 1747 bytes** bar each key's `fDatime`, the file's own
  name and the UUID — including the stale payload left behind the marker, which
  neither writer clears.

- **New document: [Writing a graph](spec/06-writing/WritingGraphs.md)** — `TGraph`
  at class version 5 and `TGraphErrors` at 3, which completes the writing layer's
  stated scope. A graph is a `TNamed` and three attribute bases, then `fNpoints` and
  two counted arrays of doubles, then `fFunctions`, `fHistogram`, `fMinimum`,
  `fMaximum` and `fOption`. Points are stored **in the order given** and nothing is
  sorted. Three values a writer generalising from `TH1` gets wrong: `fBits` is
  `0x400` (`kClipFrame`) and carries **no** `kMustCleanup`; `TAttFill` is fixed at
  (0, **1000**) by a constructor mem-initialiser while the line and marker fields
  come from `gStyle`'s *general* accessors, so a graph's line colour is 1 where a
  histogram's is 602; and the empty `TList` in `fFunctions` has `fBits` 0 where a
  histogram's list carries `0x14000`. `fMinimum`/`fMaximum` use `TH1`'s `-1111`
  sentinel but are declared in the opposite order and are returned raw.
- **New, for a reader and a writer: a null pointer writes *more* streamer infos than
  a real one** ([Writing a graph §5](spec/06-writing/WritingGraphs.md#5-nineteen-streamer-infos-for-a-198-byte-object)).
  A file holding one `TGraph` and nothing else carries **eighteen** infos and an
  11772-byte `StreamerInfo` record, because `fHistogram` is a `TH1F*` that is null
  and ROOT force-writes a null pointee's whole info chain. So a graph file describes
  `TH1F`, `TH1`, `TAxis` and `TAttAxis` without containing a histogram, **and
  describes `TArrayF`, `TArray` and `TArrayD`, which no histogram file does** — while
  the same graph after `Fit("pol1")` describes fewer.
- **Leave `fHistogram` null.** `TGraph::SetMinimum` goes through `GetHistogram()` and
  writes a whole `TH1F` into the record, taking it from 245 bytes to 1213. The two
  range members are independent of the pointer on disk, and ROOT reads them back from
  a graph that has no histogram at all.
- **New reference files** `data/classes/graph.root` and `data/written/graph.root`,
  whose two graph records **and whole `StreamerInfo` record** are byte-identical.
  Element lists: **35 classes, 194 elements**.

- **New: a `TLeafC` string branch, so a writer covers every leaf form a flat tree
  needs** ([Writing trees §4.5](spec/06-writing/WritingTrees.md#45-a-tleafc-the-one-leaf-whose-entries-are-not-all-the-same-length)).
  One value per entry, as a counted string: one length byte then the characters with
  no terminator, the byte 255 followed by a big-endian `i32` when the length reaches
  255, and — the case that matters — **nothing at all for an empty string**, not
  even the length byte. So a `TLeafC` forces its branch's `fEntryOffsetLen` non-zero
  and its baskets to carry the offset array, where an empty value shows up as two
  equal entries. `fLen` and `fMaximum` are both the longest string in the file plus
  one, which a writer only knows after a full pass; `fLenType` is 1 even though the
  two range members are `Int_t`. A `TLeafC` must be its branch's **only** leaf, for
  two independent reasons ([§4.6](spec/06-writing/WritingTrees.md#46-a-tleafc-must-be-its-branchs-only-leaf)).
  `data/written/leafc.root` reproduces the new `data/ttree/strings.root` record for
  record.
- **New, and it changes what a correct reader does: a string's length comes from the
  entry, never from the leaf's `fLen`**
  ([TLeaf §9.1](spec/04-ttree/TLeaf.md#91-flen-is-the-readers-buffer-size-and-it-can-be-too-small)).
  `fLen` on a `TLeafC` is the size ROOT allocates for the value, and it can be
  **smaller than the longest string in the leaf's own baskets** — a fast clone
  raises `fMaximum` and leaves `fLen` alone, and `hadd` fast-merges by default. ROOT
  then truncates the value on read and prints nothing, while the bytes on disk are
  complete. Measured: merging 2-character strings with 10-character ones yields
  `fLen` 3, `fMaximum` 11, and `"0123456789"` read back as `"01"`.
  `data/ttree/leafc-truncated.root` is the new reference file. A reader that takes
  the length from the counted string reads it correctly; `fMaximum`, not `fLen`, is
  the number that always covers the data.
- **Also new about `TLeafC::ReadBasketExport`** — the `TClonesArray` read path —
  which has no empty-string detection, does not implement the 255-escape, and
  desynchronises the buffer when it truncates (TLeaf §9). Source-verified; no
  fixture puts a string leaf under a `TBranchClones`.
- **New `TLeafC` element list**
  ([Element lists §7](spec/06-writing/ElementLists.md#7-a-flat-tree-file-the-other-ten)),
  bringing the published set to **33 classes, 179 elements**.

- **New: subdirectories, so a writer can produce a tree of directories**
  ([Writing a file §5](spec/06-writing/WritingFiles.md#5-a-subdirectory)). A
  subdirectory's record is the same 60 bytes as the root directory's with **no name
  and title in front of them**, so its `fNbytesName` is its `fKeylen` alone and its
  fields begin where its key ends; its key spells its class `TDirectory` however
  long ROOT has called it `TDirectoryFile`; and `fSeekParent` and the key's
  `fSeekPdir` both name the mother. Each directory gets a key-list record of its
  own, keyed by the **directory's** name, whose `fSeekPdir` is that directory's own
  `fSeekDir`; a subdirectory's key image goes in its parent's list and its contents
  go in its own. The record is written before anything it holds, with `fSeekKeys`
  still 0, and every later write of it is an **overwrite in place** — ROOT refuses
  outright to free a directory key — so subdirectories add no free entries to a file
  written once. `data/written/nested-subdir.root` is the new reference file, and it
  matches the ROOT-written `data/container/directories.root` for **all 1854 bytes**
  bar each key's `fDatime`, three UUIDs and the file's own name.
- **Correction, for every reader: a key-list entry's length is what it parses to,
  never its `fKeylen`**
  ([Directories §6.5](spec/01-container/Directory.md#65-an-images-length-is-what-it-parses-to-never-its-fkeylen)).
  This document said an image is byte-identical to the first `fKeylen` bytes of the
  record it describes. In files written by **ROOT 5.32 and earlier** a directory
  entry can be four bytes longer than that: it spells its class `TDirectoryFile`
  where the record's own key spells it `TDirectory`, while reporting the `fKeylen`
  the short spelling produced. ROOT is immune because it advances past the strings
  it has parsed; a reader that adds `fKeylen` frames the *next* entry from the
  middle of this one. The two spellings are one class name — ROOT normalises to
  `TDirectoryFile` on read — so a reader must accept either when looking for
  subdirectories, and must not treat a difference between an image and a record as
  a disagreement. `uproot-issue64.root` (ROOT 5.28/00) holds both spellings at once.
- **New `TObjString` element list**
  ([Element lists §8](spec/06-writing/ElementLists.md#8-a-file-of-one-object-tobjstring)),
  bringing the published set to **32 classes, 176 elements**. It is the one class
  the smallest possible file needs and no table described.

- **New: `TH2` and `TProfile`, so a writer covers the five histogram classes that
  matter** ([Writing histograms §7 and §8](spec/06-writing/WritingHistograms.md#7-th2f-and-th2d)).
  `TH2F` and `TH2D` are three nested frames rather than two, with `TH2`'s four own
  doubles between the `TH1` frame closing and the `TArray` base opening; `fNcells`
  is `(nx + 2) * (ny + 2)` and the cell index is `binx + (nx + 2) * biny`, so the
  in-range region the statistics cover is a rectangle. `TProfile` is a `TH1D` with
  **four parallel arrays**, none of which is a bin content: `fArray` is sum(w*y),
  `fSumw2` is sum(w*y*y) and unlike a `TH1`'s is never empty, `fBinEntries` is
  sum(w) — a weight sum, not the count its own comment claims — and `fBinSumw2` is
  sum(w²). What ROOT reports for a bin is `fArray[i] / fBinEntries[i]`, stored
  nowhere. An empty `fSumw2` is the one thing here ROOT punishes by **crashing**:
  it opens the file, returns the right entries and the right bin content, and then
  segfaults in `GetBinError`, which indexes the array with no length test.
  `data/classes/th2-profile.root` is the new reference file (71 assertions) and
  `data/written/th2-profile.root` reproduces all four of its data records byte for
  byte, plus its `StreamerInfo` record up to the `listOfRules` ROOT appends for
  `TProfile` and a file written at version 7 cannot use.
- **New, for a writer of any histogram: a zero `fTsumw` silently discards the
  statistics.** `TH2::GetStats` and `TProfile::GetStats` recompute all their sums
  from the bin contents and the bin centres when `fTsumw` is 0, with no diagnostic
  ([§7.3](spec/06-writing/WritingHistograms.md#73-a-zero-ftsumw-throws-all-seven-sums-away),
  [§8.5](spec/06-writing/WritingHistograms.md#85-only-fentries-is-unrecoverable)) —
  and a `TProfile` also repairs a zero `fTsumwy`/`fTsumwy2` pair in place. So the
  sums are not optional the way `fSumw2` is.
- **Checked: the histogram invariants, which had been stated but not verified.**
  `tools/check_invariants.py` now has a `check_histogram` pass covering
  `WritingHistograms.md` 10.1 to 10.9 over the `TH1x`, `TH2x`, `TH3x` and
  `TProfile` families — `fNcells` against the axes, every counted array against
  `fNcells`, `fXbins` against `fNbins` on each axis, `fErrorMode`'s range and the Y
  range. 0 failures over the fixtures and both corpora. Its skips are counted as
  **records** rather than branch-baskets, so they no longer enter the `ENTRIES`
  coverage ratio, which measures something else.
- **Six errata against ROOT's own comments**
  ([§12](spec/06-writing/WritingHistograms.md#12-errata)), each one a member
  definition that would mislead a writer: `fBinEntries` is not a count,
  `fScaling` is never true, `fScalefactor` scales nothing, `fgApproximate` is not
  streamed, `GetStats` is not a copy, and `GetBinError`'s history is dated by ROOT
  release inside a class whose versions run 1 to 7.

- **New: flushing, so a writer is no longer limited to one basket per branch**
  ([Writing trees §7](spec/06-writing/WritingTrees.md#7-more-than-one-basket-per-branch)).
  What a flush produces — `fWriteBasket`, the three counted arrays at any length,
  `fMaxBaskets` as `max(fWriteBasket + 1, 10)`, a basket's `fCycle` and
  `fBufferSize`, `fEntryOffsetLen` rewritten per flush — and the **cluster ranges**
  that come with it: `fClusterRangeEnd` inclusive, `fClusterSize` as the watermark
  in force, `fAutoFlush` as the size of the final open-ended range, and
  `fFlushedBytes` non-zero as the only sign that any boundary was recorded. Any tree
  big enough to flush was past what the writing layer covered; it no longer is.
  `data/written/cluster.root` is the worked example and reproduces ROOT's
  `data/ttree/clusters.root` — five baskets, two ranges, nineteen entries — with
  every basket record and the whole `TTree` record byte-identical.
- **New: the streamer-info element lists a writer has to emit**
  ([Element lists](spec/06-writing/ElementLists.md)). 31 classes and 174 elements —
  everything a writer of the five histogram classes or a flat `TTree` must describe —
  with every field of every element, the two write orders, the class versions, and
  the two checksums that cannot be recomputed from a list. This was the one part of
  the writing layer that could not be implemented from the prose: the lists existed
  only in `tools/rootwrite.py`. They are now read out of the ROOT-written reference
  files by `tools/element_lists.py`, which fails CI if the tables drift, if the
  fixtures disagree with each other, if the writer disagrees with any of them, or if
  a published list stops producing its own checksum.
- **Corrected, in four element fields nothing had been comparing.** An element's
  subclass tail is in no checksum and in no byte count, so
  `TRefTable::fProcessGUIDs` carried `fCtype` 365 where ROOT writes 61 `kObject`,
  `TArray::fN` carried `fType` 3 where a counted-array member promotes it to 6
  `kCounter`, and `TArrayF::fArray` carried a pointer's `fSize` and the wrong
  `fCountClass`. A reader is unaffected — all four are in fields it must ignore —
  but a writer emitting the first produced an info that disagreed with ROOT's.
  Fixing it made a tree file's whole `StreamerInfo` record byte-identical to ROOT's
  bar the one `listOfRules` entry a new file cannot use.
- **A full self-consistency review**, which corrected the specification in more
  places than any previous change. The findings that matter most to a reader:
  a **`TBasket` ignores the 256-byte compression threshold** that `TKey` applies,
  so a small basket in a compressed file *is* compressed and a reader assuming
  otherwise mis-parses the baskets of any sparsely filled tree
  ([Compression §8](spec/01-container/Compression.md)); the **last entry in a
  basket ends at `fLast`**, not at `fEntryOffset[j+1]`, whose slot is never written
  ([Reading entries §1](spec/04-ttree/ReadingEntries.md)); a **fixed array of
  collections** holds `fArrayLength` collections in one frame and the reading
  procedure read only the first ([Collections §13](spec/02-serialization/Collections.md));
  **`flag >= 80` in a basket header is terminal** for the offset array
  ([TBasket §4](spec/04-ttree/TBasket.md)); a **collection of `Double32_t` or
  `Float16_t`** is 4 and 3 bytes per element rather than the declared width,
  because the element has no comment to parse; **`TBranchSTL` has five added
  members**, not three, and `fContName` — the one naming the collection type — was
  among the two that were missing ([Splitting §5](spec/04-ttree/Splitting.md)); and
  **no file carries a `TCanvas` streamer info at all**, so a reader must dispatch on
  the class name ([Canvas §2.1](spec/03-classes/Canvas.md)).
- **The checksum's `[` locator is stricter than this specification said**
  ([Streamer information §11](spec/02-serialization/StreamerInfo.md)). ROOT accepts
  the bracket only when nothing but `/` and whitespace precedes it, so an ordinary
  comment like `// x position [0, 1]` folds **nothing**; the plain search this
  document specified is the rule of checksum variants 6 and below. `TPad` was
  carried as the one unexplained checksum mismatch in the whole corpus and was
  never ROOT's inconsistency — it was this. Nothing is unexplained now, and 698 of
  743 streamer infos recompute exactly. The eight variants were also tabulated as
  one difference each, where every test in `GetCheckSum` is a threshold on an
  ordered code.
- **New: recovering a file whose key list was never written**
  ([Records §1.1](spec/01-container/Record.md)) — the scan ROOT uses, with the one
  condition a third-party reader should *not* copy, since ROOT requires a compiled
  dictionary and a reader without one recovers strictly more. Reading any ROOT file
  includes files nobody closed, and no document had covered them.
- **`fSeekFree == 0` is a one-way signal.** Three places made it an *iff* for
  "never closed". `TFile::Write` writes the free list mid-job, so a crashed job
  leaves a plausible-looking header behind: no field proves a clean close
  ([File header §5.4](spec/01-container/FileHeader.md)).
- **The two corpora are 180 files, not 226.** The published figure counted 48 files
  on one machine that no manifest recorded, so `fetch_cern.py` never fetched them
  and the number could not be reproduced. Two of those files — `aod_flushed.root`
  and `gallery.root` — were cited by the specification as witnesses, and are now in
  `gen/cern/MANIFEST.sha256` and its README; the other 46 were never referenced.
  Re-measured over what the manifests record: **0 failures**, 95% of records decode,
  and 27968 of 28035 branch-baskets have their entries checked.
- **A `TBranchSTL`'s baskets were invisible to the entry checker**, in neither the
  numerator nor the denominator, which is the mistake the embedded baskets taught
  once already. They are now named as skips, and
  [Splitting §5.1](spec/04-ttree/Splitting.md) specifies what they hold — one framed
  `TIndArray` per entry, version word 0 and a checksum, since `TIndArray` is foreign.
- **A foreign class's streamer info must record `fClassVersion` 1** even though the
  object carries a version word of 0
  ([Writing an object §2](spec/06-writing/WritingObjects.md)). A writer that records
  0 to match tells every conforming reader that no checksum follows, and
  desynchronises by four bytes on every tree and every branch. The rule existed only
  in `tools/rootwrite.py`.
- **What the writing layer does not cover is now named**
  ([Writing §4](spec/06-writing/index.md)): the streamer-info **element lists**
  themselves, which exist only in `tools/rootwrite.py` and are the largest thing
  between a third party and a writer; more than one basket per branch, and cluster
  ranges; subdirectories; and a `TLeafC` branch. Three ways to obtain the element
  lists are given, including copying a `StreamerInfo` record verbatim.
- **`TFormula` version 6 is refused by ROOT** and readable by this specification;
  **`TLeafObject` is streamer-info driven at version 2** as well as 4 and above; and
  **`kAnyPnoVT` (70) cannot occur on disk**, where two documents had disagreed.
- `tools/inventory.py` called three unconditionally delegating streamers `guarded`,
  which told a reader there was a legacy layout to implement when there is none;
  fixing it needed a second pass, because requiring the call inside the braces
  reclassified `RooCategory`, which delegates in a trailing `else`, in the
  understating direction.
- New checked invariant: **a key image agrees with the key of the record it points
  at** ([Directories §9](spec/01-container/Directory.md) invariant 11). Nothing had
  compared them — which is exactly the comparison ROOT never makes either, so a
  disagreement is invisible to ROOT and fatal to everyone else.
- **The RNTuple audit's own status was stale in three ways**: ten errata rather than
  six, the type mapping marked unaudited where `NOTES` §4 marks it audited, and two
  fixtures where there are eight. Erratum 1 now reports the real disagreement —
  ROOT's source says the feature flag arrived in **1.1.0.0** where the document says
  1.0.2.1.

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
- Per-layer **invariants** run over **the two corpora this project did not write**,
  from ROOT 2.24/00 to 6.36/02, at **0 failures**. 94% of their records decode and
  96.4% of their branch-baskets have their entries decoded and checked; what the
  rest is, and why, is named file by file rather than averaged away. (The file count
  published with 0.1.0 was 226, which counted files no manifest recorded; the
  reproducible corpus is 180. See the Unreleased entry.)
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
