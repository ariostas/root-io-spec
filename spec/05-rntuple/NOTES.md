# Implementation notes

Where [the tracked copy](BinaryFormatSpecification.md) is **correct but
incomplete** for someone implementing a reader — usually because it describes
RNTuple from the inside and a reader arrives from the ROOT file side, where the
container's own rules are already in force and do not all apply.

Where the document and the code actually disagree, the entry is in
[ERRATA.md](ERRATA.md) instead.

## 1. An `RBlob` key's `fObjLen` is decorative

A reader that walks the record chain of
[Records and keys](../01-container/Record.md) meets RNTuple's payload as a series
of keys of the artificial class `RBlob`, and every instinct from the rest of the
container layer is wrong about them.

`RNTuple`'s key writer takes the on-disk and in-memory lengths as **independent
arguments** and fills the header with whatever it was given
(`root/tree/ntuple/src/RMiniFile.cxx:230-236`):

```cpp
fObjLen = szObjInMem;
fNbytes = fKeyLen + ((szObjOnDisk == 0) ? szObjInMem : szObjOnDisk);
```

and the call site says outright why (`root/tree/ntuple/src/RMiniFile.cxx:1437`):

> `// We don't need the object length except for seeing compression ratios in TFile::Map()`

So `fObjLen` is not the uncompressed length of the payload, and the two need not
even be ordered the way the container expects. In `RNTuple.root` the `RBlob` at
offset 586 has `fNbytes` 789 and `fKeyLen` 34 — a **755-byte payload** — and
`fObjLen` **723**, thirty-two bytes *less*. One key may hold several pages
(the document says so under *ROOT File embedding*), and each page carries its own
trailing checksum that `len` does not count.

Two consequences, both silent:

