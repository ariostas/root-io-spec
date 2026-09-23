/// TClonesArray in both of its encodings.
///
/// The encoding is chosen by TClonesArray::kBypassStreamer, BIT(12), and that bit
/// is written into the TObject base so that the file is self-describing. Set (the
/// default) means the objects are transposed into one column per member, as in
/// a member-wise collection but with no second version word and no
/// kStreamedMemberWise bit. Clear means one Char_t presence flag per slot,
/// followed by the object in full when the flag is 1.
///
/// fSecond leaves slot 0 empty to show that an empty slot still costs its flag
/// byte, which the shipped documentation omits.
///
/// Pt comes from classes.h and is compiled first; see gen/common/README.md. It
/// needs a real ClassDef because a TClonesArray records its element class as the
/// text "<class>;<version>", and an interpreted class has no version to record.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "TClonesArray encodings", 0);

   TClonesArray *bypass = new TClonesArray("Pt", 2);
   new ((*bypass)[0]) Pt(7, 7.f);
   new ((*bypass)[1]) Pt(8, 8.f);

   TClonesArray *plain = new TClonesArray("Pt", 2);
   new ((*plain)[1]) Pt(9, 9.f);      // slot 0 left empty on purpose
   plain->BypassStreamer(kFALSE);

   f.WriteObject(bypass, "bypass");
   f.WriteObject(plain, "plain");
   f.Close();
}
