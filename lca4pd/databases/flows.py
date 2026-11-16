"""Read the EF 3.1 list of elementary flows and characterisation factors.

The file is the "EF-LCIAMethod_CF" workbook of the JRC's EF 3.1 reference
package (.ods or .xlsx). It is used for direct emissions and resource uses
that are entered on their own instead of through a database dataset.

Some factors are given per country as well as globally. Every flow with
country factors also has a global one, and the global factor is the one used.
"""

from __future__ import annotations

import math
from pathlib import Path

from ..method import ef31
from ..model import units
from .reader import (ImportReport, Item, ParsedDatabase, ProtocolMismatch, as_number,
                     file_hash, norm)
from .sheets import iter_rows, sheet_names

PROTOCOL_ID = "ef31_flows"
SHEETS = ("flows", "lciamethods", "lciamethods_CF")

# Method names as written in the file -> category id
_METHOD_NAMES = {
    "acidification": "acidification",
    "climate change": "climate_change",
    "ecotoxicity, freshwater": "ecotoxicity_freshwater",
    "ef-particulate matter": "particulate_matter",
    "particulate matter": "particulate_matter",
    "eutrophication marine": "eutrophication_marine",
    "eutrophication, marine": "eutrophication_marine",
    "eutrophication, freshwater": "eutrophication_freshwater",
    "eutrophication, terrestrial": "eutrophication_terrestrial",
    "human toxicity, cancer": "human_toxicity_cancer",
    "human toxicity, non-cancer": "human_toxicity_non_cancer",
    "ionising radiation, human health": "ionising_radiation",
    "land use": "land_use",
    "ozone depletion": "ozone_depletion",
    "photochemical ozone formation - human health": "photochemical_ozone_formation",
    "photochemical ozone formation, human health": "photochemical_ozone_formation",
    "resource use, fossils": "resource_use_fossils",
    "resource use, minerals and metals": "resource_use_minerals_metals",
    "water use": "water_use",
}


def is_flow_list(path) -> bool:
    try:
        return set(SHEETS) <= set(sheet_names(path, stop_after=SHEETS))
    except Exception:
        return False


def _table(path, sheet: str, wanted: tuple[str, ...]):
    """Yield dicts for the wanted columns of a sheet whose first row is the header."""
    rows = iter_rows(path, sheet)
    header = [norm(value) for value in next(rows, [])]
    try:
        positions = {name: header.index(norm(name)) for name in wanted}
    except ValueError as error:
        raise ProtocolMismatch(f"sheet '{sheet}' has no column {error.args[0].split()[0]}") from None
    for row in rows:
        yield {name: (row[index] if index < len(row) else None)
               for name, index in positions.items()}


def read_flow_list(path, _checked: bool = False) -> ParsedDatabase:
    path = Path(path)
    if not _checked and not is_flow_list(path):
        raise ProtocolMismatch(
            "not an EF characterisation-factor workbook (expected the sheets "
            + ", ".join(SHEETS) + ")")
    report = ImportReport(protocol=PROTOCOL_ID, sheet="lciamethods_CF")

    method_category: dict[str, int] = {}
    for row in _table(path, "lciamethods", ("LCIAMethod_uuid", "LCIAMethod_name")):
        category_id = _METHOD_NAMES.get(norm(row["LCIAMethod_name"]))
        if category_id and row["LCIAMethod_uuid"]:
            method_category[str(row["LCIAMethod_uuid"])] = ef31.CATEGORY_IDS.index(category_id)
    absent = set(range(ef31.N)) - set(method_category.values())
    if absent:
        raise ProtocolMismatch("the file has no factors for: "
                               + ", ".join(ef31.CATEGORIES[i].name for i in sorted(absent)))

    factors: dict[str, list[float]] = {}
    regional = conflicts = unreadable = 0
    for row in _table(path, "lciamethods_CF", ("FLOW_uuid", "LCIAMethod_uuid",
                                               "LCIAMethod_CF", "LCIAMethod_location")):
        category = method_category.get(str(row["LCIAMethod_uuid"]))
        if category is None or not row["FLOW_uuid"]:
            continue
        if row["LCIAMethod_location"] not in (None, ""):
            regional += 1
            continue
        value = as_number(row["LCIAMethod_CF"])
        if value is None or math.isnan(value):
            unreadable += 1
            continue
        values = factors.setdefault(str(row["FLOW_uuid"]), [math.nan] * ef31.N)
        if not math.isnan(values[category]) and values[category] != value:
            conflicts += 1
            continue
        values[category] = value

    items = []
    for row in _table(path, "flows", ("FLOW_uuid", "FLOW_name", "FLOW_class1", "FLOW_class2",
                                      "FLOW_propertyUnit")):
        values = factors.get(str(row["FLOW_uuid"]))
        if values is None or not row["FLOW_name"] or not row["FLOW_propertyUnit"]:
            continue
        compartment = row["FLOW_class2"] or row["FLOW_class1"]
        items.append(Item(
            key=str(row["FLOW_uuid"]), name=" ".join(str(row["FLOW_name"]).split()),
            unit=units.canonical(str(row["FLOW_propertyUnit"])), location=None,
            category=str(compartment) if compartment else None, relink_key=None,
            values=tuple(0.0 if math.isnan(v) else v for v in values),
        ))
    if not items:
        raise ProtocolMismatch("no flow with a characterisation factor could be read")

    report.datasets = len(items)
    for index, category in enumerate(ef31.CATEGORIES):
        report.coverage[category.id] = sum(1 for i in items if i.values[index] != 0) / len(items)
    report.info(f"{len(items)} elementary flows with at least one EF 3.1 factor.")
    if regional:
        report.info(f"{regional} country-specific factors were skipped; the global factor "
                    "of each flow is used.")
    if conflicts:
        report.warn(f"{conflicts} factor(s) are given twice with different values; "
                    "the first one was kept.")
    if unreadable:
        report.warn(f"{unreadable} factor(s) are not numbers and were skipped.")
    return ParsedDatabase("flow", path.name, file_hash(path), items, report)
