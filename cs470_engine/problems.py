"""Problem-cell rendering.

Supports both single-select and multi-select MC via a unified
``OptionPicker`` widget that typesets ``$math$`` in option labels via
MathJax. Layout per design doc §6.1.
"""

from fractions import Fraction

import matplotlib.pyplot as plt
import networkx as nx
import ipywidgets as widgets
import markdown as _markdown
from IPython.display import display, Markdown, HTML

from .plot_style import HINT_SUMMARY_STYLE
from .scoring import credit_for_attempt, multi_select_credit, MAX_ATTEMPTS
from .widgets import OptionPicker, submit_button_with_gate
from .messages import mathjax_safe_currency


def render_problem(ws, problem: dict) -> None:
    qtype = problem.get("question_type", "single_select")
    if qtype == "multi_select":
        _render_problem_cell(ws, problem, mode="multi_select")
    else:
        _render_problem_cell(ws, problem, mode="single_select")


def _display_id(pid: str) -> str:
    """Render `q_3` as `Q3` from the INTERNAL id (fallback when no display map)."""
    return pid.replace("q_", "Q") if pid.startswith("q_") else pid


def _q_display(ws, pid: str) -> str:
    """Visible question label ``Q<n>`` using the sequential DISPLAY NUMBER
    (interleaved on-page position). Falls back to the id-derived label when no
    display map is present (older engine path / a pid outside the map)."""
    dn = getattr(ws, "display_number", None)
    if dn and pid in dn:
        return f"Q{dn[pid]}"
    return _display_id(pid)


def _internal_id_html(ws, pid: str) -> str:
    """Small muted ``(q_N)`` suffix beside the display number, for author/TA
    cross-reference. Shown ONLY when the worksheet is reordered (display number
    != id), so an un-interleaved worksheet (1.x) is unchanged. Display-only —
    never enters grading, results.json, the shuffle seed, or the persistence
    record (all of which key on ``pid``)."""
    if not getattr(ws, "display_reordered", False):
        return ""
    return (f' <span style="color: #9aa3ad; font-size: 0.82em;">'
            f'({pid})</span>')


def _shuffle_seed(ws, pid: str) -> str | None:
    """Per-(student, problem) seed string for the MC option-display shuffle.

    ``"<session_id>:<pid>"`` — varies the option order per student (session) and
    per problem, deterministically. Returns None when there is no session id
    (e.g. answer-key/QA never opens a student session), which keeps the
    canonical authored order. The live and restored render paths pass the same
    pid, so a reopened problem shows the same order the student answered in.
    """
    session_id = getattr(ws, "session_id", None)
    if not session_id:
        return None
    return f"{session_id}:{pid}"


def _render_problem_cell(ws, problem: dict, mode: str) -> None:
    """Unified problem renderer for both single- and multi-select MC.

    Differences between modes live entirely in the submit handler — scoring
    and lock semantics. The OptionPicker handles the rest uniformly.
    """
    pid = problem["id"]
    diff = problem["difficulty"]
    has_hint = bool(problem.get("hint_markdown"))
    hint_glyph = " · 💡" if has_hint else ""
    mode_hint = " · select all that apply" if mode == "multi_select" else ""

    display(Markdown(
        f"**{_q_display(ws, pid)} · {diff}**{hint_glyph}{mode_hint}"
        f"{_internal_id_html(ws, pid)}"
    ))
    display(Markdown(mathjax_safe_currency(problem["prompt_markdown"])))

    if has_hint:
        # <details> works without JS in Colab and Jupyter per design doc §6.2.
        hint_html = _markdown.markdown(
            problem["hint_markdown"], extensions=["extra"]
        )
        display(HTML(
            '<details style="margin: 0.5em 0;">'
            f'<summary style="{HINT_SUMMARY_STYLE}">💡 Show hint</summary>'
            f'<div style="padding: 0.5em 1em;">{hint_html}</div>'
            '</details>'
        ))

    figure_spec = problem.get("figure")
    if figure_spec:
        fig_out = widgets.Output()
        with fig_out:
            _render_figure(ws, figure_spec)
        display(fig_out)

    options = problem["options"]
    correct = list(problem.get("correct") or [])
    correct_set = set(correct)

    # WIDGET RESTORATION: if this problem was answered in an earlier session that
    # we restored at load() (kernel restart / workspace reopen), render it as
    # already-answered — pre-fill the prior choice, lock it, show the recorded
    # credit + rationale — instead of the live submit flow. The record is already
    # in ws.scores (so finalize is correct regardless); this just makes progress
    # visible and saves the student redoing it.
    restored = ws.scores.get(pid) if getattr(ws, "restored_session", False) else None
    if restored is not None:
        _render_restored_problem(ws, problem, mode, restored, correct)
        return

    picker = OptionPicker(
        [(opt["id"], opt["text"]) for opt in options],
        mode=mode,
        shuffle_seed=_shuffle_seed(ws, pid),
    )
    display(picker.widget)

    feedback_out = widgets.Output()
    attempts_label = widgets.Label(value=f"Attempts: 0 of {MAX_ATTEMPTS}")
    state = {"attempt": 0, "answered": False, "gate_cleared": False}

    def on_submit(btn):
        if state["answered"]:
            return
        if not picker.has_selection:
            with feedback_out:
                feedback_out.clear_output()
                display(Markdown("*Please select an option before submitting.*"))
            return

        state["attempt"] += 1
        attempt = state["attempt"]
        chosen_set = set(picker.selected_ids)
        is_perfect = chosen_set == correct_set

        if mode == "multi_select":
            credit = multi_select_credit(chosen_set, correct_set, attempt)
        else:
            credit = credit_for_attempt(attempt) if is_perfect else 0.0

        attempts_label.value = f"Attempts: {attempt} of {MAX_ATTEMPTS}"

        # Lock on a perfect match or on the final attempt.
        if is_perfect or attempt >= MAX_ATTEMPTS:
            state["answered"] = True
            btn.disabled = True
            picker.lock()
            picker.show_correct(correct)

            if is_perfect:
                marker, tag = "✓", "Correct"
            elif credit > 0:
                marker, tag = "◐", "Partial credit"
            else:
                marker, tag = "✗", "Out of attempts"

            with feedback_out:
                feedback_out.clear_output()
                display(Markdown(
                    f"**{marker} {tag}** — credit {credit:.2f}\n\n"
                    f"**Rationale:** "
                    f"{mathjax_safe_currency(problem['rationale_markdown'])}"
                ))
        else:
            with feedback_out:
                feedback_out.clear_output()
                display(Markdown(
                    f"*Not quite — try again. "
                    f"(Attempt {attempt} of {MAX_ATTEMPTS}.)*"
                ))

        ws._record_answer(
            pid=pid, attempt=attempt, is_correct=is_perfect,
            credit=credit, locked=state["answered"],
            chosen=list(chosen_set),
        )

    def on_gate_clear():
        state["gate_cleared"] = True
        if picker.has_selection and not state["answered"]:
            btn.disabled = False

    time_gate = problem.get("time_gate_seconds_override",
                            ws.time_gates.get(diff, 30))
    btn = submit_button_with_gate(int(time_gate), on_submit,
                                  on_gate_clear=on_gate_clear)

    def on_selection_change(_change):
        if state["answered"] or not state["gate_cleared"]:
            return
        btn.disabled = not picker.has_selection

    picker.observe(on_selection_change)

    display(widgets.HBox([btn, attempts_label]))
    display(feedback_out)


