"""Project-wide checks: what the missing-items panel reports."""

import pytest

from lca4pd.model import Project, check_project
from lca4pd.model.checks import has_blockers


def codes(project, severity=None):
    return [i.code for i in check_project(project) if severity in (None, i.severity)]


def blockers(project):
    return codes(project, "blocker")


def warnings(project):
    return codes(project, "warning")


def test_complete_project_has_no_open_items(lamp):
    assert check_project(lamp.p) == []


def test_empty_project_lists_the_first_steps(empty):
    assert set(blockers(empty)) == {"no_market", "no_database", "no_product"}
    assert has_blockers(check_project(empty))


def test_issue_points_to_where_it_is_fixed(lamp):
    lamp.p.update_entry(lamp.base_steel, amount=None)
    (issue,) = check_project(lamp.p)
    assert (issue.severity, issue.code) == ("blocker", "entry_incomplete")
    assert (issue.target_type, issue.target_id) == ("entry", lamp.base_steel)
    assert "Steel" in issue.message and "Base" in issue.message


# ------------------------------------------------------------- entries

def test_entry_without_dataset_blocks(lamp):
    lamp.p.add_entry(lamp.base, "production_waste", amount=0.05)
    assert blockers(lamp.p) == ["entry_incomplete"]


def test_use_entry_needs_a_dataset_for_every_market(lamp):
    lamp.p.set_market_dataset(lamp.use, lamp.us, None)
    assert blockers(lamp.p) == ["use_market_dataset_missing"]
    lamp.p.add_market("China")
    assert blockers(lamp.p).count("use_market_dataset_missing") == 2


def test_element_without_content_blocks(lamp):
    bolt = lamp.p.add_node(lamp.housing, "Bolt", weight=0.01, production_site="on_site",
                           eol_mode="whole", eol_pathway_id=lamp.eol_metal)
    assert blockers(lamp.p) == ["node_empty"]
    # A documented exclusion is the explicit way around a gap.
    lamp.p.add_entry(bolt, "exclusion", description="Bolt", exclusion_reason="negligible")
    assert blockers(lamp.p) == []


def test_dataset_gone_from_database_blocks(lamp):
    with lamp.p.conn:
        lamp.p.conn.execute("UPDATE dataset_ref SET missing = 1 WHERE id = ?", (lamp.steel,))
    assert blockers(lamp.p) == ["dataset_missing"]


def test_flagged_use_inputs_without_entries_warns(lamp):
    lamp.p.update_node(lamp.base, has_use_inputs=True)
    assert warnings(lamp.p) == ["use_entries_missing"]


# --------------------------------------------------- supplier and site

def test_production_site_must_be_answered(lamp):
    lamp.p.update_node(lamp.base, production_site=None)
    assert blockers(lamp.p) == ["production_site_unanswered"]


def test_supplier_needs_a_pathway_or_an_exclusion(lamp):
    lamp.p.update_node(lamp.led, supplier_pathway_id=None)
    assert blockers(lamp.p) == ["supplier_pathway_missing"]
    lamp.p.update_node(lamp.led, supplier_exclusion_reason="supplier location unknown")
    assert blockers(lamp.p) == []


def test_elements_below_a_supplied_element_are_not_asked(lamp):
    # 'Chip' sits inside the bought-in LED module and never answered the question.
    assert lamp.p.get_node(lamp.chip)["production_site"] is None
    assert blockers(lamp.p) == []


# -------------------------------------------------------- end of life

def test_end_of_life_question_must_be_answered(lamp):
    lamp.p.update_node(lamp.base, eol_mode=None, eol_pathway_id=None)
    assert blockers(lamp.p) == ["eol_unanswered"]


def test_lowest_element_cannot_pass_the_question_down(lamp):
    lamp.p.update_node(lamp.base, eol_mode="split", eol_pathway_id=None)
    assert blockers(lamp.p) == ["eol_pathway_missing"]
    lamp.p.update_node(lamp.base, eol_mode="excluded", eol_exclusion_reason="reused by customer")
    assert blockers(lamp.p) == []


def test_own_weight_of_a_split_element_needs_a_pathway(lamp):
    # 50 g of glue on the housing itself belongs to neither the base nor the shade.
    lamp.p.update_node(lamp.housing, weight=0.05)
    assert blockers(lamp.p) == ["eol_own_weight_uncovered"]
    lamp.p.update_node(lamp.housing, eol_own_pathway_id=lamp.eol_ewaste)
    assert blockers(lamp.p) == []


