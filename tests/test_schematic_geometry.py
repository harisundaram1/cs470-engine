#!/usr/bin/env python3
"""B8 — the schematic's LABEL-PLACEMENT gate: is each region label in the region it names?

WHY THIS GATE EXISTS
--------------------
The bow-tie's IN / OUT labels have now been misplaced TWICE, in OPPOSITE directions, and a
human found both:

  1. `-2*span/3` — the lobe's AREA CENTROID. A triangle's centroid sits a third of the way
     from its base, so on two MIRRORED lobes it pushed IN left and OUT right by span/6 each.
  2. `-span/2`   — the midpoint of the WHOLE TRIANGLE's x-extent. The lobe's apex is at the
     origin, so the triangle TAPERS; the label was lifted to y = 0.45*half_h, where the lobe
     only reaches x = -0.45*span. **It was centred against a row it was not sitting in**, and
     its box hung off the edge of the shape it was supposed to be inside.

Bug #2 is what this gate is built from: the label's box left its own lobe. That is a
PROPERTY, not a preference, and a machine can hold us to it.

WHAT THIS GATE CANNOT SEE
-------------------------
* **It cannot see "visually centred."** Bug #1 above passes every check in this file — the
  centroid label was comfortably INSIDE its lobe and clear of every arrow; it just looked
  off-centre. Whether a label is *well placed* inside a legal region is an EYEBALL call and
  this gate does not make it. It only proves the label is not somewhere illegal.
  **A green run here is not permission to skip looking at the figure.**
* It checks the two lobe labels (IN / OUT) against the two lobes. It says nothing about SCC,
  TUBE, TENDRIL or DISCONNECTED — those are fringe blobs, and their enclosure is B7's job
  (`test_dpi_invariance.py`).
* It measures in DATA space at one dpi. That is sound *here* — a data-space position is
  dpi-invariant, unlike the points-sized blobs of B7 — but do not copy this file's approach
  to anything sized in ink without re-reading B7.

    python3 tests/test_schematic_geometry.py
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.path import Path  # noqa: E402
from matplotlib.text import Text  # noqa: E402

import cs470_engine.plot_style as PS  # noqa: E402
from cs470_engine.plot_style import BOWTIE_SCHEMATIC as S  # noqa: E402

R = S["core_radius"]
SPAN = S["lobe_span"]
HALF_H = S["lobe_half_h"]
FLOW_TAIL = SPAN * 0.60          # must track draw_bowtie_schematic's own `flow_tail`

# The two lobes, as the schematic builds them: base outboard, APEX AT THE ORIGIN.
LOBES = {
    "IN": Path([(-SPAN, HALF_H), (-SPAN, -HALF_H), (0.0, 0.0)]),
    "OUT": Path([(SPAN, HALF_H), (SPAN, -HALF_H), (0.0, 0.0)]),
}
# Each lobe's flow arrow, at y = 0.
ARROWS = {"IN": (-FLOW_TAIL, -R * 1.05), "OUT": (R * 1.05, FLOW_TAIL)}

FAILURES = []


def check(cond, msg):
    if not cond:
        FAILURES.append(msg)
    return cond


def _label_boxes(ax, fig):
    """Every IN/OUT label's box in DATA coordinates. Found by text content, then verified
    against the lobe geometry — the label IS its name, so keying on it is identification by
    shape, not a blacklist of artists we happened to see."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    inv = ax.transData.inverted()
    out = {}
    for t in ax.get_children():
        if isinstance(t, Text) and t.get_text() in LOBES:
            bb = t.get_window_extent(r)
            (x0, y0), (x1, y1) = (inv.transform((bb.x0, bb.y0)),
                                  inv.transform((bb.x1, bb.y1)))
            out[t.get_text()] = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    return out


def _boxes(placement=None):
    """Render the schematic; optionally override the IN/OUT placement to plant a defect."""
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    PS.draw_bowtie_schematic(ax, labels=(placement is None))
    if placement is not None:
        x, y = placement
        for xx, txt in ((-x, "IN"), (x, "OUT")):
            ax.text(xx, y, txt, ha="center", va="center",
                    fontsize=S["label_size"], weight="bold", zorder=6)
    boxes = _label_boxes(ax, fig)
    plt.close(fig)
    return boxes


