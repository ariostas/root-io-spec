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
PYTHONPATH=. zensical build --clean --strict          # site; fails on broken links
PYTHONPATH=tools python -m unittest discover -s tools -p "test_*.py"
```

Regenerating fixtures needs ROOT on PATH, matching the pinned submodule:

```sh
tools/generate.py                                      # all cases
tools/generate.py gen/cases/container/file-minimal     # one case
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

**`data/`** — the generated reference files, committed, plus `MANIFEST.sha256`.

**`tools/`** — checkers, and `rootfile.py`, a pure-Python reader of the header,
record chain, directory records, key lists, the buffer framing layer and the
StreamerInfo record. It is deliberately an independent implementation of what
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
