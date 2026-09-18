# `TFormula` and `TF1`

One class name on disk, two unrelated C++ classes. A file written before ROOT
6.04 and a file written after it both contain a record whose class is `TFormula`,
and the member lists have nothing in common. The version word is the only thing
that separates them, and the discontinuity is deliberate.

This document is not a byte layout. **Every version of both classes that a
released ROOT ever wrote is streamer-info driven**, so
[Streamer-driven reading](../02-serialization/StreamerDriven.md) decodes them from
the file's own information and no hand-written layout is needed. What a reader
cannot get from the file is *which class it is looking at*, and that is what is
written down here.

## 1. Class versions

| Class | Version | ROOT releases | Notes |
|---|---|---|---|
| `TFormula` | 1 – 3 | ≤ 3.10 | hand-decoded by `ROOT::v5::TFormula::Streamer`; §4 |
| `TFormula` | 4, 5, 7, 8 | 3.10 – 6.02 | streamer-info driven, read into `ROOT::v5::TFormula` |
| `TFormula` | **6** | — | **ROOT 6 refuses it**: the dispatch is `v <= 8 && v > 3 && v != 6`, and 6 falls through to `Error("Streamer","Reading version %d is not supported")` (`root/hist/hist/src/TFormula.cxx:3806`, `root/hist/hist/src/TFormula.cxx:3922-3924`) |
| `TFormula` | 9 | **6.03/04 only** | the new class's first shipped version |
| `TFormula` | 10 – 14 | 6.04/00 – current | the new class; 14 is current |
| `TF1` | 1 – 4 | ≤ 3.10 | hand-decoded by `ROOT::v5::TF1Data::Streamer`; §4 |
| `TF1` | 5 – 7 | 3.10 – 6.02 | streamer-info driven, read into `ROOT::v5::TF1Data` |
| `TF1` | 8 – 12 | 6.04/00 – current | the new class; 12 is current |
| `ROOT::v5::TFormula` | 8 | 6.02 – current | the *in-memory* class old files are read into. No ordinary write path produces this name on disk; what is on disk is `TFormula` |
| `TF1Data` | 7 | 6.02 – current | likewise, as `ROOT::v5::TF1Data`. Note the `ClassDef` spells it `TF1Data`, unqualified |

`root/hist/hist/inc/TFormula.h:291`, `root/hist/hist/inc/TF1.h:694`,
`root/hist/hist/inc/v5/TFormula.h:272`, `root/hist/hist/inc/v5/TF1Data.h:60`.

### 1.1 Version 9 is not a gap, and version 1 was nearly a collision

