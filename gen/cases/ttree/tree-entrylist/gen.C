/// Both TEntryList block encodings, and the TEventList they replaced.
///
/// A TEntryList stores entry numbers in TEntryListBlocks of 64000 entries each,
/// in one of two encodings chosen by fType:
///
///   fType 0   a bit vector: 4000 UShort_t, bit (e % 16) of word (e / 16)
///   fType 1   a sorted array of fN UShort_t local entry numbers
///
/// OptimizeStorage converts to the array form only when fewer than 4000 or more
/// than 60000 of the 64000 entries pass (root/tree/tree/src/TEntryListBlock.cxx:546-556);
/// above 60000 it also flips fPassing to false and lists the *absent* entries.
/// `sparse` is optimised into the array form; `dense` is left in bits.
///
/// **The four-argument constructor is required.** TEntryList(name, title, tree)
/// bakes the absolute path of the tree's file into fFileName via
/// gSystem->PrependPathName (root/tree/tree/src/TEntryList.cxx:1311-1322),
/// which would put this checkout's location into the fixture. The
/// (name, title, treename, filename) form stores the string verbatim.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "entry lists", 0);

   // Array form: four entries, two blocks, optimised.
   TEntryList *sparse = new TEntryList("sparse", "array form", "t", "tree-entrylist.root");
   sparse->Enter(0);
   sparse->Enter(3);
   sparse->Enter(5);
   sparse->Enter(64001);          // forces a second block
   sparse->OptimizeStorage();
   sparse->Write();

   // Bit form: left unoptimised, so the block keeps its 4000-word vector.
   TEntryList *dense = new TEntryList("dense", "bit form", "t", "tree-entrylist.root");
   for (Long64_t i = 0; i < 100; i += 3) dense->Enter(i);
   dense->Write();

   // The older, simpler class: a flat sorted array of Long64_t.
   TEventList *ev = new TEventList("ev", "the older form");
   for (Int_t i = 0; i < 100; i += 7) ev->Enter(i);
   ev->Write();

   f.Close();
}
