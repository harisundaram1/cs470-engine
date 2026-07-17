#!/usr/bin/env python3
"""R1 (v0.11.1) — log axes on draw_xy_curve + the slope-annotation primitive.

Value-level (the L8 pattern): render, pull the drawn artist ordinates back off the
axes, and assert they equal the computed curve AND that the log scale + slope are
what the math says. Each carries a red case. Also proves the §2.3 ORDERING
constraint (scale set before the vline label) and linear-default additivity.

Run: ``python3 tests/test_xy_curve_log.py`` or via pytest.
"""
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402

import cs470_engine.random_graphs as rg  # noqa: E402
import cs470_engine.plot_style as ps     # noqa: E402
import cs470_engine.problems as problems  # noqa: E402
from cs470_engine.plot_style import apply_default_style  # noqa: E402

apply_default_style()


def _loglog_slope(xs, ys):
    lx = [math.log10(x) for x in xs]
    ly = [math.log10(y) for y in ys]
    n = len(lx)
    mx, my = sum(lx) / n, sum(ly) / n
    sxx = sum((x - mx) ** 2 for x in lx)
    sxy = sum((x - mx) * (y - my) for x, y in zip(lx, ly))
    return sxy / sxx


# --- R1: F1, the log-log power law -------------------------------------------

def test_F1_log_log_power_law_drawn_values_and_slope():
    for alpha in (2.1, 3.0):
        series = rg.power_law_series(alpha, 1, 1000)
        ks = [k for k, _ in series]
        pk = [p for _, p in series]
        fig, ax = plt.subplots()
        drawn = ps.draw_xy_curve(ax, [(ks, pk)], x_label="k", y_label="P(k)",
                                 xscale="log", yscale="log")
        # VALUE: the drawn artist == the computed curve.
        assert drawn[0] == (list(ks), list(pk))
        # the scale survived
        assert ax.get_xscale() == "log" and ax.get_yscale() == "log"
        # THE ANTI-CLAMP GATE: a log axis whose declared floor is 0 is always a bug.
        assert ax.get_xlim()[0] > 0 and ax.get_ylim()[0] > 0
        # THE PEDAGOGICAL INVARIANT: measured slope == -alpha.
        assert abs(_loglog_slope(*drawn[0]) - (-alpha)) < 1e-9
        plt.close(fig)


def test_F1_red_case_perturbed_ordinate_breaks_the_slope():
    series = rg.power_law_series(2.1, 1, 1000)
    ks = [k for k, _ in series]
    pk = [p for _, p in series]
    pk_bad = [pk[0] * 5] + pk[1:]           # bend the head off the law
    assert abs(_loglog_slope(ks, pk_bad) - (-2.1)) > 1e-6


def test_R1_ordering_vline_label_lands_at_the_LOG_top_not_frozen_linear():
    """§2.3: the vline label is placed at a LIVE ax.get_ylim()[1]. Setting the
    scale FIRST (as R1 does) makes that read the LOG top; the old order froze it at
    the linear top. Assert the label y == the final log top (== proof of order)."""
    series = rg.power_law_series(2.1, 1, 1000)
    ks = [k for k, _ in series]
    pk = [p for _, p in series]
    fig, ax = plt.subplots()
    ps.draw_xy_curve(ax, [(ks, pk)], xscale="log", yscale="log",
                     vlines=[{"x": 10, "label": "k = 10"}])
    labels = [t for t in ax.texts if "k = 10" in t.get_text()]
    assert labels, "vline label not drawn"
    label_y = labels[0].get_position()[1]
    top = ax.get_ylim()[1]
    assert abs(label_y - top) / top < 1e-6, (label_y, top)   # tracks the LOG top
    plt.close(fig)


def test_R1_linear_default_is_additive():
    fig, ax = plt.subplots()
    drawn = ps.draw_xy_curve(ax, [([0, 1, 2, 3], [0.0, 1.0, 4.0, 9.0])])
    assert ax.get_xscale() == "linear" and ax.get_yscale() == "linear"
    assert drawn[0] == ([0, 1, 2, 3], [0.0, 1.0, 4.0, 9.0])
    plt.close(fig)


