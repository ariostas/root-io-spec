/// Records placed into free space, rather than appended at the end.
///
/// `container/gap` shows a record being deleted; this one shows the space being
/// used again, the other half of the allocator and the half a writer has to
/// implement. Three placements happen here, all visible in the finished file:
///
///   * an **exact fit**, where the freed span is the same length as the record
///     that replaces it, so the TFree entry disappears and nothing is left
///     behind. `exact` ends up at the same offset as its first version;
///   * a **partial fit by an unrelated record**, where the record is shorter
///     than the span. `snug` is written long, then overwritten short, and
///     `lodger` is placed in the span it released;
///   * the **remainder**, which keeps its own negative-fNbytes marker, written
///     by the new record's key immediately after its payload.
///
/// The "overwrite" option makes this controllable: it frees the old key before
/// allocating the new one (TDirectoryFile.cxx:1977-1985), so the space
/// is back on the free list in time for the allocation that follows. A plain
/// Write() would append a second cycle and free nothing.
///
/// Compression is off so every payload length is the string length plus a fixed
/// header, and the two overwritten objects use the same 128-character string so
/// that the restored record is the same size as the one it replaces.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "reused free space", 0);

   TString big;
   for (int i = 0; i < 8; ++i) big += "0123456789abcdef";   // 128 characters

   TObjString first(big);
   f.WriteTObject(&first, "exact", "");

   TObjString second(big);
   f.WriteTObject(&second, "snug", "");

   TObjString tail("a record after both, so neither is at the end of the file");
   f.WriteTObject(&tail, "tail", "");

   // exact: shrink, then restore. The shrink frees 213 bytes and uses 90 of
   // them; the restore frees those 90 back, they coalesce with the 123 left
   // over into the original 213, and 213 is what it needs, so the entry is
   // removed.
   TObjString shrunk("short");
   f.WriteTObject(&shrunk, "exact", "overwrite");
   TObjString restored(big);
   f.WriteTObject(&restored, "exact", "overwrite");

   // snug: shrink and leave it, so the remainder is on the free list for
   // whatever is written next.
   TObjString smaller("short");
   f.WriteTObject(&smaller, "snug", "overwrite");

   // `lodger` is small enough to fit what snug released, so it is placed inside
   // a dead record's span rather than at the end of the file. Nothing connects
   // it to snug: the allocator matches on size and address, never on identity.
   TObjString lodger("inside snug's span");
   f.WriteTObject(&lodger, "lodger", "");

   f.Close();
}
