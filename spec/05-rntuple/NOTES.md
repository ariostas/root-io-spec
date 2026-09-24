# Implementation notes

Where [the tracked copy](BinaryFormatSpecification.md) is **correct but
incomplete** for someone implementing a reader. Usually this is because it
describes RNTuple from the inside, while a reader arrives from the ROOT file side,
where the container's own rules are already in force and do not all apply.

Where the document and the code disagree, the entry is in
[ERRATA.md](ERRATA.md) instead.

## 1. An `RBlob` key's `fObjLen` is decorative

A reader that walks the record chain of
[Records and keys](../01-container/Record.md) meets RNTuple's payload as a series
of keys of the artificial class `RBlob`, and the assumptions that hold for the rest
of the container layer do not hold for them.

`RNTuple`'s key writer takes the on-disk and in-memory lengths as **independent
arguments** and fills the header with whatever it was given
(`root/tree/ntuple/src/RMiniFile.cxx:230-236`):

```cpp
fObjLen = szObjInMem;
fNbytes = fKeyLen + ((szObjOnDisk == 0) ? szObjInMem : szObjOnDisk);
```

and the call site gives the reason (`root/tree/ntuple/src/RMiniFile.cxx:1437`):

> `// We don't need the object length except for seeing compression ratios in TFile::Map()`

`fObjLen` is therefore not the uncompressed length of the payload, and the two need
not even be ordered the way the container expects. In `RNTuple.root` the `RBlob` at
offset 586 has `fNbytes` 789 and `fKeyLen` 34, a 755-byte payload, and `fObjLen`
723, thirty-two bytes less. One key may hold several pages (the document says so
under *ROOT File embedding*), and each page has its own trailing checksum that
`len` does not count.

The consequences:

