/// Double32_t and Float16_t: the two types whose on-disk width is set by the
/// member's comment rather than by its type.
///
/// Every member here holds 1.5 except fRange, which holds 0.5, so the encodings
/// can be compared directly. The widths that result are 4, 4, 3, 3, 4 and 3
/// bytes respectively; fBits15 is wider than fBits14.
///
/// GetRange records the bit count only when it is below 15, so [0,0,15] and
/// above silently produce a plain 4-byte float, and the element does not carry
/// the kHasRange bit. A reader that computed a width
/// from the annotation alone would get this wrong.
struct Quantised {
   Double32_t fPlain;         ///< no annotation
   Double32_t fRange;         ///< [0,1]
   Double32_t fBits8;         ///< [0,0,8]
   Double32_t fBits14;        ///< [0,0,14]
   Double32_t fBits15;        ///< [0,0,15]
   Float16_t  fF16;           ///< [0,0,12]
   Int_t      fEnd;           ///< a sentinel, so the last width is pinned too
};

void gen(const char *out)
{
   TFile f(out, "RECREATE", "quantised floating point", 0);

   Quantised q;
   q.fPlain  = 1.5;
   q.fRange  = 0.5;
   q.fBits8  = 1.5;
   q.fBits14 = 1.5;
   q.fBits15 = 1.5;
   q.fF16    = 1.5;
   q.fEnd    = 0x7f7f7f7f;

   f.WriteObjectAny(&q, "Quantised", "q");
   f.Close();
}
