/// Nested subdirectories, each holding one object.
///
/// Exercises the TDirectoryFile record for a subdirectory as opposed to the
/// root directory: fSeekDir, fSeekParent and fSeekKeys, the separate keys-list
/// record per directory, and the "TDirectory" class name that directory keys
/// carry instead of "TDirectoryFile".
void gen(const char *out)
{
   TFile f(out, "RECREATE", "nested directory fixture", 0);

   TObjString top("at top level");
   f.WriteTObject(&top, "top", "");

   TDirectory *a = f.mkdir("alpha");
   a->cd();
   TObjString inA("inside alpha");
   a->WriteTObject(&inA, "in_alpha", "");

   TDirectory *b = a->mkdir("beta");
   b->cd();
   TObjString inB("inside alpha/beta");
   b->WriteTObject(&inB, "in_beta", "");

   f.Close();
}
