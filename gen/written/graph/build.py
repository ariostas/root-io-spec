"""Graphs written by this project, from `spec/06-writing/WritingGraphs.md`.

Three objects. The first two hold exactly what `data/classes/graph.root` holds
under the same names, and **both records are byte-identical to ROOT's** -- which
is what pins `fBits`, the three attribute bases and the empty `fFunctions` list,
none of which a writer would guess right. A record comparison needs only the
same class name, key name and title, because a graph stores no offsets: the class
map is measured from the start of the record, so an equal key length is enough.

The third is the object ROOT cannot write: a graph with an explicit y range and
`fHistogram` still **null**. `TGraph::SetMinimum` goes through `GetHistogram()`
and materialises a whole `TH1F` inside the record, six times the size; the
members are independent of it on disk, and `verify.C` shows ROOT reading the
range back from a graph that has no histogram at all.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import rootwrite as rw  # noqa: E402

X = [0.0, 1.0, 2.0, 3.0]
Y = [0.5, 2.5, -1.0, 4.0]
EX = [0.1, 0.1, 0.2, 0.2]
EY = [0.25, 0.5, 0.25, 0.5]


def build() -> bytes:
    f = rw.FileWriter("data/written/graph.root", "graphs")

    f.add_graph(rw.Graph("g", "four points", X, Y))
    f.add_graph(rw.Graph("gr", "with errors", X, Y, ex=EX, ey=EY))
    f.add_graph(rw.Graph("gy", "a fixed Y range", X, Y,
                         minimum=-2.0, maximum=5.0))

    for info in rw.graph_infos(("TGraph", "TGraphErrors")):
        f.add_info(info)
    return f.to_bytes()
