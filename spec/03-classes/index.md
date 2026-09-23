# Standard classes

Most ROOT classes need no text here. They are described by the streamer info in
the file that contains them, and
[Streamer-driven reading](../02-serialization/StreamerDriven.md) is enough to
decode them — including, in the ordinary case, every class a user defines.

> A class that keeps the `Streamer` that `ClassDef` generates is streamer-info
> driven whatever else it does, and almost all classes do. A class that replaces
> it need not be, and nothing in the file records which kind a class is. See
> [Bootstrap classes §6](../99-appendix/Bootstrap.md#6-the-list-cannot-be-closed)
> for the case that showed this and what a reader can do about it.

This layer covers only the classes whose recorded streamer info does **not**
describe their bytes, because their `Streamer` is hand-written.

## How small that set is

Many ROOT classes do have a hand-written `Streamer`, but it is a version guard
that delegates to the generated path above a threshold and keeps a legacy layout
below it:

| Class | Hand-written below | Streamer-info driven at |
|---|---|---|
| `TH1`, `TH2`, `TH3`, `TGraph` | class version 3 | version 3 and above |
| `TFormula` | 3 | 4 and above |
| `TF1` | 4 | 5 and above |
| `TAxis` | 6 | 6 and above |
| `TAttAxis` | 4 | 4 and above |
| `TTree` | 5 | 5 and above |
| `TBranch` | 10 | 10 and above |
| `TLeaf` | 2 | 2 and above |
| `TLeafObject` | 1 and 3, two different shapes | **2**, and 4 and above |
| `TLeafF16`, `TLeafD32` | — | every version, plus a title fixup below 2 |
| `TBranchElement`, `TRefTable` | — | every version |

Every version a current file contains is in the right-hand column, so
**histograms, graphs, formulas and `TTree` metadata are ordinary
streamer-info-driven objects** and need no hand-written specification. The
legacy layouts below each threshold need files older than ROOT 6 to test against
and are tracked as gaps in `PLAN.md` §9.1.

`TFormula` and `TF1` still get a document, because being streamer-info driven is
not enough there: one class *name* covers two unrelated C++ classes on either side
of ROOT 6.04, and only the version word separates them. See
[TFormula and TF1](Formula.md).

## The classes that diverge at every version

[Hand-written streamers](../99-appendix/HandWrittenStreamers.md) is the complete
list, extracted from ROOT's source: every class whose `Streamer` never calls
`ReadClassBuffer`, each resolved to the document that specifies it or recorded as
a gap. Its counts are generated and checked in CI, so they are not repeated here.

A class may also call `ReadClassBuffer` and then read further bytes of its own.
No streamer info describes those bytes and they sit outside the byte count, so the
object is longer than its byte count says and nothing warns. Three classes do
this; the one a physics file is likely to hold is `TMatrixTSym`, because a
covariance matrix is symmetric. See
[Matrices and vectors](Matrix.md) and
[Buffer framing §2.4](../02-serialization/Buffer.md#24-an-object-may-be-longer-than-its-byte-count-says).

The classes this layer indexes are specified where their behaviour arises
instead of being collected here (`PLAN.md` decision 6):

| Class | Specified in |
|---|---|
| `TObject` | [Buffer framing §7](../02-serialization/Buffer.md#7-the-tobject-base), and [References §1](../02-serialization/References.md#1-the-extra-word-on-a-referenced-tobject) for the referenced form |
| `TString` | [Conventions §5.1](../00-conventions.md#51-counted-string) |
| `TList` | [Streamer information §4](../02-serialization/StreamerInfo.md#4-tlist) |
| `TObjArray` | [Streamer information §5](../02-serialization/StreamerInfo.md#5-tobjarray) |
| `TClonesArray` | [Collections §12](../02-serialization/Collections.md#12-tclonesarray) |
| `TRef`, `TRefArray` | [References §3](../02-serialization/References.md#3-tref), [§4](../02-serialization/References.md#4-trefarray) |
| `TArray*` | [TArray](TArray.md) |
| `TMap`, `TExMap`, `TBtree` | [TMap, TExMap and TBtree](Containers.md) |
| `TCanvas`, `TQObject` | [TCanvas](Canvas.md) |
| `TMatrixTSym` | [Matrices and vectors](Matrix.md) — and `TMatrixT`, `TMatrixTSparse` and `TVectorT` beside it, which need nothing |
| `RooRealVar`, `RooLinkedList`, `RooAbsBinning`, `RooRefArray`, `RooCategory` | [RooFit](RooFit.md) — five of the six ways a RooFit file is not streamer-info driven, and the sixth is the `RooCategorySharedProperties` tail of the fifth |
| `TDatime` | [Records and keys §3.7](../01-container/Record.md#37-fdatime) — four bare bytes as a member, as in a key |
| `TCollection` | [TList and friends §3.2](Containers.md#32-the-elements-come-from-tcollection-through-a-class-that-adds-nothing) — a byte count, version 3, a bare `TObject`, `fName`, and a count. Reached inside any collection whose streamer ends in `TSeqCollection::Streamer`, `TBtree` among them |

`TFile` and `TDirectoryFile` are also hand-written, but they are the container
rather than objects in it, and belong to
[the container layer](../01-container/Directory.md).

`TBasket` has no streamer info at all and belongs with `TTree`: see
[TBasket](../04-ttree/TBasket.md).

`TBranch` and the `TLeaf` family are in the right-hand column above and so need no
hand-written layout, but what their fields *mean* is not recoverable from a
streamer info: see [TBranch](../04-ttree/TBranch.md) and
[TLeaf](../04-ttree/TLeaf.md). `TLeafF16` and `TLeafD32` are the exception:
their streamers are hand-written only to re-parse a packing annotation out of the
leaf title, which no streamer info records.

## Why there is no generated member table here

`PLAN.md` §2.4 planned generated member tables and version matrices for all ~440
persistable classes, produced by `tools/gen_tables.py` from the pinned submodule.
This layer does not need them. A generated table restates what the streamer info
in the file already says, and `tools/rootfile.py` reads that directly for 99.8%
of branch-baskets across both corpora. An unchecked generated table is worse than
a pointer to the algorithm that gets the same answer from the file.

What a reader cannot get from the file is which classes have a streamer info that
does not describe their bytes. That list is generated: `tools/inventory.py` writes
it into [Hand-written streamers](../99-appendix/HandWrittenStreamers.md).
