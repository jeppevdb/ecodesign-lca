"""Instant checks: what the project refuses at the moment of entry."""

import pytest

from lca4pd.model import NotFoundError, Project, ValidationError


def test_new_project_has_default_stages_and_no_options(empty):
    assert [s["name"] for s in empty.list_stages()] == [
        "Raw materials", "Manufacturing", "Distribution", "Use", "End-of-Life"]
    assert not any(empty.toggles.values())
    assert empty.get_setting("name") == "Test"


def test_project_file_round_trip(tmp_path):
    path = tmp_path / "lamp.lca4pd"
    with Project.create(path, "Lamp") as p:
        p.set_toggle("cost", True)
        p.add_node(None, "Lamp", price=20)
    with Project.open(path) as p:
        assert p.toggles["cost"] is True
        assert p.root()["price"] == 20
    with pytest.raises(ValidationError):
        Project.create(path, "Again")
    with pytest.raises(NotFoundError):
        Project.open(tmp_path / "missing.lca4pd")


# ---------------------------------------------------------------- setup

def test_stage_rules(empty, lamp):
    with pytest.raises(ValidationError):
        empty.add_stage("use")                       # name exists (case-insensitive)
    with pytest.raises(ValidationError):
        empty.add_stage("Second use", role="use")    # one stage per role
    custom = empty.add_stage("Installation")
    empty.rename_stage(custom, "Commissioning")
    empty.remove_stage(custom)
    with pytest.raises(ValidationError):
        lamp.p.remove_stage(lamp.raw)                # still used by entries


def test_market_names_are_unique(empty):
    empty.add_market("EU")
    with pytest.raises(ValidationError):
        empty.add_market("eu")


def test_unknown_option_is_refused(empty):
    with pytest.raises(ValidationError):
        empty.set_toggle("magic", True)


# ----------------------------------------------------------------- tree

def test_only_one_product(lamp):
    with pytest.raises(ValidationError):
        lamp.p.add_node(None, "Second product")


@pytest.mark.parametrize("fields", [
    {"name": "  "}, {"quantity": 0}, {"quantity": -1}, {"quantity": "many"},
    {"quantity": float("nan")}, {"weight": -0.1}, {"price": -5},
    {"production_site": "abroad"}, {"eol_mode": "excluded"},
])
def test_invalid_node_values(lamp, fields):
    with pytest.raises(ValidationError):
        lamp.p.update_node(lamp.base, **fields)


def test_sibling_names_are_unique(lamp):
    with pytest.raises(ValidationError):
        lamp.p.add_node(lamp.housing, "base")
    lamp.p.add_node(lamp.lamp, "Base")  # same name elsewhere is fine


def test_pathway_kind_must_match(lamp):
    with pytest.raises(ValidationError):
        lamp.p.update_node(lamp.base, eol_pathway_id=lamp.supplier)
    with pytest.raises(ValidationError):
        lamp.p.update_node(lamp.base, supplier_pathway_id=lamp.eol_metal)


def test_questions_follow_the_answers_higher_up(lamp):
    p = lamp.p
    assert p.questions_for(lamp.base) == {"production_site": True, "eol": True, "use": True}
    # The LED module comes from a supplier and has one end-of-life pathway as a whole.
    assert p.questions_for(lamp.chip) == {"production_site": False, "eol": False, "use": True}


def test_move_node(lamp):
    p = lamp.p
    p.move_node(lamp.shade, lamp.lamp)
    assert p.get_node(lamp.shade)["parent_id"] == lamp.lamp
    with pytest.raises(ValidationError):
        p.move_node(lamp.housing, lamp.base)       # into itself
    with pytest.raises(ValidationError):
        p.move_node(lamp.lamp, lamp.housing)       # the product


