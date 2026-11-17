"""Step: the full LCI overview – everything at once, as entered and as calculated."""

import asyncio

import pandas as pd
import panel as pn

from ...calculation import Results, calculate
from ...method import ef31
from ...model import ValidationError
from ...model.classifications import EN15804_MODULES, GHG_CATEGORIES
from ...model.overview import apply_edit, choices, editable_columns, entered_table, to_xlsx
from ..components import W, alert, note, open_dataset_picker

_GROUPS = ["(no grouping)", "Element", "Alternative", "Kind", "Stage", "Dataset", "Database",
           "GHG category", "EN 15804 module"]
_DATASET_KIND = {"production_input": "process", "production_waste": "process",
                 "production_emission": "flow"}


def _entered(session):
    project = session.project
    editable = editable_columns(project)
    messages = pn.Column()
    holder = pn.Column(sizing_mode="stretch_width")
    group = W.Select(name="Group by", options=_GROUPS, width=200)
    state = {"frame": None, "grid": None}

    def make_grid():
        frame = entered_table(project)
        state["frame"] = frame
        editors = {}
        for column in frame.columns:
            if column not in editable:
                editors[column] = None
                continue
            values = choices(project, column)
            if values is not None:
                editors[column] = {"type": "list", "values": values}
            elif column == "Amount":
                editors[column] = {"type": "number"}
            else:
                editors[column] = {"type": "input"}
        groupby = [group.value] if group.value in frame.columns else []
        grid = W.Tabulator(
            frame, show_index=False, hidden_columns=["id"], editors=editors,
            selectable="checkbox", header_filters=True, groupby=groupby,
            buttons={"open": "↗", "dataset": "🔍"}, widths={"open": 44, "dataset": 44},
            titles={"open": " ", "dataset": " "},
            sizing_mode="stretch_width", height=560, layout="fit_data_fill",
            frozen_columns=["Element"])

        def entry_id(row: int) -> int:
            return int(state["frame"].iloc[row]["id"])

        def edited(event):
            try:
                apply_edit(project, entry_id(event.row), event.column, event.value)
            except (ValidationError, LookupError) as error:
                messages[:] = [alert(f"Not changed: {error}")]
                grid.patch({event.column: [(event.row, event.old)]}, as_index=False)
                return
            messages[:] = []
            state["frame"].iat[event.row, state["frame"].columns.get_loc(event.column)] = event.value
            session.changed()

        def clicked(event):
            if event.column == "open":
                entry = project.get_entry(entry_id(event.row))
                session.goto("tree", node=entry["node_id"], entry=entry["id"])
            elif event.column == "dataset":
                entry = project.get_entry(entry_id(event.row))
                kind = _DATASET_KIND.get(entry["type"])
                if kind is None:
                    messages[:] = [alert(
                        "The dataset of this kind of entry is changed in its entry form "
                        "(use the ↗ button).", "info")]
                    return

                def picked(ref_id, entry=entry):
                    try:
                        project.update_entry(entry["id"], dataset_ref_id=ref_id)
                    except (ValidationError, LookupError) as error:
                        messages[:] = [alert(f"Not changed: {error}")]
                        return
                    messages[:] = []
                    session.changed()
                    show()

                open_dataset_picker(session, picked, kind=kind, title="Choose another dataset")

        grid.on_edit(edited)
        grid.on_click(clicked)
        state["grid"] = grid
        return grid

    # ---- bulk edit
    bulk_columns = [c for c in editable if choices(project, c) is not None]
    bulk_field = W.Select(name="Set for all ticked rows", options=bulk_columns, width=230)
    bulk_value = W.Select(name="to", width=330)
    bulk_apply = W.Button(name="Apply to ticked rows", button_type="primary", width=190)

    def bulk_options(*events):
        column = bulk_field.value
        values = choices(project, column) or []
        labels = {}
        for value in values:
            if value == "":
                labels["(empty)"] = ""
            elif column == "GHG category":
                labels[GHG_CATEGORIES[value]] = value
            elif column == "EN 15804 module":
                labels[EN15804_MODULES[value]] = value
            else:
                labels[str(value)] = value
        bulk_value.options = labels
        bulk_value.value = next(iter(labels.values()), None)

    def apply_bulk(event):
        grid = state["grid"]
        rows = list(grid.selection)
        if not rows:
            messages[:] = [alert("Tick the rows to change first.", "info")]
            return
        refused = []
        for row in rows:
            record = state["frame"].iloc[row]
            try:
                apply_edit(project, int(record["id"]), bulk_field.value, bulk_value.value)
            except (ValidationError, LookupError) as error:
                refused.append(f"{record['Element']} – {record['Description'] or record['Kind']}: "
                               f"{error}")
        session.changed()
        show()
        changed = len(rows) - len(refused)
        text = f"{changed} row(s) changed."
        if refused:
            text += " Not changed:\n\n- " + "\n- ".join(refused)
        messages[:] = [alert(text, "warning" if refused else "success")]

    bulk_field.param.watch(bulk_options, "value")
    bulk_apply.on_click(apply_bulk)
    if bulk_columns:
        bulk_options()

    download = W.FileDownload(
        callback=lambda: to_xlsx({"As entered": entered_table(project).drop(columns="id")}),
        filename="lci_as_entered.xlsx", label="Export to Excel", button_type="default", width=170)

    def show(*events):
        holder[:] = [make_grid()]

    group.param.watch(show, "value")
    show()
    bulk_row = [pn.Row(bulk_field, bulk_value, pn.Column(pn.Spacer(height=15), bulk_apply))] \
        if bulk_columns else []
    return pn.Column(
        note("Every entry of the project. Cells in the columns "
             + ", ".join(f"**{c}**" for c in editable) +
             " can be changed here, with the same checks as in the forms. Type in the boxes "
             "under the headings to filter, click a heading to sort. ↗ opens the entry form, "
             "🔍 chooses another dataset. Elements are added and moved in the tree."),
        pn.Row(group, pn.Column(pn.Spacer(height=15), download)), *bulk_row, messages, holder,
        sizing_mode="stretch_width")