def test_end_of_life_pathway_must_cover_every_market(lamp):
    for leg in lamp.p.list_legs(lamp.eol_ewaste):
        lamp.p.update_leg(leg["id"], market_id=lamp.eu)
    assert blockers(lamp.p) == ["eol_market_missing"]


def test_end_of_life_shares_should_add_up(lamp):
    lamp.p.update_leg(lamp.leg_landfill, amount=0.1)
    assert warnings(lamp.p) == ["eol_shares", "eol_shares"]   # one per market


def test_scope_without_end_of_life_asks_nothing(lamp):
    p = lamp.p
    p.update_node(lamp.base, eol_mode=None, eol_pathway_id=None)
    with p.conn:  # drop the stage from the scope
        p.conn.execute("DELETE FROM stage WHERE role = 'end_of_life'")
    assert blockers(p) == []
    assert p.questions_for(lamp.base)["eol"] is False


# -------------------------------------------------------------- weight

def test_missing_weight_blocks_where_a_pathway_needs_it(lamp):
    lamp.p.update_node(lamp.shade, weight=None)
    issues = [i for i in check_project(lamp.p) if i.severity == "blocker"]
    assert [(i.code, i.target_id) for i in issues] == [("weight_missing", lamp.shade)]


def test_total_tick_needs_a_weight(lamp):
    lamp.p.update_node(lamp.led, weight=None)
    assert blockers(lamp.p) == ["weight_missing"]


def test_total_weight_makes_weights_below_optional(lamp):
    # The chip inside the LED module has no weight; the module's total covers it.
    assert lamp.p.get_node(lamp.chip)["weight"] is None
    assert blockers(lamp.p) == []


def test_material_inputs_should_match_the_weight(lamp):
    lamp.p.update_entry(lamp.base_steel, amount=0.4)      # base weighs 1 kg
    assert warnings(lamp.p) == ["weight_material_mismatch"]


def test_material_on_an_element_without_own_weight_warns(lamp):
    lamp.p.add_entry(lamp.housing, "production_input", stage_id=lamp.raw,
                     dataset_ref_id=lamp.plastic, amount=50, unit="g", description="Glue")
    assert warnings(lamp.p) == ["weight_material_mismatch"]


# ---------------------------------------------------------------- cost

def test_cost_is_only_checked_when_enabled(lamp):
    lamp.p.update_node(lamp.housing, price=10)
    assert check_project(lamp.p) == []
    lamp.p.set_toggle("cost", True)
    assert set(warnings(lamp.p)) == {"price_missing"}


def test_cost_of_parts_should_add_up(lamp):
    p = lamp.p
    p.set_toggle("cost", True)
    prices = {lamp.lamp: 30, lamp.housing: 10, lamp.base: 4, lamp.shade: 2,
              lamp.led: 20, lamp.chip: 20}
    for node, price in prices.items():
        p.update_node(node, price=price)
    # Housing 10 = base 4 + 2 shades × 2 = 8  ->  2 short
    issues = [i for i in check_project(p) if i.code == "cost_mismatch"]
    assert [i.target_id for i in issues] == [lamp.housing]
    assert "+2" in issues[0].message
    p.add_entry(lamp.housing, "cost", amount=2, description="Assembly labour")
    assert check_project(p) == []


# ---------------------------------------------------------- pathways

def test_every_market_needs_distribution(lamp):
    lamp.p.add_market("China")
    assert "distribution_missing" in blockers(lamp.p)


def test_used_pathway_needs_complete_legs(lamp):
    p = lamp.p
    for leg in p.list_legs(lamp.supplier):
        p.remove_leg(leg["id"])
    assert blockers(p) == ["pathway_empty"]
    p.add_leg(lamp.supplier, dataset_ref_id=lamp.truck)
    assert blockers(p) == ["leg_incomplete"]


def test_unused_pathway_is_not_checked(lamp):
    lamp.p.add_pathway("supplier", "Future supplier")
    assert check_project(lamp.p) == []


# --------------------------------------------------------- scenarios

@pytest.fixture
def recycling(lamp):
    """Scenario with two parameters that move together and keep the shares at 100 %."""
    p = lamp.p
    p.set_toggle("scenarios", True)
    scenario = p.add_scenario("Steel recycling")
    lamp.up = p.add_parameter(scenario, "recycling share", best=1.125, worst=0.75)
    lamp.down = p.add_parameter(scenario, "landfill share", best=0.5, worst=2.0)
    p.link_parameter(lamp.up, "pathway_leg", lamp.leg_recycling)
    p.link_parameter(lamp.down, "pathway_leg", lamp.leg_landfill)
    return lamp