def test_duplicate_copies_everything_below(lamp):
    p = lamp.p
    copy = p.duplicate_node(lamp.housing)
    assert p.get_node(copy)["name"] == "Housing (copy)"
    assert [c["name"] for c in p.children(copy)] == ["Base", "Shade"]
    copied_base = p.children(copy)[0]["id"]
    assert [e["description"] for e in p.list_entries(copied_base)] == ["Steel"]
    # Independent: changing the copy leaves the original alone.
    p.update_node(copied_base, weight=9)
    assert p.get_node(lamp.base)["weight"] == 1.0


def test_delete_removes_subtree_and_parameter_links(lamp):
    p = lamp.p
    scenario = p.add_scenario("Steel use")
    parameter = p.add_parameter(scenario, "steel amount", best=0.9, worst=1.1)
    p.link_parameter(parameter, "entry", lamp.base_steel)
    p.link_parameter(parameter, "node_weight", lamp.base)
    p.delete_node(lamp.housing)
    with pytest.raises(NotFoundError):
        p.get_node(lamp.base)
    assert p.parameter_links(parameter) == []


# -------------------------------------------------------------- entries

def test_production_input_needs_a_stage(lamp):
    with pytest.raises(ValidationError) as error:
        lamp.p.add_entry(lamp.base, "production_input", dataset_ref_id=lamp.steel, amount=1)
    assert error.value.field == "stage_id"


def test_entry_takes_dataset_unit_and_converts_compatible_ones(lamp):
    p = lamp.p
    entry = p.add_entry(lamp.base, "production_input", stage_id=lamp.raw,
                        dataset_ref_id=lamp.steel, amount=3)
    assert p.get_entry(entry)["unit"] == "kg"
    p.update_entry(entry, unit="g", amount=3000)
    with pytest.raises(ValidationError) as error:
        p.update_entry(entry, unit="kWh")
    assert error.value.field == "unit"
    # Choosing another dataset switches to that dataset's unit.
    p.update_entry(entry, dataset_ref_id=lamp.el_eu)
    assert p.get_entry(entry)["unit"] == "kWh"


def test_negative_amount_needs_confirmation(lamp):
    p = lamp.p
    with pytest.raises(ValidationError):
        p.add_entry(lamp.base, "production_waste", dataset_ref_id=lamp.recycling, amount=-0.05)
    entry = p.add_entry(lamp.base, "production_waste", dataset_ref_id=lamp.recycling,
                        amount=-0.05, confirm_negative=True)
    p.update_entry(entry, amount_note="credit for recycled offcuts")  # no new confirmation


@pytest.mark.parametrize("amount", ["a lot", float("inf")])
def test_amount_must_be_a_number(lamp, amount):
    with pytest.raises(ValidationError):
        lamp.p.update_entry(lamp.base_steel, amount=amount)


def test_dataset_kind_must_fit_entry_type(lamp):
    p = lamp.p
    with pytest.raises(ValidationError):
        p.add_entry(lamp.base, "production_emission", dataset_ref_id=lamp.steel, amount=1)
    with pytest.raises(ValidationError):
        p.add_entry(lamp.base, "production_input", stage_id=lamp.raw,
                    dataset_ref_id=lamp.co2, amount=1)
    p.add_entry(lamp.base, "production_emission", dataset_ref_id=lamp.co2, amount=0.3)


def test_use_entries_only_on_flagged_elements(lamp):
    p = lamp.p
    with pytest.raises(ValidationError):
        p.add_entry(lamp.base, "use", amount=1)
    with pytest.raises(ValidationError):
        p.update_node(lamp.lamp, has_use_inputs=False)   # still has a use entry
    emission = p.add_entry(lamp.lamp, "use", dataset_ref_id=lamp.co2, amount=0.1)
    with pytest.raises(ValidationError):
        p.set_market_dataset(emission, lamp.eu, lamp.el_eu)  # direct emission, not per market


def test_use_market_datasets_must_share_a_unit(lamp):
    with pytest.raises(ValidationError):
        lamp.p.set_market_dataset(lamp.use, lamp.us, lamp.steel)