def _render_restored_problem(ws, problem: dict, mode: str, entry: dict,
                             correct: list) -> None:
    """Render a problem already answered in a restored (reopened) session.

    Pre-fills the student's recorded choice, locks the picker, marks correct/
    wrong, and shows the recorded credit + rationale. No submit button, no time
    gate — the answer is already in ``ws.scores`` and counts toward finalize.
    """
    from .messages import RESTORED_ANSWER_BANNER_MD

    options = problem["options"]
    chosen = list(entry.get("chosen") or [])
    credit = float(entry.get("credit", 0.0))
    attempt = int(entry.get("attempt", 0))
    is_correct = bool(entry.get("correct", False))

    display(Markdown(RESTORED_ANSWER_BANNER_MD))
    picker = OptionPicker(
        [(opt["id"], opt["text"]) for opt in options],
        mode=("multi_select" if mode == "multi_select" else "single_select"),
        # SAME seed as the live render (session_id + pid) so the restored cell
        # shows options in the order the student answered in — the pre-filled,
        # locked choice then lines up with the checkbox they actually clicked.
        shuffle_seed=_shuffle_seed(ws, problem["id"]),
    )
    if chosen:
        picker.pre_select(chosen)
    picker.lock()
    picker.show_correct(correct)
    display(picker.widget)

    if is_correct:
        tries = "try" if attempt == 1 else "tries"
        marker, tag = "✓", f"Correct ({attempt} {tries})"
    elif credit > 0:
        marker, tag = "◐", "Partial credit"
    else:
        marker, tag = "✗", "No credit"
    display(Markdown(
        f"**{marker} {tag}** — recorded credit {credit:.2f}\n\n"
        f"**Rationale:** "
        f"{mathjax_safe_currency(problem['rationale_markdown'])}"
    ))


def render_problem_answer_key(ws, problem: dict) -> None:
    """Answer-key (instructor QA) render for a problem.

    No submit button, no time gate, no attempts label. The OptionPicker
    is instantiated with the correct option(s) pre-checked, locked, and
    annotated via ``show_correct``. The hint and rationale are displayed
    inline so the author can scan the cell without interaction.
    """
    pid = problem["id"]
    diff = problem["difficulty"]
    qtype = problem.get("question_type", "single_select")
    mode_hint = " · select all that apply" if qtype == "multi_select" else ""

    display(Markdown(
        f"**[ANSWER KEY] {_q_display(ws, pid)} · {diff}**{mode_hint}"
        f"{_internal_id_html(ws, pid)}"
    ))
    display(Markdown(mathjax_safe_currency(problem["prompt_markdown"])))

    if problem.get("hint_markdown"):
        hint_html = _markdown.markdown(
            problem["hint_markdown"], extensions=["extra"]
        )
        display(HTML(
            f'<div style="margin: 0.4em 0; padding: 0.5em 0.8em; '
            f'background: #EEF0F7; border-radius: 4px;">'
            f'<em>Hint (instructor view):</em> {hint_html}</div>'
        ))

    figure_spec = problem.get("figure")
    if figure_spec:
        fig_out = widgets.Output()
        with fig_out:
            _render_figure(ws, figure_spec)
        display(fig_out)

    options = problem["options"]
    correct = list(problem.get("correct") or [])
    picker = OptionPicker(
        [(opt["id"], opt["text"]) for opt in options],
        mode=("multi_select" if qtype == "multi_select" else "single_select"),
    )
    picker.pre_select(correct)
    picker.lock()
    picker.show_correct(correct)
    display(picker.widget)

    display(Markdown(
        f"**Rationale:** "
        f"{mathjax_safe_currency(problem['rationale_markdown'])}"
    ))


def _resolve_figure_path(ws, path: str):
    """Resolve a figure ``path`` for ``kind: image`` to an existing file.

    Tries, in order: the path as given / relative to cwd; relative to the
    worksheet YAML's directory and each ancestor (covers a ``figs/...`` path in
    the dev tree and a flat PL workspace where the image ships beside the YAML);
    and finally the bare basename beside the YAML. Returns a ``Path`` or None.
    """
    from pathlib import Path
    p = Path(path)
    candidates = [p, Path.cwd() / p]
    src = getattr(ws, "source_path", None)
    if src is not None:
        src = Path(src)
        for base in [src.parent, *src.parent.parents]:
            candidates.append(base / p)
            candidates.append(base / p.name)  # flat: image beside the YAML
    for c in candidates:
        if c.exists():
            return c
    return None


def _render_payoff_matrix(figure_spec: dict) -> None:
    """Render a ``kind: payoff_matrix`` figure spec.

    Reads the spec's matrix data and (optional) ``highlight`` mode, then calls
    ``plot_style.draw_payoff_matrix`` — which COMPUTES best responses / Nash /
    dominance from the payoffs, so the overlay can't drift from the answer key.
    Cell payoffs come from ``payoffs`` (n x m of ``[p_row, p_col]``).
    """
    from .plot_style import draw_payoff_matrix, PAYOFF_STYLE

    payoffs = figure_spec.get("payoffs") or []
    n = len(payoffs)
    m = len(payoffs[0]) if n else 0
    if n == 0 or m == 0:
        print("[engine] payoff_matrix figure has no `payoffs` data.")
        return
    # Normalize each cell to a (p_row, p_col) tuple (YAML lists -> tuples).
    payoffs = [[tuple(cell) for cell in row] for row in payoffs]

    st = PAYOFF_STYLE
    figsize = (st["margin_in"] + m * st["cell_size_in"],
               st["margin_in"] + n * st["cell_size_in"])
    fig, ax = plt.subplots(figsize=figsize)
    draw_payoff_matrix(
        ax, payoffs,
        row_player=figure_spec.get("row_player", "Player 1"),
        col_player=figure_spec.get("col_player", "Player 2"),
        row_strategies=figure_spec.get("row_strategies"),
        col_strategies=figure_spec.get("col_strategies"),
        highlight=figure_spec.get("highlight", "none"),
        against=figure_spec.get("against"),
        note=figure_spec.get("note"),
    )
    plt.tight_layout()
    display(fig)
    plt.close(fig)


