/// TGraph and TGraphErrors, the two graph classes a writer needs.
///
/// A TGraph is a TNamed plus three attribute bases, fNpoints, and two counted
/// arrays of doubles. Nothing else in it is data: fHistogram stays null until
/// something draws or fits the graph, and fFunctions is an empty TList that is
/// written all the same.
///
/// Three objects, each with something the others lack:
///   g   a plain graph, fMinimum and fMaximum left at their sentinel
///   gr  the same points with symmetric errors: TGraphErrors adds fEX and fEY
///   gm  a graph with an explicit Y range, so fMinimum and fMaximum are values
///
/// Compression off so every record can be asserted byte for byte.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "graphs", 0);

   const Int_t n = 4;
   Double_t x[n] = {0.0, 1.0, 2.0, 3.0};
   Double_t y[n] = {0.5, 2.5, -1.0, 4.0};
   Double_t ex[n] = {0.1, 0.1, 0.2, 0.2};
   Double_t ey[n] = {0.25, 0.5, 0.25, 0.5};

   TGraph g(n, x, y);
   g.SetName("g");
   g.SetTitle("four points");
   g.Write();

   TGraphErrors gr(n, x, y, ex, ey);
   gr.SetName("gr");
   gr.SetTitle("with errors");
   gr.Write();

   TGraph gm(n, x, y);
   gm.SetName("gm");
   gm.SetTitle("a fixed Y range");
   gm.SetMinimum(-2.0);
   gm.SetMaximum(5.0);
   gm.Write();

   f.Close();
}
