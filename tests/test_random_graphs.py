#!/usr/bin/env python3
"""Tests for the v0.11.0 probabilistic-figure pass (Lesson 8, Erdős–Rényi).

TWO GATES, because the two failure modes are different:

1. COMPUTE correctness — the pmfs / thresholds / giant fraction match ER theory
   EXACTLY. There is no textbook to check against (E&K has no random-graph
   chapter), so the derivation IS the ground truth and these assert the closed
   forms directly (normalization to 1, known exact values, the mean identity,
   the fixed-point equation).

2. THE FIGURE SHOWS WHAT THE MATH SAYS — a VALUE-LEVEL gate. The distribution
   and sweep renderers are NOT node-link figures, so ``edge_audit`` /
   ``label_audit`` (which iterate nodes and edges) cannot see them, and the
   byte-identity harness only proves a figure did not MOVE, not that it is
   RIGHT. The right gate here is to render through the real YAML dispatch, pull
   the drawn bar heights / line ordinates back off the Matplotlib artists, and
   assert they equal the ``random_graphs`` pmf/curve to floating precision. Each
   such test carries a RED CASE (perturb the computed value; the assert must
   fail) so the gate is proven able to fail.

3. THE SAMPLER IS DETERMINISTIC GIVEN ITS SEED — same seed, same edge list. The
   cross-ENVIRONMENT half of that (local vs container byte-identity) is proven
   at build time, not here; this file proves same-process determinism, the seed
   contract, and the red cases.

Run: ``python3 tests/test_random_graphs.py`` (plain asserts, no pytest needed).
"""
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402

import cs470_engine.random_graphs as rg  # noqa: E402
import cs470_engine.problems as problems  # noqa: E402
from cs470_engine.plot_style import apply_default_style  # noqa: E402

apply_default_style()
TOL = 1e-12


# -----------------------------------------------------------------------------
# 1. COMPUTE — exact closed forms
# -----------------------------------------------------------------------------

def test_binomial_pmf_normalizes_and_matches_known_values():
    # Sums to 1 over its support (exact).
    assert abs(sum(rg.binomial_pmf(k, 20, 0.1) for k in range(21)) - 1.0) < TOL
    # Known exact value: Binomial(10, 0.2) at k=2 = C(10,2) .2^2 .8^8.
    exact = math.comb(10, 2) * 0.2**2 * 0.8**8
    assert abs(rg.binomial_pmf(2, 10, 0.2) - exact) < TOL
    # Blueprint q12: n=11 nodes -> degree Binomial(10, 0.2), P(deg=2) ~ 0.302.
    assert abs(rg.binomial_pmf(2, 10, 0.2) - 0.30199) < 1e-4
    # Out-of-support k is mass 0, not an error.
    assert rg.binomial_pmf(11, 10, 0.2) == 0.0
    assert rg.binomial_pmf(-1, 10, 0.2) == 0.0


def test_poisson_pmf_normalizes_and_matches_known_values():
    assert abs(sum(rg.poisson_pmf(k, 3.0) for k in range(60)) - 1.0) < 1e-10
    # Blueprint q16: Poisson(2) P(0) = e^-2 = 0.135 (the "converges-to-0, not
    # equals-0" trap — this is emphatically nonzero).
    assert abs(rg.poisson_pmf(0, 2.0) - math.exp(-2.0)) < TOL
    assert rg.poisson_pmf(0, 2.0) > 0.13
    # Blueprint T5: Poisson(2) at k=2 ~ 0.271, distinct from Binomial(10,.2)=0.302.
    assert abs(rg.poisson_pmf(2, 2.0) - 0.27067) < 1e-4
    assert rg.poisson_pmf(-1, 5.0) == 0.0


def test_degree_distribution_is_binomial_n_minus_1_with_mean_n_minus_1_p():
    # M4: degree ~ Binomial(n-1, p). Its EXACT mean is (n-1)p (M5), which is what
    # `expected_degree`'s docstring reconciles against its np return.
    n, p = 11, 0.2
    dd = rg.degree_distribution(n, p)
    assert len(dd) == n            # support 0..n-1
    mean = sum(d * prob for d, prob in dd)
    assert abs(mean - (n - 1) * p) < TOL          # exact finite-n mean
    assert abs(rg.expected_degree(n, p) - n * p) < TOL   # np convention
    # The two differ by exactly p (the O(p) finite-n artifact, documented).
    assert abs(rg.expected_degree(n, p) - mean - p) < TOL


