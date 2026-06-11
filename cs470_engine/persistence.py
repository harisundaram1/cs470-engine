"""Durable per-worksheet session state.

The PrairieLearn workspace *filesystem* persists across kernel restarts and
workspace reopens — only the Python kernel resets. So a JSON file on disk is a
durable store: if we write the per-problem record through on every submit, a
student who reopens the workspace (or whose kernel times out) can restore their
answers instead of finalizing an empty ``results.json`` -> 0%.

``SessionStore`` writes ``<worksheet_id>_session.json`` to the same durable
location the results file lands in:

  - PrairieLearn workspace (``PL_WORKSPACE=1``): the home dir that holds
    ``results.json`` (``CS470_RESULTS_PATH``'s parent), so it persists with the
    workspace.
  - Local: beside the notebook (cwd), like the local results file.

The file is identity-free (no NetID) — same FERPA rule as ``results.json``. It
carries only the per-problem record and the session id.

Backward compatibility: this is purely additive. A worksheet run that never
reopens behaves exactly as before — the store is written through on each submit
and simply never read back. ``InMemoryPersistence`` (the v0.1 no-op) is kept as
an alias so any older import path still resolves.
"""

import json
import os
from pathlib import Path


# Bump if the session-file shape changes so a stale file from an older engine
# is ignored rather than mis-read.
SESSION_SCHEMA_VERSION = 1


def _durable_dir() -> Path:
    """The directory the session file lives in — matches where results.json goes.

    In a PL workspace, that is the parent of ``CS470_RESULTS_PATH`` (default
    ``/home/jovyan``), which persists across kernel restarts. Locally it is the
    current working directory (beside the notebook).
    """
    if os.environ.get("PL_WORKSPACE") == "1":
        results_path = Path(
            os.environ.get("CS470_RESULTS_PATH", "/home/jovyan/results.json")
        )
        return results_path.parent
    return Path.cwd()


def session_path(worksheet_id: str, dest_dir: Path | None = None) -> Path:
    """Path to the durable session file for ``worksheet_id``."""
    base = Path(dest_dir) if dest_dir is not None else _durable_dir()
    return base / f"{worksheet_id}_session.json"


class SessionStore:
    """Write-through store for a worksheet's per-problem record.

    One instance per ``Worksheet``. ``save`` is called on every submit (cheap —
    a small JSON write); ``load_state`` is called once at ``Worksheet.load``.
    """

    def __init__(self, worksheet_id: str, dest_dir: Path | None = None):
        self.worksheet_id = worksheet_id
        self.path = session_path(worksheet_id, dest_dir)

    def save(self, *, session_id: str | None, scores: dict) -> None:
        """Write the current record through to disk. Best-effort: a write
        failure (e.g. read-only fs) must never break the live submit flow, so
        it is swallowed — the in-memory record is still authoritative for this
        session."""
        payload = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "worksheet_id": self.worksheet_id,
            "session_id": session_id,
            "scores": scores,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, indent=2))
        except Exception:
            pass

    def load_state(self) -> dict | None:
        """Return the stored ``{session_id, scores}`` for this worksheet, or
        None if there is no usable file. A file for a different worksheet id, a
        future/unknown schema, or unparsable JSON is treated as absent (None) so
        a stale or foreign file can never corrupt a fresh session."""
        try:
            if not self.path.exists():
                return None
            data = json.loads(self.path.read_text())
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        if data.get("worksheet_id") != self.worksheet_id:
            return None
        if data.get("schema_version") != SESSION_SCHEMA_VERSION:
            return None
        scores = data.get("scores")
        if not isinstance(scores, dict):
            return None
        return {"session_id": data.get("session_id"), "scores": scores}


# Backward-compatible alias: the v0.1 no-op persistence. Kept so any older
# import (``from .persistence import InMemoryPersistence``) still resolves.
class InMemoryPersistence:
    """No-op persistence (v0.1). Superseded by SessionStore; retained for
    import compatibility only."""

    def save(self, key: str, payload: dict) -> None:
        return None

    def load(self, key: str):
        return None
