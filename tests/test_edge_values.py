#!/usr/bin/env python3
"""Gate for the Lesson-10 EDGE-VALUE layer (`draw_graph(..., edge_values=...)`).

WHAT IT CHECKS
  1. The labels are actually drawn, one per requested edge, with the right text.
  2. **BYTE-IDENTITY**: `edge_values=None` renders identically to not passing it.
     That is the whole additivity claim, asserted at the smallest scale.
  3. **The perpendicular is a PAGE perpendicular, not a data perpendicular.**
     RED CASE: the same figure on a deliberately anisotropic axes, where the two
     recipes MUST disagree — so the test proves the distinction is real instead
     of asserting a tautology (F2: a check that would pass either way).
  4. **F7, the unit basis**: the gap is INK. Rendered at dpi 100 and dpi 200 the
     label's pixel offset from its shaft must scale by EXACTLY 2. A frozen
     `dpi/72` anywhere in the path breaks this and nothing else would notice.
  5. The measured clearance CAN GO NEGATIVE — the detector must be able to fail
     (gate rule: blindness blocks; a report that can only say "fine" is not a
     report). RED CASE: a third node parked on an edge's midpoint.
  6. A DIRECTED spec naming `edge_values` RAISES from the key check, naming the
     key — the capability is absent LOUDLY, not silently.

WHAT IT CANNOT SEE
  It renders on the LAPTOP, in Helvetica, with construct dpi == draw dpi. It
  says nothing about the container (see docs/stubs/container-vs-local-regime).
  Check 4 is the closest thing here to container evidence: it varies the dpi
  RATIO, which is the axis the container actually differs on.

    python3.12 tests/test_edge_values.py
"""
import io
import hashlib
import math
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import networkx as nx                    # noqa: E402
from fractions import Fraction           # noqa: E402

from cs470_engine.plot_style import (     # noqa: E402
    GRAPH_STYLE, draw_graph, draw_edge_value_labels, _point_segment_distance,
)
from cs470_engine import problems as P    # noqa: E402

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


PATH_POS = {"A": (0.0, 0.0), "B": (2.0, 0.0), "C": (1.0, 1.4)}
PATH_EDGES = [("A", "B"), ("B", "C")]


def _graph(edges=PATH_EDGES, nodes=None):
    G = nx.Graph()
    G.add_nodes_from(nodes or sorted({n for e in edges for n in e}))
    G.add_edges_from(edges)
    return G


def _labels(ax):
    return [t for t in ax.texts if t.get_gid() == "cs470:edgeval"]


# ---------------------------------------------------------------------------
# 1 — drawn, counted, formatted
# ---------------------------------------------------------------------------
def test_draws_and_formats():
    G = _graph()
    fig, ax = plt.subplots(figsize=(6, 3.8))
    draw_graph(G, ax, pos=PATH_POS, node_size=600,
               edge_values={("A", "B"): Fraction(3, 2), ("B", "C"): 12})
    texts = sorted(t.get_text() for t in _labels(ax))
    plt.close(fig)
    check("labels drawn, one per edge", len(texts) == 2, f"got {texts}")
    check("Fraction renders as plain 3/2 (no mathtext)", texts == ["12", "3/2"],
          f"got {texts}")


# ---------------------------------------------------------------------------
# 2 — BYTE-IDENTITY: None is not a feature
# ---------------------------------------------------------------------------
def test_none_is_byte_identical():
    G = _graph()

    def sha(**kw):
        fig, ax = plt.subplots(figsize=(6, 3.8))
        draw_graph(G, ax, pos=PATH_POS, node_size=600, **kw)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        plt.close(fig)
        return hashlib.sha256(buf.getvalue()).hexdigest()

    absent, none_, empty = sha(), sha(edge_values=None), sha(edge_values={})
    check("edge_values=None == not passed at all", absent == none_)
    check("edge_values={} == not passed at all", absent == empty)
    check("a non-empty edge_values DOES move the bytes (the check can fail)",
          sha(edge_values={("A", "B"): 1}) != absent)


