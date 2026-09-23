// Compiled by gen/common/aclic.C before gen.C is loaded; see gen/common/README.md.
#ifndef STRINGLONG_CLASSES_H
#define STRINGLONG_CLASSES_H

#include "TObject.h"
#include "TString.h"
#include "TStringLong.h"

/// `TStringLong` has no user anywhere in ROOT (only its own header, its source
/// and a LinkDef mention it), so the only way to get one into a file is to put
/// it in a class of one's own. `fPlain` is the control: the same text in a
/// `TString`, so the two encodings sit side by side in one record.
class SText : public TObject {
public:
   TStringLong fLong;
   TString     fPlain;

   SText() = default;
   SText(const char *s) : fLong(s), fPlain(s) {}

   ClassDefOverride(SText, 1)
};

#endif