- **The compression test of
  [Compression §1](../01-container/Compression.md#1-deciding-whether-a-payload-is-compressed)
  gives the wrong answer.** `fObjLen > fNbytes - fKeyLen` is false here, so the
  payload is treated as stored raw and a reader takes the first `fObjLen` bytes,
  truncating 755 bytes to 723 without any error. A reader using the `!=` form
  of ROOT's own `TFile::Map()` instead looks for a compression magic that is not
  there and rejects the whole file. `PLAN.md` §9.9 records that this is how
  the `!=`/`>` erratum in `Compression.md` was found.
- **With compression on it fails the other way, and visibly.** The paragraph above
  is the uncompressed case, where `fObjLen` is short and a reader silently
  truncates. With compression on, which is RNTuple's default, `fObjLen > fNbytes -
  fKeyLen` is true, so the payload is walked as a block chain. A single sealed
  page's chain then ends 8 bytes early, because the page checksum is appended
  after compression and outside `fObjLen`
  (`root/tree/ntuple/src/RPageStorage.cxx:751`). A blob holding several pages has
  no single chain at all and mixes raw pages with compressed ones, and a
  conforming container reader rejects the whole file rather than one record.
  [Compression §9.1](../01-container/Compression.md#91-what-an-rblob-is-not)
  has the details and `rntuple/compressed` is the fixture.

- **Nothing else in the key is usable either.** Follow the document's own rule:
  *"The only relevant means of finding objects is the locator information,
  consisting of an offset and a size."* Take offsets and sizes from the page list
  envelope, and treat an `RBlob` key only as a container the bytes sit inside.

The document is not wrong about any of this. It does not warn that the enclosing
key's fields contradict it, and a reader that already has a working `TFile`
implementation will use them first.

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
each block header must then satisfy `szTarget > szSource`
(`root/tree/ntuple/inc/ROOT/RNTupleZip.hxx:126-128`). The document's phrasing,
"If the compressed size == uncompressed size, the data is stored unmodified", is
correct **for RNTuple**. It must not be carried back to the container layer,
where the same sentence is the erratum recorded in `PLAN.md` §9.9.

The block format itself is shared: the nine-byte header, the algorithm triples,
and the 16 MiB cap on one chunk are the same constants `Compression.md` describes.
`ttree/basket-multiblock` pins the cap at `kMAXZIPBUF = 0xffffff`
(`root/core/zip/inc/RZip.h:40`).

## 3. Big-endian in the anchor, little-endian everywhere else

The document says this once, under *Anchor schema*, and it is easy to miss:

> all integers in the anchor, as well as the checksum, are encoded in
> **big-endian**, unlike the RNTuple payload which is encoded in little-endian.

It is the most consequential sentence in the section. The anchor is a TKey payload
and so follows [Conventions §3](../00-conventions.md#3-byte-order), big-endian like
everything else in a ROOT file. The envelopes and pages the anchor points at are
RNTuple's own format and are little-endian. The boundary is the anchor's last byte.

Every member of the `RTFNTuple` struct is big-endian: `RUInt32BE` for
`fByteCount`, `RUInt16BE` for the four version words, and `RUInt64BE` for the
offsets and lengths (`root/tree/ntuple/src/RMiniFile.cxx:547-560`). The
`RUInt32BE` is named separately because it is the field ERRATA 2 is about.

> Demonstrated by `rntuple/anchor` and `rntuple/fundamental-types`, which need
> **both** orders to describe one file: the anchor assertions read big-endian and
> the envelope assertions read little-endian, and `tools/check_bytes.py` gained an
> `le` suffix for this case. The same eight bytes read in the other order are a
> different, plausible number rather than an obvious error, so the fixture states
> the order at every offset instead of relying on a default.

## 4. What has not been audited yet

The field-by-field audit of the document against `RNTupleSerialize.cxx`, which is
the reason the copy is tracked, has covered the sections below.

`rntuple/anchor` makes the audited sections byte-checked rather than source
readings: it is this project's first RNTuple fixture, written by the pinned
release with compression off, and it asserts the anchor, both envelope preambles,
and the header envelope including its field and column records.

| Section | State |
|---|---|
| ROOT File embedding, Anchor schema | audited — ERRATA 1, 2, 3 |
| Compression Block | audited — §2 above |
| Basic Types, Feature Flags | audited, clean |
| Frames | audited, clean |
| Locators and Envelope Links | audited — ERRATA 4 |
| Envelopes, the envelope header and checksum | audited — ERRATA 5 |
| Header Envelope: field, column, alias column, extra type info | audited — ERRATA 6 |
| Footer Envelope: schema extension, cluster groups, attribute sets | audited — **ERRATA 11**: the attribute set list is new in 1.0.1.0 |
| Page List Envelope: cluster summaries, page locations, suppressed columns | audited, clean |
| Fundamental Types: the default column per C++ type | audited against bytes, clean |
| Type Name Normalization: the standard-integer-typedef rule | audited against bytes, clean |
| `std::string`'s field and columns | audited against bytes, clean |
| Stdlib Types and Collections: `vector`, `RVec`, `array`, `variant`, `pair`, `tuple`, `bitset`, `unique_ptr`, `optional`, `set`, nested collections | audited against bytes, clean — `rntuple/collections` |
| `std::atomic`, and the parent-with-one-child shape it shares with an enum | audited against bytes, clean |
| Low-precision Floating Points | audited against bytes — **ERRATA 7** |
| Type Name Normalization inside template arguments | audited against bytes, clean |
| `std::map` and the unordered/multi variants | audited against bytes, clean — `rntuple/map`, all four types; §5 says why only some maps can be written |
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
| Defaults | audited against `RNTupleWriteOptions`; the table omits same-page merging, which changes what is on disk — §7 |
| Notes on Backward and Forward Compatibility | audited: ROOT's reader implements the one MUST, §6 |
| Linked Attribute Set Record Frame: the versions, the anchor size, the locator, the name | audited against bytes — **ERRATA 12** — `rntuple/attributes` |
| Linked Attribute Sets: a set stored as an RNTuple, the three restrictions, distinct non-empty names, reserved `__` names | audited against bytes and by probing ROOT's writer and reader, clean — §8 |
| Attribute Schema Version: 1.0's three fields, their types and order, `_rangeLen` 0, the major and minor rules | audited against bytes — **ERRATA 13** |

**Not audited, on purpose:** classes with an associated collection proxy, the
only type-mapping form with no fixture and the only section of the document left.
It is set aside (2026-09-24): the audit is otherwise complete, and the form needs
`TCollectionProxyInfo`, which is not ready for this use. The document says the
associative half of it "are supported in the RNTuple binary format, but currently
are not implemented in ROOT's RNTuple reader and writer". The sequential half
needs `TClass::SetCollectionProxy` with a `TCollectionProxyInfo`, which is a
compiled template instantiation rather than a runtime attribute. It is the only
row above that a `classes.h` and an interpreted macro cannot reach.

*Linked Attribute Sets* was set aside with it until the same day, audited only as
far as the footer's record frame by reading `SerializeAttributeSet`. It is now
audited end to end against `rntuple/attributes`, the first fixture with a
non-empty attribute set list; §8 has what the audit found beyond ERRATA 11 to 13.

The dictionary attributes are **not** a barrier: they are settable at runtime with
`cl->CreateAttributeMap(); cl->GetAttributeMap()->AddProperty(...)`, which is how
`rntuple/streamed` and `rntuple/soa` are written. ROOT's own tests do the same
(`root/tree/ntuple/test/rfield_streamer.cxx:54-57`).

The type mapping is a different kind of material from the envelope sections. An
envelope describes a byte layout, checkable field by field against the
serializer. The type mapping describes **which columns a given C++ type
produces**, which can only be checked by writing an RNTuple of that type and
reading the schema back, so it advances one fixture at a time.

`gen/cases/rntuple/fundamental-types` is the first of those, and it sets the
pattern: a fixture per group of types, decoded with `rootfile.read_rntuple`, and a
test in `tools/test_rntuple.py` that parses the claim out of the tracked copy and
compares. Neither side can then change silently: not the document on a submodule
bump, and not ROOT when a default changes.

`gen/cases/rntuple/collections` is the second, and it audits *Stdlib Types and
Collections* type by type. It found three things the document does not say, none
of them a disagreement about bytes:

- **There is no "repetitive" structure on disk.** The document calls a
  `std::array` field repetitive; in the file it is a **plain** field with no
  columns and a repetition parameter of *N*. `std::bitset<8>` has the same shape
  with a `Bit` column attached. The four structural roles are plain, collection,
  record and variant, and repetition is a field of the record rather than a fifth
  role.
- **"An empty parent field" is the `record` role** for `std::pair` and
  `std::tuple`, which have no columns at all. `std::atomic` and a user-defined enum
  are described in the same words but come out **plain**, so "empty parent"
  describes the columns and not the role.
- **Type name normalization reaches inside template arguments.** `int` is spelled
  `std::int32_t` at every depth: `std::array<std::int32_t,3>`,
  `std::variant<std::int32_t,float>`, `std::set<std::int32_t>`. `RVec` is written
  fully qualified, `ROOT::VecOps::RVec<float>`, as the document requires, although
  it also asks readers to accept the short alias.

It also found one disagreement: `Double32_t` keeps its `SplitReal32` column in an
**uncompressed** ntuple, where every other default drops to unsplit. That is
ERRATA 7.

`gen/cases/rntuple/user-class` is the third, and it audits the user-class half:
a struct with a base class, two enums, a vector of itself and a transient member.
Every claim in *User-defined classes → Regular class / struct* and
*User-defined enums* holds: a record parent with no columns, members keeping their
C++ names, a base class as `:_0`, an enum as a plain parent over its underlying
integer, and a `//!` member with no field at all. Two further findings:

- **A regular class has a type checksum and a type version too.** The document
  mentions both only under the SoA form; they are on every class field, and they
  are what lets a reader match a class to a dictionary.
- **The type version of a class with no `ClassDef` is 0xFFFFFFFF**, because
  `TClass::GetClassVersion()` is −1 and the field is unsigned. ERRATA 8.

The frames section is clean. Its size field is a signed 64-bit little-endian
integer whose sign selects record (positive) or list (negative), as the prose
says, and `SerializeFramePostscript` writes `marker * size` to set it
(`root/tree/ntuple/src/RNTupleSerialize.cxx:973-980`); the read side recovers
`nitems` only for a list frame and negates the size back
(`root/tree/ntuple/src/RNTupleSerialize.cxx:996-1007`).

So are the footer and page list, which is where a reader does its work. Checked
field by field against `SerializeFooter`, `SerializeClusterGroup`,
`SerializeAttributeSet`, `SerializePageList` and `SerializeClusterSummary`: the
cluster summary does pack `nEntries` into 56 bits with 8 bits of flags above it
and refuses more (`root/tree/ntuple/src/RNTupleSerialize.cxx:1191-1193`); the
suppressed-column marker is `INT64_MIN`
(`root/tree/ntuple/inc/ROOT/RNTupleSerialize.hxx:85`); and the reader relies on
the claim that "the page size stored in the locator does _not_ include the
checksum": it adds the eight bytes back itself
(`root/tree/ntuple/src/RPageStorage.cxx:297`).

Reading the serializer missed one thing that only the deserializer and an older
file show: the footer's last list, the attribute sets, is absent from every footer
before format 1.0.1.0. ERRATA 11; it was found when the attribute set audit made
`tools/rootfile.py` read footers across the corpus, not only the fixtures.

The one section still unaudited, the collection-proxy form above, is not thereby
correct. It is not yet checked, which is the same standard the rest of this
project applies.

## 5. A `std::map` without a compiled dictionary cannot be written in 6.40.04

`std::map` is the one type in *Stdlib Types and Collections* that can be written
only for some instantiations. With the field empty and never touched:

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
both built successfully; the abort is in `Fill()`. Assigning to the field first,
with `operator[]` or `insert`, segfaults earlier, before reaching `Fill()`.

**Whether it aborts depends on the dictionary, not on `std::map`.** Measured over
eleven instantiations on 2026-09-23, each written empty and filled, through
`MakeField` and through `AddField(std::make_unique<ROOT::RField<M>>(name))` alike:

| Writes | Aborts |
|---|---|
| `map<int,int>`, `map<string,float>`, `map<string,int>`, `map<double,int>` | `map<int,float>`, `map<int,double>`, `map<std::int64_t,float>`, `map<float,int>`, `map<int,string>`, `map<char,int>`, `map<long,float>` |

The left column is exactly the instantiations ROOT ships compiled dictionaries
for, in `libmapDict` and `libmap2Dict` (`root/core/clingutils/src/mapLinkdef.h`,
`root/core/clingutils/src/map2Linkdef.h`). For every other one `TClass` has no
dictionary and is emulated, and that is the case that reaches the assertion.
`map<int,float>` writes as soon as ACLiC compiles a dictionary for it.
rntuple-validation's `map<std::string, std::int32_t>` writes for the same reason,
which is why its weekly CI passes. `map<long,float>` has a shipped dictionary and
still aborts, because RNTuple normalises the type to
`std::map<std::int64_t,float>`, which on macOS resolves to `map<Long64_t,float>`,
a `long long` map with no dictionary.

This is not a format question: the document's `std::map` paragraph describes a
collection parent over a `std::pair<K, V>` child named `_0`, which is
`std::vector<std::pair<K,V>>`'s shape and is consistent with everything else
audited. Nor does it block a fixture: `rntuple/map` writes one field of each of the
four types from a plain macro, each an instantiation with a shipped dictionary. It
is a defect in RNTuple, which accepts a field whose collection proxy is emulated
and then aborts in `Fill()` instead of refusing it when the model is built.
`PLAN.md` §7.1 item 10 holds the report.

## 6. The compatibility notes are reader requirements, and ROOT keeps the hard one

*Notes on Backward and Forward Compatibility* is the only section that constrains
**readers** rather than bytes, so auditing it means asking whether ROOT's own
reader does what it says. The important rule is the last one, because it is the
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
the sum of the fields read (`tools/rootfile.py`'s `read_rn_frame`). A fixture
written by a newer ROOT therefore parses here rather than desynchronising.

*Limits* needs no separate reading: every row is arithmetic over an encoding this
directory has already audited. A 16-bit bit count gives the 8 kB element, a 16-bit
type code the 64k column types, a 48-bit envelope length the 2^48 envelope, a
56-bit entry count the 2^56 entries per cluster, and a 32-bit string length the
4 GB metadata string. The two rows that are *design* rather than encoding, the
10 PB volume and the 8 TB cluster, say so themselves ("assuming", "depends on").

*Defaults* matches `RNTupleWriteOptions`: 128 MiB approximate zipped cluster,
1280 MiB maximum unzipped cluster (`10 *` the first, not an independent number),
and 1 MiB maximum unzipped page
(`root/tree/ntuple/inc/ROOT/RNTupleWriteOptions.hxx:198-201`). The table omits a
fourth default from the same block that is visible in the bytes:
`fInitialUnzippedPageSize` is **256**, so the first page of a column in a small
ntuple is 256 bytes rather than 1 MiB. The section says it summarizes, so this is a
gap rather than an error, but it is the default that explains a page size someone
will measure.

*Naming specification* is clean, checked from both sides. The validator forbids
`.`, `/`, space, `\` and control characters
(`root/tree/ntuple/src/RNTupleUtils.cxx:31-50`). The writer refuses an empty field
name ("name cannot be empty string") and an empty ntuple name ("empty RNTuple
name"), which the document says cannot be persistified; the validator itself does
not check them, a different piece of ROOT does.

## 7. Two page locators can name the same bytes

The document describes a page list as one locator per page and says nothing about
two locators being equal. They can be, in a file ROOT writes by default: an
identical page is written once and every column that produced it points at that
copy. The option is `EnableSamePageMerging`, **on by default**; it matches pages by
checksum and then compares their bytes
(`root/tree/ntuple/inc/ROOT/RNTupleWriteOptions.hxx:169-174`,
`root/tree/ntuple/src/RPageStorage.cxx:1117-1142`). *Defaults* lists three
`RNTupleWriteOptions` settings and not this one, though it is the one that changes
the bytes.

> Demonstrated by `rntuple/map`. `fMap` and `fMulti` each hold two pairs in the
> first entry and none in the second, so both index columns' pages are the same
> sixteen bytes, 2 then 2. There is one copy, at 1798, and the page list names it
> twice: column 0's locator at 2146 and column 7's at 2426 both say 16 bytes at
> 1798. `fUnordered` and `fUnMulti` share the page at 1873 in the same way.

A reader that reads pages through their locators is unaffected. Anything that
treats the page list as a partition of the file is: a reader that sums page sizes
to check an `RBlob`'s length, a tool that rewrites pages in place, or a checker
that expects every locator to be distinct. None of those may assume that pages
are disjoint.

## 8. Linked attribute sets

The document describes an attribute set from the inside: an RNTuple, linked from
the main footer, with three restrictions and a fixed internal schema. All of that
holds in `rntuple/attributes`, apart from ERRATA 11 to 13. What follows is what a
reader coming from the ROOT file side needs as well, and what ROOT 6.40.04 checks.

**The anchor is a key that no directory lists.** A set's anchor is written like
any RNTuple anchor, a `ROOT::RNTuple` key named after the set, and its key is then
removed from the directory's key list
(`root/tree/ntuple/src/RMiniFile.cxx:1374-1378`). The footer's locator is the only
way to it, and it names the key's payload, the anchor object itself, not the key:
78 bytes at 2508 for `runs`, whose key starts at 2462. A reader that walks the
record chain meets the set's anchor as an unlisted `ROOT::RNTuple` record, which
it can read like any other; only the main footer says what it is. Nothing stops a
set having the name of a listed key (a set named after its own main RNTuple is
accepted), so a file can hold two `ROOT::RNTuple` records of one name, one listed
and one not.

**The set is an RNTuple named after itself.** Its header's name is the set's name,
and the footer record's name is read from that header when the set is committed
(`root/tree/ntuple/src/RNTupleWriter.cxx:205-209`); its description is the user
model's (`root/tree/ntuple/src/RNTupleAttrWriting.cxx:73`). Its write options,
compression included, are the main writer's unless others are passed
(`root/tree/ntuple/src/RNTupleWriter.cxx:188`).

**An entry is a committed range, in commit order.** `_rangeStart` is the main
RNTuple's entry count when the range began and `_rangeLen` the count since
(`root/tree/ntuple/src/RNTupleAttrWriting.cxx:108-136`), so ranges can overlap and
nest, and a range committed straight after it began has length 0. In the fixture
`flags` holds (3, 0) before (1, 4). ROOT sorts the entries by start when it opens
a set (`root/tree/ntuple/src/RNTupleAttrReading.cxx:66-67`), keeps a zero-length
one, and matches it to no main entry, returning it only when all entries are asked
for (`root/tree/ntuple/src/RNTupleAttrReading.cxx:189-192`).

**What ROOT enforces, and where.** The writer was probed directly; the reader with
footers patched to point at RNTuples ROOT wrote, their checksums recomputed. On
read, the set's reader tests the major version and the count and names of the
top-level fields, and nothing in it looks at projections, streamer fields or
linked sets (`root/tree/ntuple/src/RNTupleAttrReading.cxx:20-54`):

| Rule | On write | On read |
|---|---|---|
| 1. no attribute sets of its own | by construction: the set's writer wraps an `RNTupleFillContext` (`root/tree/ntuple/inc/ROOT/RNTupleAttrWriting.hxx:157`), and only an `RNTupleWriter` can create a set | not checked: a set linking one of its own opens (probed) |
| 2. no projected fields | refused (`root/tree/ntuple/src/RNTupleAttrWriting.cxx:19-21`) | not checked (source only) |
| 3. no field of role 0x04 | refused, at any depth: a streamed member of a class is caught (`root/tree/ntuple/src/RNTupleAttrWriting.cxx:23-27`) | not checked (source only) |
| non-empty name | refused (`root/tree/ntuple/src/RNTupleWriter.cxx:185-186`) | refused (`root/tree/ntuple/src/RNTupleDescriptor.cxx:1158-1159`) |
| distinct names | refused (`root/tree/ntuple/src/RNTupleWriter.cxx:195-199`) | refused (`root/tree/ntuple/src/RNTupleDescriptor.cxx:1441-1445`) |
| reserved `__` prefix | refused (`root/tree/ntuple/src/RNTupleWriter.cxx:34-37`, `:180-183`) | allowed, as the document permits |
| unknown major version | not writable | refused when the set is opened; the main RNTuple reads (`root/tree/ntuple/src/RNTupleAttrReading.cxx:25-26`) |
| the three fields, by name and order | always written | checked, and a fourth refused (ERRATA 13) |

A reader that wants the document's restrictions checked has to check them itself;
`tools/check_invariants.py` does, on every attribute set it finds, and
`tools/test_rntuple.py` corrupts copies of the fixture to show that each check
fires.

**How to write one.** Only through `ROOT::Experimental`, and only from a writer
made by `RNTupleWriter::Append` into a `TFile`: the set's anchor is written
through the `TFile`, and any other writer refuses with "cannot clone a
non-TFile-based RNTupleFileWriter"
(`root/tree/ntuple/src/RMiniFile.cxx:1322-1328`). Committing a set also calls
`TFile::Write` (`root/tree/ntuple/src/RMiniFile.cxx:1372`), so the file's key list,
StreamerInfo record and free segments are written in the middle of the file, before
the main footer. `gen/cases/rntuple/attributes/gen.C` holds the StreamerInfo record
back to the end, because its length depends on the standard library and every
later offset would move with it.

**Three writer defects**, found while building the fixture and recorded in
`PLAN.md` §7.1 items 13 to 15:

- `RNTupleWriter::CloseAttributeSet` tests its handle the wrong way round and
  throws "Tried to close an invalid AttributeSetWriter" for every valid one
  (`root/tree/ntuple/src/RNTupleWriter.cxx:213-216`). The set is still committed
  when the writer is destroyed.
- A duplicate name is refused only after the set's sink has been cloned and its
  fill context has written the header envelope
  (`root/tree/ntuple/src/RNTupleWriter.cxx:189-199`,
  `root/tree/ntuple/src/RNTupleFillContext.cxx:33`), so the refusal leaves an
  unreferenced header `RBlob` in the file: 431 bytes in the probe that found it.
- A set whose user schema has an untyped record is written, but cannot be
  opened: the reader rebuilds each user field from its type name, which is empty
  (`root/tree/ntuple/src/RNTupleAttrReading.cxx:51`), and fails with "no type name
  specified for field". An untyped collection should fail the same way; only the
  record was probed.

The record frame's sentence also lacks a word: "followed a locator" is "followed
by a locator". The order it gives is right.
