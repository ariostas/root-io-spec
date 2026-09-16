// Compiled by gen/common/aclic.C before gen.C is loaded; a split branch needs a
// real dictionary. See gen/common/README.md.
#ifndef SPLIT_NAMING_CLASSES_H
#define SPLIT_NAMING_CLASSES_H

#include "Rtypes.h"

/// A base class with one member, so the split produces an fType 1 node with a
/// member under it -- the deepest point at which the naming rule differs.
class NBase {
public:
   Int_t fB = 0;

   ClassDef(NBase, 1)
};

class NEv : public NBase {
public:
   Int_t fI = 0;

   ClassDefOverride(NEv, 1)
};

#endif
