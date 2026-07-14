# Changelog — `cs470-engine`

What shipped in the engine, reverse-chronological.

This file starts at **0.8.0**. Versions 0.2 – 0.7.0 predate it and are not
reconstructed here: their record is the annotated tags (`git tag -l`, `v0.2` →
`v0.7.0`, one per release) and, in far more detail, the **`CHANGELOG.md` of the
`CS_470_Redesign` repo** — which is the fuller history, because the engine has
always been changed in service of a worksheet and the *why* lives next to the
worksheet. Read that one first. This file exists so an engine-only checkout is
not silent about what it is.

**The engine is consumed by two repos** (`CS_470_Redesign` for authoring, the
`pl-cs498hs` workspace image for deployment). A release is only real once it is
tagged AND baked into the image — see the redesign repo's `CLAUDE.md` §3.

---

## [0.10.3] — 2026-07-14 — IN / OUT, placed against the space they actually occupy

### Fixed — the bow-tie's lobe labels were centred against a row they were not sitting in

**This placement has now been wrong TWICE, in opposite directions, and a human found both.**
0.10.2 moved `IN`/`OUT` off the lobe's area centroid and onto the midpoint of the lobe's
**whole x-extent** (`-span/2`). That is the middle of the row at `y = 0` — but the labels were
**lifted to `y = 0.45*half_h`** to clear the flow arrow, and the lobe is a TRIANGLE WITH ITS
APEX AT THE ORIGIN, so it **tapers**: at the label's own height the lobe only reaches
`x = -0.45*span`. The label was therefore centred against a part of the shape it was not in,
came out jammed against the taper, and **its box hung off the edge of its own lobe.**

    placement                        IN's x     box inside the lobe?
    -2*span/3   area centroid         -2.67     yes — legal, just off-centre
    -span/2     whole x-extent (0.10.2) -2.00   NO  — box left the lobe   <- shipped
    -span*0.80  outboard of the arrow  -3.20    yes                       <- 0.10.3

**Now:** each label sits **outboard of its flow arrow, on the arrow's own axis (`y = 0`)** —
centred in the lobe span the arrow leaves free, the midpoint of `[span, flow_tail]`. The
figure reads as one horizontal line, which is the bow-tie's actual claim:
**IN → (arrow) → SCC → (arrow) → OUT.** The lift existed only to dodge the arrow; the label is
now *beside* the arrow, so the lift had no remaining job.

`flow_tail` is now **one constant with two consumers** — the arrow is drawn from it and the
label is placed from it — so the label cannot drift onto the arrow if the arrow ever moves (F8).

### Added — `tests/test_schematic_geometry.py` (B8), with a red case

Asserts each lobe label's box is **fully inside the lobe it names**, **clear of that lobe's
flow arrow**, and **mirror-symmetric** with its opposite. The red case replays both historical
placements: `-span/2` **reds** (its box leaves the lobe).

**And it says what it cannot see:** the *centroid* placement passes every check in the file —
it was legal and merely ugly. **Whether a label is well placed inside a legal region is an
eyeball call, and this gate does not make it.** A green B8 is not permission to skip looking.

### Render regression (0.10.2 → 0.10.3, 860 figures, `PYTHONHASHSEED=random`)

9 moved — **all of them 6.1's bow-tie schematics** (`q_8`, `q_9`, `q_12`, and
`concept_bowtie_explorer` in all six states). **L1–L5: 0 of 851 moved. 6.2: 0 moved.**

## [0.10.2] — 2026-07-14 — the blob was never in points: a frozen dpi, found only in the container

### Fixed — `_points_ellipse` froze its dpi at construction (LESSONS.md F7, instance six)

**The bug shipped, and every local render said it had not.** In the live PL workspace the
bow-tie schematic's `DISCONNECTED` and `TENDRIL` labels overflowed their blobs by ~1.6x.
Locally — dispatcher, `build.py`, `edge_audit`, `label_audit`, a bare `savefig` — they were
enclosed at 0.80 fill. Both measurements were correct. They were measuring different worlds.

`_points_ellipse` sized its ellipse with `Affine2D().scale(fig.dpi / 72)`, which **freezes
the dpi at construction**. Text does not freeze: matplotlib scales a fontsize by the
RENDERER's dpi at DRAW time. So the ellipse was never points-sized at all — it was
**pixels, frozen at construction, wearing a points costume**:

    effective ellipse size = w_pts * (construct_dpi / draw_dpi)

and it only looked right when those two happened to be equal.

**Why the container is different, and why nothing local could ever have caught it.** This
module's own `apply_default_style()` runs

    ipy.run_line_magic("config", "InlineBackend.figure_format = 'retina'")

