/// Minimal ROOT file: one small uncompressed object in the root directory.
///
/// Exercises: file header, the TFile record, the keys list, the free-segment
/// record, and a single application-layer data record. Compression is disabled
/// so that every record can be read without a decompression step.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "minimal container fixture", 0);
   TObjString s("hello");
   f.WriteTObject(&s, "str", "");
   f.Close();
}
