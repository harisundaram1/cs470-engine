#!/usr/bin/env python3
"""Worksheet-agnostic render harness — the byte-identical regression gate.

Renders EVERY figure of one or more worksheet YAMLs — BOTH seams a figure can
reach a student through — then writes a ``manifest.txt`` of ``sha256  render-id``
lines:

* **problem figures**, through the engine's real YAML dispatch
  (``problems._render_figure``, with ``display`` swapped for a PNG save);
* **concept-cell figures**, through each cell's ``render_function`` in
  ``worksheets/concepts/<id>.py``, driven by REAL ipywidgets built by the
  engine's own ``concept._make_control``.

Both seams matter and the second is the one that is easy to forget: concept cells
bypass the dispatch entirely and call ``draw_graph`` / ``draw_payoff_matrix``
directly, so a dispatch-only harness would pass while every concept figure in the
corpus silently moved.

The point is proving an engine change is ADDITIVE: capture a manifest on the old
engine, capture one on the new, diff. Identical hashes == the deployed corpus
renders byte-for-byte as it did before, which is what lets a new engine tag go
out without re-eyeballing every live figure.

    python3 tests/render_regression.py OUTDIR WS.yaml [WS2.yaml ...]
    diff before/manifest.txt after/manifest.txt && echo IDENTICAL

A figure is rendered once per USE, not once per definition: a shared figure used
by three problems is rendered three times under three render-ids, because a
``ref`` is resolved per-use and a dispatch bug could make one use differ from
another. Concept cells are rendered at their default state AND under a
one-at-a-time sweep of every control value (a full cartesian product would
explode; one-at-a-time still visits every value of every control, which is what
exercises each render branch). The harness pins only what would churn the bytes
without a pixel moving — Agg, ``svg.hashsalt``, no timestamp metadata.

🧨 **It does NOT pin ``PYTHONHASHSEED``, and it must never start.** A pinned seed
does not prove determinism, it MASKS non-determinism: it hid a set-iteration bug
in ``bowtie_partition`` whose figure came out a different COLOR on every kernel
start. Every green run was green *because* the harness was pinned. Run unpinned
(``PYTHONHASHSEED=random``), twice, and diff the two manifests against each other
before you diff against the baseline.

🧨 **``PYTHONPATH`` will NOT point this at an old engine.** The engine is installed
``pip install -e .``, and setuptools' editable finder sits on ``sys.meta_path``,
which outranks every path-based lookup — so a baseline run silently imports the
WORKING TREE and reports byte-identical against itself. To render a baseline: drop
the ``__editable__`` finder from ``sys.meta_path``, insert the old checkout at
``sys.path[0]``, and ASSERT ``cs470_engine.plot_style.__file__`` before rendering
a single figure.

And a byte-identity gate cannot see a render bug in a figure the corpus does not
yet contain. It proves a change is ADDITIVE. It does not replace looking.
"""
import hashlib
import io
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt        # noqa: E402
import yaml                            # noqa: E402

import cs470_engine.concept as concept                # noqa: E402
import cs470_engine.problems as problems              # noqa: E402
from cs470_engine.plot_style import FIGURE_STYLE, apply_default_style  # noqa: E402
from cs470_engine.worksheet import Worksheet          # noqa: E402

# Metadata carries a timestamp + a random-salted id by default; both would churn
# the bytes on every run and make "byte-identical" unprovable.
matplotlib.rcParams["svg.hashsalt"] = "cs470"
SAVE = dict(format="png", dpi=100, bbox_inches="tight", metadata={"Software": None})


def _hash_fig(fig, outdir, name, rows):
    buf = io.BytesIO()
    fig.savefig(buf, **SAVE)
    plt.close(fig)
    png = buf.getvalue()
    (outdir / f"{name}.png").write_bytes(png)
    rows.append((hashlib.sha256(png).hexdigest(), name))


