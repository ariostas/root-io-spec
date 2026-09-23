# Matrices and vectors

`TMatrixTSym` is the only class in this family whose bytes a reader has to know,
and it needs a document because of how it diverges rather than how much. Its
`Streamer` calls `ReadClassBuffer` like an ordinary class, and then reads the
matrix elements itself, outside the byte count, in a layout that no streamer info
in any file describes.

[Hand-written streamers §3](../99-appendix/HandWrittenStreamers.md) calls that
kind `extending`. Three classes in ROOT are of that kind; this is the one a
physics file is likely to contain, because a covariance matrix is symmetric.

## 1. Class versions

The concrete names are typedefs: `TMatrixDSym` is `TMatrixTSym<Double_t>`
(`root/math/matrix/inc/TMatrixDSymfwd.h:23`), `TMatrixD` is
`TMatrixT<Double_t>`, and `TVectorD` is `TVectorT<Double_t>`. A file uses the
**template spelling**, both as a class name and as a streamer info name.

Each is a template, and a file names the specialization (`TMatrixTBase<double>`),
whereas the `ClassDef` macro names the template. This table checks the latter:

| Class | Class version | `Streamer` | What a reader does |
|---|---|---|---|
| `TMatrixTBase` | 5 | none of its own | nothing: its info describes the prefix of every matrix in the family |
| `TMatrixT` | 4 | guarded above version 2 (`root/math/matrix/src/TMatrixT.cxx:3155`) | nothing for a current file — §3 |
| `TMatrixTSym` | **2, and never on disk** | `extending` (`root/math/matrix/src/TMatrixTSym.cxx:2030`) | **§2** |
| `TMatrixTSparse` | 3 | delegating | nothing |
| `TVectorT` | 4 | guarded above version 1 (`root/math/matrix/src/TVectorT.cxx:2341`) | nothing for a current file — §3 |

Class versions are checked against the submodule by `tools/check_versions.py`.

## 2. `TMatrixTSym`

### 2.1 Layout

```
byte count   version=5   TObject base        TMatrixTBase members
┌──────────┬──────────┬──────────────────┬─────────────────────────────┐
│ u32 |0x40 │   i16    │      10 bytes    │ 6 × i32, then fTol (Element)│
└──────────┴──────────┴──────────────────┴─────────────────────────────┘
             └──────────── the byte count covers this and stops ───────┘

then, past the byte count:
┌───────────────────────────────────────────────────────────────────────┐
│ row 0: fNcols elements │ row 1: fNcols−1 │ … │ row fNrows−1: 1 element │
└───────────────────────────────────────────────────────────────────────┘
```

Offsets from `classes/matrix`, whose `sym` record is a 3 × 3 `TMatrixDSym` with a
distinct value per stored element:

| Offset | Field | Bytes | Value |
|---|---|---|---|
| 329 | byte count | `u32` | `0x4000002c` — 44 |
| 333 | version word | `i16` | **5**, `TMatrixTBase<double>`'s class version |
| 335 | `TObject` base | 10 | version 1, `fUniqueID` 0, `fBits` 0 |
| 345 | `fNrows` | `i32` | 3 |
| 349 | `fNcols` | `i32` | 3 |
| 353 | `fRowLwb` | `i32` | 0 |
| 357 | `fColLwb` | `i32` | 0 |
| 361 | `fNelems` | `i32` | 9 — the full square |
| 365 | `fNrowIndex` | `i32` | 0 |
| 369 | `fTol` | `Element` | `2.220446049250313e-16` |
| 377 | element (0,0) | `Element` | 11.0 |
| 385 | element (0,1) | `Element` | 12.0 |
| 393 | element (0,2) | `Element` | 13.0 |
| 401 | element (1,1) | `Element` | 22.0 |
| 409 | element (1,2) | `Element` | 23.0 |
| 417 | element (2,2) | `Element` | 33.0 |

The framed part, from the version word to `fTol`, is what the streamer info for
`TMatrixTBase<T>` in the same file describes, read as
[Streamer-driven reading](../02-serialization/StreamerDriven.md) specifies with
the version word and byte count taken from this frame. The elements follow it.

### 2.2 The version word is the base class's

