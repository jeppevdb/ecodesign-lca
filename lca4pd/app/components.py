"""Small building blocks shared by the screens."""

from __future__ import annotations

import pandas as pd
import panel as pn

from ..databases import link
from ..model import ValidationError, units
from ..model.classifications import (EN15804_MODULES, GHG_CATEGORIES, PEDIGREE_INDICATORS,
                                     PEDIGREE_LABELS, PEDIGREE_LEVELS)

W = pn.widgets

TABLE_CONFIG = {"columnDefaults": {"headerSort": False}}

# Widgets render in their own shadow DOM, so they are styled through stylesheets.
LINK_STYLE = """
:host .bk-btn { text-align: left; white-space: normal; height: auto; padding: 4px 8px;
                font-size: 12.5px; line-height: 1.35; border: none; background: none;
                color: #1f4e79; justify-content: flex-start; }
:host .bk-btn:hover { text-decoration: underline; background: #e8eff6; }
"""
LEFT_STYLE = ":host .bk-btn { justify-content: flex-start; text-align: left; }"


def heading(text: str, level: int = 3):
    return pn.pane.Markdown(f"{'#' * level} {text}", margin=(10, 10, 0, 10))


def note(text: str):
    return pn.pane.Markdown(text, styles={"color": "#555"}, margin=(0, 10, 5, 10))


def alert(text: str, kind: str = "danger"):
    return pn.pane.Alert(text, alert_type=kind, margin=(5, 10))


def card(title: str, *objects, collapsed: bool = False):
    return pn.Card(*objects, title=title, collapsed=collapsed, collapsible=True,
                   sizing_mode="stretch_width", margin=(5, 5, 15, 5),
                   header_background="#eef4fa")


def confirm_button(label: str, on_confirm, button_type: str = "danger", **kwargs):
    """A button that acts on the second click, so nothing is deleted by accident."""
    button = W.Button(name=label, button_type="default", **kwargs)
    state = {"armed": False}

    def click(event):
        if state["armed"]:
            on_confirm()
        else:
            state["armed"] = True
            button.name, button.button_type = "Click again to confirm", button_type

    button.on_click(click)
    return button


UNANSWERED = ""


def question(options: dict, value, inline: bool = False, unanswered: str = "Not answered yet"):
    """Radio buttons for a question that starts unanswered.

    A plain radio group silently selects its first option; this one shows
    "not answered yet" until the user chooses. Read it with ``answer()``.
    """
    return W.RadioBoxGroup(options={unanswered: UNANSWERED, **options},
                           value=value if value in options.values() else UNANSWERED,
                           inline=inline)


def answer(widget):
    return None if widget.value == UNANSWERED else widget.value


def guarded(session, action, message_area=None):
    """Run a change; show a refused input next to the form instead of failing."""
    try:
        action()
    except (ValidationError, LookupError) as error:
        if message_area is not None:
            message_area[:] = [alert(str(error))]
        else:
            session.error(str(error))
        return False
    if message_area is not None:
        message_area[:] = []
    return True


def table(frame: pd.DataFrame, *, buttons: dict | None = None, hidden=(), height=None,
          selectable=False, widths: dict | None = None, **kwargs):
    widths = {**{name: 46 for name in (buttons or {})}, **(widths or {})}
    return W.Tabulator(
        frame, show_index=False, disabled=True, selectable=selectable,
        buttons=buttons or {}, hidden_columns=list(hidden), widths=widths,
        sizing_mode="stretch_width", configuration=TABLE_CONFIG, height=height,
        layout="fit_columns", **kwargs)


# ------------------------------------------------------------ dataset picker

def dataset_label(session, ref_id) -> str:
    if ref_id is None:
        return "*none chosen*"
    ref = session.project.get_dataset_ref(ref_id)
    place = f", {ref['location']}" if ref["location"] else ""
    gone = " — **no longer in its database**" if ref["missing"] else ""
    return f"**{ref['name']}**{place} (per {ref['unit']}; {ref['database_name']}){gone}"


class DatasetField:
    """A form field holding one dataset, chosen through the search dialog only."""

    def __init__(self, session, *, kind="process", dimension=None, value=None,
                 label="Dataset", on_pick=None):
        self.session, self.kind, self.dimension = session, kind, dimension
        self.value, self.label, self.on_pick = value, label, on_pick
        self._text = pn.pane.Markdown("", margin=(5, 10))
        button = W.Button(name="Search…", button_type="primary", width=110)
        button.on_click(lambda event: self.open())
        self.view = pn.Row(pn.pane.Markdown(f"**{label}**", width=150, margin=(5, 10)),
                           button, self._text)
        self._show()

    def _show(self):
        self._text.object = dataset_label(self.session, self.value)

    def unit(self) -> str | None:
        if self.value is None:
            return None
        return self.session.project.get_dataset_ref(self.value)["unit"]

    def set(self, ref_id):
        self.value = ref_id
        self._show()
        if self.on_pick:
            self.on_pick(ref_id)

    def open(self):
        open_dataset_picker(self.session, self.set, kind=self.kind, dimension=self.dimension,
                            title=self.label)


