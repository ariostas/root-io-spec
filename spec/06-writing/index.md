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

| # | Gate | What it proves | Needs |
|---|---|---|---|
| 1 | **Byte-exact** — the file matches its committed copy in `data/written/` bit for bit | a change in the writer is visible as a diff rather than as a silent behaviour change | Python only |
| 2 | **Read back** — `rootfile.py` decodes the file, and every applicable `Invariants` section holds | the two independent implementations agree, with the arrow reversed from the rest of the project | Python only |
| 3 | **ROOT reads it** — ROOT opens the file, returns the values that went in, and prints **no** warning | the procedure is right about ROOT, not just internally consistent | ROOT on `PATH` |

The numbers are the ones `tools/check_write.py` prints, so "gates 1 and 2" means
the two that need no ROOT.

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
| [Writing a file](WritingFiles.md) | The container: the header, the root directory record and its second write, subdirectories, keys, the key lists, the free list, where the end of the file is, and **reopening a file to add to it** |
| [Writing an object](WritingObjects.md) | Framing one object: the byte count, the version word, strings, the object map, compression, the `StreamerInfo` record, and **what has to be in it for a reader at another version of a class** |
| [Writing histograms](WritingHistograms.md) | `TH1F`, `TH1D`, `TH2F`, `TH2D` and `TProfile`, member by member, at the current class version |
| [Writing trees](WritingTrees.md) | A `TTree` of flat branches: the tree record, a branch, its leaf — fixed-width or a `TLeafC` string — its baskets, and flushing: more than one basket per branch, and the cluster ranges that come with it |
| [Element lists](ElementLists.md) | The streamer info of each of the thirty-five classes the other four documents need: every element, with every field |

Each is written as a numbered procedure, with a table per record or per class
giving every field and, for each, whether its value is **fixed** (only one value is
correct), **derived** (computed from something else, with the formula), or **free**
(any value in range; ROOT's own choice is given for reference, because matching it
makes a diff against a ROOT-written file readable).

A kind may carry a short qualifier, which narrows *who* requires the value rather
than adding a fourth kind:

| Qualifier | Means |
|---|---|
| **fixed by the object** | one value, but it comes from what is being written rather than from the format — a key's `fClassName`, say |
| **fixed by convention** | ROOT always writes one value and nothing reads it, so a violation is invisible; matching it is for diffs, not correctness |
| **fixed in practice** | one value unless the writer means something unusual by the field, and the unusual case changes how ROOT *interprets* the file rather than how it parses it |
| **derived, advisory** | computed, but no reader needs it — ROOT recomputes from the data instead |
| **free, with constraints** | a range or a rule rather than a single value, given beside it |

Anything marked plainly **fixed**, **derived** or **free** carries no qualifier and
means exactly what the paragraph above says.

### 3.1 What "the current version" means

**ROOT writes one version per class and it is not a choice.** Both places a version
word is emitted take `cl->GetClassVersion()` — the number compiled into the
*writing* process — and there is no argument, option or API that asks for an older
layout: objectwise at `root/io/io/src/TBufferFile.cxx:3162`, member-wise at
`root/io/io/src/TBufferFile.cxx:3192`.

So a read-and-write **upgrades**. Measured: a `TH1F` written by ROOT 5.28
(`uproot-issue64.root`, class versions `TH1F` 1, `TH1` 6, `TAxis` 9) read and
written straight back out by 6.40.04 comes out as `TH1F` 3, `TH1` 8, `TAxis` 10.
Nothing preserves the old layout, and nothing can be asked to.

That makes "the current version" precise but relative: it is the version of the
**ROOT that writes**, not a property of the format. A file from 5.28 has `TH1` 6
and is entirely conforming. These documents mean ROOT 6.40.04's numbers, which is
the release the repository pins, and `tools/check_versions.py` checks every table
here against `ClassDef` in it.

Four cases put something else in the version word, and a writer meets three of
them:

| Case | What is written | Cite |
|---|---|---|
| A **foreign** class — no `ClassDef` at all — whose version is `<= 1` | `0`, then a four-byte checksum | `root/io/io/src/TBufferFile.cxx:3163-3166` |
| A class whose `ClassDef` version is `<= 0` | that number; and a *forwarding* streamer writes no version word at all | [Forwarding streamers](../99-appendix/ForwardingStreamers.md) |
| A **member-wise** collection | the version with `0x4000` (`kStreamedMemberWise`) set | `root/io/io/src/TBufferFile.cxx:3203` |
| An **emulated** class — one the writing process has no dictionary for | the version **the file it was read from declared**, because the `TClass` is built from the streamer info as `new TClass(name, fClassVersion)` | `root/io/io/src/TStreamerInfo.cxx:928` |

