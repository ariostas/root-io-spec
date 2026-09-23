# Bootstrap classes

The classes a reader MUST hardcode, why each one is on the list, and where its
layout is specified. This is the list
[Streamer information §1](../02-serialization/StreamerInfo.md#1-the-bootstrap-problem)
promises.

Nothing here is new. This page is an index and a work order. The specification
is organised by layer, which suits describing a format but does not answer "what
do I have to write before anything works?"

## 1. Two different reasons to hardcode a class

The two are often conflated, and the consequences differ.

**A. The class is what the description is made of.** `TList`, `TObjArray`,
`TStreamerInfo`, `TStreamerElement` and its subclasses hold the file's
description of every other class. To read that description you must already be
able to read these, and no ordering of the file can avoid that. This is the
bootstrap problem proper, and the set is closed; it is listed in §3 below.

**B. The class's recorded streamer info is wrong.** Its `Streamer` is
hand-written and writes something other than its member list, but the info is in
the file anyway and nothing marks it
([Streamer-driven reading §7](../02-serialization/StreamerDriven.md#7-when-the-streamer-info-does-not-describe-the-bytes)).
Examples are `TClonesArray`, `TArray*` and `TRef`. **This set is not closed**;
see §6.

A reader that skips group A cannot start. A reader that skips group B starts and
runs, but gets the classes it meets wrong. The error shows up as a byte-count
mismatch on the first object of the class, not as corrupt values
([Streamer-driven reading §7](../02-serialization/StreamerDriven.md#7-when-the-streamer-info-does-not-describe-the-bytes)).

## 2. The start-up sequence

In dependency order. No step can be read until every step above it works.

| # | What | Needs | Specified in |
|---|---|---|---|
| 1 | The file header | nothing — raw bytes at offset 0 | [File header](../01-container/FileHeader.md) |
| 2 | The record chain and `TKey` | 1 | [Records and keys](../01-container/Record.md) |
| 3 | Decompression | 2 | [Compression](../01-container/Compression.md) |
| 4 | Byte counts, version words, class records, object slots, the map | 3 | [Buffer framing](../02-serialization/Buffer.md) |
| 5 | The `TObject` base and the counted string | 4 | [Buffer framing §7](../02-serialization/Buffer.md#7-the-tobject-base), [Conventions §5.1](../00-conventions.md#51-counted-string) |
| 6 | `TList` → `TStreamerInfo` → `TObjArray` → `TStreamerElement` | 5 | [Streamer information](../02-serialization/StreamerInfo.md) §4–§8 |
| 7 | Every other class | 6 | [Streamer-driven reading](../02-serialization/StreamerDriven.md) |
| 8 | The classes step 7 gets wrong | 7 | §5 below |

Steps 1–6 are the hardcoded part of a reader and are finite. Step 7 does not
grow as ROOT does: it reads classes this specification does not mention,
including every class a user defines.

> The order matters in one non-obvious way. Step 4 must include **the map**, the
> position table that back-references index into
> ([Buffer framing §5.2](../02-serialization/Buffer.md#52-a-class-back-reference),
> [§6.3](../02-serialization/Buffer.md#63-the-map-is-per-buffer)), and not only
> byte counts. The `StreamerInfo` record names its class once and refers back to
> it after that, so a reader that defers the map cannot read a list of more than
> one info. In `ttree/split-object`, whose list has 21 entries, the first has the
> class record `ff ff ff ff` and the name, and the twenty after it have the
> reference `80 00 00 5b` and no name.

## 3. Group A: needed before anything can be read

Six classes, plus the element subclasses. §8 lists twelve of those and a reader
needs eleven: `TStreamerArtificial` is never written to a file, and is declared
`ClassDefOverride(TStreamerArtificial, 0)` so that it cannot be
([Schema evolution §5](../02-serialization/SchemaEvolution.md#5-codes-that-cannot-appear-in-a-file)).

| Class | Role in the record | Layout |
|---|---|---|
| `TList` | the `StreamerInfo` record is one | [§4](../02-serialization/StreamerInfo.md#4-tlist) |
| `TObjArray` | `TStreamerInfo::fElements` is one | [§5](../02-serialization/StreamerInfo.md#5-tobjarray) |
| `TStreamerInfo` | one per described class | [§6](../02-serialization/StreamerInfo.md#6-tstreamerinfo) |
| `TStreamerElement` | the base of every element | [§7](../02-serialization/StreamerInfo.md#7-tstreamerelement) |
| the eleven writable `TStreamerElement` subclasses | each adds its own tail | [§8](../02-serialization/StreamerInfo.md#8-the-element-subclasses) |
| `TObject` | a base of all of the above | [Buffer framing §7](../02-serialization/Buffer.md#7-the-tobject-base) |
| `TNamed` | both `TStreamerInfo` and `TStreamerElement` derive from it (`root/core/meta/inc/TVirtualStreamerInfo.h:44`, `root/core/meta/inc/TStreamerElement.h:25`) | `TObject`, then two counted strings |

`TString` is not separately listed because at this level it is only the counted
string of [Conventions §5.1](../00-conventions.md#51-counted-string); it has no
framing of its own.

> **A file may contain streamer infos for these classes, and a reader MUST NOT
> use them.** `TagStreamerInfo` adds a class whenever an object of it is written
> through `WriteClassBuffer`, so any file written to after its first
> `StreamerInfo` record can have entries for `TList`, `TNamed`,
> `TStreamerElement` and the rest
> ([§3.3](../02-serialization/StreamerInfo.md#33-the-bootstrap-classes-may-describe-themselves)).
> For a class with a hand-written streamer those entries do not describe the
> bytes; `TString`'s lists no members at all.

## 4. What group A does *not* include

The set looks larger than it is.

`THashList` appears wherever a `TList` may. It derives from `TList`
(`root/core/cont/inc/THashList.h:34`) and adds nothing to the stream
([§4](../02-serialization/StreamerInfo.md#4-tlist)), so it needs only a name in
a dispatch table.

The `listOfRules` entry of the `StreamerInfo` record is a `TList` of
`TObjString`. A reader that does not implement schema-evolution rules does not
need `TObjString` at all: the entry is skipped by its byte count. Dispatching on
the class name rather than on position makes that safe
([§3.1](../02-serialization/StreamerInfo.md#31-listofrules)).

An empty `StreamerInfo` list means a valid file that needs no streamer info,
not a damaged one ([§3.2](../02-serialization/StreamerInfo.md#32-an-empty-list-is-meaningful)).

## 5. Group B: the classes streamer-driven reading gets wrong

Hardcode these too. A reader is already running by the time it meets them, so
they can be added one at a time as files require. The index is in
[Standard classes](../03-classes/index.md). This table is that set and more, as a
checklist with what goes wrong if each is skipped. It adds the classes a reader
meets through the container and the tree rather than as objects of their own,
among them `TBasket` and `TBranchClones`.

| Class | Symptom of not hardcoding it | Layout |
|---|---|---|
| `TString` as a member | reads a byte count that is the string's first four bytes | [Conventions §5.1](../00-conventions.md#51-counted-string) |
| `TList`, `THashList` | reads a `TSeqCollection` base, then a `TCollection` base, neither of which is there | [Streamer information §4](../02-serialization/StreamerInfo.md#4-tlist) |
| `TObjArray` | the same, plus the entry loop differs | [§5](../02-serialization/StreamerInfo.md#5-tobjarray) |
| `TClonesArray` | two encodings, and `kBypassStreamer` selects between them | [Collections §12](../02-serialization/Collections.md#12-tclonesarray) |
| `TArray*` | expects a byte count and version word; there are neither | [TArray](../03-classes/TArray.md) |
| `TRef`, `TRefArray` | a referenced `TObject` writes two extra bytes and the reader desynchronises by two | [References §3](../02-serialization/References.md#3-tref), [§4](../02-serialization/References.md#4-trefarray) |
| `TDatime` | expects framing; it is four bare bytes | [Records and keys §3.7](../01-container/Record.md#37-fdatime) |
| `std::string` | no file contains an info for it at all | [Collections §10](../02-serialization/Collections.md#10-stdstring) |
| `TCollection`, `TSeqCollection` | reachable only through the incorrect infos above; a reader that never follows those never meets them | not specified, deliberately |
| `TBranchClones` | no streamer info at all; derives from `TBranch` and streams ten of its fields individually instead of a base | [TBranchElement §13](../04-ttree/TBranchElement.md) |
| `TBasket` | no streamer info at all, and its fields sit inside the key | [TBasket](../04-ttree/TBasket.md) |
| `TTreeIndex` | no streamer info at all, and its arrays carry no is-present flag | [Auxiliary classes §2](../04-ttree/Auxiliary.md#2-ttreeindex-the-one-class-with-no-streamer-info) |
| `TStringLong` | appears as element code 62, so the reader looks for a frame; no file carries an info for it either | [Conventions §5.1.1](../00-conventions.md#511-tstringlong-the-same-idea-with-a-four-byte-count) |
| `TQObject` | its `kBase` element occupies zero bytes, and a modern file has no info for it at all; following the element desynchronises immediately. Every `TPad` and `TCanvas` has one | [Streamer-driven reading §4.4](../02-serialization/StreamerDriven.md), [Canvas §3](../03-classes/Canvas.md) |
| `TCanvas` | seven trailing bytes its info does not mention, five of them `fBits` flags | [Canvas](../03-classes/Canvas.md) |
| `TMap`, `TExMap`, `TBtree` | pointer-streamed pairs, a forced hash bit, and a `TCollection` frame reached through a class that adds nothing | [TMap, TExMap and TBtree](../03-classes/Containers.md) |
| `TMatrixTSym` | the elements sit past the byte count and the file has no info for the class, only for its base. A reader that stops where the byte count says loses the whole matrix and reports nothing | [Matrices and vectors](../03-classes/Matrix.md) |
| `RooRealVar`, `RooLinkedList`, `RooAbsBinning`, `RooRefArray`, `RooCategory` | a `RooRealVar` has no info in the file at all; a `RooLinkedList`'s info names a member that is not on disk and omits the object slots that are, and the object has no byte count to catch it | [RooFit](../03-classes/RooFit.md) |
| `TFile`, `TDirectoryFile` | the container rather than objects in it | [Directories](../01-container/Directory.md) |
| `TSeqCollection`, `THashList`, `TVirtualPerfStats` | their generated `Streamer` writes only their bases: no version word, no byte count, no members. Following their streamer info reads a frame that is not there | [Forwarding streamers](ForwardingStreamers.md) |

Two entries are on the list for the opposite of the usual reason. `TBasket` and
`TTreeIndex` have no recorded streamer info, so a reader cannot silently follow a
wrong one; it cannot proceed at all, which is easier to diagnose.
`TMatrixTSym` combines both problems: it has no info of its own, and its byte
count makes stopping too early look correct
([Buffer framing §2.4](../02-serialization/Buffer.md#24-an-object-may-be-longer-than-its-byte-count-says)).

## 6. The list cannot be closed

> **A user-defined class can have a hand-written `Streamer` too, and nothing in
> the file says so.**

[Standard classes](../03-classes/index.md) opens by saying that streamer-driven
reading is enough for "every class a user defines". That is the common case, not
a rule. `ClassDef` generates a `Streamer` that calls `ReadClassBuffer`, so a
class that uses the generated body is streamer-info driven whatever else it does.
But a class may replace that body, and experiment frameworks do.

KM3NeT's Jpp DAQ classes are the example in `gen/foreign/`.
`KM3NETDAQ::JDAQPreamble`'s recorded info lists two base classes: a
`JDAQAbstractPreamble` holding two `Int_t`, which is fourteen bytes when framed,
and a `TObject`. Its split branch's entry is eight bytes:

```
00 00 00 57  00 00 07 d1        length 87, type 2001
```

These are the base's two `Int_t`, raw, with no byte count, no version word and
no `TObject`. Nothing in the entry would let a reader work that out. The control
case is in the same tree of the same file: `KM3NETDAQ::JDAQSummarysliceHeader` is
also a `kBase` element on an `fType` 0 branch with `fStreamerType` 0, and it is
framed three levels deep and decodes to the byte.

Hardcoding this list is therefore not enough. The practical rule for an
implementer is:

1. Hardcode group A, or nothing works.
2. Hardcode group B, or ROOT's own objects decode wrongly.
3. **Check the byte counts**, and report a mismatch rather than guessing
   ([Streamer-driven reading §8](../02-serialization/StreamerDriven.md#8-resynchronisation)).
   For an unknown class this is the only defence, so the check is worth
   implementing even where it looks redundant.

`tools/rootfile.py` holds its group-B list as `CUSTOM_STREAMER`, and
`gen/foreign/IGNORE.toml` extends it per file with classes diagnosed this way.
Together they are what §7 of the streamer-driven document means by "it has to
know, from a list".

## 7. Checking a bootstrap implementation

The fixtures in `data/` are usable as test vectors with no ROOT and no
third-party packages ([Conventions §8](../00-conventions.md#8-reference-files)),
and the ones below exercise the steps of §2 in order.

| Step | Case |
|---|---|
| 1–2 | `container/file-minimal`, the shortest complete file; then `container/gap` and `container/cycles` for the chain |
| 3 | `container/compress-zlib` and its siblings, and `container/compress-none-fallback` for the case where compression is asked for and not applied |
| 4 | `serialization/basic-types`, then `serialization/object-tags` for the buffer map |
| 5 | `serialization/objects` |
| 6 | `serialization/streamer-info`, then `serialization/version-zero` for the case a reader cannot resolve from the bytes alone |
| 7 | `serialization/arrays` and `serialization/objects` |
| 8 | `serialization/collections`, `serialization/clones-array`, `serialization/references`, `classes/tarray` |

A reader that passes step 6 on a file with more than one streamer info has
necessarily implemented the map (the trap described in §2).

## 8. Reference files

This document has no fixture of its own: every claim in it is specified and
demonstrated in the document it links to, and §7 names those fixtures.

It is checked against the reference reader instead. `tools/test_bootstrap.py`
asserts, in both directions, that the class lists of §3 and §5 match what
`tools/rootfile.py` hardcodes, since drift in either direction would not show up
as a failing fixture. The groupings the tables use (`TArray*`, `std::string`) are
listed explicitly in that test rather than pattern-matched, so a new spelling has
to be considered rather than silently absorbed.
