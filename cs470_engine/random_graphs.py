"""Erdős–Rényi random-graph theory — EXACT compute + a seeded G(n,p) sampler.

Lesson 8 has NO textbook chapter (Easley & Kleinberg has no random-graph
chapter), so for every quantity here the DERIVATION IS THE GROUND TRUTH. Each
public helper names the theorem it rests on in its docstring — the authority a
reviewer checks the code against, since there is no book to check against.

Two disciplines this module keeps, both load-bearing:

1. EXACT, NOT SAMPLED. The pmfs, thresholds, expected values and the giant-
   component fraction are computed from the CLOSED FORM — ``binomial_pmf`` is
   ``C(n,k) p^k (1-p)^(n-k)`` evaluated exactly, never estimated by drawing
   graphs and counting. A sampled quantity is NOT a derived one: the theorems
   E[deg]=np, C=p, the threshold values are computed here from the formula; the
   sampler (``sample_gnp``) exists ONLY for the one optional "resample" concept.
   The two are kept in separate functions with separate names on purpose
   (``giant_component_fraction`` = theory; ``largest_component_fraction`` =
   measured off an actual graph) so a sample can never masquerade as a theorem.

2. CONVENTION (Hari's fixed decision). Thresholds are stated on the ``np`` basis:
   the giant component emerges at mean degree ``np = 1`` (``p_c = 1/n``) and the
   graph connects at ``np = ln n`` (``p_c = ln n / n``). ER theory lives in the
   ``n -> infinity`` LIMIT, where ``np`` and the exact finite-n mean ``(n-1)p``
   coincide; the ``1/n`` vs ``1/(n-1)`` gap is an asymptotically-vanishing
   finite-n artifact, NOT a real distinction in this regime. ``expected_degree``
   returns ``np`` accordingly; the docstring reconciles it with the exact mean
   of the degree distribution ``Binomial(n-1, p)`` so the two are never silently
   inconsistent.

The pmf/threshold/fraction helpers are PURE PYTHON (``math`` only). Only the
optional ``sample_gnp`` needs numpy — imported lazily inside it — so a worksheet
that draws only distributions and curves pulls in no RNG dependency at all.
"""
import math

import networkx as nx

__all__ = [
    "binomial_pmf",
    "poisson_pmf",
    "binomial_series",
    "poisson_series",
    "degree_distribution",
    "expected_degree",
    "expected_edge_count",
    "giant_component_threshold",
    "connectivity_threshold",
    "giant_component_fraction",
    "largest_component_fraction",
    "sample_gnp",
    # Lesson 9 — heavy-tailed / power-law layer (C1 closed forms + C3 estimators)
    "power_law_series",
    "power_law_ccdf",
    "exponent_from_p",
    "ek_stationary_indegree",
    "ek_copy_indegree_counts",
    "frozen_c3_indegree_counts",
    "alpha_naive_lsq",
    "alpha_mle",
]


# -----------------------------------------------------------------------------
# Probability mass functions — exact closed form
# -----------------------------------------------------------------------------

def binomial_pmf(k, n, p):
    """Binomial pmf ``P(X=k) = C(n,k) p^k (1-p)^(n-k)`` for ``X ~ Binomial(n, p)``.

    AUTHORITY: definition of the binomial distribution (``n`` i.i.d. Bernoulli(p)
    trials). Computed EXACTLY via ``math.comb`` — never estimated by sampling.

    ``k`` outside ``0..n`` has probability 0 (returned as ``0.0``, not raised —
    it is a valid query with a mass of zero). ``p`` must lie in ``[0, 1]`` and
    ``n`` must be a non-negative integer, else ``ValueError``: those are
    malformed *parameters*, a different thing from an out-of-support ``k``.

    In Lesson 8 this is the edge-count law ``Binomial(C(n,2), p)`` (M2) and,
    with ``n`` set to ``nodes - 1``, the degree law ``Binomial(n-1, p)`` (M4).
    """
    _check_prob(p, "p")
    if not (isinstance(n, int) and n >= 0):
        raise ValueError(f"binomial_pmf: n (number of trials) must be a "
                         f"non-negative int, got {n!r}.")
    if k < 0 or k > n:
        return 0.0
    return math.comb(n, k) * (p ** k) * ((1.0 - p) ** (n - k))


