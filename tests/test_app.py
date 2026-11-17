"""The interface: every screen builds from project data without errors.

These tests run the screens' code without a browser. What happens when
widgets are clicked is covered where the handlers call the model, which has
its own tests.
"""

import pytest

pn = pytest.importorskip("panel")

from lca4pd.app.main import VIEWS            # noqa: E402
from lca4pd.app.session import Session       # noqa: E402
from lca4pd.app.views import issues          # noqa: E402
from lca4pd.app.views.entries import entry_form            # noqa: E402
from lca4pd.app.views.tree import node_form                # noqa: E402
from lca4pd.databases import link                          # noqa: E402
from lca4pd.databases.reader import ImportReport, Item, ParsedDatabase   # noqa: E402
from lca4pd.model import check_project                                 # noqa: E402
from lca4pd.model.classifications import ENTRY_TYPES, TOGGLES            # noqa: E402


STEPS = ["setup", "databases", "pathways", "tree", "scenarios", "overview", "calculate"]


def shown(session) -> bool:
    """The current screen was built (a failed screen is replaced by a red message)."""
    view = session.main[0]
    return getattr(view, "alert_type", None) != "danger"


class FakeTemplate:
    def open_modal(self):
        self.open = True

    def close_modal(self):
        self.open = False


@pytest.fixture
def session(tmp_path):
    session = Session(tmp_path)
    session.template = FakeTemplate()
    session.views = VIEWS
    yield session
    if session.project is not None:
        session.project.close()
    session.library.close()


@pytest.fixture
def filled(session):
    """A project with a market, a database, pathways, a small tree and entries."""
    values = tuple(float(i + 1) for i in range(16))
    items = [Item("steel", "Steel", "kg", "RER", "metals", None, values),
             Item("lorry", "Lorry", "tkm", "RER", "transport", None, values),
             Item("power", "Electricity", "kWh", "DE", "energy", None, values),
             Item("landfill", "Landfill", "kg", None, "waste", None, values)]
    session.library.add(ParsedDatabase("process", "db.xlsx", "h1", items, ImportReport("test")),
                        "TestDB")
    flows = [Item("co2", "carbon dioxide", "kg", None, "air", None, values)]
    session.library.add(ParsedDatabase("flow", "f.xlsx", "h2", flows, ImportReport("test")),
                        "Flows")
    session.new_project("Lamp")
    p = session.project
    for toggle in TOGGLES:
        p.set_toggle(toggle, True)
    market = p.add_market("EU")
    db = link.register(p, session.library, "h1")
    flow_db = link.register(p, session.library, "h2")
    ref = {key: link.pick(p, session.library, db, key) for key in ("steel", "lorry", "power", "landfill")}
    co2 = link.pick(p, session.library, flow_db, "co2")
    gate = p.add_pathway("gate_to_customer", market_id=market)
    p.add_leg(gate, dataset_ref_id=ref["lorry"], amount=500)
    supplier = p.add_pathway("supplier", "Supplier X")
    p.add_leg(supplier, dataset_ref_id=ref["lorry"], amount=100)
    eol = p.add_pathway("eol", "Metal")
    p.add_leg(eol, dataset_ref_id=ref["landfill"], amount=1)
    root = p.add_node(None, "Lamp", eol_mode="split", has_use_inputs=True, price=30)
    base = p.add_node(root, "Base", weight=1, quantity=2, production_site="supplier",
                      supplier_pathway_id=supplier, eol_mode="whole", eol_pathway_id=eol)
    raw = p.stage_by_role("raw_materials")["id"]
    session.entries = {
        "production_input": p.add_entry(base, "production_input", stage_id=raw,
                                        dataset_ref_id=ref["steel"], amount=1.05),
        "production_waste": p.add_entry(base, "production_waste", dataset_ref_id=ref["landfill"],
                                        amount=0.05),
        "production_emission": p.add_entry(base, "production_emission", dataset_ref_id=co2,
                                           amount=0.1),
        "cost": p.add_entry(root, "cost", amount=2, description="Assembly"),
        "exclusion": p.add_entry(root, "exclusion", description="Paint", exclusion_reason="tiny"),
        "use": p.add_entry(root, "use", amount=120),
    }
    p.set_market_dataset(session.entries["use"], market, ref["power"])
    session.ids = {"root": root, "base": base, "supplier": supplier}
    session.changed()
    return session


