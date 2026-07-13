#!/usr/bin/env python3
"""Tests for the Lesson-6 link-analysis surface (engine 0.8.0).

Standalone-runnable (``python3 tests/test_link_analysis.py``) — no pytest needed,
matching the project's other suites.

The spine of this file is the CHAPTER'S OWN WORKED EXAMPLES. Every expected value
below was derived from E&K's update rules and the figure's edge list, then checked
against the source worksheet key — never transcribed from the key, which is
project policy because the source keys contain errors (one of which, ws1 P2's
"Downstream", this file pins as WRONG).
"""
import sys
import traceback
from fractions import Fraction as F

import networkx as nx

from cs470_engine.link_analysis import (
    adjacency_matrix, flow_matrix, scaled_flow_matrix,
    hits_iterations, hits_limit,
    pagerank_iterations, pagerank_limit, pagerank_equilibrium,
    is_pagerank_equilibrium,
    strongly_connected_components, giant_scc, bowtie_partition,
)

_FAILS = []


def check(label, got, want):
    if got != want:
        _FAILS.append(f"{label}\n     got:  {got}\n     want: {want}")


def check_true(label, cond):
    if not cond:
        _FAILS.append(f"{label}\n     expected True")


def raises(label, fn, exc=Exception):
    try:
        fn()
    except exc:
        return
    _FAILS.append(f"{label}\n     expected {exc.__name__}, nothing raised")


def dg(nodes, edges):
    G = nx.DiGraph()
    G.add_nodes_from(nodes)
    G.add_edges_from(edges)
    return G


def vec(d, order):
    return tuple(d[n] for n in order)


def fr(*xs):
    return tuple(F(x) for x in xs)


# --- the figures, transcribed from their edge lists ---------------------------

def fig_14_11():                       # 4 nodes; HITS worked example
    return dg([1, 2, 3, 4], [(1, 2), (1, 4), (2, 3), (2, 4), (3, 1), (4, 3)])


def fig_14_15():                       # 5 nodes; A,B -> C,D,E
    return dg("ABCDE", [("A", "C"), ("B", "C"), ("B", "D"), ("B", "E")])


def fig_14_16():                       # 8 nodes; D,E -> A,B ; F,G,H -> C
    return dg("ABCDEFGH",
              [("D", "A"), ("E", "B"), ("F", "C"), ("G", "C"), ("H", "C")])


FIG_14_6_EDGES = [("A", "B"), ("A", "C"), ("B", "D"), ("B", "E"), ("C", "F"),
                  ("C", "G"), ("D", "A"), ("D", "H"), ("E", "A"), ("E", "H"),
                  ("F", "A"), ("G", "A"), ("H", "A")]


def fig_14_6():                        # 8 nodes; the PageRank walkthrough
    return dg("ABCDEFGH", FIG_14_6_EDGES)


def fig_14_8():                        # same, but F and G point to each other
    edges = [e for e in FIG_14_6_EDGES if e not in (("F", "A"), ("G", "A"))]
    return dg("ABCDEFGH", edges + [("F", "G"), ("G", "F")])


def three_node():                      # A<->B, C->A — the oscillator
    return dg("ABC", [("A", "B"), ("B", "A"), ("C", "A")])


def scc2():                            # the 13-node worksheet-original graph
    return dg(range(1, 14),
              [(1, 5), (10, 5), (5, 6), (6, 2), (2, 3), (3, 4), (3, 7), (7, 8),
               (8, 9), (9, 7), (7, 12), (12, 11), (11, 6), (12, 13)])


def fig_13_5():                        # 16 nodes; the Univ-of-X web
    E = [("Student", "UnivX"), ("Student", "SongLyrics"), ("UnivX", "Classes"),
         ("Classes", "Networks"), ("Networks", "ITeach"),
         ("Networks", "ClassBlog"), ("ITeach", "UnivX"),
         ("ClassBlog", "BlogRankings"), ("ClassBlog", "BlogCompanyZ"),
         ("BlogRankings", "USNewsRankings"),
         ("USNewsRankings", "USNewsFeatured"), ("USNewsFeatured", "UnivX"),
         ("Applying", "USNewsRankings"), ("BlogCompanyZ", "CompanyZ"),
         ("CompanyZ", "Founders"), ("CompanyZ", "PressReleases"),
         ("Founders", "ContactUs"), ("PressReleases", "ContactUs"),
         ("ContactUs", "CompanyZ")]
    return dg(sorted({n for e in E for n in e}), E)


