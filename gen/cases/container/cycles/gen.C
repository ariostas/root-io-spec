/// The same key name written three times, producing cycles 1, 2 and 3.
///
/// Exercises TKey::fCycle and the name;cycle addressing scheme: every version
/// remains in the file, and a lookup without an explicit cycle resolves to the
/// highest one.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "key cycle fixture", 0);
   for (int i = 1; i <= 3; ++i) {
      TObjString s(TString::Format("revision %d", i));
      f.WriteTObject(&s, "str", "");
   }
   f.Close();
}
