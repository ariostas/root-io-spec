/// The TTree record itself: every member of class version 20.
///
/// Two branches of two entries each, so the record is small enough to assert
/// field by field, and compression is off so it can be read without a codec.
///
/// The point of the case is the tree-level record rather than the branches:
/// fEntries and the byte counters, the defaults ROOT writes into
/// fDefaultEntryOffsetLen / fMaxEntries / fAutoSave / fAutoFlush / fEstimate,
/// the two cluster-range counted pointers with their is-present flag *clear*
/// because fNClusterRange is 0, the two TArray members written by their own
/// hand-written streamer, the five null object pointers, and fLeaves -- which
/// holds a back-reference to every leaf rather than the leaves themselves,
/// because fBranches was written first and put them all in the buffer's map.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "the TTree record", 0);

   TTree t("t", "a tree");
   Int_t i;
   Double_t d;
   t.Branch("i", &i, "i/I");
   t.Branch("d", &d, "d/D");

   for (int n = 0; n < 2; ++n) {
      i = n;
      d = 0.5 * n;
      t.Fill();
   }

   t.Write();
   f.Close();
}
