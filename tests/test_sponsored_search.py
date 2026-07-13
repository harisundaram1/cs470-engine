#!/usr/bin/env python3
"""Engine 0.9.0 — sponsored-search compute + the three latent bug fixes.

    python3 tests/test_sponsored_search.py          # no pytest needed

TWO KINDS OF TEST LIVE HERE, and they are load-bearing in different ways.

**The chapter reproductions.** Every worked number in E&K Chapter 15 — the figures
AND all six end-of-chapter exercises — recomputed from the helpers and compared to
the book. These are not "does the code agree with itself" tests; the expected values
were read out of the printed chapter. If a helper drifts, a worksheet key drifts with
it, and this is what says so.

**The three bug tests.** Each one FAILS ON 0.8.1 and passes on 0.9.0 — that is the
point of them, and each names the shipped-code defect it pins:

    B1  optimal_assignment          -> silently returned None when agents > objects
    B2  ascending_auction_rounds    -> 69 un-cleared rounds, silently returned
    B3  _bipartite_annot_label      -> TypeError on a scalar; '[1, 0]' on "10"

⚠ THE ONE THING THIS FILE DELIBERATELY DOES NOT DO is source VCG from the ascending
auction. E&K §15.9 proves the two coincide, and it is tempting to "check" VCG by
running the auction. That would make the agreement TRUE BY CONSTRUCTION and untestable
— and would teach the wrong derivation. `vcg_prices` differences two welfare optima
(the harm rule, Eq. 15.1) and consults no auction; `test_vcg_agrees_with_the_ascending_auction`
then compares two genuinely independent computations, which is the only way that
comparison means anything.
"""
import sys
import traceback

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt        # noqa: E402

from cs470_engine import plot_style as ps          # noqa: E402
from cs470_engine import problems                  # noqa: E402

FAILS = []


def check(name, fn):
    try:
        fn()
        print(f"  ok    {name}")
    except Exception as exc:
        FAILS.append((name, traceback.format_exc()))
        print(f"  FAIL  {name}  -- {type(exc).__name__}: {exc}")


def eq(got, want, what=""):
    assert got == want, f"{what}: got {got!r}, expected {want!r}"


def vcg_of(rates, values):
    """VCG prices in advertiser order, from the harm rule alone."""
    r = ps.vcg_prices(ps.sponsored_search_valuations(rates, values))
    return [r["prices"][j] for j in range(len(values))], r["revenue"]


# -----------------------------------------------------------------------------
# B1 — optimal_assignment silently returned None on agents > objects
# -----------------------------------------------------------------------------
# E&K Exercise 1 IS this shape: 3 advertisers, 2 slots. On 0.8.1:
#     optimal_assignment([[30,15],[20,10],[10,5]]) -> None
# because the brute force iterated permutations(range(2), 3), which is empty, so the
# running best never left its None initializer. Nothing raised. The None then reached
# draw_bipartite_market and died on None.items() — an AttributeError blamed on the
# renderer, three frames from the fault. Silent-None is this project's recurring
# failure signature; the fix is to compute the answer, which exists.

def test_B1_rectangular_more_agents_than_objects():
    V = [[30, 15], [20, 10], [10, 5]]           # 3 advertisers x 2 slots
    got = ps.optimal_assignment(V)
    assert got is not None, "0.8.1 BUG: silently returned None"
    # x -> slot a (30), y -> slot b (10); z gets nothing and is ABSENT from the dict.
    eq(got, {0: 0, 1: 1}, "optimal assignment")
    eq(2 not in got, True, "the unserved advertiser has no key")
    eq(sum(V[a][o] for a, o in got.items()), 40, "welfare")
    # ...and it really is the max over every injective assignment.
    import itertools
    best = max(sum(V[p[j]][j] for j in range(2))
               for p in itertools.permutations(range(3), 2))
    eq(sum(V[a][o] for a, o in got.items()), best, "is the true optimum")


def test_B1_renderer_survives_the_rectangular_market():
    """The consequence, not just the cause: 0.8.1 died here on None.items()."""
    fig, ax = plt.subplots()
    try:
        out = ps.draw_bipartite_market(
            ax, left=["a", "b"], right=["x", "y", "z"],
            derive="optimal_assignment",
            valuations=[[30, 15], [20, 10], [10, 5]])
        eq(len(out["matching"]), 2, "two slots matched")
    finally:
        plt.close(fig)


def test_B1_fewer_agents_than_objects_still_works():
    """The other rectangle — never broken, must stay unbroken."""
    eq(ps.optimal_assignment([[30, 15, 6], [20, 10, 4]]), {0: 0, 1: 1}, "2x3")


