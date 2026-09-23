/// Three levels of splitting, and the count-branch convention.
///
/// NTop holds an NDet, which holds a std::vector<NHit>. Split, that is the
/// shape of a real physics branch in miniature:
///
///   nt            fType 0, fID -2   the split node
///   nt/fDet       fType 2           a class-typed member; no leaf, no basket
///   nt/fDet/fNo   fType 0
///   nt/fDet/fHits fType 4           the collection count branch
///   nt/fDet/fHits/fId  fType 41     a member of the collection's content
///   nt/fDet/fHits/fE   fType 41
///   nt/fRun       fType 0
///
/// What it covers:
///
/// - fType 2 is the second of the two interior node types, and like fType 1 it
///   has no leaf and no basket.
/// - The count branch's title ends in an underscore, and the member branches'
///   leaf titles name it in brackets: `fId[fHits_]`. That is the only place
///   the count relationship is written in a form a human can read; the
///   machine-readable form is each member branch's fBranchCount.
/// - fSplitLevel decrements with depth, so the same tree has several values.
///
/// Three entries with collections of three different sizes, one of them empty,
/// and compression off.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "three levels of splitting", 0);

   TTree t("t", "a nested split object");
   NTop nt;
   NTop *p = &nt;
   t.Branch("nt", &p, 32000, 99);

   const Int_t sizes[3] = {2, 0, 1};
   for (int i = 0; i < 3; ++i) {
      nt.fDet.fNo = 10 + i;
      nt.fDet.fHits.clear();
      for (int j = 0; j < sizes[i]; ++j)
         nt.fDet.fHits.emplace_back(100 * (i + 1) + j, 0.5f * j);
      nt.fRun = 7 + i;
      t.Fill();
   }

   t.Write();
   f.Close();
}
