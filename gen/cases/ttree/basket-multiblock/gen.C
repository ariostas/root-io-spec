/// A basket whose payload is split into two compression blocks.
///
/// TBasket.md 7: "TBasket performs its own multi-block splitting with the same
/// constants as the container layer", and the constant is kMAXZIPBUF = 0xffffff
/// (`root/core/zip/inc/RZip.h:40`). So a basket needs more than 16 MB of
/// UNCOMPRESSED payload to have two blocks -- which is why no fixture had one.
///
/// The way to commit it is to make the payload compress hard: 2.1M Double_t all
/// equal, 16.8 MB, which LZMA at level 9 stores in under 3 KB. The file is a
/// few kilobytes and the block structure is the real thing.
///
/// One entry, because the point is the size of one basket rather than the
/// number of them, and SetBasketSize keeps it in one.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a multi-block basket", 0);
   f.SetCompressionAlgorithm(ROOT::RCompressionSetting::EAlgorithm::kLZMA);
   f.SetCompressionLevel(9);

   TTree t("t", "one basket over 16 MB");

   const Int_t N = 2100000;              // x 8 bytes = 16 800 000 > 0xffffff
   Double_t *a = new Double_t[N];
   for (Int_t i = 0; i < N; ++i) a[i] = 0.5;
   Int_t n = N;

   t.Branch("n", &n, "n/I");
   TBranch *b = t.Branch("a", a, "a[n]/D");
   b->SetBasketSize(20000000);

   t.Fill();
   t.Write();
   f.Close();

   delete [] a;
}
