"""The Worksheet class — top-level orchestrator.

Public API (matches what scripts/build.py emits in each generated notebook):

    Worksheet.load(yaml_basename) -> Worksheet
    ws.start() -> None
    ws.render_section(section_id) -> None
    ws.show_record() -> None       # called from a near-bottom anchor cell
    ws.finalize() -> None
"""

import uuid
from pathlib import Path

import yaml
from IPython.display import display, Markdown, update_display

from .record import initial_markdown, updated_markdown
from .concept import render_concept
from .problems import render_problem, render_problem_answer_key
from .scoring import credit_for_attempt, multi_select_credit
from .submit import finalize as _finalize
from .persistence import SessionStore
from .messages import mathjax_safe_currency


DEFAULT_TIME_GATES = {"easy": 15, "medium": 30, "hard": 60}
DEFAULT_ATTEMPT_CREDITS = [1.0, 0.66, 0.33, 0.0]
DEFAULT_PASS_THRESHOLD = 0.5


class Worksheet:
    """Top-level worksheet runtime. One instance per loaded YAML."""

    @classmethod
    def load(cls, yaml_basename: str) -> "Worksheet":
        """Resolve and load a worksheet YAML by basename.

        Searches UPWARD from the current working directory: starting at cwd
        and walking up to the filesystem root, at each level it checks
        ``<dir>/worksheets/<basename>`` then ``<dir>/<basename>``, returning
        the first hit (so the directory nearest cwd wins). This makes the
        lookup independent of where Jupyter was launched: it resolves the dev
        tree (notebooks in ``iPython/``, YAML in ``../worksheets/``) and the
        flat PrairieLearn workspace (YAML sitting directly in cwd) alike.

        As a last resort it falls back to the inferred repo root
        ``Path(__file__).resolve().parents[2] / worksheets`` (works under an
        editable install of the engine inside the dev tree).

        ``source_path`` is set to whatever path resolves, and concept-module
        resolution in ``__init__`` is relative to ``source_path.parent`` — so
        a ``concepts/`` dir traveling beside the YAML is always found.
        """
        candidates: list[Path] = []
        cwd = Path.cwd().resolve()
        for d in [cwd, *cwd.parents]:
            candidates.append(d / "worksheets" / yaml_basename)
            candidates.append(d / yaml_basename)

        # Last-resort fallback: the repo root inferred from the engine's own
        # install location (covers an editable install run from outside the
        # tree). Only meaningful if that tree actually has a worksheets/ dir.
        inferred_repo_root = Path(__file__).resolve().parents[2]
        if (inferred_repo_root / "worksheets").is_dir():
            candidates.append(inferred_repo_root / "worksheets" / yaml_basename)

        for p in candidates:
            if p.exists():
                with open(p) as f:
                    ws = cls(
                        yaml.safe_load(f),
                        source_path=p,
                        repo_root=inferred_repo_root,
                    )
                # SESSION CONTINUATION: if a durable session file exists for this
                # worksheet (a prior run on this workspace), restore its
                # per-problem record + session_id into the fresh instance, so a
                # kernel restart / workspace reopen continues rather than starting
                # empty. Absent file => fresh session (unchanged behavior).
                ws._restore_session()
                return ws

        raise FileNotFoundError(
            f"Cannot locate worksheet YAML {yaml_basename!r}. Looked in: "
            + ", ".join(str(c) for c in candidates)
        )

    def __init__(self, data: dict, source_path: Path, repo_root):
        self.data = data
        self.worksheet = data["worksheet"]
        self.id = self.worksheet["id"]
        self.title = self.worksheet.get("title", self.id)
        self.sections_in_order = list(self.worksheet["sections"])
        self.sections_by_id = {s["id"]: s for s in self.sections_in_order}

        # Per-problem DISPLAY NUMBER (1..N) reflecting the interleaved on-page
        # order — concepts in YAML order, each followed by its
        # follow_up_problem_ids — derived via the SAME ordering function
        # build.py emits cells with (cs470_engine.ordering), so the visible "QN"
        # always matches on-page position rather than the internal q_N id. For an
        # already-interleaved worksheet (1.x) this equals id order, so no visible
        # change. Internal ids stay the source of truth everywhere else
        # (grading, results.json, shuffle seed, persistence).
        from .ordering import display_numbers
        self.display_number = display_numbers(self.sections_in_order)
        # ``display_reordered`` is True only when the interleaved display order
        # differs from the source problem order — i.e. the visible "QN" would
        # otherwise mismatch the internal id. The display-number annotations
        # (the small ``(q_N)`` suffix and the answer-key/record "Id" column) are
        # shown ONLY then, so an un-interleaved worksheet (1.x) is byte-identical
        # to before — no visible diff.
        _src_problem_order = [s["id"] for s in self.sections_in_order
                              if s.get("type") == "problem"]
        _disp_problem_order = [pid for pid, _ in
                               sorted(self.display_number.items(),
                                      key=lambda kv: kv[1])]
        self.display_reordered = _src_problem_order != _disp_problem_order
        self.shared_figures = self.worksheet.get("shared_figures") or {}
        self.time_gates = self.worksheet.get("time_gates_seconds") or DEFAULT_TIME_GATES

        scoring = self.worksheet.get("scoring") or {}
        self.attempt_credits = scoring.get("attempt_credits", DEFAULT_ATTEMPT_CREDITS)
        self.pass_threshold = scoring.get("pass_threshold", DEFAULT_PASS_THRESHOLD)

        self.source_path = source_path
        self.repo_root = repo_root
        self.session_id: str | None = None
        self.record_display_id: str | None = None
        self.scores: dict[str, dict] = {}
        self.answer_key_mode: bool = False

        # Durable session state (write-through store on the workspace filesystem).
        # Populated on every submit; restored at load() after a kernel reset /
        # workspace reopen so answers aren't silently lost. ``restored_session``
        # records whether this run picked up a prior session's answers.
        self.session_store = SessionStore(self.id)
        self.restored_session: bool = False

        # Derive the per-worksheet concept module path from the FULL worksheet
        # id stem (one module per worksheet, not per lesson number): id
        # `lesson_01_ties_triads` -> `concepts/lesson_01_ties_triads.py`,
        # `lesson_01_2_structural_balance` -> the matching full-id module. This
        # avoids collisions between sub-lectures of the same lesson (1.1/1.2/1.3
        # all begin `lesson_01`), which a `lesson_\d+`-only stem would conflate.
        #
        # Resolve RELATIVE TO THE YAML (source_path) first so concept cells work
        # in any layout where a concepts/ dir travels beside the YAML: the dev
        # repo (worksheets/lesson_*.yaml + worksheets/concepts/) and the flat PL
        # workspace (lesson_*.yaml + concepts/) alike. Fall back to the
        # repo_root-relative path for backward compatibility with the dev tree.
        module_stem = self.id
        self.concepts_module_path = None
        beside_yaml = source_path.parent / "concepts" / f"{module_stem}.py"
        if beside_yaml.exists():
            self.concepts_module_path = beside_yaml
        elif self.repo_root is not None:
            self.concepts_module_path = (
                self.repo_root / "worksheets" / "concepts" / f"{module_stem}.py"
            )

    # ------------------------------------------------------------------
    # Public API used by build-emitted cells
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open a session and emit the framing markdown.

        If a durable session was restored at ``load()`` (kernel restart /
        workspace reopen), the restored ``session_id`` is kept rather than
        opening a fresh one — so finalize reflects the restored answers. Only a
        genuinely fresh run mints a new session id.

        The record display itself is created later by ``show_record()`` — the
        build script emits a record-anchor cell near the bottom of the
        notebook so the running score lives at the bottom, not the top.
        """
        from .messages import RECORD_INSTRUCTIONS_MD

        if self.session_id is None:
            self.session_id = uuid.uuid4().hex
            self.record_display_id = f"record-{self.id}-{self.session_id[:8]}"

        restored_note = ""
        if self.restored_session:
            n = sum(1 for v in self.scores.values())
            restored_note = (
                f"\n\n_Continuing your earlier session — **{n}** answer(s) "
                f"restored from this workspace._"
            )
        display(Markdown(
            f"# {mathjax_safe_currency(self.title)}\n\n"
            f"_Session {self.session_id[:8]}_\n\n"
            f"{RECORD_INSTRUCTIONS_MD}{restored_note}"
        ))

    def show_record(self) -> None:
        """Render the current record at the calling cell's output location.

        Subsequent updates from problem-submit handlers target this same
        display via the registered ``record_display_id``.
        """
        if self.session_id is None:
            self.session_id = uuid.uuid4().hex
            self.record_display_id = f"record-{self.id}-{self.session_id[:8]}"
        display(
            Markdown(updated_markdown(self)),
            display_id=self.record_display_id,
        )

    def start_answer_key(self) -> None:
        """Open an instructor-QA session. Sets ``answer_key_mode = True`` so
        subsequent ``render_section`` calls show the correct answer and
        rationale instead of the student-facing submit flow.
        """
        # Answer-key (QA) builds never continue a student session: clear any
        # restored record so the verification + pre-selected correct answers
        # reflect the declared key, not a prior run on this machine.
        self.scores = {}
        self.restored_session = False
        self.answer_key_mode = True
        self.session_id = uuid.uuid4().hex
        self.record_display_id = f"record-{self.id}-{self.session_id[:8]}"
        display(Markdown(
            f"# {mathjax_safe_currency(self.title)} — Answer Key\n\n"
            f"_Instructor QA build. Each problem renders with the declared "
            f"correct answer(s) pre-selected and the rationale visible._"
        ))

    def render_section(self, section_id: str) -> None:
        section = self.sections_by_id.get(section_id)
        if section is None:
            display(Markdown(f"*Unknown section id: `{section_id}`.*"))
            return

        stype = section.get("type")
        if stype == "intro":
            display(Markdown(mathjax_safe_currency(section["markdown"])))
        elif stype == "concept":
            render_concept(self, section)
        elif stype == "problem":
            if self.answer_key_mode:
                render_problem_answer_key(self, section)
            else:
                render_problem(self, section)
        else:
            display(Markdown(f"*Unknown section type: `{stype}`.*"))

    def print_verification_table(self) -> None:
        """Run each problem's declared correct answer through the scoring
        logic. A row reads PASS iff a student submitting the declared
        correct answer would receive full credit; otherwise FAIL with the
        reason. Catches authoring mismatches between the `correct: [...]`
        field and what scoring actually credits.
        """
        from .problems import _q_display
        from .messages import ANSWER_KEY_SHUFFLE_NOTE_MD
        # "Id" column only when reordered, so 1.x's table is unchanged.
        show_id = self.display_reordered
        header = ("| Q | Id | Type | Declared correct | Credit | Status | Note |"
                  if show_id else
                  "| Q | Type | Declared correct | Credit | Status | Note |")
        rule = ("|---|----|------|------------------|--------|--------|------|"
                if show_id else
                "|---|------|------------------|--------|--------|------|")
        lines = [
            "### Answer-key verification",
            "",
            ANSWER_KEY_SHUFFLE_NOTE_MD,
            "",
            header,
            rule,
        ]
        n_pass = 0
        n_total = 0
        # List in DISPLAY order (interleaved on-page order), so the table reads
        # like the notebook; the Q column is the sequential display number and
        # the Id column carries the internal q_N for author/TA cross-reference.
        problems = [s for s in self.sections_in_order
                    if s.get("type") == "problem"]
        problems.sort(key=lambda s: self.display_number.get(s["id"], 1_000_000))
        for section in problems:
            n_total += 1
            pid = section["id"]
            qtype = section.get("question_type", "single_select")
            correct = list(section.get("correct") or [])
            option_ids = {o["id"] for o in section.get("options") or []}
            unknown = [c for c in correct if c not in option_ids]
            if not correct:
                status, note, credit = "FAIL", "empty correct", 0.0
            elif unknown:
                status, note = "FAIL", f"unknown id(s): {','.join(unknown)}"
                credit = 0.0
            else:
                correct_set = set(correct)
                if qtype == "multi_select":
                    credit = multi_select_credit(correct_set, correct_set, 1)
                else:
                    credit = credit_for_attempt(1) if correct[0] in correct_set else 0.0
                if abs(credit - 1.0) < 1e-9:
                    status, note = "PASS", "—"
                    n_pass += 1
                else:
                    status, note = "FAIL", f"credit {credit:.2f} ≠ 1.00"
            id_cell = f" {pid} |" if show_id else ""
            lines.append(
                f"| {_q_display(self, pid)} |{id_cell} {qtype} "
                f"| {','.join(correct) or '—'} "
                f"| {credit:.2f} | {status} | {note} |"
            )
        lines += ["", f"**Result:** {n_pass} / {n_total} pass."]
        display(Markdown("\n".join(lines)))

    def finalize(self) -> None:
        _finalize(self)

    # ------------------------------------------------------------------
    # Internal hook called from problem submit handlers
    # ------------------------------------------------------------------

    def _record_answer(
        self,
        pid: str,
        attempt: int,
        is_correct: bool,
        credit: float,
        locked: bool,
        chosen: list | None = None,
    ) -> None:
        self.scores[pid] = {
            "attempt": attempt,
            "correct": is_correct,
            "credit": credit,
            "locked": locked,
            # The selected option ids — persisted so a restored cell can
            # visually pre-fill the student's prior choice (not just the credit).
            "chosen": list(chosen) if chosen is not None else [],
        }
        # WRITE-THROUGH: persist the updated record to the durable session file
        # on every submit, so the in-memory record and the on-disk store stay in
        # sync. Best-effort (a write failure never breaks the live flow).
        self.session_store.save(session_id=self.session_id, scores=self.scores)
        update_display(
            Markdown(updated_markdown(self)),
            display_id=self.record_display_id,
        )

    # ------------------------------------------------------------------
    # Session continuation (durable reopen support)
    # ------------------------------------------------------------------

    def _restore_session(self) -> None:
        """Load any durable session file for this worksheet into the instance.

        Sets ``scores`` and ``session_id`` from the stored record and flags
        ``restored_session``. A missing/foreign/stale file leaves a fresh
        session (no-op). Skipped silently in answer-key mode (the QA build never
        restores — ``start_answer_key`` also clears scores defensively)."""
        state = self.session_store.load_state()
        if not state:
            return
        scores = state.get("scores") or {}
        if not scores:
            return
        self.scores = dict(scores)
        restored_sid = state.get("session_id")
        if restored_sid:
            self.session_id = restored_sid
            self.record_display_id = f"record-{self.id}-{restored_sid[:8]}"
        self.restored_session = True
