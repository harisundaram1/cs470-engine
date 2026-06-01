"""Concept-cell rendering: drives the per-lesson render functions.

Each concept section in the worksheet YAML names a ``render_function`` in
``worksheets/concepts/lesson_NN.py``. The engine loads that module from a
file path (so the worksheets/ tree does not need to be a Python package),
instantiates ipywidgets for each declared control, and re-invokes the
render function on any control change, drawing into a fresh matplotlib
Axes inside an Output widget.

Render-function contract
------------------------
Each render function takes ``(controls, ax)`` and draws into ``ax``. It
may OPTIONALLY return a caption string (Markdown text) that the engine
displays in a separate widget below (or beside, in two-column layout) the
figure. Captions must never be drawn on the axes — they collide with the
graph and force the cell to scroll.

Control kinds and how they become widget instances:

    slider     → IntSlider when ``step`` is an integer >= 1, else FloatSlider
    dropdown   → Dropdown
    button     → widgets.ClickCounterButton (exposes .value = click count)
    checkbox   → Checkbox

The render function reads ``controls['name'].value`` uniformly across kinds.

Layout
------
``section.get("layout")`` chooses how controls, figure, and caption are
arranged. When unspecified, the default depends on whether the cell has
declared controls:

  single_column   — figure / controls / caption stacked vertically.
                    Default when the cell has no controls.
  figure_left     — figure on the left; controls + caption stacked on the
                    right. Default for cells with controls.
  narration_left  — controls + caption on the left, figure on the right.
                    Use for step-walkthrough cells where the narration
                    drives the figure (e.g., Granovetter proof).
"""

import importlib.util
from pathlib import Path

import matplotlib.pyplot as plt
import ipywidgets as widgets
from IPython.display import display, Markdown

from .plot_style import CONTROL_STYLE, FIGURE_STYLE
from .widgets import ClickCounterButton


_LESSON_MODULE_CACHE: dict[str, object] = {}


def _load_lesson_module(module_path: Path):
    """Load worksheets/concepts/lesson_NN.py by file path, cached.

    Loading by path avoids requiring worksheets/ to be a Python package.
    """
    key = str(module_path)
    cached = _LESSON_MODULE_CACHE.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        f"cs470_lesson_{module_path.stem}", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load lesson module at {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _LESSON_MODULE_CACHE[key] = module
    return module


def _make_control(ctl: dict):
    """Instantiate the ipywidget (or wrapper) for one YAML control entry."""
    kind = ctl.get("kind")
    label = ctl.get("label", ctl.get("name", ""))
    full_width = widgets.Layout(width="80%")

    if kind == "slider":
        lo = ctl["min"]
        hi = ctl["max"]
        step = ctl.get("step", 1)
        default = ctl.get("default", lo)
        is_int = (isinstance(step, int) and isinstance(lo, int)
                  and isinstance(hi, int))
        cls = widgets.IntSlider if is_int else widgets.FloatSlider
        return cls(value=default, min=lo, max=hi, step=step,
                   description=label,
                   continuous_update=False,
                   style=CONTROL_STYLE,
                   layout=full_width)

    if kind == "dropdown":
        options = ctl.get("options", [])
        default = ctl.get("default", options[0] if options else None)
        return widgets.Dropdown(options=options, value=default,
                                description=label,
                                style=CONTROL_STYLE,
                                layout=full_width)

    if kind == "button":
        return ClickCounterButton(description=label)

    if kind == "checkbox":
        return widgets.Checkbox(value=ctl.get("default", False),
                                description=label,
                                style=CONTROL_STYLE)

    return None


def _control_widget(ctl_obj):
    """Return the underlying ipywidget for display, unwrapping wrappers."""
    if isinstance(ctl_obj, ClickCounterButton):
        return ctl_obj.widget
    return ctl_obj


def render_concept(ws, section: dict) -> None:
    """Render a concept cell with live controls driving the render function."""
    title = section.get("title", section.get("id", "concept"))
    description = section.get("description_markdown", "")
    takeaway = section.get("takeaway_markdown", "")
    explicit_layout = section.get("layout")
    has_controls = bool(section.get("controls"))
    # Default: figure_left when the cell has live controls; otherwise stack
    # vertically. Explicit `layout:` always wins.
    layout_kind = explicit_layout or (
        "figure_left" if has_controls else "single_column"
    )

    # Title is owned by the `title` field; descriptions are body-only.
    display(Markdown(f"### {title}"))
    if description:
        display(Markdown(description))

    # Build the controls dict and matching widget list.
    controls: dict[str, object] = {}
    control_widgets = []
    for ctl in section.get("controls") or []:
        obj = _make_control(ctl)
        if obj is None:
            continue
        controls[ctl["name"]] = obj
        control_widgets.append(_control_widget(obj))

    fig_out = widgets.Output()
    caption_out = widgets.Output()

    # Resolve the lesson module + render function.
    render_fn = None
    try:
        if ws.concepts_module_path is None or not ws.concepts_module_path.exists():
            raise FileNotFoundError(
                f"Lesson module not found: {ws.concepts_module_path}"
            )
        module = _load_lesson_module(ws.concepts_module_path)
        render_fn = getattr(module, section["render_function"], None)
        if render_fn is None:
            raise AttributeError(
                f"{ws.concepts_module_path.name} has no function "
                f"{section['render_function']!r}"
            )
    except Exception as e:
        display(Markdown(
            f"> *Concept cell unavailable: {e}. "
            f"Continuing with placeholder.*"
        ))

    def _draw():
        caption_text = None
        with fig_out:
            fig_out.clear_output(wait=True)
            fig, ax = plt.subplots(figsize=FIGURE_STYLE["concept_figsize"])
            if render_fn is not None:
                try:
                    result = render_fn(controls, ax)
                    if isinstance(result, str):
                        caption_text = result
                except NotImplementedError as exc:
                    ax.set_axis_off()
                    ax.text(0.5, 0.5,
                            f"render function not yet implemented:\n{exc}",
                            ha="center", va="center", wrap=True)
                except Exception as exc:
                    ax.set_axis_off()
                    ax.text(0.5, 0.5, f"render error: {exc}",
                            ha="center", va="center", wrap=True)
            else:
                ax.set_axis_off()
                ax.text(0.5, 0.5, "no render function available",
                        ha="center", va="center")
            plt.tight_layout()
            display(fig)
            plt.close(fig)
        with caption_out:
            caption_out.clear_output(wait=True)
            if caption_text:
                display(Markdown(caption_text))

    # Wire change observers.
    for obj in controls.values():
        try:
            obj.observe(lambda _change: _draw(), names="value")
        except Exception:
            pass

    # Compose layout.
    if layout_kind == "narration_left":
        left = widgets.VBox(
            control_widgets + [caption_out],
            layout=widgets.Layout(width="42%", padding="0 1em 0 0"),
        )
        right = widgets.VBox(
            [fig_out],
            layout=widgets.Layout(width="58%"),
        )
        display(widgets.HBox([left, right]))
    elif layout_kind == "figure_left":
        left = widgets.VBox(
            [fig_out],
            layout=widgets.Layout(width="60%", padding="0 1em 0 0"),
        )
        right = widgets.VBox(
            control_widgets + [caption_out],
            layout=widgets.Layout(width="40%"),
        )
        display(widgets.HBox([left, right]))
    else:  # single_column
        if control_widgets:
            display(widgets.VBox(control_widgets))
        display(fig_out)
        display(caption_out)

    # Initial render.
    _draw()

    if takeaway:
        display(Markdown(takeaway))
