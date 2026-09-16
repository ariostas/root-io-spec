# Glossary

Every term this specification uses with a meaning it does not have in ordinary
English, and where that meaning is fixed. The short list of the terms a reader
meets first is [Conventions §9](../00-conventions.md#9-terminology); this is the
full one.

Where a term is ROOT's own — a field name, a constant — it is spelled as ROOT
spells it. Where this specification had to choose a word, that is said.

## Container

| Term | Meaning |
|---|---|
| **Record** | A `TKey` plus its payload, at one offset in the file. The unit a file is a sequence of. [Records and keys §1](../01-container/Record.md#1-the-record-chain) |
| **Key** | The fixed-layout part of a record, describing where and what the payload is. [§2](../01-container/Record.md#2-key-layout) |
| **Payload** | The bytes of a record after the key. Possibly compressed. |
| **Object data** | A payload after decompression, as consumed by the serialization layer. |
| **Record chain** | The records in file order, each found by adding the previous one's `fNbytes`. It is a walk, not an index, and nothing in `TFile::Open` uses it. [§1](../01-container/Record.md#1-the-record-chain) |
| **Cycle** | The small integer distinguishing successive versions of an object with the same name in a directory — the `;1` in `h;1`. [§4](../01-container/Record.md#4-cycles) |
| **Directory record** | The record holding a `TDirectoryFile`'s own fields, including where its key list is. [Directories §2](../01-container/Directory.md#2-layout) |
| **Key list** | The record a directory points at with `fSeekKeys`, holding a copy of every key in that directory. [§6](../01-container/Directory.md#6-key-lists) |
| **Free segment** | A byte range in the file not occupied by any record. [Free segments](../01-container/FreeSegments.md) |
| **Large-file flag** | `fVersion >= 1000000` in the header or a directory record, selecting 8-byte file offsets instead of 4. Three of them are independent. [File header §3](../01-container/FileHeader.md#3-fversion-and-the-large-file-flag), [Directories §3](../01-container/Directory.md#3-three-independent-large-file-flags) |
| **Block header** | The nine bytes introducing one compressed block: a two-byte algorithm tag, a method byte, and two 24-bit little-endian sizes. [Compression §2](../01-container/Compression.md#2-block-header) |

## Serialization

| Term | Meaning |
|---|---|
| **Buffer** | The byte sequence one record's object data lives in. Positions and the map are relative to its start, not to the file's. [Buffer framing §1](../02-serialization/Buffer.md#1-what-a-buffer-is) |
| **Byte count** | A four-byte length with `kByteCountMask` (bit 30) set, giving the size of what follows. Authoritative: a reader that has consumed the wrong number of bytes MUST believe it. [§2](../02-serialization/Buffer.md#2-byte-counts), [§2.1](../02-serialization/Buffer.md#21-a-byte-count-is-authoritative) |
| **Version word** | A two-byte signed class version in the stream, saying which layout of a class was written. Not a ROOT version. [§3](../02-serialization/Buffer.md#3-version-words) |
| **Class record** | The encoding that names a class the first time it appears in a buffer: `kNewClassTag`, then the name. [§5.1](../02-serialization/Buffer.md#51-a-new-class) |
| **Class back-reference** / **class tag** | A later mention of the same class, as a map position with `kClassMask` set instead of the name. [§5.2](../02-serialization/Buffer.md#52-a-class-back-reference) |
| **The map** | The per-buffer table from a **map position** to the class or object recorded there. Positions 0 and 1 are reserved, which is why `kMapOffset` is 2. [§6.2](../02-serialization/Buffer.md#62-positions-0-and-1-and-why-kmapoffset-is-2), [§6.3](../02-serialization/Buffer.md#63-the-map-is-per-buffer) |
| **Object slot** | The encoding of a member that is an object or a pointer to one. Four shapes, told apart by the first `u32`. [§6](../02-serialization/Buffer.md#6-object-slots) |
| **Object reference** | An object slot whose first word is a map position: the object was already read earlier in this buffer. [§6.1](../02-serialization/Buffer.md#61-object-references) |
| **Streamer** | The routine that serializes one class. Either generated from a `TStreamerInfo` or hand-written in C++. |
| **Streamer info** | A `TStreamerInfo`: the recorded member list of one version of one class. Files carry their own. [Streamer information §6](../02-serialization/StreamerInfo.md#6-tstreamerinfo) |
| **Element** | One entry of a streamer info's `fElements`: a member or a base class, with its type code, name and declaration comment. [§7](../02-serialization/StreamerInfo.md#7-tstreamerelement) |
| **Type code** | `TStreamerElement::fType`: what kind of thing an element is, and the primary input to how its bytes are laid out. [Element types §1](../02-serialization/ElementTypes.md#1-the-type-codes) |
| **Class version** | The small integer in a class's `ClassDef`, identifying which member layout was written. [Schema evolution §1](../02-serialization/SchemaEvolution.md#1-two-version-numbers-and-only-one-of-them-is-in-the-file) |
| **Checksum** | A 32-bit value identifying a class layout when a version number cannot — for a foreign class, or a class declaring version 0. Eight variants of the algorithm exist. [Streamer information §11](../02-serialization/StreamerInfo.md#11-checksums) |
| **Foreign class** | A class with no `ClassDef`, written with a version word of 0 followed by its checksum. [Schema evolution §2](../02-serialization/SchemaEvolution.md#2-class-version-0-and-foreign-classes) |
| **Emulated class** | A class ROOT has no compiled dictionary for, read entirely through the streamer info in the file. Not a property of the file. [§7](../02-serialization/SchemaEvolution.md#7-emulated-classes) |
| **Rule** | A schema-evolution instruction recorded as text in the `StreamerInfo` record's `listOfRules`. ROOT writes them and currently ignores them. [§6](../02-serialization/SchemaEvolution.md#6-rules-and-the-listofrules-entry) |
| **Bootstrap class** | A class a reader MUST hardcode, because its streamer info does not describe what is actually written, or because the description is made of it. [Bootstrap classes](Bootstrap.md) |
| **Object-wise** | A collection layout: a count, then each element written in full. [Collections §3](../02-serialization/Collections.md#3-object-wise) |
| **Member-wise** | A collection layout: a count, then one column per member of the value class. Selected by `kStreamedMemberWise` in the version word. [§4](../02-serialization/Collections.md#4-member-wise) |
| **Value class** | The type a collection holds. For a `std::map` it is `pair<K,V>`, for which ROOT writes no streamer info at all. [§8](../02-serialization/Collections.md#8-stdmap) |
| **PIDF** | The two-byte index, appended to a referenced `TObject`, of the `TProcessID` record that resolves its references. [References §2](../02-serialization/References.md#2-pidf-and-the-tprocessid-records) |

## `TTree`

| Term | Meaning |
|---|---|
| **Entry** | One row of a tree: the *i*-th value of every branch. [Reading entries §1](../04-ttree/ReadingEntries.md#1-locating-the-entry) |
| **Branch** | One column, or one interior node of the tree of columns. It owns the baskets its data is in. [Branches §1](../04-ttree/TBranch.md#1-where-a-branch-lives) |
| **Leaf** | The description of one value within a branch's entry: its type, its width, and what counts it. A branch may have none. [Leaves §1](../04-ttree/TLeaf.md#1-two-separate-things) |
| **Basket** | The record a run of consecutive entries of one branch is stored in. Its own fields sit inside its key. [TBasket §1](../04-ttree/TBasket.md#1-a-basket-is-a-key-with-extra-fields) |
| **Entry-offset array** | The per-basket array giving where each entry starts, present when entries are not all the same length. [§5](../04-ttree/TBasket.md#5-the-entry-offset-array) |
| **Cluster** | A range of entries whose baskets were flushed together, and the unit to read whole if reading many branches. [The tree record §6](../04-ttree/TTree.md#6-clusters) |
| **Split** | Writing an object as one branch per member rather than one branch per object. [Splitting §1](../04-ttree/Splitting.md#1-the-branch-tree) |
| **Split level** | `fSplitLevel`: a depth budget in its low two digits and a pointer-collection flag above them. Not a depth counter. [§4](../04-ttree/Splitting.md#4-fsplitlevel) |
| **Split node** | An interior branch standing for a split object: `fType` 0 with `fID` −2. It holds no bytes. [Split branches §3.1](../04-ttree/TBranchElement.md#31-fid-has-two-sentinels-and-the-header-documents-only-one) |
| **Count branch** | The `fType` 3 or 4 branch holding a split collection's element count, one `Int_t` per entry. [Reading entries §3.1](../04-ttree/ReadingEntries.md#31-a-count-branch-one-int_t-and-nothing-else) |
| **Counter branch** | The branch holding the `n` of an `Int_t n; T *x; //[n]` member. A different thing from a count branch, and `fMaximum` lives on it. [§3.4](../04-ttree/ReadingEntries.md#34-a-counted-array-a-flag-byte-then-n-values) |
| **Member column** | The entry of an `fType` 31 or 41 branch: *n* values of one member, packed with no framing and no count. [§3.2](../04-ttree/ReadingEntries.md#32-a-member-of-a-split-container-a-bare-packed-column) |
| **Unsplit** | Written as one object per entry, members concatenated, with no framing for the object's own class. [§3.3](../04-ttree/ReadingEntries.md#33-an-unsplit-object-no-framing-of-its-own-but-its-members-have-theirs) |

## RNTuple

RNTuple is not yet specified here; `PLAN.md` phase 6 is the audit of ROOT's own
specification for it, which is the one format ROOT documents properly. Its terms
— envelope, page, page list, cluster group, column, field — are defined in that
document and are deliberately not duplicated or paraphrased here.

The one RNTuple fact this specification does state is that its envelopes and page
payloads are **little-endian** while the `ROOT::RNTuple` anchor, being an ordinary
key payload, is big-endian ([Conventions §3](../00-conventions.md#3-byte-order)).
Note that "cluster" and "column" mean related but not identical things in the two
formats, so the `TTree` definitions above do not carry over.