def test_start_screen_lists_projects(session):
    assert session.step == "start"
    session.goto("start")
    session.new_project("Desk lamp")
    session.close_project()
    assert [f.stem for f in session.project_files()] == ["Desk_lamp"]
    session.goto("start")
    assert shown(session)


@pytest.mark.parametrize("step", STEPS)
def test_every_step_builds_for_an_empty_project(session, step):
    session.new_project("Empty")
    session.goto(step)
    assert shown(session)


@pytest.mark.parametrize("step", STEPS)
def test_every_step_builds_for_a_filled_project(filled, step):
    filled.goto(step, node=filled.ids["base"])
    assert shown(filled)


def test_forms_build_for_every_entry_type_new_and_existing(filled):
    project = filled.project
    for entry_type in ENTRY_TYPES:
        entry = project.get_entry(filled.entries[entry_type])
        entry_form(filled, entry["node_id"], entry_type, entry, lambda: None)
        entry_form(filled, filled.ids["root"], entry_type, None, lambda: None)


def test_element_forms_build_for_new_and_existing_elements(filled):
    node_form(filled, node_id=filled.ids["root"])
    node_form(filled, node_id=filled.ids["base"])
    node_form(filled, parent_id=filled.ids["base"])     # below a supplied element


def test_missing_items_lead_to_the_place_where_they_are_fixed(filled):
    project = filled.project
    project.update_entry(filled.entries["production_input"], amount=None)
    project.add_market("US")
    filled.changed()
    targets = {issue.code: issues.target_of(filled, issue) for issue in filled.issues()}
    assert targets["entry_incomplete"] == (
        "tree", {"node": filled.ids["base"], "entry": filled.entries["production_input"]})
    assert targets["use_market_dataset_missing"][0] == "tree"
    assert targets["distribution_missing"][0] == "pathways"
    filled.goto(*targets["entry_incomplete"][:1], **targets["entry_incomplete"][1])
    assert filled.selected_node == filled.ids["base"]


def test_calculation_can_be_run_from_the_filled_project(filled):
    from lca4pd.calculation import calculate
    results = calculate(filled.project, filled.library)
    results.save(filled.results_path)
    filled.goto("calculate")                       # shows the saved results
    assert shown(filled)
    assert len(results.inventory) > 0


def test_questions_start_unanswered(filled):
    """Nothing may be answered on the user's behalf just because a form was opened."""
    project = filled.project
    form = node_form(filled, parent_id=filled.ids["root"])
    radios = list(form.select(pn.widgets.RadioBoxGroup))
    assert len(radios) == 2                                   # production site, end-of-life
    assert all(radio.value == "" for radio in radios)

    new_input = entry_form(filled, filled.ids["base"], "production_input", None, lambda: None)
    (stage,) = new_input.select(pn.widgets.RadioBoxGroup)
    assert stage.value == ""                                  # raw materials or manufacturing

    # An element saved with the questions untouched keeps them open, and is flagged.
    node = project.add_node(filled.ids["root"], "Shade")
    existing = node_form(filled, node_id=node)
    assert all(radio.value == "" for radio in existing.select(pn.widgets.RadioBoxGroup))
    codes = {issue.code for issue in check_project(project) if issue.target_id == node}
    assert {"production_site_unanswered", "eol_unanswered"} <= codes


def test_answered_questions_are_shown_as_answered(filled):
    form = node_form(filled, node_id=filled.ids["base"])
    values = [radio.value for radio in form.select(pn.widgets.RadioBoxGroup)]
    assert values == ["supplier", "whole"]


def test_steps_follow_the_setup(session):
    from lca4pd.app.main import steps
    session.new_project("P")
    assert [label for _, label in steps(session.project)] == [
        "1  Setup", "2  Databases", "3  Transport and end-of-life pathways",
        "4  Product and entries", "5  Full overview", "6  Calculate"]
    session.project.set_toggle("scenarios", True)
    assert steps(session.project)[4] == ("scenarios", "5  Scenarios")


