#!/usr/bin/env python3
"""B7 — the DPI-INVARIANCE gate: ink measured in points must STAY points at any draw dpi.

WHY THIS GATE EXISTS
--------------------
`_points_ellipse` sized its ellipse with `Affine2D().scale(fig.dpi / 72)`, which FREEZES
the dpi at construction. Text does not freeze: matplotlib scales a fontsize by the
RENDERER's dpi at DRAW time. So the two bases diverge whenever draw dpi != construct dpi:

    effective ellipse size = w_pts * (construct_dpi / draw_dpi)

That is the shipping context, not a corner: `apply_default_style()` sets
`InlineBackend.figure_format = 'retina'`, retina draws at 2x `fig.dpi`, and 0.10.1's
bow-tie fringe labels therefore overflowed their blobs by ~1.6x IN THE LIVE WORKSPACE
while every local render showed them enclosed.

WHAT THIS GATE CANNOT SEE
-------------------------
* It checks WIDTH enclosure of the fringe labels and the point-invariance of
  `_points_ellipse`. It does NOT look at colour, position, overlap, or whether the figure
  is the right figure. It is a UNIT-BASIS gate, not an eyeball.
* It sweeps the dpis matplotlib will actually draw at through the two InlineBackend
  formats this engine can select (png = 1x, retina = 2x) plus a non-integer multiple to
  catch a fix that only works for exact doubling. It cannot see a dpi nobody selects.
* It measures with the font THIS MACHINE resolves. The container resolves DejaVu where a
  Mac resolves Helvetica — the absolute widths differ, and that is fine, because both the
  measurement and the drawing use the same face, so the RATIO is font-independent. That
  invariance is itself asserted below (`test_ratio_is_font_independent`), so if it ever
  stops being true this gate says so rather than silently reporting a local truth.

IDENTIFY BY SHAPE: the fringe labels are found by walking the axes for Text artists and
pairing each with the Ellipse centred on its data point — not by a hardcoded list of
strings. A new fringe is covered the day it is added.

    python3 tests/test_dpi_invariance.py
"""
import math
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Ellipse  # noqa: E402
from matplotlib.text import Text  # noqa: E402
from matplotlib.transforms import Affine2D, ScaledTranslation  # noqa: E402

import cs470_engine.plot_style as PS  # noqa: E402

# The dpis a figure is actually drawn at in this system. 100 = rcParams figure.dpi, which
# is what InlineBackend's 'png' format uses; 200 = 'retina', which apply_default_style()
# selects inside IPython. 150 is not a format we select — it is here so that a "fix" that
# only holds for an exact 2x (a fudge factor) fails this gate.
SHIPPING_DPIS = (100.0, 200.0, 150.0)

FAILURES = []


def check(cond, msg):
    if not cond:
        FAILURES.append(msg)
    return cond


def _fringe_pairs(ax, fig, dpi):
    """Every (label, drawn_text_pts, enclosing_ellipse_pts) at the given DRAW dpi.

    Pairs BY SHAPE — a Text and the Ellipse concentric with it — so a fringe added later
    is picked up without touching this file.
    """
    fig.dpi = dpi
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    ppp = dpi / 72.0
    ellipses = [a for a in ax.get_children() if isinstance(a, Ellipse)]
    out = []
    for t in ax.get_children():
        if not isinstance(t, Text) or not t.get_text() or t.get_alpha() == 0.0:
            continue
        cx, cy = ax.transData.transform(t.get_position())
        for e in ellipses:
            eb = e.get_window_extent(r)
            if (abs(eb.x0 + eb.width / 2 - cx) < 3.0
                    and abs(eb.y0 + eb.height / 2 - cy) < 3.0):
                tb = t.get_window_extent(r)
                out.append((t.get_text(), tb.width / ppp, eb.width / ppp))
                break
    return out


def _schematic():
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    PS.draw_bowtie_schematic(ax)
    return fig, ax


# -----------------------------------------------------------------------------
# 1. the primitive: a points-sized ellipse must BE points-sized, at any draw dpi
# -----------------------------------------------------------------------------
def test_points_ellipse_is_dpi_invariant():
    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    PS._points_ellipse(ax, (0.5, 0.5), 100.0, 40.0)
    e = [a for a in ax.get_children() if isinstance(a, Ellipse)][0]
    sizes = {}
    for dpi in SHIPPING_DPIS:
        fig.dpi = dpi
        fig.canvas.draw()
        bb = e.get_window_extent(fig.canvas.get_renderer())
        sizes[dpi] = bb.width / (dpi / 72.0)
    plt.close(fig)
    spread = max(sizes.values()) - min(sizes.values())
    check(spread < 0.5,
          f"_points_ellipse is NOT dpi-invariant: a 100pt ellipse measures "
          + ", ".join(f"{d:.0f}dpi -> {w:.1f}pt" for d, w in sizes.items())
          + " (spread %.1fpt). The scale is frozen at construction." % spread)
    check(abs(sizes[100.0] - 100.0) < 0.5,
          f"a 100pt ellipse measures {sizes[100.0]:.1f}pt at 100dpi — the base case is wrong")
    return sizes


