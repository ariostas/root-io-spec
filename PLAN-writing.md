# PLAN-writing — the second half of the write side

**Status: ordered, not started.** Written 2026-09-21 against the pinned submodule
(`v6-40-04`) and measured over the 225 corpus files that `tools/rootfile.py`
loads, plus five byte-level experiments run with ROOT 6.40.04 — the release the
submodule pins — whose outputs are quoted throughout. Everything in §2 and §3 is a
measurement, not an estimate.

`PLAN.md` §8.4 ordered the first half of the write side and §8.5 closed it: a
third party following `spec/06-writing/` can create a file of histograms,
profiles, graphs and flat trees. This sub-plan orders four of the things that were
deliberately left out of that scope and are now being brought into it:

1. **free-space reuse** — placing a record in a gap rather than at the end;
2. **key ordering** — cycles, where a new key goes in a key list, deletion;
3. **updating an existing file** — the mode that needs both of the above;
4. **schema evolution on the write side** — what a writer must record so that a
   reader at a *different* class version can still read the file, without this
   project ever specifying how to *write* an earlier version.

The four are one feature seen from four angles: **a writer that can reopen its own
output.** The first two are machinery the third needs; the fourth is what the third
turns out to require as soon as the file it reopens was written by a different
ROOT.

A fifth was drafted and cut — **writing a split `TBranchElement`**. Reading one is
finished and stays finished; the write side gets a scope statement with its
reasoning instead of a procedure, and the subsection after W4 is that reasoning.

