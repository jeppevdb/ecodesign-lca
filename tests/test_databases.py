"""Database import, tested on small made-up workbooks in the layouts of the real files."""

import zipfile

import openpyxl
import pytest

from lca4pd.databases import (Library, ProtocolMismatch, describe_headings, detect_file,
                              link, load_protocols, read_file)
from lca4pd.databases.reader import repair_text
from lca4pd.databases.sheets import iter_rows, sheet_names
from lca4pd.method import ef31
from lca4pd.model import Project, check_project

PROTOCOLS = load_protocols()
CC = ef31.CATEGORY_IDS.index("climate_change")
WATER = ef31.CATEGORY_IDS.index("water_use")


def bafu_headings():
    """The 16 EF headings of the BAFU protocol, in a different order than the tool's."""
    return sorted(labels[0] for labels in PROTOCOLS["bafu"].categories.values())


def write(path, sheets: dict):
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    workbook.save(path)
    return path


@pytest.fixture
def bafu_file(tmp_path):
    headings = bafu_headings()
    cc = headings.index("Climate change [kg CO2 eq]")

    def values(climate):
        row = [0.5] * 16
        row[cc] = climate
        return row

    # "Land use" also exists under another method: only the EF 3.1 block may be read.
    rows = [
        [None, None, None, None, "IPCC 2021", "Ecological Scarcity 2021", "EF 3.1"],
        ["Product", "Category", "Sub-category", "Unit", "GWP 100 [kg CO2-eq]",
         "Land use [UBP]", *headings],
        ["Steel, at plant - RER", "metals", "steel", "kg", 2.1, 99, *values(2.0)],
        ["Transport, lorry - CH", "transport systems", "road", "t*km", 0.1, 99, *values(0.11)],
        ["Wall, ZÃƒÂ¼rich - CH", "#N/A", "#N/A", "Item(s)", 5, 99, *values(5.0)],
        ["No results - GLO", "others", None, "kg", 0, 0, *[0] * 16],
    ]
    info = [[], [None, "Information"], [None, "Version", "BAFU:2026 v1"]]
    return write(tmp_path / "bafu.xlsx", {"Info": info, "BAFU_2026 v1": rows})


@pytest.fixture
def idemat_file(tmp_path):
    labels = ["Acidification", "Climate change", "Ecotoxicity", "Particulate", "Eutrophication,",
              "Eutrophication,", "Eutrophication,", "Human toxicity,",
              "Human toxicity, non-cancer", "Ionising radiation", "Land use", "Ozone depletion",
              "Photochemical ozone formation", "Resource use,", "Resource use,", "Water use"]
    second = [None, None, "freshwater", "matter", "marine", "freshwater", "terrestrial",
              "cancer", "non-cancer", None, None, None, None, "fossils", "minerals+metals", None]
    # column letters: A code+name, B group, C short code, D group, E unit, F name, G carbon
    row1 = [".", ".heading", ".", ".", None, "Process", None, None, "EF 3.1", *labels]
    row2 = [".full", ".heading", ". short", ". Simapro", "Unit", None, "carbon", None, "Total",
            *second]
    row3 = [".nr", ".heading", ". number", ". group", None, None, "kgCO2e", None, "Pt",
            *["Pt"] * 16]

    def dataset(code, name, carbon, points):
        return [f"{code} {name}", "metals", code[:12], "Ferro metals", "kg ", name, carbon, None,
                sum(points), *points]

    steel = ef31.weighted([0.01, 2.0, 5, 1e-7, 1e-3, 1e-4, 0.02, 1e-9, 1e-8, 0.1, 10, 1e-8,
                           5e-3, 20, 1e-5, 0])
    alu = ef31.weighted([0.05, 8.0, 9, 4e-7, 3e-3, 2e-4, 0.05, 3e-9, 4e-8, 0.4, 20, 2e-8,
                         2e-2, 90, 3e-5, 0])
    rows = [row1, row2, row3,
            [None, None, None, "MATERIALS"],
            dataset("B.010.01.101.240101", "Steel", 2.0, steel),
            [None, None, None, "Non-ferro"],
            dataset("B.020.01.101.240101", "Aluminium", 8.0, alu),
            dataset("B.030.01.101.240101", "Twice", 2.0, steel),
            dataset("B.030.01.101.240101", "Twice", 2.0, steel)]
    return write(tmp_path / "idemat.xlsx", {"Introduction": [["Idemat"]],
                                            "Idemat2026 midpoints": rows})


