/// A class whose declared class version is zero: TH1L is ClassDefOverride(TH1L,0).
///
/// A reader cannot resolve this case from the bytes alone. A version word of 0
/// is followed by a 4-byte checksum when the class is *foreign* (no ClassDef;
/// see serialization/basic-types), but by nothing when the class declares
/// version 0, as TH1L does. Here the four bytes after the version
/// word are the byte count of the TH1 base class, not a checksum.
///
/// Two bins, so the payload stays small; the assertions only cover the framing.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "declared class version zero", 0);
   TH1L h("h", "t", 2, 0., 1.);
   h.Fill(0.5);
   f.WriteTObject(&h, "h", "");
   f.Close();
}
