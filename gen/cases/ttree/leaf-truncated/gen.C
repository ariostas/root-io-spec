/// The four ways a truncated floating-point leaf can be stored.
///
/// Float16_t (leaflist code `f`) and Double32_t (code `d`) both have a
/// with-factor form and a truncated-mantissa form, and the annotation in the
/// leaf title selects which one applies. The leaf class does not, and neither
/// does fLenType, which stays 4 and 8 whatever the values on disk are.
///
///   a/f            no annotation  -> 3 bytes, mantissa truncated to 12 bits
///   b/f[0,100,10]  a real range   -> 4 bytes, a scaled UInt_t
///   c/d            no annotation  -> 4 bytes, a plain Float_t
///   d/d[0,0,8]     nbits only     -> 3 bytes, mantissa truncated to 8 bits
///
/// a and c are the same declaration shape and differ by one byte per entry, in
/// the opposite direction from what the class names suggest.
///
/// Two identical entries, so a wrong width shows up as a shifted second entry
/// rather than only as a wrong total.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "truncated leaves", 0);

   TTree t("t", "a tree");
   Float_t a, b;
   Double_t c, d;
   t.Branch("a", &a, "a/f");
   t.Branch("b", &b, "b/f[0,100,10]");
   t.Branch("c", &c, "c/d");
   t.Branch("d", &d, "d/d[0,0,8]");

   for (int k = 0; k < 2; ++k) {
      a = 1.5;
      b = 50.0;
      c = 2.5;
      d = 3.5;
      t.Fill();
   }

   t.Write();
   f.Close();
}
