# AGENTS.md

This file provides guidance to coding agents working in this repository.

## What this repository is

A specification of the ROOT on-disk binary formats, written so a third party can
implement a reader without reading ROOT's C++ source. ROOT ships only one real
format spec (RNTuple). Its `TFile`/`TTree` documentation in `root/io/doc/TFile/`
describes **release 3.02.06** and is substantially wrong for current ROOT.

`PLAN.md` holds the structure, scope decisions and phasing. The sections most
worth knowing:

- **§8.12** is the second half of the write side: free-space reuse, key ordering,
  updating a file and schema evolution, all landed 2026-09-21. It records the six
  findings that came out of that work.
- **§8.13** is the first outside review, GitHub issue #1, answered in full over
  2026-09-21/22. Read it before adding a claim: eight published claims turned out
  false or incomplete, six of them among the claims nothing was checking.
- **§8.14** is the corpus survey of 2026-09-22/23. It lists ten more wrong or
  under-scoped claims, how each was found, and the confirmed dead ends, so they
  are not re-investigated.
- **§8.15** records six "ROOT 4" behaviours that were really g4tools. A file's
  header names a ROOT release, not its writer.
- **§8.16** is a consistency review of every document. It also resolves the
  failures on ROOT-written pre-5 files in `root/roottest/`, all of them legacy
  layouts or reader gaps, and lists what a sweep of all of roottest still fails.
- **§8.17** is the second consistency review, 2026-09-24. Nine claims produced
  wrong bytes and about fifty procedure steps disagreed with the text around
  them, with every check passing. Read its list of checks before adding one, and
  its lesson before writing a procedure: a *Reading* step is the most-copied and
  least-checked text here.

The sub-plan that drove the survey, `PLAN-corpus.md`, is deleted, but code and
text still cite its item numbers (C1–C19). Its lasting rule: keep a claim
reproduced here separate from one a survey merely reported, because five of the
survey's claims did not survive re-measurement.

No sub-plan is open. The second review's, `PLAN-review.md`, is deleted too, and
code, tests and fixtures cite its items as V1–V44; `PLAN.md` §8.17 is what it
left, and §9.12 what it set aside. A sub-plan is deleted once discharged, with
anything durable moved into `PLAN.md` or `spec/` first.

`spec/00-conventions.md` holds the conventions every specification document depends
on. Read it before writing spec text; this file covers how to work here, not
what to write.

## Commands

The full check suite, in the order CI runs it:

```sh
tools/generate.py --check      # byte assertions in every case.toml (no ROOT needed)
tools/check_invariants.py      # the Invariants sections of spec/01-container/
tools/check_coverage.py --check # every published invariant is checked, or has a
                              #   reason in gen/invariants.toml
tools/check_write.py           # gates 1 and 2 of spec/06-writing/ (--root adds gate 3)
tools/check_pin.py             # zensical.toml cites the pinned submodule commit
tools/check_citations.py       # every cited file and line exists, and the front
                              #   pages quote the right total (needs submodule)
tools/check_figures.py         # every other count the pages quote, per gen/figures.toml
tools/check_versions.py        # every class-version table matches ClassDef (needs submodule)
tools/sync_rntuple.py --check  # spec/05-rntuple/ matches upstream (needs submodule)
tools/inventory.py --check     # the hand-written Streamer list matches the submodule
tools/element_lists.py --check # the published element lists match the fixtures
PYTHONPATH=. zensical build --clean --strict          # site; fails on broken links
PYTHONPATH=tools python -m unittest discover -s tools -p "test_*.py"
```

Chain them with `&&`, not `set -e` (see the gotchas below for why).

CI runs the unit tests in `ci.yml`'s `tests` job, with the submodule, and fails
if any test skipped because `root/` or `.git` was missing. A test may still skip
for a corpus file under `build/`, which CI never fetches; run those locally.

Regenerating fixtures needs ROOT on PATH, matching the pinned submodule:

```sh
tools/generate.py                                      # all cases
tools/generate.py gen/cases/container/file-minimal     # one case
tools/generate.py --accept <case-dir>                  # after editing a case on purpose
```

