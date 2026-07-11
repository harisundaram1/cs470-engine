"""Centralized student-facing message tokens.

Per the project rule that copy and style live in one place (not inline in
render functions), the durable-session feature's student-facing strings live
here so wording stays consistent across the notebook intro, the finalize
confirmation, the empty-session guard, and the restored-answer banner.

Also home to the two math/markdown render helpers:
``mathjax_safe_currency`` (the Markdown() prose path) and
``render_option_markdown`` (the HTMLMath option path). They are NOT
interchangeable — see each docstring for its scope.
"""

import re

import markdown as _markdown


def mathjax_safe_currency(md_text: str) -> str:
    r"""Protect an authored literal-currency ``\$`` on the Markdown() path.

    The renderer behind ``IPython.display.Markdown`` is markdown-it
    (CommonMark), which de-escapes a backslash-escaped ASCII punctuation char.
    So an authored ``\$`` (a literal dollar sign in prose — "bidding \$100")
    reaches MathJax as a bare ``$``; MathJax then pairs it with the next ``$``
    and typesets the run between them as math — collapsed-italic, garbled prose.

    Doubling the backslash survives that pass: markdown-it de-escapes ``\\`` to a
    single ``\``, leaving ``\$``, which MathJax renders as a literal ``$``.

    SCOPED to the Markdown() path ONLY. The hint path renders through
    python-markdown + ``HTML()``, which already handles ``\$`` correctly;
    applying this there would double-escape. Real math delimiters (bare
    ``$...$``) are untouched — only the two-character sequence backslash-dollar
    is rewritten, so ``$v$``, ``$r^*$``, ``$-$`` and the rest pass through.
    """
    if not isinstance(md_text, str):
        return md_text
    return md_text.replace(r"\$", r"\\$")


# Math spans are lifted out of an option before the markdown pass and restored
# verbatim after it. Alternation order is load-bearing: a literal-currency ``\$``
# is consumed FIRST, so it can never be mistaken for a math delimiter and open a
# span that swallows the rest of the string.
_MATH_SPAN = re.compile(
    r"\\\$"                     # literal-currency \$
    r"|\$\$.+?\$\$"             # display math
    r"|\$(?:\\.|[^$\\])+?\$",   # inline math
    re.DOTALL,
)

# python-markdown is a *document* renderer: it wraps output in <p>…</p>. An
# option is inline content living inside an HBox row, where a block element
# would contribute paragraph margins. Strip the wrapper when (as for every
# option in the corpus) the whole render is a single paragraph; if it somehow
# isn't, leave the output alone rather than mangling it.
_ONE_PARAGRAPH = re.compile(r"\A<p>(.*)</p>\Z", re.DOTALL)

_MASK_TOKEN = "@@CS470MATH{}@@"
_MASK_RE = re.compile(r"@@CS470MATH(\d+)@@")


def render_option_markdown(text: str) -> str:
    r"""Render markdown in an MC option, leaving its math untouched.

    Options render through ``ipywidgets.HTMLMath`` (HTML + MathJax in the
    browser), which does no markdown — so authored ``*emph*`` / ``**bold**``
    reaches the student as literal asterisks. Adding a naive markdown pass fixes
    that but corrupts math: python-markdown's escapable set is the Markdown.pl
    set, which includes ``{`` and ``}``, and the pass has no concept of math
    mode. So ``$\{A, B\}$`` loses its backslashes, MathJax reads the bare braces
    as TeX *grouping* (which prints nothing), and the set braces silently vanish
    from the answer.

    The fix is to mask ``$…$`` (and ``\$``) out of the string, run markdown over
    the prose that remains, then restore the math verbatim. Markdown never sees
    the math, so ``\{``, ``\$``, ``\tfrac`` and every other TeX escape are
    immune *structurally* — not merely observed-safe on today's corpus, which
    matters because a future option written as ``$\{x\}$`` would otherwise
    reopen the wound silently. This mirrors what JupyterLab's own markdown
    renderer does for prose cells (``removeMath`` → markdown → ``replaceMath``);
    ``HTMLMath`` simply has no equivalent, so the engine supplies it.

    SCOPED to the option path. Do NOT chain ``mathjax_safe_currency`` onto this:
    that helper doubles a backslash to survive markdown-it's CommonMark
    de-escaping on the ``Markdown()`` prose path, whereas python-markdown leaves
    ``\$`` alone — and here the masking makes the point moot anyway. Applying
    both would double-escape and print a stray backslash.
    """
    if not isinstance(text, str) or not text:
        return text

    math = []

    def _stash(m):
        math.append(m.group(0))
        return _MASK_TOKEN.format(len(math) - 1)

    html = _markdown.markdown(_MATH_SPAN.sub(_stash, text))

    unwrapped = _ONE_PARAGRAPH.match(html)
    if unwrapped:
        html = unwrapped.group(1)

    return _MASK_RE.sub(lambda m: math[int(m.group(1))], html)


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
