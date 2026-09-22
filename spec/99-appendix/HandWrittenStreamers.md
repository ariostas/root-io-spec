# Classes whose `Streamer` is hand-written

[Streamer-driven reading](../02-serialization/StreamerDriven.md) is the
specification for almost every class in a ROOT file: the `TStreamerInfo` recorded
*in the file* describes the bytes, and a reader needs no per-class knowledge to
decode them. The exception is a class that replaces the `Streamer` its `ClassDef`
would have generated — and **nothing in the file says which classes those are**.
A reader that trusts the streamer info decodes such a class into plausible
garbage, with no error and no byte count mismatch to warn it.

So the set matters, and it has to come from ROOT's source rather than from a
file. This page is that set, extracted from the pinned submodule by
`tools/inventory.py` and checked in CI, so a class that acquires or loses a
hand-written `Streamer` in a later release cannot pass unnoticed.

A **generated** `Streamer` can diverge too, in one specific way: for a class
whose version is 0 and which was selected plainly, `rootcling` writes a body that
calls its bases and returns. Those classes are the same tool's second output,
[Forwarding streamers](ForwardingStreamers.md).

<!-- BEGIN GENERATED: summary -->
| Classification | Count | What a reader has to do |
|---|---|---|
| `delegating` | 35 | nothing — the bytes are streamer-info driven |
| `guarded` | 86 | nothing for a current file; the custom layout is below a version threshold |
| `extending` | 3 | know the bytes that follow the streamer-info-driven ones, at every version |
| `custom` | 63 | know the layout; the streamer info does not describe the bytes at any version |

Of the `custom` and `extending` classes, which are the ones a reader must know:

| Status | Count |
|---|---|
| `specified` | 43 |
| `gap` | 12 |
| `not-persisted` | 5 |
| `out-of-scope` | 6 |
<!-- END GENERATED -->

## 1. Why most of them cost a reader nothing

Defining `Streamer` yourself is not the same as changing the bytes. Sorting the
definitions by what the reading branch actually does splits them four ways:

`delegating`
:   The reading branch calls `ReadClassBuffer` with no version test around it,
    and reads nothing afterwards. Whatever else the function does — rebuilding
    caches, fixing up back-pointers, re-registering objects — happens *after*
    the bytes are consumed, and the bytes themselves are exactly what the
    streamer info describes. `RooWorkspace` is the clearest case: its `Streamer`
    exists to run `ioStreamerPass2()` over every node it just read
    (`root/roofit/roofitcore/src/RooWorkspace.cxx:2540`).

`extending`
:   The reading branch calls `ReadClassBuffer` **and then reads more bytes of its
    own**. The streamer info describes a prefix of the object and stops. This is
    the one kind that looks harmless and is not: see §3.

`guarded`
:   The reading branch calls `ReadClassBuffer` above a version threshold and
    hand-decodes below it. **The call has to be inside the version test**: a
    streamer that delegates unconditionally and then consults the version only
    to repair a title or a filename is `delegating`, not `guarded`, because
    there is no legacy layout for a reader to implement. `TEntryList`,
    `TLeafF16` and `TLeafD32` are that shape and `tools/inventory.py`
    classified them as `guarded` until 2026-09-18. `TH2F` takes the generated path at class version 3
    and above and has two legacy shapes beneath it
    (`root/hist/hist/src/TH2.cxx:3977`). Every version a ROOT 6 file contains is
    on the generated side, so these cost a reader nothing *for current files*;
    the legacy layouts need a pre-6 ROOT to test against and are tracked as gaps
    in `PLAN.md` §9.1.

`custom`
:   The reading branch never calls `ReadClassBuffer`. The streamer info does not
    describe the bytes at **any** version. These need hand-written text, and a
    class here that the specification does not account for is a hole.

The counts above are the honest scope of per-class work: not "every persistable
class", and not "every class with a hand-written `Streamer`" either.

## 2. `custom` — the streamer info never describes the bytes

Every row is resolved in `streamers.toml`, and `tools/inventory.py --check`
fails on one that is not. `gap` is the worklist.

