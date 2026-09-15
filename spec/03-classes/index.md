# Standard classes

Most ROOT classes need no text here. They are described by the streamer info in
the file that contains them, and
[Streamer-driven reading](../02-serialization/StreamerDriven.md) is enough to
decode them — including every class a user defines.

This layer covers only the classes whose recorded streamer info does **not**
describe their bytes, because their `Streamer` is hand-written.

## How small that set is

Smaller than it looks. Many ROOT classes do have a hand-written `Streamer`, but it
is a version guard that delegates to the generated path above a threshold and
keeps a legacy layout below it:

| Class | Hand-written below | Streamer-info driven at |
|---|---|---|
| `TH1`, `TH2`, `TH3`, `TGraph` | class version 3 | version 3 and above |
| `TAxis` | 6 | 6 and above |
| `TAttAxis` | 4 | 4 and above |
| `TTree` | 5 | 5 and above |
| `TBranch` | 10 | 10 and above |
| `TLeaf` | 2 | 2 and above |
| `TLeafObject` | 4, with two shapes below it | 4 and above |
| `TLeafF16`, `TLeafD32` | — | every version, plus a title fixup below 2 |
| `TBranchElement`, `TRefTable` | — | every version |

Every version a current file contains is on the right-hand side, so **histograms,
graphs and `TTree` metadata are ordinary streamer-info-driven objects** and need
no hand-written specification. The legacy layouts below each threshold need files
older than ROOT 6 to test against and are tracked as gaps in `PLAN.md` §9.1.

## The classes that diverge at every version

Ten, and they are specified where their behaviour arises rather than collected
here — see `PLAN.md` decision 6. This table is the index:

| Class | Specified in |
|---|---|
| `TObject` | [Buffer framing §7](../02-serialization/Buffer.md#7-the-tobject-base), and [References §1](../02-serialization/References.md#1-the-extra-word-on-a-referenced-tobject) for the referenced form |
| `TString` | [Conventions §5.1](../00-conventions.md#51-counted-string) |
| `TList` | [Streamer information §4](../02-serialization/StreamerInfo.md#4-tlist) |
| `TObjArray` | [Streamer information §5](../02-serialization/StreamerInfo.md#5-tobjarray) |
| `TClonesArray` | [Collections §12](../02-serialization/Collections.md#12-tclonesarray) |
| `TRef`, `TRefArray` | [References §3](../02-serialization/References.md#3-tref), [§4](../02-serialization/References.md#4-trefarray) |
| `TArray*` | [TArray](TArray.md) |
| `TDatime` | [Records and keys §3.7](../01-container/Record.md#37-fdatime) — four bare bytes as a member, exactly as in a key |
| `TCollection` | not specified; reachable only through `TList`'s fictional streamer info, which no reader should follow ([Streamer-driven reading §7](../02-serialization/StreamerDriven.md#7-when-the-streamer-info-does-not-describe-the-bytes)) |

`TFile` and `TDirectoryFile` are also hand-written, but they are the container
rather than objects in it, and belong to
[the container layer](../01-container/Directory.md).

`TBasket` has no streamer info at all and belongs with `TTree`: see
[TBasket](../04-ttree/TBasket.md).

`TBranch` and the `TLeaf` family are in the right-hand column above and so need no
hand-written layout, but what their fields *mean* is not recoverable from a
streamer info: see [TBranch](../04-ttree/TBranch.md) and
[TLeaf](../04-ttree/TLeaf.md). The `TLeafF16`/`TLeafD32` entry is the exception
that proves the rule — their streamers are hand-written purely to re-parse a
packing annotation out of the leaf title, which no streamer info records.

## Why there is no generated table here yet

`PLAN.md` §2.4 plans generated member tables and version matrices for all ~440
persistable classes, produced by `tools/gen_tables.py` from the pinned submodule.
That tooling is not built. Until it is, this layer is deliberately thin: a
generated table that nobody checks is worse than a pointer to the algorithm that
produces the same answer from the file itself.
