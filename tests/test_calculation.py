"""The calculation engine, checked against the lamp example worked out by hand.

Impact factors of the test database (climate change, kg CO2-eq per unit):
steel 2/kg, plastic 3/kg, moulding 1/kg, electricity EU 0.5/kWh, US 0.8/kWh,
truck 0.1/tkm, ship 0.01/tkm, recycling 0.2/kg, landfill 0.05/kg,
e-waste incineration 2.5/kg, CO2 1/kg.

Lamp (EU, average case), kg CO2-eq per lamp:
  entries      steel 1.05 kg × 2                       = 2.1
               plastic 0.25 kg × 2 shades × 3          = 1.5
               moulding 0.25 kg × 2 shades × 1         = 0.5
               chip material 0.01 kg × 3               = 0.03
               assembly electricity 0.2 kWh × 0.5      = 0.1
               use 120 kWh × 0.5                       = 60
  supplier     LED 0.1 kg: 400 km truck = 0.04 tkm × 0.1   = 0.004
                           1000 km ship = 0.1 tkm × 0.01   = 0.001
  distribution 1.6 kg × 500 km = 0.8 tkm × 0.1         = 0.08
  end-of-life  base 1 kg: 0.8 × 0.2 + 0.2 × 0.05       = 0.17
               shades 0.5 kg: 0.4 × 0.2 + 0.1 × 0.05   = 0.085
               LED 0.1 kg × 2.5                        = 0.25
  total                                                 64.82
"""

import pytest

from lca4pd.calculation import BlockedError, Results, calculate
from lca4pd.databases import Library
from lca4pd.databases.reader import ImportReport, Item, ParsedDatabase
from lca4pd.method import ef31

CC = "climate_change"
FACTORS = {"steel": 2, "plastic": 3, "injection moulding": 1, "electricity EU": 0.5,
           "electricity US": 0.8, "truck": 0.1, "ship": 0.01, "recycling": 0.2,
           "landfill": 0.05, "e-waste incineration": 2.5}


def values(climate, acidification=0.0):
    row = [0.0] * 16
    row[ef31.CATEGORY_IDS.index(CC)] = float(climate)
    row[ef31.CATEGORY_IDS.index("acidification")] = float(acidification)
    return tuple(row)


@pytest.fixture
def model(lamp):
    """The lamp project connected to a library holding its (made-up) impact factors."""
    library = Library(":memory:")
    refs = {r["dataset_key"]: r for r in lamp.p.list_dataset_refs(lamp.db)}
    items = [Item(key, key, refs[key]["unit"].replace("*", ""), None, None, None,
                  values(factor, acidification=factor / 100))
             for key, factor in FACTORS.items()]
    library.add(ParsedDatabase("process", "test.xlsx", "hash-process", items,
                               ImportReport("test")), "TestDB")
    co2 = Item("carbon dioxide, air", "carbon dioxide", "kg", None, "air", None, values(1))
    library.add(ParsedDatabase("flow", "flows.xlsx", "hash-flows", [co2],
                               ImportReport("test")), "EF 3.1 flows")
    lamp.p.update_database(lamp.db, file_hash="hash-process")
    flow_db = next(d["id"] for d in lamp.p.list_databases() if d["kind"] == "flow")
    lamp.p.update_database(flow_db, file_hash="hash-flows")
    lamp.library = library
    yield lamp
    library.close()


def total(results, column=CC, **run):
    return results.view(**run)[column].sum()


def by(results, key, **run):
    return results.view(**run).groupby(key)[CC].sum().round(9).to_dict()


# ------------------------------------------------------------ base design

def test_lamp_total_matches_hand_calculation(model):
    results = calculate(model.p, model.library)
    assert total(results, market="EU") == pytest.approx(64.82)
    # US: use 120 × 0.8 = 96, distribution 1.6 kg × 7000 km = 11.2 tkm × 0.1 = 1.12
    assert total(results, market="US") == pytest.approx(64.82 - 60 + 96 - 0.08 + 1.12)


def test_contributions_by_source_and_stage(model):
    results = calculate(model.p, model.library)
    assert by(results, "source", market="EU") == pytest.approx({
        "entry": 64.23, "supplier_transport": 0.005, "distribution": 0.08, "end_of_life": 0.505})
    assert by(results, "stage", market="EU") == pytest.approx({
        "Raw materials": 2.1 + 1.5 + 0.03 + 0.005, "Manufacturing": 0.6,
        "Distribution": 0.08, "Use": 60, "End-of-Life": 0.505})


