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
    theorem). Computed EXACTLY (``math.exp`` / ``math.factorial``), not sampled.

    ``k < 0`` has mass 0. ``lam`` must be ``>= 0`` else ``ValueError``.
    """
    if lam < 0:
        raise ValueError(f"poisson_pmf: lam must be >= 0, got {lam!r}.")
    if k < 0:
        return 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


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

def _check_prob(p, name):
    if not (isinstance(p, (int, float)) and 0.0 <= p <= 1.0):
        raise ValueError(f"{name} must be a probability in [0, 1], got {p!r}.")
