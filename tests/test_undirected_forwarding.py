#!/usr/bin/env python3
"""X2 (v0.11.1) — `node_size` / `show_labels` forwarding on BOTH graph paths.

F9 / F8: the 0.8.0 directed-path fix re-landed in its undirected sibling. Through
0.11.0, `_resolve_graph_annotations` (undirected) returned a dict with NO
`node_size` and NO `show_labels`, while `_GRAPH_KEYS_COMMON` allowlisted both — so
`_check_figure_keys` passed and the value SILENTLY EVAPORATED (it cost er20_p006 a
figure in L8). This asserts BOTH branches forward BOTH keys, so the bug cannot
re-land a THIRD time (the fix-one-branch mistake is what let it recur).

Run: ``python3 tests/test_undirected_forwarding.py`` or via pytest.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
from matplotlib.collections import PathCollection  # noqa: E402

import cs470_engine.problems as problems  # noqa: E402
from cs470_engine.plot_style import apply_default_style  # noqa: E402

apply_default_style()
_RENDERED = []


class FakeWS:
    shared_figures = {}


def _render(spec):
    _RENDERED.clear()
    # Set the display seam per-call: `problems.display` is a shared global that
    # other test modules also reassign, so binding it once at import is racy.
    problems.display = lambda fig: _RENDERED.append(fig)
    problems._render_figure(FakeWS(), spec)
    return _RENDERED[0]


def _node_sizes(spec):
    fig = _render(spec)
    ax = fig.axes[0]
    sizes = [s for c in ax.collections if isinstance(c, PathCollection)
             for s in c.get_sizes().tolist()]
    plt.close(fig)
    return sizes


def _label_count(spec):
    fig = _render(spec)
    ax = fig.axes[0]
    n = sum(1 for t in ax.texts if t.get_text())
    plt.close(fig)
    return n


UNDIRECTED = {"kind": "graph",
              "nodes": [{"id": "A", "pos": [0, 0]}, {"id": "B", "pos": [1, 0]},
                        {"id": "C", "pos": [0.5, 1]}],
              "edges": [["A", "B"], ["B", "C"]]}
DIRECTED = {"kind": "graph", "directed": True,
            "nodes": [{"id": "A", "pos": [0, 0]}, {"id": "B", "pos": [1, 0]},
                      {"id": "C", "pos": [0.5, 1]}],
            "edges": [["A", "B"], ["B", "C"]]}


def test_node_size_forwards_on_the_undirected_path():
    default = max(_node_sizes(UNDIRECTED))
    got = max(_node_sizes({**UNDIRECTED, "node_size": 1200}))
    assert got != default, f"undirected node_size evaporated (still {default})"
    assert got == 1200      # the DRAWN size == the requested size


def test_node_size_forwards_on_the_directed_path():
    default = max(_node_sizes(DIRECTED))     # DAG default (2000) > undirected 600
    got = max(_node_sizes({**DIRECTED, "node_size": 1200}))
    assert got != default, f"directed node_size evaporated (still {default})"
    assert got == 1200


def test_show_labels_forwards_on_the_undirected_path():
    assert _label_count({**UNDIRECTED, "show_labels": True}) == 3
    assert _label_count({**UNDIRECTED, "show_labels": False}) == 0


def test_show_labels_forwards_on_the_directed_path():
    assert _label_count({**DIRECTED, "show_labels": True}) == 3
    assert _label_count({**DIRECTED, "show_labels": False}) == 0


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()


# ---------------------------------------------------------------------------
# THE BOUNDARY TEST — the durable half. The six lines above are the instance.
# ---------------------------------------------------------------------------
#
# 🧨 THIS BUG HAS NOW LANDED THREE TIMES ON THE SAME SEAM, and each time the fix
# was "forward the key we just noticed":
#
#     0.8.0   the DIRECTED branch forwarded only pos + labels; highlight_nodes
#             and everything else evaporated.
#     0.11.1  the UNDIRECTED branch allowlisted node_size / show_labels and
#             returned neither (X2/F9 above). Cost er20_p006 a figure in L8.
#     0.12.x  the UNDIRECTED branch allowlisted node_groups / group_colors /
#             group_legend / edge_styles and returned none of them. Cost
#             DEPLOYED 10.1 `bipartite_pairs` its entire division, for months,
#             with every gate green.
#
# `_check_figure_keys` enforces "an unknown key is an error, not a shrug" — and
# it has a hole exactly where a key is KNOWN TO THE ALLOWLIST and UNKNOWN TO THE
# RESOLVER. `totally_bogus_key` raises; `node_groups` on an undirected spec was
# silent. That gap, not any particular key, is the defect.
#
# So this test does not name keys. It asserts the INVARIANT:
#
#     allowlist − dispatch-consumed − resolver-forwarded  ==  ∅
#
# A future allowlist entry that nobody wires up fires on the day it lands
# instead of years later. ⚠ IF THIS TEST FAILS, DO NOT ADD THE KEY TO
# `_CONSUMED_BY_DISPATCH` TO MAKE IT PASS. That set is for keys the dispatch
# genuinely reads before the resolver runs; padding it is how the invariant
# becomes decoration.

#: Keys `_render_graph` / `_draw_graph_into` / `_build_graph` read THEMSELVES,
#: before either resolver is called. Verified by reading those functions, not
#: assumed: `kind`/`ref` are dispatch bookkeeping, `directed` selects the branch,
#: `nodes`/`edges`/`layout`/`layout_seed` build the graph and its positions, and
#: `figsize` sizes the figure.
_CONSUMED_BY_DISPATCH = frozenset({
    "kind", "ref", "directed", "nodes", "edges", "layout", "layout_seed",
    "figsize",
})

#: `matching` is consumed INSIDE the undirected resolver (it derives
#: `matched_edges` from it) rather than forwarded under its own name, so it is
#: honored without appearing in the returned dict.
_CONSUMED_BY_RESOLVER = frozenset({"matching"})

#: `node_size` is passed to `draw_directed_graph` EXPLICITLY at the call site,
#: beside the resolver's kwargs, so it is forwarded without being in the
#: directed resolver's return value. Confirmed at `_draw_graph_into`.
_EXPLICIT_AT_CALLSITE = frozenset({"node_size"})

_PROBE = {"kind": "graph", "nodes": [{"id": "a", "pos": [0, 0]}], "edges": []}


def _unwired(allowlist, forwarded, extra=frozenset()):
    return sorted(allowlist - forwarded - _CONSUMED_BY_DISPATCH - extra)


def test_every_undirected_allowlisted_key_is_actually_forwarded():
    allow = problems._GRAPH_KEYS_COMMON | problems._GRAPH_KEYS_UNDIRECTED
    forwarded = set(problems._resolve_graph_annotations(dict(_PROBE), None))
    missing = _unwired(allow, forwarded, _CONSUMED_BY_RESOLVER)
    assert not missing, (
        "UNDIRECTED: these keys are allowlisted, so `_check_figure_keys` accepts "
        f"them, and `draw_graph` never receives them: {missing}. They will "
        "EVAPORATE SILENTLY — the author gets the default and no error. Forward "
        "them in `_resolve_graph_annotations`; do not widen the exemption sets.")


def test_every_directed_allowlisted_key_is_actually_forwarded():
    allow = problems._GRAPH_KEYS_COMMON | problems._GRAPH_KEYS_DIRECTED
    forwarded = set(problems._resolve_directed_annotations(dict(_PROBE), None))
    missing = _unwired(allow, forwarded, _EXPLICIT_AT_CALLSITE)
    assert not missing, (
        "DIRECTED: allowlisted but never forwarded: " + str(missing))


def test_the_boundary_test_can_fail():
    """RED CASE. A test that cannot fail proves nothing (gate-design rule)."""
    allow = problems._GRAPH_KEYS_COMMON | frozenset({"a_key_nobody_wired_up"})
    forwarded = set(problems._resolve_graph_annotations(dict(_PROBE), None))
    missing = _unwired(allow, forwarded, _CONSUMED_BY_RESOLVER)
    assert missing == ["a_key_nobody_wired_up"], (
        "the invariant did not notice an unwired key — it is decoration")


def test_the_group_keys_reach_draw_graph_as_drawn_ink():
    """The regression itself, measured on the ARTIST rather than the kwargs.

    Forwarding is necessary and not sufficient: the point is that a reader SEES
    two groups. So this renders and counts distinct node facecolors — one for an
    ungrouped graph, two when the groups are declared.
    """
    base = {"kind": "graph", "node_size": 620,
            "nodes": [{"id": n, "pos": p} for n, p in
                      (("A", [0, 0]), ("B", [0, 1.3]),
                       ("C", [2.2, 0]), ("D", [2.2, 1.3]))],
            "edges": [["A", "C"], ["B", "D"]]}
    grouped = dict(base, node_groups={"A": "S1", "B": "S1",
                                      "C": "S2", "D": "S2"},
                   group_colors={"S1": "#7CB9E8", "S2": "#1A9641"},
                   group_legend=False)

    def facecolors(spec):
        fig, ax = plt.subplots()
        try:
            problems._draw_graph_into(ax, spec)
            seen = set()
            for c in ax.collections:
                if isinstance(c, PathCollection):
                    for row in c.get_facecolor():
                        seen.add(tuple(round(float(v), 3) for v in row))
            return seen
        finally:
            plt.close(fig)

    plain = facecolors(base)
    assert len(plain) == 1, f"ungrouped graph should be one fill, got {plain}"
    two = facecolors(grouped)
    assert len(two) == 2, (
        "node_groups reached draw_graph but drew no distinct fills — this is "
        f"the 10.1 `bipartite_pairs` defect, got {two}")


def test_edge_styles_triples_parse_and_a_bad_one_raises():
    spec = dict(_PROBE, nodes=[{"id": "a", "pos": [0, 0]},
                               {"id": "b", "pos": [1, 0]}],
                edges=[["a", "b"]], edge_styles=[["a", "b", "dashed"]])
    got = problems._resolve_graph_annotations(spec, None)["edge_styles"]
    assert got == {("a", "b"): "dashed"}, got
    bad = dict(spec, edge_styles=[["a", "b"]])
    try:
        problems._resolve_graph_annotations(bad, None)
    except ValueError:
        pass
    else:
        raise AssertionError("a malformed edge_styles entry must raise")
