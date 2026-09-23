/// Truncated floats inside a split branch, where no TLeafD32 is involved.
///
/// ttree/leaf-truncated covers Double32_t and Float16_t reached through a
/// leaflist, where the leaf class is TLeafD32 or TLeafF16 and the annotation is
/// in the leaf's title. A split branch never produces those classes: every leaf
/// of a TBranchElement is a TLeafElement, which records no width.
///
/// The width of a split Double32_t member can therefore only come from the
/// streamer element's title in the file's StreamerInfo record. This case has
/// five members whose on-disk widths differ, all behind identical TLeafElement
/// leaves, with nothing in the branch or the leaf to tell them apart.
///
///   fPlain   no annotation   4 bytes, a plain float
///   fRange   [0,100]         4 bytes, factor-scaled
///   fBits    [0,100,12]      4 bytes, 12 significant bits
///   fHalf    [0,100]         4 bytes, factor-scaled
///   fHBits   [0,0,10]        3 bytes
///
/// Three entries, compression off.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "truncated floats in a split branch", 0);

   TTree t("t", "a split branch of truncated floats");
   DEv d;
   DEv *p = &d;
   t.Branch("d", &p, 32000, 99);

   for (int i = 0; i < 3; ++i) {
      d.fPlain = 1.5 + i;
      d.fRange = 10.0 + i;
      d.fBits  = 20.0 + i;
      d.fHalf  = 30.0 + i;
      d.fHBits = 40.0 + i;
      d.fTail  = 7 + i;
      t.Fill();
   }

   t.Write();
   f.Close();
}