def test_quantities_multiply_up_the_tree(model):
    results = calculate(model.p, model.library)
    shade = results.view(market="EU")
    shade = shade[(shade["node_id"] == model.shade) & (shade["dataset"] == "plastic")]
    assert shade["amount"].item() == pytest.approx(0.5)       # 250 g × 2 shades, in kg
    model.p.update_node(model.housing, quantity=3)
    results = calculate(model.p, model.library)
    shade = results.view(market="EU")
    shade = shade[(shade["node_id"] == model.shade) & (shade["dataset"] == "plastic")]
    assert shade["amount"].item() == pytest.approx(1.5)       # × 3 housings


def test_pathway_impacts_go_to_where_the_weight_came_from(model):
    results = calculate(model.p, model.library)
    eu = results.view(market="EU")
    distribution = eu[eu["source"] == "distribution"].groupby("node_id")[CC].sum().to_dict()
    # 0.08 shared by weight: base 1.0 kg, shades 0.5 kg, LED module 0.1 kg of 1.6 kg
    assert distribution == pytest.approx({model.base: 0.05, model.shade: 0.025, model.led: 0.005})
    # The LED module's weight was entered as a total, so nothing lands on the chip inside it.
    assert model.chip not in set(eu[eu["source"] != "entry"]["node_id"])


def test_each_element_shows_its_whole_life_cycle(model):
    results = calculate(model.p, model.library)
    eu = results.view(market="EU")
    base = results.subtree(eu, model.base)[CC].sum()
    assert base == pytest.approx(2.1 + 0.05 + 0.17)           # steel + distribution + end-of-life
    housing = results.subtree(eu, model.housing)[CC].sum()
    assert housing == pytest.approx(2.1 + 1.5 + 0.5 + 0.1 + 0.075 + 0.255)
    own = eu[eu["node_id"] == model.housing][CC].sum()         # the housing's own slice
    assert own == pytest.approx(0.1)
    assert results.subtree(eu, model.lamp)[CC].sum() == pytest.approx(64.82)


def test_other_categories_and_single_score(model):
    results = calculate(model.p, model.library)
    eu = results.view(market="EU")
    # acidification factors are 1/100 of the climate factors
    assert eu["acidification"].sum() == pytest.approx(64.82 / 100)
    expected = 64.82 / 7550 * 0.2106 + 0.6482 / 55.6 * 0.0620
    assert eu["single_score"].sum() == pytest.approx(expected)


def test_direct_emissions_use_the_flow_factors(model):
    model.p.add_entry(model.base, "production_emission", dataset_ref_id=model.co2,
                      amount=300, unit="g", description="Welding CO2")
    emission = model.p.add_entry(model.lamp, "use", dataset_ref_id=model.co2, amount=2)
    results = calculate(model.p, model.library)
    assert total(results, market="EU") == pytest.approx(64.82 + 0.3 + 2)
    assert total(results, market="US") - total(results, market="EU") == pytest.approx(37.04)
    assert emission  # a use emission is the same in every market


def test_own_weight_of_a_split_element(model):
    # 50 g of glue on the housing itself: e-waste incineration and a share of distribution
    model.p.update_node(model.housing, weight=0.05, eol_own_pathway_id=model.eol_ewaste)
    results = calculate(model.p, model.library)
    eu = results.view(market="EU")
    own = eu[eu["node_id"] == model.housing].groupby("source")[CC].sum().to_dict()
    assert own == pytest.approx({"entry": 0.1, "end_of_life": 0.05 * 2.5,
                                 "distribution": 0.05 / 1000 * 500 * 0.1})


def test_market_specific_end_of_life(model):
    for leg in model.p.list_legs(model.eol_ewaste):
        model.p.update_leg(leg["id"], market_id=model.eu)
    model.p.add_leg(model.eol_ewaste, dataset_ref_id=model.landfill, amount=1,
                    market_id=model.us)
    results = calculate(model.p, model.library)

    def led(market):
        rows = results.view(market=market)
        return rows[(rows["source"] == "end_of_life") & (rows["node_id"] == model.led)][CC].sum()

    assert led("EU") == pytest.approx(0.25) and led("US") == pytest.approx(0.1 * 0.05)


