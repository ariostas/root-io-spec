/// Back-references inside a moved basket entry, and ROOT's defect with them.
///
/// A circular tree moves its surviving entries down the basket buffer, and
/// TBasket::MoveEntries records where each entry was in a displacement array
/// (TBasket.md 5.3). The bytes move as they are, so a back-reference inside an
/// entry still names the position its target had when the entry was written.
/// ROOT reads each entry with fDisplacement = offset - displacement added to
/// every such tag (root/tree/tree/src/TBranch.cxx:1739-1744,
/// root/io/io/src/TBufferFile.cxx:2594, :2788).
///
/// That is right only for an entry moved once. MoveEntries overwrites the
/// displacement with the offset before *this* move
/// (root/tree/tree/src/TBasket.cxx:329), so after a second move it no longer
/// names where the entry was written, and ROOT resolves the tag to the wrong
/// place.
///
/// Branch `p` holds a DPair unsplit: two TNamed pointers, so the second one's
/// class tag is a back-reference to the first one's class record, in the same
/// entry. SetCircular(20) keeps 18 entries when the 21st is filled
/// (TTree::KeepCircular, root/tree/tree/src/TTree.cxx:6530), so:
///
///   once    21 fills, one move: every surviving entry moved once
///   twice   24 fills, a second move at the 24th: entries 6 to 20 moved twice
void fill(TTree &t, int n)
{
   static DPair *p = new DPair;
   t.Branch("p", &p, 32000, 0);
   t.SetCircular(20);
   for (int i = 0; i < n; ++i) {
      delete p->fA;
      delete p->fB;
      p->fA = new TNamed(Form("a%d", i), "");
      p->fB = new TNamed(Form("b%d", i), "");
      t.Fill();
   }
}

void gen(const char *out)
{
   TFile f(out, "RECREATE", "back-references in a moved basket", 0);

   TTree once("once", "every entry moved once");
   fill(once, 21);
   once.Write();

   TTree twice("twice", "most entries moved twice");
   fill(twice, 24);
   twice.Write();

   f.Close();
}
