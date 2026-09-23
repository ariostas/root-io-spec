# The CERN corpus

Files published at <https://root.cern/files/> and
<https://root.cern/files/rootbench/>, used to measure whether `spec/` is enough to
read a file nobody designed around it.

**They are not committed.** `build/cern/` is gitignored; `MANIFEST.sha256` records
what was used and `tools/fetch_cern.py` reproduces it.

```sh
tools/fetch_cern.py                  # core tier: 24 files, 5.5 MB
tools/fetch_cern.py --tier physics   # 2 real production trees, 27 MB
tools/fetch_cern.py --headers        # the 11 multi-GB files, by range request
tools/coverage_probe.py --summary build/cern/*.root
tools/check_invariants.py build/cern/*.root
```

## Why this corpus and not just `gen/foreign/`

`gen/foreign/` is uproot's regression suite. Its ROOT-written files span ROOT
5.23/02 to 6.38, which is valuable, but **it contains files uproot wrote**, so a failing invariant
there is a lead that has to be traced to a writer before it is evidence. That
ambiguity took up most of the triage recorded in `PLAN.md` §9.8.

Everything here was written by ROOT and published by the ROOT team. A failure is
evidence about the format.

This corpus also reaches further back. The two files in `gen/foreign/` whose
headers claim ROOT 4.00 were written by g4tools, not by ROOT
([TTree §13](../../spec/04-ttree/TTree.md#13-class-versions)). This corpus covers
**ROOT 2.24/00 through 6.35/01**, about twenty-five years, with known provenance
throughout.

It is also the only source of **large files**: eleven of them from 1.3 GB to
15.9 GB, read by HTTP range request rather than downloaded (see `LARGE.toml`).

## Tier `core` — 24 files, 5.5 MB

Each file below covers something no fixture and no other listed file does. The
`TGeoManager` geometry demos used to be excluded for being near-identical, with
`barres.root` standing in for the family. They now have a tier of their own; the
`geometry` section below gives the reason.

| File | ROOT | Why it is here |
|---|---|---|
| `pippa.root` | **2.24/00** | The oldest file available, by fifteen years. 517 records, **24 nested directories**, **zero streamer infos** (it predates schema evolution entirely), and every payload in the legacy `CS` codec, which this file led to specifying. Found [FileHeader erratum 2](../../spec/01-container/FileHeader.md#11-errata): four bytes past `fEND` in a cleanly closed file |
| `mlpHiggs.root` | 3.04/02 | `TTree` records from before automatic schema evolution; `CS` |
| `H1display.root` | 3.05/07 | ROOT 3.05 at 8.5 KB |
| `stock.root` | 4.00/07 | Ten `TTree` records at **`TBranch` class version 9**, the only sub-10 branches available. Byte-verified [TBranch §13.3](../../spec/04-ttree/TBranch.md#133-at-version-9-the-streamer-info-is-not-authoritative): `fBasketSeek`'s flag byte is a width selector |
| `lhcb_mag.root` | 4.03/04 | ROOT 4.03 |
| `galaxy.root` | 5.01/01 | ROOT 5.01; a `TASImage` payload |
| `linearIO.root` | 5.05/01 | `TMatrixT<float>` and `TMatrixTSym<float>` in 3.8 KB: the divergent classes `PLAN.md` §9.8 named, in a very small file |
| `rootstat.root` | 5.15/07 | `TH1` class version **5**; 82 `TH1F` records |
| `alice_ESDs.root` | 5.16/00 | The only `TBranch` class version **10** available anywhere, with `TTree` v16, 59 streamer infos and 76 baskets |
| `tmva_class_example.root` | 5.18/00 | `TBranch` v10 with a flat tree |
| `stressHistogram.5.18.00.root` | 5.18/00 | `TH1` v6, `TProfile` |
| `stressRooFit_v522_ref.root` | 5.21/07 | RooFit's divergent streamers: `RooPlot`, `RooAbsCollection`, `RooDouble` |
| `barres.root` | 5.23/03 | The smallest `TGeoManager` file, standing in for the whole geometry family |
| `geom_cms_recording.root` | 5.23/05 | `TTree` v16 + `TBranch` v11, 43 baskets |
| `fitpanel_playback.root` | 5.25/05 | `TTree` v18 + `TBranch` v12 |
| `stressRooFit_v534_ref.root` | 5.34/04 | The same RooFit classes eight releases later, with `TH1` v7 |
| `stressRooStats_v534_ref.root` | 5.99/01 | A 5.99 development build; 104 `RooDouble` records |
| `test_distroot_small.root` | 6.07/03 | `TTree` v19 + `TBranch` v12 |
| `Higgs_data.root` | 6.09/03 | 58 baskets across two trees |
| `stressHistogram.testRefRead.6.10.0.root` | 6.11/01 | `TH1` v7 |
| `tmva101.root` | 6.19/01 | Nested directories, `TVectorT<float>`/`TVectorT<double>`, and bare `vector<int>` records |
| `RNTuple.root` | **6.35/01** | The RNTuple container in 2.5 KB. Found [Compression erratum 5](../../spec/01-container/Compression.md#10-errata): an `RBlob` whose payload is *longer* than `fObjLen` and is stored raw |
| `aod_flushed.root` | 5.25/05 | The only available file with a `TTreePerfStats`, whose `TVirtualPerfStats` base has a **forwarding** streamer. It is the independent witness for [Forwarding streamers](../../spec/99-appendix/ForwardingStreamers.md), and makes that list's third entry checkable rather than asserted |
| `gallery.root` | 5.01/01 | A second `TASImage` payload beside `galaxy.root`, so the one specification gap either corpus hits is witnessed in more than one file |

## Tier `physics` — 2 files, 27 MB

Real production trees. Both decode completely, so they reveal nothing new about
the format. They serve as a regression corpus at a scale the fixtures cannot
reach, and they exposed a checker that took 675 seconds, now 40 (`PLAN.md` §9.9).
Expect `check_invariants.py` to take about a minute on `SMHiggsToZZTo4L.root`,
which is why this tier is opt-in.

| File | ROOT | Shape |
|---|---|---|
| `rootbench/SMHiggsToZZTo4L.root` | 6.23/01 | CMS NanoAOD: 42 549 entries, 32 branches, 513 records |
| `rootbench/data_A.GamGam.100k.root` | 6.23/01 | ATLAS open data: 100 000 entries, 81 branches |

`rootbench/` has about thirty more of these, from 7.5 MB to 2.1 GB, listed at
<https://root.cern/files/rootbench/>. There is little point in mirroring more of
them here: they are all flat analysis trees, and two are enough to notice a
regression.

## Tier `geometry` — 46 files, 19 MB

The `TGeoManager` sweep from <https://root.cern/files/>, in seven ROOT releases
from 5.17/07 to 6.08/06: 45 of the 46 are 5.17 to 5.27, and one is 6.08/06.
They are near-identical, mostly one `TGeoManager` per file differing only in the
detector, and on that ground they were deliberately left out, with `barres.root`
in the `core` tier standing in for all of them.

That was a mistake. The sweep had been fetched by hand while chasing a question,
four of the files became published evidence, and nothing recorded that the corpus
the measurements used was larger than the corpus the manifest defined. `PLAN.md`
§8.13 records the gap: `build/cern/` held 72 files where this manifest listed 26.
These results rested on the unlisted 46:

| Where | What |
|---|---|
| [Streamer information §9.2](../../spec/02-serialization/StreamerInfo.md) | four of the five files in its `fBaseVersion` table: `aleph`, `atlas`, `cms` and `hades.root`, the counterexample that stopped a false invariant from being published. Only `uproot-mc10events.root` was listed |
| [Streamer-driven reading §6.1](../../spec/02-serialization/StreamerDriven.md) | most of the 48 `TAtt3D` witnesses, which show that the two g4tools files' missing info is the writer's fault and not ROOT's |
| Every "over both corpora" file count | 471 directory records, 307 files carrying infos, 1368 `TStreamerSTL` elements |

So they are now listed, and the numbers that rest on them are reproducible. Files
are added to a corpus one at a time, each for a stated reason (`PLAN.md` §3.4),
but a file that has already been cited is in the corpus whether the manifest lists
it or not. This tier records the second rule.

They have a cost: `check_invariants.py` over all 72 takes about four minutes,
against one over the 26. They add almost nothing to the entry coverage (28 126
branch-baskets against 28 125 without them) because a geometry file has no trees.
Their value is breadth of classes, not of entries.

## `LARGE.toml` — 11 files, 1.3 GB to 15.9 GB, never downloaded

root.cern serves `Accept-Ranges: bytes`. The header (512 bytes), the
free-segment record, the top directory record and its key list (a few hundred
each) are all that `spec/01-container/`'s large-file statements need, so
`tools/fetch_cern.py --headers` reads those four ranges and checks every recorded
field, for roughly 25 KB of traffic over 49 GB of files.

This covers the following, none of which any fixture covers:

- The `+1000000` `fVersion` flag and `fUnits` 8, on six files from ROOT 5.19 to
  6.23.
- `lhcb2.root` has `fEND` **4 947 894 760**, past 4 GB, so a reader with 32-bit
  offsets cannot address it even unsigned.
- `volume.root` has **51 free segments, 32 in the 18-byte form and 19 in the
  10-byte form, interleaved in one record**. This is the case where
  [FreeSegments §2.1](../../spec/01-container/FreeSegments.md#21-the-large-form)
  says a reader must size each entry separately, and nothing else demonstrates it.
- Two files bracket the boundary from below: `CMS_7250E9A5-…root` is 1.997 GB and
  **not** in the large format, and `AOD.067184.big.pool_4.root` has **1539** free
  segments, all small.
- `CMS_7250E9A5-…root`'s free record has the class name
  `TStorageFactoryFile`, which is why the container's own records must be
  identified structurally rather than by class name.

Since 2026-09-22, three rows come from **CERN Open Data** rather than root.cern.
They have an absolute `url` instead of `path`, and CERN Open Data serves the same
range requests with no redirect (`LARGE.toml`'s header says how to form the URL):

- `Run2012C_TauPlusX.root`, **15.9 GB** at ROOT 6.16/00, three times the next
  largest. Every offset past 8 GB, and a sentinel `fLast` of 16 000 000 000.
- A CMS Run2024F RAW file, 3.27 GB at **6.30/03**, the newest large-format writer
  here; the previous newest was 6.23/01. Its free record is also
  `TStorageFactoryFile`, with an interior entry, so the same CMS writer is now
  listed on both sides of the boundary.
- An LHCb `.ew.dst`, 5.79 GB at **5.34/21**, the last ROOT 5 series, which
  nothing else exercises above 2 GB. The LHCb record has no licence field of its
  own and is CC0 only by the portal's terms. Only the numbers are kept.

`rootbench/Run2012BC_DoubleMuParked_Muons.root` above is an Open Data file too
(record 12341). At both URLs the header, the UUID and the 874-byte free record
are the same bytes, so it is listed once.

## `root/roottest/` — 5 files, already on disk

ROOT's own regression suite has been inside `root-project/root` since April 2025,
so the pinned submodule ships it: 273 `.root` files from ROOT 2.23/12 to 6.41/01,
written by ROOT and published by the ROOT team, the same grade of evidence as the
rest of this corpus. They need no fetch and no manifest, because the submodule
pin (`tools/check_pin.py`) fixes every byte of them.

They are not a tier. The rows below are the ones the specification cites, each
listed for a reason like the rows above. `tools/check_citations.py` reads this
table: a cited file must appear here, and a file here must exist in the
submodule.

| File | ROOT | Why it is here | `check_invariants.py` |
|---|---|---|---|
| `root/roottest/root/tree/friend/MC_uds_reco-1.root` | **2.23/12** | The oldest ROOT-written file in reach, and unlike `pippa.root` it has `TTree`s. Its byte-counted `TTree` holds bases with bare version words, and every class tag in it has a byte count, so [Buffer §6.4](../../spec/02-serialization/Buffer.md#64-legacy-buffers-key-the-map-differently)'s sequential map is never used | 0 failures |
| `root/roottest/root/io/arrayobject/Event.3.2.0.root` | 3.03/02 | A **version 1** directory and no header UUID at 3.03/02, which dated [Directory §7](../../spec/01-container/Directory.md#7-version-history) and [FileHeader §8](../../spec/01-container/FileHeader.md#8-version-history) wrongly until 2026-09-22 | 0 failures |
| `root/roottest/root/io/abstractclass/data_v3_05_07.root` | 3.05/07 | The smallest version-3 directory record, 1 199 bytes | 0 failures |
| `root/roottest/root/io/abstractclass/data_v4_00_02.root` | 4.00/02 | The smallest version-4 directory record, 1 225 bytes | 0 failures |
| `root/roottest/root/io/evolution/skim.root` | 4.03/05 | The only file anywhere with **version-3 `TStreamerElement`s**, which no ROOT release wrote ([StreamerInfo §7.1](../../spec/02-serialization/StreamerInfo.md#71-the-range-fields-moved-out-of-the-record)): 223 of them | 0 failures. Also the witness to [Streamer-driven reading §7.1](../../spec/02-serialization/StreamerDriven.md#71-an-object-with-no-byte-count): `HoldMuo` objects written with no byte count and no version word, which ROOT reads from the first byte when it has no library for the class. Until 2026-09-23 they were two `ReadingEntries 8.5` failures (`PLAN-corpus.md` C18) |

Do not run the checks over the whole directory and treat the result as evidence.
`root/tree/basket/corrupted.root` is damaged on purpose for ROOT's error-handling
tests and produces over four million failures on its own, and three files are
byte-identical to rows above and would be counted twice.

## Standing result

Run 2026-09-21, tier `all`:

- `tools/check_invariants.py`: **72 files, 0 failures**, and every branch-basket
  in them decoded (1696 of 1696). Each `NOT CHECKED` reason names a class or a
  codec rather than passing anything over. Re-measured 2026-09-21 with the
  `geometry` tier listed: 46 more files and one more branch-basket.
- `tools/coverage_probe.py`, re-measured 2026-09-23: 1623 decoded, 264
  container, 480 partial, 13 blocked. The partial ones are overwhelmingly ROOT
  2.x histograms in files with no streamer infos. That is the version floor of
  [the scope statement](../../spec/index.md#how-far-back-it-reads) rather than a
  gap in it. The RooFit records of the two `stressRooFit_*` files, once most of
  the blocked ones, decode since [RooFit](../../spec/03-classes/RooFit.md), except
  the two `RooWorkspace` records below, which are partial; what is still blocked
  is listed in `PLAN.md` §9.9.
- `tools/fetch_cern.py --headers`: **11 files, 0 failures**, re-run 2026-09-22 with
  the three Open Data rows.

> Re-measured 2026-09-18, when `aod_flushed.root` and `gallery.root` were added.
> Both were cited by the specification as corpus files and were in neither this
> table nor `MANIFEST.sha256`, so `fetch_cern.py` did not fetch them and the
> witnesses they carry could not be reproduced.

## Known gaps this corpus exposes

- `RooWorkspace::CodeRepo` is a hand-written streamer this specification does not
  describe. It leaves the one `RooWorkspace` record in each `stressRooFit_*` file
  partly decoded. The other RooFit classes these files hold are
  [RooFit](../../spec/03-classes/RooFit.md).
- `ROOT::RNTuple`'s anchor is read by `rootfile.read_rntuple_anchor` rather than
  by the streamer-driven path, so `check_invariants.py` names it in its
  `NOT CHECKED` output rather than counting it as a failure.
- `RBlob`, RNTuple's page container, has no streamer info by design. It belongs to
  `spec/05-rntuple/`.
- ROOT 2.x and 3.x files carry **no streamer infos at all**, so their `TH1F`/`TH2F`
  records cannot be decoded by anything. That is
  [StreamerDriven §6](../../spec/02-serialization/StreamerDriven.md)'s case, not a
  gap in this specification. `pippa.root` is the file `PLAN.md` §9.1 wanted for
  the `BuildEmulated` path.

**`TBranch` class versions 6 to 9** used to be on this list too. `stock.root`
(ROOT 4.00/07), with ten trees at v9, was the reproducer; they are now
[TBranch §13.1](../../spec/04-ttree/TBranch.md#131-the-layout-below-version-10),
and `tools/rootfile.py` reads them.

The legacy `CS` codec used to be on this list. It turned out to be plain raw
DEFLATE, written up as
[Compression §3.1](../../spec/01-container/Compression.md#31-cs-is-raw-deflate-and-zl-is-zlib-wrapped).
All 468 compressed records of `pippa.root` decompress with it.
