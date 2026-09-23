/// One branch whose entries do not fit in a single basket.
///
/// The basket size is 100, which is TBranch's minimum, so twenty four-byte
/// entries need three baskets of 8, 8 and 4. With more than one basket the three
/// parallel arrays fBasketBytes, fBasketEntry and fBasketSeek hold real values,
/// and fBasketEntry[fWriteBasket] is the terminator the entry-to-basket search
/// relies on.
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