A digest differing from `data/MANIFEST.sha256` is an error: either the format
changed or a fixture stopped being reproducible. So is a case with no line in the
manifest, and, when every case runs, a line no case produces. `--accept`
re-records the digests, and is the right move only when you changed or added the
case yourself.

`tools/coverage_probe.py <file.root>` is not a CI check. It measures how much of a
file the specification currently covers, and prints what blocked each record;
`--summary` gives one line per file. Run it on files the fixtures were not
designed around to get a ranked list of what is still missing, instead of
guessing from `PLAN.md`:

```sh
tools/fetch_foreign.py                      # 180 third-party files, 24 MB, to build/foreign/
tools/coverage_probe.py --summary build/foreign/*.root
```

Those files are not reference files and are not committed;
`gen/foreign/MANIFEST.sha256` records what was used. `PLAN.md` §9.8 has the
standing result.

The invariant checks run over the same corpus. That is where format errors have
actually been found: fourteen so far, plus the legacy `CS` codec.

```sh
uv run --no-project --with-requirements requirements-codecs.txt \
  python3 tools/check_invariants.py --ignore gen/foreign/IGNORE.toml build/foreign/*.root
```

Install the codecs for corpus runs, as above; CI installs them too. Without
`lz4`, eight LZ4-compressed files lose 2158 branch-baskets from both sides of the
`ENTRIES` ratio, so the ratio hides them.
That is how the `uproot-issue213.root` failure of `PLAN.md` §8.16 went unseen.

Run one checker process at a time. A single one peaks at about 1.8 GB, on
`io/evolution/Event_2.root` in roottest, and several at once have exhausted a
32 GB machine. Until 2026-09-23 `TreeReader` kept a decoder per basket, each
holding a copy of the file up to its basket, so memory grew with baskets times
file size: `sm.root` (15 MB) passed 2.9 GB and kept growing.

The provenance of these files is mixed. The source is uproot's regression corpus,
which includes files uproot wrote, so a failure there is a lead, not evidence.
Diagnose it against the pinned source and resolve it to one of four causes: a
spec error, a missing format fact, a reader gap, or a file at fault. Only the last
goes in `gen/foreign/IGNORE.toml`, per file and per invariant, with a reason and
with the suppressed count printed. **Never weaken an invariant because a file
disagrees with it.** ROOT's source is the authority, and "does ROOT itself read
this file" is a useful objective check along the way.

### The second corpus: files ROOT wrote

`gen/cern/` is the same idea without the provenance problem. Everything in it was
written by ROOT and published by the ROOT team at <https://root.cern/files/>, so a
failure there is evidence rather than a lead. It also reaches from ROOT 2.24/00 to
6.35/01, where `gen/foreign/` starts at 4.00.

```sh
tools/fetch_cern.py                         # core tier: 24 files, 5.5 MB
tools/fetch_cern.py --tier physics          # 2 production trees, 27 MB more
tools/fetch_cern.py --tier geometry         # the TGeoManager sweep, 46 files, 19 MB
tools/fetch_cern.py --tier all              # all three, 72 files
tools/fetch_cern.py --headers               # the 11 multi-GB files, ~25 KB of traffic
tools/coverage_probe.py --summary build/cern/*.root
tools/check_invariants.py build/cern/*.root
```

`gen/cern/README.md` says why each file is listed and what gaps it exposes.

The 46 `TGeoManager` demos were once excluded for being near-identical.
Since 2026-09-21 they are the `geometry` tier: four of them turned out to be
witnesses in `StreamerInfo.md` §9.2's `fBaseVersion` table (four of its five
files), and nothing had recorded that the corpus used for measurements was bigger
than the one the manifest defined (`PLAN.md` §8.13). The rule now is that a file
the specification cites is in the corpus whether the manifest lists it or not,
and it is checked: `check_citations.py` fails on a cited `.root` that no fixture
and no manifest accounts for.

