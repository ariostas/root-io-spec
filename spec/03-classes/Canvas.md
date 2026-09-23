# `TCanvas`

`TCanvas` is the top-level object of any file saved from a canvas, and it is why a
reader meets `TPad`, `TVirtualPad` and `TQObject` at all. Its `Streamer` is
hand-written at every version (`root/graf2d/gpad/src/TCanvas.cxx:2221`), and what
it writes does not match its streamer info.

Class version **8** (`root/graf2d/gpad/inc/TCanvas.h:242`).

Prerequisites: [Buffer framing](../02-serialization/Buffer.md),
[Streamer-driven reading §4](../02-serialization/StreamerDriven.md).

## 1. Layout

```
bc:u32  ver:i16=8
<TPad>                      -- a framed TPad, read through its own streamer info
fDISPLAY:string
fDoubleBuffer:i32  fRetained:u8
fXsizeUser:f32  fYsizeUser:f32  fXsizeReal:f32  fYsizeReal:f32
fWindowTopX:i32  fWindowTopY:i32
fWindowWidth:u32  fWindowHeight:u32  fCw:u32  fCh:u32
<TAttCanvas>                -- fCatt, a framed object
kMoveOpaque:u8  kResizeOpaque:u8  fHighLightColor:i16  fBatch:u8
kShowEventStatus:u8  kAutoExec:u8  kMenuBar:u8
```

`TPad` is not hand-written at any version a ROOT 6 file contains: its `Streamer`
calls `ReadClassBuffer` above class version 5
(`root/graf2d/gpad/src/TPad.cxx:6649-6659`), and it is at 13 now
(`root/graf2d/gpad/inc/TPad.h:427`). The `TPad` base is therefore read by the
ordinary streamer-info-driven procedure, and this document says nothing about its
64 members. It does need §3.

`Size_t` is `Float_t` in ROOT, so the four `fXsize`/`fYsize` fields are 4 bytes
each, and `Color_t` is `Short_t`.

### 1.1 Version history

Each row gives only what that version adds to the differences in the rows below
it, so the differences accumulate downwards: a version-1 record lacks everything
rows 1, 2 and 3 name.

| Version | Difference from §1, cumulative downwards |
|---|---|
| 1 | stops after `fBatch` — `if (v < 2) return;` (`root/graf2d/gpad/src/TCanvas.cxx:2328`) — so no `kShowEventStatus`, `kAutoExec` or `kMenuBar`, and no `fWindowWidth`/`fWindowHeight` by row 2's rule |
| 2 | `fWindowWidth` and `fWindowHeight` are absent, gated by `if (v > 2)` (`root/graf2d/gpad/src/TCanvas.cxx:2303`); a reader takes them from `fCw` and `fCh`. `kAutoExec` is also absent by row 3's rule |
| 3 | `kAutoExec` is absent, gated by `if (v > 3)` (`root/graf2d/gpad/src/TCanvas.cxx:2332`) |
| 4 – 7 | as §1 |
| 8 | as §1; current. The only change is that `ClassBegin`/`ClassMember` annotations appear (§2), and they alter no bytes |

`root/graf2d/gpad/src/TCanvas.cxx:2303-2357`. Versions below 4 have no reference
file, and `tools/rootfile.py` refuses them rather than guessing.

## 2. The member names in the source reach the file in no form

`TCanvas::Streamer` is written as a sequence of labelled members:

```cpp
if (v>7) b.ClassMember("fDoubleBuffer", "Int_t");
b >> fDoubleBuffer;
```

**`ClassBegin`, `ClassMember` and `ClassEnd` are empty in `TBufferFile`**
(`root/io/io/inc/TBufferFile.h:95-97`). They are pure virtual on `TBuffer` and are
implemented only by `TBufferJSON` and `TBufferXML`, which need member names for
their output. In a `.root` file they emit nothing, and the `v>7` guard around them
changes no bytes either, so class version 8 has the same layout as 4 through 7.

A reader must not look for the names; they are only documentation.

### 2.1 Seven fields, eight bytes, six of them not members

`kMoveOpaque`, `kResizeOpaque`, `kShowEventStatus`, `kAutoExec` and `kMenuBar` are
bits of `fBits`, not data members, and each is written as its own `Bool_t`. On
read they are turned back into bits (`SetBit`, or `MoveOpaque(1)`).

`fBatch` is written, but on read it is consumed into a dummy and discarded
(`b >> dummy; //was fBatch`), and `fBatch` is then set from `gROOT->IsBatch()`
(`root/graf2d/gpad/src/TCanvas.cxx:2327-2338`). One byte of every canvas record is
therefore never used on read.

The seven fields occupy eight bytes, because `fHighLightColor` is two:

| Order | Field | Bytes | What it is |
|---|---|---|---|
| 1 | `kMoveOpaque` | 1 | an `fBits` flag |
| 2 | `kResizeOpaque` | 1 | an `fBits` flag |
| 3 | `fHighLightColor` | **2** | a persistent data member (`Color_t`) |
| 4 | `fBatch` | 1 | a **transient** member (`///<!`), written and discarded |
| 5 | `kShowEventStatus` | 1 | an `fBits` flag |
| 6 | `kAutoExec` | 1 | an `fBits` flag |
| 7 | `kMenuBar` | 1 | an `fBits` flag |

