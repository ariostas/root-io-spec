/// Gate 3 for `written/streamerinfo`.
///
/// The main check is that nothing is printed: our TStreamerInfo has the
/// checksum ROOT computes for its own TObjString, so TStreamerInfo::BuildCheck
/// does not warn. tools/check_write.py fails the case on any ROOT diagnostic,
/// so no output here is an assertion about the checksum algorithm.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }
   if (f->GetCompressionSettings() != 101)
      printf("FAIL fCompress %d\n", f->GetCompressionSettings());
   if (f->GetSeekInfo() != 424)
      printf("FAIL fSeekInfo %lld\n", (long long)f->GetSeekInfo());
   if (f->GetNbytesInfo() != 280)
      printf("FAIL fNbytesInfo %d\n", f->GetNbytesInfo());

   // The StreamerInfo record, decompressed and parsed by ROOT.
   TList *infos = f->GetStreamerInfoList();
   if (!infos || infos->GetSize() != 1) {
      printf("FAIL streamer info list has %d entries\n",
             infos ? infos->GetSize() : -1);
   } else {
      TStreamerInfo *info = (TStreamerInfo *)infos->First();
      if (strcmp(info->GetName(), "TObjString") != 0)
         printf("FAIL info names %s\n", info->GetName());
      if (info->GetClassVersion() != 1)
         printf("FAIL info class version %d\n", info->GetClassVersion());
      if (info->GetCheckSum() != 0x9c8e4800u)
         printf("FAIL info checksum 0x%08x\n", info->GetCheckSum());
      if (info->GetElements()->GetEntriesFast() != 2)
         printf("FAIL info has %d elements\n",
                info->GetElements()->GetEntriesFast());
      TStreamerElement *base =
         (TStreamerElement *)info->GetElements()->UncheckedAt(0);
      // A TObject base is recorded as kTObject (66), not as kBase (0):
      // ElementTypes.md 3. ROOT reads back what we wrote.
      if (base->GetType() != TVirtualStreamerInfo::kTObject)
         printf("FAIL first element type %d\n", base->GetType());
      // fBaseCheckSum is stored in fMaxIndex[1].
      if (base->GetMaxIndex(1) != (Int_t)0x901bc02d)
         printf("FAIL base checksum 0x%08x\n", base->GetMaxIndex(1));
   }
   if (infos) infos->Delete();

   // The key, whose fObjlen is the uncompressed length.
   TKey *k = (TKey *)f->GetListOfKeys()->First();
   if (k) {
      if (k->GetNbytes() != 110) printf("FAIL key fNbytes %d\n", k->GetNbytes());
      if (k->GetObjlen() != 621) printf("FAIL key fObjlen %d\n", k->GetObjlen());
   }

   // The payload, which only comes back if the block header was right.
   TObjString *s = (TObjString *)f->Get("str");
   if (!s) {
      printf("FAIL no TObjString\n");
   } else {
      if (s->GetString().Length() != 600)
         printf("FAIL string length %d\n", s->GetString().Length());
      if (!s->GetString().BeginsWith("hello hello") ||
          !s->GetString().EndsWith("hello "))
         printf("FAIL string content\n");
   }

   f->Close();
   printf("VERIFY OK\n");
}
