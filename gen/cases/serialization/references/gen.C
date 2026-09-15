/// Object references: TProcessID, a referenced TObject, TRef and TRefArray.
///
/// Referencing a TObjString sets TObject::kIsReferenced on it, which adds a
/// trailing UShort_t pidf to its TObject base and forces a TProcessID record
/// into the file. The TProcessID record is written when the first reference is
/// written, so it precedes the object it describes.
///
/// TRef and TRefArray are both written through WriteObjectAny/WriteObject so
/// that their payloads sit in records of their own: TRef is not a TObject and
/// cannot be stored in a collection, and neither can be a data member of an
/// interpreted class without a dictionary.
///
/// Everything here runs in one ROOT session, so TProcessID::fgPIDs has a single
/// entry at index 0 and the top byte of every fUniqueID is 0. A file written by
/// a session that had read process ids from another file would carry a non-zero
/// byte there in the TRef and in TRefArray::fUIDs, which no single-session
/// fixture can show.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "object references", 0);

   TObjString *a = new TObjString("a");

   TRef r(a);            // assigns a->fUniqueID and sets kIsReferenced
   TRefArray *arr = new TRefArray();
   arr->Add(a);

   f.WriteObject(a, "a");
   f.WriteObjectAny(&r, "TRef", "r");
   f.WriteObject(arr, "arr");
   f.Close();
}
