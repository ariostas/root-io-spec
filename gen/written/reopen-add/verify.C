/// Gate 3 for `written/reopen-add`: ROOT opens a file this project reopened.
///
/// The structure matters more than the values. ROOT has to agree about which
/// record each key names after a session that rewrote the key list, moved the
/// free record and left a 243-byte hole. The `StreamerInfo` record the base
/// wrote must still be the one ROOT reads the objects through, since the update
/// never rewrote it.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }

   if (f->GetEND() != 1657) printf("FAIL fEND %lld\n", (long long)f->GetEND());
   if (f->GetSeekFree() != 806)
      printf("FAIL fSeekFree %lld\n", (long long)f->GetSeekFree());
   if (f->GetSeekInfo() != 372)
      printf("FAIL fSeekInfo %lld\n", (long long)f->GetSeekInfo());
   if (f->GetNbytesInfo() != 434)
      printf("FAIL fNbytesInfo %d\n", f->GetNbytesInfo());
   if (f->GetNkeys() != 3) printf("FAIL %d keys\n", f->GetNkeys());

   // The three writes, each resolved the way its option says.
   TObjString *s = (TObjString *)f->Get("str");
   if (!s || s->GetString() != "the same name, a second cycle")
      printf("FAIL Get(\"str\") is '%s'\n", s ? s->GetString().Data() : "(null)");
   TObjString *s1 = (TObjString *)f->Get("str;1");
   if (!s1 || s1->GetString() != "first")
      printf("FAIL str;1 did not survive the update\n");
   TObjString *t = (TObjString *)f->Get("two");
   if (!t || t->GetString() != "written, and then the old one freed")
      printf("FAIL Get(\"two\") is '%s'\n", t ? t->GetString().Data() : "(null)");

   // WriteDelete advanced the cycle and left only one key of that name.
   TKey *kt = f->GetKey("two");
   if (!kt || kt->GetCycle() != 2)
      printf("FAIL two has cycle %d\n", kt ? kt->GetCycle() : -1);
   if (f->GetKey("two", 1)) printf("FAIL two;1 is still reachable\n");
   if (kt && kt->GetSeekKey() != 1259)
      printf("FAIL two;2 at %lld\n", (long long)kt->GetSeekKey());

   // The record the update did not write is where the base put it.
   TKey *k1 = f->GetKey("str", 1);
   if (!k1 || k1->GetSeekKey() != 284)
      printf("FAIL str;1 moved to %lld\n",
             k1 ? (long long)k1->GetSeekKey() : -1);
   f->Close();

   // The free list, which needs a writable open: the hole the update left has
   // to be the one ROOT would allocate into next.
   TString copy = "build/scratch/verify-reopen-add.root";
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
      if (a->GetFirst() != 904 || a->GetLast() != 1146)
         printf("FAIL interior free entry [%lld, %lld]\n",
                (long long)a->GetFirst(), (long long)a->GetLast());
   }
   TObjString third("a third session");
   u->WriteTObject(&third, "str");
   u->Close();

   TFile *r = TFile::Open(copy);
   if (!r || r->IsZombie()) {
      printf("FAIL cannot reopen after ROOT's own update\n");
      return;
   }
   TObjString *newest = (TObjString *)r->Get("str");
   if (!newest || newest->GetString() != "a third session")
      printf("FAIL after ROOT's update, Get(\"str\") is '%s'\n",
             newest ? newest->GetString().Data() : "(null)");
   TKey *k3 = r->GetKey("str");
   if (!k3 || k3->GetCycle() != 3)
      printf("FAIL ROOT gave the new key cycle %d\n", k3 ? k3->GetCycle() : -1);
   if (r->GetNkeys() != 4) printf("FAIL %d keys after ROOT's update\n", r->GetNkeys());
   r->Close();

   printf("VERIFY OK\n");
}
