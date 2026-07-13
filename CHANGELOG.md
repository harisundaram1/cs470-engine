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
