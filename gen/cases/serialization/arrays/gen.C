/// Array element types: fixed-size, multidimensional, and variable-length.
///
/// Exercises kOffsetL (20 + basic type) for C arrays, which are written with no
/// prefix at all, and kOffsetP (40 + basic type) for a pointer-to-array whose
/// length is given by another member. A kOffsetP member is preceded by a single
/// "is present" byte; the counter member itself has type kCounter.
///
/// fMissing is a second variable-length array left null, to show that the
/// is-present byte is what distinguishes it from an array of zero elements.
struct Arrays {
   Int_t    fN;              ///< counter for fVar and fMissing
   Int_t    fFixed[3];       ///< fixed-size C array
   Double_t fGrid[2][2];     ///< two-dimensional C array
   Int_t   *fVar;            ///< [fN] variable-length, present
   Short_t *fMissing;        ///< [fN] variable-length, left null
};

void gen(const char *out)
{
   TFile f(out, "RECREATE", "array element types", 0);

   Arrays a;
   a.fN = 3;
   a.fFixed[0] = 0x11111111; a.fFixed[1] = 0x22222222; a.fFixed[2] = 0x33333333;
   a.fGrid[0][0] = 1.; a.fGrid[0][1] = 2.; a.fGrid[1][0] = 3.; a.fGrid[1][1] = 4.;
   a.fVar = new Int_t[3]{0x0a0b0c0d, 0x1a1b1c1d, 0x2a2b2c2d};
   a.fMissing = nullptr;

   f.WriteObjectAny(&a, "Arrays", "a");
   f.Close();
}
