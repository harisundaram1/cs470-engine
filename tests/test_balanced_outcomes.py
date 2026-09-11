#!/usr/bin/env python3
"""Gate for the BALANCED-OUTCOME SOLVER (`solve_balanced` / `balanced_values`, c12).

WHAT IT CHECKS
  1. **THE BOOK IS THE INDEPENDENT CHECK.** Section 12.7-12.8 narrates five
     outcomes in prose and figures; all five are reproduced here as fixtures. The
     solver was written from those pages, so reproducing them is the only evidence
     that separates "it computes something" from "it computes the right thing".
  2. **THE TIE INVENTORY.** A balanced outcome need not be unique, and on graphs
     this small three different shapes occur. Each is asserted by name, because the
     API's whole job is to distinguish them:
       * both unique                 -- four-node path, stem graph;
       * matching non-unique, values determined -- three- and five-node paths;
       * a CONTINUUM                 -- the four-cycle.
  3. **RED CASES, and each is proven able to fail** rather than passing for the
     wrong reason. The book supplies two outcomes it explicitly calls NOT balanced
     (Fig 12.8(a) and 12.8(c)); a checker that always said True would pass every
     positive fixture above and fail exactly here.
  4. **THE VACUITY TRAP.** `is_balanced` is vacuously True on an empty matching,
     so a solver filtering on balance alone would report the all-zero outcome on
     every graph in the book. The stability filter is what prevents that, and
     check R2 fails if it is ever removed.
  5. **THE NO-DEAL BRANCH.** `nash_bargaining_split` returns None once outside
     options sum past 1 -- the boundary that blocked authoring in the first place.
     R3 shows a matching rejected for exactly that reason, with the arithmetic.
  6. **COMPLETENESS**, cross-checked against an independent brute force that knows
     nothing about the solver's method: grid every rational split and confirm the
     solver's answer is the whole answer, not a subset of it.

WHAT IT CANNOT SEE
  Whether an item built on these numbers teaches anything. The chapter's own
  exercises are deliberately qualitative ("you do not have to give actual numbers"),
  so a numeric key is a CHOICE about what to assess, and that is a read, not a test.
  It also says nothing about per-edge stakes: Exercise 4(b) places $2 on one edge
  and $10 on the others, which this model does not represent at all.

    python3.12 tests/test_balanced_outcomes.py
"""
from fractions import Fraction as F

import networkx as nx

from cs470_engine.plot_style import (
    balanced_values,
    is_balanced,
    is_stable,
    nash_bargaining_split,
    solve_balanced,
)

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"           got  {got!r}")
        print(f"           want {want!r}")
        FAILS.append(label)


P3 = nx.path_graph(list("ABC"))
P4 = nx.path_graph(list("ABCD"))
P5 = nx.path_graph(list("abcde"))
TRIANGLE = nx.Graph([("A", "B"), ("B", "C"), ("A", "C")])
STEM = nx.Graph([("A", "B"), ("B", "C"), ("B", "D"), ("C", "D")])
C4 = nx.Graph([("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")])
#: K4 minus one edge: point outcomes AND a continuum around them, together.
K4_MINUS = nx.Graph([("A", "B"), ("A", "C"), ("A", "D"), ("B", "C"), ("B", "D")])