def poisson_pmf(k, lam):
    """Poisson pmf ``P(X=k) = e^{-lam} lam^k / k!`` for ``X ~ Poisson(lam)``.

    AUTHORITY: definition of the Poisson distribution. In Lesson 8 this is the
    ``n -> infinity`` limit of the degree law at fixed ``lam = np`` — the law of
    rare events, ``Binomial(n, lam/n) => Poisson(lam)`` (M6, the Poisson limit
    theorem). Computed EXACTLY in LOG SPACE, not sampled.

    ``k < 0`` has mass 0. ``lam`` must be ``>= 0`` else ``ValueError``.

    LOG-SPACE — WHY (the ``k >= 171`` OverflowError fix, required by Lesson 9's
    Poisson-vs-power-law tail at ``k_max = 1000``): the direct form
    ``exp(-lam) * lam**k / factorial(k)`` raises at EXACTLY ``k = 171``, because
    ``math.factorial(171) ~ 1.2e309`` exceeds the float maximum and the
    ``float / int`` division cannot convert it — so ``poisson_series(3.0, 1000)``
    could not be drawn at all. The mathematically identical
    ``exp(k*ln(lam) - lam - lgamma(k+1))`` never forms the huge factorial: it
    UNDERFLOWS smoothly toward 0 for large ``k`` (1.68e-281 at k=200, 0.0 by
    k~1000) instead of raising, and reproduces the direct form to ``< 2e-13``
    relative on ``0 <= k <= 170`` (asserted in ``tests/test_random_graphs.py`` —
    the fix moves NO correct value, it only extends the reachable range).
    """
    if lam < 0:
        raise ValueError(f"poisson_pmf: lam must be >= 0, got {lam!r}.")
    if k < 0:
        return 0.0
    if lam == 0:
        # Poisson(0) is the point mass at 0: P(0)=1, P(k>0)=0. Required (not an
        # optimization): ``math.log(0)`` below is ``-inf`` and would poison the
        # log-space expression.
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))


def binomial_series(n, p, k_max=None):
    """The binomial pmf as ``[(k, P(X=k)) for k in 0..k_max]`` (default all ``n``).

    A plotting-ready series for ``draw_distribution``. Exact; see ``binomial_pmf``.
    """
    if k_max is None:
        k_max = n
    return [(k, binomial_pmf(k, n, p)) for k in range(0, k_max + 1)]


def poisson_series(lam, k_max):
    """The Poisson pmf as ``[(k, P(X=k)) for k in 0..k_max]``.

    A plotting-ready series for ``draw_distribution``. Exact; see ``poisson_pmf``.
    ``k_max`` is required (the Poisson support is unbounded) — pick it to match
    the companion binomial's range so an overlay lines up value-for-value.
    """
    if not (isinstance(k_max, int) and k_max >= 0):
        raise ValueError(f"poisson_series: k_max must be a non-negative int, "
                         f"got {k_max!r}.")
    return [(k, poisson_pmf(k, lam)) for k in range(0, k_max + 1)]


def degree_distribution(n, p, k_max=None):
    """Degree pmf of ``G(n, p)`` as ``[(d, P(deg=d)) for d]`` — ``Binomial(n-1, p)``.

    AUTHORITY: M4. A node has ``n-1`` potential neighbors, each an independent
    Bernoulli(p) (no self-loops), so ``P(deg=d) = C(n-1,d) p^d (1-p)^(n-1-d)``.
    Its exact mean is ``(n-1)p`` (see ``expected_degree``).

    ``k_max`` defaults to ``n-1`` (the full support). Exact, not sampled.
    """
    if not (isinstance(n, int) and n >= 1):
        raise ValueError(f"degree_distribution: n (nodes) must be a positive "
                         f"int, got {n!r}.")
    trials = n - 1
    if k_max is None:
        k_max = trials
    return [(d, binomial_pmf(d, trials, p)) for d in range(0, k_max + 1)]


