# PLAN-corpus — six external resources, surveyed 2026-09-22

**Status: discharged 2026-09-23 — every item is worked. C1–C4 discharged 2026-09-22** — the four defects in published
prose, so `PLAN.md` §8.1 criterion 1 is met again. Every one has a source
citation; the bytes are a new fixture for C1 and C3, 12 385 basket keys in
`root/roottest/` for C2, and for C4 the only witness there is, now a
`gen/foreign/` file. **C5–C7 discharged the same day**: two real bugs and one
that was not, whose audit found a vacuous invariant instead. **C8–C11 discharged
the same day**, and C12 with them in its cheapest form: every witness was
re-measured here, two of the four reported claims turned out narrower than
reported, and checking them found **three more wrong release boundaries** in
published prose and one reader gap, which is the new C18. **C13 and C14
discharged the same day**, and C13 was not only manifest lines: its largest file
contradicted two more published claims and hit three reader gaps. The new C19 is
what is left of it. **C15–C19 discharged 2026-09-23**: one more wrong published
claim (`Buffer.md` §2.3's ROOT 4 framing is g4tools'), C18 and C19 closed with
spec text and no weakened invariant, C19's premise refuted, and C15's three
files measured and not taken. The survey is done; this plan orders what to do
about it.

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
| C3 | `Buffer.md` §2.3's unframed-class list omits `TDatime` | reproduced (`Buffer 9.2`, exit 1), then a census of every persisted hand-written `Streamer` | **✅ discharged** — and the census found two more classes and a reader bug |
| C4 | `Record.md` §8.6 is false for ROOT 6.34/6.35 RNTuple blob keys | reproduced (4 × `Record 8.6`), and the fix found by `git log -S`: `5fe8a99942`, first in 6.36.00 | **✅ discharged** — scoped to one writer, not to all RNTuple files |
| C5 | `check_invariants.py` resolves a base class by name, not `fBaseVersion` | reproduced (34 × `StreamerInfo 13.7`), then split: 15 matched another info of the class, 19 matched none | **✅ discharged** — the right key is the checksum, not `fBaseVersion` |
| C8 | `skim.root` is the only file anywhere with version-3 `TStreamerElement` | census over 273 files: v4 28 844, v2 7 377, **v3 426, all in one file** | **✅ discharged** — one file, but **223** elements, not 426; counted here over roottest and both corpora by the `TStreamerElement` **base** version |
| C9 | `leaves.root` carries a leaf class at a legacy version | frame bytes of six truncated leaves | **✅ discharged** — true, and the witness to the §9.1 row it named is a different file: `TLeaf` v1 in roottest's `MC_uds_reco-1.root` |
| C10 | `MC_uds_reco-1.root` witnesses a buffer written with no byte counts | "one outer byte count, then `TNamed` and `TObject` with none" | **✅ discharged, narrower** — bare version words in bases, which `pippa.root` already showed; every class tag has a byte count, so `Buffer.md` §6.4 is still unwitnessed |
| C11 | Two roottest files are the cheapest directory-version witnesses | header and directory versions | **✅ discharged** — versions 3 and 4, not 1; version 1's cheapest is `Event.3.2.0.root`, which refuted `Directory.md` §7 |
| C12 | roottest is inside the pinned submodule | `ls root/roottest/` | **Confirmed here**; adopted as a list in `gen/cern/README.md` that `check_citations.py` reads |
| C13 | 25 RNTuple files in scikit-hep-testdata, "manifest lines only" | fetched, `check_invariants.py`, `coverage_probe.py`, `read_rntuple` on each | **✅ discharged**, 23 added — and not manifest lines only: `check_invariants.py` crashed on one, which contradicted two published claims |
| C14 | Three Open Data files serve range requests | `fetch_range` and `large_file_problems` unmodified, then `fetch_cern.py --headers` | **✅ discharged** — every survey figure reproduced; 11 rows, 0 failures |
| C18 | `skim.root`'s `HoldMuo` has no byte count and no version word | `check_invariants.py` → 2 × `ReadingEntries 8.5`; ROOT 6.40.04 reads the same entries correctly | **✅ discharged 2026-09-23** — ROOT's no-dictionary rule, and `uproot-issue475.root` turned out undecodable, not contrary |
| C15 | go-hep's three newest files close a version blind spot | fetched at the pinned commit, generators read, probed and checked | **✅ discharged, not adopted** — ROOT-written and clean, but every class, version and checksum is already in a listed file |
| C16 | Two more ranges per large file witness `fPidOffset` on ordinary keys | `fetch_cern.py --headers` extended; 11 files | **✅ discharged** — and `LargeFiles.md` invariant 7, checked on all 820 local directory records |
| C17 | rntuple-validation writes `std::map` where we could not | eleven instantiations, two APIs, ACLiC | **✅ discharged** — the dictionary decides, not the API |
| C19 | A `This` element names its value class only by checksum | `TStreamerInfo::Build`, ROOT without ATLAS's libraries | **✅ discharged, premise refuted** — the title names it |
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