def test_B1_square_path_is_untouched():
    """Lesson 4's live figures all take this path. It must not move."""
    eq(ps.optimal_assignment([[30, 15, 6], [20, 10, 4], [10, 5, 2]]),
       {0: 0, 1: 1, 2: 2}, "Fig 15.3a / L4 square market")


# -----------------------------------------------------------------------------
# B2 — ascending_auction_rounds returned a 69-round trace that never cleared
# -----------------------------------------------------------------------------
# Same 3x2 market. With more buyers than sellers the set of ALL buyers is constricted
# at every price vector (|S| = 3 > 2 >= |N(S)|), so Hall's condition fails identically
# and no prices can EVER clear. 0.8.1 did not notice: it ran its defensive round-bound
# to exhaustion and handed back 69 un-cleared rounds with a meaningless final price
# vector — indistinguishable, to a caller that reads rounds[-1]["prices"], from a
# trace that cleared.

def test_B2_impossible_market_raises_instead_of_returning_garbage():
    V = [[30, 15], [20, 10], [10, 5]]
    try:
        out = ps.ascending_auction_rounds(V)
    except ValueError as exc:
        msg = str(exc)
        assert "3 buyers" in msg and "2 sellers" in msg, f"unclear message: {msg}"
        assert "sponsored_search_valuations" in msg, "must name the remedy"
        return
    raise AssertionError(
        f"0.8.1 BUG: returned {len(out)} rounds, cleared="
        f"{any(r['matching'] for r in out)}, final prices="
        f"{out[-1]['prices']} — silently.")


def test_B2_square_market_still_clears():
    """The fix must not break the markets that DO clear (all of Lesson 4's).

    Literal matrix, not `sponsored_search_valuations` — so this test runs on 0.8.1
    too, and PASSES there. That is what makes it a control: it shows the B2 guard
    rejects only the impossible market and leaves every legitimate one alone.
    """
    V = [[70, 28, 0], [60, 24, 0], [10, 4, 0]]                  # Fig 15.7
    rounds = ps.ascending_auction_rounds(V)
    eq(rounds[-1]["matching"] is not None, True, "clears")
    eq(rounds[-1]["prices"], [40, 4, 0], "Fig 15.8 market-clearing prices")


def test_B2_more_sellers_than_buyers_still_clears():
    """buyers < sellers is fine — only buyers > sellers is impossible."""
    rounds = ps.ascending_auction_rounds([[30, 15, 6], [20, 10, 4]])
    eq(rounds[-1]["matching"] is not None, True, "clears with a spare seller")


# -----------------------------------------------------------------------------
# B3 — the annotation label mangled scalars and strings
# -----------------------------------------------------------------------------
# 0.8.1: _bipartite_vector_label(3) -> TypeError: 'int' object is not iterable
#        _bipartite_vector_label("10") -> '[1, 0]'   (it walked the string's chars)
# The first blocked E&K Fig 15.2 outright. The second is worse: it did not raise, it
# rendered a wrong number onto a figure.

#
# NOTE these probe `_bipartite_vector_label` — the name that exists in BOTH versions
# (0.9.0 keeps it as an alias). Probing the new name would make the test fail on 0.8.1
# with a bare AttributeError, which proves only that the symbol is new, not that the
# behavior was WRONG. Calling the old name makes each of these a genuine behavioral
# pin: on 0.8.1 they fail because the answer is wrong; on 0.9.0 they pass.

def test_B3_scalar_entry():
    f = ps._bipartite_vector_label
    eq(f(3), "3", "0.8.1 BUG: TypeError: 'int' object is not iterable")
    eq(f(0), "0", "zero — the fictitious slot's clickthrough rate")
    eq(f(-3), "-3", "negative renders clean, not _fmt_num's '{-}3'")


def test_B3_string_entry_is_not_walked_character_by_character():
    f = ps._bipartite_vector_label
    eq(f("10"), "10", "0.8.1 BUG: iterated the chars and rendered '[1, 0]'")
    eq(f("c_1"), "c_1", "symbolic label")


def test_B3_vector_entry_is_unchanged():
    eq(ps._bipartite_vector_label([30, 15, 6]), "[30, 15, 6]", "L4's vectors")


# -----------------------------------------------------------------------------
# R1 / R2 — the four-column figure, and the note dispatch gap
# -----------------------------------------------------------------------------

