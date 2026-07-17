#!/usr/bin/env python3
"""Ride-along (v0.11.1): two-column concept cells top-align their columns.

Without `align_items="flex-start"` the HBox falls back to CSS `align-items:
stretch`, the shorter column stretches to the taller, and the figure floats above
dead space. LAYOUT-only — it touches no matplotlib figure, so it cannot perturb
any figure's byte-identity (confirmed by the render regression).

Run: ``python3 tests/test_concept_layout.py`` or via pytest.
"""
import matplotlib
matplotlib.use("Agg")
import ipywidgets as widgets            # noqa: E402

import cs470_engine.concept as concept  # noqa: E402


class _FakeWS:
    concepts_module_path = None          # -> placeholder render path (no module)


def _hbox_layouts_for(layout_kind):
    captured = []
    concept.display = lambda obj: captured.append(obj)
    section = {
        "id": "c_demo",
        "title": "Demo",
        "layout": layout_kind,
        "render_function": "does_not_exist",
        "controls": [{"name": "k", "kind": "slider", "min": 1, "max": 5}],
    }
    concept.render_concept(_FakeWS(), section)
    return [o for o in captured if isinstance(o, widgets.HBox)]


def test_two_column_layouts_top_align_their_columns():
    for kind in ("figure_left", "narration_left"):
        hboxes = _hbox_layouts_for(kind)
        assert hboxes, f"{kind} produced no HBox"
        assert hboxes[0].layout.align_items == "flex-start", kind


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
