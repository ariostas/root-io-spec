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

The struct makes it explicit — every member of `RTFNTuple` is an `RUInt64BE` or
an `RUInt16BE` (`root/tree/ntuple/src/RMiniFile.cxx:547-560`).

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

**Not yet audited**: *Linked Attribute Sets* beyond its footer record frame, most
of the C++ type mapping — the rest of *Type Name Normalization*, low-precision
floats, the stdlib collections beyond `std::string`, `std::atomic`, enums,
user-defined classes, `RNTupleCardinality`, streamed types and untyped
collections — plus *Limits*, *Naming specification*, *Defaults*, and *Notes on
Backward and Forward Compatibility*.

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