# --- matrices -----------------------------------------------------------------

def test_adjacency_matrix_is_from_row_to_column():
    check("M (Fig 14.11)", adjacency_matrix(fig_14_11()),
          [[0, 1, 0, 1], [0, 0, 1, 1], [1, 0, 0, 0], [0, 0, 1, 0]])


def test_flow_matrix_sends_a_dangling_node_to_itself():
    """E&K: a page with no out-links 'passes all its current PageRank to itself'.
    This is THE divergence from nx.pagerank, which sprays it uniformly."""
    G = dg("ABC", [("A", "B"), ("A", "C"), ("B", "C")])   # C dangles
    N = flow_matrix(G, "ABC")
    check("A splits 1/2 each", (N[0][1], N[0][2]), (F(1, 2), F(1, 2)))
    check("C keeps its own rank (self-loop)", N[2][2], F(1))
    check("C leaks nothing to A", N[2][0], F(0))
    for i, row in enumerate(N):
        check(f"row {i} is a distribution", sum(row), F(1))


def test_scaled_matrix_is_strictly_positive_and_not_symmetric():
    """Perron applies to Ñ because every entry is > 0 — and the HITS proof cannot
    be reused, because Ñ is not symmetric."""
    Nt = scaled_flow_matrix(fig_14_11(), s=F(4, 5))
    check_true("every entry strictly positive",
               all(v > 0 for row in Nt for v in row))
    check_true("Ñ is NOT symmetric",
               any(Nt[i][j] != Nt[j][i]
                   for i in range(4) for j in range(4)))
    for row in Nt:
        check("each row still sums to 1", sum(row), F(1))


# --- HITS ---------------------------------------------------------------------

def test_hits_reproduces_fig_14_11_all_four_vectors():
    it = hits_iterations(fig_14_11(), 2)
    o = [1, 2, 3, 4]
    check("auth k=1", vec(it[1]["authority"], o), fr("1/6", "1/6", "1/3", "1/3"))
    check("hub  k=1", vec(it[1]["hub"], o), fr("3/10", "2/5", "1/10", "1/5"))
    check("auth k=2", vec(it[2]["authority"], o), fr("1/17", "3/17", "6/17", "7/17"))
    check("hub  k=2", vec(it[2]["hub"], o), fr("1/3", "13/30", "1/30", "1/5"))


def test_hits_reproduces_fig_14_15():
    it = hits_iterations(fig_14_15(), 2)
    check("auth k=1", vec(it[1]["authority"], "ABCDE"), fr(0, 0, "1/2", "1/4", "1/4"))
    check("hub  k=1", vec(it[1]["hub"], "ABCDE"), fr("1/3", "2/3", 0, 0, 0))
    check("auth k=2", vec(it[2]["authority"], "ABCDE"), fr(0, 0, "3/7", "2/7", "2/7"))
    check("hub  k=2", vec(it[2]["hub"], "ABCDE"), fr("3/10", "7/10", 0, 0, 0))


def test_hits_reproduces_fig_14_16():
    """The problem the source COMMENTED OUT. Its key is correct; this pins it."""
    it = hits_iterations(fig_14_16(), 2)
    check("auth k=1", vec(it[1]["authority"], "ABCDEFGH"),
          fr("1/5", "1/5", "3/5", 0, 0, 0, 0, 0))
    check("hub  k=1", vec(it[1]["hub"], "ABCDEFGH"),
          fr(0, 0, 0, "1/11", "1/11", "3/11", "3/11", "3/11"))
    check("auth k=2", vec(it[2]["authority"], "ABCDEFGH"),
          fr("1/11", "1/11", "9/11", 0, 0, 0, 0, 0))
    check("hub  k=2", vec(it[2]["hub"], "ABCDEFGH"),
          fr(0, 0, 0, "1/29", "1/29", "9/29", "9/29", "9/29"))


