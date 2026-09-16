// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef SPLIT_CLONES_CLASSES_H
#define SPLIT_CLONES_CLASSES_H

#include "TObject.h"
#include "TClonesArray.h"

/// A TClonesArray's element class must derive from TObject.
class KHit : public TObject {
public:
   Int_t   fId = 0;
   Float_t fE = 0;

   KHit() = default;
   KHit(Int_t id, Float_t e) : fId(id), fE(e) {}

   ClassDefOverride(KHit, 1)
};

/// The branch's class, holding the array by pointer as ROOT expects.
class KEv {
public:
   TClonesArray *fHits = nullptr;

   KEv() : fHits(new TClonesArray("KHit", 4)) {}
   ~KEv() { delete fHits; }
   KEv(const KEv &) = delete;
   KEv &operator=(const KEv &) = delete;

   ClassDef(KEv, 1)
};

#endif
