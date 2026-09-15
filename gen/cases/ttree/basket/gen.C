/// A basket of each shape: one with fixed-size entries and one without.
///
/// Branch "n" holds a single Int_t per entry, so every entry is four bytes and
/// the basket needs no entry-offset array. Branch "v" holds a std::vector<float>
/// whose length grows with the entry number, so its basket carries one.
///
/// Three entries only, and compression disabled, so that the whole of both
/// baskets can be asserted byte for byte. A basket's own fields live inside
/// fKeyLen, which is why these keys are 65 bytes where an ordinary key of the
/// same name would be 46.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "basket layouts", 0);

   TTree t("t", "a tree");
   Int_t n;
   std::vector<float> v;
   t.Branch("n", &n, "n/I");
   t.Branch("v", &v);

   for (int i = 0; i < 3; ++i) {
      n = 10 + i;
      v.assign(i + 1, (float)i);
      t.Fill();
   }

   t.Write();
   f.Close();
}