# ---------------------------------------------------------------------------
# 3 — the perpendicular is a PAGE perpendicular  (RED CASE included)
# ---------------------------------------------------------------------------
def _label_offset_px(fig, ax, txt, u, v, pos):
    """Distance in PIXELS from the label's ANCHOR to its own edge segment.

    ⚠ Measured off ``get_window_extent`` and therefore only exact for a
    HORIZONTAL edge, where ``rotation`` is 0 and the bbox's bottom-centre IS the
    ``ha="center", va="bottom"`` anchor. On a tilted edge the bbox is the rotated
    glyphs' AXIS-ALIGNED hull and its bottom-centre is NOT the anchor — that
    mismatch cost this test two false reds on its first run. Tilted geometry is
    checked against the offset VECTOR instead (see below), which is exact at any
    angle.
    """
    fig.canvas.draw()
    bb = txt.get_window_extent(fig.canvas.get_renderer())
    anchor = (bb.x0 + bb.width / 2.0, bb.y0)
    a = ax.transData.transform(pos[u])
    b = ax.transData.transform(pos[v])
    return _point_segment_distance(anchor, tuple(a), tuple(b))


def test_perpendicular_is_display_space():
    """On a WIDE axes the data-space and display-space perpendiculars differ.

    RED CASE. The 9.2 precedent (``render_copying_step``) takes the perpendicular
    of the DATA chord — right there ONLY because ``draw_directed_graph`` forces
    aspect 1.0. ``draw_graph`` does not. We assert on the annotation's own offset
    VECTOR (points, exact at any rotation): it is perpendicular to the DISPLAY
    chord, and it is NOT parallel to the display image of the DATA perpendicular
    — so the distinction is measured, not assumed (F2: a check that would pass
    either way checks nothing).
    """
    G = _graph([("A", "B")], nodes=["A", "B"])
    pos = {"A": (0.0, 0.0), "B": (1.0, 1.0)}          # 45 deg in DATA space
    fig, ax = plt.subplots(figsize=(8.0, 2.0))        # 4:1 canvas => anisotropic
    draw_graph(G, ax, pos=pos, node_size=600, edge_values={("A", "B"): 7})
    txt = _labels(ax)[0]
    off = tuple(txt.xyann)                            # the offset, in POINTS

    a = ax.transData.transform(pos["A"])
    b = ax.transData.transform(pos["B"])
    chord = (b[0] - a[0], b[1] - a[1])                # the chord ON THE PAGE
    ox, oy = ax.transData.transform((0.0, 0.0))
    x1, _ = ax.transData.transform((1.0, 0.0))
    _, y1 = ax.transData.transform((0.0, 1.0))
    sx, sy = abs(x1 - ox), abs(y1 - oy)
    data_perp_on_page = (-1.0 * sx, 1.0 * sy)         # data (-dy, dx), transformed
    plt.close(fig)

    def cos_between(p, q):
        return abs(p[0] * q[0] + p[1] * q[1]) / (math.hypot(*p) * math.hypot(*q))

    gap = GRAPH_STYLE["edge_value_gap"]
    check("the offset magnitude is exactly the configured points gap",
          abs(math.hypot(*off) - gap) < 1e-9,
          f"|offset| = {math.hypot(*off):.6f} pt, gap = {gap}")
    check("the offset is PERPENDICULAR to the display chord",
          cos_between(off, chord) < 1e-6,
          f"cos = {cos_between(off, chord):.2e}, axes anisotropy sx/sy = {sx/sy:.2f}")
    check("RED CASE: the DATA-space perpendicular is NOT that direction "
          "(so the distinction is real)",
          cos_between(off, data_perp_on_page) < 0.98,
          f"cos(offset, data-perp-on-page) = "
          f"{cos_between(off, data_perp_on_page):.4f}")


# ---------------------------------------------------------------------------
# 4 — F7: the gap is INK, so it scales EXACTLY with dpi
# ---------------------------------------------------------------------------
def test_gap_is_ink_not_data():
    """F7. A HORIZONTAL edge, so ``rotation`` is 0 and the bbox bottom-centre IS
    the anchor — the one geometry where the rendered measurement is exact.

    The structural half matters as much as the rendered half: the sixth F7
    instance was a function that OBEYED the points rule and still shipped
    pixels, because it froze ``fig.dpi/72`` into an ``Affine2D``. So we assert
    the offset is handed to matplotlib as ``offset points`` — i.e. the live dpi
    is applied by the framework, never snapshotted by us — AND that the drawn
    result really does double.
    """
    G = _graph([("A", "B")], nodes=["A", "B"])
    pos = {"A": (0.0, 0.0), "B": (2.0, 0.0)}          # horizontal
    seen = {}
    for dpi in (100, 200):
        fig, ax = plt.subplots(figsize=(6, 3.8), dpi=dpi)
        draw_graph(G, ax, pos=pos, node_size=600, edge_values={("A", "B"): 5})
        txt = _labels(ax)[0]
        seen[dpi] = _label_offset_px(fig, ax, txt, "A", "B", pos)
        coords = txt.anncoords
        plt.close(fig)
    ratio = seen[200] / seen[100] if seen[100] else 0.0
    check("the offset is declared in 'offset points' — dpi applied LIVE, "
          "never snapshotted", coords == "offset points", f"got {coords!r}")
    check("label gap scales EXACTLY 2x from dpi 100 -> 200 (no frozen dpi/72)",
          abs(ratio - 2.0) < 0.005,
          f"{seen[100]:.2f}px -> {seen[200]:.2f}px, ratio {ratio:.4f}")