def test_consistent_scenario_has_no_open_items(recycling):
    assert check_project(recycling.p) == []


def test_parameter_needs_best_and_worst(recycling):
    recycling.p.update_parameter(recycling.up, worst=None)
    assert blockers(recycling.p) == ["parameter_incomplete"]


def test_shares_are_checked_in_best_and_worst_case(recycling):
    recycling.p.update_parameter(recycling.down, best=1.0)   # 0.9 + 0.2 in the best case
    issues = [i for i in check_project(recycling.p) if i.code == "eol_shares"]
    assert len(issues) == 2 and all("best case" in i.message for i in issues)


def test_parameter_and_scenario_without_effect_warn(recycling):
    p = recycling.p
    p.unlink_parameter(recycling.down, "pathway_leg", recycling.leg_landfill)
    p.update_parameter(recycling.up, best=1.0, worst=1.0)
    p.add_scenario("Empty")
    assert sorted(warnings(p)) == ["parameter_unlinked", "scenario_empty"]


def test_scenarios_are_ignored_when_switched_off(recycling):
    recycling.p.update_parameter(recycling.up, worst=None)
    recycling.p.set_toggle("scenarios", False)
    assert check_project(recycling.p) == []


# ------------------------------------------------------ alternatives

def test_untouched_copy_is_flagged_as_identical(lamp):
    p = lamp.p
    p.set_toggle("alternatives", True)
    alt = p.create_alternative(lamp.housing, "Lighter housing")
    assert warnings(p) == ["alternative_identical"]
    alt_base = p.children(alt)[0]["id"]
    p.update_node(alt_base, weight=0.8)
    p.update_entry(p.list_entries(alt_base)[0]["id"], amount=0.84)
    assert check_project(p) == []


def test_alternative_must_be_as_complete_as_the_base(lamp):
    p = lamp.p
    p.set_toggle("alternatives", True)
    alt = p.create_alternative(lamp.shade, "Glass shade", copy=False)
    found = {(i.code, i.target_id) for i in check_project(p) if i.severity == "blocker"}
    assert found == {("node_empty", alt), ("production_site_unanswered", alt),
                     ("eol_unanswered", alt), ("weight_missing", alt)}


def test_removed_alternative_needs_nothing(lamp):
    lamp.p.set_toggle("alternatives", True)
    lamp.p.create_alternative(lamp.shade, "No shade", removed=True)
    assert check_project(lamp.p) == []


# ------------------------------------------- optional classifications

@pytest.mark.parametrize("toggle, code", [
    ("uncertainty", "pedigree_missing"),
    ("ghg_protocol", "ghg_category_missing"),
    ("en15804", "en15804_module_missing"),
])
def test_unfilled_optional_fields_warn_but_do_not_block(lamp, toggle, code):
    lamp.p.set_toggle(toggle, True)
    issues = check_project(lamp.p)
    assert not has_blockers(issues)
    # 6 calculated entries and 7 pathway legs
    assert [i.code for i in issues].count(code) == 13
    assert {i.code for i in issues} == {code}


def test_internal_numbers(lamp):
    p = lamp.p
    p.set_toggle("internal_numbers", True)
    assert warnings(p).count("internal_number_missing") == 6
    for node in (lamp.lamp, lamp.housing, lamp.led, lamp.chip):
        p.update_node(node, internal_number=f"N-{node}")
    p.update_node(lamp.base, internal_number="P-100")
    p.update_node(lamp.shade, internal_number="P-100")
    assert warnings(p) == ["internal_number_conflict"] * 2
    # A copy keeps name and number: that is deliberate reuse, not a conflict.
    p.update_node(lamp.shade, internal_number="P-200")
    p.duplicate_node(lamp.shade, lamp.lamp)
    assert "internal_number_conflict" not in warnings(p)


# ----------------------------------------------------------- databases

def test_database_gaps_are_reported_when_the_database_is_used(lamp):
    p = lamp.p
    idemat = p.add_database("process", "IdeMat", coverage={
        "derived": True, "missing_categories": ["Water use"]})
    assert check_project(p) == []          # uploaded but not used
    ref = p.dataset_ref(idemat, "A.1", name="Leather", unit="kg")
    p.update_entry(lamp.base_steel, dataset_ref_id=ref)
    assert sorted(warnings(p)) == ["database_coverage", "database_derived"]
