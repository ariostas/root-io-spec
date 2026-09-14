/// Object and class tags in a TBuffer.
///
/// Exercises: the byte-count word, version words, a new-class record
/// (kNewClassTag followed by a null-terminated class name), a class
/// back-reference (kClassMask), and an object back-reference -- the same
/// pointer appears twice in the list, so the second occurrence is written as a
/// bare buffer position rather than as a second copy of the object.
///
/// The list is written with WriteTObject so that it becomes a single record;
/// TCollection::Write would otherwise write each member as its own key.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "class and object tags", 0);

   TObjString *a = new TObjString("alpha");
   TNamed     *n = new TNamed("nm", "ti");
   TObjString *b = new TObjString("beta");

   TList l;
   l.SetName("lst");
   l.Add(a);            // TObjString: new-class record
   l.Add(n);            // TNamed: a second new-class record
   l.Add(b, "opt");     // TObjString again: class back-reference
   l.Add(a);            // the same pointer again: object back-reference

   f.WriteTObject(&l, "lst", "");
   f.Close();
}
