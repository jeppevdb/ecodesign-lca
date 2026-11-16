"""Step: calculate. Only possible once nothing is missing."""

import asyncio

import pandas as pd
import panel as pn

from ...calculation import Results, calculate
from ...method import ef31
from ..components import W, alert, card, heading, note, table


def build(session):
    project = session.project
    body = pn.Column(sizing_mode="stretch_width")
    busy = pn.indicators.LoadingSpinner(value=False, size=30, visible=False)

    def show_results(results: Results):
        totals = results.totals()
        main = totals[totals["varied_scenario"].isna()]
        climate = ef31.BY_ID["climate_change"]
        frame = pd.DataFrame({
            "Design": main["design"], "Scenario setting": main["setting"],
            "Market": main["market"],
            f"Climate change ({climate.unit})": main["climate_change"].map("{:.4g}".format),
            "Single score (mPt)": (main["single_score"] * 1000).map("{:.4g}".format),
        })
        warnings = [alert(text, "warning") for text in results.scenario_direction_warnings()]
        current = results.is_current(project)
        state = (alert("These results are up to date.", "success") if current else
                 alert("The project has changed since these results were calculated. "
                       "Calculate again to update them.", "warning"))
        return card("Results per product", state, *warnings,
                    table(frame, height=min(40 + 32 * len(frame), 420)),
                    note(f"{len(results.inventory):,} inventory rows calculated. The full report "
                         "is the next part of the tool to be built; until then this table shows "
                         "the totals."))

    def show():
        issues = session.issues()
        blockers = [i for i in issues if i.severity == "blocker"]
        objects = [heading("Calculate")]
        button = W.Button(name="Calculate now", button_type="primary", width=180,
                          disabled=bool(blockers))
        if blockers:
            objects.append(alert(
                f"{len(blockers)} item(s) are still needed before the project can be calculated. "
                "They are listed on the left; click one to go to where it is fixed. Anything that "
                "cannot be filled in can be recorded as a documented exclusion.", "warning"))
        else:
            objects.append(note("Everything needed is filled in. The calculation covers every "
                                "design, scenario setting and market."))

        async def run(event):
            busy.visible = busy.value = True
            button.disabled = True
            try:
                results = await asyncio.to_thread(calculate, project, session.library)
                results.save(session.results_path)
            except Exception as error:
                body.append(alert(f"The calculation failed: {error}"))
                return
            finally:
                busy.visible = busy.value = False
            show()

        button.on_click(run)
        objects.append(pn.Row(button, busy))
        path = session.results_path
        if path is not None and path.exists():
            try:
                objects.append(show_results(Results.load(path)))
            except Exception as error:
                objects.append(alert(f"Saved results could not be opened: {error}", "warning"))
        body[:] = objects

    session.on_change(show)
    show()
    return body
