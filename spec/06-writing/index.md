# Writing ROOT files

Every other layer of this specification answers the reader's question: these bytes
are here, what do they mean. This layer answers the writer's: I have a histogram
and a tree, which bytes do I emit, in what order, and what will ROOT complain
about.

It is a smaller layer than the reading side, deliberately, and §3 says why.

## 1. Why it is separate

The reading documents already contain almost every fact a writer needs — a field's
offset is the same fact whichever direction you are going — and each of them ends
with an `Invariants` section, which is a checklist a writer can run against its own
output.

That turned out to be necessary and not sufficient, for three reasons:

1. **Order is not a property of any byte.** A file's header cannot be written until
   the free list is placed, the free list cannot be placed until every record is,
   and the root directory record has to be written twice — once when the file is
   created and once at the end, because three of its fields are not known until
   then. No amount of reading a finished file recovers that order;
   [Writing a file](WritingFiles.md) states it.
2. **A reader may be liberal where a writer may not.** A reader is told a byte
   count is a lower bound, that `fUnits` is informational, that the header's
   padding is unspecified. A writer that treats all three as free produces a file
   ROOT reads and another reader rejects. Where the two differ, this layer says so.
3. **The class layouts a writer needs are a short list, and it is not the same
   list.** A reader has to cope with every class version any file carries, back to
   ROOT 3. A writer chooses, so it needs exactly one version of each class it
   emits — the current one — and needs it completely, including the members ROOT's
   own constructors set to values that look arbitrary.

## 2. The conformance test

A writing procedure is only as good as what happens when ROOT opens the result, so
that is the test, and it is executable. `tools/rootwrite.py` is a pure-Python
writer built from these documents alone — not from ROOT's writing code, and not
from `tools/rootfile.py`, which is this project's reader — and
`tools/check_write.py` puts every file it produces through three gates:

| Gate | What it proves | Needs |
|---|---|---|
| **Read back** — `rootfile.py` decodes the file, and every applicable `Invariants` section holds | the two independent implementations agree, with the arrow reversed from the rest of the project | Python only |
| **Byte-exact** — the file matches its committed copy in `data/written/` bit for bit | a change in the writer is visible as a diff rather than as a silent behaviour change | Python only |
| **ROOT reads it** — ROOT opens the file, returns the values that went in, and prints **no** warning | the procedure is right about ROOT, not just internally consistent | ROOT on `PATH` |

The third gate is the one that finds errors, and the "no warning" half of it is not
decoration: ROOT checks a byte count against what it consumed, and compares a
class version and a checksum in the file against the class it has compiled in. A
writer that gets any of those wrong is told so, by name, on the terminal.

**`data/written/` is byte-reproducible**, which the rest of `data/` is not. Every
fixture ROOT writes carries a wall-clock timestamp in each key and a fresh UUID per
file, so the reference files are compared by a normalized digest
(`tools/normalize.py`). A writer has no such excuse: `rootwrite.py` takes the
timestamp and the UUID as inputs, and the files here are compared byte for byte
with a plain `sha256`.

## 3. What is specified

| Document | Covers |
|---|---|
| [Writing a file](WritingFiles.md) | The container: the header, the root directory record and its second write, keys, the key list, the free list, and where the end of the file is |
| `06-writing/WritingObjects.md` | Framing one object: the byte count, the version word, strings, the object map, compression, and the `StreamerInfo` record |
| `06-writing/WritingHistograms.md` | `TH1F` and `TH1D`, member by member, at the current class version |
| `06-writing/WritingTrees.md` | A `TTree` of flat branches: the tree record, a branch, its leaf, and its baskets |

Each is written as a numbered procedure, with a table per record or per class
giving every field and, for each, whether its value is **fixed** (only one value is
correct), **derived** (computed from something else, with the formula), or **free**
(any value in range; ROOT's own choice is given for reference, because matching it
makes a diff against a ROOT-written file readable).

## 4. What is not specified

- **Earlier class versions.** A writer picks its own, and nothing benefits from
  writing a layout ROOT last produced in 2008. The legacy layouts stay on the
  reading side, where files force them —
  [TBranch §13](../04-ttree/TBranch.md#13-class-versions) is the example.
- **Updating an existing file.** Everything here creates a file from nothing. An
  update has to reuse free space, rewrite a key list in place, and bump a key's
  cycle number; those mechanisms are specified from the reading side
  ([Free segments](../01-container/FreeSegments.md),
  [Directories §6](../01-container/Directory.md#6-key-lists)) and a writer that
  only ever creates files never meets them.
- **Writing a split `TBranchElement`.** Reading one is specified
  ([Split branches](../04-ttree/TBranchElement.md)); producing one means
  reimplementing ROOT's splitting decisions, which
  [Splitting](../04-ttree/Splitting.md) documents as *ROOT's* decisions rather than
  the format's. A flat tree, or one branch holding a whole object unsplit, is what
  a writer needs and is what §3 covers.
- **RNTuple.** ROOT's own specification is tracked here
  ([RNTuple](../05-rntuple/index.md)) and it is written for both directions.
- **Policy.** Basket sizes, when to flush, how many entries per cluster, which
  compression setting: ROOT's choices, and a writer's to make differently. Where a
  choice has a *format* consequence — a basket over 16 MiB is split into blocks,
  say — the consequence is specified and the choice is not.

## 5. A writer in one page

The order below is the whole of the container procedure, compressed; each step
links to where it is specified.

1. Reserve the first `fBEGIN` (100) bytes. Do not write the header yet — three of
   its fields are not known until step 7.
2. Write the **root directory record** at 100: a key whose class, name and title
   are the file's, followed by a `TDirectoryFile` payload whose three offsets are
   still zero.
3. Write each **data record**: stream the object into a buffer, compress it if the
   file says to, and write a key in front of it.
4. Write the **`StreamerInfo` record**, a `TList` of `TStreamerInfo` objects for
   the classes used in step 3.
5. Write the **key list**: the count, then a copy of each data record's key.
6. Write the **free list**: one entry for the gap that is the rest of the address
   space, since a file written once has no gaps in it.
7. Rewrite the root directory record's payload — now that the key list's position
   and the file's end are known — and write the **header**.

[Writing a file](WritingFiles.md) is that list with the bytes in it.

## 6. Reference files

`data/written/` holds one file per procedure, produced by `tools/rootwrite.py` and
checked by `tools/check_write.py`. They are usable as test vectors in the same way
as the rest of `data/`, and they are the only files in the repository this project
wrote rather than ROOT — which is exactly why each carries a note saying so.
