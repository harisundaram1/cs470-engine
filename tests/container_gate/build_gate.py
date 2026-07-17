#!/usr/bin/env python3
"""Build the SEMANTIC container-render gate notebook (G1).

The gate runs the L8/L9 log-log figures' invariants IN THE ENVIRONMENT (not a
pixel diff across environments — that design is refuted: local↔container differ on
dpi, font and matplotlib, so every figure moves and the diff carries zero
information). It EXECUTES the value-level assertions where the numbers are real.

⚠ PRECONDITION THE SPEC OMITTED, LOAD-BEARING: the FIRST cell calls
`apply_default_style()`. Retina fires ONLY after that, and ONLY under a real kernel
(nbconvert --execute -> ZMQInteractiveShell). Without it the notebook runs in the
`{'png'}` construct==draw regime where an F7 dpi-freeze is INVISIBLE and the gate
goes green testing the wrong thing (F2 — the trap the gate exists to prevent).

The notebook is SELF-CONTAINED (all check code inline) so it needs only the
installed `cs470_engine` — nothing mounted — which is what lets it run unchanged
inside the workspace image:

    docker run --rm --platform linux/amd64 -v "$PWD":/probe \
      --entrypoint jupyter cs470-workspace:<TAG> \
      nbconvert --to notebook --execute --output /probe/out.ipynb /probe/gate.ipynb

Run `python3 tests/container_gate/build_gate.py` to (re)generate `gate.ipynb`.
"""
import pathlib

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

HERE = pathlib.Path(__file__).resolve().parent

# --- Cell 0: THE PRECONDITION (apply_default_style FIRST, assert retina fired) --
CELL_PRECONDITION = r'''
# ============================================================================
# PRECONDITION (load-bearing): apply_default_style() FIRST. Retina fires only
# after it AND only under a real kernel; without it the gate tests the {'png'}
# construct==draw regime where an F7 dpi-freeze is invisible (F2).
# ============================================================================
from cs470_engine.plot_style import apply_default_style
apply_default_style()

import matplotlib
from matplotlib_inline.config import InlineBackend

fmts = set(InlineBackend.instance().figure_formats)
print("matplotlib:", matplotlib.__version__)     # gate rule 7: make the skew VISIBLE
print("figure_formats:", fmts)
assert fmts == {"retina"}, (
    "RETINA DID NOT FIRE: gate is in the {'png'} construct==draw regime where an "
    "F7 dpi-freeze is invisible. The first cell MUST call apply_default_style() "
    "and the gate MUST run through `nbconvert --execute` (a real ZMQ kernel), "
    "never `python -c` or `ipython script.py`.")
print("PRECONDITION OK: retina fired under a real kernel.")
'''.strip()