def _render_auction(figure_spec: dict) -> None:
    """Render the Lesson-3 auction figure kinds.

    ``auction_table`` / ``bid_payoff_curve`` / ``revenue_curve`` /
    ``common_value_bids`` — each defers winner/price/payoff/optimum to the
    plot_style auction helpers, so the drawn figure can't drift from the key.
    """
    from . import plot_style as ps
    kind = figure_spec.get("kind")
    st = ps.AUCTION_STYLE

    if kind == "auction_table":
        bids = figure_spec.get("bids")
        if not bids:
            print("[engine] auction_table figure has no `bids`.")
            return
        n = len(bids)
        fig, ax = plt.subplots(figsize=(st["margin_in"] + 6 * st["col_width_in"],
                                        st["margin_in"] + (n + 1) * st["row_height_in"]))
        ps.draw_auction_table(
            ax, bids=bids, values=figure_spec.get("values"),
            fmt=figure_spec.get("format", "second_price"),
            reserve=figure_spec.get("reserve"),
            labels=figure_spec.get("labels"), note=figure_spec.get("note"),
            mask_winner_price=figure_spec.get("mask_winner_price", False),
        )
    elif kind == "bid_payoff_curve":
        fig, ax = plt.subplots(figsize=(5.4, 3.6))
        ps.draw_bid_payoff_curve(
            ax, mode=figure_spec.get("mode", "second_price"),
            value=figure_spec.get("value", 1.0),
            highest_other=figure_spec.get("highest_other"),
            n=figure_spec.get("n", 2), your_bid=figure_spec.get("your_bid"),
            note=figure_spec.get("note"),
        )
    elif kind == "revenue_curve":
        fig, ax = plt.subplots(figsize=(5.4, 3.6))
        ps.draw_revenue_curve(
            ax, kind=figure_spec.get("curve", "reserve"),
            seller_value=figure_spec.get("seller_value", 0.0),
            n_max=figure_spec.get("n_max", 8), note=figure_spec.get("note"),
        )
    elif kind == "common_value_bids":
        fig, ax = plt.subplots(figsize=(6.0, 2.6))
        ps.draw_common_value_bids(
            ax, common_value=figure_spec.get("common_value", 0.5),
            estimates=figure_spec.get("estimates") or [],
            note=figure_spec.get("note"),
        )
    else:
        return
    plt.tight_layout()
    display(fig)
    plt.close(fig)


_AUCTION_KINDS = {"auction_table", "bid_payoff_curve", "revenue_curve",
                  "common_value_bids"}


def _render_bipartite_market(figure_spec: dict) -> None:
    """Render a ``kind: bipartite_market`` figure spec (Lesson 4, c10).

    Reads the spec's two node columns + edge source and defers the answer
    (preferred-seller option edges / optimal assignment / market-clearing
    matching / constricted set) to ``plot_style.draw_bipartite_market`` — which
    COMPUTES them from ``valuations``/``prices``, so the drawn figure can't drift
    from the key. ``reveal: none`` hides everything DERIVED (option edges,
    matching, constricted highlight), showing only the question's explicit
    structure — the answer-leak guard, analog of ``mask_winner_price``.
    """
    from . import plot_style as ps

    left = figure_spec.get("left") or []
    right = figure_spec.get("right") or []
    if not left and not right:
        print("[engine] bipartite_market figure has no `left`/`right` nodes.")
        return
    # Equal-aspect figure; height scales with the taller column so rows breathe.
    rows = max(len(left), len(right), 1)
    fig, ax = plt.subplots(figsize=(5.6, max(2.6, 1.0 * rows + 1.4)))
    ps.draw_bipartite_market(
        ax,
        left=left,
        right=right,
        edges=figure_spec.get("edges"),
        derive=figure_spec.get("derive"),
        prices=figure_spec.get("prices"),
        valuations=figure_spec.get("valuations"),
        price_label=figure_spec.get("price_label", "price"),
        valuations_label=figure_spec.get("valuations_label", "valuations"),
        column_titles=figure_spec.get("column_titles", ("Sellers", "Buyers")),
        matching=figure_spec.get("matching"),
        constricted=figure_spec.get("constricted"),
        open_nodes=figure_spec.get("open_nodes"),
        edge_style=figure_spec.get("edge_style"),
        reveal=figure_spec.get("reveal", "edges"),
        note=figure_spec.get("note"),
    )
    plt.tight_layout()
    display(fig)
    plt.close(fig)


def _exchange_num(v):
    """Coerce a YAML value / fraction-string to a float for the bargaining
    helpers. ``"1/3"`` -> 0.333…, ``Fraction`` / int / float -> float. (The
    RENDER side keeps the original object so it labels exactly as authored.)"""
    if isinstance(v, str):
        return float(Fraction(v))
    return float(v)


