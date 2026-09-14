# Reference file generators

One directory per case, under `gen/cases/<group>/<case-id>/`:

| File | Purpose |
|---|---|
| `gen.C` | A ROOT macro defining `void gen(const char *out)` |
| `case.toml` | What the resulting file contains, including byte-level assertions |

```sh
tools/generate.py --check                        # verify, no ROOT needed
tools/generate.py                                # regenerate everything
tools/generate.py gen/cases/container/file-minimal   # one case
```

## Writing a case

Keep each case minimal and about **one** thing. A case that exercises five
features at once is hard to read a byte table against, which defeats the purpose.

Requirements:

- Deterministic. Fixed literal data; no `gRandom` without an explicit `SetSeed`.
- Small — single-digit kilobytes. Large cases are release artifacts, not commits.
- The macro MUST write to the path it is given and nothing else. `tools/generate.py`
  passes a repo-relative path, because `TFile` stores the path it was handed as the
  file's name and title; an absolute path would bake the checkout location into the
  fixture and shift every byte offset after the header.

## `case.toml`

`[[bytes]]` entries are the point of the whole exercise: they are written from the
same reading of the format as the tables in `spec/`, so a mistake in either shows up
as a failing assertion. Types are `i8`/`u8`/`i16`/`u16`/`i32`/`u32`/`i64`/`u64`/
`f32`/`f64` (all big-endian), `bytes` (a literal), and `string` (a counted string as
defined in `spec/00-conventions.md` §5.1).

Offsets are absolute within the file. Cite the specification section each group of
assertions corresponds to, so that a change to one prompts a look at the other.
