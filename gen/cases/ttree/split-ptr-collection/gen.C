/// The only way to reach fSplitLevel >= 100, and the two read procedures that
/// depend on it.
///
/// A std::vector<T*> is not splittable by default: TClass::CanSplit returns
/// false for any collection with pointers
/// (root/core/meta/src/TClass.cxx:2354). The exception is an explicit request,
/// made by adding TTree::kSplitCollectionOfPointers (100) to the split level
/// (root/tree/tree/src/TBranchElement.cxx:969-970).
///
/// That hundreds component is then passed down to every sub-branch rather than
/// decremented (root/tree/tree/src/TBranchElement.cxx:6279-6280), so the
/// members of the collection's content end up with fSplitLevel above 100.
/// SetReadLeavesPtr tests that to choose
/// ReadLeavesCollectionSplitVectorPtrMember over ReadLeavesCollectionMember
/// (root/tree/tree/src/TBranchElement.cxx:5779-5787).
///
/// No file in either corpus reaches this. 178 files written by ROOT
/// releases from 4.00 to 6.36 have a maximum fSplitLevel of 99, so the two
/// pointer-collection rows of the dispatch table are unreachable without this
/// fixture.
///
/// Three entries with collections of three sizes, one empty, compression off.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a split collection of pointers", 0);

   TTree t("t", "a vector<T*> split by explicit request");
   PEv pe;
   PEv *p = &pe;
   t.Branch("pc", &p, 32000, TTree::kSplitCollectionOfPointers + 99);

   const Int_t sizes[3] = {2, 0, 1};
   for (int i = 0; i < 3; ++i) {
      pe.clear();
      for (int j = 0; j < sizes[i]; ++j)
         pe.fHits.push_back(new PHit(100 * (i + 1) + j, 0.5f * j));
      t.Fill();
   }
   pe.clear();

   t.Write();
   f.Close();
}
