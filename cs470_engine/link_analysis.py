"""Link analysis — HITS, PageRank, SCC and the bow-tie (Easley & Kleinberg Ch.13-14).

The compute helpers behind every Lesson-6 figure. They exist so that a score
written on a node is COMPUTED, never a literal typed into YAML that can silently
drift from the answer key — the same anti-drift discipline the Lesson-4 matching
helpers established.

⚠️ DO NOT REPLACE THESE WITH ``nx.pagerank`` / ``nx.hits``. They implement a
DIFFERENT RULE and will produce confidently wrong keys:

* ``nx.pagerank`` implements only the SCALED (damped) rule, and it redistributes
  a dangling node's mass UNIFORMLY over all nodes. E&K's **Basic** rule has no
  damping at all, and a dangling page "passes all its current PageRank to
  itself" (§14.3, verbatim) — a self-loop, not a uniform spray. Different rule,
  different numbers.
* Worse, E&K's Basic rule **does not always converge**. On the 3-node graph
  (A⇄B, C→A) it oscillates with period 2 forever, so no limiting vector exists —
  and ``nx.pagerank`` cannot express that. It would return the stationary vector
  (1/2, 1/2, 0), which the iteration provably never approaches. That
  non-convergence is the pedagogy (it is the flagship worksheet problem), so the
  helper has to be able to REPORT it rather than paper over it.
* ``nx.hits`` uses its own normalization and will not reproduce the per-step hub
  and authority vectors the worksheets tabulate.

WHY EVERY VALUE IS A ``Fraction``
---------------------------------
Exact rational arithmetic, never float. Three things fall out of that, and the
third is the one that matters:

1. The chapter's worked values reproduce EXACTLY — 1/8, 5/16, 4/13, 3/7 — rather
   than as 0.3076923076923077. The worksheets print these fractions to students.
2. Conservation (Σ PageRank == 1) holds exactly at every step, so it can be
   ASSERTED rather than checked against a tolerance.
3. **Oscillation becomes provable.** Period-2 cycling is detected by exact vector
   EQUALITY against the orbit's history — not by watching a float residual fail
   to shrink below some epsilon. With floats, "it oscillates" and "it converges
   slowly" are the same observation; with Fractions they are distinguishable, and
   the distinction is precisely what the flagship problem teaches.
"""

from fractions import Fraction

__all__ = [
    "adjacency_matrix",
    "flow_matrix",
    "scaled_flow_matrix",
    "hits_iterations",
    "hits_limit",
    "pagerank_iterations",
    "pagerank_limit",
    "pagerank_equilibrium",
    "is_pagerank_equilibrium",
    "strongly_connected_components",
    "giant_scc",
    "bowtie_partition",
    "PageRankLimit",
    "BOWTIE_ROLES",
]


# -----------------------------------------------------------------------------
# Shared plumbing
# -----------------------------------------------------------------------------

def _node_list(G, nodes=None):
    """The canonical node ORDER for every matrix and vector this module returns.

    Defaults to the graph's own insertion order (which is the order the figure's
    YAML lists its nodes), so a rendered matrix's rows line up with the figure's
    node labels. An explicit ``nodes`` overrides it.
    """
    order = list(G.nodes()) if nodes is None else list(nodes)
    missing = [n for n in order if n not in G]
    if missing:
        raise ValueError(f"nodes not in graph: {missing}")
    return order


def _as_fraction(x):
    """Exact Fraction from an int / Fraction / 'p/q' string / float."""
    if isinstance(x, Fraction):
        return x
    if isinstance(x, str):
        return Fraction(x)
    if isinstance(x, float):
        return Fraction(x).limit_denominator(10 ** 6)
    return Fraction(x)


def _normalize(vec):
    """Scale a value-dict to sum 1. An all-zero vector is returned unchanged
    (dividing by zero is what a naive implementation does here; HITS on a node
    with no in-links legitimately produces an all-zero authority column)."""
    total = sum(vec.values())
    if total == 0:
        return dict(vec)
    return {n: v / total for n, v in vec.items()}


