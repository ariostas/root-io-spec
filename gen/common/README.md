# `gen/common/`

Helpers shared by the generator macros in `gen/cases/`.

## `aclic.C` — compiling a dictionary for a case

A case directory may contain a **`classes.h`** alongside its `gen.C`. When it
does, `tools/generate.py` compiles that header with ACLiC before loading the
macro, so the classes it declares have real dictionaries.

```
gen/cases/<group>/<case>/
├── classes.h     optional: classes needing a real ClassDef
├── gen.C
└── case.toml
```

### Why a case would need one

An interpreted class has no `Streamer` method, so `TClass::IsForeign()` is true
for it and ROOT writes **a version word of 0 followed by a checksum** instead of a
version number. Most of the format is unaffected by this, so 63 of the 84 cases
here need no compiler. Three things are affected:

- `TClonesArray`, which records its element class as the text `"<class>;<version>"`;
- a member-wise collection whose value class is versioned, where the second
  version word is a plain `Version_t` rather than 0 plus a checksum;
- a `#pragma read` schema rule, which only a dictionary can carry.

Other cases compile one for a reason their `classes.h` states: the split `ttree/`
cases, the comment annotations `//[fN]` and `//[min,max,bits]`, which only a
dictionary reads, and the `rntuple/` cases, whose user classes RNTuple serializes
through a dictionary.

### The two-step load

`generate.py` runs ROOT roughly as:

```sh
root -l -b -q \
  -e '.L gen/common/aclic.C' -e 'aclic("<case>/classes.h", "build/aclic");' \
  -e '.L <case>/gen.C'       -e 'gen("data/<group>/<case>.root");'
```

The steps cannot be merged. The interpreter parses a macro in full before running
any of it, so a `gen.C` that compiled its own classes in its first line would fail
to parse the lines that use them.

Build products go to `build/aclic/`, which is gitignored. The path does not reach
the generated file.

### Gotchas

- **`classes.h` must be self-contained** and include the ROOT headers it needs.
  It is compiled, not interpreted, so it does not inherit the interpreter's state.
- **Avoid asserting on `sizeof`.** An element's `fSize` is the writing machine's
  `sizeof`. `tools/normalize.py` masks it, but a case should still avoid
  asserting one that is standard-library dependent.
- **macOS: ACLiC needs an SDK the conda compiler understands.** With conda-forge
  ROOT the bundled clang targets an older Darwin, and a recent Xcode SDK fails to
  link with `unknown architecture arm64e.x1` followed by undefined symbols. Point
  `SDKROOT` at an older SDK for the run:

  ```sh
  SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk tools/generate.py
  ```

  This is a property of the local toolchain, so the repository hardcodes no SDK
  path. Linux CI needs no such override.