def test_expected_edge_count_and_thresholds():
    # M3: E[#edges] = C(n,2) p.
    assert abs(rg.expected_edge_count(50, 0.06) - math.comb(50, 2) * 0.06) < TOL
    # M9/M10 on Hari's n=50 figures: 1/n = 0.02, ln n / n = 0.0782.
    assert abs(rg.giant_component_threshold(50) - 0.02) < TOL
    assert abs(rg.connectivity_threshold(50) - math.log(50) / 50) < TOL
    assert abs(rg.connectivity_threshold(50) - 0.07824) < 1e-4    # natural log
    # Ordering: giant appears strictly before connectivity (M9 < M10).
    assert rg.giant_component_threshold(50) < rg.connectivity_threshold(50)


def test_giant_component_fraction_knee_and_fixed_point():
    # Below/at threshold: no giant (M9). c = np, knee at c = 1.
    assert rg.giant_component_fraction(0.5) == 0.0
    assert rg.giant_component_fraction(1.0) == 0.0
    # Above: positive, and the returned S satisfies S = 1 - e^{-cS} exactly.
    for c in (1.5, 2.0, 3.0, 5.0):
        S = rg.giant_component_fraction(c)
        assert 0.0 < S < 1.0
        assert abs(S - (1.0 - math.exp(-c * S))) < 1e-9
    # Monotone in c, and just above threshold S is small but nonzero (the knee).
    assert rg.giant_component_fraction(1.01) > 0.0
    assert (rg.giant_component_fraction(1.5)
            < rg.giant_component_fraction(3.0)
            < rg.giant_component_fraction(5.0))


# -----------------------------------------------------------------------------
# 2. VALUE-LEVEL FIGURE GATE — the drawn figure equals the computed math
# -----------------------------------------------------------------------------

def _render_capture(spec):
    """Render a figure spec through the REAL dispatch, return the Figure."""
    captured = []
    problems.display = lambda fig: captured.append(fig)
    problems._render_figure(None, spec)
    assert captured, "dispatch rendered no figure"
    return captured[0]


def _bar_heights(ax):
    from matplotlib.patches import Rectangle
    bars = [(pch.get_x() + pch.get_width() / 2.0, pch.get_height())
            for pch in ax.patches if isinstance(pch, Rectangle)
            and pch.get_height() > 0]
    bars.sort()
    return bars


def test_distribution_bars_equal_the_computed_pmf():
    """R1 gate: the drawn bar heights ARE binomial_pmf, value for value."""
    n, p, kmax = 20, 0.15, 12
    spec = {"kind": "distribution",
            "compute": [{"dist": "degree", "n": n, "p": p, "k_max": kmax}],
            "x_label": "d", "y_label": "P"}
    fig = _render_capture(spec)
    ax = fig.axes[0]
    bars = _bar_heights(ax)
    expected = [(float(d), rg.binomial_pmf(d, n - 1, p))
                for d in range(kmax + 1) if rg.binomial_pmf(d, n - 1, p) > 0]
    assert len(bars) == len(expected), (len(bars), len(expected))
    for (bx, bh), (ex, eh) in zip(bars, expected):
        assert abs(bx - ex) < 1e-6, (bx, ex)
        assert abs(bh - eh) < 1e-9, (bh, eh)      # the bar IS the pmf
    plt.close(fig)

    # RED CASE — the gate must be able to fail. The bars match the TRUE pmf
    # (asserted above); against a deliberately WRONG pmf the same equality must
    # NOT hold. Proves the value-level check is not a tautology.
    wrong = [(ex, eh + 0.05) for (ex, eh) in expected]
    matches_wrong = all(abs(bh - wh) < 1e-9 for (_, bh), (_, wh) in zip(bars, wrong))
    assert not matches_wrong, "value-level gate would pass even against a wrong pmf"


def test_overlay_stem_markers_equal_the_poisson_pmf():
    """R1 overlay gate: the Poisson stem markers ARE poisson_pmf."""
    n, lam, kmax = 50, 3.0, 11
    spec = {"kind": "distribution",
            "compute": [
                {"dist": "degree", "n": n, "p": lam / n, "k_max": kmax},
                {"dist": "poisson", "lam": lam, "k_max": kmax}],
            "x_label": "d", "y_label": "P"}
    fig = _render_capture(spec)
    ax = fig.axes[0]
    # The Poisson overlay is the marker-only Line2D (linestyle "none").
    marker_lines = [ln for ln in ax.lines
                    if ln.get_linestyle() == "None" and len(ln.get_xdata())]
    assert marker_lines, "no Poisson marker line found"
    xs, ys = marker_lines[0].get_xdata(), marker_lines[0].get_ydata()
    for x, y in zip(xs, ys):
        assert abs(y - rg.poisson_pmf(int(round(x)), lam)) < 1e-9, (x, y)
    plt.close(fig)


