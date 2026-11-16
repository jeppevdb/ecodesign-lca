"""Entries of one element: choose the kind of entry, then fill in its own form."""

import pandas as pd
import panel as pn

from ...model.classifications import ENTRY_TYPE_LABELS
from ..components import (ClassificationFields, DatasetField, W, alert, guarded, note, table,
                          unit_select)

_HELP = {
    "production_input": "A material, component, energy or service that goes into making this "
                        "element. Mark it as a raw material or as manufacturing.",
    "production_waste": "Waste from making this element, sent to a treatment.",
    "production_emission": "A substance released directly while making this element.",
    "use": "Something this element consumes or emits while the product is used, over the whole "
           "service life.",
    "cost": "A cost that belongs to this element itself, such as assembly labour, so that the "
            "prices of its parts add up to its own price.",
    "exclusion": "Something knowingly left out. It is not calculated but is listed in the report.",
}
_BOX = {"background": "#f7f9fb", "border": "1px solid #d0d7de", "border-radius": "6px",
        "padding": "8px"}


def entry_form(session, node_id: int, entry_type: str, entry: dict | None, on_done):
    project = session.project
    entry = entry or {}
    editing = bool(entry.get("id"))
    markets = project.list_markets()
    stages = project.list_stages()
    local = pn.Column()
    widgets: dict = {}
    parts: list = [note(_HELP[entry_type])]

    description = W.TextInput(
        name="What is excluded" if entry_type == "exclusion" else "Description",
        value=entry.get("description") or "", sizing_mode="stretch_width")
    parts.append(description)

    unit_holder = pn.Row()
    state = {"unit": None}

    def set_unit(dataset_unit, current=None):
        widget = unit_select(dataset_unit, current)
        state["unit"] = widget
        unit_holder[:] = [widget]

    # ---- life-cycle stage
    stage = None
    if entry_type.startswith("production_"):
        allowed = [s for s in stages if s["role"] in ("raw_materials", "manufacturing", None)]
        default = entry.get("stage_id")
        if default is None and entry_type != "production_input":
            default = next((s["id"] for s in allowed if s["role"] == "manufacturing"), None)
        stage = W.RadioBoxGroup(options={s["name"]: s["id"] for s in allowed}, value=default,
                                inline=True)
        parts.append(pn.Column(pn.pane.Markdown("**Life-cycle stage**", margin=(5, 10, 0, 10)),
                               stage))

    # ---- datasets
    dataset = None
    market_fields: dict[int, DatasetField] = {}
    use_kind = None
    if entry_type in ("production_input", "production_waste"):
        dataset = DatasetField(session, kind="process", value=entry.get("dataset_ref_id"),
                               label="Treatment" if entry_type == "production_waste" else "Dataset",
                               on_pick=lambda ref: set_unit(dataset.unit()))
        parts.append(dataset.view)
    elif entry_type == "production_emission":
        dataset = DatasetField(session, kind="flow", value=entry.get("dataset_ref_id"),
                               label="Substance", on_pick=lambda ref: set_unit(dataset.unit()))
        parts.append(dataset.view)
    elif entry_type == "use":
        existing = project.market_datasets(entry["id"]) if editing else {}
        is_emission = entry.get("dataset_ref_id") is not None
        use_kind = W.RadioBoxGroup(
            options={"Energy, material or service (one dataset per market)": "markets",
                     "Direct emission": "emission"},
            value="emission" if is_emission else "markets", inline=True)
        dataset = DatasetField(session, kind="flow", value=entry.get("dataset_ref_id"),
                               label="Substance", on_pick=lambda ref: set_unit(dataset.unit()))

        def market_picked(ref):
            first = next((f.unit() for f in market_fields.values() if f.value), None)
            if state["unit"] is None or not state["unit"].options:
                set_unit(first)

        for market in markets:
            market_fields[market["id"]] = DatasetField(
                session, kind="process", value=existing.get(market["id"]),
                label=f"Dataset in {market['name']}", on_pick=market_picked)
        market_box = pn.Column(*[f.view for f in market_fields.values()],
                               note("The amount is the same in every market; only the dataset "
                                    "differs, e.g. the national electricity mix."))
        if not markets:
            market_box = pn.Column(alert("Add a market in the Setup first.", "warning"))

        def show_kind(*events):
            market_box.visible = use_kind.value == "markets"
            dataset.view.visible = use_kind.value == "emission"

        use_kind.param.watch(show_kind, "value")
        show_kind()
        parts += [use_kind, market_box, dataset.view]

    # ---- amount
    amount = None
    confirm = W.Checkbox(name="The negative amount is intended (e.g. a credit)", value=False,
                         visible=False)
    if entry_type == "cost":
        amount = W.FloatInput(name=f"Cost ({project.get_setting('currency')})",
                              value=entry.get("amount"), width=200)
        parts.append(amount)
    elif entry_type != "exclusion":
        amount = W.FloatInput(name="Amount (per one unit of this element)",
                              value=entry.get("amount"), width=260)
        first_unit = None
        if dataset is not None and dataset.value:
            first_unit = dataset.unit()
        if first_unit is None:
            first_unit = next((f.unit() for f in market_fields.values() if f.value), None)
        set_unit(first_unit, entry.get("unit"))
        amount_note = W.TextInput(name="Note on the amount (optional)",
                                  value=entry.get("amount_note") or "",
                                  placeholder="e.g. 15 W × 2 000 h/year × 8 years",
                                  sizing_mode="stretch_width")
        widgets["amount_note"] = amount_note
        parts += [pn.Row(amount, unit_holder), amount_note]
    if entry_type == "exclusion":
        reason = W.TextInput(name="Reason", value=entry.get("exclusion_reason") or "",
                             placeholder="e.g. below 1 % of the mass", sizing_mode="stretch_width")
        widgets["exclusion_reason"] = reason
        parts.append(reason)

    classification = None
    if entry_type not in ("cost", "exclusion"):
        classification = ClassificationFields(session, entry)
        if classification.view is not None:
            parts.append(classification.view)

    # ---- save
    def save(event):
        fields = {"description": description.value}
        fields.update({name: widget.value for name, widget in widgets.items()})
        if amount is not None:
            fields["amount"] = amount.value
        if stage is not None:
            fields["stage_id"] = stage.value
        if classification is not None:
            fields.update(classification.values())
        per_market = entry_type == "use" and use_kind.value == "markets"
        if entry_type not in ("cost", "exclusion"):
            fields["dataset_ref_id"] = None if per_market else dataset.value
            if state["unit"] is not None and state["unit"].value:
                fields["unit"] = state["unit"].value

        def action():
            if editing:
                entry_id = entry["id"]
                if entry_type == "use" and not per_market:
                    for market in markets:
                        project.set_market_dataset(entry_id, market["id"], None)
                project.update_entry(entry_id, confirm_negative=confirm.value, **fields)
            else:
                entry_id = project.add_entry(node_id, entry_type, confirm_negative=confirm.value,
                                             **fields)
            if per_market:
                for market_id, field in market_fields.items():
                    project.set_market_dataset(entry_id, market_id, field.value)

        if guarded(session, action, local):
            session.saved()
            session.changed()
            on_done()
        elif amount is not None and amount.value is not None and amount.value < 0:
            confirm.visible = True

    save_button = W.Button(name="Save entry", button_type="primary", width=130)
    cancel = W.Button(name="Cancel", width=100)
    save_button.on_click(save)
    cancel.on_click(lambda event: on_done())
    title = ("Edit: " if editing else "New: ") + ENTRY_TYPE_LABELS[entry_type]
    return pn.Column(pn.pane.Markdown(f"#### {title}", margin=(0, 10)), *parts, confirm, local,
                     pn.Row(save_button, cancel), styles=_BOX, sizing_mode="stretch_width")


