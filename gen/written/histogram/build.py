"""A TH1F and a TH1D written by this project, from spec/06-writing/WritingHistograms.md.

The two histograms are deliberately the **same two** that ROOT wrote in
`data/classes/histogram.root`, down to the values, so that the two files' data
records can be compared byte for byte. `tools/test_write.py` asserts that
comparison: 596 bytes and 651 bytes, identical.

The statistics are supplied rather than derived. `tools/rootwrite.py` can compute
them from the bin contents, and for `h1` -- unit weights, fills at bin centres --
that gives ROOT's own values; for `h2` it cannot, because `fEntries` counts fills
and the x moments remember where inside a bin each fill landed.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402


def build() -> bytes:
    f = rw.FileWriter("data/written/histogram.root",
                      "written by tools/rootwrite.py")

    # Five fills, two of them out of range: fEntries 5, fTsumw 3.
    axis = rw.Axis(nbins=3, xmin=0.0, xmax=3.0)
    cells = [1.0, 2.0, 1.0, 0.0, 1.0]
    sumw2 = [1.0, 2.0, 1.0, 0.0, 1.0]
    f.add_hist(rw.Hist1D("h1", "three bins", axis, cells,
                         rw.stats_from_cells(cells, axis, sumw2),
                         sumw2=sumw2, kind="F"))

    # Variable bin edges and weighted fills, at 0.5 with weight 2 and at 5.0
    # with weight 0.5.
    edges = [0.0, 1.0, 4.0, 10.0]
    axis2 = rw.Axis(nbins=3, xmin=0.0, xmax=10.0, edges=edges)
    cells2 = [0.0, 2.0, 0.0, 0.5, 0.0]
    sumw2_2 = [0.0, 4.0, 0.0, 0.25, 0.0]
    stats2 = rw.Stats(entries=2.0, tsumw=2.5, tsumw2=4.25,
                      tsumwx=3.5, tsumwx2=13.0)
    f.add_hist(rw.Hist1D("h2", "variable bins", axis2, cells2, stats2,
                         sumw2=sumw2_2, kind="D"))

    for info in rw.histogram_infos(("F", "D")):
        f.add_info(info)
    return f.to_bytes()
