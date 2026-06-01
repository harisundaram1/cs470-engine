"""Persistence backends — v0.1 stub (in-memory only).

The student's permanent record in v0.1 is the rendered-output Markdown
cell from record.py, which Jupyter preserves on save. No JSON autosave,
no Drive mount, no PrairieLearn workspace write.
"""


class InMemoryPersistence:
    """No-op persistence. v0.1 holds the record in the running Python
    process only; reopening the saved notebook restores the visible record
    (via cell output) but not the live widget state.
    """

    def save(self, key: str, payload: dict) -> None:
        return None

    def load(self, key: str):
        return None