def test_R1_four_column_figure_renders():
    """E&K Fig 15.2. On 0.8.1: TypeError: 'int' object is not iterable."""
    fig, ax = plt.subplots()
    try:
        ps.draw_bipartite_market(
            ax, left=["a", "b", "c"], right=["x", "y", "z"],
            prices=[10, 5, 2], price_label="clickthrough\nrates",
            valuations=[3, 2, 1], valuations_label="revenues\nper click",
            column_titles=("slots", "advertisers"))
        drawn = {t.get_text() for t in ax.texts}
        for want in ("10", "5", "2", "3", "2", "1", "clickthrough\nrates",
                     "revenues\nper click", "slots", "advertisers"):
            assert want in drawn, f"{want!r} not drawn"
        assert "price" not in drawn, "the hardcoded 'price' header leaked through"
        assert "valuations" not in drawn, "the hardcoded 'valuations' header leaked"
    finally:
        plt.close(fig)


def test_R1_headers_default_to_the_chapter_10_literals():
    """Every live Lesson-4 figure omits the labels and must keep its old headers."""
    fig, ax = plt.subplots()
    try:
        ps.draw_bipartite_market(ax, left=["a"], right=["x"],
                                 prices=[3], valuations=[[5]])
        drawn = {t.get_text() for t in ax.texts}
        assert "price" in drawn and "valuations" in drawn
    finally:
        plt.close(fig)


def test_R1_declash_never_fires_on_a_single_line_header():
    """The byte-identity guarantee, as a test rather than a hope.

    `_declash_annot_column` is what moves an annotation column, and it is gated on the
    header containing a newline. EVERY header in the live Chapter-10 corpus is a single
    word, so the gate can never open on them and their figures cannot move. Pinning it
    here means a future edit that loosens the gate fails loudly instead of silently
    nudging 71 deployed figures — which is exactly what an earlier version of this
    change did.
    """
    fig, ax = plt.subplots()
    try:
        # A deliberately hostile single-line case: Lesson 4's widest live title.
        ps.draw_bipartite_market(
            ax, left=["a", "b", "c"], right=["x", "y", "z"],
            prices=[13, 3, 0],
            valuations=[[30, 15, 6], [20, 10, 4], [10, 5, 2]],
            derive="preferred_seller", matching="auto",
            column_titles=("Sellers (1 real + 2 fake)", "Buyers"))
        hdr = [t for t in ax.texts if t.get_text() == "price"][0]
        eq(round(hdr.get_position()[0], 10), round(0.0 - 0.55, 10),
           "the 'price' header must sit at exactly x_left - 0.55, unmoved")
    finally:
        plt.close(fig)


def test_R1_declash_does_fire_on_the_two_line_chapter_15_header():
    """...and it must actually move the one that collides."""
    fig, ax = plt.subplots()
    try:
        ps.draw_bipartite_market(
            ax, left=["a", "b", "c"], right=["x", "y", "z"],
            prices=[10, 4, 0], price_label="clickthrough\nrates",
            valuations=[7, 6, 1], valuations_label="revenues\nper click",
            column_titles=("slots", "advertisers"))
        hdr = [t for t in ax.texts if t.get_text() == "revenues\nper click"][0]
        assert hdr.get_position()[0] > 2.6 + 0.5 + 1e-9, \
            "the wide 'advertisers' title overprints this header unless it is pushed out"
    finally:
        plt.close(fig)


def test_R2_note_is_whitelisted_on_bipartite_figures():
    """0.8.1: the dispatch FORWARDED note= but the key whitelist rejected it, and
    _check_figure_keys runs first — so note: raised ValueError and the renderer's
    whole note branch was dead code, unreachable from YAML."""
    for key in ("note", "edge_style", "price_label", "valuations_label"):
        assert key in problems._FIGURE_KEYS["bipartite_market"], \
            f"{key!r} is forwarded by _render_bipartite_market but not whitelisted"


def test_R2_unknown_keys_still_raise():
    """The whitelist must still be a whitelist."""
    try:
        problems._check_figure_keys(
            "bipartite_market", {"kind": "bipartite_market", "nonsense": 1},
            problems._FIGURE_KEYS["bipartite_market"], "draw_bipartite_market")
    except ValueError:
        return
    raise AssertionError("an unknown key no longer raises")


# -----------------------------------------------------------------------------
# C1–C4 — the chapter, reproduced
# -----------------------------------------------------------------------------

def test_C1_the_conversion():
    """v_ij = r_i * v_j — E&K Fig 15.3(a) and Fig 15.7."""
    eq(ps.sponsored_search_valuations([10, 5, 2], [3, 2, 1]),
       [[30, 15, 6], [20, 10, 4], [10, 5, 2]], "Fig 15.3(a)")
    eq(ps.sponsored_search_valuations([10, 4, 0], [7, 6, 1]),
       [[70, 28, 0], [60, 24, 0], [10, 4, 0]], "Fig 15.7")


