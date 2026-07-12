"""
plot_style.py — Centralized aesthetic module for CS 470 worksheets.

Encodes Tufte-style minimalism: no chart junk, direct labels over legends,
information density over decoration.

Design philosophy
-----------------
- Remove anything that does not carry information.
- No grid lines, no spines, no all-caps in labels.
- Trust gestalt perception to group related elements.
- Every visual element earns its place: if removing it does not lose
  information, remove it.

Single source of truth for the project's color palette and rendering
defaults. All worksheets and concept render functions must import from
this module rather than defining colors or styles inline.

Aesthetic rules (enforced by scripts/validate.py)
-------------------------------------------------
1. No matplotlib gridlines (no ax.grid(True)).
2. No rotated tick labels (rotation must be 0; reduce fontsize if needed).
3. No all-caps in titles, labels, or text (acronyms excepted).
4. No Unicode arrows in matplotlib text; use r'$\\rightarrow$' etc.
5. No solid-filled scatter markers (use facecolors='none').
6. Two curves on the same axes must differ in color OR linestyle.
7. No table or figure borders unless they mark a semantic boundary.
8. No redundant legends when direct labels work.
"""

import itertools
import math
import re
from fractions import Fraction

import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
from matplotlib import rcParams
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path as MplPath
import networkx as nx


# -----------------------------------------------------------------------------
# Color palette
# -----------------------------------------------------------------------------

#: Primary palette, UIUC-aligned. Use these for all single/two-color contexts.
COLORS = {
    "primary":    "#13294B",   # navy
    "accent":     "#CE5E11",   # orange
    "tertiary":   "#7CB9E8",   # sky blue
    "quaternary": "#C19A6B",   # caramel
    "good":       "#1A9641",   # ColorBrewer green
    "bad":        "#B2182B",   # ColorBrewer red
    "highlight":  "#009FD4",   # Arches (Illinois supporting) — flipped/highlighted edges
    "panel_bg":   "#EEF0F7",   # pale lavender-grey
    "minor_tick": "#D2D2D2",   # light gray
    "text":       "black",
}

#: Qualitative entity palette for categorical groupings (up to 4 entities).
#: Use when distinguishing e.g. students, agents, players in a game.
ENTITY_COLORS = ["#2166AC", "#D6604D", "#1A9641", "#762A83"]

#: Attribute-role palette for typed elements (e.g. skill or task types).
ATTRIBUTE_COLORS = {
    "code":   "#2C7BB6",
    "write":  "#228B22",
    "design": "#E66101",
}

#: Line styles for distinguishing multiple curves on shared axes.
LINESTYLES = ["-", "--", ":", "-."]

#: Standard kwargs for line plots with markers (open circles, white fill).
LINEPLOT_KWARGS = dict(
    linewidth=2,
    markersize=10,
    markerfacecolor="white",
    markeredgewidth=2,
)

#: Standard kwargs for scatter plots (open circles, no fill).
SCATTER_KWARGS = dict(s=120, facecolors="none", linewidths=2)


# -----------------------------------------------------------------------------
# Graph rendering config — single source of truth for node/edge aesthetics
# -----------------------------------------------------------------------------
#
# Every numeric and stylistic literal that ``draw_graph`` and
# ``draw_missing_edge`` consume lives here. Render functions that draw
# nodes/edges directly (bypassing ``draw_graph``) should pull from this
# dict rather than introducing fresh literals.

GRAPH_STYLE = {
    # Edges
    "edge_width":              1.5,
    "edge_color":              COLORS["primary"],
    "highlight_edge_width":    2.5,
    "highlight_edge_color":    COLORS["accent"],
    "weak_edge_style":         "dashed",

    # Matched-edge token (network-exchange outcomes, Lesson 5): bold BLACK,
    # rendering the "darkened edges" the chapter uses to mark a matching. It is
    # a SEPARATE token from highlight_edge_* on purpose — matched edges (bold
    # black) and highlighted edges/nodes (accent orange) carry different meaning
    # and can appear in the SAME figure, so they must stay visually distinct.
    "matched_edge_width":      3.0,
    "matched_edge_color":      COLORS["text"],   # black — distinct from accent

    # Missing-edge marker (drawn by draw_missing_edge)
    "missing_edge_style":      "dotted",
    "missing_edge_color":      COLORS["accent"],
    "missing_edge_alpha":      0.6,
    "missing_edge_width":      2,
    "missing_edge_zorder":     0,

    # Nodes
    "node_size":               600,
    "node_fill":               "white",        # "white" = open-circle look
    "node_edge_color":         COLORS["primary"],
    "node_edge_width":         2,

    # Highlighted nodes: thicker accent border + slightly larger size
    "highlight_node_size_delta":  100,
    "highlight_node_edge_color":  COLORS["accent"],
    "highlight_node_edge_width":  2.5,

    # Labels (drawn by draw_networkx_labels)
    "label_font_size":         13,
    "label_font_family":       "sans-serif",

    # Inline annotation font sizes for figure-internal text (cluster
    # labels, edge-midpoint counts, per-node stats). Smaller than the
    # primary label so they don't compete visually, but readable.
    "annotation_font_size":         11,    # single-line inline text
    "annotation_font_size_compact": 10,    # multi-line / tighter contexts

    # Bargaining-outcome annotations (Lesson 5). Node VALUES sit above each node,
    # OUTSIDE OPTIONS below; both are PLAIN text (never $-wrapped — see the L4
    # plain-integer/fraction rule). Vertical offset is in typographic points
    # (layout-scale-independent) added to the node radius so text clears the
    # circle regardless of node_size.
    "value_annotation_size":   12,
    "value_annotation_gap":    6,     # points of clearance beyond the node radius
    # Free-direction placement. A label is offset straight up (value) or straight
    # down (outside option) UNLESS that direction runs too close to one of the
    # node's own incident edges — on a diagonal layout an edge can leave a node at
    # nearly 90 deg and drive straight through the label. When the vertical is
    # within `annotation_free_angle` of an incident edge, the label rotates to the
    # smallest tilt that clears every incident edge by that angle. The tilt is
    # capped by `annotation_max_tilt` (< 90 deg) so the label always stays on its
    # own side of the node and the above/below convention survives.
    "annotation_free_angle":   38,    # degrees of angular clearance to aim for
    "annotation_max_tilt":     60,    # max rotation away from vertical
    # Rotating into the free wedge is only half the job: the wedge has to be WIDE
    # enough to hold the label. A wedge widens linearly with distance from the
    # node, so a tilted label is pushed out to where its own box fits with
    # `annotation_edge_margin` points to spare. The label's size is ESTIMATED from
    # its font size and character count (points — no renderer, no bbox pass); the
    # render gate measures the true bbox and is what actually proves the clearance.
    # An untilted label never needs the push (its wedge is wide open), so every
    # clean figure keeps byte-identical placement.
    "annotation_edge_margin":  9,     # points of clearance to keep off an incident edge
    "annotation_char_width":   0.60,  # label width ~ chars * fontsize * this
    "annotation_line_height":  1.20,  # label height ~ fontsize * this
    "annotation_max_offset":   2.5,   # cap the radial push (multiple of the base offset)
    # COLLISION FALLBACK (0.8.0). The rules above are LOCAL — they consider only
    # a node's own incident edges. That was sufficient through Lesson 5, whose
    # graphs are sparse. Lesson 6's are not: on Fig 14.6 the long D->A / E->A
    # links run right past B and C, so a label can land on an edge that does not
    # touch its own node, or on a neighbour's label. When (and ONLY when) the
    # local placement actually collides, the search widens to these bounds and
    # takes the first clean spot. A figure with no collision never enters it and
    # is left bit-for-bit alone.
    # Capped just under 90 so a relocated label NEVER crosses the horizon: an
    # "above" value stays in the upper half-plane and a "below" one stays in the
    # lower, however far it has to swing sideways. Crossing would silently make
    # the row caption lie — the caption says "above: PageRank", and a label that
    # dodged a collision by dropping underneath its node would be read as the
    # other row. Clearing the collision must not cost the figure its decodability.
    "annotation_collision_max_tilt":   88,    # degrees; sideways, never across
    "annotation_collision_distances":  (1.0, 1.3, 1.7, 2.2),  # multiples of the base offset
    # Outside-option pendant stub: a short dashed half-edge dangling from a node
    # toward its outside-option label (cf. Figures 12.6/12.8/12.9). Its length is
    # FIXED, in typographic points — the same unit basis as the annotation offset.
    # It is emphatically NOT a fraction of edge length: edge length is measured in
    # DATA units, and on a wide/flat layout matplotlib autoscales y to a tiny range,
    # so the data->display scale on y explodes and a data-unit stub renders ~30x
    # longer than on a compact layout (measured: 104 px vs 3068 px for near-identical
    # data-space edge lengths). Points are display units, so the stub is identical
    # on every layout.
    "pendant_stub_style":      "dashed",
    "pendant_stub_color":      COLORS["primary"],
    "pendant_stub_width":      1.5,
    "pendant_stub_len_pts":    20,    # stub length, POINTS (not data units)
    "pendant_label_gap":       3,     # points from the stub end to the label
    # Row caption: the above/below convention is otherwise conveyed by position
    # alone, so a bare "0.60" under a node is undecodable from the figure. The
    # caption names each row that is ACTUALLY populated — and only those, since a
    # row can vanish mid-interaction (5.1's no-deal region drops the value row).
    "row_caption_size":        10,
    "row_caption_color":       COLORS["primary"],
    "row_caption_gap":         10,    # points below the lowest below-label
    "value_row_caption":       "above: value",
    "outside_row_caption":     "below: outside option",
    "row_caption_sep":         "     ·     ",

    # Categorical node groups (Lesson 6: bow-tie roles, SCC membership). A single
    # accent highlight can mark ONE set; a partition needs one color per class,
    # and the bow-tie has five. Nodes take a translucent group fill with a solid
    # border of the same hue — the label stays black and legible on top.
    "group_fill_alpha":        0.55,
    "group_node_edge_width":   2,
    "group_legend_size":       9,
    "group_legend_marker_size": 8,
    "group_legend_anchor":     (0.5, -0.02),   # just under the axes, centred
    "group_legend_max_cols":   3,

    # Score labels. The Basic rule's values ARE small exact fractions (1/2, 5/16,
    # 4/13) and must print as such — they are the chapter's own numbers. The
    # SCALED rule's exact values at s = 0.85 are not: they are 168/547, 61/949,
    # 41/708. Same numbers, but nobody can read them, and a student cannot check
    # them. Past this denominator a row switches wholesale to decimals.
    "score_fraction_max_denominator": 64,   # > every denominator E&K prints
    "score_decimal_places":    3,

    # Reciprocal-edge arcs. A 2-cycle drawn straight superimposes two arrowheads
    # on ONE segment and reads as a single edge; bowing the halves apart in
    # opposite directions is what makes F⇄G and A⇄B legible as MUTUAL links.
    # 0.0 (dead straight) for every non-reciprocal edge, so nothing else moves.
    "reciprocal_edge_rad":     0.18,
}

#: Bow-tie role -> color. Semantic, not arbitrary: the SCC core takes the accent
#: (it is the subject), IN and OUT take cool/warm flanking hues, and DISCONNECTED
#: takes the grey that reads as "not part of the story".
BOWTIE_COLORS = {
    "IN":           COLORS["tertiary"],     # sky blue  — upstream of the core
    "SCC":          COLORS["accent"],       # orange    — the core itself
    "OUT":          COLORS["good"],         # green     — downstream of the core
    "TENDRIL":      COLORS["quaternary"],   # caramel   — hanging off a lobe
    "TUBE":         COLORS["highlight"],    # Arches    — IN -> OUT, bypassing
    "DISCONNECTED": COLORS["minor_tick"],   # grey      — off the bow-tie
}

#: Fallback palette for non-bow-tie groupings (e.g. "which SCC is this node in?"),
#: taken in order. All COLORS tokens — no literals.
GROUP_COLOR_CYCLE = [
    COLORS["accent"], COLORS["tertiary"], COLORS["good"],
    COLORS["quaternary"], COLORS["highlight"], COLORS["bad"],
    COLORS["primary"],
]


# -----------------------------------------------------------------------------
# Figure-level config consumed by the engine's concept renderer
# -----------------------------------------------------------------------------

FIGURE_STYLE = {
    # Default figsize for concept-cell figures. Sized to fit a normal
    # notebook viewport without requiring window resize.
    "concept_figsize": (6, 3.8),
}


# -----------------------------------------------------------------------------
# ipywidgets control styling
# -----------------------------------------------------------------------------
#
# Applied to slider/dropdown/checkbox `description` rendering so labels
# show at natural width instead of the narrow ipywidgets default.

CONTROL_STYLE = {
    "description_width": "initial",
}


# -----------------------------------------------------------------------------
# Hint-disclosure HTML styling (consumed by the problem-cell renderer)
# -----------------------------------------------------------------------------
#
# The <summary> of a hint <details> uses this CSS so students recognise
# the disclosure as clickable rather than decoration. Defined here so the
# panel-bg color stays governed by the COLORS palette.

HINT_SUMMARY_STYLE = (
    "cursor: pointer; user-select: none; "
    "display: inline-block; "
    "padding: 0.3em 0.7em; "
    "margin: 0.2em 0; "
    f"background: {COLORS['panel_bg']}; "
    "border-radius: 4px; "
    "font-weight: 500;"
)


# -----------------------------------------------------------------------------
# Notebook-level setup
# -----------------------------------------------------------------------------

def apply_default_style():
    """Call once at the top of every notebook.

    Sets retina rendering (in IPython environments), sans-serif fonts with
    Helvetica preferred, and disables the matplotlib Unicode-minus quirk.
    Safe to call outside IPython (the magic call is wrapped in try/except).
    """
    try:
        from IPython import get_ipython
        ipy = get_ipython()
        if ipy is not None:
            ipy.run_line_magic("config", "InlineBackend.figure_format = 'retina'")
    except Exception:
        pass
    rcParams["font.sans-serif"] = ["Helvetica", "Arial", "DejaVu Sans"]
    rcParams["font.family"] = "sans-serif"
    rcParams["axes.unicode_minus"] = False
    # Math renders in Computer Modern (TeX look) while labels/body stay sans —
    # mathtext.fontset is independent of font.family, so `$X_i$`, `$2pq$`, etc.
    # get clean CM math without changing prose typography. Restyles math in every
    # figure (engine-wide); ships in the Phase B bundle.
    rcParams["mathtext.fontset"] = "cm"


# -----------------------------------------------------------------------------
# Axes helpers
# -----------------------------------------------------------------------------

