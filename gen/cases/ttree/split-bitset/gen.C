/// A std::bitset member of a split branch: not packed, and not always written.
///
/// A bitset reaches the file as a TStreamerSTL with fSTLtype 8 (kSTLbitset),
/// and its branch is an ordinary object-wise collection of bool: one byte per
/// bit, least significant bit first, with no packing at all. Sixteen bits cost
/// twenty-six bytes.
///
/// The case exists mainly for the other form: before the ROOT-8574 fix, which
/// landed in 6.08/06, the collection proxy did not work in this path and ROOT
/// wrote the branch with no bytes in it at all. That form is in the foreign
/// corpus (uproot-mc10events.root, ROOT 6.08/04), so a reader has to handle
/// both. This fixture has the modern shape; ReadingEntries.md 3.6 gives the
/// boundary.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a bitset in a split branch", 0);

   TTree t("t", "a std::bitset member");
   BEv e;
   BEv *p = &e;
   t.Branch("ev", &p, 32000, 99);

   for (int i = 0; i < 3; ++i) {
      e.fI = 10 + i;
      e.fBits = std::bitset<16>(0xA5A5u >> i);
      e.fJ = 100 + i;
      t.Fill();
   }

   t.Write();
   f.Close();
}
