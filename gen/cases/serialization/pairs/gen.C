/// The six shapes a pair<K,V> member takes, and the empty case.
///
/// A std::map is written member-wise because its value class is pair<K,V>
/// (Collections.md 5), so each member is two columns: every `first`, then every
/// `second`. What a column looks like depends on the member's type, and this
/// case has one map per shape:
///
///   std::string   one shared byte count and version, then n counted strings
///   TString       n counted strings, with no shared frame
///   a class       n objects, each with its own byte count and version
///   a collection  one shared frame, then n object-wise collections
///   a pointer     n object slots
///
/// fEmpty is the seventh shape, and the easiest to get wrong: an empty
/// member-wise collection writes its count and then nothing, not even the
/// columns' own headers.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "pair<K,V> member shapes", 0);

   PairHolder h;
   h.fStrKey["ab"] = 1;
   h.fStrKey["cd"] = 2;
   h.fStrVal[7] = "xy";
   h.fStrVal[8] = "z";
   h.fTStrKey["pq"] = 3;
   h.fClassVal[5] = PHit(100, 0.5f);
   h.fVecVal[9] = std::vector<Short_t>{11, 12, 13};
   h.fPtrVal["rs"] = new PHit(7, 1.5f);

   f.WriteObject(&h, "h");
   f.Close();
}
