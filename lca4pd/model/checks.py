"""Project-wide checks behind the missing-items panel.

``check_project`` returns every open item. Blockers prevent a calculation;
warnings do not. Each item names the record where it is fixed.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from . import units
from .classifications import PEDIGREE_FIELDS
from .tree import Tree

BLOCKER = "blocker"
WARNING = "warning"

# Material inputs may exceed the finished weight (offcuts, losses) but should
# not fall short of it. Outside this band the weight check warns.
MATERIAL_MASS_MIN_RATIO = 0.9
MATERIAL_MASS_MAX_RATIO = 1.5
COST_TOLERANCE = 0.005      # relative
SHARE_TOLERANCE = 1e-6
WEIGHT_EPSILON = 1e-9

_CALCULATED_TYPES = ("production_input", "production_waste", "production_emission", "use")


@dataclass(frozen=True)
class Issue:
    severity: str            # "blocker" or "warning"
    code: str                # stable identifier, used to group items in the panel
    message: str
    target_type: str | None = None   # "node", "entry", "pathway", "pathway_leg", …
    target_id: int | None = None


def has_blockers(issues: list[Issue]) -> bool:
    return any(issue.severity == BLOCKER for issue in issues)


def check_project(project) -> list[Issue]:
    """All open items of a project, blockers first."""
    issues = _Checker(project).run()
    return sorted(issues, key=lambda issue: issue.severity != BLOCKER)


class _Checker:
    def __init__(self, project):
        self.p = project
        self.issues: list[Issue] = []
        self.toggles = project.toggles
        self.tree = Tree(project)
        self.markets = project.list_markets()
        self.stage_role = {stage["id"]: stage["role"] for stage in project.list_stages()}
        self.roles = set(self.stage_role.values())
        self.refs = {row["id"]: row for row in project._rows(
            "SELECT r.*, d.kind AS kind FROM dataset_ref r JOIN database d ON d.id = r.database_id"
        )}
        self.entries: dict[int, list[dict]] = defaultdict(list)
        for entry in project._rows("SELECT * FROM entry ORDER BY position, id"):
            self.entries[entry["node_id"]].append(entry)
        self.market_refs: dict[int, dict[int, int]] = defaultdict(dict)
        for row in project._rows("SELECT * FROM entry_market_dataset"):
            self.market_refs[row["entry_id"]][row["market_id"]] = row["dataset_ref_id"]
        self.pathways = {row["id"]: row for row in project._rows("SELECT * FROM pathway")}
        self.legs: dict[int, list[dict]] = defaultdict(list)
        for leg in project._rows("SELECT * FROM pathway_leg ORDER BY position, id"):
            self.legs[leg["pathway_id"]].append(leg)
        self.parameters = {row["id"]: row for row in project.list_parameters()}
        self.links = project.parameter_links()
        self.used_pathways: set[int] = set()
        self.used_refs: set[int] = set()
        self.weight_needed: set[int] = set()

    def add(self, severity, code, message, target_type=None, target_id=None):
        self.issues.append(Issue(severity, code, message, target_type, target_id))

    def block(self, *args):
        self.add(BLOCKER, *args)

    def warn(self, *args):
        self.add(WARNING, *args)

    # ------------------------------------------------------------------ run

    def run(self) -> list[Issue]:
        self.check_setup()
        if self.tree.root_id is None:
            self.block("no_product", "Add the product at the top of the tree.")
        for node_id, node in self.tree.nodes.items():
            if node["is_removed"]:
                continue
            self.check_structure(node_id, node)
            self.check_entries(node_id, node)
            self.check_supplier(node_id, node)
            self.check_end_of_life(node_id, node)
            self.check_cost(node_id, node)
            self.check_material_mass(node_id, node)
        self.check_weights()
        self.check_internal_numbers()
        self.check_pathways()
        self.check_scenarios()
        self.check_alternatives()
        self.check_databases()
        return self.issues

    # ---------------------------------------------------------------- setup

    def check_setup(self):
        if not self.markets:
            self.block("no_market", "Add at least one market in the setup.")
        if not any(db["kind"] == "process" for db in self.p.list_databases()):
            self.block("no_database", "Upload at least one database with impact factors.")

    # ------------------------------------------------------------ structure

    def check_structure(self, node_id, node):
        label = self.tree.label(node_id)
        entries = self.entries[node_id]
        if not self.tree.children(node_id) and not any(e["type"] != "cost" for e in entries):
            self.block("node_empty", f"'{label}' has no entries and no sub-elements.",
                       "node", node_id)
        if node["weight_is_total"] and node["weight"] is None:
            self.block("weight_missing",
                       f"'{label}' is ticked 'this is the total' but has no weight.",
                       "node", node_id)
        if "use" in self.roles and node["has_use_inputs"] and not any(
                e["type"] == "use" for e in entries):
            self.warn("use_entries_missing",
                      f"'{label}' is marked as having use-stage inputs but has none yet.",
                      "node", node_id)
        if self.toggles["internal_numbers"] and not node["internal_number"]:
            self.warn("internal_number_missing", f"'{label}' has no internal number.",
                      "node", node_id)

    # -------------------------------------------------------------- entries

    def check_entries(self, node_id, node):
        label = self.tree.label(node_id)
        for entry in self.entries[node_id]:
            name = entry["description"] or entry["type"].replace("_", " ")
            where = f"'{name}' on '{label}'"
            if entry["type"] == "cost":
                if self.toggles["cost"] and entry["amount"] is None:
                    self.warn("cost_entry_incomplete", f"Cost entry {where} has no amount.",
                              "entry", entry["id"])
                continue
            if entry["type"] not in _CALCULATED_TYPES:
                continue
            if entry["type"] == "use" and "use" not in self.roles:
                continue

            market_refs = self.market_refs.get(entry["id"], {})
            if entry["dataset_ref_id"] is None and not market_refs:
                self.block("entry_incomplete", f"Entry {where} has no dataset.",
                           "entry", entry["id"])
            elif entry["type"] == "use" and entry["dataset_ref_id"] is None:
                for market in self.markets:
                    if market["id"] not in market_refs:
                        self.block(
                            "use_market_dataset_missing",
                            f"Use entry {where} has no dataset for market '{market['name']}'.",
                            "entry", entry["id"])
            if entry["amount"] is None:
                self.block("entry_incomplete", f"Entry {where} has no amount.",
                           "entry", entry["id"])
            for ref_id in (entry["dataset_ref_id"], *market_refs.values()):
                self.note_ref(ref_id, f"Entry {where}", "entry", entry["id"])
            self.check_classification(entry, f"Entry {where}", "entry")

    def note_ref(self, ref_id, where, target_type, target_id):
        if ref_id is None:
            return
        self.used_refs.add(ref_id)
        ref = self.refs[ref_id]
        if ref["missing"]:
            self.block("dataset_missing",
                       f"{where} uses '{ref['name']}', which is no longer in its database.",
                       target_type, target_id)

    def check_classification(self, record, where, target_type):
        if self.toggles["uncertainty"] and any(record[f] is None for f in PEDIGREE_FIELDS):
            self.warn("pedigree_missing", f"{where} has no complete pedigree scores.",
                      target_type, record["id"])
        if self.toggles["ghg_protocol"] and record["ghg_category"] is None:
            self.warn("ghg_category_missing", f"{where} has no GHG Protocol category.",
                      target_type, record["id"])
        if self.toggles["en15804"] and record["en15804_module"] is None:
            self.warn("en15804_module_missing", f"{where} has no EN 15804 module.",
                      target_type, record["id"])

    # ------------------------------------------------------------- supplier

    def check_supplier(self, node_id, node):
        if any(a["production_site"] == "supplier" for a in self.tree.ancestors(node_id)):
            return  # settled by an element higher up
        label = self.tree.label(node_id)
        if node["production_site"] is None:
            self.block("production_site_unanswered",
                       f"State where '{label}' is produced.", "node", node_id)
        elif node["production_site"] == "supplier":
            if node["supplier_pathway_id"] is not None:
                self.used_pathways.add(node["supplier_pathway_id"])
                self.need_weight(node_id)
            elif not node["supplier_exclusion_reason"]:
                self.block("supplier_pathway_missing",
                           f"Choose the transport pathway from the supplier of '{label}'.",
                           "node", node_id)

    # ---------------------------------------------------------- end of life

    def check_end_of_life(self, node_id, node):
        if "end_of_life" not in self.roles:
            return
        if any(a["eol_mode"] in ("whole", "excluded") for a in self.tree.ancestors(node_id)):
            return  # settled by an element higher up
        label = self.tree.label(node_id)
        mode = node["eol_mode"]
        if mode is None:
            self.block("eol_unanswered",
                       f"State whether one end-of-life pathway applies to '{label}' as a whole.",
                       "node", node_id)
        elif mode == "whole":
            if node["eol_pathway_id"] is None:
                self.block("eol_pathway_missing",
                           f"Choose the end-of-life pathway of '{label}'.", "node", node_id)
            else:
                self.used_pathways.add(node["eol_pathway_id"])
                self.need_weight(node_id)
        elif mode == "split":
            if not self.tree.children(node_id):
                self.block("eol_pathway_missing",
                           f"'{label}' has no sub-elements: choose an end-of-life pathway "
                           "or record an exclusion.", "node", node_id)
                return
            own = self.tree.own_weight(node_id)
            if own is None:
                return  # reported as a missing weight
            if own < -WEIGHT_EPSILON:
                self.warn("weight_exceeded",
                          f"The sub-elements of '{label}' weigh more than its total weight.",
                          "node", node_id)
            elif own > WEIGHT_EPSILON:
                if node["eol_own_pathway_id"] is not None:
                    self.used_pathways.add(node["eol_own_pathway_id"])
                elif not node["eol_own_exclusion_reason"]:
                    self.block("eol_own_weight_uncovered",
                               f"{own:g} kg of '{label}' belongs to none of its sub-elements: "
                               "choose an end-of-life pathway for it.", "node", node_id)

    # --------------------------------------------------------------- weight

    def need_weight(self, node_id):
        self.weight_needed.add(node_id)

    def weight_contributors(self, node_id) -> list[int]:
        """The node and the sub-elements whose weights add up to its weight."""
        found, stack = [], [node_id]
        while stack:
            current = stack.pop()
            found.append(current)
            if not self.tree.nodes[current]["weight_is_total"]:
                stack.extend(self.tree.children(current))
        return found

    def check_weights(self):
        # Distribution applies to the whole product, so the product needs a
        # complete weight.
        if "distribution" in self.roles and self.tree.root_id is not None:
            self.need_weight(self.tree.root_id)
        # An alternative takes the place of its base element, so it needs a
        # weight wherever the base element's weight is used.
        for node_id in list(self.weight_needed):
            for contributor in self.weight_contributors(node_id):
                for alt_id in self.tree.alternatives(contributor):
                    if not self.tree.nodes[alt_id]["is_removed"]:
                        self.need_weight(alt_id)
        missing: set[int] = set()
        for node_id in self.weight_needed:
            missing.update(self.tree.total_weight(node_id)[1])
        for node_id in sorted(missing):
            node = self.tree.nodes[node_id]
            if node["weight_is_total"]:
                continue  # already reported
            self.block("weight_missing",
                       f"'{self.tree.label(node_id)}' needs a weight "
                       "(used for transport and end-of-life).", "node", node_id)

    def check_material_mass(self, node_id, node):
        own = self.tree.own_weight(node_id)
        if own is None:
            return
        mass, found = 0.0, False
        for entry in self.entries[node_id]:
            if (entry["type"] == "production_input" and entry["amount"] is not None
                    and self.stage_role.get(entry["stage_id"]) == "raw_materials"
                    and entry["unit"] and units.dimension(entry["unit"]) == "mass"):
                mass += units.convert(entry["amount"], entry["unit"], "kg")
                found = True
        if not found:
            return
        label = self.tree.label(node_id)
        if own <= WEIGHT_EPSILON:
            self.warn("weight_material_mismatch",
                      f"'{label}' has {mass:g} kg of material inputs of its own but no weight "
                      "of its own, so their transport and end-of-life are not covered.",
                      "node", node_id)
        elif not MATERIAL_MASS_MIN_RATIO <= mass / own <= MATERIAL_MASS_MAX_RATIO:
            self.warn("weight_material_mismatch",
                      f"'{label}' weighs {own:g} kg but its material inputs add up to {mass:g} kg.",
                      "node", node_id)

    # ----------------------------------------------------------------- cost

    def check_cost(self, node_id, node):
        if not self.toggles["cost"]:
            return
        label = self.tree.label(node_id)
        if node["price"] is None:
            self.warn("price_missing", f"'{label}' has no price.", "node", node_id)
            return
        children = self.tree.children(node_id)
        if not children:
            return
        parts, incomplete = 0.0, False
        for child_id in children:
            child = self.tree.nodes[child_id]
            if child["price"] is None:
                incomplete = True
            else:
                parts += child["quantity"] * child["price"]
        if incomplete:
            return  # the missing prices are reported on the sub-elements
        parts += sum(e["amount"] or 0.0 for e in self.entries[node_id] if e["type"] == "cost")
        difference = node["price"] - parts
        if abs(difference) > max(COST_TOLERANCE * abs(node["price"]), 0.005):
            currency = self.p.get_setting("currency")
            self.warn("cost_mismatch",
                      f"'{label}' costs {node['price']:g} {currency}, but its sub-elements and "
                      f"cost entries add up to {parts:g} {currency} "
                      f"(difference {difference:+g}).", "node", node_id)

    def check_internal_numbers(self):
        names: dict[str, set[str]] = defaultdict(set)
        holders: dict[str, list[int]] = defaultdict(list)
        for node_id, node in self.tree.nodes.items():
            if node["internal_number"] and node["alternative_of"] is None:
                names[node["internal_number"]].add(node["name"].lower())
                holders[node["internal_number"]].append(node_id)
        for number, used_names in names.items():
            if len(used_names) > 1:
                for node_id in holders[number]:
                    self.warn("internal_number_conflict",
                              f"Internal number '{number}' is used for elements with "
                              "different names.", "node", node_id)

    # ------------------------------------------------------------- pathways

    def multiplier(self, target_type, target_id, case) -> float:
        factor = 1.0
        for link in self.links:
            if link["target_type"] == target_type and link["target_id"] == target_id:
                value = self.parameters[link["parameter_id"]][case]
                if value is not None:
                    factor *= value
        return factor

    def check_pathways(self):
        if "distribution" in self.roles:
            gates = {p["market_id"]: p for p in self.pathways.values()
                     if p["kind"] == "gate_to_customer"}
            for market in self.markets:
                if market["id"] in gates:
                    self.used_pathways.add(gates[market["id"]]["id"])
                else:
                    self.block("distribution_missing",
                               f"Define the gate-to-customer distribution for market "
                               f"'{market['name']}'.", "market", market["id"])

        for pathway_id in sorted(self.used_pathways):
            pathway = self.pathways[pathway_id]
            legs = self.legs.get(pathway_id, [])
            if not legs:
                self.block("pathway_empty", f"Pathway '{pathway['name']}' has no legs.",
                           "pathway", pathway_id)
                continue
            for leg in legs:
                where = f"A leg of pathway '{pathway['name']}'"
                if leg["dataset_ref_id"] is None or leg["amount"] is None:
                    self.block("leg_incomplete", f"{where} has no dataset or amount.",
                               "pathway_leg", leg["id"])
                self.note_ref(leg["dataset_ref_id"], where, "pathway_leg", leg["id"])
                self.check_classification(leg, where, "pathway_leg")
            if pathway["kind"] == "eol":
                self.check_eol_shares(pathway, legs)

    def check_eol_shares(self, pathway, legs):
        cases = ("average", "best", "worst") if self.toggles["scenarios"] else ("average",)
        for market in self.markets:
            applicable = [leg for leg in legs if leg["market_id"] in (None, market["id"])]
            if not applicable:
                self.block("eol_market_missing",
                           f"End-of-life pathway '{pathway['name']}' has no treatment for "
                           f"market '{market['name']}'.", "pathway", pathway["id"])
                continue
            if any(leg["amount"] is None for leg in applicable):
                continue
            for case in cases:
                total = sum(
                    leg["amount"] * (1.0 if case == "average"
                                     else self.multiplier("pathway_leg", leg["id"], case))
                    for leg in applicable)
                if abs(total - 1.0) > SHARE_TOLERANCE:
                    self.warn("eol_shares",
                              f"The shares of end-of-life pathway '{pathway['name']}' add up to "
                              f"{total:.0%} in market '{market['name']}' ({case} case), "
                              "not 100%.", "pathway", pathway["id"])

    # ------------------------------------------------------------ scenarios

    def check_scenarios(self):
        if not self.toggles["scenarios"]:
            return
        linked = {link["parameter_id"] for link in self.links}
        with_parameters = set()
        for parameter in self.parameters.values():
            with_parameters.add(parameter["scenario_id"])
            if parameter["best"] is None or parameter["worst"] is None:
                self.block("parameter_incomplete",
                           f"Parameter '{parameter['name']}' needs a best and a worst value.",
                           "parameter", parameter["id"])
            if parameter["id"] not in linked:
                self.warn("parameter_unlinked",
                          f"Parameter '{parameter['name']}' does not affect anything.",
                          "parameter", parameter["id"])
        for scenario in self.p.list_scenarios():
            if scenario["id"] not in with_parameters:
                self.warn("scenario_empty", f"Scenario '{scenario['name']}' has no parameters.",
                          "scenario", scenario["id"])

    # --------------------------------------------------------- alternatives

    def signature(self, node_id, top=True):
        """Everything that defines a subtree, for comparing an alternative with its base."""
        node = self.tree.nodes[node_id]
        skipped = {"id", "parent_id", "alternative_of", "position", "alt_label",
                   "alt_short_description", "alt_long_description"}
        fields = tuple(sorted((k, v) for k, v in node.items() if k not in skipped))
        entries = sorted(
            json.dumps(
                {k: v for k, v in entry.items() if k not in ("id", "node_id", "position")}
                | {"markets": sorted(self.market_refs.get(entry["id"], {}).items()),
                   "parameters": sorted(l["parameter_id"] for l in self.links
                                        if l["target_type"] == "entry"
                                        and l["target_id"] == entry["id"])},
                sort_keys=True)
            for entry in self.entries[node_id])
        children = tuple(self.signature(child, False) for child in self.tree.children(node_id))
        return fields, tuple(entries), children

    def check_alternatives(self):
        if not self.toggles["alternatives"]:
            return
        for node_id, node in self.tree.nodes.items():
            base_id = node["alternative_of"]
            if base_id is None or node["is_removed"]:
                continue
            if self.signature(node_id) == self.signature(base_id):
                self.warn("alternative_identical",
                          f"Alternative '{node['alt_label']}' is identical to "
                          f"'{self.tree.nodes[base_id]['name']}'.", "node", node_id)

    # ------------------------------------------------------------ databases

    def check_databases(self):
        used = {self.refs[ref_id]["database_id"] for ref_id in self.used_refs}
        for database in self.p.list_databases():
            if database["id"] not in used:
                continue
            coverage = database["coverage"]
            if coverage.get("derived"):
                self.warn("database_derived",
                          f"Values of database '{database['name']}' are calculated back from "
                          "weighted scores.", "database", database["id"])
            missing = coverage.get("missing_categories") or []
            if missing:
                self.warn("database_coverage",
                          f"Database '{database['name']}' does not cover: "
                          f"{', '.join(missing)}.", "database", database["id"])
