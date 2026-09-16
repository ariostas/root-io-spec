/// The element type codes no other case reaches.
///
///   7    kCharStar     n:i32 then n bytes, no terminator and no 255-escape
///   501  kStreamLoop   a counted array of objects, the count NOT stored
///   81   kObject + kOffsetL
///   82   kAny    + kOffsetL
///
/// fNull and fEmptyLoop are the degenerate forms: a null char* is four zero
/// bytes and indistinguishable from an empty string, and a kStreamLoop whose
/// counter is zero writes its frame and nothing else.
///
/// fPtrArr is here for the negative result: a fixed array of object pointers
/// keeps the scalar code 69, because TStreamerObjectAnyPointer::SetArrayDim
/// does not add kOffsetL the way TStreamerElement::SetArrayDim does.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "element type codes", 0);

   ElementZoo z;

   z.fText = new char[3];
   strcpy(z.fText, "hi");
   z.fNull = nullptr;

   z.fN = 2;
   z.fLoop = new EPoint[2];
   z.fLoop[0] = EPoint(1, 0.5f);
   z.fLoop[1] = EPoint(2, 1.5f);

   z.fM = 2;
   z.fLoopP = new EPoint *[2];
   z.fLoopP[0] = new EPoint(3, 2.5f);
   z.fLoopP[1] = new EPoint(4, 3.5f);

   z.fZ = 0;
   z.fEmptyLoop = new EPoint[1];

   z.fObjArr[0] = EMark(10);
   z.fObjArr[1] = EMark(11);

   z.fAnyArr[0] = EPoint(5, 4.5f);
   z.fAnyArr[1] = EPoint(6, 5.5f);
   z.fAnyArr[2] = EPoint(7, 6.5f);

   z.fPtrArr[0] = new EPoint(8, 7.5f);
   z.fPtrArr[1] = nullptr;

   f.WriteObject(&z, "z");
   f.Close();
}
