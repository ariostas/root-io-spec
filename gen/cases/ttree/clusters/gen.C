/// A tree whose cluster size changes part way through.
///
/// SetAutoFlush is called with a positive entry count, so ROOT flushes every
/// four entries and records the boundary; changing it to 3 and then to 5 closes
/// out a cluster range each time. The result is the only shape in which
/// fNClusterRange, fClusterRangeEnd and fClusterSize hold anything: two ranges
/// on disk, the two counted pointers with their is-present flag set, and the
/// third, open-ended range described by fAutoFlush alone.
///
/// A positive fAutoFlush also makes fFlushedBytes and fSavedBytes non-zero,
/// which distinguishes a tree whose cluster boundaries are recorded from one
/// where they were never reached.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "cluster ranges", 0);

   TTree t("t", "a tree");
   Int_t x;
   t.Branch("x", &x, "x/I", 100);

   t.SetAutoFlush(4);
   for (int i = 0; i < 8; ++i) { x = i; t.Fill(); }
   t.SetAutoFlush(3);
   for (int i = 8; i < 14; ++i) { x = i; t.Fill(); }
   t.SetAutoFlush(5);
   for (int i = 14; i < 19; ++i) { x = i; t.Fill(); }

   t.Write();
   f.Close();
}