# -----------------------------------------------------------------------------
# Expected values and thresholds — exact / by-convention
# -----------------------------------------------------------------------------

def expected_degree(n, p):
    """Mean degree of ``G(n, p)`` — the ``np`` on which the thresholds are stated.

    AUTHORITY: M5. Returns ``n * p``.

    HONEST RECONCILIATION: the degree distribution is ``Binomial(n-1, p)``
    (``degree_distribution``), whose EXACT finite-n mean is ``(n-1)p``. ER's
    threshold theorems live in the ``n -> infinity`` limit, where ``(n-1)p -> np``;
    ``np`` is the form those theorems (giant component at mean degree 1,
    connectivity at ``ln n``) and the Poisson limit ``lam = np`` are written in,
    so this returns ``np`` to stay consistent with them. The ``np`` vs ``(n-1)p``
    difference is an ``O(p)`` finite-n artifact, not a competing theory.
    """
    return n * p


def expected_edge_count(n, p):
    """Expected number of edges in ``G(n, p)`` — ``C(n,2) * p``.

    AUTHORITY: M3, linearity of expectation over the ``C(n,2)`` edge indicators.
    Exact. Setting ``p = m / C(n,2)`` makes this ``m`` in expectation (NOT an
    exact-``m`` G(n,m)).
    """
    if not (isinstance(n, int) and n >= 0):
        raise ValueError(f"expected_edge_count: n must be a non-negative int, "
                         f"got {n!r}.")
    return math.comb(n, 2) * p


def giant_component_threshold(n):
    """Critical ``p`` for the giant component: ``p_c = 1/n`` (mean degree ``np = 1``).

    AUTHORITY: M9, Erdős–Rényi (1960) phase transition. Below mean degree 1 the
    largest component is ``O(log n)``; above it a UNIQUE giant of size
    ``Theta(n)`` emerges. The threshold is mean-degree ``= 1``, taken here on the
    ``np`` basis (Hari's convention): ``np = 1 <=> p = 1/n``.
    """
    if not (isinstance(n, int) and n >= 1):
        raise ValueError(f"giant_component_threshold: n must be a positive int, "
                         f"got {n!r}.")
    return 1.0 / n


def connectivity_threshold(n):
    """Critical ``p`` for connectivity: ``p_c = ln(n)/n`` (mean degree ``np = ln n``).

    AUTHORITY: M10, Erdős–Rényi (1959) connectivity theorem — a sharp threshold
    at ``ln(n)/n``: below it isolated vertices survive w.h.p.; above it the graph
    is connected w.h.p. ``ln`` is the NATURAL log (confirmed by Hari's figure
    ``p = ln 50 / 50 = 0.0782``).
    """
    if not (isinstance(n, int) and n >= 1):
        raise ValueError(f"connectivity_threshold: n must be a positive int, "
                         f"got {n!r}.")
    return math.log(n) / n


