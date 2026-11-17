"""Step: the report, built from the saved results."""

import panel as pn

from ...calculation import Results
from ...report.views import build_report
from ..components import W, alert, note


def build(session):
    path = session.results_path
    if path is None or not path.exists():
        go = W.Button(name="Go to Calculate", button_type="primary", width=170)
        go.on_click(lambda event: session.goto("calculate"))
        return pn.Column(alert("There are no results yet. Calculate the project first; the "
                               "report is built from the results.", "info"), go)
    try:
        results = Results.load(path)
    except Exception as error:
        return alert(f"The saved results could not be opened: {error}")
    parts = []
    if not results.is_current(session.project):
        go = W.Button(name="Calculate again", button_type="primary", width=170)
        go.on_click(lambda event: session.goto("calculate"))
        parts.append(pn.Row(alert("The project has changed since these results were "
                                  "calculated. The report shows the last results.", "warning"),
                            go))
    if "toggles" not in results.meta:
        return alert("These results were calculated with an earlier version of the tool. "
                     "Calculate again to see them in the report.", "warning")
    parts.append(build_report(results))
    parts.append(note(f"Results file: `{path.name}`"))
    return pn.Column(*parts, sizing_mode="stretch_width")