@pytest.fixture
def ecoinvent_file(tmp_path):
    """Layout assumed for the ecoinvent cumulative LCIA workbook (not verified on a real file)."""
    categories = [labels[0] for labels in PROTOCOLS["ecoinvent"].categories.values()]
    lead = [None] * 5
    rows = [
        [*lead, "EF v3.0", *["EF v3.1"] * 17, "EF v3.1 EN15804"],
        [*lead, "climate change", *categories, "climate change: fossil", "climate change"],
        [*lead, *["indicator"] * 19],
        ["Activity UUID_Product UUID", "Activity Name", "Geography", "Reference Product Name",
         "Reference Product Unit", *["unit"] * 19],
        ["a1_p1", "steel production", "RER", "steel", "kg", 7, *range(1, 17), 1.9, 7],
        ["a2_p2", "transport, lorry", "GLO", "transport", "metric ton*km", 7, *range(1, 17),
         0.1, 7],
    ]
    return write(tmp_path / "ecoinvent.xlsx", {"LCIA": rows})


# ------------------------------------------------------------------ method

def test_ef31_weights_sum_to_one_hundred():
    assert sum(c.weighting for c in ef31.CATEGORIES) == pytest.approx(100.0)
    assert len(set(ef31.CATEGORY_IDS)) == 16


def test_weighting_round_trip():
    values = [float(i + 1) for i in range(16)]
    assert ef31.from_weighted(ef31.weighted(values)) == pytest.approx(values)
    assert ef31.single_score(values) == pytest.approx(sum(ef31.weighted(values)))


def test_one_person_year_of_climate_change():
    values = [0.0] * 16
    values[CC] = 7550.0
    assert ef31.normalised(values)[CC] == pytest.approx(1.0)
    assert ef31.single_score(values) == pytest.approx(0.2106)


# -------------------------------------------------------------------- BAFU

def test_bafu_is_recognised_and_read(bafu_file):
    assert detect_file(bafu_file) == ["bafu"]
    parsed = read_file(bafu_file)
    assert parsed.kind == "process" and parsed.report.version == "BAFU:2026 v1"
    assert [i.key for i in parsed.items] == [
        "Steel, at plant - RER", "Transport, lorry - CH", "Wall, ZÃƒÂ¼rich - CH"]
    steel, lorry, wall = parsed.items
    assert steel.values[CC] == 2.0 and steel.values[WATER] == 0.5
    assert (steel.location, steel.unit, steel.category) == ("RER", "kg", "metals / steel")
    assert lorry.unit == "tkm" and wall.unit == "p"
    assert not parsed.report.derived


def test_bafu_repairs_names_and_reports_what_was_left_out(bafu_file):
    parsed = read_file(bafu_file)
    wall = parsed.items[2]
    assert wall.name == "Wall, Zürich - CH" and wall.category is None
    texts = " ".join(text for _, text in parsed.report.messages)
    assert "1 dataset(s) without any EF 3.1 result were left out" in texts
    assert "1 dataset(s) have no category" in texts
    assert "repaired in 1 name" in texts


def test_repair_text_leaves_good_text_alone():
    assert repair_text("Zürich") == "Zürich"
    assert repair_text("ZÃ¼rich") == "Zürich"
    assert repair_text("Ã…") == "Å"


# ------------------------------------------------------------------ IdeMat

def test_idemat_points_are_calculated_back(idemat_file):
    assert detect_file(idemat_file) == ["idemat"]
    parsed = read_file(idemat_file)
    steel, alu = parsed.items
    assert (steel.key, steel.name, steel.unit) == ("B.010.01.101.240101", "Steel", "kg")
    assert steel.relink_key == "B.010.01.101"
    assert steel.values[CC] == pytest.approx(2.0) and alu.values[CC] == pytest.approx(8.0)
    assert parsed.report.derived