### C3. `Buffer.md` §2.3 omits `TDatime` — ✅ discharged 2026-09-22

**Done**: `Buffer.md` §2.3 is now a **complete** list for 6.40.04, organised by
what each class writes first; `check_invariants.py`'s `UNFRAMED` agrees with it;
`rootfile.py` reads a `TObject` record correctly; `serialization/unframed-records`
writes five of the classes as records, 14 assertions, portable (the arm64
libstdc++ container reproduces the digest).

**Reproduced first**, as §1 required: `Buffer 9.2: payload of 4 bytes at 244`,
exit 1, on go-hep's `tdatime.root`. Then the question was asked once rather than
answered one name at a time: every hand-written `Streamer` of the 55 persisted
classes in `streamers.toml`, read with `inventory.py`'s own scanner for what its
write branch emits first. The heuristic flagged `TRef` and `TVirtualStreamerInfo`
falsely — both delegate to a streamer that frames — so every unframed row was
then read by hand. What that found:

- **The actual bug was an inconsistency, not a missing name.** The checker
  declared `TDatime` *described by hand* — so the framing check ran on it — and
  did not exempt it from needing a byte count. `TStringLong` and `TQObject` were
  in exactly the same position and would have failed the first time either
  appeared as a record.
- **`rootfile.py` misread a `TObject` record** — found by the fixture, not the
  survey. It took the generic path, reading a version word for the class and then
  a `TObject` base after it, and consumed 12 bytes of a 10-byte payload. It
  changes nothing over either corpus (checked by re-running the probe with the
  previous reader), so no `TObject` record had occurred in one.
- **Three `gap` classes were never gaps.** `TGraphEdge`, `TGraphNode` and
  `TGraphStruct` have `Streamer`s with empty bodies, so their specification is
  "nothing", which §2.3 now states. `streamers.toml` 15 gaps → 12, and "ten
  narrow classes" → seven wherever the front pages and `PLAN.md` said it.
- **`TQObject` as a record is a key with `fObjlen` 0** — an edge case worth
  having in a fixture: §1's compression test calls it raw, correctly, and a
  reader that sniffs one byte for a magic does not survive it.
- **Two C2 leftovers were still in the text**: `Buffer.md` §6.1 called
  small-form basket keys something "ROOT never writes", and `Pitfalls.md` said
  "a basket key always uses the large-file layout". Both are scoped now. C2's
  sweep had looked for the claim in `TBasket.md` and missed the restatements.

Each exempted class is still **checked**: `StreamerDriven 10.1` requires the
hand-written shape to consume the payload exactly, and corrupting the fixture's
`TString` length, `TStringLong` length or `TObject` `fBits` (setting
`kIsReferenced`) each fails. `TDatime` (always 4 bytes) and `TQObject` (always 0)
have no internal length to corrupt; only their key can be wrong, and the
container invariants own that.

---


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

### C4. `Record.md` §8.6 needs a ROOT 6.34/6.35 exception — ✅ discharged 2026-09-22

**Done**: `Record.md` §3.6 states the exception with its history and invariant 6
is scoped to it; `check_invariants.py` accepts exactly that shape; the witness is
in `gen/foreign/`.

