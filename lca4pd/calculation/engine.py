"""Turn a project into results.

For every design, scenario setting and market the engine builds the full
inventory – every entry and every pathway leg, scaled to one product – and
multiplies it by the impact factors from the library.

Rules (see docs/design_2.0.md):
- Entry amounts are per one unit of their element; quantities multiply up the tree.
- Supplier transport, distribution and end-of-life are calculated from weight
  and attributed to where the weight came from: to the sub-elements whose
  weights add up to it, or to the element itself where its weight was entered.
- A scenario parameter multiplies what it is linked to; the average case is 1.
- A design alternative replaces its base element; a removed one drops it.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import pandas as pd

from ..databases.library import Library
from ..method import ef31
from ..model import units
from ..model.checks import Issue, check_project, has_blockers
from ..model.classifications import PEDIGREE_FIELDS
from .results import Results

SETTINGS = ("best", "average", "worst")
_CALCULATED_TYPES = ("production_input", "production_waste", "production_emission", "use")
_EPSILON = 1e-12


class BlockedError(RuntimeError):
    """The project still has blockers; ``issues`` lists them."""

    def __init__(self, issues: list[Issue]):
        self.issues = [issue for issue in issues if issue.severity == "blocker"]
        super().__init__(
            f"{len(self.issues)} open item(s) prevent the calculation, e.g.: "
            + self.issues[0].message)


@dataclass(frozen=True)
class Run:
    """One combination to calculate."""
    design: str
    substitutions: tuple                # ((base node id, alternative node id), …)
    setting: str                        # best / average / worst
    market_id: int
    market: str
    varied_scenario_id: int | None = None   # one-at-a-time: only this scenario leaves average
    varied_scenario: str | None = None


def fingerprint(project) -> str:
    """Identifies the exact state of a project, including the databases it points to."""
    digest = hashlib.sha256()
    for line in project.conn.iterdump():
        digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def calculate(project, library: Library) -> Results:
    """Calculate every design, scenario setting and market of a project.

    Raises ``BlockedError`` if the missing-items check still reports blockers.
    """
    issues = check_project(project, library)
    if has_blockers(issues):
        raise BlockedError(issues)
    model = _Model(project, library)
    inventory, costs = [], []
    for run in model.runs():
        calculation = _Calculation(model, run)
        inventory.extend(calculation.rows())
        if model.toggles["cost"]:
            costs.extend(calculation.costs())
    columns = _RUN_COLUMNS + _ROW_COLUMNS + list(ef31.CATEGORY_IDS)
    frame = pd.DataFrame(inventory, columns=columns)
    frame["single_score"] = sum(
        frame[c.id] / c.normalisation * c.weighting / 100 for c in ef31.CATEGORIES)
    return Results(
        inventory=frame,
        costs=pd.DataFrame(costs, columns=_RUN_COLUMNS + ["node_id", "unit_price", "multiplier", "cost"]),
        nodes=model.node_table(),
        exclusions=model.exclusion_table(),
        meta={"fingerprint": fingerprint(project), "project": project.get_setting("name"),
              "currency": project.get_setting("currency")},
    )


_RUN_COLUMNS = ["design", "setting", "market", "varied_scenario"]
_ROW_COLUMNS = [
    "node_id", "path_ids", "path", "source", "source_id", "entry_type", "stage", "stage_role",
    "description", "database", "dataset_key", "dataset", "location", "amount", "unit",
    "ghg_category", "en15804_module", *PEDIGREE_FIELDS, "uncertainty_score",
]


class _Model:
    """Everything the calculation needs, read from the project once."""

    def __init__(self, project, library: Library):
        self.project = project
        self.toggles = project.toggles
        rows = project._rows
        self.nodes = {n["id"]: n for n in rows("SELECT * FROM node ORDER BY position, id")}
        self.plain_children: dict[int, list[int]] = {}
        self.root_id = None
        for node in self.nodes.values():
            if node["alternative_of"] is not None:
                continue
            if node["parent_id"] is None:
                self.root_id = node["id"]
            else:
                self.plain_children.setdefault(node["parent_id"], []).append(node["id"])
        self.entries: dict[int, list[dict]] = {}
        for entry in rows("SELECT * FROM entry ORDER BY position, id"):
            self.entries.setdefault(entry["node_id"], []).append(entry)
        self.market_refs: dict[int, dict[int, int]] = {}
        for row in rows("SELECT * FROM entry_market_dataset"):
            self.market_refs.setdefault(row["entry_id"], {})[row["market_id"]] = row["dataset_ref_id"]
        self.pathways = {p["id"]: p for p in rows("SELECT * FROM pathway")}
        self.legs: dict[int, list[dict]] = {}
        for leg in rows("SELECT * FROM pathway_leg ORDER BY position, id"):
            self.legs.setdefault(leg["pathway_id"], []).append(leg)
        self.gate = {p["market_id"]: p["id"] for p in self.pathways.values()
                     if p["kind"] == "gate_to_customer"}
        self.markets = project.list_markets()
        self.stages = {s["id"]: s for s in project.list_stages()}
        self.stage_of_role = {s["role"]: s for s in self.stages.values() if s["role"]}
        self.scenarios = project.list_scenarios()
        self.parameters = {p["id"]: p for p in project.list_parameters()}
        self.links: dict[tuple[str, int], list[int]] = {}
        for link in project.parameter_links():
            self.links.setdefault((link["target_type"], link["target_id"]), []).append(
                link["parameter_id"])

        databases = {d["id"]: d for d in project.list_databases()}
        self.refs = {}
        for ref in rows("SELECT * FROM dataset_ref"):
            database = databases[ref["database_id"]]
            self.refs[ref["id"]] = {**ref, "database": database["name"],
                                    "file_hash": database["file_hash"]}
        self.library = library
        self._factors: dict[int, tuple] = {}

    def factors(self, ref_id: int) -> tuple[str, tuple]:
        """Unit and characterised results per unit of a referenced dataset."""
        if ref_id not in self._factors:
            ref = self.refs[ref_id]
            item = self.library.get(ref["file_hash"], ref["dataset_key"])
            if item is None:
                raise LookupError(f"'{ref['name']}' is not in database '{ref['database']}'.")
            self._factors[ref_id] = (item["unit"], item["values"])
        return self._factors[ref_id]

    def runs(self):
        designs = self.project.list_designs() if self.toggles["alternatives"] else [
            {"name": "Base design", "substitutions": {}}]
        settings = SETTINGS if self.toggles["scenarios"] else ("average",)
        for design in designs:
            substitutions = tuple(sorted(design["substitutions"].items()))
            for market in self.markets:
                for setting in settings:
                    yield Run(design["name"], substitutions, setting, market["id"], market["name"])
        if self.toggles["scenarios"]:
            # One scenario at a time on the base design, the others staying average.
            used = {self.parameters[p]["scenario_id"] for ids in self.links.values() for p in ids}
            for scenario in self.scenarios:
                if scenario["id"] not in used:
                    continue
                for market in self.markets:
                    for setting in ("best", "worst"):
                        yield Run("Base design", (), setting, market["id"], market["name"],
                                  scenario["id"], scenario["name"])

    def node_table(self) -> pd.DataFrame:
        records = []
        for node in self.nodes.values():
            depth, parent = 0, node["parent_id"]
            while parent is not None:
                depth, parent = depth + 1, self.nodes[parent]["parent_id"]
            records.append({
                "node_id": node["id"], "parent_id": node["parent_id"],
                "alternative_of": node["alternative_of"], "name": node["name"],
                "alternative": node["alt_label"], "depth": depth,
                "level_label": node["level_label"], "internal_number": node["internal_number"],
                "quantity": node["quantity"], "has_children": node["id"] in self.plain_children,
                "is_removed": bool(node["is_removed"]),
                "alt_short_description": node["alt_short_description"],
                "alt_long_description": node["alt_long_description"],
            })
        return pd.DataFrame(records)

    def exclusion_table(self) -> pd.DataFrame:
        """Everything deliberately left out of the calculation, with the reason given."""
        records = []
        for node in self.nodes.values():
            for entry in self.entries.get(node["id"], []):
                if entry["type"] == "exclusion":
                    records.append({"node_id": node["id"], "element": node["name"],
                                    "what": entry["description"],
                                    "reason": entry["exclusion_reason"]})
            for what, field in (("Transport from supplier", "supplier_exclusion_reason"),
                                ("End-of-life", "eol_exclusion_reason"),
                                ("End-of-life of own weight", "eol_own_exclusion_reason")):
                if node[field] and (field != "eol_exclusion_reason" or node["eol_mode"] == "excluded"):
                    records.append({"node_id": node["id"], "element": node["name"],
                                    "what": what, "reason": node[field]})
        return pd.DataFrame(records, columns=["node_id", "element", "what", "reason"])


class _Calculation:
    """One run: a design in a market under a scenario setting."""

    def __init__(self, model: _Model, run: Run):
        self.m = model
        self.run = run
        self.substitutions = dict(run.substitutions)
        self._weights: dict[int, float] = {}
        self._shares: dict[int, list] = {}
        self.paths: dict[int, tuple[str, str]] = {}
        self.multiplier: dict[int, float] = {}
        root = self.substitutions.get(model.root_id, model.root_id)
        self.root_id = None if model.nodes[root]["is_removed"] else root
        self.run_values = {"design": run.design, "setting": run.setting, "market": run.market,
                           "varied_scenario": run.varied_scenario}

    # ------------------------------------------------------------ structure

    def children(self, node_id: int) -> list[int]:
        """Sub-elements in this design: alternatives take the place of their base."""
        result = []
        for child in self.m.plain_children.get(node_id, []):
            child = self.substitutions.get(child, child)
            if not self.m.nodes[child]["is_removed"]:
                result.append(child)
        return result

    def factor(self, target_type: str, target_id: int) -> float:
        """Combined multiplier of the parameters linked to a target in this run."""
        if self.run.setting == "average":
            return 1.0
        result = 1.0
        for parameter_id in self.m.links.get((target_type, target_id), ()):
            parameter = self.m.parameters[parameter_id]
            if self.run.varied_scenario_id in (None, parameter["scenario_id"]):
                result *= parameter[self.run.setting]
        return result

    # --------------------------------------------------------------- weight

    def entered_weight(self, node_id: int) -> float:
        weight = self.m.nodes[node_id]["weight"]
        return 0.0 if weight is None else weight * self.factor("node_weight", node_id)

    def total_weight(self, node_id: int) -> float:
        """Weight of one unit of an element in kg."""
        if node_id not in self._weights:
            node = self.m.nodes[node_id]
            children = self.children(node_id)
            total = self.entered_weight(node_id)
            if not node["weight_is_total"]:
                total += sum(self.m.nodes[c]["quantity"] * self.total_weight(c) for c in children)
            self._weights[node_id] = total
        return self._weights[node_id]

    def own_weight(self, node_id: int) -> float:
        """Weight that belongs to the element itself and to none of its sub-elements."""
        node = self.m.nodes[node_id]
        if not node["weight_is_total"]:
            return self.entered_weight(node_id)
        below = sum(self.m.nodes[c]["quantity"] * self.total_weight(c)
                    for c in self.children(node_id))
        return self.entered_weight(node_id) - below

    def weight_shares(self, node_id: int) -> list[tuple[int, float]]:
        """Who the weight of one unit of an element belongs to: (element, kg) pairs."""
        if node_id not in self._shares:
            node = self.m.nodes[node_id]
            children = self.children(node_id)
            if node["weight_is_total"] or not children:
                shares = [(node_id, self.total_weight(node_id))]
            else:
                shares = [(node_id, self.entered_weight(node_id))]
                for child in children:
                    quantity = self.m.nodes[child]["quantity"]
                    shares += [(owner, quantity * kg) for owner, kg in self.weight_shares(child)]
            self._shares[node_id] = [(owner, kg) for owner, kg in shares if abs(kg) > _EPSILON]
        return self._shares[node_id]

    # ----------------------------------------------------------------- rows

    def rows(self) -> list[dict]:
        if self.root_id is None:
            return []
        self.out: list[dict] = []
        self.place(self.root_id, 1.0, "/", "")
        self.walk(self.root_id, supplied=False, eol_settled=False)
        self.distribution()
        return self.out

    def place(self, node_id, parent_multiplier, parent_ids, parent_path) -> None:
        """Record where each element sits and how many of it go into one product."""
        node = self.m.nodes[node_id]
        self.multiplier[node_id] = parent_multiplier * node["quantity"]
        self.paths[node_id] = (f"{parent_ids}{node_id}/",
                               f"{parent_path} > {node['name']}" if parent_path else node["name"])
        for child in self.children(node_id):
            self.place(child, self.multiplier[node_id], *self.paths[node_id])

    def walk(self, node_id, supplied, eol_settled) -> None:
        node = self.m.nodes[node_id]
        multiplier = self.multiplier[node_id]
        self.entries(node_id, multiplier)

        if not supplied and node["production_site"] == "supplier":
            supplied = True
            if node["supplier_pathway_id"] is not None:
                self.transport(node["supplier_pathway_id"], node_id, multiplier,
                               "supplier_transport", self.supplier_stage())
        if "end_of_life" in self.m.stage_of_role and not eol_settled:
            mode = node["eol_mode"]
            if mode in ("whole", "excluded"):
                eol_settled = True
                if mode == "whole":
                    for owner, kg in self.weight_shares(node_id):
                        self.end_of_life(node["eol_pathway_id"], owner, kg * multiplier)
            elif mode == "split" and node["eol_own_pathway_id"] is not None:
                own = self.own_weight(node_id)
                if own > _EPSILON:
                    self.end_of_life(node["eol_own_pathway_id"], node_id, own * multiplier)
        for child in self.children(node_id):
            self.walk(child, supplied, eol_settled)

    def supplier_stage(self):
        roles = self.m.stage_of_role
        return roles.get("raw_materials") or roles.get("manufacturing")

    def add(self, node_id, source, record, stage, description, ref_id, amount, amount_unit):
        """Append one inventory row: ``amount`` of a dataset, attributed to an element."""
        ref = self.m.refs[ref_id]
        unit, values = self.m.factors(ref_id)
        amount = units.convert(amount, amount_unit, unit)
        scores = [record[f] for f in PEDIGREE_FIELDS]
        path_ids, path = self.paths[node_id]
        row = {
            **self.run_values,
            "node_id": node_id, "path_ids": path_ids, "path": path,
            "source": source, "source_id": record["id"], "entry_type": record.get("type"),
            "stage": stage["name"] if stage else None,
            "stage_role": stage["role"] if stage else None,
            "description": description, "database": ref["database"],
            "dataset_key": ref["dataset_key"], "dataset": ref["name"],
            "location": ref["location"], "amount": amount, "unit": unit,
            "ghg_category": record["ghg_category"], "en15804_module": record["en15804_module"],
            **{f: record[f] for f in PEDIGREE_FIELDS},
            "uncertainty_score": (sum(scores) / len(scores)
                                  if all(s is not None for s in scores) else math.nan),
        }
        for category_id, value in zip(ef31.CATEGORY_IDS, values):
            row[category_id] = amount * value
        self.out.append(row)

    def entries(self, node_id: int, multiplier: float) -> None:
        for entry in self.m.entries.get(node_id, []):
            if entry["type"] not in _CALCULATED_TYPES:
                continue
            if entry["type"] == "use" and "use" not in self.m.stage_of_role:
                continue
            ref_id = entry["dataset_ref_id"]
            if ref_id is None:
                ref_id = self.m.market_refs[entry["id"]][self.run.market_id]
            amount = entry["amount"] * self.factor("entry", entry["id"]) * multiplier
            self.add(node_id, "entry", entry, self.m.stages.get(entry["stage_id"]),
                     entry["description"], ref_id, amount, entry["unit"])

    def transport(self, pathway_id, node_id, multiplier, source, stage) -> None:
        """Transport legs for the weight of ``node_id``, shared out to the weight's owners."""
        pathway = self.m.pathways[pathway_id]
        for leg in self.m.legs.get(pathway_id, []):
            kilometres = units.convert(leg["amount"], leg["unit"], "km") * self.factor(
                "pathway_leg", leg["id"])
            for owner, kg in self.weight_shares(node_id):
                self.add(owner, source, leg, stage, pathway["name"], leg["dataset_ref_id"],
                         kg * multiplier / 1000 * kilometres, "tkm")

    def distribution(self) -> None:
        stage = self.m.stage_of_role.get("distribution")
        pathway_id = self.m.gate.get(self.run.market_id)
        if stage is None or pathway_id is None:
            return
        self.transport(pathway_id, self.root_id, self.multiplier[self.root_id],
                       "distribution", stage)

    def end_of_life(self, pathway_id, owner_id, kilograms) -> None:
        pathway = self.m.pathways[pathway_id]
        stage = self.m.stage_of_role["end_of_life"]
        for leg in self.m.legs.get(pathway_id, []):
            if leg["market_id"] not in (None, self.run.market_id):
                continue
            share = leg["amount"] * self.factor("pathway_leg", leg["id"])
            self.add(owner_id, "end_of_life", leg, stage, pathway["name"],
                     leg["dataset_ref_id"], kilograms * share, "kg")

    # ----------------------------------------------------------------- cost

    def price(self, node_id: int) -> float | None:
        """Price of one unit of an element in this run.

        The entered price is the starting point. Changes below it – an
        alternative, a removed part, a price parameter – are carried upwards
        as differences, so the entered prices themselves stay authoritative.
        """
        node = self.m.nodes[node_id]
        if node["price"] is None:
            return None
        price = node["price"]
        for base_child in self.m.plain_children.get(node_id, []):
            base = self.m.nodes[base_child]
            actual = self.substitutions.get(base_child, base_child)
            if self.m.nodes[actual]["is_removed"]:
                new = 0.0
            else:
                unit_price = self.price(actual)
                if unit_price is None:
                    return None
                new = self.m.nodes[actual]["quantity"] * unit_price
            if base["price"] is None:
                return None
            price += new - base["quantity"] * base["price"]
        return price * self.factor("node_price", node_id)

    def costs(self) -> list[dict]:
        """Price of every element in this run; call after ``rows``."""
        records = []
        for node_id, multiplier in self.multiplier.items():
            unit_price = self.price(node_id)
            records.append({**self.run_values, "node_id": node_id, "unit_price": unit_price,
                            "multiplier": multiplier,
                            "cost": None if unit_price is None else unit_price * multiplier})
        return records