`ROOT::TIOFeatures` is the first case and is unavoidable: every `TTree` and every
`TBranch` contains one
([Writing trees §3.2](WritingTrees.md#32-fiofeatures-is-the-one-foreign-class-a-tree-contains)).
The last case is why a file written today can carry a class version that is not
current for anything — the class has no current version, only the one its file
describes. Measured: `Head` in `uproot-issue-214.root` loads as an emulated class
whose `GetClassVersion()` is **2**, the number that file declares.

**And a copy is not a write.** `hadd` clones a tree by loading each basket's bytes
and copying them to the output untouched
(`root/tree/tree/src/TTreeCloner.cxx:753-761`), carrying the source file's streamer
infos across with them (`root/tree/tree/src/TTreeCloner.cxx:472`) — so records
produced by an older ROOT survive into a new file unchanged, at their original class
versions. A reader must therefore not infer a class
version from the file's `fVersion`, or from anything but the object's own version
word.

## 4. What is not specified

- **Earlier class versions.** ROOT does not write them either (§3.1), and there is
  no mechanism in the format to request one: the version word says what the writer
  emitted. The legacy layouts stay on the reading side, where files force them —
  [TBranch §13](../04-ttree/TBranch.md#13-class-versions) is the example.
- **Two writers on one file.** ROOT takes no lock a third party can see, and
  nothing in the format detects two sessions updating one file
  ([Writing a file §13.10](WritingFiles.md#1310-two-writers-one-file)). Updating a
  file that already exists **is** specified, as of 2026-09-21
  ([Writing a file §13](WritingFiles.md#13-updating-an-existing-file)); doing it
  concurrently is not.
- **Resolving a *collision* between a writer's class and a file's.** When an
  update's info for a class disagrees with the file's at the same version, ROOT
  keeps the file's and silently truncates what it writes
  ([Writing an object §8.5](WritingObjects.md#85-when-the-versions-collide-the-file-wins-and-members-are-lost)).
  This document specifies the two honest responses — bump the version, or refuse —
  and declines to specify the third. Everything else about **writing for a reader
  at another version** is specified
  ([Writing an object §8](WritingObjects.md#8-writing-for-a-reader-that-is-not-you)).
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
  say — the consequence is specified and the choice is not. Flushing is the largest
  example: [Writing trees §7](WritingTrees.md#7-more-than-one-basket-per-branch)
  specifies everything a flush *produces*, cluster ranges included, and states
  ROOT's own rule for when to do it without requiring it. The two values ROOT
  derives at its first flush, `fBasketSize` and `fAutoSave`, are inputs to this
  project's writer for the same reason.
- **The streamer-info element lists of any other class.**
  [Element lists](ElementLists.md) publishes the thirty-five a histogram, a profile,
  a graph, a flat tree or a bare `TObjString` needs, which was the largest omission here until 2026-09-18 and
  the one thing that made the writing layer unimplementable from the prose. It does
  not generalise: a `TH3`, a `TGraph2D` or a user-defined class needs infos
  that are not published, and there is no procedure for *deriving* an element list
  from a class definition — `TStreamerInfo::Build` is a dictionary walk, and this
  project specifies its output rather than reimplementing it. Two ways to obtain a
  list that is not published: `TFile::ShowStreamerInfo` on any ROOT-written file, or
  reading that file's `StreamerInfo` record with
  [Streamer information §12](../02-serialization/StreamerInfo.md#12-reading) — and
  **copying the record verbatim** into the file being written is legitimate, since
  a `StreamerInfo` record is self-contained.

## 5. A writer in one page

The order below is the whole of the container procedure, compressed; each step
links to where it is specified.

1. Reserve the first `fBEGIN` (100) bytes. Do not write the header yet — three of
   its fields are not known until step 8.
2. Write the **root directory record** at 100: a key whose class, name and title
   are the file's, followed by a `TDirectoryFile` payload whose three offsets are
   still zero.
3. Write each **data record**: stream the object into a buffer, compress it if the
   file says to, and write a key in front of it. A tree is many records, and its
   baskets come first because the tree stores their offsets
   ([Writing trees §2](WritingTrees.md#2-order-of-operations)).
4. Write a **subdirectory record** wherever one is created, which is ahead of
   everything it holds: the same payload with no name and title in front of it, a
   key whose class is `TDirectory`, and `fSeekKeys` still zero.
5. Write the **`StreamerInfo` record**, a `TList` of `TStreamerInfo` objects for
   the classes used in step 3 — [their element lists](ElementLists.md).
6. Write **one key list per directory**, the root's first: the count, then a copy
   of the key of each record that directory owns.
7. Write the **free list**: one entry for the gap that is the rest of the address
   space, since a file written once has no gaps in it — and a directory record
   never moves, so subdirectories do not add any.
8. Rewrite every directory record's payload — now that the key lists' positions
   and the file's end are known — and write the **header**.

[Writing a file](WritingFiles.md) is that list with the bytes in it.

## 6. Reference files

`data/written/` holds one file per procedure, produced by `tools/rootwrite.py` and
checked by `tools/check_write.py`. They are usable as test vectors in the same way
as the rest of `data/`, and they are the only files in the repository this project
wrote rather than ROOT — which is exactly why each carries a note saying so.
