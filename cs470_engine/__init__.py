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

from importlib.metadata import version, PackageNotFoundError

from .worksheet import Worksheet

__all__ = ["Worksheet"]

# Derive the version from the installed package metadata (pyproject) rather than
# a hand-maintained literal, which had drifted (stale "0.2.1"). This makes
# ``cs470_engine.__version__`` always match the installed wheel — the
# authoritative check when verifying which engine a built image actually runs
# (LESSON_2_DEPLOY.md step 2). Falls back to a sentinel for a source tree with
# no install.
try:
    __version__ = version("cs470-engine")
except PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0+unknown"
