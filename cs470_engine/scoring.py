"""Scoring helpers for the engine.

Single-select MC uses the 1.0 / 0.66 / 0.33 / 0.0 attempt-credit schedule.
Multi-select MC uses the partial-credit formula from design doc §6.6,
multiplied by the same attempt schedule.
"""

ATTEMPT_CREDITS = [1.0, 0.66, 0.33]
MAX_ATTEMPTS = 3


def credit_for_attempt(attempt_number: int) -> float:
    """Return the credit earned if `attempt_number` (1-indexed) is correct.

    Beyond the credit schedule, returns 0.0.
    """
    if 1 <= attempt_number <= len(ATTEMPT_CREDITS):
        return ATTEMPT_CREDITS[attempt_number - 1]
    return 0.0


def multi_select_credit(chosen_set: set,
                        correct_set: set,
                        attempt: int) -> float:
    """Partial credit for a multi-select MC attempt, per design doc §6.6.

        correct_chosen   = |A ∩ C|
        incorrect_chosen = |A \\ C|
        raw              = (correct_chosen − incorrect_chosen) / |C|
        credit           = max(0, raw) * credit_for_attempt(attempt)

    where A is the student's chosen set and C is the correct set. Floored
    at 0 so guessing all options does not exceed picking only the correct
    ones; capped at 1.0 × attempt_multiplier.

    Worked examples (for C = {a, b, d}):
        A == C            : raw = 3/3 = 1.0
        A = {a, b}        : raw = 2/3 ≈ 0.667    (partial, no wrong picks)
        A = {a, b, c}     : raw = (2 − 1)/3 ≈ 0.333  (one wrong pick)
        A = {c}           : raw = (0 − 1)/3 < 0  → floored to 0
        A = {}            : raw = 0/3 = 0
    """
    if not correct_set:
        return 0.0
    correct_chosen = len(chosen_set & correct_set)
    incorrect_chosen = len(chosen_set - correct_set)
    raw = (correct_chosen - incorrect_chosen) / len(correct_set)
    raw = max(0.0, min(1.0, raw))
    return raw * credit_for_attempt(attempt)
