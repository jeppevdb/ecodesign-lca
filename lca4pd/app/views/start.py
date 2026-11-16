"""Opening screen: open an existing project or start a new one."""

import panel as pn

from ..components import W, alert, card, guarded, heading, note


def build(session):
    files = session.project_files()
    messages = pn.Column()

    name = W.TextInput(name="Name of the new project", placeholder="e.g. Desk lamp", width=350)
    create = W.Button(name="Create project", button_type="primary", width=150)
    create.on_click(lambda event: guarded(
        session, lambda: session.new_project(name.value_input or name.value), messages))

    existing = [note("No projects yet.")]
    if files:
        select = W.Select(name="Existing projects", options={f.stem: f for f in files}, width=350)
        open_button = W.Button(name="Open", button_type="primary", width=150)
        open_button.on_click(lambda event: guarded(
            session, lambda: session.open_project(select.value), messages))
        existing = [pn.Row(select, pn.Column(pn.Spacer(height=15), open_button))]

    return pn.Column(
        heading("LCA for product development", 2),
        note("Model a product step by step, calculate its environmental impact with your own "
             "databases, and read the results in the report. Everything stays on this computer: "
             f"projects and databases are stored in `{session.workspace}`."),
        messages,
        card("Open a project", *existing),
        card("Start a new project",
             pn.Row(name, pn.Column(pn.Spacer(height=15), create))),
        sizing_mode="stretch_width",
    )