def apply_ax_style(ax):
    """Apply Tufte-style spines and ticks to a matplotlib axes.

    Removes all four spines. Major ticks are accent-orange; minor ticks are
    light gray. Tick labels stay horizontal (the project never rotates
    tick labels). Use on every axes the project produces.
    """
    for spine in ("top", "right", "left", "bottom"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(
        axis="both", which="major",
        labelsize=11,
        color=COLORS["accent"],
        labelcolor=COLORS["text"],
    )
    ax.tick_params(axis="both", which="minor", color=COLORS["minor_tick"])
    ax.minorticks_on()


# -----------------------------------------------------------------------------
# Signed-edge rendering (structural-balance worksheets)
# -----------------------------------------------------------------------------

#: Edge attribute key carrying a sign, and its two values, as emitted by the
#: worksheet YAML (e.g. ``- [A, B, {sign: pos}]``).
_SIGN_KEY = "sign"
_SIGN_POS = "pos"
_SIGN_NEG = "neg"

#: Curvature applied ONLY to figures that have crossing edges, so the two
#: members of a crossing pair bow apart and their sign labels don't overlap.
#: Non-crossing layouts (triangles, etc.) stay straight (rad=0).
_SIGN_EDGE_RAD = 0.22


#: A bare letter followed by digits, e.g. ``m2`` / ``f1`` — the only node-label
#: shape we turn into a subscript. Strictly guarded: plain letters (``A``),
#: bare digits (``5``), names (``Claire``), and existing mathtext (``X_i``,
#: ``A_{ij}``, ``Y_i(t)`` — all contain ``_``, ``{`` or ``(``) never match.
_SUBSCRIPT_LABEL_RE = re.compile(r"^([A-Za-z])(\d+)$")


def subscript_label(text):
    """Format a ``letter+digits`` node id as mathtext ``$letter_{digits}$``.

    ``m2 -> $m_2$``, ``f1 -> $f_1$``. Anything not matching ``^[A-Za-z]\\d+$``
    (single letters, bare digits, names, already-mathtext labels) is returned
    unchanged, so this is safe to apply to every node label by default.
    """
    s = str(text)
    m = _SUBSCRIPT_LABEL_RE.match(s)
    if not m:
        return s
    return f"${m.group(1)}_{{{m.group(2)}}}$"


def sign_label(sign):
    """Mathtext sign glyph — ``$-$`` avoids any Helvetica/Unicode fallback."""
    return "$+$" if sign == _SIGN_POS else "$-$"


def sign_color(sign):
    """Positive edges navy (primary); negative edges red (bad)."""
    return COLORS["primary"] if sign == _SIGN_POS else COLORS["bad"]


# Backward-compatible private aliases (kept so existing imports don't break).
_sign_label = sign_label
_sign_color = sign_color


def _segments_cross(p1, p2, p3, p4):
    """True if open segments p1-p2 and p3-p4 properly cross.

    Callers must have already excluded segments that share an endpoint node
    (adjacent edges), since this works purely on coordinates. Coordinates may be
    tuples or numpy arrays — only indexing is used.
    """
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1 = orient(p3, p4, p1)
    d2 = orient(p3, p4, p2)
    d3 = orient(p1, p2, p3)
    d4 = orient(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def signed_edges_cross(pos, edges):
    """True if any two of the given edges cross when drawn as straight chords.

    ``edges`` is an iterable of ``(u, v)``; ``pos`` maps node -> (x, y) (tuples
    or numpy arrays). Edges that share an endpoint *node* are adjacent, not
    crossing, and are skipped by node identity (positions may be unhashable).
    Used to decide whether to curve signed edges: only crossing layouts need it.
    """
    edges = list(edges)
    for i in range(len(edges)):
        a, b = edges[i]
        for j in range(i + 1, len(edges)):
            c, d = edges[j]
            if len({a, b, c, d}) < 4:
                continue  # shared endpoint node — adjacent edges
            if _segments_cross(pos[a], pos[b], pos[c], pos[d]):
                return True
    return False


def _node_radius_data(ax, node_size):
    """Marker radius (``sqrt(node_size/pi)`` points) in DATA units.

    Requires the axes limits + aspect to already be set (call after
    ``frame_signed_axes``) so the data<->display transform is stable. Falls back
    to 0 if the transform is not yet usable.
    """
    r_points = math.sqrt(max(node_size, 0.0) / math.pi)
    try:
        x_px0, _ = ax.transData.transform((0, 0))
        x_px1, _ = ax.transData.transform((1, 0))
        px_per_data = abs(x_px1 - x_px0) or 1.0
        px_per_point = ax.figure.dpi / 72.0
        return r_points * px_per_point / px_per_data
    except Exception:
        return 0.0


def frame_signed_axes(ax, pos, *, node_size=None, rad=0.0, pad_frac=0.18,
                      extra_points=None):
    """Set deterministic limits + equal aspect for a signed-graph figure.

    Self-drawn ``PathPatch`` edges don't update the axes data limits the way
    networkx's drawing did, so without this the limits hug the node *centers*,
    clipping the node circles and (with aspect=auto) distorting non-square
    layouts — e.g. the wide two-faction rectangle collapsing to a strip. We
    therefore frame the axes explicitly from the node positions, expanded to fit
    the node circles, the arc bulge (``0.5 * rad * max_chord``), and a small
    fractional margin; then lock ``aspect='equal'`` and turn autoscale off so
    bare patches can't drive it.

    ``extra_points`` is an optional iterable of ``(x, y)`` that must also stay in
    frame — e.g. annotation text a figure draws outside the node bbox (the
    two-faction "group X / Y" labels). They widen the bbox before padding.

    Call this BEFORE drawing edges, so the shrink transform is stable.
    """
    if node_size is None:
        node_size = GRAPH_STYLE["node_size"]
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    for ex, ey in (extra_points or []):
        xs.append(ex)
        ys.append(ey)
    if not xs:
        return
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny, 1e-6)

    # Provisionally frame on equal aspect so the node-radius transform resolves,
    # then add the radius + arc bulge + fractional pad and finalize.
    base_pad = pad_frac * span
    ax.set_xlim(minx - base_pad, maxx + base_pad)
    ax.set_ylim(miny - base_pad, maxy + base_pad)
    ax.set_aspect("equal")

    r_data = _node_radius_data(ax, node_size)
    max_chord = 0.0
    pts = list(pos.values())
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            max_chord = max(max_chord, math.hypot(pts[i][0] - pts[j][0],
                                                  pts[i][1] - pts[j][1]))
    bulge = 0.5 * abs(rad) * max_chord
    pad = base_pad + r_data + bulge
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_aspect("equal")
    ax.autoscale(False)
    ax.set_axis_off()


def draw_signed_edge(ax, p0, p2, sign, *, rad, color, width, alpha=1.0,
                     node_size=None, node_radius=None, label=True):
    """Draw ONE signed edge as an explicit quadratic Bezier + its sign label.

    This is the single source of truth for signed-edge rendering, shared by the
    engine's ``draw_graph`` (question figures) and the worksheet module's
    ``_draw_signed_graph`` (concept figures), so the two paths cannot drift.

    The control point is owned here:
        M  = (p0 + p2) / 2
        n  = unit perpendicular to the chord, (-d_y, d_x) / |d|
        P1 = M + rad * |d| * n
    The edge is the quadratic Bezier P0->P1->P2, and the label is placed at that
    same curve's midpoint B(0.5) = 0.25*P0 + 0.5*P1 + 0.25*P2. Because the draw
    and the label share the one control point P1, the label is provably on the
    curve (the previous bug chose the label's perpendicular independently of the
    drawn arc). With ``rad == 0``, P1 = M and B(0.5) = M, so this one path also
    renders straight edges with the label centered on the chord.

    ``node_radius`` (data units) shrinks the endpoints toward each other so the
    curve meets the node borders; if None it is derived from ``node_size`` via
    the axes transform (call ``frame_signed_axes`` first so it is stable). The
    shrink is capped so endpoints never cross past the chord midpoint.
    """
    if node_size is None:
        node_size = GRAPH_STYLE["node_size"]
    (x0, y0), (x2, y2) = p0, p2
    dx, dy = x2 - x0, y2 - y0
    length = math.hypot(dx, dy)
    if node_radius is None:
        node_radius = _node_radius_data(ax, node_size)
    if length > 0:
        # Cap the shrink at 40% of the chord so endpoints stay between nodes.
        s = min(node_radius, 0.4 * length)
        ux, uy = dx / length, dy / length
        x0, y0 = x0 + ux * s, y0 + uy * s
        x2, y2 = x2 - ux * s, y2 - uy * s
    e0, e2 = (x0, y0), (x2, y2)
    mx, my = (x0 + x2) / 2.0, (y0 + y2) / 2.0
    dx, dy = x2 - x0, y2 - y0
    length = math.hypot(dx, dy)
    if length == 0:
        p1 = (mx, my)
    else:
        nx_, ny_ = -dy / length, dx / length
        p1 = (mx + rad * length * nx_, my + rad * length * ny_)

    path = MplPath([e0, p1, e2],
                   [MplPath.MOVETO, MplPath.CURVE3, MplPath.CURVE3])
    ax.add_patch(PathPatch(path, edgecolor=color, facecolor="none",
                           linewidth=width, alpha=alpha, zorder=1,
                           capstyle="round"))

    if label:
        # B(0.5) of the SAME Bezier — guaranteed on the drawn curve.
        bx = 0.25 * x0 + 0.5 * p1[0] + 0.25 * x2
        by = 0.25 * y0 + 0.5 * p1[1] + 0.25 * y2
        ax.text(
            bx, by, sign_label(sign),
            ha="center", va="center",
            fontsize=GRAPH_STYLE["label_font_size"],
            color=color, alpha=alpha,
            bbox=dict(boxstyle="circle,pad=0.12", fc="white", ec="none"),
            zorder=4,
        )


def _draw_signed_edges(G, pos, ax, signed_edges, *, highlight_set, node_size):
    """Draw a set of signed edges via the shared ``draw_signed_edge`` helper.

    Curvature is gated on whether these edges cross: a crossing layout gets
    ``rad = _SIGN_EDGE_RAD``; a non-crossing one stays straight (``rad = 0``).
    Frames the axes first (deterministic limits + equal aspect) so node circles
    fit and the shrink transform is stable, then draws every edge with one
    shared node radius.
    """
    rad = _SIGN_EDGE_RAD if signed_edges_cross(pos, signed_edges) else 0.0
    frame_signed_axes(ax, pos, node_size=node_size, rad=rad)
    node_radius = _node_radius_data(ax, node_size)
    for u, v in signed_edges:
        sign = (G.get_edge_data(u, v) or {}).get(_SIGN_KEY)
        highlighted = tuple(sorted((u, v))) in highlight_set
        color = COLORS["highlight"] if highlighted else sign_color(sign)
        width = (GRAPH_STYLE["highlight_edge_width"] if highlighted
                 else GRAPH_STYLE["edge_width"])
        draw_signed_edge(ax, pos[u], pos[v], sign, rad=rad,
                         color=color, width=width, node_size=node_size,
                         node_radius=node_radius)


# -----------------------------------------------------------------------------
# Directed-graph (causal DAG) rendering helper
# -----------------------------------------------------------------------------

#: Node size + label font for directed causal-graph figures, tuned so wide
#: LaTeX labels (e.g. $Y_j(t-1)$) sit inside the circles. Shared by the engine's
#: figure path and worksheet concept DAGs so they render identically.
DAG_NODE_SIZE = 2000
DAG_LABEL_FONTSIZE = 8.5


def _draw_grouped_nodes(G, pos, ax, nodelist, node_size, node_groups,
                        group_colors, group_legend):
    """Draw ``nodelist``: plain open circles, or colored by categorical group.

    With no ``node_groups`` this is EXACTLY the legacy open-circle node pass, so
    every pre-0.8.0 figure is untouched. With groups, each node takes its group's
    color as a translucent fill plus a solid border of the same hue, and a legend
    is emitted so the colors decode themselves.

    Categorical grouping is what a single ``highlight_nodes`` accent cannot do:
    the bow-tie has FIVE classes (IN / SCC / OUT / tendril / disconnected) and
    SCC identification wants one color per component. Highlight marks *a* set;
    groups partition *every* node.
    """
    if not node_groups:
        nx.draw_networkx_nodes(
            G, pos, ax=ax, nodelist=nodelist,
            node_color=GRAPH_STYLE["node_fill"],
            edgecolors=GRAPH_STYLE["node_edge_color"],
            linewidths=GRAPH_STYLE["node_edge_width"],
            node_size=node_size,
        )
        return

    # Color groups in the order the GROUP MAP lists them, not the order the nodes
    # happen to appear in. The two differ, and the difference is visible: on Fig
    # 13.5 the node order starts with a lone singleton, so a node-order palette
    # hands the loudest color to a node nobody is looking at while the giant SCC
    # — the entire subject of the figure — takes whatever is left. The helpers
    # emit their group maps deliberately (biggest component first), and honoring
    # that is what puts the accent on the thing being taught.
    ordered = list(dict.fromkeys(node_groups.values()))
    palette = _resolve_group_colors(ordered, group_colors)

    ungrouped = [n for n in nodelist if n not in node_groups]
    if ungrouped:
        nx.draw_networkx_nodes(
            G, pos, ax=ax, nodelist=ungrouped,
            node_color=GRAPH_STYLE["node_fill"],
            edgecolors=GRAPH_STYLE["node_edge_color"],
            linewidths=GRAPH_STYLE["node_edge_width"],
            node_size=node_size,
        )
    for grp, color in palette.items():
        members = [n for n in nodelist if node_groups.get(n) == grp]
        if not members:
            continue
        nx.draw_networkx_nodes(
            G, pos, ax=ax, nodelist=members,
            node_color=color, alpha=GRAPH_STYLE["group_fill_alpha"],
            edgecolors=color, linewidths=GRAPH_STYLE["group_node_edge_width"],
            node_size=node_size,
        )
    if group_legend:
        _draw_group_legend(ax, palette)


def _reciprocal_rad(G, u, v):
    """Arc curvature for edge (u, v) — nonzero only for a RECIPROCAL pair.

    A 2-cycle drawn as two straight edges puts both arrows on the SAME line
    segment, one on top of the other: the reader sees one line and cannot tell
    a mutual pair from a single link. Since F⇄G (Fig 14.8) and A⇄B (the 3-node
    oscillation) are precisely the two figures that carry the leak and the
    non-convergence insights, that ambiguity would land on the two most important
    pictures in the lesson.

    Bowing the two halves apart in opposite directions separates them. The sign
    is keyed to a stable comparison of the endpoints, so each half of a pair bows
    the opposite way and the rendering does not depend on edge iteration order.
    Non-reciprocal edges get 0.0 and stay dead straight — which is every edge of
    every figure drawn before 0.8.0.
    """
    if not G.has_edge(v, u) or u == v:
        return 0.0
    rad = GRAPH_STYLE["reciprocal_edge_rad"]
    return rad if str(u) < str(v) else -rad


def draw_directed_graph(G, ax, *, pos, labels=None, node_size=None,
                        show_labels=True,
                        highlight_nodes=None, highlight_edges=None,
                        highlight_color=None,
                        node_values=None, node_values_below=None,
                        value_caption=None, below_caption=None,
                        node_groups=None, group_colors=None, group_legend=True,
                        curved_reciprocal=True, value_format="auto"):
    """Draw a directed graph: arrowheads, labels inside nodes, full annotation layer.

    AT PARITY WITH ``draw_graph``. Through 0.7.0 this renderer had none of the
    annotation layer ``draw_graph`` grew across Lessons 4-5 — no node values, no
    node highlighting, no categorical grouping — and the YAML dispatch forwarded
    it only ``pos`` and ``labels``. Lesson 6 is the first directed-graph lesson,
    so it is the first to hit that wall, but it will not be the last: the fix is
    parity, sharing ``draw_graph``'s machinery, rather than an L6 special case.

    Parameters beyond the original ``pos`` / ``labels`` / ``node_size`` /
    ``highlight_edges`` / ``highlight_color``:

    show_labels : bool
        Draw the node labels. Default True (the legacy behavior).
    highlight_nodes : list, optional
        Nodes to mark in accent orange (thicker border, slightly larger). The
        renderer accepted ``highlight_edges`` but never ``highlight_nodes``, and
        the dispatch forwarded NEITHER — so a directed figure could not mark a
        node at all.
    node_values : dict, optional
        ``{node: value}`` annotated ABOVE each node — the hub / authority /
        PageRank score written on the node. This is the single most important
        figure class in Lesson 6 and was simply unrenderable before.
    node_values_below : dict, optional
        A SECOND row, annotated below. Hub and authority are two scores on the
        same node, so a HITS figure wants both at once; PageRank wants one.
    value_caption, below_caption : str, optional
        What each row MEANS ("above: authority", "below: hub"). A bare number
        under a node is undecodable, so the caption is not decoration — it is
        what makes the figure self-contained. Rows with no caption are drawn
        uncaptioned rather than mislabeled.
    node_groups : dict, optional
        ``{node: group}`` — categorical coloring (bow-tie roles, SCC membership).
        Emits a decoding legend unless ``group_legend=False``.
    value_format : "auto" | "fraction" | "decimal"
        How the two score rows print. ``"auto"`` (the default) keeps exact
        fractions while they stay legible and switches a row to decimals once a
        denominator gets ugly — so the Basic rule shows the chapter's 1/2 and
        5/16, while the scaled rule shows 0.307 rather than 168/547.
    curved_reciprocal : bool
        Bow a reciprocal edge pair (u→v and v→u) into two visible arcs instead of
        two arrows superimposed on one segment. Default True; it is a no-op on a
        graph with no 2-cycle, which is every directed figure drawn before 0.8.0.

    Values are formatted by ``_exchange_value_label`` — plain text, so a Fraction
    renders as "4/13" and never as ``$\\frac{4}{13}$``. Figure labels must not go
    through mathtext (the Lesson-4 double-wrap crash class), and Lesson 6's labels
    are almost entirely fractions.
    """
    node_size = node_size or DAG_NODE_SIZE
    highlight = {tuple(e) for e in (highlight_edges or [])}
    highlight_nodes = list(highlight_nodes or [])
    hl_color = highlight_color or COLORS["accent"]

    frame_signed_axes(ax, pos, node_size=node_size, rad=0.0)

    for u, v in G.edges():
        is_hl = (u, v) in highlight
        rad = _reciprocal_rad(G, u, v) if curved_reciprocal else 0.0
        nx.draw_networkx_edges(
            G, pos, edgelist=[(u, v)], ax=ax,
            edge_color=hl_color if is_hl else GRAPH_STYLE["edge_color"],
            width=2.6 if is_hl else 1.4,
            arrows=True, arrowstyle="-|>", arrowsize=16,
            node_size=node_size, min_source_margin=15, min_target_margin=15,
            connectionstyle=f"arc3,rad={rad}",
        )

    other = [n for n in G.nodes() if n not in highlight_nodes]
    _draw_grouped_nodes(G, pos, ax, other, node_size, node_groups,
                        group_colors, group_legend)
    if highlight_nodes:
        nx.draw_networkx_nodes(
            G, pos, ax=ax, nodelist=highlight_nodes,
            node_color=GRAPH_STYLE["node_fill"],
            edgecolors=GRAPH_STYLE["highlight_node_edge_color"],
            linewidths=GRAPH_STYLE["highlight_node_edge_width"],
            node_size=node_size + GRAPH_STYLE["highlight_node_size_delta"],
        )

    if show_labels:
        nx.draw_networkx_labels(
            G, pos, labels=labels, ax=ax,
            font_size=DAG_LABEL_FONTSIZE, font_color=COLORS["text"],
        )

    # The SAME annotation machinery draw_graph uses — collision-aware placement,
    # wedge-fitted offsets, conditional self-decoding captions. Not a reimplementation.
    _draw_node_annotations(
        G, pos, ax, node_size=node_size,
        above=node_values, below=node_values_below,
        above_caption=value_caption, below_caption=below_caption,
        value_format=value_format,
    )

    ax.set_axis_off()
    return pos


# -----------------------------------------------------------------------------
# Graph rendering helper
# -----------------------------------------------------------------------------

def _exchange_value_label(v):
    """Plain-text label for a bargaining value / outside option — NO mathtext.

    Renders the small rationals that network-exchange outcomes use ("0", "1",
    "1/2", "1/3", "2/3", "1/4", "3/4") as PLAIN text — never ``$\\frac{..}{..}$``
    and never $-wrapped — echoing the Lesson-4 rule that plain integer/fraction
    labels must not go through mathtext (the double-wrap crash class). A string
    passes through verbatim; an int/float/Fraction is converted to a "p/q" (or
    "p") string, snapping floats to a small-denominator fraction when one matches
    closely so 0.3333.. renders as "1/3".
    """
    if isinstance(v, str):
        return v
    frac = Fraction(v).limit_denominator(1000)
    if frac.denominator == 1:
        return str(frac.numerator)
    return f"{frac.numerator}/{frac.denominator}"


# -----------------------------------------------------------------------------
# Free-direction annotation placement
# -----------------------------------------------------------------------------
#
# The value / outside-option rows are offset from a node by a fixed distance in
# points. Offsetting them straight up / straight down is right on a path layout,
# but on a diagonal layout an incident edge can leave the node at close to 90
# degrees and run straight through the label (5.1's stem: the C-D edge leaves C
# at -73 deg, and C's outside-option label sits at -90 deg — 17 deg apart, so the
# edge cuts the text).
#
# The fix is LOCAL and angle-driven: look only at the directions of the node's own
# incident edges and rotate the label into the free gap. No bbox measurement, so
# it needs no renderer and is scale-independent — which matches the measured
# failure (identical collision set at three figure sizes: it is driven by edge
# ANGLE, not by figure scale).

def _decimal_label(v, places=None):
    """Plain-text DECIMAL label — e.g. 0.307. No mathtext, no ``$``."""
    places = GRAPH_STYLE["score_decimal_places"] if places is None else places
    return f"{float(v):.{places}f}"


def _row_formatter(values, value_format="auto"):
    """Pick ONE formatter for a whole annotation row — fractions or decimals.

    Chosen per ROW, never per value: a row reading "1/2, 0.307, 1/16" would be
    unreadable, so the decision has to see every value before it is made.

    ``"auto"`` keeps exact fractions while they stay legible and switches the
    whole row to decimals once any denominator passes
    ``score_fraction_max_denominator``. That threshold is not arbitrary — it is
    set above every denominator the chapter actually prints (the worst are 1/32,
    9/29, 13/30, 7/17, 4/13), so every worked example in Ch.13-14 renders as the
    EXACT fraction the book shows, while the scaled rule at s = 0.85 — whose
    exact values are honestly things like 168/547 and 61/949 — renders as 0.307
    and 0.064. Both are the same number; only one of them teaches anything.
    """
    if value_format == "fraction":
        return _exchange_value_label
    if value_format == "decimal":
        return _decimal_label
    if value_format != "auto":
        raise ValueError(
            f"value_format must be 'auto', 'fraction' or 'decimal', "
            f"got {value_format!r}")

    cap = GRAPH_STYLE["score_fraction_max_denominator"]
    for v in values:
        if isinstance(v, str):
            continue                       # authored text passes through verbatim
        try:
            if Fraction(v).limit_denominator(10 ** 9).denominator > cap:
                return _decimal_label
        except (TypeError, ValueError):
            continue
    return _exchange_value_label


def _incident_angles(G, pos, node):
    """Directions (radians) of every edge touching ``node``, in data space.

    On a DIRECTED graph ``G.neighbors()`` yields SUCCESSORS ONLY. That is the
    wrong set for collision avoidance: an edge arriving at a node runs through
    the space beside it exactly as an edge leaving it does, so a label placed
    using out-edges alone will happily be dropped on top of an in-edge. Both
    directions are collected here (deduplicated, order preserved).

    An UNDIRECTED graph is untouched — ``neighbors()`` there already means every
    incident edge, and ``is_directed()`` is False — so ``draw_graph`` keeps its
    byte-identical placement.
    """
    if node not in pos:
        return []
    x, y = pos[node]
    nbrs = list(G.neighbors(node))
    if G.is_directed():
        seen = set(nbrs)
        nbrs += [p for p in G.predecessors(node) if p not in seen]
    angles = []
    for nb in nbrs:
        if nb == node or nb not in pos:
            continue
        dx, dy = pos[nb][0] - x, pos[nb][1] - y
        if dx or dy:
            angles.append(math.atan2(dy, dx))
    return angles


def _edge_clearance(theta, edge_angles):
    """Smallest angle (radians) between direction ``theta`` and any incident edge."""
    if not edge_angles:
        return math.pi
    return min(abs(math.remainder(theta - a, 2 * math.pi)) for a in edge_angles)


def _crosses_edge(base, tilt, edge_angles):
    """True if rotating from ``base`` by ``tilt`` sweeps PAST an incident edge."""
    for a in edge_angles:
        d = math.remainder(a - base, 2 * math.pi)   # edge's offset from base, (-pi, pi]
        if (tilt > 0 and 0 < d <= tilt) or (tilt < 0 and tilt <= d < 0):
            return True
    return False


def _free_direction(edge_angles, base, *, safe, max_tilt, step=math.radians(1)):
    """A direction for an annotation: ``base``, or the smallest rotation off it
    that clears every incident edge.

    Returns ``base`` unchanged whenever ``base`` already clears every incident
    edge by ``safe`` — which is every node of every path/horizontal layout, so
    those figures render exactly as they did before. Otherwise it rotates to the
    SMALLEST tilt reaching ``safe`` clearance, within two hard constraints:

    * ``max_tilt`` (< 90 deg) keeps the label on its own side of the node, so a
      value stays above and an outside option stays below. Without it, "maximize
      the angular gap" would park a leaf node's label straight out sideways —
      a regression on figures that are fine today, and a break of the above/below
      convention the rows are read by.
    * the label may never rotate PAST an incident edge. It stays in the angular
      gap it started in — the wedge between the two edges that bracket ``base``.
      This matters: on 5.1's stem, node C's two edges leave at -146 and -73 deg,
      so the wedge below C is only 73 deg wide and cannot offer more than 36 deg
      of clearance. Allowed to cross, the search would hop the C-D edge and park
      C's label out at -35 deg — clear of the edges, but hanging off C's lower
      RIGHT, reading as if it belonged to the C-D edge rather than to C. Pinned
      to the wedge, it settles on the bisector instead: the best placement the
      geometry actually admits, and still recognizably below C.

    So when the wedge is too narrow to reach ``safe``, this returns the freest
    direction inside it (the bisector) rather than a wider-clearance direction
    outside it. ``safe`` is a target, not a guarantee; the render gate is what
    proves the resulting pixel clearance.
    """
    best_gap = _edge_clearance(base, edge_angles)
    if best_gap >= safe:
        return base
    best = base
    for i in range(1, int(max_tilt / step) + 1):
        cands = []
        for sign in (-1, 1):
            tilt = sign * i * step
            if _crosses_edge(base, tilt, edge_angles):
                continue
            cands.append((_edge_clearance(base + tilt, edge_angles), base + tilt))
        if not cands:
            break
        cands.sort(key=lambda t: -t[0])
        if cands[0][0] >= safe:
            return cands[0][1]
        if cands[0][0] > best_gap:
            best_gap, best = cands[0]
    return best


def _fitted_distance(text, theta, edge_angles, base_dist):
    """How far out (points) a label must sit to clear every incident edge.

    The label is an axis-aligned box of estimated half-width ``hw`` and half-height
    ``hh``. For an edge leaving the node at angle ``a``, the box's extent TOWARD
    that edge is its support along the edge's normal, ``hw*|sin a| + hh*|cos a|``,
    while the label's centre stands ``dist * sin(theta - a)`` away from the edge
    line. Requiring the difference to be at least ``annotation_edge_margin`` and
    solving for ``dist`` gives the distance below; the largest over all incident
    edges wins.

    A label pointing straight down from a node on a horizontal path has
    ``sin(theta - a) = 1`` and a support of just ``hh``, so the requirement is far
    below the base offset and ``base_dist`` is returned untouched — which is why
    every clean figure stays byte-identical. It only bites in a narrow wedge,
    where ``sin(theta - a)`` is small and the label has to move out to fit.
    """
    fs = GRAPH_STYLE["value_annotation_size"]
    hw = 0.5 * max(len(str(text)), 1) * fs * GRAPH_STYLE["annotation_char_width"]
    hh = 0.5 * fs * GRAPH_STYLE["annotation_line_height"]
    margin = GRAPH_STYLE["annotation_edge_margin"]
    need = base_dist
    for a in edge_angles:
        delta = abs(math.remainder(theta - a, 2 * math.pi))
        # An edge is a RAY leaving the node, not an infinite line. If the label
        # points more than 90 deg away from it, the label is behind the edge's
        # origin and moving further out only increases the gap — the nearest point
        # of the ray is the node itself, which the base offset already clears. Such
        # an edge must not drive the distance: treating it as a line would make
        # sin(delta) collapse toward zero for a near-anti-parallel edge and demand
        # an enormous push (5.1's stem: D's edge to C leaves UPWARD at 107 deg while
        # D's outside-option label points DOWN, and D's label would be flung out to
        # the cap to "clear" an edge it is walking away from).
        if delta > math.pi / 2:
            continue
        sep = math.sin(delta)
        if sep < 1e-6:          # label points straight along the edge: pushing out
            continue            # cannot help; the tilt search is what avoids this
        support = hw * abs(math.sin(a)) + hh * abs(math.cos(a))
        need = max(need, (support + margin) / sep)
    return min(need, base_dist * GRAPH_STYLE["annotation_max_offset"])


def _tilt_ladder(span, step=math.radians(6)):
    """Tilts to try, smallest first, alternating sides: 0, +6, -6, +12, -12 ...

    Smallest-first keeps a nudged label as close to its canonical above/below
    position as the geometry allows — the point is to clear the collision, not to
    wander. Alternating sides keeps the search unbiased between left and right.
    """
    yield 0.0
    i = 1
    while i * step <= span:
        yield i * step
        yield -i * step
        i += 1


def _data_per_point(ax):
    """Data units per typographic point. ``None`` if the axes has no extent yet.

    The placement search below reasons in DATA space (nodes and edges live
    there), but label offsets are in POINTS. This is the bridge. Equal aspect is
    already locked by ``frame_signed_axes``, so one scale serves both axes.
    """
    try:
        bb = ax.get_window_extent()
    except Exception:
        return None
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    if bb.width <= 0 or bb.height <= 0 or x1 == x0 or y1 == y0:
        return None
    # EQUAL ASPECT (locked by frame_signed_axes) means the data box is fitted
    # inside the axes box preserving shape, so the BINDING dimension is whichever
    # needs more room per pixel — and it is not always x. A tall, narrow layout
    # (Fig 14.16's two stacked columns) is bound by y: assuming x, as this did at
    # first, understates the data-per-point scale, which shrinks every computed
    # label box and makes the collision search declare a clean figure that is not.
    # The symptom is diagnostic and counter-intuitive: giving a tall graph MORE
    # vertical room made the collisions WORSE, because more y-range meant more
    # compression, and the error scaled with it. Taking the max fixes it.
    return max(abs(x1 - x0) / bb.width,
               abs(y1 - y0) / bb.height) * (ax.figure.dpi / 72.0)


def _seg_box_clear(box, p, q, margin):
    """Is the segment p-q clear of the axis-aligned ``box`` (cx, cy, hw, hh)?"""
    cx, cy, hw, hh = box
    hw, hh = hw + margin, hh + margin
    (px, py), (qx, qy) = p, q
    # Separating-axis on the box's two axes: if the segment's extent misses the
    # slab on either axis, they cannot touch.
    if max(px, qx) < cx - hw or min(px, qx) > cx + hw:
        return True
    if max(py, qy) < cy - hh or min(py, qy) > cy + hh:
        return True
    # Separating axis along the segment's own normal.
    dx, dy = qx - px, qy - py
    if dx == 0 and dy == 0:
        return False
    nx_, ny_ = -dy, dx
    norm = math.hypot(nx_, ny_)
    nx_, ny_ = nx_ / norm, ny_ / norm
    dist = abs((cx - px) * nx_ + (cy - py) * ny_)
    reach = hw * abs(nx_) + hh * abs(ny_)
    return dist > reach


def _boxes_overlap(a, b, margin):
    return (abs(a[0] - b[0]) < a[2] + b[2] + margin
            and abs(a[1] - b[1]) < a[3] + b[3] + margin)


def _placement_cost(box, node, pos, edges_xy, placed, node_r, margin):
    """How badly a candidate label box collides. 0 == clean.

    Counts every edge in the WHOLE graph, not just the node's own — which is the
    generalization L6 forced. A label on a dense layered graph collides with
    edges that merely pass NEARBY (in Fig 14.6 the long D→A / E→A links run right
    past B and C), and with OTHER nodes' labels. The 0.7.0 rule looked only at a
    node's incident edges, which is why those collisions got through: on Lesson
    5's sparse graphs there was nothing else close enough to hit.
    """
    cost = 0
    for (p, q) in edges_xy:
        if not _seg_box_clear(box, p, q, margin):
            cost += 2
    for other in placed:
        if _boxes_overlap(box, other, margin):
            cost += 3
    for n, (x, y) in pos.items():
        if n == node:
            continue
        if _boxes_overlap(box, (x, y, node_r, node_r), margin * 0.5):
            cost += 3
    return cost


def _annotate_offset(ax, ax_xy, text, theta, dist, gid, **kw):
    """Place ``text`` at ``dist`` POINTS from ``ax_xy`` along direction ``theta``.

    Stays horizontally centred on the offset point and sits above it (value) or
    below it (outside option) — the same anchoring an untilted label has always
    used, so a label that does not tilt lands exactly where it used to.
    """
    art = ax.annotate(
        text, xy=ax_xy, textcoords="offset points",
        xytext=(dist * math.cos(theta), dist * math.sin(theta)),
        ha="center", va=("bottom" if math.sin(theta) >= 0 else "top"),
        annotation_clip=False,
        fontsize=GRAPH_STYLE["value_annotation_size"],
        family="sans-serif", color=COLORS["text"], **kw,
    )
    art.set_gid(gid)
    return art


def _draw_node_annotations(G, pos, ax, *, node_size, above=None, below=None,
                           above_caption=None, below_caption=None,
                           pendant_stub=False, value_format="fraction"):
    """Annotate an ABOVE row and a BELOW row of per-node values, with a caption.

    THE ONE PLACE node-value annotation happens. ``draw_graph`` (undirected) and
    ``draw_directed_graph`` both call it, so the collision-aware placement rules
    that 0.7.0 built — angle-driven free-direction search, wedge-fitted radial
    distance, conditional self-decoding row captions — apply identically to a
    directed figure without being reimplemented for it. A second copy of this
    logic is exactly how the two renderers drifted apart in the first place.

    The two rows are GENERIC (an above row and a below row); the CALLER supplies
    what they mean via the captions. Lesson 5 reads them as "value" / "outside
    option"; Lesson 6 reads them as e.g. "hub score" / "authority score" — the
    same machinery, because the placement problem is identical and only the
    words change.

    Rows are filtered to nodes that are actually drawn, and the caption names
    only the rows that survive that filter — so a row that empties out
    mid-interaction takes its caption with it rather than stranding a heading
    over nothing.
    """
    value_row = {n: v for n, v in (above or {}).items() if n in pos}
    outside_row = {n: v for n, v in (below or {}).items() if n in pos}
    if not (value_row or outside_row):
        return

    # ONE formatter across BOTH rows — a figure that mixed "1/2" above with
    # "0.307" below would read as two different quantities.
    fmt = _row_formatter(list(value_row.values()) + list(outside_row.values()),
                         value_format)

    radius_pts = math.sqrt(node_size / math.pi)
    annot_offset = radius_pts + GRAPH_STYLE["value_annotation_gap"]
    safe = math.radians(GRAPH_STYLE["annotation_free_angle"])
    max_tilt = math.radians(GRAPH_STYLE["annotation_max_tilt"])
    up, down = math.pi / 2, -math.pi / 2

    below_reach = []   # how far below its node each below-label hangs, in points

    # Global collision context. `dpp` converts the point-based label offsets into
    # the data space the nodes and edges live in; when the axes has no extent yet
    # it is None and the search degrades to the 0.7.0 local rule, which is a safe
    # floor rather than a crash.
    dpp = _data_per_point(ax)
    edges_xy = [(pos[u], pos[v]) for u, v in G.edges()
                if u in pos and v in pos and u != v]
    node_r = math.sqrt(node_size / math.pi) * (dpp or 0)
    placed = []

    def place(node, val, base, gid, base_dist=None):
        """Position one label: keep the 0.7.0 placement if it is clean, else move.

        THE DEFAULT PATH IS BIT-FOR-BIT THE OLD ONE. The angle-driven local
        placement is computed exactly as before and, if it collides with nothing,
        used verbatim — so every figure that was already clean (all 681 in the
        deployed corpus) is untouched, and this cannot regress them. Only a label
        that would actually land on an edge, a node, or another label enters the
        search below. Same discipline as 0.7.0's tilt rule: bite only when there
        is something to fix.
        """
        edges = _incident_angles(G, pos, node)
        label = fmt(val)
        theta = _free_direction(edges, base, safe=safe, max_tilt=max_tilt)
        dist = base_dist if base_dist is not None else annot_offset
        dist = _fitted_distance(label, theta, edges, dist)

        if dpp:
            hw = 0.5 * max(len(label), 1) * GRAPH_STYLE["value_annotation_size"] \
                * GRAPH_STYLE["annotation_char_width"] * dpp
            hh = 0.5 * GRAPH_STYLE["value_annotation_size"] \
                * GRAPH_STYLE["annotation_line_height"] * dpp
            margin = GRAPH_STYLE["annotation_edge_margin"] * dpp * 0.5

            def box_at(th, d):
                x, y = pos[node]
                return (x + d * dpp * math.cos(th), y + d * dpp * math.sin(th),
                        hw, hh)

            best = (theta, dist)
            best_cost = _placement_cost(box_at(theta, dist), node, pos, edges_xy,
                                        placed, node_r, margin)
            if best_cost:
                # Widen the search: the label may swing further off vertical and
                # stand further out than the local rule would ever have moved it.
                span = math.radians(GRAPH_STYLE["annotation_collision_max_tilt"])
                for mult in GRAPH_STYLE["annotation_collision_distances"]:
                    for tilt in _tilt_ladder(span):
                        th = base + tilt
                        d = dist * mult
                        c = _placement_cost(box_at(th, d), node, pos, edges_xy,
                                            placed, node_r, margin)
                        if c < best_cost:
                            best_cost, best = c, (th, d)
                        if not best_cost:
                            break
                    if not best_cost:
                        break
            theta, dist = best
            placed.append(box_at(theta, dist))

        _annotate_offset(ax, pos[node], label, theta, dist, gid)
        return dist

    for node, val in value_row.items():
        place(node, val, up, "cs470:value")

    for node, val in outside_row.items():
        if not pendant_stub:
            # Same collision-aware search as the above row. The pendant path
            # below is left exactly as it was: its geometry is tuned to the
            # fixed-length stub it hangs off, and its only consumers (Lesson 5's
            # wide horizontal paths) are already collision-free.
            below_reach.append(place(node, val, down, "cs470:outside"))
            continue

        edges = _incident_angles(G, pos, node)
        theta = _free_direction(edges, down, safe=safe, max_tilt=max_tilt)
        label = fmt(val)
        dist = _fitted_distance(label, theta, edges, annot_offset)
        if pendant_stub:
            # A stub of FIXED length in points — drawn as an annotate offset so it
            # lives in display space. (The old rule took a fraction of the median
            # edge length, a DATA-unit quantity, and applied it along y; on a flat
            # layout the y data->display scale explodes and the stub ran ~30x long.)
            # zorder 0 tucks it under the node marker, so the stub reads as leaving
            # the circle rather than starting at its center.
            stub = GRAPH_STYLE["pendant_stub_len_pts"]
            ax.annotate(
                "", xy=pos[node], xycoords="data",
                textcoords="offset points",
                xytext=(stub * math.cos(theta), stub * math.sin(theta)),
                arrowprops=dict(
                    arrowstyle="-", shrinkA=0, shrinkB=0,
                    linestyle=GRAPH_STYLE["pendant_stub_style"],
                    color=GRAPH_STYLE["pendant_stub_color"],
                    linewidth=GRAPH_STYLE["pendant_stub_width"],
                ),
                annotation_clip=False, zorder=0,
            )
            # The STUB is fixed-length; the LABEL still has to clear the wedge. On
            # the pendant's intended consumers (wide horizontal paths) nothing is
            # tilted, so the label lands right off the stub end as designed; in a
            # tight wedge it slides further out rather than being pulled back into
            # an incident edge.
            dist = _fitted_distance(label, theta, edges,
                                    stub + GRAPH_STYLE["pendant_label_gap"])
        below_reach.append(dist)
        _annotate_offset(ax, pos[node], label, theta, dist, "cs470:outside")

    # Row caption — CONDITIONAL. Names only the rows that are populated, so a
    # figure carrying just one row announces that row and nothing else, and a row
    # that disappears mid-interaction takes its caption with it (5.1's no-deal
    # region drops the value row, and a static heading would be left stranded
    # over an empty row).
    #
    # Anchored to the CONTENT, not to an axes fraction: y at the lowest node in
    # DATA coords, then dropped a fixed number of POINTS below the deepest label
    # that hangs off it. An axes-fraction anchor is not usable here — the axes box
    # bears no fixed relation to the drawn graph (equal aspect leaves slack, and a
    # 2-node layout is degenerate in y), so "6% below the axes" lands inside the
    # figure on the stem and far adrift on the 2-node one. x rides the axes centre.
    caption = GRAPH_STYLE["row_caption_sep"].join(
        part for part, present in (
            (above_caption, value_row),
            (below_caption, outside_row),
        ) if present and part
    )
    if caption:
        drop = (max(below_reach, default=annot_offset)
                + GRAPH_STYLE["value_annotation_size"] * GRAPH_STYLE["annotation_line_height"]
                + GRAPH_STYLE["row_caption_gap"])
        anchor = mtransforms.blended_transform_factory(ax.transAxes, ax.transData)
        cap = ax.annotate(
            caption, xy=(0.5, min(y for _, y in pos.values())), xycoords=anchor,
            textcoords="offset points", xytext=(0, -drop),
            ha="center", va="top", annotation_clip=False,
            fontsize=GRAPH_STYLE["row_caption_size"],
            family="sans-serif", color=GRAPH_STYLE["row_caption_color"],
        )
        cap.set_gid("cs470:rowcap")


def _resolve_group_colors(groups, group_colors=None):
    """Map each group name to a palette color, in first-appearance order.

    A caller may pin any subset via ``group_colors`` (naming either a ``COLORS``
    token — "accent" — or a literal color). Unpinned groups take the bow-tie
    semantic color if their name is a bow-tie role, else the next color off
    ``GROUP_COLOR_CYCLE``. No literals here or in the render code: every color
    resolves to a ``COLORS`` token.
    """
    pinned = {}
    for g, c in (group_colors or {}).items():
        pinned[g] = COLORS.get(c, c)      # a COLORS token, or a literal color

    seen = []
    for g in groups:
        if g not in seen:
            seen.append(g)                # first-appearance order == stable

    out = {}
    nxt = 0
    for g in seen:
        if g in pinned:
            out[g] = pinned[g]
        elif g in BOWTIE_COLORS:
            out[g] = BOWTIE_COLORS[g]
        else:
            out[g] = GROUP_COLOR_CYCLE[nxt % len(GROUP_COLOR_CYCLE)]
            nxt += 1
    return out


def _draw_group_legend(ax, colors_by_group):
    """A legend decoding the node colors — the figure must decode ITSELF.

    A node colored orange means nothing without this. Same principle as the
    conditional row caption: an annotation the reader cannot decode from the
    figure alone is a defect, not a decoration.
    """
    if not colors_by_group:
        return
    handles = [
        mlines.Line2D([], [], marker="o", linestyle="none",
                      markersize=GRAPH_STYLE["group_legend_marker_size"],
                      markerfacecolor=c, markeredgecolor=c,
                      alpha=GRAPH_STYLE["group_fill_alpha"], label=str(g))
        for g, c in colors_by_group.items()
    ]
    leg = ax.legend(
        handles=handles, loc="upper center",
        bbox_to_anchor=GRAPH_STYLE["group_legend_anchor"],
        ncol=min(len(handles), GRAPH_STYLE["group_legend_max_cols"]),
        frameon=False, handletextpad=0.3, columnspacing=1.1,
        fontsize=GRAPH_STYLE["group_legend_size"],
    )
    for txt in leg.get_texts():
        txt.set_color(COLORS["text"])


def draw_graph(
    G,
    ax,
    *,
    pos=None,
    highlight_nodes=None,
    highlight_edges=None,
    edge_styles=None,
    seed=42,
    node_size=None,
    show_labels=True,
    matched_edges=None,
    node_values=None,
    outside_options=None,
    pendant_stub=False,
    node_groups=None,
    group_colors=None,
    group_legend=True,
):
    """Draw a networkx graph in the project's style.

    Defaults to open-circle nodes (white fill, navy border) and solid navy
    edges. Edges with attribute ``strength='weak'`` or ``style='dashed'``
    are rendered dashed. Highlighted nodes and edges use accent orange with
    thicker stroke.

    Edges carrying a ``sign`` attribute (``'pos'`` / ``'neg'``, as emitted by
    structural-balance worksheet YAML) are drawn as **signed edges**: gently
    curved, colored by sign (positive navy, negative red), with a ``+`` / ``$-$``
    mathtext label at the curved-arc apex. The Arches highlight color marks a
    highlighted signed edge. Edges WITHOUT a ``sign`` attribute are completely
    unaffected by this and render exactly as before.

    The ``matched_edges`` / ``node_values`` / ``outside_options`` / ``pendant_stub``
    parameters are an ADDITIVE Lesson-5 network-exchange layer: they annotate an
    outcome (a matching + node values + endogenous outside options) on top of an
    ordinary structure figure. They all default off, and when unused the output
    is byte-identical to the pre-Lesson-5 renderer.

    Parameters
    ----------
    G : networkx.Graph
        The graph to render.
    ax : matplotlib.axes.Axes
        The axes to draw into. The function calls ``ax.set_axis_off()``
        before returning.
    pos : dict, optional
        Position dict mapping node id -> (x, y). If None, computed via
        spring layout with the given seed.
    highlight_nodes : list, optional
        Node IDs to draw in accent orange.
    highlight_edges : list of tuples, optional
        Edges to draw in accent orange. Either orientation accepted.
    edge_styles : dict, optional
        Mapping ``(u, v) -> "solid" | "dashed"`` to override default styling
        derived from edge attributes.
    seed : int
        Layout seed (used only when pos is None) for reproducibility.
    node_size : int
        Default node marker size.
    show_labels : bool
        Whether to draw node labels.
    matched_edges : list of tuples, optional
        Edges of a network-exchange matching, drawn with the **bold-black
        matched-edge token** (``GRAPH_STYLE["matched_edge_*"]``). This is a
        distinct token from ``highlight_edges`` (accent orange), so a figure can
        show a matching in bold black AND highlight some node/edge in accent at
        the same time. Either orientation accepted. If a matched edge is also in
        ``highlight_edges`` it is drawn bold-and-accent (bold width, accent
        color); normally the two sets are disjoint.
    node_values : dict, optional
        Mapping ``node -> value`` (the outcome's split, e.g. ``Fraction(1, 3)``
        or ``"1/3"``), drawn as a PLAIN-text annotation ABOVE the node. Numbers
        are formatted via ``_exchange_value_label`` (no ``$``/mathtext).
    outside_options : dict, optional
        Mapping ``node -> value`` drawn as a PLAIN-text annotation BELOW the
        node — the node's best outside option in the outcome.
    pendant_stub : bool
        When True, each node in ``outside_options`` also gets a short dashed
        "pendant stub" half-edge dangling toward its outside-option label
        (cf. Figures 12.6/12.8/12.9). No effect unless ``outside_options`` is set.

    Returns
    -------
    pos : dict
        The position dict used. Useful for chained calls or annotations.
    """
    if pos is None:
        pos = nx.spring_layout(G, seed=seed)
    if node_size is None:
        node_size = GRAPH_STYLE["node_size"]

    edge_styles = edge_styles or {}
    highlight_nodes = highlight_nodes or []
    highlight_edges = highlight_edges or []
    matched_edges = matched_edges or []
    node_values = node_values or {}
    outside_options = outside_options or {}

    def _style_for(u, v):
        explicit = edge_styles.get((u, v)) or edge_styles.get((v, u))
        if explicit:
            return explicit
        data = G.get_edge_data(u, v) or {}
        if data.get("strength") == "weak" or data.get("style") == "dashed":
            return GRAPH_STYLE["weak_edge_style"]
        return "solid"

    # Normalize highlight edges to canonical (sorted) tuple for matching
    highlight_set = {tuple(sorted((u, v))) for u, v in highlight_edges}
    def _is_highlighted(u, v):
        return tuple(sorted((u, v))) in highlight_set

    # Matched edges (network-exchange outcome). Empty by default, so the two
    # `_is_matched` filters below are no-ops and the legacy partition is
    # byte-identical unless a caller actually passes matched_edges.
    matched_set = {tuple(sorted((u, v))) for u, v in matched_edges}
    def _is_matched(u, v):
        return tuple(sorted((u, v))) in matched_set

    # Signed edges (structural-balance figures) get the curve + apex-label +
    # sign-color treatment. Edges WITHOUT a `sign` attribute fall through to the
    # legacy path below and render exactly as before — no label, no color/style
    # change, no curvature — so unsigned graphs (e.g. 1.1's tie/triad figures)
    # are visually unchanged.
    signed_edges = [(u, v) for u, v in G.edges()
                    if _SIGN_KEY in (G.get_edge_data(u, v) or {})]
    if signed_edges:
        _draw_signed_edges(
            G, pos, ax, signed_edges,
            highlight_set=highlight_set, node_size=node_size,
        )
    signed_set = {tuple(sorted(e)) for e in signed_edges}

    # Legacy (unsigned) edges partitioned by style and highlight status.
    unsigned = [(u, v) for u, v in G.edges()
                if tuple(sorted((u, v))) not in signed_set]
    solid_all = [(u, v) for u, v in unsigned if _style_for(u, v) == "solid"]
    dashed_all = [(u, v) for u, v in unsigned
                  if _style_for(u, v) == GRAPH_STYLE["weak_edge_style"]]

    # Matched edges are pulled OUT of the legacy passes and drawn with the
    # bold-black matched token below. `_is_matched` is always False when no
    # matched_edges were passed, so these filters change nothing by default.
    base_solid = [e for e in solid_all
                  if not _is_highlighted(*e) and not _is_matched(*e)]
    base_dashed = [e for e in dashed_all
                   if not _is_highlighted(*e) and not _is_matched(*e)]
    hl_solid = [e for e in solid_all
                if _is_highlighted(*e) and not _is_matched(*e)]
    hl_dashed = [e for e in dashed_all
                 if _is_highlighted(*e) and not _is_matched(*e)]

    if base_solid:
        nx.draw_networkx_edges(
            G, pos, ax=ax, edgelist=base_solid,
            edge_color=GRAPH_STYLE["edge_color"],
            width=GRAPH_STYLE["edge_width"],
        )
    if base_dashed:
        nx.draw_networkx_edges(
            G, pos, ax=ax, edgelist=base_dashed,
            edge_color=GRAPH_STYLE["edge_color"],
            width=GRAPH_STYLE["edge_width"],
            style=GRAPH_STYLE["weak_edge_style"],
        )
    if hl_solid:
        nx.draw_networkx_edges(
            G, pos, ax=ax, edgelist=hl_solid,
            edge_color=GRAPH_STYLE["highlight_edge_color"],
            width=GRAPH_STYLE["highlight_edge_width"],
        )
    if hl_dashed:
        nx.draw_networkx_edges(
            G, pos, ax=ax, edgelist=hl_dashed,
            edge_color=GRAPH_STYLE["highlight_edge_color"],
            width=GRAPH_STYLE["highlight_edge_width"],
            style=GRAPH_STYLE["weak_edge_style"],
        )

    # Matched-edge pass (bold BLACK). Drawn as bold solid regardless of the
    # edge's default style, echoing the chapter's "darkened edges". A matched
    # edge that is ALSO highlighted keeps the bold width but takes the accent
    # color, so "emphasize a matched edge" stays legible; normally the matched
    # and highlight sets are disjoint. Skipped entirely (lists empty) by default.
    matched_present = [(u, v) for u, v in unsigned if _is_matched(u, v)]
    matched_plain = [e for e in matched_present if not _is_highlighted(*e)]
    matched_hl = [e for e in matched_present if _is_highlighted(*e)]
    if matched_plain:
        nx.draw_networkx_edges(
            G, pos, ax=ax, edgelist=matched_plain,
            edge_color=GRAPH_STYLE["matched_edge_color"],
            width=GRAPH_STYLE["matched_edge_width"],
        )
    if matched_hl:
        nx.draw_networkx_edges(
            G, pos, ax=ax, edgelist=matched_hl,
            edge_color=GRAPH_STYLE["highlight_edge_color"],
            width=GRAPH_STYLE["matched_edge_width"],
        )

    # Nodes: highlighted ones drawn with thicker accent-color edge. When
    # node_groups is supplied the un-highlighted nodes are drawn per-group
    # instead (categorical fill + matching border); highlight still wins on top,
    # so "color by bow-tie role AND mark the node under discussion" composes.
    other = [n for n in G.nodes() if n not in highlight_nodes]
    if other:
        _draw_grouped_nodes(G, pos, ax, other, node_size, node_groups,
                            group_colors, group_legend)
    if highlight_nodes:
        nx.draw_networkx_nodes(
            G, pos, ax=ax, nodelist=highlight_nodes,
            node_color=GRAPH_STYLE["node_fill"],
            edgecolors=GRAPH_STYLE["highlight_node_edge_color"],
            linewidths=GRAPH_STYLE["highlight_node_edge_width"],
            node_size=node_size + GRAPH_STYLE["highlight_node_size_delta"],
        )

    if show_labels:
        # Format letter+digit ids as subscripts (m2 -> $m_2$); all other labels
        # (plain letters, digits, names) pass through unchanged.
        labels = {n: subscript_label(n) for n in G.nodes()}
        nx.draw_networkx_labels(
            G, pos, ax=ax, labels=labels,
            font_family=GRAPH_STYLE["label_font_family"],
            font_size=GRAPH_STYLE["label_font_size"],
        )

    # Bargaining-outcome annotations (Lesson 5). Both default off. The placement
    # machinery is shared with draw_directed_graph — see _draw_node_annotations.
    _draw_node_annotations(
        G, pos, ax, node_size=node_size,
        above=node_values, below=outside_options,
        above_caption=GRAPH_STYLE["value_row_caption"],
        below_caption=GRAPH_STYLE["outside_row_caption"],
        pendant_stub=pendant_stub,
    )

    ax.set_axis_off()
    return pos


# -----------------------------------------------------------------------------
# Generic matrix / iteration-table renderer (Lesson 6)
# -----------------------------------------------------------------------------
#
# Nothing generic existed: draw_payoff_matrix is 2-player-game-specific and
# draw_auction_table is auction-specific, so the adjacency matrix M, the flow
# matrix N, the scaled matrix Ñ and the k-step score tables all had nowhere to
# land. One renderer covers both shapes, because they differ only in chrome:
#
#   style="matrix" — bracketed grid, labels OUTSIDE the brackets. It is a matrix:
#                    an object with rows and columns, and the brackets say so.
#   style="table"  — booktabs rules, a header row and a label column. It is a
#                    table: a log of iterations, read down the steps.

MATRIX_STYLE = {
    "cell_fontsize":    11,
    "label_fontsize":   11,
    "header_fontsize":  11,
    "corner_fontsize":  10,
    "title_fontsize":   12,
    "note_fontsize":    10,
    "cell_w":           1.0,        # axes units
    "cell_h":           0.62,
    "label_color":      COLORS["primary"],
    "cell_color":       COLORS["text"],
    "bracket_color":    COLORS["primary"],
    "bracket_width":    1.6,
    "bracket_tick":     0.16,       # serif length on the [ ] arms
    "bracket_pad":      0.30,
    "rule_color":       COLORS["primary"],
    "rule_width":       1.4,
    "thin_rule_width":  0.7,
    "highlight_fill":   COLORS["highlight"],
    "highlight_alpha":  0.20,
    "highlight_text":   COLORS["accent"],
    "note_color":       COLORS["primary"],
}


def draw_matrix(ax, values, *, row_labels=None, col_labels=None, corner=None,
                style="matrix", highlight_cells=None, highlight_rows=None,
                title=None, note=None, row_title=None, col_title=None,
                value_format="auto"):
    """Render a matrix (bracketed) or an iteration table (booktabs) on ``ax``.

    ``values``  — a 2D sequence. Entries may be int / float / Fraction / str and
    render as PLAIN TEXT, so ``Fraction(4, 13)`` becomes ``4/13`` and never
    ``$\\frac{4}{13}$``. Figure labels must not go through mathtext — matplotlib
    decides mathtext on the PARITY of ``$`` in the whole string, so a stray one
    silently swallows the rest of the label (the Lesson-4 double-wrap crash
    class). Lesson 6's cells are almost all fractions, which is exactly where
    this bites.

    ``value_format`` picks fractions or decimals for the WHOLE grid at once (see
    ``_row_formatter``): the flow matrix N is exact small fractions, but the
    scaled Ñ at s = 0.85 is not, and a grid mixing the two would be unreadable.

    ``highlight_cells`` — ``[(i, j), ...]`` tinted and re-colored: "here is the
    entry the question is about". ``highlight_rows`` — ``[i, ...]``, for marking
    the step of an iteration table under discussion.

    ``corner`` is the top-left cell (e.g. ``"step"``); ``row_title`` /
    ``col_title`` are axis names written outside the labels (e.g. ``"from"`` /
    ``"to"`` on an adjacency matrix, which is the distinction the whole M-vs-Mᵀ
    confusion turns on).
    """
    if style not in ("matrix", "table"):
        raise ValueError(f"style must be 'matrix' or 'table', got {style!r}")

    st = MATRIX_STYLE
    rows = [list(r) for r in values]
    nrow = len(rows)
    ncol = len(rows[0]) if nrow else 0
    if not nrow or not ncol:
        ax.set_axis_off()
        return

    row_labels = list(row_labels or [""] * nrow)
    col_labels = list(col_labels or [""] * ncol)
    hl_cells = {tuple(c) for c in (highlight_cells or [])}
    hl_rows = set(highlight_rows or [])

    cw, ch = st["cell_w"], st["cell_h"]
    has_rowlab = any(str(x) for x in row_labels) or corner
    x0 = cw if has_rowlab else 0.0            # grid starts after the label column
    y0 = 0.0                                  # header row sits above y0

    def cx(j):
        return x0 + (j + 0.5) * cw

    def cy(i):
        return y0 - (i + 0.5) * ch

    ax.set_xlim(-0.15 * cw, x0 + ncol * cw + 0.15 * cw)
    ax.set_ylim(-(nrow * ch) - 1.15 * ch, 1.45 * ch)
    ax.set_aspect("auto")
    ax.autoscale(False)
    ax.set_axis_off()

    # tints first, so text and rules land on top
    for i in range(nrow):
        if i in hl_rows:
            ax.add_patch(Rectangle((x0, cy(i) - ch / 2), ncol * cw, ch,
                                   facecolor=st["highlight_fill"],
                                   alpha=st["highlight_alpha"],
                                   edgecolor="none", zorder=0))
    for (i, j) in hl_cells:
        if 0 <= i < nrow and 0 <= j < ncol:
            ax.add_patch(Rectangle((x0 + j * cw, cy(i) - ch / 2), cw, ch,
                                   facecolor=st["highlight_fill"],
                                   alpha=st["highlight_alpha"],
                                   edgecolor="none", zorder=0))

    # column headers
    for j, lab in enumerate(col_labels):
        if str(lab):
            ax.text(cx(j), y0 + 0.42 * ch, str(lab), ha="center", va="center",
                    fontsize=st["header_fontsize"],
                    fontweight="bold" if style == "table" else "normal",
                    color=st["label_color"])
    # row labels
    for i, lab in enumerate(row_labels):
        if str(lab):
            ax.text(x0 - 0.35 * cw, cy(i), str(lab), ha="right", va="center",
                    fontsize=st["label_fontsize"],
                    fontweight="bold" if style == "table" else "normal",
                    color=st["label_color"])
    if corner:
        ax.text(x0 - 0.35 * cw, y0 + 0.42 * ch, str(corner),
                ha="right", va="center", fontsize=st["corner_fontsize"],
                fontweight="bold" if style == "table" else "normal",
                color=st["label_color"])

    # cells — one formatter for the whole grid, decided over every entry
    fmt = _row_formatter([v for r in rows for v in r], value_format)
    for i in range(nrow):
        for j in range(ncol):
            hot = (i, j) in hl_cells
            ax.text(cx(j), cy(i), fmt(rows[i][j]),
                    ha="center", va="center", fontsize=st["cell_fontsize"],
                    color=st["highlight_text"] if hot else st["cell_color"],
                    fontweight="bold" if hot else "normal")

    if style == "matrix":
        # square brackets around the numeric grid (NOT around the labels)
        pad = st["bracket_pad"] * ch
        top, bot = y0 - pad * 0.4, y0 - nrow * ch + pad * 0.4
        left, right = x0 - 0.10 * cw, x0 + ncol * cw + 0.10 * cw
        tick = st["bracket_tick"] * cw
        for xx, dx in ((left, tick), (right, -tick)):
            ax.plot([xx, xx], [top, bot], color=st["bracket_color"],
                    linewidth=st["bracket_width"], zorder=3)
            ax.plot([xx, xx + dx], [top, top], color=st["bracket_color"],
                    linewidth=st["bracket_width"], zorder=3)
            ax.plot([xx, xx + dx], [bot, bot], color=st["bracket_color"],
                    linewidth=st["bracket_width"], zorder=3)
    else:
        # booktabs rules: top, under the header, bottom
        for yy, w in ((y0 + 0.18 * ch, st["rule_width"]),
                      (y0, st["thin_rule_width"]),
                      (y0 - nrow * ch, st["rule_width"])):
            ax.plot([x0 - cw if has_rowlab else x0, x0 + ncol * cw], [yy, yy],
                    color=st["rule_color"], linewidth=w, zorder=2)

    if col_title:
        ax.text(x0 + ncol * cw / 2, y0 + 1.05 * ch, str(col_title),
                ha="center", va="center", fontsize=st["note_fontsize"],
                style="italic", color=st["note_color"])
    if row_title:
        ax.text(x0 - 1.15 * cw, y0 - nrow * ch / 2, str(row_title),
                ha="center", va="center", fontsize=st["note_fontsize"],
                style="italic", color=st["note_color"], rotation=90)
    if title:
        ax.set_title(str(title), fontsize=st["title_fontsize"],
                     color=COLORS["primary"], pad=8)
    if note:
        ax.text(x0 + ncol * cw / 2, y0 - nrow * ch - 0.65 * ch, str(note),
                ha="center", va="center", fontsize=st["note_fontsize"],
                color=st["note_color"])


# -----------------------------------------------------------------------------
# Payoff-matrix game-theory helpers (Lesson 2)
# -----------------------------------------------------------------------------
#
# A payoff matrix is an n x m grid; each cell is a (row_player, col_player)
# payoff pair. We store it as ``payoffs[i][j] = (p_row, p_col)`` with row i a
# row-player strategy and column j a column-player strategy — matching the
# Easley-Kleinberg convention (row-player payoff listed first in each box).
#
# These COMPUTE helpers are the single source of truth for best responses,
# pure Nash equilibria, and strict-dominance deletion. The renderer below and
# the Stage-2 ipywidgets wrappers both call them, so a highlighted figure can
# never drift from the answer key — the highlight IS the computation.
#
# Best-response / Nash use WEAK comparison (``>=``) so tie-induced equilibria
# are caught. Dominated-strategy deletion uses STRICT comparison (``>``),
# matching the textbook's "strictly dominated."

#: Game-theory figure styling. Kept here (no inline literals in render code).
PAYOFF_STYLE = {
    "cell_size_in":     1.15,   # per-cell side length (inches), pre-margin
    "margin_in":        0.95,   # left/top margin for player + strategy labels
    "payoff_fontsize":  13,
    "strategy_fontsize": 12,
    "player_fontsize":  12,
    "grid_color":       COLORS["primary"],
    "grid_width":       1.3,
    "br_color":         COLORS["highlight"],   # best-response underline (Arches)
    "nash_fill":        COLORS["highlight"],    # NE cell tint
    "nash_fill_alpha":  0.16,
    "nash_edge":        COLORS["primary"],
    "deleted_alpha":    0.28,    # struck-out (deleted) row/col fade
    "deleted_color":    COLORS["bad"],
}


def _payoff_value(payoffs, i, j, player):
    """One player's payoff in cell (i, j). ``player`` is 0 (row) or 1 (col)."""
    return payoffs[i][j][player]


def best_responses(payoffs, player):
    """Cells that are a WEAK best response for ``player`` (0 row, 1 col).

    For the row player (0): in each column j, every row i whose row-payoff
    equals the column's maximum row-payoff. For the col player (1): in each
    row i, every column j whose col-payoff equals that row's maximum
    col-payoff. Returns a set of ``(i, j)`` tuples. Weak (``>=``) so ties are
    all included — required to catch tie-induced Nash equilibria.
    """
    n = len(payoffs)
    m = len(payoffs[0]) if n else 0
    cells = set()
    if player == 0:
        for j in range(m):
            best = max(_payoff_value(payoffs, i, j, 0) for i in range(n))
            for i in range(n):
                if _payoff_value(payoffs, i, j, 0) == best:
                    cells.add((i, j))
    else:
        for i in range(n):
            best = max(_payoff_value(payoffs, i, j, 1) for j in range(m))
            for j in range(m):
                if _payoff_value(payoffs, i, j, 1) == best:
                    cells.add((i, j))
    return cells


def pure_nash(payoffs):
    """Pure-strategy Nash equilibria as a sorted list of ``(i, j)`` cells.

    A cell is a pure NE iff the row strategy is a weak best response in its
    column AND the column strategy is a weak best response in its row — i.e.
    the cell is in both players' best-response sets. Weak comparison means a
    tie-induced equilibrium (e.g. a player indifferent between two columns)
    is correctly reported as a Nash equilibrium.
    """
    br_row = best_responses(payoffs, 0)
    br_col = best_responses(payoffs, 1)
    return sorted(br_row & br_col)


def strictly_dominated(payoffs, player, *, rows=None, cols=None):
    """Indices of ``player``'s STRICTLY dominated strategies in a subgame.

    ``rows`` / ``cols`` restrict attention to a surviving submatrix (the
    indices still in play); default = all. A row i is strictly dominated if
    some other surviving row k beats it (``>``) in EVERY surviving column; a
    column j is strictly dominated if some other surviving column beats it in
    every surviving row. Returns a sorted list of strategy indices (row
    indices for player 0, column indices for player 1).
    """
    n = len(payoffs)
    m = len(payoffs[0]) if n else 0
    rows = list(range(n)) if rows is None else list(rows)
    cols = list(range(m)) if cols is None else list(cols)
    dominated = []
    if player == 0:
        for i in rows:
            for k in rows:
                if k == i:
                    continue
                if all(_payoff_value(payoffs, k, j, 0)
                       > _payoff_value(payoffs, i, j, 0) for j in cols):
                    dominated.append(i)
                    break
    else:
        for j in cols:
            for k in cols:
                if k == j:
                    continue
                if all(_payoff_value(payoffs, i, k, 1)
                       > _payoff_value(payoffs, i, j, 1) for i in rows):
                    dominated.append(j)
                    break
    return sorted(dominated)


def iterated_deletion(payoffs):
    """Iterated deletion of STRICTLY dominated strategies.

    Repeatedly removes any strictly dominated row or column from the surviving
    submatrix until none remain. Returns a list of *steps*; each step is a
    dict ``{"rows": [...], "cols": [...], "deleted_rows": [...],
    "deleted_cols": [...]}`` giving the surviving indices BEFORE the deletion
    and the indices deleted at that step. The final entry has empty
    ``deleted_*`` and records the surviving submatrix. Order-independent for
    strict dominance, so the sequence is deterministic here (rows then cols
    each round); the surviving set is what matters.
    """
    n = len(payoffs)
    m = len(payoffs[0]) if n else 0
    rows = list(range(n))
    cols = list(range(m))
    steps = []
    while True:
        dr = strictly_dominated(payoffs, 0, rows=rows, cols=cols)
        dc = strictly_dominated(payoffs, 1, rows=rows, cols=cols)
        steps.append({
            "rows": list(rows), "cols": list(cols),
            "deleted_rows": list(dr), "deleted_cols": list(dc),
        })
        if not dr and not dc:
            break
        rows = [i for i in rows if i not in dr]
        cols = [j for j in cols if j not in dc]
    return steps


def expected_payoff_lines(payoffs, player, *, against_strategy=0):
    """Each of ``player``'s pure strategies' expected payoff vs an opponent mix.

    The opponent mixes over their two strategies with probability ``q`` on
    column index ``against_strategy`` (default 0) and ``1 - q`` on the other.
    Requires the opponent to have exactly two strategies (the indifference /
    mixed-equilibrium setting). Returns ``{strategy_index: (a, b)}`` where the
    expected payoff of that strategy is the line ``a*q + b``. For the row
    player this reads the row-payoff column; the geometry is the two H/T lines
    of Matching Pennies, etc.
    """
    n = len(payoffs)
    m = len(payoffs[0]) if n else 0
    lines = {}
    if player == 0:
        if m != 2:
            raise ValueError("expected_payoff_lines(player=0) needs a 2-column "
                             "opponent (the mixing player).")
        other = 1 - against_strategy
        for i in range(n):
            v_q = _payoff_value(payoffs, i, against_strategy, 0)
            v_o = _payoff_value(payoffs, i, other, 0)
            # E = q*v_q + (1-q)*v_o = (v_q - v_o)*q + v_o
            lines[i] = (v_q - v_o, v_o)
    else:
        if n != 2:
            raise ValueError("expected_payoff_lines(player=1) needs a 2-row "
                             "opponent (the mixing player).")
        other = 1 - against_strategy
        for j in range(m):
            v_q = _payoff_value(payoffs, against_strategy, j, 1)
            v_o = _payoff_value(payoffs, other, j, 1)
            lines[j] = (v_q - v_o, v_o)
    return lines


def indifference_crossing(line_a, line_b):
    """Solve ``a1*q + b1 == a2*q + b2`` for the crossing ``q``.

    Each line is ``(slope, intercept)``. Returns ``q`` in principle anywhere on
    the real line (callers check it lies in [0, 1]); returns None if the lines
    are parallel (no unique crossing). For Matching Pennies' E[H]=1-2q and
    E[T]=2q-1 this returns q = 1/2.
    """
    a1, b1 = line_a
    a2, b2 = line_b
    denom = a1 - a2
    if denom == 0:
        return None
    return (b2 - b1) / denom


def draw_payoff_matrix(
    ax,
    payoffs,
    *,
    row_player="Player 1",
    col_player="Player 2",
    row_strategies=None,
    col_strategies=None,
    highlight="none",
    against=None,
    note=None,
):
    """Draw an n x m payoff matrix in the project's Tufte style.

    ``payoffs[i][j] = (p_row, p_col)`` — the row-player payoff is listed first
    in each cell, per the Easley-Kleinberg convention. The matrix is drawn as a
    clean grid with the two players' strategy labels on the margins and each
    cell's ``$(p_1, p_2)$`` typeset in mathtext.

    ``highlight`` selects an analysis overlay, all COMPUTED from ``payoffs``:

    - ``"none"``      — plain matrix.
    - ``"best_response"`` — underline each player's weak best-response payoff.
      With ``against={"player": "col"|0|1, "strategy": <idx or label>}`` only
      that player's best responses (in the fixed opponent context) are marked;
      otherwise both players' best responses are shown.
    - ``"nash"``      — tint every pure-NE cell (mutual weak best response) and
      box it; tie-induced NE are included.
    - ``"deletion"``  — iterated deletion of STRICTLY dominated strategies:
      struck-out (faded, line-through) rows/cols are those deleted across all
      rounds; the surviving submatrix is left at full strength. (A per-round
      stepper is a Stage-2 widget concern; this static form shows the end
      state with every deleted strategy marked.)

    Returns the (rows, cols) surviving indices for ``deletion`` (else None),
    so callers can chain. Pure compute lives in the helpers above; this only
    draws.
    """
    n = len(payoffs)
    m = len(payoffs[0]) if n else 0
    if n == 0 or m == 0:
        ax.set_axis_off()
        return None
    row_strategies = row_strategies or [str(i) for i in range(n)]
    col_strategies = col_strategies or [str(j) for j in range(m)]

    st = PAYOFF_STYLE

    # Coordinate frame: cell (i, j) occupies the unit square with top-left at
    # (j, -i) so row 0 is on top and column 0 on the left (reading order).
    ax.set_xlim(-1.0, m)
    ax.set_ylim(-n, 1.0)
    ax.set_aspect("equal")
    ax.autoscale(False)
    ax.set_axis_off()

    # --- analysis overlays (computed) -------------------------------------
    br_cells = set()
    nash_cells = set()
    deleted_rows, deleted_cols = set(), set()
    surviving = None
    if highlight == "best_response":
        if against is None:
            br_cells = best_responses(payoffs, 0) | best_responses(payoffs, 1)
        else:
            who = against.get("player")
            who = 0 if who in (0, "row") else 1
            # Restrict to the named opponent context (a fixed opponent strategy).
            br_all = best_responses(payoffs, who)
            strat = against.get("strategy")
            if strat is not None:
                if who == 0:
                    # opponent is the col player fixing a column
                    jdx = (col_strategies.index(strat)
                           if strat in col_strategies else strat)
                    br_cells = {(i, j) for (i, j) in br_all if j == jdx}
                else:
                    idx = (row_strategies.index(strat)
                           if strat in row_strategies else strat)
                    br_cells = {(i, j) for (i, j) in br_all if i == idx}
            else:
                br_cells = br_all
    elif highlight == "nash":
        nash_cells = set(pure_nash(payoffs))
    elif highlight == "deletion":
        steps = iterated_deletion(payoffs)
        for s in steps:
            deleted_rows.update(s["deleted_rows"])
            deleted_cols.update(s["deleted_cols"])
        surviving = (steps[-1]["rows"], steps[-1]["cols"])

    def _faded(i, j):
        return i in deleted_rows or j in deleted_cols

    # --- cells ------------------------------------------------------------
    from matplotlib.patches import Rectangle
    for i in range(n):
        for j in range(m):
            x0, y0 = j, -i            # top-left of the cell
            faded = _faded(i, j)
            alpha = st["deleted_alpha"] if faded else 1.0
            if (i, j) in nash_cells:
                ax.add_patch(Rectangle(
                    (x0, y0 - 1), 1, 1,
                    facecolor=st["nash_fill"], alpha=st["nash_fill_alpha"],
                    edgecolor=st["nash_edge"], linewidth=st["grid_width"] + 0.6,
                    zorder=0.5,
                ))
            p_row, p_col = payoffs[i][j]
            txt = _format_pair(p_row, p_col)
            ax.text(
                x0 + 0.5, y0 - 0.5, txt,
                ha="center", va="center",
                fontsize=st["payoff_fontsize"], color=COLORS["text"],
                alpha=alpha, zorder=3,
            )
            # best-response underline: mark the maximizing player's payoff(s)
            if (i, j) in br_cells:
                ax.plot(
                    [x0 + 0.18, x0 + 0.82], [y0 - 0.72, y0 - 0.72],
                    color=st["br_color"], linewidth=2.4, zorder=2,
                    solid_capstyle="round",
                )

    # --- grid lines -------------------------------------------------------
    for j in range(m + 1):
        ax.plot([j, j], [-n, 0], color=st["grid_color"],
                linewidth=st["grid_width"], zorder=1)
    for i in range(n + 1):
        ax.plot([0, m], [-i, -i], color=st["grid_color"],
                linewidth=st["grid_width"], zorder=1)

    # --- strategy labels --------------------------------------------------
    for j in range(m):
        faded = j in deleted_cols
        ax.text(j + 0.5, 0.18, str(col_strategies[j]),
                ha="center", va="bottom", fontsize=st["strategy_fontsize"],
                color=COLORS["text"],
                alpha=st["deleted_alpha"] if faded else 1.0,
                zorder=3)
        if faded:   # strike-through on a deleted column label
            ax.plot([j + 0.2, j + 0.8], [0.30, 0.30],
                    color=st["deleted_color"], linewidth=1.6, zorder=4)
    for i in range(n):
        faded = i in deleted_rows
        ax.text(-0.18, -i - 0.5, str(row_strategies[i]),
                ha="right", va="center", fontsize=st["strategy_fontsize"],
                color=COLORS["text"],
                alpha=st["deleted_alpha"] if faded else 1.0,
                zorder=3)
        if faded:
            ax.plot([-0.55, -0.05], [-i - 0.5, -i - 0.5],
                    color=st["deleted_color"], linewidth=1.6, zorder=4)

    # --- player names -----------------------------------------------------
    ax.text(m / 2.0, 0.62, str(col_player), ha="center", va="bottom",
            fontsize=st["player_fontsize"], color=COLORS["primary"],
            fontweight="bold", zorder=3)
    ax.text(-0.72, -n / 2.0, str(row_player), ha="center", va="center",
            rotation=90, fontsize=st["player_fontsize"],
            color=COLORS["primary"], fontweight="bold", zorder=3)

    if note:
        ax.text(m / 2.0, -n - 0.25, str(note), ha="center", va="top",
                fontsize=st["strategy_fontsize"] - 1, color=COLORS["text"],
                zorder=3)

    return surviving


def _format_pair(p_row, p_col):
    """Format a payoff pair as mathtext ``$(a,\\ b)$`` (no Unicode minus)."""
    def fmt(v):
        # Render ints without trailing .0; keep floats compact.
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        s = f"{v}"
        return s.replace("-", "{-}")   # mathtext minus, avoids font fallback
    return f"$({fmt(p_row)},\\ {fmt(p_col)})$"


# -----------------------------------------------------------------------------
# Auction helpers + renderers (Lesson 3)
# -----------------------------------------------------------------------------
#
# Lesson 3 (Auctions, c9) has essentially no source figures, so these renderers
# ARE the figures. Same discipline as the Lesson-2 payoff-matrix work: the
# winner / price / payoff / optimum is COMPUTED from the bid/value data by the
# helpers below, and the renderers + Stage-2 widgets both call them — so a
# figure can never drift from the answer key.
#
# Conventions: a sealed-bid auction is a list of submitted ``bids``; the winner
# is the highest bid (ties -> lowest index, deterministic). First-price: the
# winner pays their own bid. Second-price (Vickrey): the winner pays the
# second-highest bid (or ``max(second_bid, reserve)`` with a reserve). A payoff
# is ``value - price`` if you win, else 0.

#: Auction figure styling. Centralized — no inline literals in render code.
AUCTION_STYLE = {
    # table
    "row_height_in":   0.52,
    "col_width_in":    1.02,
    "margin_in":       0.55,
    "header_fontsize": 12,
    "cell_fontsize":   12,
    "rule_color":      COLORS["primary"],
    "rule_width":      1.4,
    "thin_rule_width": 0.7,
    "winner_fill":     COLORS["highlight"],
    "winner_fill_alpha": 0.16,
    "price_color":     COLORS["accent"],
    # curves
    "curve_color":     COLORS["primary"],
    "curve_width":     2.2,
    "optimum_color":   COLORS["highlight"],
    "truthful_color":  COLORS["good"],
    "marker_color":    COLORS["accent"],
    "guide_color":     COLORS["minor_tick"],
    "guide_width":     1.0,
    # common-value strip
    "common_value_color": COLORS["primary"],
    "estimate_color":     COLORS["tertiary"],
    "curse_color":        COLORS["bad"],
    "axis_fontsize":   11,
    "annot_fontsize":  10,
}


def _fmt_num(v):
    """Compact mathtext number: int when integral, else up to 3 decimals,
    mathtext minus to avoid a Unicode-minus font fallback."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = f"{v:.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v}"
    return s.replace("-", "{-}")


def _fmt_num_plain(v):
    """Compact PLAIN-TEXT number (no mathtext): int when integral, else up to
    3 decimals. Unlike ``_fmt_num`` it emits a plain ASCII minus and NO ``$…$``
    / ``{-}`` mathtext — with ``axes.unicode_minus=False`` the ``-`` stays in
    the sans body font. Use for labels drawn OUTSIDE a math context (the
    bipartite_market valuation/price columns) so they can never collide with
    matplotlib's ``$`` mathtext parser."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f"{v:.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v}"


# --- compute helpers (single source of truth) --------------------------------

def auction_outcome(bids, *, fmt="second_price", reserve=None):
    """Winner index + price for a sealed-bid auction, computed from ``bids``.

    ``fmt`` is ``"first_price"`` (winner pays own bid) or ``"second_price"``
    (winner pays the second-highest bid). The highest bid wins; ties break to
    the lowest index (deterministic). With a ``reserve``, the item is unsold if
    the top bid is below it; otherwise second-price pays ``max(second, reserve)``
    and first-price pays the winner's own bid. Returns
    ``{"winner": idx|None, "price": float|None, "sold": bool}``.
    """
    if not bids:
        return {"winner": None, "price": None, "sold": False}
    winner = max(range(len(bids)), key=lambda i: (bids[i], -i))
    top = bids[winner]
    others = [b for k, b in enumerate(bids) if k != winner]
    second = max(others) if others else 0.0
    if reserve is not None and top < reserve:
        return {"winner": None, "price": None, "sold": False}
    if fmt == "first_price":
        price = top
    else:
        price = second if reserve is None else max(second, reserve)
    return {"winner": winner, "price": float(price), "sold": True}


def bid_payoff(value, bid, others, *, fmt="second_price", reserve=None):
    """Your payoff bidding ``bid`` (true value ``value``) against ``others``.

    You are bidder 0 in the combined vector ``[bid] + others``. If you win, your
    payoff is ``value - price`` (price per ``auction_outcome``/``fmt``); if you
    lose, 0. The engine, not the author, decides whether you win — so a
    truthfulness/shading figure can't disagree with the math.
    """
    out = auction_outcome([bid] + list(others), fmt=fmt, reserve=reserve)
    if out["winner"] == 0:
        return float(value) - out["price"]
    return 0.0


def optimal_reserve(seller_value):
    """Optimal second-price reserve for one bidder with value ~ U(0,1):
    ``(1 + v)/2`` (maximizes ``v*r + r*(1-r)``)."""
    return (1.0 + seller_value) / 2.0


def reserve_revenue(r, seller_value):
    """Expected seller revenue at reserve ``r`` (one bidder, value ~ U(0,1)):
    ``v*r + r*(1-r)`` — kept the item (value ``v``) w.p. ``r``, else gets ``r``."""
    return seller_value * r + r * (1.0 - r)


def second_price_revenue_binary(n):
    """Expected second-price revenue, ``n`` i.i.d. bidders with value in {0,1}
    each w.p. 1/2. Revenue is 1 iff at least two bidders have value 1 (the
    second-highest value is then 1); the count of such outcomes is
    ``2**n - n - 1``, so the expectation is ``(2**n - n - 1) / 2**n``."""
    return (2 ** n - n - 1) / (2 ** n)


def equilibrium_shade(value, n):
    """First-price symmetric-equilibrium bid for values ~ U(0,1) and ``n``
    bidders: ``(n-1)/n * value``. (n=2 gives the ``v/2`` "shade by half".)"""
    return (n - 1) / n * value


def _win_prob_first_price(bid, n):
    """P(win) for bidder 0 bidding ``bid`` when the ``n-1`` opponents play the
    symmetric equilibrium ``s(v)=(n-1)/n v`` with values ~ U(0,1). An opponent's
    bid is below ``bid`` iff their value is below ``bid/c`` with ``c=(n-1)/n``,
    so P(win) = ``min(1, bid/c)**(n-1)``."""
    if n <= 1:
        return 1.0
    c = (n - 1) / n
    per = min(1.0, max(0.0, bid / c)) if c > 0 else (1.0 if bid > 0 else 0.0)
    return per ** (n - 1)


def pretend_value_payoff(value, pretend, n=2):
    """Expected first-price surplus when your true value is ``value`` but you
    bid as if your value were ``pretend`` — report type ``pretend``, hence bid
    the symmetric equilibrium ``s(pretend)=(n-1)/n*pretend`` — against ``n-1``
    rivals playing the same strategy with values ~ U(0,1).

    Each rival's bid is below yours iff their value is below ``pretend``, so
    ``P(win)=pretend**(n-1)`` directly — SMOOTH, with NO ``min`` saturation/clamp
    for ``pretend`` in [0,1] (it is the rival-value CDF, never pinned at 1 inside
    the support). The payoff is therefore::

        g = pretend**(n-1) * (value - equilibrium_shade(pretend, n))

    a smooth function of ``pretend`` whose unique stationary point is
    ``pretend = value`` (``g'(value)=0`` for every ``n``): reporting your true
    type is optimal. This is the honest "flat top" of the first-price FOC — no
    kink, unlike the bid-swept ``first_price`` surplus curve, whose maximum sits
    at the saturation corner ``b=value``.
    """
    p = max(0.0, pretend)
    return p ** (n - 1) * (value - equilibrium_shade(p, n))


# --- renderer A: auction outcome table ---------------------------------------

def draw_auction_table(ax, *, bids, values=None, fmt="second_price",
                       reserve=None, labels=None, note=None,
                       compare=None, compare_headers=None,
                       mask_winner_price=False):
    """Render an auction outcome table; winner + price + payoff COMPUTED.

    One row per bidder with columns Bidder / Value / Bid / Wins / Pays /
    Payoff. ``bids`` decides the outcome; ``values`` (default = ``bids``, i.e.
    truthful bidding) feeds the payoff column. The winning row is tinted and its
    price marked. Booktabs-style (top/header/bottom rules, no vertical lines).

    Paired/comparison mode — ``compare`` an ordered list of formats, e.g.
    ``compare=["first_price", "second_price"]`` — prices the *same* bids two (or
    more) ways on the *single* ``ax``: the shared Bidder/Value/Bid/Wins columns
    are followed by a Pays + Payoff column pair per listed format, in list
    order, so each bidder row shows both prices side by side. Each format's
    Pays + Payoff pair is grouped under a single per-format super-header (a
    two-row header: short "Pays"/"Payoff" sub-headers under a format name) so
    the eight columns fit at notebook width without colliding. The winner and
    sold/unsold status depend only on the bids (highest bid wins; sold iff the
    top bid clears any ``reserve``), so they stay shared — only the price, and
    hence payoff, differs by format. ``compare_headers`` optionally overrides
    the per-format super-header (a ``{format: label}`` map), e.g. to label the
    equivalence "First-price ≡ Dutch". In compare mode the single
    "{fmt}-price auction" sub-caption is suppressed (ambiguous with two
    formats); pass ``note=`` to set a caption explicitly. With ``compare=None``
    the rendering is unchanged and returns the single outcome dict; in compare
    mode it returns ``{format: outcome_dict}`` for every listed format.

    ``mask_winner_price`` (single-format only) blanks the WINNING row's Pays and
    Payoff cells to a literal ``"?"`` so a figure can SET UP a second-price
    scenario without revealing the price/payoff the question asks for. Only the
    winner row's last two cells change (rendered as plain ``"?"`` in the normal
    cell color, not the price highlight); every other cell — including the
    winner-row tint and non-winner rows' ``"$-$"``/``0`` — is untouched. It is
    incompatible with ``compare`` (paired mode has no single defined winner-price
    cell): passing both raises ``ValueError`` rather than half-applying.
    """
    bids = [float(b) for b in bids]
    n = len(bids)
    if n == 0:
        ax.set_axis_off()
        return None
    values = [float(v) for v in (values if values is not None else bids)]
    labels = labels or [f"B{i + 1}" for i in range(n)]
    if compare is not None:
        if mask_winner_price:
            raise ValueError(
                "mask_winner_price is single-format only (compare=None); "
                "paired compare mode has no single winner-price cell to mask")
        return _draw_auction_compare(
            ax, bids=bids, values=values, labels=labels, formats=compare,
            reserve=reserve, note=note, headers=compare_headers)
    out = auction_outcome(bids, fmt=fmt, reserve=reserve)
    st = AUCTION_STYLE

    cols = ["Bidder", "Value", "Bid", "Wins", "Pays", "Payoff"]
    ncol = len(cols)
    # x-centers; first column a touch wider visually but uniform cells keep it
    # simple and aligned.
    ax.set_xlim(0, ncol)
    ax.set_ylim(-(n + 1), 0)
    ax.set_aspect("auto")
    ax.autoscale(False)
    ax.set_axis_off()

    from matplotlib.patches import Rectangle

    # winner row tint (row index = winner+1 because row 0 is the header)
    if out["sold"] and out["winner"] is not None:
        wr = out["winner"]
        ax.add_patch(Rectangle((0, -(wr + 2)), ncol, 1,
                               facecolor=st["winner_fill"],
                               alpha=st["winner_fill_alpha"],
                               edgecolor="none", zorder=0))

    # header
    for c, name in enumerate(cols):
        ax.text(c + 0.5, -0.5, name, ha="center", va="center",
                fontsize=st["header_fontsize"], fontweight="bold",
                color=COLORS["primary"])

    # rows
    for i in range(n):
        y = -(i + 1.5)
        won = (out["winner"] == i and out["sold"])
        masked = won and mask_winner_price   # hide the answer (Pays + Payoff)
        pays = _fmt_num(out["price"]) if won else "$-$"
        payoff = (values[i] - out["price"]) if won else 0.0
        cells = [labels[i], _fmt_num(values[i]), _fmt_num(bids[i]),
                 ("yes" if won else "no"), pays, _fmt_num(payoff)]
        if masked:
            cells[4] = cells[5] = "?"        # plain literal, normal cell color
        for c, txt in enumerate(cells):
            color = (st["price_color"] if (won and c == 4 and not masked)
                     else COLORS["text"])
            ax.text(c + 0.5, y, txt, ha="center", va="center",
                    fontsize=st["cell_fontsize"], color=color)

    # booktabs rules
    for yy, w in [(0, st["rule_width"]), (-1, st["thin_rule_width"]),
                  (-(n + 1), st["rule_width"])]:
        ax.plot([0, ncol], [yy, yy], color=st["rule_color"], linewidth=w,
                zorder=2)

    fmt_label = "second-price" if fmt == "second_price" else "first-price"
    sub = f"{fmt_label} auction"
    if reserve is not None:
        sub += f", reserve $r={_fmt_num(reserve)}$"
    if not out["sold"]:
        sub += " — unsold (top bid below reserve)"
    ax.text(ncol / 2.0, -(n + 1) - 0.35, note or sub, ha="center", va="top",
            fontsize=st["annot_fontsize"], color=COLORS["text"])
    return out


def _auction_fmt_label(fmt):
    """Hyphenated display label for an auction-format key
    (``"first_price"`` -> ``"first-price"``)."""
    return {"first_price": "first-price",
            "second_price": "second-price"}.get(fmt, str(fmt).replace("_", "-"))


def _compare_group_label(fmt, headers):
    """Super-header label for one format group in the paired auction table:
    the caller's ``compare_headers[fmt]`` when given (e.g. an equivalence label
    ``"First-price ≡ Dutch"``), else the capitalized format name
    (``"First-price"``). A literal ``≡`` is rendered via mathtext — the body
    font (Helvetica) lacks the glyph but the CM mathtext fontset has it, the
    same idiom the table uses for ``"$-$"``."""
    if headers and fmt in headers:
        lbl = headers[fmt]
    else:
        lbl = _auction_fmt_label(fmt)
        lbl = lbl[:1].upper() + lbl[1:]
    return lbl.replace("≡", r"$\equiv$")


def _wrap_header(text, width):
    """Greedily wrap a header onto multiple lines on whitespace only — never
    splitting a word or a hyphenated term — so a long compare super-header such
    as ``"Second-price ≡ English"`` stacks instead of overrunning its group.
    Width is measured *visually*: a ``$...$`` mathtext span (e.g.
    ``$\\equiv$``) counts as one glyph, not its source length, so it wraps with
    its neighbor rather than landing alone."""
    width = max(6, width)
    words = text.split()
    if not words:
        return text
    lines, cur, cur_len = [], [], 0
    for w in words:
        wl = len(re.sub(r"\$[^$]*\$", "x", w))   # mathtext span -> 1 glyph
        if cur and cur_len + 1 + wl > width:
            lines.append(" ".join(cur))
            cur, cur_len = [w], wl
        else:
            cur_len += (1 if cur else 0) + wl
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines)