# --- Cell 1: TIER A — value-level (F1 / F2 / F4), the L8 pattern ---------------
CELL_TIER_A = r'''
# ============================================================================
# TIER A — structural / value-level, per log figure. The drawn artist values ==
# the computed curve; the scale survived; the measured slope == -alpha.
# ============================================================================
import math
import matplotlib.pyplot as plt
import cs470_engine.random_graphs as rg
import cs470_engine.plot_style as ps


def loglog_slope(xs, ys):
    lx = [math.log10(x) for x in xs]
    ly = [math.log10(y) for y in ys]
    n = len(lx)
    mx, my = sum(lx) / n, sum(ly) / n
    return (sum((x - mx) * (y - my) for x, y in zip(lx, ly))
            / sum((x - mx) ** 2 for x in lx))


# F1 — the log-log power law, at both exponents, with a slope annotation.
for alpha in (2.1, 3.0):
    s = rg.power_law_series(alpha, 1, 1000)
    ks = [k for k, _ in s]
    pk = [p for _, p in s]
    fig, ax = plt.subplots()
    drawn = ps.draw_xy_curve(
        ax, [(ks, pk)], x_label="k", y_label="P(k)",
        xscale="log", yscale="log",
        slope_annotation={"slope": -alpha, "x0": 3, "x1": 30})
    assert ax.get_xscale() == "log" and ax.get_yscale() == "log", "scale did not survive"
    assert ax.get_xlim()[0] > 0 and ax.get_ylim()[0] > 0, "clamped log floor"
    assert drawn[0] == (ks, pk), "drawn artist != computed power_law_series"
    assert abs(loglog_slope(*drawn[0]) - (-alpha)) < 1e-9, "measured slope != -alpha"
    plt.close(fig)
    print(f"F1 alpha={alpha}: log-log, drawn==computed, slope==-{alpha} OK")

# F2 — Poisson tail vs power-law tail (forces the poisson k>=171 fix).
ks = list(range(1, 1001))
pois = [rg.poisson_pmf(k, 3.0) for k in ks]        # pre-fix: OverflowError at k=171
plaw = [p for _, p in rg.power_law_series(2.1, 1, 1000)]
fig, ax = plt.subplots()
drawn = ps.draw_xy_curve(
    ax, [{"x": ks, "y": pois, "label": "Poisson(3)"},
         {"x": ks, "y": plaw, "label": "power law"}],
    xscale="log", yscale="log")
assert drawn[0][1] == pois, "drawn Poisson != computed poisson_pmf"
assert ax.get_ylim()[0] > 0
assert rg.poisson_pmf(200, 3.0) > 0.0, "poisson_pmf(200,3) must return, not raise"
plt.close(fig)
print("F2 Poisson-vs-power-law: drawn==computed, no k>=171 overflow OK")

# F4 — CCDF and its transpose (Zipf) — the claim the figure makes, gated.
c = rg.power_law_ccdf(2.1, 1, 1000)
fig, ax = plt.subplots()
d1 = ps.draw_xy_curve(ax, [([k for k, _ in c], [v for _, v in c])],
                      xscale="log", yscale="log")
plt.close(fig)
fig, ax = plt.subplots()
d2 = ps.draw_xy_curve(ax, [([v for _, v in c], [k for k, _ in c])],
                      xscale="log", yscale="log")
plt.close(fig)
assert d2[0][0] == d1[0][1] and d2[0][1] == d1[0][0], "Fig 18.4 != transpose of Fig 18.3"
print("F4 CCDF transpose (Zipf) OK")
'''.strip()

# --- Cell 2: ANTI-CLAMP — the honest red case (spec's literal one is a tautology)
CELL_ANTI_CLAMP = r'''
# ============================================================================
# ANTI-CLAMP. MEASURED CORRECTION (code wins over spec): `ax.get_ylim()[0] > 0`
# is a TAUTOLOGY on a matplotlib log axis — set_ylim(0,.) / set_ylim(bottom=0) are
# both CLAMPED to a small POSITIVE floor (6.3e-5 / 0.89), so that assertion can
# never observe a 0 floor and is NOT a red-case-able gate on its own. The real
# anti-clamp guard is that draw_distribution RAISES on a log axis (its bars/stems
# are anchored at y=0 — three separate anchors). Red case, red-case-able:
# ============================================================================
raised = False
fig, ax = plt.subplots()
try:
    ps.draw_distribution(ax, [rg.poisson_series(3.0, 20)], yscale="log")
except ValueError:
    raised = True
plt.close(fig)
assert raised, ("RED CASE FAILED: draw_distribution did not RAISE on a log axis — "
                "the y=0-anchored silent-clamp (73,000px overhang) is unguarded.")
print("anti-clamp: draw_distribution RAISES on log (the 3-anchor bug guarded at source) OK")
'''.strip()

