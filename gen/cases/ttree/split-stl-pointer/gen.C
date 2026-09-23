/// Collection members whose branch's fStreamerType is not the element's 500.
///
/// A TStreamerSTL element stores fType 500 whatever the member is, and its read
/// path computes the code it actually uses: kSTLp (71) when the type name ends
/// in `*`, else kSTL (300), plus kOffsetL (20) for a fixed array
/// (root/core/meta/src/TStreamerElement.cxx:2124-2128). A split member's branch
/// samples that computed code (root/tree/tree/src/TBranchElement.cxx:351), so:
///
///   h               fType 0, fID -2   the split node
///   h/fPtr          fStreamerType 71   vector<PItem>*
///   h/fPtrArr[2]    fStreamerType 91   vector<PItem>*[2]
///   h/fArr[2]       fStreamerType 320  vector<PItem>[2]
///   h/fFlag         fStreamerType 18   Bool_t, against an element of 18
///
/// None of the three collection branches has sub-branches here. Three entries,
/// with collections of zero, one and two elements, and compression off.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "collection members of a split object", 0);

   TTree t("t", "pointers to and arrays of collections");
   PHolder *h = new PHolder;
   t.Branch("h", &h, 32000, 99);

   for (int i = 0; i < 3; ++i) {
      h->fPtr->clear();
      h->fPtrArr[0]->clear();
      h->fPtrArr[1]->clear();
      h->fArr[0].clear();
      h->fArr[1].clear();
      for (int j = 0; j < i; ++j) {
         h->fPtr->emplace_back(10 * i + j, 0.5f * j);
         h->fPtrArr[1]->emplace_back(20 * i + j, 1.5f);
         h->fArr[0].emplace_back(30 * i + j, 2.5f);
      }
      h->fFlag = (i % 2 == 1);
      t.Fill();
   }

   t.Write();
   f.Close();
}