def _resolve_graph_annotations(figure_spec: dict, G) -> dict:
    """Resolve the ``draw_graph`` annotation kwargs for a ``kind: graph`` spec.

    Highlights are forwarded verbatim (the pre-existing dispatch dropped them);
    the Lesson-5 network-exchange OUTCOME layer is DERIVED from the compute
    helpers rather than read as YAML literals — the same anti-drift discipline
    ``bipartite_market`` uses for its matching / constricted set, expressed with
    the identical ``"auto"`` idiom:

    - ``matching`` — a list of ``[u, v]`` edges (the outcome's matching). The
      bold **matched-edge** set defaults to exactly this matching, so the drawn
      bold edges can't disagree with the stated matching. ``matched_edges`` may
      still be given explicitly (or ``"auto"`` == the matching).
    - ``outside_options: auto`` — each matched node's endogenous best outside
      option, computed by ``best_outside_option`` from the rest of the network's
      values (never hand-typed, so the pendant labels match what balance uses).
    - ``node_values: auto`` — each matched pair's split, computed by
      ``nash_bargaining_split`` from that pair's outside options (the §12.5
      two-person primitive). There is no balance SOLVER — only a checker — so a
      general balanced outcome's ``node_values`` are supplied explicitly (they
      are the answer key), while ``outside_options``/``matched_edges`` still
      derive from them.

    A purely structural graph figure (Lessons 1-4) passes none of these, so the
    returned kwargs are all empty/off and ``draw_graph`` renders byte-identically
    to the pre-Lesson-5 dispatch.
    """
    from .plot_style import best_outside_option, nash_bargaining_split

    def _edges(key):
        return [tuple(e) for e in (figure_spec.get(key) or [])]

    highlight_nodes = list(figure_spec.get("highlight_nodes") or [])
    highlight_edges = _edges("highlight_edges")
    pendant_stub = bool(figure_spec.get("pendant_stub"))
    matching = _edges("matching")

    # Matched (bold-black) edges: explicit list, "auto" (== the matching), or —
    # the default — the matching itself when one is given.
    me = figure_spec.get("matched_edges")
    if me == "auto" or me is None:
        matched_edges = list(matching)
    else:
        matched_edges = [tuple(e) for e in me]

    nv = figure_spec.get("node_values")
    oo = figure_spec.get("outside_options")

    # node_values: explicit outcome dict (the answer key — no solver exists),
    # or derive each matched pair's Nash split from its two outside options.
    node_values = {}
    if isinstance(nv, dict):
        node_values = dict(nv)
    elif nv == "auto":
        if not isinstance(oo, dict):
            raise ValueError(
                "node_values: auto needs an explicit outside_options map to "
                "derive the Nash split from")
        for u, v in matching:
            split = nash_bargaining_split(_exchange_num(oo[u]), _exchange_num(oo[v]))
            if split is None:
                raise ValueError(
                    f"node_values: auto — no Nash deal for matched edge "
                    f"({u!r}, {v!r}); outside options sum to more than 1")
            node_values[u], node_values[v] = split

    # outside_options: explicit dict, or derive each matched node's endogenous
    # best outside option from the current values via the helper.
    outside_options = {}
    if isinstance(oo, dict):
        outside_options = dict(oo)
    elif oo == "auto":
        vals = {n: _exchange_num(x) for n, x in node_values.items()}
        matched_nodes = [n for e in matching for n in e]
        outside_options = {
            n: best_outside_option(n, G, matching, vals) for n in matched_nodes
        }

    return {
        "highlight_nodes": highlight_nodes,
        "highlight_edges": highlight_edges,
        "matched_edges": matched_edges,
        "node_values": node_values,
        "outside_options": outside_options,
        "pendant_stub": pendant_stub,
    }


# -----------------------------------------------------------------------------
# Figure-spec key validation — AN UNKNOWN KEY IS AN ERROR, NOT A SHRUG
# -----------------------------------------------------------------------------
#
# Until 0.8.0 the directed branch forwarded only `pos` and `labels`. An author
# who wrote `directed: true` with `highlight_nodes: [...]` got a figure with no
# highlight AND NO ERROR — the key simply evaporated. That is the same
# silent-failure archetype as the old update_worksheet.sh (staged the notebook,
# silently shipped no content) and the concept-cell placeholder (rendered
# "unavailable" instead of raising): THE THING YOU ASKED FOR DOESN'T HAPPEN, AND
# NOTHING TELLS YOU. It is the worst failure mode this project has, because it
# survives every green test and only surfaces as a wrong figure in front of
# students.
#
# So: every key a figure spec supplies must be one the SELECTED renderer actually
# consumes, or the render raises. The allowlists are per-renderer, not per-kind,
# because that is the resolution the bug lives at — `matching:` is meaningful to
# the undirected renderer and meaningless to the directed one, and an author who
# writes it on a directed graph must be told, not ignored.

_GRAPH_KEYS_COMMON = frozenset({
    "kind", "ref", "directed", "nodes", "edges", "layout", "layout_seed",
    "node_size", "show_labels", "highlight_nodes", "highlight_edges",
    "node_values", "node_groups", "group_colors", "group_legend", "figsize",
})
# The Lesson-5 network-exchange layer. Bargaining concepts: an "outside option"
# has no meaning on a directed web graph, so these are undirected-only and a
# directed spec that names one is a mistake worth raising on.
_GRAPH_KEYS_UNDIRECTED = frozenset({
    "matching", "matched_edges", "outside_options", "pendant_stub", "edge_styles",
})
_GRAPH_KEYS_DIRECTED = frozenset({
    "highlight_color", "node_values_below", "value_caption", "below_caption",
    "curved_reciprocal", "value_format",
})

# `directed` is accepted on both link-analysis kinds and is HONORED (it must be
# true — link analysis is defined on a digraph, and these renderers build one).
# It is allowlisted rather than rejected because writing it is natural and the
# renderer really does obey it; but `directed: false` is REJECTED below rather
# than silently overridden to true, which would be the very bug this guard exists
# to kill — the request quietly not happening.
_MATRIX_KEYS = frozenset({
    "kind", "ref", "directed", "nodes", "edges", "compute", "s", "values",
    "row_labels", "col_labels", "corner", "style", "highlight_cells",
    "highlight_rows", "title", "note", "row_title", "col_title", "value_format",
})
_ITERATION_TABLE_KEYS = frozenset({
    "kind", "ref", "directed", "nodes", "edges", "compute", "rule", "s", "steps",
    "highlight_rows", "highlight_cells", "title", "note", "corner", "style",
    "value_format",
})


def _require_directed(kind: str, figure_spec: dict) -> dict:
    """Link analysis is defined on a DIGRAPH. Honor `directed`, never override it."""
    if "directed" in figure_spec and not figure_spec["directed"]:
        raise ValueError(
            f"figure kind {kind!r}: 'directed: false' cannot be honored — HITS, "
            f"PageRank and the flow matrices are defined on a DIRECTED graph. "
            f"Rather than silently render a directed one anyway, this raises. "
            f"Drop the key (it defaults to directed) or set it true.")
    spec = dict(figure_spec)
    spec["directed"] = True
    return spec