- **The compression test of
  [Compression §1](../01-container/Compression.md#1-deciding-whether-a-payload-is-compressed)
  gives the wrong answer.** `fObjLen > fNbytes - fKeyLen` is false here, so the
  payload reads as "stored raw" and a reader takes the **first `fObjLen` bytes**
  — truncating 755 bytes to 723 without any error. A reader using the `!=` form
  that ROOT's own `TFile::Map()` uses instead finds a compression magic that is
  not there and rejects the whole file. `PLAN.md` §9.9 records that this is how
  the `!=`/`>` erratum in `Compression.md` was found.
- **Nothing else in the key is usable either.** The document's own rule is the
  one to follow: *"The only relevant means of finding objects is the locator
  information, consisting of an offset and a size."* Take offsets and sizes from
  the page list envelope, and treat an `RBlob` key as nothing but a container the
  bytes happen to sit inside.

The document is not wrong about any of this. It simply does not warn that the
enclosing key's fields contradict it, and a reader that already has a working
`TFile` implementation will reach for them first.

## 2. Decompression tests equality, and anything else is an error

The container layer decides that a payload is compressed when
`fObjLen > fNbytes - fKeyLen`, and **tolerates** a payload longer than `fObjLen`
by taking the first `fObjLen` bytes
([Compression §1.1](../01-container/Compression.md#1-deciding-whether-a-payload-is-compressed)).

RNTuple does not. `RNTupleDecompressor::Unzip` takes the compressed and
uncompressed sizes as arguments and branches on equality
(`root/tree/ntuple/inc/ROOT/RNTupleZip.hxx:106-113`):

```cpp
if (dataLen == nbytes) { memcpy(to, from, nbytes); return; }
R__ASSERT(dataLen > nbytes);
```

so `nbytes > dataLen` is a hard failure rather than the container's raw case, and
each block header is then required to satisfy `szTarget > szSource`
(`root/tree/ntuple/inc/ROOT/RNTupleZip.hxx:126-128`). The document's phrasing —
"If the compressed size == uncompressed size, the data is stored unmodified" — is
exactly right **for RNTuple**, and must not be carried back to the container
layer, where the same sentence is the erratum recorded in `PLAN.md` §9.9.

The block format itself is shared and identical: the nine-byte header, the
algorithm triples, and the 16 MiB cap on one chunk are the same constants
`Compression.md` describes, which `ttree/basket-multiblock` pins at
`kMAXZIPBUF = 0xffffff` (`root/core/zip/inc/RZip.h:40`).

## 3. Big-endian in the anchor, little-endian everywhere else

The document says this once, under *Anchor schema*, and it is easy to read past:

> all integers in the anchor, as well as the checksum, are encoded in
> **big-endian**, unlike the RNTuple payload which is encoded in little-endian.

It is the single most consequential sentence in the section. The anchor is a TKey
payload and so follows
[Conventions §3](../00-conventions.md#3-byte-order), big-endian like everything
else in a ROOT file; the envelopes and pages the anchor points at are RNTuple's
own format and are little-endian. The boundary is exactly the anchor's last byte.

The struct makes it explicit — every member of `RTFNTuple` is big-endian:
`RUInt32BE` for `fByteCount`, `RUInt16BE` for the four version words, and
`RUInt64BE` for the offsets and lengths
(`root/tree/ntuple/src/RMiniFile.cxx:547-560`). The `RUInt32BE` is the one ERRATA 2
exists for, so it is worth naming rather than folding into "64 or 16".

> Demonstrated by `rntuple/anchor` and `rntuple/fundamental-types`, which need
> **both** orders to describe one file: its anchor assertions read big-endian and its envelope assertions read
> little-endian, and `tools/check_bytes.py` gained an `le` suffix for exactly
> this case. The same eight bytes read the other way are a different, plausible
> number rather than an obvious error, which is why the fixture states the order
> at every offset instead of relying on a default.

## 4. What has not been audited yet

This directory is new. The field-by-field audit of the document against
`RNTupleSerialize.cxx` — which is the actual work of the audit and the reason the
copy is tracked at all — has so far covered:

Since the table below was written, `rntuple/anchor` has turned the audited
sections from source readings into byte-checked ones: it is this project's first
RNTuple fixture, written by the pinned release with compression off, and it
asserts the anchor, both envelope preambles, and the whole header envelope
including its field and column records.

| Section | State |
|---|---|
| ROOT File embedding, Anchor schema | audited — ERRATA 1, 2, 3 |
| Compression Block | audited — §2 above |
| Basic Types, Feature Flags | audited, clean |
| Frames | audited, clean |
| Locators and Envelope Links | audited — ERRATA 4 |
| Envelopes, the envelope header and checksum | audited — ERRATA 5 |
| Header Envelope: field, column, alias column, extra type info | audited — ERRATA 6 |
| Footer Envelope: schema extension, cluster groups, attribute sets | audited, clean |
| Page List Envelope: cluster summaries, page locations, suppressed columns | audited, clean |
| Fundamental Types: the default column per C++ type | audited against bytes, clean |
| Type Name Normalization: the standard-integer-typedef rule | audited against bytes, clean |
| `std::string`'s field and columns | audited against bytes, clean |
| Stdlib Types and Collections: `vector`, `RVec`, `array`, `variant`, `pair`, `tuple`, `bitset`, `unique_ptr`, `optional`, `set`, nested collections | audited against bytes, clean — `rntuple/collections` |
| `std::atomic`, and the parent-with-one-child shape it shares with an enum | audited against bytes, clean |
| Low-precision Floating Points | audited against bytes — **ERRATA 7** |
| Type Name Normalization inside template arguments | audited against bytes, clean |
| `std::map` and the unordered/multi variants | audited against the source only — ROOT aborts writing one here, §5 |
| User-defined enums, scoped and unscoped | audited against bytes, clean — `rntuple/user-class` |
| User-defined classes → Regular class / struct, base classes, transient members | audited against bytes, clean |
| Field Description: the type version and checksum of a class field | audited against bytes — **ERRATA 8** |
| Alias columns, and the projected-field flag | audited against bytes, clean — `rntuple/projected` |
| `ROOT::RNTupleCardinality<SizeT>`, both widths | audited against bytes, clean |
| Untyped collections and records | audited against bytes, clean — `rntuple/untyped` |
| ROOT streamed types: role 0x04, its two columns | audited against bytes, clean — `rntuple/streamed` |
| Extra type information: the record, and where the streamer info goes | audited against bytes — **ERRATA 9, 10** |
| Classes representing a SoA layout: flag 0x08 | audited against bytes, clean — `rntuple/soa` |
| Limits | audited against the encodings this project has already checked |
| Naming specification | audited against the validator and by probing the writer, clean |
| Defaults | audited against `RNTupleWriteOptions`, clean |
| Notes on Backward and Forward Compatibility | audited: ROOT's reader implements the one MUST, §6 |

**What is left**: *Linked Attribute Sets* beyond its footer record frame, and
**classes with an associated collection proxy** — the one type-mapping form with no
fixture. The document itself says the associative half of it "are supported in the
RNTuple binary format, but currently are not implemented in ROOT's RNTuple reader
and writer", and the sequential half needs `TClass::SetCollectionProxy` with a
`TCollectionProxyInfo`, which is a compiled template instantiation rather than a
runtime attribute. It is the only row above that a `classes.h` and an interpreted
macro cannot reach.

The dictionary attributes turned out **not** to be a barrier: they are settable at
runtime, `cl->CreateAttributeMap(); cl->GetAttributeMap()->AddProperty(...)`, which
is how `rntuple/streamed` and `rntuple/soa` exist at all. ROOT's own tests do the
same (`root/tree/ntuple/test/rfield_streamer.cxx:54-57`).

The type mapping is a different kind of material from the envelope sections. An
envelope describes a byte layout, checkable field by field against the
serializer. The type mapping describes **which columns a given C++ type
produces**, which is only checkable by writing an RNTuple of that type and
reading the schema back — so it advances one fixture at a time rather than one
reading.

`gen/cases/rntuple/fundamental-types` is the first of those, and the pattern it
sets is worth repeating: a fixture per group of types, decoded with
`rootfile.read_rntuple`, and a test in `tools/test_rntuple.py` that parses the
claim **out of the tracked copy** and compares. That way neither side can move
silently — not the document on a submodule bump, and not ROOT when a default
changes.

`gen/cases/rntuple/collections` is the second, and it audits *Stdlib Types and
Collections* type by type. Three things came out of it that the document does not
say, none of them a disagreement about bytes:

- **There is no "repetitive" structure on disk.** The document calls a
  `std::array` field repetitive; what the file carries is a **plain** field with
  no columns and a repetition parameter of *N*. `std::bitset<8>` is the same shape
  with a `Bit` column attached. The four structural roles are plain, collection,
  record and variant, and repetition is a field of the record rather than a fifth
  role.
- **"An empty parent field" is the `record` role**, for `std::pair` and
  `std::tuple` — no columns at all. `std::atomic` and a user-defined enum are
  described in the same words but come out **plain**, so "empty parent" describes
  the columns and not the role.
- **Type name normalization reaches inside template arguments.** `int` is spelled
  `std::int32_t` at every depth: `std::array<std::int32_t,3>`,
  `std::variant<std::int32_t,float>`, `std::set<std::int32_t>`. And `RVec` is
  written fully qualified, `ROOT::VecOps::RVec<float>`, exactly as the document
  requires while also asking readers to accept the short alias.

And one disagreement that is: `Double32_t` keeps its `SplitReal32` column in an
**uncompressed** ntuple, where every other default drops to unsplit. That is
ERRATA 7.

`gen/cases/rntuple/user-class` is the third, and it audits the user-class half:
a struct with a base class, two enums, a vector of itself and a transient member.
Every claim in *User-defined classes → Regular class / struct* and
*User-defined enums* holds — record parent with no columns, members keeping their
C++ names, a base class as `:_0`, an enum as a plain parent over its underlying
integer, and a `//!` member with no field at all. Two things worth keeping:

- **A regular class carries a type checksum and a type version too.** The document
  mentions both only under the SoA form; they are on every class field, and they
  are what lets a reader match a class to a dictionary.
- **The type version of a class with no `ClassDef` is 0xFFFFFFFF**, because
  `TClass::GetClassVersion()` is −1 and the field is unsigned. ERRATA 8.

The frames section came out clean. Its size field is a signed 64-bit
little-endian integer whose sign selects record (positive) from list (negative),
exactly as the prose says, and `SerializeFramePostscript` writes
`marker * size` to set it (`root/tree/ntuple/src/RNTupleSerialize.cxx:973-980`);
the read side recovers `nitems` only for a list frame and negates the size back
(`root/tree/ntuple/src/RNTupleSerialize.cxx:996-1007`).

So did the footer and page list, which is worth recording because they are where
a reader does its work. Checked field by field against `SerializeFooter`,
`SerializeClusterGroup`, `SerializeAttributeSet`, `SerializePageList` and
`SerializeClusterSummary`: the cluster summary really does pack `nEntries` into
56 bits with 8 bits of flags above it and refuses more
(`root/tree/ntuple/src/RNTupleSerialize.cxx:1191-1193`); the suppressed-column
marker really is `INT64_MIN`
(`root/tree/ntuple/inc/ROOT/RNTupleSerialize.hxx:85`); and the claim that "the
page size stored in the locator does _not_ include the checksum" is exactly what
the reader relies on — it adds the eight bytes back itself
(`root/tree/ntuple/src/RPageStorage.cxx:297`).

Nothing here should be read as a statement that the unaudited sections are
correct. They are simply not yet checked, which is the same standard the rest of
this project holds itself to.

## 5. `std::map` cannot be written from the interpreter in 6.40.04

The one type in *Stdlib Types and Collections* that this project cannot put in a
fixture. With the field empty and never touched:

```cpp
auto model = ROOT::RNTupleModel::Create();
auto f = model->MakeField<std::map<int, float>>("f");
ROOT::RNTupleWriteOptions opts; opts.SetCompression(0);
auto w = ROOT::RNTupleWriter::Recreate(std::move(model), "t", "map.root", opts);
w->Fill();      // <-- aborts
```

```
Fatal: 0 violated at line 1530 of io/io/src/TGenCollectionProxy.cxx
```

which is `R__ASSERT(0)` in `TGenCollectionProxy__VectorNext`, a function whose own
comment is "Should not be used"
(`root/io/io/src/TGenCollectionProxy.cxx:1528-1530`). The model and the writer are
both built successfully; the abort is in `Fill()`. Assigning to the field first —
`operator[]` or `insert` — segfaults earlier, before reaching `Fill()`.

Two things this is **not**. It is not a format question: the document's `std::map`
paragraph is a collection parent over a `std::pair<K, V>` child named `_0`, which
is `std::vector<std::pair<K,V>>`'s shape and is consistent with everything else
audited. And it is not necessarily a bug in RNTuple — the path taken here is the
interpreted one, and ACLiC on this machine cannot compile a comparison (`AGENTS.md`
records why). What it is, is a reason the `std::map` row above says *source only*,
and a candidate worth reporting with that caveat attached: `PLAN.md` §7.1 item 10.

## 6. The compatibility notes are reader requirements, and ROOT keeps the hard one

*Notes on Backward and Forward Compatibility* is the one section that constrains
**readers** rather than bytes, so auditing it means asking whether ROOT's own
reader does what it says. The load-bearing rule is the last one, because it is the
only MUST:

> When a reader encounters an unknown feature flag, it must refuse reading any
> further.

ROOT does. `DeserializeFeatureFlags` reads a chain of 64-bit words while the top
bit is set (`root/tree/ntuple/src/RNTupleSerialize.cxx:1049-1065`), and
`CheckFeatureFlags` fails with "unsupported format feature" on any bit it does not
know (`root/tree/ntuple/src/RNTupleSerialize.cxx:1869-1877`), called from both the
header and the footer deserializers (`:1903`, `:1958`).

The other rules are SHOULDs about ignoring what a reader does not understand, and
this project's own reader follows the important one by construction: every frame is
sized from its own preamble and the next read starts at the frame's end, never at
the sum of the fields read (`tools/rootfile.py`'s `read_rn_frame`). That is what
makes a fixture written by a newer ROOT parse here rather than desynchronise.

*Limits* needs no separate reading: every row is arithmetic over an encoding this
directory has already audited — a 16-bit bit count gives the 8 kB element, a 16-bit
type code the 64k column types, a 48-bit envelope length the 2^48 envelope, a
56-bit entry count the 2^56 entries per cluster, a 32-bit string length the 4 GB
metadata string. The two rows that are *design* rather than encoding — the 10 PB
volume and the 8 TB cluster — say so themselves ("assuming", "depends on").

*Defaults* matches `RNTupleWriteOptions`: 128 MiB approximate zipped cluster,
1280 MiB maximum unzipped cluster (which is `10 *` the first, not an independent
number), 1 MiB maximum unzipped page
(`root/tree/ntuple/inc/ROOT/RNTupleWriteOptions.hxx:198-201`). The table omits a
fourth default from the same block that a reader can see in the bytes:
`fInitialUnzippedPageSize` is **256**, so the first page of a column in a small
ntuple is 256 bytes rather than 1 MiB. The section says it summarizes, so that is a
gap rather than an error — but it is the one of the four that explains a page size
somebody will measure.

*Naming specification* is clean, and checked from both sides: the validator forbids
exactly `.`, `/`, space, `\` and control characters
(`root/tree/ntuple/src/RNTupleUtils.cxx:31-50`), and the writer refuses an empty
field name ("name cannot be empty string") and an empty ntuple name ("empty RNTuple
name"), which the document says cannot be persistified and which the validator
itself does not check — a different piece of ROOT does.
