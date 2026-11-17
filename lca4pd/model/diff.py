"""What a design alternative changes compared with the element it replaces."""

from __future__ import annotations

from collections import defaultdict

_FIELDS = (
    ("quantity", "Quantity", ""),
    ("weight", "Weight", " kg"),
    ("price", "Price", ""),
    ("internal_number", "Internal number", ""),
)


def _show(value, unit="") -> str:
    if value is None or value == "":
        return "not set"
    if isinstance(value, float):
        return f"{value:g}{unit}"
    return f"{value}{unit}"


class _Differ:
    def __init__(self, project):
        self.p = project
        self.pathways = {p["id"]: p["name"] for p in project.list_pathways()}
        self.stages = {s["id"]: s["name"] for s in project.list_stages()}
        self.parameters = {p["id"]: p["name"] for p in project.list_parameters()}
        self.lines: list[str] = []

    def add(self, where: str, text: str) -> None:
        self.lines.append(f"{where}: {text}")

    def dataset(self, entry) -> str:
        if entry["dataset_ref_id"]:
            return self.p.get_dataset_ref(entry["dataset_ref_id"])["name"]
        per_market = self.p.market_datasets(entry["id"])
        names = sorted({self.p.get_dataset_ref(ref)["name"] for ref in per_market.values()})
        return " / ".join(names)

    def entry_text(self, entry) -> str:
        label = entry["description"] or self.dataset(entry) or entry["type"].replace("_", " ")
        if entry["type"] == "exclusion" or entry["amount"] is None:
            return label
        return f"{label} ({entry['amount']:g} {entry['unit'] or ''})".replace(" )", ")")

    def node(self, base: dict, alt: dict, where: str) -> None:
        for field, label, unit in _FIELDS:
            if base[field] != alt[field]:
                self.add(where, f"{label} {_show(base[field], unit)} → {_show(alt[field], unit)}")
        if bool(base["weight_is_total"]) != bool(alt["weight_is_total"]):
            self.add(where, "weight is now "
                     + ("the total" if alt["weight_is_total"] else "on top of the sub-elements"))
        site = lambda n: ("not answered" if n["production_site"] is None else   # noqa: E731
                          "on site" if n["production_site"] == "on_site" else
                          "supplier, " + self.pathways.get(n["supplier_pathway_id"], "transport left out"))
        if site(base) != site(alt):
            self.add(where, f"Produced: {site(base)} → {site(alt)}")
        eol = lambda n: {None: "not answered", "split": "per sub-element",   # noqa: E731
                         "excluded": "left out",
                         "whole": self.pathways.get(n["eol_pathway_id"], "no pathway")}[n["eol_mode"]]
        if eol(base) != eol(alt):
            self.add(where, f"End-of-life: {eol(base)} → {eol(alt)}")
        if bool(base["has_use_inputs"]) != bool(alt["has_use_inputs"]):
            self.add(where, "use-stage inputs "
                     + ("added" if alt["has_use_inputs"] else "no longer attributed here"))
        for target, label in (("node_weight", "weight"), ("node_price", "price")):
            before = set(self.p.links_for(target, base["id"]))
            after = set(self.p.links_for(target, alt["id"]))
            if before != after:
                self.add(where, f"scenario parameters on the {label} changed")
        self.entries(base, alt, where)
        self.children(base, alt, where)

    def entries(self, base: dict, alt: dict, where: str) -> None:
        def key(entry, with_dataset=True):
            parts = [entry["type"], (entry["description"] or "").casefold()]
            if with_dataset:
                parts.append(self.dataset(entry))
            return tuple(parts)

        old, new = self.p.list_entries(base["id"]), self.p.list_entries(alt["id"])
        pairs, rest_old = [], []
        pool = defaultdict(list)
        for entry in new:
            pool[key(entry)].append(entry)
        for entry in old:
            match = pool[key(entry)]
            (pairs.append((entry, match.pop(0))) if match else rest_old.append(entry))
        rest_new = [entry for group in pool.values() for entry in group]
        # second pass: same kind and description, other dataset
        loose = defaultdict(list)
        for entry in rest_new:
            loose[key(entry, False)].append(entry)
        still_old = []
        for entry in rest_old:
            match = loose[key(entry, False)]
            (pairs.append((entry, match.pop(0))) if match and entry["description"]
             else still_old.append(entry))
        still_new = [entry for group in loose.values() for entry in group]

        for before, after in pairs:
            changes = []
            if self.dataset(before) != self.dataset(after):
                changes.append(f"dataset {self.dataset(before) or 'none'} → "
                               f"{self.dataset(after) or 'none'}")
            if (before["amount"], before["unit"]) != (after["amount"], after["unit"]):
                changes.append(f"amount {_show(before['amount'])} {before['unit'] or ''} → "
                               f"{_show(after['amount'])} {after['unit'] or ''}".replace("  ", " "))
            if before["stage_id"] != after["stage_id"]:
                changes.append(f"stage {self.stages.get(before['stage_id'], 'none')} → "
                               f"{self.stages.get(after['stage_id'], 'none')}")
            if set(self.p.links_for("entry", before["id"])) != set(
                    self.p.links_for("entry", after["id"])):
                changes.append("scenario parameters changed")
            if changes:
                label = after["description"] or self.dataset(after) or after["type"]
                self.add(where, f"{label}: " + "; ".join(changes))
        for entry in still_old:
            self.add(where, f"removed entry {self.entry_text(entry)}")
        for entry in still_new:
            self.add(where, f"added entry {self.entry_text(entry)}")

    def children(self, base: dict, alt: dict, where: str) -> None:
        old = {c["name"].casefold(): c for c in self.p.children(base["id"])}
        new = {c["name"].casefold(): c for c in self.p.children(alt["id"])}
        for name, child in old.items():
            if name in new:
                self.node(child, new[name], f"{where} › {child['name']}")
            else:
                self.add(where, f"removed element {child['name']}")
        for name, child in new.items():
            if name not in old:
                self.add(where, f"added element {child['name']}")


def diff_alternative(project, alternative_id: int) -> list[str]:
    """Plain-language list of what an alternative changes; empty if nothing."""
    alt = project.get_node(alternative_id)
    if alt["alternative_of"] is None:
        raise ValueError("Not a design alternative.")
    base = project.get_node(alt["alternative_of"])
    if alt["is_removed"]:
        return [f"{base['name']}: the element is removed"]
    differ = _Differ(project)
    if base["name"] != alt["name"]:
        differ.add(base["name"], f"renamed to {alt['name']}")
    differ.node(base, alt, alt["name"])
    return differ.lines
