# Pitfalls

Facts that are unobvious and have cost somebody time, each stated in a sentence
or two with a link to where it is specified. Most were found by comparing ROOT's
source with real bytes. Thirteen were found by checking this specification
against files it was not written from, and were errors in it before they were
listed here.

Read once before implementing, and again when a decode is wrong by two or four
bytes.

## 1. The container

**A file has two byte orders in it.** Everything in the `TFile` layer is
big-endian; an RNTuple's envelopes and pages are little-endian. A length read
with the wrong byte order is a plausible number rather than an obvious error.
[Conventions §3](../00-conventions.md#3-byte-order)

**"Is this payload compressed" is an inequality, not a difference.** The test is
`fObjlen > fNbytes - fKeylen`. A payload longer than `fObjlen` is stored raw
with slack after it, as RNTuple's own key writer produces. A reader using `!=`
tries to decompress such a payload, finds no valid block header at its start, and
rejects the whole file. (The slack sits after the object data and is never read
as a header.)
[Compression §1.1](../01-container/Compression.md#11-why-the-test-is-an-inequality)

**`fEND` is at most the file size, not equal to it.** ROOT compares the two only
to detect truncation, and a cleanly closed file may have unexplained trailing
bytes. [File header §10](../01-container/FileHeader.md#10-invariants)

**Walking the record chain is optional, and some files cannot be walked.** ROOT
opens a file through the directory and key lists; a hole in the chain stops a
walker but not a reader.
[Records and keys §1](../01-container/Record.md#1-the-record-chain)

**A directory record is not identified by its class name.** A `TFile` subclass,
such as CMS's `TStorageFactoryFile`, is still a directory. Recognise the
structure; a key-list entry names `TDirectory` or `TDirectoryFile`, but the top
directory's own key carries whatever `TFile` subclass wrote the file.
[Directories §6.2](../01-container/Directory.md#62-the-key-list-record-cannot-be-identified-from-its-key)

**`fSeekParent` is not reliably the parent directory.** Before ROOT 6.38 it held
the top directory's offset for every nested directory; from 6.38 it holds the
mother's, and files written before 6.38 are everywhere. Reconstruct the tree from
the keys instead.
[Directories §4.3](../01-container/Directory.md#43-fseekparent-do-not-use-it-for-parentage)

**A key-list entry is not always `fKeylen` bytes long.** Step to the next one by
the bytes you parsed (18 or 26 fixed, then three counted strings), never by adding
`fKeylen`. A directory entry written by ROOT 5.32 or earlier is four bytes longer
than the `fKeylen` it reports, because it names its class `TDirectoryFile` where
the record's own key names it `TDirectory`. A reader that adds `fKeylen` starts
parsing the next entry in the middle of this one, and both spellings occur in one
file.
[Directories §6.5](../01-container/Directory.md#65-an-images-length-is-what-it-parses-to-never-its-fkeylen)

**A string's length comes from the entry, never from the leaf's `fLen`.** `fLen`
on a `TLeafC` is a buffer size, and in a fast-merged file (what `hadd` produces
by default) it can be smaller than the longest string in the same baskets. ROOT
then truncates the value silently; a reader that uses the counted string in the
entry gets it right.
[TLeaf §9.1](../04-ttree/TLeaf.md#91-flen-is-the-readers-buffer-size-and-it-can-be-too-small)

**A basket key written by ROOT 4.02 or later always uses the large-file
layout**, whatever the file's size, because `TBasket` adds 1000 to `fVersion`
unconditionally. One written before 4.02 never does. Take the width from the
key's own `fVersion`, as for any other key.
[TBasket §1](../04-ttree/TBasket.md#1-a-basket-is-a-key-with-extra-fields)

## 2. Framing

**Buffer position 0 is the start of the key, not of the payload.** Every
back-reference is expressed as a buffer position, so a reader that decompresses
into a fresh array and counts from zero gets every one of them wrong by
`fKeylen`. [Buffer framing §1](../02-serialization/Buffer.md#1-what-a-buffer-is)

**A byte count is a lower bound on an object's length, not its length.** Three
classes keep writing after the frame they opened, and nothing warns, because
`CheckByteCount` is satisfied. The one you are likely to meet is `TMatrixTSym`.
[Buffer framing §2.4](../02-serialization/Buffer.md#24-an-object-may-be-longer-than-its-byte-count-says)

**A version word of 0 has two different meanings**, and nothing at that point
in the stream tells them apart: a class that declares version 0, or a foreign
class whose checksum follows. Look it up in the file's own streamer info.
[Buffer framing §4](../02-serialization/Buffer.md#4-a-version-word-of-0-has-two-different-meanings)

**A record's payload does not always begin with a byte count.** `TArray` begins
with a count of elements, `TRef` with a version word, and a `TBasket` with entry
data. On a pre-ROOT-5 file, an ordinary class's payload may also begin without
one.
[Buffer framing §2.3](../02-serialization/Buffer.md#23-a-records-object-data-does-not-always-begin-with-one)

**`kIsReferenced` changes the length of a `TObject` base**, from 10 bytes to 12.
It is a bit in `fBits`, so you have to read `fBits` before you know the length
of the object you are reading. [References §1](../02-serialization/References.md#1-the-extra-word-on-a-referenced-tobject)

**`fUniqueID` is truncated to 24 bits when that bit is set**, so the value you
read is not the value the writer held.
[References §5](../02-serialization/References.md#5-what-funiqueid-means)

## 3. Streamer information

**A recorded streamer info can be wrong.** A class with a hand-written
`Streamer` still has one, and nothing in the file marks it. `TList`'s info lists
two base classes its streamer never writes.
[Streamer-driven reading §7](../02-serialization/StreamerDriven.md#7-when-the-streamer-info-does-not-describe-the-bytes),
[Hand-written streamers](HandWrittenStreamers.md)

**A generated `Streamer` can write nothing of its own.** For class version 0 with
a plain `#pragma link`, ROOT generates a body that calls its bases and returns:
no version word, no byte count, no members.
[Forwarding streamers](ForwardingStreamers.md)

**A `kBase` element is not "read the base by its streamer info".** It dispatches
to the base's own `Streamer` first, so a `TQObject` base occupies zero bytes
while its info is in the file with zero elements.
[Streamer-driven reading §4](../02-serialization/StreamerDriven.md#4-base-classes)

**`fSize` is the writer's `sizeof`, not the on-disk width**, and it differs
between standard libraries for the same class. Derive widths from `fType`.
[Streamer information §7](../02-serialization/StreamerInfo.md#7-tstreamerelement)

**`fType` is not a stable property of a class either.** The same member is
`kULong` (14) on one platform and `kULong64` (17) on another, because ROOT
records the resolved type of a typedef. All of 4, 14, 16 and 17 are eight bytes.
[Element types §2.4](../02-serialization/ElementTypes.md#24-one-member-two-codes-depending-on-the-writers-standard-library)

**`fOffset` is an in-memory offset and means nothing on disk.**
[Streamer information §7](../02-serialization/StreamerInfo.md#7-tstreamerelement)

**A counter may live in a base class.** `fCountName` names the member,
`fCountClass` names where it is, and a counted pointer's length may come from a
class other than the one you are decoding.
[Element types §4](../02-serialization/ElementTypes.md#4-koffsetp-t-40-t-counted-pointer)

**A `TStreamerSTL` element's `fType` is 500, not 300**, in everything ROOT 5 and
later wrote. The code says `kStreamer`, but the layout is an STL collection
anyway. [Streamer information §10](../02-serialization/StreamerInfo.md#10-tstreamerstl-stores-a-type-code-it-does-not-mean)

**The version word inside a 500/501 frame is not the constant 10.** It is
`TStreamerInfo`'s own class version in the writing ROOT: 8 or less before 5.27/02,
9 until 6.35, 10 from 6.36. [Element types §8](../02-serialization/ElementTypes.md#8-kstreamer-500-and-kstreamloop-501)

**The order of infos in the `StreamerInfo` record is not a property of the file.**
It is the order in which the writing process happened to register classes, and
two files with identical content can differ in it.
[Streamer information §3.4](../02-serialization/StreamerInfo.md#34-in-no-guaranteed-order-is-stronger-than-it-sounds)

**Some codes cannot occur in a file at all.** Anything in the `kSkip`, `kConv`,
`kCache` or `kArtificial` ranges is produced by schema evolution in memory.
Implementing them is wasted effort.
[Schema evolution §5](../02-serialization/SchemaEvolution.md#5-codes-that-cannot-appear-in-a-file)

## 4. Values

**A `Bool_t` on disk need not be 0 or 1.** An unassigned member reaches the file
as ROOT's heap fill pattern, `0x99` in every byte. This is deterministic, and it
applies to every type, not only `Bool_t`.
[Element types §2.5](../02-serialization/ElementTypes.md#25-a-value-can-be-0x99-because-nobody-wrote-one)

**`Long_t` and `ULong_t` occupy 8 bytes on disk even where they are 4 in
memory.** [Conventions §4](../00-conventions.md#4-primitive-types)

**There are four string encodings and they are routinely confused**: the counted
string with its 255 escape, `TString` (which is the same encoding but written
with no frame wherever it appears), `TStringLong` with a four-byte count and no
escape, and the NUL-terminated names in class records.
[Conventions §5](../00-conventions.md#5-string-encodings)

**A `std::string` written as a whole object has no frame at all**, and no file
carries a streamer info for `string`.
[Collections §10.1](../02-serialization/Collections.md#101-a-stdstring-object-has-no-frame-either)

**`Double32_t` is not a type, it is an annotation**, and its width on disk is set
by the element's title: 4 bytes for a packed range or a plain `Double32_t`, 3
bytes for a truncated mantissa, and never the 8 the name suggests. An annotation
of `[0,0,15]` is wider on disk than `[0,0,14]`, and two members of the same type
in one class can have different widths.
[Element types §5.2](../02-serialization/ElementTypes.md#52-the-three-encodings)

**A `pair<K,V>`'s checksum does not identify the class.** ROOT can compute it
before the pair's members are known and then caches it forever, so distinct pairs
in one file share a value. A checksum-to-info table decodes them as the wrong
type; resolve the value class by its declared name instead.
[Collections §8.2](../02-serialization/Collections.md#82-the-checksum-does-not-identify-the-pair)

**A collection's value class may have no streamer info anywhere in the file.**
Nobody can read those bytes, ROOT included, and it happens without a warning on
the write side.
[Collections §9](../02-serialization/Collections.md#9-the-value-classs-streamer-info-can-be-missing-entirely)

## 5. `TTree`

**A tree's record need not be of class `TTree`.** `TNtuple`, `TNtupleD` and
`TChain` derive from it; find trees through the base-class chain in the file's
own streamer infos. [The tree record §1](../04-ttree/TTree.md#1-finding-the-trees-in-a-file)

**A branch's last basket is often inside the tree record**, not a record of its
own: a whole `TKey` embedded in object data, which `fBasketSeek` reports as 0.
A reader that misses it loses the tail of the branch.
[TBasket §4.1](../04-ttree/TBasket.md#41-the-embedded-layout)

**A basket with no entry-offset array is not necessarily fixed-length.** A flag
of 80 means the offsets were not written and must be regenerated from the
branch's leaf. Otherwise the two cases look identical.
[TBasket §5.2](../04-ttree/TBasket.md#52-with-kgenerateoffsetmap-the-array-holds-sizes)

**When `fNevBuf` is 0 no offset array is written even though the flag says there
is one**, and a reader that trusts the flag reads the reserved key area as a
count. [TBasket §5](../04-ttree/TBasket.md#5-the-entry-offset-array)

**`fEntries` on a split branch's parent is not the tree's entry count**, and its
`fEntryNumber` stays 0: the parent's fill path is a bare increment.
[Branches §7](../04-ttree/TBranch.md#7-the-entry-counters)

**`fEntries` on the tree may disagree with its branches by design.**
`TTree::SetEntries(-1)` warns about that case rather than refusing.
[The tree record §3](../04-ttree/TTree.md#3-fentries-is-a-counter-not-a-derived-quantity)

**An interior branch of a split tree has no leaves and no baskets.** It is a
node, not data. [Branches §11](../04-ttree/TBranch.md#11-invariants)

**A `TLeafElement`'s `fLen` may be −1**, a documented parse failure that is
normal on a split branch. [Leaves §4.2](../04-ttree/TLeaf.md#42-flen-can-be-1)

**`fType` alone does not select the read procedure.** `fID`, `fSplitLevel` and
`fStreamerType` participate, and two of the eleven conditions are reachable only
through `fSplitLevel >= 100`.
[Split branches §8](../04-ttree/TBranchElement.md#8-the-read-procedure-is-selected-by-four-fields-not-one)

**The header of a member-wise column is written once for the whole column**, not
per value — including the value class's version word.
[Reading entries §5](../04-ttree/ReadingEntries.md#5-what-one-members-bytes-look-like)

**`TBasket` and `TTreeIndex` have no streamer info at all.** This is easier to
handle than a wrong one, which a reader might follow.
[TBasket](../04-ttree/TBasket.md), [Auxiliary §2](../04-ttree/Auxiliary.md#2-ttreeindex-the-one-class-with-no-streamer-info)

**`TBranch` below class version 10 is not streamer-info driven**, and the
is-present byte of `fBasketSeek` also selects the width at version 9.
[Branches §13](../04-ttree/TBranch.md#13-class-versions)

## 6. Three that are ROOT's bugs, not yours

**An empty `TLeafC` string is misread by ROOT itself** when the `TLeafC` is not
its branch's only leaf: the emptiness test compares whole-entry offsets. The file
is fine; ROOT's value is not. [Leaves §9](../04-ttree/TLeaf.md#9-tleafc)

**A `TLeafC` cannot be followed by another leaf in a leaflist.** `fOffset`
doubles as an in-memory offset and a `TLeafC` contributes 1, so `c/C:x/I` reads
`x` from the second byte of the string. This happens silently, at write time as
well as at read time.
[Leaves §3.2](../04-ttree/TLeaf.md#32-foffset-is-a-position-in-the-entry)

**A counted array's counter branch is resolved over the whole tree, so two split
objects of one class share the first object's counter.** `fBranchCount` is set from
a name looked up across every branch (`root/tree/tree/src/TBranchElement.cxx:438`),
and when the sub-branches have no parent prefix both objects' counted members point
at the same counter. In `alice_ESDs.root`, a file ROOT itself published, ROOT
silently reads 0 elements for `PrimaryVertex.fIndices`, whose entries hold 18, 22,
6 and 13. A reader must resolve the counter **among the branch's siblings** instead
of following the recorded `fBranchCount`.
[Reading entries §4.1](../04-ttree/ReadingEntries.md#41-resolve-the-counter-by-name-not-by-fbranchcount)

All three are recorded as bug candidates in `PLAN.md` §7.1, with the byte-level
reproducers, and are not yet reported upstream.
