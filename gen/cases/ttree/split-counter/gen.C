/// A counted array inside a split object: fBranchCount pointing at a counter.
///
/// `Int_t fN; Float_t *fX; //[fN]` is the oldest variable-length shape in ROOT,
/// and splitting it produces the one case where an fType 0 branch carries an
/// fBranchCount:
///
///   ce        fType 0, fID -2   the split node
///   ce/fN     fType 0, fStreamerType 6 (kCounter), no fBranchCount
///   ce/fX     fType 0, fStreamerType 41 (kOffsetP + kFloat), fBranchCount -> fN
///   ce/fTail  fType 0, fStreamerType 3
///
/// The dispatch of TBranchElement.md section 8 sends fN to ReadLeavesMemberCounter
/// and fX to ReadLeavesMemberBranchCount, which are the two rows with the fewest
/// occurrences in either corpus -- 2 and 16.
///
/// The relationship is recorded twice and independently: fX's branch has an
/// fBranchCount naming fN's *branch*, and fX's leaf has an fLeafCount naming
/// fN's *leaf*. Three entries with three different lengths, so the counter is
/// doing real work.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a counted array in a split object", 0);

   TTree t("t", "a split object with a counted array");
   CEv ce;
   ce.fX = new Float_t[4];
   CEv *p = &ce;
   t.Branch("ce", &p, 32000, 99);

   const Int_t lengths[3] = {1, 3, 2};
   for (int i = 0; i < 3; ++i) {
      ce.fN = lengths[i];
      for (int j = 0; j < ce.fN; ++j)
         ce.fX[j] = 100 * (i + 1) + j;
      ce.fTail = 7 + i;
      t.Fill();
   }

   t.Write();
   f.Close();
}
