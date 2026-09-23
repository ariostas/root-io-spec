/// `TMatrixTSym`, the class whose `Streamer` reads past what its streamer info
/// describes, and the three neighbours in the same family that do not.
///
/// `TMatrixTSym<Element>::Streamer` hands `ReadClassBuffer` the base class's
/// `TClass` (`root/math/matrix/src/TMatrixTSym.cxx:2030`), so the version word on
/// disk is `TMatrixTBase`'s and the file has an info for `TMatrixTBase<T>` and
/// none for the symmetric class. It then reads the upper-right triangle,
/// row by row, `fNcols - i` elements at a time, outside the byte count.
///
/// Five objects, each uncompressed and under its own key except the last:
///
///  - `sym`, a 3x3 `TMatrixDSym` with a distinct value per stored element, so a
///    reader that transposes or that walks the full square is wrong in a visible
///    way. Six doubles reach the file for nine elements.
///  - `symf`, a 2x2 `TMatrixFSym`: the same layout with 4-byte elements, which
///    is the only evidence that the width comes from the template argument and
///    not from the class name.
///  - `gen`, a 2x3 `TMatrixD`, which is ordinary streamer-info driven data: its
///    `fElements` is a counted pointer and all six values are on disk.
///  - `vec`, a `TVectorD`, likewise ordinary, and the class in this family whose
///    `Streamer` is a plain version guard.
///  - `holder`, a `TObjArray` holding one 2x2 `TMatrixDSym`, so the same object
///    appears inside another object's frame: the outer byte count has to
///    include the triangle, where the inner one does not.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "the matrix family", 0);

   TMatrixDSym sym(3);
   for (Int_t i = 0; i < 3; i++)
      for (Int_t j = i; j < 3; j++) {
         sym(i, j) = 10 * (i + 1) + (j + 1);
         sym(j, i) = sym(i, j);
      }
   sym.Write("sym");

   TMatrixFSym symf(2);
   symf(0, 0) = 1.5;
   symf(0, 1) = 2.5;
   symf(1, 0) = 2.5;
   symf(1, 1) = 3.5;
   symf.Write("symf");

   TMatrixD gen(2, 3);
   for (Int_t i = 0; i < 2; i++)
      for (Int_t j = 0; j < 3; j++)
         gen(i, j) = 100 + 10 * i + j;
   gen.Write("gen");

   TVectorD vec(4);
   for (Int_t i = 0; i < 4; i++)
      vec(i) = i + 0.5;
   vec.Write("vec");

   TMatrixDSym *inner = new TMatrixDSym(2);
   (*inner)(0, 0) = 7.0;
   (*inner)(0, 1) = 8.0;
   (*inner)(1, 0) = 8.0;
   (*inner)(1, 1) = 9.0;
   TObjArray holder(1);
   holder.SetName("holder");
   holder.Add(inner);
   holder.Write("holder", TObject::kSingleKey);

   f.Close();
}