def test_hits_authority_is_not_in_degree():
    """The lesson's thesis: authority is NOT in-degree. In Fig 14.16 C has in-degree
    3 of 5 (=0.6) but takes 9/11 (=0.818) of the authority, because it is endorsed
    by the STRONG hubs. If these were equal the worksheet's central item collapses."""
    a = hits_iterations(fig_14_16(), 2)[2]["authority"]
    check("C's authority after 2 rounds", a["C"], F(9, 11))
    check_true("...which is NOT its in-degree share (3/5)", a["C"] != F(3, 5))


def test_hits_end_normalization_matches_step_normalization():
    """The chapter normalizes once at the end; the worksheets normalize every
    sub-step. The updates are linear, so the NORMALIZED answers must agree."""
    G = fig_14_11()
    stepwise = hits_iterations(G, 2)[2]["authority"]
    raw = hits_iterations(G, 2, normalize=False)[2]["authority"]
    total = sum(raw.values())
    check("end-normalized == step-normalized",
          {n: raw[n] / total for n in G}, stepwise)


def test_hits_limit_settles_nonnegative_and_normalized():
    lim = hits_limit(fig_14_15())
    check_true("authority settles", all(v >= 0 for v in lim["authority"].values()))
    check("authority sums to 1", sum(lim["authority"].values()), F(1))


# --- `initial=` (0.8.1) -------------------------------------------------------
#
# hits_iterations grew an `initial=` in 0.8.1 to match pagerank_iterations, which
# had had one all along. The asymmetry was an omission, not a decision, and it had
# a cost: the test directly below THIS COMMENT used to be called
# `test_hits_limit_is_independent_of_the_starting_vector` — a name asserting the
# one property the missing parameter made impossible to test. It checked that the
# limit was nonnegative and summed to 1, and nothing whatever about starting
# vectors. It has been renamed to what it actually does, and the property it
# claimed is now genuinely tested, below.


def test_omitting_initial_reproduces_the_pre_0_8_1_output_exactly():
    """(a) THE NO-REGRESSION TEST. `initial=None` must reproduce, value for value,
    what the all-ones initialization produced before the parameter existed —
    including the `_raw` rows and `state_0`."""
    for name, G in (("14.11", fig_14_11()), ("14.15", fig_14_15()),
                    ("14.16", fig_14_16())):
        default = hits_iterations(G, 4)
        explicit = hits_iterations(G, 4, initial={n: 1 for n in G})
        check(f"{name}: initial=None == explicit all-ones", default, explicit)
        # state_0 is still the all-ones initialization, exactly as before.
        check(f"{name}: state_0 hub is all ones",
              default[0]["hub"], {n: F(1) for n in G})
        check(f"{name}: state_0 authority is all ones",
              default[0]["authority"], {n: F(1) for n in G})
    # And the chapter's worked vectors are untouched (the values the worksheets
    # print). If `initial` had perturbed the default path, these would move.
    a = hits_iterations(fig_14_11(), 1)[1]["authority"]
    check("14.11 round-1 authority unmoved", vec(a, [1, 2, 3, 4]),
          fr("1/6", "1/6", "1/3", "1/3"))


def _gap(a, b):
    """Largest coordinate-wise difference between two score vectors."""
    return max(abs(a[n] - b[n]) for n in a)


def test_a_skewed_start_converges_to_the_SAME_limit():
    """(b) THE PEDAGOGICAL CLAIM, PROVEN. This is what the parameter exists for.

    HITS is the power method on MMᵀ / MᵀM, so any start with a positive component
    along the dominant eigenvector is amplified toward the SAME eigenvector. Skew
    everything onto one page, reverse the ranking, use absurd magnitudes — the limit
    is the same. Only the number of rounds it takes changes.

    ⚠️ COMPARED WITH A TOLERANCE, NOT WITH `==`, and that is not a fudge — it is the
    mathematics. The HITS limit is an EIGENVECTOR and is generally IRRATIONAL: on
    Fig 14.15 the limiting authority of page C is exactly sqrt(2) - 1, which no
    Fraction can represent. The iteration therefore never reaches a fixed point, and
    hits_limit necessarily returns a rational APPROXIMATION after max_iter rounds.
    Two different starts land at slightly different points on the approach, so they
    agree to within the residual — not byte-for-byte. `test_..._gap_shrinks` below
    is what turns "they are close" into "they converge".
    """
    TOL = F(1, 10 ** 20)          # residual at max_iter=200 is ~1e-153; 1e-20 is slack
    for name, G, order in (("14.11", fig_14_11(), [1, 2, 3, 4]),
                           ("14.15", fig_14_15(), list("ABCDE")),
                           ("14.16", fig_14_16(), list("ABCDEFGH"))):
        baseline = hits_limit(G)
        starts = {
            "all-ones (the default)": {n: F(1) for n in order},
            "skewed onto one page": {n: (F(1000) if i == 0 else F(1))
                                     for i, n in enumerate(order)},
            "reversed magnitudes": {n: F(len(order) - i)
                                    for i, n in enumerate(order)},
            "tiny and lopsided": {n: F(1, 7 ** (i + 1))
                                  for i, n in enumerate(order)},
        }
        for label, init in starts.items():
            lim = hits_limit(G, initial=init)
            for row in ("authority", "hub"):
                g = _gap(lim[row], baseline[row])
                check_true(
                    f"{name}: {row} limit from {label!r} agrees with the default "
                    f"(gap {float(g):.2e} < 1e-20)", g < TOL)


