/// Gate 3 for `written/reopen-reuse`: ROOT opens a file whose update placed a
/// record into a hole an earlier session left.
///
/// The free list is the half that matters. `fits` consumed an entry exactly, so
/// if the written list still claimed that span ROOT's next write would land on
/// live data -- which is what appending an object here tests.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }

   if (f->GetEND() != 1928) printf("FAIL fEND %lld\n", (long long)f->GetEND());
   if (f->GetSeekFree() != 1053)
      printf("FAIL fSeekFree %lld\n", (long long)f->GetSeekFree());
   if (f->GetSeekInfo() != 619)
      printf("FAIL fSeekInfo %lld\n", (long long)f->GetSeekInfo());
   if (f->GetNkeys() != 4) printf("FAIL %d keys\n", f->GetNkeys());

   TString big;
   for (int i = 0; i < 8; ++i) big += "0123456789abcdef";
   big = big(0, 120);

   // The exact fit, at the offset the base's hole began.
   TKey *kf = f->GetKey("fits");
   if (!kf) {
      printf("FAIL no key 'fits'\n");
   } else {
      if (kf->GetSeekKey() != 398)
         printf("FAIL fits at %lld\n", (long long)kf->GetSeekKey());
      if (kf->GetNbytes() != 95) printf("FAIL fits fNbytes %d\n", kf->GetNbytes());
   }

   // overwrite reused the address and did not advance the cycle.
   TKey *kt = f->GetKey("tail");
   if (!kt) {
      printf("FAIL no key 'tail'\n");
   } else {
      if (kt->GetSeekKey() != 493)
         printf("FAIL tail at %lld\n", (long long)kt->GetSeekKey());
      if (kt->GetCycle() != 1) printf("FAIL tail cycle %d\n", kt->GetCycle());
   }

   TObjString *b = (TObjString *)f->Get("big");
   TObjString *fi = (TObjString *)f->Get("fits");
   TObjString *t = (TObjString *)f->Get("tail");
   TObjString *w = (TObjString *)f->Get("wide");
   if (!b || b->GetString() != "cut short, leaving a hole")
      printf("FAIL big is '%s'\n", b ? b->GetString().Data() : "(null)");
   if (!fi || fi->GetString() != "fills it up")
      printf("FAIL fits is '%s'\n", fi ? fi->GetString().Data() : "(null)");
   if (!t || t->GetString() != "shorter than what it replaces")
      printf("FAIL tail is '%s'\n", t ? t->GetString().Data() : "(null)");
   if (!w || w->GetString() != big)
      printf("FAIL wide is not the 120-character string\n");
   f->Close();

   TString copy = "build/scratch/verify-reopen-reuse.root";
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
   if (!fr || fr->GetSize() != 3) {
      printf("FAIL free list has %d entries\n", fr ? fr->GetSize() : -1);
   } else {
      TFree *a = (TFree *)fr->First();
      if (a->GetFirst() != 606 || a->GetLast() != 618)
         printf("FAIL first free entry [%lld, %lld]\n",
                (long long)a->GetFirst(), (long long)a->GetLast());
   }
   TObjString added("appended by ROOT");
   u->WriteTObject(&added, "added");
   u->Close();

   TFile *r = TFile::Open(copy);
   if (!r || r->IsZombie()) {
      printf("FAIL cannot reopen after ROOT's update\n");
      return;
   }
   TObjString *back = (TObjString *)r->Get("fits");
   TObjString *got = (TObjString *)r->Get("added");
   if (!back || back->GetString() != "fills it up")
      printf("FAIL 'fits' did not survive ROOT's update\n");
   if (!got || got->GetString() != "appended by ROOT")
      printf("FAIL the appended object did not come back\n");
   if (r->GetNkeys() != 5) printf("FAIL %d keys after the update\n", r->GetNkeys());
   r->Close();

   printf("VERIFY OK\n");
}