def open_dataset_picker(session, on_pick, *, kind="process", dimension=None,
                        title="Choose a dataset"):
    project, library = session.project, session.library
    databases = {db["name"]: db for db in project.list_databases()
                 if db["kind"] == kind and library.has(db["file_hash"])}
    what = "impact factors" if kind == "process" else "elementary flows"
    if not databases:
        session.open_modal(pn.Column(
            heading(title), alert(f"No database with {what} is loaded for this project. "
                                  "Add one in the step 'Databases' first.", "warning")))
        return

    search = W.TextInput(placeholder="Type words from the name, place or category…",
                         sizing_mode="stretch_width")
    chosen = W.MultiChoice(name="Databases", options=list(databases), value=list(databases),
                           sizing_mode="stretch_width")
    columns = ["name", "location", "unit", "category", "database_name"]
    results = table(pd.DataFrame(columns=columns), selectable=1, height=380,
                    titles={"database_name": "database", "category": "group"},
                    widths={"name": "45%"})
    info = pn.pane.Markdown("", margin=(0, 10))
    select = W.Button(name="Use selected dataset", button_type="primary", disabled=True)
    found: list[dict] = []

    def run(*events):
        hashes = [databases[name]["file_hash"] for name in chosen.value]
        found[:] = library.search(search.value_input or "", kind=kind, dimension=dimension,
                                  databases=hashes, limit=200)
        results.selection = []
        results.value = pd.DataFrame([{c: item[c] for c in columns} for item in found],
                                     columns=columns)
        limit = " (first 200 shown – add words to narrow down)" if len(found) == 200 else ""
        only = f" Only datasets per {dimension} unit are listed." if dimension else ""
        info.object = f"{len(found)} found{limit}.{only}"

    def selection_changed(event):
        select.disabled = not results.selection

    def use(event):
        item = found[results.selection[0]]
        database = next(db for db in databases.values() if db["file_hash"] == item["file_hash"])
        ref_id = link.pick(project, library, database["id"], item["key"])
        session.close_modal()
        on_pick(ref_id)

    search.param.watch(run, "value_input")
    chosen.param.watch(run, "value")
    results.param.watch(selection_changed, "selection")
    select.on_click(use)
    run()
    session.open_modal(pn.Column(heading(title), search, chosen, info, results, select,
                                 sizing_mode="stretch_width"))


# ------------------------------------------------------- optional fields

class ClassificationFields:
    """Pedigree scores, GHG Protocol category and EN 15804 module – only those switched on."""

    def __init__(self, session, record: dict | None = None):
        toggles, record = session.project.toggles, record or {}
        self.widgets: dict[str, object] = {}
        rows = []
        if toggles["ghg_protocol"]:
            self.widgets["ghg_category"] = W.Select(
                name="GHG Protocol category",
                options={"(not set)": "", **{label: code for code, label in GHG_CATEGORIES.items()}},
                value=record.get("ghg_category") or "", width=380)
            rows.append(self.widgets["ghg_category"])
        if toggles["en15804"]:
            self.widgets["en15804_module"] = W.Select(
                name="EN 15804 module",
                options={"(not set)": "", **{label: code for code, label in EN15804_MODULES.items()}},
                value=record.get("en15804_module") or "", width=380)
            rows.append(self.widgets["en15804_module"])
        if toggles["uncertainty"]:
            rows.append(pn.pane.Markdown("**Data quality (pedigree matrix)**", margin=(10, 10, 0, 10)))
            for indicator in PEDIGREE_INDICATORS:
                options = {"(not scored)": 0}
                for score, text in enumerate(PEDIGREE_LEVELS[indicator], start=1):
                    options[f"{score} – {text}"] = score
                widget = W.Select(name=PEDIGREE_LABELS[indicator], options=options,
                                  value=record.get(f"ped_{indicator}") or 0,
                                  sizing_mode="stretch_width")
                self.widgets[f"ped_{indicator}"] = widget
                rows.append(widget)
        self.view = pn.Column(*rows, sizing_mode="stretch_width") if rows else None

    def values(self) -> dict:
        return {name: widget.value or None for name, widget in self.widgets.items()}


def unit_select(unit: str | None, value: str | None = None, name: str = "Unit"):
    options = units.alternatives(unit) if unit else []
    current = units.canonical(value) if value else (units.canonical(unit) if unit else None)
    if current and current not in options:
        options = [current, *options]
    return W.Select(name=name, options=options, value=current, width=110, disabled=not options)


class ParameterField:
    """'Affected by': which scenario parameters act on an amount, weight or price.

    Shown only when scenarios are switched on. Parameters are picked from the
    existing ones; they are defined in the step 'Scenarios'.
    """

    def __init__(self, session, target_type: str, target_id=None, label="Affected by"):
        project = session.project
        self.session, self.target_type = session, target_type
        self.widget, self.view = None, None
        if not project.toggles["scenarios"]:
            return
        scenarios = {s["id"]: s["name"] for s in project.list_scenarios()}
        options = {f"{scenarios[p['scenario_id']]} – {p['name']}": p["id"]
                   for p in project.list_parameters()}
        if not options:
            self.view = note(f"*{label}:* no scenario parameters are defined yet "
                             "(step 'Scenarios').")
            return
        current = project.links_for(target_type, target_id) if target_id else []
        self.widget = W.MultiChoice(name=f"{label} (scenario parameters)", options=options,
                                    value=current, sizing_mode="stretch_width",
                                    placeholder="none – the same in best, average and worst case")
        self.view = self.widget

    def save(self, target_id: int) -> None:
        if self.widget is not None:
            self.session.project.set_links(self.target_type, target_id, self.widget.value)
