/// Gate 3 for `written/cluster`: ROOT reads a five-basket tree this project wrote.
///
/// The interesting part is not the values -- `written/tree` already drives
/// GetEntry -- but the two structures only a multi-basket tree has. Reading
/// entry by entry makes ROOT's binary search over fBasketEntry pick each of the
/// five baskets in turn and check that the record it finds reports the same
/// fSeekKey, which is the one consistency check it makes on a tree; and
/// GetClusterIterator walks the cluster ranges, so a wrong fClusterRangeEnd or
/// fClusterSize shows up as a boundary in the wrong place.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }
   if (f->GetNkeys() != 1)
      printf("FAIL %d keys -- no basket may be in the key list\n",
             f->GetNkeys());

   TTree *t = (TTree *)f->Get("t");
   if (!t) {
      printf("FAIL no TTree t\n");
      return;
   }
   if (t->GetEntries() != 19) printf("FAIL entries %lld\n", t->GetEntries());
   if (t->GetTotBytes() != 401)
      printf("FAIL fTotBytes %lld\n", t->GetTotBytes());
   if (t->GetAutoFlush() != 5)
      printf("FAIL fAutoFlush %lld\n", t->GetAutoFlush());
   if (t->GetAutoSave() != 3703700)
      printf("FAIL fAutoSave %lld\n", t->GetAutoSave());

   TBranch *b = t->GetBranch("x");
   if (!b) {
      printf("FAIL no branch x\n");
      return;
   }
   if (b->GetWriteBasket() != 5)
      printf("FAIL fWriteBasket %d\n", b->GetWriteBasket());
   if (b->GetMaxBaskets() != 10)
      printf("FAIL fMaxBaskets %d\n", b->GetMaxBaskets());
   if (b->GetBasketSize() != 512)
      printf("FAIL fBasketSize %d\n", b->GetBasketSize());
   if (b->GetEntryOffsetLen() != 0)
      printf("FAIL fEntryOffsetLen %d\n", b->GetEntryOffsetLen());

   // The three counted arrays, as ROOT read them back.
   const Long64_t want_entry[6] = {0, 4, 8, 11, 14, 19};
   const Int_t want_bytes[5] = {81, 81, 77, 77, 85};
   for (Int_t i = 0; i < 6; ++i)
      if (b->GetBasketEntry()[i] != want_entry[i])
         printf("FAIL fBasketEntry[%d] = %lld\n", i,
                b->GetBasketEntry()[i]);
   for (Int_t i = 0; i < 5; ++i) {
      if (b->GetBasketBytes()[i] != want_bytes[i])
         printf("FAIL fBasketBytes[%d] = %d\n", i, b->GetBasketBytes()[i]);
      if (b->GetBasketSeek(i) <= 0)
         printf("FAIL fBasketSeek[%d] = %lld\n", i, b->GetBasketSeek(i));
   }

   // Every entry, through ROOT's own basket machinery: five baskets are opened
   // and each is checked against the offset the branch recorded.
   Int_t x = -1;
   t->SetBranchAddress("x", &x);
   for (Long64_t i = 0; i < 19; ++i) {
      if (t->GetEntry(i) != 4)
         printf("FAIL entry %lld read %d bytes\n", i, t->GetEntry(i));
      if (x != (Int_t)i) printf("FAIL entry %lld x=%d\n", i, x);
   }
   // Backwards too, so the search does not simply walk forward.
   for (Long64_t i = 18; i >= 0; --i) {
      t->GetEntry(i);
      if (x != (Int_t)i) printf("FAIL reverse entry %lld x=%d\n", i, x);
   }

   // The cluster ranges: 0-3, 4-7 in range 0; 8-10, 11-13 in range 1; 14-18 in
   // the open-ended range described by fAutoFlush alone.
   const Long64_t want_start[5] = {0, 4, 8, 11, 14};
   const Long64_t want_next[5] = {4, 8, 11, 14, 19};
   TTree::TClusterIterator it = t->GetClusterIterator(0);
   Int_t n = 0;
   Long64_t start = 0;
   while ((start = it()) < t->GetEntries()) {
      if (n >= 5) {
         printf("FAIL more than five clusters\n");
         break;
      }
      if (start != want_start[n] || it.GetNextEntry() != want_next[n])
         printf("FAIL cluster %d is [%lld, %lld)\n", n, start,
                it.GetNextEntry());
      ++n;
   }
   if (n != 5) printf("FAIL %d clusters, expected 5\n", n);

   t->Draw("x", "", "goff");
   if (t->GetSelectedRows() != 19)
      printf("FAIL Draw selected %lld values\n",
             (long long)t->GetSelectedRows());

   f->Close();
   printf("VERIFY OK\n");
}
