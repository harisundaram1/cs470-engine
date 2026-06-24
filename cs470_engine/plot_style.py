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

import math
import re

import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.patches import PathPatch
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
}


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


def draw_directed_graph(G, ax, *, pos, labels=None, node_size=None,
                        highlight_edges=None, highlight_color=None):
    """Draw a directed graph as a causal DAG: arrowheads, labels inside nodes.

    Open-circle nodes (sized for their labels), navy directed edges with
    arrowheads, optional LaTeX ``labels`` map (id -> text), optional
    ``highlight_edges`` drawn in the accent/given color. Frames the axes from the
    node positions with margin (no autoscale-to-patches) and sets equal aspect.
    """
    node_size = node_size or DAG_NODE_SIZE
    highlight = {tuple(e) for e in (highlight_edges or [])}
    hl_color = highlight_color or COLORS["accent"]

    frame_signed_axes(ax, pos, node_size=node_size, rad=0.0)

    for u, v in G.edges():
        is_hl = (u, v) in highlight
        nx.draw_networkx_edges(
            G, pos, edgelist=[(u, v)], ax=ax,
            edge_color=hl_color if is_hl else GRAPH_STYLE["edge_color"],
            width=2.6 if is_hl else 1.4,
            arrows=True, arrowstyle="-|>", arrowsize=16,
            node_size=node_size, min_source_margin=15, min_target_margin=15,
        )
    nx.draw_networkx_nodes(
        G, pos, ax=ax, node_size=node_size,
        node_color=GRAPH_STYLE["node_fill"],
        edgecolors=GRAPH_STYLE["node_edge_color"],
        linewidths=GRAPH_STYLE["node_edge_width"],
    )
    nx.draw_networkx_labels(
        G, pos, labels=labels, ax=ax,
        font_size=DAG_LABEL_FONTSIZE, font_color=COLORS["text"],
    )
    ax.set_axis_off()


# -----------------------------------------------------------------------------
# Graph rendering helper
# -----------------------------------------------------------------------------

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

    base_solid = [e for e in solid_all if not _is_highlighted(*e)]
    base_dashed = [e for e in dashed_all if not _is_highlighted(*e)]
    hl_solid = [e for e in solid_all if _is_highlighted(*e)]
    hl_dashed = [e for e in dashed_all if _is_highlighted(*e)]

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

    # Nodes: highlighted ones drawn with thicker accent-color edge
    other = [n for n in G.nodes() if n not in highlight_nodes]
    if other:
        nx.draw_networkx_nodes(
            G, pos, ax=ax, nodelist=other,
            node_color=GRAPH_STYLE["node_fill"],
            edgecolors=GRAPH_STYLE["node_edge_color"],
            linewidths=GRAPH_STYLE["node_edge_width"],
            node_size=node_size,
        )
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

    ax.set_axis_off()
    return pos


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
    equilibrium shade ``(n-1)/n * value``.

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