**The scope is one writer, not RNTuple.** `git log -S` on the submodule finds the
fix, `5fe8a99942` (2024-11-29, *"fSeekKey and fSeekPdir were set to the same
offset"*), first released in **6.36.00** and never backported. Its title names
`RFileProper` — the writer that appends into a `TFile` the caller opened — and
6.34's source confirms the other writer, `RFileSimple`, always passed 100
(`v6-34-00` `RMiniFile.cxx` lines 1178 and 1254, against 1025). That is why
`RNTuple.root` in the CERN corpus, also 6.35/01, was never flagged. The checker's
exception is scoped to all three facts at once — class `RBlob`, `fSeekPdir` equal
to the key's own offset, writing release below 6.36 — and each was corrupted
separately: the witness claiming 6.36/00 fails all four keys, and an anchor made
to point at itself fails.

**The witness is outside, and there is no way round that.** The pinned ROOT can no
longer write the shape, and none of the 23 RNTuple files in `root/roottest/`
carries it — they come from the other writer or from after the fix. So
`Run2012BC_DoubleMuParked_Muons_1000evts_rntuple_v1-0-0-0.root`, 27 643 bytes from
scikit-hep-testdata (upstream bytes matched), joins `gen/foreign/MANIFEST.sha256`
with its reason in the header, as `uproot-issue283.root` did. It fails nothing
else, so the corpus stays at 0 failures over **156** files — and it is the first
RNTuple file there, so C13 has begun.

**Adding it exposed two stale things, both now fixed.** `coverage_probe.py` wrote
the whole file off as not walkable because one multi-page `RBlob` could not be
decompressed; a record that cannot be decompressed is now one blocked record.
And `PLAN.md` §9.8's probe figures were stale since this morning's RooFit commit
`5d6a95b`, which decoded two records on the foreign side too — re-running the
probe with the tools as they were before that commit reproduces the old figures
exactly, which is how the two moves were told apart rather than lumped together.

---


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

## 3. Three reader and checker bugs — ✅ discharged 2026-09-22

**C6 was real, C5 was real but latent, and C7 was not a bug** — but auditing it
found one that was.

- **C6 ✅.** Reproduced on this project's own `rntuple/compressed`: the anchor at
  727 is compressed and `read_rntuple_anchor` read the first four bytes of a zlib
  stream as a byte count. It now reads through `object_data`. After the fix **27
  anchors** within reach read through to their header schema, **19 of them
  compressed** — every roottest 6.37/01 file included. *Why it survived*: only
  the unit tests call `read_rntuple`, on three named fixtures, all uncompressed.
  `test_rntuple.EveryAnchorReads` now reads every anchor in `data/` and requires at
  least one to be compressed, and it fails against the previous reader.
- **C7 — not a bug.** All 20 `payload_range` call sites were traced: every one
  indexes the buffer `object_data` returns, where the payload is decompressed in
  place and `start + obj_len` is exact, or a record already known to be raw. A
  multi-page `RBlob` never reaches it; `object_data` raises first, which C1
  already handles. The survey read the function without its callers. The
  docstring now states the contract the audit relied on.
- **…but the audit found `Compression` 9.7 checking the wrong bytes.**
  `check_raw_is_not_a_block` added the record's offset to a `start` that already
  included it, so it read nine bytes at twice the record's offset — another
  record, or past the end of the file, where it returned early. **A published,
  "checked" invariant that had never checked anything**: rewriting a raw payload
  to open with a valid `ZL` header did not trip it. Fixed, it catches that
  corruption and is clean over every fixture, written file and all 228 corpus
  files, so 9.7's claim is now measured for the first time. `check_coverage.py`
  could not see this — it matches labels, and the label was emitted by live code.
  It is the §8.13 lesson again from the other side: an invariant wired to a check
  is still only as good as the check.
- **C5 ✅, latent.** Reproduced: 34 × `StreamerInfo 13.7` on UnROOT's
  `TLeafC_pr342.root`. The question that decided it was whether *another* info for
  the base class in the file carried the recorded checksum: **15 did** — our
  lookup kept the last info of each name — and **19 matched no info at all**, the
  g4tools writer's canned list, and a lead. The survey's proposed fix was wrong:
  the key is not `fBaseVersion`, which §9.2 already shows may name a version the
  file lacks, but the checksum, which identifies a layout. 13.7 now accepts a
  checksum matching **any** info of the class, the published wording says so, and
  the lead file goes from 34 failures to exactly the 19. A search of every file in
  reach — fixtures, both corpora, all of `root/roottest/` — found **no** base
  element naming a class its file describes twice, so no ROOT-written file had
  ever hit it. The witness is therefore built: `test_write` writes a file whose
  base class has two infos with the derived class pointing at the one a name
  lookup does not keep, and checks both that it passes and that an unmatched
  checksum still fails. It failed before the fix.

---

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

## 4. Four §9 rows with a witness for the first time — ✅ discharged 2026-09-22

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

**Done.** The rule was the one C1–C4 used: re-measure every claim with this
project's tools before writing any of it down. That paid for itself. Two of the
four reported claims were narrower than reported, and in checking them three
published boundaries turned out wrong, each settled by reading a class version at
a release tag in the submodule (`git show v3-03-07:base/inc/TDirectory.h`), which
reaches back to ROOT 1.

- **C12 first, as a README list.** `gen/cern/README.md` gains a
  `root/roottest/` table of the five files the specification now cites, with each
  one's `check_invariants.py` result, and the two exclusions (`corrupted.root`,
  and the three byte-identical duplicates of `gen/cern/` files).
  `check_citations.py` reads that table: a cited roottest file must be a row, and
  a row must exist in the submodule. Both corrupted and tested
  (`tools/test_coverage.py`). No third corpus, no fetch step, no manifest.