def test_xy_curve_ordinates_equal_giant_component_fraction():
    """R2 gate: the drawn phase-transition curve IS giant_component_fraction,
    and the threshold verticals sit exactly at 1/n and ln n / n."""
    n = 50
    spec = {"kind": "xy_curve",
            "compute": {"curve": "giant_fraction", "n": n, "p_min": 0.0,
                        "p_max": 0.12, "points": 60},
            "thresholds": ["giant", "connectivity"],
            "x_label": "p", "y_label": "S"}
    fig = _render_capture(spec)
    ax = fig.axes[0]
    # The curve is the only solid multi-point Line2D.
    curve = max((ln for ln in ax.lines if ln.get_linestyle() == "-"),
                key=lambda ln: len(ln.get_xdata()))
    xs, ys = curve.get_xdata(), curve.get_ydata()
    for x, y in zip(xs, ys):
        c = rg.expected_degree(n, float(x))          # np
        assert abs(y - rg.giant_component_fraction(c)) < 1e-9, (x, y)
    # Threshold verticals: axvline is a Line2D with two equal x's.
    vlines = sorted({ln.get_xdata()[0] for ln in ax.lines
                     if len(ln.get_xdata()) == 2
                     and ln.get_xdata()[0] == ln.get_xdata()[1]})
    assert any(abs(v - rg.giant_component_threshold(n)) < TOL for v in vlines)
    assert any(abs(v - rg.connectivity_threshold(n)) < TOL for v in vlines)
    plt.close(fig)

    # RED CASE: the knee must be at np=1 (p=1/n=0.02). A curve value at p just
    # below threshold must be ~0; just above, positive. If the compute silently
    # used (n-1)p or 1/(n-1) the knee would shift off 0.02 and this would catch it.
    below = rg.giant_component_fraction(rg.expected_degree(n, 0.019))
    above = rg.giant_component_fraction(rg.expected_degree(n, 0.030))
    assert below == 0.0 and above > 0.0


# -----------------------------------------------------------------------------
# 3. SAMPLER — deterministic given its seed; the seed contract; red cases
# -----------------------------------------------------------------------------

def test_sample_gnp_is_deterministic_and_is_gnp_not_gnm():
    n, p, seed = 50, 0.06, 470
    G1 = rg.sample_gnp(n, p, seed)
    G2 = rg.sample_gnp(n, p, seed)
    assert sorted(G1.edges()) == sorted(G2.edges())      # same seed -> same graph
    assert G1.number_of_nodes() == n
    # G(n,p), NOT G(n,m): a DIFFERENT seed generally gives a DIFFERENT edge count
    # (an exact-m model could not). Edge count is random, not fixed.
    counts = {rg.sample_gnp(n, p, s).number_of_edges() for s in range(20)}
    assert len(counts) > 1, "edge count never varies — that would be G(n,m)"
    # p=0 -> empty; p=1 -> complete (the two deterministic corners).
    assert rg.sample_gnp(n, 0.0, seed).number_of_edges() == 0
    assert rg.sample_gnp(n, 1.0, seed).number_of_edges() == math.comb(n, 2)


def test_sample_gnp_edge_probability_is_p_across_seeds():
    # Averaged over many seeds, edge density -> p (a sanity check on the model,
    # NOT how any KEY is computed — keys are exact theorems, not sample means).
    n, p, trials = 30, 0.2, 200
    dens = [rg.sample_gnp(n, p, s).number_of_edges() / math.comb(n, 2)
            for s in range(trials)]
    assert abs(sum(dens) / trials - p) < 0.02


def test_sample_gnp_seed_contract_red_cases():
    # Seed must be an explicit int — no time/hash/PID seeding (byte-identity).
    for bad_seed in (None, "470", 4.7):
        try:
            rg.sample_gnp(10, 0.1, bad_seed)
            assert False, f"non-int seed {bad_seed!r} did not raise"
        except ValueError:
            pass
    # n and p validation.
    for bad in (lambda: rg.sample_gnp(-1, 0.1, 0),
                lambda: rg.sample_gnp(10, 1.5, 0),
                lambda: rg.sample_gnp(10, -0.1, 0)):
        try:
            bad()
            assert False, "bad n/p did not raise"
        except ValueError:
            pass


def test_dispatch_red_cases():
    # An unknown key on a probabilistic figure RAISES (fail-loudly dispatch),
    # rather than silently ignoring it.
    for spec in (
        {"kind": "distribution", "compute": [{"dist": "degree", "n": 5, "p": 0.2}],
         "bogus_key": 1},
        {"kind": "xy_curve",
         "compute": {"curve": "giant_fraction", "n": 5, "p_max": 0.5},
         "nope": 2},
        {"kind": "distribution",
         "compute": [{"dist": "poisson", "lam": 2.0}]},   # lone poisson, no k_max
        {"kind": "xy_curve",
         "compute": {"curve": "no_such_curve", "n": 5, "p_max": 0.5}},
    ):
        try:
            _render_capture(spec)
            assert False, f"spec did not raise: {spec}"
        except (ValueError, KeyError):
            pass


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
