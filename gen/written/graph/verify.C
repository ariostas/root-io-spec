/// Gate 3 for `written/graph`: ROOT reads graphs this project wrote.
///
/// The interesting object is `gy`: its y range is set and its `fHistogram` is
/// null, which is a state ROOT's own API cannot produce because `SetMinimum`
/// goes through `GetHistogram()`. ROOT reads the range back from the members,
/// and builds the histogram on demand when asked for it -- so nothing is lost by
/// leaving the pointer null, which is what `WritingGraphs.md` 3.4 says to do.
///
/// Anything ROOT says on either stream fails the case too, so the absence of
/// output is half the assertion.
void verify(const char *path)
{
   TFile *f = TFile::Open(path);
   if (!f || f->IsZombie()) {
      printf("FAIL cannot open %s\n", path);
      return;
   }
   if (f->GetEND() != 13605) printf("FAIL fEND %lld\n", (long long)f->GetEND());
   if (f->GetNkeys() != 3) printf("FAIL %d keys\n", f->GetNkeys());

   const Double_t x[4] = {0.0, 1.0, 2.0, 3.0};
   const Double_t y[4] = {0.5, 2.5, -1.0, 4.0};

   // --- a plain TGraph -------------------------------------------------
   TGraph *g = (TGraph *)f->Get("g");
   if (!g) {
      printf("FAIL no TGraph at key 'g'\n");
      return;
   }
   if (strcmp(g->ClassName(), "TGraph") != 0)
      printf("FAIL g class %s\n", g->ClassName());
   if (strcmp(g->GetTitle(), "four points") != 0)
      printf("FAIL g title '%s'\n", g->GetTitle());
   if (g->GetN() != 4) printf("FAIL g fNpoints %d\n", g->GetN());
   for (int i = 0; i < 4; ++i) {
      Double_t px = 0, py = 0;
      g->GetPoint(i, px, py);
      if (px != x[i] || py != y[i])
         printf("FAIL g point %d is (%g, %g)\n", i, px, py);
   }
   // The sentinel comes back as -1111, and the points are unsorted.
   if (g->GetMinimum() != -1111) printf("FAIL g fMinimum %g\n", g->GetMinimum());
   if (g->GetMaximum() != -1111) printf("FAIL g fMaximum %g\n", g->GetMaximum());
   if (g->TestBit(TGraph::kClipFrame) == 0)
      printf("FAIL g has no kClipFrame\n");
   if (g->TestBit(TObject::kMustCleanup))
      printf("FAIL g has kMustCleanup, which ROOT does not set on a graph\n");
   // fFunctions is an empty list, not a null pointer.
   if (!g->GetListOfFunctions())
      printf("FAIL g has no fFunctions list\n");
   else if (g->GetListOfFunctions()->GetSize() != 0)
      printf("FAIL g fFunctions holds %d entries\n",
             g->GetListOfFunctions()->GetSize());
   // The points come back in the order they were written, negative y included.
   if (g->GetPointY(2) != -1.0) printf("FAIL g GetPointY(2) %g\n", g->GetPointY(2));

   // --- TGraphErrors ---------------------------------------------------
   TGraphErrors *gr = (TGraphErrors *)f->Get("gr");
   if (!gr) {
      printf("FAIL no TGraphErrors at key 'gr'\n");
      return;
   }
   const Double_t ex[4] = {0.1, 0.1, 0.2, 0.2};
   const Double_t ey[4] = {0.25, 0.5, 0.25, 0.5};
   if (gr->GetN() != 4) printf("FAIL gr fNpoints %d\n", gr->GetN());
   for (int i = 0; i < 4; ++i) {
      if (gr->GetErrorX(i) != ex[i] || gr->GetErrorY(i) != ey[i])
         printf("FAIL gr errors %d are (%g, %g)\n", i, gr->GetErrorX(i),
                gr->GetErrorY(i));
   }

   // --- the range without a histogram ----------------------------------
   TGraph *gy = (TGraph *)f->Get("gy");
   if (!gy) {
      printf("FAIL no TGraph at key 'gy'\n");
      return;
   }
   if (gy->GetMinimum() != -2.0) printf("FAIL gy fMinimum %g\n", gy->GetMinimum());
   if (gy->GetMaximum() != 5.0) printf("FAIL gy fMaximum %g\n", gy->GetMaximum());
   // And ROOT builds the axis histogram on demand, applying the two members.
   TH1F *h = gy->GetHistogram();
   if (!h) {
      printf("FAIL gy GetHistogram() returned null\n");
   } else {
      if (h->GetMinimum() != -2.0)
         printf("FAIL the rebuilt histogram's minimum is %g\n", h->GetMinimum());
      if (h->GetMaximum() != 5.0)
         printf("FAIL the rebuilt histogram's maximum is %g\n", h->GetMaximum());
   }
   f->Close();

   printf("VERIFY OK\n");
}
