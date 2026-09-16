// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef SPLIT_STL_TOPLEVEL_CLASSES_H
#define SPLIT_STL_TOPLEVEL_CLASSES_H

#include "Rtypes.h"
#include <vector>

class SHit {
public:
   Int_t   fId = 0;
   Float_t fE = 0;

   SHit() = default;
   SHit(Int_t id, Float_t e) : fId(id), fE(e) {}

   ClassDef(SHit, 1)
};

/// Never instantiated. It exists so that ACLiC emits a collection proxy for
/// vector<SHit>: without one TTree::Branch refuses the collection outright
/// ("does not have a compiled CollectionProxy"), and a class *containing* the
/// vector is the portable way to ask for it from a header alone.
class SHitHolder {
public:
   std::vector<SHit> fV;

   ClassDef(SHitHolder, 1)
};

#endif
