/// Gate 3 for `written/reused-space`: ROOT opens a file whose records were
/// placed into released space rather than appended.
///
/// The free list is the important half. ROOT reads it only when the file is
/// opened writable (root/io/io/src/TFile.cxx:769-775), and then allocates
/// against it. If our interior entry named the wrong span, or if the remainder
/// marker at 696 disagreed with it, ROOT's next write would land on live data.
/// Appending an object here tests that, and the three original objects are
/// read back afterwards to show nothing was overwritten.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }

   if (f->GetEND() != 1747) printf("FAIL fEND %lld\n", (long long)f->GetEND());
   if (f->GetSeekFree() != 1646)
      printf("FAIL fSeekFree %lld\n", (long long)f->GetSeekFree());
   if (f->GetNbytesFree() != 101) printf("FAIL fNbytesFree %d\n", f->GetNbytesFree());
   if (f->GetNkeys() != 4) printf("FAIL %d keys\n", f->GetNkeys());

   // The exact fit: `exact` is back at the offset its first version had, and
   // it is 213 bytes there, which made the fit exact.
   TKey *ke = f->GetKey("exact");
   if (!ke) {
      printf("FAIL no key 'exact'\n");
   } else {
      if (ke->GetSeekKey() != 290)
         printf("FAIL exact fSeekKey %lld\n", (long long)ke->GetSeekKey());
      if (ke->GetNbytes() != 213) printf("FAIL exact fNbytes %d\n", ke->GetNbytes());
   }

   // The partial fit: `lodger` sits inside the span `snug` released.
   TKey *kl = f->GetKey("lodger");
   if (!kl) {
      printf("FAIL no key 'lodger'\n");
   } else if (kl->GetSeekKey() != 592) {
      printf("FAIL lodger fSeekKey %lld\n", (long long)kl->GetSeekKey());
   }

   TString big;
   for (int i = 0; i < 8; ++i) big += "0123456789abcdef";

   TObjString *e = (TObjString *)f->Get("exact");
   TObjString *s = (TObjString *)f->Get("snug");
   TObjString *l = (TObjString *)f->Get("lodger");
   TObjString *t = (TObjString *)f->Get("tail");
   if (!e || e->GetString() != big) printf("FAIL exact is not the long string\n");
   if (!s || s->GetString() != "short") printf("FAIL snug is not 'short'\n");
   if (!l || l->GetString() != "inside snug's span")
      printf("FAIL lodger is '%s'\n", l ? l->GetString().Data() : "(null)");
   if (!t) printf("FAIL no tail\n");
   f->Close();

   // Now the free list, which needs a writable open.
   TString copy = "build/scratch/verify-reused-space.root";
   gSystem->mkdir("build/scratch", kTRUE);
   if (gSystem->CopyFile(path, copy, kTRUE) != 0) {
      printf("FAIL cannot copy to %s\n", copy.Data());
      return;
   }

   TFile *u = TFile::Open(copy, "UPDATE");
   if (!u || u->IsZombie()) {
      printf("FAIL cannot reopen %s for UPDATE\n", copy.Data());
      return;
   }
   TList *fr = u->GetListOfFree();
   if (!fr || fr->GetSize() != 2) {
      printf("FAIL free list has %d entries\n", fr ? fr->GetSize() : -1);
   } else {
      TFree *a = (TFree *)fr->First();
      TFree *b = (TFree *)fr->Last();
      // The remainder, inclusive, as the marker at 696 says.
      if (a->GetFirst() != 696 || a->GetLast() != 714)
         printf("FAIL interior free entry [%lld, %lld]\n",
                (long long)a->GetFirst(), (long long)a->GetLast());
      if (b->GetFirst() != 1747 || b->GetLast() != 2000000000)
         printf("FAIL trailing free entry [%lld, %lld]\n",
                (long long)b->GetFirst(), (long long)b->GetLast());
   }
   TObjString added("appended by ROOT");
   u->WriteTObject(&added, "added");
   u->Close();

   TFile *r = TFile::Open(copy);
   if (!r || r->IsZombie()) {
      printf("FAIL cannot reopen %s after the update\n", copy.Data());
      return;
   }
   TObjString *back = (TObjString *)r->Get("exact");
   TObjString *added2 = (TObjString *)r->Get("added");
   if (!back || back->GetString() != big)
      printf("FAIL 'exact' did not survive ROOT's update\n");
   if (!added2 || added2->GetString() != "appended by ROOT")
      printf("FAIL the appended object did not come back\n");
   if (r->GetNkeys() != 5) printf("FAIL %d keys after the update\n", r->GetNkeys());
   r->Close();

   printf("VERIFY OK\n");
}
