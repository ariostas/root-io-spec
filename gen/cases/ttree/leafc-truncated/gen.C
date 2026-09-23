/// A TLeafC whose fLen is smaller than the longest string in its own baskets.
///
/// TLeafC::FillBasket raises fLen and fMaximum together, so a tree written by
/// TTree::Fill always has fLen == fMaximum. A *fast clone* does not: ROOT copies
/// baskets wholesale, never runs FillBasket, and widens only fMaximum through
/// TLeafC::IncludeRange. The target keeps the fLen it inherited from the first
/// source tree.
///
/// fLen sizes the read buffer: TLeafC::ReadBasket calls
/// ReadFastArrayString(fValue, fLen), which clamps to fLen - 1 characters. ROOT
/// therefore reads the long strings in tree "merged" back as two characters
/// each, silently, while the bytes in the basket hold all ten. A reader that
/// takes the length from the counted string in the entry, the only correct
/// source, reads the file correctly where ROOT does not.
///
/// This is reachable from `hadd`, which fast-merges by default, so files of this
/// shape exist in the wild.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a short fLen", 0);

   char s[64];

   // Two sources, written the ordinary way: fLen == fMaximum in both.
   TTree shortt("short", "two-character strings");
   shortt.Branch("s", s, "s/C");
   for (int i = 0; i < 3; ++i) { strcpy(s, "ab"); shortt.Fill(); }
   shortt.Write();

   TTree longt("long", "ten-character strings");
   longt.Branch("s", s, "s/C");
   for (int i = 0; i < 3; ++i) { strcpy(s, "0123456789"); longt.Fill(); }
   longt.Write();

   // The fast clone. CloneTree(0) takes its leaf from "short", so fLen is 3;
   // copying "long" in raises fMaximum to 11 and leaves fLen alone.
   TTree *merged = shortt.CloneTree(0);
   merged->SetName("merged");
   merged->SetTitle("fast-cloned from both");
   merged->CopyEntries(&shortt, -1, "fast");
   merged->CopyEntries(&longt, -1, "fast");
   merged->Write();

   f.Close();
}
