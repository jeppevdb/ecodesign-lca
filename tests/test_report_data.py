"""The report's figures, checked against the lamp worked out by hand (see test_calculation)."""

import pytest

from lca4pd.calculation import calculate
from lca4pd.report.data import OWN, ReportData

from test_calculation import model  # noqa: F401  (fixture)

CC = "climate_change"


@pytest.fixture
def report(model):  # noqa: F811
    model.report = ReportData(calculate(model.p, model.library))
    return model


def by_label(series, values):
    return values.groupby(series).sum().round(9).to_dict()


def test_choices(report):
    data = report.report
    assert data.markets == ["EU", "US"] and data.settings == ["average"]
    assert data.stages == ["Raw materials", "Manufacturing", "Distribution", "Use", "End-of-Life"]
    assert list(data.impact_options().values())[0] == "single_score"
    assert data.levels() == 2 and data.unit(CC) == "kg CO2 eq"


def test_every_level_adds_up_to_the_product(report):
    data = report.report
    rows = data.rows(market="EU")
    level1 = by_label(data.at_level(rows, 1), rows[CC])
    assert level1 == pytest.approx({"Housing": 4.53, "LED module": 0.29, "Lamp" + OWN: 60})
    level2 = by_label(data.at_level(rows, 2), rows[CC])
    assert level2 == pytest.approx({
        "Base": 2.32, "Shade": 2.11, "Housing" + OWN: 0.1, "Chip": 0.03,
        "LED module" + OWN: 0.26, "Lamp" + OWN: 60})
    assert sum(level2.values()) == pytest.approx(64.82)


def test_parts_of_an_element(report):
    data = report.report
    rows = data.rows(market="EU")
    housing = data.subtree(rows, report.housing)
    labels, kind = data.parts_of(housing, report.housing)
    assert kind == "elements"
    assert by_label(labels, housing[CC]) == pytest.approx(
        {"Base": 2.32, "Shade": 2.11, "Housing" + OWN: 0.1})
    base = data.subtree(rows, report.base)
    labels, kind = data.parts_of(base, report.base)
    assert kind == "processes"
    assert by_label(labels, base[CC]) == pytest.approx({
        "Steel": 2.1, "distribution: truck": 0.05, "end-of-life: recycling": 0.16,
        "end-of-life: landfill": 0.01})


def test_top90(report):
    data = report.report
    rows = data.rows(market="EU")
    contributors, table = data.top90(rows.groupby("stage")[CC].sum(), "Stage")
    assert contributors == [("Use", 92.6)]
    assert table["Stage"].tolist() == ["Use", "Raw materials", "Remaining"]


def test_sunburst_values_add_up_and_follow_the_tree(report):
    data = report.report
    frame = data.sunburst(data.rows(market="EU"), CC).set_index("id")
    lamp, housing, base = report.lamp, report.housing, report.base
    assert frame.loc[str(lamp), "value"] == pytest.approx(64.82)
    assert frame.loc[f"{lamp}/{housing}", "value"] == pytest.approx(4.53)
    assert frame.loc[f"{lamp}/{housing}/{base}", "parent"] == f"{lamp}/{housing}"
    assert frame.loc[f"{lamp}/own", "label"] == "Lamp" + OWN
    shallow = data.sunburst(data.rows(market="EU"), CC, max_depth=1)
    assert shallow["id"].str.count("/").max() == 1
    housing_only = data.sunburst(data.rows(market="EU"), CC, top=housing)
    assert housing_only.set_index("id").loc[str(housing), "value"] == pytest.approx(4.53)


def test_uncertainty_is_weighted_by_impact(report):
    p = report.p
    p.update_entry(report.base_steel, ped_reliability=4, ped_completeness=4, ped_temporal=4,
                   ped_geographical=4, ped_technological=4)
    data = ReportData(calculate(p, report.library))
    rows = data.rows(market="EU")
    mean, unscored = data.uncertainty(rows, CC)
    assert mean == 4.0 and unscored == pytest.approx(1 - 2.1 / 64.82)


