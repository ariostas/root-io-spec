/// Gate 3 for `written/cycles`: ROOT resolves the cycles the way the key list
/// orders them.
///
/// The interesting assertions are the lookups, not the values. ROOT takes the
/// first key of a name and never compares cycles, so `Get("str")` returning
/// `revision 3` is the evidence that the images are in descending order --
/// reversing them makes it return `revision 1` instead, silently.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }

   if (f->GetEND() != 1361) printf("FAIL fEND %lld\n", (long long)f->GetEND());
   if (f->GetNkeys() != 3) printf("FAIL %d keys\n", f->GetNkeys());

   // An unqualified name resolves to the highest cycle -- because it is first.
   TObjString *s = (TObjString *)f->Get("str");
   if (!s || s->GetString() != "revision 3")
      printf("FAIL Get(\"str\") is '%s'\n", s ? s->GetString().Data() : "(null)");

   // Every cycle is still there and still addressable.
   for (int i = 1; i <= 3; ++i) {
      TObjString *v = (TObjString *)f->Get(TString::Format("str;%d", i));
      if (!v || v->GetString() != TString::Format("revision %d", i))
         printf("FAIL Get(\"str;%d\") is '%s'\n", i,
                v ? v->GetString().Data() : "(null)");
   }

   // The two lookup paths differ on an explicit cycle: Get wants an exact
   // match, GetKey takes the highest at or below it (Record.md 4). Both agree
   // here because every cycle exists.
   TKey *k = f->GetKey("str");
   if (!k || k->GetCycle() != 3)
      printf("FAIL GetKey(\"str\") cycle %d\n", k ? k->GetCycle() : -1);
   TKey *k2 = f->GetKey("str", 2);
   if (!k2 || k2->GetCycle() != 2)
      printf("FAIL GetKey(\"str\", 2) cycle %d\n", k2 ? k2->GetCycle() : -1);

   // The list order itself, which is what all of the above rests on.
   TIter it(f->GetListOfKeys());
   TKey *e;
   int want = 3;
   while ((e = (TKey *)it())) {
      if (e->GetCycle() != want)
         printf("FAIL key list holds cycle %d where %d was expected\n",
                e->GetCycle(), want);
      --want;
   }

   // The records are in the order they were written, which is the opposite.
   if (f->GetKey("str", 1)->GetSeekKey() != 282)
      printf("FAIL str;1 is not the first record\n");
   if (f->GetKey("str", 3)->GetSeekKey() != 468)
      printf("FAIL str;3 is not the last record\n");

   f->Close();

   // A fourth write must become cycle 4 and go to the front of the run.
   TString copy = "build/scratch/verify-cycles.root";
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
   TObjString fourth("revision 4");
   u->WriteTObject(&fourth, "str");
   u->Close();

   TFile *r = TFile::Open(copy);
   TObjString *newest = (TObjString *)r->Get("str");
   if (!newest || newest->GetString() != "revision 4")
      printf("FAIL after ROOT's write, Get(\"str\") is '%s'\n",
             newest ? newest->GetString().Data() : "(null)");
   TKey *k4 = r->GetKey("str");
   if (!k4 || k4->GetCycle() != 4)
      printf("FAIL ROOT gave the new key cycle %d\n", k4 ? k4->GetCycle() : -1);
   if (r->GetNkeys() != 4) printf("FAIL %d keys after the write\n", r->GetNkeys());
   r->Close();

   printf("VERIFY OK\n");
}
