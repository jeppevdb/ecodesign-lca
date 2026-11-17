"""Step: pathways – distribution to customers, transport from suppliers, end-of-life.

A pathway is defined once and applied by weight to every element that uses it.
"""

import pandas as pd
import panel as pn

from ...model import units
from ..components import (ClassificationFields, DatasetField, ParameterField, W, alert, card,
                          confirm_button, guarded, heading, note, table)

_INTRO = {
    "gate_to_customer": "How the finished product travels from your gate to the customer, for "
                        "each market. It is applied to the weight of the whole product.",
    "supplier": "How bought-in parts travel from your direct supplier to your site. Define a "
                "pathway once and select it on every element that comes from that supplier.",
    "eol": "What happens to an element after use. Each line sends a share of the weight to a "
           "treatment; the shares should add up to 100 % in every market.",
}


def pathway_editor(session, pathway_id: int, on_change=None):
    """Edit one pathway: its name and its legs."""
    project = session.project
    pathway = project.get_pathway(pathway_id)
    is_eol = pathway["kind"] == "eol"
    markets = {m["id"]: m["name"] for m in project.list_markets()}
    legs_area = pn.Column(sizing_mode="stretch_width")
    form_area = pn.Column(sizing_mode="stretch_width")
    messages = pn.Column()

    def done():
        form_area[:] = []
        show()
        session.changed()
        if on_change:
            on_change()

    def leg_form(leg=None):
        leg = leg or {}
        dataset = DatasetField(session, kind="process",
                               dimension="mass" if is_eol else "transport",
                               value=leg.get("dataset_ref_id"),
                               label="Treatment" if is_eol else "Means of transport")
        local = pn.Column()
        confirm = W.Checkbox(name="The negative amount is intended (e.g. a credit)",
                             value=False, visible=False)
        note_input = W.TextInput(name="Note (optional)", value=leg.get("note") or "",
                                 sizing_mode="stretch_width")
        classification = ClassificationFields(session, leg)
        parameters = ParameterField(session, "pathway_leg", leg.get("id"),
                                    label="Share affected by" if is_eol else "Distance affected by")
        if is_eol:
            amount = W.FloatInput(name="Share of the weight (%)", width=200,
                                  value=None if leg.get("amount") is None else leg["amount"] * 100)
            market = W.Select(name="Applies in", width=220, value=leg.get("market_id") or 0,
                              options={"all markets": 0,
                                       **{name: mid for mid, name in markets.items()}})
            inputs = pn.Row(amount, market)
        else:
            amount = W.FloatInput(name="Distance", value=leg.get("amount"), width=200)
            unit = W.Select(name="Unit", options=units.alternatives("km"),
                            value=leg.get("unit") or "km", width=100)
            inputs = pn.Row(amount, unit)

        def save(event):
            fields = {"dataset_ref_id": dataset.value, "note": note_input.value,
                      **classification.values()}
            if is_eol:
                fields["amount"] = None if amount.value is None else amount.value / 100
                fields["market_id"] = market.value or None
            else:
                fields["amount"], fields["unit"] = amount.value, unit.value

            def action():
                leg_id = leg.get("id")
                if leg_id:
                    project.update_leg(leg_id, confirm_negative=confirm.value, **fields)
                else:
                    leg_id = project.add_leg(pathway_id, confirm_negative=confirm.value, **fields)
                parameters.save(leg_id)

            if guarded(session, action, local):
                done()
            elif amount.value is not None and amount.value < 0:
                confirm.visible = True

        save_button = W.Button(name="Save", button_type="primary", width=100)
        cancel = W.Button(name="Cancel", width=100)
        save_button.on_click(save)
        cancel.on_click(lambda event: form_area.clear())
        parts = [dataset.view, inputs, note_input]
        if parameters.view is not None:
            parts.append(parameters.view)
        if classification.view is not None:
            parts.append(classification.view)
        form_area[:] = [pn.Column(*parts, confirm, local, pn.Row(save_button, cancel),
                                  styles={"background": "#f7f9fb", "border": "1px solid #d0d7de",
                                          "border-radius": "6px", "padding": "8px"},
                                  sizing_mode="stretch_width")]

    def show():
        legs = project.list_legs(pathway_id)
        rows = []
        for leg in legs:
            ref = project.get_dataset_ref(leg["dataset_ref_id"]) if leg["dataset_ref_id"] else None
            if is_eol:
                amount = "—" if leg["amount"] is None else f"{leg['amount'] * 100:g} %"
            else:
                amount = "—" if leg["amount"] is None else f"{leg['amount']:g} {leg['unit']}"
            row = {"Dataset": ref["name"] if ref else "— not chosen —",
                   "Database": ref["database_name"] if ref else "",
                   "Share of weight" if is_eol else "Distance": amount}
            if is_eol:
                row["Market"] = markets.get(leg["market_id"], "all markets")
            row["Note"] = leg["note"] or ""
            rows.append(row)
        objects = []
        if rows:
            grid = table(pd.DataFrame(rows), buttons={"edit": "✏️", "delete": "🗑️"})

            def clicked(event):
                leg = legs[event.row]
                if event.column == "edit":
                    leg_form(leg)
                elif event.column == "delete":
                    project.remove_leg(leg["id"])
                    done()

            grid.on_click(clicked)
            objects.append(grid)
        else:
            objects.append(note("No legs yet."))
        if is_eol and legs:
            for market_id, market_name in markets.items():
                shares = [leg["amount"] for leg in legs
                          if leg["market_id"] in (None, market_id) and leg["amount"] is not None]
                total = sum(shares)
                if not shares:
                    objects.append(alert(f"No treatment defined for market '{market_name}'.",
                                         "warning"))
                elif abs(total - 1) > 1e-6:
                    objects.append(alert(f"Shares add up to {total:.0%} in market "
                                         f"'{market_name}', not 100 %.", "warning"))
        add = W.Button(name="Add treatment" if is_eol else "Add transport leg",
                       button_type="primary", width=180)
        add.on_click(lambda event: leg_form())
        objects.append(add)
        legs_area[:] = objects

    header = []
    if pathway["kind"] != "gate_to_customer":
        name = W.TextInput(name="Name", value=pathway["name"], width=320)

        def rename(event):
            if guarded(session, lambda: project.update_pathway(pathway_id, name=event.new),
                       messages):
                session.changed()
                if on_change:
                    on_change()

        name.param.watch(rename, "value")
        users = project.pathway_users(pathway_id)
        used = ("Used by: " + ", ".join(u["name"] for u in users)) if users else "Not used yet."
        header = [pn.Row(name, pn.pane.Markdown(used, margin=(25, 10)))]
    show()
    return pn.Column(*header, messages, legs_area, form_area, sizing_mode="stretch_width")


