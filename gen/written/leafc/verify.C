/// Gate 3 for `written/leafc`: ROOT reads a TLeafC branch this project wrote.
///
/// The empty string is the important case. It occupies no bytes in the basket,
/// so ROOT recovers it from the entry-offset array alone. The buffer is filled
/// with a sentinel before every GetEntry here, so a value ROOT leaves untouched
/// fails rather than passing on the previous entry's contents.
///
/// Any ROOT output on either stream also fails the case.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }

   if (f->GetEND() != 16878) printf("FAIL fEND %lld\n", (long long)f->GetEND());
   if (f->GetSeekInfo() != 2039)
      printf("FAIL fSeekInfo %lld\n", (long long)f->GetSeekInfo());
   // The baskets are deliberately not in the key list.
   if (f->GetNkeys() != 1) printf("FAIL %d keys\n", f->GetNkeys());

   TTree *t = (TTree *)f->Get("t");
   if (!t) {
      printf("FAIL no TTree at key 't'\n");
      return;
   }
   if (t->GetEntries() != 3)
      printf("FAIL %lld entries\n", (long long)t->GetEntries());

   // A TLeafC forces an offset array; a fixed-width branch has none.
   TBranch *bs = t->GetBranch("s");
   TBranch *bn = t->GetBranch("n");
   if (!bs || !bn) {
      printf("FAIL a branch is missing\n");
      return;
   }
   if (bn->GetEntryOffsetLen() != 0)
      printf("FAIL n fEntryOffsetLen %d\n", bn->GetEntryOffsetLen());
   if (bs->GetEntryOffsetLen() != 12)
      printf("FAIL s fEntryOffsetLen %d\n", bs->GetEntryOffsetLen());
   if (bs->GetBasketSeek(0) != 345)
      printf("FAIL s fBasketSeek[0] %lld\n", (long long)bs->GetBasketSeek(0));
   if (bs->GetZipBytes() != 393)
      printf("FAIL s fZipBytes %lld\n", (long long)bs->GetZipBytes());

   // The leaf's two high-water marks, both the longest string plus one.
   TLeafC *lf = (TLeafC *)t->GetLeaf("s");
   if (!lf) {
      printf("FAIL no leaf 's'\n");
      return;
   }
   if (strcmp(lf->ClassName(), "TLeafC") != 0)
      printf("FAIL leaf class %s\n", lf->ClassName());
   if (lf->GetLen() != 301) printf("FAIL fLen %d\n", lf->GetLen());
   if (lf->GetLenType() != 1) printf("FAIL fLenType %d\n", lf->GetLenType());
   if (lf->GetMaximum() != 301) printf("FAIL fMaximum %d\n", lf->GetMaximum());
   if (lf->IsRange()) printf("FAIL fIsRange is set on a TLeafC\n");

   // The values. TString rather than char[] so the sentinel is visible.
   char s[512];
   Int_t n = 0;
   t->SetBranchAddress("n", &n);
   t->SetBranchAddress("s", s);
   const char *want[3] = {"ab", "", nullptr};
   TString longest('x', 300);
   for (int i = 0; i < 3; ++i) {
      memset(s, 'Z', sizeof s);
      t->GetEntry(i);
      if (n != i + 1) printf("FAIL entry %d: n is %d\n", i, n);
      TString got(s);
      TString expect = want[i] ? TString(want[i]) : longest;
      if (got != expect)
         printf("FAIL entry %d: string is '%s' (%d chars), expected %d\n",
                i, got.Data(), got.Length(), expect.Length());
   }
   t->ResetBranchAddresses();
   f->Close();

   printf("VERIFY OK\n");
}