def test_idemat_checks_and_coverage(idemat_file):
    report = read_file(idemat_file).report
    texts = " ".join(text for _, text in report.messages)
    assert "Single score check passed" in texts
    assert "Climate change matches the file's own reference column" in texts
    assert "1 dataset key(s) occur more than once and were left out" in texts
    assert report.missing_categories == ["Water use"]
    assert report.coverage["water_use"] == 0 and report.coverage["climate_change"] == 1


def test_idemat_back_calculation_mismatch_is_reported(idemat_file, tmp_path):
    workbook = openpyxl.load_workbook(idemat_file)
    workbook["Idemat2026 midpoints"]["G5"] = 3.0      # carbon footprint column, steel
    workbook.save(tmp_path / "off.xlsx")
    texts = " ".join(text for _, text in read_file(tmp_path / "off.xlsx").report.messages)
    assert "Climate change differs by more than 1%" in texts


# --------------------------------------------------------------- ecoinvent

def test_ecoinvent_layout_as_assumed(ecoinvent_file):
    assert detect_file(ecoinvent_file) == ["ecoinvent"]
    steel, lorry = read_file(ecoinvent_file).items
    assert steel.key == "a1_p1" and steel.name == "steel production | steel"
    assert steel.location == "RER" and lorry.unit == "tkm"
    # Only the 'EF v3.1' block is read, not EF v3.0 or the EN15804 variant.
    order = list(PROTOCOLS["ecoinvent"].categories)
    assert steel.values[CC] == order.index("climate_change") + 1


def test_older_method_version_is_refused_with_a_hint(ecoinvent_file, tmp_path):
    workbook = openpyxl.load_workbook(ecoinvent_file)
    for cell in workbook["LCIA"][1]:
        if cell.value == "EF v3.1":
            cell.value = "EF v3.0"
    workbook.save(tmp_path / "old.xlsx")
    assert detect_file(tmp_path / "old.xlsx") == []
    with pytest.raises(ProtocolMismatch) as error:
        read_file(tmp_path / "old.xlsx", "ecoinvent")
    assert "found instead: EF v3.0" in str(error.value)


def test_missing_category_column_is_named(bafu_file, tmp_path):
    workbook = openpyxl.load_workbook(bafu_file)
    for cell in workbook["BAFU_2026 v1"][2]:
        if cell.value == "Water use [m3 world eq]":
            cell.value = "Water [m3]"
    workbook.save(tmp_path / "changed.xlsx")
    with pytest.raises(ProtocolMismatch) as error:
        read_file(tmp_path / "changed.xlsx", "bafu")
    assert "Water use: no column" in str(error.value)


def test_headings_can_be_shown_without_data(bafu_file):
    text = describe_headings(bafu_file)
    assert "Climate change [kg CO2 eq]" in text and "Product" in text
    assert "Steel, at plant" not in text


# ------------------------------------------------------------------- flows