def test_exclusion_needs_description_and_reason(lamp):
    p = lamp.p
    with pytest.raises(ValidationError):
        p.add_entry(lamp.base, "exclusion", description="Paint")
    p.add_entry(lamp.base, "exclusion", description="Paint", exclusion_reason="below 1 % of mass")


@pytest.mark.parametrize("fields", [
    {"ghg_category": "4"}, {"en15804_module": "Z9"}, {"ped_reliability": 6},
    {"ped_temporal": 2.5},
])
def test_classification_values_come_from_the_lists(lamp, fields):
    with pytest.raises(ValidationError):
        lamp.p.update_entry(lamp.base_steel, **fields)


def test_valid_classification_is_stored(lamp):
    lamp.p.update_entry(lamp.base_steel, ghg_category="3.1", en15804_module="A1",
                        ped_reliability=2)
    entry = lamp.p.get_entry(lamp.base_steel)
    assert (entry["ghg_category"], entry["en15804_module"], entry["ped_reliability"]) == (
        "3.1", "A1", 2)


# ------------------------------------------------------------- pathways

def test_one_distribution_pathway_per_market(lamp):
    with pytest.raises(ValidationError):
        lamp.p.add_pathway("gate_to_customer", market_id=lamp.eu)
    with pytest.raises(ValidationError):
        lamp.p.add_pathway("gate_to_customer")


def test_leg_datasets_must_fit_the_pathway(lamp):
    p = lamp.p
    with pytest.raises(ValidationError):
        p.add_leg(lamp.supplier, dataset_ref_id=lamp.steel, amount=100)     # not transport
    with pytest.raises(ValidationError):
        p.add_leg(lamp.eol_metal, dataset_ref_id=lamp.truck, amount=0.5)    # not per mass
    with pytest.raises(ValidationError):
        p.add_leg(lamp.supplier, dataset_ref_id=lamp.truck, amount=100, unit="kg")
    with pytest.raises(ValidationError):
        p.add_leg(lamp.supplier, dataset_ref_id=lamp.truck, amount=100, market_id=lamp.eu)


def test_used_pathway_cannot_be_removed(lamp):
    with pytest.raises(ValidationError):
        lamp.p.remove_pathway(lamp.supplier)


def test_used_database_cannot_be_removed(lamp):
    with pytest.raises(ValidationError):
        lamp.p.remove_database(lamp.db)


# ------------------------------------------------------------ scenarios

def test_parameter_values_and_targets(lamp):
    p = lamp.p
    scenario = p.add_scenario("Recycling")
    with pytest.raises(ValidationError):
        p.add_parameter(scenario, "share", best=-1)
    parameter = p.add_parameter(scenario, "share", best=1.125, worst=0.5)
    with pytest.raises(ValidationError):
        p.add_parameter(scenario, "Share")
    with pytest.raises(ValidationError):
        p.link_parameter(parameter, "node_colour", lamp.base)
    with pytest.raises(NotFoundError):
        p.link_parameter(parameter, "entry", 9999)
    for target_type, target in (("entry", lamp.base_steel), ("pathway_leg", lamp.leg_recycling),
                                ("node_weight", lamp.base), ("node_price", lamp.base)):
        p.link_parameter(parameter, target_type, target)
    assert len(p.parameter_links(parameter)) == 4


# --------------------------------------------------------- alternatives

def test_alternative_starts_as_copy_of_base(lamp):
    p = lamp.p
    alt = p.create_alternative(lamp.housing, "Aluminium housing", short_description="Al")
    node = p.get_node(alt)
    assert node["alternative_of"] == lamp.housing and node["parent_id"] == lamp.lamp
    assert [c["name"] for c in p.children(alt)] == ["Base", "Shade"]
    assert [c["name"] for c in p.children(lamp.lamp)] == ["Housing", "LED module"]
    assert [d["name"] for d in p.list_designs()] == ["Base design", "Aluminium housing"]
    assert p.list_designs()[1]["substitutions"] == {lamp.housing: alt}


