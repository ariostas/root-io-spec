/// An incompressible payload written to a file that requests compression.
///
/// When compression does not shrink a payload, ROOT stores it raw with no
/// compression block header at all. The record is then identifiable only by
/// fNbytes - fKeyLen == fObjLen. This fixture pins that fallback.
///
/// The payload comes from a fixed linear congruential sequence rather than
/// gRandom, so the file is reproducible without depending on ROOT's RNG state.
/// It spans the full byte range: restricting it to printable characters leaves
/// only ~6.6 bits of entropy per byte, which zlib still compresses.
void gen(const char *out)
{
   TString payload;
   UInt_t x = 12345u;
   for (int i = 0; i < 512; ++i) {
      x = 1664525u * x + 1013904223u;          // Numerical Recipes LCG
      payload += (char)(1 + (x >> 24) % 255);  // full byte range, minus NUL
   }

   TFile f(out, "RECREATE", "incompressible payload fixture", 101);
   TObjString s(payload);
   f.WriteTObject(&s, "str", "");
   f.Close();
}