**guarded by `if get_ipython() is not None`.** In JupyterLab that fires: retina makes
`print_figure` draw at **2x** `fig.dpi`, so the ellipse rendered at half its intended point
size while the label stayed put. In every local context `get_ipython()` is `None`, the magic
silently no-ops, construct dpi == draw dpi == 100, and the frozen scale is *accidentally
right*. **The environment was an unenumerated axis.** Measured, same figure, same engine:

    context     draw dpi   font          DRAWN text   ELLIPSE   ratio
    local          100     Helvetica       72.2pt      90.3pt   0.80  enclosed
    container      200     DejaVu Sans     78.9pt      49.7pt   1.59  OVERFLOW

The fonts differ too (the container has no Helvetica) — but that is a red herring: the blob
is sized from the extent measured in whatever face is live, so the font cancels out of the
ratio exactly. **Only dpi drove it.**

**Fixed at the cause:** the scale is now `fig.dpi_scale_trans`, matplotlib's own inches->pixels
transform, which `Figure._set_dpi` mutates **in place** on every dpi change and therefore
re-evaluates at draw time. Not a fudge factor — a fudge factor fixes 200 and breaks 150.

### Fixed — IN / OUT sat at the lobe's AREA CENTROID, which is not its visual centre

A triangle's centroid is a third of the way from its base, so on two mirrored lobes it pulled
`IN` left and `OUT` right by `span/6` each, in opposite directions — the signature of a
centroid, and visible on the live render as "not centred" in either lobe. A correct rule
computing the wrong quantity: a label is centred against the shape's **extent**, which is what
the eye bisects, not against its **mass**. Now at the midpoint of the lobe's x-extent.

### Added — `tests/test_dpi_invariance.py` (B7), with a red case

Sweeps the dpis a figure actually ships at (100 = inline `png`, 200 = `retina`, plus 150 so a
2x-only fudge fails), asserts `_points_ellipse` is point-invariant and every fringe label is
enclosed, and asserts the text/blob ratio is **font-independent** — so a local pass means
something about the container. The red case rebuilds 0.10.1's frozen transform and proves the
gate reds on it (100pt -> 50pt at 200dpi).

### 🧨 The render-regression gate was structurally blind to this, and is now labelled

`render_regression.py` saves at `dpi=100` — **the construction dpi** — so every frozen-basis
bug cancels inside it. Had 0.10.2 fixed *only* the dpi, that gate would have reported **860/860
byte-identical** and called the change additive. **Byte-identity answers "did the corpus move",
not "is the unit basis sound".** Noted next to the constant; the dpi axis belongs to B7.

### Render regression (v0.10.1 -> 0.10.2, 860 figures, `PYTHONHASHSEED=random`)

**9 moved, all of them 6.1's bow-tie schematics** — `q_8`, `q_9`, `q_12`, and
`concept_bowtie_explorer` in all six states. **L1-L5: 0 of 851 moved. 6.2: 0 moved.** The nine
moved because of the IN/OUT reposition (the dpi fix is a no-op at the harness's dpi, which is
the whole point above). Deployed L1-L5 stay on the v0.7.0 image and are untouched either way.

## [0.10.1] — 2026-07-13 — the schematic's ink-vs-data pass, and a warning that must not ship

Polish on 0.10.0's `bowtie_schematic` / `stack`. **NOT tagged, NOT deployed.**

### Fixed — a UserWarning was rendering ABOVE the student's figure

- **`kind: stack` emitted `UserWarning: This figure includes Axes that are not compatible
  with tight_layout`.** The figure was fine; the warning was not — it draws as a red box
  above the figure, and a course that trains students to ignore warnings has taught them
  the wrong habit.
- **It had nothing to do with the equal-aspect axes.** The cause is
  `gridspec_kw={"hspace": ...}`: that marks the GridSpec as having locally-modified
  subplot params, and matplotlib's `get_subplotspec_list` then returns `None` for those
  Axes, which is exactly the condition the warning reports. Verified both ways — a plain
  two-row `subplots` with equal-aspect children does not warn, and the same call *with*
  `gridspec_kw` warns even with no aspect set. The panel gap is now requested through
  `tight_layout(h_pad=...)`, which leaves the GridSpec alone. **Scoped fix, no
  warning-suppression anywhere.**

### Fixed — the fringe blob was DATA-sized and its label was INK-sized

- **🧨 THE FOURTH INK-VS-DATA BASIS ERROR IN THIS ENGINE**, after `pendant_stub` (pre-0.7.0),
  the collision search's binding dimension (0.8.0) and the reciprocal arc's bow (0.10.0).
  A fringe blob was an `Ellipse` with radii in DATA units holding a label in POINTS. A
  label's width in data units is (its point width) / (points per data unit), which moves
  with the panel — so the two bases never tracked. Measured across the three panels this
  schematic actually ships in, "DISCONNECTED" spanned **2.48 / 2.11 / 1.88 data units**
  against a fixed **1.90**-unit oval: it **overflowed in two contexts and just fitted in the
  third**.
