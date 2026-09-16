// Compiled by gen/common/aclic.C before gen.C is loaded. A split branch needs a
// real dictionary: TTree::Branch splits a class by walking its TStreamerInfo,
// and an interpreted class is foreign, so it has no version and ROOT refuses to
// split it.
#ifndef SPLIT_OBJECT_CLASSES_H
#define SPLIT_OBJECT_CLASSES_H

#include "Rtypes.h"

/// A base class with one member, so that the split produces an fType 1 branch.
class Base {
public:
   Int_t fBase = 0;

   ClassDef(Base, 1)
};

/// The branch's class. Members of three different widths, so the three fType 0
/// member branches cannot be confused with one another.
class Ev : public Base {
public:
   Int_t    fI = 0;
   Double_t fD = 0;
   Short_t  fS = 0;

   ClassDefOverride(Ev, 1)
};

#endif