def _draw_auction_compare(ax, *, bids, values, labels, formats, reserve,
                          note, headers):
    """Paired/comparison auction table on a single ``ax`` (see
    ``draw_auction_table``'s ``compare`` argument).

    Shared Bidder/Value/Bid/Wins columns, then a Pays + Payoff pair per format
    in list order, the pair grouped under one per-format super-header (a two-row
    header) so the eight columns fit at notebook width. Winner and sold/unsold
    status are format-independent (they follow from the bids), so they are
    computed once and shared; only price and payoff vary by format. Returns
    ``{format: auction_outcome(...)}``.
    """
    from matplotlib.patches import Rectangle

    st = AUCTION_STYLE
    n = len(bids)
    headers = headers or {}

    outs = {f: auction_outcome(bids, fmt=f, reserve=reserve) for f in formats}
    base = outs[formats[0]]            # winner/sold do not depend on the format
    sold = base["sold"]
    winner = base["winner"]

    # Column layout. Shared columns carry a single centered header; each format
    # contributes a Pays + Payoff sub-column pair grouped under one super-header
    # (the format name, or a caller equivalence label). Short "Pays"/"Payoff"
    # sub-headers + a grouped super-header keep all eight columns from colliding
    # at notebook width — the old long per-column headers ("Pays (second-price)",
    # "Payoff (first-price)") overlapped once the figure shrank to ~700-900px.
    # Each entry is (text, width, kind, fmt); kind drives the cell value/tint.
    shared = [("Bidder", 1.1), ("Value", 0.95), ("Bid", 0.95), ("Wins", 0.85)]
    pays_w, payoff_w = 1.4, 1.4
    columns = [(name, w, "shared", None) for name, w in shared]
    groups = []                        # (fmt, super_label, x_left, x_right)
    for f in formats:
        x0 = sum(w for _, w, _, _ in columns)         # left edge of this group
        columns.append(("Pays", pays_w, "pays", f))
        columns.append(("Payoff", payoff_w, "payoff", f))
        x1 = sum(w for _, w, _, _ in columns)         # right edge of this group
        groups.append((f, _compare_group_label(f, headers), x0, x1))

    # Cumulative x extents -> per-column centers.
    x_left, acc = [], 0.0
    for _, w, _, _ in columns:
        x_left.append(acc)
        acc += w
    total_w = acc
    centers = [x_left[i] + columns[i][1] / 2.0 for i in range(len(columns))]

    # Wrap each super-header to its group width; the tallest sets the super row
    # (a long equivalence label like "Second-price ≡ English" stacks to 2 lines,
    # a plain "First-price" stays on 1).
    super_wrapped, super_lines = [], 1
    for _f, lbl, x0, x1 in groups:
        wt = _wrap_header(lbl, int(round((x1 - x0) * 5.5)))
        super_wrapped.append(wt)
        super_lines = max(super_lines, wt.count("\n") + 1)

    # Two-row header band: a super-header row (1-2 lines) over a one-line
    # sub-header row, with a booktabs cmidrule between them per group.
    top_pad, row_h, gap, bot_pad = 0.18, 0.46, 0.16, 0.16
    super_block = row_h * super_lines
    header_h = top_pad + super_block + gap + row_h + bot_pad
    y_super = -(top_pad + super_block / 2.0)
    y_cmid = -(top_pad + super_block + gap / 2.0)
    y_sub = -(top_pad + super_block + gap + row_h / 2.0)
    y_shared = -header_h / 2.0

    cap_pad = 0.9 if note else 0.25
    ax.set_xlim(0, total_w)
    ax.set_ylim(-(header_h + n) - cap_pad, 0)
    ax.set_aspect("auto")
    ax.autoscale(False)
    ax.set_axis_off()

    # Winner row tint, spanning the full (wider) table.
    if sold and winner is not None:
        ax.add_patch(Rectangle((0, -(header_h + winner + 1)), total_w, 1,
                               facecolor=st["winner_fill"],
                               alpha=st["winner_fill_alpha"],
                               edgecolor="none", zorder=0))

    hfs = st["header_fontsize"] - 1
    # Shared headers: vertically centered across the whole band.
    for i, (text, w, kind, _f) in enumerate(columns):
        if kind == "shared":
            ax.text(centers[i], y_shared, text, ha="center", va="center",
                    fontsize=hfs, fontweight="bold", color=COLORS["primary"])
    # Per-format super-headers + a thin cmidrule grouping each Pays+Payoff pair.
    for (_f, _lbl, x0, x1), wt in zip(groups, super_wrapped):
        ax.text((x0 + x1) / 2.0, y_super, wt, ha="center", va="center",
                fontsize=hfs, fontweight="bold", color=COLORS["primary"],
                linespacing=1.05)
        ax.plot([x0 + 0.08, x1 - 0.08], [y_cmid, y_cmid],
                color=st["rule_color"], linewidth=st["thin_rule_width"],
                zorder=2)
    # Sub-headers (Pays / Payoff) under each super-header.
    for i, (text, w, kind, _f) in enumerate(columns):
        if kind in ("pays", "payoff"):
            ax.text(centers[i], y_sub, text, ha="center", va="center",
                    fontsize=hfs, fontweight="bold", color=COLORS["primary"])

    # Rows.
    for r in range(n):
        y = -(header_h + r + 0.5)
        won = (winner == r and sold)
        for i, (text, w, kind, f) in enumerate(columns):
            color = COLORS["text"]
            if kind == "shared":
                if text == "Bidder":
                    val = labels[r]
                elif text == "Value":
                    val = _fmt_num(values[r])
                elif text == "Bid":
                    val = _fmt_num(bids[r])
                else:  # Wins
                    val = "yes" if won else "no"
            elif kind == "pays":
                val = _fmt_num(outs[f]["price"]) if won else "$-$"
                color = st["price_color"] if won else COLORS["text"]
            else:  # payoff
                val = _fmt_num((values[r] - outs[f]["price"]) if won else 0.0)
            ax.text(centers[i], y, val, ha="center", va="center",
                    fontsize=st["cell_fontsize"], color=color)

    # Booktabs rules (top / under-header / bottom).
    for yy, lw in [(0, st["rule_width"]), (-header_h, st["thin_rule_width"]),
                   (-(header_h + n), st["rule_width"])]:
        ax.plot([0, total_w], [yy, yy], color=st["rule_color"], linewidth=lw,
                zorder=2)

    # Sub-caption suppressed by default in compare mode (ambiguous with two
    # formats); render only an explicit note override.
    if note:
        ax.text(total_w / 2.0, -(header_h + n) - 0.35, note,
                ha="center", va="top",
                fontsize=st["annot_fontsize"], color=COLORS["text"])
    return outs


