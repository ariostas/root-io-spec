/// A split TClonesArray: fType 3 and fType 31, which no other fixture has.
///
/// TClonesArray predates STL streaming and splits through its own pair of
/// branch types. The arrangement mirrors the STL one of ttree/split-nested,
/// with 3 where that has 4 and 31 where it has 41:
///
///   ke                fType 0, fID -2   the split node
///   ke/fHits          fType 3           the count branch
///   ke/fHits/fId      fType 31          a member of the array's content
///   ke/fHits/fE       fType 31
///   ke/fHits/TObject  fType 31          KHit's TObject base, also a column
///
/// The TObject base is the difference from the STL case: a TClonesArray element
/// must derive from TObject, so the split produces a column for it too.
///
/// Three entries with arrays of 2, 0 and 3 elements, compression off.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a split TClonesArray", 0);

   TTree t("t", "a split TClonesArray");
   KEv ke;
   KEv *p = &ke;
   t.Branch("ke", &p, 32000, 99);

   const Int_t sizes[3] = {2, 0, 3};
   for (int i = 0; i < 3; ++i) {
      ke.fHits->Clear();
      for (int j = 0; j < sizes[i]; ++j)
         new ((*ke.fHits)[j]) KHit(100 * (i + 1) + j, 0.5f * j);
      t.Fill();
   }

   t.Write();
   f.Close();
}
