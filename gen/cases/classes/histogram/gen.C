/// The histogram chain, which nothing else in the corpus carries at byte level:
/// TH1F and TH1D with the whole TH1 -> TAxis -> TAttAxis hierarchy, plus the
/// fourteen streamer infos ROOT records for it.
///
/// Two histograms, because they differ in exactly two places -- the TArray base
/// and the class version word -- and because the second uses **variable bin
/// edges**, which is the only way to get a non-empty TAxis::fXbins into a file.
///
/// Sumw2 is called on the first so fSumw2 is a populated TArrayD rather than an
/// empty one; the second leaves it empty. Two fills land outside the range, so
/// the underflow and overflow cells are not zero and fEntries differs from the
/// sum of the in-range weights.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "the histogram chain", 0);

   TH1F h1("h1", "three bins", 3, 0., 3.);
   h1.Sumw2();
   h1.Fill(0.5);
   h1.Fill(0.5);
   h1.Fill(1.5);
   h1.Fill(-1.0);   // underflow
   h1.Fill(9.0);    // overflow
   h1.Write();

   const Double_t edges[4] = {0., 1., 4., 10.};
   TH1D h2("h2", "variable bins", 3, edges);
   h2.Fill(0.5, 2.0);
   h2.Fill(5.0, 0.5);
   h2.Write();

   f.Close();
}