# --- renderer B: bid -> payoff curve (truthfulness / shading) ----------------

def draw_bid_payoff_curve(ax, *, mode, value, highest_other=None, n=2,
                          your_bid=None, note=None):
    """Your payoff as a function of your bid — the truthfulness / shading view.

    ``mode="second_price"``: with the highest competing bid fixed at
    ``highest_other``, your payoff is a step — 0 until your bid reaches
    ``highest_other``, then the constant ``value - highest_other`` (which is the
    *same* for every winning bid). Bidding your ``value`` always lands on the
    better of the two plateaus, so truthful is **weakly best** — the four
    over/under-bid x win/lose cases, in one picture.

    ``mode="first_price"``: expected surplus ``P(win)*(value - bid)`` vs your
    bid, when the ``n-1`` opponents play ``s(v)=(n-1)/n v``. It peaks at the
    equilibrium shade ``(n-1)/n * value`` — a kinked curve whose maximum is the
    saturation corner.

    ``mode="first_price_pretend"``: the *smooth* companion to ``first_price``.
    The x-axis is the **pretend value** ``tilde-v`` (the type you report) over
    the full support [0,1], not the bid; you bid the equilibrium ``s(tilde-v)``.
    The payoff ``pretend_value_payoff(value, tilde-v, n)`` is smooth with no
    saturation clamp and peaks at the truthful report ``tilde-v = value`` for
    every ``n`` — the honest "flat top" of the first-price FOC (``g'(v)=0``).

    ``your_bid`` (optional) marks the current slider position for the marquee
    widgets. Everything is computed from the helpers — nothing hardcoded.
    """
    st = AUCTION_STYLE
    apply_ax_style(ax)
    ax.set_xlabel("your bid", fontsize=st["axis_fontsize"])
    ax.set_ylabel("payoff", fontsize=st["axis_fontsize"])

    if mode == "second_price":
        h = float(highest_other if highest_other is not None else value * 0.6)
        xmax = max(value, h) * 1.35 + 1e-9
        win_payoff = value - h
        # step function via the helper, evaluated densely
        xs = [xmax * k / 240 for k in range(241)]
        ys = [bid_payoff(value, b, [h], fmt="second_price") for b in xs]
        ax.plot(xs, ys, color=st["curve_color"], linewidth=st["curve_width"])
        # truthful bid marker
        ax.axvline(value, color=st["truthful_color"], linestyle=":",
                   linewidth=st["guide_width"])
        ax.plot([value], [bid_payoff(value, value, [h], fmt="second_price")],
                "o", markersize=10, markerfacecolor="white",
                markeredgecolor=st["truthful_color"], markeredgewidth=2.2,
                zorder=5)
        ax.text(value, win_payoff if win_payoff > 0 else 0,
                "  truthful $b=v$", color=st["truthful_color"],
                fontsize=st["annot_fontsize"], va="bottom")
        ax.axhline(0, color=st["guide_color"], linewidth=st["guide_width"],
                   zorder=0)
        best = max(0.0, win_payoff)
        cap = (f"$v={_fmt_num(value)}$, top rival $={_fmt_num(h)}$ — best "
               f"payoff ${_fmt_num(best)}$, reached by bidding $v$ "
               f"(weakly dominant).")
    elif mode == "first_price":
        xs = [value * k / 240 for k in range(241)]
        ys = [_win_prob_first_price(b, n) * (value - b) for b in xs]
        ax.plot(xs, ys, color=st["curve_color"], linewidth=st["curve_width"])
        bstar = equilibrium_shade(value, n)
        gstar = _win_prob_first_price(bstar, n) * (value - bstar)
        ax.axvline(bstar, color=st["optimum_color"], linestyle=":",
                   linewidth=st["guide_width"])
        ax.plot([bstar], [gstar], "o", markersize=11, markerfacecolor="white",
                markeredgecolor=st["optimum_color"], markeredgewidth=2.4,
                zorder=5)
        ax.text(bstar, gstar, f"  shade $b^*={_fmt_num(bstar)}$",
                color=st["optimum_color"], fontsize=st["annot_fontsize"],
                va="bottom")
        cap = (f"$v={_fmt_num(value)}$, $n={n}$ — expected surplus peaks at "
               f"$b^*=\\frac{{{n-1}}}{{{n}}}v={_fmt_num(bstar)}$.")
    elif mode == "first_price_pretend":
        # The x-axis is the *pretend value* (the type you report) over the full
        # value support [0,1] — a different semantic axis from the kinked
        # ``first_price`` mode, which sweeps the BID over [0, value]. The curve
        # is smooth (no saturation corner) and peaks at the truthful report
        # tilde-v = v, making the first-price FOC "flat top" honest.
        ax.set_xlabel("pretend value $\\tilde{v}$ (the type you report)",
                      fontsize=st["axis_fontsize"])
        vts = [k / 240 for k in range(241)]
        ys = [pretend_value_payoff(value, vt, n) for vt in vts]
        ax.plot(vts, ys, color=st["curve_color"], linewidth=st["curve_width"])
        vstar = value
        gstar = pretend_value_payoff(value, vstar, n)
        ax.axvline(vstar, color=st["optimum_color"], linestyle=":",
                   linewidth=st["guide_width"])
        ax.plot([vstar], [gstar], "o", markersize=11, markerfacecolor="white",
                markeredgecolor=st["optimum_color"], markeredgewidth=2.4,
                zorder=5)
        ax.text(vstar, gstar, "truthful $\\tilde{v}=v$  ",
                color=st["optimum_color"], fontsize=st["annot_fontsize"],
                va="bottom", ha="right")
        ax.axhline(0, color=st["guide_color"], linewidth=st["guide_width"],
                   zorder=0)
        cap = (f"$v={_fmt_num(value)}$, $n={n}$ — bid as if your value were "
               f"$\\tilde{{v}}$; smooth surplus peaks at $\\tilde{{v}}=v$ "
               f"(report truthfully, no kink).")
    else:
        ax.text(0.5, 0.5, f"unknown mode {mode!r}", ha="center", va="center")
        return None

    if your_bid is not None:
        ax.axvline(your_bid, color=st["marker_color"],
                   linewidth=st["curve_width"], alpha=0.8, zorder=1)
    if note:
        cap = note
    ax.set_title(cap, fontsize=st["annot_fontsize"], color=COLORS["text"])
    return None


