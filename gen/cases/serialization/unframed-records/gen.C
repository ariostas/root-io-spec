/// Records whose payload opens with neither a byte count nor, for most of them,
/// a version word -- the classes of Buffer.md 2.3 that no fixture had written as
/// a record of their own.
///
/// `WriteClassBuffer` asks for a byte count, so a class whose streamer is
/// generated always has one. These five have hand-written streamers that do not:
///
///   TDatime      b << fDatime                     root/core/base/src/TDatime.cxx:415
///   TString      WriteTString, a counted string   root/core/base/src/TString.cxx:1418
///   TStringLong  an i32 length and the chars      root/core/base/src/TStringLong.cxx:131
///   TObject      a version word and no count      root/core/base/src/TObject.cxx:994
///   TQObject     nothing at all                   root/core/base/src/TQObject.cxx:1033
///
/// The case exists because a ROOT-written file in go-hep's corpus, tdatime.root,
/// stores a TDatime as a record, and check_invariants.py rejected it: the
/// specification's list of unframed record payloads left TDatime out.
void gen(const char *out)
{
   TFile f(out, "RECREATE");
   f.SetCompressionSettings(0);

   TDatime d(2026, 9, 22, 12, 0, 0);
   f.WriteObject(&d, "datime");

   TString s("hello");
   f.WriteObject(&s, "tstring");

   TStringLong sl("a long string");
   f.WriteObject(&sl, "tstringlong");

   TObject o;
   o.Write("tobject");

   TQObject q;
   f.WriteObjectAny(&q, TQObject::Class(), "tqobject");
}
