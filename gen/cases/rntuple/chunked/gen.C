/// An RNTuple whose payloads are split across several keys, which no other
/// fixture and neither corpus has: every anchor in them keeps the default
/// `fMaxKeySize` of 1 GiB (`root/tree/ntuple/inc/ROOT/RNTupleWriteOptions.hxx:191`).
///
/// `RNTupleFileWriter::WriteBlob` splits any payload longer than the anchor's
/// `Max Key Size` (`root/tree/ntuple/src/RMiniFile.cxx:1427-1490`), so a limit
/// of 128 bytes splits the header, the footer, the page list and both pages.
/// The limit is set through the same internal setter ROOT's `MiniFile.MultiKeyBlob`
/// test uses (`root/tree/ntuple/test/ntuple_minifile.cxx:471`); nothing public
/// reaches it.
///
/// 31 entries, so that the two pages straddle the limit in the two ways that
/// matter. `n`'s page is 124 bytes of data, under the limit, but 132 with its
/// checksum, so it is split: the test is on the sealed page, checksum included
/// (`root/tree/ntuple/src/RPageStorageFile.cxx:228`). `x`'s page is 248 + 8 =
/// 256 bytes, an exact multiple of the limit, which still needs three chunks
/// because the first one also holds the offsets of the other two.
///
/// Compression is off so the chunks are readable in place.
void gen(const char *out)
{
   auto model = ROOT::RNTupleModel::Create();
   auto fn = model->MakeField<std::int32_t>("n");
   auto fx = model->MakeField<std::int64_t>("x");

   ROOT::RNTupleWriteOptions opts;
   opts.SetCompression(0);
   ROOT::Internal::RNTupleWriteOptionsManip::SetMaxKeySize(opts, 128);

   auto writer = ROOT::RNTupleWriter::Recreate(std::move(model), "ntpl", out, opts);
   for (int i = 0; i < 31; ++i) {
      *fn = i;
      *fx = 1000 + i;
      writer->Fill();
   }
}
