# PLAN-corpus — six external resources, surveyed 2026-09-22

**Status: open. C1 and C2 discharged 2026-09-22**, both with a fixture and a
source citation; C5–C7, C3–C4 and the rest stand. The survey is done; this plan
orders what to do about it.

Six resources were investigated on 2026-09-22, one subagent each, all of them
read-only and all of them made to probe with this project's own tools rather than
to describe what they found:

| Resource | Licence | What it is |
|---|---|---|
| [root-project/roottest](https://github.com/root-project/roottest) | LGPL-2.1 | ROOT's own regression suite — **already inside the pinned submodule** |
| [root-project/rntuple-validation](https://github.com/root-project/rntuple-validation) | LGPL-2.1 | ROOT's RNTuple conformance suite; 50 files in a release asset |
| [go-hep/hep `groot/testdata`](https://codeberg.org/go-hep/hep/src/branch/main/groot/testdata) | BSD-3 | groot's corpus; generating ROOT macros committed alongside |
| [KM3NeT/km3net-testdata](https://github.com/KM3NeT/km3net-testdata) | MIT | a neutrino telescope's production output, 38 files |
| [UnROOT.jl `test/samples`](https://github.com/JuliaHEP/UnROOT.jl/tree/main/test/samples) | MIT | UnROOT's corpus, 94 files |
| [opendata.cern.ch](http://opendata.cern.ch/) | CC0 | real LHC production files, multi-GB, range-readable |

**The result in one line:** four published claims of ours are wrong or
under-scoped, three reader bugs are behind them, four open `PLAN.md` §9 rows have
a witness for the first time, and the single most valuable resource costs nothing
to adopt because it is already on disk.

Two things are worth recording before the items.

**The survey found defects, not just material.** The brief asked what could
*extend* the corpus. What came back first is what the corpus would *break*: every
one of C1–C4 is a statement in `spec/` that a ROOT-written file contradicts. That
is the same shape as §8.13's outside review, and it means `PLAN.md` §8.1 release
criterion 1 — "no published claim is known to be wrong" — is **not met** as of
2026-09-22, and C1–C4 are what it takes to meet it again.

**The rule in `AGENTS.md` applies to all of it**: never weaken an invariant
because a file disagrees. Each of C1–C4 below was diagnosed *against the pinned
submodule* before being written down here, and the citation is in the item. A
file that merely fails is a lead; a file that fails with a source line explaining
why is evidence.

## 1. What was verified, and by whom

The distinction in the last column is load-bearing and is not to be collapsed
when these items are worked. **Confirmed here** means it was reproduced in this
repository with this project's own tools, and the commands are in the item.
**Reported** means one subagent observed it and nothing else has checked it yet;
the first task of such an item is to reproduce it.

| # | Claim | Checked how | Verdict |
|---|---|---|---|
| C1 | A compressed RNTuple page's block chain does **not** fill the record payload | `check_invariants.py` on 4 files → exit 1, 6 failures; gap exactly 8 bytes in each `9.2` case (488/496, 3686/3694) | **✅ discharged**, and cited: `RPageStorage.hxx:74`, `RPageStorage.cxx:751` |
| C2 | A basket does **not** always use the large key layout | census of every `TBasket` key in `root/roottest/`, 62 ROOT releases | **✅ discharged**; the boundary is ROOT 4.02, and the commit that moved it is `3970c0bead` |
| C3 | `Buffer.md` §2.3's unframed-class list omits `TDatime` | one file, `tdatime.root`, in go-hep's corpus | **Reported** — reproduce before acting |
| C4 | `Record.md` §8.6 is false for ROOT 6.34/6.35 RNTuple blob keys | one file; agent traced the fix to `RMiniFile.cxx:963` in the pinned release | **Reported** — reproduce before acting |
| C5 | `check_invariants.py` resolves a base class by name, not `fBaseVersion` | read at `check_invariants.py:846`; symptom is 34 failures on one file | **Reported** — the line is real, the consequence is not reproduced |
| C8 | `skim.root` is the only file anywhere with version-3 `TStreamerElement` | census over 273 files: v4 28 844, v2 7 377, **v3 426, all in one file** | **Reported** — file confirmed present in the submodule |
| C12 | roottest is inside the pinned submodule | `ls root/roottest/` | **Confirmed here** |
| — | Open Data serves HTTP range requests | agent ran this project's own `fetch_range`, `read_header`, `parse_free_entries`, `large_file_problems` → 0 problems | **Reported**, with our tools unmodified |

## 2. Four defects in published prose — these should not wait

### C1. `Compression.md` §9 has no `RBlob` carve-out — ✅ discharged 2026-09-22

**Done**: `Compression.md` §9 is scoped and gains §9.1 *What an `RBlob` is not*;
`NOTES.md` §1 gains the compressed direction; `check_invariants.py` carves the
shape out under the existing labels; and `gen/cases/rntuple/compressed` is the
fixture — 1420 bytes, written by the pinned ROOT, 10 assertions.

**What the fixture added that the survey had not seen.** The carve-out is
narrower than "an `RBlob` is exempt", because the file has four of them: the
header envelope, the page, the page list and the footer. **The three envelopes
close flush and only the page is 8 bytes short** — an envelope's checksum is
inside its own declared length, a page's is not. That distinction is what §9.1
states, and without a file carrying both shapes it could not have been written.

**And the first attempt at the fix was wrong**, which is the part worth keeping:
reporting any misaligned `RBlob` chain as unverifiable let a *corrupted* page
through — `csize + 1` on the fixture passed with exit 0. The discriminator is
`fObjLen`: once the blocks account for it, the payload must close either flush or
8 bytes early, and anything else is a malformed page rather than an unplaceable
one. Corrupting the fixture now fails, and the ordinary-record path still fails
as it always did (verified on `container/compress-lz4`).

Measured after: rntuple-validation 6 Compression failures → 0, UnROOT's RNTuple
tier 37 → 0, roottest's two `cms_opendata` files from `UNREADABLE` → clean. What
remains in those sets is C4 and one unrelated `StreamerDriven 10.5`.

---

§9.2 says the block chain fills the record payload. For an RNTuple page it does
not, and this is not an edge case: it is what ROOT does by default on every page.

```
FAIL compression.algorithms.zlib.root: Compression 9.2: block chain ends at 488, payload ends at 496
FAIL compression.block.big.root:       Compression 9.2: block chain ends at 3686, payload ends at 3694
```

The 8 bytes are the page's XXH3-64 checksum, appended **after** compression and
outside `fObjLen`. `root/tree/ntuple/inc/ROOT/RPageStorage.hxx:74` defines
`kNBytesPageChecksum = sizeof(std::uint64_t)`; `root/tree/ntuple/src/RPageStorage.cxx:751`
seals a page as `RSealedPage sealedPage{pageBuf, nBytesZipped + nBytesChecksum, …}`;
`RPageStorage.hxx:113-114` subtracts it back off on the read side.

A second, worse form: **one `RBlob` may hold several pages, some raw and some
compressed**, so `fObjLen` comes out *larger* than the payload. Then
`is_compressed()` returns true and the whole file becomes unwalkable —
`coverage_probe.py` reports `UNREADABLE`. `test_nested_structs_rntuple_v1-0-0-0.root`
gives `fObjlen` 280 against a chain decoding to 0 and `unknown compression magic
b'\x00\x02'`. The arithmetic closes exactly on a roottest file: `RBlob` at 688,
six sealed pages, Σ usize 11060 = `fObjLen`, Σ(9 + csize + 8) = 5529 = `fNbytes − fKeyLen`.

`spec/05-rntuple/NOTES.md` §1 already predicts the *uncompressed* direction
(`fObjLen` short, payload raw with trailing slack). This is the compressed
direction it does not list, where the `>` form fails as badly as the `!=` form.

Three independent witnesses: rntuple-validation, scikit-hep-testdata's RNTuple
tier, and roottest. Nothing in `data/` or either corpus has a compressed RNTuple
page, which is why this was never seen — all eight RNTuple generators call
`opts.SetCompression(0)`.

**To do:** state the exception in `Compression.md` §9; extend `NOTES.md` §1 with
the compressed direction; teach `check_invariants.py` the carve-out **without
weakening §9 for ordinary records**; add a fixture — the cheapest is an
`rntuple/anchor`-style case written by the pinned ROOT with compression *on*,
which this project can generate itself rather than vendoring.

### C2. `TBasket.md` §1's "always" is true only from ROOT 4.02 — ✅ discharged 2026-09-22

**Done**: §1 is scoped and carries the reason; invariant 2 and pitfall row 2 are
scoped with it; `check_invariants.py` gates `TBasket 9.2` on the writing release;
`IGNORE.toml`'s `uproot-issue413.root` entry is re-argued.

**The boundary is now cited, not just measured.** `git log -S` on the submodule
finds `3970c0bead`, 2004-09-10, first in `v4-01-02` and first in a production
release at **4.02/00** — which is exactly where the census puts it. Its message
gives the reason, and it is the same one `LargeFiles.md` §1.1 records: *"a
TBasket created long before the file reaches 2 GBytes and written long after the
file has been above 2 GBytes."* The width cannot be decided when the record is
written, so ROOT pays 8 bytes on every basket rather than know.

**A number in this plan was wrong.** The survey reported 238 small-form basket
keys; the real figure, counted here, is **12 385 in 19 files** — including 1139
in `BcMC.root` and 10 752 in `sm.root`, both at header 4.00/04, which is what
puts 4.00 firmly on the small side of the boundary.

**`IGNORE.toml` keeps its conclusion and changes its argument.** "The key is
small-form" is not on its own evidence about a writer, now that ROOT itself is
known to write them; it is evidence there because that file's header names
6.18/04, sixteen years past the boundary. The entry still suppresses its 6
failures, checked — so it did not quietly become a no-op.

---

§1 says, in bold: *"A basket always uses the large key layout. Its constructor
does `fVersion += 1000` unconditionally (`root/tree/tree/src/TBasket.cxx:71`), so
`fSeekKey` and `fSeekPdir` are 8 bytes each however small the file is. This is
the only place in ROOT where the large form appears in a file under 2 GB."*

The citation is correct for the pinned release — the line is there and it is
unconditional. The **scope** is wrong. Census of every `TBasket` key in
`root/roottest/`:

| ROOT release | `TBasket` key `fVersion` |
|---|---|
| 2.23/12 – 3.10/02 | **2** — small form |
| 4.00/04 | **3** — still small |
| 4.02/00 – 4.04/02 | 1003 |
| 5.10/00 – 6.41/01 | 1004 |

So `fVersion += 1000` arrives in **ROOT 4.02**, and 238 basket keys in files ROOT
wrote carry the small form. Reader-facing in both directions: §1's own pitfall
table row 2 warns that a reader switching on file size reads `fSeekKey` four bytes
*short*, and the inverse is now also true — a reader that unconditionally assumes
the large form reads a pre-4.02 basket four bytes *long*.

**To do:** scope the claim in `TBasket.md` §1 and its pitfall row; find the ROOT
4.02 commit that added the line, so the boundary is cited and not merely measured;
**re-examine `gen/foreign/IGNORE.toml`'s `uproot-issue413.root` entry**, which
rests its diagnosis on "ROOT adds 1000 unconditionally" — the conclusion is
probably still right, since that file claims a modern release, but the stated
ground needs the version qualifier or the entry is unsound.

### C3. `Buffer.md` §2.3 omits `TDatime` — reported, reproduce first

`tdatime.root` (go-hep, 7 209 B, ROOT 6.24/06, generated by a committed ROOT
macro) is the only invariant failure in that corpus from a ROOT-written file:

```
FAIL tdatime.root: Buffer 9.2: payload of 4 bytes at 244 is too short for a byte count and a version
```

A top-level key of class `TDatime`, `fObjlen` 4, payload `2c 44 f1 05` — no byte
count, no version word, because `TDatime::Streamer` (`root/core/base/src/TDatime.cxx:415-422`)
writes `fDatime` and nothing else. §2.3 enumerates the classes whose record
payload does not open with a byte count — `TRef`, `RooLinkedList`, `TArray*`,
`TBasket` — and omits `TDatime`. So does `UNFRAMED` at `check_invariants.py:528`,
**even though the same file already special-cases `TDatime` at line 636**. One
class name missing in two places.

**To do:** reproduce; then add `TDatime` to §2.3 and to `UNFRAMED`; check whether
any other class in `inventory.py`'s 187 hand-written Streamers has the same shape
and is likewise absent — the census exists, so this should be asked once and
answered for all of them rather than one class at a time.

### C4. `Record.md` §8.6 needs a ROOT 6.34/6.35 exception — reported

§8.6 says `fSeekPdir` names a directory record. In one 27 KB RNTuple file every
`RBlob` key has **`fSeekPdir` equal to its own offset**. Reported diagnosis:
ROOT 6.34/6.35's `RNTupleFileWriter::ReserveBlobKey` wrote
`RTFKey keyHeader(offset, offset, …)`; the pinned 6.40.04 has
`RTFKey keyHeader(offset, RTFHeader::kBEGIN, …)` at
`root/tree/ntuple/src/RMiniFile.cxx:963`.

**To do:** reproduce and confirm both source lines — the *old* one needs a
release tag, since the pinned submodule no longer contains it, and a claim about
6.34/6.35 that cannot be cited at 6.40.04 needs `check_citations.py`-friendly
handling. Then state the exception.

## 3. Three reader and checker bugs

- **C5. `check_invariants.py:846` resolves a base class with `by_name.get(e.name)`**
  — one info per class name. On a file carrying two infos for one class at
  different versions it picks the wrong one. The correct match is by
  `fBaseVersion`, which `StreamerInfo.md` §9.2 already tabulates. Reported symptom
  is 34 failures on a g4tools file, which is a lead, not evidence — but the bug is
  ours regardless of which file exposed it.
- **C6. `rootfile.read_rntuple_anchor()` cannot read a compressed anchor.** It
  reads `buf` at `payload_range()` directly. `ntpl001_staff_rntuple_v1-0-1-0.root`
  has one (`nbytes` 125, `fKeylen` 55, `fObjlen` 78), as do the roottest 6.37/01
  files (a ZSTD anchor, payload beginning `5a 53 01`).
- **C7. `rootfile.payload_range()` returns `start + obj_len`**, which for a
  multi-page `RBlob` runs past the record's end into the next key. Same root cause
  as C1; fix them together.

## 4. Four §9 rows with a witness for the first time

All four files are **already on disk** in `root/roottest/`, except C9.

| # | Row | File | Evidence |
|---|---|---|---|
| C8 | §9.1 version-3 `TStreamerElement` with `fXmin`/`fXmax`/`fFactor` — ☐ *"not in either corpus"* | `root/roottest/root/io/evolution/skim.root`, 26 603 B, ROOT 4.03/05 | 426 v3 elements, **every one in this file**; exercises `rootfile.py`'s `if elem.version == 3: eo += 24`, which nothing has ever reached |
| C9 | §9.1 a leaf class at a legacy version — ☐ *"v2 and v4 are the current versions and are all that occur"* | go-hep `leaves.root`, 15 094 B, ROOT 6.28/04 | `TLeafF16`/`TLeafD32` at class version **1** where the pinned headers are `ClassDefOverride(…, 2)`; frame bytes `40 00 00 3e 00 01` |
| C10 | §9.1 a buffer written with no byte counts — ☐ *"needs a pre-ROOT-3 file"* | `root/roottest/root/tree/friend/MC_uds_reco-1.root`, 614 718 B, ROOT **2.23/12** | one outer byte count, then `TNamed` and `TObject` with none of their own; older than `pippa.root` and, unlike it, **has `TTree`s** |
| C11 | §9.1 directory record versions 1, 3, 4 — ✅ read, no fixture | `root/roottest/root/io/abstractclass/data_v3_05_07.root` (1 199 B) and `data_v4_00_02.root` (1 225 B) | cheapest witnesses that exist; directory version 2 occurs in **0 of 273**, confirming §9.10 |

C9 also gives a byte witness for `TLeaf.md` §7's boxed claim, currently
source-cited only: all six truncated leaves carry the bare version-1 title
(`f[0,0,16]`, no name, no dimensions) **including on `[10]` static arrays and
`[N]` slices** — the counter information really is lost.

## 5. Corpus additions, cheapest first

### C12. roottest as a third corpus — costs a README and a list

roottest was merged into `root-project/root` in April 2025 (commit `9133116945c`),
so the pinned submodule ships it at `root/roottest/`: **274 `.root` files, 138 MB,
80 distinct header versions from ROOT 2.23/12 to 6.41/01** — both ends outside the
existing corpora's 2.24/00 – 6.36/02.

The framing matters. These are neither fixtures nor a fetched corpus: they are
reproducible from `check_pin.py`'s pin alone, with **no `tools/fetch_*.py` and no
bandwidth**. That is a stronger guarantee than `gen/cern/`'s manifest, and it is
`gen/cern/`-grade evidence — ROOT's own files, published by the ROOT team.

Three files are byte-identical to `gen/cern/` entries and are therefore already on
disk twice; zero overlap with `gen/foreign/`.

**Exclude `root/roottest/root/tree/basket/corrupted.root`** — deliberately damaged
for ROOT's error-handling tests, and it produced 4 210 748 of a 4 213 134-failure
run on its own. Excluding it needs a reason recorded, not a silent skip.

**Open question, and it is the reason this is not already done:** a `gen/roottest/`
would be a third corpus with a third set of conventions. Decide whether it is that,
or a tier of `gen/cern/`, or simply a list in `gen/cern/README.md` pointing into the
submodule. The last is cheapest and probably right.

### C13. The RNTuple tier `gen/foreign/` never picked up

`grep -i rntuple gen/foreign/MANIFEST.sha256` returns nothing, yet
scikit-hep-testdata now carries **25 RNTuple files, 2.2 MB**, and
`tools/fetch_foreign.py` pulls by path from that repo's `main` — so adding them is
**manifest lines only**. They bring three anchor versions (1.0.0.0, 1.0.0.1,
**1.0.1.0**), ROOT **6.37/01 and 6.38/00** — past the 6.36/02 ceiling — and four
features with no fixture: deferred/schema-extension columns, multiple column
representations, multiple cluster groups, and `Real32Trunc`/`Real32Quant` at seven
bit widths.

One is a 2 382-byte witness for `§9.2`'s *wide key at a small offset*, which today
rests solely on a 5 GB range read of `volume.root`:
`rntviewer-testfile-multiple-rntuples-v1-0-0-0.root` has `fVersion` 1004 keys at
offsets 224–2119.

Also confirms `rntviewer-testfile-uncomp-single-rntuple-v1-0-0-0.root` is
byte-identical to `gen/cern/RNTuple.root`.

### C14. Three rows for `LARGE.toml`

Range requests work against `opendata.cern.ch`, verified with this project's own
`fetch_range` unmodified. The URL form is the catch: take the
`root://eospublic.cern.ch//eos/opendata/...` URI from record metadata, strip the
`root://` prefix, prepend `https://opendata.cern.ch`. No redirect. The
`/record/<id>/files/<name>` form 404s.

| File | Size | ROOT | Why |
|---|---|---|---|
| `Run2012C_TauPlusX.root` | **15.9 GB** | 6.16/00 | triples the size ceiling from 5.3 GB; a key at offset 15 885 617 883 |
| CMS Run2024F RAW `071ab81e…` | 3.27 GB | **6.30/03** | `LARGE.toml`'s newest large-format entry is 6.23/01; **and** the only `TStorageFactoryFile` free record *above* the boundary, completing a pair whose small-format half is 5.22/00 |
| LHCb `00041836_00008626_1.ew.dst` | 5.79 GB | **5.34/21** | the most widely deployed ROOT 5 release; nothing exercises it above 2 GB. **Licence caveat:** LHCb records carry no per-record `license` field; CC0 comes from the portal Terms of Use only |

`LARGE.toml`'s `path` is currently relative to `https://root.cern/files/`. These
need an absolute-URL or `base` field — a schema decision to take before adding any
of them.

`Run2012BC_DoubleMuParked_Muons.root` is **already listed** via `rootbench/`, and
Open Data is its origin: every recorded field matches at both URLs. Worth a line in
the README, not a row.

### C15. 17 KB that closes the newest-version blind spot

Both corpora stop at 6.36/02. go-hep has `issue-1063.root` (**6.40/02**, 4 608 B),
`embedded-tbox.root` (**6.40/00**, 4 334 B) and `tefficiency.root` (6.38/04, 8 375 B).
All three probe 0 partial / 0 blocked — so the generic streamer-driven read already
handles `TEfficiency`, `TScatter`, `TGraphMultiErrors` and `TF1Convolution`, none of
which appear in `spec/`. A clean positive for the 6.40 era, and cheap.

## 6. C16. Extend the range technique — no new file needed

`gen/cern/LARGE.toml` reads two ranges per file: the header and the free-segment
record. The top directory record (at `fBEGIN`, sized by `fNbytesName`) and its key
list (at `fSeekKeys`, sized by `fNbytesKeys`) cost **one more request each, ~700
bytes**, and yield the wide `fSeekKeys`, per-key `fSeekKey` above 4 GB, and every
key's `fPidOffset` and `fSeekPdir`.

`spec/01-container/LargeFiles.md` §8.6 currently asserts the wide-`fSeekPdir`/
`fPidOffset` masking on the **free record alone**. This would witness it on
ordinary object keys too, **on all eight files already listed**, for about 1 KB
more traffic. Self-contained, and independent of every other item here.

## 7. C17. One retraction to check before it goes upstream

`PLAN.md` §7.1 item 10 holds that `std::map` cannot be written from the
interpreter in 6.40.04. rntuple-validation writes `std::map<std::string, std::int32_t>`
from a plain interpreted macro with no dictionary; the released file exists,
decodes here, and their weekly CI has been green including 2026-09-21. Their
formulation differs in three ways from our failing snippet:
`std::make_unique<ROOT::RField<Map>>(name)` + `model.AddField(...)` rather than
`model->MakeField<>`, a `std::string` key rather than `int`, and whole-map
assignment before `Fill()`.

**To do:** retry with their formulation against the pinned 6.40.04. If it works,
item 10 is not a ROOT bug and must not be reported as one.

## 8. Confirmed negatives — do not re-investigate

Each was measured across a named population, not assumed. Recording them is the
point: the next person to go looking should not repeat these trips.

| Question | Answer | Where measured |
|---|---|---|
| A file with more free segments than `volume.root`'s 1539 | **No, and there will not be one.** Production writers open, fill and close once; `nfree` is 1, 2, 9–19 or 74 across six writers | Open Data, six file families |
| A non-zero `pidf` / `fPidOffset` / a surviving `fUniqueID` top byte | **None anywhere** — 0 of 273 in roottest, 0 in km3net, 0 in go-hep, 0 in every Open Data key list decoded. §9.4 stays open | all six |
| A branch with a non-empty `fFileName` | zero across 5425 km3net branches and every go-hep tree; **unchecked in roottest** (the agent's proxy scan was unsound) | km3net, go-hep |
| `TClonesArray` class version 3 | only version 4 occurs | roottest, go-hep, km3net |
| `ROOT::v5::TFormula` 1–3 / `TF1Data` 1–4 | nowhere, roottest included. v4/v5/v7 **do** occur in roottest and would advance the row without closing it | all |
| Two streamer infos for one class at the **same** version, different checksums | none | roottest, km3net, go-hep |
| A `type=readraw` rule | none; the only `ReadRaw` hit in 5602 tracked files is an unrelated ALICE method | roottest |
| A new compression codec | none — zlib, LZMA, LZ4, ZSTD and the legacy codec are all that occur | all six |
| `TRef` in a production experiment corpus | **no.** aanet uses index members, not references — the hypothesis that drove part of the km3net brief was wrong | km3net |

Two near-misses worth naming so they are not re-chased: go-hep's `pid.root` looks
like the `fPidOffset` witness and is **groot-written** (its `TProcessID` key is
named `type-TProcessID` with `fName` `my-pid`, where ROOT writes `ProcessID<n>` for
both — `root/io/io/src/TFile.cxx:2017`); and roottest's `foreignVec.root` carries
the large-file flag on a 7 KB file with `fUnits` 4, which is exactly the shape
`FileHeader.md` §10.9 predicted and said nothing witnessed — **but the write path
is not identified**, and `TFile::WriteHeader` sets `fUnits = 8` whenever it adds
the flag. It is a lead until that is traced, and it is the only candidate for the
large layout at committable size that the survey found.

## 9. External verification banked, no action needed

Worth citing, not acting on. Three independent reimplementations agreeing with
this specification on points it derived from ROOT's source alone:

- **groot's `rvers/versions_gen.go`**, an independently generated table of 119
  class versions pinned to ROOT 6.40/00, cross-checked mechanically against every
  `ClassDef*` in the pinned headers: **118/118 agree, 0 disagreements.**
- **UnROOT's `test/issues.jl:92`** comment describes `TBranch` v8's layout member
  for member as `TBranch.md` §13.1 does — `fEntryNumber` as Int32, `fBasketEntry`
  as Int32, `fEntries`/`fTotBytes`/`fZipBytes` as Float64 — arrived at
  independently, from bytes.
- **groot walks into `Collections.md` §12's trap**: it defines
  `BypassStreamer = 1<<12` with no class-version branch, and then cannot read the
  bypass file at all (its test is commented out, *"FIXME: needs member-wise
  streaming"*). §12 says a reader MUST branch on the class version before testing
  the bit; here is a working implementation that did not.
- **ERRATA 6** (`0x17 SplitReal16` does not exist) gains the ROOT team's own
  words: `types/fundamental/real/write.C` carries `// NB there is no kSplitReal16`,
  and a suite whose stated goal is covering every part of the format produces every
  column code **except** `0x17`.
- **ERRATA 8** (Type Version is a signed version in an unsigned field) is
  strengthened: rntuple-validation stamps `0xFFFFFFFF` for classes with a compiled
  `rootcling` dictionary, where this project's witness was interpreted classes only.
  That rules out an interpreter artifact.

Upstream issues open at rntuple-validation that this project is **ahead** on:
#21 (streamed types), #22 (anchor tests), #23 (checksum tests) — the last two are
exactly what ERRATA 1/2/3/5 and `gen/cases/rntuple/anchor` cover.

## 10. What is not decided

1. **Whether to adopt roottest as a corpus at all**, and if so in what form — a
   third corpus, a `gen/cern/` tier, or a list in a README. C12.
2. **The licence question.** roottest and rntuple-validation are both LGPL-2.1.
   `LICENSES/` holds only BSD-3-Clause and CC-BY-4.0. Nothing needs committing —
   roottest is in the submodule and rntuple-validation can be fetched — but if any
   file is ever committed as a fixture, this has to be answered first.
3. **`LARGE.toml`'s `path` schema**, which assumes one base URL. C14.
4. **Whether to cut `2026.09.22`** before or after this work. Cutting first gives
   the corrections a clean "since" boundary in `CHANGELOG.md`; cutting after means
   the first CalVer release contains them. No strong argument either way.

## 11. Order

~~C1–C4 first, and C1 and C2 before C3 and C4~~ — **C1 and C2 are done**. C3 and
C4 are next, and each begins by reproducing what one survey reported. C5–C7 fall
out of C1 and are **not** closed by it: the checker now handles the shapes, but
`rootfile.read_rntuple_anchor()` still cannot read a compressed anchor and
`payload_range()` still overruns. `gen/cases/rntuple/compressed` is a witness for
both — its anchor at 727 is compressed, and the file reports
`NOT CHECKED ROOT::RNTuple ...` for exactly that reason. C16 is independent
of everything and cheap enough to do at any point. C8–C11 need no new
infrastructure once C12's question is answered, because three of the four files
are already on disk. C13 is manifest lines. C17 should happen before anything is
reported upstream.
