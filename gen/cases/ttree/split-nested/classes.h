// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef SPLIT_NESTED_CLASSES_H
#define SPLIT_NESTED_CLASSES_H

#include "Rtypes.h"
#include <vector>

/// The value type of the collection: two members of different widths.
class NHit {
public:
   Int_t   fId = 0;
   Float_t fE = 0;

   NHit() = default;
   NHit(Int_t id, Float_t e) : fId(id), fE(e) {}

   ClassDef(NHit, 1)
};

/// A class-typed member of the top class, holding a collection of its own.
class NDet {
public:
   Int_t             fNo = 0;
   std::vector<NHit> fHits;

   ClassDef(NDet, 1)
};

/// The branch's class. fDet is what becomes an fType 2 node.
class NTop {
public:
   NDet  fDet;
   Int_t fRun = 0;

   ClassDef(NTop, 1)
};

#endif