def _initial_vector(order, initial, default):
    """The vector an iteration STARTS from — ``initial`` if given, else ``default``
    on every node.

    ONE implementation, shared by HITS and PageRank, because the two used to differ
    for no reason: ``pagerank_iterations`` took an ``initial=`` and
    ``hits_iterations`` did not. That asymmetry was not a design decision, it was an
    omission, and it blocked the one thing worth showing about HITS — that the scores
    converge to the SAME limit no matter where you start them (see
    :func:`hits_limit`). Sharing the resolution here means the two helpers cannot
    drift apart again on the shape of their argument or on its validation.

    Values are coerced to exact ``Fraction``s, so a caller may pass ints, floats,
    ``'p/q'`` strings or Fractions and still get exact arithmetic downstream.
    """
    if initial is None:
        return {n: default for n in order}
    missing = [n for n in order if n not in initial]
    if missing:
        raise ValueError(
            f"initial: no starting value for {missing}. The iteration is defined on "
            f"every node, so supply one entry per node — or omit `initial` "
            f"entirely to start from the default.")
    return {n: _as_fraction(initial[n]) for n in order}


# -----------------------------------------------------------------------------
# Matrices (R4's data source)
# -----------------------------------------------------------------------------

def adjacency_matrix(G, nodes=None):
    """The HITS adjacency matrix **M**: ``M[i][j] = 1`` iff i → j (0 otherwise).

    Row *i* = FROM, column *j* = TO — E&K's convention (Fig 14.11/14.12), the one
    under which the hub update is ``h = M a`` and the authority update is
    ``a = Mᵀ h``. Hubs look ALONG a row (out-links); authorities look DOWN a
    column (in-links).
    """
    order = _node_list(G, nodes)
    return [[1 if G.has_edge(u, v) else 0 for v in order] for u in order]


def flow_matrix(G, nodes=None):
    """The Basic-PageRank flow matrix **N**: ``N[i][j]`` = the share of i's
    PageRank that flows to j — ``1/outdeg(i)`` when i → j, else 0.

    A DANGLING node (out-degree 0) gets ``N[i][i] = 1``: E&K's rule is that such
    a page "passes all its current PageRank to itself". This is the single
    convention on which the engine departs from ``nx.pagerank``, which would
    instead spray i's mass uniformly over every node. One Basic update is
    ``r' = Nᵀ r``.
    """
    order = _node_list(G, nodes)
    idx = {n: i for i, n in enumerate(order)}
    M = [[Fraction(0)] * len(order) for _ in order]
    for u in order:
        succ = [v for v in G.successors(u) if v in idx]
        if not succ:
            M[idx[u]][idx[u]] = Fraction(1)      # dangling: all of it, to itself
            continue
        share = Fraction(1, len(succ))
        for v in succ:
            M[idx[u]][idx[v]] = share
    return M


def scaled_flow_matrix(G, nodes=None, s=Fraction(4, 5)):
    """The Scaled-PageRank matrix **Ñ** = ``s·N + (1-s)/n`` in every entry.

    Every entry is STRICTLY POSITIVE (the ``(1-s)/n`` term guarantees it), which
    is exactly what lets Perron's theorem apply to Ñ where it cannot apply to N.
    Note Ñ is NOT symmetric — the HITS convergence proof leans on symmetry and
    therefore cannot be reused here, which is why the chapter reaches for Perron.
    """
    s = _as_fraction(s)
    order = _node_list(G, nodes)
    n = len(order)
    if n == 0:
        return []
    N = flow_matrix(G, order)
    teleport = (1 - s) / n
    return [[s * N[i][j] + teleport for j in range(n)] for i in range(n)]


# -----------------------------------------------------------------------------
# HITS  (E&K §14.2)
# -----------------------------------------------------------------------------

