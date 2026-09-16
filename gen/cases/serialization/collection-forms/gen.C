/// The collection forms Collections.md 11 and 16 describe but no file showed.
///
///   std::array<T,N>      NOT a collection: a fixed C array, kOffsetL added
///   std::vector<T> a[N]  a fixed array of collections
///   std::vector<Cls>     member-wise, with a value class that has a ClassDef,
///                        so a plain version word instead of 0 plus a checksum
void gen(const char *out)
{
   TFile f(out, "RECREATE", "collection forms", 0);

   CollectionForms c;

   c.fArrInt = {7, 8, 9};
   c.fArrHit = {CHit(1, 0.5f), CHit(2, 1.5f)};

   c.fVecArr[0] = std::vector<Int_t>{11, 12};
   c.fVecArr[1] = std::vector<Int_t>{13};

   c.fHits.push_back(CHit(3, 2.5f));
   c.fHits.push_back(CHit(4, 3.5f));

   f.WriteObject(&c, "c");
   f.Close();
}
