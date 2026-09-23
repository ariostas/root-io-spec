/// The two histogram classes a writer reaches for after TH1: TH2 and TProfile.
///
/// Both have hand-written Streamers in both directions and both insert their
/// own members after the TH1 base, which is why they need their own procedure;
/// `classes/histogram` covers TH1F and TH1D, whose records end at the TArray
/// base.
///
/// Four records, each with something the other three lack:
///
///  * `h2f` is a TH2F with fixed-width bins, an explicit Sumw2() and fills that
///    land outside the range in x and in y, separately. A cell is incremented
///    either way, and neither fill reaches fTsumw, so fEntries is 6 while
///    fTsumw is 4.
///  * `h2d` is a TH2D with variable edges on both axes, which is the only
///    way a non-empty fXbins reaches a Y axis anywhere in data/, and it is
///    filled with weights so the four y sums are not the x sums.
///  * `p1` is a TProfile with unit weights, so fBinSumw2 stays empty while
///    fSumw2 does not. A profile's fSumw2 is allocated by its constructor and
///    holds sum(w*y*y), which is unlike a TH1's.
///  * `p2` is a TProfile with a Y range, a non-default fErrorMode, and
///    weighted fills, so fBinSumw2 is populated. One of its fills is outside
///    the Y range and increments nothing at all, fEntries included.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "TH2 and TProfile", 0);

   TH2F h2f("h2f", "three by two", 3, 0., 3., 2, 0., 2.);
   h2f.Sumw2();
   h2f.Fill(0.5, 0.5);
   h2f.Fill(0.5, 0.5);
   h2f.Fill(1.5, 1.5);
   h2f.Fill(2.5, 0.5);
   h2f.Fill(-1.0, 0.5);   // x underflow
   h2f.Fill(0.5, 9.0);    // y overflow
   h2f.Write();

   const Double_t xedges[3] = {0., 1., 4.};
   const Double_t yedges[3] = {0., 2., 10.};
   TH2D h2d("h2d", "variable both ways", 2, xedges, 2, yedges);
   h2d.Fill(0.5, 1.0, 2.0);
   h2d.Fill(2.5, 6.0, 0.5);
   h2d.Write();

   TProfile p1("p1", "unit weights", 3, 0., 3.);
   p1.Fill(0.5, 1.0);
   p1.Fill(0.5, 3.0);
   p1.Fill(1.5, 2.0);
   p1.Fill(-1.0, 7.0);    // x underflow
   p1.Write();

   TProfile p2("p2", "a Y range", 2, 0., 2., 0., 10., "s");
   p2.Fill(0.5, 2.0, 3.0);
   p2.Fill(1.5, 4.0, 0.5);
   p2.Fill(0.5, 6.0, 0.5);
   p2.Fill(0.5, 99.0, 1.0);   // outside fYmin..fYmax: nothing at all changes
   p2.Write();

   f.Close();
}