def hits_iterations(G, steps=1, nodes=None, normalize=True, initial=None):
    """Run k hub-authority updates; return the state after EACH one.

    E&K's rule, verbatim: all hub and authority scores start at 1; each update
    applies the **Authority Update Rule** first — ``auth(p)`` becomes the sum of
    the hub scores of the pages that point to p — and then the **Hub Update
    Rule** to the *resulting* scores: ``hub(p)`` becomes the sum of the authority
    scores of the pages p points to.

    Returns ``[state_0, state_1, ... state_k]``, where ``state_0`` is the
    initialization and each later state is a dict::

        {"authority": {node: Fraction}, "hub": {node: Fraction},
         "authority_raw": {...}, "hub_raw": {...}}

    ``normalize=True`` (the default) divides each vector down by its own sum
    after each sub-step — the convention the worksheets use, and the one that
    keeps the numbers small enough to print. The chapter instead normalizes once
    at the very end. **Both give identical normalized answers**: the updates are
    linear, so an intermediate positive rescale cancels out. Only the
    *unnormalized* intermediates differ, and those are kept in the ``_raw`` keys.

    ``initial`` — a ``{node: value}`` starting vector, defaulting to the chapter's
    all-ones. Same shape and same coercion as ``pagerank_iterations``' ``initial``
    (they share :func:`_initial_vector`); omit it and the output is exactly what it
    was before this parameter existed.

    ⚠️ ``initial`` SETS THE STARTING **HUB** SCORES, and the starting authority
    scores are cosmetic. Look at the loop: the first thing an update does is
    recompute every authority from the hub scores, so whatever authorities the
    iteration started with are overwritten before they are ever read. ``state_0``
    reports them anyway (it reports what you passed in, exactly as it always
    reported the all-ones), but they do not influence a single number after it.
    This is not a quirk of the implementation — it is why the *pedagogy* works: the
    hub vector is the only thing you can perturb, and perturbing it still lands on
    the same limit (:func:`hits_limit`).
    """
    order = _node_list(G, nodes)
    start = _initial_vector(order, initial, Fraction(1))
    hub = dict(start)
    auth = dict(start)
    out = [{"authority": dict(auth), "hub": dict(hub),
            "authority_raw": dict(auth), "hub_raw": dict(hub)}]

    for _ in range(steps):
        # Authority Update Rule — sum the hub scores of the pages pointing to p.
        auth_raw = {p: sum((hub[q] for q in G.predecessors(p)), Fraction(0))
                    for p in order}
        auth = _normalize(auth_raw) if normalize else auth_raw
        # Hub Update Rule — sum the authority scores of the pages p points to,
        # using the authorities JUST computed ("apply to the resulting scores").
        hub_raw = {p: sum((auth[q] for q in G.successors(p)), Fraction(0))
                   for p in order}
        hub = _normalize(hub_raw) if normalize else hub_raw
        out.append({"authority": dict(auth), "hub": dict(hub),
                    "authority_raw": dict(auth_raw), "hub_raw": dict(hub_raw)})
    return out


def hits_limit(G, nodes=None, max_iter=200, initial=None):
    """The normalized hub/authority vectors HITS settles on.

    Iterates until the normalized vectors stop moving (exact equality — the
    scores are Fractions, so "stopped" is a fact, not a tolerance). Returns the
    final ``{"authority": ..., "hub": ...}`` state.

    Unlike Basic PageRank, this always settles for the graphs in scope: the
    normalized HITS iteration is the power method on the symmetric PSD matrices
    MᵀM and MMᵀ. It can still be *periodic* on adversarial bipartite-like graphs,
    so the loop is bounded and simply returns the last state if it never repeats.

    ``initial`` — the starting vector (see :func:`hits_iterations`). **THE LIMIT
    DOES NOT DEPEND ON IT**, for any start that is positive somewhere: the iteration
    is the power method, so it converges on the dominant eigenvector of MMᵀ / MᵀM
    whatever it set out from, and the starting vector decides only how many rounds
    that takes. That claim is the entire point of the parameter — a worksheet can
    now *demonstrate* it rather than assert it.

    ⚠️ WHAT THIS FUNCTION RETURNS IS AN APPROXIMATION, AND IT HAS TO BE. Unlike
    :func:`pagerank_equilibrium`, whose stationary vector is the exact rational
    solution of a linear system, the HITS limit is an EIGENVECTOR — and it is
    generally IRRATIONAL. On Fig 14.15 the limiting authority of page C is exactly
    ``sqrt(2) - 1``, which no ``Fraction`` can hold. So the iteration never lands on
    a fixed point, the "have the vectors stopped moving?" test above never fires on
    a real graph, and this returns the state after ``max_iter`` rounds: a rational
    approximation whose residual shrinks geometrically with ``max_iter``.

    The practical consequence for a caller: **two runs from different starting
    vectors do not come back byte-equal.** They come back agreeing to within that
    residual — about 1e-153 at the default ``max_iter``, and demonstrably shrinking
    as ``max_iter`` grows (10 -> 4.8e-8, 20 -> 1.1e-15, 40 -> 5.2e-31, 80 ->
    1.2e-61). Compare limits with a tolerance, never with ``==``. Both facts are
    pinned by ``test_a_skewed_start_converges_to_the_SAME_limit``.

    (A start that is zero everywhere is the degenerate exception: there is no signal
    to amplify, zeros stay zero, and the power method promises nothing.)
    """
    order = _node_list(G, nodes)
    prev = None
    for st in hits_iterations(G, max_iter, nodes=order, normalize=True,
                              initial=initial)[1:]:
        cur = (tuple(st["authority"][n] for n in order),
               tuple(st["hub"][n] for n in order))
        if cur == prev:
            return {"authority": st["authority"], "hub": st["hub"]}
        prev = cur
        last = st
    return {"authority": last["authority"], "hub": last["hub"]}


