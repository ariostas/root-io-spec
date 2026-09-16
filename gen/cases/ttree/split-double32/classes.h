// Compiled by gen/common/aclic.C before gen.C is loaded. The //[min,max,bits]
// annotations only mean anything to a dictionary.
#ifndef SPLIT_DOUBLE32_CLASSES_H
#define SPLIT_DOUBLE32_CLASSES_H

#include "Rtypes.h"

/// All four truncated-float encodings as members of one split class.
class DEv {
public:
   Double32_t fPlain = 0;    //
   Double32_t fRange = 0;    //[0,100]
   Double32_t fBits  = 0;    //[0,100,12]
   Float16_t  fHalf  = 0;    //[0,100]
   Float16_t  fHBits = 0;    //[0,0,10]
   Int_t      fTail  = 0;    //

   ClassDef(DEv, 1)
};

#endif
