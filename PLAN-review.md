# PLAN-review — the second consistency review, 2026-09-24

**Status: open. Phases A to D (V1–V30), V31, V32, V41 and V42's false statements done 2026-09-24; §8.1 criterion 1 holds again.** V6 turned out
larger than reported: `_proxyList` has three forms, not two, and the corpus files
match their writers rather than carrying old infos. Items are numbered V1–V44
so that commits and `PLAN.md` can cite them after this file is deleted; the
prefix is new because R1–R8 belong to the first outside review (`PLAN.md` §8.13)
and M1–M9 to the MVP.

Seven read-only reviewers, one per layer, went over every document in `spec/`,
the front matter, and `tools/` on 2026-09-24, at commit `385a3e2`, with the
brief of `PLAN.md` §8.16: correctness against the pinned submodule, byte tables
against the fixtures, self-consistency, completeness of the reading and writing
procedures, and clarity. Between them they opened about 400 cited `path:line`
ranges, recomputed about 50 byte tables with stdlib Python, traced which
`check_invariants.py` comparisons actually execute over the fixtures, and
compared three writing procedures field by field with `tools/rootwrite.py`.

**The result in one line:** the full CI suite passes at `385a3e2`, and none of
the findings below is caught by any check, which is the finding. Nine published
claims are wrong or produce wrong bytes when followed literally (V1–V9), so
`PLAN.md` §8.1 release criterion 1, *no published claim is known to be wrong*,
is **not met** as of 2026-09-24. About thirty more statements are contradictory,
stale or narrower than the format, and the tools have a handful of paths that
turn a failure into silence.

Three patterns account for most of it, and the plan is organised around them:

1. **The numbered procedures diverge from the field text around them.** Four of
   the correctness errors sit in a *Reading* or *Writing* procedure step whose
   surrounding table is right (V1, V3, V10, V11, V12). The `[[bytes]]`
   assertions protect tables; nothing protects a procedure step, and a procedure
   is the part an implementer copies.
2. **The project's description of itself is hand-maintained.** Two front-page
   figures are pinned by a tool and both are current; about fifteen are not, and
   roughly half of those are stale (V27–V30). Scope statements on three pages
   disagree with each other.
3. **Version boundaries written before the tag survey are the shakiest claims.**
   Three more "since ROOT X.Y" statements are wrong (V6, V7, V8), all settled in
   minutes by `git show <tag>:<header>`, the method `PLAN-corpus.md` C9/C11
   established. It has not been run over every boundary the documents state.

The rules of `AGENTS.md` apply throughout. **Never weaken an invariant because a
file disagrees**: where an invariant is wrong here (V13, V14, V15) it is wrong
against the *source*, and the item cites the line. A correction needs no fixture
but does need a `CHANGELOG.md` entry when a reader would now do something
differently. Run one checker process at a time.

## 1. What was verified, and by whom

The distinction is the one `PLAN-corpus.md` §1 made. **Confirmed here** means
the dispatching session reproduced the finding itself against the source, the
fixture bytes or the tags, and the command is in the item. **Reported** means
one reviewer found it with a citation and nothing else has checked it; the first
task of such an item is to reproduce it, and a reported item that does not
survive reproduction is recorded as such rather than silently dropped, because
five of the corpus survey's claims did not survive either.

| Severity | Confirmed here | Reported | Total |
|---|---|---|---|
| HIGH — wrong bytes or a false claim | 9 | 0 | 9 |
| MEDIUM — contradiction, stale text, narrower than the format | 14 | 21 | 35 |
| LOW — citation a few lines off, unit slip, wording | 0 | ~45 | ~45 |

Every HIGH was confirmed before this plan was written. The reviewers' full
reports, with every LOW item and its `file:line`, are not in the repository; the
LOW items are summarised in §7 with enough of a locator to find each one.

## 2. Phase A — nine published claims to fix first

These are one commit, `fix(spec): nine wrong claims from the second review`.
They are the claims that produce wrong bytes or a wrong reader; §8.1 criterion 1
also needs Phase B, because V18 and V19 are false statements too, only smaller
ones, and the stale figures of V27–V28, which are false statements about the
project itself. Each is a small edit; the value is in the commit body, which records what
was wrong and how it was shown.

### V1. `Record.md` §6 step 5 states the compression test as "differs" ✅

`spec/01-container/Record.md:440-441`: "Decompress per Compression if it differs
from `fObjlen`." The rule everywhere else in the document (§3, lines 154–159),
in `Compression.md` §1 and its erratum 5, in `Pitfalls.md` and in
`ReaderChecklist.md` is *compressed iff* `fObjlen > fNbytes − fKeylen`, and all
eight sites in `root/io/io/src/TKey.cxx` (827, 871, 948, 983, 1056, 1116, 1179,
1191) test exactly that. A reader implementing the numbered procedure literally
reproduces the bug erratum 5 records: it rejects every RNTuple page blob whose
payload exceeds `fObjlen` (the `RBlob` at 586 in `RNTuple.root`, `fObjlen` 723,
payload 755). **Fix:** restate step 5 with the inequality. **Confirmed here**
by reading the step and the eight `TKey.cxx` sites.

### V2. `WritingFiles.md` §5 gives the subdirectory key length as 43 + … ✅