FLOW_SHEETS = {
    "flows": [
        ["FLOW_uuid", "FLOW_name", "FLOW_casnumber", "FLOW_class0", "FLOW_class1",
         "FLOW_class2", "FLOW_property", "FLOW_propertyUnit"],
        ["f-co2", "carbon dioxide (fossil)", None, "Emissions", "Emissions to air",
         "Emissions to air, unspecified", "Mass", "kg"],
        ["f-nh3", "ammonia", None, "Emissions", "Emissions to air",
         "Emissions to air, unspecified", "Mass", "kg"],
        ["f-none", "inert thing", None, "Emissions", "Emissions to air", None, "Mass", "kg"],
    ],
    "lciamethods": [["LCIAMethod_uuid", "LCIAMethod_name"]] + [
        [f"m-{i}", name] for i, name in enumerate([
            "Acidification", "Climate change", "Climate change-Fossil",
            "Ecotoxicity, freshwater", "EF-particulate matter", "Eutrophication marine",
            "Eutrophication, freshwater", "Eutrophication, terrestrial",
            "Human toxicity, cancer", "Human toxicity, non-cancer",
            "Ionising radiation, human health", "Land use", "Ozone depletion",
            "Photochemical ozone formation - human health", "Resource use, fossils",
            "Resource use, minerals and metals", "Water use"])],
    "lciamethods_CF": [
        ["FLOW_uuid", "FLOW_name", "LCIAMethod_uuid", "LCIAMethod_name", "LCIAMethod_CF",
         "LCIAMethod_location"],
        ["f-co2", "carbon dioxide (fossil)", "m-1", "Climate change", 1.0, None],
        ["f-co2", "carbon dioxide (fossil)", "m-2", "Climate change-Fossil", 1.0, None],
        ["f-nh3", "ammonia", "m-0", "Acidification", 3.02, None],
        ["f-nh3", "ammonia", "m-0", "Acidification", 0.021, "AL"],
    ],
}


def test_flow_list_uses_global_factors(tmp_path):
    path = write(tmp_path / "flows.xlsx", FLOW_SHEETS)
    assert detect_file(path) == ["ef31_flows"]
    parsed = read_file(path)
    assert parsed.kind == "flow"
    co2, nh3 = parsed.items                         # the flow without factors is left out
    assert co2.key == "f-co2" and co2.values[CC] == 1.0 and sum(co2.values) == 1.0
    assert nh3.values[ef31.CATEGORY_IDS.index("acidification")] == 3.02
    assert nh3.category == "Emissions to air, unspecified" and nh3.unit == "kg"
    assert any("1 country-specific factors were skipped" in t for _, t in parsed.report.messages)


def test_incomplete_flow_list_is_refused(tmp_path):
    sheets = dict(FLOW_SHEETS, lciamethods=FLOW_SHEETS["lciamethods"][:5])
    with pytest.raises(ProtocolMismatch) as error:
        read_file(write(tmp_path / "flows.xlsx", sheets))
    assert "Water use" in str(error.value)


def test_unknown_file_is_refused(tmp_path):
    path = write(tmp_path / "other.xlsx", {"Sheet1": [["a", "b"], [1, 2]]})
    assert detect_file(path) == []
    with pytest.raises(ProtocolMismatch):
        read_file(path)


# -------------------------------------------------------------------- .ods

def test_ods_files_are_read_like_xlsx(tmp_path):
    ns = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
          'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"')

    def text(value):
        return (f'<table:table-cell office:value-type="string"><text:p>{value}</text:p>'
                '</table:table-cell>')

    content = (
        f'<office:document-content {ns}><office:body><office:spreadsheet>'
        '<table:table table:name="first"><table:table-row>' + text("a") + text("b")
        + '</table:table-row></table:table>'
        '<table:table table:name="second">'
        '<table:table-row>' + text("name")
        + '<table:table-cell table:number-columns-repeated="2"/>' + text("value")
        + '</table:table-row>'
        '<table:table-row table:number-rows-repeated="2"><table:table-cell/></table:table-row>'
        '<table:table-row>' + text("x")
        + '<table:table-cell office:value-type="float" office:value="0.021">'
          '<text:p>0.02</text:p></table:table-cell>'
        + '<table:table-cell table:number-columns-repeated="16000"/></table:table-row>'
        '<table:table-row table:number-rows-repeated="1000000"><table:table-cell/>'
        '</table:table-row></table:table>'
        '</office:spreadsheet></office:body></office:document-content>')
    path = tmp_path / "book.ods"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("content.xml", content)
    assert sheet_names(path) == ["first", "second"]
    assert list(iter_rows(path, "second")) == [
        ["name", None, None, "value"], [], [], ["x", 0.021]]   # full precision, no trailing rows


# ------------------------------------------------------- library and project

