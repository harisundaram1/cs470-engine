"""Submission backends — v0.1 stub.

Final submission (Gradescope or PrairieLearn) is deferred until after the
platform decision in August. v0.1 only emits a placeholder message at
finalize().
"""

from IPython.display import display, Markdown


def finalize_stub(ws) -> None:
    display(Markdown(
        f"### Submission · {ws.id}\n\n"
        "*v0.1 stub: no results file produced. Submission backends will "
        "land alongside the Colab-vs-PrairieLearn platform decision.*"
    ))