`--headers` reads large files by HTTP range request. root.cern serves
`Accept-Ranges: bytes`, so the header, free-segment record, top directory record
and key list of a 5 GB file cost a few hundred bytes each. `gen/cern/LARGE.toml`
records the measured facts for eleven files from 1.3 GB to 15.9 GB, three of them
from CERN Open Data by an absolute `url`. **This is the only thing that exercises
the large-file layout at all**; no fixture does.
`.github/workflows/large-files.yml` runs it weekly, on demand, and on a pull
request that touches `LARGE.toml` or `fetch_cern.py`. It has already confirmed the
interleaved 10-byte/18-byte `TFree` entries of `FreeSegments.md` §2.1 on
`volume.root` (51 entries, 32 large). Re-running `--headers` after a
`rootfile.py` change is a cheap regression check on the container layer.

`root/roottest/` needs no fetch. ROOT's own test suite ships inside the pinned
submodule: 273 ROOT-written files from 2.23/12 to 6.41/01. The ones the
specification cites are listed in a table in `gen/cern/README.md` that
`check_citations.py` reads. Run the tools on a listed path directly, not on the
whole directory: `root/tree/basket/corrupted.root` is damaged on purpose.

To date a class version to a release, read the header at the release tag; the
submodule's history reaches back to ROOT 1:
`git -C root show v3-03-07:base/inc/TDirectory.h`. Three published boundaries
were wrong until this was done (`PLAN-corpus.md` C9, C11).

**Adding a file to either corpus.** It must cover something no fixture and no
listed file does, and the reason goes in the README. It is added as a manifest
line, never as a committed file. No third-party file is committed, above all
none from roottest or rntuple-validation, which are LGPL-2.1 (`LICENSE`,
"Third-party corpora are never committed"). `tools/test_provenance.py` fails on a
tracked `.root` that no case generates and on any tracked file identical to one
in `root/roottest/`. When a corpus file teaches something worth a fixture, write
a generator that reproduces it.

**Entry checks over the corpora.** Two checks decode entries:

- `entry_spans`, for a plain `TBranch`, which is leaf-driven;
- `rootfile.TreeReader`, for a `TBranchElement`. This is `ReadingEntries.md`
  invariant 5: the bytes an entry occupies equal the bytes its decoding consumes.

The entry check samples large baskets. `TLeaf.md` 10.7 costs one `entry_spans`
call per entry per branch, so a 42 000-entry tree with 32 branches needs millions
of them. Above 256 entries in a basket, `check_invariants.py` checks the first and
last 32 and a stride through the middle, and prints `SAMPLED n basket(s)`, a
count of distinct baskets.
`--all-entries` forces the exhaustive check. Both modes give 0 failures over the
fixtures and `gen/foreign/`, which justifies the default.

When a check cannot run, it prints `SKIPPED n branch-basket(s)` for each reason,
and the run ends with an `ENTRIES` line. Every branch-basket that holds entries
is in it exactly once: checked, failed, or skipped with a reason. A failure does
not take a basket out of the denominator, and a skip or failure in one basket
does not end its branch. Over the two corpora, with `lz4` installed, that is
**48278 of 48501, 99.5%**, with 0 failed. Of the 223 skips, 153 are things no
reader could decode from the file, of two kinds:

- a collection whose value class has no streamer info in the file.
  `Collections.md` §9 says nobody can read those, ROOT included;
- a class whose `Streamer` is hand-written, which no streamer info describes. Two
  of these are identified from the bytes rather than from a list:
  `nEXO::SmartRef` has no byte count, and neither of the two readings
  `StreamerDriven.md` §7.1 allows ends where its entry does.

The other 70 can be read, just not by this checker from this file: 65 baskets of
`alice_ESDs.root`'s `ESDfriend` branches, whose `fFileName` puts them in
`AliESDfriends.root`, which no corpus holds; and 5 `TBranchObject` baskets,
whose `TLeafObject` has no width, so the leaf-driven check cannot walk them. The
second is a reader gap.

Read a `0 failure(s)` line together with the `ENTRIES` line: it means zero
failures among the things checked, and that is the number to quote. Two past
mistakes show why:

- For one day there was a third kind of skip, and the figure was 97.7%: 975
  branch-baskets of an ATLAS class that is a collection whose value class the
  reader could not find. The value class was in the element's title
  (`Collections.md` §11.2). The survey that raised it had said "named only by
  checksum"; reading `TStreamerInfo::Build` showed otherwise.
- The `SmartRef` skips used to be passes. The reader read every object with no
  byte count version first, which by coincidence lands exactly on each 20-byte
  `SmartRef`, but fails on `skim.root`, which ROOT reads correctly. A pass means
  only as much as the reading behind it.
