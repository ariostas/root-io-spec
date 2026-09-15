/// A schema evolution rule, as it appears inside the StreamerInfo record.
///
/// TFile::WriteStreamerInfo appends one extra entry to the StreamerInfo TList
/// when any class being written has rules: a nested TList named "listOfRules"
/// whose members are TObjStrings, each holding one rule rendered as flat text
/// by TSchemaRule::AsString. The rules themselves are not streamed as objects.
///
/// The rule is added with TClass::AddRule rather than a #pragma read, because a
/// pragma needs a dictionary and this class is interpreted. The on-disk result
/// is the same: TClass::AddRule and the dictionary path both end in
/// TSchemaRuleSet::AddRule.
///
/// Note that the rule changes nothing about the streamer info itself: fOld and
/// fNew are both real members and both appear as ordinary TStreamerBasicType
/// elements. No kConv, kSkip or kArtificial code is written -- those exist only
/// in memory, after BuildOld has run.
struct Evolved {
   Int_t fOld;
   Int_t fNew;
};

void gen(const char *out)
{
   TClass::AddRule("sourceClass=\"Evolved\" targetClass=\"Evolved\" "
                   "version=\"[1-]\" source=\"Int_t fOld\" target=\"fNew\" "
                   "code=\"{ fNew = onfile.fOld; }\"");

   TFile f(out, "RECREATE", "a schema evolution rule", 0);

   Evolved e;
   e.fOld = 1;
   e.fNew = 2;

   f.WriteObjectAny(&e, "Evolved", "e");
   f.Close();
}
