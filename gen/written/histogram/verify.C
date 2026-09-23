/// Gate 3 for `written/histogram`: ROOT reads two histograms this project wrote.
///
/// The assertions are the ones a physicist would notice if they were wrong: the
/// entry count, the mean, the per-bin contents and the per-bin errors, and for
/// the second histogram the variable bin edges. Each is derived by ROOT from
/// a different part of the record: the mean from fTsumwx/fTsumw, the errors from
/// fSumw2, the edges from TAxis::fXbins.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }
   if (f->GetNkeys() != 2) printf("FAIL %d keys\n", f->GetNkeys());

   TH1F *h1 = (TH1F *)f->Get("h1");
   if (!h1) {
      printf("FAIL no TH1F h1\n");
   } else {
      if (h1->GetNbinsX() != 3) printf("FAIL h1 nbins %d\n", h1->GetNbinsX());
      if (h1->GetEntries() != 5) printf("FAIL h1 entries %g\n", h1->GetEntries());
      if (TMath::Abs(h1->GetMean() - 5.0 / 6.0) > 1e-9)
         printf("FAIL h1 mean %.17g\n", h1->GetMean());
      const Double_t want[5] = {1, 2, 1, 0, 1};
      for (Int_t i = 0; i < 5; ++i)
         if (h1->GetBinContent(i) != want[i])
            printf("FAIL h1 cell %d is %g\n", i, h1->GetBinContent(i));
      // From fSumw2, not from the contents.
      if (TMath::Abs(h1->GetBinError(1) - TMath::Sqrt(2.0)) > 1e-9)
         printf("FAIL h1 bin 1 error %g\n", h1->GetBinError(1));
      if (strcmp(h1->GetTitle(), "three bins") != 0)
         printf("FAIL h1 title %s\n", h1->GetTitle());
      if (h1->GetXaxis()->GetXmax() != 3.0)
         printf("FAIL h1 xmax %g\n", h1->GetXaxis()->GetXmax());
      // -1111 means "not set", so ROOT computes a maximum from the data.
      if (h1->GetMaximumStored() != -1111)
         printf("FAIL h1 fMaximum %g\n", h1->GetMaximumStored());
   }

   TH1D *h2 = (TH1D *)f->Get("h2");
   if (!h2) {
      printf("FAIL no TH1D h2\n");
   } else {
      if (h2->GetEntries() != 2) printf("FAIL h2 entries %g\n", h2->GetEntries());
      if (TMath::Abs(h2->GetMean() - 1.4) > 1e-9)
         printf("FAIL h2 mean %.17g\n", h2->GetMean());
      const Double_t edges[4] = {0., 1., 4., 10.};
      for (Int_t i = 0; i < 3; ++i)
         if (h2->GetXaxis()->GetBinLowEdge(i + 1) != edges[i])
            printf("FAIL h2 edge %d is %g\n", i,
                   h2->GetXaxis()->GetBinLowEdge(i + 1));
      if (h2->GetXaxis()->GetBinUpEdge(3) != 10.)
         printf("FAIL h2 last edge %g\n", h2->GetXaxis()->GetBinUpEdge(3));
      if (h2->GetBinContent(1) != 2.0 || h2->GetBinContent(3) != 0.5)
         printf("FAIL h2 contents %g %g\n", h2->GetBinContent(1),
                h2->GetBinContent(3));
      if (TMath::Abs(h2->GetBinError(1) - 2.0) > 1e-9)
         printf("FAIL h2 bin 1 error %g\n", h2->GetBinError(1));
      if (h2->Integral() != 2.5) printf("FAIL h2 integral %g\n", h2->Integral());
   }

   // The streamer infos: fifteen of them. ROOT must agree with every checksum
   // or BuildCheck warns, which fails the case.
   TList *infos = f->GetStreamerInfoList();
   if (!infos || infos->GetSize() != 15)
      printf("FAIL streamer info list has %d entries\n",
             infos ? infos->GetSize() : -1);
   if (infos) infos->Delete();

   f->Close();
   printf("VERIFY OK\n");
}