`PLAN.md` decision 3 and
[Writing §4](spec/06-writing/index.md#4-what-is-not-specified) name all of it as
out of scope. **The first three items of each have to change when this lands**, and
§9 says exactly how; the split-branch entry stays and gains its reasons.

## 1. Why this is the next thing

The first half answered "I have a histogram, which bytes do I emit". Every
project that writes ROOT files hits the second half within a week of shipping the
first, for a reason that is not symmetry: **a file is rarely written once.** The
three container items are one feature — a writer that can reopen its own output —
and a third party that cannot do it has to rewrite whole files to add one
histogram.

The other two are different in kind and are included for different reasons.
Splitting is the largest single thing on the read side that the write side cannot
produce, and it is what a tree of user objects looks like in every physics file.
Schema evolution is the one write-side subject where **getting it wrong is silent
for years**: a file whose streamer infos are subtly wrong reads back perfectly in
the session that wrote it, because that session has the classes compiled in, and
fails for everyone else.

### 1.1 The asymmetry that makes this worth writing down

Everything here is already specified **from the reading side**, and specified
well:

| Item | Reading side already has |
|---|---|
| Free-space reuse | [Free segments](spec/01-container/FreeSegments.md) — the record, the in-place marker, its two producers, coalescing, the trailing segment, shrinking |
| Cycles | [Records §4](spec/01-container/Record.md#4-cycles) — the numbering, both of ROOT's resolution rules, and `container/cycles` |
| Key lists | [Directories §6](spec/01-container/Directory.md#6-key-lists) — the images, and §6.5 on how to advance between them |
| Schema evolution | [Schema evolution](spec/02-serialization/SchemaEvolution.md) — choosing an info, checksums, `listOfRules`, emulated classes, and §8.1 on duplicates |
| Splitting | [Splitting](spec/04-ttree/Splitting.md) and [Split branches](spec/04-ttree/TBranchElement.md) — the branch tree, the names, `fSplitLevel`, and the nine-way read dispatch |

So this is **not** five new subjects. It is the same facts turned around, plus the
three things a reading document never states: **the order**, **the decision**, and
**which of the two sides is allowed to be liberal**. That is the same shape §2.8
of `PLAN.md` found for invariants against procedures, and it is why the work is
bounded.

### 1.2 What the research found about the *reading* side: nothing

Four independent sweeps of the pinned source went into this plan — allocation and
key order, update mode, splitting, schema evolution — and each was asked to end
with what ROOT's shipped documentation gets wrong. Between them they produced
around thirty such entries, most of which this project has already recorded.

**None of them contradicted a claim in `spec/`.** Three checked facts that looked
like the most likely places for an error and confirmed the text instead: the
checksum smuggled into a `TStreamerBase`'s `fMaxIndex[1]`
([Streamer information §9](spec/02-serialization/StreamerInfo.md#9-tstreamerbase-and-a-checksum-hidden-in-fmaxindex)),
the forged temporary that gives every STL element `fType` 500 and loses its status
bits ([§10](spec/02-serialization/StreamerInfo.md#10-tstreamerstl-stores-a-type-code-it-does-not-mean)),
and the slack past a key list and the zero padding past a free list, which are
already errata in
[Directories](spec/01-container/Directory.md#9-invariants) and
[Free segments](spec/01-container/FreeSegments.md#8-invariants).

That is the useful result to record before starting: this work is expected to be a
**reorganisation of known facts into write order**, not a discovery exercise. If it
turns out otherwise — if a byte comparison fails for a reason the reading side does
not predict — that is a finding about `spec/`, and it is the more valuable outcome
of the two.

## 2. The five experiments this plan rests on

Run with ROOT 6.40.04, reading the results with `tools/rootfile.py`. A 4031-byte
base file holds three objects — `a` and `b` (`TObjString`) and `h` (`TH1F`) — a
`StreamerInfo` record, a key list and a free list. Each experiment copies it and
reopens the copy in `UPDATE`.

### 2.1 Add one object

```
base                                 after adding c
   100    114 TFile   (the file)        100    114 TFile
   214     86 TObjString a              214     86 TObjString a
   300     85 TObjString b              300     85 TObjString b
   385    246 TH1F      h               385    246 TH1F      h
   631   3137 TList     StreamerInfo    631   3137 TList     StreamerInfo
  3768    210 key list                 3768     62 free list        <-- reused
  3978     53 free list                3830   -201 GAP
                                       4031     86 TObjString c     <-- old fEND
                                       4117    273 key list
fEND 4031, nfree 1                    fEND 4390, nfree 2
```

Five facts in one picture, and each one is a section of the document this plan
orders:

- **The key list and the free list are both freed and rewritten**, because both
  changed. Nothing else moved: the three data records and the `StreamerInfo`
  record are byte-for-byte where they were.
- **The new record goes at the old `fEND`** — not into the 263 bytes the key list
  and free list had just released, because it was written before they were.
- **The new key list did not fit** in that 263-byte gap (it needs 273) and went to
  the end. **The new free list did fit** (62) and took the front of it.
- **The order is therefore: data, then key list, then free list**, each allocated
  against the gaps that exist at the moment it is placed. An allocator is not an
  optimisation here; it decides the layout.
- **`fSeekInfo` did not move.** `TObjString`'s info was already in the file.

### 2.2 Rewrite an object under a name that exists

Writing `a` again, plus a `TGraph` under a new name:

```
   631    315 key list          <-- reused, from the freed StreamerInfo record
   946     63 free list
  1009  -3022 GAP
  4031     86 TObjString a   cycle 2
  4117    217 TGraph     g
  4334   3443 TList      StreamerInfo   <-- rewritten, 306 bytes longer
key list: a;2 @4031, a;1 @214, b;1 @300, h;1 @385, g;1 @4117
```

- **The old record at 214 is still there and still reachable.** `a;1` and `a;2`
  are both in the key list. A rewrite is an append.
- **The `StreamerInfo` record is freed and rewritten at the end** as soon as it
  changes, which released 3137 bytes at 631 — and the new key list went there.
  The file grew to 7777 bytes with a 3022-byte hole in the middle.
- **The key list is not in offset order, and not in insertion order either.**
  `a;2` precedes `a;1`, and `g` is last.

### 2.3 The key-list order rule

`TDirectoryFile::AppendKey` (`root/io/io/src/TDirectoryFile.cxx:225-256`) is the
whole rule, and it is four lines:

```cpp
   TKey *oldkey = (TKey*)fKeys->FindObject(key->GetName());
   if (!oldkey) { fKeys->Add(key); return 1; }          // a new name: append
   ...                                                   // else find the first
   fKeys->AddBefore(lnk, key);                           // and insert ahead of it
   return oldkey->GetCycle() + 1;
```

A new name is appended at the end; a name that already exists gets its key
inserted **before** the first key of that name, and its cycle is that key's cycle
plus one. Because every insertion is at the front of its name group, the first
match is always the highest cycle — which is what makes
[Records §4](spec/01-container/Record.md#4-cycles) say "highest existing cycle
plus one" and be right. The order in §2.2 falls straight out of it.

### 2.4 `kOverwrite`, where the payload fits

```cpp
a2.Write("a", TObject::kOverwrite);     // "alpha" -> "ALPHA", same length
```

```
   214     86 TObjString a   cycle 1     <-- same offset, same size, rewritten
  3768    210 key list                   <-- same offset, exactly refilled
  3978     53 free list
fEND 4031, nfree 1, size unchanged at 4031 bytes
key list: b;1 @300, h;1 @385, a;1 @214   <-- a moved to the end
```

The file is the same length it was and has no gap in it. **`kOverwrite` is the
only path that writes over live bytes**, and the key list still changed, because
the key was removed and re-appended.

### 2.5 `kOverwrite`, where it does not fit

The same write with a 29-character string:

```
   214     73 free list      <-- the free list took the freed record's front
   287    -13 GAP            <-- 13 bytes, smaller than any key
   3768   210 key list
   3978   -53 GAP
   4031   110 TObjString a   cycle 1     <-- at the old fEND
fEND 4141, nfree 3
```

`kOverwrite` degrades to delete-and-append, and the allocator leaves a **13-byte**
gap behind — marked, listed, and far too small to hold anything. That is the
smallest fragment this project has seen, and it is evidence about the allocation
rule: whatever ROOT does with a remainder, it does not have a minimum.

## 3. What the corpora show

Measured over `gen/foreign/` (154) and `gen/cern/` (26) as their manifests list
them, plus the 46 further `root.cern` files a previous session had fetched — 226
in all, of which `tools/rootfile.py` loads 225. `uproot-issue261.root` has a
zero-length record at 10427 and is already in `gen/foreign/IGNORE.toml`.

> The **tracked** corpora are 180 files, which is the number the front pages
> quote and what `check_invariants.py` runs over in CI. The wider set is used
> here because a census is worth more the more files it sees; every count below
> says which set it is over.

| Measured | Value |
|---|---|
| Files with **interior free space** — a gap that is not the trailing segment | **15 of 225** |
| Interior gaps in them | **139**, sizes 4 / 63 / 10908 (min / median / max) |
| Files where the in-place markers and the free list **agree exactly**, offset and length | **15 of 15** |
| Files holding a key at **cycle ≥ 2** | 5, with 9 such keys |
| Files whose key list is **not in offset order** | 10 |
| Directories walked | 372, in 225 files |
| Key lists walked, over the corpora **and** `data/` | 462 directories, 2395 keys |
| Name groups holding more than one cycle | **6**, and all six are in descending cycle order |
| Keys carrying the KEEP flag — a **negative** `fCycle` on disk | **0** |
| Files holding a class at **two different `fClassVersion`s** | **0 of 218** |
| Files holding a **duplicate** `(class, version)` | 3, all `ROOT::TIOFeatures` |

Three of those decide things in this plan.

**A 4-byte gap exists.** The smallest interior free segment in the corpora is four
bytes — exactly the width of its own marker, and nothing else. Any invariant of
the form "a gap is at least a key long" would be false, and §2.5 shows ROOT
producing a 13-byte one on demand.

**The marker is never missing.** [Free segments §4.2](spec/01-container/FreeSegments.md#42-the-marker-may-be-missing)
records, correctly, that the four-byte write is unchecked and the marker *may* be
absent. Across 139 gaps in 15 files it never is, and the magnitudes match the free
list as well as the offsets do. That makes "write the marker" a **fixed** field in
the procedure rather than an advisory one, and it makes a new invariant checkable
against the whole corpus rather than against one fixture.

**No file in 218 carries a class at two versions.** This is the measurement that
shapes item W4. The situation schema evolution exists for — one file describing two
layouts of one class — is *unwitnessed in the entire corpus*, so no fixture can be
found for it; one has to be **built**, and building it requires exactly what this
plan adds, an update of a file written earlier. `PLAN.md` §9.4 listed it as a gap
needing "two ROOT sessions or two files". It needs the same thing W3 does.

## 4. The four items

Ordered by dependency, not by size. W1 and W2 are prerequisites of W3 and are
small; W3 is the feature; W4 rides on W3 because it needs the file W3 produces.
A fifth — writing a split `TBranchElement` — was drafted and then cut; the
subsection after W4 says why, since the reasoning is the useful part.

Each item ends the way every item in `PLAN.md` §8.4 ended: with a file in
`data/written/` that ROOT opens without a word, and — wherever a ROOT-written
fixture of the same shape exists — with a **byte comparison** against it, because
that is what has found every error worth having in this layer.

### W1 — Free space, and where a record goes ✅ done 2026-09-21

*Delivered: `WritingFiles.md` §2 in five subsections, an allocator in
`tools/rootwrite.py`, `container/gap-reused` written by ROOT, and
`written/reused-space` written by this project — **the same 1747 bytes**, bar
each key's `fDatime`, the file's own name and the UUID, down to the stale bytes
left behind the marker. One new invariant, `FreeSegments 8.10`, confirmed by
corrupting a fixture and holding over 142 interior free segments.*

**What it adds.** One section of `WritingFiles.md` §2, which today says
"Allocation, in the one case that matters" and covers the case where there is no
free space. The procedure becomes: given a length, choose an offset; and given a
placement, update the free list and write the markers.

**What is already specified.** [Free segments](spec/01-container/FreeSegments.md)
has the record, both producers of the in-place marker (§4, §4.1), coalescing, the
1 GB steps of the trailing entry's `fLast`, and the rule that a directory record
is never freed. The reading side is complete; none of it is written as a
procedure.

**What the search actually is**, established for this plan and to be re-verified
against bytes when the section is written. `TKey::Create` asks
`TFree::GetBestFree` (`root/io/io/src/TFree.cxx:126-153`), and despite the name it
is **not** best fit:

- an **exact** match returns immediately, from anywhere in the list;
- otherwise it is **first fit** — lowest address, since the list is sorted — among
  segments satisfying `nleft > nbytes + 3`;
- the trailing segment is an ordinary candidate, not a fallback, and is almost
  always the one that first satisfies the test;
- the fallthrough — grow the last entry's `fLast` by 1 GB — runs only when nothing
  in the list fits at all.

**The `+ 3` is the fact worth having.** A partial use always leaves at least four
bytes, which is exactly the width of the marker that has to go there; and a segment
one, two or three bytes larger than the request is **skipped entirely** and stays
unused. That is why §3's smallest interior gap in 225 files is four bytes, and why
§2.5's thirteen-byte fragment is legal rather than a bug.

**The remainder is written by the new record's own key.** `TKey::Create` puts the
negative marker into the key's write buffer immediately after the payload
(`root/io/io/src/TKey.cxx:559-561`) and `TKey::WriteFile` extends the write by four
bytes to carry it (`root/io/io/src/TKey.cxx:1501`). There is no separate seek. A
writer that allocates into a gap and forgets those four bytes produces a file whose
free list knows about the remainder and whose record chain runs into the stale
bytes of whatever was deleted — which is the failure
[Free segments §4.2](spec/01-container/FreeSegments.md#42-the-marker-may-be-missing)
describes as "only recovery suffers", and it deserves testing rather than
assuming.

**An exact fit removes the entry** (`root/io/io/src/TKey.cxx:551-552`), which is
why `nfree` can fall as well as rise.

**The freedom question, and the answer looks favourable.** `TFile::ReadFree`
terminates on the first entry whose `fLast` exceeds `fEND`
(`root/io/io/src/TFile.cxx:1990-1995`) and **`nfree` is parsed into a local that is
never used again** (`root/io/io/src/TFile.cxx:681`, `:743`, `:753`) — a fact
[Writing files §15](spec/06-writing/WritingFiles.md#15-what-root-does-not-check)
already records from the other direction. So the trailing entry is a hard
requirement and the rest of the list is bookkeeping ROOT trusts. If a third-party
allocator that is not first fit survives contact with ROOT — and nothing so far
suggests it will not — then the search is **free, with constraints** and the
constraints are the invariants below, which is the treatment basket sizing already
gets.

**Fixtures.** `gen/written/reuse/` — a file whose second object is placed in a gap
left by a first. And the byte target: `gen/cases/container/gap` already exists on
the ROOT side and is a deletion without a reuse, so a companion ROOT case
`container/gap-reused` is wanted, and it is the comparison that proves the
allocator rather than the bookkeeping.

**Invariants.** Candidates, each to be confirmed by corrupting a fixture:
every interior free segment carries a marker whose magnitude is its length; no
free segment overlaps a live record; the free list is sorted and non-overlapping;
the last entry begins at `fEND`. The first of those is checkable over all 225
corpus files today, which is the standard `check_invariants.py` entries are held
to.

### W2 — Keys: cycles, order, and deletion ✅ done 2026-09-21

*Delivered: `WritingFiles.md` §8.1 and §8.2, `AppendKey`'s rule in
`tools/rootwrite.py`, and `written/cycles` — **the same 1361 bytes** as
`data/container/cycles.root`. One new invariant, `Directory 9.14`. The ordering
claim is no longer a reading of the source: reversing three key images in a file
and changing nothing else makes `Get("str")` return the **oldest** copy, silently,
and that measurement is in §8.1.*

**What it adds.** A short document section, and it is short because §2.3 is the
whole rule. A writer has to know: where a new key goes in the list, what cycle it
gets, what happens to the old one, and what a deletion leaves behind.

**What is already specified.** [Records §4](spec/01-container/Record.md#4-cycles)
has the numbering and both resolution rules, with `container/cycles` as the
fixture. What no document states is the **order**, which is `AppendKey`'s
insert-before-the-first-match — and which is why ten corpus files have key lists
that are not in offset order.

**The order is not a convention, and this is the finding that makes the item worth
a section.** ROOT never compares cycles to pick a maximum. `Get`, `GetKey` and
`FindKeyAny` all return the **first** match in the name's hash bucket, which is the
key-list order (`root/io/io/src/TDirectoryFile.cxx:1002`, `:1167`, `:829`). The
"highest cycle" semantics that
[Records §4](spec/01-container/Record.md#4-cycles) states are therefore *produced by
the ordering*, not by the lookup — so a writer that appends a new cycle at the end
of the key list makes `Get("h")` return the **oldest** copy, with no error anywhere.
`TDirectoryFile::Purge` inherits the same dependency and would delete the newest
(`root/io/io/src/TDirectoryFile.cxx:1316-1327`).

So the write-side rule splits cleanly, which is what this layer's field kinds are
for: the order of **distinct names** is **free**, and the order **within one name**
is **fixed** — newest cycle first.

**One more thing a writer must not normalise away.** A stored `fCycle` is
*negative* when the KEEP flag is set (`root/io/io/src/TKey.cxx:731-733`), written
raw (`root/io/io/src/TKey.cxx:659`), and `GetCycle` returns its absolute value
(`root/io/io/src/TKey.cxx:623-625`). `tools/rootfile.py` already exposes it as
`Record.keep`.

**Fixtures.** `gen/written/cycles/` — the same name written three times, checked
against ROOT's own `container/cycles` record for record. `verify.C` asserts that
`Get("x")` returns the third and `GetKey("x;2")` the second.

**Invariants.** Within a directory, keys sharing a name have distinct cycles and
appear in **descending** cycle order; a key's `fSeekKey` equals the offset of the
record it describes (already
[Directories 9.11](spec/01-container/Directory.md#9-invariants)); no key's cycle is
zero. The descending-order one is checkable today but **thinly**: §3 finds only six
multi-cycle name groups in 462 directories, and all six satisfy it. It would still
be the first invariant this project has that catches a *writer's* mistake in a file
ROOT reads without a word, and W2's fixtures are what give it teeth.

### W3 — Updating an existing file ✅ done 2026-09-21

*Delivered: `WritingFiles.md` §13 in ten subsections, `FileWriter.reopen` in
`tools/rootwrite.py`, and two fixture pairs — `container/reopened` and
`container/reopen-gap` written by ROOT, `written/reopen-add` and
`written/reopen-reuse` written here, **the same 1657 and 1928 bytes**, bar each
key's `fDatime`, the file's own name and two UUIDs, and including the dead keys
still buried behind the gap markers. One new invariant, `FileHeader 10.11`.*

**Four of the open questions below were settled by measurement**, and two of them
turned out to be bigger than the plan expected:

1. **`kOverwrite` against `kWriteDelete` differ in three visible ways**, not one.
   `overwrite` frees before it allocates, so the replacement lands at the old
   address and the cycle does **not** advance; `WriteDelete` frees afterwards, so
   it cannot, and the cycle does. Both take the **newest** key of that name.
   Tabulated in §13.5, and both halves are in the bytes — `tail` at 493 with
   cycle 1, `two` at 1259 with cycle 2.
2. **The 2 GB question has an answer and it is a defect.** Each field widens when
   its own value crosses, independently — a key on `fSeekKey`, a free entry on
   `fLast` alone, the header on `fEND`. But the large header is **75 bytes** and
   `TFile::WriteHeader` allocates `fBEGIN` of them; **four files in the corpora
   have `fBEGIN` of 64**, so updating one past 2 GB writes over its own first
   record. Stated as `FileHeader 10.11`, refused by `reopen`, and one for
   `PLAN.md` M10.
3. **A no-op update changes three bytes, not four**, and they are timestamps:
   `fDatimeM` plus the `fDatime` of the two recreated keys. Everything else,
   `fEND` included, is identical, because both records are freed and refitted
   exactly where they were. A read-only open changes nothing.
4. **Two writers, one file** is stated as out of scope in §13.10 and in
   `spec/06-writing/index.md` §4, as planned.

**Two findings the plan did not anticipate.** `TDirectoryFile::Delete` is a
**save** — it writes the key list, the directory header and the free list before
returning (`root/io/io/src/TDirectoryFile.cxx:736-738`) — which is why the
fixtures make their holes with `"overwrite"` instead; and `Delete("name")` with no
cycle touches memory only, so it takes `Delete("name;1")` to remove a key. Both
are in §8.2.

**And the invariants question resolved the other way.** The plan expected an
update to need invariants of its own; it needs none, because nothing in the
result records that a file was reopened. That is now said explicitly in §14 and
in `WriterInvariants.md` §8. The one exception is `fBEGIN`, which a create
satisfies by construction and an update is handed.

**What the fixtures cost in naming.** Both pairs needed names of equal length —
`data/container/reopened.root` against `data/written/reopen-add.root`, and
`reopen-gap` against `reopen-reuse`, 28 and 30 characters — because four records
carry the file's name and two carry their own offsets.

---

*The original plan for this item follows.*

**The feature.** Everything above exists to make this possible. The procedure is
a reopen: read the header, the free list and the key lists; write new records into
the space that is free; free and rewrite the key lists, the `StreamerInfo` record
if it changed, and the free list; rewrite each directory header and the file
header.

**What §2 already establishes**, and what the document can therefore state as
fact rather than as a reading of the source: the order of the three closing
writes, that the `StreamerInfo` record is rewritten only when it changes, that a
rewrite is an append, that `kOverwrite` is the one path that writes over live
bytes and degrades to append when the payload grows, and that the directory
record itself never moves — which
[Writing files §5.3](spec/06-writing/WritingFiles.md#53-the-record-never-moves-and-a-directory-key-is-never-freed)
already says for creation and which is what makes an update possible at all.

**What an update inherits from the file, which is more than it looks.** On
`UPDATE` ROOT reads the header and then **overwrites four of its own members with
what the file says**: `fVersion`, `fUnits`, `fCompress` and `fTitle`
(`root/io/io/src/TFile.cxx:734`, `:745`, `:746`, `:839`). The compression level
passed to `TFile::Open` is silently discarded, and the header written at close
carries the **original producer's** `fVersion` — so a file updated by 6.40.04 can
still declare that it was written by 5.28, and every claim a reader makes from
`fVersion` is a claim about the *first* writer.

**`fName` is the exception, and it is visible in the bytes.** ROOT deliberately
does not restore it — the source says so on the line that skips it,
`// fName.ReadBuffer(buffer); file may have been renamed`
(`root/io/io/src/TFile.cxx:838`). The key list and the free list stamp `fName` into
the keys they create, so after an update **the file's own record and its key-list
record disagree about the file's name**. §2.1 shows it: the records at 100 and 214
still say `base.root` while the keys written at close say `upd.root`. A writer
following this procedure has to decide which name it writes, and a *reader* must
not assume the two agree.

**When the `StreamerInfo` record is rewritten, and when it is not.** There is an
early-out — nothing is rewritten unless a class new *to the file* was used
(`root/io/io/src/TFile.cxx:3497-3503`) — and §2.1 and §2.2 are the two sides of
it: adding a `TObjString` to a file that already describes one left `fSeekInfo`
untouched, and adding a `TGraph` moved it and grew the record by 306 bytes. That
early-out is the difference between an update that touches three records and one
that touches four and leaves a 3 KB hole.

**What the close sequence is.** `WriteStreamerInfo`, then each directory's
`WriteKeys` and `WriteDirHeader`, then `WriteFree`, then `WriteHeader`. Two details
of it are what §2 measured rather than assumed: `WriteKeys` **always reallocates**,
freeing its old record before sizing the new one — which is why the new key list so
often lands on the old one's address — while `WriteDirHeader` **always rewrites in
place**, at `fSeekDir + fNbytesName`, which is the same fact
[Writing files §5.3](spec/06-writing/WritingFiles.md#53-the-record-never-moves-and-a-directory-key-is-never-freed)
already states for creation.

**What still has to be established**, each to be verified against bytes rather than
taken from a reading of the source:

1. **`kOverwrite` against `kWriteDelete`.** They differ in *when* the old record is
   freed — before the allocation or after — which decides both whether the address
   is reused and whether the cycle advances. §2.4 and §2.5 measured `kOverwrite`
   only.
2. **The 2 GB crossing during an update**, which produces a file whose old records
   are 32-bit and whose new ones are wide. The reading side has this
   ([Large files](spec/01-container/LargeFiles.md), witnessed by `volume.root`);
   what the writing side needs is the *order* in which the widths change, and
   whether a file whose `fBEGIN` is 64 can be pushed past the boundary at all —
   the large header is 75 bytes and would not fit. That last one is a suspected
   defect rather than a fact, and it is the first thing to check because the
   failure mode is overwriting the first record.
3. **A no-op update still changes bytes.** Open, write nothing, close: the free
   record is freed and reallocated with a fresh `fDatime`. If that holds, an update
   procedure cannot describe itself as "no change, no write", and a fixture should
   pin it.
4. **Two writers, one file** — out of scope, and the document should say so rather
   than leave it: ROOT takes no lock a third party can see.

**Fixtures.** This is where `data/written/` being byte-reproducible pays off, and
it is the reason this item is feasible at all as a checked case: an update case's
`build()` reads a committed `data/written/*.root`, applies the update and returns
the bytes, so the result is as reproducible as the input. Three cases:

| Case | Base | Adds |
|---|---|---|
| `written/update-append` | `objstring.root` | a second object, into a file with no gaps |
| `written/update-reuse` | a base with a gap | a record that fits the gap, and one that does not |
| `written/update-cycle` | `objstring.root` | the same name again, so the key list grows a second cycle |

Each also gets a ROOT-side twin: ROOT performing the *same* update on the *same*
committed base, compared record by record with the datime and UUID masked, which
is the comparison `tools/test_write.py` already knows how to do.

**Invariants.** The ones a file carries after an update that it does not carry
after a create: no two records overlap; every free segment is disjoint from every
record; `fEND` is at or past the end of the last record; the key count in each
directory's key list matches the records that name it as parent. Most of these are
worth checking on *every* file, not only updated ones, which is the usual sign
that an invariant is the right one.

### W4 — Schema evolution, from the writing side ✅ done 2026-09-21

*Delivered: `WritingObjects.md` §8 in seven subsections, `listOfRules` support in
`tools/rootwrite.py`, `written/two-versions` — one class at two versions, which no
single ROOT session can produce — and a correction to `StreamerInfo.md` §9.1 that
came out of an invariant this item got wrong.*

**The merge rule, which was the one thing left to establish, has two answers and
the plan guessed the wrong one.** It expected ROOT to discard one of the two infos;
measured with two ACLiC sessions over one file, it does not:

- **different class versions** → ROOT keeps **both**, writes two records of
  different lengths, and says nothing. So the file this item was going to have to
  construct by hand is one ROOT produces itself, on any update by a session whose
  class has evolved;
- **the same version, different checksum** → ROOT warns at open
  (`BuildCheck`, `CompareContent`) and then keeps **the file's** info and
  truncates the object it writes. The third member of a three-member class never
  reaches disk: 54 bytes where 58 were due, with no further word. That is the
  destructive case, and §8.5 records it. This project's writer refuses instead.

**Two findings the plan did not have.**

*ROOT cannot read an emulated class that derives from `TObject`* — a silent
data-loss path in ROOT, found here and witnessed on a file **ROOT wrote itself**.
`TKey::ReadObj` streams a `TObject`-derived object with `tobj->Streamer()`, which
with no dictionary resolves to `TObject::Streamer`: ten bytes and stop. A class
with `fA = 77` and `fB = 1.25` reads back as 0 and 0. `tools/rootfile.py` recovers
both from the same bytes. It is why `written/two-versions` uses a non-`TObject`
class, and it is in `SchemaEvolution.md` §7.1 and §8.7 of the new section. One for
`PLAN.md` M10.

*The incomplete closure is loud, not silent.* The plan said a missing base info
gives "a `Warning` and then a desynchronised buffer... surfacing later as a
`CheckByteCount` complaint about an unrelated object". Measured, it complains about
**the base itself** and recovers, because the base's bytes carry their own byte
count — the members after it still read correctly and the next record is untouched.
The silent version needs a base whose bytes have no byte count, which `TObject`'s
do not.

**`listOfRules` paid off more than expected.** The plan said specifying it "buys a
byte-identical comparison where today two of the nine are identical bar one
entry". It was four, not two, and emitting it makes **seven whole `StreamerInfo`
records** byte-identical to ROOT's: 370, 9628, 11789, 12169, 14121, 14580 and
14584 bytes. Four `case.toml`s and four fixtures moved to pay for it.

**The invariant that was not.** `StreamerInfo 13.13` was written, checked in, and
withdrawn within the hour: it claimed a `TStreamerBase`'s `fBaseVersion` equals the
base info's `fClassVersion`, and the two corpora produced five counterexamples on
the first run. All five are correct — `fBaseVersion` records the base version the
*derived* class's info was built against, which an info carried into a later file
outlives. The return is better than the invariant would have been: four
ROOT-published files (`aleph`, `atlas`, `cms`, `hades`) have `fBaseCheckSum` 0
*and* an `fBaseVersion` naming a version the file has no info for, so **the
fallback `StreamerInfo.md` §9.1 instructs a reader to use has nothing to land on**.
§9.2 is new and adds the third step. This is the third time a wrong claim of this
project's has been caught by running the invariants over files it did not write,
and the first time the wrong claim was one it had just written.

The *closure* is deliberately not an invariant either: its exemption is a property
of ROOT's source rather than of the file, and the two lists that carry it are
already CI-checked.

---

*The original plan for this item follows.*

**What it adds.** A section of `WritingObjects.md`, or a document of its own, that
answers one question: **what must be in the file so that a reader whose class is
not the writer's can still read it?** This is deliberately not "how to write an
earlier version" — `PLAN.md` decision 3 keeps that out, ROOT has no mechanism for
it ([Writing §3.1](spec/06-writing/index.md#31-what-the-current-version-means)),
and nothing here changes that.

**What is already specified.**
[Schema evolution](spec/02-serialization/SchemaEvolution.md) is one of the more
complete documents in the project: §3 checksums, §4 how a reader chooses an info,
§6 `listOfRules` and the finding that **ROOT writes it and never reads it back**,
§7 emulated classes, §8.1 duplicates. The write side of all of that is one
paragraph long today — [Writing files §7](spec/06-writing/WritingFiles.md), which
says to emit an info for every class used.

**What the research for this plan established**, and it makes the item much
smaller than it looked. `TStreamerInfo::BuildOld` — the reader's evolution engine —
iterates the **on-disk** element list, not the in-memory one, and matches each
element to a member **by name and nothing else**. So a writer's obligations are a
short list:

| Obligation | Why |
|---|---|
| One info per class actually serialized, **plus the transitive closure** of its bases and contained classes | the failure below |
| `fClassVersion` in range, written as an **absolute value** — a `-1` in memory reaches disk as 1 | the write path negates it |
| `fCheckSum` agreeing with the element list shipped beside it | it is the key the reader's own rules are selected by |
| Element `fName` strings matching the in-memory member names | the only thing evolution matches on |
| For every `TStreamerBase`, a correct `fBaseVersion` **and** the base's checksum in `fMaxIndex[1]` | [Streamer information §9](spec/02-serialization/StreamerInfo.md#9-tstreamerbase-and-a-checksum-hidden-in-fmaxindex) already specifies the smuggled field from the reading side |

**And the mistake that actually destroys a file is not any of the obvious ones.**
Writing an info for a derived class but **not for its base** produces, in a reader
with no dictionary for that base, a `Warning` and then a **desynchronised buffer** —
the base's bytes are never consumed, and everything after them is read at the wrong
offset. It surfaces later as a `CheckByteCount` complaint about an unrelated
object. That is why the closure is an obligation rather than a nicety, and it is
the first invariant this item should add.

**Three things a writer might reasonably worry about and does not have to.**

- **`fSize` is discarded** for any member of a class the reader has compiled in —
  `BuildOld` recomputes it from the in-memory type and the on-disk
  `fArrayLength`. It matters only for an emulated class. That is also why
  `tools/normalize.py` can mask it at all.
- **`fArrayDim` and `fMaxIndex` are never compared** against the in-memory member;
  a disagreement is silent.
- **Artificial and cache elements never reach disk.** The write path does not
  stream `fElements`; it builds a filtered temporary, dropping every
  `TStreamerArtificial`, every `kRepeat`, and every read-only `kCache`
  (`root/io/io/src/TStreamerInfo.cxx:5694-5707`), and `TStreamerArtificial`'s own
  `Streamer` is a deliberate no-op. This is the write-side confirmation of
  [Schema evolution §6.3](spec/02-serialization/SchemaEvolution.md#63-rules-do-not-change-the-streamer-info)
  and of [Element types §11](spec/02-serialization/ElementTypes.md#11-invariants),
  which forbid those codes in a file — and it means an info that came *off* a file,
  went through `BuildOld`, and is written back out is stripped automatically.

**When a file legitimately holds two infos for one class**, which §3 says no corpus
file does: a `TStreamerInfo`'s identity number is **per instance, not per class**,
so two infos for one class occupy two slots and both are written. Four things
produce that — a fast clone carrying the source file's infos across, **reopening a
file** and writing an object of a class already described in it, the dependency
closure, and writing an object at a version the session had to rebuild. The second
is W3, which is why this item rides on it.

**`listOfRules` is optional, and now for a stated reason.** ROOT collects the rules
of the *class*, with no reference to the version being written, so a file written
at `TTree` 20 ships two rules that apply to source versions ≤ 16 and ≤ 18, and a
`TProfile` 7 file ships one that applies to versions 1–5 — rules that can never
match their own data. Since ROOT also never reads the list back
([Schema evolution §6.2](spec/02-serialization/SchemaEvolution.md#62-root-ignores-it)),
a writer emitting only current versions may omit it with **no loss of
information**, which is what `data/written/th2-profile.root` already does. What
specifying it buys is a byte-identical comparison where today two of the nine are
identical bar one entry.

**What is left to establish**, and it is one question rather than four: **the merge
rule.** When an update meets a file whose info for a class disagrees with the
session's, ROOT resolves it by discarding one of the two — and which one it
discards depends on whether the incumbent has been used yet. A writer has to decide
deliberately what this project's procedure does, and the honest options are to keep
both or to refuse. That decision needs the fixture below before it is taken.

**Fixtures.** `written/update-evolve`: take a committed base, and write into it an
object of the same class at a different layout — which is exactly the file §3 says
does not exist in 218 corpus files. `verify.C` reads both objects back. This is
the one case in this plan that produces a file **no ROOT session can produce**,
which makes it the most interesting and the one most likely to find something.

### Not an item: a split `TBranchElement`, which stays read-only

This was drafted as W5 and is **deliberately not one**. The decision is worth
recording with its reasoning, because "we specify reading it and not writing it"
is an odd-looking asymmetry until the reasons are on the page.

**Reading one is finished.** [Splitting](spec/04-ttree/Splitting.md) and
[Split branches](spec/04-ttree/TBranchElement.md) specify the branch tree, the
naming rules, `fSplitLevel`, `fType`/`fID` and the nine-way read dispatch;
`rootfile.TreeReader` decodes it, and the `ENTRIES` line over both corpora is
**27969 of 28036 branch-baskets, 99.8%, 0 failures**, with neither remaining skip
being a split-branch gap. What is left is `PLAN.md` §9.11's residue —
`TBranchSTL` entries, `kStreamLoop` values, a non-null `fBranchCount2` — and it
stays there, on the reading side, where it already is.

**Writing one would buy a third party very little**, for three reasons:

1. **Jagged data does not need splitting, and this layer already writes it.** What
   people usually want from "columnar output" is a variable-length array per
   entry, `Int_t n; Float_t x[n]`, and that is a **flat** `TBranch` with a counter
   leaf — no `TBranchElement` anywhere.
   [Writing trees §4.3–§4.4](spec/06-writing/WritingTrees.md#43-the-leaf) specifies
   it and `data/written/tree.root` contains one, written as
   `tree.branch("a", "F", counter=n)`.
2. **A split file is only fully usable by a reader that has the class.**
   `TBranchElement::InitializeOffsets` reconstructs each member's offset by string
   surgery on the branch name followed by a **dictionary lookup**
   (`root/tree/tree/src/TBranchElement.cxx:3186` onward, `Fatal` at `:3727`). So
   splitting buys nothing for a consumer that is uproot or a third-party reader —
   they take the columns from the streamer info either way.
3. **An unsplit branch is never wrong.** A branch at `fType` 0, `fID` −1 holding
   each whole object produces a file ROOT opens and reads correctly. The cost is
   read performance on files the writer itself produced, which is the writer's own
   trade to make — exactly the kind of choice `PLAN.md` §8.4 settled as policy.

**What the writing layer says instead**, and it is a paragraph rather than a
procedure: a conforming writer SHOULD emit unsplit branches; here is what a split
file requires of whoever produces one — the `fType` set, the naming rules,
`fMaximum`, and the closure of streamer infos — and here is
[the reading side](spec/04-ttree/Splitting.md) for anyone who wants to. That
paragraph belongs in
[Writing §4](spec/06-writing/index.md#4-what-is-not-specified), which already
excludes split branches and currently gives one sentence of reason.

**Two facts found while scoping it are worth keeping**, because they are true of
the format rather than of the plan:

- **The shape is policy; the names are format.** A writer may split less deeply
  than ROOT would. It may not invent names, because the names are what the offsets
  are reconstructed from.
- **A trailing dot on every top-level branch name is strictly better than ROOT's
  default.** With no dot, `Unroll` drops the parent prefix from every child
  (`root/tree/tree/src/TBranchElement.cxx:6217`), which is precisely the condition
  under which `PLAN.md` §7.1 item 9's counter bug fires. That belongs in
  [Splitting §3](spec/04-ttree/Splitting.md#3-names) as a note to anyone *choosing*
  a branch name, reader or writer.

## 5. The fixture matrix

Eight new cases, two of them ROOT-written and there only to be a byte target.
`data/written/` grows from nine files to **fifteen**.

| Case | Kind | Proves |
|---|---|---|
| `gen/cases/container/gap-reused` | ROOT | a record placed **into** a gap, which no committed fixture has |
| `gen/written/reuse` | ours | the allocator: exact fit, partial fit, and the remainder marker |
| `gen/written/cycles` | ours | three cycles of one name, in descending order |
| `gen/written/update-append` | ours | an update of a file with no gaps |
| `gen/written/update-reuse` | ours | an update that fills a gap and one that cannot |
| `gen/written/update-cycle` | ours | an update that adds a cycle |
| `gen/cases/container/update-twin` | ROOT | ROOT performing those same three updates on the same committed bases |
| `gen/written/update-evolve` | ours | one file, two layouts of one class — **the file no ROOT session produces** |

The three `update-*` cases are what make the whole plan checkable, and the reason
is worth stating once more: **`data/written/` is byte-reproducible**, so a case
whose input is a committed file this project wrote has a deterministic output. An
update of a *ROOT-written* fixture would not — its key datimes and UUID are masked,
not fixed — which is why the twins are compared record by record with
`tools/normalize.py`'s masks rather than byte for byte.

## 6. Tooling

**`tools/rootwrite.py`** needs one structural change and it is the only large one:
today `FileWriter` builds a file in memory in a single pass, with no model of
occupied space. It needs an allocator — a free list, `place(length) -> offset`,
and the marker write — and a constructor that starts from an existing file's
header, free list and key lists rather than from nothing. Everything else in the
writer is already expressed as "a record and its key", which is the unit an
allocator hands out.

**`tools/check_write.py`** needs a case to be able to declare a **base file**, so
that `build()` receives it rather than reaching for a path itself. Gate 3 gains
nothing new: ROOT opens the updated file the same way it opens a created one.

**`tools/check_invariants.py`** gains the W1–W3 entries, and they are the first
in the project that are about *consistency between records* rather than inside
one — no two records overlap, no free segment overlaps a record, the markers
agree with the list. Those run over every file in `data/` and both corpora from
the day they are added, which is the test of whether they are the right
invariants.

**`tools/rootfile.py`** needs very little: it already reads the free list, the
markers, the key lists and the cycles. The one addition W2 implies is exposing a
key's position in its list, so an invariant can check descending cycle order.

## 7. Open questions

Each is small, each is answerable, and each is written down so it is not
rediscovered.

1. **May a third-party allocator differ from first-fit?** §4's W1 argues yes on
   the evidence that `nfree` is never read and the free list is only consulted
   when writing. The test is a written file whose records are placed differently
   from ROOT's and that ROOT then updates.
2. **What does ROOT do with a file whose `fBEGIN` is 64 when an update pushes it
   past 2 GB?** The large header does not fit. This is a suspected defect and it
   was found by reading rather than by running; it needs a test before it is
   written down as anything.
3. **Does a no-op update really change four bytes and no more?** If so it belongs
   in `Pitfalls.md` as well as in the procedure.
4. **Does an update of a file this project wrote round-trip through ROOT and back
   into our writer?** One direction is already measured — ROOT updated
   `data/written/objstring.root` cleanly, reusing the key list's space, placing
   the new record at the old `fEND` and **adding a `StreamerInfo` record** because
   our file deliberately has none. The other direction is the test that matters:
   our writer updating a file ROOT wrote.

## 8. What this does *not* add

Named here so the boundary stays visible, because the last scope statement grew
without anyone deciding it should:

- **Earlier class versions.** Unchanged, and for the same reason as before: ROOT
  has no mechanism to write one. W4 is about what a *reader* at another version
  needs, not about emitting an old layout.
- **RNTuple writing.** Upstream's specification covers both directions.
- **Two writers on one file.** ROOT takes no lock a third party can see.
- **Writing a split `TBranchElement`**, which the subsection after W4 argues at
  length. Reading one is finished and stays finished; a writer emits unsplit
  branches, and a flat branch with a counter leaf already covers what jagged data
  needs.
- **`TBranchSTL`, and collections of pointers at split level 100.** Zero corpus
  coverage, one fixture, and not decodable by either entry check today
  (`PLAN.md` §9.11) — a **reading** gap, and it stays in §9.11.
- **Policy, still.** Basket sizes, when to flush, which gap to choose. W1
  specifies what a choice *produces* rather than requiring a particular choice —
  which is the treatment `PLAN.md` §8.4 settled on and this plan does not
  reopen.

## 9. What changes in `PLAN.md` when this lands

Four places, and all four currently say the opposite, so none of them should be
edited before the work is done:

1. **Decision 3** names "free-space reuse, updating an existing file, basket
   sizing, key ordering" as unspecified. Basket sizing stays; the other three go.
2. **§2.8**'s last paragraph and **§2.9**'s table — one more procedure document,
   for the update, and the reuse and cycle sections of `WritingFiles.md`.
3. **[Writing §4](spec/06-writing/index.md#4-what-is-not-specified)**, which is
   the user-facing version of the same list and the one that matters most. Its
   **split-branch entry stays**, and gains the reasoning from the subsection after
   W4 — a scope statement with reasons is worth more than the one sentence it
   carries now.
4. **§9.4**, where "two streamer infos for one class distinguished by checksum"
   and "a non-zero `fPidOffset`" are listed as gaps needing two sessions. W3 and
   W4 close the first; the second becomes reachable for the first time, since
   copying a key between files is what an update makes possible.

And one thing that does **not** change: the conformance test. Every item here ends
with a file ROOT opens in silence, and wherever a ROOT-written fixture of the same
shape exists, with a byte comparison against it. That standard is what found the
`TObjArray` framing, the Y axis's `fTitleOffset`, the `fEntryOffsetLen` shrink, the
pre-5.34 directory key-name bug and the `TGraph` fill defaults, and nothing in this
plan is worth having if it is not held to it.