`TMatrixTSym<Element>::Streamer` passes `ReadClassBuffer` the `TClass` of
`TMatrixTBase<Element>`, not its own
(`root/math/matrix/src/TMatrixTSym.cxx:2036`), and the write side matches
(`root/math/matrix/src/TMatrixTSym.cxx:2054`). As a result:

- the version word on disk is `TMatrixTBase`'s class version, 5;
- `TMatrixTSym`'s own `ClassDefOverride(TMatrixTSym,2)`
  (`root/math/matrix/inc/TMatrixTSym.h:190`) never reaches a file. A reader
  must not look up a `TMatrixTSym` info by that version, or by any version;
- **the file has no streamer info for `TMatrixTSym<T>` at all.** Recording an
  info is a side effect of `WriteClassBuffer`, and the class it was given was the
  base. `classes/matrix` has four infos (`TMatrixTBase<double>`,
  `TMatrixTBase<float>`, `TMatrixT<double>` and `TVectorT<double>`) and none for
  either symmetric matrix it contains.

A reader that resolves the key's class name to a streamer info therefore finds
nothing, as with [`TBasket`](../04-ttree/TBasket.md), and must dispatch on the
name.

### 2.3 The elements, and how many there are

The read loop is one `ReadFastArray` per row, starting on the diagonal
(`root/math/matrix/src/TMatrixTSym.cxx:2040`):

- row *i* holds `fNcols − i` elements, for *i* from 0 to `fNrows − 1`;
- the total is `fNrows × (fNrows + 1) / 2`: six for a 3 × 3 and three for the
  2 × 2 in the same fixture;
- the lower-left triangle is **reconstructed** by ROOT after reading
  (`root/math/matrix/src/TMatrixTSym.cxx:2042`), not stored. `fNelems` is the
  full square, not the number of values on disk.

The element width is that of the template argument, and nothing in the record
states it. `symf` in the same fixture is a `TMatrixTSym<float>` whose three
elements are 4 bytes each, and so is its `fTol`, since `fTol` is declared
`Element`. A reader gets the width from the class name.

### 2.4 Outside its own byte count, inside every other

The byte count at 329 is 44 and covers only the framed part. This has two
consequences:

- **`CheckByteCount` cannot detect the mistake.** A reader that stops where the
  byte count says consumes 48 of the record's 96 payload bytes and reports no
  error. It does this on five `TMatrixTSym<double>` records in
  `uproot-issue-359.root` (ROOT 5.34/34): 48 of 3528, 48 of 13736. `PLAN.md` §9.8
  had filed this as a missing class rather than as the symptom of a wrong claim.
- **Every enclosing frame does count the elements.** In `classes/matrix` the same
  class appears inside a `TObjArray`: the pointer-streamed slot at 882 has a byte
  count of 96, which includes the triangle, while the `TMatrixTBase` byte count
  at 910 is 44 and does not. A file containing one is therefore never
  inconsistent: the bytes are accounted for by the object that holds it.

The second point has a consequence for skipping. `TBufferFile::SkipObjectAny`
skips an object by seeking to `start + count + 4`
(`root/io/io/src/TBufferFile.cxx:2499-2503`), so **an object of this kind cannot
be skipped by its byte count**: the seek lands
`width × fNrows × (fNrows + 1) / 2` bytes short. For a pointer member the slot's
own byte count is used and the skip is safe; for a by-value member it is the
class's own frame, and the skip is not safe. No file here demonstrates it (it
needs a class that dropped such a member), and it is recorded as a bug candidate
in `PLAN.md` §7.1 rather than as an established fact.

## 3. The rest of the family needs nothing

`TMatrixT` and `TVectorT` have hand-written `Streamer`s that are version guards:
above the threshold they call `ReadClassBuffer` with their **own** `TClass` and
read nothing further. They are ordinary streamer-info-driven objects, with an
info in the file and their own class version on disk.

`classes/matrix` pins both, for contrast with §2:

| Record | Shape |
|---|---|
| `gen`, a 2 × 3 `TMatrixD` | outer frame at 580 with version 4, a **nested** `TMatrixTBase` frame at 586 with its own byte count, then `fElements` as a counted pointer — the `01` is-present byte at 634 and all six values inside the outer byte count |
| `vec`, a `TVectorD` | one frame at 731 with version 4, `TObject`, `fNrows`, `fRowLwb`, then `fElements` with its is-present byte — 53 bytes, elements included |

