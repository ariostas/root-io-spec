/// Gate 3 for `written/objstring`: ROOT opens a file this project wrote.
///
/// It checks the container fields ROOT recovers from the header and the
/// directory record, then the object itself. Anything ROOT says on either
/// stream fails the case too -- see ROOT_DIAGNOSTICS in tools/check_write.py --
/// so the absence of output is half the assertion.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }

   // The header, as TFile::Init parsed it.
   if (f->GetVersion() != 64004) printf("FAIL fVersion %d\n", f->GetVersion());
   if (f->GetEND() != 656) printf("FAIL fEND %lld\n", (long long)f->GetEND());
   if (f->GetSeekFree() != 556) printf("FAIL fSeekFree %lld\n", (long long)f->GetSeekFree());
   if (f->GetNbytesFree() != 100) printf("FAIL fNbytesFree %d\n", f->GetNbytesFree());
   if (f->GetSeekInfo() != 0) printf("FAIL fSeekInfo %lld\n", (long long)f->GetSeekInfo());
   if (f->GetCompressionSettings() != 0)
      printf("FAIL fCompress %d\n", f->GetCompressionSettings());

   // The key list.
   if (f->GetNkeys() != 1) printf("FAIL %d keys\n", f->GetNkeys());
   TKey *k = (TKey *)f->GetListOfKeys()->First();
   if (k) {
      if (strcmp(k->GetClassName(), "TObjString") != 0)
         printf("FAIL key class %s\n", k->GetClassName());
      if (k->GetSeekKey() != 308)
         printf("FAIL key fSeekKey %lld\n", (long long)k->GetSeekKey());
      if (k->GetNbytes() != 88) printf("FAIL key fNbytes %d\n", k->GetNbytes());
      if (k->GetObjlen() != 22) printf("FAIL key fObjlen %d\n", k->GetObjlen());
      if (k->GetCycle() != 1) printf("FAIL key fCycle %d\n", k->GetCycle());
      // The fixed timestamp, 2000-01-01 00:00:00.
      if (k->GetDatime().GetDate() != 20000101 || k->GetDatime().GetTime() != 0)
         printf("FAIL key fDatime %d/%d\n",
                k->GetDatime().GetDate(), k->GetDatime().GetTime());
   }

   // And the object. This is the part that drives ROOT's own streamer over
   // bytes tools/rootwrite.py produced.
   TObjString *s = (TObjString *)f->Get("str");
   if (!s) {
      printf("FAIL no TObjString at key 'str'\n");
   } else if (s->GetString() != "hello") {
      printf("FAIL string is '%s'\n", s->GetString().Data());
   }

   f->Close();

   // ROOT reads the free list only when the file is opened writable
   // (root/io/io/src/TFile.cxx:769-775), so that half of the check needs an
   // UPDATE open -- and an UPDATE open rewrites the key list, the free list and
   // the header. Do it on a copy, and then use it: appending an object exercises
   // ROOT's allocator against our free entry, which is WritingFiles.md 8's
   // hazard. If our last entry named the wrong span, this overwrites live data.
   TString copy = "build/scratch/verify-objstring.root";
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
   if (!fr || fr->GetSize() != 1) {
      printf("FAIL free list has %d entries\n", fr ? fr->GetSize() : -1);
   } else {
      TFree *e = (TFree *)fr->First();
      if (e->GetFirst() != 656 || e->GetLast() != 2000000000)
         printf("FAIL free entry [%lld, %lld]\n",
                (long long)e->GetFirst(), (long long)e->GetLast());
   }
   TObjString added("appended by ROOT");
   u->WriteTObject(&added, "added");
   u->Close();

   TFile *r = TFile::Open(copy);
   if (!r || r->IsZombie()) {
      printf("FAIL cannot reopen %s after the update\n", copy.Data());
      return;
   }
   TObjString *first = (TObjString *)r->Get("str");
   TObjString *second = (TObjString *)r->Get("added");
   if (!first || first->GetString() != "hello")
      printf("FAIL the original object did not survive ROOT's update\n");
   if (!second || second->GetString() != "appended by ROOT")
      printf("FAIL the appended object did not come back\n");
   if (r->GetNkeys() != 2) printf("FAIL %d keys after the update\n", r->GetNkeys());
   r->Close();

   printf("VERIFY OK\n");
}
