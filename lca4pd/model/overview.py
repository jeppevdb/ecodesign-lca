"""The full LCI overview "as entered": every entry of the project in one table.

The table is a second way to look at and edit what the guided forms hold.
Edits go through the same checks as the forms.
"""

from __future__ import annotations

import io

import pandas as pd

from .classifications import (EN15804_MODULES, ENTRY_TYPE_LABELS, GHG_CATEGORIES,
                              PEDIGREE_INDICATORS, PEDIGREE_LABELS)
from .errors import ValidationError

# Column title -> entry field, for the columns that can be edited in the table.
_ALWAYS = {"Description": "description", "Stage": "stage_id", "Amount": "amount",
           "Note": "amount_note"}
_PEDIGREE = {PEDIGREE_LABELS[i]: f"ped_{i}" for i in PEDIGREE_INDICATORS}


def editable_columns(project) -> dict[str, str]:
    """Editable column titles and the entry field each one changes."""
    toggles = project.toggles
    columns = dict(_ALWAYS)
    if toggles["ghg_protocol"]:
        columns["GHG category"] = "ghg_category"
    if toggles["en15804"]:
        columns["EN 15804 module"] = "en15804_module"
    if toggles["uncertainty"]:
        columns.update(_PEDIGREE)
    return columns


def choices(project, column: str) -> list | None:
    """Allowed values of a pick-list column (``None`` for free input)."""
    if column == "Stage":
        return [stage["name"] for stage in project.list_stages()]
    if column == "GHG category":
        return ["", *GHG_CATEGORIES]
    if column == "EN 15804 module":
        return ["", *EN15804_MODULES]
    if column in _PEDIGREE:
        return ["", 1, 2, 3, 4, 5]
    return None


def entered_table(project) -> pd.DataFrame:
    """One row per entry, in tree order. The ``id`` column is the entry id."""
    toggles = project.toggles
    stages = {s["id"]: s["name"] for s in project.list_stages()}
    scenarios = {s["id"]: s["name"] for s in project.list_scenarios()}
    parameters = {p["id"]: f"{scenarios[p['scenario_id']]} – {p['name']}"
                  for p in project.list_parameters()}
    refs: dict[int, dict] = {}

    def ref(ref_id):
        if ref_id not in refs:
            refs[ref_id] = project.get_dataset_ref(ref_id)
        return refs[ref_id]

    rows = []

    def visit(node, path, alternative):
        if node["alternative_of"] is not None:
            alternative = node["alt_label"]
        if node["is_removed"]:
            return
        here = f"{path} › {node['name']}" if path else node["name"]
        for entry in project.list_entries(node["id"]):
            per_market = project.market_datasets(entry["id"])
            if entry["dataset_ref_id"]:
                found = [ref(entry["dataset_ref_id"])]
            else:
                found = [ref(r) for r in dict.fromkeys(per_market.values())]
            row = {"id": entry["id"], "Element": here}
            if toggles["internal_numbers"]:
                row["Internal number"] = node["internal_number"] or ""
            if toggles["alternatives"]:
                row["Alternative"] = alternative or ""
            is_cost = entry["type"] == "cost"
            row.update({
                "Kind": ENTRY_TYPE_LABELS[entry["type"]],
                "Stage": stages.get(entry["stage_id"], ""),
                "Description": entry["description"] or "",
                "Dataset": " / ".join(f["name"] for f in found),
                "Database": " / ".join(dict.fromkeys(f["database_name"] for f in found)),
                "Amount": entry["amount"],
                "Unit": project.get_setting("currency") if is_cost else (entry["unit"] or ""),
                "Note": entry["amount_note"] or entry["exclusion_reason"] or "",
            })
            if toggles["scenarios"]:
                row["Parameters"] = "; ".join(parameters[p] for p in
                                              project.links_for("entry", entry["id"]))
            if toggles["ghg_protocol"]:
                row["GHG category"] = entry["ghg_category"] or ""
            if toggles["en15804"]:
                row["EN 15804 module"] = entry["en15804_module"] or ""
            if toggles["uncertainty"]:
                for title, field in _PEDIGREE.items():
                    row[title] = entry[field] if entry[field] is not None else ""
            rows.append(row)
        for child in project.children(node["id"]):
            visit(child, here, alternative)
        if toggles["alternatives"] and node["alternative_of"] is None:
            for other in project.alternatives(node["id"]):
                visit(other, path, None)

    root = project.root()
    if root is not None:
        visit(root, "", None)
    columns = list(rows[0]) if rows else ["id", "Element", "Kind", "Stage", "Description",
                                          "Dataset", "Database", "Amount", "Unit", "Note"]
    return pd.DataFrame(rows, columns=columns)


def apply_edit(project, entry_id: int, column: str, value) -> None:
    """Change one cell of the overview. Raises ``ValidationError`` if the value is refused."""
    columns = editable_columns(project)
    if column not in columns:
        raise ValidationError(f"'{column}' cannot be changed in the table.", column)
    field = columns[column]
    entry = project.get_entry(entry_id)
    if isinstance(value, str):
        value = value.strip()
    if value in ("", None) or (isinstance(value, float) and pd.isna(value)):
        value = None
    if field == "stage_id":
        if value is not None:
            match = [s["id"] for s in project.list_stages() if s["name"] == value]
            if not match:
                raise ValidationError(f"There is no life-cycle stage '{value}'.", column)
            value = match[0]
    elif field.startswith("ped_") and value is not None:
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValidationError("Pedigree scores are whole numbers from 1 to 5.", column) from None
    elif field == "amount":
        if entry["type"] == "exclusion":
            raise ValidationError("A documented exclusion has no amount.", column)
        if value is not None:
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValidationError("The amount must be a number.", column) from None
            if value < 0 and not (entry["amount"] is not None and entry["amount"] < 0):
                raise ValidationError(
                    "A negative amount has to be confirmed in the entry form.", column)
    elif field == "amount_note" and entry["type"] == "exclusion":
        field = "exclusion_reason"
    elif field in ("ghg_category", "en15804_module") and entry["type"] in ("cost", "exclusion"):
        raise ValidationError("This kind of entry has no classification.", column)
    confirm = field == "amount" and value is not None and value < 0
    project.update_entry(entry_id, confirm_negative=confirm, **{field: value})


def to_xlsx(sheets: dict[str, pd.DataFrame]) -> io.BytesIO:
    """An Excel workbook with one sheet per table, ready to download."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
    buffer.seek(0)
    return buffer
