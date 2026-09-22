/// The two RooFit classes whose recorded streamer info does not describe their
/// bytes, one object each and nothing else.
///
/// `RooRealVar::Streamer` (root/roofit/roofitcore/src/RooRealVar.cxx:1252) never
/// calls ReadClassBuffer, so no info for it is written at all: the file's
/// StreamerInfo record has RooAbsRealLValue and RooRealVarSharedProperties and
/// no RooRealVar. The object is a full framed object all the same, and its byte
/// count covers every byte -- including the RooRealVarSharedProperties written
/// directly at the end, which is the part no info anywhere describes.
///
/// `RooLinkedList::Streamer` (root/roofit/roofitcore/src/RooLinkedList.cxx:890)
/// opens its frame with WriteVersion(IsA()) and no byte count at all, then
/// writes its TObject base, an Int_t size, that many object slots, and a
/// TString. The info the file *does* carry for it lists a member it never
/// writes and no slots.
///
/// The RooRealVar is deliberately one that never had a shared property
/// installed, so the tail is RooRealVar::_nullProp() and the TUUID inside it is
/// all zeros (root/roofit/roofitcore/src/RooRealVar.cxx:88). A RooRealVar that
/// has been through a RooDataSet carries a real, per-run TUUID and would make
/// this fixture irreproducible.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "RooFit classes with hand-written streamers", 0);

   RooRealVar x("x", "a variable", 1.5, -2.0, 3.0);
   x.setError(0.25);
   x.Write();

   RooLinkedList l;
   l.Add(new TNamed("one", "first"));
   l.Add(new TNamed("two", "second"));
   l.Write("l");

   f.Close();
}
