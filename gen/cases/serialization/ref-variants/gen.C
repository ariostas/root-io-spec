/// The two TRef variants References.md 3 describes and no file showed: the
/// kHasUUID form, whose trailing u16 becomes a counted string, and a TExec
/// index living in bits 16-23 of the TRef's own fBits.
///
/// Neither arises from an ordinary TRef(obj). kHasUUID belongs to a TRef that
/// names its target by UUID through gROOT's TProcessUUID rather than by a
/// process id, and the TExec index is put there by TRef::SetAction. The
/// generator drives both directly, which is what a file with them in it looks
/// like however it was produced.
///
/// Both are written through WriteObjectAny so each payload sits in a record of
/// its own: TRef is not a TObject and cannot be stored in a collection.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "TRef variants", 0);

   TObjString *a = new TObjString("a");

   // --- the kHasUUID form ------------------------------------------------
   // The UUID is a fixed literal rather than a generated one, so the record is
   // reproducible; a real TRef would carry whatever TUUID the target had.
   TProcessUUID *uuids = gROOT->GetUUIDs();
   UInt_t number = uuids->AddUUID("3f2504e0-4f89-11d3-9a0c-0305e82c3301");
   TRef ruuid;
   ruuid.SetUniqueID(number);
   ruuid.SetBit(TObject::kHasUUID);

   // --- the TExec index --------------------------------------------------
   // AddExec registers the TExec and returns its index; SetAction stores
   // 1 + index shifted left by 16 into fBits. Two of them, so the fixture
   // shows the index is a number and not a flag.
   TRef::AddExec("first");
   TRef::AddExec("second");
   TRef rexec1(a);
   rexec1.SetAction("first");
   TRef rexec2(a);
   rexec2.SetAction("second");

   f.WriteObject(a, "a");
   f.WriteObjectAny(&ruuid, "TRef", "ruuid");
   f.WriteObjectAny(&rexec1, "TRef", "rexec1");
   f.WriteObjectAny(&rexec2, "TRef", "rexec2");
   f.Close();
}
