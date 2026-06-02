"""Submission backends.

At finalize(), the worksheet builds an identity-free ``results`` payload
from the in-memory per-problem scores and hands it to a backend that
decides *where* it lands:

  - ``LocalDownloadBackend`` (default) writes ``<id>_results.json`` next to
    the notebook for manual download/upload.
  - ``PrairieLearnBackend`` (active when ``PL_WORKSPACE=1`` is set in the
    workspace container) writes ``results.json`` to ``/home/jovyan`` so
    PrairieLearn collects it via the question's ``gradedFiles``.

Backend selection is by the ``PL_WORKSPACE`` environment variable, set in
the PrairieLearn workspace Docker image. Locally that variable is unset, so
existing local behavior (a downloadable JSON) is preserved.

The payload carries no NetID — identity is bound server-side by the upload
destination, per the project's FERPA rule.
"""

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

from IPython.display import display, Markdown

# Bump when the results.json shape changes so graders can branch on it.
RESULTS_SCHEMA_VERSION = 1


class SubmitBackend(ABC):
    """Where a finalized results payload is written, and how the student is
    told to submit it."""

    @abstractmethod
    def emit_results(self, results: dict, dest_dir: Path) -> Path:
        """Write ``results`` somewhere durable and return the path written."""

    @abstractmethod
    def submission_instructions(self) -> str:
        """One short Markdown sentence telling the student how to submit."""


class LocalDownloadBackend(SubmitBackend):
    """Default backend: write ``<id>_results.json`` into the notebook's
    working directory for manual download and upload."""

    def emit_results(self, results: dict, dest_dir: Path) -> Path:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / f"{results['worksheet_id']}_results.json"
        out.write_text(json.dumps(results, indent=2))
        return out

    def submission_instructions(self) -> str:
        return (
            "A results file was written next to this notebook. Download it "
            "and upload it to the course submission page to record your "
            "participation credit."
        )


class PrairieLearnBackend(SubmitBackend):
    """PrairieLearn Workspace backend: write ``results.json`` to the
    workspace home so PL collects it via ``gradedFiles: [\"results.json\"]``."""

    RESULTS_PATH = Path(
        os.environ.get("CS470_RESULTS_PATH", "/home/jovyan/results.json")
    )

    def emit_results(self, results: dict, dest_dir: Path) -> Path:
        # dest_dir is ignored: PL collects from a fixed path in the home dir.
        out = self.RESULTS_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2))
        return out

    def submission_instructions(self) -> str:
        return (
            "Click **Save & Grade** above the workspace to submit. "
            "PrairieLearn will read your results and record your "
            "participation credit automatically."
        )


def select_backend() -> SubmitBackend:
    """Choose a backend from the environment. ``PL_WORKSPACE=1`` (set in the
    PrairieLearn workspace image) selects PrairieLearn; otherwise local."""
    if os.environ.get("PL_WORKSPACE") == "1":
        return PrairieLearnBackend()
    return LocalDownloadBackend()


def build_results(ws) -> dict:
    """Assemble the identity-free results payload from ``ws.scores``.

    Mirrors the running-total math in ``record.updated_markdown``: a problem
    with no recorded answer counts toward ``total_possible`` at zero credit,
    and ``passed_threshold`` is ``fraction >= ws.pass_threshold``.
    """
    problems: dict[str, dict] = {}
    total_credit = 0.0
    total_possible = 0
    answered = 0

    for section in ws.worksheet["sections"]:
        if section.get("type") != "problem":
            continue
        pid = section["id"]
        total_possible += 1
        entry = ws.scores.get(pid)
        if entry is None:
            problems[pid] = {
                "answered": False,
                "attempt": 0,
                "credit": 0.0,
                "locked": False,
            }
            continue
        answered += 1
        credit = float(entry.get("credit", 0.0))
        total_credit += credit
        # Note: per-problem `correct` is deliberately omitted — this is a
        # participation grade, so results.json must not reveal which
        # problems the student got right.
        problems[pid] = {
            "answered": True,
            "attempt": entry.get("attempt", 0),
            "credit": credit,
            "locked": bool(entry.get("locked", False)),
        }

    fraction = (total_credit / total_possible) if total_possible else 0.0
    return {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "worksheet_id": ws.id,
        "session_id": ws.session_id,
        "problems": problems,
        "summary": {
            "answered": answered,
            "total_problems": total_possible,
            "total_credit": round(total_credit, 4),
            "total_possible": float(total_possible),
            "fraction": round(fraction, 4),
            "pass_threshold": ws.pass_threshold,
            "passed_threshold": bool(fraction >= ws.pass_threshold),
        },
    }


def finalize(ws) -> None:
    """Build the results payload, emit it through the selected backend, and
    show the student a short confirmation with submission instructions."""
    results = build_results(ws)
    backend = select_backend()
    out = backend.emit_results(results, Path.cwd())

    s = results["summary"]
    status = "✓ above" if s["passed_threshold"] else "✗ below"
    display(Markdown(
        f"### Submission · {ws.id}\n\n"
        f"**{s['total_credit']:.2f} / {s['total_possible']:.0f}** "
        f"({s['fraction'] * 100:.1f}%) — {status} the "
        f"{int(ws.pass_threshold * 100)}% participation threshold.\n\n"
        f"Results written to `{out}`.\n\n"
        f"{backend.submission_instructions()}"
    ))


# Backward-compatible alias: the v0.1 build emitted a call path through
# ``finalize_stub``. Keep it pointing at the real implementation so older
# built notebooks still finalize correctly.
def finalize_stub(ws) -> None:
    finalize(ws)
