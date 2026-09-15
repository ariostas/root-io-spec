/// Baskets written with kGenerateOffsetMap, the one optional IO feature.
///
/// TTree::SetIOFeatures puts the feature in the tree's fIOFeatures, from which
/// each branch copies it, and each basket then records it. Two things follow,
/// and TBasket.md section 12 had no fixture for either:
///
///   - fNevBufSize is written NEGATED and a fIOBits byte follows it, so the
///     basket header is 20 bytes rather than 19 and fKeylen is 66 rather than
///     65 (TBasket.md section 2.2);
///   - the branch whose entries vary in length writes NO entry-offset array at
///     all, with flag 80, so its basket looks exactly like a fixed-length one
///     and is not. A reader must generate the offsets from the branch's leaf
///     (TBasket.md section 5.2.1).
///
/// The same two branches as ttree/basket, so the three files -- record,
/// embedded, generated -- differ in one thing each and can be compared.
///
/// This is a leaflist tree on purpose: kGenerateOffsetMap never reaches a
/// TBranchElement, because its constructors do not copy the tree's features.
/// See PLAN.md 7.1 item 3.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "generated offset map", 0);

   TTree t("t", "a tree");
   ROOT::TIOFeatures features;
   features.Set(ROOT::Experimental::EIOFeatures::kGenerateOffsetMap);
   t.SetIOFeatures(features);

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

   t.Write();
   f.Close();
}
