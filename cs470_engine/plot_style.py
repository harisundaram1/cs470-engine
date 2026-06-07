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