def test_alternative_can_start_empty_or_removed(lamp):
    p = lamp.p
    empty_alt = p.create_alternative(lamp.shade, "New shade", copy=False)
    assert p.list_entries(empty_alt) == [] and p.get_node(empty_alt)["quantity"] == 2
    removed = p.create_alternative(lamp.shade, "No shade", removed=True)
    with pytest.raises(ValidationError):
        p.add_node(removed, "Something")
    with pytest.raises(ValidationError):
        p.add_entry(removed, "cost", amount=1)


def test_alternative_names_unique_per_element(lamp):
    lamp.p.create_alternative(lamp.shade, "Glass")
    with pytest.raises(ValidationError):
        lamp.p.create_alternative(lamp.shade, "glass")


def test_no_alternatives_inside_alternatives(lamp):
    p = lamp.p
    alt = p.create_alternative(lamp.housing, "Aluminium housing")
    with pytest.raises(ValidationError):
        p.create_alternative(alt, "Nested")
    with pytest.raises(ValidationError):
        p.create_alternative(p.children(alt)[0]["id"], "Nested deeper")
    # Alternatives elsewhere in the base tree stay possible …
    p.create_alternative(lamp.shade, "Glass")
    # … but such an element cannot then be moved into an alternative.
    with pytest.raises(ValidationError):
        p.move_node(lamp.shade, alt)


def test_alternative_follows_its_base_when_moved(lamp):
    p = lamp.p
    alt = p.create_alternative(lamp.shade, "Glass")
    p.move_node(lamp.shade, lamp.lamp)
    assert p.get_node(alt)["parent_id"] == lamp.lamp


# ------------------------------------------------- links and differences

def test_set_links_makes_exactly_these_parameters_act(lamp):
    p = lamp.p
    scenario = p.add_scenario("S")
    a = p.add_parameter(scenario, "a", best=0.9, worst=1.1)
    b = p.add_parameter(scenario, "b", best=0.8, worst=1.2)
    p.set_links("entry", lamp.base_steel, [a, b])
    assert p.links_for("entry", lamp.base_steel) == [a, b]
    p.set_links("entry", lamp.base_steel, [b])
    assert p.links_for("entry", lamp.base_steel) == [b]
    p.set_links("node_weight", lamp.base, [a])
    assert p.links_for("node_weight", lamp.base) == [a]


def test_differences_of_an_alternative(lamp):
    from lca4pd.model.diff import diff_alternative
    p = lamp.p
    alt = p.create_alternative(lamp.housing, "Lighter housing")
    assert diff_alternative(p, alt) == []
    alt_base, alt_shade = (c["id"] for c in p.children(alt))
    p.update_node(alt_base, weight=0.6)
    p.update_entry(p.list_entries(alt_base)[0]["id"], amount=0.63)
    p.delete_node(alt_shade)
    glass = p.add_node(alt, "Glass shade", weight=0.3)
    p.add_entry(alt, "exclusion", description="Paint", exclusion_reason="tiny")
    assert diff_alternative(p, alt) == [
        "Housing: added entry Paint",
        "Housing › Base: Weight 1 kg → 0.6 kg",
        "Housing › Base: Steel: amount 1.05 kg → 0.63 kg",
        "Housing: removed element Shade",
        "Housing: added element Glass shade",
    ]
    assert glass
    removed = p.create_alternative(lamp.shade, "No shade", removed=True)
    assert diff_alternative(p, removed) == ["Shade: the element is removed"]


def test_difference_names_a_changed_dataset(lamp):
    from lca4pd.model.diff import diff_alternative
    p = lamp.p
    alt = p.create_alternative(lamp.base, "Plastic base")
    p.update_entry(p.list_entries(alt)[0]["id"], dataset_ref_id=lamp.plastic)
    assert diff_alternative(p, alt) == ["Base: Steel: dataset steel → plastic"]