def _violations(boxes):
    """The three properties, evaluated. Returns a list of human-readable breaches."""
    bad = []
    for name, (x0, y0, x1, y1) in boxes.items():
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        if not all(LOBES[name].contains_point(c) for c in corners):
            bad.append(f"{name}: its box x[{x0:+.2f},{x1:+.2f}] y[{y0:+.2f},{y1:+.2f}] is "
                       f"NOT FULLY INSIDE the {name} lobe — the label has left the region "
                       f"it names")
        a0, a1 = ARROWS[name]
        if (y0 < 0.0 < y1) and not (x1 < min(a0, a1) or x0 > max(a0, a1)):
            bad.append(f"{name}: its box OVERLAPS the {name} flow arrow "
                       f"(x [{min(a0,a1):+.2f},{max(a0,a1):+.2f}] at y=0)")
    if len(boxes) == 2:
        cx_in = (boxes["IN"][0] + boxes["IN"][2]) / 2
        cx_out = (boxes["OUT"][0] + boxes["OUT"][2]) / 2
        cy_in = (boxes["IN"][1] + boxes["IN"][3]) / 2
        cy_out = (boxes["OUT"][1] + boxes["OUT"][3]) / 2
        if abs(cx_in + cx_out) > 0.02 or abs(cy_in - cy_out) > 0.02:
            bad.append(f"IN/OUT are NOT MIRROR-SYMMETRIC: IN at ({cx_in:+.2f},{cy_in:+.2f}), "
                       f"OUT at ({cx_out:+.2f},{cy_out:+.2f}) — one lobe was edited and the "
                       f"other was not (F8)")
    return bad


def test_shipped_placement_is_legal():
    boxes = _boxes()
    check(len(boxes) == 2,
          f"COVERAGE: found {len(boxes)} lobe labels, expected 2 — the gate saw nothing to "
          "check and would have passed an empty figure")
    for v in _violations(boxes):
        check(False, v)
    return boxes


def red_cases():
    """Both historical placements, replayed. The gate MUST red on #2.

    It does NOT red on #1 — and that is stated, not hidden: the centroid label was legal and
    merely ugly, which is exactly the boundary of what this gate can know.
    """
    out = []
    for name, placement in (
            ("#1 area centroid  (-2*span/3, y=+0.79)", (2 * SPAN / 3, HALF_H * 0.45)),
            ("#2 full x-extent  (-span/2,   y=+0.79)", (SPAN / 2, HALF_H * 0.45)),
    ):
        bad = _violations(_boxes(placement))
        out.append((name, bad))
    caught_2 = bool(out[1][1])
    if not caught_2:
        FAILURES.append(
            "RED CASE DID NOT RED: the `-span/2` placement — which SHIPPED, and which a "
            "human found in the live workspace — raised no violation. This gate cannot "
            "fail and therefore proves nothing.")
    return out


if __name__ == "__main__":
    PS.apply_default_style()
    print(f"plot_style: {PS.__file__}")
    print(f"lobe span {SPAN}, half-height {HALF_H}, core r {R}, flow tail {FLOW_TAIL:.2f}\n")

    boxes = test_shipped_placement_is_legal()
    for n, (x0, y0, x1, y1) in sorted(boxes.items()):
        print(f"  {n:<4} box x[{x0:+.2f},{x1:+.2f}] y[{y0:+.2f},{y1:+.2f}]  "
              f"inside its lobe, clear of its arrow")

    print("\nRED CASES (both placements that actually shipped):")
    for name, bad in red_cases():
        if bad:
            print(f"  {name} -> CAUGHT")
            for b in bad:
                print(f"       {b}")
        else:
            print(f"  {name} -> not caught (LEGAL but off-centre — this gate cannot see "
                  f"'visually centred'; that stays an eyeball call)")

    print()
    if FAILURES:
        for f in FAILURES:
            print(f"FAIL: {f}")
        sys.exit(1)
    print("B8 schematic geometry: GREEN (2 lobe labels inside their regions and clear of "
          "their arrows, mirror-symmetric; the shipped defect reds)")