_FIGURE_KEYS = {
    "image":             frozenset({"kind", "ref", "path", "alt"}),
    "payoff_matrix":     frozenset({"kind", "ref", "row_player", "col_player",
                                    "row_strategies", "col_strategies",
                                    "payoffs", "highlight"}),
    "auction_table":     frozenset({"kind", "ref", "bids", "values", "format",
                                    "labels", "note", "reserve", "compare",
                                    "compare_headers", "mask_winner_price"}),
    "bid_payoff_curve":  frozenset({"kind", "ref", "value", "highest_other",
                                    "n", "mode", "reserve"}),
    "revenue_curve":     frozenset({"kind", "ref", "curve", "seller_value",
                                    "n_max"}),
    "common_value_bids": frozenset({"kind", "ref", "common_value", "estimates"}),
    # `note` and `edge_style` were FORWARDED by _render_bipartite_market from the
    # day it shipped, but were never whitelisted — and _check_figure_keys runs
    # FIRST. So `note:` on any bipartite figure RAISED, and the renderer's entire
    # note branch was dead code, unreachable from YAML. Fixed in 0.9.0.
    # `price_label` / `valuations_label` are 0.9.0's annotation-column captions.
    "bipartite_market":  frozenset({"kind", "ref", "left", "right", "edges",
                                    "valuations", "prices", "matching",
                                    "constricted", "open_nodes", "derive",
                                    "reveal", "column_titles", "note",
                                    "edge_style", "price_label",
                                    "valuations_label"}),
    "matrix":            _MATRIX_KEYS,
    "iteration_table":   _ITERATION_TABLE_KEYS,
    # The bow-tie SCHEMATIC — regions and flows, not nodes and edges. It draws the
    # SHAPE of the web (IN / SCC / OUT and the three fringes) and takes no graph at
    # all: there is nothing to compute, which is exactly what distinguishes it from
    # the role-colored graph that sits beside it.
    "bowtie_schematic":  frozenset({"kind", "ref", "highlight", "show_fringes",
                                    "labels", "title", "figsize"}),
    # Two or more figures, stacked vertically, as ONE figure.
    "stack":             frozenset({"kind", "ref", "figures", "ratios", "width",
                                    "panel_height", "hspace"}),
}


def _check_figure_keys(kind: str, spec: dict, allowed: frozenset,
                       renderer: str) -> None:
    """Raise if the spec carries a key ``renderer`` will not consume."""
    unknown = sorted(set(spec) - allowed)
    if not unknown:
        return
    raise ValueError(
        f"figure kind {kind!r} ({renderer}): unknown key(s) "
        f"{', '.join(repr(k) for k in unknown)}. This renderer would SILENTLY "
        f"IGNORE them, so it raises instead. Known keys: "
        f"{', '.join(sorted(allowed))}."
    )


# -----------------------------------------------------------------------------
# Lesson-6 derived values — computed here, NEVER hardcoded in YAML
# -----------------------------------------------------------------------------
#
# The standing rule: compute derived values in the dispatch, never type a literal
# into a figure spec. Without it, ~20 Lesson-6 figures would each carry a
# hand-typed score that can drift from the answer key with nothing to catch it.
# So a spec asks for the CONCEPT and the dispatch runs the helper:
#
#     node_values: {compute: pagerank, rule: basic, step: 2}
#     node_groups: {compute: bowtie}
#
# An explicit map is still accepted (it is sometimes the answer key itself), but
# the computed form is the one to reach for.

def _fraction_or(v, default=None):
    return _exchange_num_fraction(v) if v is not None else default


def _exchange_num_fraction(v):
    return Fraction(v) if not isinstance(v, Fraction) else v


def _compute_node_values(block: dict, G):
    """Resolve a ``{compute: ...}`` node-value block to ``{node: Fraction}``."""
    from .link_analysis import hits_iterations, pagerank_iterations, pagerank_limit

    what = block.get("compute")
    step = int(block.get("step", 1))
    rule = block.get("rule", "basic")
    s = _fraction_or(block.get("s"), Fraction(4, 5))

    if what == "pagerank":
        if block.get("limit"):
            lim = pagerank_limit(G, rule=rule, s=s)
            if lim.limit is None:
                raise ValueError(
                    f"node_values: pagerank limit requested, but the {rule} rule "
                    f"does not converge on this graph ({lim.reason}). There is no "
                    f"limiting vector to draw — render the cycle instead "
                    f"(step: k), which is the point of the figure.")
            return lim.limit
        return pagerank_iterations(G, step, rule=rule, s=s)[step]

    if what in ("hits_authority", "hits_hub"):
        state = hits_iterations(G, step)[step]
        return state["authority" if what == "hits_authority" else "hub"]

    raise ValueError(
        f"node_values: unknown compute {what!r}. Known: 'pagerank', "
        f"'hits_authority', 'hits_hub'.")


def _compute_node_groups(block: dict, G):
    """Resolve a ``{compute: ...}`` node-group block to ``{node: group}``."""
    from .link_analysis import bowtie_partition, strongly_connected_components

    what = block.get("compute")
    if what == "bowtie":
        return bowtie_partition(G)
    if what == "scc":
        # strongly_connected_components() returns LARGEST FIRST, and group colors
        # are assigned in first-appearance order — so emit the giant component's
        # members before any singleton's. Otherwise a lone node that happens to
        # sort first (Fig 13.5's "Student") takes the accent color and the giant
        # SCC — the thing the figure is about — gets whatever is left.
        comps = strongly_connected_components(G)
        named = [(f"SCC {i + 1}" if len(c) > 1 else "singleton", c)
                 for i, c in enumerate(comps)]
        multi = [(g, c) for g, c in named if len(c) > 1]
        singles = [(g, c) for g, c in named if len(c) == 1]
        return {n: g for g, c in multi + singles for n in c}
    raise ValueError(
        f"node_groups: unknown compute {what!r}. Known: 'bowtie', 'scc'.")


def _resolve_directed_annotations(figure_spec: dict, G) -> dict:
    """The FULL ``draw_directed_graph`` kwarg set for a directed graph spec.

    Through 0.7.0 this did not exist: the directed branch forwarded ``pos`` and
    ``labels`` and dropped everything else. Highlights, node scores and grouping
    are all forwarded here, and score/group values may be COMPUTED rather than
    typed (see above).
    """
    def _edges(key):
        return [tuple(e) for e in (figure_spec.get(key) or [])]

    nv = figure_spec.get("node_values")
    nvb = figure_spec.get("node_values_below")
    ng = figure_spec.get("node_groups")

    def _values(block):
        if block is None:
            return {}
        if isinstance(block, dict) and "compute" in block:
            return _compute_node_values(block, G)
        return dict(block)

    node_groups = {}
    if isinstance(ng, dict) and "compute" in ng:
        node_groups = _compute_node_groups(ng, G)
    elif ng:
        node_groups = dict(ng)

    return {
        "highlight_nodes": list(figure_spec.get("highlight_nodes") or []),
        "highlight_edges": _edges("highlight_edges"),
        "highlight_color": figure_spec.get("highlight_color"),
        "node_values": _values(nv),
        "node_values_below": _values(nvb),
        "value_caption": figure_spec.get("value_caption"),
        "below_caption": figure_spec.get("below_caption"),
        "node_groups": node_groups,
        "group_colors": figure_spec.get("group_colors") or {},
        "group_legend": bool(figure_spec.get("group_legend", True)),
        "curved_reciprocal": bool(figure_spec.get("curved_reciprocal", True)),
        "show_labels": bool(figure_spec.get("show_labels", True)),
        "value_format": figure_spec.get("value_format", "auto"),
    }