# --- Cell 3: TIER B — dpi-ratio invariance on the log figure ink + red case ----
CELL_TIER_B = r'''
# ============================================================================
# TIER B — ink geometry (the F7 axis), RATIO-based, in the environment. Every
# IN-VIEW text artist's extent / dpi must be dpi-invariant across the shipping
# dpis; a frozen (construction-dpi) size fails. Extends B7 to the R1 log figure.
# ⚠ Filter to IN-VIEW ticks (LogLocator emits off-view decade labels).
#
# ⚠ THRESHOLD IS RELATIVE, MEASURED: B7's absolute 0.5pt was tuned for a 100pt
# ellipse (0.5%). The log figure's ink is small mathtext ($10^k$, ~17pt) whose
# width carries ~3-7% RASTERIZATION/HINTING noise across dpi — an absolute 0.5pt
# would false-positive on it (measured). An F7 construction-dpi FREEZE is a
# monotonic ~2x divergence (~50-69% relative). So the gate uses a RELATIVE
# threshold that sits above the hinting floor (~7%) and far below a freeze (~69%).
# ============================================================================
from matplotlib.patches import Ellipse
from matplotlib.transforms import Affine2D, ScaledTranslation

SHIPPING_DPIS = (100.0, 200.0, 150.0)   # 150 catches an exact-2x-only "fix"
REL_TOL = 0.20                          # hinting noise <=7%, an F7 freeze ~69%


def inview_ink_by_dpi(build, dpi):
    fig, ax = build()
    fig.dpi = dpi
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    ppp = dpi / 72.0
    widths = {}
    # axis labels (points-based text; always in view)
    for key, lab in (("xlabel", ax.xaxis.label), ("ylabel", ax.yaxis.label)):
        if lab.get_text().strip():
            widths[key] = lab.get_window_extent(r).width / ppp
    # in-view decade tick labels only (filter by tick LOCATION vs the view limits)
    for axis, ticks, labels, lim in (
            ("x", ax.get_xticks(), ax.get_xticklabels(), ax.get_xlim()),
            ("y", ax.get_yticks(), ax.get_yticklabels(), ax.get_ylim())):
        lo, hi = lim
        for loc, lab in zip(ticks, labels):
            txt = lab.get_text().strip()
            if txt and lo <= loc <= hi:
                widths[f"{axis}tick:{txt}"] = lab.get_window_extent(r).width / ppp
    plt.close(fig)
    return widths


def build_F1():
    s = rg.power_law_series(2.1, 1, 1000)
    fig, ax = plt.subplots()
    ps.draw_xy_curve(ax, [([k for k, _ in s], [p for _, p in s])],
                     x_label="k", y_label="P(k)", xscale="log", yscale="log")
    return fig, ax


def rel_spread(vals):
    return (max(vals) - min(vals)) / (sum(vals) / len(vals))


by_dpi = {d: inview_ink_by_dpi(build_F1, d) for d in SHIPPING_DPIS}
keys = set.intersection(*[set(m) for m in by_dpi.values()])
assert keys, "COVERAGE: no in-view text artists measured on the log figure"
worst = 0.0
for k in keys:
    worst = max(worst, rel_spread([by_dpi[d][k] for d in SHIPPING_DPIS]))
assert worst < REL_TOL, (f"log-figure ink NOT dpi-invariant (worst relative spread "
                         f"{worst:.1%} >= {REL_TOL:.0%}) — an F7 construction-dpi freeze")
print(f"Tier B: {len(keys)} in-view text artists dpi-invariant "
      f"(worst relative spread {worst:.1%}, tol {REL_TOL:.0%})")

# RED CASE (VERIFY the ratio detector can fail — the ellipse defeated two prior
# candidate gates, so we prove it reds against THE SAME relative detector, UNSURE #6).
fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
tr = (Affine2D().scale(ax.figure.dpi / 72.0)
      + ScaledTranslation(0.5, 0.5, ax.transData))   # 0.10.1's frozen-dpi transform
e = Ellipse((0, 0), 100.0, 40.0, transform=tr)
ax.add_patch(e)
sizes = {}
for d in SHIPPING_DPIS:
    fig.dpi = d
    fig.canvas.draw()
    sizes[d] = e.get_window_extent(fig.canvas.get_renderer()).width / (d / 72.0)
plt.close(fig)
red_rel = rel_spread(list(sizes.values()))
assert red_rel >= REL_TOL, (f"RED CASE DID NOT RED: frozen-dpi ellipse relative spread "
                            f"{red_rel:.1%} < {REL_TOL:.0%} — the ratio gate cannot fail.")
print(f"Tier B red case: frozen-dpi ellipse CAUGHT (relative spread {red_rel:.0%})")
print("\\nGATE PASSED (Tier A value-level + Tier B dpi-ratio + both red cases).")
'''.strip()


def build():
    nb = new_notebook()
    nb.cells = [
        new_markdown_cell(
            "# Semantic container-render gate (G1)\n\n"
            "Runs the L8/L9 log-log figure invariants through a real kernel. "
            "Green here means: retina fired, the log scale survived, drawn == "
            "computed, the slope reads -alpha, and the ink is dpi-invariant. It "
            "does NOT see colour, the-right-figure, or overlap — the eyeball pass "
            "stays."),
        new_code_cell(CELL_PRECONDITION),
        new_code_cell(CELL_TIER_A),
        new_code_cell(CELL_ANTI_CLAMP),
        new_code_cell(CELL_TIER_B),
    ]
    nb.metadata = {}      # deployed-shell convention: no kernelspec drift
    out = HERE / "gate.ipynb"
    nbformat.write(nb, out)
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}")
