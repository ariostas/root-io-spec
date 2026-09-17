# RNTuple

RNTuple is the one ROOT format that already has a real specification, written and
maintained by the ROOT team. **This project does not fork it**, and this directory
is deliberately shaped differently from the rest of `spec/`:

| | |
|---|---|
| [Binary format specification](BinaryFormatSpecification.md) | A **verbatim tracked copy** of ROOT's own document. Never edited here |
| [Provenance and sync](UPSTREAM.md) | Which commit the copy came from, how to re-sync, and why the other five upstream documents are not tracked |
| [Errata](ERRATA.md) | Where the document and ROOT's code disagree. Candidates for upstream pull requests |
| [Implementation notes](NOTES.md) | Where the document is correct but incomplete for a reader arriving from the ROOT file side |

Everywhere else in this specification, a document is the primary source and the
citations support it. Here the tracked copy is the primary source and **this
project's contribution is the audit** — checking it against
`RNTupleSerialize.cxx` and `RMiniFile.cxx` field by field, the way
[the container layer](../01-container/FileHeader.md) was checked against
`TFile.cxx`, and feeding what that finds back upstream rather than keeping it.

`tools/sync_rntuple.py --check` runs in CI and fails if the copy drifts from the
submodule, so the copy cannot quietly become a fork.

**`gen/cases/rntuple/anchor`** is the audit's fixture: an RNTuple written by the
pinned ROOT with compression off, whose bytes the errata are asserted against.
Before it existed, every byte in them came from one file in the CERN corpus
written by an older release.

## Where RNTuple meets the rest of this specification

An RNTuple in a ROOT file is not self-contained: it sits inside the container this
specification already describes, and the two layers' rules differ in ways that
break a reader coming from the TFile side. Those are
[NOTES 1](NOTES.md#1-an-rblob-keys-fobjlen-is-decorative)
and [NOTES 2](NOTES.md#2-decompression-tests-equality-and-anything-else-is-an-error) —
an `RBlob` key's `fObjLen` is decorative, and RNTuple's compression test is
stricter than the container's.

Reading an RNTuple therefore needs
[the file header](../01-container/FileHeader.md),
[records and keys](../01-container/Record.md) and
[compression](../01-container/Compression.md) from this specification, the anchor
and everything below it from the tracked copy, and the three errata in between.

## Status

**Six errata**, each verified against the pinned submodule and, where there are
bytes to check, against `RNTuple.root`. Three are in the anchor and the ROOT file
embedding, one in the locator type table, one in the envelope header, and one in
the column type table — where the document lists a column encoding, `0x17
SplitReal16`, that ROOT's C++ implementation does not have and **ROOT's own
JavaScript reader does**.

The audit now covers every envelope: the header's field, column, alias column and
extra-type-info records, the footer's schema extension, cluster groups and
attribute sets, and the page list's cluster summaries and page locations. The
remaining half of the document — the C++ type mapping, limits, naming and the
compatibility notes — is **not yet audited**, and
[NOTES §4](NOTES.md#4-what-has-not-been-audited-yet) says so plainly rather than
leaving the silence to be read as approval.
