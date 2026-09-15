/// A basket of each shape: one with fixed-size entries and one without.
///
/// Branch "n" holds a single Int_t per entry, so every entry is four bytes and
/// the basket needs no entry-offset array. Branch "a" is a counted array whose
/// length is the value of n, so its entries are 4, 8 and 12 bytes and its basket
/// carries an offset array.
///
/// Three entries only, and compression disabled, so that the whole of both
/// baskets can be asserted byte for byte. A basket's own fields live inside
/// fKeyLen, which is why these keys are 65 bytes where an ordinary key with the
/// same three strings would be 46.
///
/// Both branches are leaflist branches on purpose. A std::vector<float> branch
/// produces the same two basket shapes, but it drags TBranchElement and
/// TLeafElement into the StreamerInfo record and that made the file's normalized
/// digest differ between macOS and Linux while all of its byte assertions passed
/// on both. The cause is somewhere in a region this case does not assert; see
/// PLAN.md 9.6.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "basket layouts", 0);

   TTree t("t", "a tree");
   Int_t   n;
   Float_t a[3];
   t.Branch("n", &n, "n/I");
   t.Branch("a", a, "a[n]/F");

   for (int i = 0; i < 3; ++i) {
      n = i + 1;
      for (int j = 0; j < n; ++j)
         a[j] = (float)i;
      t.Fill();
   }

   t.Write();
   f.Close();
}
