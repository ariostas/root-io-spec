/// An update meeting free space it did not create, which is what separates a
/// writer that reopens a file from one that only appends.
///
/// The base is closed with a hole in it: `big` is written with a 120-character
/// payload and then overwritten with a short one, so the file has an interior
/// `TFree` entry that the next session inherits. Nothing in the update knows
/// where that hole came from; the free list is all it is told.
///
/// The hole is made with `"overwrite"` rather than `Delete` on purpose.
/// `TDirectoryFile::Delete` is a save: it writes the key list, the directory
/// header and the free list before it returns
/// (TDirectoryFile.cxx:736-738), so a delete costs three record writes and
/// leaves the layout depending on when it happened. `"overwrite"` frees through
/// `TKey::Delete` alone and writes nothing extra.
///
/// Three writes follow the reopen, and each resolves differently:
///
///   * `fits` is the same size as the inherited hole, so it lands in it and the
///     free entry disappears: a record written in one session fills a span
///     another session released;
///   * `overwrite` on `tail` frees the old record before allocating the new
///     one (TDirectoryFile.cxx:1977-1985), so a shorter replacement lands at the
///     old one's address, leaves a 13-byte remainder behind it, and the cycle
///     does not advance, the opposite of the `WriteDelete` in
///     `container/reopened`;
///   * `wide` fits nothing and is appended at the end of the file.
///
/// The close then allocates from the same space: the key list frees its own
/// record before sizing the new one, and the free-segment record is allocated
/// last, out of everything the close itself has just released.
void gen(const char *out)
{
   TString big;
   for (int i = 0; i < 8; ++i) big += "0123456789abcdef";
   big = big(0, 120);                                       // 120 characters

   {
      TFile f(out, "RECREATE", "a hole to inherit", 0);

      TObjString wide(big);
      f.WriteTObject(&wide, "big", "");

      TObjString tail("a record after it, so the hole is interior");
      f.WriteTObject(&tail, "tail", "");

      TObjString cut("cut short, leaving a hole");
      f.WriteTObject(&cut, "big", "overwrite");

      f.Close();
   }

   TFile *u = TFile::Open(out, "UPDATE");

   TObjString fits("fills it up");
   u->WriteTObject(&fits, "fits", "");

   TObjString shorter("shorter than what it replaces");
   u->WriteTObject(&shorter, "tail", "overwrite");

   TObjString wide2(big);
   u->WriteTObject(&wide2, "wide", "");

   u->Close();
   delete u;
}
