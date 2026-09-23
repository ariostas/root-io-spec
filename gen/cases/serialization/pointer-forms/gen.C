/// Two framing distinctions that are invisible in a member's declared type.
///
/// fArrow is annotated `->`, which promises the pointer is never null. ROOT then
/// writes the pointee with no class record, because no null check and no
/// dynamic type are needed. fPlainP has the same C++ type and no annotation, and
/// gets the full object-reference protocol: byte count, class record, object.
/// The two differ only in the comment.
///
/// fS1 and fS2 are the second distinction. A scalar TString member (kTString,
/// 65) has neither byte count nor version word. The array form (85, kTString +
/// kOffsetL) has both, and its version word is TStreamerInfo's own class
/// version, 10, unrelated to TString.
///
/// Generating this case prints "In2* has no streamer or dictionary" warnings.
/// They are benign, as in serialization/objects: the elements are saved, with
/// fType 68 and 69 as asserted below.
struct In2 { Int_t fV; };

struct Arrow {
   In2     *fArrow;    ///<-> never null, so no class record is written
   In2     *fPlainP;   ///< ordinary pointer, gets a class record
   TString  fS1;       ///< kTString, no framing
   TString  fS2[2];    ///< kTString + kOffsetL, framed
   Int_t    fEnd;      ///< sentinel, so the last width is pinned
};

void gen(const char *out)
{
   TFile f(out, "RECREATE", "pointer and array framing", 0);

   Arrow a;
   a.fArrow  = new In2{0x11111111};
   a.fPlainP = new In2{0x22222222};
   a.fS1 = "a";
   a.fS2[0] = "b";
   a.fS2[1] = "c";
   a.fEnd = 0x7e7e7e7e;

   f.WriteObjectAny(&a, "Arrow", "a");
   f.Close();
}
