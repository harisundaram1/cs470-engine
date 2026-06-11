"""The Worksheet Record cell — a Markdown-output table that persists in
the saved .ipynb (as cell output) so students can revisit their answers
after closing and reopening the notebook.

A single display_id is created at session start; every submit handler calls
`update_display` against it, replacing the rendered Markdown in place.
"""


def _display_id(pid: str) -> str:
    """Render `q_3` as `Q3` from the internal id (fallback)."""
    return pid.replace("q_", "Q") if pid.startswith("q_") else pid


def _q_display(ws, pid: str) -> str:
    """``Q<n>`` from the sequential DISPLAY NUMBER, else the id-derived label."""
    dn = getattr(ws, "display_number", None)
    if dn and pid in dn:
        return f"Q{dn[pid]}"
    return _display_id(pid)


def _problems_in_display_order(ws):
    """Problem sections ordered by display number (interleaved on-page order),
    so the record table reads top-to-bottom like the notebook. Falls back to
    YAML order when no display map exists."""
    probs = [s for s in ws.worksheet["sections"] if s.get("type") == "problem"]
    dn = getattr(ws, "display_number", None)
    if dn:
        probs.sort(key=lambda s: dn.get(s["id"], 1_000_000))
    return probs


def initial_markdown(ws) -> str:
    return (
        f"## Your worksheet record · {ws.id} · session {ws.session_id[:8]}\n\n"
        "_No answers yet._"
    )


def updated_markdown(ws) -> str:
    # The "Id" column (internal q_N) appears only when the worksheet is
    # reordered, so 1.x's record table is byte-identical to before.
    show_id = getattr(ws, "display_reordered", False)
    if show_id:
        lines = [
            f"## Your worksheet record · {ws.id} · session {ws.session_id[:8]}",
            "",
            "| Q | Id | Difficulty | Answered | Result | Credit |",
            "|---|----|-----------|----------|--------|--------|",
        ]
    else:
        lines = [
            f"## Your worksheet record · {ws.id} · session {ws.session_id[:8]}",
            "",
            "| Q | Difficulty | Answered | Result | Credit |",
            "|---|------------|----------|--------|--------|",
        ]
    total_credit = 0.0
    total_possible = 0
    for section in _problems_in_display_order(ws):
        pid = section["id"]
        difficulty = section["difficulty"]
        total_possible += 1
        entry = ws.scores.get(pid)
        if entry is None:
            answered = "no"
            result = "—"
            credit_str = "—"
        else:
            attempt = entry["attempt"]
            credit = entry["credit"]
            total_credit += credit
            if entry["correct"]:
                tries = "try" if attempt == 1 else "tries"
                result = f"✓ ({attempt} {tries})"
            else:
                result = "✗"
            answered = "yes"
            credit_str = f"{credit:.2f}"
        id_cell = f" {pid} |" if show_id else ""
        lines.append(
            f"| {_q_display(ws, pid)} |{id_cell} {difficulty} | {answered} "
            f"| {result} | {credit_str} |"
        )

    if total_possible == 0:
        return "\n".join(lines)

    frac = total_credit / total_possible
    threshold = ws.pass_threshold
    above = "✓ above" if frac >= threshold else "✗ below"
    threshold_pct = int(threshold * 100)
    lines += [
        "",
        f"**Running total:** {total_credit:.2f} / {total_possible:.2f} "
        f"({frac * 100:.1f}%) · {above} {threshold_pct}% threshold",
    ]
    return "\n".join(lines)
