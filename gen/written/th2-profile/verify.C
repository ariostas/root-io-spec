/// Gate 3 for `written/th2-profile`: ROOT reads a TH2F, a TH2D and two
/// TProfiles this project wrote.
///
/// Every assertion is a value ROOT *derives* from a member the writer had to
/// get right, and they are chosen so that each of the added members is behind
/// at least one of them:
///
///  * GetMean(2) is fTsumwy / fTsumw, and GetCovariance reads fTsumwxy -- the
///    only getter that does;
///  * GetBinContent(binx, biny) exercises the cell index, so a transposed
///    array fails even though fNcells is right;
///  * a TProfile's GetBinContent is fArray / fBinEntries and its GetBinError
///    needs fSumw2 and, for p2, fBinSumw2 as well, so all four arrays are read;
///  * GetErrorOption returns "s" only if fErrorMode survived as kERRORSPREAD.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }
   if (f->GetNkeys() != 4) printf("FAIL %d keys\n", f->GetNkeys());

   TH2F *h2f = (TH2F *)f->Get("h2f");
   if (!h2f) {
      printf("FAIL no TH2F h2f\n");
   } else {
      if (h2f->GetNbinsX() != 3 || h2f->GetNbinsY() != 2)
         printf("FAIL h2f bins %d x %d\n", h2f->GetNbinsX(), h2f->GetNbinsY());
      if (h2f->GetNcells() != 20)
         printf("FAIL h2f ncells %d\n", h2f->GetNcells());
      if (h2f->GetEntries() != 6)
         printf("FAIL h2f entries %g\n", h2f->GetEntries());
      // Four fills in range: the two out-of-range ones reach no statistic.
      if (h2f->GetSumOfWeights() != 4)
         printf("FAIL h2f sum of weights %g\n", h2f->GetSumOfWeights());
      if (TMath::Abs(h2f->GetMean(1) - 1.25) > 1e-12)
         printf("FAIL h2f mean x %.17g\n", h2f->GetMean(1));
      if (TMath::Abs(h2f->GetMean(2) - 0.75) > 1e-12)
         printf("FAIL h2f mean y %.17g\n", h2f->GetMean(2));
      // The only getter that reads fTsumwxy.
      if (TMath::Abs(h2f->GetCovariance() - 0.0625) > 1e-12)
         printf("FAIL h2f covariance %.17g\n", h2f->GetCovariance());
      // Cell by (binx, biny), which is where a transposed array shows up.
      if (h2f->GetBinContent(1, 1) != 2 || h2f->GetBinContent(3, 1) != 1 ||
          h2f->GetBinContent(2, 2) != 1)
         printf("FAIL h2f contents %g %g %g\n", h2f->GetBinContent(1, 1),
                h2f->GetBinContent(3, 1), h2f->GetBinContent(2, 2));
      // The two cells no in-range bin owns: x underflow and y overflow.
      if (h2f->GetBinContent(0, 1) != 1 || h2f->GetBinContent(1, 3) != 1)
         printf("FAIL h2f overflow cells %g %g\n", h2f->GetBinContent(0, 1),
                h2f->GetBinContent(1, 3));
      // From fSumw2, one entry per cell.
      if (TMath::Abs(h2f->GetBinError(1, 1) - TMath::Sqrt(2.0)) > 1e-12)
         printf("FAIL h2f error(1,1) %.17g\n", h2f->GetBinError(1, 1));
   }

   TH2D *h2d = (TH2D *)f->Get("h2d");
   if (!h2d) {
      printf("FAIL no TH2D h2d\n");
   } else {
      if (h2d->GetEntries() != 2)
         printf("FAIL h2d entries %g\n", h2d->GetEntries());
      if (h2d->Integral() != 2.5)
         printf("FAIL h2d integral %g\n", h2d->Integral());
      if (TMath::Abs(h2d->GetMean(1) - 0.9) > 1e-12)
         printf("FAIL h2d mean x %.17g\n", h2d->GetMean(1));
      if (TMath::Abs(h2d->GetMean(2) - 2.0) > 1e-12)
         printf("FAIL h2d mean y %.17g\n", h2d->GetMean(2));
      // Variable edges on both axes, from each axis's own fXbins.
      const Double_t xe[3] = {0., 1., 4.};
      const Double_t ye[3] = {0., 2., 10.};
      for (Int_t i = 0; i < 2; ++i) {
         if (h2d->GetXaxis()->GetBinLowEdge(i + 1) != xe[i])
            printf("FAIL h2d x edge %d is %g\n", i,
                   h2d->GetXaxis()->GetBinLowEdge(i + 1));
         if (h2d->GetYaxis()->GetBinLowEdge(i + 1) != ye[i])
            printf("FAIL h2d y edge %d is %g\n", i,
                   h2d->GetYaxis()->GetBinLowEdge(i + 1));
      }
      if (h2d->GetXaxis()->GetBinUpEdge(2) != 4. ||
          h2d->GetYaxis()->GetBinUpEdge(2) != 10.)
         printf("FAIL h2d last edges %g %g\n", h2d->GetXaxis()->GetBinUpEdge(2),
                h2d->GetYaxis()->GetBinUpEdge(2));
      if (h2d->GetBinContent(1, 1) != 2 || h2d->GetBinContent(2, 2) != 0.5)
         printf("FAIL h2d contents %g %g\n", h2d->GetBinContent(1, 1),
                h2d->GetBinContent(2, 2));
      if (TMath::Abs(h2d->GetBinError(1, 1) - 2.0) > 1e-12)
         printf("FAIL h2d error(1,1) %.17g\n", h2d->GetBinError(1, 1));
   }

   TProfile *p1 = (TProfile *)f->Get("p1");
   if (!p1) {
      printf("FAIL no TProfile p1\n");
   } else {
      if (p1->GetEntries() != 4)
         printf("FAIL p1 entries %g\n", p1->GetEntries());
      if (strcmp(p1->GetErrorOption(), "") != 0)
         printf("FAIL p1 error option '%s'\n", p1->GetErrorOption());
      // fArray / fBinEntries, computed on demand and stored nowhere.
      if (p1->GetBinContent(1) != 2 || p1->GetBinContent(2) != 2)
         printf("FAIL p1 contents %g %g\n", p1->GetBinContent(1),
                p1->GetBinContent(2));
      if (p1->GetBinEntries(1) != 2 || p1->GetBinEntries(2) != 1)
         printf("FAIL p1 entries per bin %g %g\n", p1->GetBinEntries(1),
                p1->GetBinEntries(2));
      // The underflow cell holds a fill too, and its content is the mean there.
      if (p1->GetBinContent(0) != 7)
         printf("FAIL p1 underflow %g\n", p1->GetBinContent(0));
      // sqrt(fSumw2[1]/fBinEntries[1] - content^2) / sqrt(fBinEntries[1]).
      if (TMath::Abs(p1->GetBinError(1) - TMath::Sqrt(0.5)) > 1e-12)
         printf("FAIL p1 error %.17g\n", p1->GetBinError(1));
      if (TMath::Abs(p1->GetMean() - 5.0 / 6.0) > 1e-12)
         printf("FAIL p1 mean %.17g\n", p1->GetMean());
   }

   TProfile *p2 = (TProfile *)f->Get("p2");
   if (!p2) {
      printf("FAIL no TProfile p2\n");
   } else {
      // Three fills; the fourth was outside fYmin..fYmax and changed nothing.
      if (p2->GetEntries() != 3)
         printf("FAIL p2 entries %g\n", p2->GetEntries());
      if (p2->GetYmin() != 0 || p2->GetYmax() != 10)
         printf("FAIL p2 Y range %g..%g\n", p2->GetYmin(), p2->GetYmax());
      if (strcmp(p2->GetErrorOption(), "s") != 0)
         printf("FAIL p2 error option '%s'\n", p2->GetErrorOption());
      if (TMath::Abs(p2->GetBinContent(1) - 9.0 / 3.5) > 1e-12)
         printf("FAIL p2 content %.17g\n", p2->GetBinContent(1));
      if (p2->GetBinEntries(1) != 3.5)
         printf("FAIL p2 entries per bin %g\n", p2->GetBinEntries(1));
      // fBinSumw2 is what makes this a weighted spread rather than 1/sqrt(N).
      if (TMath::Abs(p2->GetBinEffectiveEntries(1) - 12.25 / 9.25) > 1e-12)
         printf("FAIL p2 effective entries %.17g\n",
                p2->GetBinEffectiveEntries(1));
      if (TMath::Abs(p2->GetBinError(1) - 1.39970842444753) > 1e-12)
         printf("FAIL p2 error %.17g\n", p2->GetBinError(1));
   }

   // And the streamer infos: eighteen, every checksum agreeing with ROOT's own
   // or BuildCheck warns -- which fails the case.
   TList *infos = f->GetStreamerInfoList();
   if (!infos || infos->GetSize() != 18)
      printf("FAIL streamer info list has %d entries\n",
             infos ? infos->GetSize() : -1);
   if (infos) infos->Delete();

   f->Close();
   printf("VERIFY OK\n");
}
