/// One branch carrying a leaf of every scalar type, plus a fixed-size array
/// and a string.
///
/// The members are declared in non-increasing size order on purpose. A
/// leaflist branch reads each leaf from `address + fOffset`, where fOffset is
/// the cumulative *unpadded* size of the leaves before it, so ROOT assumes the
/// struct is packed exactly as the leaflist describes. Declaring the members
/// largest first is what makes the natural C++ layout agree with that
/// assumption; any other order silently reads the wrong bytes.
///
/// The second entry's string is empty, because an empty string occupies zero
/// bytes in the basket -- TBufferFile::WriteFastArrayString returns before
/// writing even the length byte -- and that is the one case a reader cannot
/// get right without the entry-offset array.
struct All {
   Long64_t l;
   ULong64_t L;
   Double_t d;
   Double_t v[3];
   Int_t i;
   UInt_t I;
   Float_t f;
   Short_t s;
   UShort_t S;
   Char_t b;
   UChar_t B;
   Bool_t o;
   Char_t c[8];
};

void gen(const char *out)
{
   TFile f(out, "RECREATE", "leaf types", 0);

   TTree t("t", "a tree");
   All a;
   t.Branch("all", &a,
            "l/L:L/l:d/D:v[3]/D:i/I:I/i:f/F:s/S:S/s:b/B:B/b:o/O:c/C");

   for (int k = 0; k < 2; ++k) {
      a.l = -4;
      a.L = 5;
      a.d = 2.5;
      for (int j = 0; j < 3; ++j)
         a.v[j] = j + k;
      a.i = -3;
      a.I = 3000000000u;
      a.f = 1.5;
      a.s = -2;
      a.S = 40000;
      a.b = -1;
      a.B = 200;
      a.o = k;
      strcpy(a.c, k == 0 ? "ab" : "");
      t.Fill();
   }

   t.Write();
   f.Close();
}
