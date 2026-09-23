/// A file reopened and added to, which is the other way a ROOT file comes to
/// exist.
///
/// Everything before `Close()` on the first file is a create; everything after
/// `TFile::Open(out, "UPDATE")` is the procedure this case exists for. The three
/// writes that follow use the three options `TObject::Write` offers, and each
/// resolves differently:
///
///   * a **new name**, appended at the end of the file and appended to the key
///     list with cycle 1;
///   * **the same name again**, plain, which appends a second record and
///     inserts its key *before* the first with cycle 2;
///   * **`WriteDelete`**, which writes first and frees afterwards
///     (TDirectoryFile.cxx:1986, :2004-2007). The new record cannot land on the
///     old one's bytes, and its key is appended while the old key is still in
///     the list, so the cycle advances. `overwrite` is the same two operations
///     in the other order; `container/gap-reused` shows it, and
///     `container/reopen-gap` shows it in an update, with the opposite result.
///
/// The main subject of the case is what the close then does: the key list and
/// the free-segment record are both reallocated, each freeing its old span
/// before sizing the new one, while the root directory's 60-byte header is
/// rewritten in place and its key is not rewritten at all.
///
/// Compression is off so every length is arithmetic.
void gen(const char *out)
{
   {
      TFile f(out, "RECREATE", "a file to reopen", 0);
      TObjString first("first");
      f.WriteTObject(&first, "str", "");
      f.Close();
   }

   TFile *u = TFile::Open(out, "UPDATE");

   TObjString second("a name new to the file");
   u->WriteTObject(&second, "two", "");

   TObjString again("the same name, a second cycle");
   u->WriteTObject(&again, "str", "");

   TObjString replaced("written, and then the old one freed");
   u->WriteTObject(&replaced, "two", "WriteDelete");

   u->Close();
   delete u;
}
