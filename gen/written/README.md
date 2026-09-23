# Files this project wrote

One directory per case, under `gen/written/<case>/`:

| File | Purpose |
|---|---|
| `build.py` | defines `build() -> bytes`, using `tools/rootwrite.py` |
| `case.toml` | what the resulting file contains, including byte-level assertions |
| `verify.C` | a ROOT macro `void verify(const char *path)` for gate 3 |

```sh
tools/check_write.py                  # gates 1 and 2; no ROOT needed
tools/check_write.py --root           # all three gates
tools/check_write.py --accept         # re-record data/written/ after a deliberate change
tools/check_write.py gen/written/objstring
```

These are **not** reference files in the sense the rest of `data/` is. Everything
under `data/` except `data/written/` was written by ROOT, so it is evidence about
the format. These files were written by `tools/rootwrite.py` from
`spec/06-writing/`, so they are evidence about this project's understanding of
the format. They are worth committing because of gate 3, where ROOT reads them
back.

As a result:

- **They are byte-reproducible**, unlike the ROOT-written fixtures, because a
  writer has no reason to consult a clock. `data/written/MANIFEST.sha256` is a
  plain sha256 of each file, not the normalized digest `tools/normalize.py`
  computes for the rest.
- **A change in `tools/rootwrite.py` shows up as a byte difference.** `--accept`
  re-records it, deliberately.

## Writing a case

Same discipline as `gen/cases/`: one case, one thing. Beyond that:

- `build()` must be deterministic and must take no arguments. Pass the file's own
  repo-relative path as its name, as `tools/generate.py` does for the ROOT-written
  fixtures, so the name a key carries does not depend on where the checkout is.
- `verify.C` prints a line starting with `FAIL` for every problem it finds and
  `VERIFY OK` at the end. `tools/check_write.py` fails the case on a `FAIL` line,
  on a missing `VERIFY OK`, on a non-zero exit, **and on anything that looks like a
  ROOT diagnostic**. A warning from `TStreamerInfo::BuildCheck` or a
  `CheckByteCount` complaint is the most informative signal a writer can get, so
  it must not scroll past unnoticed.
- Assert the container fields ROOT recovers (`GetEND`, `GetSeekFree`, `GetNkeys`,
  the key's `fSeekKey` and `fObjlen`) as well as the object's values. A file can
  hold the right object and still have wrong container fields.
- A diagnostic ROOT cannot avoid goes in `expected_diagnostics`, a list of
  substrings in `case.toml`, with the reason in the description. It must be about
  the **session** rather than the file. The only one so far is
  `no dictionary for class X is available`, which any class a writer invented
  produces. A declared line that ROOT stops printing fails the case, so the list
  cannot go stale, and no other diagnostic is tolerated.

## A case that updates a file

`reopen-add` and `reopen-reuse` build a **base** with `rootwrite` inside the same
`build()`, serialize it, and hand those bytes to `FileWriter.reopen`. Nothing else
is passed: no committed fixture is read, and the update is given only what a third
party opening the file would have. When such a case matches a ROOT-written one
byte for byte, this shows both that the base was byte-identical to ROOT's and that
the update reached ROOT's result from it.

The ROOT twin is an ordinary `gen/cases/` case whose `gen.C` creates the base,
closes it, and reopens the *same path* for `UPDATE`. Both file names then have to
be the **same length**, because four records store the file's name (the directory
record, the key list, the free record, and the repeated name) and two store their
own offsets. `data/container/reopened.root` against
`data/written/reopen-add.root` is 28 characters each; `reopen-gap` against
`reopen-reuse` is 30.

Make a hole with `"overwrite"`, not `Delete`: `TDirectoryFile::Delete` writes the
key list, the directory header and the free list before it returns
(`root/io/io/src/TDirectoryFile.cxx:736-738`), so the layout then depends on when
in the session the delete happened.