# --- renderer C: revenue / parameter curve -----------------------------------

def draw_revenue_curve(ax, *, kind="reserve", seller_value=0.0, n_max=8,
                       note=None):
    """A computed 1-D auction curve with its key feature marked.

    ``kind="reserve"``: expected revenue ``r*(v+1-r)`` vs reserve ``r`` over
    [0,1], peaking at ``optimal_reserve(v)=(1+v)/2``. ``kind="revenue_vs_n"``:
    discrete second-price revenue ``(2^n-n-1)/2^n`` vs ``n`` (-> 1).
    ``kind="shade_vs_n"``: the equilibrium shade factor ``(n-1)/n`` vs ``n``
    (-> 1, "more bidders -> shade less").
    """
    st = AUCTION_STYLE
    apply_ax_style(ax)
    if kind == "reserve":
        rs = [k / 240 for k in range(241)]
        ys = [reserve_revenue(r, seller_value) for r in rs]
        ax.plot(rs, ys, color=st["curve_color"], linewidth=st["curve_width"])
        rstar = optimal_reserve(seller_value)
        ax.axvline(rstar, color=st["optimum_color"], linestyle=":",
                   linewidth=st["guide_width"])
        ax.plot([rstar], [reserve_revenue(rstar, seller_value)], "o",
                markersize=11, markerfacecolor="white",
                markeredgecolor=st["optimum_color"], markeredgewidth=2.4,
                zorder=5)
        ax.set_xlabel("reserve price $r$", fontsize=st["axis_fontsize"])
        ax.set_ylabel("expected revenue", fontsize=st["axis_fontsize"])
        cap = (f"seller value $v={_fmt_num(seller_value)}$ — optimal reserve "
               f"$r^*=\\frac{{1+v}}{{2}}={_fmt_num(rstar)}$.")
    elif kind in ("revenue_vs_n", "shade_vs_n"):
        ns = list(range(1, n_max + 1))
        if kind == "revenue_vs_n":
            ys = [second_price_revenue_binary(k) for k in ns]
            ylab = "expected revenue"
            cap = "discrete second-price revenue rises toward 1 as $n$ grows."
        else:
            ys = [(k - 1) / k for k in ns]
            ylab = "shade factor $(n{-}1)/n$"
            cap = "more bidders -> shade factor $(n{-}1)/n \\to 1$ (shade less)."
        ax.plot(ns, ys, "-o", color=st["curve_color"],
                linewidth=st["curve_width"], markersize=7,
                markerfacecolor="white", markeredgecolor=st["curve_color"],
                markeredgewidth=2)
        ax.axhline(1.0, color=st["guide_color"], linestyle="--",
                   linewidth=st["guide_width"])
        ax.set_xlabel("number of bidders $n$", fontsize=st["axis_fontsize"])
        ax.set_ylabel(ylab, fontsize=st["axis_fontsize"])
    else:
        ax.text(0.5, 0.5, f"unknown kind {kind!r}", ha="center", va="center")
        return None
    ax.set_title(note or cap, fontsize=st["annot_fontsize"],
                 color=COLORS["text"])
    return None