- Until 2026-09-24 the ratio lost baskets in four ways. A branch's decode
  stopped at its first skip or failure. A failed basket, or one whose codec was
  missing, left the denominator. A `TBranchObject` never entered it. And a slot
  holding both an embedded basket and a record was counted twice. All four walks
  of a branch's baskets now go through `Checker.branch_baskets`, and the figure
  went from 99.8% of 48399 to 99.5% of 48501.

The figure was 99.7% until 2026-09-17, then 96.4%, and both changes were
corrections. Neither entry check had looked at an embedded basket, one kept
inside the `TTree` record rather than written as its own key (`TBranch.md` §5).
The leaf-driven check iterated the baskets below `fWriteBasket`, and an embedded
basket sits at it, so 1266 branch-baskets were in neither the numerator nor the
denominator: the old 99.7% had the wrong denominator. Making them visible dropped
the ratio to 96.4%; reading them raised it to 99.8% of a bigger number. A ratio
that cannot see what it skipped is less useful than a lower one that can.

Similarly, two causes used to share the message `counter basket unavailable`: a
basket whose codec is missing, and a counter basket embedded in the tree record.
They now have separate messages, because a shared message hides a category.

Reading the embedded baskets found a ROOT bug. `fBranchCount` is set from a
counter name looked up over the whole tree
(`root/tree/tree/src/TBranchElement.cxx:438`). When a tree holds two split objects
of one class whose sub-branches have no parent prefix, both objects'
counted-array members point at the first object's counter. In `alice_ESDs.root`
ROOT reads 0 elements for `PrimaryVertex.fIndices`, whose entries hold 18, 22, 6
and 13. `TreeReader` resolves a counter among siblings instead
(`ReadingEntries.md` §4.1 and erratum 6), and the entry's byte span is the
cross-check that catches the difference.

### The writing layer, and why its checks are the strongest here

`spec/06-writing/` is the write side: five numbered procedures with every field
marked **fixed**, **derived** or **free**, plus `ElementLists.md`, which is a
table document rather than a procedure. `tools/rootwrite.py` is the executable
form, a pure-Python writer built from those documents and independent of
`rootfile.py`. `tools/check_write.py` puts each file through three gates
(`spec/06-writing/index.md` §2):

```sh
tools/check_write.py                  # gates 1 and 2; no ROOT needed
tools/check_write.py --root           # all three
tools/check_write.py --accept         # re-record data/written/ after a deliberate change
```

1. the bytes match the committed copy in `data/written/` and every `[[bytes]]`
   assertion holds;
2. `rootfile.py` reads it and `check_invariants.py` accepts it;
3. ROOT opens it, `verify.C` finds the values that went in, and nothing on either
   output stream looks like a ROOT diagnostic. A `BuildCheck` warning or a
   `CheckByteCount` complaint fails the case, so gate 3 tests checksums and byte
   counts as well as values. A case may declare `expected_diagnostics` for lines
   about the session rather than the file; a declared line must then actually
   appear, so the list cannot go stale. The only one is the `no dictionary`
   warning that any class a writer invented produces.

Unlike the rest of `data/`, `data/written/` is byte-reproducible. A writer has no
reason to consult a clock, so `rootwrite.py` takes the timestamp and UUID as
inputs, and the manifest is a plain sha256.

**Eight kinds of record are byte-identical to ROOT's.** This comparison has found
every significant error:

- a `TH1F` (596 bytes) and a `TH1D` (651) against `data/classes/histogram.root`;
- a `StreamerInfo` record of fifteen infos (9628);
- both baskets plus the whole `TTree` record against `data/ttree/basket.root`;
- five baskets plus the 860-byte `TTree` record against
  `data/ttree/clusters.root`, the multi-basket and cluster-range case;
- a `TH2F`, a `TH2D` and two `TProfile`s against `data/classes/th2-profile.root`;
- a `TLeafC` basket with all three string forms plus the `TTree` record against
  `data/ttree/strings.root`;
- a `TGraph` and a `TGraphErrors` plus the whole 19-info `StreamerInfo` record
  against `data/classes/graph.root`;
