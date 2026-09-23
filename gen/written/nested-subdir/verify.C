/// Gate 3 for `written/nested-subdir`: ROOT opens a nested file this project wrote.
///
/// It checks three things no other written case reaches: that ROOT rebuilds
/// the directory tree from the records, that it recovers each subdirectory's
/// own fSeekDir/fSeekParent/fSeekKeys, and that it can write into a
/// subdirectory this project created. The last exercises the claim in
/// `spec/06-writing/WritingFiles.md` 5.3 that the record never moves.
///
/// Any ROOT output on either stream also fails the case.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }

   // The header.
   if (f->GetEND() != 1854) printf("FAIL fEND %lld\n", (long long)f->GetEND());
   if (f->GetSeekFree() != 1755)
      printf("FAIL fSeekFree %lld\n", (long long)f->GetSeekFree());
   if (f->GetSeekInfo() != 821)
      printf("FAIL fSeekInfo %lld\n", (long long)f->GetSeekInfo());
   if (f->GetSeekKeys() != 1255)
      printf("FAIL root fSeekKeys %lld\n", (long long)f->GetSeekKeys());
   if (f->GetNkeys() != 2) printf("FAIL %d keys at top level\n", f->GetNkeys());

   // A directory key spells its class TDirectory on disk and ROOT hands it back
   // as TDirectoryFile: the two are one class name (Directory.md 6.5).
   TKey *dk = (TKey *)f->GetListOfKeys()->FindObject("alpha");
   if (!dk) {
      printf("FAIL no key 'alpha' in the root key list\n");
   } else {
      if (strcmp(dk->GetClassName(), "TDirectoryFile") != 0)
         printf("FAIL alpha key class %s\n", dk->GetClassName());
      if (dk->GetSeekKey() != 401)
         printf("FAIL alpha key fSeekKey %lld\n", (long long)dk->GetSeekKey());
      if (dk->GetObjlen() != 60)
         printf("FAIL alpha key fObjlen %d\n", dk->GetObjlen());
   }

   // The two subdirectories, and the fields only their own records hold.
   TDirectoryFile *alpha = (TDirectoryFile *)f->Get("alpha");
   if (!alpha) {
      printf("FAIL no directory 'alpha'\n");
      return;
   }
   if (strcmp(alpha->GetTitle(), "alpha") != 0)
      printf("FAIL alpha title '%s'\n", alpha->GetTitle());
   if (alpha->GetSeekDir() != 401)
      printf("FAIL alpha fSeekDir %lld\n", (long long)alpha->GetSeekDir());
   if (alpha->GetSeekParent() != 100)
      printf("FAIL alpha fSeekParent %lld\n", (long long)alpha->GetSeekParent());
   if (alpha->GetSeekKeys() != 1463)
      printf("FAIL alpha fSeekKeys %lld\n", (long long)alpha->GetSeekKeys());
   if (alpha->GetNbytesKeys() != 171)
      printf("FAIL alpha fNbytesKeys %d\n", alpha->GetNbytesKeys());
   if (alpha->GetNkeys() != 2)
      printf("FAIL alpha holds %d keys\n", alpha->GetNkeys());

   TDirectoryFile *beta = (TDirectoryFile *)f->Get("alpha/beta");
   if (!beta) {
      printf("FAIL no directory 'alpha/beta'\n");
      return;
   }
   if (beta->GetSeekDir() != 610)
      printf("FAIL beta fSeekDir %lld\n", (long long)beta->GetSeekDir());
   // The mother's offset, not the top directory's: the post-6.38 meaning.
   if (beta->GetSeekParent() != 401)
      printf("FAIL beta fSeekParent %lld\n", (long long)beta->GetSeekParent());
   if (beta->GetSeekKeys() != 1634)
      printf("FAIL beta fSeekKeys %lld\n", (long long)beta->GetSeekKeys());
   if (beta->GetNkeys() != 1)
      printf("FAIL beta holds %d keys\n", beta->GetNkeys());

   // Every directory has its own UUID (Directory.md 4.5). Copy each one out
   // before comparing: TUUID::AsString returns a thread-local static buffer
   // (root/core/base/src/TUUID.cxx:602-612), so two calls in one expression
   // compare a string with itself and every UUID looks identical.
   TString ua(alpha->GetUUID().AsString());
   TString ub(beta->GetUUID().AsString());
   TString uf(f->GetUUID().AsString());
   if (ua == ub) printf("FAIL alpha and beta share a UUID\n");
   if (uf == ua) printf("FAIL the file and alpha share a UUID\n");

   // One object per level, addressed by path.
   const char *where[3] = {"top", "alpha/in_alpha", "alpha/beta/in_beta"};
   const char *what[3] = {"at top level", "inside alpha", "inside alpha/beta"};
   for (int i = 0; i < 3; ++i) {
      TObjString *s = (TObjString *)f->Get(where[i]);
      if (!s) {
         printf("FAIL no TObjString at '%s'\n", where[i]);
      } else if (s->GetString() != what[i]) {
         printf("FAIL '%s' holds '%s'\n", where[i], s->GetString().Data());
      }
   }
   // cd() is the other way in, and it uses fSeekPdir rather than the paths.
   if (!f->cd("alpha/beta") || strcmp(gDirectory->GetName(), "beta") != 0)
      printf("FAIL cd('alpha/beta') landed on '%s'\n", gDirectory->GetName());
   f->Close();

   // Now write into a subdirectory this project created. ROOT frees alpha's old
   // key-list record, writes a new one, and rewrites alpha's directory record
   // in place (WritingFiles.md 5.3). If fSeekDir, fNbytesName or fSeekKeys were
   // wrong, it shows here.
   TString copy = "build/scratch/verify-nested-subdir.root";
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
   TDirectory *d = u->GetDirectory("alpha");
   if (!d) {
      printf("FAIL no 'alpha' after reopening for UPDATE\n");
      return;
   }
   TObjString added("appended by ROOT");
   d->WriteTObject(&added, "added");
   u->Close();

   TFile *r = TFile::Open(copy);
   if (!r || r->IsZombie()) {
      printf("FAIL cannot reopen %s after the update\n", copy.Data());
      return;
   }
   TDirectoryFile *a2 = (TDirectoryFile *)r->Get("alpha");
   if (!a2) {
      printf("FAIL 'alpha' did not survive ROOT's update\n");
      return;
   }
   if (a2->GetSeekDir() != 401)
      printf("FAIL alpha moved to %lld\n", (long long)a2->GetSeekDir());
   if (a2->GetNkeys() != 3)
      printf("FAIL alpha holds %d keys after the update\n", a2->GetNkeys());
   TObjString *kept = (TObjString *)r->Get("alpha/beta/in_beta");
   TObjString *fresh = (TObjString *)r->Get("alpha/added");
   if (!kept || kept->GetString() != "inside alpha/beta")
      printf("FAIL the deepest object did not survive ROOT's update\n");
   if (!fresh || fresh->GetString() != "appended by ROOT")
      printf("FAIL the appended object did not come back\n");
   r->Close();

   printf("VERIFY OK\n");
}
