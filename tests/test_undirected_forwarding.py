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
