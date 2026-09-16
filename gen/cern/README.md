# The CERN corpus

Files published at <https://root.cern/files/> and
<https://root.cern/files/rootbench/>, used to measure whether `spec/` is enough to
read a file nobody designed around it.

**They are not committed.** `build/cern/` is gitignored; `MANIFEST.sha256` records
exactly what was used and `tools/fetch_cern.py` reproduces it.

```sh
tools/fetch_cern.py                  # core tier: 22 files, 5 MB
tools/fetch_cern.py --tier physics   # 2 real production trees, 27 MB
tools/fetch_cern.py --headers        # the 8 multi-GB files, by range request
tools/coverage_probe.py --summary build/cern/*.root
tools/check_invariants.py build/cern/*.root
```

## Why this corpus and not just `gen/foreign/`

`gen/foreign/` is uproot's regression suite. It spans ROOT 4.00 to 6.36 and is
excellent for that, but **it contains files uproot wrote**, so a failing invariant
there is a lead that has to be traced to a writer before it is evidence. That
ambiguity dominated the triage recorded in `PLAN.md` §9.8.

Everything here was written by ROOT and published by the ROOT team. A failure is
evidence about the format.

It also reaches further back: `gen/foreign/` starts at ROOT 4.00, and its two
ROOT-4-labelled files turned out not to be ROOT's output at all
([TTree §13](../../spec/04-ttree/TTree.md#13-class-versions)). This corpus has
**ROOT 2.24/00 through 6.35/01**, a span of about twenty-five years, with real
provenance throughout.

And it is the only source of **large files**: eight of them from 1.3 GB to 5.3 GB,
read by HTTP range request rather than downloaded (see `LARGE.toml`).

## Tier `core` — 22 files, 5 MB

Curated. The listing has roughly forty near-identical `TGeoManager` geometry
demos; one of them is here and the rest are not, because they differ only in their
geometry. Each file below covers something no fixture and no other listed file
does.

| File | ROOT | Why it is here |
|---|---|---|
| `pippa.root` | **2.24/00** | The oldest file in reach, by fifteen years. 517 records, **24 nested directories**, **zero streamer infos** — it predates schema evolution entirely — and every payload in the legacy `CS` codec, which it is what led to specifying. Found [FileHeader erratum 2](../../spec/01-container/FileHeader.md#11-errata): four bytes past `fEND` in a cleanly closed file |
| `mlpHiggs.root` | 3.04/02 | `TTree` records from before automatic schema evolution; `CS` |
| `H1display.root` | 3.05/07 | ROOT 3.05 at 8.5 KB |
| `stock.root` | 4.00/07 | Ten `TTree` records at **`TBranch` class version 9**, the only sub-10 branches in reach. Byte-verified [TBranch §13.1](../../spec/04-ttree/TBranch.md#131-at-version-9-the-streamer-info-is-not-authoritative): `fBasketSeek`'s flag byte is a width selector |
| `lhcb_mag.root` | 4.03/04 | ROOT 4.03 |
| `galaxy.root` | 5.01/01 | ROOT 5.01; a `TASImage` payload |
| `linearIO.root` | 5.05/01 | `TMatrixT<float>` **and** `TMatrixTSym<float>` in 3.8 KB — the divergent classes `PLAN.md` §9.8 named, at the cheapest possible size |
| `rootstat.root` | 5.15/07 | `TH1` class version **5**; 82 `TH1F` records |
| `alice_ESDs.root` | 5.16/00 | The only `TBranch` class version **10** anywhere in reach, with `TTree` v16, 59 streamer infos and 76 baskets |
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

## Tier `physics` — 2 files, 27 MB

Real production trees. Both decode completely, so they find nothing about the
format; their job is to be a regression corpus at a scale the fixtures cannot
reach — and they did expose a 675-second checker, now 40 (`PLAN.md` §9.9). Expect
`check_invariants.py` to take about a minute on `SMHiggsToZZTo4L.root`, which is why
this tier is opt-in.

| File | ROOT | Shape |
|---|---|---|
| `rootbench/SMHiggsToZZTo4L.root` | 6.23/01 | CMS NanoAOD: 42 549 entries, 32 branches, 513 records |
| `rootbench/data_A.GamGam.100k.root` | 6.23/01 | ATLAS open data: 100 000 entries, 81 branches |

`rootbench/` has about thirty more of these, from 7.5 MB to 2.1 GB. They are
listed at <https://root.cern/files/rootbench/> and there is little point in
mirroring more of them here: they are all flat analysis trees, and two is enough to
notice a regression.

## `LARGE.toml` — 8 files, 1.3 GB to 5.3 GB, never downloaded

root.cern serves `Accept-Ranges: bytes`. The header (512 bytes) and the
free-segment record (a few hundred) are all that `spec/01-container/`'s large-file
statements need, so `tools/fetch_cern.py --headers` reads those two ranges and
checks every recorded field. Roughly 8 KB of traffic for 20 GB of files.

What that buys, none of which any fixture covers:

- The `+1000000` `fVersion` flag and `fUnits` 8, on six files from ROOT 5.19 to
  6.23.
- `lhcb2.root` has `fEND` **4 947 894 760** — past 4 GB, so a reader with 32-bit
  offsets cannot address it even unsigned.
- `volume.root` has **51 free segments, 32 in the 18-byte form and 19 in the
  10-byte form, interleaved in one record**. That is exactly the case
  [FreeSegments §2.1](../../spec/01-container/FreeSegments.md#21-the-large-form)
  says a reader must size per entry, and nothing else demonstrates it.
- Two files bracket the boundary from below: `CMS_7250E9A5-…root` is 1.997 GB and
  **not** in the large format, and `AOD.067184.big.pool_4.root` has **1539** free
  segments, all small.
- `CMS_7250E9A5-…root`'s free record carries the class name
  `TStorageFactoryFile`, which is why the container's own records must be
  identified structurally rather than by class name.

## Standing result

Run 2026-09-15, tier `all`:

- `tools/check_invariants.py`: **24 files, 0 failures**, with twelve `NOT CHECKED`
  reasons, each naming a class or a codec rather than passing anything over.
- `tools/coverage_probe.py`: 1396 decoded, 264 container, 515 partial, 205 blocked,
  **0 no codec**. Of the blocked, 197 are RooFit classes in the two
  `stressRooFit_*` files; the partial are overwhelmingly ROOT 2.x histograms in
  files with no streamer infos.
- `tools/fetch_cern.py --headers`: **8 files, 0 failures**.

## Known gaps this corpus exposes

- **`TBranch` class versions 6 to 9** are not specified. `stock.root` (ROOT
  4.00/07) has ten trees at v9 and is the reproducer; `TBranch.md` §13.1 now gives
  the fact that makes the generic algorithm inapplicable there, byte-verified on
  this file. `tools/rootfile.py` refuses them by name.
- `RooAbsCollection` and `ROOT::RNTuple` are hand-written streamers this
  specification does not describe; both are named in `check_invariants.py`'s
  `NOT CHECKED` output rather than counted as failures.
- `RBlob`, RNTuple's page container, has no streamer info by design. It belongs to
  `spec/05-rntuple/`.
- ROOT 2.x and 3.x files carry **no streamer infos at all**, so their `TH1F`/`TH2F`
  records cannot be decoded by anything. That is
  [StreamerDriven §6](../../spec/02-serialization/StreamerDriven.md)'s case, not a
  gap in this specification — and `pippa.root` is the file `PLAN.md` §9.1 wanted
  for the `BuildEmulated` path.

The legacy **`CS`** codec was on this list and is not any more: it turned out to be
plain raw DEFLATE, written up as
[Compression §3.1](../../spec/01-container/Compression.md#31-cs-is-raw-deflate-and-zl-is-zlib-wrapped).
All 468 compressed records of `pippa.root` decompress with it.
