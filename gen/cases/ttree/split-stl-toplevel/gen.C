/// A collection as the branch itself, not as a member of one.
///
/// ttree/split-nested has an fType 4 count branch that is a *member* of a split
/// class, so its fID indexes that class and its fClassName names the parent.
/// This is the other form: the collection is the whole branch, fID is -1, and
/// fClassName is therefore the collection's own type.
///
///   v          fType 4, fID -1, fClassName vector<SHit>
///     v.fId    fType 41
///     v.fE     fType 41
///
/// There is no fType 0 split node above it: a top-level collection branch is
/// itself the root of its sub-tree. That makes it the shortest split
/// arrangement ROOT produces, and the corpora hold only 34 examples of it
/// against 50 of the member form.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a top-level collection branch", 0);

   TTree t("t", "a vector as the branch itself");
   std::vector<SHit> v;
   std::vector<SHit> *p = &v;
   t.Branch("v", &p, 32000, 99);

   const Int_t sizes[3] = {2, 0, 1};
   for (int i = 0; i < 3; ++i) {
      v.clear();
      for (int j = 0; j < sizes[i]; ++j)
         v.emplace_back(100 * (i + 1) + j, 0.5f * j);
      t.Fill();
   }

   t.Write();
   f.Close();
}