- **The blob is now sized in POINTS, from its own text**, positioned at a data coordinate
  (`_points_ellipse`), with the width solved from the ellipse-contains-a-box condition so
  the label is enclosed **by construction, not by taste**. The text extent is read with
  `_text_extent_pts`, which depends only on font + string + size and is therefore invariant
  under panel size, figure size **and `tight_layout`** — which matters, because a text's box
  in DATA units is **not** invariant under `tight_layout` (measured: 2.506 → 2.086 data
  units, a 17% shrink).
  ⚠️ **That refutes `_data_bbox`'s docstring**, which claims a data-space box survives the
  rescale. It does for an artist defined in data units; it does **not** for text. Flagged,
  not changed — `_declash_annot_column` is gated structurally and does not depend on it.
- **The brief's diagnosis was inverted, and the measurement is why we know.** The font size
  was *already* points-based and identical (11pt / 9pt) in every context; making it "more
  points-based" would have fixed nothing. The offender was the container.

### Fixed — three text defects in `draw_bowtie_schematic`

- **`IN` / `OUT` are centred.** They sat outboard of their flow arrows (mirror-symmetric, but
  reading as off-centre in both lobes). They now sit at the lobe's **centroid** in x
  (a third of the way from the base), lifted clear of the arrow along y=0. One rule, both
  lobes.
- **Labels are drawn in INK-BLACK, not in their role's colour. LEGIBILITY BEATS SEMANTIC
  MUTING.** `DISCONNECTED`'s role colour is the muted-grey token, so it was pale grey text on
  a pale grey blob; `IN` was a washed-out sky blue. The roles are still colour-coded — by the
  region's **fill and outline**, which is what has to match the role-coloured graph. The label
  was encoding something the fill already said.
- A **dimmed** label (when another role is highlighted) now sits at alpha 0.78, not 0.45. The
  focusing is done by the region (whose fill drops to 0.10); the label only steps back.

### Changed — the schematic is the same SIZE in both places it appears

Its labels are ink and are identical at any panel size, but its **lobes are data** and scale
with the panel. So 6.1's concept cell (8.6 × 9.4, ratios 0.90/1.0) and `bowtie_over_web16`
(schematic panel figsize `[8.6, 3.7]`) are tuned to give the schematic a panel of **4.92in and
4.95in** — a 0.6% match. Without that, a student meets the same schematic at two different
sizes.

### FINDINGS

- **The deployed corpus is untouched: 681/681 byte-identical** vs the 0.9.0 baseline, with
  `plot_style.__file__` asserted against the baseline checkout, unpinned, twice per engine,
  self-diffs identical. All 120 moved figures are in 6.1 / 6.2 (undeployed).
- **Engine 0.9.0 cannot render 6.1 any more** — it raises on `kind: bowtie_schematic` and
  `kind: stack`. That is the fail-loudly dispatch working, and it means the baseline
  comparison has to be scoped to the deployed corpus, which is the corpus the gate is for.

---

## [0.10.0] — 2026-07-13 — the reciprocal-edge fix, the bow-tie schematic, stacked figures. **NOT tagged, NOT deployed**

Lesson 6's renderer pass. One shipped bug that made a figure state the opposite of its
caption, and two capabilities the L6 walkthrough proved were missing.

### Fixed — reciprocal edges were drawn as ONE curve, not two

- **🧨 A reciprocal pair's two arcs were SUPERIMPOSED. There was never a second code
  path.** The walkthrough reported 6.2's F⇄G rendering as an unreadable blob in the leak
  concept cell and as a single **double-headed arrow** in q_15, and reasonably inferred
  two renderers. There is one: both figures emit two single-headed `FancyArrowPatch`es
  through `draw_directed_graph` → `_reciprocal_rad`, with **identical** parameters. The
  two appearances are the same defect at two axes scales.

  `arc3` places its control point at `mid + rad * (dy, -dx)` with `d = end - start`.
  **Reversing an edge already flips `d`, and therefore already flips the perpendicular.**
  `_reciprocal_rad` negated `rad` on top of that — which flips it *back*. Both halves got
  the same control point and were drawn as **the same curve**:

      F->G, rad=+0.18  ->  control (2.25, -0.27)
      G->F, rad=-0.18  ->  control (2.25, -0.27)     <- identical

  The docstring's stated intent ("each half bows the opposite way") was right; the code
  did the exact opposite. The sign is now **constant** — each direction bows to the side
  its own travel direction picks, which is just as iteration-order-independent.

  This is not cosmetic. A double-headed arrow reads as **undirected adjacency**, the one
  notion Chapter 14 teaches students to abandon, and it destroys the leak cell's claim:
  the mechanism *is* that F and G point only at each other, and the picture has to show
  two arrows.

- **The bow is now a fixed length in POINTS (`reciprocal_edge_offset`, 10pt).** `arc3`'s
  `rad` is a fraction of the CHORD, so even with correct signs a fixed rad bows a short
  edge by a tiny absolute amount: F⇄G's 1.5-unit chord (~56pt) separated by ~10pt against
  a 16pt node radius. **This is the same data-unit basis bug as `pendant_stub` before
  0.7.0** (29.6× spread → 1.0×). The rad is now solved for per edge from the axes scale,
  so long edges bow gently and short ones bow more — the separation is what stays
  constant, because separation is what legibility depends on.

