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
    """Render `q_3` as `Q3` for student-facing display."""
    return pid.replace("q_", "Q") if pid.startswith("q_") else pid


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

    display(Markdown(f"**{_display_id(pid)} · {diff}**{hint_glyph}{mode_hint}"))
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
    picker = OptionPicker(
        [(opt["id"], opt["text"]) for opt in options],
        mode=mode,
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
        f"**[ANSWER KEY] {_display_id(pid)} · {diff}**{mode_hint}"
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
    if kind != "graph":
        print(f"[engine] Figure kind {kind!r} not yet implemented.")
        return

    from .plot_style import draw_graph, apply_ax_style

    G = nx.Graph()
    for n in figure_spec.get("nodes") or []:
        if isinstance(n, dict):
            G.add_node(n["id"])
        else:
            G.add_node(n)
    for e in figure_spec.get("edges") or []:
        if isinstance(e, list):
            if len(e) >= 3 and isinstance(e[2], dict):
                G.add_edge(e[0], e[1], **e[2])
            elif len(e) >= 2:
                G.add_edge(e[0], e[1])

    layout = figure_spec.get("layout", "spring")
    seed = figure_spec.get("layout_seed", 42)
    if layout == "circular":
        pos = nx.circular_layout(G)
    elif layout == "kamada_kawai":
        pos = nx.kamada_kawai_layout(G)
    else:
        pos = nx.spring_layout(G, seed=seed)

    fig, ax = plt.subplots(figsize=(5, 4))
    draw_graph(G, ax, pos=pos)
    apply_ax_style(ax)
    plt.tight_layout()
    display(fig)
    plt.close(fig)
