# Implementing a reader

The specification is organised by layer, which suits describing the format but
not building a reader. This page presents the same material as a work order:
eight milestones, each a state in which something useful works, with the
documents to read, the reference files that test it, and the invariants worth
checking at that point.

It assumes you want to read files written by ROOT 6, and to cope with files
written by ROOT 4 and 5; see [Conventions §1](../00-conventions.md#1-status-of-this-specification)
for what is in scope.

[Bootstrap classes](Bootstrap.md) covers milestone 3 in more detail: the classes
you must hardcode, in dependency order. [Pitfalls](Pitfalls.md) lists things
that have cost implementers time; read it once now, and again when something
does not add up.

## 1. Open a file and list what is in it

*Working state: the equivalent of `TFile::Map()`. No object is decoded yet.
Almost everything below depends on this milestone and nothing else.*

| Read | For |
|---|---|
| [Conventions](../00-conventions.md) | Byte order, the primitive widths, the four string encodings |
| [File header](../01-container/FileHeader.md) | The 64/100-byte header, and the `+1000000` flag that widens three fields — `fEND`, `fSeekFree` and `fSeekInfo` |
| [Records and keys](../01-container/Record.md) | The key layout, `fNbytes`/`fObjlen`/`fKeylen`, cycles, the record chain |
| [Directories and key lists](../01-container/Directory.md) | The root directory record, nested directories, the list of keys |
| [Free segments](../01-container/FreeSegments.md) | Only if you intend to write, or to explain gaps |

Implement: read the header, walk the record chain from `fBEGIN`, read the key of
each record, and read the key list a directory points at. Recognise directory
records **structurally**, by `fSeekDir`, `fSeekParent` and `fSeekKeys`, and not by
class name, because a `TFile` subclass is still a directory
([Directories §6.2](../01-container/Directory.md#62-the-key-list-record-cannot-be-identified-from-its-key)).
Step between key-list entries by the number of bytes each one parses to, not by
its `fKeylen`: the two differ in files from ROOT 5.32 and earlier, and a subdirectory
there may be listed as `TDirectoryFile` rather than `TDirectory`
([Directories §6.5](../01-container/Directory.md#65-an-images-length-is-what-it-parses-to-never-its-fkeylen)).

Test it with `container/file-minimal`, `container/directories`,
`container/cycles`, `container/empty-directory` and `container/gap`, then check
the invariants of all four documents above.

## 2. Decompress

*Working state: you can obtain the bytes of any object, whatever the file's
compression settings.*

[Compression](../01-container/Compression.md) is a short document and almost all
of it matters. Two things commonly go wrong:

- **the test for "is this compressed" is an inequality**, `fObjlen > fNbytes - fKeylen`,
  not a difference between the two ([§1.1](../01-container/Compression.md#11-why-the-test-is-an-inequality));
- a payload may be **several blocks**, each with its own 9-byte header, and you
  concatenate them ([§7](../01-container/Compression.md#7-multi-block-payloads)).

`container/compress-zlib`, `-lzma`, `-lz4`, `-zstd` and
`container/compress-none-fallback` cover the four algorithms and the case where
ROOT gives up and stores the payload raw. Old files may use the `CS` magic, which
is raw DEFLATE and needs no new algorithm
([§3.1](../01-container/Compression.md#31-cs-is-raw-deflate-and-zl-is-zlib-wrapped)).

## 3. Read the streamer information

*Working state: you hold, for every class the file contains, the member list ROOT
recorded for it. Nothing else can be decoded yet. Reading that list is itself a
decoding problem, and this milestone is the bootstrap.*

[Streamer information](../02-serialization/StreamerInfo.md) gives the byte layout
of the record and of every class inside it, because those classes cannot be read
from the information they carry.
[Bootstrap classes](Bootstrap.md) gives the same set as an ordered checklist and
is the document to work from here. It also says what group A does **not**
include, which covers most of what a first attempt implements unnecessarily.

You need, in this order: `TObject` and `TNamed`, `TString`, `TList`, `TObjArray`,
`TStreamerInfo`, `TStreamerElement` and its eleven subclasses. `serialization/streamer-info`
and `serialization/object-tags` are the fixtures. The second contains a class
back-reference between two infos, the first place where the buffer's object map
matters.

An empty list means a valid file that needs no streamer info, not a damaged one
([§3.2](../02-serialization/StreamerInfo.md#3-what-the-list-contains)).

## 4. Decode an arbitrary object

*Working state: every ordinary class in the file, including user-defined ones.
Most of the value is here: ~90% of what a file contains needs no per-class
code.*

| Read | For |
|---|---|
| [Buffer framing](../02-serialization/Buffer.md) | Byte counts, version words, class records, object references, the `TObject` base |
| [Streamer-driven reading](../02-serialization/StreamerDriven.md) | The normative element loop |
| [Element types](../02-serialization/ElementTypes.md) | Every type code → exact bytes, including `Double32_t` |
| [Collections](../02-serialization/Collections.md) | STL containers, object-wise and member-wise, `TClonesArray` |
| [Schema evolution](../02-serialization/SchemaEvolution.md) | Choosing an info by version or checksum, and what class version 0 means |
| [References](../02-serialization/References.md) | `TRef`, `TRefArray`, and the extra word on a referenced `TObject` |

Fixtures, roughly in the order they become useful: `serialization/basic-types`,
`serialization/objects`, `serialization/arrays`, `serialization/pointer-forms`,
`serialization/element-types`, `serialization/collections`,
`serialization/collection-forms`, `serialization/pointer-collection`,
`serialization/pairs`,
`serialization/clones-array`, `serialization/version-zero`,
`serialization/schema-rules`, `serialization/references`,
`serialization/ref-variants`, `serialization/double32`.

Implement first the invariant that catches everything else: **an object ends
where its byte count says**. A decode that stops anywhere else is a bug in
your reader, in the specification, or in the file, in that order of likelihood
([Buffer framing §9](../02-serialization/Buffer.md#9-invariants)).

## 5. The classes the streamer info gets wrong

*Working state: the previous milestone stops producing plausible garbage.*

None of these three lists can be derived from a file:

- [Bootstrap classes §5](Bootstrap.md#5-group-b-the-classes-streamer-driven-reading-gets-wrong)
  — the classes to hardcode, with the symptom of skipping each one;
- [Hand-written streamers](HandWrittenStreamers.md) — every ROOT class whose
  `Streamer` is written by hand, generated from ROOT's source, sorted by whether
  it matters;
- [Forwarding streamers](ForwardingStreamers.md) — the classes whose generated
  `Streamer` writes only their base classes.

The layouts themselves are documented where the behaviour arises rather than in
one place ([Standard classes](../03-classes/index.md) maps them). The ones a
physics file is most likely to need are
[`TArray*`](../03-classes/TArray.md), [`TString`](../00-conventions.md#51-counted-string),
[`TList` and `TObjArray`](../02-serialization/StreamerInfo.md#4-tlist),
[`TClonesArray`](../02-serialization/Collections.md#12-tclonesarray) and
[`TMatrixTSym`](../03-classes/Matrix.md). The last matters because a covariance
matrix is symmetric, and because it is the only class whose bytes continue past
its own byte count.

If the files you care about are workspaces, plots or fit results, also do
[RooFit](../03-classes/RooFit.md) early: five classes, two of which every
`RooRealVar` reaches. Until those two are read, nothing else in such a file can
be.

## 6. Read an unsplit tree

*Working state: values out of a `TTree` whose branches hold whole objects or
plain leaves. That covers every tree written before splitting, and many written
since.*

| Read | For |
|---|---|
| [The tree record](../04-ttree/TTree.md) | Finding trees (through the base-class chain, not the class name), the branch list, clusters |
| [Branches](../04-ttree/TBranch.md) | The three basket arrays, and the basket that lives inside the tree record |
| [Leaves](../04-ttree/TLeaf.md) | What a leaf contributes to an entry, counts, `TLeafC` |
| [TBasket](../04-ttree/TBasket.md) | The basket record, entry offsets, and the flag byte |
| [Reading entries §1–4](../04-ttree/ReadingEntries.md#1-locating-the-entry) | Entry number → basket → byte range |

`ttree/tree`, `ttree/branch`, `ttree/leaf`, `ttree/leaf-forms`, `ttree/basket`,
`ttree/basket-compressed`, `ttree/basket-embedded`, `ttree/clusters`.
Handle `ttree/basket-embedded` early: a tree's **last basket is often inside the
tree record itself**, not a record of its own, and a reader that does not
implement that misses the tail of every branch it touches
([TBasket §4.1](../04-ttree/TBasket.md#4-the-flag-byte-and-the-two-shapes-of-a-basket)).

## 7. Read a split tree

*Working state: a modern physics file.*

[Split branches](../04-ttree/TBranchElement.md) and
[Splitting](../04-ttree/Splitting.md) describe the branch tree and what each
branch holds; [Split branches §8](../04-ttree/TBranchElement.md#8-the-read-procedure-is-selected-by-four-fields-not-one)
gives the eleven conditions and the four fields that choose between them:
`fType`, `fID`, `fSplitLevel` and `fStreamerType`, not `fType` alone. The
conditions select ten distinct procedures, since `ReadLeavesMember` serves two
of them.

There is one fixture per shape: `ttree/split-object`, `split-unsplit`,
`split-naming`, `split-nested`, `split-counter`, `split-clones`,
`split-stl-toplevel`, `split-ptr-collection`, `split-bitset`, `split-double32`.

The most useful check here is
[Reading entries invariant 5](../04-ttree/ReadingEntries.md#8-invariants): the
bytes an entry occupies equal the bytes its decoding consumes. Without it, you
only know that the values look plausible, not that they are right.

## 8. The rest

- [Auxiliary classes](../04-ttree/Auxiliary.md) — `TTreeIndex`, friends,
  `TBranchRef`, entry lists, `TNtuple`, `TChain`. Needed only if the files you
  read use them; `ttree/tree-index`, `tree-friend`, `tree-entrylist`,
  `tree-branchref` and `tree-ntuple` cover them.
- [RNTuple](../05-rntuple/index.md) — a different format in the same container.
  Read ROOT's own specification, which this project tracks verbatim, together
  with [the errata](../05-rntuple/ERRATA.md): ten places where it and ROOT's code
  disagree. One of them has already made two readers in the same repository
  diverge.

## 9. How to know you are right

Four checks, in increasing order of strength:

1. **The byte assertions.** Every reference file comes with a `case.toml` listing
   offsets, types and expected values. They can be checked with only the standard
   library (`tools/check_bytes.py` in this repository is about seventy lines), so
   they work as test vectors for an implementation in any language.
2. **The invariants.** Every document ends with a numbered `Invariants` section.
   They are the cheapest way to find a misreading: a file that violates one is
   either being read wrongly or is not a ROOT file.
3. **Consumption.** Decode an object and compare where you stopped against the
   byte count, and an entry against its span in the basket. Most
   misunderstandings show up here as an offset that is wrong by two or four bytes.
4. **Files you did not choose.** This project's two corpora, 252 files spanning
   ROOT 2.24/00 to 6.38/00, found errors in this specification that its own
   fixtures did not, because a fixture tests what its author already understood.
   A failure means different things in the two: the 72 files of `gen/cern/` were
   published by the ROOT team, so a failure there is evidence. The 180 of
   `gen/foreign/` come almost all from uproot's regression suite and include
   files uproot itself wrote, so a failure there is a lead to be traced to a writer.

## 10. What you can leave out

Deliberately, and without losing the ability to read ordinary files:

- **Writing a file of your own**, if you only need to read. The `Invariants`
  sections state what a conforming file satisfies, collected for a writer in
  [A writer's invariants](WriterInvariants.md). If you do need to write,
  [Writing](../06-writing/index.md) gives the procedures (the container, an
  object and its streamer info, `TH1F`/`TH1D` and a flat `TTree`) with every
  field marked fixed, derived or free.
- **Class layouts older than ROOT 4.** A file written before streamer
  information existed has none, and its classes can only be read from
  hardcoded per-version layouts this specification does not give
  ([Streamer-driven reading §6](../02-serialization/StreamerDriven.md#6-when-there-is-no-usable-streamer-info)).
- **`TBranch` below class version 10**, whose legacy layout is described but not
  fully specified ([Branches §13](../04-ttree/TBranch.md#13-class-versions)).
- **RooFit, `TGeo*` internals, EVE and the GUI classes.** They do appear in
  files, but reading them is a per-experiment concern rather than a format one.
