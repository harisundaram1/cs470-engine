"""Problem-cell rendering.

Supports both single-select and multi-select MC via a unified
``OptionPicker`` widget that typesets ``$math$`` in option labels via
MathJax. Layout per design doc §6.1.
"""

import matplotlib.pyplot as plt
import networkx as nx
import ipywidgets as widgets
import markdown as _markdown
from IPython.display import display, Markdown, HTML

from .plot_style import HINT_SUMMARY_STYLE
from .scoring import credit_for_attempt, multi_select_credit, MAX_ATTEMPTS
from .widgets import OptionPicker, submit_button_with_gate


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
    display(Markdown(problem["prompt_markdown"]))

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
                    f"**Rationale:** {problem['rationale_markdown']}"
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
        f"**Rationale:** {problem['rationale_markdown']}"
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
    display(Markdown(problem["prompt_markdown"]))

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
        f"**Rationale:** {problem['rationale_markdown']}"
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


def _render_figure(ws, figure_spec: dict) -> None:
    """Render a YAML figure spec into the current Output context.

    Supports ``kind: graph`` (inline or via ``ref:``) and ``kind: image`` (a
    pre-rendered raster via ``path:``). Other kinds print a placeholder note.
    """
    if "ref" in figure_spec:
        name = figure_spec["ref"]
        figure_spec = ws.shared_figures.get(name)
        if not figure_spec:
            print(f"[engine] Missing shared figure: {name}")
            return

    kind = figure_spec.get("kind", "graph")
    if kind == "image":
        path = figure_spec.get("path")
        resolved = _resolve_figure_path(ws, path) if path else None
        if resolved is None:
            print(f"[engine] Figure image not found: {path!r}")
            return
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
        _render_payoff_matrix(figure_spec)
        return
    if kind in _AUCTION_KINDS:
        _render_auction(figure_spec)
        return
    if kind != "graph":
        print(f"[engine] Figure kind {kind!r} not yet implemented.")
        return

    from .plot_style import draw_graph, draw_directed_graph, apply_ax_style

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

    fig, ax = plt.subplots(figsize=(5, 4))
    if directed:
        # Directed causal-graph figures (e.g. the Shalizi-Thomas DAG): arrowheads
        # + LaTeX label map + curated positions, matching the module-drawn DAG.
        draw_directed_graph(G, ax, pos=pos, labels=label_map or None)
    else:
        draw_graph(G, ax, pos=pos)
    apply_ax_style(ax)
    plt.tight_layout()
    display(fig)
    plt.close(fig)
