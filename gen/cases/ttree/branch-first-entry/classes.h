// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef BRANCH_FIRST_ENTRY_CLASSES_H
#define BRANCH_FIRST_ENTRY_CLASSES_H

#include "Rtypes.h"
#include <vector>

class FHit {
public:
   Int_t   fId = 0;
   Float_t fE = 0;

   FHit() = default;
   FHit(Int_t id, Float_t e) : fId(id), fE(e) {}

   ClassDef(FHit, 1)
};

/// Declared only so ACLiC generates the collection dictionary for
/// std::vector<FHit *>, which TTree::Branch needs before it will build a
/// TBranchSTL for a top-level branch of that type.
class FHolder {
public:
   std::vector<FHit *> fHits;

   ~FHolder()
   {
      for (auto *h : fHits) delete h;
   }

   ClassDef(FHolder, 1)
};

#endif
