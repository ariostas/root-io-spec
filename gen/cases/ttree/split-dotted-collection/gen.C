/// The same split collection under a name ending in a dot and one that does not.
///
/// For a split *object*, a trailing dot changes every name below the branch
/// (ttree/split-naming). For a top-level split *collection* it changes nothing:
/// TBranchElement::Init removes the dot before anything is named
/// (root/tree/tree/src/TBranchElement.cxx:906-909), so both halves come out in
/// the same shape.
///
///   Branch("v.", ...)             Branch("w", ...)
///   v        title v_             w        title w_
///     v.fId  title fId[v_]          w.fId  title fId[w_]
///     v.fE   title fE[v_]           w.fE   title fE[w_]
///
/// One entry, compression off, so the whole TTree record is assertable.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a split collection under a trailing dot", 0);

   TTree t("t", "one collection under two branch names");
   std::vector<DHit> v, w;
   t.Branch("v.", &v, 32000, 99);
   t.Branch("w", &w, 32000, 99);

   v.emplace_back(1, 1.5f);
   v.emplace_back(2, 2.5f);
   w.emplace_back(3, 3.5f);
   t.Fill();

   t.Write();
   f.Close();
}