Six of the eight bytes, the five flags and the transient `fBatch`, correspond to
nothing a streamer info could describe. `fHighLightColor`'s two bytes are an
ordinary persistent member (`root/graf2d/gpad/inc/TCanvas.h:38`) that any info
would list.

> In practice no file has a `TCanvas` streamer info at all.
> `TCanvas::Streamer` never calls `WriteClassBuffer`
> (`root/graf2d/gpad/src/TCanvas.cxx:2221`), which is the only path that forces an
> info to be recorded, and a scan of every `StreamerInfo` record in this project's
> reference files and both corpora, 305 files, finds zero. **A reader must dispatch
> on the class name**, as for the containers of
> [TList and friends §4](Containers.md). If an info were present it would be in
> declaration order, where `fCatt` is the first member
> (`root/graf2d/gpad/inc/TCanvas.h:32`), not the last.

## 3. Three empty base classes, three different reasons

A `TCanvas` record contains, next to each other, both cases that make "an empty
base occupies nothing" false as a general rule; the third case is in
[TMap, TExMap and TBtree §6](Containers.md). All three bases are empty in the
sense that they contribute no members of their own:

| Base | `ClassDef` | `#pragma link` | Bytes | Why |
|---|---|---|---|---|
| `TQObject` | 1 | `-` (`root/core/base/inc/LinkDef2.h:131`) | **0** | hand-written `Streamer` that reads and writes nothing (`root/core/base/src/TQObject.cxx:1033-1040`) |
| `TAttBBox2D` | **0** | `+` (`root/core/base/inc/LinkDef1.h:184`) | **6** | the generated `ReadClassBuffer` streamer: byte count, then a version word of 0 |
| `TSeqCollection` | **0** | plain (`root/core/cont/inc/LinkDef.h:49`) | **0** | the version-0 forwarding streamer, which writes only its bases |

In `classes/canvas` they are adjacent:

```
317  40 00 00 60  00 03     TVirtualPad, byte count 96, version 3
323  <TObject, 10 bytes>
333  <TAttLine frame>  345 <TAttFill frame>  355 <TAttPad frame>
417                         TVirtualPad's frame ends here -- TQObject got nothing
417  40 00 00 02  00 00     TAttBBox2D: byte count 2, version 0, no members
423  fX1, the first TPad member
```

`TVirtualPad`'s streamer info has five elements, and the fifth is
`kBase TQObject` (code 0). Its byte count is 96, and `TObject` + `TAttLine` +
`TAttFill` + `TAttPad` account for all 96. Only the byte count shows that
`TQObject` occupies nothing. This makes the case recoverable, unlike `PLAN.md`
§9.9's `TTreePerfStats` case, where the same kind of surprise sits among a dozen
members under one byte count and cannot be localised.

> A modern file has no streamer info for `TQObject` at all (`classes/canvas` has
> 14 infos and `TQObject` is not among them), because nothing ever calls
> `WriteClassBuffer` for it. The element therefore names a class the file does
> not describe. `H1display.root` (ROOT 3.05) does have one, with zero elements,
> which misleads a reader in the same way.

## 4. Reading

1. Read the frame. Refuse a version below 4 or use §1.1.
2. Read the `TPad` base as an ordinary framed object through the streamer info in
   the file, with the `TQObject` rule of §3. Without that rule the read
   desynchronises inside `TVirtualPad` and never recovers.
3. Read `fDISPLAY` as a counted string, then the twelve fixed-width fields of §1
   in order.
4. Read `fCatt` as a framed `TAttCanvas`.
5. Read the eight bytes of §2.1.
6. Check the byte count.

## 5. Invariants

1. A `TCanvas` record's version word is in 1–8, and the fields of §1 consume
   exactly its byte count.
2. A `TVirtualPad` frame's byte count is exactly what its non-`TQObject` bases
   occupy: a `kBase TQObject` element contributes zero bytes.
3. `fCw` and `fCh` are positive, and `fHighLightColor` is a valid colour index
   (≥ 0).

Checked by `tools/check_invariants.py`; invariants 1 and 2 are consumption checks
raised by the reader.

## 6. Errata

| # | Claim | Correction |
|---|---|---|
| 1 | `TCanvas`'s streamer info describes its bytes | No file has one: `TCanvas::Streamer` never calls `WriteClassBuffer`, so nothing forces the info to be recorded, and zero of 305 files scanned contain it (§2.1). A reader must dispatch on the class name. Even if one were present, six of the eight trailing bytes of §2.1 are `fBits` flags or the transient `fBatch` and correspond to no element |
| 2 | A base class with no persistent members occupies nothing | It depends on why it has none. §3: 0, 6 and 0 bytes for three such classes, determined by a `ClassDef` version and a `LinkDef` suffix, neither of which is in the file |

## 7. Reference files

| File | What it pins |
|---|---|
| `classes/canvas` | §1 in full at version 8, §2.1's eight trailing bytes, and §3: `TQObject` at zero bytes and `TAttBBox2D` at six, six bytes apart. 49 KB of the record is the `TPad`'s primitives and the 800-entry list of colours a canvas holds, all of it read through streamer infos |
| `H1display.root` (`gen/cern/`) | a ROOT 3.05 canvas, whose `TQObject` info is present and empty. Not decodable here: its `TPad` is below class version 6 |
| — | `TCanvas` versions 1 to 3: needs a pre-ROOT-4 file (`PLAN.md` §9.1) |