# --- renderer D: common-value bids (winner's curse) --------------------------

def draw_common_value_bids(ax, *, common_value, estimates, note=None):
    """Winner's-curse strip: estimates ``v_i = v + x_i`` scattered around the
    common value ``v`` on a number line; the winner (highest estimate, COMPUTED)
    is highlighted to show the winner systematically over-estimates and overpays.
    """
    st = AUCTION_STYLE
    est = [float(e) for e in estimates]
    winner = max(range(len(est)), key=lambda i: (est[i], -i))
    lo = min(min(est), common_value)
    hi = max(max(est), common_value)
    pad = (hi - lo) * 0.12 + 1e-9
    ax.set_xlim(lo - pad, hi + pad)
    ax.set_ylim(-1.0, 1.0)
    ax.set_yticks([])
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_position(("data", 0))
    ax.spines["bottom"].set_color(COLORS["minor_tick"])
    ax.tick_params(axis="x", labelsize=st["axis_fontsize"],
                   color=COLORS["accent"], labelcolor=COLORS["text"])

    # common value line
    ax.axvline(common_value, color=st["common_value_color"], linewidth=2.0,
               zorder=1)
    ax.text(common_value, 0.78, f"common value $v={_fmt_num(common_value)}$",
            ha="center", va="bottom", color=st["common_value_color"],
            fontsize=st["annot_fontsize"])
    # estimates as open circles on the line; winner highlighted in curse color
    for i, e in enumerate(est):
        is_w = (i == winner)
        ax.plot([e], [0], "o", markersize=13 if is_w else 10,
                markerfacecolor="white",
                markeredgecolor=st["curse_color"] if is_w else st["estimate_color"],
                markeredgewidth=2.6 if is_w else 2.0, zorder=3)
    we = est[winner]
    ax.annotate(f"winner bids highest (${_fmt_num(we)}$) — overpays by "
                f"${_fmt_num(we - common_value)}$",
                xy=(we, 0), xytext=(we, -0.7), ha="center",
                color=st["curse_color"], fontsize=st["annot_fontsize"],
                arrowprops=dict(arrowstyle="->", color=st["curse_color"]))
    if note:
        ax.set_title(note, fontsize=st["annot_fontsize"], color=COLORS["text"])
    return {"winner": winner, "overpay": we - common_value}


