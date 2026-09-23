/// An unsigned counter: TBits::fNbytes keeps kUInt (13) and is never kCounter.
///
/// A counter is promoted to kCounter (6) only when its code is below 6
/// (root/core/meta/src/TStreamerElement.cxx:99), so the UInt_t fNbytes that
/// counts TBits::fAllBits stays 13. Split, its branch is the only counter branch
/// whose fStreamerType is not 6:
///
///   split           fType 0, fID -2   the split node
///   split/TObject   fType 1           the base, split into two members
///   split/fNbits    fType 0, fStreamerType 13
///   split/fNbytes   fType 0, fStreamerType 13, the counter
///   split/fAllBits  fType 0, fStreamerType 51, fBranchCount -> fNbytes
///
/// The same class is written two more ways, so a counter of code 13 is read on
/// every path: as a TBits record ("bits") and as an unsplit branch, whose entries
/// are whole TBits objects read element by element.
///
/// TBits has a dictionary in libCore, so the case needs no classes.h.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "an unsigned counter", 0);

   TBits bits(20);
   bits.SetBitNumber(3);
   bits.SetBitNumber(17);
   bits.Write("bits");

   TTree t("t", "TBits, unsplit and split");
   TBits *u = new TBits();
   TBits *s = new TBits();
   t.Branch("unsplit", &u, 32000, 0);
   t.Branch("split", &s, 32000, 99);

   // ResetAllBits keeps the size, so the highest bit set so far fixes fNbytes.
   // SetBitNumber doubles what it needs, so the counts are 1, 1, 4 on the
   // unsplit branch and 1, 4, 4 on the split one.
   for (int i = 0; i < 3; ++i) {
      u->ResetAllBits();
      s->ResetAllBits();
      u->SetBitNumber(i * 5);
      s->SetBitNumber(i * 9);
      t.Fill();
   }

   t.Write();
   f.Close();
}
