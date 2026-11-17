"""The full LCI overview: every entry in one table, edited with the same checks as the forms."""

import openpyxl
import pytest

from lca4pd.model import ValidationError
from lca4pd.model.overview import (apply_edit, choices, editable_columns, entered_table,
                                   to_xlsx)


def test_one_row_per_entry_in_tree_order(lamp):
    table = entered_table(lamp.p)
    assert table["Element"].tolist() == [
        "Lamp", "Lamp › Housing", "Lamp › Housing › Base", "Lamp › Housing › Shade",
        "Lamp › Housing › Shade", "Lamp › LED module › Chip"]
    steel = table[table["id"] == lamp.base_steel].iloc[0]
    assert (steel["Kind"], steel["Stage"], steel["Dataset"], steel["Amount"], steel["Unit"]) == (
        "Production input", "Raw materials", "steel", 1.05, "kg")
    use = table[table["id"] == lamp.use].iloc[0]
    assert use["Dataset"] == "electricity EU / electricity US" and use["Database"] == "TestDB"


def test_optional_columns_follow_the_setup(lamp):
    p = lamp.p
    assert "GHG category" not in entered_table(p) and "Reliability" not in entered_table(p)
    for toggle in ("ghg_protocol", "en15804", "uncertainty", "internal_numbers", "scenarios"):
        p.set_toggle(toggle, True)
    scenario = p.add_scenario("Use intensity")
    parameter = p.add_parameter(scenario, "hours", best=0.5, worst=1.5)
    p.link_parameter(parameter, "entry", lamp.use)
    table = entered_table(p)
    for column in ("GHG category", "EN 15804 module", "Reliability", "Internal number"):
        assert column in table
    assert table[table["id"] == lamp.use]["Parameters"].item() == "Use intensity – hours"
    assert set(editable_columns(p)) >= {"Amount", "Stage", "GHG category", "Reliability"}


def test_alternatives_are_listed_with_their_name(lamp):
    p = lamp.p
    p.set_toggle("alternatives", True)
    p.create_alternative(lamp.base, "Lighter base")
    p.create_alternative(lamp.shade, "No shade", removed=True)
    table = entered_table(p)
    assert table["Alternative"].tolist().count("Lighter base") == 1
    assert len(table) == 7                       # six base entries + the copied steel entry


def test_edits_change_the_entry(lamp):
    p = lamp.p
    p.set_toggle("ghg_protocol", True)
    p.set_toggle("uncertainty", True)
    apply_edit(p, lamp.base_steel, "Amount", "1.2")
    apply_edit(p, lamp.base_steel, "Stage", "Manufacturing")
    apply_edit(p, lamp.base_steel, "Note", "from supplier quote")
    apply_edit(p, lamp.base_steel, "GHG category", "3.1")
    apply_edit(p, lamp.base_steel, "Reliability", 2)
    entry = p.get_entry(lamp.base_steel)
    assert (entry["amount"], entry["amount_note"], entry["ghg_category"],
            entry["ped_reliability"]) == (1.2, "from supplier quote", "3.1", 2)
    assert entry["stage_id"] == lamp.manufacturing
    apply_edit(p, lamp.base_steel, "GHG category", "")       # emptied again
    assert p.get_entry(lamp.base_steel)["ghg_category"] is None


@pytest.mark.parametrize("column, value", [
    ("Amount", "a lot"), ("Amount", -1), ("Stage", "Use"), ("Stage", "Nonsense"),
    ("Dataset", "plastic"), ("Unit", "g"), ("Kind", "Cost"),
])
def test_refused_edits_leave_the_entry_alone(lamp, column, value):
    before = lamp.p.get_entry(lamp.base_steel)
    with pytest.raises(ValidationError):
        apply_edit(lamp.p, lamp.base_steel, column, value)
    assert lamp.p.get_entry(lamp.base_steel) == before


def test_refused_classification_values(lamp):
    p = lamp.p
    for toggle in ("ghg_protocol", "uncertainty"):
        p.set_toggle(toggle, True)
    for column, value in (("GHG category", "4"), ("Reliability", 7), ("Reliability", "good")):
        with pytest.raises(ValidationError):
            apply_edit(p, lamp.base_steel, column, value)


def test_pick_list_values(lamp):
    lamp.p.set_toggle("ghg_protocol", True)
    assert choices(lamp.p, "Stage")[0] == "Raw materials"
    assert "3.11" in choices(lamp.p, "GHG category")
    assert choices(lamp.p, "Amount") is None


def test_excel_export(lamp, tmp_path):
    table = entered_table(lamp.p).drop(columns="id")
    path = tmp_path / "overview.xlsx"
    path.write_bytes(to_xlsx({"As entered": table}).read())
    sheet = openpyxl.load_workbook(path)["As entered"]
    assert [c.value for c in sheet[1]][:3] == ["Element", "Kind", "Stage"]
    assert sheet.max_row == len(table) + 1
