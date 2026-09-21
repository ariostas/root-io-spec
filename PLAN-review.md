# PLAN-review — the rootfilespec review, issue #1

**Status: ordered, not started.** Written 2026-09-21. Every item below was
re-checked against the corpora and against our own reference files *before* being
planned, and the verification is recorded per item, because the point of a review
is what it turns out to be right about.

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
`gen/foreign/` is 154 of them. Two of their findings rest on files we do not have,
and that is a corpus decision (§4) rather than a doubt about the finding.

## 1. What was verified, before planning

| # | Their claim | Checked how | Verdict |
|---|---|---|---|
| 1 | Directory records of version **1001** exist | read both files | **Confirmed** — and it found a bug in our reader, R1 |
| 2 | `fBEGIN = 64` with `fVersion = 40000` | read both headers | **Confirmed** |
| 3 | `uproot-issue413.root` is groot's fixture, not uproot's | not independently checked | **Plausible**, and cheap to credit |
| 4 | `fCheckSum == 0` occurs in a `TStreamerInfo` | scanned every info in the 218 corpus files whose `StreamerInfo` record parses | **Not reproducible here** — 0 occurrences; their witness is a file we lack |
| 5 | `TTime` appears with no streamer info | read the file | **Confirmed** — two `TTime` records, 70 bytes each |
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

### R6 — `fCheckSum == 0`, and `TTime`

Two separate small things the specification does not mention.

**`fCheckSum == 0`**: their witness is `uproot-issue283.root`, which we do not
have, and **no info in the 218 corpus files we can read carries it**. So this needs the file before it
needs a sentence — §4. Their reading is that it means a custom streamer; the
statement `SchemaEvolution.md` §3 needs is whether a zero checksum is a legitimate
value or a writer's omission, and either answer changes what a reader should do
when §4 step 2 tries to use it as a lookup key.

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

- `Buffer.md` §2.3's nineteen `00 01 00 03 40 00 …` records — they count the same
  nineteen across 235 files, which turns our "19 records" into a measurement two
  readers agree on;
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

1. **R1** — the reader bug, plus a test. Half an hour, and it is wrong right now.
2. **R3** — the `fBits` correction, measurable on files in hand.
3. **R2** — restate invariant 5, wire it into `check_invariants.py`, confirm it
   catches a corruption, and check it over both corpora.
4. **R7** — the unchecked-invariant audit, which R2 is the argument for. Expect it
   to find more.
5. **R4**, **R5** — the two directory/header notes, and the attribution fix.
6. **Reply to the issue** (§7), including the corpus question.
7. **R6** — needs `uproot-issue283.root` for half of it; the `TTime` half needs a
   ten-minute ROOT experiment and nothing else.
8. **R8** — the three framing observations, as container-layer questions.

Done when: every item above has an outcome recorded in this file, the issue has a
reply, and `PLAN.md` §8.1 criterion 1 is true again — which it is not today, and
which is the reason the order starts where it does.