def test_scope_without_use_and_end_of_life(model):
    with model.p.conn:
        model.p.conn.execute("DELETE FROM entry WHERE type = 'use'")
        model.p.conn.execute("DELETE FROM stage WHERE role IN ('use', 'end_of_life')")
    results = calculate(model.p, model.library)
    assert total(results, market="EU") == pytest.approx(64.82 - 60 - 0.505)


def test_blockers_stop_the_calculation(model):
    model.p.update_entry(model.base_steel, amount=None)
    with pytest.raises(BlockedError) as error:
        calculate(model.p, model.library)
    assert [i.code for i in error.value.issues] == ["entry_incomplete"]


def test_exclusions_are_listed(model):
    model.p.add_entry(model.base, "exclusion", description="Paint",
                      exclusion_reason="below 1 % of mass")
    model.p.update_node(model.led, supplier_pathway_id=None,
                        supplier_exclusion_reason="supplier unknown")
    results = calculate(model.p, model.library)
    assert results.exclusions[["element", "what", "reason"]].values.tolist() == [
        ["Base", "Paint", "below 1 % of mass"],
        ["LED module", "Transport from supplier", "supplier unknown"]]
    assert total(results, market="EU") == pytest.approx(64.82 - 0.005)


# -------------------------------------------------------------- scenarios

@pytest.fixture
def scenarios(model):
    p = model.p
    p.set_toggle("scenarios", True)
    recycling = p.add_scenario("Steel recycling")
    up = p.add_parameter(recycling, "recycling share", best=1.125, worst=0.75)
    down = p.add_parameter(recycling, "landfill share", best=0.5, worst=2.0)
    p.link_parameter(up, "pathway_leg", model.leg_recycling)
    p.link_parameter(down, "pathway_leg", model.leg_landfill)
    lifetime = p.add_scenario("Use intensity")
    hours = p.add_parameter(lifetime, "hours of use", best=0.5, worst=1.5)
    p.link_parameter(hours, "entry", model.use)
    return model


def test_average_case_is_unchanged_by_scenarios(scenarios):
    results = calculate(scenarios.p, scenarios.library)
    assert total(results, market="EU", setting="average") == pytest.approx(64.82)


def test_best_and_worst_apply_every_parameter(scenarios):
    results = calculate(scenarios.p, scenarios.library)
    # metal end-of-life per kg: best 0.9 × 0.2 + 0.1 × 0.05 = 0.185, worst 0.6 × 0.2 + 0.4 × 0.05 = 0.14
    # (recycling has the higher factor in this made-up database), 1.5 kg of metal parts
    best = 64.82 - 60 + 30 + 1.5 * (0.185 - 0.17)
    worst = 64.82 - 60 + 90 + 1.5 * (0.14 - 0.17)
    assert total(results, market="EU", setting="best") == pytest.approx(best)
    assert total(results, market="EU", setting="worst") == pytest.approx(worst)


def test_one_scenario_at_a_time(scenarios):
    results = calculate(scenarios.p, scenarios.library)
    run = dict(market="EU", varied_scenario="Use intensity")
    assert total(results, setting="best", **run) == pytest.approx(64.82 - 30)
    assert total(results, setting="worst", **run) == pytest.approx(64.82 + 30)
    run = dict(market="EU", varied_scenario="Steel recycling")
    assert total(results, setting="best", **run) == pytest.approx(64.82 + 1.5 * 0.015)
    totals = results.totals()
    assert len(totals) == 2 * 3 + 2 * 2 * 2      # markets × settings + scenarios × best/worst × markets


def test_scenario_the_wrong_way_round_is_flagged(scenarios):
    results = calculate(scenarios.p, scenarios.library)
    (warning,) = {w.split(" (market")[0] for w in results.scenario_direction_warnings()}
    assert "Steel recycling" in warning       # here more recycling scores worse


def test_weight_parameter_carries_through_to_pathways(scenarios):
    p = scenarios.p
    weight = p.add_scenario("Base weight")
    lighter = p.add_parameter(weight, "base weight", best=0.8, worst=1.2)
    p.link_parameter(lighter, "node_weight", scenarios.base)
    results = calculate(p, scenarios.library)
    best = results.view(market="EU", setting="best", varied_scenario="Base weight")
    base = best[best["node_id"] == scenarios.base].groupby("source")[CC].sum().to_dict()
    # 0.8 kg: distribution 0.8/1000 × 500 × 0.1, end-of-life 0.8 × 0.17; steel input unchanged
    assert base == pytest.approx({"entry": 2.1, "distribution": 0.04, "end_of_life": 0.136})


