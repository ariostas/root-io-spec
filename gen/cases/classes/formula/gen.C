/// A `TF1` written by the pinned ROOT: class version 12, holding a `TFormula`
/// at class version 14.
///
/// The case exists for the contrast with a pre-6.02 file. `TF1` v7 lists
/// `TFormula` as its first base class; `TF1` v12 has no `TFormula` base and
/// holds one as a member instead. Each is described by the streamer info in its
/// own file, so a reader that follows the info needs neither layout written
/// down, but a reader that hardcodes "TFormula" by name has two unrelated
/// classes under one name. Formula.md is about telling them apart.
///
/// The function is `gaus` rather than a compiled one, so `fType` is `kFormula`
/// and the write path does not sample the function into `fSave`.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a function and its formula", 0);

   TF1 g("g", "gaus", -3., 3.);
   g.SetParameters(2., 0.5, 1.5);
   g.Write();

   f.Close();
}
