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
