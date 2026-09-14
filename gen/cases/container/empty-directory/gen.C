/// Two empty subdirectories: one saved, one not.
///
/// A saved empty directory still gets a key-list record, whose payload is just
/// the 4-byte count zero. A directory that was never saved has fSeekKeys == 0
/// and no key-list record at all. Both are legal, and a reader must treat
/// fSeekKeys == 0 as "no keys" rather than as corruption.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "empty directory fixture", 0);

   TDirectory *saved = f.mkdir("saved");
   saved->Write();               // writes its key list, with a count of zero

   f.mkdir("unsaved");           // record only; fSeekKeys stays 0

   f.Close();
}