# -----------------------------------------------------------------------------
# PageRank  (E&K §14.3)
# -----------------------------------------------------------------------------

class PageRankLimit:
    """What the PageRank iteration DOES in the limit — which may be "not settle".

    WHY THIS IS AN OBJECT AND NOT A VECTOR
    --------------------------------------
    The honest answer to "what is the limiting PageRank?" is sometimes *there
    isn't one*. On (A⇄B, C→A) under the Basic rule the values swap forever with
    period 2. A helper that returns a plain vector cannot say that, and would
    have to either invent a limit or raise — and RAISING IS WRONG HERE, because
    non-convergence is not an error condition, it is the correct answer to the
    worksheet's best question. So the return type carries the finding:

    ``converged``  — did the iteration reach a fixed point?
    ``limit``      — the limiting vector, or ``None`` when it does not converge.
    ``period``     — the length of the cycle the orbit falls into: ``1`` == a
                     fixed point == converged; ``2`` == the A⇄B swap; ``0`` ==
                     no exact cycle, and the run hit ``max_iter`` still moving.
    ``cycle``      — the vectors the orbit cycles through, in order, when
                     ``period > 1``; ``None`` otherwise. This is what a figure
                     draws to SHOW the oscillation.
    ``iterations`` — every state from r⁰ onward, so a worksheet can tabulate the
                     walk to the limit instead of only reporting its end.
    ``reason``     — a short human-readable account, for the answer key.

    ⚠️ ``period`` IS THE FIELD THAT SEPARATES THE TWO WAYS OF NOT CONVERGING, and
    they are not the same finding. ``period >= 2`` is a PROOF of oscillation —
    the orbit closed on itself, exactly, and no limit exists. ``period == 0``
    means only that the iteration was still moving when the budget ran out; the
    graph may well converge, just slowly (Fig 14.6 needs ~213 updates to settle
    to 1e-12, so a max_iter of 200 would report ``period == 0`` on a graph that
    converges perfectly well). Never read ``converged == False`` alone as
    "it oscillates" — check ``period``.

    Truthiness follows ``converged``, so ``if pagerank_limit(G):`` reads the way
    it should — a non-converging run is falsy.
    """

    def __init__(self, converged, limit, period, cycle, iterations, reason):
        self.converged = converged
        self.limit = limit
        self.period = period
        self.cycle = cycle
        self.iterations = iterations
        self.reason = reason

    def __bool__(self):
        return bool(self.converged)

    def __repr__(self):
        if self.converged:
            return f"<PageRankLimit converged limit={self.limit!r}>"
        return (f"<PageRankLimit NOT converged period={self.period} "
                f"reason={self.reason!r}>")


def _pagerank_step(r, N, order):
    """One update: ``r' = Nᵀ r``. N already encodes the rule (basic or scaled)."""
    idx = {n: i for i, n in enumerate(order)}
    return {v: sum((r[u] * N[idx[u]][idx[v]] for u in order), Fraction(0))
            for v in order}