def test_scenarios_alternatives_and_links_show_up_in_the_screens(filled):
    from lca4pd.app.views import scenarios as scenario_view
    from lca4pd.app.views.tree import alternative_details, new_alternative_form
    project = filled.project
    scenario = project.add_scenario("Steel use")
    parameter = project.add_parameter(scenario, "steel amount", best=0.9, worst=1.2)
    project.link_parameter(parameter, "entry", filled.entries["production_input"])
    project.link_parameter(parameter, "node_weight", filled.ids["base"])
    leg = project.list_legs(filled.ids["supplier"])[0]["id"]
    project.link_parameter(parameter, "pathway_leg", leg)
    rows = scenario_view.affected(project, project.list_parameters()[0])
    assert [(r["What"], r["Best"], r["Average"], r["Worst"]) for r in rows] == [
        ("Amount of 'production input'", "0.945 kg", "1.05 kg", "1.26 kg"),
        ("Weight", "0.9 kg", "1 kg", "1.2 kg"),
        ("Distance by 'Lorry'", "90 km", "100 km", "120 km")]

    alternative = project.create_alternative(filled.ids["base"], "Lighter base")
    removed = project.create_alternative(filled.ids["base"], "No base", removed=True)
    filled.changed()
    for node in (alternative, removed, filled.ids["base"]):
        filled.goto("tree", node=node)
        assert shown(filled)
    alternative_details(filled, alternative, lambda _id: None)
    new_alternative_form(filled, filled.ids["base"], lambda _id: None)
    for step in ("scenarios", "overview"):
        filled.goto(step)
        assert shown(filled)


def test_forms_offer_the_parameters_only_with_scenarios_on(filled):
    project = filled.project
    scenario = project.add_scenario("S")
    project.add_parameter(scenario, "x", best=0.9, worst=1.1)
    form = entry_form(filled, filled.ids["base"], "production_input", None, lambda: None)
    assert len(form.select(pn.widgets.MultiChoice)) == 1
    project.set_toggle("scenarios", False)
    form = entry_form(filled, filled.ids["base"], "production_input", None, lambda: None)
    assert len(form.select(pn.widgets.MultiChoice)) == 0


def test_unit_follows_a_changed_dataset_in_a_copied_alternative(filled):
    """Reported: after copying an element as an alternative, changing an entry's dataset
    left the unit as it was."""
    from lca4pd.app.components import DatasetField
    project = filled.project
    project.set_toggle("scenarios", False)
    alternative = project.create_alternative(filled.ids["base"], "Other base")
    entry = next(e for e in project.list_entries(alternative) if e["type"] == "production_input")
    form = entry_form(filled, alternative, "production_input", entry, lambda: None)
    unit = next(w for w in form.select(pn.widgets.Select) if w.name == "Unit")
    assert unit.value == "kg"
    power = next(r["id"] for r in project.list_dataset_refs(1) if r["unit"] == "kWh")
    pickers = [w for w in form.select(pn.widgets.Button) if w.name == "Search…"]
    assert len(pickers) == 1
    # choose the electricity dataset the way the search dialog does
    import gc
    dataset_field = [o for o in gc.get_objects() if isinstance(o, DatasetField)
                     and o.view in form.select(pn.Row)][-1]
    dataset_field.set(power)
    assert unit is next(w for w in form.select(pn.widgets.Select) if w.name == "Unit")
    assert unit.value == "kWh" and "MJ" in unit.options
    save = next(b for b in form.select(pn.widgets.Button) if b.name == "Save entry")
    save.clicks += 1
    stored = project.get_entry(entry["id"])
    assert (stored["dataset_ref_id"], stored["unit"]) == (power, "kWh")
    original = project.get_entry(filled.entries["production_input"])
    assert original["unit"] == "kg"                       # the base entry is untouched


def test_a_unit_that_does_not_fit_the_dataset_is_corrected_before_saving(filled):
    project = filled.project
    entry = project.get_entry(filled.entries["production_input"])
    form = entry_form(filled, entry["node_id"], "production_input", entry, lambda: None)
    import gc
    from lca4pd.app.components import DatasetField
    dataset_field = [o for o in gc.get_objects() if isinstance(o, DatasetField)
                     and o.view in form.select(pn.Row)][-1]
    power = next(r["id"] for r in project.list_dataset_refs(1) if r["unit"] == "kWh")
    dataset_field.value = power                      # dataset changed, unit field left behind
    save = next(b for b in form.select(pn.widgets.Button) if b.name == "Save entry")
    save.clicks += 1
    assert project.get_entry(entry["id"])["dataset_ref_id"] != power   # not saved yet
    unit = next(w for w in form.select(pn.widgets.Select) if w.name == "Unit")
    assert unit.value == "kWh"
    save.clicks += 1
    assert project.get_entry(entry["id"])["unit"] == "kWh"
