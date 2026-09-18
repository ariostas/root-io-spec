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
under `data/` except `data/written/` was written by ROOT, which is what makes it
evidence about the format. These were written by `tools/rootwrite.py` from
`spec/06-writing/`, so they are evidence about *this project's understanding* of
the format — and the thing that makes them worth committing is gate 3, where ROOT
reads them back.

Two consequences:

- **They are byte-reproducible**, unlike the ROOT-written fixtures, because a
  writer has no reason to consult a clock. `data/written/MANIFEST.sha256` is a
  plain sha256 of each file, not the normalized digest `tools/normalize.py`
  computes for the rest.
- **A change in `tools/rootwrite.py` shows up as a byte difference**, and that is
  the point: `--accept` is the deliberate act of re-recording one.

## Writing a case

Same discipline as `gen/cases/`: one case, one thing. Beyond that:

- `build()` must be deterministic and must take no arguments. Pass the file's own
  repo-relative path as its name, as `tools/generate.py` does for the ROOT-written
  fixtures, so the name a key carries does not depend on where the checkout is.
- `verify.C` prints a line starting with `FAIL` for every problem it finds and
  `VERIFY OK` at the end. `tools/check_write.py` fails the case on a `FAIL` line,
  on a missing `VERIFY OK`, on a non-zero exit, **and on anything that looks like a
  ROOT diagnostic** — a warning from `TStreamerInfo::BuildCheck` or a
  `CheckByteCount` complaint is the most informative thing that can happen to a
  writer, so it must not be allowed to scroll past.
- Assert the container fields ROOT recovers (`GetEND`, `GetSeekFree`, `GetNkeys`,
  the key's `fSeekKey` and `fObjlen`) as well as the object's values. A file can
  hold the right object and still be wrong about itself.