def test_R1_unknown_scale_raises_fail_loud():
    fig, ax = plt.subplots()
    try:
        ps.draw_xy_curve(ax, [([1, 2], [1, 2])], yscale="symlog")
        assert False, "unknown scale did not raise"
    except ValueError as e:
        assert "yscale" in str(e)
    finally:
        plt.close(fig)


# --- R1: F2, Poisson tail vs power-law tail (forces the poisson k>=171 fix) ---

def test_F2_poisson_vs_power_law_tail_no_overflow():
    lam = 3.0
    ks = list(range(1, 1001))
    pois = [rg.poisson_pmf(k, lam) for k in ks]          # would OverflowError pre-fix
    plaw = [p for _, p in rg.power_law_series(2.1, 1, 1000)]
    fig, ax = plt.subplots()
    drawn = ps.draw_xy_curve(ax, [{"x": ks, "y": pois, "label": "Poisson(3)"},
                                  {"x": ks, "y": plaw, "label": "power law"}],
                             xscale="log", yscale="log")
    assert drawn[0][1] == pois                            # drawn == computed poisson
    assert ax.get_ylim()[0] > 0                           # anti-clamp
    plt.close(fig)
    # the spec's explicit red case for the overflow fix
    assert rg.poisson_pmf(200, lam) > 0.0


# --- Option ②: the slope-annotation primitive -------------------------------

def test_slope_annotation_draws_the_TRUE_slope_at_both_alphas():
    for alpha in (2.1, 3.0):
        series = rg.power_law_series(alpha, 1, 1000)
        ks = [k for k, _ in series]
        pk = [p for _, p in series]
        fig, ax = plt.subplots()
        ps.draw_xy_curve(ax, [(ks, pk)], xscale="log", yscale="log")
        res = ps.slope_annotation(ax, -alpha, x0=3, x1=30)
        (ax0, ay0), _, (cx, cy) = res["vertices"]
        measured = (math.log10(cy) - math.log10(ay0)) / (math.log10(cx) - math.log10(ax0))
        # THE PEDAGOGICAL INVARIANT: the drawn triangle SHOWS the true slope.
        assert abs(measured - (-alpha)) < 1e-9, (alpha, measured)
        plt.close(fig)


def test_slope_annotation_requires_log_log_axes():
    fig, ax = plt.subplots()
    ps.draw_xy_curve(ax, [([1, 2, 3], [1, 2, 3])])       # linear axes
    try:
        ps.slope_annotation(ax, -2.1, x0=1, x1=2)
        assert False, "slope_annotation did not raise on linear axes"
    except ValueError as e:
        assert "LOG-LOG" in str(e)
    finally:
        plt.close(fig)


def test_slope_annotation_through_dispatch():
    fig = None
    _RENDERED = []
    problems.display = lambda f: _RENDERED.append(f)

    class FakeWS:
        shared_figures = {}

    problems._render_figure(FakeWS(), {
        "kind": "xy_curve",
        "curves": [{"x": [1, 10, 100, 1000],
                    "y": [1.0, 10 ** -2.1, 10 ** -4.2, 10 ** -6.3]}],
        "xscale": "log", "yscale": "log",
        "slope_annotation": {"slope": -2.1, "x0": 3, "x1": 30},
    })
    ax = _RENDERED[0].axes[0]
    assert ax.get_xscale() == "log" and ax.get_yscale() == "log"
    assert len(ax.lines) >= 4          # 1 curve + 3 triangle legs
    plt.close(_RENDERED[0])


# --- X1: draw_distribution RAISES on a log axis ------------------------------

def test_X1_draw_distribution_raises_on_a_log_axis():
    fig, ax = plt.subplots()
    try:
        ps.draw_distribution(ax, [rg.poisson_series(3.0, 20)], yscale="log")
        assert False, "draw_distribution did not raise on a log axis"
    except ValueError as e:
        assert "log axis" in str(e) and "draw_xy_curve" in str(e)
    finally:
        plt.close(fig)
    # ...and the same figure on a LINEAR axis still draws (the guard is scoped).
    fig, ax = plt.subplots()
    drawn = ps.draw_distribution(ax, [rg.poisson_series(3.0, 20)])
    assert drawn[0][1] == [p for _, p in rg.poisson_series(3.0, 20)]
    plt.close(fig)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