### Added — two new figure kinds

- **`bowtie_schematic` — a NEW FIGURE CLASS: regions and flows, not nodes and edges.**
  The engine had nothing that could draw it; every renderer here drew a node-link
  diagram, a table, or a curve. Draws the IN lobe, SCC core, OUT lobe, a tendril off IN,
  a mirror tendril off OUT, a tube bypassing the core, and a disconnected fragment — a
  qualitative recreation of Broder / E&K §13.6, **not** a port of the raster.
  `highlight=` brings one role forward so a single authored figure serves several
  questions.

  This partially reverses the blueprint's "colour a real graph by role instead" call.
  That was right not to port and right that the role-coloured graph is good — but the
  schematic is not redundant, because the two teach different things: the schematic
  **orients** (here is the shape of the web, here is where the fringes live); the
  role-coloured graph **mechanizes** (roles are computed from edges; one link moves a
  page between them). Colours come from the existing `BOWTIE_COLORS`, so a role means one
  colour across both figures.

  Regions are `Ellipse`/`Polygon`, never `Circle` — deliberately. `edge_audit` reads a
  circle as a NODE, and would otherwise confidently audit the flows of a figure that has
  no graph in it.

- **`stack` — two or more figures stacked vertically as one figure**, plus
  `plot_style.stacked_axes()` for the concept seam. Needed in two independent places
  (6.1's q_15 wants the schematic above the university network; 6.2's random-walk cell
  wants the 8-page graph above the walk table, which currently asks a student to imagine
  a walker on a network it never shows). **Neither seam could express it**: a section's
  `figure:` is one spec and every renderer called `plt.subplots` itself, while
  `concept.py` hands a render function exactly one axes. `_render_graph` is now split
  into `_draw_graph_into(ax, spec)` + a wrapper — the byte-identical corpus proves the
  split moved nothing.

  **Panel heights are DERIVED, not declared.** Every figure here locks equal aspect, and
  `frame_signed_axes` chooses its limits to fit the axes box it is GIVEN — so the box's
  shape is an *input* to the drawing. Hand-guessed ratios produce two correct drawings
  separated by a third of a page of white space that `tight_layout` cannot reclaim,
  because the space is inside the axes. Each child's own `figsize:` is its statement of
  shape, and the stack sizes itself from those before drawing.

### Fixed — a test that ENCODED the bug

- `test_only_reciprocal_edges_curve` asserted that the two halves of a pair take
  **opposite-signed** rads. That is precisely the defect. The sign of an internal number
  was never the property worth testing; where the two arcs END UP is. Replaced, and the
  geometric property is now pinned against the rendered path in the redesign repo's
  `test_edge_audit.py`.

### FINDINGS

- **The render-regression gate is scoped exactly.** 915 figures, unpinned, twice per
  engine; both engines self-diff identical (so the determinism is real, not a pinned
  seed). **The deployed L1–L5 corpus is byte-identical — 0 of 685 figures moved.** All 34
  diffs are in 6.2, and they are one-to-one with the figures that contain a 2-cycle
  (`pr8_leak`'s F⇄G, `pr3`'s A⇄B, and the two concept cells that draw them). Every 6.2
  figure *without* a reciprocal pair is unchanged; 6.1 and 7.1 are untouched, and 6.1 has
  no 2-cycle anywhere, which is why.
- **⚠️ The gates cannot see any of this, and both bugs found by eyeballing.** The
  coincident-arc bug passed every numeric test for two releases. The bow-tie schematic's
  TUBE was drawn bowing straight THROUGH the SCC core — labelled TUBE, meaning "bypasses
  the core" — on the first cut, with the `arc3` rad sign backwards *again*. No gate can
  see either. **`arc3`'s sign convention has now produced three separate bugs in this
  engine. Compute the control point before trusting it.**

---

## [0.9.0] — 2026-07-12 — sponsored search (Ch.15): the four-column figure, VCG/GSP, and three latent bugs. **NOT tagged, NOT deployed**

The renderer-first gate for Lesson 7. Chapter 15's foundational figure could not be
drawn at all, VCG and GSP did not exist, and three bugs in shipped code were waiting
for the first rectangular market to walk into them.

### Added — renderer

- **The two annotation columns are now GENERAL, and symmetric.** Each entry may be a
  SCALAR, a VECTOR, or a pre-formatted string, and each column's header is a caption
  you pass (`price_label=`, `valuations_label=`). This is what unlocks E&K's Fig 15.2
  / 15.6 — `clickthrough rates | slots | advertisers | revenues per click`, four
  columns and no edges — and all five of the worksheet's `bi-partite*.pdf` figures,
  which are that same shape. Through 0.8.1 the right column ITERATED its argument (a
  scalar raised `TypeError: 'int' object is not iterable`) and both headers were the
  hardcoded literals `"price"` and `"valuations"` — so even a 1-vector workaround
  would have captioned a clickthrough rate as a *price*, on the one figure whose whole
  point is that it is not one. Defaults are the old literals, so every Chapter-10
  caller is untouched.
