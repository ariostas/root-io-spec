/// A TLeafC branch, in the three forms one basket can hold.
///
/// Branch "s" is a variable-length C string, so its entries are 3, 0 and 305
/// bytes and its basket must have an entry-offset array; a TLeafC forces
/// fEntryOffsetLen non-zero whatever the branch was asked for. Branch "n" is a
/// single Int_t in the same file for the contrast: fixed entries, no array.
///
/// The three strings are the three cases a writer has to get right: the short
/// counted form, an empty string that occupies no bytes at all, and one long
/// enough to need the 255-escape. The empty one is second so that it is neither
/// the first nor the last entry of the basket, which is where ROOT's own
/// offset-comparison test in TLeafC::ReadBasket is at its weakest.
///
/// Three entries and no compression, so both baskets can be asserted byte for
/// byte, and so this file can be compared with the one
/// tools/rootwrite.py produces for the same content.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "string leaves", 0);

   TTree t("t", "a tree");
   Int_t n = 0;
   char s[400];
   t.Branch("n", &n, "n/I");
   t.Branch("s", s, "s/C");

   for (int i = 0; i < 3; ++i) {
      n = i + 1;
      if (i == 0)
         strcpy(s, "ab");
      else if (i == 1)
         s[0] = 0;
      else {
         for (int j = 0; j < 300; ++j)
            s[j] = 'x';
         s[300] = 0;
      }
      t.Fill();
   }

   t.Write();
   f.Close();
}
