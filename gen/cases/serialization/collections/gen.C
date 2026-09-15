/// STL containers: object-wise and member-wise, and every framing variant.
///
/// The members are chosen so that each one lands in a different branch of the
/// member-wise gate (TStreamerInfoActions.cxx:1183-1188), which requires the
/// collection to have a value *class* that can split:
///
///   fInts   vector<int>           object-wise: no value class
///   fFlags  vector<bool>          object-wise: no value class; one byte per bool
///   fSet    set<int>              object-wise: no value class; fSTLtype 6
///   fHits   vector<Hit>           MEMBER-WISE: Hit is a class and can split
///   fNested vector<vector<int>>   object-wise: a value class that is a collection
///   fWords  vector<string>        object-wise: TClass::CanSplit refuses string
///   fMap    map<int,int>          MEMBER-WISE: the value class is pair<int,int>
///   fStr    string                TStreamerSTLstring, never a collection frame
///   fOne    Hit                   not a collection; see below
///
/// Hit is interpreted and therefore foreign, so the member-wise value-class
/// version word is 0 followed by a checksum. A class with a ClassDef would get a
/// plain version word and no checksum; no interpreted class can show that, so
/// this fixture pins the foreign form only.
///
/// fOne exists only to get Hit's streamer info into the file. Without it ROOT
/// writes the vector<Hit> bytes but records no info for Hit, and the file cannot
/// be read back -- not even by ROOT, which reports "object of class vector<Hit>
/// read too few bytes". That is a real defect and it is silent on the write
/// side; see Collections.md section 9.
///
/// Note what is still NOT in the resulting file even so: a streamer info for
/// pair<int,int>, whose checksum the fMap frame names. A reader must be able to
/// synthesise the pair layout from the type name.
#include <map>
#include <set>
#include <string>
#include <vector>

struct Hit {
   Int_t   x;
   Float_t y;
};

struct Coll {
   std::vector<int>              fInts;
   std::vector<bool>             fFlags;
   std::set<int>                 fSet;
   std::vector<Hit>              fHits;
   std::vector<std::vector<int>> fNested;
   std::vector<std::string>      fWords;
   std::map<int, int>            fMap;
   std::string                   fStr;
   Hit                           fOne;
};

void gen(const char *out)
{
   TFile f(out, "RECREATE", "STL containers", 0);

   Coll a;
   a.fInts   = {1, 2, 3};
   a.fFlags  = {true, false, true};
   a.fSet    = {5, 6};
   a.fHits   = {{10, 1.5f}, {20, 2.5f}};
   a.fNested = {{1, 2}, {3}};
   a.fWords  = {"pq", "rs"};
   a.fMap    = {{1, 100}, {2, 200}};
   a.fStr    = "abc";
   a.fOne    = {30, 3.5f};

   f.WriteObjectAny(&a, "Coll", "a");
   f.Close();
}
