# PLAN-review — the rootfilespec review, issue #1

**Status: in progress.** Written 2026-09-21; **R1–R7 done** the same day — the
three defects of §2, all four gaps of §3, the item-3 attribution, and §4.1's
corpus question. The reply and R8 remain. Every item below was re-checked against
the corpora and against our own reference files *before* being planned, and the
verification is recorded per item, because the point of a review is what it turns
out to be right about.
[Issue #1](https://github.com/ariostas/root-io-spec/issues/1) is the first
review of this specification from outside it.
[rootfilespec](https://github.com/nsmith-/rootfilespec) — a pure-Python,
dataclass-based ROOT reader — vendored `spec/` as a submodule, checked its own
hand-written bootstrap layer against it, and sent back the traffic in the other
direction: ten places where their code or their corpus knows something this
specification does not say, plus six corroborations.

Two things about it are worth recording before the items.

**It found three defects, not six gaps.** The issue is framed politely as
"possible spec changes", and four of its six items are indeed gaps — things true
of files in the wild that our documents do not mention. But three of the things it
points at are **wrong** rather than **missing**, and two of those are contradicted
by reference files already committed in this repository. `PLAN.md` §8.1 release
criterion 1 is "no published claim is known to be wrong"; as of this review it is
not met, and R1–R3 are what it takes to meet it again.

**Their corpus is bigger than ours.** They test on scikit-hep-testdata, 235 files;
`gen/foreign/` was 154 of them, and is 155 since R6 added the one their item 4
needed. Two of their findings rested on files we did not have, which was a corpus
decision (§4) rather than a doubt about the finding.

## 1. What was verified, before planning

| # | Their claim | Checked how | Verdict |
|---|---|---|---|
| 1 | Directory records of version **1001** exist | read both files | **Confirmed** — and it found a bug in our reader, R1 |
| 2 | `fBEGIN = 64` with `fVersion = 40000` | read both headers | **Confirmed** |
| 3 | `uproot-issue413.root` is groot's fixture, not uproot's | corroborated from the bytes, not proven: Go type spellings, and its basket keys are not ROOT's | **Credited** (R5) |
| 4 | `fCheckSum == 0` occurs in a `TStreamerInfo` | scanned every info in the 218 corpus files whose `StreamerInfo` record parses | **Not reproducible here** — 0 occurrences; their witness is a file we lack, now fetched and **confirmed**: two such infos, and it means a *failed* computation (R6) |
| 5 | `TTime` appears with no streamer info | read the file | **Confirmed** — two `TTime` records, 70 bytes each, and ROOT would have described it (R6) |
| 6 | Counterexamples to `StreamerDriven` 10.5 | scanned every info in both corpora **and in `data/`** | **Confirmed, and worse than reported** — R2 |
| 7–10 | RooFit layouts | out of scope, not checked | **Needs a scope decision**, §5 |
| — | Duplicate `TIOFeatures` in four files, and the differing bit is not always `kIsCompiled` | read all three of ours | **Confirmed on our own files** — R3 |

Measured while checking, and both numbers belong in the documents this plan
touches: **36 `kBase` elements in 27 corpus files name a class with no info in
the same file**, and **no info in the 218 corpus files we can read carries `fCheckSum == 0`**.

## 2. Three defects — these should not wait for the rest

### R1 — `rootfile.py` mis-reads a version-1001 directory record

**The bug, exactly.** `read_directory` decides the offset width from
`version > 1000` and the presence of a UUID from `version > 1`:

```python
if version > 1000:              # large-file directory   <- correct
    ...
if version > 1:                 # a UUID is present      <- wrong for 1001
    uuid = buf[p + 2 : p + 18]
```

For a record at version **1001** — class version 1, wide layout — both tests pass,
so the reader invents a sixteen-byte UUID out of whatever follows the record.
Measured on `uproot-from-geant4.root`: the record is 138 bytes at offset 64, so it
ends at 202, and the UUID is read from **offset 204**. The same on
`uproot-issue-250.root`. The review's phrasing is the fix: the two axes are
independent, and the UUID test is `version % 1000 > 1`.

**Why nothing caught it.** No invariant compares a directory's UUID with anything;
the bytes are read and never used. That is its own small lesson, and the
invariant candidate that comes out of it is in R4.

**Scope**: a one-line fix in `tools/rootfile.py`, a test in `tools/test_*.py`
pinned to those two files, and the payload-size table in R4.

**Done 2026-09-21.** The measurement stands exactly as planned — `uuid_offset`
204 against a record ending at 202, and 158 against 156 in the smaller file — and
the fix is the `version % 1000` test, on **both** axes rather than one.

Three things came out of doing it that the plan did not have:

1. **The same line was wrong a second time.** `version > 1` also assumed a
   `TUUID` version word, which a **version 2** record does not have (§7's own
   table, `TDirectoryFile.cxx:1792-1797`). So the reader mis-read two of the five
   class versions, not one, and the second was already documented. Four tests fail
   against the old line: the 1001 case on the two corpus files, the 1001 case
   synthetically, and the version-2 framing.
2. **The legacy versions are witnessed after all.** `spec/01-container/Directory.md`
   §11 said no file covers version 1, 2 or 3. True of `data/`, which is version 5
   throughout — 99 records over 88 files — but false since `gen/cern/` arrived:
   `pippa.root` (ROOT 2.24/00) holds **24 version-1 records**, 23 of them exactly
   the 30 bytes §7 predicts; `mlpHiggs.root` (3.04/02) and `H1display.root`
   (3.05/07) hold a **version-3** record each at 48 bytes; five more files carry
   version 4. So every row of §7's payload table is now measured on a
   ROOT-written file **except version 2**, which only 3.03/01–3.03/07 wrote and
   which nothing in either corpus carries. §11 says so; R4 should build its
   per-(version, width) table on this rather than re-derive it.
3. **A fixture cannot cover this and neither can a corrupted one**, which is why
   the synthetic record in `tools/test_container.py` builds all six framings —
   1, 2, 3, 5, 1001, 1005 — with a sentinel behind the payload so the old
   behaviour is visible as *the next record's bytes returned as a UUID*. The
   corpus tests skip when `build/foreign/` and `build/cern/` are not fetched;
   they are the pin the plan asked for, and they are not the only check.

Left to R4, deliberately: nothing bounded the payload against (version, width),
which is why a mis-framed UUID had no detector. R4 is now done and `Directory.md`
invariant 15 is that bound — the UUID's bytes are still never compared with
anything, but a record whose framing does not match its claimed version is now
the wrong length and says so.

### R2 — `StreamerDriven.md` invariant 5 is false, and was never checked

The published text:

> 5. Every class named by a `TStreamerBase` element, and every class named in the
>    `fTypeName` of an element with an object-valued code, has a streamer info in
>    the same file — unless it is `TObject`, `TNamed` or `TString`, which are read
>    by hardcoded rules.

**It is contradicted by `data/classes/histogram.root`**, a file ROOT wrote and
this repository ships: `TH1F`'s info names `TArrayF` as a `kBase`, and there is no
`TArrayF` info in the file. Same for `TH1D` and `TArrayD`. It is contradicted by
`data/written/histogram.root`, which this project wrote and which passes all three
write gates. And it is contradicted by **36 elements in 27 files** across the two
corpora — mostly the `TArray*` bases of histograms, plus `TAtt3D` as a base of
`TH3` in the two files the review names.

**This is the same fact §8.11 established from the other side three days ago.**
`ElementLists.md` §10 is titled "Three classes a histogram file does not describe",
and those three classes are `TArrayF`, `TArray` and `TArrayD`. The invariant and
the element-list document have contradicted each other since, and nothing noticed
**because invariant 5 was never added to `check_invariants.py`** — the checker's
own docstring says it covers "invariants 3, 4 and 6".

That is a process failure as much as a content one, and it is worth saying so in
the fix: `CLAUDE.md` requires every `Invariants` entry to be checked and confirmed
against a corrupted fixture, and this entry was neither. **The audit that follows
from it is: which other invariants are published but unchecked?** That question is
R7 and it is the most valuable thing in this plan.

**The fix is not to delete the invariant** — something true is in there. A class
whose `Streamer` is hand-written records no info for itself, which is exactly
`TArray*`, and the honest restatement is a rule with a real exemption: *every class
named by a `TStreamerBase` element has an info in the same file unless its
`Streamer` is hand-written or forwarding*, which
[`HandWrittenStreamers.md`](spec/99-appendix/HandWrittenStreamers.md) and
[`ForwardingStreamers.md`](spec/99-appendix/ForwardingStreamers.md) already
enumerate from the submodule. That version is checkable, and the 36 cases are the
test of whether it is right.

**Done 2026-09-21.** The restatement is
[`StreamerDriven.md` §6.1](spec/02-serialization/StreamerDriven.md) with invariant
5 rewritten against it, and `check_invariants.undescribed_classes` is the check —
wired in, provoked by corrupting a fixture, and run over both corpora.

The base clause came out as planned. **The member clause did not, and that half of
the invariant was wrong in a way the review did not reach**: it required an info
for every class named by an object-valued member, and over the two corpora *778*
such members name a class the file does not describe. The dividing line turns out
to be sharp and worth having:

| Code | Requirement |
|---|---|
| `kBase`, `kObject` (61), `kAny` (62), and `kObjectp`/`kAnyp` (63, 68) | **must** be described — the bytes are written inline and the declared type is the only thing that says what they are |
| `kObjectP` (64), `kAnyP` (69) | **need not** be — the member may be null in every object in the file, and a non-null one names its class in the bytes |

So the second half is not a weakening, it is a different statement: a reader must
take a nullable pointer's class from the bytes and must never require its declared
type to be described. 289 pointer members in the corpora depend on it, `TTree`'s
`fTreeIndex` alone in 145 files, and the five declared types that account for them
are abstract classes with no info anywhere.

A third exemption appeared that neither list covers: an **STL container** used as
an inline member. `vector<double> twovectors[2]` reaches disk as code 82, and the
`StreamerInfo` record of the ROOT 6.24/06 file holding one has a single entry.
`Collections.md` describes it from its type name, so nothing is lost.

**Measured, over `data/` and both corpora — 306 files carrying an info:** 92
`kBase` elements in 65 files and 489 inline members name a class with no info, and
every one is exempt **except two**. Both are `TAtt3D` as a base of `TH3` in the two
g4tools files, and the diagnosis is the writer: `TAtt3D` is `ClassDef(TAtt3D,1)`,
on neither published list, and 48 ROOT-written corpus files carry its info —
including four of the six that describe a `TH3` at all.
`gen/foreign/IGNORE.toml` records that per file, per invariant, with the reason.

**And it corrected a claim made the same day.** `WritingObjects.md` §8.2, written
for W4 that morning, named `TAtt3D` as one of six bases legitimately absent from
files — resting on exactly those two g4tools files. Five of the six were right.
The same paragraph also said the closure was *not* checkable because the
exemption is a property of ROOT's source; it is, because that property is
**published**, and the checker reads the exempt set out of `spec/99-appendix/`
rather than out of the submodule. Both statements are now fixed, and its two
population counts were re-measured while there (89 files, 731 base elements with
an info).

**The process point the review made is the one that held.** The old invariant had
never been wired in, and everything above — the member clause, the pointer rule,
the STL exemption, the `TAtt3D` correction — surfaced within minutes of wiring it.
That is the argument for R7, which should now be expected to find more than one.

### R3 — `SchemaEvolution.md` §8.1 generalises from one file

The text says two duplicate infos differ in `fBits` "where the difference is
`kIsCompiled` (`BIT(16)`)". Measured on the three files we have:

| File | `fBits` | XOR | Bit |
|---|---|---|---|
| `uproot-issue121.root` | `0x3000000`, `0x3010000` | `0x10000` | `kIsCompiled` ✓ |
| `uproot-issue243.root` | `0x3030000`, `0x3010000` | `0x20000` | **`kBuildOldUsed`** |
| `uproot-issue-750.root` | `0x3030000`, `0x3010000` | `0x20000` | **`kBuildOldUsed`** |

So the claim is true of the one file the section quotes and false of the other two
in the same corpus, which were available when it was written. `kBuildOldUsed` is
`BIT(17)` (`root/core/meta/inc/TVirtualStreamerInfo.h:86`); in those two files
**both** entries carry `kIsCompiled`.

The correct statement is weaker and more useful: the two entries differ only in
`fBits`, the differing bits are in-memory status flags that reach disk because
`fBits` is written wholesale, and **which** flags differ is not fixed. A reader
must not key on any of them.

**Done 2026-09-21.** The measurement reproduced exactly — three files across
`data/` and both corpora carry a duplicate, all `ROOT::TIOFeatures` version 1 at
checksum `0x1aa12f10`, `kIsCompiled` in one and `kBuildOldUsed` in the other two,
where in those two **both** entries carry `kIsCompiled`. §8.1 is rewritten around
it, and one detail makes the point better than the correction does: `0x3000000`
is in *every* entry of all three, and it is `kIsOnHeap | kNotDeleted`
(`root/core/base/inc/TObject.h:90-91`) — the bits that say an object was on the
heap and had not been destructed. What reaches disk in `fBits` is the writing
session's memory state.

Two things were added rather than only corrected:

1. **§8.1 conflated two different duplicates.** It said a reader "may take either
   entry; they describe the same layout" — true of the `TIOFeatures` pair and
   false of `data/written/two-versions.root`, which this project wrote for W4 and
   which holds `Grown` at versions 1 and 2 with different checksums and different
   elements. The rewritten section separates them: same identity means either
   entry will do, different identity means the object's version word chooses. A
   reader that indexes by class alone and keeps the last entry decodes silently
   wrong.
2. **The "take either" half is now an invariant**, `SchemaEvolution.md` 9.6: two
   entries agreeing on `fClassVersion` **and** `fCheckSum` have identical element
   lists. It was prose asserted about three files; it is now checked over all
   226, and `fBits` is deliberately not part of the comparison, which is what the
   correction above is about. Provoked by forging `two-versions.root` so its
   second entry claims the first's identity: 9.6 fires, **and so does
   `StreamerDriven` 10.1**, because the version-1 object is then decoded through
   the two-element layout and over-runs its byte count. That is the cost the
   invariant exists to prevent, visible in the same corruption.

Count of published invariants: 256 → 257, and `WriterInvariants.md` gains the row
plus a note under §8 that a streamer info's `fBits` is deliberately unconstrained.

## 3. Four gaps — things true of the wild that we do not say

### R4 — A directory record's class version and its offset width are independent

`Directory.md` §5 tabulates payload sizes 30/46/48/60/60 for versions 1–5 and §7's
history reads as though the wide form arrived with class version 4. Both files
above carry **1001**: 42 bytes = `2 + 4 + 4 + 4 + 4 + 3×8`, no UUID, three 8-byte
offsets. The reading rules in §3 and §7 already handle it; what is missing is one
sentence that the two axes are orthogonal, and a payload size per *(version,
width)* rather than per version.

Both files are third-party — g4tools, `fVersion` 40000 with a 2018–2020 `fDatime`
and a zeroed header UUID — so the review suggests an `IGNORE.toml`-style note may
be the right home. **Disagree, and the reason matters**: our reader gets it wrong
(R1), so this is a fact a reader needs, not a quirk to suppress. It belongs in the
document, with the provenance stated.

**Done 2026-09-21.** `Directory.md` gains §3.1 for the orthogonality and §7.1 for
the payload length, and invariant 15 makes the length checkable. Three things
turned out better than "one sentence and a table":

1. **The source says *why* the axes are independent**, so it need not be asserted.
   The version word is a **sum**: `version = TDirectoryFile::Class_Version()`, then
   `version += 1000` (`TDirectoryFile.cxx:750`, `:759`). ROOT hides it by always
   writing the class version it was compiled with — every wide record ROOT has ever
   written is 1004 or 1005 — and g4tools' 1001 is what an *uncoupled* writer
   produces. Stated that way, §7's history needs no correction: the wide form did
   arrive with class version 4 **in ROOT**, and never did in the format.
2. **ROOT gets 1001 right, and our reader did not.** Both of ROOT's readers take
   the UUID from `version % 1000` (`TFile.cxx:808`, `:823`;
   `TDirectoryFile.cxx:1792-1796`). So R1 was not a case of copying a ROOT bug —
   the only ROOT defect near here is the version-2 one §7 already records, and
   this reader had *both*. Worth saying plainly in the document, which now does.
3. **The length depends on a third thing**, which the plan's arithmetic missed:
   the 12 reserved bytes are allocated on the **file header's** `fVersion`, not the
   record's (`TDirectoryFile.cxx:1725-1735`). That is why a version-3 record is 48
   bytes rather than 60, and it makes the table a function of three inputs. Every
   value that occurs in a real file is measured; the rest are arithmetic and
   labelled as such.

Invariant 15 holds on **all 471 directory records** of `data/` and both corpora.
Confirming it by corruption showed the two axes are guarded by two different
invariants, which is the useful half: `container/directories` with its version word
changed 5 → 1 reports exactly invariant 15, while 5 → 1005 reports **five `Record`
8.6 failures and no 9.15** — offsets read at the wrong width leave `fSeekDir`
pointing elsewhere, so the record stops being recognisable as a directory at all.
A width lie cannot hide; a class-version lie could, and now cannot.

### R5 — `fBEGIN` is whatever the header says

`FileHeader.md` §8 ties `fBEGIN = 64` to ROOT ≤ 3.04, which is true of ROOT and
false of files in the wild: both g4tools files pair `fBEGIN = 64` with
`fVersion = 40000`. §4 already says to take `fBEGIN` from the header, so this is a
note against §8, not a rule change. It pairs with
[File header §10](spec/01-container/FileHeader.md#10-invariants) invariant 11,
added 2026-09-21: a 64-byte `fBEGIN` leaves no room for the 75-byte large header,
so updating such a file past 2 GB would write over its own first record — which
makes these two g4tools files the live examples of that hazard rather than
curiosities.

**Done 2026-09-21**, as `FileHeader.md` §8.1, with §4's MUST strengthened to say
`fBEGIN` must not be derived from `fVersion` either, and invariant 11's evidence
sentence corrected: it said "four files, from ROOT 2.24/00 to 4.00", which reads
as four old files and is only true of two.

The four `fBEGIN = 64` files in `data/` and both corpora, measured:

| File | `fVersion` | Header UUID |
|---|---|---|
| `pippa.root` | 22400 | none — bytes 45-63 unwritten, as §8 predicts for ≤ 3.02 |
| `mlpHiggs.root` | 30402 | present, as §8 predicts for 3.03–3.04 |
| `uproot-from-geant4.root` | **40000** | 16 zero bytes |
| `uproot-issue-250.root` | **40000** | 16 zero bytes |

Two things came out of measuring rather than asserting:

1. **ROOT gives a reader no help at all here.** Its only check on the field is
   `fBEGIN < 0 || fBEGIN > fEND` (`TFile.cxx:760-766`) — never against 100, never
   against the length of the header it is about to write. So "ROOT opens it" is not
   evidence that `fBEGIN` is sane, which is worth saying in a document whose
   invariant 11 exists precisely because ROOT does not check it.
2. **Neither g4tools file carries a UUID anywhere.** Zeroes in the header, and
   their directory records are version 1001, which has no UUID field at all (R4).
   Harmless, and only because §6 already establishes that ROOT never reads the
   header's — but it is the third thing these two files do that the version-history
   table does not predict, after `fBEGIN` and the 1001.

Their `fDatimeC` values are 2018-10-03 and 2021-01-20, so the plan's "2018–2020"
was a guess at the range; the document gives the two dates.

**Their item 3, the attribution, is done in the same pass** and is no longer only
credited. `gen/foreign/IGNORE.toml` and `Buffer.md` §6.1 now say groot rather than
uproot, with the evidence separated from the claim: the branch names are Go type
spellings — `SliF64` is a *slice* of float64 — and nothing in the bytes names a
writer, so the review's report is corroborated, not proven. What *is* proven is
the negative: every basket key carries `fVersion` 4 where ROOT adds 1000
unconditionally, so it is not ROOT's. The entry also said "two departures" above
three bullets; fixed.

### R6 — `fCheckSum == 0`, and `TTime`

Two separate small things the specification does not mention.

**`fCheckSum == 0`**: their witness is `uproot-issue283.root`, which we do not
have, and **no info in the 218 corpus files we can read carries it**. So this needs the file before it
needs a sentence — §4. Their reading is that it means a custom streamer; the
statement `SchemaEvolution.md` §3 needs is whether a zero checksum is a legitimate
value or a writer's omission, and either answer changes what a reader should do
when §4 step 2 tries to use it as a lookup key.

**Done 2026-09-21**, and it was worth the file. `uproot-issue283.root` is fetched
and in the manifest (155 files now), and the answer is neither of the two the plan
offered: **a zero checksum is a computation that failed.**

`TClass::GetCheckSum` has exactly one path returning 0 — a base class whose meta
information is unavailable, where it prints an `Error`, sets `isvalid` to false and
returns 0 (`TClass.cxx:6704-6710`) — and `TStreamerInfo::Build` stores it anyway,
because it calls the one-argument overload and never sees `isvalid`
(`TStreamerInfo.cxx:447`). So the file records a failure the writing session was
told about and a reader cannot see. `SchemaEvolution.md` §3.1 says so, and says
what a reader does: treat the field as **absent**, never as a key.

The measurement that rules out the alternatives is the useful part. The two zeros
are `Sni3DataArray` and `I3Eval_t::ChannelContainer_t`, both with **no elements** —
and emptiness is not the cause, because **247 other infos across the corpora also
have no elements and every one carries the fold of its own class name**: `TString`
`0x00017419`, `TAtt3D` `0x0000757a`, `TQObject` `0x00042e9c` and five more, all
reproduced from the algorithm. The two zeros should have been `0x04442992` and
`0x4c1ebbfe`. It is also not a custom-streamer marker, the review's reading: those
247 include hand-written-`Streamer` classes, with proper checksums.

**`TTime`: the writer is at fault, now checked rather than suspected.** ROOT
6.40.04 writing two `TTime` objects emits the info (version 2, checksum
`0x839dbf90`, one member `fMilliSec`), and so does adding a `TTime` to an existing
histogram file opened for **update** — which is the obvious way to reach this state
by accident, and which W3's StreamerInfo early-out made worth testing. That second
test reproduces `uproot-issue-861.root`'s info list exactly: the same fourteen
entries, **plus `TTime`**. The object bytes agree too — both writers frame it
`40 00 00 0a | 00 02 | Long64_t`, `fObjlen` 14 — so nothing about the object is
unusual and only its description is missing. `StreamerDriven.md` §6.2 has it, with
the CoMPASS provenance (the file's own name is a Windows path) and its equally
undescribed `CalibrationCoefficient`.

**And the file caught a reader bug, which is the third finding.** Its `I3Eval_t`
has a `set<long>` whose `fSTLtype` is **5**, and `rootfile.py` read 5 as
`kSTLmultimap`, took the container to be paired, and crashed. `TStreamerSTL`
numbered `kSTLset = 5` and `kSTLmultimap = 6` — the reverse of every other use of
the enum — until `d1ffea01e01` standardised the declaration in **5.34/13**;
`TStreamerSTL::Streamer` gained the read-side repair only in **6.00/00**
(`cf539483218`), and it resolves the value from `fTypeName`. **The element version
is 3 on both sides of the change**, so nothing in the element says which convention
wrote it. Measured on one member across four files — `RooAbsArg._boolAttrib`, a
`set<string>` — it is 5 in `stressRooFit_v522_ref.root` and `v534_ref.root` and 6
in `uproot-issue49.root` and `uproot-issue-350.root`.

`Collections.md` §1 **already stated the repair**, with the citation. So this is not
a specification gap: it is the third time in this review that the documents were
right and something else was not — R1 was the reader against `Directory.md` §7, R2
was the checker against an invariant nobody wired up, and this is the reader again.
Invariant 10 now checks it, on the value a reader ends up with, so the omission
cannot come back: 1368 `TStreamerSTL` elements across `data/` and both corpora, and
three of them need the repair to pass. `stl_kind` also learnt `ROOT::VecOps::RVec`,
which it had been missing.

**`TTime`**: confirmed — `uproot-issue-861.root` holds two top-level `TTime`
records of 70 bytes each, and no `TTime` info. `TTime` has `ClassDef(TTime,2)`
and is not in `HandWrittenStreamers.md` or `ForwardingStreamers.md`, so the
specification says a reader should find an info and there is none. The honest
answer is probably that the writer is at fault — the file is from a CAEN DAQ tool,
opens with a Windows path as its name, and carries a `CalibrationCoefficient`
class that is equally undescribed. **But "the writer is at fault" is a finding
only if we check it**, and the check is whether ROOT itself, writing a `TTime` to
a file, emits an info for it. That is ten minutes with the ROOT on `PATH`, and the
result goes either in `Bootstrap.md` §5 or in `StreamerDriven.md` §6.

### R7 — The audit R2 implies: which invariants are published but unchecked?

`CLAUDE.md` states the rule — every `Invariants` entry goes into
`check_invariants.py` and is confirmed by corrupting a fixture — and
`WriterInvariants.md` counts **248 entries across 32 documents**. R2 shows at
least one that was never wired up, and it was wrong.

So: enumerate every numbered entry under every `## Invariants` heading, match it
against the `self.bad("<Doc> <n>.<m>")` labels in `check_invariants.py`, and print
the entries with no check. That is a tool — call it `tools/check_coverage.py`, or
fold it into the existing checker as a `--audit` mode — and it makes the rule
enforceable rather than aspirational. Every unchecked entry then gets one of three
outcomes: a check, an explicit "not checkable, because…" note in the document, or
deletion.

**This is the item most likely to find more of what R2 was.**

**Done 2026-09-21, and it was right about that.** `tools/check_coverage.py` reads
every numbered entry under every `Invariants` heading, matches it against the
labels the tools report, and requires the remainder to be accounted for in
`gen/invariants.toml`. It runs in CI between `check_invariants.py` and
`check_write.py`.

**The count: 259 published entries across 32 documents, 183 with a check.** So 76
were unmatched when the tool first ran — and the important half of that number is
not 76, it is what wiring some of them up did.

**Two more published invariants were wrong**, both in `ElementTypes.md`, both
found the moment a check existed:

- **invariant 4 was false.** It said `fArrayLength` is "positive for any code in
  `[20, 59]`", and 211 elements in `data/` alone say otherwise: it is positive for
  a `kOffsetL` code (20–39), the fixed extent, and **0 for a `kOffsetP` code
  (40–59)**, whose length is its counter's value at read time. Measured over `data/`
  and both corpora: 651 `kOffsetL` all positive, **2229 `kOffsetP` all zero**. The
  restatement also had to name the one scalar-looking exception — an object-pointer
  code spells a fixed array with `fArrayLength` and no `kOffsetL` — which this
  project's own `element-types` fixture was built to demonstrate and whose element
  title says so;
- **invariant 3 was incomplete and over-general at once.** It allowed `fType` 500
  or 501 on "an element whose class carries a custom streamer" and did not mention
  `TStreamerLoop`, which is the only class that ever carries 501. Measured: 500 is
  a `TStreamerSTL` (1137) or a `TStreamerSTLstring` (213), 501 is a `TStreamerLoop`
  (13), the legacy 300 is a `TStreamerSTL` (18), and no other class carries any of
  them. The escape clause described nothing.

**And a document claimed a check it did not have.** `ReadingEntries.md` §8 said
"all six are checked over every fixture and both corpora" while two of the six had
no check of their own — 2 is checked under `Splitting` 8.2 and 6 only through
invariant 5's consumption. Both are true, but the sentence could not be verified by
anything, and that is the class of statement this tool exists to stop.

Eight entries gained a check: `ElementTypes` 11.3, 11.4, 11.5 and 11.7,
`FileHeader` 10.3 (ROOT's own open-time test, which we had never made),
`StreamerInfo` 13.2 with `SchemaEvolution` 9.2 and 9.3 — the outer list holds infos
and at most one `listOfRules` — and `Compression` 9.7, that a raw payload never
looks like a compression block.

The remaining 68 are accounted for, each with the check that covers it:

| `by` | Count | What it means |
|---|---|---|
| `write-gate` | 44 | a `spec/06-writing/` entry, checked by `check_write.py` on our own output — gate 2 runs the reading invariants over it, gate 1 compares bytes with ROOT's, or `rootwrite.py` raises |
| `alias` | 10 | the same claim under another document's label, named |
| `structural` | 10 | enforced by the reader: a wrong value fails the parse, reported under the label given |
| `not-checkable` | 2 | `LargeFiles` 8.6 needs a file past 2 GB; `WritingTrees` 9.14 cannot be violated by construction |
| `unchecked` | 2 | the honest worklist: `Auxiliary` 8.4 and half of `WritingHistograms` 10.5 |

Every `alias` and `structural` claim was verified by finding the check, not
asserted. `tools/test_coverage.py` drives the three ways the tool must fail: a new
unchecked entry, a reason for something checked after all, and a label a tool
reports that no document publishes.

## 4. The corpus question

Two findings rest on files we do not have: `uproot-issue283.root` (R6's
`fCheckSum == 0`) and `uproot-issue243-new.root` (a fourth duplicate-`TIOFeatures`
witness). `gen/foreign/` takes 154 of scikit-hep-testdata's 235 files.

`CLAUDE.md`'s rule for adding one is that it must cover something no fixture and no
listed file does, with the reason in the README. **`uproot-issue283.root` qualifies
on R6 alone** — it is the only known witness to a zero checksum, and without it
that item cannot be written at all. `uproot-issue243-new.root` does not: three
files already witness the duplicate, and R3's correction is measurable on the two
we have.

**`uproot-issue283.root` is added** (2026-09-21), and it earned its place twice
over: the zero checksum, and a reader bug nothing else in either corpus exposes
(R6). The reason is recorded in `gen/foreign/MANIFEST.sha256`'s header, since that
corpus has no README. 155 files now.

### 4.1 A discrepancy this turned up ✅ resolved 2026-09-21

**`build/cern/` holds 72 files and `gen/cern/MANIFEST.sha256` lists 26** — 24 core
plus 2 physics. The other **46 are the `TGeoManager` demo sweep** from root.cern
that `CLAUDE.md` says is deliberately excluded, "~40 near-identical demos and only
one is included". They were fetched by hand in an earlier session, not by
`tools/fetch_cern.py`, and nothing records them.

That matters because **they are already load-bearing evidence**. Four of the five
rows of [`StreamerInfo.md` §9.2](spec/02-serialization/StreamerInfo.md)'s
`fBaseVersion` table are `aleph`, `atlas`, `cms` and `hades.root`, every one
outside the manifest — only `uproot-mc10events.root` was listed — and so are most
of the 48 `TAtt3D` witnesses R2 relied on. And every "over both
corpora" file count published today — 471 directory records, 307 files carrying
infos, 1368 `TStreamerSTL` elements — was measured over 155 + 72, not 155 + 26.

What is **not** affected: failures and entry coverage. The 181-file reproducible
corpus gives `28058 of 28125` branch-baskets and **0 failures**, against
`27969 of 28036` and 0 over 227 files — the geometry files carry no trees, so they
contribute file counts and nothing else.

Two honest resolutions, and the choice is a corpus-scope decision like §5's:

| | Add the 46 to the manifest, as a `geometry` tier | Drop them |
|---|---|---|
| For | They are ROOT-written and root.cern-published, so a failure is evidence; they already are evidence; the published numbers become reproducible | Keeps the corpus small, and `CLAUDE.md`'s "one demo is enough" rule intact |
| Against | Amends a stated rule, and 46 near-identical geometry files earn little per file | §9.2's table and R2's `TAtt3D` control would have to be re-derived or dropped, and today's file counts re-measured |

**Recommendation: add them as a tier**, because the alternative is to un-publish
evidence that is correct. Either way the counts should then say which corpus they
were measured over, which none of them currently do.

**Done 2026-09-21**, that way. `gen/cern/MANIFEST.sha256` gains a `geometry` tier
of 46 files, 19 MB, in seven ROOT releases from 5.17/07 to 6.08/06, and
`fetch_cern.py --tier geometry`
fetches it. Every row was verified twice before it was written: the digest against
the local file, and the size against a `HEAD` request to
`https://root.cern/files/<name>`, so all 46 are fetchable at the path the manifest
claims. `--tier all` verifies 72 of 72.

The counts that rested on the unlisted files are re-measured rather than adjusted:
**227 files** in both corpora, 219 carrying a `StreamerInfo` record, and
`ForwardingStreamers.md`'s table moves from 168/33/1 of 177 to **211/79/1 of 219**.
That `THashList` row is its own confirmation — it names `TGeoManager::fHashPNE` as
one of two sources, and it rose by exactly 46.

**How far the drift had spread:** `PLAN.md`'s own corpora table already said
`gen/cern/` was 72 files. So the documentation had been describing the corpus the
measurements used for some time, and only the manifest — the one artefact a third
party would fetch from — said 26.

**The lesson is not "add the files", it is that this had already happened once.**
`gen/cern/README.md`'s standing result records `aod_flushed.root` and
`gallery.root` being cited and in no manifest on 2026-09-18, fixed by hand; this is
the same failure three days later, with four files and a whole invariant table
behind it. So it is now a check rather than a habit:
**`tools/check_citations.py` fails on any `.root` the specification names that is
neither a fixture in `data/` nor listed in a corpus manifest.** Seven names are
allowlisted in `NOT_CORPUS`, each with its reason — a placeholder, two
illustrations, three files an experiment wrote and discarded, and the Windows path
`uproot-issue-861.root` carries in its own header. Provoked by unlisting
`aleph.root`: the check names `StreamerInfo.md` as the document that would have
become unreproducible.

That check is the durable half of this item. The tier is just the backlog it found.

Worth asking in the reply whether there is a reason `gen/foreign/` should track the
whole of scikit-hep-testdata rather than a selection. The argument for is that
their review found two things in the 81 files we skip; the argument against is
`PLAN.md` §3.4's, that a corpus earns its place file by file.

## 5. RooFit — a scope decision, not a task

Items 7–10 are RooFit: `RooLinkedList` v3's real layout, `RooRealVar` behaving as
an `extending` class, an extra frame around `RooAbsCategory`'s members, and a
doubled collection frame in `RooVectorDataStore`. rootfilespec's maintainer would
rather these were specified **here** than reverse-engineered downstream, and says
so explicitly.

`PLAN.md` decision 8 puts RooFit out of scope — one of four groups of "frameworks
inside ROOT that define their own persistent classes", 15 classes in
`streamers.toml`, each with its reason. The corpora contain them: 197 blocked
records in two `stressRooFit_*` files, plus the RooFit graphs in
`uproot-issue-350.root`.

**The decision is genuinely open and it is the user's, not mine.** What this plan
can do is state the trade honestly:

| | For specifying RooFit | Against |
|---|---|---|
| Demand | A second independent reader is asking, which is the strongest signal this project has had about what to write next | One asker |
| Cost | Four classes, and the review has already done the reconnaissance for three of them | RooFit is large; four classes is where it starts, not where it ends |
| Discipline | Each is checkable the usual way — a fixture, a byte table, an invariant | Needs RooFit in the generator environment, which is a new build dependency for `gen/` |
| Precedent | `Formula.md` and `Matrix.md` are the same shape of work and are done | Decision 8's boundary is what keeps the project finite |

**A middle option exists and is probably right**: specify the *three framing
observations* — the extra frame after a `RooRealVar`, the extra frame around
`RooAbsCategory`'s members, the doubled collection frame — **as container-layer
facts rather than as RooFit class layouts**. Item 10 in particular is not really
about RooFit: "a collection preceded by a frame whose version word is 1, then the
ordinary collection frame" is a statement about `Collections.md` §2, and if it is
real it is a gap in a document that is in scope. Same for item 8: `Buffer.md` §2.4
and `HandWrittenStreamers.md` §3 currently name exactly three `extending` classes,
and if `RooRealVar` is a fourth then either the list or the definition is wrong —
which is an `inventory.py` question, not a RooFit question.

That reframing costs little, keeps decision 8 intact, and answers most of what they
actually need. It is R8, and it is the only RooFit item this plan proposes.

## 6. Corroborations — what to fold in

No action is required on the six, but four carry citations worth having, since a
second implementation confirming a byte pattern is exactly the evidence
`spec/00-conventions.md` §7 says a citation cannot give:

- `Buffer.md` §2.3's nineteen records — they count the same nineteen across 235
  files, which turns our "19 records" into a measurement two readers agree on.
  **Checking that before quoting it back found our own sentence wrong** (fixed
  2026-09-21): it said all 19 "begin `00 01 00 03 40 00`", and only the 14 `TH1D`
  do. The 5 `TH2D` begin `00 03 00 03 00 03` — three bare version words, no byte
  count among them — so the *count* and the *shape* were right and the bytes were
  one instance quoted as if it were all of them. The sharper fact, now published:
  the depth at which framing resumes follows the class chain, so a reader matching
  one prefix has hard-coded a class rather than implemented the rule. Sixth
  correction of the review, and the only one not found by a check;
- `uproot-issue-222.root` as a field witness for `Buffer.md` §4's version-0,
  byte-count-2, no-checksum case;
- `0x00D7BED2` as a wild member-wise `pair<double,double>` checksum for
  `Collections.md` §8.2;
- `uproot-issue-407.root` confirming `Record.md` §3.7's bare four-byte `TDatime`
  member, on a class we did not write.

Each is one line in the document's reference-files table or a footnote beside the
claim. Cheap, and it makes the next review cheaper.

## 7. What to reply, and when

The issue deserves a reply before the work is finished, not after, and it should
say three things: **which items were confirmed and how** — including that item 1
found a bug in our reader and item 6 found a false invariant plus an unchecked-
invariant audit; **which needs a file we do not have**, with the question about
scikit-hep-testdata coverage; and **what happens to RooFit**, which is the one
thing they asked for that this plan does not simply grant.

Their item 3 (the `uproot-issue413.root` attribution) is a correction to
`IGNORE.toml`'s reason text and costs nothing — worth doing before replying, so the
reply can say it is done.

Per the repository's convention the reply opens with the AI-content marker.

## 8. Order, and definition of done

1. ~~**R1** — the reader bug, plus a test.~~ **Done**: the fix is on both axes,
   the version-2 framing was wrong on the same line, and §7's payload table is
   now measured on ROOT-written files for every version but 2 (§2).
2. ~~**R3** — the `fBits` correction, measurable on files in hand.~~ **Done**:
   the correction stands as measured, §8.1 was also conflating two kinds of
   duplicate, and the half of it that is true is now invariant 9.6 (§2).
3. ~~**R2** — restate invariant 5, wire it into `check_invariants.py`, confirm it
   catches a corruption, and check it over both corpora.~~ **Done**: the member
   half of the invariant was wrong too, the pointer/inline split is the real rule,
   and it caught a claim W4 had published the same morning in
   `WritingObjects.md` §8.2 (§2).
4. ~~**R7** — the unchecked-invariant audit, which R2 is the argument for. Expect
   it to find more.~~ **Done**: `tools/check_coverage.py`, in CI. It found two more
   false invariants and a document claiming a check it did not have (§3).
5. ~~**R4**, **R5** — the two directory/header notes, and the attribution fix.~~
   **Done**: `Directory.md` §3.1, §7.1 and invariant 15; `FileHeader.md` §8.1 with
   §4 and invariant 11 corrected; and the groot attribution, with the evidence
   separated from the claim (§3).
6. **Reply to the issue** (§7), including the corpus question.
7. ~~**R6** — needs `uproot-issue283.root` for half of it; the `TTime` half needs a
   ten-minute ROOT experiment and nothing else.~~ **Done**, and it cost more than
   ten minutes because the file it needed also caught a reader bug: a zero
   checksum is a failed computation, `TTime`'s absence is the writer's, and
   `set`/`multimap` were swapped in `fSTLtype` until 5.34/13 (§3).
8. **R8** — the three framing observations, as container-layer questions.

Done when: every item above has an outcome recorded in this file, the issue has a
reply, and `PLAN.md` §8.1 criterion 1 is true again — which it is not today, and
which is the reason the order starts where it does.
