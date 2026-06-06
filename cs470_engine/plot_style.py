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

import matplotlib.pyplot as plt
from matplotlib import rcParams
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

#: Gentle, consistent curvature for signed edges so the two members of a
#: crossing pair (e.g. the A-D / B-C diagonals) bow apart and their sign labels
#: never overlap. Matches the worksheet module's ``_draw_signed_graph``.
_SIGN_EDGE_RAD = 0.22


def _sign_label(sign):
    """Mathtext sign glyph — ``$-$`` avoids any Helvetica/Unicode fallback."""
    return "$+$" if sign == _SIGN_POS else "$-$"


def _sign_color(sign):
    """Positive edges navy (primary); negative edges red (bad)."""
    return COLORS["primary"] if sign == _SIGN_POS else COLORS["bad"]


def _arc_apex(p_u, p_v, rad):
    """Apex (t=0.5 point) of matplotlib's ``arc3,rad`` quadratic Bezier.

    The control point is the straight midpoint displaced perpendicular to the
    edge by ``rad * |edge|`` (positive rad bows toward ``(-dy, dx)``), so the
    apex — where the sign label belongs — is the midpoint displaced by
    ``(rad / 2) * |edge|`` along that same perpendicular. networkx/matplotlib
    otherwise place edge labels at the straight midpoint even on curved edges.
    """
    (x1, y1), (x2, y2) = p_u, p_v
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return mx, my
    nx_, ny_ = -dy / length, dx / length
    off = 0.5 * rad * length
    return mx + nx_ * off, my + ny_ * off


def _draw_signed_edges(G, pos, ax, signed_edges, *, highlight_set, node_size):
    """Draw signed edges with curvature + apex sign labels + sign color.

    Mirrors the worksheet module's ``_draw_signed_graph`` so concept-cell and
    question signed graphs look identical. Highlighted signed edges use the
    Arches highlight color and a thicker stroke.
    """
    conn = f"arc3,rad={_SIGN_EDGE_RAD}"
    for u, v in signed_edges:
        sign = (G.get_edge_data(u, v) or {}).get(_SIGN_KEY)
        highlighted = tuple(sorted((u, v))) in highlight_set
        if highlighted:
            color = COLORS["highlight"]
            width = GRAPH_STYLE["highlight_edge_width"]
        else:
            color = _sign_color(sign)
            width = GRAPH_STYLE["edge_width"]
        # arrows=True forces FancyArrowPatches (the LineCollection path silently
        # ignores connectionstyle); arrowstyle="-" keeps edges headless.
        nx.draw_networkx_edges(
            G, pos, ax=ax, edgelist=[(u, v)],
            edge_color=color, width=width,
            connectionstyle=conn, arrows=True, arrowstyle="-",
            node_size=node_size,
        )
    # Sign labels at each edge's curved-arc apex.
    for u, v in signed_edges:
        sign = (G.get_edge_data(u, v) or {}).get(_SIGN_KEY)
        lx, ly = _arc_apex(pos[u], pos[v], _SIGN_EDGE_RAD)
        lab_color = (COLORS["highlight"] if tuple(sorted((u, v))) in highlight_set
                     else _sign_color(sign))
        ax.text(
            lx, ly, _sign_label(sign),
            ha="center", va="center",
            fontsize=GRAPH_STYLE["label_font_size"],
            color=lab_color,
            bbox=dict(boxstyle="circle,pad=0.12", fc="white", ec="none"),
            zorder=4,
        )


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
        nx.draw_networkx_labels(
            G, pos, ax=ax,
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
