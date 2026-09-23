/// The only branch kind with no fixture: `TBranchClones`.
///
/// Nothing in ROOT's modern API produces one. `TTree::Branch` gives a
/// `TBranchElement`; only `TTree::BranchOld` does, and only for a
/// `TClonesArray*` data member at a split level other than 2
/// (`root/tree/tree/src/TTree.cxx:2216-2227`). The tree is therefore built with
/// `BranchOld`, which also makes the parent a `TBranchObject`, the other branch
/// class the corpora do not cover.
///
/// Three entries with one, two and three hits, so the count branch is not
/// constant and `fN` differs from the entry number.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a TBranchClones", 0);

   TTree t("t", "one TBranchClones");
   CEvtC *e = new CEvtC();
   t.BranchOld("ev", "CEvtC", &e, 32000, 1);

   for (Int_t entry = 0; entry < 3; entry++) {
      e->fHits->Clear();
      for (Int_t i = 0; i <= entry; i++)
         new ((*e->fHits)[i]) CHitC(i, 0.5f * i);
      e->fN = entry + 1;
      t.Fill();
   }

   t.Write();
   f.Close();
}