def pagerank_iterations(G, steps=1, nodes=None, rule="basic", s=Fraction(4, 5),
                        initial=None):
    """Run k PageRank updates; return the vector after EACH one.

    ``rule="basic"``  — E&K's Basic rule. Each page divides its PageRank equally
    across its out-links; a page with no out-links passes all of it to itself.
    Total PageRank is conserved exactly (no renormalization — unlike HITS).

    ``rule="scaled"`` — E&K's Scaled rule: apply the Basic rule, scale everything
    by ``s``, then divide the residual ``1-s`` equally over all n nodes
    (``(1-s)/n`` each). Also exactly conservative, and every node is floored at
    ``(1-s)/n``.

    Returns ``[r0, r1, ..., rk]`` of ``{node: Fraction}``. ``r0`` is uniform
    ``1/n`` unless ``initial`` is given.
    """
    if rule not in ("basic", "scaled"):
        raise ValueError(f"rule must be 'basic' or 'scaled', got {rule!r}")
    order = _node_list(G, nodes)
    n = len(order)
    if n == 0:
        return [{}]

    N = (flow_matrix(G, order) if rule == "basic"
         else scaled_flow_matrix(G, order, s))

    r = _initial_vector(order, initial, Fraction(1, n))

    out = [dict(r)]
    for _ in range(steps):
        r = _pagerank_step(r, N, order)
        out.append(dict(r))
    return out


def pagerank_limit(G, nodes=None, rule="basic", s=Fraction(4, 5), max_iter=1000,
                   initial=None, tol=Fraction(1, 10 ** 12)):
    """What the PageRank iteration converges to — or that it DOESN'T.

    Returns a :class:`PageRankLimit`. See that class for why the answer is an
    object rather than a vector, and why ``period`` (not ``converged``) is what
    tells oscillation apart from mere slowness.

    HOW OSCILLATION IS DETECTED — exactly, not by tolerance. Every iterate is a
    vector of Fractions, so the orbit's history can be kept in a dict and each
    new iterate looked up in it. A repeat means the orbit has closed into a cycle
    of length ``k - first_seen``:

    * period 1 — the iterate maps to itself: a genuine fixed point. Converged.
    * period > 1 — the orbit cycles forever and NO limit exists. On (A⇄B, C→A)
      this fires at k=3 with period 2, and it is a PROOF, not an estimate: the
      Fractions are exact, so r³ == r¹ is an identity. (A stationary vector does
      still exist there — (1/2, 1/2, 0) — but the iteration provably never
      approaches it, which is exactly the distinction ``nx.pagerank`` erases by
      reporting the stationary vector as though it were the limit.)

    Floats could not do this. A float residual that stops shrinking is equally
    consistent with "oscillating" and "converging too slowly to see", so the
    flagship finding would be a judgment call. Exact rationals make it a fact.

    HOW CONVERGENCE IS DETECTED. A graph whose iterates approach a limit without
    ever landing on it exactly (Fig 14.6 approaches 4/13 asymptotically and never
    repeats) would spin forever under cycle detection alone. So the orbit is also
    compared each step against the EXACT stationary vector from
    :func:`pagerank_equilibrium`, and declared converged once it is within
    ``tol``. The reported ``limit`` is then that exact stationary vector — 4/13,
    not a 40-digit decimal approaching it.

    ``max_iter`` is a BUDGET, not a verdict. Fig 14.6 takes ~213 updates to reach
    the default 1e-12, so a stingy cap would report ``period == 0`` on a graph
    that converges fine. Exhausting the budget yields ``converged=False`` with
    ``period == 0`` and a ``reason`` that says so — never a claim of oscillation.
    """
    order = _node_list(G, nodes)
    n = len(order)
    if n == 0:
        return PageRankLimit(True, {}, 1, None, [{}], "empty graph")

    N = (flow_matrix(G, order) if rule == "basic"
         else scaled_flow_matrix(G, order, s))
    r = _initial_vector(order, initial, Fraction(1, n))

    def key(vec):
        return tuple(vec[node] for node in order)

    seen = {key(r): 0}
    iters = [dict(r)]
    fixed = pagerank_equilibrium(G, nodes=order, rule=rule, s=s)

    for step in range(1, max_iter + 1):
        r = _pagerank_step(r, N, order)
        iters.append(dict(r))
        k = key(r)

        if k in seen:
            start = seen[k]
            period = step - start
            if period == 1:
                return PageRankLimit(
                    True, dict(r), 1, None, iters,
                    f"reached an exact fixed point after {start} update(s)")
            cycle = iters[start:step]
            return PageRankLimit(
                False, None, period, cycle, iters,
                f"the values cycle with period {period} and never converge — "
                f"r^{step} is exactly r^{start}")
        seen[k] = step

        # Asymptotic approach (never an exact repeat): settle against the exact
        # stationary vector rather than against the previous iterate, so the
        # limit reported is 4/13 and not a 40-digit approximation of it.
        if fixed is not None:
            gap = sum(abs(r[node] - fixed[node]) for node in order)
            if gap < tol:
                return PageRankLimit(
                    True, dict(fixed), 1, None, iters,
                    f"converged to the stationary vector (within 1e-12 after "
                    f"{step} updates)")

    return PageRankLimit(
        False, None, 0, None, iters,
        f"still moving after {max_iter} updates, with no exact cycle — this is "
        f"a spent budget, NOT a proof of oscillation (period is 0, not >= 2); "
        f"raise max_iter or loosen tol if the graph merely converges slowly")


