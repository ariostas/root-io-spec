/// A TTreeIndex: the one class in this layer that publishes no streamer info.
///
/// TTree::BuildIndex creates a TTreeIndex and hangs it off fTreeIndex. Its
/// Streamer is fully hand-written (root/tree/treeplayer/src/TTreeIndex.cxx:631)
/// -- it never calls ReadClassBuffer or WriteClassBuffer -- so **no
/// TStreamerInfo for TTreeIndex is written into the file**. Every other class
/// in Auxiliary.md is discoverable from the file it appears in; this one has to
/// be hard-coded from the specification.
///
/// Ten entries with two Run values and five Event values each, so the index is
/// a real permutation rather than the identity: fIndexValues is 1,1,1,1,1,
/// 2,2,2,2,2 and fIndex is 8,6,4,2,0,9,7,5,3,1.
///
/// Compression off, so the TTreeIndex object can be read byte for byte.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a tree with an index", 0);

   TTree *t = new TTree("t", "indexed");
   Int_t run, evt;
   t->Branch("Run", &run, "Run/I");
   t->Branch("Event", &evt, "Event/I");
   for (Int_t i = 0; i < 10; ++i) {
      run = 1 + (i % 2);
      evt = 10 - i;
      t->Fill();
   }
   t->BuildIndex("Run", "Event");   // must precede Write()

   t->Write();
   f.Close();
}
