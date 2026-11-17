"""Step: scenarios. Best and worst cases for uncertain assumptions.

A scenario groups one or more parameters that always switch together. A
parameter multiplies what it is linked to; the average case is always the
value as entered.
"""

import pandas as pd
import panel as pn

from ..components import W, alert, card, confirm_button, guarded, note, table

_BOX = {"background": "#f7f9fb", "border": "1px solid #d0d7de", "border-radius": "6px",
        "padding": "8px"}


def affected(project, parameter: dict) -> list[dict]:
    """Everything a parameter acts on, with the value in each case."""
    pathways = {p["id"]: p for p in project.list_pathways()}
    rows = []

    def cases(value, unit="", scale=1.0):
        if value is None:
            return {"Best": "—", "Average": "—", "Worst": "—"}
        result = {}
        for case, factor in (("Best", parameter["best"]), ("Average", 1.0),
                             ("Worst", parameter["worst"])):
            result[case] = "—" if factor is None else f"{value * factor * scale:g} {unit}".strip()
        return result

    for link in project.parameter_links(parameter["id"]):
        kind, target = link["target_type"], link["target_id"]
        if kind == "entry":
            entry = project.get_entry(target)
            node = project.get_node(entry["node_id"])
            unit = project.get_setting("currency") if entry["type"] == "cost" else entry["unit"] or ""
            what = entry["description"] or entry["type"].replace("_", " ")
            rows.append({"Where": node["name"], "What": f"Amount of '{what}'",
                         **cases(entry["amount"], unit), "_step": "tree",
                         "_focus": {"node": node["id"], "entry": target}})
        elif kind == "pathway_leg":
            leg = project._row("pathway_leg", target)
            pathway = pathways[leg["pathway_id"]]
            ref = project.get_dataset_ref(leg["dataset_ref_id"]) if leg["dataset_ref_id"] else None
            name = ref["name"] if ref else "leg without dataset"
            if pathway["kind"] == "eol":
                values = cases(leg["amount"], "%", 100)
                what = f"Share to '{name}'"
            else:
                values = cases(leg["amount"], leg["unit"] or "km")
                what = f"Distance by '{name}'"
            rows.append({"Where": f"Pathway '{pathway['name']}'", "What": what, **values,
                         "_step": "pathways", "_focus": {"pathway": pathway["id"]}})
        else:
            node = project.get_node(target)
            if kind == "node_weight":
                values, what = cases(node["weight"], "kg"), "Weight"
            else:
                values, what = cases(node["price"], project.get_setting("currency")), "Price"
            rows.append({"Where": node["name"], "What": what, **values, "_step": "tree",
                         "_focus": {"node": node["id"]}})
    return rows