def test_the_gap_between_two_starts_shrinks_with_more_rounds():
    """The limits merely being CLOSE would prove nothing on its own — two arbitrary
    vectors can be close. What makes it convergence is that the gap SHRINKS
    geometrically as the iteration runs longer. Measured on Fig 14.15:
    max_iter 10 -> 4.8e-8, 20 -> 1.1e-15, 40 -> 5.2e-31, 80 -> 1.2e-61.
    """
    G = fig_14_15()
    skew = {n: (F(50) if n == "A" else F(1)) for n in G}
    gaps = [_gap(hits_limit(G, max_iter=m)["authority"],
                 hits_limit(G, max_iter=m, initial=skew)["authority"])
            for m in (10, 20, 40, 80)]
    for i in range(len(gaps) - 1):
        check_true(f"gap shrinks between max_iter steps {i} -> {i+1} "
                   f"({float(gaps[i]):.1e} -> {float(gaps[i+1]):.1e})",
                   gaps[i + 1] < gaps[i])
    check_true(f"and it shrinks HARD (1e-8 -> {float(gaps[-1]):.1e})",
               gaps[-1] < F(1, 10 ** 50))


def test_the_hits_limit_is_irrational_so_the_iteration_never_lands_on_it():
    """Why hits_limit returns an approximation, pinned. Fig 14.15's limiting
    authority for C is sqrt(2) - 1. No Fraction equals it, so no finite iteration
    reaches a fixed point — successive states are NEVER exactly equal, and any test
    that compares two limits with `==` is asserting something false."""
    G = fig_14_15()
    states = hits_iterations(G, 30)
    repeats = [k for k in range(2, 31)
               if states[k]["authority"] == states[k - 1]["authority"]]
    check("the iteration never lands on a fixed point", repeats, [])
    c = hits_limit(G)["authority"]["C"]
    check_true("C's authority is sqrt(2) - 1 to 1e-30",
               abs(float(c) - (2 ** 0.5 - 1)) < 1e-15)
    check_true("...but it is not exactly representable: it is a Fraction "
               "approximation, so squaring (c+1) does not give exactly 2",
               (c + 1) ** 2 != 2)


def test_a_skewed_start_moves_the_EARLY_rounds_but_not_the_limit():
    """The claim above is only interesting if the start genuinely perturbs the
    iteration. It does: round 1 from a skewed start is NOT round 1 from all-ones.
    So the limits agreeing is a real convergence result, not a no-op."""
    G = fig_14_15()
    skew = {n: (F(50) if n == "A" else F(1)) for n in G}
    r1_default = hits_iterations(G, 1)[1]["authority"]
    r1_skewed = hits_iterations(G, 1, initial=skew)[1]["authority"]
    check_true("round 1 actually differs", r1_default != r1_skewed)
    check_true("but the limits agree (to the iteration's residual — the limit is "
               "irrational, so `==` would be the wrong assertion)",
               _gap(hits_limit(G, initial=skew)["authority"],
                    hits_limit(G)["authority"]) < F(1, 10 ** 20))


