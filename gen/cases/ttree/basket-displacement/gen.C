/// A displacement array, in both of the forms it takes.
///
/// Two functions build one (TBasket.md 4): TBasket::Update with a skip count,
/// reached only from TBranch::FillEntryBuffer, and TBasket::MoveEntries, for a
/// circular tree. A circular tree is the reachable one:
/// TTree::KeepCircular calls TBranch::KeepCircular, which calls
/// TBasket::MoveEntries, which builds fDisplacement out of the entry offsets
/// that are about to be rewritten.
///
/// MoveEntries only builds it when there is an entry-offset array, so the
/// fixed-width branch `n` never gets one and the string branch `s` does.
///
/// Two trees, because the two basket forms cannot both come from one:
///
///   circ  Write()        a basket record:   flag 0, and the displacement
///                        array sits in the payload with nothing signalling it
///   emb   WriteTObject   embedded:          flag 51 = 1 + 10 + 40
///
/// SetCircular(3) keeps 3 entries, so filling 7 moves the window four times.
/// Each string is one character longer than the last, so every entry offset is
/// distinct and the displacements are visibly the pre-move offsets.
void fill(TTree &t)
{
   static char s[64];
   static Int_t n;
   t.Branch("n", &n, "n/I");
   t.Branch("s", s, "s/C");
   t.SetCircular(3);
   for (int i = 0; i < 7; ++i) {
      n = i;
      for (int j = 0; j <= i; ++j) s[j] = '0' + i;
      s[i + 1] = 0;
      t.Fill();
   }
}

void gen(const char *out)
{
   TFile f(out, "RECREATE", "displacement arrays", 0);

   TTree circ("circ", "written to records");
   fill(circ);
   circ.Write();

   TTree emb("emb", "kept in memory");
   fill(emb);
   f.WriteTObject(&emb, "emb");

   f.Close();
}
