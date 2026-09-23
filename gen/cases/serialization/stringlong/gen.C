/// `TStringLong` against `TString`: a four-byte count with no escape, against a
/// one-byte count that escapes to five.
///
/// Two objects, chosen so that every branch of both encodings appears:
///
///   * `small`, six characters. `TString` writes `06` and the bytes;
///     `TStringLong` writes `00 00 00 06` and the bytes.
///   * `big`, 300 characters. `TString` writes `ff` then `00 00 01 2c` then the
///     bytes (the 255 escape of Conventions 5.1), while `TStringLong` writes
///     `00 00 01 2c` and the bytes, as before. Above 254 characters `TString` is
///     one byte longer, the escape, and the two differ in nothing else.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "TStringLong against TString", 0);

   SText small("abcdef");
   small.Write("small");

   SText big(TString('x', 300).Data());
   big.Write("big");

   f.Close();
}