def _build_graph(figure_spec: dict):
    """Build the networkx graph + layout shared by every graph-shaped figure."""
    directed = bool(figure_spec.get("directed"))

    # Per-node label map (id -> LaTeX/text) and explicit positions, when the
    # YAML supplies them. Both are optional; absent => raw id / computed layout.
    label_map = {}
    fixed_pos = {}
    node_ids = []
    for n in figure_spec.get("nodes") or []:
        if isinstance(n, dict):
            node_ids.append(n["id"])
            if "label" in n:
                label_map[n["id"]] = n["label"]
            if "pos" in n:
                fixed_pos[n["id"]] = tuple(n["pos"])
        else:
            node_ids.append(n)

    G = (nx.DiGraph() if directed else nx.Graph())
    G.add_nodes_from(node_ids)
    for e in figure_spec.get("edges") or []:
        if isinstance(e, list):
            if len(e) >= 3 and isinstance(e[2], dict):
                G.add_edge(e[0], e[1], **e[2])
            elif len(e) >= 2:
                G.add_edge(e[0], e[1])

    layout = figure_spec.get("layout", "spring")
    seed = figure_spec.get("layout_seed", 42)
    if fixed_pos and len(fixed_pos) == len(node_ids):
        pos = fixed_pos                      # fully-specified curated layout
    elif layout == "circular":
        pos = nx.circular_layout(G)
    elif layout == "kamada_kawai":
        pos = nx.kamada_kawai_layout(G)
    else:
        pos = nx.spring_layout(G, seed=seed)

    return G, pos, label_map


def _render_graph(figure_spec: dict) -> None:
    """Render a ``kind: graph`` figure spec (the default kind).

    Both branches now forward their renderer's FULL parameter set, and both
    validate their keys first: a key the selected renderer cannot consume RAISES
    rather than vanishing (see ``_check_figure_keys``).

    The undirected branch carries the Lesson-5 outcome layer (matched edges, node
    values, outside options, pendant stubs), with bargaining values derived from
    the compute helpers. The directed branch — new in 0.8.0 — carries node scores,
    node highlighting, categorical grouping and reciprocal-edge arcs, with scores
    and groups likewise derived rather than typed.
    """
    # A tall layout needs a tall canvas. Equal aspect fits the drawing inside the
    # axes box, so a two-column graph forced into the default 5x4 is compressed
    # until its node circles crowd and its labels have nowhere to go. Default
    # unchanged, so every pre-0.8.0 figure keeps its exact canvas.
    fig, ax = plt.subplots(figsize=tuple(figure_spec.get("figsize") or (5, 4)))
    _draw_graph_into(ax, figure_spec)
    plt.tight_layout()
    display(fig)
    plt.close(fig)


def _draw_graph_into(ax, figure_spec: dict) -> None:
    """Draw a ``kind: graph`` spec into an axes SOMEONE ELSE OWNS.

    Split out of ``_render_graph`` so the same spec can be drawn either as a figure of
    its own or as one panel of a ``kind: stack``. The split is the whole reason stacking
    is cheap: every ``plot_style.draw_*`` function already takes an ``ax``, and it was
    only the dispatch wrappers that insisted on making their own figure.

    Nothing here changed — same key checks, same builder, same draw calls in the same
    order — so a standalone graph renders byte-for-byte as it did before.
    """
    from .plot_style import draw_graph, draw_directed_graph, apply_ax_style

    directed = bool(figure_spec.get("directed"))
    if directed:
        _check_figure_keys(
            "graph", figure_spec, _GRAPH_KEYS_COMMON | _GRAPH_KEYS_DIRECTED,
            "directed: true -> draw_directed_graph")
    else:
        _check_figure_keys(
            "graph", figure_spec, _GRAPH_KEYS_COMMON | _GRAPH_KEYS_UNDIRECTED,
            "draw_graph")

    G, pos, label_map = _build_graph(figure_spec)
    if directed:
        draw_directed_graph(G, ax, pos=pos, labels=label_map or None,
                            node_size=figure_spec.get("node_size"),
                            **_resolve_directed_annotations(figure_spec, G))
    else:
        draw_graph(G, ax, pos=pos, **_resolve_graph_annotations(figure_spec, G))
    apply_ax_style(ax)


def _draw_bowtie_schematic_into(ax, figure_spec: dict) -> None:
    """Draw ``kind: bowtie_schematic`` into a given axes."""
    from .plot_style import draw_bowtie_schematic

    _check_figure_keys("bowtie_schematic", figure_spec,
                       _FIGURE_KEYS["bowtie_schematic"], "draw_bowtie_schematic")
    draw_bowtie_schematic(
        ax,
        highlight=figure_spec.get("highlight"),
        show_fringes=bool(figure_spec.get("show_fringes", True)),
        labels=bool(figure_spec.get("labels", True)),
        title=figure_spec.get("title"),
    )


def _render_bowtie_schematic(figure_spec: dict) -> None:
    fig, ax = plt.subplots(figsize=tuple(figure_spec.get("figsize") or (6.4, 4.6)))
    _draw_bowtie_schematic_into(ax, figure_spec)
    plt.tight_layout()
    display(fig)
    plt.close(fig)


#: The kinds that can render into an axes they do not own — i.e. the ones a `stack` may
#: contain. Every `plot_style.draw_*` takes an `ax`, so this list is short only because
#: the dispatch wrappers have not all been split yet; extending it is mechanical.
_STACKABLE = {
    "graph": _draw_graph_into,
    "bowtie_schematic": _draw_bowtie_schematic_into,
}


