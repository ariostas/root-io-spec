/// The same class written twice, split and unsplit, with the same data.
///
/// TTree::Branch at split level 0 does not produce a branch tree: it produces
/// one branch whose entries are whole serialised objects. The file records
/// which happened, and not through fSplitLevel:
///
///   sp     fType 0, fID -2   split; the columns are in fBranches
///   un     fType 0, fID -1   unsplit; the whole object is in this branch
///
/// fID is the discriminator. Both branches carry the same class, the same
/// fClassName, the same fCheckSum and the same three entries; `un` simply has
/// an empty fBranches and baskets holding UEv objects rather than columns.
///
/// This is the pair Splitting.md section 6 calls the unsplit fallback, produced
/// deliberately here rather than by a refusal, so that the two forms can be
/// compared byte for byte in one file.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "the same class split and unsplit", 0);

   TTree t("t", "split and unsplit side by side");
   UEv sp, un;
   UEv *psp = &sp, *pun = &un;
   t.Branch("sp", &psp, 32000, 99);
   t.Branch("un", &pun, 32000, 0);

   for (int i = 0; i < 3; ++i) {
      sp.fB = un.fB = 10 + i;
      sp.fI = un.fI = 20 + i;
      sp.fD = un.fD = 30 + i;
      t.Fill();
   }

   t.Write();
   f.Close();
}