def giant_component_fraction(mean_degree):
    """Fraction ``S`` of vertices in the giant component vs mean degree ``c = np``.

    AUTHORITY: M9, the Erdős–Rényi giant-component size equation. ``S`` is the
    survival probability of a Poisson(c) branching process and satisfies the
    self-consistent fixed point ``S = 1 - e^{-c S}`` (equivalently ``S = 1 - u``
    with ``u = e^{-cS}`` the extinction probability). For ``c <= 1`` the only
    root in ``[0,1]`` is ``S = 0`` (no giant component); for ``c > 1`` there is a
    unique positive root, returned here.

    This is the ``n -> infinity`` THEORETICAL curve — the flagship phase-transition
    plot, with its knee exactly at ``c = 1`` (``np = 1``). Solved by bisection
    (deterministic, no slow near-critical fixed-point iteration). It is NOT a
    measurement off a sampled graph — that is ``largest_component_fraction``.
    """
    c = float(mean_degree)
    if c <= 1.0:
        return 0.0

    # g(S) = 1 - e^{-cS} - S. g(0)=0 with g'(0)=c-1>0 (so g>0 just above 0), and
    # g(1) = -e^{-c} < 0 — exactly one root in (0, 1). Bisect for it.
    def g(s):
        return 1.0 - math.exp(-c * s) - s

    lo, hi = 1e-15, 1.0            # g(lo) > 0, g(hi) < 0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if g(mid) > 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def largest_component_fraction(G):
    """MEASURED fraction of nodes in the largest connected component of ``G``.

    ``len(largest component) / number_of_nodes``. This is an OBSERVATION off an
    actual graph (via ``networkx.connected_components``), NOT the ER theorem —
    named distinctly from ``giant_component_fraction`` so a sampled measurement
    is never mistaken for the derived curve. Use it only to report a property of
    a ``sample_gnp`` instance in the optional resample concept.
    """
    n = G.number_of_nodes()
    if n == 0:
        return 0.0
    largest = max((len(c) for c in nx.connected_components(G)), default=0)
    return largest / n


# -----------------------------------------------------------------------------
# Seeded G(n, p) sampler — the ONE optional concept; must be byte-reproducible
# -----------------------------------------------------------------------------

def sample_gnp(n, p, seed):
    """Sample ``G(n, p)``: each of the ``C(n,2)`` possible edges present
    independently with probability ``p``. DETERMINISTIC given ``seed``.

    MODEL (M1): the Gilbert / Erdős–Rényi ``G(n, p)`` — NOT ``G(n, m)`` (which
    fixes an exact edge count). The code is the model literally: it iterates the
    ``C(n,2)`` node pairs in the fixed upper-triangle order ``(0,1),(0,2),...``
    (== ``itertools.combinations(range(n), 2)``) and includes pair ``(u,v)`` iff
    its independent uniform draw is ``< p``.

    RNG — WHY IT IS REPRODUCIBLE ACROSS ENVIRONMENTS (the whole ballgame for a
    sampled figure): a ``numpy`` ``Generator`` over an EXPLICIT ``PCG64`` bit
    generator seeded from the integer ``seed``. numpy's stream-compatibility
    policy guarantees a given BitGenerator + SeedSequence yields the SAME stream
    across numpy versions, so the same ``seed`` gives the SAME edge list
    byte-for-byte on the laptop and inside the container (proven at build time
    against numpy 2.4.3 local vs 2.4.4 in the image). It does NOT delegate to
    ``networkx.gnp_random_graph`` — that is G(n,p) too, but it seeds off Python's
    ``random`` via ``@py_random_state`` and its internals can shift across
    networkx versions; owning the draw here makes reproducibility depend only on
    the pinned numpy bit generator, nothing else.

    ``seed`` is REQUIRED and must be an int: there is no seeding off time / hash /
    PID / environment — that would break byte-identity. ``n`` must be a
    non-negative int and ``p`` in ``[0, 1]``.
    """
    import numpy as np

    if not (isinstance(n, int) and n >= 0):
        raise ValueError(f"sample_gnp: n must be a non-negative int, got {n!r}.")
    _check_prob(p, "p")
    if not isinstance(seed, int):
        raise ValueError(
            f"sample_gnp: seed must be an int (byte-reproducibility requires an "
            f"explicit fixed seed — never time/hash/PID), got {seed!r}.")

    rng = np.random.Generator(np.random.PCG64(seed))
    G = nx.Graph()
    G.add_nodes_from(range(n))
    if n >= 2:
        rows, cols = np.triu_indices(n, k=1)          # C(n,2) pairs, fixed order
        draws = rng.random(rows.shape[0])             # one uniform per pair
        for u, v, d in zip(rows.tolist(), cols.tolist(), draws.tolist()):
            if d < p:
                G.add_edge(int(u), int(v))
    return G


