void gen(const char *out)
{
   TFile f(out, "RECREATE", "a canvas", 0);
   TCanvas c("c", "a canvas", 10, 20, 300, 200);
   c.Write();
   f.Close();
}