def new_pathway_form(session, kind: str, area, on_created):
    """Create a supplier or end-of-life pathway in place, inside ``area``.

    Shown in the page itself rather than in a dialog, because choosing a
    dataset for a leg already opens one.
    """
    project = session.project
    title = "New supplier pathway" if kind == "supplier" else "New end-of-life pathway"
    name = W.TextInput(name="Name", width=360,
                       placeholder="e.g. Supplier X, Shenzhen" if kind == "supplier"
                       else "e.g. Electronic waste")
    create = W.Button(name="Create", button_type="primary", width=100)
    cancel = W.Button(name="Cancel", width=100)
    local = pn.Column()
    box = {"background": "#fffdf5", "border": "1px solid #e0c97f", "border-radius": "6px",
           "padding": "8px"}

    def make(event):
        created = {}

        def action():
            created["id"] = project.add_pathway(kind, name.value_input or name.value)

        if not guarded(session, action, local):
            return
        session.changed()
        finish = W.Button(name="Done with this pathway", button_type="primary", width=220)

        def close(event):
            area[:] = []
            on_created(created["id"])

        finish.on_click(close)
        area[:] = [pn.Column(pn.pane.Markdown(f"#### {title}", margin=(0, 10)),
                             pathway_editor(session, created["id"]), finish,
                             styles=box, sizing_mode="stretch_width")]

    create.on_click(make)
    cancel.on_click(lambda event: area.clear())
    area[:] = [pn.Column(pn.pane.Markdown(f"#### {title}", margin=(0, 10)), note(_INTRO[kind]),
                         name, local, pn.Row(create, cancel), styles=box,
                         sizing_mode="stretch_width")]


def build(session):
    project = session.project
    roles = {stage["role"] for stage in project.list_stages()}
    focus = session.focus.get("pathway")
    focus_kind = project.get_pathway(focus)["kind"] if focus else None

    def section(kind):
        area = pn.Column(sizing_mode="stretch_width")

        def show():
            objects = [note(_INTRO[kind])]
            if kind == "gate_to_customer":
                if "distribution" not in roles:
                    area[:] = [alert("Distribution is not in the scope of this project "
                                     "(see Setup, life-cycle stages).", "info")]
                    return
                markets = project.list_markets()
                if not markets:
                    objects.append(alert("Add a market in the Setup first.", "warning"))
                existing = {p["market_id"]: p["id"] for p in project.list_pathways(kind)}
                for market in markets:
                    pathway_id = existing.get(market["id"]) or project.add_pathway(
                        kind, market_id=market["id"])
                    objects.append(card(f"Sold in {market['name']}",
                                        pathway_editor(session, pathway_id)))
            else:
                if kind == "eol" and "end_of_life" not in roles:
                    area[:] = [alert("End-of-life is not in the scope of this project "
                                     "(see Setup, life-cycle stages).", "info")]
                    return
                for pathway in project.list_pathways(kind):
                    def remove(pathway=pathway):
                        if guarded(session, lambda: project.remove_pathway(pathway["id"])):
                            show()
                            session.changed()

                    objects.append(card(
                        pathway["name"], pathway_editor(session, pathway["id"], on_change=None),
                        confirm_button("Delete this pathway", remove, width=200),
                        collapsed=focus is not None and pathway["id"] != focus))
                new = W.Button(name="New pathway", button_type="primary", width=160)
                new_area = pn.Column(sizing_mode="stretch_width")
                new.on_click(lambda event: new_pathway_form(session, kind, new_area,
                                                            lambda _id: show()))
                objects += [new, new_area]
            area[:] = objects

        show()
        return area

    kinds = ["gate_to_customer", "supplier", "eol"]
    titles = ["Distribution to customer", "Transport from supplier", "End-of-life"]
    tabs = pn.Tabs(*[(title, section(kind)) for title, kind in zip(titles, kinds)],
                   active=kinds.index(focus_kind) if focus_kind else 0, dynamic=False,
                   sizing_mode="stretch_width")
    return pn.Column(tabs, sizing_mode="stretch_width")
