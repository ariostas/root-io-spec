// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef PAIRS_CLASSES_H
#define PAIRS_CLASSES_H

#include "Rtypes.h"
#include "TString.h"
#include <map>
#include <string>
#include <vector>

class PHit {
public:
   Int_t   fId = 0;
   Float_t fE = 0;

   PHit() = default;
   PHit(Int_t i, Float_t e) : fId(i), fE(e) {}

   ClassDef(PHit, 1)
};

/// One map per shape a pair<K,V> member can take. Every std::map is written
/// member-wise, so each member is a pair<K,V> column pair.
class PairHolder {
public:
   std::map<std::string, Int_t>          fStrKey;   // string  / fundamental
   std::map<Int_t, std::string>          fStrVal;   // fundamental / string
   std::map<TString, Int_t>              fTStrKey;  // TString / fundamental
   std::map<Int_t, PHit>                 fClassVal; // fundamental / class
   std::map<Int_t, std::vector<Short_t>> fVecVal;   // fundamental / collection
   std::map<TString, PHit *>             fPtrVal;   // TString / pointer
   std::map<std::string, Int_t>          fEmpty;    // left empty on purpose

   ClassDef(PairHolder, 1)
};

#endif
