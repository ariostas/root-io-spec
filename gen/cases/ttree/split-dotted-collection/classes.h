// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef SPLIT_DOTTED_COLLECTION_CLASSES_H
#define SPLIT_DOTTED_COLLECTION_CLASSES_H

#include "Rtypes.h"
#include <vector>

/// The value class of the collection: two members of different widths.
class DHit {
public:
   Int_t   fId = 0;
   Float_t fE = 0;

   DHit() = default;
   DHit(Int_t id, Float_t e) : fId(id), fE(e) {}

   ClassDef(DHit, 1)
};

#ifdef __ROOTCLING__
// The collection is a top-level branch, so nothing else would make ROOT
// generate its proxy; without it TTree::Branch refuses the branch.
#pragma link C++ class std::vector<DHit>+;
#endif

#endif