- two subdirectory records and three key lists against
  `data/container/directories.root`, where the whole 1854-byte file matches
  except for each key's `fDatime`, three UUIDs and the file's own name.

Five files match a ROOT-written one in every byte, on the same terms:
`nested-subdir` (1854), `reused-space` (1747), `cycles-3` (1361), and the two
update cases `reopen-add` (1657) and `reopen-reuse` (1928). The update cases
build their bases in the same `build()` and hand them to `FileWriter.reopen` as
bytes, so the match shows both that the base was ROOT's and that the update
reached ROOT's result from it. The match includes the dead keys behind a gap
marker, which neither writer clears. `tools/test_write.py` names those two
offsets per file rather than blanking them, because a dead key cannot be parsed
out of a file.

Seven complete `StreamerInfo` records are byte-identical to ROOT's: 370, 9628,
11789, 12169, 14121, 14580 and 14584 bytes. That includes the `listOfRules` entry
ROOT appends, which four of them used to differ by. The entry is optional (ROOT
never reads it back) and holds rules for versions this writer never emits.
`rootwrite.KNOWN_RULES` holds the strings verbatim, and
`FileWriter(emit_rules=False)` drops the entry. If a fixture's `StreamerInfo`
record is ever one entry short, check this first.

The tree and subdirectory comparisons are the strictest. A branch stores its
baskets' offsets and a directory record stores three of its own, so in both cases
the two file names are deliberately the same length. When a comparison fails, the
difference is the finding: that is how the `TObjArray` pointer-versus-member
framing, the Y axis's `fTitleOffset` of 0, and the `fEntryOffsetLen` shrink at
flush were found.

Writing a class's streamer info requires the checksum algorithm
(`spec/02-serialization/StreamerInfo.md` §11). Two values cannot be computed from
an element list and are stored as constants in `rootwrite.KNOWN_CHECKSUMS`:
`THashList` and `TSeqCollection`, both class version 0, whose infos list no
members while their checksums include them. §11.2 has the other two exception
classes.

`element_lists.py` publishes the element list of each of the thirty-five classes
those procedures need into `spec/06-writing/ElementLists.md`. It reads the lists
out of the ROOT-written fixtures rather than out of `rootwrite.py`, compares the
seven sources against each other, compares every field with `rootwrite.py`, and
recomputes each checksum from the list it publishes.

```sh
tools/element_lists.py          # rewrite the generated blocks
tools/element_lists.py --check  # what CI runs
```

It exists because one category of field was unchecked. The subclass tail of an
element, such as a `TStreamerSTL`'s `fCtype` or a basic pointer's `fCountClass`,
is in no checksum and no byte count, and the element-by-element comparison in
`test_write.py` stopped at the `TStreamerElement` base. Four wrong values in
`rootwrite.py` had survived there, all in infos that nothing compared byte for
byte. Where possible, write a check that compares the whole record rather than
selected fields.

## Architecture

The repository has these parts, which depend on each other:

**`spec/`** is the specification, split by layer rather than by class, because
ROOT's format is layered and ~90% of classes are fully described by the container
and serialization layers plus a `TStreamerInfo` read out of the file itself. Only
the divergent classes need hand-written text. `docs_dir = "spec"`, so the
directory is also the site.

**`gen/written/<case>/`** holds the write side's cases: a `build.py` defining
`build() -> bytes`, a `case.toml` of the same shape, and a `verify.C` defining
`void verify(const char *path)` that prints `FAIL` lines and `VERIFY OK`. See
`gen/written/README.md`.

**`gen/cases/<group>/<case>/`** holds one `gen.C` (a ROOT macro defining
`void gen(const char *out)`) plus one `case.toml`. Each case exercises one thing.
A case may also hold a `classes.h`, which `generate.py` compiles into a dictionary
with ACLiC before loading the macro; `gen/common/README.md` says when that is
needed and why it has to be a separate step.

**`data/`** holds the generated reference files, committed, plus
`MANIFEST.sha256`.