- **C8.** 223 version-3 elements in `skim.root`, not 426, each carrying exactly
  24 bytes after `fTypeName` — the three doubles, all zero. The survey's 426 did
  not reproduce; this count is by the `TStreamerElement` **base** version, over
  roottest and both corpora, and the file's 29 `TStreamerBase` elements at
  *subclass* version 3 are a different number and not in it. Nothing was wrong in
  `StreamerInfo.md`; what it gained is the history. Version 3 **never shipped**:
  `ccca6c91c4a` introduced it on 2005-04-18 and `81aa9214fd3` replaced it on
  2005-04-21, both stamped 4.03/05, and no release tag contains it. §7.1 now says
  so, with the witness, and §15 no longer says a version below 4 needs ROOT 3.
- **C9.** `leaves.root`'s claims hold exactly: six `TLeafF16`/`TLeafD32` at
  version 1, bare titles on the scalar, the `[10]` and the `[N]`. It joins
  `gen/foreign/` as the first file from outside scikit-hep-testdata:
  `fetch_foreign.py` gained `SOURCES`, go-hep pinned to commit `8d0fccd8a3b5`, and
  a `go-hep/` prefix in the manifest. Two things the survey did not report:
  - **`TLeaf.md` dated version 2 to 6.40, and it is 6.38.** `da232dd758f` is first
    tagged `v6-38-00`, and `v6-36-14` still has `ClassDefOverride(TLeafF16, 1)`.
    Corrected in §7, §12 and in `ttree/leaf-truncated`'s descriptions.
  - **The §9.1 row was about layouts, and a version-1 `TLeafF16` is not one**:
    its layout is version 2's and only the title differs. The row's real witness
    is `TLeaf` **version 1** in roottest's `MC_uds_reco-1.root`, whose leaves read
    in version 2's field order end exactly on their byte counts. And
    `uproot-double32-float16.root` had twelve version-1 truncated leaves in
    `gen/foreign/` all along; §9.10's census had looked at `TLeaf` and
    `TLeafObject` only. `TLeafObject` 1–3 occur nowhere.
- **C10, narrower than reported.** `MC_uds_reco-1.root` does write bases as
  bare version words inside a byte-counted `TTree` — but so does `pippa.root`,
  already in `gen/cern/`, inside a byte-counted `TH1F`. What the §9.1 row needs is
  `Buffer.md` §6.4's sequential object map, and that needs a class tag with no
  byte count in front of it: the 2.23/12 file has 11 class tags and a byte count
  before every one, and `pippa.root` has none. No older ROOT-written file exists
  in reach, so §6.4 stays source-only and now says why. Both files also carry
  `fBits` `0x03000000` unmasked, a byte witness for `Buffer.md` erratum 9.
- **C11, and the find of the batch.** The two files are versions 3 and 4, as
  reported; version 1's cheapest witness in roottest is `Event.3.2.0.root`, and
  that file is **ROOT 3.03/02 with a version-1 directory and no header UUID** —
  where `Directory.md` §7 said version 2 began at 3.03/01 and `FileHeader.md` §8
  said the UUID arrived with 3.03. The tags say: `v3-03-06` has
  `ClassDef(TDirectory,1)` and no `fUUID` in `TFile.cxx`, `v3-03-07` has 2 and the
  UUID, `v3-03-08` has 3. Version 2 was released exactly once, in 3.03/07.
  Corrected in both documents, with the witness, including `Directory.md` §7's
  "latent inconsistency" note, which named the same wrong range.
