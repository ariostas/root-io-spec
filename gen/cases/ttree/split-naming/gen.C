/// The same class split twice, under a plain name and a name ending in a dot.
///
/// TTree::Branch takes the branch name as a string, and a trailing dot in it
/// changes the name of every branch below it, and the fParentName of the
/// deepest one. Nothing else differs: same class, same split level, same data.
///
///   Branch("plain", ...)      Branch("dotted.", ...)
///   plain                     dotted.
///     NBase                     dotted.NBase
///       fB                        dotted.NBase.fB
///     fI                        dotted.fI
///
/// ROOT's own source calls this "very annoying"
/// (root/tree/tree/src/TBranchElement.cxx:476-480). As a result a reader cannot
/// use branch names to recover the object hierarchy: the same class produces two
/// different sets of names, and only the fBranches nesting is reliable.
///
/// Two entries, compression off, so the whole TTree record is assertable.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "branch naming under a trailing dot", 0);

   TTree t("t", "the same class under two branch names");
   NEv plain, dotted;
   t.Branch("plain", &plain, 32000, 99);
   t.Branch("dotted.", &dotted, 32000, 99);

   for (int i = 0; i < 2; ++i) {
      plain.fB  = 10 + i;
      plain.fI  = 20 + i;
      dotted.fB = 30 + i;
      dotted.fI = 40 + i;
      t.Fill();
   }

   t.Write();
   f.Close();
}
