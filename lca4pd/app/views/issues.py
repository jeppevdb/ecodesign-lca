"""The missing-items panel shown next to every step."""

import panel as pn

from ..components import LINK_STYLE, W

MAX_SHOWN = 40

# Where each kind of item is fixed
_STEP_FOR_TARGET = {
    "node": "tree", "entry": "tree", "pathway": "pathways", "pathway_leg": "pathways",
    "market": "pathways", "database": "databases", "parameter": "scenarios",
    "scenario": "scenarios",
}
_STEP_FOR_CODE = {"no_market": "setup", "no_database": "databases", "no_product": "tree"}


def target_of(session, issue) -> tuple[str, dict]:
    """The step, and what to open there, for an open item."""
    step = _STEP_FOR_CODE.get(issue.code) or _STEP_FOR_TARGET.get(issue.target_type, "setup")
    focus = {}
    if issue.target_type == "node":
        focus = {"node": issue.target_id}
    elif issue.target_type == "entry":
        entry = session.project.get_entry(issue.target_id)
        focus = {"node": entry["node_id"], "entry": issue.target_id}
    elif issue.target_type == "pathway":
        focus = {"pathway": issue.target_id}
    elif issue.target_type == "pathway_leg":
        leg = session.project._row("pathway_leg", issue.target_id)
        focus = {"pathway": leg["pathway_id"]}
    elif issue.target_type in ("parameter", "scenario"):
        focus = {issue.target_type: issue.target_id}
    if step not in session.views:
        step = "setup"
    return step, focus


def build(session):
    """A column that lists blockers and warnings and keeps itself up to date."""
    body = pn.Column(sizing_mode="stretch_width")

    def goto(issue):
        step, focus = target_of(session, issue)
        session.goto(step, **focus)

    def refresh():
        if session.project is None:
            body[:] = []
            return
        issues = session.issues()
        blockers = [i for i in issues if i.severity == "blocker"]
        warnings = [i for i in issues if i.severity == "warning"]
        objects = []
        if not issues:
            objects.append(pn.pane.Markdown("✅ Nothing is missing. The project can be calculated."))
        for title, group, colour in ((f"⛔ Needed before calculating ({len(blockers)})", blockers, "#b42318"),
                                     (f"⚠️ Worth checking ({len(warnings)})", warnings, "#b54708")):
            if not group:
                continue
            objects.append(pn.pane.Markdown(f"**{title}**", styles={"color": colour},
                                            margin=(8, 5, 0, 5)))
            for issue in group[:MAX_SHOWN]:
                button = W.Button(name=issue.message, button_type="light",
                                  stylesheets=[LINK_STYLE], sizing_mode="stretch_width")
                button.on_click(lambda event, issue=issue: goto(issue))
                objects.append(button)
            if len(group) > MAX_SHOWN:
                objects.append(pn.pane.Markdown(f"… and {len(group) - MAX_SHOWN} more."))
        body[:] = objects

    session.on_change(refresh, persistent=True)
    refresh()
    return body
