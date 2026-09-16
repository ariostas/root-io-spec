/// A split object branch: the three fType values an ordinary split produces.
///
/// TTree::Branch with a split level above 0 does not write one branch. It walks
/// the class's TStreamerInfo and writes a branch per member, arranged as a tree
/// whose interior nodes carry no data. This case is the smallest arrangement
/// that produces all three kinds of node at once:
///
///   ev          fType 0, fID -2   the split node; no data of its own
///   ev.Base     fType 1           the base class; no leaf, no basket
///   ev.fBase    fType 0, fID >= 0 a member of the base
///   ev.fI       fType 0, fID >= 0
///   ev.fD       fType 0, fID >= 0
///   ev.fS       fType 0, fID >= 0
///
/// Every one of them is a TBranchElement carrying a TLeafElement, which is why
/// no existing fixture covers any of this: the unsplit path in TBranch.md and
/// TLeaf.md never produces one.
///
/// Three entries with distinct values per member, and compression off, so the
/// TTree record and every basket can be asserted byte for byte.
///
/// Ev and Base come from classes.h and are compiled first; see
/// gen/common/README.md for why that has to be a separate step.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a split object branch", 0);

   TTree t("t", "a tree with one split branch");
   Ev ev;
   t.Branch("ev", &ev, 32000, 99);

   for (int i = 0; i < 3; ++i) {
      ev.fBase = 10 + i;
      ev.fI    = 20 + i;
      ev.fD    = 30 + i;
      ev.fS    = 40 + i;
      t.Fill();
   }

   t.Write();
   f.Close();
}
