/// Baskets written inside the TTree record instead of as records of their own.
///
/// TTree::Write flushes every basket first, so a tree written the ordinary way
/// never embeds one. TDirectory::WriteTObject does not go through that override,
/// so the baskets are still in memory when TBranch::Streamer runs, and
/// TBranch::Streamer only nulls the slots of baskets that are already on disk or
/// empty, and these are neither. The result is the second shape of TBasket.md
/// section 4: the key, the header, the entry-offset array and the data all
/// inline, in one object slot inside fBaskets.
///
/// The same two branches as ttree/basket, so the two files differ only in how
/// the baskets were written and can be compared field by field. This file has no
/// TBasket record at all.
///
/// This is not rare: the probe of PLAN.md section 9.8 found embedded baskets in
/// files from ROOT 4.00 and 5.34, one of them with eighty in a single tree.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "embedded baskets", 0);

   TTree t("t", "a tree");
   Int_t n;
   Float_t a[3];
   t.Branch("n", &n, "n/I");
   t.Branch("a", a, "a[n]/F");

   for (int i = 0; i < 3; ++i) {
      n = i + 1;
      for (int j = 0; j < n; ++j)
         a[j] = (float)i;
      t.Fill();
   }

   f.WriteTObject(&t, "t");
   f.Close();
}