def _control_states(ctl):
    """Every value of one control — the one-at-a-time sweep's axis."""
    kind = ctl.get("kind")
    if kind == "dropdown":
        return list(ctl.get("options") or [])
    if kind == "checkbox":
        return [False, True]
    if kind == "button":
        return [0, 1, 2, 3]              # click counts
    if kind == "slider":
        lo, hi, step = ctl["min"], ctl["max"], ctl.get("step", 1)
        vals, v, guard = [], lo, 0
        while v <= hi + 1e-9 and guard < 64:
            vals.append(round(v, 6) if isinstance(step, float) else v)
            v += step
            guard += 1
        return vals
    return []


def render_problem_figures(ws, outdir, rows):
    """Seam 1 — problem figures, through the real YAML dispatch."""
    stem = ws.worksheet["id"]
    captured = []
    problems.display = lambda fig: captured.append(fig)   # swap the notebook seam

    for sec in ws.worksheet.get("sections") or []:
        spec = sec.get("figure")
        if not spec:
            continue
        captured.clear()
        problems._render_figure(ws, spec)
        if not captured:
            rows.append(("NO-FIGURE", f"{stem}:{sec.get('id', '?')}"))
            continue
        _hash_fig(captured[0], outdir, f"{stem}__{sec.get('id', '?')}", rows)


def render_concept_figures(ws, outdir, rows):
    """Seam 2 — concept cells, through their render_function + real widgets.

    Rendered at the default control state, then once per value of each control
    with the others left at default. Concept cells never touch the dispatch, so
    this is the ONLY path that covers their draw_graph calls.
    """
    stem = ws.worksheet["id"]
    if ws.concepts_module_path is None or not ws.concepts_module_path.exists():
        return
    module = concept._load_lesson_module(ws.concepts_module_path)

    for sec in ws.worksheet.get("sections") or []:
        if sec.get("type") != "concept":
            continue
        fn = getattr(module, sec.get("render_function", ""), None)
        if fn is None:
            rows.append(("NO-RENDER-FN", f"{stem}:{sec.get('id', '?')}"))
            continue

        decls = sec.get("controls") or []
        controls = {c["name"]: concept._make_control(c) for c in decls}
        controls = {k: v for k, v in controls.items() if v is not None}

        # (state-label, {name: value}) — default, then one control at a time.
        states = [("default", {})]
        for c in decls:
            if c["name"] not in controls:
                continue
            for val in _control_states(c):
                states.append((f"{c['name']}={val}", {c["name"]: val}))

        # Every control kind exposes `.value` uniformly — a ClickCounterButton
        # wraps its click count behind the same attribute, which is exactly why
        # concept render functions can read controls without knowing the kind.
        defaults = {n: o.value for n, o in controls.items()}
        for label, overrides in states:
            for n, o in controls.items():
                o.value = overrides.get(n, defaults[n])
            fig, ax = plt.subplots(figsize=FIGURE_STYLE["concept_figsize"])
            try:
                fn(controls, ax)
            except Exception as exc:                      # a render that raises
                plt.close(fig)                            # is itself a regression
                rows.append((f"RAISED:{type(exc).__name__}",
                             f"{stem}:{sec['id']}[{label}]"))
                continue
            safe = label.replace("/", "_").replace(" ", "_")
            _hash_fig(fig, outdir, f"{stem}__{sec['id']}__{safe}", rows)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    outdir = pathlib.Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    apply_default_style()

    rows = []
    for y in sys.argv[2:]:
        ws = Worksheet.load(pathlib.Path(y).name)
        render_problem_figures(ws, outdir, rows)
        render_concept_figures(ws, outdir, rows)

    manifest = "\n".join(f"{h}  {name}" for h, name in rows) + "\n"
    (outdir / "manifest.txt").write_text(manifest)
    bad = [n for h, n in rows if not len(h) == 64]
    print(f"{len(rows)} figures -> {outdir}/manifest.txt")
    if bad:
        print(f"WARNING — {len(bad)} did not render: {bad[:5]}")


if __name__ == "__main__":
    main()