# ----------------------------------------------------------- alternatives

def test_alternative_replaces_its_base_element(model):
    p = model.p
    p.set_toggle("alternatives", True)
    alt = p.create_alternative(model.base, "Lighter base")
    p.update_node(alt, weight=0.6)
    p.update_entry(p.list_entries(alt)[0]["id"], amount=0.63)
    results = calculate(p, model.library)
    assert total(results, market="EU") == pytest.approx(64.82)            # base untouched
    # steel 0.63 × 2 = 1.26; distribution 1.2 kg → 0.06; end-of-life base 0.6 × 0.17 = 0.102
    expected = 64.82 - 2.1 + 1.26 - 0.08 + 0.06 - 0.17 + 0.102
    assert total(results, design="Lighter base", market="EU") == pytest.approx(expected)
    rows = results.view(design="Lighter base", market="EU")
    assert model.base not in set(rows["node_id"]) and alt in set(rows["node_id"])
    assert results.subtree(rows, alt)[CC].sum() == pytest.approx(1.26 + 0.03 + 0.102)


def test_removed_alternative_drops_the_element(model):
    model.p.set_toggle("alternatives", True)
    model.p.create_alternative(model.shade, "No shade", removed=True)
    results = calculate(model.p, model.library)
    # without shades: no plastic, no moulding, 1.1 kg distributed, no shade end-of-life
    expected = 64.82 - 1.5 - 0.5 - 0.08 + 0.055 - 0.085
    assert total(results, design="No shade", market="EU") == pytest.approx(expected)


def test_alternatives_are_ignored_when_switched_off(model):
    model.p.create_alternative(model.shade, "No shade", removed=True)
    results = calculate(model.p, model.library)
    assert set(results.inventory["design"]) == {"Base design"}


# ------------------------------------------------------------------- cost

def test_cost_follows_alternatives_and_price_parameters(model):
    p = model.p
    p.set_toggle("cost", True)
    p.set_toggle("alternatives", True)
    p.set_toggle("scenarios", True)
    for node, price in {model.lamp: 30, model.housing: 10, model.base: 4, model.shade: 2,
                        model.led: 20, model.chip: 20}.items():
        p.update_node(node, price=price)
    alt = p.create_alternative(model.shade, "Glass shade")
    p.update_node(alt, price=3.5, weight=0.3)
    steel_price = p.add_scenario("Steel price")
    parameter = p.add_parameter(steel_price, "base price", best=0.5, worst=1.5)
    p.link_parameter(parameter, "node_price", model.base)
    results = calculate(p, model.library)

    def cost(node, **run):
        run = {"design": "Base design", "setting": "average", "market": "EU", **run}
        frame = results.costs
        mask = (frame["node_id"] == node) & frame["varied_scenario"].isna()
        for column, value in run.items():
            mask &= frame[column] == value
        return frame[mask]["cost"].item()

    assert cost(model.lamp) == 30 and cost(model.shade) == 4          # 2 shades × 2
    # glass shades cost 2 × 1.5 more; the difference is carried up to the lamp
    assert cost(model.lamp, design="Glass shade") == pytest.approx(33)
    assert cost(model.housing, design="Glass shade") == pytest.approx(13)
    # steel price −50 %: the base is 2 cheaper, and so is the lamp
    assert cost(model.lamp, setting="best") == pytest.approx(28)
    assert cost(model.lamp, setting="worst") == pytest.approx(32)


# ---------------------------------------------------------------- results

def test_results_are_saved_next_to_the_project_and_go_stale(model, tmp_path):
    results = calculate(model.p, model.library)
    path = tmp_path / "lamp.results"
    results.save(path)
    loaded = Results.load(path)
    assert total(loaded, market="EU") == pytest.approx(64.82)
    assert len(loaded.inventory) == len(results.inventory)
    assert loaded.is_current(model.p)
    model.p.update_entry(model.base_steel, amount=1.1)
    assert not loaded.is_current(model.p)


def test_uncertainty_score_is_the_mean_of_five(model):
    model.p.update_entry(model.base_steel, ped_reliability=1, ped_completeness=2,
                         ped_temporal=3, ped_geographical=4, ped_technological=5)
    rows = calculate(model.p, model.library).view(market="EU")
    steel = rows[rows["dataset"] == "steel"]["uncertainty_score"].item()
    assert steel == 3.0 and rows["uncertainty_score"].isna().sum() == len(rows) - 1