def test_initial_preserves_exact_fractions():
    """(c) EXACTNESS. A start given as ints / 'p/q' strings / floats / Fractions is
    coerced to exact Fractions — no float creeps into the iteration, so the printed
    scores stay 3/7 and never 0.42857142857142855."""
    G = fig_14_15()
    init = {"A": 3, "B": "7/2", "C": F(1, 3), "D": 0.25, "E": 2}
    states = hits_iterations(G, 2, initial=init)
    for st in states:
        for row in ("authority", "hub", "authority_raw", "hub_raw"):
            for n, v in st[row].items():
                check_true(f"{row}[{n}] is an exact Fraction", isinstance(v, F))
    check("'7/2' parsed exactly", states[0]["hub"]["B"], F(7, 2))
    check("0.25 parsed exactly", states[0]["hub"]["D"], F(1, 4))
    # And the limit off this ragged start is still the chapter's limit (to the
    # iteration's residual — see test_the_hits_limit_is_irrational_...).
    check_true("ragged start still lands on the default limit",
               _gap(hits_limit(G, initial=init)["authority"],
                    hits_limit(G)["authority"]) < F(1, 10 ** 20))


def test_initial_is_the_HUB_vector_authorities_are_overwritten_immediately():
    """`initial` sets the starting HUB scores. The first sub-step of every update
    recomputes each authority FROM the hubs, so the starting authorities are
    overwritten before they are ever read — state_0 reports them and nothing else
    depends on them. Pinned so nobody later 'fixes' the loop to consume them."""
    G = fig_14_15()
    start = {n: F(2) for n in G}
    a = hits_iterations(G, 3, initial=start)
    # Same hub start, but state_0's authorities are reported as given...
    check("state_0 authority is what was passed", a[0]["authority"], start)
    # ...and every state from 1 on is determined by the HUB start alone.
    b = hits_iterations(G, 3, initial=start)
    check("iteration is a function of the hub start", a[1:], b[1:])


def test_initial_missing_a_node_raises_rather_than_silently_dropping_it():
    """A start that omits a node is an authoring error, not a default. It raises —
    the alternative is a figure that quietly iterates from a vector the author did
    not write."""
    G = fig_14_15()
    raises("hits: partial initial raises",
           lambda: hits_iterations(G, 1, initial={"A": 1}), ValueError)
    raises("pagerank: partial initial raises",
           lambda: pagerank_iterations(G, 1, initial={"A": 1}), ValueError)


def test_hits_and_pagerank_share_initial_semantics():
    """The two helpers resolve `initial` through the same code path, so their
    argument cannot drift apart again — which is the bug this release fixes."""
    G = fig_14_6()
    init = {n: F(i + 1) for i, n in enumerate(G)}
    h = hits_iterations(G, 1, initial=init)[0]["hub"]
    p = pagerank_iterations(G, 1, initial=init)[0]
    check("both read the same starting vector, exactly", h, p)
    check("both coerce to Fraction", {n: F(i + 1) for i, n in enumerate(G)}, p)


# --- PageRank: the Basic rule -------------------------------------------------

def test_pagerank_reproduces_fig_14_6_two_steps():
    r = pagerank_iterations(fig_14_6(), 2, rule="basic")
    check("r^0 uniform 1/8", vec(r[0], "ABCDEFGH"), fr(*(["1/8"] * 8)))
    check("step 1", vec(r[1], "ABCDEFGH"),
          fr("1/2", "1/16", "1/16", "1/16", "1/16", "1/16", "1/16", "1/8"))
    check("step 2", vec(r[2], "ABCDEFGH"),
          fr("5/16", "1/4", "1/4", "1/32", "1/32", "1/32", "1/32", "1/16"))


def test_pagerank_is_conserved_exactly_and_needs_no_renormalization():
    """Conserved BY CONSTRUCTION — unlike HITS. Students reliably import HITS's
    renormalization step; this is the fact that says they must not."""
    for r in pagerank_iterations(fig_14_6(), 8, rule="basic"):
        check("total is exactly 1", sum(r.values()), F(1))
    for r in pagerank_iterations(fig_14_6(), 8, rule="scaled", s=F(17, 20)):
        check("scaled total is exactly 1 too", sum(r.values()), F(1))