# -----------------------------------------------------------------------------
# 2. the figure: every fringe label ENCLOSED, at every dpi it ships at
# -----------------------------------------------------------------------------
def test_fringe_labels_enclosed_at_every_shipping_dpi():
    fig, ax = _schematic()
    seen = 0
    for dpi in SHIPPING_DPIS:
        pairs = _fringe_pairs(ax, fig, dpi)
        check(pairs, f"COVERAGE: no label/ellipse pairs found at {dpi:.0f}dpi — "
                     "the gate saw nothing and would pass an empty figure")
        for label, tw, ew in pairs:
            seen += 1
            check(tw < ew,
                  f"{label!r} OVERFLOWS its blob at {dpi:.0f}dpi: "
                  f"text {tw:.1f}pt > ellipse {ew:.1f}pt (ratio {tw / ew:.2f})")
    plt.close(fig)
    return seen


# -----------------------------------------------------------------------------
# 3. the ratio must not depend on the font — so a local pass means something
# -----------------------------------------------------------------------------
def test_ratio_is_font_independent():
    ratios = {}
    # Restore the font family afterward: this test deliberately clobbers
    # rcParams["font.sans-serif"], and leaking that state made the font-metric-
    # sensitive sponsored-search declash test fail when it ran later in the suite
    # (a test-isolation bug, not a logic one — both pass in isolation).
    _saved_font = list(matplotlib.rcParams["font.sans-serif"])
    try:
        for family in (["DejaVu Sans"], ["Helvetica", "Arial", "DejaVu Sans"]):
            matplotlib.rcParams["font.sans-serif"] = family
            fig, ax = _schematic()
            pairs = _fringe_pairs(ax, fig, 200.0)
            ratios[family[0]] = max(tw / ew for _, tw, ew in pairs)
            plt.close(fig)
    finally:
        matplotlib.rcParams["font.sans-serif"] = _saved_font
    lo, hi = min(ratios.values()), max(ratios.values())
    check(hi - lo < 0.05,
          f"the text/blob ratio depends on the resolved FONT ({ratios}) — a local pass "
          "would then say nothing about the container, and this gate is not portable")
    return ratios


# -----------------------------------------------------------------------------
# 4. THE RED CASE — the gate must be able to FAIL. Rebuild the 0.10.1 bug and
#    prove check #1 catches it. A gate with no red case is a green light with no bulb.
# -----------------------------------------------------------------------------
def red_case_frozen_scale_is_caught():
    """Reconstruct the ORIGINAL frozen-dpi transform and assert the gate reds on it."""
    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    # THE 0.10.1 CODE, verbatim — scale frozen at construction dpi.
    tr = (Affine2D().scale(ax.figure.dpi / 72.0)
          + ScaledTranslation(0.5, 0.5, ax.transData))
    e = Ellipse((0, 0), 100.0, 40.0, transform=tr)
    ax.add_patch(e)
    sizes = {}
    for dpi in SHIPPING_DPIS:
        fig.dpi = dpi
        fig.canvas.draw()
        bb = e.get_window_extent(fig.canvas.get_renderer())
        sizes[dpi] = bb.width / (dpi / 72.0)
    plt.close(fig)
    spread = max(sizes.values()) - min(sizes.values())
    caught = spread >= 0.5
    detail = ", ".join(f"{d:.0f}dpi -> {w:.1f}pt" for d, w in sizes.items())
    if not caught:
        FAILURES.append(
            "RED CASE DID NOT RED: the frozen-scale ellipse measured "
            f"{detail} (spread {spread:.1f}pt) and test #1 would have PASSED it. "
            "This gate cannot fail and therefore proves nothing.")
    return caught, detail, spread


if __name__ == "__main__":
    PS.apply_default_style()   # the shipped style. get_ipython() is None here, so the
                               # retina magic no-ops — which is exactly why a local render
                               # never saw this bug. We sweep the dpis explicitly instead.
    print(f"plot_style: {PS.__file__}")
    print(f"resolved sans-serif: {matplotlib.rcParams['font.sans-serif'][:3]}")
    print(f"sweeping draw dpi: {', '.join(f'{d:.0f}' for d in SHIPPING_DPIS)}\n")

    sizes = test_points_ellipse_is_dpi_invariant()
    print("1. _points_ellipse dpi-invariance: "
          + ", ".join(f"{d:.0f}dpi -> {w:.1f}pt" for d, w in sizes.items()))

    seen = test_fringe_labels_enclosed_at_every_shipping_dpi()
    print(f"2. fringe labels enclosed: {seen} label/blob pairs checked "
          f"across {len(SHIPPING_DPIS)} dpis")

    ratios = test_ratio_is_font_independent()
    print("3. ratio is font-independent: "
          + ", ".join(f"{k} -> {v:.2f}" for k, v in ratios.items()))

    caught, detail, spread = red_case_frozen_scale_is_caught()
    print(f"4. RED CASE (0.10.1's frozen scale): {detail} (spread {spread:.1f}pt) "
          f"-> {'CAUGHT' if caught else 'NOT CAUGHT'}")

    print()
    if FAILURES:
        for f in FAILURES:
            print(f"FAIL: {f}")
        sys.exit(1)
    print(f"B7 dpi-invariance: GREEN ({seen} enclosures over {len(SHIPPING_DPIS)} dpis; "
          "red case reds)")
