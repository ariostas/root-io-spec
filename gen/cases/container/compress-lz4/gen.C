/// One compressed object, using the lz4 algorithm (compression setting 404).
///
/// Exercises the compression block header and its lz4 magic bytes, and the
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

   TFile f(out, "RECREATE", "lz4 compression fixture", 404);
   TObjString s(payload);
   f.WriteTObject(&s, "str", "");
   f.Close();
}
