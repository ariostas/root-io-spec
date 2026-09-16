// Compiled by gen/common/aclic.C before gen.C is loaded. The //[fN] annotation
// only means anything to a dictionary, so this case cannot be interpreted.
#ifndef SPLIT_COUNTER_CLASSES_H
#define SPLIT_COUNTER_CLASSES_H

#include "Rtypes.h"

/// A split class holding a counted pointer: the `Int_t n; Float_t x[n];` shape.
///
/// fN is the counter and fX is the counted array. Split, they become two sibling
/// branches, and the one holding fX records an fBranchCount back-reference to
/// the one holding fN.
class CEv {
public:
   Int_t    fN = 0;
   Float_t *fX = nullptr;   //[fN]
   Int_t    fTail = 0;      // a plain member after the array, to show the
                            // counter relationship does not disturb the rest

   CEv() = default;
   ~CEv() { delete[] fX; }
   CEv(const CEv &) = delete;
   CEv &operator=(const CEv &) = delete;

   ClassDef(CEv, 1)
};

#endif
