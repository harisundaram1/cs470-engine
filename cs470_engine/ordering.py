"""Interleaved display order — the single source of truth.

A worksheet YAML lists concepts then problems; the *display* order interleaves
each concept immediately before the problems it anchors (its
``follow_up_problem_ids``). Two consumers must agree on that order exactly:

  - ``scripts/build.py`` emits one notebook cell per section in this order.
  - the engine derives each problem's sequential **display number** from it
    (so the visible "QN" label matches on-page position, not the internal id).

Both import ``interleave_sections`` from here, so they can never drift. The
internal ``q_N`` ids are untouched — this only governs *order*, and the display
number is computed from it.
"""


def problem_sort_key(pid: str):
    """Sort ``q_<n>`` numerically (q_2 before q_10), other ids lexically."""
    if pid.startswith("q_") and pid[2:].isdigit():
        return (0, int(pid[2:]))
    return (1, pid)


def interleave_sections(sections: list[dict]) -> list[dict]:
    """Return ``sections`` in interleaved display order.

    Order: every non-problem section (intro, …) keeps its leading position,
    then for each concept (in source order) the concept cell followed by its
    not-yet-emitted follow-up problems (numeric q-id order). Any problem listed
    by no concept is appended after the last concept, in q-id order, so nothing
    is dropped. A problem named by several concepts is placed under the first
    that lists it.

    **No-op when the source is already interleaved** — i.e. when any problem
    already appears before the last concept. Worksheets authored in the
    interleaved style (1.1/1.2/1.3) are returned unchanged, so display order ==
    source order == id order there (no visible relabeling).
    """
    types = [s.get("type") for s in sections]
    if "concept" in types and "problem" in types:
        last_concept = max(i for i, t in enumerate(types) if t == "concept")
        first_problem = min(i for i, t in enumerate(types) if t == "problem")
        if first_problem < last_concept:
            return list(sections)  # already interleaved — leave untouched

    problems = {s["id"]: s for s in sections if s.get("type") == "problem"}
    concepts = [s for s in sections if s.get("type") == "concept"]
    leading = [s for s in sections
               if s.get("type") not in ("problem", "concept")]

    out = list(leading)
    emitted: set[str] = set()
    for concept in concepts:
        out.append(concept)
        follow = [pid for pid in concept.get("follow_up_problem_ids", [])
                  if pid in problems and pid not in emitted]
        for pid in sorted(follow, key=problem_sort_key):
            out.append(problems[pid])
            emitted.add(pid)

    # Any problem no concept claimed — keep it (trailing), in q-id order.
    leftover = [pid for pid in problems if pid not in emitted]
    for pid in sorted(leftover, key=problem_sort_key):
        out.append(problems[pid])
        emitted.add(pid)

    return out


def display_numbers(sections: list[dict]) -> dict:
    """Map each problem id -> its 1-based display number (interleaved order).

    The engine calls this at load so a problem's visible "QN" reflects its
    on-page position. Built from ``interleave_sections``, so the numbering
    matches the order ``build.py`` actually emits cells in.
    """
    ordered = interleave_sections(sections)
    n = 0
    out: dict[str, int] = {}
    for s in ordered:
        if s.get("type") == "problem":
            n += 1
            out[s["id"]] = n
    return out
