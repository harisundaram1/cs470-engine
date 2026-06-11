"""Centralized student-facing message tokens.

Per the project rule that copy and style live in one place (not inline in
render functions), the durable-session feature's student-facing strings live
here so wording stays consistent across the notebook intro, the finalize
confirmation, the empty-session guard, and the restored-answer banner.
"""

# Shown in the session-start framing (Worksheet.start) and reinforced in the
# worksheet intro: how answers get recorded, and what to do after a reopen.
RECORD_INSTRUCTIONS_MD = (
    "**Recording your answers.** Submit each problem as you go. Your answers are "
    "saved to the workspace as you submit, *and* the running record at the bottom "
    "of the notebook keeps your progress. When you finish, run the last two cells "
    "— **`show_record()`** and **`finalize()`** — to record your participation. "
    "**If you reopened this workspace** (or the kernel restarted), use "
    "**Kernel → Restart Kernel and Run All Cells** before finalizing, so every "
    "answer is reloaded."
)

# Shown when a problem cell is re-rendered after the kernel reset but the answer
# was restored from the durable session file.
RESTORED_ANSWER_BANNER_MD = (
    "_Restored from your earlier session — already answered. Your recorded credit "
    "is shown below; you don't need to redo this problem._"
)

# The empty-session guard in finalize(): about to write 0 answered. Loud, with
# the concrete fix.
EMPTY_SESSION_GUARD_MD = (
    "### ⚠️ Nothing recorded yet — did you reopen the workspace?\n\n"
    "**0 of {total} problems are answered in this session.** Finalizing now would "
    "record a score of **0%**.\n\n"
    "If you already answered earlier and reopened the workspace (or the kernel "
    "timed out), your answers are saved on disk but this fresh kernel hasn't "
    "reloaded them. **Before finalizing:** run **Kernel → Restart Kernel and Run "
    "All Cells**, which reloads your saved answers, then run `finalize()` again.\n\n"
    "If you genuinely haven't answered anything yet, go answer the problems first."
)

# Appended to the finalize confirmation when the session was restored from disk,
# so the student understands the score reflects reloaded answers.
RESTORED_SESSION_NOTE_MD = (
    "_Your answers were restored from a previous session on this workspace._"
)

# Header note on the answer-key verification table, so a reviewer doesn't read
# the canonical 'a'-first ordering as evidence that the per-student shuffle is
# missing — the live worksheet shuffles; this QA view is intentionally canonical.
ANSWER_KEY_SHUFFLE_NOTE_MD = (
    "_Live worksheet shuffles option order per student; this table shows the "
    "canonical (authored) order._"
)

# finalize() submission instructions — ENVIRONMENT-AWARE, one per backend.
#
# In the PrairieLearn workspace, results.json is auto-collected from the
# workspace (the question's gradedFiles) and graded when the student clicks
# Save & Grade on the PL question page — there is NO separate upload page. The
# pre-persistence wording below is the correct PL instruction.
#
# The local backend (running the notebook outside PL) must NOT tell the student
# to upload anything to a submission page — there isn't one. (The earlier
# "download it and upload it to the course submission page" wording was wrong
# for the PL flow and is removed.)
SUBMIT_INSTRUCTIONS_PL_MD = (
    "✅ Your work is saved. **One more step**: leave this workspace, return to "
    "the PrairieLearn question page (the tab you came from), and click the blue "
    "**Save & Grade** button. Your participation isn't recorded until you do."
)

SUBMIT_INSTRUCTIONS_LOCAL_MD = (
    "**Local run** — the results file was written next to this notebook (path "
    "above). In PrairieLearn you would return to the question page and click "
    "**Save & Grade** to record participation."
)
