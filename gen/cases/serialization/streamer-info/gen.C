/// The StreamerInfo record itself: a TList of TStreamerInfo, one per class.
///
/// The class produces one element subclass of each shape a reader must hardcode:
/// a TStreamerBasicType for the counter, a TStreamerString for the TString, a
/// TStreamerSTL for the vector, and a TStreamerBasicPointer for the counted
/// array.
///
/// There is deliberately no std::string member, and so no TStreamerSTLstring.
/// An element's fSize is the writer's sizeof, and sizeof(std::string) is 24 with
/// libc++ but 32 with libstdc++, so a file containing one is not reproducible
/// across platforms and cannot serve as a reference file. This is the fSize trap
/// of spec/02-serialization/StreamerInfo.md section 7.
/// sizeof(std::vector<int>) is 24 in both, so the vector is safe.
///
/// TStreamerBase is covered by serialization/object-tags, whose StreamerInfo
/// record carries the infos for TObjString and TNamed and therefore a
/// TStreamerBase for their TObject base. It is not covered here because an
/// interpreted class deriving from TObject crashes ROOT 6.40.04 during the write.
///
/// The class is named Members rather than Info because Info collides with ROOT's
/// Info() logging function in the interpreter.
#include <vector>

struct Members {
   Int_t             fN;
   TString           fStr;
   std::vector<int>  fVec;
   Int_t            *fPtr;   //[fN]
};

void gen(const char *out)
{
   TFile f(out, "RECREATE", "the StreamerInfo record", 0);

   Members a;
   a.fN = 2;
   a.fStr = "s";
   a.fVec = {7, 8};
   a.fPtr = new Int_t[2]{3, 4};

   f.WriteObjectAny(&a, "Members", "a");
   f.Close();
}
