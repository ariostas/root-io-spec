# Provenance and sync procedure

RNTuple is the one ROOT format that already has a real specification, written and
maintained by the ROOT team. **This project does not fork it.**

`BinaryFormatSpecification.md` in this directory is a **verbatim tracked copy**,
byte for byte, of

```
root/tree/ntuple/doc/BinaryFormatSpecification.md
```

at the commit `root/` is pinned to. Nothing in this project edits it. Everything
this project has to say about it is in [ERRATA.md](ERRATA.md), where the document
and the code disagree, and [NOTES.md](NOTES.md), where the document is correct
but incomplete for someone implementing a reader.

## The copy

| | |
|---|---|
| Source commit | `1211eda93010f26710eafd527d1e66921bffdf8e` |
| Upstream path | `root/tree/ntuple/doc/BinaryFormatSpecification.md` |
| Last upstream change to that file | `6e179236815` — *[ntuple] Introduce feature flag 0 (nested deferred columns)*, 2026-05-04 |
| Document version, per its own title | 1.0.2.1 |
| Version the writer stamps into an anchor | **1.0.2.0** — see ERRATA 1 |
| Size | 73 872 bytes |

## Syncing

```sh
tools/sync_rntuple.py            # re-copy from the submodule
tools/sync_rntuple.py --check    # CI: fail if the tracked copy has drifted
```

`--check` runs in CI on every push. A failure means one of two things, and they
need opposite responses:

- **the submodule was bumped** and the copy is stale. Re-run without `--check`,
  then read the diff: it is exactly the set of upstream changes to audit, and
  nothing in it is ours. Update the table above, and re-check every ERRATA entry
  the diff touches — an erratum that upstream has fixed must be closed, not left
  standing;
- **the copy was edited in place.** Revert it. A correction belongs in ERRATA.md
  with a citation, not in the copy, or the copy stops being evidence of what
  upstream says.

The tool also asserts that the commit recorded above **is** the commit `root/` is
pinned to. Without that check a stale copy and a stale provenance note would agree
with each other and look correct.

## Why the other documents are not tracked

`root/tree/ntuple/doc/` holds six files. Only the format specification describes
bytes; the rest are design and tuning material that a reader does not need:

| File | Lines | Tracked |
|---|---|---|
| `BinaryFormatSpecification.md` | 1271 | **yes** |
| `Architecture.md` | 544 | no — the C++ class design, not the format |
| `SchemaEvolution.md` | 243 | no — cited from NOTES.md where it bears on reading |
| `Merging.md` | 92 | no |
| `tuning.md` | 88 | no |
| `README.md` | 79 | no |

Adding one is a one-line change to `DOCUMENTS` in `tools/sync_rntuple.py`.

## What this directory does not do

It does not restate the format in this project's house style, and it should not
start to. The value here is the **audit** — checking the upstream document against
`RNTupleSerialize.cxx` field by field, the way `spec/01-container/` and
`spec/02-serialization/` were checked against `TFile.cxx` and `TStreamerInfo.cxx`
— and feeding what that finds back upstream as pull requests rather than keeping
it here. ERRATA.md tracks the PR link per entry for exactly that reason.