def entries_panel(session, node_id: int, on_changed=None):
    project = session.project
    node = project.get_node(node_id)
    toggles = project.toggles
    stage_names = {s["id"]: s["name"] for s in project.list_stages()}
    listing = pn.Column(sizing_mode="stretch_width")
    form_area = pn.Column(sizing_mode="stretch_width")

    def done():
        form_area[:] = []
        if on_changed:
            on_changed()
        else:
            show()

    def describe(entry) -> str:
        if entry["type"] in ("cost", "exclusion"):
            return ""
        if entry["dataset_ref_id"]:
            return project.get_dataset_ref(entry["dataset_ref_id"])["name"]
        per_market = project.market_datasets(entry["id"])
        if not per_market:
            return "— not chosen —"
        names = {project.get_dataset_ref(ref)["name"] for ref in per_market.values()}
        return next(iter(names)) if len(names) == 1 else f"{len(per_market)} datasets (per market)"

    def amount_text(entry) -> str:
        if entry["type"] == "exclusion":
            return ""
        if entry["amount"] is None:
            return "—"
        unit = project.get_setting("currency") if entry["type"] == "cost" else (entry["unit"] or "")
        return f"{entry['amount']:g} {unit}".strip()

    def show():
        entries = project.list_entries(node_id)
        objects = []
        if entries:
            frame = pd.DataFrame([{
                "Kind": ENTRY_TYPE_LABELS[e["type"]],
                "Stage": stage_names.get(e["stage_id"], ""),
                "Description": e["description"] or "",
                "Dataset": describe(e),
                "Amount": amount_text(e),
                "Note": e["amount_note"] or e["exclusion_reason"] or "",
            } for e in entries])
            grid = table(frame, buttons={"edit": "✏️", "delete": "🗑️"},
                         widths={"Kind": 150, "Stage": 120, "Amount": 100, "Note": "15%"})

            def clicked(event):
                entry = entries[event.row]
                if event.column == "edit":
                    form_area[:] = [entry_form(session, node_id, entry["type"], entry, done)]
                elif event.column == "delete":
                    project.delete_entry(entry["id"])
                    session.changed()
                    done()

            grid.on_click(clicked)
            objects.append(grid)
        else:
            objects.append(note("No entries yet. Choose below what to add."))

        kinds = ["production_input", "production_waste", "production_emission"]
        if node["has_use_inputs"] and project.stage_by_role("use") is not None:
            kinds.append("use")
        if toggles["cost"]:
            kinds.append("cost")
        kinds.append("exclusion")
        buttons = []
        for kind in kinds:
            button = W.Button(name=f"+ {ENTRY_TYPE_LABELS[kind]}", button_type="primary",
                              width=200)
            button.on_click(lambda event, kind=kind: form_area.__setitem__(
                slice(None), [entry_form(session, node_id, kind, None, done)]))
            buttons.append(button)
        objects.append(pn.pane.Markdown("**Add an entry**", margin=(10, 10, 0, 10)))
        objects.append(pn.FlexBox(*buttons))
        if not node["has_use_inputs"] and project.stage_by_role("use") is not None:
            objects.append(note("Use entries become available once this element is marked as "
                                "having use-stage inputs (tab 'Element')."))
        listing[:] = objects

    show()
    focus_entry = session.focus.get("entry")
    if focus_entry:
        for entry in project.list_entries(node_id):
            if entry["id"] == focus_entry:
                form_area[:] = [entry_form(session, node_id, entry["type"], entry, done)]
    return pn.Column(listing, form_area, sizing_mode="stretch_width")
