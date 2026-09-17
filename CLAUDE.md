# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A specification of the ROOT on-disk binary formats, written so a third party can
implement a reader without reading ROOT's C++ source. ROOT ships only one real
format spec (RNTuple); its `TFile`/`TTree` documentation in `root/io/doc/TFile/`
describes **release 3.02.06** and is substantially wrong for current ROOT.

`PLAN.md` holds the structure, scope decisions and phasing. `spec/00-conventions.md`
holds the conventions every specification document depends on. Read both before
writing spec text; this file covers how to *work* here, not what to write.

## Commands

The full check suite, in the order CI runs it:

```sh
tools/generate.py --check      # byte assertions in every case.toml (no ROOT needed)
tools/check_invariants.py      # the Invariants sections of spec/01-container/
tools/check_pin.py             # zensical.toml cites the pinned submodule commit
tools/check_citations.py       # every cited file and line exists (needs submodule)
tools/check_versions.py        # every class-version table matches ClassDef (needs submodule)
tools/sync_rntuple.py --check  # spec/05-rntuple/ matches upstream (needs submodule)
tools/inventory.py --check     # the hand-written Streamer list matches the submodule
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
tools/fetch_foreign.py                      # 154 third-party files, 20 MB, to build/foreign/
tools/coverage_probe.py --summary build/foreign/*.root
```

Those files are **not** reference files and are not committed;
`gen/foreign/MANIFEST.sha256` records what was used. `PLAN.md` §9.8 has the
standing result.

The invariant checks run over the same corpus, and that is where format errors have
actually been found — thirteen of them so far, plus the legacy `CS` codec:

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
tools/fetch_cern.py                         # core tier: 22 files, 5 MB
tools/fetch_cern.py --tier physics          # 2 production trees, 27 MB more
tools/fetch_cern.py --headers               # the 8 multi-GB files, ~8 KB of traffic
tools/coverage_probe.py --summary build/cern/*.root
tools/check_invariants.py build/cern/*.root
```

`gen/cern/README.md` says why each file is listed and what gaps it exposes; the
listing has ~40 near-identical `TGeoManager` demos and only one is included.

`--headers` is the interesting one. root.cern serves `Accept-Ranges: bytes`, so the
header and free-segment record of a 5 GB file cost a few hundred bytes each, and
`gen/cern/LARGE.toml` records the measured facts for eight files from 1.3 GB to
5.3 GB. **That is the only thing exercising the large-file layout at all** — no
fixture does, and it already confirmed the interleaved 10-byte/18-byte `TFree`
entries of `FreeSegments.md` §2.1 on `volume.root` (51 entries, 32 large).

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

Over the two corpora that is **26948 of 27949, 96.4%**, with 0 failures. Read a
`0 failure(s)` line against the `ENTRIES` line: it means zero failures among the
things checked. The 1001 skips are named individually and fall into four groups:

- **920 an embedded basket** — a basket kept inside the `TTree` record rather than
  written as its own key (`TBranch.md` §5). `TreeReader` fetches baskets by file
  offset and an embedded one has none, so `ReadingEntries` invariant 5 cannot run
  on it. Reachable, unimplemented, and by far the largest item left: `PLAN.md`
  §8.3 item M8.
- **48 a collection whose value class has no streamer info in the file** — not a
  gap at all; `Collections.md` §9 says it is unreadable by anyone, ROOT included.
- **18 a branch or class whose `Streamer` is hand-written**, which no streamer
  info describes.
- **15 a basket whose record could not be read here**, a missing codec or a
  truncated file.

So two of the four groups are the reader's own plumbing and two are things no
reader could decode. `PLAN.md` §9.11 tracks what that leaves.

**That figure used to read 99.7%, and the difference is a correction, not a
regression.** Until 2026-09-17 neither entry check looked at an embedded basket
at all: the leaf-driven one iterated the baskets *below* `fWriteBasket` and the
embedded one sits *at* it, so 1266 branch-baskets were in neither the numerator
nor the denominator. The leaf-driven check now covers them, which is what closed
346 of those skips outright and what turned the other 920 from invisible into a
named line. A ratio that cannot see what it skipped is worth less than a lower
ratio that can.

Its companion lesson stands: two causes used to share the message
`counter basket unavailable` — a basket whose codec is missing, and a counter
basket embedded in the tree record — so they are spelled out separately. The
count is only as informative as the reason, and a shared message hides a
category.

**No skip over the fixtures is merely unimplemented any more.** `ttree/branch-clones`
used to contribute four, because its counter branch keeps its basket embedded and
the counter lookup could only fetch a record; it now reads the embedded basket out
of the `TTree` payload. The two that remain are a class with a hand-written
`Streamer` and a collection with no streamer info in its own file.

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