def _render_stack(figure_spec: dict) -> None:
    """Render ``kind: stack`` — two or more figures STACKED VERTICALLY as one figure.

    Needed in two independent places in Lesson 6, which is what makes it a capability
    rather than a one-off: 6.1's q_15 wants the bow-tie schematic above the 16-node
    university network, and 6.2's random-walk cell wants the 8-page graph above the
    walk-vs-PageRank table. Neither seam could express it — a section's `figure:` is one
    spec, and every renderer made its own figure.

    STACKED, not side-by-side. That is forced, not chosen: the university network is
    already cramped horizontally and the walk table is 8 columns wide, so side-by-side
    crushes both.

    A child kind that has not been split out to draw into a caller's axes RAISES, rather
    than rendering something subtly different and staying quiet about it — the standing
    rule for this dispatch.
    """
    _check_figure_keys("stack", figure_spec, _FIGURE_KEYS["stack"], "_render_stack")
    panels = figure_spec.get("figures") or []
    if len(panels) < 2:
        raise ValueError(
            f"figure kind 'stack' needs at least 2 entries under 'figures:', got "
            f"{len(panels)}. A stack of one is just that figure — use it directly.")

    ratios = figure_spec.get("ratios") or [1.0] * len(panels)
    if len(ratios) != len(panels):
        raise ValueError(
            f"figure kind 'stack': 'ratios' has {len(ratios)} entries but there are "
            f"{len(panels)} figures.")

    for p in panels:
        kind = p.get("kind", "graph")
        if kind not in _STACKABLE:
            raise ValueError(
                f"figure kind 'stack': cannot stack a {kind!r} panel — that renderer "
                f"still makes its own figure and cannot draw into a shared axes. "
                f"Stackable kinds: {', '.join(sorted(_STACKABLE))}. (Split its "
                f"`_render_{kind}` into a `_draw_{kind}_into(ax, spec)` + a wrapper, "
                f"as `graph` is, and add it to _STACKABLE.)")

    w = float(figure_spec.get("width", 6.4))
    hspace = float(figure_spec.get("hspace", 0.12))

    # 🧨 THE PANEL HEIGHTS COME FROM EACH PANEL'S OWN SHAPE, AND THEY MUST BE RIGHT
    # BEFORE ANYTHING IS DRAWN. This is the whole subtlety of stacking in this engine.
    #
    # Every figure here locks EQUAL ASPECT (a graph whose x and y scales differ is a
    # graph with the wrong angles), and `frame_signed_axes` chooses its data limits to
    # fit the AXES BOX IT IS GIVEN. So the box's shape is an INPUT to the drawing, not a
    # consequence of it: hand a wide graph a square box and it pads its own limits until
    # they are square, and the nodes end up floating in a band of white space that
    # `tight_layout` cannot reclaim — because the space is INSIDE the axes.
    #
    # The first cut of this drew the panels first and measured them afterwards. It could
    # not work: by the time there was anything to measure, the limits had already been
    # baked against the wrong box. Two correct drawings, a third of a page of nothing
    # between them.
    #
    # A child's own `figsize:` is exactly the statement of shape we need — it is what the
    # author already declares for that figure standing alone (web16 is 9.6 x 3.8: wide
    # and short, which is what a 16-node university network wants). So the stack reads
    # each child's aspect, sizes the figure to fit them all at the shared width, and
    # draws ONCE, into boxes that are already the right shape.
    _DEFAULT_ASPECT = {"graph": 4.0 / 5.0, "bowtie_schematic": 4.6 / 6.4}

    def panel_aspect(p):
        fs = p.get("figsize")
        if fs and float(fs[0]):
            return float(fs[1]) / float(fs[0])
        return _DEFAULT_ASPECT.get(p.get("kind", "graph"), 0.8)

    aspects = ([panel_aspect(p) for p in panels] if figure_spec.get("ratios") is None
               else [float(r) for r in ratios])
    total_h = w * sum(aspects) * (1.0 + hspace) + 0.25

    # 🧨 THE PANEL GAP IS SET THROUGH `tight_layout`, NOT THROUGH THE GRIDSPEC — AND THAT
    # IS NOT A STYLE PREFERENCE, IT IS THE WARNING FIX.
    #
    # Passing `gridspec_kw={"hspace": ...}` marks the GridSpec as having locally-modified
    # subplot params. matplotlib's `tight_layout` treats such an Axes as one it cannot
    # lay out (`get_subplotspec_list` returns None for it) and emits
    #
    #     UserWarning: This figure includes Axes that are not compatible with
    #     tight_layout, so results might be incorrect.
    #
    # which renders as a RED WARNING BOX ABOVE THE STUDENT'S FIGURE. The figure itself was
    # fine; the warning was not. And a warning a student is trained to ignore is worse
    # than no warning at all, in a course that is teaching them to read warnings.
    #
    # It has nothing to do with the equal-aspect axes (verified: a plain two-row subplots
    # call with equal-aspect children warns not at all, while the same call with
    # `gridspec_kw={"hspace": ...}` warns even with no aspect set). The gap is therefore
    # requested through `tight_layout`'s own `h_pad`, in font-size units, which leaves the
    # GridSpec unmodified and lets `tight_layout` do the job it is for.
    fig, axes = plt.subplots(len(panels), 1, figsize=(w, total_h),
                             height_ratios=aspects)
    for ax, p in zip(list(axes), panels):
        # The child's `figsize` has done its job (it set this panel's shape); drop it so
        # the renderer does not think it owns a figure.
        child = {k: v for k, v in p.items() if k != "figsize"}
        _STACKABLE[child.get("kind", "graph")](ax, child)

    fig.tight_layout(h_pad=hspace * 8.0)
    display(fig)
    plt.close(fig)


def _render_matrix(figure_spec: dict) -> None:
    """Render ``kind: matrix`` — the adjacency M, flow N, or scaled Ñ matrix.

    Entries may be given explicitly (``values:``) but are normally COMPUTED from
    the same graph the figure draws (``compute: adjacency | flow | scaled_flow``),
    so the matrix and the picture cannot disagree.
    """
    from .link_analysis import adjacency_matrix, flow_matrix, scaled_flow_matrix
    from .plot_style import draw_matrix, apply_ax_style

    _check_figure_keys("matrix", figure_spec, _MATRIX_KEYS, "draw_matrix")

    what = figure_spec.get("compute")
    values = figure_spec.get("values")
    row_labels = figure_spec.get("row_labels")
    col_labels = figure_spec.get("col_labels")

    if values is None:
        if not what:
            raise ValueError(
                "figure kind 'matrix' needs either explicit 'values' or a "
                "'compute' of 'adjacency', 'flow' or 'scaled_flow'.")
        G, _, label_map = _build_graph(_require_directed("matrix", figure_spec))
        order = list(G.nodes())
        s = _fraction_or(figure_spec.get("s"), Fraction(4, 5))
        if what == "adjacency":
            values = adjacency_matrix(G, order)
        elif what == "flow":
            values = flow_matrix(G, order)
        elif what == "scaled_flow":
            values = scaled_flow_matrix(G, order, s)
        else:
            raise ValueError(
                f"figure kind 'matrix': unknown compute {what!r}. Known: "
                f"'adjacency', 'flow', 'scaled_flow'.")
        labels = [label_map.get(n, n) for n in order]
        row_labels = row_labels or labels
        col_labels = col_labels or labels

    n = len(values)
    fig, ax = plt.subplots(figsize=(max(3.6, 1.0 + 0.62 * n),
                                    max(2.6, 1.2 + 0.46 * n)))
    draw_matrix(
        ax, values,
        row_labels=row_labels, col_labels=col_labels,
        corner=figure_spec.get("corner"),
        style=figure_spec.get("style", "matrix"),
        highlight_cells=figure_spec.get("highlight_cells"),
        highlight_rows=figure_spec.get("highlight_rows"),
        title=figure_spec.get("title"), note=figure_spec.get("note"),
        row_title=figure_spec.get("row_title"),
        col_title=figure_spec.get("col_title"),
        value_format=figure_spec.get("value_format", "auto"),
    )
    apply_ax_style(ax)
    plt.tight_layout()
    display(fig)
    plt.close(fig)


