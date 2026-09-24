// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef BASKET_DISPLACEMENT_REFS_CLASSES_H
#define BASKET_DISPLACEMENT_REFS_CLASSES_H

#include "Rtypes.h"
#include "TNamed.h"

/// Two pointers to the same class. Written unsplit, the first carries a
/// new-class record for TNamed and the second only a class back-reference to
/// it, a buffer position inside the same entry.
class DPair {
public:
   TNamed *fA = nullptr;
   TNamed *fB = nullptr;

   DPair() = default;
   ~DPair() { delete fA; delete fB; }

   ClassDef(DPair, 1)
};

#endif
