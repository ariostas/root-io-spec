// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef BRANCH_CLONES_CLASSES_H
#define BRANCH_CLONES_CLASSES_H

#include "TObject.h"
#include "TClonesArray.h"

class CHitC : public TObject {
public:
   Int_t   fI = 0;
   Float_t fX = 0;

   CHitC() = default;
   CHitC(Int_t i, Float_t x) : fI(i), fX(x) {}

   ClassDefOverride(CHitC, 1)
};

/// A `TClonesArray*` member makes `TTree::BranchOld` produce a
/// `TBranchClones`; `BranchOld` is the only thing in ROOT that constructs one
/// (`root/tree/tree/src/TTree.cxx:2223`).
class CEvtC : public TObject {
public:
   TClonesArray *fHits = nullptr;
   Int_t         fN = 0;

   CEvtC() : fHits(new TClonesArray("CHitC", 8)) {}

   ClassDefOverride(CEvtC, 1)
};

#endif