**`tools/`** holds the checkers and `rootfile.py`, a pure-Python reader of the
header, record chain, directory records, key lists, decompression, the buffer
framing layer, the StreamerInfo record, the streamer-driven read, collections,
references and `TClonesArray`. zlib and lzma come from the standard library; zstd
needs Python 3.14 or `zstandard`, and LZ4 needs `lz4` (`requirements-codecs.txt`).
A record whose codec is missing is reported as "NOT CHECKED" rather than passing
silently. `rootfile.py` is
deliberately an independent implementation, written from the specification rather
than from ROOT's code, so that a disagreement between the two is detectable. It
reproduces `TFile::Map()` exactly.

### The central discipline

Every claim is verified twice: against the pinned submodule with a `path:line`
citation, and against real bytes in a fixture. The `[[bytes]]` assertions in
`case.toml` and the byte tables in `spec/` are written from the same reading, so an
error in either surfaces as a failing assertion. This has caught real mistakes.
Do not skip it, and do not write a byte table from the source alone.

`case.toml` assertions are checkable with stdlib Python only, so a third party
can use the fixtures as test vectors.

Three more tools check the specification's own claims.

**`check_coverage.py`** finds published claims that nothing checks. It reads every
numbered entry under every `Invariants` heading in `spec/`, matches it against the
labels the tools report, and requires anything left over to be accounted for in
`gen/invariants.toml` with one of five reasons: `alias`, `structural`,
`write-gate`, `not-checkable` or `unchecked`. It was written because the one
invariant this project published that was outright false was also one nobody had
wired up (`PLAN.md` §8.13); wiring up the rest found two more wrong
(`ElementTypes` 11.3 and 11.4) within the hour. There are 267 entries, 200 with a
check. The `unchecked` reason is a worklist, not an excuse, and it should stay
short. A second worklist is `--untested`: the checked labels no unit test names,
so no test has seen them fire. `tools/test_corruption.py` covers every label that
has been wrong before; add one there when a label joins that list.

**`inventory.py`** finds the classes whose streamer info does not describe their
bytes, which a reader cannot learn from a file. It reads every
`X::Streamer(TBuffer &)` in the submodule and sorts it by what the reading branch
does:

- `delegating`: calls `ReadClassBuffer` unconditionally and reads nothing after
  it, so the bytes are generated;
- `guarded`: does so above a version threshold;
- `extending`: calls it and then reads more bytes, which no streamer info
  describes and which sit outside the byte count;
- `custom`: never calls it, so the streamer info describes the bytes at no
  version.

`custom` and `extending` need specification, and each one must be resolved in
`spec/99-appendix/streamers.toml` or `--check` fails, so a submodule bump cannot
add one silently.

In the same pass it writes `spec/99-appendix/ForwardingStreamers.md`: the classes
whose generated `Streamer` writes only their bases, which is `ClassDef` version
`<= 0` plus a plain `#pragma link`. A reader cannot derive that list from a file,
because both generators record a streamer info and both record class version 0.
Having it is what lets `rootfile.py` read `aod_flushed.root`'s `TTreePerfStats`.

The `extending` category exists because the earlier three-way split published a
wrong claim for two months: `TMatrixTSym` reads the upper-right triangle after
`ReadClassBuffer`, and classifying it as `delegating` told a reader it needed
nothing. Two traps when editing the tool: a definition may spell its own scope
(`void ROOT::RNTuple::Streamer`), and a version dispatch may be a `switch` rather
than a comparison. Both failure modes were silent, and both understated what a
reader has to know.

The tool scans source text with comments and string literals blanked out.
`TStreamerInfo::Streamer` has its `ReadClassBuffer` call commented out and
replaced, and `ROOT::v5::TFormula` lives in a namespace inside a file full of
braces in string literals. Both were misclassified before blanking was added, in
the direction of "a reader needs nothing".

**`check_versions.py`** complements `check_citations.py`. The latter proves a
cited line exists but cannot prove the line still says what the citing sentence
claims, as `spec/00-conventions.md` §7 admits. For a class version that gap can
be closed completely, because the answer is an integer in a `ClassDef` macro.
64 are checked, across 13 documents, `TKey` among them from the `fVersion` table of
`Record.md` §3.4. A row that cites a header line must cite the `ClassDef` line
itself; four rows cited a blank line or an unrelated method until 2026-09-24. It
prints `NARROWED` for a table row that names classes it does not spell, a row it
can only partly check, so a silent narrowing is as visible as a `SKIPPED`.