# -----------------------------------------------------------------------------
# Matching-market helpers + renderer (Lesson 4, c10)
# -----------------------------------------------------------------------------
#
# Lesson 4 (Matching Markets, c10) follows the same discipline as the Lesson-2
# payoff matrix and the Lesson-3 auction surface: the *answer* a figure shows —
# the optimal assignment, the market-clearing matching, the constricted set, the
# ascending-auction trace — is COMPUTED from the underlying valuations/prices by
# the pure helpers below, and the renderer (plus the Stage-2 widgets to come)
# both call them. A figure therefore can never drift from the answer key; the
# highlight IS the computation.
#
# A matching-market figure has one of THREE distinct edge sources, and the
# renderer serves all three (the helpers supply the latter two):
#   1. EXPLICIT adjacency  — a plain bipartite graph (Section 10.1 figures);
#      edges are given, there are no valuations or prices.
#   2. COMPUTED optimal assignment — the maximum-total-valuation matching, from
#      valuations alone, no prices (``optimal_assignment``).
#   3. COMPUTED preferred-seller graph — argmax_j (v_ij - p_j) per buyer, ties
#      kept, negative-payoff options dropped (``preferred_seller_edges``, and the
#      market-clearing test / ascending auction built on it).
#
# The valuation/price helpers are INDEX-BASED and pure: a buyer is an integer
# row index, a seller an integer column index, ``valuations[buyer][seller]`` the
# buyer's value for that seller's item, ``prices[seller]`` the seller's price.
# They return plain dicts/lists of indices; mapping indices back to node labels
# is the renderer's job. ``find_constricted_set`` is the exception — it is
# generic over node identity (any hashable), since it also serves the
# explicit-adjacency figures.


# --- compute helpers (single source of truth) --------------------------------

def preferred_seller_edges(valuations, prices):
    """Each buyer's preferred seller(s) at the given prices (Section 10.3).

    For buyer ``i`` the payoff from seller ``j`` is ``valuations[i][j] -
    prices[j]``; the buyer's preferred sellers are the ones MAXIMIZING that
    payoff. Ties are KEPT (a buyer can have several preferred sellers). Options
    with NEGATIVE payoff are dropped, so a buyer for whom every payoff is
    negative has no preferred seller at all (an empty list) — matching the text's
    "buyer ``j`` has no preferred seller if the payoffs ``v_ij - p_i`` are
    negative for all ``i``."

    Returns ``{buyer_index: [seller_index, ...]}`` for every buyer (the list is
    empty when the buyer prefers no one).
    """
    prefs = {}
    for i, row in enumerate(valuations):
        surplus = [row[j] - prices[j] for j in range(len(row))]
        best = max(surplus) if surplus else None
        if best is None or best < 0:
            prefs[i] = []
        else:
            prefs[i] = [j for j, s in enumerate(surplus) if s == best]
    return prefs


def _bipartite_matching(left, adj):
    """Maximum-cardinality bipartite matching via augmenting paths (Kuhn's).

    ``left`` is the list of left nodes (any hashable); ``adj`` maps each left
    node to an iterable of right nodes. Returns ``match_right``, a dict mapping
    each MATCHED right node to its left partner. The left->right view is
    ``{l: r for r, l in match_right.items()}``; the matching is perfect (covers
    every left node) iff ``len(match_right) == len(left)``. Deterministic given a
    fixed ``left`` order and adjacency order.
    """
    match_right = {}

    def _augment(u, seen):
        for v in adj.get(u, ()):
            if v in seen:
                continue
            seen.add(v)
            if v not in match_right or _augment(match_right[v], seen):
                match_right[v] = u
                return True
        return False

    for u in left:
        _augment(u, set())
    return match_right


def is_market_clearing(valuations, prices):
    """Are these prices market-clearing? If so, return a clearing matching.

    Builds the preferred-seller graph at ``prices`` and tests whether it admits a
    perfect matching — every buyer assigned a distinct preferred seller (Hall's
    condition, Section 10.3). Returns ``(True, {buyer: seller})`` when it clears
    (one valid clearing assignment, since ties can leave several), else
    ``(False, None)``.
    """
    prefs = preferred_seller_edges(valuations, prices)
    buyers = list(range(len(valuations)))
    match_right = _bipartite_matching(buyers, prefs)
    if len(match_right) == len(buyers):
        return True, {l: r for r, l in match_right.items()}
    return False, None


def optimal_assignment(valuations):
    """Maximum-total-valuation assignment of objects to agents (Section 10.2).

    ``valuations[i][j]`` is agent ``i``'s value for object ``j``. Returns the
    injective assignment ``{agent_index: object_index}`` maximizing the summed
    valuation — the social-welfare-maximizing ("optimal") matching. Brute-forced
    over injective assignments: exact, and the worksheets' markets are small
    (n <= 5). Ties break to the lexicographically-first arg-max (deterministic).
    """
    n = len(valuations)
    if n == 0:
        return {}
    m = len(valuations[0])
    best_total, best = None, None
    for perm in itertools.permutations(range(m), n):
        total = sum(valuations[i][perm[i]] for i in range(n))
        if best_total is None or total > best_total:
            best_total, best = total, {i: perm[i] for i in range(n)}
    return best


def find_constricted_set(left, right, edges):
    """A constricted set witnessing the absence of a perfect matching (Hall).

    ``left`` / ``right`` are node-id lists (any hashable); ``edges`` an iterable
    of ``(left_node, right_node)`` pairs. A set ``S`` of left nodes is
    *constricted* when ``|S| > |N(S)|`` — strictly more left nodes than the right
    nodes they collectively touch (Section 10.1's obstacle to a perfect
    matching). Returns ``(S, N(S))`` as two lists (each ordered as in ``left`` /
    ``right``) when no perfect matching exists, or ``None`` when one does.

    The witness is the canonical Konig set: take a maximum matching, then the
    left/right nodes reachable by alternating paths from the UNMATCHED left
    nodes. This is the tightest deficient set tied to the matching, and it is
    exactly the neighborhood the ascending auction must raise prices on — so the
    same routine drives ``ascending_auction_rounds``. (Other constricted sets can
    exist; this returns one valid witness, not necessarily the largest.)
    """
    adj = {u: [] for u in left}
    for u, v in edges:
        adj[u].append(v)
    match_right = _bipartite_matching(left, adj)
    if len(match_right) == len(left):
        return None
    matched_left = set(match_right.values())
    # Alternating BFS from every unmatched left node: left->right along ANY edge,
    # right->left along the matching edge only.
    reach_left = set(u for u in left if u not in matched_left)
    reach_right = set()
    stack = list(reach_left)
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v in reach_right:
                continue
            reach_right.add(v)
            w = match_right.get(v)
            if w is not None and w not in reach_left:
                reach_left.add(w)
                stack.append(w)
    S = [u for u in left if u in reach_left]
    NS = [v for v in right if v in reach_right]
    return S, NS


def auction_potential(valuations, prices):
    """Potential energy of the auction at the current prices (Section 10.4).

    The text's "potential energy" is the sum of every participant's potential
    payoff: each seller's potential is the price he charges, each buyer's is the
    maximum payoff ``max_j (v_ij - p_j)`` she can currently get. So the potential
    is ``sum(prices) + sum_i max_j (valuations[i][j] - prices[j])``. It starts at
    a whole number ``P0 >= 0`` and strictly decreases every round the auction
    raises prices, which is why the auction must terminate.
    """
    total = sum(prices)
    for row in valuations:
        total += max(row[j] - prices[j] for j in range(len(row)))
    return total


def ascending_auction_rounds(valuations):
    """Trace of the Demange-Gale-Sotomayor ascending auction (Section 10.4).

    All sellers start at price 0. Each round: build the preferred-seller graph;
    if it clears (perfect matching) the auction stops; otherwise take a
    constricted set ``S`` of buyers and raise every price in ``N(S)`` by one unit,
    then subtract the minimum price from all so the lowest price stays 0 (the
    text's price-reduction step — it never triggers while some seller sits at 0,
    but keeps the trace canonical in general). Returns one dict per round::

        {"prices": [...], "potential": P, "raised_set": [seller, ...],
         "matching": {buyer: seller} | None}

    ``raised_set`` lists the sellers whose price this round raises (empty on the
    final, clearing round); ``matching`` is ``None`` until the clearing round,
    where it holds the market-clearing assignment. The potential strictly
    decreases until clearing.
    """
    n = len(valuations)
    m = len(valuations[0]) if n else 0
    prices = [0 for _ in range(m)]
    buyers = list(range(n))
    sellers = list(range(m))
    rounds = []
    maxval = max((max(row) for row in valuations), default=0)
    # The potential strictly decreases and no price exceeds the max valuation, so
    # the auction always clears well within this many rounds; the bound is a
    # defensive backstop, not the termination argument.
    for _ in range((maxval + 2) * m + n + 2):
        prefs = preferred_seller_edges(valuations, prices)
        match_right = _bipartite_matching(buyers, prefs)
        potential = auction_potential(valuations, prices)
        if len(match_right) == n:
            rounds.append({"prices": list(prices), "potential": potential,
                           "raised_set": [],
                           "matching": {l: r for r, l in match_right.items()}})
            return rounds
        edges = [(b, s) for b, ss in prefs.items() for s in ss]
        S, NS = find_constricted_set(buyers, sellers, edges)
        rounds.append({"prices": list(prices), "potential": potential,
                       "raised_set": list(NS), "matching": None})
        for s in NS:
            prices[s] += 1
        low = min(prices) if prices else 0
        if low > 0:
            prices = [p - low for p in prices]
    return rounds


# -----------------------------------------------------------------------------
# Network-exchange bargaining helpers (Lesson 5, c12)
# -----------------------------------------------------------------------------
#
# Chapter 12 models exchange on a graph as an OUTCOME = (matching, node values):
# matched partners split $1 so their two values sum to 1, and an unmatched node
# has value 0. Two refinements sit on top of an outcome — STABILITY (no unused
# edge whose endpoints together make < 1, so no pair can profitably defect) and
# BALANCE (every matched split is the Nash bargaining outcome given the outside
# options the rest of the network endogenously provides). These COMPUTE helpers
# are the single source of truth for those predicates, exactly as the bipartite
# helpers above are for market clearing: the figures derive their keys/values
# from the helpers, so a rendered outcome can never drift from the definition.
#
# The layers unify. ``nash_bargaining_split`` is the two-person PRIMITIVE
# (Section 12.5); the graph-global checkers call the outside-option and split
# routines per matched/unmatched edge (Sections 12.7-12.8), so the same code
# serves both two-node bargaining and network exchange on an arbitrary graph.
#
# Values may be written as exact fractions rendered to floats (1/3, 2/3, ...);
# the "sum to 1" and split-equality tests use a small tolerance so, e.g.,
# 1/3 + 2/3 reads as exactly 1 rather than 0.999... .

#: Numerical tolerance for the bargaining predicates' equality/inequality tests.
_EXCHANGE_EPS = 1e-9


def nash_bargaining_split(x, y):
    """The Nash bargaining split of $1 with outside options x and y (Section 12.5).

    Two people divide one unit of money; A can walk away with an outside option
    of ``x`` and B with ``y``. When ``x + y > 1`` no division can beat both
    outside options, so there is NO DEAL and this returns ``None``. Otherwise the
    pair split the surplus ``s = 1 - x - y`` evenly on top of their outside
    options, giving the equidependent (Nash) division::

        A gets  x + s/2 = (x + 1 - y) / 2
        B gets  y + s/2 = (y + 1 - x) / 2

    Returns ``(share_x, share_y)`` — the shares of the party with outside option
    ``x`` and the party with outside option ``y``, in that order; they always sum
    to 1 — or ``None`` in the no-deal case. This is the two-player primitive the
    network-exchange checkers below call once per matched edge.
    """
    if x + y > 1 + _EXCHANGE_EPS:
        return None
    share_x = (x + 1 - y) / 2
    share_y = (y + 1 - x) / 2
    return share_x, share_y


def _exchange_partner_map(matching):
    """Map each matched node to its partner, from an iterable of edge pairs."""
    partner = {}
    for u, v in matching:
        partner[u] = v
        partner[v] = u
    return partner


def best_outside_option(node, G, matching, values):
    """A node's best outside option in the current outcome (Section 12.8).

    The outside option is the most a node can make by luring a neighbor away
    from that neighbor's current partnership: to steal neighbor ``Y`` the node
    must match Y's current value, keeping ``1 - values[Y]`` for itself. So the
    best outside option is the maximum of ``1 - values[Y]`` over every neighbor
    ``Y`` OTHER than the node's own current partner. An unmatched neighbor has
    value 0 and hence offers an outside option of 1 (you could pair with it and
    keep almost everything). A node with no eligible neighbor — e.g. a pendant
    whose only neighbor is its current partner — has an outside option of 0.

    These are the endogenous outside options the network provides; ``is_balanced``
    feeds them into the Nash split for each matched edge. (Missing entries in
    ``values`` are treated as 0, i.e. an unmatched node.)
    """
    partner = _exchange_partner_map(matching).get(node)
    opts = [1 - values.get(nbr, 0) for nbr in G.neighbors(node) if nbr != partner]
    return max(opts, default=0.0)


def find_instabilities(G, matching, values):
    """Every instability in the outcome (Section 12.7).

    An instability is an edge NOT in the matching whose two endpoints' values
    sum to strictly less than 1: the pair could abandon their current
    arrangements, exchange with each other, and both end up better off. Returns
    the list of witnessing edges as ``(u, v)`` tuples in ``G.edges()`` order. The
    strict ``< 1`` test carries a small tolerance, so an unused edge summing to
    exactly 1 (e.g. 1/3 + 2/3) is NOT flagged. (Missing entries in ``values`` are
    treated as 0.) An outcome is stable exactly when this list is empty.
    """
    matched = {frozenset(e) for e in matching}
    witnesses = []
    for u, v in G.edges():
        if frozenset((u, v)) in matched:
            continue
        if values.get(u, 0) + values.get(v, 0) < 1 - _EXCHANGE_EPS:
            witnesses.append((u, v))
    return witnesses