def test_C1_fictitious_slot_padding():
    """3 advertisers, 2 slots -> a third slot of clickthrough rate 0."""
    eq(ps.pad_sponsored_market([10, 5], [3, 2, 1]), ([10, 5, 0], [3, 2, 1]))
    eq(ps.pad_sponsored_market([10, 5, 2], [3, 2]), ([10, 5, 2], [3, 2, 0]))
    eq(ps.sponsored_search_valuations([10, 5], [3, 2, 1]),
       [[30, 15, 0], [20, 10, 0], [10, 5, 0]], "padded to square")
    eq(ps.sponsored_search_valuations([10, 5], [3, 2, 1], pad=False),
       [[30, 15], [20, 10], [10, 5]], "pad=False leaves it rectangular")


def test_C2_vcg_reproduces_figure_15_3():
    p, _ = vcg_of([10, 5, 2], [3, 2, 1])
    eq(p, [13, 3, 0], "E&K Fig 15.3(b) VCG prices")


def test_C2_vcg_reproduces_figure_15_7_including_the_books_own_arithmetic():
    V = ps.sponsored_search_valuations([10, 4, 0], [7, 6, 1])
    out = ps.vcg_prices(V)
    eq([out["prices"][j] for j in range(3)], [40, 4, 0], "VCG prices")
    eq(out["revenue"], 44, "VCG revenue")
    # The book: "without x, y would move up one slot gaining 60-24 = 36, and z would
    # move up gaining 4-0 = 4; therefore x pays 40." Our route is Eq. (15.1) — two
    # welfare optima, differenced — and it must land on the same 40.
    h = out["harm"][0]
    eq((h["without_j"], h["with_j"], h["price"]), (64, 24, 40), "x's harm")
    eq(h["without_j"] - h["with_j"], 36 + 4, "= the book's 36 + 4")


def test_C2_vcg_on_a_non_factored_market():
    """VCG does not require v_ij = r_i*v_j. Nothing in the harm rule assumes it, and
    ws2's Dan/Elaine/Frank problem depends on that (it is the one place the source
    breaks the product structure)."""
    V = [[5, 3, 0], [4, 3, 0], [3, 3, 0]]        # deliberately NOT a product market
    out = ps.vcg_prices(V)
    eq(out["assignment"][0], 0, "Dan takes item 0")
    assert all(p >= 0 for p in out["prices"].values()), "no negative VCG price"


def test_C3_gsp_reproduces_the_truthful_bid_outcome():
    """Fig 15.6 at truthful bids: x takes the top slot at 6/click, pays 60, payoff 10."""
    g = ps.gsp_outcome([10, 4, 0], [7, 6, 1], [7, 6, 1])
    eq(g["assignment"], {0: 0, 1: 1, 2: 2}, "i-th slot to i-th highest bidder")
    eq(g["price_per_click"][0], 6, "= the (i+1)-st highest bid")
    eq(g["price"][0], 60, "cumulative = r_i * b_{i+1}")
    eq(g["payoff"][0], 10, "70 - 60")
    eq(g["price"][2], 0, "the bottom advertiser pays nothing")


def test_C3_gsp_rejects_unsorted_rates():
    """'the i-th slot' only means something if slot 0 is the top slot."""
    try:
        ps.gsp_outcome([4, 10], [7, 6], [7, 6])
    except ValueError as exc:
        assert "non-increasing" in str(exc)
        return
    raise AssertionError("unsorted rates silently produced an answer")


def test_C4_truth_telling_is_NOT_a_gsp_equilibrium():
    """The headline result of the chapter."""
    rates, vals = [10, 4, 0], [7, 6, 1]
    eq(ps.is_gsp_equilibrium(rates, [7, 6, 1], vals), False, "truthful bids")
    d = ps.gsp_deviations(rates, [7, 6, 1], vals)
    eq(len(d), 1, "exactly one profitable deviation")
    eq((d[0]["advertiser"], d[0]["from_slot"], d[0]["to_slot"]), (0, 0, 1), "x drops a slot")
    eq((d[0]["current_payoff"], d[0]["deviation_payoff"]), (10, 24), "payoff 10 -> 24")


def test_C4_both_of_the_books_equilibria_are_equilibria():
    rates, vals = [10, 4, 0], [7, 6, 1]
    eq(ps.is_gsp_equilibrium(rates, [5, 4, 2], vals), True, "bids (5,4,2)")
    eq(ps.is_gsp_equilibrium(rates, [3, 5, 1], vals), True, "bids (3,5,1)")
    # ...and the second is socially NON-optimal: y takes the top slot.
    eq(ps.gsp_outcome(rates, [3, 5, 1], vals)["assignment"][1], 0, "y in slot a")


