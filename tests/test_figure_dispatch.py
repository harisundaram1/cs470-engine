#!/usr/bin/env python3
"""Tests for the figure dispatch + directed-graph renderer parity (engine 0.8.0).

Standalone-runnable (``python3 tests/test_figure_dispatch.py``).

The centre of gravity here is the UNKNOWN-KEY GUARD. Through 0.7.0 the directed
branch forwarded only ``pos`` and ``labels``: an author who wrote
``highlight_nodes`` on a directed graph got no highlight AND NO ERROR. Silence is
the bug. So most of what follows asserts that things RAISE.
"""
import sys
import traceback

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt        # noqa: E402
import networkx as nx                  # noqa: E402

import cs470_engine.problems as problems             # noqa: E402
from cs470_engine.plot_style import (                # noqa: E402
    BOWTIE_COLORS, draw_directed_graph, draw_graph, draw_matrix,
    _reciprocal_rad, _row_formatter,
)

_FAILS = []
_RENDERED = []
problems.display = lambda fig: (_RENDERED.append(fig), plt.close(fig))


class FakeWS:
    shared_figures = {}


def check(label, got, want):
    if got != want:
        _FAILS.append(f"{label}\n     got:  {got}\n     want: {want}")


def check_true(label, cond):
    if not cond:
        _FAILS.append(f"{label}\n     expected True")


def raises(label, fn, contains=None):
    try:
        fn()
    except Exception as e:
        if contains and contains not in str(e):
            _FAILS.append(f"{label}\n     raised, but message lacked {contains!r}:"
                          f"\n     {e}")
        return
    _FAILS.append(f"{label}\n     NOTHING RAISED — the key was silently dropped")


def render(spec):
    _RENDERED.clear()
    problems._render_figure(FakeWS(), spec)
    return _RENDERED


DIGRAPH = {"kind": "graph", "directed": True,
           "nodes": [{"id": "A", "pos": [0, 1]}, {"id": "B", "pos": [1, 1]},
                     {"id": "C", "pos": [0.5, 0]}],
           "edges": [["A", "B"], ["B", "C"], ["C", "A"]]}
UNDIRECTED = {"kind": "graph",
              "nodes": [{"id": "A", "pos": [0, 0]}, {"id": "B", "pos": [1, 0]}],
              "edges": [["A", "B"]]}


# --- THE GUARD: an unknown key must RAISE, never evaporate --------------------

def test_typo_on_a_directed_graph_raises():
    raises("'highlight_node' (singular typo) on a directed graph",
           lambda: render({**DIGRAPH, "highlight_node": ["A"]}),
           contains="unknown key")


def test_typo_on_an_undirected_graph_raises():
    raises("'highlight_node' on an undirected graph",
           lambda: render({**UNDIRECTED, "highlight_node": ["A"]}),
           contains="unknown key")


def test_bargaining_key_on_a_directed_graph_raises():
    """An 'outside option' is a bargaining concept with no meaning on a directed
    web graph. Silently dropping it is what 0.7.0 did."""
    raises("'outside_options' on a directed graph",
           lambda: render({**DIGRAPH, "outside_options": {"A": "1/2"}}),
           contains="outside_options")
    raises("'matching' on a directed graph",
           lambda: render({**DIGRAPH, "matching": [["A", "B"]]}),
           contains="matching")


def test_directed_only_key_on_an_undirected_graph_raises():
    raises("'curved_reciprocal' on an undirected graph",
           lambda: render({**UNDIRECTED, "curved_reciprocal": True}),
           contains="curved_reciprocal")
    raises("'node_values_below' on an undirected graph",
           lambda: render({**UNDIRECTED, "node_values_below": {"A": 1}}),
           contains="node_values_below")


def test_unknown_kind_raises():
    raises("an unknown figure kind",
           lambda: render({"kind": "scatter_of_doom"}),
           contains="unknown figure kind")


def test_dangling_ref_raises():
    raises("a ref that resolves to nothing",
           lambda: render({"ref": "no_such_figure"}),
           contains="resolves to nothing")


def test_unknown_compute_raises():
    raises("an unknown node_values compute",
           lambda: render({**DIGRAPH,
                           "node_values": {"compute": "eigencentrality"}}),
           contains="unknown compute")
    raises("an unknown node_groups compute",
           lambda: render({**DIGRAPH, "node_groups": {"compute": "cliques"}}),
           contains="unknown compute")
    raises("an unknown matrix compute",
           lambda: render({"kind": "matrix", **{k: DIGRAPH[k]
                                                for k in ("nodes", "edges")},
                           "compute": "laplacian"}),
           contains="unknown compute")


