/// A file written with the `?reproducible` URL option: one subdirectory and one
/// small uncompressed object.
///
/// Exercises: the sentinel timestamp ROOT writes in every key, key image and
/// directory record in reproducible mode, and the all-zero UUID in the header and
/// in every directory record (spec/01-container/Record.md §3.7).
///
/// The sentinel is Unix time 1 packed as *local* time, so it depends on the
/// writer's timezone. TZ is fixed to UTC here so that the bytes the case asserts
/// do not depend on the machine that regenerates it; tzset() is needed because
/// localtime_r need not re-read TZ once the process has initialised it.
#include <cstdlib>
#include <ctime>

void gen(const char *out)
{
   setenv("TZ", "UTC", 1);
   tzset();
   TFile f(TString(out) + "?reproducible", "RECREATE", "reproducible fixture", 0);
   f.mkdir("sub");
   TObjString s("hello");
   f.WriteTObject(&s, "str", "");
   f.Close();
}