`spec/06-writing/WritingFiles.md:333`: "`26 + sizeof("TDirectory") +
sizeof(fName) + sizeof(fTitle)`, so `43 + len(name) + len(title)`". The
arithmetic is 26 + 11 + (n+1) + (t+1) = **39** + n + t. `data/written/nested-subdir.root`
has `fKeylen` 49 at record 401 (`alpha`/`alpha`, 39+5+5) and 47 at 610;
`rootwrite.Key.key_len` (`tools/rootwrite.py:241`) computes 39. A writer copying
the shortcut is four bytes off on every subdirectory key and its `fNbytesName`.
**Confirmed here** from the fixture bytes.

### V3. `WritingTrees.md` §3's `TTree` table is not in streamed order ✅

`spec/06-writing/WritingTrees.md:80-82`: the table is headed "in streamed order"
and lists `fTimerInterval, fUpdate` as one row before `fScanField`. The disk
order is `fTimerInterval, fScanField, fUpdate, fDefaultEntryOffsetLen`
(`ElementLists.md` §7 rows 11–14; `tools/rootwrite.py:3462`). Followed
literally the table emits `0, 0, 25, 1000` where ROOT writes `0, 25, 0, 1000`.
**Fix:** split the row. Then V38, because this is exactly the class of error a
mechanical comparison between a procedure's order and the writer's would catch.
**Confirmed here** against `rootwrite.py`.

### V4. `TBranch.md` §2 has an erratum pasted into the layout table ✅

`spec/04-ttree/TBranch.md:50`: a second row numbered 16, reading "*This
document, until 2026-09-23*: `fBasketSeek[i]` is 0 exactly when slot *i* holds
a basket …", sits between `fZipBytes` and `fBranches`. It is erratum text in the
style of §12, which stops at 16 and does not contain it. A reader parsing the
table gets a phantom member. **Fix:** move it to §12 as erratum 17.
**Confirmed here** by reading the table.

### V5. `References.md` invariant 5 gives the wrong `TRefArray` length ✅

`spec/02-serialization/References.md:312-314`: "payload length is `10 or 12 +
|fName| + 1 + 4 + 4 + 2 + 4 × nobjects`". The formula omits the version word (2)
and the byte count (4). In `data/serialization/references.root` the `TRefArray`
at 658 has byte count `40 00 00 1b` = 27 and a 31-byte payload; the formula
gives 25. `check_invariants.py:1209-1212` checks the invariant by consumption
(`arr.end != end`), so the published arithmetic is never exercised — the pattern
`check_coverage.py` was built to expose, one level down. §4's "27 payload bytes
at 658" is the byte-count *value*, not the payload. **Fix:** restate the formula
and the §4 sentence; consider a unit test that evaluates the published formula
on the fixture, since consumption alone did not. **Confirmed here** from the
bytes.

### V6. `RooFit.md` §4.2 dates `RooRefArray` to 6.26 ✅

`spec/03-classes/RooFit.md:225-228`: "declared `TRefArray` until ROOT 6.26 and
`RooRefArray` after it". At the tags:

```
git show v5-34-00:roofit/roofitcore/inc/RooAbsArg.h   # TRefArray  _proxyList; ClassDef(RooAbsArg,5)
git show v5-34-38:roofit/roofitcore/inc/RooAbsArg.h   # RooRefArray _proxyList; ClassDef(RooAbsArg,6)
git show v6-24-00:roofit/roofitcore/inc/RooAbsArg.h   # RooRefArray; ClassDef(RooAbsArg,7)
git show v6-26-00:roofit/roofitcore/inc/RooAbsArg.h   # RooRefArray; ClassDef(RooAbsArg,8)
```

The change is commit `132f5917f47` (2013-09-20), in the 5.34 patch series. The
corpus observation behind the sentence, `_proxyList` named `TRefArray` in
`uproot-issue-350.root` (header 6.24/00), must therefore be a streamer info
carried over from an older input file, and the `RooAbsArg` `fClassVersion` in
that info will show it (5 if so). **Fix:** re-measure that file's `RooAbsArg`
info, restate the boundary as 5.34/xx by tag, and keep the useful part (same
bytes under two element type names). **Confirmed here** at the tags; the
re-measurement needs `build/foreign/` and is the one corpus step in Phase A.

**Done.** The survey at the tags found three forms: `TList _proxyList` up to
`v5-30-00` (`RooAbsArg` 3, 4), `TRefArray` from `v5-32-00` to `v5-34-05` (5),
`RooRefArray` from `v5-34-06` (6 and later). The two forms also differ by a
frame, so "the same bytes" was wrong too. `RooFit.md` §4.2 has the table and
erratum 6; the reader's comment is corrected.

### V7. `Record.md` §3.4 and §7 date key version 2 to "3.x" ✅

`spec/01-container/Record.md:181-187` and `:446-450`: `1 | 1.x – 2.x`,
`2 | 3.x`, and §7 "5.08 | Key version 4" (correct) beside no row for 2.
`ClassDef(TKey,2)` is already in `base/inc/TKey.h` at `v2-24-05`, the 2000-05-16
import, and at every 2.25/2.26 tag; version 3 is at `v4-00-08`; `v5-06-00`
still has 3 and `v5-08-00` has 4. Where version 1 ended is before the
repository's history and should be stated as unknown rather than "2.x".
`check_versions.py` does not cover `TKey`, so the table is unchecked; V35 adds
it. **Confirmed here** at the tags.

### V8. `Record.md` §3.11 and §7 say a basket key is *always* large ✅

`spec/01-container/Record.md:376-378` and `:457-460`: "`TBasket` keys are always
written in the large layout … regardless of file size". At `v3-10-02` and
`v4-00-08`, `tree/src/TBasket.cxx:69` reads `if (file && file->GetEND() >
TFile::kStartBigFile) fVersion += 1000;`; the unconditional `fVersion += 1000`
first appears at `v4-01-02`, so the production boundary is 4.02. `Pitfalls.md`
63–67 already says this (it came from `PLAN-corpus.md` C2); the normative
document and its version-history table were not updated with it. **Fix:** add
the qualifier and the 4.02 row. **Confirmed here** at the tags.

### V9. `spec/index.md` says RooFit is unwritten and `TASImage` the only gap ✅

`spec/index.md:182`: RooFit's own classes "**being specified**"; `:214-220`:
"The classes are not written yet, so `HandWrittenStreamers.md` still records
each as `out-of-scope`". `spec/03-classes/RooFit.md` has existed since `5d6a95b`
(2026-09-22) and `streamers.toml` marks four of the classes `specified`.
`:184-186`: "`TASImage` is the only **specification** gap that a file in either
corpus reaches" — `RooWorkspace::CodeRepo` is the second (`streamers.toml:275-277`,
`gen/cern/README.md:251-254`), and `README.md:107` already says "two". Also
`PLAN.md:955` repeats "only gap". **Fix:** rewrite the RooFit row and blockquote
as a record of the decision and its outcome, and count the gaps as two.
**Confirmed here** by reading.

## 3. Phase B — procedures and invariants that contradict their own documents

One commit per document or per pair, each with its `CHANGELOG.md` line. These
are the items where a reader who trusts the procedure and a reader who trusts
the field text build different readers.

### V10. `StreamerDriven.md` §9 step 3.4 puts 501 on a `TStreamerSTL` and has no `TStreamerLoop` branch ✅

`spec/02-serialization/StreamerDriven.md:623-624`: "If `fType` is 500 or 501 on
a `TStreamerSTL`, read a collection". `ElementTypes.md` invariant 11.3 says 501
and 521 belong to `TStreamerLoop` only, and `check_invariants.py:1043-1046`
enforces it. Step 3 has no branch at all for 501/521 on a `TStreamerLoop`,
although §3.2 and `ElementTypes.md` §8 specify the read. **Fix:** 3.4 becomes
"500 on a `TStreamerSTL` or `TStreamerSTLstring`"; add a step for 501/521 with
the counter from `fCountName`. While there, `:182` and `:624` write
`02-serialization/Collections.md` as inline code; conventions §6.5 says a
document that exists MUST be a link. **Confirmed here** by reading the step.

### V11. `SchemaEvolution.md` §4 step 1 takes a lone info for any version ✅

`spec/02-serialization/SchemaEvolution.md:164-165`: "If exactly one entry exists
for the class, take it." This contradicts step 3 ("If no entry matches, the
object is not readable") and `StreamerDriven.md` §6 (skip by byte count,
`root/io/io/src/TBufferFile.cxx:3663-3667`). ROOT accepts a lone info only when
the version word equals its `fClassVersion` or is 1
(`TBufferFile.cxx:3505-3517`). `tools/rootfile.py:1509-1512` (`Decoder.info_for`)
implements the spec's version, so two layouts of equal width pass silently —
the "passes by coincidence" class `AGENTS.md` warns about. **Fix:** qualify
step 1 to versions 0/1 and the info's own; change `info_for` to match; note in
the commit whether any fixture or corpus number moves. **Confirmed here** by
reading both.

**Done, and the fallback was hiding something.** Instrumented over the fixtures
and both corpora, the lone-info fallback fired in three files, all written by
g4tools or unknown writers, never by ROOT. In `uproot-from-geant4.root` and
`uproot-issue-250.root` a `TH1D` record opens with two bare version words,
`TH1D` 1 and `TH1` 3; the reader chose the reading one level too shallow, so
`TH1` took version 1 and `TNamed` version 3, each borrowed its only info, and
the read landed exactly on the byte count. With ROOT's rule (version 1 only) that
reading fails and the correct one is chosen; every successful `TH1` read is now
at version 3. Corpus figures unchanged: 48278 of 48501, 0 failures.

### V12. `Collections.md` §13 has no pre-8/pre-9 branch and reads a checksum ROOT does not ✅

`spec/02-serialization/Collections.md:890-919`: step 5.1 always reads a
value-class version word, so a reader following §13 on a file at `TStreamerInfo`
version 7 (`kSTL`) or 8 (`kSTLp`), member-wise, reads two bytes of the count as
a version; §6 documents the frames but §13 never points at it. Step 5.1 also says
"if it is 0 or less, read a `u32` checksum", where `ReadVersionForMemberWise`
reads one only when `cl->GetClassVersion() != 0` (`TBufferFile.cxx:3093-3097`).
`tools/rootfile.py:2692-2704` (`resolve_bare_version`) has the same rule as the
text while `resolve_version` at `:2223-2227` has ROOT's; a member-wise
collection of a `ClassDef(X,0)` class becomes a tolerant skip of something ROOT
reads. Also §6 row 1 cites the `kSTLp` half (`TStreamerInfoReadBuffer.cxx:1166-1169`,
`vers >= 9`) for the `kSTL` case, which is `:1271-1274`, `vers >= 8`;
`ElementTypes.md:704-712` states the two thresholds as one. **Reported**, with
citations; reproduce by reading the two ROOT functions, then fix text and reader
together.

### V13. `ReadingEntries.md` §3 misstates when a `TBranchElement` has an offset array ✅

`spec/04-ttree/ReadingEntries.md:56-61`: `fEntryOffsetLen` is non-zero "unless
the branch is a container node, or `fStreamerType` is …". The source is
`root/tree/tree/src/TBranchElement.cxx:362`: `if (btype || fStreamerType <= kBase
|| …)`, and `btype` is the constructor's branch type — **any non-zero `fType`**,
so 1, 2, 31 and 41 as well as 3 and 4. `data/ttree/split-nested.root`'s
`fDet.fHits.fId` (`fType` 41, `Int_t`) has `fNevBufSize` 1000 and an offset
array `[78, 86, 86, 0]`. The next sentence, "A column of `Int_t` therefore has
no offset array", is false for a column inside a collection. **Confirmed here**
at the source line.

### V14. `TBranchSTL` holds data, and two documents say it does not ✅

`spec/04-ttree/ReadingEntries.md:437` (§7 step 1) "If the branch has sub-branches
and `fType` is not 3 or 4, it holds nothing" and `TBranch.md:392-397` say the
same; `Splitting.md:383-385` correctly says a `TBranchSTL` has sub-branches *and*
its own baskets of `TIndArray` entries, read first (`root/tree/tree/src/TBranchSTL.cxx:381`,
then the element branches at `:453`). `rootfile.TreeReader.holds_data` treats it
as data-bearing. **Fix:** add the exception to both sentences. **Reported**,
citations given; reproduce by opening `TBranchSTL.cxx`.

### V15. Three invariants are stated differently from what is true or checked ✅

- `spec/01-container/FreeSegments.md:217-218`, invariant 2: above 2 GB the
  sentinel "is a multiple of 1000000000". `TFile::Recover`
  (`root/io/io/src/TFile.cxx:2189-2191`) builds it as `fEND + 1000000000`, which
  is a multiple only by coincidence, and `Write()` persists it. §8's closing
  paragraph exempts invariants 5, 6 and 7 for a recovered file but not 2, and
  `check_invariants.py` enforces the multiple. No fixture can show it (needs
  > 2 GB), so it is stated from the source. **Fix:** add 2 to the exemption, or
  restate as "`fEND` + 10⁹ rounded up, or exactly `fEND` + 10⁹ after recovery".
- `spec/06-writing/WritingTrees.md:641`, invariant 4: `fMaxBaskets >=
  fWriteBasket + 1`; `spec/04-ttree/TBranch.md:591`, invariant 1: `>= max(fWriteBasket
  + 1, 10)`. `gen/invariants.toml` routes WritingTrees 9.4 to gate 2, which runs
  `check_invariants.py`, which enforces the 10. A writer that satisfies the
  written invariant with `fMaxBaskets` 5 fails gate 2. One statement changes.
- `spec/02-serialization/ElementTypes.md:754-763`, invariant 11.4: `fArrayLength`
  "positive for a `kOffsetL` code in `[20, 39]` and for 521, 0 for a scalar".
  Codes 81, 82, 85, 86 and 87 are `kOffsetL` forms with positive `fArrayLength`
  (`serialization/element-types` `fObjArr` = 2, `pointer-forms` `fS2` = 2), and a
  `TStreamerSTL` fixed array is stored as 500 with `fArrayLength > 0`
  (`root/core/meta/src/TStreamerElement.cxx:2126-2128` adds `kOffsetL` only on
  read). The checker tests exactly the published clause, so it never sees them:
  not vacuous, but narrower than the format. **Fix:** restate over every
  `kOffsetL` form and 500-on-`TStreamerSTL`, and widen the check.

**Confirmed here** for the `fMaxBaskets` pair (both lines read); the other two
**reported** with citations.

### V16. `StreamerInfo.md` §11 folds a base checksum for every base ✅

`spec/02-serialization/StreamerInfo.md:656-660`, step 2: "for each element that
is a base … `acc_num(id, fBaseCheckSum)`". `root/io/io/src/TStreamerInfo.cxx:3600`
guards it with `el->IsA() == TStreamerBase::Class()`: an STL base
(`StreamerDriven.md` §4.3, a `TStreamerSTL` whose `IsBase()` is true) folds its
name only. `tools/rootwrite.py:1486-1487` is right by accident (`is_base` tests
`cls == "TStreamerBase"`). A checker recomputing the checksum of a class that
derives from `std::vector` gets a different value from the text. **Confirmed
here** at `:3598-3602`.

### V17. Buffer §4's checksum rule misses the foreign version-0 class ✅

`spec/02-serialization/Buffer.md:277-287` and `SchemaEvolution.md:64-71`: info
`fClassVersion == 0` ⇒ no checksum after the version word. `TBufferFile::WriteVersion`
(`root/io/io/src/TBufferFile.cxx:3162-3165`) writes `0` + checksum for any
`version <= 1 && cl->IsForeign()`, including a foreign class whose
`Class_Version()` returns 0, and `ReadVersion` has the explicit branch
`(clversion == 0 && version == 0 && cl->IsForeign())` at `:2973-2974`, with a
comment saying exactly this. No fixture and no known corpus file exhibits it.
**Fix:** state the exception, and state that the file does not distinguish the
two cases (a reader can only try the checksum when the info is version 0 and
foreign-shaped). **Confirmed here** at both lines.

### V18. Five smaller contradictions between documents ✅

- `spec/03-classes/Matrix.md:25`: `TMatrixTBase` "none of its own" vs
  `HandWrittenStreamers.md` `guarded` (`root/math/matrix/src/TMatrixTBase.cxx:1057-1072`).
- `spec/99-appendix/streamers.toml:126-128`, `HandWrittenStreamers.md:115`,
  `Bootstrap.md:134`: `TCollection` "reachable only through `TList`'s fictional
  streamer info". `TBtree` writes a real `TCollection` frame via
  `TSeqCollection::Streamer` (`Containers.md` §3.2, offset 756/760 in
  `classes/containers.root`), and `Bootstrap.md:141` in the same table says so.
- `spec/99-appendix/Bootstrap.md:140`: `TCanvas` "seven trailing bytes, five of
  them `fBits` flags" vs `Canvas.md` §2.1 (seven fields, **eight** bytes, six
  non-members), which is the one checked against `TCanvas.cxx:2319-2337`.
- `spec/index.md:78`, `RooFit.md:3`, `Bootstrap.md:143`: "the five RooFit
  classes with a hand-written `Streamer`". The inventory lists nine `custom`
  RooFit classes (the five plus `RooCFunction1-4Ref`, `RooWorkspace::CodeRepo`)
  and `RooCategory` is `guarded`. Say "the five specified here".
- `spec/02-serialization/Collections.md:987`, erratum 14: ROOT at `TClonesArray`
  v3 "tests its own in-memory bit rather than the file's". `TClonesArray.cxx:756-758`
  tests the in-memory BIT(14) before `TObject::Streamer` overwrites `fBits`, and
  `:811` then tests `CanBypassStreamer()` on the **file's** bit 12, a bit a v3
  writer never set. The reader rule stands; the description of ROOT should give
  both tests, since that is what makes "ROOT cannot be the reference" true.

All **reported**, each with a citation to reproduce from.

### V19. Two offsets and a claim about RNTuple files are wrong ✅

- `spec/01-container/Directory.md:257`: "the free list at 1786" — the header's
  `fSeekFree` in `data/container/directories.root` is 1755 and
  `gen/cases/container/directories/case.toml:100` asserts it.
- `spec/00-conventions.md:132-135`: "the `TObjString` payload ends at offset 392
  with `05 68 65 6c 6c 6f`" — the counted string *starts* at 392
  (`bytes.find(b'\x05hello')` in `file-minimal.root`); the payload ends at 398.
- `spec/99-appendix/Pitfalls.md:37-38`: "RNTuple's minimal writer leaves the name
  empty". Every one of the eleven `data/rntuple/*.root` files has a top key with
  class `TFile`, name equal to the file name and an empty **title**. Say "title",
  or drop the example.

**Confirmed here**, all three, from the bytes.

### V20. `WriterInvariants.md` and `WritingFiles.md` §14 disagree with the checker about what is checked ✅

`spec/99-appendix/WriterInvariants.md:54`: "Every key image in the key list is
byte-identical to the first `fKeylen` bytes of the record … | Directory 9 |
**nothing**". Directory 9.11 checks it field-wise, with `TDirectory` and
`TDirectoryFile` counted as one class name, and `PLAN.md` §9.8 records that the
byte-copy claim was disproved on `uproot-issue64.root`; §7 of the same file
(`:188-190`) says item 2 *is* checked. `:55` cites `WritingFiles 4.1` for an
invariant that is 14.8. `spec/06-writing/WritingFiles.md:1061-1066` says "Items
9 to 15 and 17 are checked", while `check_invariants.py` checks 1
(`FreeSegments 8.1`, `:2744`), 2 (`8.2`, `:2747`), 7 (`Record 8.8`) and 5
field-wise. **Fix:** the row says "checked, field-wise (Directory 9.11)"; the
§14 sentence lists what is checked from `gen/invariants.toml` rather than from
memory. **Reported**; reproduce by reading the two tables against the toml.

**Done, and larger than reported.** The `gen/invariants.toml` reasons for
`WritingFiles 14.1`–`14.15` were misaligned with §14's numbering: written against
an older list, they named the wrong check for most items (14.2's reason was the
record walk, which is item 7). All sixteen reasons are rewritten from a mapping
checked against the labels `check_invariants.py` emits, and §14's closing
paragraph now gives the same mapping. Item 8 is only partly checked (Record 8.6
requires a directory, not the right one) and item 10's spelling not at all.

## 4. Phase C — what the code knows and the prose does not

Each of these is a fact `tools/rootfile.py` or `tools/rootwrite.py` implements
that no document states, or a claim that needs a file to settle. They are the
completeness items, and three of them need a ROOT session or a corpus run.

### V21. Displacement arrays have no reading semantics anywhere ✅

`spec/04-ttree/TBasket.md` §5.3 says what the array holds and stops. ROOT calls
`SetBufferDisplacement(displacement[entry-first])` per entry
(`root/tree/tree/src/TBranch.cxx:1742-1744`), which sets `fDisplacement =
Length() − skipped` (`root/io/io/inc/TBufferIO.h:83`), and adds it to every
back-reference tag read inside the entry (`root/io/io/src/TBufferFile.cxx:2594`,
`:2788`). A reader of an entry containing object references in a circular tree
must apply `offset[j] − displacement[j]` (−5 in `ttree/basket-displacement`) to
tags. `ReadingEntries.md` and `Buffer.md` do not contain the word.
`tools/rootfile.py:3489-3498` parses the array and never applies it; the one
fixture has only fundamental leaves, so nothing shows the omission. **Fix:** a
§ in `ReadingEntries.md`, the reader change, and a fixture whose entries hold
back-references so the rule is exercised (a split object with a `TRef` to
another member is the smallest). Needs ROOT to generate. **Reported**, with
citations; two reviewers found it independently.

### V22. The update procedure's free-segment record can shrink after it is sized ✅

`spec/06-writing/WritingFiles.md` §13: when the free-segment record is placed
during an update it can take an exact-fit span, which removes an entry, so the
payload comes out shorter than the `fObjlen` sized before placement. ROOT
zero-pads the remainder (`root/io/io/src/TFile.cxx:2652-2654`);
`tools/rootwrite.py:1193-1200` reproduces it and `_read_free` (`:765`) skips the
zero padding. Nothing in §9 or §13.4 tells a writer, and §3 step 7's "simple
arithmetic, not a fixed point" is true only for a create. **Reported**; the
`reopen-reuse` case is where to check whether the padding appears in the
byte-identical file.

### V23. `fClusterSize` under a negative watermark ✅

`spec/06-writing/WritingTrees.md` §7.4 says `fClusterSize[i]` is "the watermark
that was in force" and does not say what is recorded when the watermark is
negative: `MarkEventCluster` writes `fEntries` for the first range and the
difference of the two ends otherwise (`root/tree/tree/src/TTree.cxx:8492-8497`);
`rootwrite.Tree.mark_cluster` (`:3378-3384`) implements it. **Reported.**

### V24. Two legacy read branches, and the scope floor they imply ✅

`root/io/io/src/TStreamerInfoReadBuffer.cxx:1380-1387`: for a file with header
`fVersion < 30208`, code 81 (`kObject+kOffsetL`) is rerouted to the `kStreamer`
case, read through a `bc ver` frame rather than as bare back-to-back objects.
`:1414-1426`: for an info at `TStreamerInfo` version < 3, an 85/86/87 element is
skipped entirely when `count <= 0 || v != fOldVersion`. Neither is in
`ElementTypes.md` §7.2 nor `StreamerInfo.md` §6.1's version-consequence table,
which lists < 3 only for the collection encoding. No file in either corpus is
affected (the oldest infos are ROOT 3.03). **Fix:** either state both branches or
state, in `spec/index.md`'s scope section, that streamer infos written before
3.02.08 are outside the reading floor. The second is honest and cheaper; decide
and do one. **Reported.**

### V25. A top-level STL collection's count title may keep its trailing dot ✅

`spec/04-ttree/Splitting.md:167-185` (§3.3) and invariants 3/4: "A collection or
`TClonesArray` count branch's title is the name it was constructed with, a
trailing dot removed and an underscore appended", citing
`root/tree/tree/src/TBranchElement.cxx:985-989`. That range is `branchname += "_"`
with **no** dot removal, unlike the three other sites (`:818-825`, `:579-585`,
`:633-639`), and `TTree::BronchExec` passes `name` through unchanged
(`root/tree/tree/src/TTree.cxx:2520`) while `BuildTitle` strips it for the member
titles (`:1185-1189`). By the source, `Branch("v.", &vec, 32000, 99)` on a
`std::vector` of a dictionary class gives count title `v._` and member titles
`fX[v_]`, which breaks Splitting invariant 4 on a ROOT-written file. **Needs a
generator run**; ROOT is not on PATH in the session that wrote this. If it
reproduces, it is a fixture, a narrowed invariant with the ROOT line, and a
`PLAN.md` §7.1 bug candidate. **Confirmed here** at the source level only.

### V26. Re-measure `RooAbsArg` in the two files V6 relied on ✅

The corpus half of V6: read the `RooAbsArg` streamer info's `fClassVersion` and
`_proxyList` type name in `uproot-issue-350.root` and `stressRooFit_v522_ref.root`
(`build/foreign/`, after `tools/fetch_foreign.py`). Expected: version 5 with
`TRefArray` in both, which makes the 6.24 file a carrier of a 5.2x-era info and
the sentence in `RooFit.md` a statement about infos rather than releases.
Record the result in the erratum.

**Done.** Not what V6 expected: `stressRooFit_v522_ref.root` (5.21/07) has
`RooAbsArg` 4 with a `TList`, `stressRooFit_v534_ref.root` (5.34/04) 5 with a
`TRefArray`, and `uproot-issue-350.root` (6.24/00) 7 with a `RooRefArray`. Each
file matches its writer; the published sentence had simply misread the third.

**Phase C done, V21–V25, with ROOT 6.40.04 from a local conda environment.**
V25's suspicion did not hold: the collection constructor drops the dot at
`TBranchElement.cxx:906-909`, before the cited lines, so the claim was right and
its citation incomplete. What it found instead is that a trailing dot changes
nothing below a top-level split collection, which §3.1 now says, with a fixture.
V21 was larger than reported. The reader now applies the displacement, but a
fixture with back-references showed that ROOT's displacement is right only for
an entry moved once: `MoveEntries` overwrites it on each move, and ROOT 6.40.04
reads 13 of 15 twice-moved entries with a pointer silently null. That is
`PLAN.md` §7.1 item 16; the reader reports such entries as a named skip. V24
measured both legacy branches as unwitnessed (754 version-2 infos, none with
85–87; no code 81 below 3.02/08) and documents them rather than only declaring a
floor. Corpus figures unchanged.

## 5. Phase D — the project's description of itself

One sweep, one commit, then a check so it cannot recur. The reviewer recomputed
every figure below at `385a3e2` with stdlib Python, `find` and `git`; the
recomputed value is the one given.

### V27. Stale counts in `Bibliography.md` ✅

`spec/99-appendix/Bibliography.md:63-75`: "155 files, all of which this project
uses" (scikit-hep-testdata) → the `gen/foreign/` manifest has 180 lines and
since C9/C13 includes go-hep's `leaves.root` and the 23-file RNTuple tier, so
neither number nor "all" holds; "34 of them: 26 downloaded, and 8 multi-gigabyte
files" → 72 in `gen/cern/MANIFEST.sha256` and 11 rows in `LARGE.toml`; "`data/`
holds 76 small files … plus the 9 in `data/written/`" → 87 and 14. Also `:14`
"the ten places" (RNTuple errata) → thirteen. **Confirmed here** for lines
68–75.

### V28. Counts on the front pages and in the appendix that were never re-measured ✅

| Where | Says | Is |
|---|---|---|
| `spec/index.md:119-122` | "256 `Invariants` entries … nine cases where nothing does" | 267; `WriterInvariants.md` §7 lists ten |
| `spec/index.md:81` | Pitfalls "forty-five facts" | 48 bold-led entries |
| `spec/index.md:184`, `PLAN.md:866` | "ten" hand-written `gap` classes | 12 `gap` rows (`PLAN.md` §2.4 itself lists twelve) |
| `spec/index.md:183` vs `PLAN.md:2469` | "137 without LZ4" / "132 records" | never reconciled; re-measure or delete one |
| `spec/index.md` §"What is missing" | every non-decoding record has a row | the probe of 2026-09-24 also reports ~165 RNTuple records through the classic-object path (95 `no streamer info for RBlob`, 34 multi-page `RBlob`s, 29 `ROOT::RNTuple: consumed 70 of 78 bytes`, …); give them a row or exclude RNTuple from the count, and say whether the anchor's 8 unconsumed bytes are a probe gap |
| `spec/99-appendix/ReaderChecklist.md:195`, `Bibliography.md:14` | "ten" RNTuple errata | thirteen |
| `spec/06-writing/index.md:160` | "99.8% of branch-baskets" | 99.5% (48278 of 48501) |
| `spec/06-writing/WritingObjects.md:291-292` | "614 of the 653 streamer infos" | 698 of 743 (`StreamerInfo.md` §11.2) |
| `spec/03-classes/Canvas.md:104,175` | "305 files" | 306/307 elsewhere; explain or align |
| `PLAN.md:2450` | "Twelve upstream bug candidates" | §7.1 has items 0–15, item 2 withdrawn: 15 |
| `PLAN.md:2645-2700` (§9.11) | 1001 of 27949; 67 of 28036; "178 corpus files" | pre-2026-09-24 figures; item 6 alone was refreshed |
| `PLAN.md:2065-2075` (§8.14) | "Ten published claims" | nine table rows; find the tenth or say nine |
| `gen/cern/README.md:162` | "`root/roottest/` — 16 files" | 39 table rows |
| `gen/cern/README.md:227-232` | "1696 of 1696" branch-baskets, run 2026-09-21 | predates the denominator change; re-run or date it |
| `spec/99-appendix/Pitfalls.md:5-7` | "Thirteen were found by checking … against files" | README says nineteen; say which population |

### V29. Scope statements that disagree across README, index and checklist ✅

- `spec/index.md:100-104` "Four documents (the container, an object, histograms,
  a flat `TTree`)": `spec/06-writing/` has six; `:28-30` and
  `spec/06-writing/index.md:65-71` likewise omit `WritingGraphs.md` ("the other
  four documents"); `README.md:121-124` omits graphs, subdirectories and update.
- `spec/index.md:144-149` and `CONTRIBUTING.md:154-156`: "Free-space reuse,
  basket sizing and key ordering are left unspecified" — `README.md:118-119`
  and `WritingFiles.md` §8.1 specify the allocator and the ordering (landed
  2026-09-21). Basket sizing alone is still free.
- `spec/99-appendix/ReaderChecklist.md`: `:237-238` "leave RooFit out … a
  per-experiment concern" vs `:139-142` "do RooFit early"; `:235-236` `TBranch`
  below version 10 "not fully specified" vs `spec/index.md:193-195` and
  `TBranch.md` §13.1; `:226-230` lists the writing procedures as of 09-18;
  `:136` `TMatrixTSym` "the only class whose bytes continue past its own byte
  count" vs the three `extending` classes; `:9-11` sends the reader to
  conventions §1 for scope, which is in `spec/index.md`; `:171-175` "eleven
  conditions" is not a phrase `TBranchElement.md` uses (§8 is organised by
  eleven *members*); `:25` and `Pitfalls.md:163` "four string encodings" where
  conventions §5 defines five.
- `README.md:70-72` "Every object-bearing record in `data/written/` is
  byte-identical to the one ROOT wrote" vs `spec/index.md:52` "In twelve of
  them". Index is right (`two-versions` cannot be, `objstring` has no ROOT twin
  with the same key, `graph.root`'s `gy` is one ROOT cannot produce).
- `CITATION.cff:12-20` abstract lists four layers and omits the writing layer
  and the RNTuple audit.

### V30. Missing `CHANGELOG.md` entries, and a check so figures stop drifting ✅

`## Unreleased` has no entry for `spec/03-classes/RooFit.md` itself (`5d6a95b`,
six newly decodable classes), nor for five of the eight §8.13 corrections
`README.md:41` advertises: `kIsCompiled` → `kBuildOldUsed` (`52521f3`),
`StreamerDriven.md` invariant 5 restated as §6.1 (`cc480ff`),
`ElementTypes.md` invariants 3 and 4 (`181811b`), `fCheckSum` 0 and `TTime`
(`6be84ff`), `Collections.md` §3.1 pointer framing (`cc968a1`). Write them.

Then the check. `tools/check_citations.py` pins two figures (the citation total
on `README.md` and `spec/index.md`); everything in V27–V29 is pinned by nothing.
Add a small `gen/figures.toml` — each figure that appears on more than one page,
with the command or the expression that recomputes it — and a `--check` that
recomputes what stdlib can (case count, `[[bytes]]` count, document count,
errata rows, invariant entries, manifest lines, `gap` rows, Pitfalls entries)
and greps every listed page for the value. A figure that can only come from a
corpus run is listed with its date, and the check requires the date to appear
beside it. `CONTRIBUTING.md:32-39`'s check list also omits `check_coverage.py`,
`check_write.py` and `element_lists.py`; add the new one and those.

**Done, V27–V30.** Every figure in the tables above is corrected, each
re-measured rather than copied from another page: the probe over both corpora
(which also showed the "What is missing" table had never listed 165 RNTuple
records; the probe now reads anchors with the RNTuple reader and counts `RBlob`s
as RNTuple data, so blocked went from 191 to 26), the LZ4 figure in an
environment without `lz4` (132; `PLAN.md` was right and `spec/index.md` wrong),
the `gen/cern` entries (1696 of **1761**, not of 1696), the `TCanvas` scan (352
files), and the gap and bug-candidate counts. §8.14's "ten" was right; the table
had merged two C11 claims into one row. `tools/check_figures.py` now recomputes
sixteen figures and checks 40 statements of them across nine pages
(`gen/figures.toml`), in CI's `spec` job; a stale value fails with what the page
says and what it should.

## 6. Phase E — the tools

### V31. The unit tests never run with the submodule in CI ✅

`.github/workflows/docs.yml:30` runs `python -m unittest discover -s tools`
without `submodules: true`; `ci.yml:51` checks out the submodule and never runs
the tests. Simulated without the submodule: 628 tests, `OK (skipped=27)`, and
the 27 skips are every submodule- and roottest-gated assertion —
`test_inventory` against the submodule, `test_versions.py:138`,
`test_rntuple.py:79`, `test_streamer_driven.py:441/833`, `test_ttree.py:1726`,
`test_coverage.py:151/160`, `test_container.py:505`, and
`test_provenance.py:63-82`'s roottest-identity check, which `AGENTS.md` and
`LICENSE` present as the guard against committing an LGPL file. No step asserts
the skip count. **Fix:** run the tests in `ci.yml`'s `spec` job after the
checkers, with the codecs installed, and fail on `skipped=` above a stated
floor (or make the submodule tests error rather than skip when `root/` is
absent). `AGENTS.md` lists the tests in "the full check suite, in the order CI
runs it"; make that true. **Confirmed here** by reading both workflows.

### V32. Four places where a failure becomes silence ✅

- `tools/generate.py:118`: `DRIFT` is raised only `if rel in known`. A case with
  no line in `data/MANIFEST.sha256` passes `--check`; the non-check path merges
  it in silently. A missing line should be a failure in `--check` mode.
- `tools/inventory.py:705,716`: `doubts` print `UNRESOLVED` but the exit is
  `1 if problems`; `--check` tests `problems or stale`. The forwarding list has
  no doubts today, so it is latent. A doubt should fail `--check`.
- `tools/check_invariants.py:4312-4324`: an `IGNORE.toml` entry that suppresses
  nothing prints nothing, while `gen/foreign/IGNORE.toml:12-14` claims a stale
  entry "shows up as suppressing nothing". Print `IGNORED 0 x …` for every
  entry, and consider making zero a failure over the full corpus. The `IGNORED`
  line also hard-codes `(gen/foreign/IGNORE.toml)` regardless of `--ignore`.
- `tools/check_invariants.py:184-186`: `Collections 14.11` (a `This` element
  names its own class) has no witness in `data/`; its loop body never runs over
  the fixtures, so the `AGENTS.md` rule "confirm it catches a violation by
  corrupting a copy of a fixture" cannot have been followed, and there is no
  unit test. Either a fixture with a `This` element (a class deriving from
  `std::vector`, ACLiC) or a unit test built on a synthetic info.

**Confirmed here** for the first three by reading the lines.

**Done.** V31: a `tests` job in `ci.yml` with the submodule, the docs and codec
requirements, and a step that fails on any skip whose reason names the
submodule, roottest or the git checkout. Simulated in a worktree without the
submodule: 19 such skips, all caught; 0 with it. The 8 remaining skips are
`build/` corpus files, which CI does not fetch. V32: `generate.py` fails on a
case with no manifest line and on a line no case produces (both mutation-tested);
`inventory.py` fails on a doubt; `check_invariants.py --ignore` reports every
entry and fails on one that suppressed nothing (none does over the corpus; a
bogus one fails); `Collections 14.11` has three unit tests. Adding those
tests found one more silence: the new class was named `ThisElement`, which an
existing class already was, so five older tests stopped running with nothing
reported (the count went from 640 to 638). `tools/test_hygiene.py` now fails on
any name defined twice at the top level of a test module or within a test class.

### V33. `rootfile.py` paths that swallow a failure into "absent" ☐

- `:3835-3838` (`_embedded_baskets`): `FormatError`, `struct.error`,
  `IndexError` and `ValueError` all make the slot silently absent;
  `TreeReader.basket_for` (`:4461-4477`) then falls through to `fBasketSeek[i]`
  — a seek of 0 becomes a "basket unavailable" skip (a reader bug reported as a
  missing basket), a stale non-zero seek checks a different basket's bytes.
- `:4174-4177` (`_read_branch_ref`): a `KeyError` (a member the reader expected)
  returns `None`, and the `fBranchRef` branch disappears from
  `TreeReader.branches` and from the `ENTRIES` denominator with no skip line —
  the mechanism that hid 1266 baskets before 2026-09-17.
- V11's `info_for` and V12's `resolve_bare_version`, listed there.
- Displacement is parsed and never applied (V21).

Each becomes a named skip or a failure; then re-run both corpora once and record
whether `48278 of 48501` moves, because that number is quoted in five places.
**Reported**, each with a line.

### V34. Corruption tests for the invariants that have none ☐

About 150 of the 199 checked labels have no test that corrupts a fixture and
asserts the label fires; `Compression 9.7`, which `PLAN-corpus.md` C7 found
vacuous once already, is among them. `check_coverage.py:15-18` says as much
about itself. A full sweep is not the ask; the ask is a test per label that has
been wrong before (the §8.13, §8.14 and §8.16 lists, and V5, V15) and a
one-line note in `gen/invariants.toml` on which labels still have none, so the
worklist is visible rather than implied.

### V35. `check_versions.py` should validate the cited line, and cover `TKey` ☐

`spec/06-writing/WritingGraphs.md:352-353` cites `TList.h:80` (a blank line) and
`TH1.h:672` (`Smooth(...)`) for `ClassDef`s that are at `:115` and `:902`;
`check_versions.py` passes because it matches by class name in the table, not by
the cited line, and `check_citations.py` passes because the lines exist. Having
`check_versions.py` also require the cited line to contain `ClassDef` closes the
gap between the two tools for the one kind of citation where it can be closed
completely. Add `TKey` (V7) to the classes it reads. **Confirmed here** for the
two wrong lines.

### V36. Smaller tool items ☐

- `tools/rootwrite.py:265-267, 874-878`: `Key.parse` and `reopen` read counted
  strings with a single length byte and no 255 escape; a reopen of a file whose
  name or title is ≥ 255 bytes mis-parses silently. Document or fix.
- `tools/rootwrite.py:865-869`: `reopen` refuses any `fBEGIN != 100` with the
  message "a file whose header is shorter than 75 bytes cannot be pushed past
  2 GB", which is wrong for `fBEGIN > 100`; `WritingFiles.md` §13.8 says the
  writer declines below 75.
- `tools/rootwrite.py:2551`: the `Graph` docstring says `SetMinimum`
  "multiplies the record's size by six"; `WritingGraphs.md` §3.4 says five
  (1213/245). `:2523-2524` names `TGraph::Build` at `TGraph.cxx:174` for
  `kClipFrame`; the function is `CtorAllocate` and the `SetBit` is at `:838`.
- `tools/check_invariants.py:1015` exempts every `TStreamerSTL` from 13.11
  while `StreamerInfo.md:838-839` scopes the legitimate failure to files before
  6.24/02.
- `tools/check_invariants.py:775` prints `NOT CHECKED TMap/TExMap/TBtree has no
  streamer info in its own file` on `classes/containers.root`, for classes
  `Containers.md` §4 says never have one; the message suggests a gap where
  there is none.
- `tools/check_invariants.py:420` `bad("Compression 9", …)` is an unnumbered
  label for a real failure (decompressed length ≠ `fObjlen`); give it a number
  or publish the invariant.
- `Buffer 9.3` is labelled only when `read_tlist` raises (`:827`); nesting is
  enforced by `decode_record` under `StreamerDriven 10.1`. A line in
  `gen/invariants.toml` so 9.3 is not read as independently checked.
- `gen/README.md` documents `id/file/size/[[bytes]]`; the `gen/cases` files
  carry ~610 `[[records]]` tables that only `check_write.py` reads, so for
  `gen/cases` they are unverified prose. Either check them or say they are
  documentation. `check_bytes.py:27-29` also accepts `*le` types the README
  omits.
- `tools/rootfile.py:2253`: `read_branch` dispatches `version < 10` to the
  `v > 5` legacy layout with no floor; ROOT's `< 6` order differs
  (`TBranch.cxx:3111-3150`). Unreachable today (the 2.23/12 file has no infos);
  say so in a comment or add the floor.
- `check_coverage.py` reads only the first `Invariants` heading per document; a
  second would be ignored silently. A guard costs one line.

### V37. `fetch_cern.py --headers` runs nowhere in CI ☐

It is the only thing that exercises the large-file layout at all
(`AGENTS.md`), and `LargeFiles 8.6` is `not-checkable` in `gen/invariants.toml`
for that reason. A scheduled or manual workflow that runs it (≈25 KB of
traffic) would make the reason "checked weekly" rather than "checked by
nobody". Decide; the cost is one workflow file.

### V38. A test that compares each writing procedure's order with the writer's ☐

V3 would have been caught by a test that, for each `spec/06-writing/` table
headed "in streamed order", reads the member names in table order and compares
them with the element order `rootwrite.py` emits for that class (which
`element_lists.py` already has from the fixtures). The tables are regular
enough to parse. This is the check for pattern 1 in the writing layer; the
reading layer's equivalent is V39.

### V39. Reconcile every Reading procedure step against the field it names ☐

Not a tool: a reading pass, one document at a time, taking each numbered step in
every *Reading* section and finding the sentence in the same document's field
text that it summarises, then the source line. V1, V10, V11, V12 and V14 are
what this pass finds; the reviewers covered every procedure once, so the pass
is a second reading with the specific question "does this step say what the
table says". Record in the commit which steps were re-read and found right, so
the pass is not repeated.

## 7. Phase F — the LOW items, one sweep

Fix in one commit per document, no changelog entries unless a reader would act
differently. Locators are as the reviewers gave them.

### V40. Citations that land a few lines from the claim ☐

`check_citations.py` cannot see these (the line exists); each was opened and the
supporting line is a few away. `Directory.md:266` `TFile.cxx:3522` → `:3555`
(`fKeys->Remove`); `Record.md:360` `TKey.cxx:254` → `:255`;
`TLeaf.md:52-54` `TLeaf.cxx:444-449` is `SetAddress`, which `Streamer` calls at
`:504`; `StreamerDriven.md:44` `:1362-1379` covers 61/62 only, 63/68 are at
`TStreamerInfoReadBuffer.cxx:1084-1096`; `StreamerDriven.md:224` `:826` → `:836`;
`Buffer.md:328-329` `ReadClass (:2740)` is the `R__ASSERT`, definition two lines
up; `ElementTypes.md:576-578` `:730` → `:732`; `StreamerInfo.md:762-763`
`TClass.cxx:6604-6609` is `MatchLegacyCheckSum`, the claim is at `:6650-6655`;
`Containers.md:225` `TClingUtils.cxx:3016` → `:3017`; `References.md:130`
`TRef.cxx:489` is the read side, the write is `:515`; `Collections.md:682`
`TGenCollectionStreamer.cxx:1400-1402` is the read dispatch, the write is
`:910-911` → `TBufferFile.cxx:1985`; `Collections.md` §6 row 1 (see V12);
`WritingGraphs.md:352-353` (see V35).

### V41. Unit and arithmetic slips ✅

`TTree.md:22-26` "four bytes later" → six (a 4-byte count and a 2-byte version);
`Splitting.md:341-347` describes three entries as "byte count of 13", "11 bytes",
"12 bytes" where the bytes are 17/15/16 — pick one unit; `WritingGraphs.md:64`
"4 + 11 + 4 + 2 + 15" sums to 36 for a 35-byte slot (the `TList` class record is
10); `WritingGraphs.md:252-253` "11708-byte record" vs `:287` "11772" (the second
includes the 64-byte key; every other figure is payload); `ElementLists.md:69-72`
"two" subclasses without an example → three (`TStreamerSTLstring`);
`ElementLists.md:153, 574-577` "every file needs these nine infos" vs §11 and the
fixtures (one); `WritingObjects.md:223` info `fTitle` "= its comment" → empty,
as `ElementLists.md` §1 already says; `ReaderChecklist.md:41-43` "all four
documents above" under a five-row table.

**Done.** Every item verified against the bytes first. Two more stale figures
turned up on the way: the "743 infos, 698 recomputed" of three pages is now 1000
and 937 with the fixtures added since, and it had gone stale once before, so
`gen/figures.toml` now pins it too (skipped, with a message, when a codec is
missing). Re-reading V42 for this showed that several of its items are false
statements rather than wording: `TLeaf.md`'s `nbits ≤ 31`, `StreamerDriven.md`'s
`fBits` claim about the corpus, `Buffer.md`'s "cannot be written", `Pitfalls.md`'s
"ROOT 5 and later" for `fType` 500, `RooFit.md`'s diagram pointing at §2.3, and
`SchemaEvolution.md`'s "up to 5.34.18". Criterion 1 waits on those as well.

### V42. Wording a reader would misread ◐

`TLeaf.md:364` `nbits ≤ 31` excludes the legal 32 (`TStreamerElement.cxx:141-148`;
`ElementTypes.md` §5 has it right); `TBranchElement.md:45` a column headed
`fType` that holds streamer-element codes, two rows above the member `fType`;
`TBranchElement.md:375` the `fType 0, fID −1` row omits that ROOT first tests
`hasCustomStreamer` (`TBranchElement.cxx:5795-5803`), a reader-side property;
`TBasket.md:385-389` "every `TBranchElement` constructor delegates to `TBranch()`"
— the sub-branch constructor copies the parent's features (`:294-295`), the
conclusion holds, the reason is incomplete; `ReadingEntries.md:51` and
`WritingTrees.md:402-404` say the offset array's extra element "is 0" where
`basket-displacement` has −14/−9 (`TBasket.md` §5.1 says it right); `Buffer.md:76-78`
"cannot be written" — the word is already written, ROOT only calls `Error`;
`StreamerInfo.md:252` "strict byte-count check" — both branches tolerate, one
reports; `StreamerInfo.md:449-450` `fCountName`/`fCountClass` typed "string" →
counted string; `StreamerDriven.md:67-69` "no element in the reference corpus has
`fBits` other than 0 or 0x40" vs `Buffer.md:524-526`'s `0x03000000` on a 6.20
file — say "in `data/`"; `ElementTypes.md:704-712` the two second-version-word
thresholds (V12); `Record.md:230-232` `fSeekPdir` "rejected everywhere else" —
only `ReadKeys` on key-list images; `Directory.md:435-438` walking by class name
vs `ReaderChecklist.md:32-35`'s "structurally" — reconcilable (the hazard is the
root record's class name), but say so; `Directory.md:452` invariant 4
generalises ROOT's root-only `fNbytesName` check (`TFile.cxx:841`) to every
directory, and a subdirectory with a title near `kTitleMax` would violate it
while ROOT reads it; `FileHeader.md:164-166` `fEND` is also compared at
`TFile.cxx:875`; `FileHeader.md:423` "read at least 100 bytes" in a document
that insists `fBEGIN` may be 64; `Compression.md` 9.5 is checked as a block
count plus a cap, weaker than "every block but the last declares exactly
`0xFFFFFF`", and no multi-block fixture exists; `SchemaEvolution.md:94-103` era
"up to 5.34.18" → "and v5.99/06" (`TClass.h:116-119`); `References.md:104-108`
two sentences that read as contradictory (the pid record is before, the target
may be after); `RooFit.md:56` diagram "(§2.3)" → `Buffer.md` §6;
`Pitfalls.md:135-137` `fType` 500 "in everything ROOT 5 and later wrote" → forced
from `v4-00-01` (`PLAN.md` §8.15); `00-conventions.md:348` free segment "not
occupied by any record" vs `Glossary.md:22` "no live record" (Glossary is
right); `05-rntuple/index.md:53` "the three errata in between"; `WritingHistograms.md:113-114`
"free, with constraints — the default is mandatory" → "fixed in practice";
`WritingFiles.md` §7 never states the `StreamerInfo` key's `fTitle`
(`"Doubly linked list"`), which sizes `fKeylen` and every map position;
`ElementLists.md:55-57` the Extra column's order is not the disk order;
`streamers.toml` `TStringLong:158` and `TBranchClones:154` `spec` strings lack
`§` and an anchor, and specified entries sit under a `# gaps` header;
`WriterInvariants.md:3-7` "organises the same material" overstates a document
that covers five of the layers' invariant sections; `Formula.md:21` `TFormula`
v6 lived between `v3-10-02` (5) and `v4-00-08` (7), so the "—" release column
may understate.

**Factual subset done.** Ten were false statements, each checked before it was
changed: `TLeaf.md` `nbits` 32; `StreamerDriven.md` `fBits` (true of `data/`, not
of pre-6.30 files); `Buffer.md` "cannot be written" (written, then an error);
`StreamerInfo.md` §6.1's "strict" row; `Record.md` §3.6 `fSeekPdir` (checked
only on key-list images); `Directory.md` invariant 4 (the top directory only,
and the check now matches); `FileHeader.md`'s "only to detect truncation";
`SchemaEvolution.md`'s variant eras; `Pitfalls.md`'s `fType` 500 (every ROOT file
available has it back to 3.04/02, not only ROOT 5); `RooFit.md`'s diagram
reference; `TBasket.md`'s constructor sentence; the Conventions free-segment
definition; the "extra offset slot is 0" in two documents; `References.md`'s two
sentences; `WriterInvariants.md`'s scope. `Formula.md`'s "—" for `TFormula` v6
was right: that version lived three days in 2004 and no tag has it, now said.
Left, as wording or missing detail: `TBranchElement.md`'s `hasCustomStreamer`
note, `FileHeader.md` §9's "100 bytes", the Directory walk wording, the RNTuple
index's "three errata", the `WritingHistograms` kind label, the `StreamerInfo`
key's `fTitle`, the Extra column's order, `streamers.toml`'s headers, and the
`Compression 9.5` check strength.

### V43. Whether `TBranchElement` invariant 5 is an invariant ☐

`spec/04-ttree/TBranchElement.md:431-433`: "On `fType` 3 and 4 that leaf is
always a back-reference". The leaf is created before `Unroll`
(`TBranchElement.cxx:975-996`) and becomes a back-reference only because a
sub-branch leaf's `fLeafCount` writes it first. A collection whose value class
has an info with no elements would get no sub-branches and a leaf written in
place. Measured 105/105; decide whether it is an invariant or an observation,
and if the latter, move it out of *Invariants* with the reason. **Reported,
unsure.**

### V44. Discharge ☐

When V1–V43 are worked or explicitly set aside: a `PLAN.md` §8.17 in the shape
of §8.16 (what the review was, the three patterns, the count of wrong claims
and where each stood, the checks added so the class cannot recur), the
`CHANGELOG.md` entries, the §8.1 criterion 1 paragraph updated with the date it
held again, `AGENTS.md`'s and `CONTRIBUTING.md`'s "no open sub-plan" sentences
restored, and this file deleted. Anything set aside becomes a ⏸ row in §9 with
this plan's item number, so it can be cited after the file is gone.

## 8. Order of work

1. **Phase A** (V1–V9) as one commit, then push, because criterion 1 is down
   until it lands. V6's corpus half (V26) can follow.
2. **Phase B** (V10–V20), a commit per document. V11 and V12 change the reader;
   run both corpora once after them and quote the `ENTRIES` line in the commit.
3. **Phase E's** V31 and V32 next, before more spec work, because they are the
   ones that let the next mistake through: unit tests with the submodule in CI,
   `generate.py` drift on a missing line, `inventory.py` doubts.
4. **Phase D** (V27–V30) as one sweep ending in the figures check, so the sweep
   is the last one done by hand.
5. **Phase C** (V21–V26), which needs ROOT for V21 and V25 and the corpus for
   V26; batch the ROOT work.
6. **The rest of Phase E** and **Phase F**, then V44.

The things this plan does not do: re-run the corpora to re-measure every
corpus-derived count in the documents (the reviewers could not verify any of
them, and nothing suggests they are wrong beyond the ones in V28); re-verify
gate 3 (`check_write.py --root`) or the ROOT-session behaviours the writing
documents report; re-derive the release columns of the `TTree`,
`TBranchElement` and `TLeaf` version tables at the tags, which V7/V8 suggest is
worth doing and which is a candidate for a `check_versions.py --tags` mode
rather than a hand pass.
