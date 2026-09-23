// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef SPLIT_STL_POINTER_CLASSES_H
#define SPLIT_STL_POINTER_CLASSES_H

#include "Rtypes.h"
#include <vector>

/// The value type of every collection here.
class PItem {
public:
   Int_t   fA = 0;
   Float_t fB = 0;

   PItem() = default;
   PItem(Int_t a, Float_t b) : fA(a), fB(b) {}

   ClassDef(PItem, 1)
};

/// Three collection members whose branches record an fStreamerType other than
/// the 500 their streamer elements store, and a bool whose two codes agree.
class PHolder {
public:
   std::vector<PItem> *fPtr = nullptr;        // kSTLp, 71
   std::vector<PItem> *fPtrArr[2] = {};       // kSTLp + kOffsetL, 91
   std::vector<PItem>  fArr[2];               // kSTL + kOffsetL, 320
   Bool_t              fFlag = false;         // kBool, 18, on both sides

   PHolder()
   {
      fPtr = new std::vector<PItem>;
      fPtrArr[0] = new std::vector<PItem>;
      fPtrArr[1] = new std::vector<PItem>;
   }
   ~PHolder()
   {
      delete fPtr;
      delete fPtrArr[0];
      delete fPtrArr[1];
   }
   PHolder(const PHolder &) = delete;
   PHolder &operator=(const PHolder &) = delete;

   ClassDef(PHolder, 1)
};

#endif
