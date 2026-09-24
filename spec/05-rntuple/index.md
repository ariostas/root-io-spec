# RNTuple

RNTuple is the only ROOT format that already has a real specification, written and
maintained by the ROOT team. **This project does not fork it**, and this directory
is organised differently from the rest of `spec/`:

| | |
|---|---|
| [Binary format specification](BinaryFormatSpecification.md) | A **verbatim tracked copy** of ROOT's own document. Never edited here |
| [Provenance and sync](UPSTREAM.md) | Which commit the copy came from, how to re-sync, and why the other five upstream documents are not tracked |
| [Errata](ERRATA.md) | Where the document and ROOT's code disagree. Candidates for upstream pull requests |
| [Implementation notes](NOTES.md) | Where the document is correct but incomplete for a reader coming from the ROOT file side |

Everywhere else in this specification, a document is the primary source and the
citations support it. Here the tracked copy is the primary source, and this
project's contribution is an audit of it: a field-by-field check against
`RNTupleSerialize.cxx` and `RMiniFile.cxx`, the way
[the container layer](../01-container/FileHeader.md) was checked against
`TFile.cxx`. What the audit finds is meant to go upstream rather than stay here.

`tools/sync_rntuple.py --check` runs in CI and fails if the copy drifts from the
submodule, so the copy cannot quietly become a fork.

The audit rests on ten fixtures. `gen/cases/rntuple/anchor` is an RNTuple
written by the pinned ROOT with compression off, and the errata are asserted
against its bytes; before it existed, every byte in them came from one file in the
CERN corpus written by an older release. `fundamental-types` has one field per
fundamental C++ type and pins the column each lands in, and `collections`, `map`,
`user-class`, `projected`, `untyped`, `streamed` and `soa` each pin one area of
the type mapping. `compressed` is the only one written with compression on, so
the only one whose pages go through a codec.

`tools/rootfile.py` reads an RNTuple anchor and header envelope independently of
ROOT. It is written from the tracked copy, so a disagreement between the two is
detectable, as it is for the rest of this specification.

## Where RNTuple meets the rest of this specification

An RNTuple in a ROOT file is not self-contained. It sits inside the container this
specification already describes, and some of the two layers' rules differ in ways
that break a reader coming from the TFile side:
[NOTES 1](NOTES.md#1-an-rblob-keys-fobjlen-is-decorative)
(an `RBlob` key's `fObjLen` is decorative) and
[NOTES 2](NOTES.md#2-decompression-tests-equality-and-anything-else-is-an-error)
(RNTuple's compression test is stricter than the container's).

Reading an RNTuple therefore needs
[the file header](../01-container/FileHeader.md),
[records and keys](../01-container/Record.md) and
[compression](../01-container/Compression.md) from this specification, the anchor
and everything below it from the tracked copy, and the three errata in between.

## Status

There are ten errata, each verified against the pinned submodule and, where there
are bytes to check, against a fixture:

- three in the anchor and the ROOT file embedding;
- one in the locator type table;
- one in the envelope header;
- one in the column type table, which lists a column encoding, `0x17
  SplitReal16`, that ROOT's C++ implementation does not have but **ROOT's own
  JavaScript reader does**;
- four in the type mapping, the last of which puts the *Extra type information*
  record in a different envelope from the one the document introduces it under.

The audit covers every envelope and, with one exception, all of the type mapping:
the header's field, column, alias column and extra-type-info records, the footer's
schema extension, cluster groups and attribute sets, the page list's cluster
summaries and page locations, the stdlib types, user-defined classes and enums,
projected fields and alias columns, `RNTupleCardinality`, untyped collections and
records, ROOT streamed types, the SoA layout, and the limits, naming and
compatibility notes. Two forms are left out on purpose: *Linked Attribute Sets*
beyond its footer record frame, and classes with an associated collection proxy,
which needs a compiled `TCollectionProxyInfo` that is not ready for this use.
[NOTES §4](NOTES.md#4-what-has-not-been-audited-yet) has the per-section table,
including which claims rest on the source alone rather than on bytes.
