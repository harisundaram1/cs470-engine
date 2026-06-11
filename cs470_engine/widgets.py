"""ipywidgets helpers for the engine."""

import hashlib
import random
import threading
import time

import ipywidgets as widgets

from .plot_style import COLORS


# Slight type-size bump for MC option labels — readable but not blown out.
def _option_label_wrap(html: str) -> str:
    return f'<span style="font-size: 1.05em;">{html}</span>'


def _stable_seed(key: str) -> int:
    """A process-independent integer seed derived from ``key``.

    Uses a BLAKE2b digest rather than the builtin ``hash()`` (which is salted
    per process via PYTHONHASHSEED), so the same key produces the same seed in
    every kernel — required for the option order to survive a kernel restart and
    match the order a student answered in (the restored-problem view relies on
    this). The first 8 digest bytes are ample entropy for seeding ``Random``.
    """
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _shuffled_options(options, seed_key: str):
    """Return ``options`` reordered by a deterministic permutation of ``seed_key``.

    A fresh ``random.Random`` seeded from ``_stable_seed(seed_key)`` drives the
    shuffle, so the permutation is process-independent and depends only on the
    key string (e.g. ``"<session_id>:<pid>"``). Distinct keys give independent
    orders; identical keys always give the same order.
    """
    items = list(options)
    random.Random(_stable_seed(seed_key)).shuffle(items)
    return items


def submit_button_with_gate(seconds: int, on_click, on_gate_clear=None):
    """Return a Submit button with a live countdown gate.

    Starts disabled with description "Submit in Ns…" and counts down once
    per second on a background daemon thread, updating the button's
    description. When the gate expires, the button's description changes
    to "Submit"; whether the button becomes enabled is delegated to
    ``on_gate_clear`` (so the caller can require additional preconditions,
    e.g. that an option has been selected). If ``on_gate_clear`` is None,
    the button is unconditionally enabled on gate expiry.
    """
    btn = widgets.Button(
        description=f"Submit in {seconds}s…",
        disabled=True,
        button_style="",
    )

    def _countdown():
        for remaining in range(seconds, 0, -1):
            btn.description = f"Submit in {remaining}s…"
            time.sleep(1)
        btn.description = "Submit"
        btn.button_style = "primary"
        if on_gate_clear is not None:
            on_gate_clear()
        else:
            btn.disabled = False

    threading.Thread(target=_countdown, daemon=True).start()
    btn.on_click(on_click)
    return btn


class ClickCounterButton:
    """Concept-cell button wrapper: exposes ``.value`` as the click count.

    Concept render functions read controls uniformly via ``.value`` —
    sliders give their current numeric value, dropdowns their current
    selection, and buttons (via this wrapper) their cumulative click
    count. Re-render callbacks register via ``.observe(cb, names='value')``
    mirroring the ipywidgets traitlet API.
    """

    def __init__(self, description: str):
        self._btn = widgets.Button(description=description)
        self.value = 0
        self._observers = []
        self._btn.on_click(self._on_click)

    def _on_click(self, _btn):
        old = self.value
        self.value = old + 1
        change = {"name": "value", "old": old, "new": self.value, "owner": self}
        for cb in self._observers:
            cb(change)

    def observe(self, callback, names=None):
        self._observers.append(callback)

    @property
    def widget(self):
        return self._btn


# -----------------------------------------------------------------------------
# OptionPicker — custom MC selection widget with MathJax-typeset labels
# -----------------------------------------------------------------------------
#
# ipywidgets.RadioButtons/SelectMultiple render option labels as plain text,
# so `$N(B) \setminus \{D\}$` shows up literally instead of typesetting.
# This widget replaces both with a VBox of (Checkbox, HTMLMath) rows.
# JupyterLab / Colab / PrairieLearn Workspaces all typeset `$…$` inside
# HTMLMath via MathJax.
#
# A single class handles both modes:
#   - mode="single_select": checking one option auto-unchecks the others.
#   - mode="multi_select":  checkboxes are independent.

