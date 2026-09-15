/// A TNtuple, so that the tree is not a record of class TTree.
///
/// TNtuple derives from TTree and adds one member, fNvar. The record's class
/// name is therefore "TNtuple" and the whole TTree layout sits inside it as a
/// base class -- which is why a reader cannot find the trees in a file by
/// matching the class name against "TTree".
///
/// Compression is off so the record can be asserted field by field.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a TNtuple", 0);

   TNtuple n("n", "an ntuple", "x:y:z");
   n.Fill(1, 2, 3);
   n.Fill(4, 5, 6);

   n.Write();
   f.Close();
}
