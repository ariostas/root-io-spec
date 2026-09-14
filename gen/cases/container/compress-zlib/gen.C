/// One compressed object, using the zlib algorithm (compression setting 101).
///
/// Exercises the compression block header and its zlib magic bytes, and the
/// relationship between TKey::fNbytes, fKeyLen and fObjLen when a payload is
/// stored compressed.
///
/// The payload is repetitive so that every algorithm shrinks it substantially,
/// which keeps the record unambiguously compressed rather than falling back to
/// raw storage.
void gen(const char *out)
{
   TString payload;
   for (int i = 0; i < 200; ++i)
      payload += "ROOT compresses repeated text very well. ";

   TFile f(out, "RECREATE", "zlib compression fixture", 101);
   TObjString s(payload);
   f.WriteTObject(&s, "str", "");
   f.Close();
}