class OptionPicker:
    """A MathJax-aware MC option list.

    Construct with a list of ``(option_id, html_label)`` tuples and a
    ``mode`` of ``"single_select"`` or ``"multi_select"``. Embed the
    rendered widget by displaying ``picker.widget``.

    Public surface mirrors the contract from Session 7:
      - ``selected_ids`` → list of currently-selected option ids.
      - ``has_selection`` → True iff at least one row is checked.
      - ``observe(callback)`` → register a callable invoked on any change.
      - ``lock()`` → disable all rows after finalization.
      - ``show_correct(correct_ids)`` → annotate rows with ✓ / ✗ markers
        once the cell is finalized.
    """

    def __init__(self, options, *, mode: str, shuffle_seed: str | None = None):
        assert mode in ("single_select", "multi_select"), mode
        self.mode = mode
        self._option_ids: list[str] = []
        self._checkboxes: dict = {}
        self._labels: dict = {}
        self._original_labels: dict = {}
        self._observers: list = []
        self._silencing = False
        rows = []

        # Per-student display shuffle. When ``shuffle_seed`` is given (the live
        # render path passes ``"<session_id>:<pid>"``), the DISPLAY order of the
        # options is permuted deterministically from that string so the correct
        # answer doesn't sit in the same slot for every student. Ids are
        # untouched and grading is an id-set comparison (see ``selected_ids``),
        # so the shuffle cannot affect scoring. Seeding uses hashlib — NOT the
        # builtin ``hash()``, which is salted per process — so the same
        # ``(session_id, pid)`` yields the SAME order across kernel restarts,
        # which the restored-answer view depends on. ``shuffle_seed=None``
        # (answer-key / QA) keeps the canonical authored order.
        options = list(options)
        if shuffle_seed is not None:
            options = _shuffled_options(options, shuffle_seed)

        for oid, label in options:
            cb = widgets.Checkbox(
                value=False,
                indent=False,
                layout=widgets.Layout(width="24px", margin="0"),
            )
            html = widgets.HTMLMath(
                value=_option_label_wrap(label),
                layout=widgets.Layout(width="auto", margin="0 0 0 0.4em"),
            )
            cb.observe(self._on_change, names="value")
            self._option_ids.append(oid)
            self._checkboxes[oid] = cb
            self._labels[oid] = html
            self._original_labels[oid] = label
            rows.append(widgets.HBox(
                [cb, html],
                layout=widgets.Layout(align_items="center", margin="0.15em 0"),
            ))

        self.widget = widgets.VBox(rows)

    def _on_change(self, change):
        if self._silencing:
            return
        # Single-select: when an option becomes checked, uncheck the others.
        if self.mode == "single_select" and change["new"]:
            self._silencing = True
            try:
                owner = change["owner"]
                for cb in self._checkboxes.values():
                    if cb is not owner and cb.value:
                        cb.value = False
            finally:
                self._silencing = False
        for cb in self._observers:
            cb(change)

    @property
    def selected_ids(self) -> list:
        return [oid for oid in self._option_ids
                if self._checkboxes[oid].value]

    @property
    def has_selection(self) -> bool:
        return any(cb.value for cb in self._checkboxes.values())

    def observe(self, callback) -> None:
        """Register a callback fired on any selection change."""
        self._observers.append(callback)

    def pre_select(self, option_ids) -> None:
        """Check the given option ids without firing observer callbacks.

        Used by the answer-key build to seed the cell with the declared
        correct answer(s) before locking.
        """
        self._silencing = True
        try:
            for oid in option_ids:
                cb = self._checkboxes.get(oid)
                if cb is not None:
                    cb.value = True
        finally:
            self._silencing = False

    def lock(self) -> None:
        for cb in self._checkboxes.values():
            cb.disabled = True

    def show_correct(self, correct_ids) -> None:
        """Annotate each row with a ✓ (correct option) or ✗ (a wrong pick)
        glyph. Called once the cell is finalized; safe to call before lock.
        """
        correct_set = set(correct_ids)
        good = COLORS["good"]
        bad = COLORS["bad"]
        for oid in self._option_ids:
            original = self._original_labels[oid]
            picked = self._checkboxes[oid].value
            if oid in correct_set:
                marker = (
                    f' <span style="color: {good}; font-weight: 600;">'
                    f'&nbsp;✓ correct</span>'
                )
            elif picked:
                marker = (
                    f' <span style="color: {bad}; font-weight: 600;">'
                    f'&nbsp;✗</span>'
                )
            else:
                marker = ""
            self._labels[oid].value = _option_label_wrap(original + marker)