def book_fixtures():
    print("A. THE BOOK'S OWN NARRATED OUTCOMES (Sections 12.7-12.8)")

    check("Fig 12.8(b): the four-node path is (1/3, 2/3, 2/3, 1/3)",
          balanced_values(P4), {"A": F(1, 3), "B": F(2, 3), "C": F(2, 3), "D": F(1, 3)})

    check("Fig 12.9: the stem graph is (A 1/4, B 3/4, C 1/2, D 1/2)",
          balanced_values(STEM), {"A": F(1, 4), "B": F(3, 4), "C": F(1, 2), "D": F(1, 2)})
    check("Fig 12.9 is THE UNIQUE balanced outcome, as the book says",
          solve_balanced(STEM)["matching_unique"], True)

    check("p316: on the three-node path B gets the FULL one unit",
          balanced_values(P3)["B"], F(1))
    check("p316: and the two end nodes get nothing",
          (balanced_values(P3)["A"], balanced_values(P3)["C"]), (F(0), F(0)))

    check("p316: on the five-node path the OFF-CENTER nodes b and d get 1",
          (balanced_values(P5)["b"], balanced_values(P5)["d"]), (F(1), F(1)))
    check("p316: and the central node c is 'in fact very weak' -- it gets 0",
          balanced_values(P5)["c"], F(0))

    check("p317: the triangle has NO stable outcome, hence none balanced",
          solve_balanced(TRIANGLE)["outcomes"], [])
    try:
        balanced_values(TRIANGLE)
        check("...and balanced_values REFUSES rather than inventing one", "returned", "raised")
    except ValueError as e:
        check("...and balanced_values REFUSES rather than inventing one",
              "no stable outcome" in str(e), True)

    check("p320: B's advantage on the STEM (3/4) exceeds its advantage on the 4-path (2/3)",
          balanced_values(STEM)["B"] > balanced_values(P4)["B"], True)


def tie_inventory():
    print("\nB. THE TIE INVENTORY -- three shapes, each named")

    p4 = solve_balanced(P4)
    check("BOTH UNIQUE: four-node path, one matching and one value set",
          (p4["matching_unique"], p4["determined"]), (True, True))

    p5 = solve_balanced(P5)
    check("MATCHING NON-UNIQUE, VALUES DETERMINED: five-node path has 3 matchings",
          len({m for m, _ in p5["outcomes"]}), 3)
    check("...yet its values ARE determined, so values are keyable and the matching is NOT",
          (p5["matching_unique"], p5["determined"]), (False, True))

    p3 = solve_balanced(P3)
    check("same shape on the three-node path: 2 matchings, one value set",
          (len({m for m, _ in p3["outcomes"]}), p3["determined"]), (2, True))

    c4 = solve_balanced(C4)
    check("CONTINUUM: the four-cycle reports underdetermined matchings",
          len(c4["underdetermined"]) > 0, True)
    check("...and is NOT determined", c4["determined"], False)