## Repository-specific gotchas

These have cost time before. Most are not discoverable by reading the code.

**`spec/05-rntuple/` is not ours to edit.** `BinaryFormatSpecification.md` there
is a byte-for-byte copy of ROOT's own RNTuple specification, and
`tools/sync_rntuple.py --check` fails in CI, on every push, if it drifts from the
submodule. A correction goes in `ERRATA.md` beside it, never in the copy, or the
copy stops being evidence of what upstream says. `check_citations.py` skips that
one file, because a stale citation inside it could not be fixed without editing
it.

```sh
tools/sync_rntuple.py          # re-copy after a submodule bump, then audit the diff
tools/sync_rntuple.py --check  # what CI runs
```

**Reproducing a cross-platform digest drift.** A `DRIFT` from the Linux
regenerate job used to cost a CI round-trip per guess. The difference is libc++
against libstdc++, not architecture (see the `fSize` item below), so an arm64
container reproduces the x86_64 CI digests byte for byte and the loop runs
locally:

```sh
docker run --rm --platform linux/arm64 -v "$PWD":/work -w /work \
  condaforge/miniforge3:latest bash -lc \
  'conda install -y -q -c conda-forge root=6.40.04 && python3 tools/generate.py'
```

Copy `gen/`, `tools/` and `data/` into a scratch directory and mount that, so the
container's regeneration does not touch the working tree. `docker commit` the
container afterwards so reruns skip the four-minute ROOT install.

Then run `tools/normalize.py --members <file>` on each side and `diff` the output.
It prints one line per decoded member with its path, length and bytes, and no
offsets, so a member that grows does not bury the line that matters. That is how
the three causes in `PLAN.md` §9.6 were found, after `--per-record` had narrowed
the difference to a record.

Check exit codes rather than reading output: `DRIFT` goes to stderr, and a
`| tail` hides it along with the non-zero status.

**`set -e` does not abort in this environment.** `set -e; check1; check2; echo OK`
prints `OK` even when `check1` fails, so that idiom gives a false guarantee. Chain
the suite with `&&` instead, and treat CI as the authority:

```sh
tools/generate.py --check && tools/check_invariants.py \
  && tools/check_coverage.py --check && tools/check_write.py \
  && tools/check_pin.py && tools/check_citations.py && tools/check_versions.py \
  && tools/check_figures.py && tools/sync_rntuple.py --check \
  && tools/inventory.py --check && tools/element_lists.py --check \
  && PYTHONPATH=. .venv/bin/zensical build --clean --strict \
  && PYTHONPATH=tools .venv/bin/python -m unittest discover -s tools -p "test_*.py"
```

**The docs toolchain is separate** from the checks and is not needed for any
fixture check. `.venv/` is gitignored, so create it there:

```sh
uv venv .venv && uv pip install --python .venv/bin/python -r requirements-docs.txt
PYTHONPATH=. .venv/bin/zensical build --clean --strict
PYTHONPATH=. .venv/bin/zensical serve      # live preview
```

The rest:

- **Generators must receive repo-relative output paths.** `TFile` stores the path it
  was given as the file's name and title, so an absolute path bakes the checkout
  location into the fixture and shifts every byte offset after the header.
  `tools/generate.py` handles this; don't work around it.
- **Fixtures cannot be byte-reproducible.** Every `TKey` records the wall clock and
  every file and every directory gets its own UUID. `tools/normalize.py` masks
  them. Never add a raw `git diff -- data/` check; `generate.py`'s normalized digest
  is the real check.
- **Executable tools need a `#!/usr/bin/env python3` shebang.** CI invokes them as
  `./tools/foo.py`, so a missing shebang means bash tries to run Python.
- **`markdown` and `pymdownx` live only in the docs environment**, which comes with
  `zensical`. The citation extension's tests need it; the fixture checks do not.
- **Forward references must be inline code, not links.** `--strict` fails on links
  to pages that do not exist, and it checks anchors too. Convert to a link when
  the target is written. `spec/00-conventions.md` §6.5 has the rule, and the
  remaining inline-code references are the working list of what is missing.
