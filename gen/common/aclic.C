/// Compile a case's `classes.h` into a dictionary, before its `gen.C` is loaded.
///
/// Most cases here define their classes in the interpreter, which is enough for
/// anything written through a streamer info. It is not enough for a class that
/// needs a real ClassDef: an interpreted class has no Streamer method, so ROOT
/// treats it as *foreign* and writes a version word of 0 plus a checksum rather
/// than a version number. Cases that need the versioned form -- TClonesArray,
/// which stores "<class>;<version>" as text, and a member-wise collection whose
/// value class is versioned -- must therefore compile a dictionary first.
///
/// tools/generate.py calls this automatically when a case directory contains a
/// `classes.h`, and then loads `gen.C` in a second step. The two steps cannot be
/// merged: the interpreter parses the whole macro before running any of it, so a
/// `gen.C` that mentions a class compiled in its own first line does not parse.
///
/// Build products go to `builddir`, never next to the source, so that `gen/` stays
/// text-only. The path does not reach the generated file; only the class name and
/// its members do.
void aclic(const char *header, const char *builddir)
{
   gSystem->mkdir(builddir, kTRUE);
   gSystem->SetBuildDir(builddir, kTRUE);

   // "k" keeps the shared library, "f" forces a rebuild. Forcing costs a few
   // seconds per case and removes a class of staleness bug that would otherwise
   // surface as an unexplained digest drift.
   if (!gSystem->CompileMacro(header, "kf")) {
      ::Error("aclic", "could not compile %s -- see gen/common/README.md", header);
      gSystem->Exit(1);
   }
}
