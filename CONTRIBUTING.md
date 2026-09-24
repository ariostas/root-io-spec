# Contributing

The project rests on one rule:

> **Every claim is verified twice.** Once against ROOT's source, with a
> `path:line` citation into the pinned release. Once against real bytes, in a
> committed reference file with assertions that a third party can check.

A claim with only one of the two is not finished. Nineteen errors in this
specification were found by one witness disagreeing with the other; `PLAN.md`
§9.8 and §9.9 list them.

Two consequences:

- **A correction to the specification is more welcome than an addition.** If you
  can show that a sentence here is wrong about ROOT, that is the most valuable
  thing you can send, and it does not need a fixture.
- **Never weaken an invariant because a file disagrees with it.** Diagnose the
  disagreement first. It is a specification error, a missing format fact, a
  reader gap, or a file at fault, and only the last one gets suppressed. ROOT's
  source is the authority, and "does ROOT itself read this file" is a useful
  check along the way.

## Running the checks

The fixture checks need only Python 3.12+. ROOT is needed only to regenerate
fixtures, and the docs toolchain is separate from both.

```sh
git clone --recurse-submodules https://github.com/ariostas/root-io-spec
cd root-io-spec
tools/generate.py --check      # the byte assertions in every case.toml
tools/check_invariants.py      # the Invariants sections, over the reference files
tools/check_coverage.py --check # every published invariant is checked, or has a reason
tools/check_write.py           # the files tools/rootwrite.py writes (--root adds ROOT)
tools/element_lists.py --check # the published element lists match the fixtures
tools/check_citations.py       # every cited file and line exists (needs the submodule)
tools/check_figures.py         # the counts the pages quote, per gen/figures.toml
tools/check_versions.py        # every class-version table matches ClassDef
tools/check_pin.py             # zensical.toml cites the pinned submodule commit
tools/sync_rntuple.py --check  # spec/05-rntuple/ matches upstream
tools/inventory.py --check     # the two generated class lists match the submodule
PYTHONPATH=tools python -m unittest discover -s tools -p "test_*.py"
```

CI runs those, plus a strict docs build. Chain them with `&&` rather than
`set -e`, and check exit codes rather than output: `DRIFT` and `FAIL` go to
stderr, where a `| tail` will hide them.

The site needs its own environment:

```sh
pip install -r requirements-docs.txt
PYTHONPATH=. zensical serve             # live preview
PYTHONPATH=. zensical build --strict    # as CI builds it
```

`--strict` fails on a link to a page or an anchor that does not exist. A forward
reference to something unwritten is therefore written as inline code rather than
as a link, and the remaining inline-code references are the working list of what
is missing (`spec/00-conventions.md` §6.5).

## Adding a reference file

One directory per case under `gen/cases/<group>/<case>/`, holding a ROOT macro
and its assertions. **Each case exercises one thing**, because a case that
demonstrates five facts is hard to shrink when one of them changes.

```
gen/cases/container/gap/
├── gen.C        void gen(const char *out) { ... }   -- writes one file
└── case.toml    what its bytes must be
```

`gen.C` defines `void gen(const char *out)` and nothing else. Regenerate with:

```sh
tools/generate.py gen/cases/container/gap     # one case
tools/generate.py                             # all of them
tools/generate.py --accept <case-dir>         # after changing a case on purpose
```

The ROOT on `PATH` must match the pinned submodule, or the fixtures will not be
reproducible against CI.

A case that needs a class with a real `ClassDef` adds a `classes.h`, which
`generate.py` compiles into a dictionary with ACLiC before loading the macro;
`gen/common/README.md` says why that has to be a separate step.

### `case.toml`

Assertions must be checkable with stdlib Python only, so that another project can
vendor the fixtures as test vectors:

```toml
[[bytes]]
offset = 718
type = "i32"
value = -187
note = "the in-place marker: the negative of the merged span, FreeSegments.md 4"
```

Give every assertion a `note` naming the section it comes from. The byte tables in
`spec/` and the assertions here are written from the same reading, so an error in
either shows up as a failing assertion. Write them together, and never write a
byte table from ROOT's source alone.

### Two traps that cost a day each

- **Generators receive repo-relative output paths.** `TFile` stores the path it
  was given as the file's name *and* title, so an absolute path bakes your
  checkout location into the fixture and shifts every offset after the header.
  `tools/generate.py` handles this; do not work around it.
- **Fixtures cannot be byte-reproducible.** Every key records the wall clock and
  every file and directory gets a UUID. `tools/normalize.py` masks those, and
  `generate.py`'s normalized digest against `data/MANIFEST.sha256` is the real
  check. Never add a raw `git diff -- data/` check.

A digest that differs is an error: either the format changed or a fixture stopped
being reproducible. So is a case with no line in the manifest. `--accept`
re-records the digests, and is the right move only when you changed or added the
case yourself.

### When the digest differs between platforms