# -----------------------------------------------------------------------------
# Lesson 9 — heavy-tailed / power-law layer (C1 closed forms + C3 estimators)
# -----------------------------------------------------------------------------
#
# Same discipline as the pmf helpers above: EXACT closed form, never sampled;
# each helper names its Easley & Kleinberg authority. The two ESTIMATORS
# (``alpha_naive_lsq`` / ``alpha_mle``) are the deliberate exception — they are
# UNCORRECTED on purpose, because their bias IS Lesson 9's lesson (see each
# docstring). The one place a sampled artifact is unavoidable — C3 Figure B's
# finite-sample noise — is produced by a DETERMINISTIC, seed-pinned generator
# (``ek_copy_indegree_counts``) whose output is committed as data, so no live
# sampler ever runs at figure-render time (honors L9 decision Q2).


def power_law_series(alpha, k_min, k_max):
    """Exact normalized power-law pmf ``P(k) = C * k**(-alpha)`` as ``[(k, P), ...]``.

    AUTHORITY: E&K Section 18.2 (the ``1/k^2``-style degree distribution of the
    Web). Normalized over the FINITE plotted support ``[k_min, k_max]`` so it is
    a genuine pmf (``sum P = 1``); the normalization is an additive constant in
    log space, so a log-log least-squares fit of ``P`` vs ``k`` recovers the
    slope EXACTLY ``-alpha`` regardless of ``k_min`` / ``k_max`` — the pedagogical
    invariant Figure F1 asserts. Plotting-ready like ``poisson_series``.

    This is F1's IDEAL straight line and F3's TRUE line. ``1 <= k_min <= k_max``.
    """
    if not (isinstance(k_min, int) and isinstance(k_max, int)
            and 1 <= k_min <= k_max):
        raise ValueError(f"power_law_series: need integers 1 <= k_min <= k_max, "
                         f"got k_min={k_min!r}, k_max={k_max!r}.")
    ks = list(range(k_min, k_max + 1))
    weights = [float(k) ** (-alpha) for k in ks]
    z = sum(weights)
    return [(k, w / z) for k, w in zip(ks, weights)]


def power_law_ccdf(alpha, k_min, k_max):
    """Power-law CCDF ``F(k) = P(X >= k) = (k / k_min)**(-(alpha - 1))``.

    AUTHORITY: E&K Section 18.7 (Eq. 18.4) — the tail of a power law with density
    exponent ``alpha`` is itself a power law with exponent ``alpha - 1``. This is
    the ANALYTIC closed-form CCDF (continuous approximation), NOT the exact
    discrete tail sum of ``power_law_series`` — the two agree asymptotically and
    E&K states the figure in this closed form. Normalized so ``F(k_min) = 1``
    ("every item has at least ``k_min``"), decreasing thereafter. A log-log fit
    recovers slope EXACTLY ``-(alpha - 1)``.

    Feeds F4 (Section 18.5 long-tail / rank-frequency): F4's Fig 18.4 is Fig 18.3
    with the axes swapped, so the same series drawn transposed IS the Zipf plot.
    """
    if not (isinstance(k_min, int) and isinstance(k_max, int)
            and 1 <= k_min <= k_max):
        raise ValueError(f"power_law_ccdf: need integers 1 <= k_min <= k_max, "
                         f"got k_min={k_min!r}, k_max={k_max!r}.")
    return [(k, (k / k_min) ** (-(alpha - 1.0)))
            for k in range(k_min, k_max + 1)]


