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

## 4. What has not been audited yet

This directory is new. The field-by-field audit of the document against
`RNTupleSerialize.cxx` — which is the actual work of phase 6 and the reason the
copy is tracked at all — has so far covered:

| Section | State |
|---|---|
| ROOT File embedding, Anchor schema | audited — ERRATA 1, 2, 3 |
| Compression Block | audited — §2 above |
| Frames | audited, nothing found |
| Locators and Envelope Links | audited — ERRATA 4 |
| Envelopes, the envelope header and checksum | audited — ERRATA 5 |

**Not yet audited**: the contents of the Header, Footer and Page List envelopes,
Linked Attribute Sets, the C++ type mapping (*Mapping of C++ Types to Fields and
Columns* and everything under it), Limits, and Naming. Those are the bulk of the
document and where a reader spends most of its time.

The frames section came out clean. Its size field is a signed 64-bit
little-endian integer whose sign selects record (positive) from list (negative),
exactly as the prose says, and `SerializeFramePostscript` writes
`marker * size` to set it (`root/tree/ntuple/src/RNTupleSerialize.cxx:973-980`);
the read side recovers `nitems` only for a list frame and negates the size back
(`root/tree/ntuple/src/RNTupleSerialize.cxx:996-1007`).

Nothing here should be read as a statement that the unaudited sections are
correct. They are simply not yet checked, which is the same standard the rest of
this project holds itself to.