Below their thresholds (`TMatrixT` at class version ≤ 2 and `TVectorT` at
version 1) both hand-decode a legacy layout, which is a gap tracked in
`PLAN.md` §9.1. Neither version occurs in either corpus.

`TMatrixTSparse` delegates unconditionally
(`root/math/matrix/src/TMatrixTSparse.cxx:2991`); its `fRowIndex` and `fColIndex`
are ordinary counted pointers, and `fNrowIndex` is their count. `linearIO.root`
in `gen/cern/` has its info.

## 4. Reading

Given a buffer position where an object of class `TMatrixTSym<T>` begins, with
`T` taken from the class name:

1. Read the byte count and version word as
   [Buffer framing §3](../02-serialization/Buffer.md) specifies. The version is
   `TMatrixTBase<T>`'s class version, and it selects the info.
2. Find the streamer info for **`TMatrixTBase<T>`** at that version. There is no
   info for `TMatrixTSym<T>`; if the info for the base is missing, the object
   cannot be read at all.
3. Apply [Streamer-driven reading](../02-serialization/StreamerDriven.md) to that
   info over the frame. This yields `fNrows`, `fNcols`, `fRowLwb`, `fColLwb`,
   `fNelems`, `fNrowIndex` and `fTol`.
4. Position at the end of the frame (byte-count position plus 4 plus the byte
   count) and read `fNrows × (fNrows + 1) / 2` values of `T`, in row order, row
   *i* holding `fNcols − i` of them beginning at column *i*.
5. Element (*i*, *j*) for *j* < *i* is element (*j*, *i*). The stored index of
   (*i*, *j*) for *j* ≥ *i* is `i × fNcols − i × (i − 1) / 2 + (j − i)`.
6. The object ends after the last element. An enclosing frame's byte count
   includes everything read in steps 1 to 4.

## 5. Invariants

1. A `TMatrixTSym<T>` record's version word equals the class version of the
   `TMatrixTBase<T>` streamer info in the same file.
2. `fNrows == fNcols`, and `fNelems == fNrows × fNcols`.
3. `fNrowIndex` is 0. It is the length of the row-index array, which only a
   sparse matrix has.
4. The bytes from the end of the frame to the end of the object are exactly
   `sizeof(T) × fNrows × (fNrows + 1) / 2`.
5. The byte count covers the version word, the `TObject` base and
   `TMatrixTBase`'s members, and **no** elements, so for a top-level record
   `fObjlen` exceeds the byte count's span by invariant 4's amount.
6. No file contains a streamer info named `TMatrixTSym<T>`.
7. For `TMatrixT<T>` and `TVectorT<T>` above their version guards, the object
   ends exactly where its byte count says.

`tools/check_invariants.py` checks all seven.

## 6. Errata

Against ROOT's own documentation and against earlier versions of this
specification.

| # | Was claimed | Actually |
|---|---|---|
| 1 | [Hand-written streamers](../99-appendix/HandWrittenStreamers.md), until 2026-09-17: a class that calls `ReadClassBuffer` with no version test around it produces "exactly what the streamer info describes" | Three do not, and this is one of them. The kind is now called `extending` and is listed there separately |
| 2 | `TMatrixTSym`'s reference documentation describes a class version 2 | True in C++ and unobservable on disk: the version word written is `TMatrixTBase`'s (§2.2) |

## 7. Reference files

| Case | Exercises |
|---|---|
| `classes/matrix` | All of §2 and §3: a 3 × 3 `TMatrixDSym`, a 2 × 2 `TMatrixFSym` for the element width, an ordinary `TMatrixD` and `TVectorD`, and a `TMatrixDSym` inside a `TObjArray` for the two byte counts of §2.4. 48 assertions |

`uproot-issue-359.root` in `gen/foreign/` is an independent check: five
`TMatrixTSym<double>` records written by ROOT 5.34/34, at 29 × 29 and 58 × 58,
each accounting for every byte as §2 describes. `linearIO.root` in `gen/cern/`
has `TMatrixT<float>`, `TMatrixT<double>`, `TMatrixTSparse` and `TVectorT` infos,
written by ROOT 5.05/01.

No fixture covers `TMatrixT` at class version ≤ 2 or `TVectorT` at version 1
(`PLAN.md` §9.1), a `TMatrixTSym` as a **by-value member** of another class, or
`TMatrixTSparse` with a non-zero `fNrowIndex`.
