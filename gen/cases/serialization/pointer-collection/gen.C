/// A collection whose content type is a pointer to a class.
///
/// Collections.md 3's table says such an element is "a full object slot, class
/// record and all", and nothing else in `data/` writes one: the only other
/// vector<T*> here is data/ttree/split-ptr-collection.root, where the collection
/// is split into branches and never appears whole.
///
/// The bytes show two frames in a row before the content's own members: the
/// object slot's byte count and class record, then the content class's own byte
/// count and version word. The second is the class frame every object carries,
/// not a second collection frame as an outside review of this specification read
/// it (issue #1 item 10, seen on RooVectorDataStore::RealVector, whose class
/// version is also 1).
///
/// Three elements: two objects and a null pointer, which is four zero bytes and
/// nothing else. The second object writes a class back-reference rather than a
/// name, so all three of the object-slot forms a collection can hold are here.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a collection of pointers", 0);

   PointerCollection c;
   c.fPtrs.push_back(new PtrItem(std::vector<double>{1.0, 2.0}));
   c.fPtrs.push_back(nullptr);
   c.fPtrs.push_back(new PtrItem(std::vector<double>{4.0}));
   c.fEnd = 0x7e7e7e7e;

   f.WriteObject(&c, "c");
   f.Close();
}
