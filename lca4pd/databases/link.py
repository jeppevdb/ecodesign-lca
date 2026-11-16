"""Connect a project to databases in the library.

Datasets are always picked from the library, never typed, so a reference in
the project cannot contain a mistyped name, unit or identifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model import units
from ..model.errors import NotFoundError, ValidationError
from .library import Library


def register(project, library: Library, file_hash: str) -> int:
    """Make a library database available in the project; returns the project's database id."""
    stored = library.database(file_hash)
    if stored is None:
        raise NotFoundError("This file has not been imported into the library.")
    for database in project.list_databases():
        if database["file_hash"] == file_hash:
            return database["id"]
    report = stored["report"]
    return project.add_database(
        stored["kind"], stored["name"], version=stored["version"], protocol=stored["protocol"],
        file_hash=file_hash,
        coverage={key: report[key] for key in ("derived", "missing_categories",
                                               "partial_categories")},
    )


def pick(project, library: Library, database_id: int, key: str) -> int:
    """Reference a dataset of a registered database; returns the dataset reference id."""
    database = project._row("database", database_id)
    item = library.get(database["file_hash"], key)
    if item is None:
        raise NotFoundError(f"'{key}' is not in database '{database['name']}'.")
    return project.dataset_ref(database_id, key, name=item["name"], unit=item["unit"],
                               location=item["location"], relink_key=item["relink_key"])


def unloaded_databases(project, library: Library) -> list[dict]:
    """Databases the project uses whose file is not in this library."""
    return [db for db in project.list_databases() if not library.has(db["file_hash"])]


@dataclass
class ReplaceReport:
    unchanged: int = 0
    relinked: list[str] = field(default_factory=list)       # found under a new identifier
    renamed: list[str] = field(default_factory=list)        # same identifier, new name
    unit_changed: list[str] = field(default_factory=list)   # no longer usable as entered
    missing: list[str] = field(default_factory=list)        # not in the new file


def replace(project, library: Library, database_id: int, new_file_hash: str) -> ReplaceReport:
    """Switch a project database to another file, e.g. a new release.

    Every dataset the project uses is looked up in the new file by its
    identifier, then by its version-independent code if the file has one.
    Datasets that are gone, or whose unit changed to another kind of unit,
    are marked as missing; the missing-items panel lists where they are used.
    """
    old = project._row("database", database_id)
    new = library.database(new_file_hash)
    if new is None:
        raise NotFoundError("The new file has not been imported into the library.")
    if new["kind"] != old["kind"]:
        raise ValidationError("A database can only be replaced by one of the same kind.")
    report = ReplaceReport()
    for ref in project.list_dataset_refs(database_id):
        item = library.get(new_file_hash, ref["dataset_key"])
        by_code = False
        if item is None and ref["relink_key"]:
            candidates = library.by_relink_key(new_file_hash, ref["relink_key"])
            if len(candidates) == 1:
                item, by_code = candidates[0], True
        if item is None:
            project.update_dataset_ref(ref["id"], missing=1)
            report.missing.append(ref["name"])
            continue
        if not units.compatible(item["unit"], ref["unit"]):
            project.update_dataset_ref(ref["id"], missing=1)
            report.unit_changed.append(f"{ref['name']} ({ref['unit']} -> {item['unit']})")
            continue
        if by_code:
            report.relinked.append(ref["name"])
        elif item["name"] != ref["name"]:
            report.renamed.append(f"{ref['name']} -> {item['name']}")
        else:
            report.unchanged += 1
        project.update_dataset_ref(
            ref["id"], dataset_key=item["key"], name=item["name"], unit=item["unit"],
            location=item["location"], relink_key=item["relink_key"], missing=0)
    stored = new["report"]
    project.update_database(
        database_id, version=new["version"], protocol=new["protocol"], file_hash=new_file_hash,
        coverage={key: stored[key] for key in ("derived", "missing_categories",
                                               "partial_categories")})
    return report