- **A fixture can pass every byte assertion and still not be portable.** An
  element's `fSize` in a streamer info is `sizeof` on the writing machine, and it
  differs between standard libraries for several ordinary types:
  `sizeof(std::string)` is 24 with libc++ and 32 with libstdc++, and
  `sizeof(std::map<int,int>)` is 24 and 48. That changes the normalized digest
  between macOS and Linux CI while the file size and every assertion stay
  identical, so the only symptom is `DRIFT` in the regenerate job.
  `tools/normalize.py` now masks every `fSize` for this reason, which is what
  makes a `std::map` or `std::string` fixture possible at all. Because the digest
  no longer sees `fSize`, a case SHOULD assert it directly for members whose
  `sizeof` is standard-library independent (`std::vector` is 24 everywhere), so
  a change in which value ROOT stores still fails an assertion.
- **A fixture can also be one ROOT cannot read.** `serialization/collections`
  needs its `fOne` member for that reason; see `PLAN.md` 7.1. When a generated
  fixture is meant to round-trip, check it:
  `root -l -b -q -e 'auto f=TFile::Open("data/.../x.root"); f->Get("a");'` and
  look for `CheckByteCount` errors.
- **ACLiC fails on macOS with a recent Xcode SDK.** conda-forge ROOT's bundled
  clang targets an older Darwin, and linking against Xcode 26/27's SDK dies with
  `unknown architecture arm64e.x1` and then undefined symbols. Regenerate a case
  that has a `classes.h` with an older SDK:

  ```sh
  SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk tools/generate.py
  ```

  Nothing in the repository hardcodes that path; it is a property of the local
  toolchain. Linux CI needs no override, because conda-forge `root` has a
  compiler as a run dependency so that ACLiC works.
- **Never assume `root/io/doc/TFile/*.md` is correct.** It is the 3.02.06-era
  documentation. Roughly 37 errata against it are already recorded. Treat it as a
  source of questions, not answers.

## Writing a specification document

Follow the shape of `spec/01-container/Record.md`: overview, layout (bit diagram
plus an offset table, with a column per layout variant), fields, a numbered
**Reading** procedure, **Invariants**, **Errata**, and **Reference files**.

- Errata stay in the document they concern, as a table. Do not collect them centrally.
- Every `Invariants` entry should be checkable; add it to `tools/check_invariants.py`
  and confirm it catches a violation by corrupting a copy of a fixture. An invariant
  that passes vacuously is worse than none.
- Writing is specified as invariants, never as algorithms; see `PLAN.md` §2.8.
- Cite as `root/io/io/src/TFile.cxx:2679`; the site turns that into a link at the
  pinned commit via `tools/rootcite.py`.
- When the submodule is bumped, `tools/check_pin.py` will fail until the
  `tools.rootcite` commit in `zensical.toml` is updated.

## Researching ROOT internals

Dispatching the source archaeology to subagents has worked well. Ask for a dense
report with a `path:line` citation for every claim, an explicit instruction to
say "I am unsure" rather than guess, and a final section listing where the
shipped ROOT documentation is wrong. Then verify the findings against real bytes
yourself before writing them down. Subagent reports have been accurate here, but
byte-level confirmation has still caught errors in the dispatching agent's own
understanding.

Useful for ground truth: `TFile::Map()` for the record list, `TFile::ShowStreamerInfo()`
for member tables and checksums, and `git log -L` in the submodule for when a class
version changed.

## Commit messages

Bodies record what was *found*, not just what changed: a version-dependent field,
an erratum, a reader bug and how it surfaced. The git log is part of the project's
record of how the format was reverse-engineered.

**`CHANGELOG.md` is the reader's half of the same record** (`PLAN.md` decision 9).
A commit body says what was found; a changelog entry says what a reader of the
specification should now do differently. Add one under `## Unreleased` when a
change is reader-facing (a new document, a corrected claim, a closed gap, a fact a
reader would get wrong without it), and add none when it is not: a fixture, a
check or a refactor of `tools/` gets no entry. Releases are CalVer, `YYYY.MM.DD`,
tagged at a milestone. Cutting one means retitling `## Unreleased` with the date
and bumping `version` and `date-released` in `CITATION.cff`, and nothing else,
because the only version the documents state is ROOT's.
