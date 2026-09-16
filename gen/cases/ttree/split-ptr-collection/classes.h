// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef SPLIT_PTR_COLLECTION_CLASSES_H
#define SPLIT_PTR_COLLECTION_CLASSES_H

#include "Rtypes.h"
#include <vector>

/// The pointee class.
class PHit {
public:
   Int_t   fId = 0;
   Float_t fE = 0;

   PHit() = default;
   PHit(Int_t id, Float_t e) : fId(id), fE(e) {}

   ClassDef(PHit, 1)
};

/// A collection **of pointers**. TClass::CanSplit refuses to split one
/// (root/core/meta/src/TClass.cxx:2354) unless the split level asked for is
/// above TTree::kSplitCollectionOfPointers.
class PEv {
public:
   std::vector<PHit *> fHits;

   ~PEv() { clear(); }
   void clear()
   {
      for (auto *h : fHits) delete h;
      fHits.clear();
   }

   ClassDef(PEv, 1)
};

#endif
