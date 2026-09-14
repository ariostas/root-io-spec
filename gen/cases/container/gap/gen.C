/// A record deleted from the middle of a file, leaving a gap.
///
/// Exercises the free-segment list with an interior entry, and the negative
/// fNbytes convention that marks the reclaimed span in place so that a reader
/// walking the record chain can skip it.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "deleted record fixture", 0);

   TObjString first("first object, stays");
   f.WriteTObject(&first, "keep_me", "");

   // Padded so the deleted record leaves a gap wide enough to be obvious.
   TString filler;
   for (int i = 0; i < 20; ++i) filler += "delete this payload. ";
   TObjString doomed(filler);
   f.WriteTObject(&doomed, "delete_me", "");

   TObjString last("third object, stays");
   f.WriteTObject(&last, "keep_me_too", "");

   f.Delete("delete_me;1");
   f.Close();
}