- **Counts.** `gen/foreign/` is 157 files and the corpora 229; both still
  0 failures, and every count moved by exactly `leaves.root`'s share.

### C18. An object with no byte count and no version word — ✅ discharged 2026-09-23

**Done.** The two files did not need opposite readings. `nEXO::SmartRef` has
a hand-written `Streamer` its info does not describe: 20 bytes where the info says 18.
ROOT 6.40.04 without nEXO's library reads it by the same rewind rule that is
right for `HoldMuo`, and says `read too few bytes: 37 instead of 39` on every
object. The version-first reading had landed on 20 by coincidence, reading the
`TObject` base's version word as 0. So one rule serves both, with two checks
that reject a wrong reading:

- a `TObject` base's version word is always 1. That was measured over 525 files,
  and every other value any reading met was one of these misreadings; it is now
  `Buffer.md` invariant 10;
- the enclosing extent.

`StreamerDriven.md` §7.1 has the whole of it, including why the rule is ROOT's
only for classes it has no dictionary for. `skim.root` passes, and
`SmartRef`'s two baskets are a named skip. Checking the rule against
`uproot-from-geant4.root` found that `Buffer.md` §2.3's "ROOT 4 records open
with bare version words" rested on g4tools files. A census of 2 025 records in
ROOT-written files, from ROOT 2 on, found none, and the paragraph is corrected.

What follows is the item as it was written on 2026-09-22.


Found doing C8: `check_invariants.py` over `skim.root` gives two
`ReadingEntries 8.5` failures, `Jpsi.jmu1` and `Jpsi.jmu2` entry 0, **122 bytes
in the basket and 120 decoded**. The entry is one `HoldMuo`, a `kObject` (61)
member of a split `TClonesArray` column, and its bytes are
`00 01 | 00 00 00 00 | 03 00 00 00 | 52 bytes of members | 40 00 00 38 00 01 …` —
a bare `TObject`, then `HoldMuo`'s own members, then a byte-counted `HoldPtl`. So
**`HoldMuo` itself has neither a byte count nor a version word**; the reader takes
`00 01` as its version and then reads a `TObject` two bytes late. `Jpsi.pvx` and
`Jpsi.ptl`, the same shape of member on other classes, are framed normally.

**ROOT reads it correctly**, which makes it a reader gap and not a file at fault:
`TTree::Scan` in 6.40.04 gives `Jpsi.jmu1.ptl.pt` 3.425, equal to the same muon's
`Muo.ptl.pt`. The mechanism is `TBufferFile::ReadClassEmulated`, which ROOT takes
for a class it has no dictionary for: *"We attempt to recover if a version count
was not written"* — with no byte count it rewinds to the object's start and reads
the members with no version word at all
(`root/io/io/src/TBufferFile.cxx:3428-3435`, since `ec691d21d29`, 2001, written
for `TVector3`, whose streamer wrote no version). The compiled path,
`ReadClassBuffer`, has no such rewind.

**Why it is not fixed yet: the file alone does not say which reading applies.**
Every generic-path object without a byte count was counted over every fixture,
both corpora and the two roottest files. `HoldMuo` is the only unframed one; the
others with no byte count all have a version word, and some are read correctly
**only** that way. `nEXO::SmartRef` in `uproot-issue475.root` opens with the same
`00 01 00 00 00 …` bytes, but the objects sit 20 bytes apart: the version-first
reading consumes 2 + 10 + 8 and lands on the next one, giving `m_entry` 0, 1, 2 in
order, while the no-version reading consumes 18. So ROOT without the nEXO library
would, by arithmetic, fall two bytes short per object, and applying ROOT's rule
everywhere would move this failure from one file to another. (That file is in
`gen/foreign/`, so it is a lead; its writer has not been traced.) What is needed:

1. a statement in `StreamerDriven.md` or `Buffer.md`: an object with no byte count
   was written by a hand-written `Streamer`, which no streamer info describes;
   ROOT without the class's library assumes there is no version word, and with
   it, whatever that `Streamer` does;
2. a reader policy that is exact where the extent is known — a basket entry, or
   an enclosing byte count — which is where both readings can be tested, as
   ROOT's two paths in effect do;
3. `skim.root` then passes, `uproot-issue475.root` still does, and the census
   above is the regression test.


