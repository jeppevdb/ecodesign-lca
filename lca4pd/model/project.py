"""A project file and every operation that changes it.

Each write is checked first (the "instant checks") and raises
``ValidationError`` if the input is not acceptable. Records may be saved
incomplete – a missing dataset or amount is reported by
``checks.check_project`` instead, so users can work in any order.
"""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

from . import units
from .classifications import (
    DEFAULT_STAGES,
    EN15804_MODULES,
    ENTRY_TYPES,
    GHG_CATEGORIES,
    PARAMETER_TARGETS,
    PATHWAY_KINDS,
    PEDIGREE_FIELDS,
    PRODUCTION_TYPES,
    STAGE_ROLES,
    TOGGLES,
)
from .errors import NotFoundError, ValidationError
from .schema import DDL, SCHEMA_VERSION

SETTINGS = ("name", "functional_unit", "scope", "reference_flow", "currency")

_NODE_FIELDS = (
    "name", "quantity", "level_label", "internal_number", "description",
    "price", "weight", "weight_is_total",
    "production_site", "supplier_pathway_id", "supplier_exclusion_reason",
    "eol_mode", "eol_pathway_id", "eol_exclusion_reason",
    "eol_own_pathway_id", "eol_own_exclusion_reason",
    "has_use_inputs",
    "alt_label", "alt_short_description", "alt_long_description",
)
_CLASSIFICATION_FIELDS = ("ghg_category", "en15804_module", *PEDIGREE_FIELDS)
_ENTRY_FIELDS = (
    "stage_id", "description", "dataset_ref_id", "amount", "unit",
    "amount_note", "exclusion_reason", *_CLASSIFICATION_FIELDS,
)
_LEG_FIELDS = ("market_id", "dataset_ref_id", "amount", "unit", "note", *_CLASSIFICATION_FIELDS)
_PARAMETER_FIELDS = (
    "name", "best", "worst",
    "assumption_best", "assumption_average", "assumption_worst",
)

# Which stage roles each entry type may use (None = a user-defined stage).
_STAGE_ROLES_FOR_TYPE = {
    "production_input": ("raw_materials", "manufacturing", None),
    "production_waste": ("raw_materials", "manufacturing", None),
    "production_emission": ("raw_materials", "manufacturing", None),
    "use": ("use",),
}
_DEFAULT_STAGE_ROLE = {
    "production_waste": "manufacturing",
    "production_emission": "manufacturing",
    "use": "use",
}


