"""cs470_engine v0.1 — minimum viable engine for CS 470 worksheets.

v0.1 scope:
  - Single-select MC problems with time-gated submission.
  - In-memory score tracking.
  - Markdown record cell that persists via cell output across save/reload.

Stubbed and slated for later engine releases:
  - Concept-cell interactive widgets (require per-lesson render functions).
  - Multi-select MC and partial credit.
  - Drive auto-save and crash-recovery persistence.
  - Gradescope / PrairieLearn submission backends.
"""

from .worksheet import Worksheet

__all__ = ["Worksheet"]
__version__ = "0.1.0"