### C12. roottest as a third corpus — costs a README and a list — ✅ adopted as the list, 2026-09-22

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

### C13. The RNTuple tier `gen/foreign/` never picked up — ✅ discharged 2026-09-22

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

**Done, and it was not manifest lines only.** All 25 files were fetched and put
through `check_invariants.py`, `coverage_probe.py` and `read_rntuple` before any
went in. The survey's figures hold: anchors 1.0.0.0, 1.0.0.1 and 1.0.1.0, writers
6.34/04 to 6.38/00, and every anchor reads through to its header schema, the
CMS one's 1679 fields and 710 alias columns included. The duplicate of
`RNTuple.root` stays out, and the other 23 are in `gen/foreign/MANIFEST.sha256`.
Twenty-two passed as they were. The 23rd, `uproot-physlite-rntuple_v1-0-0-0.root`
(2 MB, ATLAS, ROOT 6.34/04), crashed the checker with a `StopIteration`. Behind
that were two published claims a ROOT-written file contradicts, and three reader
gaps:

- **`FreeSegments.md` §4.2 said a gap's marker is never missing in practice.**
  The record chain lost sync at 200897 because the four bytes there are stale,
  `03 10 dc 00`. The free list has `(200897, 200923)` all the same, directly after
  a 126-byte `RBlob` at 200771: a 153-byte free slot, a blob, and a 27-byte
  remainder with no marker. `TKey::Create` puts that marker four bytes past the
  key in its own buffer, and only `TKey::WriteFile` writes it
  (`root/io/io/src/TKey.cxx:1501`). RNTuple bypasses `WriteFile`, and ROOT fixed
  the omission in `d328b598b32` (2025-01-29), first released in 6.36.00. It is the
  same writer, and the same file, as C4's self-parented keys. §4.2 now says so,
  invariant 6 exempts exactly that case (an `RBlob`'s end, before 6.36), and §7
  and `Record.md` §6 say to read the free list first and trust it. **Reader:**
  `read_records` does that, and `read_free_segments` reads the key at `fSeekFree`
  instead of finding it through the chain it exists to repair, which is what
  crashed. Corrupted three ways: an unmarked gap in `container/gap`, the ATLAS file
  relabelled 6.36, and a marked gap of it broken. All three fail 8.6.
- **`Collections.md` §4.1 said a member-wise base is read once per element.**
  1005 branch-baskets of `vector<ElementLink<…>>` failed with "version word 0 …
  checksum 0x0". The bytes are four `m_persKey`s then four `m_persIndex`s:
  ROOT reads the base's own info over the whole array
  (`root/io/io/src/TStreamerInfoReadBuffer.cxx:1409-1410`), so a base is one
  column per member. **Reader:** `read_column` does that, choosing the base's info
  the way `TStreamerBase` does, by checksum when `fBaseVersion` is −1
  (`root/core/meta/src/TStreamerElement.cxx:762-765`). All 1005 now decode.
- **A container named without template arguments crashed `value_type_name`**
  (975 × `substring not found`) where `stl_kind` already declined it. It now
  declines too, which is C19.

Nothing that was already in either corpus moved: 26410 of 26477 and 1696 of 1696
branch-baskets, 0 failures, before and after the three reader changes. The one
wrong row found on the way is `PLAN.md` §9.2's "wide key at a small offset rests on
`volume.root`". Every key in a 6.40 fixture is `fVersion` 1004, and
`rntuple/compressed` asserts one at 385.

### C14. Three rows for `LARGE.toml` — ✅ discharged 2026-09-22

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

**Done.** The schema decision was the smallest one: a row has `path`, relative to
root.cern as before, or `url`, absolute, and never both (`fetch_cern.large_url`,
unit-tested). The two paths the survey did not record came from its own report,
since Open Data's search does not index files inside a dataset. Each file was
measured with `fetch_range` and `large_file_problems` unmodified, then written
down and checked by `fetch_cern.py --headers`: **11 files, 0 failures**. Every
survey figure reproduced — 15 886 107 547 bytes at 6.16/00, 3 274 820 145 at
6.30/03 with a `TStorageFactoryFile` free record and one interior entry, and
5 786 425 072 at 5.34/21 — with no redirect and `Accept-Ranges: bytes` on all
three. The LHCb record (24506) has no licence field, confirmed; the CMS ones are
CC0. Nothing is kept of any of them but the numbers. The `rootbench/` Muons file is
Open Data record 12341, whose header, UUID and free-record bytes are identical
at both URLs; `gen/cern/README.md` says so in a line.

### C19. A class that is a collection, named only by checksum — ✅ discharged 2026-09-23, premise refuted

**Done, and the premise was wrong.** `TStreamerInfo::Build` writes the value
class into the `This` element's **title**, as `<xAOD::CutBookkeeper_v1> Used to
call the proper TStreamerInfo case`
(`root/io/io/src/TStreamerInfo.cxx:421-429`). This has been so since
`e69180ee910`, first released in 5.34/10 and 6.00. Without a dictionary ROOT
reads the type back from the title and emulates a `vector` of it (`:1000-1024`),
and it reads all 4 elements of the entry quoted below. No ROOT code path looks a
checksum up across classes.

`Collections.md` §11.2 has the rule, and all 975 branch-baskets decode. One
trap was found by the per-file comparison: an STL class's own info has a `This`
element too, and ROOT consults the title only when the name gave no proxy.
Taking the title for `uproot-issue243.root`'s `map<string,double>` branch read a
map as a `vector` of pairs, and silently dropped 113 branch-baskets from the
entry denominator. Invariant 10 is scoped to match, and invariant 11 is new.

What follows is the item as it was written on 2026-09-22.


Left by C13. ATLAS's `xAOD::CutBookkeeperContainer_v1` has a streamer info
of one element, a `TStreamerSTL` named **`This`** with `fSTLtype` 2, `fCtype` 61
and `fTypeName` the class's own name. That is how ROOT describes a class that has
a collection proxy of its own, a `DataVector` here. The type name carries no
`<…>`, so nothing in the element says what the collection holds, and
`rootfile.py` declines it: **975 branch-baskets**, all in
`uproot-physlite-rntuple_v1-0-0-0.root`, reported as `SKIPPED`.

The file does say it, one level down. Entry 0 of `CutBookkeepers` reads
`40 00 00 0c | 40 09 | 00 00 f1 3a 09 61 | 00 00 00 04`: member-wise, and
`0xf13a0961` is the checksum of the file's `xAOD::CutBookkeeper_v1` info. So a
reader could find the value class by checksum among the file's infos whenever the
collection is written member-wise, and never when it is written object-wise.
What is needed first is the spec text: where ROOT builds a `This` element
(`TStreamerInfo::Build`), what it reads it with when there is no dictionary, and
whether a checksum lookup across all infos is what ROOT itself would do, or only
what the bytes allow. Then the reader, then the 975.

### C15. 17 KB that closes the newest-version blind spot — ✅ discharged 2026-09-23, not adopted

**Measured, and not taken.** All three are ROOT-written: go-hep's
`gen-embedded-tbox.go`, `gen-teff.go` and `issue-1063.go` run ROOT macros. All
three decode completely with 0 failures, but none earns a place:

- their `TEfficiency` v2, `TH1D` v3 and `TH1` v8 infos are identical, checksums
  included, to `uproot-issue209.root`'s;
- `TBox` and `TAttBBox2D` are already in four listed files;
- the fixtures are written by 6.40.04, so a 6.40 release number adds no
  container-layer coverage either.

The survey's `TScatter`, `TGraphMultiErrors` and `TF1Convolution` come from
other go-hep generators (`gen-tscatter.go`, `gen-tgme.go`), not from these
files. Recorded in §8.


Both corpora stop at 6.36/02. go-hep has `issue-1063.root` (**6.40/02**, 4 608 B),
`embedded-tbox.root` (**6.40/00**, 4 334 B) and `tefficiency.root` (6.38/04, 8 375 B).
All three probe 0 partial / 0 blocked — so the generic streamer-driven read already
handles `TEfficiency`, `TScatter`, `TGraphMultiErrors` and `TF1Convolution`, none of
which appear in `spec/`. A clean positive for the 6.40 era, and cheap.

## 6. C16. Extend the range technique — no new file needed — ✅ discharged 2026-09-23

**Done.** `--headers` now reads the top directory record and its key list too,
and `LARGE.toml` records six more fields per file. It found more than the item
asked for:

- **8.6 on ordinary keys.** Every wide key has `fSeekPdir` equal to `fBEGIN`
  once masked, and `fPidOffset` 0: 20 key images and 18 record keys.
- **Offsets past 4 GB.** Seven keys hold an `fSeekKey` above 2³².
- **Mixed widths in one list.** `Event100000.root`'s key list holds both widths.
- **Narrow directory records in large files.** Three large files have one.

That last point became `LargeFiles.md` invariant 7, `FillBuffer`'s rule. It needs
no large file to fail, so `check_invariants.py` checks it on all 820 directory
records in reach. It holds on every one except g4tools' two version-1001
records, which are now in `IGNORE.toml` with the reason.


`gen/cern/LARGE.toml` reads two ranges per file: the header and the free-segment
record. The top directory record (at `fBEGIN`, sized by `fNbytesName`) and its key
list (at `fSeekKeys`, sized by `fNbytesKeys`) cost **one more request each, ~700
bytes**, and yield the wide `fSeekKeys`, per-key `fSeekKey` above 4 GB, and every
key's `fPidOffset` and `fSeekPdir`.

`spec/01-container/LargeFiles.md` §8.6 currently asserts the wide-`fSeekPdir`/
`fPidOffset` masking on the **free record alone**. This would witness it on
ordinary object keys too, **on all eight files already listed**, for about 1 KB
more traffic. Self-contained, and independent of every other item here.

## 7. C17. One retraction to check before it goes upstream — ✅ discharged 2026-09-23

**Done, and item 10 narrowed rather than retracted.** Neither the API nor the
key type decides it; the dictionary does. Over eleven instantiations, each tried
through `MakeField` and through `AddField`, empty and filled:

- exactly the four that ROOT ships compiled dictionaries for write
  (`libmapDict`, `libmap2Dict`);
- `map<int,float>` writes once ACLiC compiles one;
- `map<long,float>` has a dictionary and still aborts, because RNTuple
  normalises it to `std::int64_t`, which on macOS is `long long`.

rntuple-validation's `map<std::string,std::int32_t>` is one of the four.
`PLAN.md` §7.1 item 10 and `spec/05-rntuple/NOTES.md` §5 now say this. What is
reportable is that RNTuple accepts an emulated proxy and aborts in `Fill()`
instead of refusing the field.


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
| go-hep's `issue-1063.root`, `embedded-tbox.root`, `tefficiency.root` (C15) | **nothing new**: ROOT-written and clean, but every class, version and checksum is already in a listed file | `gen/foreign/`, `gen/cern/` |
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

1. ~~**Whether to adopt roottest as a corpus at all**, and if so in what form — a
   third corpus, a `gen/cern/` tier, or a list in a README. C12.~~ Decided
   2026-09-22: the list, in `gen/cern/README.md`, checked by `check_citations.py`.
   Revisit only if a use needs roottest run as a whole rather than file by file.
2. **The licence question.** roottest and rntuple-validation are both LGPL-2.1.
   `LICENSES/` holds only BSD-3-Clause and CC-BY-4.0. Nothing needs committing —
   roottest is in the submodule and rntuple-validation can be fetched — but if any
   file is ever committed as a fixture, this has to be answered first.
3. ~~**`LARGE.toml`'s `path` schema**, which assumes one base URL. C14.~~ Decided
   2026-09-22: `path` or `url`, exactly one.
4. **Whether to cut `2026.09.22`** before or after this work. Cutting first gives
   the corrections a clean "since" boundary in `CHANGELOG.md`; cutting after means
   the first CalVer release contains them. No strong argument either way.

## 11. Order

~~C1–C4 first, and C1 and C2 before C3 and C4~~ — **C1–C7 are done**. ~~C5–C7 fall
out of C1 and are **not** closed by it: the checker now handles the shapes, but
`rootfile.read_rntuple_anchor()` still cannot read a compressed anchor and
`payload_range()` still overruns. `gen/cases/rntuple/compressed` is a witness for
both — its anchor at 727 is compressed, and the file reports
`NOT CHECKED ROOT::RNTuple ...` for exactly that reason.~~ C16 is independent
of everything and cheap enough to do at any point. ~~C8–C11 need no new
infrastructure once C12's question is answered, because three of the four files
are already on disk.~~ **C8–C14 are done**, and left C18 and C19, each needing
spec text or a reader-policy decision before code. `fetch_foreign.py`'s `SOURCES`
makes C15 manifest lines, though C13 is the warning about that phrase: measure
first. C17 should happen before anything is reported upstream.
