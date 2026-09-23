/// The leaf forms TLeaf.md 13 lists as uncovered and that do not need a legacy
/// ROOT: TLeafG, a two-dimensional leaf, and a TLeafC long enough to need the
/// 255-escape of the counted string.
///
/// TLeafObject and TLeafElement were on that list too and turned out to be
/// covered already: tree-branchref has a real TLeafObject and the split cases
/// have 52 TLeafElements between them.
///
/// Two entries. The second string is 300 characters, which forces the long
/// form: one byte of 255, then an i32 length, then the bytes. The first is
/// short, so both forms sit in one basket.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "leaf forms", 0);
   TTree t("t", "leaf forms");

   Long_t g = 0;
   Int_t  n = 0;
   Float_t a[2][3];      // a[n][3], n <= 2
   char s[400];

   t.Branch("g", &g, "g/G");
   t.Branch("n", &n, "n/I");
   t.Branch("a", a, "a[n][3]/F");
   t.Branch("s", s, "s/C");

   // entry 0: n = 2, so six floats; a short string
   g = 0x0102030405060708L;
   n = 2;
   a[0][0] = 1; a[0][1] = 2; a[0][2] = 3;
   a[1][0] = 4; a[1][1] = 5; a[1][2] = 6;
   strcpy(s, "ab");
   t.Fill();

   // entry 1: n = 1, so three floats; a 300-character string
   g = -1L;
   n = 1;
   a[0][0] = 7; a[0][1] = 8; a[0][2] = 9;
   for (int i = 0; i < 300; ++i) s[i] = 'x';
   s[300] = 0;
   t.Fill();

   t.Write();
   f.Close();
}
