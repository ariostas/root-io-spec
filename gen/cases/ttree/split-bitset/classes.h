// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef SPLIT_BITSET_CLASSES_H
#define SPLIT_BITSET_CLASSES_H

#include "Rtypes.h"
#include <bitset>

class BEv {
public:
   Int_t           fI = 0;
   std::bitset<16> fBits;
   Int_t           fJ = 0;

   ClassDef(BEv, 1)
};

#endif