@pytest.fixture
def library(bafu_file, idemat_file, tmp_path):
    lib = Library(tmp_path / "library")
    lib.add(read_file(bafu_file), "BAFU")
    lib.add(read_file(idemat_file), "IdeMat")
    lib.add(read_file(write(tmp_path / "flows.xlsx", FLOW_SHEETS)), "EF 3.1 flows")
    yield lib
    lib.close()


def hashes(library):
    return {db["name"]: db["file_hash"] for db in library.databases()}


def test_library_keeps_databases_between_sessions(library, tmp_path):
    library.close()
    reopened = Library(tmp_path / "library")
    assert [db["name"] for db in reopened.databases()] == ["BAFU", "EF 3.1 flows", "IdeMat"]
    assert reopened.databases()[0]["version"] == "BAFU:2026 v1"
    assert reopened.databases()[2]["report"]["missing_categories"] == ["Water use"]


def test_search_across_databases(library):
    assert {i["database_name"] for i in library.search("steel", kind="process")} == {
        "BAFU", "IdeMat"}
    assert [i["name"] for i in library.search("lorry transport")] == ["Transport, lorry - CH"]
    assert [i["name"] for i in library.search("", dimension="transport")] == [
        "Transport, lorry - CH"]
    assert [i["name"] for i in library.search("carbon", kind="flow")] == [
        "carbon dioxide (fossil)"]
    only_idemat = library.search("steel", databases=[hashes(library)["IdeMat"]])
    assert [i["name"] for i in only_idemat] == ["Steel"]
    assert library.search("100%") == []                 # no wildcard surprises


def test_get_returns_the_factors(library):
    item = library.get(hashes(library)["BAFU"], "Steel, at plant - RER")
    assert item["values"][CC] == 2.0 and len(item["values"]) == 16
    assert library.get(hashes(library)["BAFU"], "nothing") is None


def test_project_references_datasets_without_storing_factors(library, tmp_path):
    path = tmp_path / "p.lca4pd"
    project = Project.create(path, "P")
    database = link.register(project, library, hashes(library)["BAFU"])
    assert link.register(project, library, hashes(library)["BAFU"]) == database   # only once
    ref = link.pick(project, library, database, "Steel, at plant - RER")
    stored = project.get_dataset_ref(ref)
    assert (stored["name"], stored["unit"], stored["location"]) == (
        "Steel, at plant - RER", "kg", "RER")
    project.close()
    reopened = Project.open(path)
    columns = [row[1] for row in reopened.conn.execute("PRAGMA table_info(dataset_ref)")]
    assert not any(column.startswith("v") and column[1:].isdigit() for column in columns)
    reopened.close()


def test_database_not_on_this_computer_blocks(library, lamp):
    assert "database_not_loaded" in [i.code for i in check_project(lamp.p, library)]
    assert "database_not_loaded" not in [i.code for i in check_project(lamp.p)]


def test_replacing_a_database_relinks_what_is_used(library, idemat_file, tmp_path):
    project = Project.create(":memory:", "P")
    database = link.register(project, library, hashes(library)["IdeMat"])
    steel = link.pick(project, library, database, "B.010.01.101.240101")
    alu = link.pick(project, library, database, "B.020.01.101.240101")

    # New release: steel has a new date code, aluminium is gone.
    workbook = openpyxl.load_workbook(idemat_file)
    sheet = workbook["Idemat2026 midpoints"]
    sheet["A5"] = "B.010.01.101.260101 Steel, low alloyed"
    sheet.delete_rows(7)
    workbook.save(tmp_path / "idemat_new.xlsx")
    new_hash = library.add(read_file(tmp_path / "idemat_new.xlsx"), "IdeMat 2027")

    report = link.replace(project, library, database, new_hash)
    assert report.relinked == ["Steel"] and report.missing == ["Aluminium"]
    assert project.get_dataset_ref(steel)["dataset_key"] == "B.010.01.101.260101"
    assert project.get_dataset_ref(steel)["name"] == "Steel, low alloyed"
    assert project.get_dataset_ref(alu)["missing"] == 1
    assert project.list_databases()[0]["file_hash"] == new_hash
    project.close()