def test_directed_false_on_a_link_analysis_kind_raises():
    """Link analysis is defined on a digraph. Overriding `directed: false` to true
    silently would be the exact bug the guard exists to kill."""
    raises("'directed: false' on an iteration_table",
           lambda: render({"kind": "iteration_table", "directed": False,
                           "nodes": ["A", "B"], "edges": [["A", "B"]],
                           "compute": "pagerank"}),
           contains="cannot be honored")


def test_requesting_a_limit_that_does_not_exist_raises():
    """Asking a figure to draw the limiting PageRank of a graph that OSCILLATES has
    no honest answer. It must not draw one anyway."""
    osc = {"kind": "graph", "directed": True,
           "nodes": [{"id": "A", "pos": [0, 0]}, {"id": "B", "pos": [1, 0]},
                     {"id": "C", "pos": [0.5, 1]}],
           "edges": [["A", "B"], ["B", "A"], ["C", "A"]]}
    raises("the limit of a non-converging graph",
           lambda: render({**osc, "node_values": {"compute": "pagerank",
                                                  "rule": "basic", "limit": True}}),
           contains="does not converge")


def test_every_live_key_still_renders():
    """The guard must not red the deployed corpus. Each key below is in live use."""
    check_true("undirected + L5 bargaining layer",
               bool(render({**UNDIRECTED, "matching": [["A", "B"]],
                            "node_values": {"A": "1/2", "B": "1/2"},
                            "outside_options": {"A": 0, "B": 0}})))
    check_true("directed + the full 0.8.0 annotation layer",
               bool(render({**DIGRAPH, "highlight_nodes": ["A"],
                            "highlight_edges": [["A", "B"]],
                            "node_values": {"compute": "pagerank", "step": 1},
                            "node_values_below": {"compute": "hits_hub", "step": 1},
                            "value_caption": "above: PageRank",
                            "below_caption": "below: hub",
                            "node_groups": {"compute": "bowtie"},
                            "value_format": "decimal",
                            "layout": "circular", "node_size": 700})))


# --- PARITY: the directed renderer now takes what draw_graph takes -------------

def test_directed_graph_accepts_the_full_annotation_set():
    G = nx.DiGraph([("A", "B"), ("B", "C"), ("C", "A")])
    pos = {"A": (0, 1), "B": (1, 1), "C": (0.5, 0)}
    fig, ax = plt.subplots()
    out = draw_directed_graph(
        G, ax, pos=pos,
        highlight_nodes=["A"], highlight_edges=[("A", "B")],
        node_values={"A": 1, "B": 2, "C": 3},
        node_values_below={"A": 4, "B": 5, "C": 6},
        value_caption="above: x", below_caption="below: y",
        node_groups={"A": "IN", "B": "SCC", "C": "OUT"},
        show_labels=True, node_size=700,
    )
    check("returns the pos dict, like draw_graph", out, pos)
    texts = [t.get_text() for t in ax.texts]
    for want in ("1", "2", "3", "4", "5", "6"):
        check_true(f"node value {want!r} was drawn", want in texts)
    check_true("the row caption decodes both rows",
               any("above: x" in t and "below: y" in t for t in texts))
    plt.close(fig)


def test_the_row_caption_names_only_the_populated_row():
    """A caption over an empty row is a lie. If only one row is supplied, only that
    row is named."""
    G = nx.DiGraph([("A", "B")])
    pos = {"A": (0, 0), "B": (1, 0)}
    fig, ax = plt.subplots()
    draw_directed_graph(G, ax, pos=pos, node_values={"A": 1, "B": 2},
                        value_caption="above: score", below_caption="below: hub")
    caps = [t.get_text() for t in ax.texts if "above" in t.get_text()
            or "below" in t.get_text()]
    check_true("names the populated row", any("above: score" in c for c in caps))
    check_true("does NOT name the empty row",
               not any("below: hub" in c for c in caps))
    plt.close(fig)


def test_undirected_graph_gained_groups_too():
    """Parity runs both ways: categorical grouping is on draw_graph as well."""
    G = nx.Graph([("A", "B")])
    fig, ax = plt.subplots()
    draw_graph(G, ax, pos={"A": (0, 0), "B": (1, 0)},
               node_groups={"A": "IN", "B": "OUT"})
    check_true("a decoding legend is emitted", ax.get_legend() is not None)
    plt.close(fig)


def test_group_legend_decodes_the_colors():
    G = nx.DiGraph([("A", "B")])
    fig, ax = plt.subplots()
    draw_directed_graph(G, ax, pos={"A": (0, 0), "B": (1, 0)},
                        node_groups={"A": "IN", "B": "OUT"})
    leg = ax.get_legend()
    check_true("legend exists", leg is not None)
    check("legend names the roles",
          sorted(t.get_text() for t in leg.get_texts()), ["IN", "OUT"])
    plt.close(fig)


