/// A TBranchRef and its TRefTable, which is how a TRef is resolved in a tree.
///
/// TTree::BranchRef creates a TBranchRef -- a branch that is *not* in
/// fBranches, but in the tree's own fBranchRef member. Two things about it are
/// easy to get wrong and are the point of this case.
///
/// **It is compressed even in an uncompressed file.** TBranchRef's constructor
/// hard-codes fCompress = 1 (root/tree/tree/src/TBranchRef.cxx:62), so its
/// basket carries a zlib block header while every other basket here is raw.
///
/// **Its basket is not written unless you ask.** TTree::FlushBasketsImpl walks
/// only GetListOfBranches (root/tree/tree/src/TTree.cxx:5255-5265), and
/// fBranchRef is not in that list, so TTree::Write never flushes it. Without
/// the explicit FlushBaskets below the file has a TBranchRef with no basket at
/// all and the references cannot be resolved.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a tree with a ref table", 0);

   TTree *t = new TTree("t", "referencing");
   t->BranchRef();

   TNamed *obj = new TNamed("n", "n");
   TRef ref;
   t->Branch("obj", "TNamed", &obj, 32000, 0);
   t->Branch("ref", "TRef", &ref, 32000, 0);
   for (Int_t i = 0; i < 5; ++i) {
      obj->SetName(TString::Format("n%d", i));
      ref = obj;
      t->Fill();
   }
   t->GetBranchRef()->FlushBaskets();   // required; see above

   t->Write();
   f.Close();
}