def pagerank_equilibrium(G, nodes=None, rule="basic", s=Fraction(4, 5)):
    """The EXACT stationary vector: the r with ``r = Nᵀ r`` and ``Σr = 1``.

    Solved as a linear system over the rationals by Gaussian elimination with
    Fraction pivots — so the 8-node example's equilibrium comes back as exactly
    (4/13, 2/13, 2/13, 1/13, 1/13, 1/13, 1/13, 1/13), not a float near it.

    Returns ``None`` when no unique stationary vector exists (the system is
    rank-deficient — e.g. a graph with two separate closed sinks, where every
    convex combination of their indicators is stationary).

    ⚠️ A stationary vector EXISTING does not mean the iteration REACHES it. On
    (A⇄B, C→A) this returns (1/2, 1/2, 0) while the Basic iteration oscillates
    forever and never approaches it. Use :func:`pagerank_limit` to ask what the
    iteration actually does; use this to ask what would be self-reproducing.
    """
    order = _node_list(G, nodes)
    n = len(order)
    if n == 0:
        return {}
    N = (flow_matrix(G, order) if rule == "basic"
         else scaled_flow_matrix(G, order, s))

    # (Nᵀ - I) r = 0, with the last row replaced by Σr = 1 to pin the scale.
    A = [[(N[j][i] if i != j else N[j][i] - 1) for j in range(n)]
         for i in range(n)]
    A[-1] = [Fraction(1)] * n
    b = [Fraction(0)] * n
    b[-1] = Fraction(1)

    # Gaussian elimination, exact.
    for col in range(n):
        piv = next((r for r in range(col, n) if A[r][col] != 0), None)
        if piv is None:
            return None                      # singular: no unique stationary r
        A[col], A[piv] = A[piv], A[col]
        b[col], b[piv] = b[piv], b[col]
        inv = A[col][col]
        A[col] = [x / inv for x in A[col]]
        b[col] = b[col] / inv
        for r in range(n):
            if r == col or A[r][col] == 0:
                continue
            f = A[r][col]
            A[r] = [x - f * y for x, y in zip(A[r], A[col])]
            b[r] = b[r] - f * b[col]

    return {order[i]: b[i] for i in range(n)}


def is_pagerank_equilibrium(G, r, nodes=None, rule="basic", s=Fraction(4, 5)):
    """Is ``r`` an equilibrium — the TWO-PART check the chapter specifies?

    It must (a) sum to 1 and (b) be unchanged by one update. Students reliably
    check only one of the two, so both are enforced here and neither is folded
    into the other.
    """
    order = _node_list(G, nodes)
    vec = {node: _as_fraction(r[node]) for node in order}
    if sum(vec.values()) != 1:
        return False
    N = (flow_matrix(G, order) if rule == "basic"
         else scaled_flow_matrix(G, order, s))
    return _pagerank_step(vec, N, order) == vec


# -----------------------------------------------------------------------------
# Strong connectivity and the bow-tie  (E&K §13.3-13.4)
# -----------------------------------------------------------------------------

#: The bow-tie roles, in the order a legend should list them (E&K Fig 13.7).
BOWTIE_ROLES = ("IN", "SCC", "OUT", "TENDRIL", "TUBE", "DISCONNECTED")


