// Compiled by gen/common/aclic.C before gen.C is loaded, so that Pt has a real
// dictionary and therefore a real class version. An interpreted class would be
// foreign, and TClonesArray records its element class as the text
// "<class>;<version>" -- which for a foreign class would be ";-1".
#ifndef CLONES_ARRAY_CLASSES_H
#define CLONES_ARRAY_CLASSES_H

#include "TObject.h"

/// A TObject-derived element class with an explicit ClassDef version.
///
/// TClonesArray requires a TObject; fX and fY are chosen so that the two
/// member-wise columns have different widths and cannot be confused.
class Pt : public TObject {
public:
   Int_t   fX = 0;
   Float_t fY = 0;

   Pt() = default;
   Pt(Int_t x, Float_t y) : fX(x), fY(y) {}

   ClassDefOverride(Pt, 2)
};

#endif
