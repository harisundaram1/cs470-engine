"""The Worksheet Record cell — a Markdown-output table that persists in
the saved .ipynb (as cell output) so students can revisit their answers
after closing and reopening the notebook.

A single display_id is created at session start; every submit handler calls
`update_display` against it, replacing the rendered Markdown in place.
"""


def _display_id(pid: str) -> str:
    """Render `q_3` as `Q3` for student-facing display."""
    return pid.replace("q_", "Q") if pid.startswith("q_") else pid


def initial_markdown(ws) -> str:
    return (
        f"## Your worksheet record · {ws.id} · session {ws.session_id[:8]}\n\n"
        "_No answers yet._"
    )


def updated_markdown(ws) -> str:
    lines = [
        f"## Your worksheet record · {ws.id} · session {ws.session_id[:8]}",
        "",
        "| Q | Difficulty | Answered | Result | Credit |",
        "|---|------------|----------|--------|--------|",
    ]
    total_credit = 0.0
    total_possible = 0
    for section in ws.worksheet["sections"]:
        if section["type"] != "problem":
            continue
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
        lines.append(
            f"| {_display_id(pid)} | {difficulty} | {answered} | {result} | {credit_str} |"
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
