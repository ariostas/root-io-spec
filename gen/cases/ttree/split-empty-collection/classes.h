// Two value classes for split collections. EHit has no data members, so its
// streamer info has no elements and a split std::vector<EHit> gets no
// sub-branches. PHit has one, for contrast.
#include <vector>
#include "Rtypes.h"

class EHit {
public:
   virtual ~EHit() {}
   ClassDef(EHit, 1)
};

class PHit {
public:
   PHit() {}
   explicit PHit(int id) : fId(id) {}
   virtual ~PHit() {}
   int fId = 0;
   ClassDef(PHit, 1)
};

#ifdef __ROOTCLING__
#pragma link C++ class EHit+;
#pragma link C++ class PHit+;
#pragma link C++ class std::vector<EHit>+;
#pragma link C++ class std::vector<PHit>+;
#endif