def test_normalised_and_weighted(report):
    data = report.report
    table = data.normalised(data.rows(market="EU")).set_index("Impact category")
    assert table.loc["Climate change", "Normalised (person-year eq.)"] == pytest.approx(64.82 / 7550)
    assert table["Share of single score (%)"].sum() == pytest.approx(100)


def test_tornado_from_one_scenario_at_a_time(report):
    p = report.p
    p.set_toggle("scenarios", True)
    hours = p.add_parameter(p.add_scenario("Use intensity"), "hours", best=0.5, worst=1.5)
    p.link_parameter(hours, "entry", report.use)
    steel = p.add_parameter(p.add_scenario("Steel"), "amount", best=0.9, worst=1.1)
    p.link_parameter(steel, "entry", report.base_steel)
    data = ReportData(calculate(p, report.library))
    table = data.tornado(CC, "EU").set_index("Scenario")
    assert table.index.tolist() == ["Steel", "Use intensity"]       # smallest swing first
    assert table.loc["Use intensity", "best (%)"] == pytest.approx(-30 / 64.82 * 100)
    assert table.loc["Steel", "worst (%)"] == pytest.approx(0.21 / 64.82 * 100)
    housing = data.tornado(CC, "EU", node_id=report.housing).set_index("Scenario")
    assert housing.loc["Use intensity", "best (%)"] == 0


def test_alternatives_compared_with_their_base(report):
    p = report.p
    p.set_toggle("alternatives", True)
    p.set_toggle("cost", True)
    for node, price in {report.lamp: 30, report.housing: 10, report.base: 4, report.shade: 2,
                        report.led: 20, report.chip: 20}.items():
        p.update_node(node, price=price)
    alt = p.create_alternative(report.base, "Lighter base", short_description="less steel")
    p.update_node(alt, weight=0.6, price=5)
    p.update_entry(p.list_entries(alt)[0]["id"], amount=0.63)
    data = ReportData(calculate(p, report.library))
    (alternative,) = data.alternatives()
    assert (alternative.base_id, alternative.alternative_id, alternative.removed) == (
        report.base, alt, False)
    assert alternative.short_description == "less steel"
    lighter = 64.82 - 2.1 + 1.26 - 0.08 + 0.06 - 0.17 + 0.102
    table = data.compare(alternative, CC, "average", "EU").set_index("Version")
    assert table.loc["Base design", "Element impact"] == pytest.approx(2.32)
    assert table.loc["Lighter base", "Element impact"] == pytest.approx(1.26 + 0.03 + 0.102)
    assert table.loc["Lighter base", "Product impact"] == pytest.approx(lighter)
    assert table.loc["Lighter base", "Element cost"] == 5
    summary = data.design_summary(CC, "average", "EU").set_index("Design")
    assert summary.loc["Lighter base", "Cost change"] == 1
    assert summary.loc["Lighter base", "Impact reduction"] == pytest.approx(64.82 - lighter)
    assert summary.loc["Lighter base", "Cost per unit of reduction"] == pytest.approx(
        1 / (64.82 - lighter))


def test_classifications_with_unclassified_share(report):
    p = report.p
    p.update_entry(report.use, ghg_category="3.11", en15804_module="B6")
    p.update_entry(report.base_steel, ghg_category="3.1", en15804_module="A1")
    data = ReportData(calculate(p, report.library))
    rows = data.rows(market="EU")
    ghg = data.ghg(rows).set_index("Category")
    assert ghg.loc["Scope 3.11 – Use of sold products", "Climate change (kg CO2 eq)"] == 60
    assert ghg.loc["Unclassified", "Climate change (kg CO2 eq)"] == pytest.approx(64.82 - 62.1)
    epd = data.en15804(rows).set_index("Impact category")
    assert epd.loc["Climate change", "B6"] == 60 and epd.loc["Climate change", "A1"] == 2.1
    assert epd.loc["Climate change", "Total"] == pytest.approx(64.82)


def test_data_notes(report):
    data = report.report
    notes = data.data_notes(data.rows(market="EU"), CC)
    assert notes == []
