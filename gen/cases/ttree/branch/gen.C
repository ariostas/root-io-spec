/// One branch whose entries do not fit in a single basket.
///
/// The basket size is 100, which is TBranch's minimum, so twenty four-byte
/// entries need three baskets of 8, 8 and 4. That is the point of the case:
/// with more than one basket the three parallel arrays fBasketBytes,
/// fBasketEntry and fBasketSeek carry real values, and fBasketEntry[fWriteBasket]
/// is the terminator that makes the entry-to-basket search work.
///
/// Compression is off so the TTree record can be asserted byte for byte.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "branch basket arrays", 0);

   TTree t("t", "a tree");
   Int_t x;
   t.Branch("x", &x, "x/I", 100);

   for (int i = 0; i < 20; ++i) {
      x = 100 + i;
      t.Fill();
   }

   t.Write();
   f.Close();
}
