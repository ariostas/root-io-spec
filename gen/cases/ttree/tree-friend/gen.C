/// A friend tree, recorded in the parent tree's fFriends list.
///
/// TTree::AddFriend stores three things, and the mapping between them and the
/// arguments is not obvious:
///
///   fName       the alias, or the tree name when there is no alias
///   fTitle      the *filename*, or "" when the friend is in the same file
///   fTreeName   the real tree name
///
/// Both friends here live in the same file as the parent, so fTitle is empty
/// and fOwnFile is false (root/tree/tree/src/TFriendElement.cxx:199-203). The
/// second uses the "alias=tree" form, which splits at the '='
/// (root/tree/tree/src/TFriendElement.cxx:59-69), so its fName and fTreeName
/// differ. That is the only way to see that they are separate fields.
void gen(const char *out)
{
   TFile f(out, "RECREATE", "a tree with friends", 0);

   Int_t x, y;
   TTree *t1 = new TTree("t1", "the parent");
   TTree *t2 = new TTree("t2", "the friend");
   t1->Branch("x", &x, "x/I");
   t2->Branch("y", &y, "y/I");
   for (Int_t i = 0; i < 5; ++i) { x = i; y = i * i; t1->Fill(); t2->Fill(); }

   t1->AddFriend("t2");            // fName "t2",    fTreeName "t2"
   t1->AddFriend("alias=t2");      // fName "alias", fTreeName "t2"

   t1->Write();
   t2->Write();
   f.Close();
}