def _number(value, field: str, *, minimum: float | None = None, exclusive: bool = False):
    """Return ``value`` as a finite float or raise; ``None`` passes through."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValidationError(f"'{field}' must be a number.", field)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"'{field}' must be a number.", field) from None
    if not math.isfinite(number):
        raise ValidationError(f"'{field}' must be a finite number.", field)
    if minimum is not None and (number < minimum or (exclusive and number == minimum)):
        bound = "greater than" if exclusive else "at least"
        raise ValidationError(f"'{field}' must be {bound} {minimum:g}.", field)
    return number


def _text(value, field: str, *, required: bool = False):
    text = None if value is None else str(value).strip()
    if required and not text:
        raise ValidationError(f"'{field}' is required.", field)
    return text or None


def _check_classification(record: dict) -> None:
    if record.get("ghg_category") is not None and record["ghg_category"] not in GHG_CATEGORIES:
        raise ValidationError("Unknown GHG Protocol category.", "ghg_category")
    if record.get("en15804_module") is not None and record["en15804_module"] not in EN15804_MODULES:
        raise ValidationError("Unknown EN 15804 module.", "en15804_module")
    for field in PEDIGREE_FIELDS:
        score = record.get(field)
        if score is not None and score not in (1, 2, 3, 4, 5):
            raise ValidationError("Pedigree scores must be whole numbers from 1 to 5.", field)


class Project:
    """One project file."""

    def __init__(self, connection: sqlite3.Connection, path: Path | None):
        self.conn = connection
        self.path = path

    # ------------------------------------------------------------------ file

    @staticmethod
    def _connect(path) -> sqlite3.Connection:
        # The interface may call from more than one thread of the local server.
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @classmethod
    def create(cls, path, name: str) -> "Project":
        """Create a new project file (``path=":memory:"`` for a temporary one)."""
        in_memory = str(path) == ":memory:"
        if not in_memory and Path(path).exists():
            raise ValidationError(f"File already exists: {path}")
        conn = cls._connect(path)
        with conn:
            conn.executescript(DDL)
        project = cls(conn, None if in_memory else Path(path))
        project._set_meta("schema_version", SCHEMA_VERSION)
        project._set_meta("toggles", {toggle: False for toggle in TOGGLES})
        project.set_setting("name", name)
        project.set_setting("currency", "EUR")
        for position, (stage_name, role) in enumerate(DEFAULT_STAGES):
            project._insert("stage", {"name": stage_name, "role": role, "position": position})
        return project

    @classmethod
    def open(cls, path) -> "Project":
        if not Path(path).exists():
            raise NotFoundError(f"No project file at {path}")
        project = cls(cls._connect(path), Path(path))
        version = project._get_meta("schema_version")
        if version != SCHEMA_VERSION:
            raise ValidationError(
                f"Project file has layout version {version}; this tool reads version {SCHEMA_VERSION}."
            )
        return project

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -------------------------------------------------------------- plumbing

    def _rows(self, sql: str, params=()) -> list[dict]:
        return [dict(row) for row in self.conn.execute(sql, params)]

    def _row(self, table: str, record_id, label: str | None = None) -> dict:
        row = self.conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"No {label or table} with id {record_id}.")
        return dict(row)

    def _insert(self, table: str, data: dict) -> int:
        columns = ", ".join(data)
        marks = ", ".join("?" for _ in data)
        with self.conn:
            cursor = self.conn.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(data.values())
            )
        return cursor.lastrowid

    def _update(self, table: str, record_id, data: dict) -> None:
        if not data:
            return
        assignments = ", ".join(f"{column} = ?" for column in data)
        with self.conn:
            self.conn.execute(
                f"UPDATE {table} SET {assignments} WHERE id = ?", (*data.values(), record_id)
            )

    def _delete(self, table: str, record_id) -> None:
        with self.conn:
            self.conn.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))

    def _next_position(self, table: str, column: str, value) -> int:
        if value is None:
            sql, params = f"SELECT MAX(position) FROM {table} WHERE {column} IS NULL", ()
        else:
            sql, params = f"SELECT MAX(position) FROM {table} WHERE {column} = ?", (value,)
        highest = self.conn.execute(sql, params).fetchone()[0]
        return 0 if highest is None else highest + 1

    @staticmethod
    def _only(fields: dict, allowed: tuple, what: str) -> None:
        unknown = set(fields) - set(allowed)
        if unknown:
            raise ValidationError(f"Unknown {what} field(s): {', '.join(sorted(unknown))}.")

    def _get_meta(self, key: str, default=None):
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return default if row is None else json.loads(row[0])

    def _set_meta(self, key: str, value) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    # ----------------------------------------------------------------- setup

    def get_setting(self, key: str):
        if key not in SETTINGS:
            raise ValidationError(f"Unknown setting '{key}'.")
        return self._get_meta(f"setting:{key}")

    def set_setting(self, key: str, value) -> None:
        if key not in SETTINGS:
            raise ValidationError(f"Unknown setting '{key}'.")
        self._set_meta(f"setting:{key}", _text(value, key, required=key in ("name", "currency")))

    @property
    def toggles(self) -> dict[str, bool]:
        stored = self._get_meta("toggles", {})
        return {toggle: bool(stored.get(toggle, False)) for toggle in TOGGLES}

    def set_toggle(self, toggle: str, enabled: bool) -> None:
        """Switch an optional feature. Data already entered for it is kept."""
        if toggle not in TOGGLES:
            raise ValidationError(f"Unknown option '{toggle}'.")
        self._set_meta("toggles", {**self.toggles, toggle: bool(enabled)})

    # Stages

    def list_stages(self) -> list[dict]:
        return self._rows("SELECT * FROM stage ORDER BY position")

    def stage_by_role(self, role: str) -> dict | None:
        rows = self._rows("SELECT * FROM stage WHERE role = ?", (role,))
        return rows[0] if rows else None

    def _check_stage_name(self, name: str, stage_id=None) -> str:
        name = _text(name, "name", required=True)
        clash = self._rows("SELECT id FROM stage WHERE name = ? AND id IS NOT ?", (name, stage_id))
        if clash:
            raise ValidationError(f"A life-cycle stage named '{name}' already exists.", "name")
        return name

    def add_stage(self, name: str, role: str | None = None) -> int:
        if role is not None:
            if role not in STAGE_ROLES:
                raise ValidationError(f"Unknown stage role '{role}'.", "role")
            if self.stage_by_role(role):
                raise ValidationError(f"There already is a stage for '{role}'.", "role")
        return self._insert("stage", {
            "name": self._check_stage_name(name),
            "role": role,
            "position": self._next_position("stage", "1", 1),
        })

    def rename_stage(self, stage_id: int, name: str) -> None:
        self._row("stage", stage_id)
        self._update("stage", stage_id, {"name": self._check_stage_name(name, stage_id)})

    def remove_stage(self, stage_id: int) -> None:
        self._row("stage", stage_id)
        used = self.conn.execute(
            "SELECT COUNT(*) FROM entry WHERE stage_id = ?", (stage_id,)
        ).fetchone()[0]
        if used:
            raise ValidationError(f"This stage is used by {used} entr{'y' if used == 1 else 'ies'}.")
        self._delete("stage", stage_id)

    # Markets

    def list_markets(self) -> list[dict]:
        return self._rows("SELECT * FROM market ORDER BY id")

    def _check_market_name(self, name: str, market_id=None) -> str:
        name = _text(name, "name", required=True)
        if self._rows("SELECT id FROM market WHERE name = ? AND id IS NOT ?", (name, market_id)):
            raise ValidationError(f"A market named '{name}' already exists.", "name")
        return name

    def add_market(self, name: str, description: str | None = None) -> int:
        return self._insert("market", {
            "name": self._check_market_name(name),
            "description": _text(description, "description"),
        })

    def rename_market(self, market_id: int, name: str) -> None:
        self._row("market", market_id)
        self._update("market", market_id, {"name": self._check_market_name(name, market_id)})

    def remove_market(self, market_id: int) -> None:
        """Remove a market with its distribution pathway and market-specific datasets."""
        self._row("market", market_id)
        self._delete("market", market_id)

    # ------------------------------------------------------------- databases

    def list_databases(self) -> list[dict]:
        rows = self._rows("SELECT * FROM database ORDER BY id")
        for row in rows:
            row["coverage"] = json.loads(row["coverage"])
        return rows

    def add_database(self, kind: str, name: str, *, version=None, protocol=None,
                     file_hash=None, coverage: dict | None = None) -> int:
        if kind not in ("process", "flow"):
            raise ValidationError("A database is either 'process' or 'flow'.", "kind")
        name = _text(name, "name", required=True)
        if self._rows("SELECT id FROM database WHERE name = ?", (name,)):
            raise ValidationError(f"A database named '{name}' already exists.", "name")
        return self._insert("database", {
            "kind": kind, "name": name, "version": version, "protocol": protocol,
            "file_hash": file_hash, "coverage": json.dumps(coverage or {}),
        })

    def remove_database(self, database_id: int) -> None:
        self._row("database", database_id)
        used = self._rows(
            "SELECT r.id FROM dataset_ref r WHERE r.database_id = ? AND ("
            " EXISTS (SELECT 1 FROM entry e WHERE e.dataset_ref_id = r.id)"
            " OR EXISTS (SELECT 1 FROM entry_market_dataset m WHERE m.dataset_ref_id = r.id)"
            " OR EXISTS (SELECT 1 FROM pathway_leg l WHERE l.dataset_ref_id = r.id))",
            (database_id,),
        )
        if used:
            raise ValidationError(
                f"{len(used)} dataset(s) of this database are still used in the project."
            )
        with self.conn:
            self.conn.execute("DELETE FROM dataset_ref WHERE database_id = ?", (database_id,))
            self.conn.execute("DELETE FROM database WHERE id = ?", (database_id,))

    def update_database(self, database_id: int, *, version=None, protocol=None,
                        file_hash=None, coverage: dict | None = None) -> None:
        """Point a project database at another file (see ``databases.link.replace``)."""
        self._row("database", database_id)
        self._update("database", database_id, {
            "version": version, "protocol": protocol, "file_hash": file_hash,
            "coverage": json.dumps(coverage or {}),
        })

    def list_dataset_refs(self, database_id: int) -> list[dict]:
        return self._rows("SELECT * FROM dataset_ref WHERE database_id = ? ORDER BY id",
                          (database_id,))

    def update_dataset_ref(self, ref_id: int, **fields) -> None:
        self._only(fields, ("dataset_key", "name", "unit", "location", "relink_key", "missing"),
                   "dataset reference")
        self.get_dataset_ref(ref_id)
        self._update("dataset_ref", ref_id, fields)

    def dataset_ref(self, database_id: int, dataset_key: str, *, name: str, unit: str,
                    location: str | None = None, relink_key: str | None = None) -> int:
        """Return the id of the reference to a dataset, creating it if new."""
        self._row("database", database_id)
        existing = self._rows(
            "SELECT id FROM dataset_ref WHERE database_id = ? AND dataset_key = ?",
            (database_id, dataset_key),
        )
        if existing:
            return existing[0]["id"]
        return self._insert("dataset_ref", {
            "database_id": database_id,
            "dataset_key": _text(dataset_key, "dataset_key", required=True),
            "name": _text(name, "name", required=True),
            "unit": _text(unit, "unit", required=True),
            "location": _text(location, "location"),
            "relink_key": _text(relink_key, "relink_key"),
        })

    def get_dataset_ref(self, ref_id: int) -> dict:
        row = self.conn.execute(
            "SELECT r.*, d.kind AS kind, d.name AS database_name "
            "FROM dataset_ref r JOIN database d ON d.id = r.database_id WHERE r.id = ?",
            (ref_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No dataset reference with id {ref_id}.")
        return dict(row)

    def _dataset(self, ref_id: int, kind: str, field: str = "dataset_ref_id") -> dict:
        ref = self.get_dataset_ref(ref_id)
        if ref["kind"] != kind:
            wanted = "a database dataset" if kind == "process" else "an elementary flow"
            raise ValidationError(f"This field needs {wanted}.", field)
        return ref

    # -------------------------------------------------------------- pathways

    def list_pathways(self, kind: str | None = None) -> list[dict]:
        if kind is None:
            return self._rows("SELECT * FROM pathway ORDER BY kind, name")
        return self._rows("SELECT * FROM pathway WHERE kind = ? ORDER BY name", (kind,))

    def get_pathway(self, pathway_id: int) -> dict:
        return self._row("pathway", pathway_id)

    def list_legs(self, pathway_id: int) -> list[dict]:
        return self._rows(
            "SELECT * FROM pathway_leg WHERE pathway_id = ? ORDER BY position, id", (pathway_id,)
        )

    def add_pathway(self, kind: str, name: str | None = None, *, market_id: int | None = None,
                    description: str | None = None) -> int:
        """Add a pathway. Gate-to-customer pathways belong to exactly one market."""
        if kind not in PATHWAY_KINDS:
            raise ValidationError(f"Unknown pathway kind '{kind}'.", "kind")
        if kind == "gate_to_customer":
            if market_id is None:
                raise ValidationError("Gate-to-customer distribution is defined per market.", "market_id")
            market = self._row("market", market_id)
            if self._rows("SELECT id FROM pathway WHERE kind = ? AND market_id = ?", (kind, market_id)):
                raise ValidationError(
                    f"Market '{market['name']}' already has a distribution pathway.", "market_id"
                )
            name = name or f"Distribution – {market['name']}"
        elif market_id is not None:
            raise ValidationError("Only gate-to-customer pathways belong to a market.", "market_id")
        name = _text(name, "name", required=True)
        if self._rows("SELECT id FROM pathway WHERE kind = ? AND name = ?", (kind, name)):
            raise ValidationError(f"A pathway named '{name}' already exists.", "name")
        return self._insert("pathway", {
            "kind": kind, "name": name, "market_id": market_id,
            "description": _text(description, "description"),
        })

    def update_pathway(self, pathway_id: int, *, name: str | None = None,
                       description: str | None = None) -> None:
        pathway = self._row("pathway", pathway_id)
        changes = {}
        if name is not None:
            name = _text(name, "name", required=True)
            clash = self._rows("SELECT id FROM pathway WHERE kind = ? AND name = ? AND id != ?",
                               (pathway["kind"], name, pathway_id))
            if clash:
                raise ValidationError(f"A pathway named '{name}' already exists.", "name")
            changes["name"] = name
        if description is not None:
            changes["description"] = _text(description, "description")
        self._update("pathway", pathway_id, changes)

    def pathway_users(self, pathway_id: int) -> list[dict]:
        """Elements that use a pathway."""
        return self._rows(
            "SELECT * FROM node WHERE ? IN (supplier_pathway_id, eol_pathway_id, eol_own_pathway_id)",
            (pathway_id,))

    def remove_pathway(self, pathway_id: int) -> None:
        self._row("pathway", pathway_id)
        used = self.conn.execute(
            "SELECT COUNT(*) FROM node WHERE ? IN (supplier_pathway_id, eol_pathway_id, eol_own_pathway_id)",
            (pathway_id,),
        ).fetchone()[0]
        if used:
            raise ValidationError(f"This pathway is used by {used} element(s).")
        self._delete("pathway", pathway_id)

    def _check_leg(self, leg: dict, confirm_negative: bool) -> dict:
        pathway = self._row("pathway", leg["pathway_id"])
        is_eol = pathway["kind"] == "eol"
        if leg.get("market_id") is not None:
            if not is_eol:
                raise ValidationError("Only end-of-life legs can be market-specific.", "market_id")
            self._row("market", leg["market_id"])
        leg["amount"] = _number(leg.get("amount"), "amount")
        if leg["amount"] is not None and leg["amount"] < 0 and not confirm_negative:
            raise ValidationError("Negative amount: confirm that this is intended.", "amount")
        leg["note"] = _text(leg.get("note"), "note")
        ref = None
        if leg.get("dataset_ref_id") is not None:
            ref = self._dataset(leg["dataset_ref_id"], "process")
        if is_eol:
            # The amount is a share of the weight; the dataset must be per mass.
            leg["unit"] = None
            if ref and units.dimension(ref["unit"]) != "mass":
                raise ValidationError(
                    f"End-of-life treatment must be a dataset per mass, not per '{ref['unit']}'.",
                    "dataset_ref_id",
                )
        else:
            leg["unit"] = units.canonical(leg.get("unit") or "km")
            if units.dimension(leg["unit"]) != "length":
                raise ValidationError("A transport leg needs a distance (e.g. km).", "unit")
            if leg["amount"] is not None and leg["amount"] < 0:
                raise ValidationError("A distance cannot be negative.", "amount")
            if ref and units.dimension(ref["unit"]) != "transport":
                raise ValidationError(
                    f"A transport leg needs a dataset per tonne-kilometre, not per '{ref['unit']}'.",
                    "dataset_ref_id",
                )
        _check_classification(leg)
        return leg

    def add_leg(self, pathway_id: int, *, confirm_negative: bool = False, **fields) -> int:
        self._only(fields, _LEG_FIELDS, "pathway leg")
        leg = self._check_leg({"pathway_id": pathway_id, **fields}, confirm_negative)
        leg["position"] = self._next_position("pathway_leg", "pathway_id", pathway_id)
        return self._insert("pathway_leg", leg)

    def update_leg(self, leg_id: int, *, confirm_negative: bool = False, **fields) -> None:
        self._only(fields, _LEG_FIELDS, "pathway leg")
        current = self._row("pathway_leg", leg_id, "pathway leg")
        merged = self._check_leg({**current, **fields}, confirm_negative)
        self._update("pathway_leg", leg_id, {key: merged[key] for key in (*fields, "unit")})

    def remove_leg(self, leg_id: int) -> None:
        self._row("pathway_leg", leg_id, "pathway leg")
        self._delete("pathway_leg", leg_id)

    # ------------------------------------------------------------------ tree

    def get_node(self, node_id: int) -> dict:
        return self._row("node", node_id, "element")

    def root(self) -> dict | None:
        """The product: the one base node without a parent."""
        rows = self._rows("SELECT * FROM node WHERE parent_id IS NULL AND alternative_of IS NULL")
        return rows[0] if rows else None

    def children(self, node_id: int) -> list[dict]:
        """Direct sub-elements of a node, without design alternatives."""
        return self._rows(
            "SELECT * FROM node WHERE parent_id = ? AND alternative_of IS NULL ORDER BY position, id",
            (node_id,),
        )

    def alternatives(self, base_id: int) -> list[dict]:
        return self._rows(
            "SELECT * FROM node WHERE alternative_of = ? ORDER BY position, id", (base_id,)
        )

    def ancestors(self, node_id: int) -> list[dict]:
        """Parents of a node, nearest first."""
        chain = []
        node = self.get_node(node_id)
        while node["parent_id"] is not None:
            node = self.get_node(node["parent_id"])
            chain.append(node)
        return chain

    def in_alternative(self, node_id: int) -> bool:
        """True if the node is a design alternative or sits inside one."""
        node = self.get_node(node_id)
        return node["alternative_of"] is not None or any(
            ancestor["alternative_of"] is not None for ancestor in self.ancestors(node_id)
        )

    def questions_for(self, node_id: int) -> dict[str, bool]:
        """Which creation questions apply to a node.

        The production-site question is skipped below an element that comes
        from a supplier; the end-of-life question is skipped below an element
        whose end-of-life is settled as a whole. Scope matters too: without a
        use or end-of-life stage those questions are not asked at all.
        """
        ancestors = self.ancestors(node_id)
        return {
            "production_site": not any(a["production_site"] == "supplier" for a in ancestors),
            "eol": self.stage_by_role("end_of_life") is not None
            and not any(a["eol_mode"] in ("whole", "excluded") for a in ancestors),
            "use": self.stage_by_role("use") is not None,
        }

    def _subtree_ids(self, node_id: int) -> list[int]:
        """The node and everything below it, including alternatives found there."""
        rows = self._rows(
            "WITH RECURSIVE sub(id) AS ("
            " SELECT ? UNION"
            " SELECT n.id FROM node n JOIN sub ON n.parent_id = sub.id"
            " UNION SELECT n.id FROM node n JOIN sub ON n.alternative_of = sub.id"
            ") SELECT id FROM sub",
            (node_id,),
        )
        return [row["id"] for row in rows]

    def _check_node(self, node: dict, node_id: int | None = None) -> dict:
        node["name"] = _text(node.get("name"), "name", required=True)
        node["quantity"] = _number(node.get("quantity", 1), "quantity", minimum=0, exclusive=True)
        if node["quantity"] is None:
            raise ValidationError("'quantity' is required.", "quantity")
        node["price"] = _number(node.get("price"), "price", minimum=0)
        node["weight"] = _number(node.get("weight"), "weight", minimum=0)
        for flag in ("weight_is_total", "has_use_inputs", "is_removed"):
            node[flag] = int(bool(node.get(flag)))
        for field in ("level_label", "internal_number", "description", "alt_label",
                      "alt_short_description", "alt_long_description",
                      "supplier_exclusion_reason", "eol_exclusion_reason",
                      "eol_own_exclusion_reason"):
            node[field] = _text(node.get(field), field)

        if node.get("production_site") not in (None, "on_site", "supplier"):
            raise ValidationError("Production site is 'on_site' or 'supplier'.", "production_site")
        if node.get("eol_mode") not in (None, "whole", "split", "excluded"):
            raise ValidationError("Unknown end-of-life choice.", "eol_mode")
        if node.get("eol_mode") == "excluded" and not node["eol_exclusion_reason"]:
            raise ValidationError("Give a reason for excluding end-of-life.", "eol_exclusion_reason")
        for field, kind in (("supplier_pathway_id", "supplier"), ("eol_pathway_id", "eol"),
                            ("eol_own_pathway_id", "eol")):
            if node.get(field) is not None and self._row("pathway", node[field])["kind"] != kind:
                raise ValidationError(f"'{field}' needs a pathway of kind '{kind}'.", field)

        parent_id, base_id = node.get("parent_id"), node.get("alternative_of")
        if base_id is None:
            if parent_id is None:
                root = self.root()
                if root and root["id"] != node_id:
                    raise ValidationError("The project already has a product at the top of the tree.")
            clash = self._rows(
                "SELECT id FROM node WHERE parent_id IS ? AND alternative_of IS NULL"
                " AND name = ? COLLATE NOCASE AND id IS NOT ?",
                (parent_id, node["name"], node_id),
            )
            if clash:
                raise ValidationError(
                    f"There already is an element named '{node['name']}' at this place.", "name"
                )
        else:
            if not node["alt_label"]:
                raise ValidationError("A design alternative needs a name.", "alt_label")
            clash = self._rows(
                "SELECT id FROM node WHERE alternative_of = ? AND alt_label = ? COLLATE NOCASE"
                " AND id IS NOT ?",
                (base_id, node["alt_label"], node_id),
            )
            if clash:
                raise ValidationError(
                    f"This element already has an alternative named '{node['alt_label']}'.",
                    "alt_label",
                )
        if parent_id is not None and self.get_node(parent_id)["is_removed"]:
            raise ValidationError("A removed element cannot have sub-elements.")
        return node

    def add_node(self, parent_id: int | None, name: str, **fields) -> int:
        """Add an element below ``parent_id`` (``None`` creates the product itself)."""
        self._only(fields, _NODE_FIELDS, "element")
        if parent_id is not None:
            self.get_node(parent_id)
        elif "production_site" not in fields:
            fields["production_site"] = "on_site"  # the product is made by the user
        node = self._check_node({"parent_id": parent_id, "alternative_of": None,
                                 "name": name, **fields})
        node["position"] = self._next_position("node", "parent_id", parent_id)
        return self._insert("node", node)

    def update_node(self, node_id: int, **fields) -> None:
        self._only(fields, _NODE_FIELDS, "element")
        current = self.get_node(node_id)
        merged = self._check_node({**current, **fields}, node_id)
        if "has_use_inputs" in fields and not merged["has_use_inputs"]:
            count = self.conn.execute(
                "SELECT COUNT(*) FROM entry WHERE node_id = ? AND type = 'use'", (node_id,)
            ).fetchone()[0]
            if count:
                raise ValidationError(
                    f"Remove the {count} use entr{'y' if count == 1 else 'ies'} of this element first.",
                    "has_use_inputs",
                )
        self._update("node", node_id, {key: merged[key] for key in fields})

    def delete_node(self, node_id: int) -> None:
        """Delete an element with everything below it and all its alternatives."""
        self.get_node(node_id)
        self._delete("node", node_id)

    def move_node(self, node_id: int, new_parent_id: int) -> None:
        node = self.get_node(node_id)
        if node["alternative_of"] is not None:
            raise ValidationError("A design alternative stays with the element it replaces.")
        if node["parent_id"] is None:
            raise ValidationError("The product itself cannot be moved.")
        subtree = self._subtree_ids(node_id)
        if new_parent_id in subtree:
            raise ValidationError("An element cannot be moved into itself.")
        if self.in_alternative(new_parent_id):
            has_alternatives = self.conn.execute(
                f"SELECT COUNT(*) FROM node WHERE alternative_of IS NOT NULL"
                f" AND id IN ({','.join('?' * len(subtree))})", subtree,
            ).fetchone()[0]
            if has_alternatives:
                raise ValidationError(
                    "This element has design alternatives and cannot be moved into an alternative."
                )
        self._check_node({**node, "parent_id": new_parent_id}, node_id)
        with self.conn:
            self.conn.execute(
                "UPDATE node SET parent_id = ?, position = ? WHERE id = ?",
                (new_parent_id, self._next_position("node", "parent_id", new_parent_id), node_id),
            )
            # Alternatives share the parent of the element they replace.
            self.conn.execute(
                "UPDATE node SET parent_id = ? WHERE alternative_of = ?", (new_parent_id, node_id)
            )

    def _copy_subtree(self, source_id: int, parent_id: int | None, overrides: dict) -> int:
        """Copy a node with its entries, parameter links and plain sub-elements."""
        source = self.get_node(source_id)
        data = {key: value for key, value in source.items() if key != "id"}
        data.update(parent_id=parent_id, **overrides)
        new_id = self._insert("node", data)
        self._copy_links(("node_weight", "node_price"), source_id, new_id)
        for entry in self.list_entries(source_id):
            new_entry = self._insert(
                "entry", {k: v for k, v in entry.items() if k != "id"} | {"node_id": new_id}
            )
            with self.conn:
                self.conn.execute(
                    "INSERT INTO entry_market_dataset (entry_id, market_id, dataset_ref_id)"
                    " SELECT ?, market_id, dataset_ref_id FROM entry_market_dataset WHERE entry_id = ?",
                    (new_entry, entry["id"]),
                )
            self._copy_links(("entry",), entry["id"], new_entry)
        for child in self.children(source_id):
            self._copy_subtree(child["id"], new_id, {})
        return new_id

    def _copy_links(self, target_types: tuple, source_id: int, new_id: int) -> None:
        marks = ",".join("?" * len(target_types))
        with self.conn:
            self.conn.execute(
                f"INSERT INTO parameter_link (parameter_id, target_type, target_id)"
                f" SELECT parameter_id, target_type, ? FROM parameter_link"
                f" WHERE target_id = ? AND target_type IN ({marks})",
                (new_id, source_id, *target_types),
            )

    def duplicate_node(self, node_id: int, parent_id: int | None = None) -> int:
        """Copy an element and everything below it (its alternatives are not copied).

        The copy is independent: later changes to the original do not reach it.
        """
        node = self.get_node(node_id)
        if node["alternative_of"] is not None:
            raise ValidationError("Copy the base element, not one of its alternatives.")
        target = node["parent_id"] if parent_id is None else parent_id
        if target is None:
            raise ValidationError("The product itself cannot be copied.")
        if target in self._subtree_ids(node_id):
            raise ValidationError("An element cannot be copied into itself.")
        self.get_node(target)
        taken = {row["name"].lower() for row in self.children(target)}
        name, counter = node["name"], 1
        while name.lower() in taken:
            name = f"{node['name']} (copy{'' if counter == 1 else f' {counter}'})"
            counter += 1
        return self._copy_subtree(node_id, target, {
            "name": name, "position": self._next_position("node", "parent_id", target),
        })

    def create_alternative(self, base_id: int, label: str, *, copy: bool = True,
                           removed: bool = False, short_description: str | None = None,
                           long_description: str | None = None) -> int:
        """Add a design alternative for ``base_id``.

        ``copy=True`` starts from a copy of the base, ``copy=False`` from an
        empty element, ``removed=True`` models a redesign that drops the element.
        """
        base = self.get_node(base_id)
        if self.in_alternative(base_id):
            raise ValidationError("Alternatives inside alternatives are not supported.")
        overrides = {
            "alternative_of": base_id,
            "alt_label": label,
            "alt_short_description": short_description,
            "alt_long_description": long_description,
            "is_removed": int(removed),
            "position": self._next_position("node", "alternative_of", base_id),
        }
        if copy and not removed:
            candidate = {**base, **overrides}
            candidate.pop("id")
            checked = self._check_node(candidate)
            return self._copy_subtree(
                base_id, base["parent_id"], {key: checked[key] for key in overrides}
            )
        blank = self._check_node({
            "parent_id": base["parent_id"], "name": base["name"], "quantity": base["quantity"],
            "level_label": base["level_label"], "internal_number": None, **overrides,
        })
        return self._insert("node", blank)

    # --------------------------------------------------------------- entries

    def list_entries(self, node_id: int) -> list[dict]:
        return self._rows(
            "SELECT * FROM entry WHERE node_id = ? ORDER BY position, id", (node_id,)
        )

    def get_entry(self, entry_id: int) -> dict:
        return self._row("entry", entry_id)

    def market_datasets(self, entry_id: int) -> dict[int, int]:
        """For a use entry: market id -> dataset reference id."""
        rows = self._rows(
            "SELECT market_id, dataset_ref_id FROM entry_market_dataset WHERE entry_id = ?",
            (entry_id,),
        )
        return {row["market_id"]: row["dataset_ref_id"] for row in rows}

    def _check_entry(self, entry: dict, confirm_negative: bool) -> dict:
        entry_type = entry.get("type")
        if entry_type not in ENTRY_TYPES:
            raise ValidationError(f"Unknown entry type '{entry_type}'.", "type")
        node = self.get_node(entry["node_id"])
        if node["is_removed"]:
            raise ValidationError("A removed element cannot have entries.")
        if entry_type == "use" and not node["has_use_inputs"]:
            raise ValidationError(
                "This element is not marked as having use-stage inputs of its own.", "type"
            )

        for field in ("description", "amount_note", "exclusion_reason"):
            entry[field] = _text(entry.get(field), field)
        entry["amount"] = _number(entry.get("amount"), "amount")
        if entry["amount"] is not None and entry["amount"] < 0 and not confirm_negative:
            raise ValidationError("Negative amount: confirm that this is intended.", "amount")
        _check_classification(entry)

        # Life-cycle stage
        allowed_roles = _STAGE_ROLES_FOR_TYPE.get(entry_type)
        if entry.get("stage_id") is None and entry_type in _DEFAULT_STAGE_ROLE:
            default = self.stage_by_role(_DEFAULT_STAGE_ROLE[entry_type])
            entry["stage_id"] = default["id"] if default else None
        if entry_type == "production_input" and entry.get("stage_id") is None:
            raise ValidationError("Choose 'Raw materials' or 'Manufacturing'.", "stage_id")
        if entry_type == "use" and entry.get("stage_id") is None:
            raise ValidationError("The project has no use stage.", "stage_id")
        if entry.get("stage_id") is not None:
            stage = self._row("stage", entry["stage_id"])
            if allowed_roles is not None and stage["role"] not in allowed_roles:
                raise ValidationError(
                    f"Stage '{stage['name']}' cannot be used for this type of entry.", "stage_id"
                )

        # Dataset and unit
        ref_id = entry.get("dataset_ref_id")
        if entry_type in ("cost", "exclusion"):
            if ref_id is not None:
                raise ValidationError("This type of entry has no dataset.", "dataset_ref_id")
            entry["unit"] = None
            if entry_type == "exclusion":
                if not entry["description"]:
                    raise ValidationError("Describe what is excluded.", "description")
                if not entry["exclusion_reason"]:
                    raise ValidationError("Give a reason for the exclusion.", "exclusion_reason")
                entry["amount"] = None
            return entry

        ref = None
        if ref_id is not None:
            if entry_type == "use":
                ref = self._dataset(ref_id, "flow")  # per-market datasets are set separately
            else:
                ref = self._dataset(ref_id, "flow" if entry_type == "production_emission" else "process")
        if entry.get("unit"):
            entry["unit"] = units.canonical(entry["unit"])
        elif ref:
            entry["unit"] = units.canonical(ref["unit"])
        else:
            entry["unit"] = None
        if ref and not units.compatible(entry["unit"], ref["unit"]):
            raise ValidationError(
                f"Unit '{entry['unit']}' does not fit the dataset, which is per '{ref['unit']}'.",
                "unit",
            )
        return entry

    def add_entry(self, node_id: int, entry_type: str, *, confirm_negative: bool = False,
                  **fields) -> int:
        self._only(fields, _ENTRY_FIELDS, "entry")
        entry = self._check_entry({"node_id": node_id, "type": entry_type, **fields},
                                  confirm_negative)
        entry["position"] = self._next_position("entry", "node_id", node_id)
        return self._insert("entry", entry)

    def update_entry(self, entry_id: int, *, confirm_negative: bool = False, **fields) -> None:
        self._only(fields, _ENTRY_FIELDS, "entry")
        current = self.get_entry(entry_id)
        if "dataset_ref_id" in fields and "unit" not in fields:
            current["unit"] = None  # a new dataset brings its own unit
        negative_before = current["amount"] is not None and current["amount"] < 0
        merged = self._check_entry({**current, **fields},
                                   confirm_negative or (negative_before and "amount" not in fields))
        for market_id, ref_id in self.market_datasets(entry_id).items():
            if merged["dataset_ref_id"] is not None:
                raise ValidationError(
                    "A use entry is either a direct emission or has datasets per market.",
                    "dataset_ref_id",
                )
            ref = self.get_dataset_ref(ref_id)
            if merged["unit"] and not units.compatible(merged["unit"], ref["unit"]):
                raise ValidationError(
                    f"Unit '{merged['unit']}' does not fit the dataset chosen for a market "
                    f"(per '{ref['unit']}').", "unit",
                )
        changed = {key: merged[key] for key in (*fields, "unit", "stage_id", "amount")}
        self._update("entry", entry_id, changed)

    def delete_entry(self, entry_id: int) -> None:
        self.get_entry(entry_id)
        self._delete("entry", entry_id)

    def set_market_dataset(self, entry_id: int, market_id: int, ref_id: int | None) -> None:
        """Choose (or clear, with ``None``) the dataset a use entry takes in one market."""
        entry = self.get_entry(entry_id)
        if entry["type"] != "use":
            raise ValidationError("Only use entries have datasets per market.")
        self._row("market", market_id)
        if ref_id is None:
            with self.conn:
                self.conn.execute(
                    "DELETE FROM entry_market_dataset WHERE entry_id = ? AND market_id = ?",
                    (entry_id, market_id),
                )
            return
        if entry["dataset_ref_id"] is not None:
            raise ValidationError(
                "This use entry is a direct emission; it has no datasets per market."
            )
        ref = self._dataset(ref_id, "process")
        if entry["unit"] is None:
            self._update("entry", entry_id, {"unit": units.canonical(ref["unit"])})
        elif not units.compatible(entry["unit"], ref["unit"]):
            raise ValidationError(
                f"The entry is in '{entry['unit']}', but this dataset is per '{ref['unit']}'.",
                "dataset_ref_id",
            )
        with self.conn:
            self.conn.execute(
                "INSERT INTO entry_market_dataset (entry_id, market_id, dataset_ref_id)"
                " VALUES (?, ?, ?) ON CONFLICT(entry_id, market_id)"
                " DO UPDATE SET dataset_ref_id = excluded.dataset_ref_id",
                (entry_id, market_id, ref_id),
            )

    # ------------------------------------------------------------- scenarios

    def list_scenarios(self) -> list[dict]:
        return self._rows("SELECT * FROM scenario ORDER BY id")

    def add_scenario(self, name: str, description: str | None = None) -> int:
        name = _text(name, "name", required=True)
        if self._rows("SELECT id FROM scenario WHERE name = ?", (name,)):
            raise ValidationError(f"A scenario named '{name}' already exists.", "name")
        return self._insert("scenario", {"name": name,
                                         "description": _text(description, "description")})

    def remove_scenario(self, scenario_id: int) -> None:
        self._row("scenario", scenario_id)
        self._delete("scenario", scenario_id)

    def list_parameters(self, scenario_id: int | None = None) -> list[dict]:
        if scenario_id is None:
            return self._rows("SELECT * FROM parameter ORDER BY scenario_id, id")
        return self._rows("SELECT * FROM parameter WHERE scenario_id = ? ORDER BY id",
                          (scenario_id,))

    def _check_parameter(self, parameter: dict, parameter_id=None) -> dict:
        parameter["name"] = _text(parameter.get("name"), "name", required=True)
        for case in ("best", "worst"):
            parameter[case] = _number(parameter.get(case), case, minimum=0)
        for field in ("assumption_best", "assumption_average", "assumption_worst"):
            parameter[field] = _text(parameter.get(field), field)
        clash = self._rows(
            "SELECT id FROM parameter WHERE scenario_id = ? AND name = ? AND id IS NOT ?",
            (parameter["scenario_id"], parameter["name"], parameter_id),
        )
        if clash:
            raise ValidationError(
                f"This scenario already has a parameter named '{parameter['name']}'.", "name"
            )
        return parameter

    def add_parameter(self, scenario_id: int, name: str, **fields) -> int:
        """Add a parameter. ``best`` and ``worst`` multiply the average-case value."""
        self._only(fields, _PARAMETER_FIELDS, "parameter")
        self._row("scenario", scenario_id)
        return self._insert("parameter", self._check_parameter(
            {"scenario_id": scenario_id, "name": name, **fields}))

    def update_parameter(self, parameter_id: int, **fields) -> None:
        self._only(fields, _PARAMETER_FIELDS, "parameter")
        current = self._row("parameter", parameter_id)
        merged = self._check_parameter({**current, **fields}, parameter_id)
        self._update("parameter", parameter_id, {key: merged[key] for key in fields})

    def remove_parameter(self, parameter_id: int) -> None:
        self._row("parameter", parameter_id)
        self._delete("parameter", parameter_id)

    def link_parameter(self, parameter_id: int, target_type: str, target_id: int) -> None:
        """Let a parameter act on an entry amount, pathway leg, node weight or node price."""
        self._row("parameter", parameter_id)
        if target_type not in PARAMETER_TARGETS:
            raise ValidationError(f"A parameter cannot act on '{target_type}'.", "target_type")
        if target_type == "entry":
            if self.get_entry(target_id)["type"] == "exclusion":
                raise ValidationError("A documented exclusion has no amount to vary.")
        elif target_type == "pathway_leg":
            self._row("pathway_leg", target_id, "pathway leg")
        else:
            self.get_node(target_id)
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO parameter_link (parameter_id, target_type, target_id)"
                " VALUES (?, ?, ?)", (parameter_id, target_type, target_id),
            )

    def unlink_parameter(self, parameter_id: int, target_type: str, target_id: int) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM parameter_link WHERE parameter_id = ? AND target_type = ?"
                " AND target_id = ?", (parameter_id, target_type, target_id),
            )

    def parameter_links(self, parameter_id: int | None = None) -> list[dict]:
        if parameter_id is None:
            return self._rows("SELECT * FROM parameter_link ORDER BY id")
        return self._rows("SELECT * FROM parameter_link WHERE parameter_id = ? ORDER BY id",
                          (parameter_id,))

    # --------------------------------------------------------------- designs

    def list_designs(self) -> list[dict]:
        """Every design to calculate: the base, then one per alternative.

        A design is a set of substitutions {base node id: alternative node id}.
        Stored combinations (for a later version) are appended at the end.
        """
        designs = [{"name": "Base design", "substitutions": {}}]
        for alt in self._rows(
            "SELECT * FROM node WHERE alternative_of IS NOT NULL ORDER BY alternative_of, position, id"
        ):
            designs.append({"name": alt["alt_label"],
                            "substitutions": {alt["alternative_of"]: alt["id"]}})
        for design in self._rows("SELECT * FROM design ORDER BY id"):
            pairs = self._rows(
                "SELECT base_node_id, alternative_node_id FROM design_substitution"
                " WHERE design_id = ?", (design["id"],),
            )
            designs.append({
                "name": design["name"],
                "substitutions": {p["base_node_id"]: p["alternative_node_id"] for p in pairs},
            })
        return designs
