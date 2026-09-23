/// A compressed basket.
///
/// Every other ttree case writes with compression 0 so its bytes can be
/// asserted directly. This one is the exception TBasket.md 7 needs: the
/// entry-offset array is appended to the basket's buffer before the buffer is
/// compressed, so it is inside the compressed payload and a reader cannot
/// reach it without decompressing the whole basket.
///
/// zlib at level 1, which is what a ROOT file uses by default. Two branches,
/// the same pair as ttree/basket: a fixed-width one with no offset array and a
/// variable-length one with it, so the compressed payload can be compared
/// against the uncompressed layout that case asserts.
///
/// The entries are long runs of one value so the payload compresses. The case is
/// about the block header and where the offset array sits, not the codec's
/// output.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a compressed basket", 0);
   f.SetCompressionAlgorithm(ROOT::RCompressionSetting::EAlgorithm::kZLIB);
   f.SetCompressionLevel(1);

   TTree t("t", "compressed baskets");
   Int_t n = 0;
   Float_t a[300];
   t.Branch("n", &n, "n/I");
   t.Branch("a", a, "a[n]/F");

   for (Int_t e = 0; e < 3; ++e) {
      n = 100 * (e + 1);
      for (Int_t i = 0; i < n; ++i) a[i] = 0.5f;
      t.Fill();
   }

   t.Write();
   f.Close();
}
