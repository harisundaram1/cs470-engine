#!/usr/bin/env python3
"""node-6 fix (v0.11.1): the opt-in per-axis anisotropic node-framing pad.

CAUSE (measured, F4(e) re-derived — NOT the docket's refuted "limits fit node
CENTERS"): under ``aspect='auto'`` a scatter marker's data HALF-HEIGHT exceeds
the isotropic radius matplotlib's autoscale budgets, so top/bottom nodes are left
a knife-edge of vertical clearance that tips into a clip under vertical
compression or the container's retina/DejaVu metrics.

The value test is the piece's own: EVERY node circle is fully inside the axes,
across sampled layouts and the compressed L8 figsizes — AND the fix is byte-safe
by default (opt-in), so the deployed corpus does not move.

Run: ``python3 tests/test_node_framing.py`` (plain asserts) or via pytest.
"""
import hashlib
import io
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt        # noqa: E402
import networkx as nx                  # noqa: E402

import cs470_engine.random_graphs as rg              # noqa: E402
import cs470_engine.plot_style as ps                 # noqa: E402
from cs470_engine.plot_style import apply_default_style, GRAPH_STYLE  # noqa: E402

apply_default_style()
NS = GRAPH_STYLE["node_size"]


def _min_clearance_px(pos, ax, node_size):
    """Min over nodes of (node-circle edge -> nearest axes-frame edge) in px.
    Negative == the circle overflows the frame (a clip)."""
    fig = ax.figure
    fig.canvas.draw()
    r_px = math.sqrt(node_size / math.pi) * fig.dpi / 72.0
    bb = ax.get_window_extent()
    worst = None
    for cx, cy in pos.values():
        px, py = ax.transData.transform((cx, cy))
        cl = min(px - bb.x0 - r_px, bb.x1 - px - r_px,
                 py - bb.y0 - r_px, bb.y1 - py - r_px)
        worst = cl if worst is None else min(worst, cl)
    return worst


def _render(figsize, frame_nodes, seed=3):
    G = rg.sample_gnp(8, 0.25, seed)      # concept_one_generator's 8-node graph
    pos = nx.circular_layout(G)           # ...on the unit circle (node 6 at bottom)
    fig, ax = plt.subplots(figsize=figsize)
    ps.draw_graph(G, ax, pos=pos, node_size=NS, frame_nodes=frame_nodes)
    plt.tight_layout()
    return G, pos, fig, ax


def test_frame_nodes_clears_every_circle_across_L8_layouts():
    """VALUE: with the pad on, every node circle is fully inside the axes — across
    several sampled 8-node layouts AND the L8 figsizes, including compressed ones
    the diagnostic showed clipping (6x2.5 / 7x2.2 / 8x2.0)."""
    figsizes = [(6, 3.8), (6.2, 3.8), (5, 4), (6, 2.5), (7, 2.2), (8, 2.0)]
    for seed in (0, 3, 7, 11):
        for fs in figsizes:
            _, pos, fig, ax = _render(fs, frame_nodes=True, seed=seed)
            cl = _min_clearance_px(pos, ax, NS)
            plt.close(fig)
            assert cl > 0.0, f"node clipped despite frame_nodes at {fs} seed {seed}: {cl:.1f}px"
    # And at the flagship concept figsize it reaches the robust ~27px target
    # (measured 34px), not the fragile ~6px matplotlib leaves.
    _, pos, fig, ax = _render((6, 3.8), frame_nodes=True)
    cl = _min_clearance_px(pos, ax, NS)
    plt.close(fig)
    assert cl > 25.0, f"frame_nodes clearance below the ~27px target: {cl:.1f}px"


def test_frame_nodes_is_the_fix_for_the_compression_clip():
    """RED/GREEN: at a compressed figsize the UNFRAMED figure clips (min < 0,
    matching the diagnostic's -2.5 .. -5.8px); the framed one clears robustly."""
    for fs in [(8, 2.0), (7, 2.2)]:
        _, pos, fig, ax = _render(fs, frame_nodes=False)
        bad = _min_clearance_px(pos, ax, NS)
        plt.close(fig)
        _, pos, fig, ax = _render(fs, frame_nodes=True)
        good = _min_clearance_px(pos, ax, NS)
        plt.close(fig)
        assert bad < 0.0, f"expected a clip at {fs} without the fix, got {bad:.1f}px"
        assert good > 8.0, f"fix did not clear the clip at {fs}: {good:.1f}px"


def test_frame_nodes_default_off_is_byte_identical():
    """The pad is OPT-IN: default off renders byte-for-byte as the pre-0.11.1
    renderer, so the deployed L1-L7 corpus (which never sets it) cannot move."""
    def png(kw):
        G = rg.sample_gnp(8, 0.25, 3)
        pos = nx.circular_layout(G)
        fig, ax = plt.subplots(figsize=(6, 3.8))
        ps.draw_graph(G, ax, pos=pos, node_size=NS, **kw)
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        plt.close(fig)
        return hashlib.sha256(buf.getvalue()).hexdigest()

    assert png({}) == png({"frame_nodes": False})


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