The new `TFormula` was introduced in `b39823e310a` (2013-09-13, "right now
doesn't derive from TFormula, instead has object of it") at **`ClassDef(TFormula,
1)`** — the same version number the *old* class had used since ROOT 2. It was
lifted to 9 in `803a72ec9b9` (2014-12-03), then to 10 in `6a1710b9f39`
(2015-05-07).

Both the introduction and the jump to 9 fall inside the same first release,
`v6-03-04`, so **no released ROOT ever wrote the new class at a version below 9**,
and the collision at 1 never reached a file. Version 9 did ship, in the
development release 6.03/04; the first production release, 6.04/00, already wrote
10.

So the boundary is clean: **`TFormula` at version ≤ 8 is the old class, ≥ 9 is the
new one.** A reader may use that as a rule. It is the only such rule available,
because nothing else in the record distinguishes them — same name, same
`TNamed` base, and a checksum that is only useful if you already have both
schemas.

## 2. The two schemas share almost nothing

From the streamer infos of two real files — `uproot-issue-181.root`, written by
ROOT 5.34/36, and `classes/formula`, written by the pin:

| | `TFormula` v8 | `TFormula` v14 |
|---|---|---|
| base | `TNamed` (67) | `TNamed` (67) |
| parameters | `fNpar` (6), `fParams` a counted `Double_t*` (48) | `fClingParameters`, a `vector<double>` (500) |
| parameter names | `fNames`, a `kStreamLoop` of `TString` (501) | `fParams`, a `map<TString,int,TFormulaParamOrder>` (500) |
| the expression | `fExpr`, a `kStreamLoop` of `TString` (501), `fNoper` tokens | `fFormula`, one `TString` (65) |
| the compiled form | `fOper` (43), `fConst` (48), `fNoper`, `fNconst`, `fNval`, `fNstring` | none — JIT-compiled from `fFormula` |
| sub-functions | `fFunctions`, `fLinearParts`: two `TObjArray`s by value (61) | `fLinearParts`, a `vector<TObject*>` (500) |
| identity | `fNdim`, `fNumber` | `fNdim`, `fNumber` |

The old class stores a **pre-parsed operator stream**; the new one stores the
source text and compiles it. `fNdim` and `fNumber` are the only members that
survive with the same name and meaning — `fParams` survives the *name* and means
something else entirely, a counted array of values in v8 and a name-to-index map in
v14.

`TF1` changes shape too, and more visibly:

| | `TF1` v7 | `TF1` v12 |
|---|---|---|
| first element | `kBase TFormula` (0) — it **derives** from the formula | `kTNamed` (67) |
| the formula | the base class | `fFormula`, a `TFormula*` member (64) |
| parameter errors | `fParErrors`, a counted `Double_t*` (48) | `fParErrors`, a `vector<double>` (500) |
| saved samples | `fNsave` (6) and `fSave` (48) | `fSave`, a `vector<double>`; no separate count |
| limits | `fMaximum` **then** `fMinimum` | `fMinimum` **then** `fMaximum` |
| added in v12 | — | `fNpar`, `fNdim`, `fNormalized`, `fNormIntegral`, `fParams`, `fComposition` |

The limits row is the trap in the pair: the two members are adjacent `Double_t`s
whose order is swapped between the versions, so reading a v7 record with a v12
layout puts a value in each and neither is wrong-looking.

`classes/formula` pins the v12 side at offsets 335 to 798; the `TNamed` frame at
341 is where v7 has its `TFormula` base.

## 3. What ROOT does, and why a reader need not copy it

`TF1::Streamer` reads the version word and branches
(`root/hist/hist/src/TF1.cxx:3626-3650`):

- **v > 7** — `ReadClassBuffer(TF1::Class(), ...)`. Ordinary streamer-info driven
  reading.
- **v ≤ 7** — it constructs a `ROOT::v5::TF1Data` on the stack, calls
  `fold.Streamer(b, v, R__s, R__c, TF1::Class())`, and converts the result.

That second path then branches again
(`root/hist/hist/src/TF1Data_v5.cxx:80-95`):

- **v > 4** — `ReadClassBuffer(ROOT::v5::TF1Data::Class(), this, v, R__s, R__c,
  onfile_class)`, where `onfile_class` is `TF1::Class()`. The **file's own `TF1`
  info at version v** describes the bytes; the in-memory target is a different
  class, and schema evolution maps one onto the other
  ([Schema evolution](../02-serialization/SchemaEvolution.md)).
- **v ≤ 4** — hand-decoded, member by member, starting with
  `ROOT::v5::TFormula::Streamer(b)`.

`ROOT::v5::TFormula::Streamer` has the same shape, with the threshold at **3**
(`root/hist/hist/src/TFormula_v5.cxx:3507-3540`).

**The `onfile_class` detour is invisible from outside.** It exists because ROOT
wants the old bytes in a different C++ object; the bytes themselves are exactly
what the file's `TF1` v5–v7 streamer info says. A third-party reader that decodes
records with the info in the file gets them right without knowing that
`ROOT::v5::TF1Data` exists.

> This is also why the two `v5` classes are *not* in
> [Hand-written streamers](../99-appendix/HandWrittenStreamers.md)'s `custom`
> list, though a first pass put them there: their `ReadClassBuffer` lives in a
> sibling overload, and the overloads are one streamer.

## 4. The layouts that are hand-decoded

`TFormula` v ≤ 3 and `TF1` v ≤ 4 are read member by member with no reference to a
streamer info, and they predate schema evolution, so a file that old may carry no
info at all. Both are specified by the source and **neither is verified against
bytes**: they need a ROOT 3-era file, which is `PLAN.md` §9.1's standing gap.
Recorded here rather than transcribed, so the gap is not mistaken for coverage:

- `TFormula` v ≤ 3: `TNamed`, `fNdim`, `fNumber`, then `fNval` (v > 1) and
  `fNstring` (v > 2), then three counted arrays — `fParams`, `fOper`, `fConst` —
  read with `TBuffer::ReadArray`, which writes its own count, then `fNoper`
  `TString`s and `fNpar` `TString`s (`root/hist/hist/src/TFormula_v5.cxx:3541-3556`).
  **This layout is not reachable from a `TFormula` key**: ROOT 6's
  `TFormula::Streamer` has no branch for v ≤ 3 at all (it errors out), and the v5
  path that does hand-decode it is entered only from `TF1Data::Streamer` at `TF1`
  v ≤ 4.
- `TF1` v ≤ 4: the formula, `TAttLine`, `TAttFill`, `TAttMarker`, then `fXmin`
  and `fXmax` as **`Float_t` below v4 and `Double_t` at v4**, `fNpx`, `fType`,
  `fChisquare`, counted arrays, and at v1 a `TH1*` that is read and immediately
  deleted (`root/hist/hist/src/TF1Data_v5.cxx:95-140`).

The `TH1*` at v1 is worth noting: the histogram is on disk, is read, and is thrown
away. A reader must consume it.

## 5. Reading

1. Read the frame and the version word.
2. If the class is `TFormula`: version ≥ 9 is the ROOT 6 class, ≤ 8 the ROOT 5
   one. If the class is `TF1`: ≥ 8 is the ROOT 6 class, ≤ 7 the ROOT 5 one.
3. Above the thresholds of §3 — `TFormula` > 3 **except 6**, `TF1` > 4 — read with
   the streamer info **recorded in the file for that class at that version**, which
   is the ordinary path and needs nothing from this document. A `TFormula` at
   version 6 is readable by this rule even though ROOT itself refuses it (§1).
4. Below them, use §4 and a ROOT 3-era reference file that this project does not
   have.

## 6. Invariants

1. A `TF1` record's version word is in 1–12, and a `TFormula` record's in 1–14.
2. A `TF1` info at version ≤ 7 has `TFormula` as its first element, at code 0; at
   version ≥ 8 it has `TNamed`, at code 67. A `TF1` with both, or neither, is
   malformed.
3. A `TFormula` info at version ≤ 8 has `fNoper`; at version ≥ 9 it has
   `fClingParameters`. No info has both.

Checked by `tools/check_invariants.py` wherever a file carries the info. Invariant
2's v ≤ 7 half and invariant 3's v ≤ 8 half are exercised by
`uproot-issue-181.root` in `gen/foreign/`; **that file is a lead rather than
evidence** by the standing provenance rule, but its ROOT version word is 53436, so
ROOT 5.34/36 wrote it, and in any case the claim is about the file's agreement with
itself.

## 7. Errata

| # | Claim | Correction |
|---|---|---|
| 1 | A `Bool_t` member is 0 or 1 | `classes/formula` byte 665 is `TFormula::fAllParametersSetted` and holds **0x99**, because `TF1("g", "gaus", …)` never assigns it and ROOT pre-fills heap objects with that pattern. See [Element types §2.5](../02-serialization/ElementTypes.md). A ROOT bug candidate, `PLAN.md` §7.1 |
| 2 | `TFormula`'s class version identifies its schema | It identifies the schema *and the class*. Versions 1–8 and 9–14 are different C++ classes with different member lists under one name — the only case of this the project has found |

## 8. Reference files

| File | What it pins |
|---|---|
| `classes/formula` | the ROOT 6 side in full: `TF1` v12 with a `TNamed` base and a `TFormula*` member, `TFormula` v14 with its `vector<double>` and its `map<TString,int>`, and the `0x99` `kBool` of §7 |
| `uproot-issue-181.root` (`gen/foreign/`) | the ROOT 5 side: `TF1` v7 with a `TFormula` base, `TFormula` v8 with `fNoper`. Not a reference file — see §6 |
| — | `TFormula` v ≤ 3 and `TF1` v ≤ 4: needs a ROOT 3-era file (`PLAN.md` §9.1) |
