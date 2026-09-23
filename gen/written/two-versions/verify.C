/// Gate 3 for `written/two-versions`: ROOT reads one class at two layouts.
///
/// ROOT has no dictionary for `Grown`, so it builds the class from the file and
/// takes the highest version it finds as the in-memory layout. Reading `first`,
/// written at version 1, therefore goes through the evolution path: `fA` comes
/// off the file and `fB`, which version 1 does not have, is left at its default.
/// That is the claim of `spec/06-writing/WritingObjects.md` 8.4. ROOT
/// confirming it counts for more than this project's own reader confirming it,
/// because ROOT's answer is the one a user gets.
///
/// The `no dictionary` warning is declared in `case.toml` rather than avoided:
/// it is unavoidable for a class a writer invented, it concerns the session and
/// not the file, and every other diagnostic still fails the case.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }

   if (f->GetEND() != 1546) printf("FAIL fEND %lld\n", (long long)f->GetEND());
   if (f->GetNkeys() != 2) printf("FAIL %d keys\n", f->GetNkeys());

   // Both infos are in the record, in the order they were written.
   TList *infos = f->GetStreamerInfoList();
   if (!infos || infos->GetSize() != 2) {
      printf("FAIL info list has %d entries\n", infos ? infos->GetSize() : -1);
   } else {
      for (int i = 0; i < 2; ++i) {
         TVirtualStreamerInfo *si = (TVirtualStreamerInfo *)infos->At(i);
         if (strcmp(si->GetName(), "Grown") != 0)
            printf("FAIL info %d is for '%s'\n", i, si->GetName());
         if (si->GetClassVersion() != i + 1)
            printf("FAIL info %d has version %d\n", i, si->GetClassVersion());
         if (si->GetElements()->GetEntries() != i + 1)
            printf("FAIL info %d has %d elements\n", i,
                   si->GetElements()->GetEntries());
      }
   }
   if (infos) infos->Delete();

   // The emulated class takes the newest layout, and both records read through
   // it. Offsets come from the streamer info because an emulated class has no
   // compiled layout to ask.
   void *older = f->GetObjectUnchecked("first");
   void *newer = f->GetObjectUnchecked("second");
   TClass *c = TClass::GetClass("Grown");
   if (!c) {
      printf("FAIL no TClass for Grown\n");
      return;
   }
   if (c->GetClassVersion() != 2)
      printf("FAIL the emulated class is at version %d\n", c->GetClassVersion());
   TVirtualStreamerInfo *si = c->GetStreamerInfo();
   Int_t offA = si->GetOffset("fA"), offB = si->GetOffset("fB");
   if (!older) {
      printf("FAIL 'first' did not read\n");
   } else {
      Int_t a = *(Int_t *)((char *)older + offA);
      Double_t b = *(Double_t *)((char *)older + offB);
      if (a != 11) printf("FAIL first fA=%d\n", a);
      // Version 1 has no fB, so evolution leaves it at the default.
      if (b != 0) printf("FAIL first fB=%g, expected the default\n", b);
   }
   if (!newer) {
      printf("FAIL 'second' did not read\n");
   } else {
      Int_t a = *(Int_t *)((char *)newer + offA);
      Double_t b = *(Double_t *)((char *)newer + offB);
      if (a != 22) printf("FAIL second fA=%d\n", a);
      if (b != 3.5) printf("FAIL second fB=%g\n", b);
   }

   f->Close();
   printf("VERIFY OK\n");
}
