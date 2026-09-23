"""A TH2F, a TH2D and two TProfiles, from spec/06-writing/WritingHistograms.md.

The four objects are the same four ROOT wrote in
`data/classes/th2-profile.root`, down to the values, so that all four data
records can be compared byte for byte; `tools/test_write.py` asserts it.

The statistics are derived here, unlike in `written/histogram`. One value in
two of the four cannot be:

* `fEntries` counts fills, and neither a `TH2`'s cells nor a profile's
  `fBinEntries` remembers how many fills made up a weighted total. `h2d` and
  `p2` are filled with weights, so both supply it and the other seven or six
  sums come out of the arrays exactly.
* the x moments need bin centres in general (`WritingHistograms.md` 5). Every
  fill in this file happens to sit at one, so `fTsumwx` and `fTsumwx2` are
  right too. For the two profiles every sum is, because a profile stores
  sum(w*y) and sum(w*y*y) per cell rather than discarding them (7.2).
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402


def cells(nx: int, ny: int, filled) -> list:
    """`(nx + 2) * (ny + 2)` cells, from a {(binx, biny): value} mapping."""
    out = [0.0] * ((nx + 2) * (ny + 2))
    for (binx, biny), value in filled.items():
        out[rw.cell_index(binx, biny, nx)] = value
    return out


def build() -> bytes:
    f = rw.FileWriter("data/written/th2-profile.root", "TH2 and TProfile")

    # A TH2F, unit weights, with a fill outside the range in x and another
    # outside it in y: six fills, four of them in the statistics.
    xaxis = rw.Axis(nbins=3, xmin=0.0, xmax=3.0)
    yaxis = rw.Axis(name="yaxis", nbins=2, xmin=0.0, xmax=2.0)
    filled = {(1, 1): 2.0, (3, 1): 1.0, (2, 2): 1.0, (0, 1): 1.0, (1, 3): 1.0}
    c = cells(3, 2, filled)
    f.add_hist(rw.Hist2D("h2f", "three by two", xaxis, c,
                         rw.stats_from_cells_2d(c, xaxis, yaxis, c),
                         yaxis=yaxis, sumw2=c, kind="F"))

    # A TH2D with variable edges on both axes and weighted fills, so fSumw2 is
    # not the cell contents and fEntries is not their sum.
    xaxis2 = rw.Axis(nbins=2, xmin=0.0, xmax=4.0, edges=[0.0, 1.0, 4.0])
    yaxis2 = rw.Axis(name="yaxis", nbins=2, xmin=0.0, xmax=10.0,
                     edges=[0.0, 2.0, 10.0])
    c2 = cells(2, 2, {(1, 1): 2.0, (2, 2): 0.5})
    sumw2 = cells(2, 2, {(1, 1): 4.0, (2, 2): 0.25})
    stats2 = rw.stats_from_cells_2d(c2, xaxis2, yaxis2, sumw2)
    stats2.entries = 2.0        # two fills; the derived value sums weight
    f.add_hist(rw.Hist2D("h2d", "variable both ways", xaxis2, c2, stats2,
                         yaxis=yaxis2, sumw2=sumw2, kind="D"))

    # A TProfile with unit weights: fBinSumw2 stays empty while fSumw2, which
    # holds sum(w*y*y), does not. Every statistic is derivable.
    paxis = rw.Axis(nbins=3, xmin=0.0, xmax=3.0)
    sumwy = [7.0, 4.0, 2.0, 0.0, 0.0]
    sumwy2 = [49.0, 10.0, 4.0, 0.0, 0.0]
    entries = [1.0, 2.0, 1.0, 0.0, 0.0]
    f.add_hist(rw.Profile("p1", "unit weights", paxis, sumwy,
                          rw.stats_from_profile(sumwy, sumwy2, entries, paxis),
                          sumw2=sumwy2, bin_entries=entries))

    # A TProfile with a Y range, fErrorMode kERRORSPREAD, and weighted fills,
    # so fBinSumw2 is populated. Three fills reached it; a fourth was outside
    # fYmin..fYmax and changed nothing at all, fEntries included.
    paxis2 = rw.Axis(nbins=2, xmin=0.0, xmax=2.0)
    sumwy_2 = [0.0, 9.0, 2.0, 0.0]
    sumwy2_2 = [0.0, 30.0, 8.0, 0.0]
    entries2 = [0.0, 3.5, 0.5, 0.0]
    bin_sumw2 = [0.0, 9.25, 0.25, 0.0]
    stats_p2 = rw.stats_from_profile(sumwy_2, sumwy2_2, entries2, paxis2,
                                     bin_sumw2=bin_sumw2)
    stats_p2.entries = 3.0
    f.add_hist(rw.Profile("p2", "a Y range", paxis2, sumwy_2, stats_p2,
                          sumw2=sumwy2_2, bin_entries=entries2,
                          bin_sumw2=bin_sumw2, error_mode=1, ymax=10.0))

    for info in rw.histogram_infos(("TH2F", "TH2D", "TProfile")):
        f.add_info(info)
    return f.to_bytes()