def test_bowtie_roles_have_semantic_colors():
    check_true("the SCC core takes the accent",
               BOWTIE_COLORS["SCC"] == "#CE5E11")
    check_true("all six roles are colored", len(BOWTIE_COLORS) == 6)


# --- R6: reciprocal-edge arcs -------------------------------------------------

def test_only_reciprocal_edges_curve():
    """A 2-cycle drawn straight superimposes two arrows on one segment. Every other
    edge must stay DEAD straight — that is what keeps pre-0.8.0 figures identical."""
    G = nx.DiGraph([("A", "B"), ("B", "A"), ("B", "C")])
    check_true("A->B bows one way", _reciprocal_rad(G, "A", "B") > 0)
    check_true("B->A bows the other", _reciprocal_rad(G, "B", "A") < 0)
    check("the two halves are opposite",
          _reciprocal_rad(G, "A", "B"), -_reciprocal_rad(G, "B", "A"))
    check("a one-way edge stays straight", _reciprocal_rad(G, "B", "C"), 0.0)


def test_reciprocal_curvature_does_not_depend_on_edge_order():
    """Keyed to a stable endpoint comparison, not to iteration order — otherwise the
    same figure could bow differently on different runs."""
    G1 = nx.DiGraph([("A", "B"), ("B", "A")])
    G2 = nx.DiGraph([("B", "A"), ("A", "B")])
    check("same curvature regardless of insertion order",
          _reciprocal_rad(G1, "A", "B"), _reciprocal_rad(G2, "A", "B"))


# --- the value formatter ------------------------------------------------------

def test_fractions_stay_fractions_while_they_are_legible():
    """Every denominator E&K prints must survive as an exact fraction — they ARE
    the chapter's numbers, and the worksheets ask students to produce them."""
    from fractions import Fraction as F
    chapter = [F(1, 2), F(5, 16), F(4, 13), F(3, 7), F(9, 11), F(1, 32),
               F(13, 30), F(9, 29), F(7, 17)]
    fmt = _row_formatter(chapter, "auto")
    check("4/13 stays exact", fmt(F(4, 13)), "4/13")
    check("5/16 stays exact", fmt(F(5, 16)), "5/16")
    check("9/29 stays exact", fmt(F(9, 29)), "9/29")


def test_ugly_scaled_values_become_decimals():
    """The scaled rule's exact values at s=0.85 are things like 168/547. Same number,
    but unreadable and uncheckable — the whole ROW goes decimal."""
    from fractions import Fraction as F
    fmt = _row_formatter([F(168, 547), F(61, 949), F(3, 28)], "auto")
    check("168/547 -> a decimal", fmt(F(168, 547)), "0.307")
    check("...and the WHOLE row goes with it (no mixed row)",
          fmt(F(3, 28)), "0.107")


def test_no_label_ever_goes_through_mathtext():
    """Figure labels must never be $-wrapped: matplotlib decides mathtext on the
    PARITY of '$' in the string, so a stray one swallows the rest of the label."""
    from fractions import Fraction as F
    for fmt_name in ("auto", "fraction", "decimal"):
        fmt = _row_formatter([F(4, 13)], fmt_name)
        check_true(f"{fmt_name}: no '$' in the label", "$" not in fmt(F(4, 13)))
        check_true(f"{fmt_name}: no LaTeX \\frac",
                   "frac" not in fmt(F(4, 13)))


def test_bad_value_format_raises():
    raises("an unknown value_format",
           lambda: _row_formatter([1], "scientific"),
           contains="value_format")


# --- the matrix renderer ------------------------------------------------------

def test_matrix_renders_computed_adjacency():
    figs = render({"kind": "matrix", "nodes": ["A", "B"],
                   "edges": [["A", "B"]], "compute": "adjacency"})
    check_true("a matrix figure was produced", bool(figs))


def test_matrix_style_must_be_matrix_or_table():
    fig, ax = plt.subplots()
    raises("an unknown matrix style",
           lambda: draw_matrix(ax, [[1]], style="hexagonal"),
           contains="style")
    plt.close(fig)


def test_iteration_table_rows_are_computed_not_typed():
    figs = render({"kind": "iteration_table",
                   "nodes": ["A", "B", "C"],
                   "edges": [["A", "B"], ["B", "A"], ["C", "A"]],
                   "compute": "pagerank", "rule": "basic", "steps": 3})
    check_true("an iteration table was produced", bool(figs))


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        before = len(_FAILS)
        try:
            t()
        except Exception:
            _FAILS.append(f"{t.__name__} RAISED\n{traceback.format_exc()}")
        print(f"  [{'ok' if len(_FAILS) == before else 'FAIL':4s}] {t.__name__}")
    print()
    if _FAILS:
        for f in _FAILS:
            print(f"FAIL: {f}")
        print(f"\n{len(_FAILS)} failure(s) across {len(tests)} tests")
        return 1
    print(f"{len(tests)}/{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
