// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef SPLIT_UNSPLIT_CLASSES_H
#define SPLIT_UNSPLIT_CLASSES_H

#include "Rtypes.h"

class UBase {
public:
   Int_t fB = 0;

   ClassDef(UBase, 1)
};

class UEv : public UBase {
public:
   Int_t    fI = 0;
   Double_t fD = 0;

   ClassDefOverride(UEv, 1)
};

#endif