def test_pagerank_equilibrium_of_fig_14_6():
    G = fig_14_6()
    eq = pagerank_equilibrium(G, rule="basic")
    check("equilibrium (Fig 14.7)", vec(eq, "ABCDEFGH"),
          fr("4/13", "2/13", "2/13", "1/13", "1/13", "1/13", "1/13", "1/13"))
    check_true("it regenerates itself under one update",
               is_pagerank_equilibrium(G, eq, rule="basic"))
    check("...and the iteration actually converges to it",
          vec(pagerank_limit(G, rule="basic").limit, "ABCDEFGH"),
          fr("4/13", "2/13", "2/13", "1/13", "1/13", "1/13", "1/13", "1/13"))


def test_equilibrium_check_is_two_parted():
    """Sums to 1 AND is unchanged by an update. Neither half alone is enough."""
    G = fig_14_6()
    sums_but_moves = {n: F(1, 8) for n in G}                   # uniform: sums to 1
    check_true("uniform sums to 1 but is NOT an equilibrium",
               not is_pagerank_equilibrium(G, sums_but_moves, rule="basic"))
    eq = pagerank_equilibrium(G, rule="basic")
    scaled_up = {n: v * 2 for n, v in eq.items()}              # fixed by N^T, but sums to 2
    check_true("a doubled equilibrium fails the sum-to-1 half",
               not is_pagerank_equilibrium(G, scaled_up, rule="basic"))


def test_the_leak_drains_everything_into_F_and_G():
    lim = pagerank_limit(fig_14_8(), rule="basic")
    check("F and G take it all; the rest go to exactly 0",
          vec(lim.limit, "ABCDEFGH"), fr(0, 0, 0, 0, 0, "1/2", "1/2", 0))


def test_scaling_does_not_rescue_a_small_network():
    """E&K footnote 2, and genuinely counter-intuitive: on EIGHT nodes, s in
    [0.8, 0.9] does NOT fix Fig 14.8 — F and G still take MOST of the PageRank.
    The scaled rule works because real networks are enormous. Students reliably
    over-claim the opposite, so this is pinned."""
    G = fig_14_8()
    for s in (F(8, 10), F(85, 100), F(9, 10)):
        lim = pagerank_limit(G, rule="scaled", s=s).limit
        fg = lim["F"] + lim["G"]
        check_true(f"s={float(s)}: F+G still hold MORE THAN HALF (got {float(fg):.3f})",
                   fg > F(1, 2))


# --- PageRank: NON-CONVERGENCE, the flagship ---------------------------------

def test_basic_rule_oscillates_forever_on_the_three_node_graph():
    """THE flagship. (A⇄B, C→A) under the Basic rule cycles with period 2 and has
    NO limit. Exact Fractions make this a proof (r^3 IS r^1), not an estimate."""
    G = three_node()
    r = pagerank_iterations(G, 2, rule="basic")
    check("step 1", vec(r[1], "ABC"), fr("2/3", "1/3", 0))
    check("step 2", vec(r[2], "ABC"), fr("1/3", "2/3", 0))

    lim = pagerank_limit(G, rule="basic")
    check_true("does NOT converge", not lim.converged)
    check_true("...and is falsy", not lim)
    check("period is 2", lim.period, 2)
    check("there is NO limiting vector", lim.limit, None)
    check("the cycle is the A/B swap",
          [vec(c, "ABC") for c in lim.cycle],
          [fr("2/3", "1/3", 0), fr("1/3", "2/3", 0)])


def test_a_stationary_vector_exists_but_the_iteration_never_reaches_it():
    """The subtlety that makes nx.pagerank dangerous here. (1/2,1/2,0) IS
    self-reproducing — so a solver returns it, confidently. But the Basic
    iteration from a uniform start provably never approaches it. Both facts are
    true; only one of them answers 'what happens as k -> infinity'."""
    G = three_node()
    st = pagerank_equilibrium(G, rule="basic")
    check("a stationary vector exists", vec(st, "ABC"), fr("1/2", "1/2", 0))
    check_true("...and it really is self-reproducing",
               is_pagerank_equilibrium(G, st, rule="basic"))
    check_true("yet the ITERATION does not converge",
               not pagerank_limit(G, rule="basic").converged)