def is_stable(G, matching, values):
    """True iff the outcome contains no instabilities (Section 12.7).

    Thin wrapper over ``find_instabilities`` — an outcome is stable if and only
    if no unused edge joins two nodes whose values sum to less than 1.
    """
    return not find_instabilities(G, matching, values)


def is_balanced(G, matching, values):
    """True iff every matched split is its Nash bargaining outcome (Section 12.8).

    This is the balance CHECKER, not the solver: given a proposed outcome it
    verifies the balance fixed point rather than computing balanced values. For
    each edge in the matching it takes both endpoints' endogenous outside options
    (``best_outside_option``, derived from the rest of the network's current
    values), computes the Nash bargaining split for those outside options, and
    checks that the outcome's values match it (within tolerance). Returns False
    if any matched edge deviates, or if a matched pair's outside options sum to
    more than 1 (no Nash deal exists for them).

    Balance is a refinement of stability — every balanced outcome is stable —
    but this routine checks the balance condition directly and does not re-test
    stability. (Missing entries in ``values`` are treated as 0.)
    """
    for u, v in matching:
        x = best_outside_option(u, G, matching, values)
        y = best_outside_option(v, G, matching, values)
        split = nash_bargaining_split(x, y)
        if split is None:
            return False
        share_u, share_v = split
        if (abs(values.get(u, 0) - share_u) > _EXCHANGE_EPS
                or abs(values.get(v, 0) - share_v) > _EXCHANGE_EPS):
            return False
    return True


# --- renderer: bipartite matching market -------------------------------------

#: Matching-market figure styling (Lesson 4). Centralized — no inline literals in
#: the renderer. Every color DISTINCTION maps to a palette token, never raw hex:
#:   * left vs right partition  -> two-tone node borders (primary / quaternary);
#:   * open / fictitious nodes  -> faint dashed border + dashed edges (Fig 10.7);
#:   * constricted-set highlight -> accent border emphasis, distinct from fill;
#:   * matching vs option edges -> Arches bold-solid vs navy dashed.
BIPARTITE_STYLE = {
    "col_gap":          2.6,    # x-distance between the two node columns
    "row_gap":          1.0,    # y-distance between adjacent nodes in a column
    "node_radius":      0.20,   # node circle radius (data units; aspect equal)
    "node_fill":        "white",          # open-circle look (cf. GRAPH_STYLE)
    "left_edge_color":  COLORS["primary"],     # left partition border (navy)
    "right_edge_color": COLORS["quaternary"],  # right partition border (caramel)
    "node_edge_width":  2.0,
    "label_fontsize":        13,   # names placed BESIDE the node
    "inside_label_fontsize": 11,   # short ids drawn INSIDE the circle — smaller
                                   # so single digits/letters clear the node edge
    # option / preference edges vs the matching (answer) edges
    "edge_color":         COLORS["primary"],
    "edge_width":         1.5,
    "dashed_on_off":      (0, (4, 3)),    # dash pattern for option/open edges
    "match_edge_color":   COLORS["highlight"],   # Arches — the chosen matching
    "match_edge_width":   2.8,
    # open / fictitious nodes (Fig 10.7 auction panel)
    "open_edge_color":  COLORS["minor_tick"],
    # constricted-set highlight (border emphasis, distinct from fill)
    "constricted_color":  COLORS["accent"],
    "constricted_width":  3.0,
    "constricted_radius_delta": 0.035,
    # side-column annotations + titles
    "title_fontsize":   12,
    "annot_fontsize":   11,
    "price_color":      COLORS["accent"],
    "note_fontsize":    10,
}


def _bipartite_vector_label(vec):
    """Plain-text ``[a, b, c]`` for a valuation vector — NO mathtext.

    Deliberately unwrapped (no ``$…$``): these are bracketed integer vectors,
    not math, so plain text loses nothing — and it makes the ``$$`` double-wrap
    that crashes matplotlib's mathtext parser impossible by construction (a
    string with no ``$`` cannot be re-wrapped into one). Uses ``_fmt_num_plain``
    so a negative value renders a clean ``-3``, not ``_fmt_num``'s ``{-}3``."""
    return "[" + ", ".join(_fmt_num_plain(v) for v in vec) + "]"


def draw_bipartite_market(
    ax,
    *,
    left,
    right,
    edges=None,
    derive=None,
    prices=None,
    valuations=None,
    column_titles=("Sellers", "Buyers"),
    matching=None,
    constricted=None,
    open_nodes=None,
    edge_style=None,
    reveal="edges",
    note=None,
):
    """Render a bipartite matching market (Lesson 4, c10); answer COMPUTED.

    A stateless, side-neutral two-column bipartite figure. ``left`` and ``right``
    are node-id lists (any hashable; ids are formatted with ``subscript_label``,
    so ``m2`` -> m_2 while names pass through). The figure serves the THREE edge
    semantics of c10 (see the module helpers): explicit adjacency, the computed
    optimal assignment, and the computed preferred-seller graph.

    Edge source — pick ONE:

    - ``derive=None`` (default): the bipartite structure is the explicit
      ``edges`` (a list of ``(left_id, right_id)`` pairs) — Section 10.1's plain
      adjacency graph. Drawn solid.
    - ``derive="optimal_assignment"``: the max-total-valuation matching is
      computed from ``valuations`` alone (no prices) and drawn as the bold
      matching. Convention: the RIGHT column is the valuing side (one valuation
      vector per right node, ``valuations[right_index]``), the LEFT column the
      objects.
    - ``derive="preferred_seller"``: the preferred-seller graph
      ``argmax_j (v_ij - p_j)`` is computed from ``valuations`` + ``prices`` and
      drawn as dashed option edges. Convention: LEFT = sellers (aligned to
      ``prices``), RIGHT = buyers (aligned to ``valuations`` rows). With
      ``matching="auto"`` the market-clearing matching (if any) is overlaid bold.

    Annotations align to node rows: ``prices`` is the outer-LEFT column (one per
    left node), ``valuations`` the outer-RIGHT column (one vector per right
    node). ``matching`` is an explicit list of ``(left_id, right_id)`` pairs to
    bold, or ``"auto"`` to derive; ``constricted`` is an explicit ``(S, N(S))``
    pair of id-lists to highlight, or ``"auto"`` to derive via
    ``find_constricted_set``. ``open_nodes`` lists fictitious/empty nodes (drawn
    unfilled with a faint dashed border and dashed incident edges, e.g. the
    Fig 10.7 auction panel). ``edge_style`` is a per-edge
    ``{(l, r): "solid"|"dashed"}`` override.

    ``reveal`` is the answer-leak guard (analog of ``mask_winner_price``):

    - ``"edges"`` (default): show everything — explicit edges, derived option
      edges, the bold matching, and the constricted highlight.
    - ``"none"``: show only the explicit ``edges`` (the question's given
      structure), the nodes, and the side columns. Everything DERIVED — the
      preferred-seller option edges, the matching, the constricted highlight — is
      hidden, so the figure can pose the question without leaking its answer.

    Side-neutral: the draw core never assumes which column is sellers/people;
    ``column_titles`` and the pricing semantics live in the caller. Returns a
    dict ``{"edges", "matching", "constricted", "clears"}`` recording what was
    computed (handy for Stage-2 widget wrappers and tests).
    """
    if reveal not in ("edges", "none"):
        raise ValueError(f"reveal must be 'edges' or 'none', got {reveal!r}")
    st = BIPARTITE_STYLE
    left = list(left)
    right = list(right)
    open_set = set(open_nodes or [])

    # --- resolve edge sources (derive when asked) -------------------------
    explicit_edges = [tuple(e) for e in (edges or [])]
    derived_options = []          # dashed preference edges (preferred_seller)
    matching_pairs = []           # bold matching edges
    clears = None

    if derive == "preferred_seller":
        prefs = preferred_seller_edges(valuations, prices)
        derived_options = [(left[s], right[b])
                           for b, ss in prefs.items() for s in ss]
        if matching == "auto":
            clears, mm = is_market_clearing(valuations, prices)
            if mm:
                matching_pairs = [(left[s], right[b]) for b, s in mm.items()]
    elif derive == "optimal_assignment":
        assign = optimal_assignment(valuations)
        matching_pairs = [(left[o], right[a]) for a, o in assign.items()]
    elif derive is not None:
        raise ValueError(
            "derive must be None, 'preferred_seller', or 'optimal_assignment', "
            f"got {derive!r}")

    # explicit matching (only when not auto-derived)
    if isinstance(matching, str):
        if matching != "auto":
            raise ValueError(f"matching must be a list or 'auto', got {matching!r}")
    elif matching is not None:
        matching_pairs = [tuple(e) for e in matching]

    # constricted set: explicit (S, N(S)) or "auto". For a priced market the
    # Hall-violating side is the BUYERS (right) — a set of buyers chasing too few
    # preferred sellers, exactly why prices don't clear — so derive it there; for
    # a plain adjacency graph it is the left side, find_constricted_set's native
    # orientation. Highlighting itself is side-agnostic (it keys off node ids).
    constr = None
    if constricted == "auto":
        if derive == "preferred_seller":
            rev = [(r, l) for (l, r) in derived_options]
            constr = find_constricted_set(right, left, rev)
        else:
            constr = find_constricted_set(left, right,
                                          explicit_edges + derived_options)
    elif constricted is not None:
        constr = (list(constricted[0]), list(constricted[1]))

    # --- answer-leak guard ------------------------------------------------
    # Explicit edges are the QUESTION'S structure (always shown). Everything
    # derived (preference edges, matching, constricted highlight) is the ANSWER.
    if reveal == "none":
        option_edges = [(l, r, "solid") for (l, r) in explicit_edges]
        shown_matching = []
        shown_constr = None
    else:
        option_edges = ([(l, r, "solid") for (l, r) in explicit_edges]
                        + [(l, r, "dashed") for (l, r) in derived_options])
        shown_matching = list(matching_pairs)
        shown_constr = constr

    # per-edge style override
    def _style_of(l, r, default):
        if edge_style:
            s = edge_style.get((l, r)) or edge_style.get((r, l))
            if s:
                return s
        return default

    match_set = {tuple(sorted(map(str, e))) for e in shown_matching}
    S_set = set(shown_constr[0]) if shown_constr else set()

    # --- geometry ---------------------------------------------------------
    nL, nR = len(left), len(right)
    G = st["row_gap"]
    x_left, x_right = 0.0, st["col_gap"]
    R = st["node_radius"]

    def _col_y(n, i):
        return ((n - 1) / 2.0 - i) * G

    pos_left = {left[i]: (x_left, _col_y(nL, i)) for i in range(nL)}
    pos_right = {right[j]: (x_right, _col_y(nR, j)) for j in range(nR)}

    # Short ids (<= 2 chars: a/b/c, x/y/z, room numbers) sit INSIDE the node;
    # longer labels (names) sit BESIDE it on the outer side so they never spill
    # over the circle. Annotation columns are then pushed out past the labels.
    label_pad, name_room = 0.16, 1.25
    left_inside = nL > 0 and max(len(str(n)) for n in left) <= 2
    right_inside = nR > 0 and max(len(str(n)) for n in right) <= 2

    if left_inside:
        left_label_x, left_label_ha = x_left, "center"
        price_x = x_left - 0.55
        left_edge = (price_x - 0.4) if prices is not None else (x_left - R - 0.4)
    else:
        left_label_x, left_label_ha = x_left - (R + label_pad), "right"
        price_x = left_label_x - name_room
        left_edge = (price_x - 0.4) if prices is not None \
            else (left_label_x - name_room)
    if right_inside:
        right_label_x, right_label_ha = x_right, "center"
        val_x = x_right + 0.5
        right_edge = (val_x + 1.7) if valuations is not None else (x_right + R + 0.4)
    else:
        right_label_x, right_label_ha = x_right + (R + label_pad), "left"
        val_x = right_label_x + name_room
        right_edge = (val_x + 1.7) if valuations is not None \
            else (right_label_x + name_room)

    ax.set_aspect("equal")
    top = max(_col_y(nL, 0) if nL else 0.0, _col_y(nR, 0) if nR else 0.0)
    bot = min(_col_y(nL, nL - 1) if nL else 0.0, _col_y(nR, nR - 1) if nR else 0.0)
    ax.set_xlim(left_edge, right_edge)
    ax.set_ylim(bot - 0.95, top + 1.1)
    ax.autoscale(False)
    ax.set_axis_off()

    # --- edges ------------------------------------------------------------
    def _draw_edge(l, r, *, color, width, style, zorder):
        if l not in pos_left or r not in pos_right:
            return
        x0, y0 = pos_left[l]
        x1, y1 = pos_right[r]
        ax.plot([x0, x1], [y0, y1], color=color, linewidth=width,
                linestyle=style, zorder=zorder, solid_capstyle="round")

    def _ls(name):
        return st["dashed_on_off"] if name == "dashed" else "-"

    for (l, r, default) in option_edges:
        if tuple(sorted((str(l), str(r)))) in match_set:
            continue  # drawn bold below; don't double-draw under it
        is_open = l in open_set or r in open_set
        style = _ls("dashed") if is_open else _ls(_style_of(l, r, default))
        color = st["open_edge_color"] if is_open else st["edge_color"]
        _draw_edge(l, r, color=color, width=st["edge_width"], style=style,
                   zorder=1)

    # constricted emphasis: edges incident to S (either endpoint, so it works
    # whether S is the left or the right partition) drawn accent.
    if shown_constr:
        for (l, r, _d) in option_edges:
            if l in S_set or r in S_set:
                _draw_edge(l, r, color=st["constricted_color"],
                           width=st["edge_width"] + 0.6, style="-", zorder=1.5)

    # matching (the answer): bold Arches solid
    for (l, r) in shown_matching:
        _draw_edge(l, r, color=st["match_edge_color"],
                   width=st["match_edge_width"], style="-", zorder=2)

    # --- nodes ------------------------------------------------------------
    from matplotlib.patches import Circle

    def _draw_node(nid, x, y, base_color, label_x, label_ha):
        is_open = nid in open_set
        is_constr = nid in S_set or (shown_constr and nid in set(shown_constr[1]))
        if is_constr:
            ax.add_patch(Circle(
                (x, y), R + st["constricted_radius_delta"],
                facecolor=st["node_fill"], edgecolor=st["constricted_color"],
                linewidth=st["constricted_width"], zorder=3))
        else:
            ax.add_patch(Circle(
                (x, y), R, facecolor=st["node_fill"],
                edgecolor=(st["open_edge_color"] if is_open else base_color),
                linewidth=st["node_edge_width"], zorder=3,
                linestyle=(st["dashed_on_off"] if is_open else "-")))
        # Short ids sit INSIDE the circle (ha="center") and must clear the node
        # edge, so they use the smaller inside_label_fontsize; names placed
        # BESIDE the node (ha="left"/"right") keep the full label_fontsize.
        inside = label_ha == "center"
        ax.text(label_x, y, subscript_label(nid), ha=label_ha, va="center",
                fontsize=st["inside_label_fontsize"] if inside
                else st["label_fontsize"],
                color=COLORS["text"], zorder=4)

    for nid, (x, y) in pos_left.items():
        _draw_node(nid, x, y, st["left_edge_color"], left_label_x, left_label_ha)
    for nid, (x, y) in pos_right.items():
        _draw_node(nid, x, y, st["right_edge_color"], right_label_x, right_label_ha)

    # --- side columns (aligned to node rows) ------------------------------
    if prices is not None:
        for i in range(min(nL, len(prices))):
            _, y = pos_left[left[i]]
            ax.text(price_x, y, _fmt_num_plain(prices[i]),
                    ha="right", va="center", fontsize=st["annot_fontsize"],
                    color=st["price_color"], zorder=4)
        ax.text(price_x, top + 0.5, "price", ha="right", va="bottom",
                fontsize=st["annot_fontsize"], color=st["price_color"],
                style="italic", zorder=4)
    if valuations is not None:
        for j in range(min(nR, len(valuations))):
            _, y = pos_right[right[j]]
            ax.text(val_x, y, _bipartite_vector_label(valuations[j]),
                    ha="left", va="center", fontsize=st["annot_fontsize"],
                    color=COLORS["text"], zorder=4)
        ax.text(val_x, top + 0.5, "valuations", ha="left", va="bottom",
                fontsize=st["annot_fontsize"], color=COLORS["text"],
                style="italic", zorder=4)

    # --- column titles + note --------------------------------------------
    lt, rt = column_titles
    ax.text(x_left, top + 0.74, str(lt), ha="center", va="bottom",
            fontsize=st["title_fontsize"], fontweight="bold",
            color=COLORS["primary"], zorder=4)
    ax.text(x_right, top + 0.74, str(rt), ha="center", va="bottom",
            fontsize=st["title_fontsize"], fontweight="bold",
            color=COLORS["primary"], zorder=4)
    if note:
        ax.text((x_left + x_right) / 2.0, bot - 0.7, str(note),
                ha="center", va="top", fontsize=st["note_fontsize"],
                color=COLORS["text"], zorder=4)

    return {"edges": [(l, r) for (l, r, _s) in option_edges],
            "matching": list(shown_matching),
            "constricted": shown_constr,
            "clears": clears}


# -----------------------------------------------------------------------------
# Annotation helper for missing/forbidden edges
# -----------------------------------------------------------------------------

def draw_missing_edge(ax, pos, u, v, *, color=None, alpha=None):
    """Draw a dotted orange line between two nodes to mark a "missing" edge.

    Used by concept cells that need to show an edge which *should* exist
    (e.g. STC violations, expected triadic closure) but does not. The
    dotted style distinguishes it visually from real edges in the graph.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    pos : dict
        Position dict from draw_graph or networkx layout.
    u, v : node IDs
        Endpoints of the missing edge.
    color : str, optional
        Defaults to ``GRAPH_STYLE["missing_edge_color"]``.
    alpha : float, optional
        Defaults to ``GRAPH_STYLE["missing_edge_alpha"]``.
    """
    if color is None:
        color = GRAPH_STYLE["missing_edge_color"]
    if alpha is None:
        alpha = GRAPH_STYLE["missing_edge_alpha"]
    xu, yu = pos[u]
    xv, yv = pos[v]
    ax.plot(
        [xu, xv], [yu, yv],
        color=color,
        linestyle=GRAPH_STYLE["missing_edge_style"],
        linewidth=GRAPH_STYLE["missing_edge_width"],
        alpha=alpha,
        zorder=GRAPH_STYLE["missing_edge_zorder"],
    )


# -----------------------------------------------------------------------------
# Text annotation helper
# -----------------------------------------------------------------------------

def annotate(ax, text, *, loc="bottom-left", fontsize=10):
    """Add a small annotation block to a figure in the project's style.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    text : str
        The annotation content. Multi-line allowed. MathJax-style math
        (e.g., r"$N(u)$") renders via matplotlib's mathtext.
    loc : str
        One of "bottom-left", "top-left", "bottom-right", "top-right".
    fontsize : int
        Annotation font size.
    """
    presets = {
        "bottom-left":  (0.02, 0.02, "left",  "bottom"),
        "top-left":     (0.02, 0.98, "left",  "top"),
        "bottom-right": (0.98, 0.02, "right", "bottom"),
        "top-right":    (0.98, 0.98, "right", "top"),
    }
    if loc not in presets:
        raise ValueError(f"Unknown loc {loc!r}; expected one of {list(presets)}")
    x, y, ha, va = presets[loc]
    ax.text(
        x, y, text,
        transform=ax.transAxes,
        fontsize=fontsize,
        family="sans-serif",
        horizontalalignment=ha,
        verticalalignment=va,
        color=COLORS["text"],
    )
