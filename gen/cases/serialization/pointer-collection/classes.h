// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef POINTER_COLLECTION_CLASSES_H
#define POINTER_COLLECTION_CLASSES_H

#include "Rtypes.h"
#include <vector>

/// The content class. It has a real dictionary, so its frame carries a plain
/// version word -- 1 -- rather than a 0 and a checksum, and it holds a
/// collection of its own so that the two frames appear back to back.
class PtrItem {
public:
   std::vector<double> fV;

   PtrItem() = default;
   explicit PtrItem(std::vector<double> v) : fV(std::move(v)) {}

   ClassDef(PtrItem, 1)
};

class PointerCollection {
public:
   std::vector<PtrItem *> fPtrs; ///< pointer content: one object slot each
   Int_t                  fEnd = 0;

   ClassDef(PointerCollection, 1)
};

#endif
