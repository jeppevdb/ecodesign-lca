"""Step: project and calculation setup. Everything here can be changed later."""

import panel as pn

from ...model.classifications import STAGE_ROLES, TOGGLE_LABELS, TOGGLES
from ..components import W, card, confirm_button, guarded, note

_ROLE_TEXT = {
    "raw_materials": "production inputs",
    "manufacturing": "production inputs",
    "distribution": "gate-to-customer distribution",
    "use": "use entries",
    "end_of_life": "end-of-life pathways",
    None: "production inputs",
}


def build(session):
    project = session.project

    # ---- general
    def setting(key, label, area=False, **kwargs):
        widget = (W.TextAreaInput if area else W.TextInput)(
            name=label, value=project.get_setting(key) or "", sizing_mode="stretch_width", **kwargs)

        def save(event):
            if guarded(session, lambda: project.set_setting(key, event.new)):
                session.saved()
                session.changed()

        widget.param.watch(save, "value")
        return widget

    general = card(
        "Project",
        setting("name", "Project name"),
        setting("functional_unit", "Functional unit",
                placeholder="e.g. Lighting a desk for 10 years"),
        setting("reference_flow", "Reference flow", placeholder="e.g. One desk lamp"),
        setting("scope", "Scope and system boundary", area=True, height=90),
        setting("currency", "Currency", width=120),
    )

    # ---- markets
    markets = pn.Column(sizing_mode="stretch_width")
    market_messages = pn.Column()

    def show_markets():
        rows = []
        for market in project.list_markets():
            name = W.TextInput(value=market["name"], width=260)

            def rename(event, market=market):
                if guarded(session, lambda: project.rename_market(market["id"], event.new),
                           market_messages):
                    session.changed()

            def remove(market=market):
                project.remove_market(market["id"])
                show_markets()
                session.changed()

            name.param.watch(rename, "value")
            rows.append(pn.Row(name, confirm_button("Remove", remove, width=170)))
        new = W.TextInput(placeholder="e.g. EU, United States, China", width=260)
        add = W.Button(name="Add market", button_type="primary", width=170)

        def add_market(event):
            if guarded(session, lambda: project.add_market(new.value_input or new.value),
                       market_messages):
                show_markets()
                session.changed()

        add.on_click(add_market)
        markets[:] = [*rows, pn.Row(new, add)]

    show_markets()
    market_card = card(
        "Markets",
        note("Countries or regions where the product is sold. Distribution, use and "
             "end-of-life are modelled per market. At least one is needed."),
        market_messages, markets)

    # ---- stages
    stages = pn.Column(sizing_mode="stretch_width")
    stage_messages = pn.Column()

    def show_stages():
        rows = []
        present = set()
        for stage in project.list_stages():
            present.add(stage["role"])
            name = W.TextInput(value=stage["name"], width=260)

            def rename(event, stage=stage):
                if guarded(session, lambda: project.rename_stage(stage["id"], event.new),
                           stage_messages):
                    session.changed()

            def remove(stage=stage):
                if guarded(session, lambda: project.remove_stage(stage["id"]), stage_messages):
                    show_stages()
                    session.changed()

            name.param.watch(rename, "value")
            rows.append(pn.Row(
                name, confirm_button("Remove", remove, width=170),
                pn.pane.Markdown(f"used for {_ROLE_TEXT[stage['role']]}", margin=(0, 10))))
        missing = [role for role in STAGE_ROLES if role not in present]
        new = W.TextInput(placeholder="Name of an extra stage", width=260)
        kind = W.Select(value="", options={"extra stage for production inputs": "",
                                 **{f"stage for {_ROLE_TEXT[r]} ({r.replace('_', ' ')})": r
                                    for r in missing}}, width=330)
        add = W.Button(name="Add stage", button_type="primary", width=170)

        def add_stage(event):
            if guarded(session, lambda: project.add_stage(new.value_input or new.value, kind.value or None),
                       stage_messages):
                show_stages()
                session.changed()

        add.on_click(add_stage)
        stages[:] = [*rows, pn.Row(new, add, kind)]

    show_stages()
    stage_card = card(
        "Life-cycle stages",
        note("The standard stages can be renamed. Removing Distribution, Use or End-of-Life "
             "takes that stage out of the scope: its questions are no longer asked."),
        stage_messages, stages)

    # ---- optional features
    options = []
    toggles = project.toggles
    for toggle in TOGGLES:
        label, description = TOGGLE_LABELS[toggle]
        box = W.Checkbox(name=f"{label} – {description}", value=toggles[toggle])

        def switch(event, toggle=toggle):
            project.set_toggle(toggle, event.new)
            session.changed()

        box.param.watch(switch, "value")
        options.append(box)
    option_card = card(
        "Optional detail",
        note("Only what is ticked here is asked for while modelling. Start simple and add "
             "detail later: nothing entered is lost when an option is switched off."),
        *options)

    return pn.Column(general, market_card, stage_card, option_card, sizing_mode="stretch_width")