def _reachable(G, sources, reverse=False):
    """Every node reachable from ``sources`` (following edges backward if
    ``reverse``). Plain BFS — kept explicit because reachability IS the
    definition being taught."""
    step = (G.predecessors if reverse else G.successors)
    seen = set(sources)
    stack = list(sources)
    while stack:
        for nxt in step(stack.pop()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def strongly_connected_components(G):
    """The SCCs, largest first — computed straight from E&K's definition.

    A node's SCC is ``{u : v reaches u AND u reaches v}``. Grouping by that set
    yields components that are maximal BY CONSTRUCTION, which is the part of the
    definition students drop: ``{Univ of X, Classes, Networks, I teach at...}``
    in Fig 13.5 is mutually reachable (part i) but is NOT an SCC, because it sits
    inside a strictly larger mutually-reachable set (part ii). Implementing the
    definition literally, rather than reaching for Tarjan, is what makes that
    property self-evident here — and the test cross-checks the result against
    networkx's Tarjan implementation, so nothing is lost by the choice.

    A lone node with no cycle IS an SCC (of size 1) — the other thing students
    drop, and the reason Fig 13.5 has six SCCs rather than two.
    """
    comps = {}
    for v in G.nodes():
        fwd = _reachable(G, [v])
        back = _reachable(G, [v], reverse=True)
        comp = frozenset(fwd & back)          # always contains v itself
        comps.setdefault(comp, None)
    # Largest first; ties broken by the node order in the graph, so the output
    # is deterministic (a figure's component colors must not shuffle per run).
    order = {n: i for i, n in enumerate(G.nodes())}
    return sorted((set(c) for c in comps),
                  key=lambda c: (-len(c), min(order[n] for n in c)))


def giant_scc(G):
    """The largest strongly connected component (the bow-tie's knot)."""
    comps = strongly_connected_components(G)
    return comps[0] if comps else set()


def bowtie_partition(G, core=None):
    """Classify every node into its bow-tie role. Returns ``{node: role}``.

    Roles, per E&K §13.4, relative to the giant SCC:

    * ``SCC``          — in the giant strongly connected component.
    * ``IN``           — can reach the SCC, but is not reachable FROM it.
    * ``OUT``          — reachable from the SCC, but cannot reach it.
    * ``TUBE``         — reachable from IN and reaches OUT, but bypasses the SCC.
    * ``TENDRIL``      — hangs off IN (reachable from IN, reaches neither the SCC
                         nor OUT) or off OUT (reaches OUT, reachable from neither
                         the SCC nor IN).
    * ``DISCONNECTED`` — touches none of the above.

    ⚠️ OUT means reachable-from-the-SCC **with no path back**. Being pointed AT by
    an SCC node is not sufficient, and that is the trap: in the 13-node worksheet
    graph, node 7 points to 8, so 8 *looks* downstream — but 8→9→7 returns, so 8
    is squarely inside the SCC. (The source worksheet's own key gets this wrong,
    listing 8 and 9 in both the SCC and the downstream set.) The implementation
    cannot make that mistake because it asks for reachability in BOTH directions.
    """
    nodes = set(G.nodes())
    if not nodes:
        return {}
    scc = set(core) if core is not None else giant_scc(G)
    if not scc:
        return {n: "DISCONNECTED" for n in nodes}

    from_scc = _reachable(G, scc)              # SCC ∪ everything downstream
    to_scc = _reachable(G, scc, reverse=True)  # SCC ∪ everything upstream

    IN = to_scc - scc
    OUT = from_scc - scc
    rest = nodes - scc - IN - OUT

    from_in = _reachable(G, IN) - IN if IN else set()
    to_out = _reachable(G, OUT, reverse=True) - OUT if OUT else set()

    # Iterate G.nodes(), NOT the `nodes` set. Set iteration order over strings
    # varies with Python's per-process hash seed, so a set here would give the
    # returned dict a different KEY ORDER on every kernel start — and a figure
    # that colors nodes by group assigns its palette in group-first-appearance
    # order. The colors would therefore be stable within one session and
    # different in the next, which is about the worst kind of bug to debug from
    # a screenshot. Insertion order is the figure's own node order; it is stable.
    roles = {}
    for n in G.nodes():
        if n in scc:
            roles[n] = "SCC"
        elif n in IN:
            roles[n] = "IN"
        elif n in OUT:
            roles[n] = "OUT"
        elif n in rest and n in from_in and n in to_out:
            roles[n] = "TUBE"          # IN -> ... -> OUT, bypassing the SCC
        elif n in rest and (n in from_in or n in to_out):
            roles[n] = "TENDRIL"
        else:
            roles[n] = "DISCONNECTED"
    return roles
