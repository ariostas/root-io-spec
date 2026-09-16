/// The other half of `classes/tarray`: a file that DOES carry a TStreamerInfo
/// for a concrete TArray, so that TArray.md 2's "wrong by one byte" claim is
/// checkable against real bytes rather than asserted.
///
/// Writing a TH2F is not enough. A TH2F written with Write(), or held in a
/// TObjArray, produces fifteen streamer infos and none of them is TArrayF --
/// TH1's hand-written Streamer never asks for it. Putting the TH2F in a TTree
/// branch does produce it, because creating the branch builds the streamer
/// info of every class in the hierarchy.
///
/// 5 x 5 bins, so the TArrayF base has fN = (5+2) * (5+2) = 49 and occupies
/// 4 + 49 * 4 = 200 bytes, where the recorded info would read 201.
///
/// One entry, and two bins filled so the payload is not all zeros. The tree is
/// a vehicle for the branch; TBasket and TBranch have cases of their own.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a TArray streamer info", 0);

   TTree t("t", "one TH2F");
   TH2F *h = new TH2F("h", "h", 5, 0., 1., 5, 0., 1.);
   t.Branch("h", "TH2F", &h);

   h->SetBinContent(1, 1, 0.5f);
   h->SetBinContent(2, 3, 1.5f);
   t.Fill();

   t.Write();
   f.Close();
}
