/// A branch whose fFirstEntry is not 0.
///
/// TBranch::SetFirstEntry is called from exactly one place in ROOT that is not
/// a user: TBranchSTL::Fill, when it meets an object class it has not seen
/// before and creates a sub-branch for it mid-stream
/// (root/tree/tree/src/TBranchSTL.cxx:285). The new sub-branch is told the
/// entry number it was born at, and that number reaches disk.
///
/// A TBranchSTL is built only for a TOP-LEVEL branch of a collection with
/// pointers, at a split level above TTree::kSplitCollectionOfPointers
/// (root/tree/tree/src/TTree.cxx:2516-2518). ttree/split-ptr-collection has the
/// other shape -- the same collection as a member of a holder class -- which
/// goes through TBranchElement instead and never reaches this code.
///
/// So: two empty entries, then two with a hit. The sub-branch is created at
/// entry 2 and carries fFirstEntry 2, while the top-level branch has 0.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a branch born mid-stream", 0);

   TTree t("t", "fFirstEntry");
   std::vector<FHit *> v;
   std::vector<FHit *> *vp = &v;   // TBranchSTL needs the pointer-to-pointer
   t.Branch("v", &vp, 32000, TTree::kSplitCollectionOfPointers + 1);

   for (int i = 0; i < 4; ++i) {
      for (auto *p : v) delete p;
      v.clear();
      if (i >= 2)
         v.push_back(new FHit(10 * i, 0.5f * i));
      t.Fill();
   }
   for (auto *p : v) delete p;
   v.clear();

   t.Write();
   f.Close();
}
