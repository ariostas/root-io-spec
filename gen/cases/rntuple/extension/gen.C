/// Late model extension: fields added after a cluster has been committed.
///
/// The page list gives each cluster a list of column ranges, and the document
/// says there is one "for each column in this RNTuple". A cluster committed
/// before the model was extended has ranges only for the columns that existed
/// then, so its list is shorter. ERRATA 14.
///
/// The extension adds a plain `float`, whose column is deferred because two
/// entries were already written, and a `std::vector<std::int32_t>`, whose index
/// column is deferred and whose item column is not: it is below a collection,
/// and the collection had no items before it existed.
///
/// Compression is off so the page list envelope is readable in place.
#include <vector>

void gen(const char *out)
{
   auto model = ROOT::RNTupleModel::Create();
   auto fA = model->MakeField<std::int32_t>("fA");

   ROOT::RNTupleWriteOptions opts;
   opts.SetCompression(0);

   auto writer = ROOT::RNTupleWriter::Recreate(std::move(model), "ext", out, opts);

   // Cluster 0: two entries, one column.
   *fA = 1;
   writer->Fill();
   *fA = 2;
   writer->Fill();
   writer->CommitCluster();

   auto updater = writer->CreateModelUpdater();
   updater->BeginUpdate();
   updater->AddField(ROOT::RFieldBase::Create("fB", "float").Unwrap());
   updater->AddField(ROOT::RFieldBase::Create("fV", "std::vector<std::int32_t>").Unwrap());
   updater->CommitUpdate();

   auto &entry = writer->GetModel().GetDefaultEntry();
   auto fB = entry.GetPtr<float>("fB");
   auto fV = entry.GetPtr<std::vector<std::int32_t>>("fV");

   // Cluster 1: two more entries, four columns.
   *fA = 3;
   *fB = 3.5f;
   *fV = {7, 8};
   writer->Fill();
   *fA = 4;
   *fB = 4.5f;
   *fV = {9};
   writer->Fill();
}
