/// TNtuple and TNtupleD: what a TTree subclass adds on disk.
///
/// Very little. Each adds one persistent Int_t, fNvar, after the TTree base
/// (root/tree/tree/inc/TNtuple.h:31, root/tree/tree/inc/TNtupleD.h:31); fArgs
/// is transient. Their branches are ordinary single-leaf TBranches with
/// TLeafF and TLeafD leaves respectively.
///
/// The case exists because a reader must find trees by walking the base-class
/// chain rather than by comparing the key's class name against "TTree"
/// (TTree.md section 1), and these are the two most common subclasses that
/// show it. ttree/ntuple already covers TNtuple alone; this pairs it with
/// TNtupleD so the TLeafF/TLeafD difference is visible in one file.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "ntuples", 0);

   TNtuple *n = new TNtuple("n", "single precision", "x:y:z");
   TNtupleD *d = new TNtupleD("d", "double precision", "u:v");
   for (Int_t i = 0; i < 5; ++i) {
      n->Fill(i, i * 2, i * 3);
      d->Fill(i, i * 0.5);
   }
   n->Write();
   d->Write();
   f.Close();
}