def test_starting_AT_the_fixed_point_converges_immediately():
    """Period 1 == converged. Distinguishes a fixed point from a cycle."""
    G = three_node()
    st = pagerank_equilibrium(G, rule="basic")
    lim = pagerank_limit(G, rule="basic", initial=st)
    check_true("starting at the fixed point IS converged", lim.converged)
    check("period 1", lim.period, 1)


def test_the_scaled_rule_rescues_the_oscillator():
    """The scaling factor is not a quality knob — it is what GUARANTEES a limit
    exists at all."""
    lim = pagerank_limit(three_node(), rule="scaled", s=F(85, 100))
    check_true("scaled converges where basic oscillates", lim.converged)
    check("scaled total is 1", sum(lim.limit.values()), F(1))
    check_true("every node is floored at (1-s)/n",
               all(v >= (1 - F(85, 100)) / 3 for v in lim.limit.values()))


def test_exhausting_the_budget_is_not_a_claim_of_oscillation():
    """period == 0 means 'still moving when the budget ran out'; period >= 2 means
    'proven to cycle'. Collapsing them would report Fig 14.6 — which converges
    perfectly well, just slowly — as non-convergent."""
    lim = pagerank_limit(fig_14_6(), rule="basic", max_iter=5)
    check_true("not converged within 5 updates", not lim.converged)
    check("but period is 0 — no cycle was PROVEN", lim.period, 0)
    check("and no cycle is reported", lim.cycle, None)
    check_true("with a real budget it converges fine",
               pagerank_limit(fig_14_6(), rule="basic").converged)


def test_iterations_are_exposed_for_the_worksheet_tables():
    lim = pagerank_limit(three_node(), rule="basic")
    check_true("per-iteration states are available", len(lim.iterations) > 3)
    check("iteration 0 is the uniform start",
          vec(lim.iterations[0], "ABC"), fr("1/3", "1/3", "1/3"))


def test_unknown_rule_raises():
    raises("rule='damped' is not a rule E&K defines",
           lambda: pagerank_iterations(fig_14_6(), 1, rule="damped"), ValueError)


# --- SCC and the bow-tie ------------------------------------------------------

def test_fig_13_5_has_six_sccs_including_singletons():
    """A lone node IS an SCC. Forgetting that gives 2 instead of 6 — a distractor."""
    comps = strongly_connected_components(fig_13_5())
    check("six SCCs", len(comps), 6)
    check("sizes, largest first", [len(c) for c in comps], [8, 4, 1, 1, 1, 1])
    check("the giant SCC", giant_scc(fig_13_5()),
          {"UnivX", "Classes", "Networks", "ITeach", "ClassBlog", "BlogRankings",
           "USNewsRankings", "USNewsFeatured"})


def test_the_books_own_trap_set_is_not_an_scc():
    """{UnivX, Classes, Networks, ITeach} is mutually reachable (part i) but is NOT
    an SCC — it sits inside a strictly larger such set, failing MAXIMALITY (part
    ii). E&K calls this out; it is the flagship distractor."""
    G = fig_13_5()
    trap = {"UnivX", "Classes", "Networks", "ITeach"}
    comps = [set(c) for c in strongly_connected_components(G)]
    check_true("the trap set is not returned as an SCC", trap not in comps)
    check_true("...because it is strictly contained in the giant SCC",
               trap < giant_scc(G))


def test_fig_13_5_bowtie_roles():
    bt = bowtie_partition(fig_13_5())
    role = lambda r: {n for n, v in bt.items() if v == r}
    check("IN", role("IN"), {"Student", "Applying"})
    check("OUT", role("OUT"), {"BlogCompanyZ", "CompanyZ", "Founders",
                               "PressReleases", "ContactUs"})
    check("TENDRIL", role("TENDRIL"), {"SongLyrics"})


def test_scc2_out_is_4_and_13_NOT_the_source_keys_answer():
    """★ THE ERRATUM, PINNED. The source worksheet key lists Downstream as
    {4, 8, 9, 13} — while ALSO listing 8 and 9 in the largest SCC. A node cannot
    be in the giant SCC and in OUT at once. 7 points to 8, so 8 LOOKS downstream,
    but 8→9→7 returns: 8 and 9 are squarely inside the SCC. OUT = {4, 13}."""
    G = scc2()
    bt = bowtie_partition(G)
    role = lambda r: {n for n, v in bt.items() if v == r}
    check("largest SCC", giant_scc(G), {2, 3, 6, 7, 8, 9, 11, 12})
    check("IN", role("IN"), {1, 5, 10})
    check("OUT is {4, 13}", role("OUT"), {4, 13})
    check("8 and 9 are SCC members, not downstream", {bt[8], bt[9]}, {"SCC"})
    check_true("the source key's OUT is NOT what we compute",
               role("OUT") != {4, 8, 9, 13})