An element's `fSize` in a streamer info is `sizeof` on the writing machine, and
several ordinary types differ between standard libraries:
`sizeof(std::string)` is 24 with libc++ and 32 with libstdc++. `normalize.py`
masks every `fSize` for that reason, so a case SHOULD assert `fSize` directly for
members whose `sizeof` is standard-library independent.

A cross-platform `DRIFT` comes from **libc++ against libstdc++, not from
architecture**, so a Linux container reproduces CI's digests locally:

```sh
docker run --rm --platform linux/arm64 -v "$PWD":/work -w /work \
  condaforge/miniforge3:latest bash -lc \
  'conda install -y -q -c conda-forge root=6.40.04 && python3 tools/generate.py'
```

Copy `gen/`, `tools/` and `data/` to a scratch directory and mount that, so the
container does not touch your working tree. Then `tools/normalize.py --members`
on each side and `diff`.

## Writing specification text

Follow the shape of `spec/01-container/Record.md`: overview, layout (a bit diagram
plus an offset table with a column per variant), fields, a numbered **Reading**
procedure, **Invariants**, **Errata**, **Reference files**.

- **Cite as `root/io/io/src/TFile.cxx:2679`.** The site turns that into a link at
  the pinned commit. `check_citations.py` proves the line exists but not that it
  still says what your sentence claims, so keep the claim near the citation.
- **Every invariant must be checkable.** Add it to `tools/check_invariants.py`
  and confirm it catches a violation by corrupting a copy of a fixture. An
  invariant that passes vacuously is worse than none. Where no fixture can reach
  it (the >2 GB layout, the legacy `TBranch` versions), say so in the document
  and pin it with a unit test instead.
- Writing is specified as invariants, never as algorithms (`PLAN.md` §2.8).
  Free-space allocation, basket sizing and key ordering are ROOT's choices, not
  requirements of the format, so they are marked free; where a byte comparison
  with ROOT needs ROOT's own choice, it is specified as that and still marked
  free (`spec/06-writing/WritingFiles.md` §8).
- Errata stay in the document they concern, as a table. Do not collect them
  centrally.
- **Do not edit `spec/05-rntuple/BinaryFormatSpecification.md`.** It is a tracked
  copy of ROOT's own document and CI fails if it drifts. Corrections go in
  `ERRATA.md` beside it, so the copy remains evidence of what upstream says.
- Never assume `root/io/doc/TFile/*.md` is correct. It describes release
  3.02.06, and roughly 37 errata against it are already recorded. Treat it as a
  source of questions, not answers.

## The two corpora

Neither is committed. Both are fetched on demand, and running the checks over
them is where format errors have actually been found:

```sh
tools/fetch_cern.py && tools/check_invariants.py build/cern/*.root
tools/fetch_foreign.py && tools/check_invariants.py --ignore gen/foreign/IGNORE.toml build/foreign/*.root
tools/coverage_probe.py --summary build/cern/*.root      # what is still unread, ranked
```

They are not equivalent. `gen/cern/` holds files the ROOT team published, so a
failure there is evidence. `gen/foreign/` is uproot's regression corpus and
contains files uproot wrote, so a failure there is a lead until the writer is
known. Only a file genuinely at fault goes in `gen/foreign/IGNORE.toml`, per file
and per invariant, with a reason.

Adding a file to either corpus: it must cover something no fixture and no listed
file does, and the reason goes in the README beside it. It goes in as a manifest
line. **No third-party file is ever committed**: not from either corpus, not
from `root/roottest/` (which is read in place), and not from rntuple-validation.
Those last two are LGPL-2.1 (`LICENSE` has the reasoning).
`tools/test_provenance.py` enforces the rule: every tracked `.root` must be the
output of a case, and no tracked file may be identical to a roottest file. If a
corpus file shows something a fixture should pin, write a generator that
reproduces it.

## Pull requests

- One subject per pull request. A correction and a new fixture are two.
- CI must be green. If a check cannot pass, say why in the description rather
  than adjusting the check.
- **Commit messages record what was *found*, not only what changed**: a
  version-dependent field, an erratum, a reader bug and how it surfaced. The git
  log is part of this project's record of how the format was reverse-engineered.
- Conventional-commit subjects (`fix(classes):`, `docs(container):`,
  `feat(ttree):`).

`PLAN.md` holds the structure, the scope decisions and what is left; `§8` records
how the work proceeded and `§9` lists every known gap. If you are looking for
something to do, those gaps are ranked by how much of the corpora they block.

One sub-plan is open, `PLAN-review.md`, which orders the response to the second
consistency review of 2026-09-24 (items V1–V44). A sub-plan is deleted when it
is discharged, as `PLAN-ttree.md`, `PLAN-writing.md`, the first `PLAN-review.md`
and `PLAN-corpus.md` were. Anything worth keeping moves into `PLAN.md` or
`spec/` first, and the git log keeps the rest. The last two answered the first
outside review and a survey of six external corpora; what remains of them is
`PLAN.md` §8.13 and §8.14.
