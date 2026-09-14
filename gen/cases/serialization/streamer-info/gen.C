/// The StreamerInfo record itself: a TList of TStreamerInfo, one per class.
///
/// The class is chosen to produce one element subclass of each shape a reader
/// must hardcode: a TStreamerBasicType for the counter, a TStreamerString for
/// the TString, a TStreamerSTL for the vector, a TStreamerSTLstring for the
/// std::string, and a TStreamerBasicPointer for the counted array.
///
/// TStreamerBase is covered by serialization/object-tags, whose StreamerInfo
/// record carries the infos for TObjString and TNamed and therefore a
/// TStreamerBase for their TObject base. It is not covered here because an
/// interpreted class deriving from TObject crashes ROOT 6.40.04 during the
/// write, and because a non-TObject base is reported as having "no streamer or
/// dictionary" and is then saved anyway, which is not a behaviour worth
/// enshrining in a reference file.
///
/// The class is named Members rather than Info because Info collides with
/// ROOT's Info() logging function in the interpreter.
#include <vector>
#include <string>

struct Members {
   Int_t             fN;
   TString           fStr;
   std::vector<int>  fVec;
   std::string       fStd;
   Int_t            *fPtr;   //[fN]
};

void gen(const char *out)
{
   TFile f(out, "RECREATE", "the StreamerInfo record", 0);

   Members a;
   a.fN = 2;
   a.fStr = "s";
   a.fVec = {7, 8};
   a.fStd = "z";
   a.fPtr = new Int_t[2]{3, 4};

   f.WriteObjectAny(&a, "Members", "a");
   f.Close();
}
