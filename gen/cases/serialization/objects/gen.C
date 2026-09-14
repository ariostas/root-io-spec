/// Object-valued element types: embedded objects, pointers, and TString.
///
/// Exercises kTString (65), kAny (62) for an embedded non-TObject class,
/// kAnyP (69) for a pointer to one, and kObjectP (64) for a pointer to a
/// TObject-derived class. fNullPtr is left null to show how a null pointer is
/// distinguished from an object.
///
/// Generating this case prints "Inner has no streamer or dictionary" warnings.
/// They are benign: TStreamerInfo::Build runs once for Objects before the
/// interpreter has materialised Inner, then again successfully. The streamer
/// info actually stored describes all five members, which is what case.toml
/// asserts.
struct Inner {
   Int_t    fValue;
   Double_t fWeight;
};

struct Objects {
   TString  fStr;        ///< kTString
   Inner    fInner;      ///< embedded by value
   Inner   *fPtr;        ///< pointer, set
   Inner   *fNullPtr;    ///< pointer, left null
   TNamed  *fNamed;      ///< pointer to a TObject-derived class
};

void gen(const char *out)
{
   TFile f(out, "RECREATE", "object element types", 0);

   Objects o;
   o.fStr = "str";
   o.fInner.fValue = 0x01020304;
   o.fInner.fWeight = 1.5;
   o.fPtr = new Inner{0x0a0b0c0d, -2.5};
   o.fNullPtr = nullptr;
   o.fNamed = new TNamed("nm", "ti");

   f.WriteObjectAny(&o, "Objects", "o");
   f.Close();
}