def exponent_from_p(p):
    """Power-law exponent of the E&K rich-get-richer model: ``alpha = 1 + 1/(1-p)``.

    AUTHORITY: E&K Section 18.7. In the copying model a new page copies a link
    with probability ``q = 1 - p`` (and links uniformly at random with prob ``p``);
    the stationary in-degree distribution is a power law with exponent
    ``1 + 1/q = 1 + 1/(1-p)``. At ``p = 1/2`` this is exactly ``3.0`` — the truth
    line for C3.

    COLLAPSE TRAP (do NOT pose an exponent MC item at ``p = 1/2``): ``1 + 1/(1-p)``
    and the natural ``p<->q`` transposition ``1 + 1/p`` are BOTH ``3.000`` at
    ``p = 1/2``, so the most natural student error is indistinguishable from the
    key and the item has no unique answer. ``p = 1/2`` is safe ONLY where 3.0 is a
    drawn TARGET (F3), never a keyed distractor. -> ``check_distractors`` /
    ``distinctness`` (not ``limit_distinct``, which passes the converging pair).
    """
    _check_prob(p, "p")
    if p >= 1.0:
        raise ValueError("exponent_from_p: p must be < 1 (q = 1 - p is the "
                         "copying probability; p = 1 is degenerate).")
    return 1.0 + 1.0 / (1.0 - p)


def ek_stationary_indegree(p, k_max):
    """EXACT stationary in-degree distribution of the E&K copying model.

    AUTHORITY: E&K Section 18.3, the deterministic rate (mean-field) equation for
    the copying model, solved as the recurrence

        f(0) = 1 / (1 + p)
        f(k) = f(k-1) * (p + q*(k-1)) / (1 + p + q*k),   q = 1 - p

    Returns ``[(k, f_k) for k in 0..k_max]`` — a plotting-ready EXACT distribution,
    NO sampler. Its asymptotic exponent is ``1 + 1/q = exponent_from_p(p)``.

    This is C3 Figure A's data. The whole point (vs a sampled degree list) is that
    it is INFINITE-DATA: the ``alpha_mle`` @ ``k_min = 5`` bias it exhibits (2.57
    at ``p = 1/2``, truth 3.0) is a CURVATURE / BODY property of the distribution,
    present with zero sampling noise and invariant to the tail cap ``k_max`` — a
    fundamentally different bias from C3 Figure B's finite-sample LSQ divergence.
    Deterministic, byte-identical forever.
    """
    _check_prob(p, "p")
    if not (isinstance(k_max, int) and k_max >= 0):
        raise ValueError(f"ek_stationary_indegree: k_max must be a non-negative "
                         f"int, got {k_max!r}.")
    q = 1.0 - p
    out = [(0, 1.0 / (1.0 + p))]
    fk = out[0][1]
    for k in range(1, k_max + 1):
        fk = fk * (p + q * (k - 1)) / (1.0 + p + q * k)
        out.append((k, fk))
    return out


