/// Every fixed-width scalar element type, in one streamer-info-driven class.
///
/// The class is defined in this macro, so ROOT builds its TStreamerInfo from
/// the interpreter's view of it. It has no ClassDef and so is foreign: the
/// object's version word is 0 and a checksum follows it, while the streamer info
/// records class version 1. No base class is present, which keeps the record
/// down to a byte count, a version word, a checksum and the members back to
/// back.
///
/// Values are chosen so that every byte of every member is distinct and the
/// big-endian ordering is visible.
struct BasicTypes {
   Char_t    fChar;
   Short_t   fShort;
   Int_t     fInt;
   Long_t    fLong;
   Float_t   fFloat;
   Double_t  fDouble;
   UChar_t   fUChar;
   UShort_t  fUShort;
   UInt_t    fUInt;
   ULong_t   fULong;
   Long64_t  fLong64;
   ULong64_t fULong64;
   Bool_t    fBool;
};

void gen(const char *out)
{
   TFile f(out, "RECREATE", "scalar element types", 0);

   BasicTypes b;
   b.fChar    = 0x41;
   b.fShort   = 0x0102;
   b.fInt     = 0x01020304;
   b.fLong    = 0x0102030405060708L;
   b.fFloat   = 1.5f;                     // 0x3fc00000
   b.fDouble  = -2.5;                     // 0xc004000000000000
   b.fUChar   = 0xfe;
   b.fUShort  = 0xfffe;
   b.fUInt    = 0xfffffffeU;
   b.fULong   = 0x0102030405060708UL;
   b.fLong64  = -2;
   b.fULong64 = 0xfffffffffffffffeULL;
   b.fBool    = true;

   f.WriteObjectAny(&b, "BasicTypes", "b");
   f.Close();
}
