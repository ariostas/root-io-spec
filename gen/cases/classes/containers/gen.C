/// The three ROOT containers whose `Streamer` is hand-written at every version
/// and which the specification did not describe: `TMap`, `TExMap` and `TBtree`.
/// `tools/inventory.py` listed them; this file pins their bytes.
///
/// Each is written under its own key, uncompressed, so every offset below is a
/// file offset.
///
/// `TMap` and `TBtree` are `TCollection`s, so `Write()` writes each element
/// under its own key unless `kSingleKey` is given. That flag is used here and in
/// no other case.
///
/// The `TMap` stores one `TObjString` as the value of both pairs on purpose. A
/// map's entries are pointer-streamed, so the second occurrence is a
/// back-reference rather than a second copy, and the file shows both forms of
/// the object tag within eleven bytes of each other.
///
/// The `TExMap` gets four entries in a table sized for five, which `Expand`
/// turns into eleven slots. `fSize` is the capacity and `fTally` the count. Both
/// are on disk and they differ here, so a reader cannot use one for the other.
///
/// Two of the four hashes are even, and `Assoc_t::SetHash` forces bit 0 to mark
/// the slot in use, so the file stores 7 for 6 and 11 for 10. The slot follows
/// from the stored hash, which puts the entries in slots 0, 3, 7 and 9: neither
/// contiguous nor in insertion order, since the write loop walks the table by
/// slot. The entry added last is the first on disk.
///
/// The `TBtree` is order 3 with five entries, enough to split the root node,
/// though none of that structure reaches the file. A `TBtree` streams its six
/// shape integers and then hands the elements to the generated
/// `TSeqCollection::Streamer`, whose `TCollection` base dispatches back to a
/// hand-written `Streamer`. This case exists for that path as much as for the
/// three classes.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "the hand-written containers", 0);

   TObjString *alpha = new TObjString("alpha");
   TObjString *beta  = new TObjString("beta");
   TObjString *shared = new TObjString("shared");

   TMap m(3);
   m.SetName("pairs");
   m.Add(alpha, shared);
   m.Add(beta, shared);
   m.Write("m", TObject::kSingleKey);

   TExMap x(5);
   x.Add(3, 101, 1001);
   x.Add(6, 102, 1002);
   x.Add(9, 103, 1003);
   x.Add(10, 104, 1004);
   x.Write("x");

   TBtree b(3);
   b.SetName("sorted");
   for (const char *s : {"p", "q", "r", "s", "t"})
      b.Add(new TObjString(s));
   b.Write("b", TObject::kSingleKey);

   f.Close();
}