# ---------------------------------------------------------------------------
# 5 — the clearance report CAN GO NEGATIVE  (RED CASE)
# ---------------------------------------------------------------------------
def test_clearance_can_fail():
    # GREEN: an open layout.
    G = _graph()
    fig, ax = plt.subplots(figsize=(6, 3.8))
    rep = draw_graph_report(G, ax, PATH_POS, {("A", "B"): 1})
    plt.close(fig)
    good = min(v["clearance_points"] for v in rep.values())

    # RED: park a third node exactly on the A-B midpoint. The label anchor now
    # sits inside that node's circle and the clearance must go NEGATIVE.
    G2 = _graph([("A", "B"), ("C", "A")], nodes=["A", "B", "C"])
    bad_pos = {"A": (0.0, 0.0), "B": (2.0, 0.0), "C": (1.0, 0.0)}
    fig, ax = plt.subplots(figsize=(6, 3.8))
    rep2 = draw_graph_report(G2, ax, bad_pos, {("A", "B"): 1})
    plt.close(fig)
    bad = rep2[("A", "B")]["clearance_points"]

    check("clean layout reports POSITIVE clearance", good > 0, f"{good:.2f} pt")
    check("RED CASE: a node on the midpoint reports NEGATIVE clearance",
          bad < 0, f"{bad:.2f} pt")


def draw_graph_report(G, ax, pos, edge_values):
    """draw_graph, then re-run the helper to capture its measurement."""
    draw_graph(G, ax, pos=pos, node_size=600)
    return draw_edge_value_labels(G, pos, ax, edge_values, node_size=600)


# ---------------------------------------------------------------------------
# 6 — absent LOUDLY on the directed branch
# ---------------------------------------------------------------------------
def test_directed_raises():
    spec = {"kind": "graph", "directed": True, "nodes": ["a", "b"],
            "edges": [["a", "b"]], "edge_values": [["a", "b", 1]]}
    fig, ax = plt.subplots()
    try:
        P._draw_graph_into(ax, spec)
        ok, msg = False, "no raise"
    except ValueError as exc:
        ok, msg = "edge_values" in str(exc), str(exc)[:70]
    plt.close(fig)
    check("directed + edge_values RAISES and names the key", ok, msg)

    # and the UNDIRECTED spec goes all the way through the real dispatch
    spec2 = dict(spec)
    spec2.pop("directed")
    spec2["edge_values"] = [["a", "b", Fraction(1, 2)]]
    fig, ax = plt.subplots()
    P._draw_graph_into(ax, spec2)
    got = [t.get_text() for t in _labels(ax)]
    plt.close(fig)
    check("undirected spec renders edge_values through the YAML dispatch",
          got == ["1/2"], f"got {got}")

    # a malformed triple must raise, not silently drop
    spec3 = dict(spec2, edge_values=[["a", "b"]])
    fig, ax = plt.subplots()
    try:
        P._draw_graph_into(ax, spec3)
        ok3 = False
    except ValueError:
        ok3 = True
    plt.close(fig)
    check("a non-triple edge_values entry RAISES", ok3)


def main():
    print("test_edge_values.py — the Lesson-10 edge-value layer")
    for fn in (test_draws_and_formats, test_none_is_byte_identical,
               test_perpendicular_is_display_space, test_gap_is_ink_not_data,
               test_clearance_can_fail, test_directed_raises):
        print(f"\n{fn.__name__}:")
        fn()
    print(f"\n{'ALL PASS' if not FAILURES else 'FAILURES: ' + ', '.join(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
