// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef COLLECTION_FORMS_CLASSES_H
#define COLLECTION_FORMS_CLASSES_H

#include "Rtypes.h"
#include <array>
#include <vector>

/// A real dictionary, so a member-wise collection of it carries a plain version
/// word rather than a 0 and a checksum.
class CHit {
public:
   Int_t   fId = 0;
   Float_t fE = 0;

   CHit() = default;
   CHit(Int_t i, Float_t e) : fId(i), fE(e) {}

   ClassDef(CHit, 2)
};

class CollectionForms {
public:
   std::array<Int_t, 3>   fArrInt;    ///< not a collection: a fixed C array
   std::array<CHit, 2>    fArrHit;    ///< the same, of objects
   std::vector<Int_t>     fVecArr[2]; ///< a fixed array OF collections
   std::vector<CHit>      fHits;      ///< member-wise, versioned value class

   ClassDef(CollectionForms, 1)
};

#endif