def ek_copy_indegree_counts(n, p, seed, m0=2):
    """Deterministic E&K copying-model sample -> ``{in_degree: node_count}``.

    AUTHORITY: E&K Section 18.3 implemented DIRECTLY (never ``networkx`` /
    ``nx.barabasi_albert_graph`` — that model has no ``p`` parameter and cannot
    state this lesson's question). Each new node ``j`` forms ONE out-link:

      * with probability ``p`` -> a uniformly random existing node;
      * with probability ``q = 1 - p`` -> COPY, i.e. the target of a uniformly
        random existing edge (equivalently, preferential attachment by in-degree).

    Returns the in-degree HISTOGRAM (``{k: number of nodes with in-degree k}``),
    the compact form C3 Figure B commits (a ~150-entry table, not ``n`` integers).

    BYTE-REPRODUCIBLE local-vs-container, the whole point (same discipline as
    ``sample_gnp``): all randomness is drawn from an EXPLICIT ``PCG64`` generator
    seeded from the integer ``seed``; numpy's stream-compatibility policy makes the
    identical histogram appear on the laptop and inside the workspace image. This
    is the ONE sampled artifact in the engine; it is generated OFFLINE, its output
    committed as data, and the figure reads the committed table — no live sampler
    at render time (L9 decision Q2). ``ek_stationary_indegree`` is the exact,
    sampler-free companion.

    ``seed`` REQUIRED and an int (no time/hash/PID seeding — that breaks
    byte-identity). ``n >= m0 >= 1``; ``p`` in ``[0, 1]``.
    """
    import numpy as np
    from collections import Counter

    if not (isinstance(n, int) and n >= 1):
        raise ValueError(f"ek_copy_indegree_counts: n must be a positive int, "
                         f"got {n!r}.")
    _check_prob(p, "p")
    if not isinstance(seed, int):
        raise ValueError(
            f"ek_copy_indegree_counts: seed must be an int (byte-reproducibility "
            f"requires a fixed seed — never time/hash/PID), got {seed!r}.")
    if not (isinstance(m0, int) and 1 <= m0 <= n):
        raise ValueError(f"ek_copy_indegree_counts: need 1 <= m0 <= n, "
                         f"got m0={m0!r}, n={n!r}.")

    rng = np.random.Generator(np.random.PCG64(seed))
    indeg = [0] * n
    targets = []            # multiset of edge targets: a uniform pick == PA
    # Seed structure: a short chain among the first m0 nodes, so `targets` is
    # non-empty before the first copy draw. (Affects only the low-k body, not the
    # tail exponent.)
    for j in range(1, m0):
        indeg[j - 1] += 1
        targets.append(j - 1)

    coin = rng.random(n)    # p/q coin per new node
    pick = rng.random(n)    # selection uniform per new node
    for j in range(m0, n):
        if coin[j] < p or not targets:
            tgt = int(pick[j] * j)                    # uniform node in [0, j)
        else:
            tgt = targets[int(pick[j] * len(targets))]  # PA by in-degree
        indeg[tgt] += 1
        targets.append(tgt)

    return dict(sorted(Counter(indeg).items()))


def _count_items(counts):
    """Yield ``(k, weight)`` from a ``{k: w}`` dict OR a sequence of ``(k, w)``
    pairs — so an estimator accepts both an empirical histogram and an exact
    ``ek_stationary_indegree`` series."""
    items = counts.items() if isinstance(counts, dict) else counts
    for k, w in items:
        yield k, w


def alpha_naive_lsq(counts, k_min):
    """The NAIVE, BIASED log-log least-squares power-law exponent estimator.

    AUTHORITY: the WRONG estimator whose bias is Clauset-Shalizi-Newman (2009)
    Section 3's central critique — NOT E&K. Fits a straight line to
    ``log10(pmf)`` vs ``log10(k)`` over ``k >= k_min`` by ORDINARY least squares,
    EVERY non-empty bin weighted EQUALLY, empty bins dropped; returns ``-slope``.

    >>> the equal weighting and the empty-bin dropping ARE THE BUG, and they must
    NOT be "fixed": on a finite sample the sparse, high-variance tail bins each
    get a full equal vote, so the fit diverges catastrophically as ``k_min`` rises
    (C3 Figure B: 1.93 at k_min=5 -> 0.88 at k_min=50 on the committed sample).
    That divergence is exactly ws1 P9's point; deleting it deletes the lesson. <<<

    ``counts`` is ``{k: count}`` (or ``(k, count)`` pairs). Needs >= 2 non-empty
    bins with ``k >= k_min``.
    """
    xs, ys = [], []
    total = sum(w for _, w in _count_items(counts))
    for k, c in _count_items(counts):
        if k >= k_min and c > 0 and k > 0:
            xs.append(math.log10(k))
            ys.append(math.log10(c / total))
    if len(xs) < 2:
        raise ValueError(f"alpha_naive_lsq: need >= 2 non-empty bins with "
                         f"k >= k_min={k_min}, got {len(xs)}.")
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return -(sxy / sxx)