def test_the_revenue_race_GSP_DOES_NOT_DOMINATE_VCG():
    """⛔ The source worksheet's ws2 P6 concludes 'revenue from GSP is higher than
    that of VCG'. E&K's OWN example refutes it. Both numbers must reproduce."""
    rates, vals = [10, 4, 0], [7, 6, 1]
    hi = ps.gsp_outcome(rates, [5, 4, 2], vals)["revenue"]
    lo = ps.gsp_outcome(rates, [3, 5, 1], vals)["revenue"]
    vcg = ps.vcg_prices(ps.sponsored_search_valuations(rates, vals))["revenue"]
    eq((hi, vcg, lo), (48, 44, 34), "the three revenues")
    assert hi > vcg > lo, "VCG sits BETWEEN the two GSP equilibria"
    assert not (lo >= vcg), "GSP >= VCG is FALSE: 34 < 44"


def test_vcg_agrees_with_the_ascending_auction():
    """§15.9 — VCG prices ARE the minimum market-clearing prices.

    The two sides of this are computed by genuinely different code: the harm rule
    differences two welfare optima and never looks at a price; the ascending auction
    raises prices on constricted sets and never computes a welfare optimum. That is
    the ONLY reason this assertion carries information. Source one from the other and
    it becomes a tautology that can never fail.
    """
    for rates, vals in [([10, 5, 2], [3, 2, 1]), ([10, 4, 0], [7, 6, 1]),
                        ([6, 5, 1], [4, 2, 1]), ([5, 2, 1], [3, 2, 1]),
                        ([10, 5], [3, 2, 1]), ([4, 3], [4, 3, 1])]:
        V = ps.sponsored_search_valuations(rates, vals)
        out = ps.vcg_prices(V)
        by_slot = [0] * len(V[0])
        for j, i in out["assignment"].items():
            by_slot[i] = out["prices"][j]
        clearing = ps.ascending_auction_rounds(V)[-1]["prices"]
        eq(clearing, by_slot, f"harm rule vs ascending auction on r={rates} v={vals}")


def test_chapter_exercises():
    """§15.10, all six. Keys derived from the chapter, not from the engine."""
    eq(vcg_of([10, 5], [3, 2, 1])[0], [15, 5, 0], "Ex 1 (needs the fictitious slot)")
    eq(vcg_of([6, 5, 1], [4, 2, 1])[0], [6, 4, 0], "Ex 2")
    eq(vcg_of([5, 2, 1], [3, 2, 1])[0], [7, 1, 0], "Ex 3")
    a, rev_a = vcg_of([4, 3], [4, 3, 1])
    b, rev_b = vcg_of([4, 3, 2], [4, 3, 1])
    eq((a, rev_a), ([6, 3, 0], 9), "Ex 4(a)")
    eq((b, rev_b), ([4, 1, 0], 5), "Ex 4(b)")
    assert rev_b < rev_a, "Ex 4(c): ADDING A SLOT LOWERED REVENUE, 9 -> 5"
    p5, rev5 = vcg_of([12, 5], [5, 4])
    eq((p5, rev5), ([28, 0], 28), "Ex 5(a)")
    eq(ps.gsp_outcome([12], [5, 4], [5, 4])["revenue"], 48, "Ex 5(b) second-price")
    assert 48 - rev5 == 5 * 4, "Ex 5(d): the gap is exactly r_b * v_y, always"
    eq(vcg_of([1], [6, 3, 1])[0], [3, 0, 0], "Ex 6 VCG")
    eq(ps.gsp_outcome([1], [6, 3, 1], [6, 3, 1])["price"][0], 3, "Ex 6 second-price")


def test_second_price_is_the_k_equals_1_case():
    """One real slot: VCG == GSP == second-price. E&K Ex 6, and the reason the
    worksheet must never offer the three as competing options at k=1."""
    for vals in ([6, 3, 1], [10, 7, 2], [5, 5, 1]):
        vcg = vcg_of([1], vals)[0][0]
        gsp = ps.gsp_outcome([1], vals, vals)["price"][0]
        eq(vcg, sorted(vals, reverse=True)[1], f"VCG = 2nd-highest value {vals}")
        eq(gsp, vcg, f"GSP agrees at k=1 {vals}")


if __name__ == "__main__":
    print("engine:", ps.__file__)
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            check(name, fn)
    print()
    if FAILS:
        for name, tb in FAILS:
            print("=" * 70)
            print(name)
            print(tb)
        print(f"{len(FAILS)} FAILED")
        sys.exit(1)
    print("all green")