def _render_iteration_table(figure_spec: dict) -> None:
    """Render ``kind: iteration_table`` — the k-step score table.

    One row per update step, one column per node. The rows are COMPUTED by the
    helpers, so the table cannot drift from the figure or the key.
    """
    from .link_analysis import hits_iterations, pagerank_iterations
    from .plot_style import draw_matrix, apply_ax_style

    _check_figure_keys("iteration_table", figure_spec, _ITERATION_TABLE_KEYS,
                       "draw_matrix(style='table')")

    G, _, label_map = _build_graph(_require_directed("iteration_table", figure_spec))
    order = list(G.nodes())

    what = figure_spec.get("compute", "pagerank")
    steps = int(figure_spec.get("steps", 2))
    rule = figure_spec.get("rule", "basic")
    s = _fraction_or(figure_spec.get("s"), Fraction(4, 5))

    if what == "pagerank":
        seq = pagerank_iterations(G, steps, rule=rule, s=s)
        rows = [[r[n] for n in order] for r in seq]
    elif what in ("hits_authority", "hits_hub"):
        key = "authority" if what == "hits_authority" else "hub"
        seq = hits_iterations(G, steps)
        rows = [[st[key][n] for n in order] for st in seq]
    else:
        raise ValueError(
            f"figure kind 'iteration_table': unknown compute {what!r}. Known: "
            f"'pagerank', 'hits_authority', 'hits_hub'.")

    fig, ax = plt.subplots(figsize=(max(4.0, 0.95 + 0.72 * len(order)),
                                    max(2.2, 1.1 + 0.44 * len(rows))))
    draw_matrix(
        ax, rows,
        row_labels=[str(k) for k in range(len(rows))],
        col_labels=[label_map.get(n, n) for n in order],
        corner=figure_spec.get("corner", "step"),
        style=figure_spec.get("style", "table"),
        highlight_rows=figure_spec.get("highlight_rows"),
        highlight_cells=figure_spec.get("highlight_cells"),
        title=figure_spec.get("title"), note=figure_spec.get("note"),
        value_format=figure_spec.get("value_format", "auto"),
    )
    apply_ax_style(ax)
    plt.tight_layout()
    display(fig)
    plt.close(fig)


def _render_figure(ws, figure_spec: dict) -> None:
    """Render a YAML figure spec into the current Output context.

    Dispatches on ``kind`` (inline or via ``ref:``). Every kind validates its
    keys before rendering — an unrecognized key RAISES rather than being silently
    dropped (see ``_check_figure_keys``), and an unrecognized *kind* raises too.
    A figure that can't be drawn as specified must say so; the one thing it must
    never do is render something subtly different and stay quiet about it.
    """
    if "ref" in figure_spec:
        name = figure_spec["ref"]
        resolved_spec = ws.shared_figures.get(name)
        if not resolved_spec:
            raise ValueError(
                f"figure ref {name!r} resolves to nothing. Known shared figures: "
                f"{', '.join(sorted(ws.shared_figures)) or '(none)'}.")
        figure_spec = resolved_spec

    kind = figure_spec.get("kind", "graph")
    if kind == "image":
        _check_figure_keys("image", figure_spec, _FIGURE_KEYS["image"], "imshow")
        path = figure_spec.get("path")
        resolved = _resolve_figure_path(ws, path) if path else None
        if resolved is None:
            raise FileNotFoundError(
                f"figure kind 'image': file not found: {path!r}. (A missing "
                f"figure used to print a note and carry on, which shipped a "
                f"worksheet with a hole in it.)")
        img = plt.imread(str(resolved))
        # Size the axes to the image aspect; equal aspect + axis off so the
        # raster is shown undistorted and unframed (no autoscale surprises).
        h, w = img.shape[0], img.shape[1]
        fig, ax = plt.subplots(figsize=(5, 5 * h / w if w else 4))
        ax.imshow(img)
        ax.set_aspect("equal")
        ax.set_axis_off()
        plt.tight_layout()
        display(fig)
        plt.close(fig)
        return
    if kind == "payoff_matrix":
        _check_figure_keys(kind, figure_spec, _FIGURE_KEYS[kind],
                           "draw_payoff_matrix")
        _render_payoff_matrix(figure_spec)
        return
    if kind in _AUCTION_KINDS:
        _check_figure_keys(kind, figure_spec, _FIGURE_KEYS[kind],
                           f"draw_{kind}")
        _render_auction(figure_spec)
        return
    if kind == "bipartite_market":
        _check_figure_keys(kind, figure_spec, _FIGURE_KEYS[kind],
                           "draw_bipartite_market")
        _render_bipartite_market(figure_spec)
        return
    if kind == "matrix":
        _render_matrix(figure_spec)
        return
    if kind == "iteration_table":
        _render_iteration_table(figure_spec)
        return
    if kind == "bowtie_schematic":
        _render_bowtie_schematic(figure_spec)
        return
    if kind == "stack":
        _render_stack(figure_spec)
        return
    if kind != "graph":
        raise ValueError(
            f"unknown figure kind {kind!r}. Known: 'graph', 'image', "
            f"'payoff_matrix', 'bipartite_market', 'matrix', 'iteration_table', "
            f"'bowtie_schematic', 'stack', "
            f"{', '.join(repr(k) for k in sorted(_AUCTION_KINDS))}. "
            f"(This used to print a note and render nothing.)")

    _render_graph(figure_spec)
