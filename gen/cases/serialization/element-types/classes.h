// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef ELEMENT_TYPES_CLASSES_H
#define ELEMENT_TYPES_CLASSES_H

#include "Rtypes.h"
#include "TObject.h"

/// Not derived from TObject, so its members take the kAny family (62, 68, 69).
class EPoint {
public:
   Int_t   fI = 0;
   Float_t fX = 0;

   EPoint() = default;
   EPoint(Int_t i, Float_t x) : fI(i), fX(x) {}

   ClassDef(EPoint, 1)
};

/// Derived from TObject, so its members take the kObject family (61, 63, 64).
class EMark : public TObject {
public:
   Int_t fK = 0;

   EMark() = default;
   EMark(Int_t k) : fK(k) {}

   ClassDefOverride(EMark, 1)
};

/// One member per type code no other case reaches.
class ElementZoo {
public:
   char   *fText = nullptr;  ///< 7   kCharStar
   char   *fNull = nullptr;  ///< 7   kCharStar, left null
   Int_t   fN = 0;           ///< 6   kCounter for fLoop
   EPoint *fLoop;            ///<[fN] 501 kStreamLoop, one star: objects
   Int_t   fM = 0;           ///< 6   kCounter for fLoopP
   EPoint **fLoopP;          ///<[fM] 501 kStreamLoop, two stars: object slots
   Int_t   fZ = 0;           ///< 6   kCounter left at zero
   EPoint *fEmptyLoop;       ///<[fZ] 501 with a zero count
   EMark   fObjArr[2];       ///< 81  kObject + kOffsetL
   EPoint  fAnyArr[3];       ///< 82  kAny + kOffsetL
   EPoint *fPtrArr[2];       ///< 69  kAnyP, and NOT 89 -- see case.toml

   ElementZoo() : fLoop(nullptr), fLoopP(nullptr), fEmptyLoop(nullptr)
   {
      fPtrArr[0] = nullptr;
      fPtrArr[1] = nullptr;
   }

   ClassDef(ElementZoo, 1)
};

#endif
