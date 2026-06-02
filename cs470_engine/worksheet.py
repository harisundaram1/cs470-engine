"""The Worksheet class — top-level orchestrator.

Public API (matches what scripts/build.py emits in each generated notebook):

    Worksheet.load(yaml_basename) -> Worksheet
    ws.start() -> None
    ws.render_section(section_id) -> None
    ws.show_record() -> None       # called from a near-bottom anchor cell
    ws.finalize() -> None
"""

import re
import uuid
from pathlib import Path

import yaml
from IPython.display import display, Markdown, update_display

from .record import initial_markdown, updated_markdown
from .concept import render_concept
from .problems import render_problem, render_problem_answer_key
from .scoring import credit_for_attempt, multi_select_credit
from .submit import finalize as _finalize


DEFAULT_TIME_GATES = {"easy": 15, "medium": 30, "hard": 60}
DEFAULT_ATTEMPT_CREDITS = [1.0, 0.66, 0.33, 0.0]
DEFAULT_PASS_THRESHOLD = 0.5


class Worksheet:
    """Top-level worksheet runtime. One instance per loaded YAML."""

    @classmethod
    def load(cls, yaml_basename: str) -> "Worksheet":
        """Resolve and load a worksheet YAML by basename.

        Searches, in order:
          1. `<cwd>/<yaml_basename>`
          2. `<cwd>/worksheets/<yaml_basename>`
          3. `<inferred_repo_root>/worksheets/<yaml_basename>`, where the
             repo root is `Path(__file__).resolve().parents[2]` (works
             under `pip install -e ./engine`).
        """
        inferred_repo_root = Path(__file__).resolve().parents[2]
        if not (inferred_repo_root / "worksheets").is_dir():
            inferred_repo_root = None

        candidates = [Path(yaml_basename), Path("worksheets") / yaml_basename]
        if inferred_repo_root is not None:
            candidates.append(inferred_repo_root / "worksheets" / yaml_basename)

        for p in candidates:
            if p.exists():
                with open(p) as f:
                    return cls(
                        yaml.safe_load(f),
                        source_path=p,
                        repo_root=inferred_repo_root,
                    )

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

        # Derive the per-lesson concept module path from the worksheet id.
        # e.g., "lesson_01_ties_triads" -> worksheets/concepts/lesson_01.py
        m = re.match(r"(lesson_\d+)", self.id)
        if m and self.repo_root is not None:
            self.concepts_module_path = (
                self.repo_root / "worksheets" / "concepts" / f"{m.group(1)}.py"
            )
        else:
            self.concepts_module_path = None

    # ------------------------------------------------------------------
    # Public API used by build-emitted cells
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open a session and emit the framing markdown.

        The record display itself is created later by ``show_record()`` — the
        build script emits a record-anchor cell near the bottom of the
        notebook so the running score lives at the bottom, not the top.
        """
        self.session_id = uuid.uuid4().hex
        self.record_display_id = f"record-{self.id}-{self.session_id[:8]}"
        display(Markdown(
            f"# {self.title}\n\n"
            f"_Session {self.session_id[:8]} · engine v0.1_\n\n"
            f"Submit answers below. Your running record appears at the "
            f"bottom of the notebook and is preserved when you save the file."
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
        self.answer_key_mode = True
        self.session_id = uuid.uuid4().hex
        self.record_display_id = f"record-{self.id}-{self.session_id[:8]}"
        display(Markdown(
            f"# {self.title} — Answer Key\n\n"
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
            display(Markdown(section["markdown"]))
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
        from .problems import _display_id
        lines = [
            "### Answer-key verification",
            "",
            "| Q | Type | Declared correct | Credit | Status | Note |",
            "|---|------|------------------|--------|--------|------|",
        ]
        n_pass = 0
        n_total = 0
        for section in self.sections_in_order:
            if section.get("type") != "problem":
                continue
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
            lines.append(
                f"| {_display_id(pid)} | {qtype} | {','.join(correct) or '—'} "
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
    ) -> None:
        self.scores[pid] = {
            "attempt": attempt,
            "correct": is_correct,
            "credit": credit,
            "locked": locked,
        }
        update_display(
            Markdown(updated_markdown(self)),
            display_id=self.record_display_id,
        )