def build(session):
    project = session.project
    if not project.toggles["scenarios"]:
        return alert("Scenarios are switched off for this project. Switch them on in the Setup "
                     "under 'Optional detail'.", "info")
    area = pn.Column(sizing_mode="stretch_width")
    focus = session.focus

    def refresh():
        show()
        session.changed()

    def parameter_form(scenario_id, parameter, target):
        parameter = parameter or {}
        local = pn.Column()
        name = W.TextInput(name="Parameter name", value=parameter.get("name", ""), width=320,
                           placeholder="e.g. recycling share")
        best = W.FloatInput(name="Best case (× entered value)", value=parameter.get("best"),
                            start=0, step=0.05, width=230)
        worst = W.FloatInput(name="Worst case (× entered value)", value=parameter.get("worst"),
                             start=0, step=0.05, width=230)
        texts = {case: W.TextInput(name=f"Assumption, {case} case",
                                   value=parameter.get(f"assumption_{case}") or "",
                                   sizing_mode="stretch_width")
                 for case in ("best", "average", "worst")}

        def save(event):
            fields = {"name": name.value_input or name.value, "best": best.value,
                      "worst": worst.value,
                      **{f"assumption_{case}": widget.value for case, widget in texts.items()}}

            def action():
                if parameter.get("id"):
                    project.update_parameter(parameter["id"], **fields)
                else:
                    project.add_parameter(scenario_id, fields.pop("name"), **fields)

            if guarded(session, action, local):
                refresh()

        save_button = W.Button(name="Save parameter", button_type="primary", width=160)
        cancel = W.Button(name="Cancel", width=100)
        save_button.on_click(save)
        cancel.on_click(lambda event: target.clear())
        target[:] = [pn.Column(
            note("Multipliers on the value as entered: 1 leaves it unchanged, 0.8 is 20 % less, "
                 "1.5 is 50 % more. The average case is always 1."),
            pn.Row(name, best, worst), *texts.values(), local, pn.Row(save_button, cancel),
            styles=_BOX, sizing_mode="stretch_width")]

    def scenario_card(scenario):
        form_area = pn.Column(sizing_mode="stretch_width")
        local = pn.Column()
        name = W.TextInput(name="Scenario name", value=scenario["name"], width=320)
        description = W.TextInput(name="Description", value=scenario["description"] or "",
                                  sizing_mode="stretch_width")

        def rename(event):
            if guarded(session, lambda: project.update_scenario(scenario["id"], name=event.new),
                       local):
                session.changed()

        name.param.watch(rename, "value")
        description.param.watch(
            lambda event: project.update_scenario(scenario["id"], description=event.new), "value")

        def remove():
            project.remove_scenario(scenario["id"])
            refresh()

        objects = [pn.Row(name, description), local]
        parameters = project.list_parameters(scenario["id"])
        if not parameters:
            objects.append(note("No parameters yet. A scenario needs at least one."))
        for parameter in parameters:
            def edit(event, parameter=parameter):
                parameter_form(scenario["id"], parameter, form_area)

            def delete(parameter=parameter):
                project.remove_parameter(parameter["id"])
                refresh()

            def show_value(value):
                return "not set" if value is None else f"× {value:g}"

            edit_button = W.Button(name="Edit", width=70)
            edit_button.on_click(edit)
            header = pn.Row(
                pn.pane.Markdown(
                    f"**{parameter['name']}** — best {show_value(parameter['best'])}, "
                    f"average × 1, worst {show_value(parameter['worst'])}", margin=(8, 10)),
                edit_button, confirm_button("Delete", delete, width=170))
            assumptions = [f"*{case}:* {parameter[f'assumption_{case}']}"
                           for case in ("best", "average", "worst")
                           if parameter[f"assumption_{case}"]]
            rows = affected(project, parameter)
            parts = [header]
            if assumptions:
                parts.append(note(" · ".join(assumptions)))
            if rows:
                frame = pd.DataFrame([{k: v for k, v in row.items() if not k.startswith("_")}
                                      for row in rows])
                grid = table(frame, buttons={"open": "↗"}, widths={"Where": "22%"})

                def clicked(event, rows=rows):
                    if event.column == "open":
                        row = rows[event.row]
                        session.goto(row["_step"], **row["_focus"])

                grid.on_click(clicked)
                parts.append(grid)
            else:
                parts.append(alert(
                    "This parameter does not affect anything yet. Link it from an entry, a "
                    "pathway leg or an element (field 'affected by').", "warning"))
            objects.append(pn.Column(*parts, styles={"border-top": "1px solid #ddd"},
                                     sizing_mode="stretch_width"))
        add = W.Button(name="Add parameter", button_type="primary", width=160)
        add.on_click(lambda event: parameter_form(scenario["id"], None, form_area))
        objects += [pn.Row(add, confirm_button("Delete scenario", remove, width=170)), form_area]
        collapsed = bool(focus.get("scenario")) and focus["scenario"] != scenario["id"]
        return card(scenario["name"], *objects, collapsed=collapsed)

    def show():
        objects = [note(
            "A scenario is one uncertain assumption, e.g. 'Steel recycling' or 'Hours of use'. "
            "It holds one or more parameters that move together. The calculation runs every "
            "design with all scenarios in their best, average and worst case, and each scenario "
            "on its own to show which matters most.")]
        for scenario in project.list_scenarios():
            objects.append(scenario_card(scenario))
        new = W.TextInput(placeholder="Name of a new scenario", width=320)
        add = W.Button(name="Add scenario", button_type="primary", width=160)
        local = pn.Column()

        def add_scenario(event):
            if guarded(session, lambda: project.add_scenario(new.value_input or new.value), local):
                refresh()

        add.on_click(add_scenario)
        objects += [local, pn.Row(new, add)]
        area[:] = objects

    if focus.get("parameter"):
        focus["scenario"] = project._row("parameter", focus["parameter"])["scenario_id"]
    show()
    return area