def _calculated(session):
    project = session.project
    body = pn.Column(sizing_mode="stretch_width")
    busy = pn.indicators.LoadingSpinner(value=False, size=30, visible=False)
    blockers = [i for i in session.issues() if i.severity == "blocker"]
    if blockers:
        return pn.Column(alert(
            f"The calculated inventory is available once nothing is missing "
            f"({len(blockers)} item(s) still open, see the list on the left).", "warning"))

    cache = session.__dict__.setdefault("calculated", {})

    async def results() -> Results:
        path = session.results_path
        if cache.get("results") is not None and cache["results"].is_current(project):
            return cache["results"]
        if path is not None and path.exists():
            saved = Results.load(path)
            if saved.is_current(project):
                cache["results"] = saved
                return saved
        fresh = await asyncio.to_thread(calculate, project, session.library)
        fresh.save(path)
        cache["results"] = fresh
        return fresh

    designs = [d["name"] for d in project.list_designs()] if project.toggles["alternatives"] \
        else ["Base design"]
    settings = ["average", "best", "worst"] if project.toggles["scenarios"] else ["average"]
    markets = [m["name"] for m in project.list_markets()]
    design = W.Select(name="Design", options=designs, width=260)
    setting = W.Select(name="Scenario setting", options=settings, width=170)
    market = W.Select(name="Market", options=markets, width=170)
    holder = pn.Column(sizing_mode="stretch_width")
    climate = ef31.BY_ID["climate_change"]
    state = {}

    def columns(rows: pd.DataFrame, everything: bool) -> pd.DataFrame:
        frame = pd.DataFrame({
            "Element": rows["path"], "Part of": rows["source"].map({
                "entry": "entry", "supplier_transport": "transport from supplier",
                "distribution": "distribution", "end_of_life": "end-of-life"}),
            "Stage": rows["stage"], "Description": rows["description"],
            "Dataset": rows["dataset"], "Database": rows["database"],
            "Amount": rows["amount"], "Unit": rows["unit"],
        })
        if everything:
            for category in ef31.CATEGORIES:
                frame[f"{category.name} ({category.unit})"] = rows[category.id]
            frame["Single score (Pt)"] = rows["single_score"]
        else:
            frame[f"Climate change ({climate.unit})"] = rows["climate_change"]
            frame["Single score (mPt)"] = rows["single_score"] * 1000
        return frame

    async def show(*events):
        busy.visible = busy.value = True
        try:
            found = await results()
        except Exception as error:
            holder[:] = [alert(f"The calculation failed: {error}")]
            return
        finally:
            busy.visible = busy.value = False
        rows = found.view(design=design.value, setting=setting.value, market=market.value)
        state["rows"] = rows
        frame = columns(rows, everything=False)
        grid = W.Tabulator(
            frame, show_index=False, disabled=True, header_filters=True,
            sizing_mode="stretch_width", height=560, layout="fit_data_fill",
            frozen_columns=["Element"])
        total = rows["climate_change"].sum()
        holder[:] = [
            note(f"{len(rows)} rows, all scaled to one product. Total climate change: "
                 f"**{total:.4g} {climate.unit}**; single score: "
                 f"**{rows['single_score'].sum() * 1000:.4g} mPt**."), grid]

    download = W.FileDownload(
        callback=lambda: to_xlsx({"As calculated": columns(state["rows"], everything=True)}),
        filename="lci_as_calculated.xlsx", label="Export to Excel (all impact categories)",
        button_type="default", width=300)
    async def changed(event):
        if "rows" in state:          # only once a table is being shown
            await show()

    for widget in (design, setting, market):
        widget.param.watch(changed, "value")
    start = W.Button(name="Show", button_type="primary", width=100)
    start.on_click(show)
    holder[:] = [note("Choose what to look at and click **Show**. If the project changed since "
                      "the last calculation, it is calculated again first.")]
    body[:] = [
        note("The full inventory behind one result: every entry and every transport and "
             "end-of-life step, with quantities multiplied through the tree. Read-only."),
        pn.Row(design, setting, market, pn.Column(pn.Spacer(height=15), pn.Row(start, busy)),
               pn.Column(pn.Spacer(height=15), download)), holder]
    return body


def build(session):
    if session.project.root() is None:
        return alert("There is nothing to show yet: add the product in the step "
                     "'Product and entries' first.", "info")
    return pn.Tabs(("As entered", _entered(session)), ("As calculated", _calculated(session)),
                   dynamic=True, sizing_mode="stretch_width")