def alpha_mle(counts, k_min):
    """The Hill / maximum-likelihood power-law exponent estimator (discrete approx).

    AUTHORITY: Clauset-Shalizi-Newman (2009) Eq. 3.7 — the discrete MLE with the
    ``k_min - 1/2`` continuity correction:

        alpha = 1 + W / SUM_{k >= k_min} w_k * ln( k / (k_min - 1/2) ),
        W = SUM_{k >= k_min} w_k.

    Works identically on integer sample COUNTS and on exact pmf WEIGHTS (the sum
    is the population expectation in the latter), which is the discriminator C3
    uses: applied to BOTH ``ek_stationary_indegree`` (exact) and
    ``ek_copy_indegree_counts`` (sample) it reads the SAME 2.57 at ``k_min = 5``,
    proving that number is a CURVATURE property, not sampling bias.

    UNCORRECTED at ``k_min = 5`` on purpose (reads 2.57 vs truth 3.0); raising
    ``k_min`` toward the tail converges it to 3.0 — "fit the tail, not the body".
    ``counts`` is ``{k: weight}`` (or pairs); needs mass at ``k >= k_min`` and
    ``k_min >= 1``.
    """
    if k_min < 1:
        raise ValueError(f"alpha_mle: k_min must be >= 1, got {k_min!r}.")
    w_sum = 0.0
    s = 0.0
    for k, w in _count_items(counts):
        if k >= k_min and w > 0:
            w_sum += w
            s += w * math.log(k / (k_min - 0.5))
    if w_sum <= 0 or s <= 0:
        raise ValueError(f"alpha_mle: no positive mass at k >= k_min={k_min}.")
    return 1.0 + w_sum / s


#: C3 Figure B's committed frozen sample: the file, its generator parameters, and
#: the sha256 of the canonical count-table. The reproducibility test regenerates
#: ``ek_copy_indegree_counts(**params)`` and asserts the sha256 matches — proving
#: the committed data is a faithful, byte-reproducible (local == container) frozen
#: sample, not a hand-edited blob. Change the params -> the sha256 must be
#: re-derived, which is a reviewable diff (never silently drifted).
C3_FROZEN_SAMPLE = {
    "file": "ek_copy_indegree_p50_seed7_n400000.json",
    "params": {"n": 400000, "p": 0.5, "seed": 7, "m0": 2},
    "sha256": "fbf639eef4c67073c755a1d25858ce9bc52728b225dbab002802006477213d0c",
}


def frozen_c3_indegree_counts():
    """Load C3 Figure B's committed in-degree histogram ``{k: node_count}``.

    The figure reads THIS committed table (no live sampler at render time — L9
    decision Q2). Its identity is pinned by ``C3_FROZEN_SAMPLE`` and verified by
    the reproducibility test, which regenerates it from
    ``ek_copy_indegree_counts`` and checks the sha256. Ships as package data.
    """
    import json
    from importlib import resources

    ref = resources.files("cs470_engine").joinpath("data",
                                                    C3_FROZEN_SAMPLE["file"])
    with ref.open("r") as f:
        doc = json.load(f)
    return {int(k): v for k, v in doc["counts"].items()}


def _c3_count_table_sha256(counts):
    """sha256 of a ``{k: count}`` histogram in the committed canonical form
    (string keys, sorted, compact JSON). The single source of truth for the
    ``C3_FROZEN_SAMPLE`` identity — used by both the generator's data file and
    the reproducibility test, so they cannot compute it two different ways."""
    import hashlib
    import json

    table = {str(k): v for k, v in counts.items()}
    blob = json.dumps(table, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


# -----------------------------------------------------------------------------

def _check_prob(p, name):
    if not (isinstance(p, (int, float)) and 0.0 <= p <= 1.0):
        raise ValueError(f"{name} must be a probability in [0, 1], got {p!r}.")
