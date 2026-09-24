/// A split collection whose value class has no data members, beside one whose
/// value class has one.
///
/// A split collection's count leaf is written through the first sub-branch's
/// fLeafCount, because TBranch streams fBranches before fLeaves, so the
/// collection's own fLeaves entry is a back-reference. With no data members
/// there is no sub-branch, and the leaf is written in place.
///
///   e   fType 4, no sub-branches, leaf e_ written in full
///   p   fType 4, sub-branch p.fId, leaf p_ a back-reference
///
/// Three entries of 0, 1 and 2 elements, compression off.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a split collection with no sub-branches", 0);

   TTree t("t", "two split collections");
   std::vector<EHit> e;
   std::vector<PHit> p;
   t.Branch("e", &e, 32000, 99);
   t.Branch("p", &p, 32000, 99);

   for (int i = 0; i < 3; ++i) {
      e.resize(i);
      p.clear();
      for (int k = 0; k < i; ++k) p.emplace_back(10 * i + k);
      t.Fill();
   }

   t.Write();
   f.Close();
}
