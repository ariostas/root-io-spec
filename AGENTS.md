# AGENTS.md

This file provides guidance to coding agents working in this repository.

## What this repository is

A specification of the ROOT on-disk binary formats, written so a third party can
implement a reader without reading ROOT's C++ source. ROOT ships only one real
format spec (RNTuple); its `TFile`/`TTree` documentation in `root/io/doc/TFile/`
describes **release 3.02.06** and is substantially wrong for current ROOT.

`PLAN.md` holds the structure, scope decisions and phasing; its §8.12 is the write
side's second half — free-space reuse, key ordering, updating a file and schema
evolution, all landed 2026-09-21 — and carries the six findings that came out of
it. Its §8.13 is the first outside review, GitHub issue #1, answered in full over
2026-09-21/22 and worth reading before adding a claim: eight published claims of
ours turned out false or incomplete, six of them in the population nothing was
checking. **`PLAN-corpus.md` is the open sub-plan**, written 2026-09-22 from a
survey of six external resources: four published claims of ours that a ROOT-written
file contradicts, three reader bugs behind them, four §9 rows with a first witness,
and a list of confirmed dead ends so they are not re-investigated. Read its §1
before working any item — it separates what was reproduced here from what one
survey merely reported, and that column is not to be collapsed.
A sub-plan is deleted once discharged, with anything durable moved into `PLAN.md`
or `spec/` first.
`spec/00-conventions.md` holds the conventions every specification document depends
on. Read those before writing spec text; this file covers how to *work* here, not
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
tools/check_versions.py        # every class-version table matches ClassDef (needs submodule)
tools/sync_rntuple.py --check  # spec/05-rntuple/ matches upstream (needs submodule)
tools/inventory.py --check     # the hand-written Streamer list matches the submodule
tools/element_lists.py --check # the published element lists match the fixtures
PYTHONPATH=. zensical build --clean --strict          # site; fails on broken links
PYTHONPATH=tools python -m unittest discover -s tools -p "test_*.py"
```

Regenerating fixtures needs ROOT on PATH, matching the pinned submodule:

```sh
tools/generate.py                                      # all cases
tools/generate.py gen/cases/container/file-minimal     # one case
tools/generate.py --accept <case-dir>                  # after editing a case on purpose
```

A digest differing from `data/MANIFEST.sha256` is an error: either the format
changed or a fixture stopped being reproducible. `--accept` re-records it, and is
the right move only when you changed the case yourself.

`tools/coverage_probe.py <file.root>` is not a CI check: it measures how much of a
file the specification currently covers, and prints what blocked each record.
`--summary` gives one line per file. Point it at files the fixtures were not
designed around to get a ranked list of what is still missing, rather than guessing
from `PLAN.md`:

```sh
tools/fetch_foreign.py                      # 180 third-party files, 24 MB, to build/foreign/
tools/coverage_probe.py --summary build/foreign/*.root
```

Those files are **not** reference files and are not committed;
`gen/foreign/MANIFEST.sha256` records what was used. `PLAN.md` §9.8 has the
standing result.

The invariant checks run over the same corpus, and that is where format errors have
actually been found — fourteen of them so far, plus the legacy `CS` codec:

```sh
tools/check_invariants.py --ignore gen/foreign/IGNORE.toml build/foreign/*.root
```

**Their provenance is mixed**: the source is uproot's regression corpus, which
includes files uproot wrote. So a failure there is a lead, not evidence. Diagnose
it against the pinned source and resolve it to one of four things — a spec error, a
missing format fact, a reader gap, or a file at fault. Only the last goes in
`gen/foreign/IGNORE.toml`, per file and per invariant, with a reason and with the
suppressed count printed. **Never weaken an invariant because a file disagrees with
it**; ROOT's source is the authority, and "does ROOT itself read this file" is a
useful objective check along the way.

### The second corpus: files ROOT wrote

`gen/cern/` is the same idea without the provenance problem. Everything in it was
written by ROOT and published by the ROOT team at <https://root.cern/files/>, so a
failure **is** evidence rather than a lead. It also reaches from ROOT 2.24/00 to
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

`gen/cern/README.md` says why each file is listed and what gaps it exposes. The ~40
near-identical `TGeoManager` demos used to be excluded for being near-identical;
they are the `geometry` tier since 2026-09-21, because four of them turned out to
carry `StreamerInfo.md` §9.2's whole `fBaseVersion` table and nothing recorded that
the corpus the measurements used was bigger than the corpus the manifest defined
(`PLAN.md` §8.13). **A file the specification cites is in the corpus whether
the manifest says so or not**, which is now a check: `check_citations.py` fails on a
cited `.root` that no fixture and no manifest accounts for.

`--headers` is the interesting one. root.cern serves `Accept-Ranges: bytes`, so the
header, free-segment record, top directory record and key list of a 5 GB file
cost a few hundred bytes each, and
`gen/cern/LARGE.toml` records the measured facts for eleven files from 1.3 GB to
15.9 GB, three of them from CERN Open Data by an absolute `url`. **That is the only thing exercising the large-file layout at all** — no
fixture does, and it already confirmed the interleaved 10-byte/18-byte `TFree`
entries of `FreeSegments.md` §2.1 on `volume.root` (51 entries, 32 large).

**`root/roottest/` needs no fetch**: ROOT's own test suite ships inside the pinned
submodule, 274 ROOT-written files from 2.23/12 to 6.41/01, and the ones the
specification cites are a table in `gen/cern/README.md` that `check_citations.py`
reads. Run the tools on a listed path directly. Do not run them on the whole
directory: `root/tree/basket/corrupted.root` is damaged on purpose.
**To date a class version to a release, read it at the tag**, since the
submodule's history reaches ROOT 1:
`git -C root show v3-03-07:base/inc/TDirectory.h`. Three published boundaries
were wrong until that was done (`PLAN-corpus.md` C9, C11).

Adding a file to either corpus: it must earn its place by covering something no
fixture and no listed file does, and the reason goes in the README. Re-running
`--headers` after a `rootfile.py` change is a cheap regression check on the
container layer.

**The entry check samples on large baskets.** `TLeaf.md` 10.7 costs one
`entry_spans` call per entry per branch, so a 42 000-entry tree with 32 branches is
millions of them. Above 256 entries in a basket, `check_invariants.py` checks the
first and last 32 and a stride through the middle, and says `SAMPLED n basket(s)`
so it is never silent about it. `--all-entries` forces the exhaustive check; both
modes give 0 failures over the fixtures and `gen/foreign/`, which is what justifies
the default.

**And it says out loud what it could not reach.** Two checks decode entries:
`entry_spans` for a plain `TBranch`, which is leaf-driven, and
`rootfile.TreeReader` for a `TBranchElement`, which is `ReadingEntries.md`
invariant 5 — the bytes an entry occupies equal the bytes its decoding consumes.
Each prints `SKIPPED n branch-basket(s)` per reason when it cannot run, and the
run ends with an `ENTRIES` line giving the fraction it did reach.

Over the two corpora that is **46137 of 46241, 99.8%**, with 0 failures, and
all 104 skips are of two kinds, both of them **things no reader could decode
from the file**:

- **a collection whose value class has no streamer info in it** — `Collections.md`
  §9 says nobody can read those, ROOT included;
- **a class whose `Streamer` is hand-written**, which no streamer info describes.
  Two of these are named by the bytes rather than by a list: `nEXO::SmartRef`
  has no byte count, and neither of the two readings `StreamerDriven.md` §7.1
  allows ends where its entry does.

For one day that list had a third kind, and the figure was 97.7%: 975
branch-baskets of an ATLAS class that *is* a collection, whose value class the
reader could not find. It was in the element's title all along
(`Collections.md` §11.2): the survey that raised it had said "named only by
checksum", and reading `TStreamerInfo::Build` was enough to find otherwise. And the
`SmartRef` skips used to be **passes**: the reader read every object with no
byte count version first, which lands exactly on each 20-byte `SmartRef` by
coincidence, while failing `skim.root`, which ROOT reads correctly. A pass is
only as good as the reading behind it.
Read a `0 failure(s)` line against the `ENTRIES` line all the same: it means zero
failures among the things checked, and that is the number to quote.

**That figure read 99.7% until 2026-09-17, then 96.4%, and both moves were
corrections.** Neither entry check had ever looked at an **embedded** basket — one
kept inside the `TTree` record rather than written as its own key (`TBranch.md`
§5). The leaf-driven check iterated the baskets *below* `fWriteBasket` and an
embedded one sits *at* it, so 1266 branch-baskets were in neither the numerator nor
the denominator: the old 99.7% was measuring the wrong denominator. Making them
visible dropped the ratio to 96.4%, and then reading them raised it to 99.8% of a
bigger number. A ratio that cannot see what it skipped is worth less than a lower
one that can.

Its companion lesson stands: two causes used to share the message
`counter basket unavailable` — a basket whose codec is missing, and a counter
basket embedded in the tree record — so they are spelled out separately. The count
is only as informative as the reason, and a shared message hides a category.

**Reading those baskets found a ROOT bug**, which is the return on the work.
`fBranchCount` is set from a counter name looked up over the whole tree
(`root/tree/tree/src/TBranchElement.cxx:438`), so when a tree holds two split
objects of one class whose sub-branches carry no parent prefix, both objects'
counted-array members point at the **first** object's counter. In
`alice_ESDs.root` ROOT reads 0 elements for `PrimaryVertex.fIndices`, whose entries
hold 18, 22, 6 and 13. `TreeReader` resolves a counter among siblings instead —
`ReadingEntries.md` §4.1 and erratum 6 — and the entry's byte span is the
cross-check that catches the difference.

### The writing layer, and why its checks are the strongest here

`spec/06-writing/` is the write side: five numbered procedures with every field
marked **fixed**, **derived** or **free**, plus `ElementLists.md`, which is a table
document rather than a procedure. `tools/rootwrite.py` is
the executable form — a pure-Python writer built from those documents, independent
of `rootfile.py` — and `tools/check_write.py` puts each file through three gates
(`spec/06-writing/index.md` §2):

```sh
tools/check_write.py                  # gates 1 and 2; no ROOT needed
tools/check_write.py --root           # all three
tools/check_write.py --accept         # re-record data/written/ after a deliberate change
```

1. the bytes match the committed copy in `data/written/` and every `[[bytes]]`
   assertion holds;
2. `rootfile.py` reads it and `check_invariants.py` accepts it;
3. ROOT opens it, `verify.C` finds the values that went in, and **nothing on
   either stream looks like a ROOT diagnostic** — a `BuildCheck` warning or a
   `CheckByteCount` complaint fails the case, which is what makes gate 3 an
   assertion about checksums and byte counts rather than about values. A case may
   declare `expected_diagnostics` for lines that are about the *session* rather
   than the file; a declared line must then actually appear, so the escape hatch
   cannot rot. The only one is the `no dictionary` warning any class a writer
   invented produces.

`data/written/` is **byte-reproducible**, unlike the rest of `data/`: a writer has
no reason to consult a clock, so `rootwrite.py` takes the timestamp and UUID as
inputs and the manifest is a plain sha256.

**Eight kinds of record are byte-identical to ROOT's**, which is the check that
found every error worth having: a `TH1F` (596 bytes) and a `TH1D` (651) against
`data/classes/histogram.root`, a `StreamerInfo` record of fifteen infos (9628),
both baskets plus the whole `TTree` record against `data/ttree/basket.root`,
**five baskets plus the 860-byte `TTree` record** against
`data/ttree/clusters.root`, which is the multi-basket and cluster-range case,
a `TH2F`, a `TH2D` and two `TProfile`s against `data/classes/th2-profile.root`,
a `TLeafC` basket with all three string forms plus the `TTree` record against
`data/ttree/strings.root`, a `TGraph` and a `TGraphErrors` **plus the whole
19-info `StreamerInfo` record** against `data/classes/graph.root`, and
**two subdirectory records and three key lists** against
`data/container/directories.root` — where the whole 1854-byte file matches bar each
key's `fDatime`, three UUIDs and the file's own name.

**Five files match a ROOT-written one for every byte of the file**, on those same
terms: `nested-subdir` (1854), `reused-space` (1747), `cycles-3` (1361), and the
two **update** cases `reopen-add` (1657) and `reopen-reuse` (1928), whose bases
are built in the same `build()` and handed to `FileWriter.reopen` as bytes — so
the agreement says both that the base was ROOT's and that the update reached
ROOT's answer from it. Their agreement extends to the dead keys buried behind a
gap marker, which neither writer clears: `tools/test_write.py` names those two
offsets per file rather than blanking them, because a dead key cannot be parsed
out of a file.
**Seven whole `StreamerInfo` records** are byte-identical to ROOT's — 370, 9628,
11789, 12169, 14121, 14580 and 14584 bytes — including the `listOfRules` entry
ROOT appends, which four of them used to differ by. That entry is optional (ROOT
never reads it back) and carries rules for versions this writer never emits;
`rootwrite.KNOWN_RULES` holds the strings verbatim and `FileWriter(emit_rules=False)`
drops it. If a fixture's `StreamerInfo` record is ever one entry short, that is
the first thing to check.
The tree and subdirectory comparisons are the strictest, because a branch stores
its baskets' *offsets* and a directory record stores three of its own, so in both
cases the two file names are deliberately the same length. When a
comparison fails, the difference is the finding — that is how the `TObjArray`
pointer-versus-member framing, the Y axis's `fTitleOffset` of 0, and the
`fEntryOffsetLen` shrink at flush were all discovered.

Writing a class's streamer info is where a writer meets the checksum algorithm
(`spec/02-serialization/StreamerInfo.md` §11). Two values **cannot** be computed
from an element list and are carried as constants in `rootwrite.KNOWN_CHECKSUMS`:
`THashList` and `TSeqCollection`, both class version 0, whose infos list no members
while their checksums fold them. §11.2 has the other two exception classes.

`element_lists.py` publishes the element list of each of the thirty-five classes
those procedures need, into `spec/06-writing/ElementLists.md`, **read out of the
ROOT-written fixtures** rather than out of `rootwrite.py` — and it compares the
seven sources against each other, compares every field with `rootwrite.py`, and
recomputes each checksum from the list it publishes.

```sh
tools/element_lists.py          # rewrite the generated blocks
tools/element_lists.py --check  # what CI runs
```

It exists because a whole category of field was unchecked: the **subclass tail** of
an element — a `TStreamerSTL`'s `fCtype`, a basic pointer's `fCountClass` — is in
no checksum and in no byte count, and the element-by-element comparison in
`test_write.py` stopped at the `TStreamerElement` base. Four wrong values in
`rootwrite.py` had survived there, all four in infos nothing compared byte for
byte. Prefer a check that reads the whole record over one that reads the fields
you thought of.

**`spec/05-rntuple/` is not ours to edit.** `BinaryFormatSpecification.md` there
is a byte-for-byte copy of ROOT's own RNTuple specification, and
`tools/sync_rntuple.py --check` fails if it drifts from the submodule — in CI, on
every push. A correction goes in `ERRATA.md` beside it, never in the copy, or the
copy stops being evidence of what upstream says. `check_citations.py` skips that
one file for the same reason: a stale citation inside it could not be fixed
without editing it.

```sh
tools/sync_rntuple.py          # re-copy after a submodule bump, then audit the diff
tools/sync_rntuple.py --check  # what CI runs
```

`check_coverage.py` is the same idea applied to this project rather than to ROOT:
**which of our own published claims is nothing checking?** It reads every numbered
entry under every `Invariants` heading in `spec/`, matches it against the labels
the tools actually report, and requires anything left over to be accounted for in
`gen/invariants.toml` with one of five reasons — `alias`, `structural`,
`write-gate`, `not-checkable` or `unchecked`. It exists because the one invariant
this project has published that was outright **false** was also one nobody had
wired up (`PLAN.md` §8.13), and wiring up the rest found two more wrong
(`ElementTypes` 11.3 and 11.4) within the hour. 259 entries, 191 with a check.

The `unchecked` reason is a worklist, not an excuse, and it should stay short.

`inventory.py` answers the one question a reader cannot put to a file: **which
classes is the streamer info lying about?** It reads every
`X::Streamer(TBuffer &)` in the submodule and sorts it by what the reading branch
does — `delegating` (calls `ReadClassBuffer` unconditionally and reads nothing
after it, so the bytes are generated), `guarded` (above a version threshold),
`extending` (calls it and then reads **more bytes**, which no streamer info
describes and which sit outside the byte count), or `custom` (never, so the
streamer info describes the bytes at no version). `custom` and `extending` need
specification, and each one must be resolved in
`spec/99-appendix/streamers.toml` or `--check` fails, so a submodule bump cannot
add one silently.

It writes a second document in the same pass,
`spec/99-appendix/ForwardingStreamers.md`: the classes whose **generated**
`Streamer` writes only their bases, which is `ClassDef` version `<= 0` plus a
plain `#pragma link`. That list is what a reader cannot derive from a file — both
generators record a streamer info and both record class version 0 — and carrying
it is what lets `rootfile.py` read `aod_flushed.root`'s `TTreePerfStats`.

`extending` exists because the three-way split published a wrong claim for two
months: `TMatrixTSym` reads the upper-right triangle after `ReadClassBuffer`, and
calling that `delegating` told a reader it needed nothing. Two smaller traps in
the same tool are worth remembering when editing it — a definition may spell its
own scope (`void ROOT::RNTuple::Streamer`), and a version dispatch may be a
`switch` rather than a comparison. Both failure modes were silent and both
understated what a reader has to know, which is the direction that matters.

It scans source text with comments and string literals blanked out, which is not
fussiness: `TStreamerInfo::Streamer` has its `ReadClassBuffer` call commented out
and replaced, and `ROOT::v5::TFormula` lives in a namespace inside a file full of
braces in string literals. Both were misclassified before that pass existed, and
both in the direction of "a reader needs nothing".

`check_versions.py` is the companion to `check_citations.py`. The latter proves a
cited line exists; it cannot prove the line still says what the citing sentence
claims, and `spec/00-conventions.md` §7 admits as much. A **class version** is the
one kind of claim where that gap can be closed completely, because the answer is
an integer in a `ClassDef` macro. Sixteen of them are checked. It also prints
`NARROWED` for a table row that names classes it does not spell — a row it can
only partly check — so a silent narrowing is visible the way `SKIPPED` is.

**Reproducing a cross-platform digest drift.** `DRIFT` from the Linux regenerate
job used to mean a CI round-trip per guess. It does not have to: the difference is
**libc++ against libstdc++, not architecture**, so an arm64 container reproduces
the x86_64 CI digests byte for byte and the loop becomes local and fast.

```sh
docker run --rm --platform linux/arm64 -v "$PWD":/work -w /work \
  condaforge/miniforge3:latest bash -lc \
  'conda install -y -q -c conda-forge root=6.40.04 && python3 tools/generate.py'
```

Copy `gen/`, `tools/` and `data/` into a scratch directory and mount that, so the
container's regeneration does not touch the working tree; `docker commit` the
container afterwards and reruns skip the four-minute ROOT install.

Then `tools/normalize.py --members <file>` on each side and `diff` them: it prints
one line per decoded member with its path, length and bytes, and no offsets, so a
member that grows does not bury the one line that matters. That is how the three
causes in `PLAN.md` §9.6 were found, after `--per-record` had narrowed it to a
record.

Check exit codes rather than eyeballing output — `DRIFT` goes to stderr and a
`| tail` will hide it along with the non-zero status.

**`set -e` does not abort in this environment.** A `set -e; check1; check2; echo OK`
prints `OK` even when `check1` fails, so that idiom gives a false guarantee. Chain
the suite with `&&` instead, and treat CI as the authority:

```sh
tools/generate.py --check && tools/check_invariants.py && tools/check_pin.py \
  && tools/check_citations.py && tools/check_versions.py \
  && PYTHONPATH=. .venv/bin/zensical build --clean --strict \
  && PYTHONPATH=tools .venv/bin/python -m unittest discover -s tools -p "test_*.py"
```

Docs toolchain is separate from the checks and is not needed for any fixture
check. `.venv/` is gitignored, so create it there:

```sh
uv venv .venv && uv pip install --python .venv/bin/python -r requirements-docs.txt
PYTHONPATH=. .venv/bin/zensical build --clean --strict
PYTHONPATH=. .venv/bin/zensical serve      # live preview
```

## Architecture

Four pieces that lean on each other:

**`spec/`** — the specification, split by *layer* rather than by class, because
ROOT's format is layered and ~90% of classes are fully described by the container
plus serialization layers plus a `TStreamerInfo` read out of the file itself. Only
the divergent classes need hand-written text. `docs_dir = "spec"`, so the directory
is also the site.

**`gen/written/<case>/`** — the write side's cases: a `build.py` defining
`build() -> bytes`, a `case.toml` of the same shape, and a `verify.C` defining
`void verify(const char *path)` that prints `FAIL` lines and `VERIFY OK`. See
`gen/written/README.md`.

**`gen/cases/<group>/<case>/`** — one `gen.C` (a ROOT macro defining
`void gen(const char *out)`) plus one `case.toml`. Each case exercises *one* thing.
A case may also hold a `classes.h`, which `generate.py` compiles into a dictionary
with ACLiC before loading the macro; `gen/common/README.md` says when that is
needed and why it has to be a separate step.

**`data/`** — the generated reference files, committed, plus `MANIFEST.sha256`.

**`tools/`** — checkers, and `rootfile.py`, a pure-Python reader of the header,
record chain, directory records, key lists, decompression, the buffer framing
layer, the StreamerInfo record, the streamer-driven read, collections, references
and `TClonesArray`. zlib and lzma come from the standard library; zstd needs Python
3.14 and LZ4 needs a package, and a record whose codec is missing is reported as
"NOT CHECKED" rather than passing silently. It is deliberately an independent implementation of what
`spec/` specifies, written from the specification rather than from ROOT's code, so
that the two disagreeing is a detectable event. It reproduces `TFile::Map()`
exactly.

### The central discipline

Every claim is verified twice: against the pinned submodule with a `path:line`
citation, and against real bytes in a fixture. The `[[bytes]]` assertions in
`case.toml` and the byte tables in `spec/` are written from the same reading, so an
error in either surfaces as a failing assertion. This has already caught real
mistakes — do not skip it, and do not write a byte table from the source alone.

`case.toml` assertions are checkable with stdlib Python only, which is what lets a
third party use the fixtures as test vectors.

## Repository-specific gotchas

These cost time this session. Most are not discoverable by reading the code.

- **Generators must receive repo-relative output paths.** `TFile` stores the path it
  was given as the file's name and title, so an absolute path bakes the checkout
  location into the fixture and shifts every byte offset after the header.
  `tools/generate.py` handles this; don't work around it.
- **Fixtures cannot be byte-reproducible.** Every `TKey` records the wall clock and
  every file *and every directory* gets its own UUID. `tools/normalize.py` masks
  them. Never add a raw `git diff -- data/` check; `generate.py`'s normalized digest
  is the real check.
- **Executable tools need a `#!/usr/bin/env python3` shebang.** CI invokes them as
  `./tools/foo.py`, so a missing shebang means bash tries to run Python.
- **`markdown` and `pymdownx` live only in the docs environment**, which comes with
  `zensical`. The citation extension's tests need it; the fixture checks do not.
- **Forward references must be inline code, not links.** `--strict` fails on links
  to pages that do not exist, and it checks **anchors** too. Convert to a link when
  the target is written — `spec/00-conventions.md` §6.5 has the rule, and the
  remaining inline-code references are the working list of what is missing.
- **A fixture can pass every byte assertion and still not be portable.** An
  element's `fSize` in a streamer info is `sizeof` on the writing machine, and it
  differs between standard libraries for several ordinary types:
  `sizeof(std::string)` is 24 with libc++ and 32 with libstdc++,
  `sizeof(std::map<int,int>)` 24 and 48. That drifts the normalized digest
  between macOS and Linux CI while the file size and every assertion stay
  identical, so the only symptom is `DRIFT` in the regenerate job.
  `tools/normalize.py` now masks every `fSize` for exactly this reason, which is
  what makes a `std::map` or `std::string` fixture possible at all. Because the
  digest can no longer see `fSize`, a case SHOULD assert it directly for members
  whose `sizeof` is standard-library independent (`std::vector` is 24
  everywhere), so a change in *which* value ROOT stores still fails an assertion.
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
  toolchain. Linux CI needs no override — conda-forge `root` has a compiler as a
  run dependency precisely so ACLiC works.
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
- Writing is specified as invariants, never as algorithms — see `PLAN.md` §2.8.
- Cite as `root/io/io/src/TFile.cxx:2679`; the site turns that into a link at the
  pinned commit via `tools/rootcite.py`.
- When the submodule is bumped, `tools/check_pin.py` will fail until the
  `tools.rootcite` commit in `zensical.toml` is updated.

## Researching ROOT internals

Dispatching the source archaeology to subagents worked well: ask for a dense report
with a `path:line` citation for **every** claim, an explicit instruction to say "I am
unsure" rather than guess, and a final section listing where the shipped ROOT
documentation is wrong. Then verify the findings against real bytes yourself before
writing them down — subagent reports have been accurate here but the byte-level
confirmation has still caught errors in *my* understanding.

Useful for ground truth: `TFile::Map()` for the record list, `TFile::ShowStreamerInfo()`
for member tables and checksums, and `git log -L` in the submodule for when a class
version changed.

## Commit messages

Bodies record what was *found*, not just what changed — a version-dependent field, an
erratum, a reader bug and how it surfaced. The git log is part of the project's
record of how the format was reverse-engineered.

**`CHANGELOG.md` is the reader's half of the same record** (`PLAN.md` decision 9).
A commit body says what was *found*; a changelog entry says what a reader of the
specification should now do differently. Add one under `## Unreleased` when a change
is reader-facing -- a new document, a corrected claim, a closed gap, a fact a reader
would get wrong without it -- and add none when it is not: a fixture, a check, a
refactor of `tools/` leaves no entry. Releases are CalVer, `YYYY.MM.DD`, tagged at a
milestone; cutting one means retitling `## Unreleased` with the date and bumping
`version` and `date-released` in `CITATION.cff`, and nothing else, because the only
version the documents state is **ROOT's**.
