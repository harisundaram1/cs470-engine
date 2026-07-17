# Semantic container-render gate (G1)

Runs the L8/L9 log-log figure invariants **in the environment** (not a pixel diff
across environments — that design is refuted). L9's are the first log-log figures
ever, and L8 ships two figure kinds (`distribution`, `xy_curve`) that have never
rendered in the container.

## Files
- `build_gate.py` — regenerates the self-contained `gate.ipynb`.
- `gate.ipynb` — the committed gate (self-contained: needs only the installed
  `cs470_engine`, so it runs unchanged in the image).
- `run_gate.py` — executes `gate.ipynb` through a real ZMQ kernel.

## ⚠ Precondition the spec omitted (load-bearing)
The FIRST cell calls `apply_default_style()`. Retina fires **only** after that and
**only** under a real kernel (`nbconvert --execute` → `ZMQInteractiveShell`).
Without it the gate runs in the `{'png'}` construct==draw regime where an F7
dpi-freeze is **invisible** and the gate goes green testing the wrong thing (F2).
The gate asserts `figure_formats == {'retina'}` so this cannot silently regress.

Also refuted (code wins over spec): `ax.get_ylim()[0] > 0` is a **tautology** on a
matplotlib log axis (a 0 floor is silently clamped to a small positive value), so
it is not a red-case-able anti-clamp gate. The honest guard is `draw_distribution`
**raising** on a log axis (its bars/stems are anchored at y=0).

## What it checks
- **Tier A** (value-level): retina fired; `get_?scale()=='log'`; drawn artist
  values == the computed C1 curve; measured log-log slope == −α (1e-9); F2 draws
  with no k≥171 overflow; F4 is the transpose of F3; `draw_distribution` raises on
  log. Prints the container's `matplotlib.__version__` (gate rule 7 — skew visible).
- **Tier B** (ink geometry, extends B7): every in-view text artist's extent/dpi is
  dpi-invariant across `(100, 200, 150)`, RELATIVE tolerance 20% (mathtext hinting
  is ~7%, an F7 freeze ~69%). In-view ticks only (LogLocator emits off-view labels).
- **Red cases**: `draw_distribution` raises on log; the 0.10.1 frozen-dpi ellipse is
  caught by the same relative ratio detector.

## Local (pre-image, CI)
```
python3 tests/container_gate/run_gate.py
```
Real ZMQ kernel here too, so the precondition is exercised. Covered by
`tests/test_container_gate.py`.

## In the container (after the v0.11.1 image is built — a LATER pass)
The entrypoint override is mandatory or the image launches JupyterLab and "passes":
```
docker run --rm --platform linux/amd64 -v "$PWD":/probe \
  --entrypoint jupyter cs470-workspace:<TAG> \
  nbconvert --to notebook --execute --output /probe/out.ipynb /probe/gate.ipynb
```
Compare the printed `matplotlib` version against local — the gate shares matplotlib
with what it draws (its one blind spot, gate rule 7), so make the skew visible.

## What it cannot see
Colour, whether it is the *right* figure, overlap. The eyeball pass stays and walks
a **written** property list (F5).