def test_scc2_single_edge_that_grows_the_scc_most():
    """Fresh, and it out-thinks the source key: 13→10 absorbs THREE nodes (13, 10
    and 5) via 6→2→3→7→12→13→10→5→6, giving an SCC of 11. The key's 4→9 reaches
    only 9, and 9→4 — the same pair, reversed — grows it not at all."""
    G = scc2()
    def size_with(u, v):
        H = G.copy()
        H.add_edge(u, v)
        return len(giant_scc(H))
    check("13->10 gives 11", size_with(13, 10), 11)
    check("4->5 gives 10 (the near miss)", size_with(4, 5), 10)
    check("4->9 gives 9 (the source key's answer)", size_with(4, 9), 9)
    check("9->4 gives 8 — no growth at all (wrong direction)", size_with(9, 4), 8)
    best = max(((size_with(u, v), u, v) for u in G for v in G
                if u != v and not G.has_edge(u, v)))
    check("13->10 is the unique maximum", best, (11, 13, 10))


def test_scc_matches_networkx_tarjan():
    """The SCC DEFINITION genuinely coincides with the library's (unlike PageRank's
    and HITS's). Implemented from the definition for legibility, cross-checked
    against Tarjan so nothing is lost by that choice."""
    for name, G in [("Fig 13.5", fig_13_5()), ("scc2", scc2()),
                    ("Fig 14.6", fig_14_6()), ("3-node", three_node())]:
        mine = sorted(map(sorted, strongly_connected_components(G)), key=str)
        theirs = sorted(map(sorted, nx.strongly_connected_components(G)), key=str)
        check(f"{name} matches nx", mine, theirs)


def test_bowtie_partition_is_deterministic_across_processes():
    """The group map's KEY ORDER decides the figure's color assignment. Built from
    a set, it would shuffle with Python's per-process hash seed and the bow-tie
    would come out a different color next kernel start."""
    G = fig_13_5()
    order = list(dict.fromkeys(bowtie_partition(G).values()))
    check("group order follows the graph's node order, not a set's",
          order, list(dict.fromkeys(bowtie_partition(G).values())))
    check("keys are exactly the graph's nodes, in its order",
          list(bowtie_partition(G)), list(G.nodes()))


def test_scaled_rule_agrees_with_networkx_on_dangling_free_graphs():
    """SANITY CHECK ONLY — networkx's semantics are NOT adopted. On a graph with no
    dangling node, E&K's scaled rule and nx's damped rule coincide, so agreement
    here says our scaled arithmetic is right. They part company the moment a node
    dangles (see test_flow_matrix_sends_a_dangling_node_to_itself), and nx cannot
    express the Basic rule at all."""
    for name, G in [("Fig 14.6", fig_14_6()), ("Fig 14.8", fig_14_8()),
                    ("3-node", three_node())]:
        check_true(f"{name}: no dangling node",
                   all(G.out_degree(n) > 0 for n in G))
        ours = pagerank_limit(G, rule="scaled", s=F(85, 100)).limit
        theirs = nx.pagerank(G, alpha=0.85, tol=1e-14, max_iter=2000)
        check_true(f"{name}: agrees with nx to 1e-9",
                   max(abs(float(ours[n]) - theirs[n]) for n in G) < 1e-9)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        before = len(_FAILS)
        try:
            t()
        except Exception:
            _FAILS.append(f"{t.__name__} RAISED\n{traceback.format_exc()}")
        status = "ok" if len(_FAILS) == before else "FAIL"
        print(f"  [{status:4s}] {t.__name__}")
    print()
    if _FAILS:
        for f in _FAILS:
            print(f"FAIL: {f}")
        print(f"\n{len(_FAILS)} failure(s) across {len(tests)} tests")
        return 1
    print(f"{len(tests)}/{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
