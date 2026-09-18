/// Gate 3 for `written/tree`: ROOT reads a TTree this project wrote.
///
/// This is the strongest read-back in the repository, because it drives ROOT's
/// own basket, leaf and branch code over bytes tools/rootwrite.py produced --
/// GetEntry resolves fBasketSeek, reads the basket key, positions the buffer
/// from the offset array, and hands each leaf its slice; Draw goes through
/// TTreeFormula, which is the only thing that reads a leaf's fTitle.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }
   if (f->GetNkeys() != 1)
      printf("FAIL %d keys -- a basket must not be in the key list\n",
             f->GetNkeys());

   TTree *t = (TTree *)f->Get("t");
   if (!t) {
      printf("FAIL no TTree t\n");
      return;
   }
   if (t->GetEntries() != 3) printf("FAIL entries %lld\n", t->GetEntries());
   if (t->GetNbranches() != 2)
      printf("FAIL %d branches\n", t->GetNbranches());
   if (t->GetTotBytes() != 186) printf("FAIL fTotBytes %lld\n", t->GetTotBytes());
   if (t->GetWeight() != 1.0) printf("FAIL fWeight %g\n", t->GetWeight());

   TBranch *bn = t->GetBranch("n");
   TBranch *ba = t->GetBranch("a");
   if (!bn || !ba) {
      printf("FAIL a branch is missing\n");
      return;
   }
   if (bn->GetWriteBasket() != 1)
      printf("FAIL fWriteBasket %d\n", bn->GetWriteBasket());
   if (bn->GetEntryOffsetLen() != 0)
      printf("FAIL n fEntryOffsetLen %d\n", bn->GetEntryOffsetLen());
   if (ba->GetEntryOffsetLen() == 0)
      printf("FAIL a fEntryOffsetLen is 0, so its offsets would not be read\n");

   // The leaf and its counter: the object reference in fLeafCount has to have
   // resolved for this to be non-null.
   TLeaf *la = t->GetLeaf("a");
   if (!la || !la->GetLeafCount())
      printf("FAIL leaf a has no counter\n");
   else if (strcmp(la->GetLeafCount()->GetName(), "n") != 0)
      printf("FAIL leaf a's counter is %s\n", la->GetLeafCount()->GetName());
   TLeaf *ln = t->GetLeaf("n");
   if (ln && ln->GetMaximum() != 3)
      printf("FAIL leaf n fMaximum %d\n", ln->GetMaximum());

   // Read every entry, through ROOT's own basket machinery.
   Int_t n = 0;
   Float_t a[16];
   t->SetBranchAddress("n", &n);
   t->SetBranchAddress("a", a);
   const Int_t want_bytes[3] = {8, 12, 16};
   for (Long64_t i = 0; i < 3; ++i) {
      Int_t got = t->GetEntry(i);
      if (got != want_bytes[i])
         printf("FAIL entry %lld read %d bytes, expected %d\n", i, got,
                want_bytes[i]);
      if (n != i + 1) printf("FAIL entry %lld n=%d\n", i, n);
      for (Int_t j = 0; j < n; ++j)
         if (a[j] != (Float_t)i)
            printf("FAIL entry %lld a[%d]=%g\n", i, j, a[j]);
   }

   // And through TTreeFormula, which reads the leaf titles.
   t->Draw("a", "", "goff");
   if (t->GetSelectedRows() != 6)
      printf("FAIL Draw selected %lld values, expected 6\n",
             (long long)t->GetSelectedRows());
   t->Draw("n", "", "goff");
   if (t->GetSelectedRows() != 3)
      printf("FAIL Draw on n selected %lld values\n",
             (long long)t->GetSelectedRows());

   f->Close();
   printf("VERIFY OK\n");
}
