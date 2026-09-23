/// The seven concrete TArray classes, each written as a record of its own.
///
/// TArray's streamer is the shortest hand-written one in ROOT: an Int_t count
/// and then that many values, with no byte count and no version word. Writing
/// each as a standalone record makes the payload only that, so the record's
/// fObjlen pins the element width.
///
/// The values are chosen so that each array's bytes are distinguishable: the
/// first element is the element width. The second is 0x7F repeated to fill the
/// type for TArrayC, TArrayS and TArrayI, the largest signed value of each; a
/// long decimal constant for TArrayL and TArrayL64; and 0.5 for TArrayF and
/// TArrayD.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "the TArray classes", 0);

   TArrayC c(2); c.SetAt(1, 0);   c.SetAt(127, 1);
   TArrayS s(2); s.SetAt(2, 0);   s.SetAt(32767, 1);
   TArrayI i(2); i.SetAt(4, 0);   i.SetAt(2147483647, 1);
   TArrayL l(2); l.SetAt(8, 0);   l.SetAt(1234567890, 1);
   // SetAt takes a Double_t, so a 64-bit value would be rounded through a
   // double and lose its low bits. Assign fArray directly.
   TArrayL64 q(2); q.SetAt(8, 0); q.fArray[1] = 1234567890123456789LL;
   TArrayF g(2); g.SetAt(4, 0);   g.SetAt(0.5, 1);
   TArrayD d(2); d.SetAt(8, 0);   d.SetAt(0.5, 1);
   TArrayD empty(0);

   f.WriteObjectAny(&c, "TArrayC", "c");
   f.WriteObjectAny(&s, "TArrayS", "s");
   f.WriteObjectAny(&i, "TArrayI", "i");
   f.WriteObjectAny(&l, "TArrayL", "l");
   f.WriteObjectAny(&q, "TArrayL64", "q");
   f.WriteObjectAny(&g, "TArrayF", "g");
   f.WriteObjectAny(&d, "TArrayD", "d");
   f.WriteObjectAny(&empty, "TArrayD", "empty");
   f.Close();
}