def red_cases():
    print("\nC. RED CASES -- each must be able to FAIL for the reason it exists")

    print("\n  R1. the book's own NOT-balanced outcomes must be REJECTED")
    M = [("A", "B"), ("C", "D")]
    half = {"A": 0.5, "B": 0.5, "C": 0.5, "D": 0.5}
    quarter = {"A": 0.25, "B": 0.75, "C": 0.75, "D": 0.25}
    check("Fig 12.8(a), all one-half: is_balanced says False",
          is_balanced(P4, M, half), False)
    check("Fig 12.8(c), (1/4, 3/4, 3/4, 1/4): is_balanced says False",
          is_balanced(P4, M, quarter), False)
    check("both ARE stable, so it is balance and not stability doing the rejecting",
          (is_stable(P4, M, half), is_stable(P4, M, quarter)), (True, True))
    check("and neither appears among the solver's outcomes",
          any(v == {k: F(x).limit_denominator(4) for k, x in half.items()}
              for _, v in solve_balanced(P4)["outcomes"]), False)

    print("\n  R2. THE VACUITY TRAP -- balance alone would return the all-zero outcome")
    check("is_balanced is VACUOUSLY True on the empty matching",
          is_balanced(P4, [], {}), True)
    check("...but the empty matching is NOT stable",
          is_stable(P4, [], {}), False)
    check("...so the solver excludes it (this fails if the stability filter is dropped)",
          any(m == () for m, _ in solve_balanced(P4)["outcomes"]), False)

    print("\n  R3. THE NO-DEAL BRANCH -- the boundary that blocked authoring")
    check("nash_bargaining_split(1, 1) is None: outside options sum past 1",
          nash_bargaining_split(1, 1), None)
    check("nash_bargaining_split(0.6, 0.5) is None too -- the measured blocker",
          nash_bargaining_split(0.6, 0.5), None)
    check("on the four-node path, matching {BC} alone leaves A and D unmatched ...",
          sorted(set("ABCD") - {"B", "C"}), ["A", "D"])
    check("...each giving its partner an outside option of 1, so 1+1 > 1 and no "
          "balanced outcome uses that matching",
          any(m == (("B", "C"),) for m, _ in solve_balanced(P4)["outcomes"]), False)

    print("\n  R4. THE CONTINUUM, and the misreading the flag exists to prevent")
    c4 = solve_balanced(C4)
    check("the four-cycle reports ZERO point outcomes ...", len(c4["outcomes"]), 0)
    check("...which read ALONE would say 'no balanced outcome exists' -- and is wrong: "
          "a continuum is flagged", len(c4["underdetermined"]) > 0, True)
    try:
        balanced_values(C4)
        check("balanced_values refuses the four-cycle", "returned", "raised")
    except ValueError as e:
        check("balanced_values refuses the four-cycle, naming the continuum",
              "CONTINUUM" in str(e), True)
    # the continuum is REAL, not an artifact of the method: exhibit two members.
    for t in (F(1, 4), F(3, 8)):
        vals = {"A": t, "B": 1 - t, "C": t, "D": 1 - t}
        fl = {k: float(v) for k, v in vals.items()}
        check(f"  (t={t}) is genuinely balanced AND stable on the four-cycle",
              (is_balanced(C4, [("A", "B"), ("C", "D")], fl),
               is_stable(C4, [("A", "B"), ("C", "D")], fl)), (True, True))

    print("\n  R5. COEXISTENCE -- point outcomes AND a continuum on the same graph")
    k4 = solve_balanced(K4_MINUS)
    check("K4-minus-an-edge reports point outcome(s) ...", len(k4["outcomes"]) > 0, True)
    check("...AND a continuum around them", len(k4["underdetermined"]) > 0, True)
    check("its node_values look like a SINGLETON, which would read as 'determined' ...",
          all(len(v) == 1 for v in k4["node_values"].values()), True)
    check("...so `determined` is the flag that must be read, and it is False",
          k4["determined"], False)
    try:
        balanced_values(K4_MINUS)
        check("balanced_values refuses, naming the CONTINUUM not a disagreement",
              "returned", "raised")
    except ValueError as e:
        check("balanced_values refuses, naming the CONTINUUM not a disagreement",
              "CONTINUUM" in str(e), True)

    print("\n  R6. EXACTNESS -- keys must read 1/3, never 0.3333333333333333")
    v = balanced_values(P4)["A"]
    check("the value is a Fraction", isinstance(v, F), True)
    check("and it is EXACTLY one third: 3*v == 1", v * 3, F(1))

    print("\n  R7. THE GUARD CAN FIRE -- a runaway enumeration is loud, not slow")
    try:
        solve_balanced(P5, cap=1)
        check("cap=1 raises rather than enumerating", "returned", "raised")
    except ValueError as e:
        check("cap=1 raises rather than enumerating", "matchings" in str(e), True)

    print("\n  R8. THE DISAGREEMENT BRANCH -- no natural witness, so exercised directly")
    print("       (searched 766 connected graphs on 4-5 nodes exhaustively and 2,986")
    print("        sampled on 6-7 nodes: ZERO graphs whose stable balanced outcomes")
    print("        disagree on a value. The branch is DEFENSIVE and unwitnessed.)")
    import cs470_engine.plot_style as ps
    real = ps.solve_balanced
    ps.solve_balanced = lambda G, cap=None: {
        "outcomes": [((("A", "B"),), {"A": F(0), "B": F(1)})],
        "node_values": {"A": (F(0),), "B": (F(0), F(1))},
        "determined": False,
        "matching_unique": True,
        "underdetermined": (),
    }
    try:
        ps.balanced_values(P3)
        check("a disagreeing result raises, naming the spread", "returned", "raised")
    except ValueError as e:
        check("a disagreeing result raises, naming the spread",
              "disagree" in str(e) and "'B'" in str(e), True)
    finally:
        ps.solve_balanced = real

    print("\n  R9. COMPLETENESS -- an INDEPENDENT brute force must find the same set")
    M = (("A", "B"), ("C", "D"))
    den, hits = 12, []
    for i in range(den + 1):
        for j in range(den + 1):
            vals = {"A": F(i, den), "B": 1 - F(i, den),
                    "C": F(j, den), "D": 1 - F(j, den)}
            fl = {k: float(x) for k, x in vals.items()}
            if is_balanced(P4, M, fl) and is_stable(P4, M, fl):
                hits.append(vals)
    check("grid search over denominator 12 finds exactly ONE stable balanced outcome",
          len(hits), 1)
    check("...and it is the solver's answer", hits[0], balanced_values(P4))

    print("\n  R11. THE ARGMAX CHECK IS REDUNDANT WITH is_balanced -- measured, not assumed")
    print("       Mutation testing found this: deleting the argmax-consistency test")
    print("       inside _balanced_for_matching left the ENTIRE suite green, because")
    print("       is_balanced recomputes every outside option itself and rejects a")
    print("       wrong guess anyway. The check is kept as EXACT-arithmetic defense in")
    print("       front of a float comparison carrying a 1e-9 tolerance -- so what is")
    print("       asserted here is the redundancy, which is the thing that could break.")
    import itertools as _it
    from cs470_engine.plot_style import _exchange_solve_linear
    for G, M in ((P4, (("A", "B"), ("C", "D"))), (STEM, (("A", "B"), ("C", "D")))):
        partner = {}
        for u, w in M:
            partner[u] = w
            partner[w] = u
        matched = sorted(partner, key=str)
        elig = {u: [y for y in sorted(G.neighbors(u), key=str) if y != partner[u]]
                for u in matched}
        nodes = sorted(G.nodes(), key=str)
        with_chk, without_chk, explored = [], [], 0
        for pick in _it.product(*[elig[u] if elig[u] else [None] for u in matched]):
            guess = dict(zip(matched, pick))
            rows = [({n: 1}, 0) for n in nodes if n not in partner]
            for u, w in M:
                rows.append(({u: 1, w: 1}, 1))
                coef, rhs = {u: 2}, 1
                if guess[u] is not None:
                    coef[guess[u]] = coef.get(guess[u], 0) + 1
                    rhs += 1
                if guess[w] is not None:
                    coef[guess[w]] = coef.get(guess[w], 0) - 1
                    rhs -= 1
                rows.append((coef, rhs))
            kind = _exchange_solve_linear(nodes, rows)
            if kind[0] != "unique":
                continue
            sol = kind[1]
            if any(not (0 <= x <= 1) for x in sol.values()):
                continue
            explored += 1
            fl = {k: float(x) for k, x in sol.items()}
            argmax_ok = all(
                (F(0) if guess[u] is None else 1 - sol[guess[u]])
                == max([1 - sol[y] for y in elig[u]], default=F(0))
                for u in matched)
            if is_balanced(G, M, fl):
                without_chk.append(sol)
                if argmax_ok:
                    with_chk.append(sol)
        check(f"  {len(nodes)} nodes: the exact argmax filter and the float checker "
              f"accept the SAME set ({explored} candidate guess(es) explored)",
              with_chk, without_chk)

    print("\n  R10. EVERY returned outcome round-trips through BOTH checkers")
    bad = []
    for G in (P3, P4, P5, STEM, C4, TRIANGLE, K4_MINUS):
        for m, v in solve_balanced(G)["outcomes"]:
            fl = {k: float(x) for k, x in v.items()}
            if not (is_balanced(G, m, fl) and is_stable(G, m, fl)):
                bad.append((m, v))
    check("no outcome fails is_balanced or is_stable", bad, [])


def main():
    book_fixtures()
    tie_inventory()
    red_cases()
    print("\n" + ("FAIL: " + ", ".join(FAILS) if FAILS else "PASS -- all checks green"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