- **`_declash_annot_column`** — a wide column title and a two-line header OVERPRINT
  each other ("advertisers" is 1.54 data units against the 0.5 the header sits at, and
  a second header line grows up into the title's row). The figure rendered
  `advertisersrevenues`. **No numeric gate can see this** — every number on the figure
  is correct — **and the byte-identity gate cannot see it either**, because the figure
  is new and has no baseline. It was found by LOOKING at the figure, which is the only
  thing that finds this class.

### Added — compute (Chapter 15, derived from the chapter)

- **`sponsored_search_valuations(rates, values)`** — `v_ij = r_i * v_j`, the conversion
  the whole chapter rests on, plus **`pad_sponsored_market`**, the fictitious
  clickthrough-rate-0 slot that squares the market (E&K Exercise 6 makes the padding
  step 1 of the mechanism, not bookkeeping).
- **`vcg_prices(valuations)`** — the **HARM RULE**, Equation (15.1):
  `p_ij = V^S_{B-j} - V^{S-i}_{B-j}`. Returns the prices, the assignment, the revenue,
  and — deliberately — the **two welfare terms behind each price**, so a worksheet can
  SHOW the subtraction instead of asserting the answer.
- **`gsp_outcome`**, **`gsp_deviations`**, **`is_gsp_equilibrium`** — the generalized
  second-price auction: slot *i* to the *i*-th highest bidder at the *(i+1)*-st highest
  bid, cumulative `r_i * b_{i+1}`. `gsp_deviations` names the *specific* profitable lie
  rather than merely reporting that one exists.

> ⚠️ **VCG IS NOT SOURCED FROM THE ASCENDING AUCTION, AND MUST NEVER BE.** §15.9 proves
> the VCG prices ARE the minimum market-clearing prices, so it is tempting to compute
> them by running `ascending_auction_rounds` and reading the prices off. That agreement
> is a **THEOREM ABOUT TWO CONSTRUCTIONS, NOT A DEFINITION OF EITHER**. Sourcing VCG
> that way teaches the wrong derivation even when the number lands right — the student
> never meets the harm rule, which *is* the conceptual content of VCG — and it makes
> the chapter's deepest result unfalsifiable by construction, since the two "different"
> computations would be the same code and would agree no matter what. `vcg_prices`
> differences two welfare optima and never looks at a price;
> `test_vcg_agrees_with_the_ascending_auction` then compares two genuinely independent
> computations, which is the only reason that comparison carries information.

### Fixed — three latent bugs in shipped code, independent of Lesson 7

- **B1. `optimal_assignment` SILENTLY RETURNED `None` when agents > objects** — the
  canonical sponsored-search shape, and E&K Exercise 1 verbatim (3 advertisers, 2
  slots). It brute-forced `permutations(range(m), n)`, which is EMPTY when `n > m`, so
  the running best never left its `None` initializer. Nothing raised. The `None` then
  travelled to `draw_bipartite_market` and died on `None.items()` — an `AttributeError`
  blamed on the renderer, three frames from the fault. It now computes the answer,
  which exists: every object goes to a distinct agent, and the agents who get nothing
  are absent from the returned dict.
- **B2. `ascending_auction_rounds` returned a 69-round trace that never cleared** — on
  the same market. With more buyers than sellers the set of ALL buyers is constricted
  at every price vector, so no prices can EVER clear; the loop ran its defensive
  round-bound to exhaustion and handed back a meaningless final price vector,
  indistinguishable to any caller reading `rounds[-1]["prices"]` from a trace that
  cleared. It now raises, and names the remedy.
- **B3. `_bipartite_vector_label` mangled scalars and strings** — `TypeError` on `3`;
  and `"10"` was walked character-by-character and rendered as **`[1, 0]`**. The second
  is the worse one: it did not raise, it drew a wrong number onto a figure.
- **`note` and `edge_style` were forwarded by the bipartite dispatch but never
  whitelisted**, and `_check_figure_keys` runs first — so `note:` on any bipartite
  figure RAISED, and the renderer's entire note branch was dead code, unreachable from
  YAML since the day it shipped.

### Not changed — and proven so

- **Render regression: 858/858 figures BYTE-IDENTICAL** to 0.8.1 across all 13
  worksheet YAMLs, both seams (dispatch + concept cells). Baseline rendered from a real
  0.8.1 checkout with `cs470_engine.plot_style.__file__` **asserted** to resolve inside
  it before a single figure was drawn — `PYTHONPATH` does not shadow an editable
  install, and a baseline that silently imports the working tree compares 0.9.0 to
  itself. Run **unpinned** (`PYTHONHASHSEED=random`), twice per engine; both self-diffs
  clean.
- **The de-clash is gated on the header containing a NEWLINE**, which is what makes the
  above true *by construction*: every header in the live corpus is a single word, so the
  gate cannot open on them. An earlier version of this change tested the measured boxes
  alone and **moved 71 live figures** — the measurement runs pre-`tight_layout`, where
  text extents in data units are not yet final, and it grazed on Lesson 4's long titles
  ("Sellers (1 real + 2 fake)"). `tight_layout` is **not idempotent**, so the renderer
  cannot simply call it and measure the truth. `test_R1_declash_never_fires_on_a_single_line_header`
  pins this.

### 🧨 FINDINGS — the load-bearing ones. Read these before touching Ch.15 or the bipartite renderer.

**1. VCG comes from the HARM RULE. It must NEVER be sourced from the ascending auction.**
E&K §15.9 *proves* the VCG prices equal the minimum market-clearing prices, so it is
tempting to compute them by running `ascending_auction_rounds` and reading the prices
off. **That coincidence is a THEOREM ABOUT TWO CONSTRUCTIONS, NOT A COMPUTATION OF
EITHER.** Sourcing VCG that way teaches the WRONG DERIVATION even when the number lands
right — the student never meets the harm rule, which *is* the conceptual content of VCG —
and it makes the chapter's deepest result **unfalsifiable by construction**: the two
"different" computations would be the same code, and would agree no matter what.
`vcg_prices` differences two welfare optima (Eq. 15.1) and never consults a price, a bid,
or an auction. The agreement is therefore a **TEST**
(`test_vcg_agrees_with_the_ascending_auction`, six markets — on Fig 15.8 both give
40, 4, 0), and it is available to a concept cell as a result to *show*, not an assumption
that was smuggled in.

**2. GSP does NOT dominate VCG on revenue.** E&K's own example: GSP yields **48** at one
equilibrium and **34** at another, with VCG at **44** *in between*. So `34 < 44` — and the
source worksheet's concluding claim that GSP revenue always beats VCG is **unconditionally
false**. Pinned by `test_the_revenue_race_GSP_DOES_NOT_DOMINATE_VCG`, which asserts
`not (lo >= vcg)` so the claim cannot creep back in.

**3. ⚠️ FALSE PREMISE — "a long header would be silently CLIPPED." IT IS NOT.**
matplotlib `Text` has **`clip_on=False`** by default, and the save path uses
**`bbox_inches="tight"`** — so text overflowing the axes still DRAWS, and the saved PNG
simply grows to include it. This is not theoretical: **0.8.1's `"price"` header already
spills outside the axes on every Lesson-4 figure**, and those figures are fine. A fix
premised on clipping — sizing the frame to fit the caption — **moved 71 live figures and
was reverted.** The real defect was never clipping; it was two texts OVERPRINTING each
other. Recording it because it is an intuitive, wrong premise that will otherwise be
re-adopted by the next person who sees a caption hanging off the axes.

**4. ⚠️ `tight_layout` IS NOT IDEMPOTENT.** Calling it twice on the same unchanged figure
produces a **different PNG each time** (verified: three calls, three hashes). So a renderer
CANNOT call `tight_layout` internally in order to measure true post-layout text extents —
doing so drifts the layout and moves the entire live corpus. This is the reason the
title/header de-clash is gated **structurally** (on a newline in the header, the actual
cause: the header is anchored *below* the title and only a second line can rise into its
row) rather than on a measurement. The engine's standing caveat — *collision detection runs
pre-`tight_layout`, so it is an APPROXIMATION* — has this as its sharp edge: you cannot
simply fix it by measuring later.

---

## [0.8.1] — 2026-07-12 — `initial=` on the HITS iteration, **NOT tagged, NOT deployed**

A one-parameter fix, and the parameter is the whole point of a concept cell.

### Added

- **`hits_iterations(..., initial=None)`** — a starting vector, matching
  `pagerank_iterations`, which had taken one all along. The asymmetry was an
  **omission, not a design decision**, and it blocked the only thing worth showing
  about HITS: that the scores converge to the **same limit no matter where you start
  them**. Without a way to vary the start, Worksheet 6.1's stepper cell could only
  animate an iteration; it could not demonstrate the property. `hits_limit` forwards
  it too, so the claim can be *checked* and not merely asserted.
- **`_initial_vector(order, initial, default)`** — ONE shared resolver, now used by
  `hits_iterations`, `hits_limit`, `pagerank_iterations` and `pagerank_limit`. Same
  shape, same `Fraction` coercion (ints / floats / `'p/q'` strings / Fractions), same
  validation, for both algorithms. The two helpers cannot drift apart on this
  argument again, which is exactly how they came to differ in the first place.

### Changed

- A partial `initial` (one that omits a node) now **raises `ValueError`** naming the
  missing nodes, on *both* algorithms. It previously raised a bare `KeyError` from
  inside `pagerank_iterations`. An incomplete starting vector is an authoring
  mistake, not a request for defaults.
- `hits_limit`'s docstring now states plainly that **what it returns is an
  approximation, and has to be**: the HITS limit is an *eigenvector* and is generally
  **irrational** (on Fig 14.15 page C's limiting authority is exactly `sqrt(2) - 1`),
  so — unlike `pagerank_equilibrium`, which solves an exact rational linear system —
  the iteration never lands on a fixed point and the "have the vectors stopped
  moving?" check never fires on a real graph. **Two runs from different starts do not
  come back `==`.** They agree to within the residual (~1e-153 at the default
  `max_iter`), and the residual shrinks geometrically. Compare limits with a
  tolerance.

### Not changed — and proven so

- **Omitting `initial` reproduces 0.8.0 exactly**, including `state_0` and the `_raw`
  rows (`test_omitting_initial_reproduces_the_pre_0_8_1_output_exactly`).
- **Render regression: 723/723 figures BYTE-IDENTICAL** to 0.8.0 across all 12
  worksheet YAMLs (both seams — dispatch and concept cells). Baseline rendered from a
  real `cb7c6d0` worktree with `cs470_engine.plot_style.__file__` **asserted** to
  resolve there before a single figure was drawn — `PYTHONPATH` alone would have
  silently imported the working tree and compared 0.8.1 against itself. Run
  **unpinned** (`PYTHONHASHSEED=random`), twice per engine; both self-diffs identical,
  so the pass is not a masked non-determinism.
- `ENGINE_SYMBOLS` needs no update: `initial=` adds a **parameter**, not a public
  symbol, and `hits_iterations` / `hits_limit` were already on the frozen list. The
  drift test (`test_engine_symbols_covers_the_engine_surface`) confirms it.

### Fixed (a test that was lying)

- `test_hits_limit_is_independent_of_the_starting_vector` **never tested that**. It
  asserted the limit was nonnegative and summed to 1 — nothing about starting vectors,
  because there was no way to set one. A test named for the property that the missing
  parameter made untestable. Renamed to
  `test_hits_limit_settles_nonnegative_and_normalized`, and the property it claimed is
  now genuinely tested, from four different starting vectors on three figures, with
  the gap-shrinks-with-`max_iter` check that turns "they are close" into "they
  converge".

Tests: **39/39** (`tests/test_link_analysis.py`), 24/24 (`tests/test_figure_dispatch.py`).

---

## [0.8.0] — 2026-07-12 — built + proven, **NOT tagged, NOT deployed**

The Lesson 6 renderer/helper package: the blocking gate in front of L6 authoring.
Built as **parity**, not an L6 special case — L6 is the first of nine remaining
lessons and the first to use a directed graph, so a special case here would have
been paid for eight more times.

**Deliberately un-tagged and un-deployed.** `v0.7.0` remains the tagged, deployed
engine. L6 is not authored yet; tagging and image-baking are a separate step.

### Added

- **`draw_directed_graph` brought to annotation PARITY with `draw_graph`**
  (`plot_style.py`). It had none of the layers `draw_graph` grew across L4/L5. It
  now takes node-value annotations (**two rows** — hub *and* authority are two
  scores on one node), node highlighting, categorical node grouping, and
  `show_labels`. The placement machinery is **SHARED, not forked**:
  `_draw_node_annotations` is now the single place annotation happens, so 0.7.0's
  collision-aware angle-driven placement and conditional self-decoding row captions
  apply to directed figures without being reimplemented for them.
- **`link_analysis.py`** (new module) — `hits_iterations` / `hits_limit`;
  `pagerank_iterations` / `pagerank_limit` / `pagerank_equilibrium` /
  `is_pagerank_equilibrium`; `strongly_connected_components` / `giant_scc` /
  `bowtie_partition`; and the matrices `adjacency_matrix` / `flow_matrix` /
  `scaled_flow_matrix`. **Every value is an exact `Fraction`** — see below.
- **`draw_matrix`** — the generic matrix (bracketed) / iteration-table (booktabs)
  renderer. Nothing generic existed; `draw_payoff_matrix` and `draw_auction_table`
  are domain-specific. New figure kinds **`matrix`** and **`iteration_table`**, with
  rows **computed**, not typed.
- **Reciprocal-edge arcs.** A 2-cycle used to render as two arrowheads superimposed
  on ONE segment — indistinguishable from a single link. The two figures that need
  it (F⇄G's leak, A⇄B's oscillation) are the two carrying the lesson's key insights.
- **`figsize` + `value_format`** on figure specs.

### Changed — the figure dispatch now FAILS LOUDLY (`problems.py`)

- **An unknown figure-spec key RAISES.** The directed branch used to forward only
  `pos` and `labels`, so an author who wrote `directed: true` + `highlight_nodes`
  got **no highlight and no error**. Now: per-**renderer** allowlists, so `matching:`
  on a *directed* graph raises rather than evaporating. Also raises on an unknown
  `kind`, a dangling `ref`, a missing `image` path, an unknown `compute`, and
  `directed: false` on a link-analysis kind.
- **Reds nothing live** — all 11 worksheets still validate green.

### Fixed — three bugs the eyeball pass caught that the numbers did not

**All three were invisible to passing tests.** Second build running where looking at
the figures found what green tests missed.

- 🧨 **`bowtie_partition` was NON-DETERMINISTIC across processes.** It iterated a
  `set` of nodes, so the returned dict's KEY ORDER varied with Python's per-process
  hash seed — and the group palette is assigned in group-first-appearance order. **The
  bow-tie could come out a different color on every kernel start**, which from a
  screenshot reads as a content bug, not an engine bug. Now iterates `G.nodes()`.
  Verified under `PYTHONHASHSEED=random`.
- 🧨 **The collision search computed its label boxes against the wrong scale.**
  `_data_per_point` assumed **x** is always the binding dimension under equal aspect.
  On a TALL layout (Fig 14.16's two stacked columns) it is **y**, so every label box
  came out too small and the search declared a colliding figure clean. The symptom was
  diagnostic and backwards: giving the graph MORE vertical room made the collisions
  WORSE. Now takes the max of both ratios.
- **`_incident_angles` used `G.neighbors()` on a DiGraph** — which is **successors
  only**. An in-edge runs through a label just as surely as an out-edge, so labels were
  being placed on in-edges. Now unions predecessors. (Undirected is untouched:
  `neighbors()` there already means every incident edge — which is why the 681-figure
  byte-identity gate below still holds.)

### 🧨 DO NOT USE `nx.pagerank` / `nx.hits` — recorded so it is not re-litigated

E&K's **Basic** rule has no damping and sends a dangling node's rank **to itself**;
`nx.pagerank` implements only the **scaled** rule and sprays dangling mass
**uniformly**. **Measured divergence: 0.358** on a 3-node graph with one dangling node.

Worse, the Basic rule **does not always converge**. On (A⇄B, C→A) it oscillates with
period 2 forever. `nx.pagerank(alpha=1.0)` **raises `PowerIterationFailedConvergence`**
there — an error, not a finding — while at its default `alpha=0.85` it returns a
confident vector answering a *different question*. Either way the oscillation, which is
the worksheet's best item, is unavailable. `pagerank_limit` returns a **`PageRankLimit`**
object instead of a vector, because "there is no limit" is an *answer*, not an error:
`.converged`, `.limit` (`None`), `.period` (2), `.cycle`, `.iterations`.

**This is why every value is an exact `Fraction`.** Oscillation is detected by exact
vector equality against the orbit's history — `r³` **is** `r¹`, an identity, not a
tolerance judgment. With floats, "oscillating" and "converging too slowly to see" are
the same observation. **`period` (not `converged`) is what separates proven oscillation
(≥2) from a spent iteration budget (0)** — Fig 14.6 needs ~213 updates to settle and
would otherwise be libeled as non-convergent.

`networkx` is a **sanity check only**: on dangling-free graphs the scaled rule agrees
with `nx.pagerank(alpha=0.85)` to **<1e-9**. SCC is the one place the definitions
genuinely coincide, and is cross-checked against Tarjan.

### Verified

- **REGRESSION: 681 / 681 figures BYTE-IDENTICAL to 0.7.0.** Both render seams — the
  **YAML dispatch** (all 11 worksheets' problem figures) **and the concept cells** (84
  cells swept one-at-a-time over every control value, a path a dispatch-only harness
  would miss entirely). Run unpinned; both engines hash identically across two
  independent random hash seeds. Committed as **`tests/render_regression.py`** — 0.7.0's
  harness was ephemeral and had to be rewritten. *(Byte-identity also re-confirms 0.7.0's
  "0 collisions" claim: the new collision fallback is a detector, and it fires on none of
  the 681.)*
- **Chapter worked examples reproduce EXACTLY (56/56):** Fig 14.11 all four HITS vectors;
  Figs 14.15 / 14.16 all four each; Fig 14.6 both PageRank steps + the 4/13 equilibrium;
  Fig 14.8's drain to F=G=1/2; the 3-node period-2 cycle. Plus **E&K footnote 2 pinned**:
  at s = 0.8 / 0.85 / 0.9, F and G still take **54.8% / 61.4% / 70.2%** — scaling does
  **not** rescue a small network, the over-claim students reliably make.
- **Tests: 30/30** (`test_link_analysis.py`) + **24/24** (`test_figure_dispatch.py`), both
  standalone-runnable.
- **Eyeballed: 34 L6 figures** rendered through the real dispatch. **The scc2 erratum is
  pinned in a test**: OUT = **{4, 13}**, not the source key's {4, 8, 9, 13} (which puts 8
  and 9 in the SCC *and* downstream).

---

## 0.2 – 0.7.0

See the annotated tags and `CS_470_Redesign/CHANGELOG.md`.