<!-- BEGIN GENERATED: custom -->
| Class | Defined | Status | Where |
|---|---|---|---|
| `REveTrans` | `root/graf3d/eve7/src/REveTrans.cxx:941` | out-of-scope | the ROOT 7 event display |
| `RModel` | `root/tmva/sofie/src/RModel.cxx:1914` | out-of-scope | TMVA SOFIE |
| `RooAbsBinning` | `root/roofit/roofitcore/src/RooAbsBinning.cxx:117` | specified | [RooFit §4.1](../03-classes/RooFit.md#41-rooabsbinning-writes-a-tnamed-it-does-not-declare) |
| `RooCFunction1Ref` | `root/roofit/roofit/inc/RooCFunction1Binding.h:145` | gap | RooFit — a persistent reference to a compiled C function, by index into a registry; no file in either corpus contains one |
| `RooCFunction2Ref` | `root/roofit/roofit/inc/RooCFunction2Binding.h:161` | gap | RooFit — a persistent reference to a compiled C function, by index into a registry; no file in either corpus contains one |
| `RooCFunction3Ref` | `root/roofit/roofit/inc/RooCFunction3Binding.h:165` | gap | RooFit — a persistent reference to a compiled C function, by index into a registry; no file in either corpus contains one |
| `RooCFunction4Ref` | `root/roofit/roofit/inc/RooCFunction4Binding.h:158` | gap | RooFit — a persistent reference to a compiled C function, by index into a registry; no file in either corpus contains one |
| `RooLinkedList` | `root/roofit/roofitcore/src/RooLinkedList.cxx:891` | specified | [RooFit §3](../03-classes/RooFit.md#3-roolinkedlist) |
| `RooRealVar` | `root/roofit/roofitcore/src/RooRealVar.cxx:1252` | specified | [RooFit §2](../03-classes/RooFit.md#2-roorealvar) |
| `RooRefArray` | `root/roofit/roofitcore/src/RooAbsArg.cxx:2195` | specified | [RooFit §4.2](../03-classes/RooFit.md#42-roorefarray-writes-a-trefarray) |
| `RooWorkspace::CodeRepo` | `root/roofit/roofitcore/src/RooWorkspace.cxx:2427` | gap | RooFit — the code repository nested inside a workspace; it blocks two records in stressRooFit_v534_ref.root |
| `TASImage` | `root/graf2d/asimage/src/TASImage.cxx:6080` | gap | graf2d; an embedded image |
| `TArrayC` | `root/core/cont/src/TArrayC.cxx:147` | specified | [TArray](../03-classes/TArray.md) |
| `TArrayD` | `root/core/cont/src/TArrayD.cxx:148` | specified | [TArray](../03-classes/TArray.md) |
| `TArrayF` | `root/core/cont/src/TArrayF.cxx:147` | specified | [TArray](../03-classes/TArray.md) |
| `TArrayI` | `root/core/cont/src/TArrayI.cxx:147` | specified | [TArray](../03-classes/TArray.md) |
| `TArrayL` | `root/core/cont/src/TArrayL.cxx:147` | specified | [TArray](../03-classes/TArray.md) |
| `TArrayL64` | `root/core/cont/src/TArrayL64.cxx:147` | specified | [TArray](../03-classes/TArray.md) |
| `TArrayS` | `root/core/cont/src/TArrayS.cxx:147` | specified | [TArray](../03-classes/TArray.md) |
| `TBasket` | `root/tree/tree/src/TBasket.cxx:979` | specified | [TBasket](../04-ttree/TBasket.md) |
| `TBranchClones` | `root/tree/tree/src/TBranchClones.cxx:386` | specified | [TBranchElement 13](../04-ttree/TBranchElement.md) |
| `TBtree` | `root/core/cont/src/TBtree.cxx:459` | specified | [TMap, TExMap and TBtree](../03-classes/Containers.md) |
| `TCanvas` | `root/graf2d/gpad/src/TCanvas.cxx:2221` | specified | [TCanvas](../03-classes/Canvas.md) |
| `TClassTree` | `root/graf2d/gpad/src/TClassTree.cxx:1102` | gap | graf2d/gpad |
| `TClonesArray` | `root/core/cont/src/TClonesArray.cxx:744` | specified | [Collections §12](../02-serialization/Collections.md#12-tclonesarray) |
| `TCollection` | `root/core/cont/src/TCollection.cxx:637` | specified | [Streamer-driven reading §7](../02-serialization/StreamerDriven.md) — reachable only through `TList`'s fictional streamer info, which no reader should follow |
| `TCollectionStreamer` | `root/io/io/src/TCollectionProxyFactory.cxx:160` | not-persisted | [Collections](../02-serialization/Collections.md) — the STL streaming machinery, never an object in a file |
| `TDatime` | `root/core/base/src/TDatime.cxx:415` | specified | [Records and keys §3.7](../01-container/Record.md#37-fdatime) |
| `TDirectory` | `root/core/base/src/TDirectory.cxx:1466` | specified | [Directory records](../01-container/Directory.md) |
| `TDirectoryFile` | `root/io/io/src/TDirectoryFile.cxx:1741` | specified | [Directory records](../01-container/Directory.md) |
| `TEmulatedCollectionProxy` | `root/io/io/src/TEmulatedCollectionProxy.cxx:629` | not-persisted | [Collections](../02-serialization/Collections.md) |
| `TEmulatedMapProxy` | `root/io/io/src/TEmulatedMapProxy.cxx:237` | not-persisted | [Collections](../02-serialization/Collections.md) |
| `TEveTrans` | `root/graf3d/eve/src/TEveTrans.cxx:941` | out-of-scope | the event display |
| `TExMap` | `root/core/cont/src/TExMap.cxx:305` | specified | [TMap, TExMap and TBtree](../03-classes/Containers.md) |
| `TFile` | `root/io/io/src/TFile.cxx:2458` | specified | [File header](../01-container/FileHeader.md) |
| `TGenCollectionProxy` | `root/io/io/src/TGenCollectionProxy.cxx:1431` | not-persisted | [Collections](../02-serialization/Collections.md) |
| `TGenCollectionStreamer` | `root/io/io/src/TGenCollectionStreamer.cxx:1389` | not-persisted | [Collections](../02-serialization/Collections.md) |
| `TGraphEdge` | `root/graf2d/gviz/src/TGraphEdge.cxx:215` | specified | [Buffer framing §2.3](../02-serialization/Buffer.md#23-a-records-object-data-does-not-always-begin-with-one) |
| `TGraphNode` | `root/graf2d/gviz/src/TGraphNode.cxx:163` | specified | [Buffer framing §2.3](../02-serialization/Buffer.md#23-a-records-object-data-does-not-always-begin-with-one) |
| `TGraphStruct` | `root/graf2d/gviz/src/TGraphStruct.cxx:307` | specified | [Buffer framing §2.3](../02-serialization/Buffer.md#23-a-records-object-data-does-not-always-begin-with-one) |
| `TKey` | `root/io/io/src/TKey.cxx:1387` | specified | [Records and keys](../01-container/Record.md) |
| `TList` | `root/core/cont/src/TList.cxx:1323` | specified | [Streamer information §4](../02-serialization/StreamerInfo.md#4-tlist) |
| `TMap` | `root/core/cont/src/TMap.cxx:360` | specified | [TMap, TExMap and TBtree](../03-classes/Containers.md) |
| `TMaterial` | `root/graf3d/g3d/src/TMaterial.cxx:80` | gap | graf3d/g3d, the pre-TGeo geometry |
| `TMixture` | `root/graf3d/g3d/src/TMixture.cxx:96` | gap | graf3d/g3d, the pre-TGeo geometry |
| `TObjArray` | `root/core/cont/src/TObjArray.cxx:448` | specified | [Streamer information §5](../02-serialization/StreamerInfo.md#5-tobjarray) |
| `TObject` | `root/core/base/src/TObject.cxx:994` | specified | [Buffer framing §7](../02-serialization/Buffer.md#7-the-tobject-base) |
| `TPolyLine3D` | `root/graf3d/g3d/src/TPolyLine3D.cxx:696` | gap | graf3d/g3d |
| `TPolyMarker3D` | `root/graf3d/g3d/src/TPolyMarker3D.cxx:617` | gap | graf3d/g3d |
| `TQObject` | `root/core/base/src/TQObject.cxx:1033` | specified | [TCanvas](../03-classes/Canvas.md) |
| `TRef` | `root/core/base/src/TRef.cxx:485` | specified | [References §3](../02-serialization/References.md#3-tref) |
| `TRefArray` | `root/core/cont/src/TRefArray.cxx:516` | specified | [References §4](../02-serialization/References.md#4-trefarray) |
| `TRemoteObject` | `root/core/base/src/TRemoteObject.cxx:206` | out-of-scope | PROOF |
| `TSQLFile` | `root/io/sql/src/TSQLFile.cxx:2667` | out-of-scope | a SQL database, not a ROOT file |
| `TStreamerArtificial` | `root/core/meta/src/TStreamerElement.cxx:2253` | specified | [Schema evolution](../02-serialization/SchemaEvolution.md) |
| `TStreamerBase` | `root/core/meta/src/TStreamerElement.cxx:851` | specified | [Streamer information §7](../02-serialization/StreamerInfo.md) |
| `TStreamerElement` | `root/core/meta/src/TStreamerElement.cxx:541` | specified | [Streamer information §7](../02-serialization/StreamerInfo.md) |
| `TStreamerInfo` | `root/io/io/src/TStreamerInfo.cxx:5608` | specified | [Streamer information](../02-serialization/StreamerInfo.md) |
| `TString` | `root/core/base/src/TString.cxx:1418` | specified | [Conventions §5.1](../00-conventions.md#51-counted-string) |
| `TStringLong` | `root/core/base/src/TStringLong.cxx:131` | specified | [Conventions 5.1.1](../00-conventions.md) |
| `TTreeIndex` | `root/tree/treeplayer/src/TTreeIndex.cxx:631` | specified | [Auxiliary structures §2](../04-ttree/Auxiliary.md) |
| `TTreeRow` | `root/tree/tree/src/TTreeRow.cxx:172` | out-of-scope | a `TSQLRow`, from the SQL backend |
| `TVirtualStreamerInfo` | `root/core/meta/src/TVirtualStreamerInfo.cxx:256` | specified | [Streamer information](../02-serialization/StreamerInfo.md) |
<!-- END GENERATED -->

## 3. `extending` — the streamer info describes a prefix and stops

Three classes call `ReadClassBuffer` and then read further bytes of their own.
They are the dangerous kind, for three reasons that compound:

- **Nothing frames the extra bytes.** They are not in the class's streamer info,
  not in any other class's, and not announced by a version word of their own.
- **They are outside the byte count.** In all three cases the byte count that
  precedes the version word covers only the streamer-info-driven part, so
  `CheckByteCount` succeeds for a reader that stops early — and for ROOT, which
  goes on reading past it.
- **The class may have no streamer info at all.** For `TMatrixTSym` ROOT records
  an info for the *base* class and none for the class itself, because the
  `Streamer` hands `ReadClassBuffer` the base's `TClass`. A reader looking the
  class up by name finds nothing.

Every row is resolved in `streamers.toml`, like `custom`.

<!-- BEGIN GENERATED: extending -->
| Class | Defined | Status | Where |
|---|---|---|---|
| `ROOT::RNTuple` | `root/tree/ntuple/src/RNTuple.cxx:25` | specified | [RNTuple](../05-rntuple/index.md) — `extending`: an 8-byte XXH3-64 checksum follows the anchor's members, outside the byte count ([errata 2 and 3](../05-rntuple/ERRATA.md)) |
| `TMatrixTSym` | `root/math/matrix/src/TMatrixTSym.cxx:2030` | specified | [Matrices and vectors](../03-classes/Matrix.md) — `extending`: the upper-right triangle follows the base class's members, outside the byte count |
| `TPointSet3D` | `root/graf3d/g3d/src/TPointSet3D.cxx:156` | gap | graf3d/g3d; `extending` — when `fOwnIds` is set, an `Int_t` count and then that many object references follow the framed part (`root/graf3d/g3d/src/TPointSet3D.cxx:156`) |
<!-- END GENERATED -->

A reader that treats these as `delegating` stops at the end of the framed part
and reports no error. That is what this page said until 2026-09-17, and the
corpora had been showing the consequence for as long: five `TMatrixTSym<double>`
records in one file, each decoding 48 bytes of 3528 or 13736 and passing every
consistency check on the way (`PLAN.md` §9.8).

## 4. `guarded` — hand-written below a version threshold

<!-- BEGIN GENERATED: guarded -->
| Class | Defined |
|---|---|
| `ROOT::v5::TF1Data` | `root/hist/hist/src/TF1Data_v5.cxx:58` |
| `ROOT::v5::TFormula` | `root/hist/hist/src/TFormula_v5.cxx:3469` |
| `RooBinning` | `root/roofit/roofitcore/src/RooBinning.cxx:298` |
| `RooCategory` | `root/roofit/roofitcore/src/RooCategory.cxx:431` |
| `RooDataHist` | `root/roofit/roofitcore/src/RooDataHist.cxx:2361` |
| `RooDataSet` | `root/roofit/roofitcore/src/RooDataSet.cxx:1576` |
| `RooFitResult` | `root/roofit/roofitcore/src/RooFitResult.cxx:1275` |
| `RooPlot` | `root/roofit/roofitcore/src/RooPlot.cxx:1323` |
| `TAttAxis` | `root/core/base/src/TAttAxis.cxx:317` |
| `TAttPad` | `root/core/base/src/TAttPad.cxx:149` |
| `TAxis` | `root/hist/hist/src/TAxis.cxx:1224` |
| `TBox` | `root/graf2d/graf/src/TBox.cxx:613` |
| `TBranch` | `root/tree/tree/src/TBranch.cxx:2968` |
| `TCTUB` | `root/graf3d/g3d/src/TCTUB.cxx:152` |
| `TCandle` | `root/graf2d/graf/src/TCandle.cxx:917` |
| `TChain` | `root/tree/tree/src/TChain.cxx:3023` |
| `TEllipse` | `root/graf2d/graf/src/TEllipse.cxx:661` |
| `TEventList` | `root/tree/tree/src/TEventList.cxx:399` |
| `TF1` | `root/hist/hist/src/TF1.cxx:3626` |
| `TF2` | `root/hist/hist/src/TF2.cxx:1056` |
| `TF3` | `root/hist/hist/src/TF3.cxx:760` |
| `TFormula` | `root/hist/hist/src/TFormula.cxx:3800` |
| `TGaxis` | `root/graf2d/graf/src/TGaxis.cxx:3028` |
| `TGeoVoxelFinder` | `root/geom/geom/src/TGeoVoxelFinder.cxx:2473` |
| `TGeometry` | `root/graf3d/g3d/src/TGeometry.cxx:572` |
| `TGraph` | `root/hist/hist/src/TGraph.cxx:2561` |
| `TGraphAsymmErrors` | `root/hist/hist/src/TGraphAsymmErrors.cxx:1410` |
| `TGraphErrors` | `root/hist/hist/src/TGraphErrors.cxx:820` |
| `TH1` | `root/hist/hist/src/TH1.cxx:7076` |
| `TH2` | `root/hist/hist/src/TH2.cxx:2818` |
| `TH2C` | `root/hist/hist/src/TH2.cxx:2999` |
| `TH2D` | `root/hist/hist/src/TH2.cxx:4250` |
| `TH2F` | `root/hist/hist/src/TH2.cxx:3977` |
| `TH2S` | `root/hist/hist/src/TH2.cxx:3262` |
| `TH3` | `root/hist/hist/src/TH3.cxx:3540` |
| `TH3C` | `root/hist/hist/src/TH3.cxx:3745` |
| `TH3D` | `root/hist/hist/src/TH3.cxx:4827` |
| `TH3F` | `root/hist/hist/src/TH3.cxx:4611` |
| `TH3S` | `root/hist/hist/src/TH3.cxx:3984` |
| `THelix` | `root/graf3d/g3d/src/THelix.cxx:596` |
| `TInetAddress` | `root/core/base/src/TInetAddress.cxx:165` |
| `TLeaf` | `root/tree/tree/src/TLeaf.cxx:481` |
| `TLeafObject` | `root/tree/tree/src/TLeafObject.cxx:191` |
| `TLine` | `root/graf2d/graf/src/TLine.cxx:496` |
| `TLorentzVector` | `root/math/physics/src/TLorentzVector.cxx:298` |
| `TMarker` | `root/graf2d/graf/src/TMarker.cxx:371` |
| `TMarker3DBox` | `root/graf3d/g3d/src/TMarker3DBox.cxx:434` |
| `TMatrixT` | `root/math/matrix/src/TMatrixT.cxx:3150` |
| `TMatrixTBase` | `root/math/matrix/src/TMatrixTBase.cxx:1057` |
| `TNode` | `root/graf3d/g3d/src/TNode.cxx:817` |
| `TNtuple` | `root/tree/tree/src/TNtuple.cxx:248` |
| `TPCON` | `root/graf3d/g3d/src/TPCON.cxx:262` |
| `TPad` | `root/graf2d/gpad/src/TPad.cxx:6641` |
| `TParticle` | `root/montecarlo/eg/src/TParticle.cxx:402` |
| `TPave` | `root/graf2d/graf/src/TPave.cxx:709` |
| `TPaveStats` | `root/graf2d/graf/src/TPaveStats.cxx:548` |
| `TPaveText` | `root/graf2d/graf/src/TPaveText.cxx:776` |
| `TPolyLine` | `root/graf2d/graf/src/TPolyLine.cxx:733` |
| `TPolyMarker` | `root/hist/hist/src/TPolyMarker.cxx:433` |
| `TProfile` | `root/hist/hist/src/TProfile.cxx:1820` |
| `TProfile2D` | `root/hist/hist/src/TProfile2D.cxx:2071` |
| `TRandom3` | `root/math/mathcore/src/TRandom3.cxx:247` |
| `TRotMatrix` | `root/graf3d/g3d/src/TRotMatrix.cxx:240` |
| `TSPHE` | `root/graf3d/g3d/src/TSPHE.cxx:270` |
| `TShape` | `root/graf3d/g3d/src/TShape.cxx:161` |
| `TSpline` | `root/hist/hist/src/TSpline.cxx:225` |
| `TSpline3` | `root/hist/hist/src/TSpline.cxx:1165` |
| `TSpline5` | `root/hist/hist/src/TSpline.cxx:2479` |
| `TStreamerBasicPointer` | `root/core/meta/src/TStreamerElement.cxx:1032` |
| `TStreamerBasicType` | `root/core/meta/src/TStreamerElement.cxx:1230` |
| `TStreamerLoop` | `root/core/meta/src/TStreamerElement.cxx:1155` |
| `TStreamerObject` | `root/core/meta/src/TStreamerElement.cxx:1373` |
| `TStreamerObjectAny` | `root/core/meta/src/TStreamerElement.cxx:1484` |
| `TStreamerObjectPointer` | `root/core/meta/src/TStreamerElement.cxx:1588` |
| `TStreamerSTL` | `root/core/meta/src/TStreamerElement.cxx:2092` |
| `TStreamerSTLstring` | `root/core/meta/src/TStreamerElement.cxx:2227` |
| `TStreamerString` | `root/core/meta/src/TStreamerElement.cxx:1753` |
| `TTUBE` | `root/graf3d/g3d/src/TTUBE.cxx:317` |
| `TText` | `root/graf2d/graf/src/TText.cxx:841` |
| `TTree` | `root/tree/tree/src/TTree.cxx:9813` |
| `TTreeFormula` | `root/tree/treeplayer/src/TTreeFormula.cxx:5209` |
| `TVector2` | `root/math/physics/src/TVector2.cxx:133` |
| `TVector3` | `root/math/physics/src/TVector3.cxx:418` |
| `TVectorT` | `root/math/matrix/src/TVectorT.cxx:2336` |
| `TView3D` | `root/graf3d/g3d/src/TView3D.cxx:1861` |
| `TVirtualPad` | `root/core/base/src/TVirtualPad.cxx:124` |
<!-- END GENERATED -->

## 5. `delegating` — custom code, generated bytes

<!-- BEGIN GENERATED: delegating -->
| Class | Defined |
|---|---|
| `PiecewiseInterpolation` | `root/roofit/histfactory/src/PiecewiseInterpolation.cxx:456` |
| `RooAbsArg` | `root/roofit/roofitcore/src/RooAbsArg.cxx:2120` |
| `RooAbsData` | `root/roofit/roofitcore/src/RooAbsData.cxx:2364` |
| `RooHistFunc` | `root/roofit/roofitcore/src/RooHistFunc.cxx:494` |
| `RooHistPdf` | `root/roofit/roofitcore/src/RooHistPdf.cxx:625` |
| `RooONNXFunc` | `root/roofit/roofit/src/RooONNXFunc.cxx:435` |
| `RooTreeDataStore` | `root/roofit/roofitcore/src/RooTreeDataStore.cxx:1091` |
| `RooVectorDataStore` | `root/roofit/roofitcore/src/RooVectorDataStore.cxx:1096` |
| `RooWorkspace` | `root/roofit/roofitcore/src/RooWorkspace.cxx:2532` |
| `TBaseClass` | `root/core/meta/src/TBaseClass.cxx:146` |
| `TBranchElement` | `root/tree/tree/src/TBranchElement.cxx:6025` |
| `TBranchObject` | `root/tree/tree/src/TBranchObject.cxx:544` |
| `TCutG` | `root/graf2d/graf/src/TCutG.cxx:429` |
| `TDataMember` | `root/core/meta/src/TDataMember.cxx:967` |
| `TEntryList` | `root/tree/tree/src/TEntryList.cxx:1645` |
| `TGeoArb8` | `root/geom/geom/src/TGeoArb8.cxx:1323` |
| `TGeoManager` | `root/geom/geom/src/TGeoManager.cxx:4060` |
| `TGeoPatternCylPhi` | `root/geom/geom/src/TGeoPatternFinder.cxx:1836` |
| `TGeoPcon` | `root/geom/geom/src/TGeoPcon.cxx:1767` |
| `TGeoTessellated` | `root/geom/geom/src/TGeoTessellated.cxx:1380` |
| `TGeoVGShape` | `root/geom/vecgeom/src/TGeoVGShape.cxx:492` |
| `TGeoVolume` | `root/geom/geom/src/TGeoVolume.cxx:2252` |
| `TGraph2D` | `root/hist/hist/src/TGraph2D.cxx:1806` |
| `TGraph2DAsymmErrors` | `root/hist/hist/src/TGraph2DAsymmErrors.cxx:661` |
| `TGraph2DErrors` | `root/hist/hist/src/TGraph2DErrors.cxx:505` |
| `TKDTreeBinning` | `root/math/mathcore/src/TKDTreeBinning.cxx:674` |
| `TLeafD32` | `root/tree/tree/src/TLeafD32.cxx:205` |
| `TLeafF16` | `root/tree/tree/src/TLeafF16.cxx:218` |
| `TLinearFitter` | `root/math/minuit/src/TLinearFitter.cxx:1939` |
| `TListOfDataMembers` | `root/core/meta/src/TListOfDataMembers.cxx:529` |
| `TMatrixTSparse` | `root/math/matrix/src/TMatrixTSparse.cxx:2991` |
| `TNtupleD` | `root/tree/tree/src/TNtupleD.cxx:228` |
| `TRefTable` | `root/core/cont/src/TRefTable.cxx:390` |
| `TSchemaRuleSet` | `root/core/meta/src/TSchemaRuleSet.cxx:561` |
| `TStreamerObjectAnyPointer` | `root/core/meta/src/TStreamerElement.cxx:1691` |
<!-- END GENERATED -->

## 6. What this means for a base class

A `kBase` element does **not** mean "read the base class by its streamer info".
`TStreamerBase::ReadBuffer` dispatches to the base class's own `Streamer`
whenever the class has one — `fStreamerFunc`, taken from
`TClass::GetStreamerFunc()` at `root/core/meta/src/TStreamerElement.cxx:760` and
called at `:820` — and falls back to `ReadClassBuffer`, with the version word
that implies, only when there is none.

So a base contributes whatever its `Streamer` writes, and the table above is the
list of cases where that is not what its streamer info says. The extreme is
`TQObject`, whose `Streamer` reads nothing and writes nothing in either
direction (`root/core/base/src/TQObject.cxx:1033-1040`): a `TQObject` base
occupies **zero bytes**, not a framed empty object and not a bare version word.

That resolves the `H1display.root` reading recorded in `PLAN.md` §9.9. A `TPad`
in that file has a `TVirtualPad` v2 base listing five `kBase` elements ending in
`TQObject`, and counting bytes showed `TObject` + `TAttLine` + `TAttFill` +
`TAttPad` exhausting the frame with nothing left for `TQObject`. The bytes were
right. The question the note left open — "what does a `kBase` element whose class
has no persistent members occupy on disk?" — was the wrong question: it is not
about having no members. `TQObject` contributes nothing because its `Streamer`
was written to contribute nothing, and a class with no members whose `Streamer`
is generated from a `ClassDef` above 0 still writes a byte count and a version
word. That is not true of every generated streamer: the 534 classes of
[Forwarding streamers](ForwardingStreamers.md) write **neither**, which is the
case that document exists for.

**A reader cannot derive this from the file.** The file even carries a
`TQObject` streamer info, with zero elements, which is precisely the fiction
[Streamer-driven reading §7](../02-serialization/StreamerDriven.md) describes.
The class name is the only signal, which is what this page is for.

## 7. What the extraction does and does not see

`tools/inventory.py` reads the submodule's sources with comments and string
literals blanked out, so that neither can be mistaken for code. Both cases are
real:

- `TStreamerInfo::Streamer` has its `ReadClassBuffer` call **commented out** and
  replaced by a hand-written sequence (`root/io/io/src/TStreamerInfo.cxx:5615`).
  Counting the commented line would classify the format's own bootstrap class as
  needing no specification.
- `ROOT::v5::TFormula` is defined inside `namespace ROOT { namespace v5 {`, so
  its definition is written unqualified and reads as `TFormula`
  (`root/hist/hist/src/TFormula_v5.cxx:3469`). The current `TFormula` is a
  different class with a different classification, and merging them would hide
  one behind the other. Namespaces are tracked by brace, which is only sound once
  braces inside string literals are gone — and that file parses formula syntax.
- The opposite spelling has to be handled too. `ROOT::RNTuple::Streamer` is
  defined **qualified**, at file scope with no `namespace` block around it
  (`root/tree/ntuple/src/RNTuple.cxx:25`), and so is
  `RooWorkspace::CodeRepo::Streamer`
  (`root/roofit/roofitcore/src/RooWorkspace.cxx:2427`). Matching only an
  unqualified name dropped both from this page entirely — including the one class
  in §3 that the RNTuple specification already documents.
- A version dispatch need not be a comparison. `RooBinning` selects its layout
  with `switch (R__v)` and hand-decodes version 1 in a `case`
  (`root/roofit/roofitcore/src/RooBinning.cxx:298`); tested for comparisons alone
  it read as `delegating`, which is the reading that tells a reader it needs
  nothing.

Two declarations are deliberately **not** counted:
`TParameter<Long64_t>::Streamer` and `TNDArrayT<double>::Streamer` are forward
declarations with no body, added so a `-fmodules` build can compile the
dictionary (`root/core/base/inc/TParameter.h:195-203`). The definitions are
generated. A plain grep reports both as hand-written and sends a reader to
specify two classes that need nothing.

What it does not see: a class whose bytes come from an *adopted* streamer —
`TClass::AdoptStreamer`, the `extstrm` branch at
`root/core/meta/src/TStreamerElement.cxx:826` — rather than from a `Streamer`
member function. The STL collection proxies in §2 reach files that way, and they
are in the table because they also define `Streamer`; a class that used only the
adopted path would not be. No such class is known here, and the gap is recorded
rather than assumed away.

## 8. Reference files

This page is derived from the pinned submodule, not from bytes, and is checked
against it rather than against a fixture. The byte-level evidence for §6 is the
`H1display.root` reading in `PLAN.md` §9.9, over a file in `gen/cern/`.
