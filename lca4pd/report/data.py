"""Everything the report shows, worked out from a results file.

Pure pandas, no charts: each function answers one question the report asks,
so it can be tested on its own. Charts and layout are in ``views.py``.

The tree can be any depth. Two ways of grouping replace the fixed
system / assembly / component levels of version 1:

- by **level**: every row is attributed to its element at that depth of the
  tree. Rows that belong to an element higher up (its own processes) stay
  with that element, labelled "… – own processes", so totals always add up.
- by **parts of an element**: the element's direct sub-elements, plus a
  slice for its own processes; for an element without sub-elements, its
  individual entries.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..calculation import Results
from ..method import ef31

SINGLE_SCORE = "single_score"
OWN = " – own processes"
BASE_DESIGN = "Base design"
UNCLASSIFIED = "Unclassified"
SETTING_ORDER = ("best", "average", "worst")
SOURCE_LABELS = {"entry": "entry", "supplier_transport": "transport from supplier",
                 "distribution": "distribution", "end_of_life": "end-of-life"}


@dataclass(frozen=True)
class Alternative:
    name: str
    base_id: int
    alternative_id: int
    removed: bool
    short_description: str | None
    long_description: str | None


class ReportData:
    def __init__(self, results: Results):
        self.results = results
        self.meta = results.meta
        self.inventory = results.inventory.copy()
        self.inventory["varied_scenario"] = self.inventory["varied_scenario"].where(
            self.inventory["varied_scenario"].notna(), None)
        self.nodes = results.nodes.set_index("node_id")
        self.toggles = self.meta.get("toggles", {})
        self.currency = self.meta.get("currency") or ""
        self._paths: dict[str, list[int]] = {}
        self.labels = self._labels()

    # ------------------------------------------------------------ choices

    @property
    def markets(self) -> list[str]:
        order = [m["name"] for m in self.meta.get("markets", [])]
        present = set(self.inventory["market"])
        return [m for m in order if m in present] or sorted(present)

    @property
    def settings(self) -> list[str]:
        present = set(self.inventory["setting"])
        return [s for s in ("average", "best", "worst") if s in present]

    @property
    def stages(self) -> list[str]:
        order = [s["name"] for s in self.meta.get("stages", [])]
        present = set(self.inventory["stage"].dropna())
        return [s for s in order if s in present] + sorted(present - set(order))

    def impact_options(self) -> dict[str, str]:
        """Selector label -> column, single score first."""
        options = {"Single score (EF 3.1)": SINGLE_SCORE}
        options.update({f"{c.name}": c.id for c in ef31.CATEGORIES})
        return options

    def unit(self, key: str) -> str:
        return ef31.SINGLE_SCORE_UNIT if key == SINGLE_SCORE else ef31.BY_ID[key].unit

    def label_of(self, key: str) -> str:
        return "Single score" if key == SINGLE_SCORE else ef31.BY_ID[key].name

    @property
    def scenarios(self) -> list[str]:
        return [s for s in self.inventory["varied_scenario"].dropna().unique()]

    @property
    def root_id(self) -> int:
        roots = self.nodes[self.nodes["parent_id"].isna() & self.nodes["alternative_of"].isna()]
        return int(roots.index[0])

    # ------------------------------------------------------------- labels

    def _labels(self) -> dict[int, str]:
        """A readable, unique name for every element."""
        nodes = self.nodes
        labels = {}
        counts = nodes[nodes["alternative_of"].isna()]["name"].str.casefold().value_counts()
        for node_id, node in nodes.iterrows():
            name = node["name"]
            if node["alternative_of"] is not None and not pd.isna(node["alternative_of"]):
                name = f"{name} [{node['alternative']}]"
            elif counts.get(str(name).casefold(), 0) > 1 and not pd.isna(node["parent_id"]):
                name = f"{name} ({nodes.loc[int(node['parent_id']), 'name']})"
            labels[int(node_id)] = name
        return labels

    def has_children(self, node_id: int) -> bool:
        return bool(self.nodes.loc[node_id, "has_children"])

    def depth(self, node_id: int) -> int:
        return int(self.nodes.loc[node_id, "depth"])

    def path(self, path_ids: str) -> list[int]:
        if path_ids not in self._paths:
            self._paths[path_ids] = [int(part) for part in path_ids.strip("/").split("/")]
        return self._paths[path_ids]

    def levels(self, design: str = BASE_DESIGN) -> int:
        """Number of levels below the product in a design."""
        rows = self.inventory[self.inventory["design"] == design]
        if rows.empty:
            return 0
        return max(len(self.path(p)) for p in rows["path_ids"].unique()) - 1

    def elements(self, design: str = BASE_DESIGN) -> list[int]:
        """Elements in a design, in tree order (parents before children)."""
        rows = self.inventory[self.inventory["design"] == design]
        seen: dict[int, None] = {}
        for path_ids in sorted(rows["path_ids"].unique(), key=lambda p: self.path(p)):
            for node_id in self.path(path_ids):
                seen.setdefault(node_id, None)
        return list(seen)

    # --------------------------------------------------------------- rows

    def rows(self, design: str = BASE_DESIGN, setting: str | list | None = "average",
             market: str | list | None = None, varied: str | None = None) -> pd.DataFrame:
        frame = self.inventory
        mask = frame["design"] == design
        if setting is not None:
            mask &= frame["setting"].isin([setting] if isinstance(setting, str) else setting)
        if market is not None:
            mask &= frame["market"].isin([market] if isinstance(market, str) else market)
        if varied is None:
            mask &= frame["varied_scenario"].isna()
        else:
            mask &= frame["varied_scenario"] == varied
        return frame[mask]

    def subtree(self, rows: pd.DataFrame, node_id: int) -> pd.DataFrame:
        return rows[rows["path_ids"].str.contains(f"/{node_id}/", regex=False)]

    # ----------------------------------------------------------- grouping

    def at_level(self, rows: pd.DataFrame, level: int) -> pd.Series:
        """The element at ``level`` (0 = product) each row belongs to."""
        def label(path_ids):
            path = self.path(path_ids)
            if len(path) > level:
                return self.labels[path[level]]
            node = path[-1]
            return self.labels[node] + (OWN if self.has_children(node) else "")
        return rows["path_ids"].map(label)

    def parts_of(self, rows: pd.DataFrame, node_id: int) -> tuple[pd.Series, str]:
        """Labels for the parts of an element, and what the parts are.

        Returns ("elements") the sub-elements plus a slice for the element's own
        processes, or ("processes") the individual entries and steps if the
        element has no sub-elements.
        """
        if not self.has_children(node_id):
            return self.process_labels(rows), "processes"

        def label(path_ids):
            path = self.path(path_ids)
            index = path.index(node_id)
            if index + 1 < len(path):
                return self.labels[path[index + 1]]
            return self.labels[node_id] + OWN
        return rows["path_ids"].map(label), "elements"

    @staticmethod
    def process_labels(rows: pd.DataFrame) -> pd.Series:
        """Entries by their description; transport and end-of-life steps by what they are."""
        description = rows["description"].fillna(rows["dataset"])
        steps = rows["source"] != "entry"
        labelled = description.copy()
        labelled[steps] = (rows["source"][steps].map(SOURCE_LABELS) + ": "
                           + rows["dataset"][steps].astype(str))
        return labelled

    def total(self, rows: pd.DataFrame, key: str) -> float:
        return float(rows[key].sum())

    @staticmethod
    def top90(series: pd.Series, label: str) -> tuple[list[tuple[str, float]], pd.DataFrame]:
        """The largest contributors that together make up 90 % of the total.

        Shares are taken of the sum of positive contributions, so that credits
        do not inflate them; negative contributions are listed separately.
        """
        positive = series[series > 0]
        total = positive.sum()
        if total <= 0:
            return [], pd.DataFrame(columns=[label, "Contribution share (%)"])
        share = (series / total * 100).sort_values(ascending=False)
        contributors, cumulative = [], 0.0
        for name, value in share.items():
            if value <= 0:
                break
            contributors.append((name, round(float(value), 1)))
            cumulative += value
            if cumulative >= 90:
                break
        table = share.round(1).reset_index()
        table.columns = [label, "Contribution share (%)"]
        main = table[table["Contribution share (%)"].abs() > 2]
        rest = table.loc[table["Contribution share (%)"].abs() <= 2, "Contribution share (%)"].sum()
        if len(main) < len(table):
            main = pd.concat([main, pd.DataFrame([{label: "Remaining",
                                                    "Contribution share (%)": round(rest, 1)}])],
                             ignore_index=True)
        return contributors, main.reset_index(drop=True)

    # -------------------------------------------------------- uncertainty

    @staticmethod
    def uncertainty(rows: pd.DataFrame, key: str) -> tuple[float, float]:
        """Impact-weighted mean uncertainty score, and the share of impact without a score."""
        weights = rows[key].abs()
        total = weights.sum()
        if total == 0:
            return np.nan, 0.0
        scored = rows["uncertainty_score"].notna()
        if not scored.any():
            return np.nan, 1.0
        mean = float((rows.loc[scored, "uncertainty_score"] * weights[scored]).sum()
                     / weights[scored].sum()) if weights[scored].sum() else np.nan
        return mean, float(weights[~scored].sum() / total)

    def sunburst(self, rows: pd.DataFrame, key: str, top: int | None = None,
                 max_depth: int | None = None) -> pd.DataFrame:
        """ids / parents / values / colour for a sunburst of the tree.

        Contributions below zero (credits) cannot be drawn as segments and are
        left out; ``credits`` in the attrs of the result says how much.
        """
        top = self.root_id if top is None else top
        rows = self.subtree(rows, top)
        values: dict[str, float] = {}
        weighted: dict[str, float] = {}
        scored: dict[str, float] = {}
        labels: dict[str, str] = {}
        parents: dict[str, str] = {}
        credits = float(-rows.loc[rows[key] < 0, key].sum())
        for path_ids, value, score in zip(rows["path_ids"], rows[key], rows["uncertainty_score"]):
            if value <= 0:
                continue
            path = self.path(path_ids)
            path = path[path.index(top):]
            chain = []
            for node_id in path:
                chain.append(str(node_id))
                ident = "/".join(chain)
                labels[ident] = self.labels[node_id]
                parents[ident] = "/".join(chain[:-1])
            node_id = path[-1]
            if self.has_children(node_id):          # the element's own processes
                own = ident + "/own"
                labels[own] = self.labels[node_id] + OWN
                parents[own] = ident
                chain.append("own")
            if max_depth is not None:
                chain = chain[:max_depth + 1]
            for i in range(1, len(chain) + 1):
                ident = "/".join(chain[:i])
                values[ident] = values.get(ident, 0.0) + value
                if not pd.isna(score):
                    weighted[ident] = weighted.get(ident, 0.0) + value * score
                    scored[ident] = scored.get(ident, 0.0) + value
        frame = pd.DataFrame({
            "id": list(values), "label": [labels[i] for i in values],
            "parent": [parents[i] for i in values], "value": list(values.values()),
            "uncertainty": [weighted[i] / scored[i] if scored.get(i) else np.nan
                            for i in values],
        })
        frame.attrs["credits"] = credits
        return frame

    # -------------------------------------------------- impact categories

    def normalised(self, rows: pd.DataFrame) -> pd.DataFrame:
        """Per category: characterised total, normalised (person-years) and weighted points."""
        totals = rows[list(ef31.CATEGORY_IDS)].sum()
        records = []
        for category in ef31.CATEGORIES:
            value = float(totals[category.id])
            records.append({
                "Impact category": category.name, "Characterised": value, "Unit": category.unit,
                "Normalised (person-year eq.)": value / category.normalisation,
                "Weighted (Pt)": value / category.normalisation * category.weighting / 100,
            })
        frame = pd.DataFrame(records)
        total = frame["Weighted (Pt)"].sum()
        frame["Share of single score (%)"] = frame["Weighted (Pt)"] / total * 100 if total else 0.0
        return frame

    # ---------------------------------------------------------- scenarios

    def tornado(self, key: str, market: str, node_id: int | None = None) -> pd.DataFrame:
        """Change against the average case when one scenario at a time is best or worst."""
        node_id = self.root_id if node_id is None else node_id
        average = self.total(self.subtree(self.rows(setting="average", market=market), node_id),
                             key)
        records = []
        for scenario in self.scenarios:
            row = {"Scenario": scenario}
            for setting in ("best", "worst"):
                value = self.total(self.subtree(
                    self.rows(setting=setting, market=market, varied=scenario), node_id), key)
                row[setting] = value
                row[f"{setting} (%)"] = (value - average) / abs(average) * 100 if average else 0.0
            records.append(row)
        frame = pd.DataFrame(records, columns=["Scenario", "best", "best (%)", "worst",
                                               "worst (%)"])
        if frame.empty:
            return frame
        frame["swing"] = (frame["worst (%)"] - frame["best (%)"]).abs()
        return frame.sort_values("swing").reset_index(drop=True)

    # -------------------------------------------------------- alternatives

    def alternatives(self) -> list[Alternative]:
        found = []
        for design in self.meta.get("designs", []):
            if len(design["substitutions"]) != 1:
                continue
            base_id, alt_id = design["substitutions"][0]
            if design["name"] not in set(self.inventory["design"]):
                continue
            node = self.nodes.loc[alt_id]
            found.append(Alternative(
                design["name"], int(base_id), int(alt_id), bool(node["is_removed"]),
                node["alt_short_description"], node["alt_long_description"]))
        return found

    def product_cost(self, design: str, setting: str, market: str) -> float | None:
        costs = self.results.costs
        if costs.empty:
            return None
        mask = ((costs["design"] == design) & (costs["setting"] == setting)
                & (costs["market"] == market) & costs["varied_scenario"].isna()
                & (costs["node_id"] == self.design_root(design)))
        found = costs.loc[mask, "cost"]
        return None if found.empty or pd.isna(found.iloc[0]) else float(found.iloc[0])

    def element_cost(self, design: str, setting: str, market: str, node_id: int) -> float | None:
        costs = self.results.costs
        if costs.empty:
            return None
        mask = ((costs["design"] == design) & (costs["setting"] == setting)
                & (costs["market"] == market) & costs["varied_scenario"].isna()
                & (costs["node_id"] == node_id))
        found = costs.loc[mask, "cost"]
        return None if found.empty or pd.isna(found.iloc[0]) else float(found.iloc[0])

    def design_root(self, design: str) -> int:
        for alternative in self.alternatives():
            if alternative.name == design and alternative.base_id == self.root_id:
                return alternative.alternative_id
        return self.root_id

    def design_summary(self, key: str, setting: str, market: str) -> pd.DataFrame:
        """Each design against the base: impact, cost and what one unit of reduction costs."""
        designs = [BASE_DESIGN] + [a.name for a in self.alternatives()]
        base_impact = self.total(self.rows(BASE_DESIGN, setting, market), key)
        base_cost = self.product_cost(BASE_DESIGN, setting, market)
        records = []
        for design in designs:
            rows = self.rows(design, setting, market)
            impact = self.total(rows, key)
            cost = self.product_cost(design, setting, market)
            reduction = base_impact - impact
            cost_change = None if cost is None or base_cost is None else cost - base_cost
            mean, _ = self.uncertainty(rows, key)
            records.append({
                "Design": design,
                "Impact": impact,
                "Impact reduction": reduction,
                "Impact reduction (%)": reduction / base_impact * 100 if base_impact else np.nan,
                "Cost": cost,
                "Cost change": cost_change,
                "Cost change (%)": (cost_change / base_cost * 100
                                    if cost_change is not None and base_cost else np.nan),
                "Cost per unit of reduction": (cost_change / reduction
                                               if cost_change is not None and reduction else np.nan),
                "Uncertainty": mean,
            })
        return pd.DataFrame(records)

    def compare(self, alternative: Alternative, key: str, setting: str,
                market: str) -> pd.DataFrame:
        """Base element and its alternative: the element itself and the whole product."""
        base_rows = self.rows(BASE_DESIGN, setting, market)
        alt_rows = self.rows(alternative.name, setting, market)
        records = []
        for label, rows, node in (("Base design", base_rows, alternative.base_id),
                                  (alternative.name, alt_rows, alternative.alternative_id)):
            part = self.subtree(rows, node) if not (
                node == alternative.alternative_id and alternative.removed) else rows.iloc[0:0]
            product = self.total(rows, key)
            impact = self.total(part, key)
            design = BASE_DESIGN if label == "Base design" else alternative.name
            mean, _ = self.uncertainty(part, key)
            records.append({
                "Version": label,
                "Element impact": impact,
                "Element share of product (%)": impact / product * 100 if product else np.nan,
                "Product impact": product,
                "Element cost": self.element_cost(design, setting, market, node),
                "Product cost": self.product_cost(design, setting, market),
                "Uncertainty": mean,
            })
        frame = pd.DataFrame(records)
        base = frame.iloc[0]
        frame["Product change (%)"] = ((frame["Product impact"] - base["Product impact"])
                                       / abs(base["Product impact"]) * 100
                                       if base["Product impact"] else np.nan)
        return frame

    # ------------------------------------------------------ classifications

    def ghg(self, rows: pd.DataFrame) -> pd.DataFrame:
        """Climate change by GHG Protocol category, including what is not classified."""
        from ..model.classifications import GHG_CATEGORIES
        category = rows["ghg_category"].fillna(UNCLASSIFIED)
        grouped = rows.groupby(category)["climate_change"].sum()
        order = [c for c in GHG_CATEGORIES if c in grouped.index] + (
            [UNCLASSIFIED] if UNCLASSIFIED in grouped.index else [])
        total = grouped.sum()
        return pd.DataFrame({
            "Category": [GHG_CATEGORIES.get(c, c) for c in order],
            "Climate change (kg CO2 eq)": [grouped[c] for c in order],
            "Share (%)": [grouped[c] / total * 100 if total else np.nan for c in order],
        })

    def en15804(self, rows: pd.DataFrame) -> pd.DataFrame:
        """All 16 categories (rows) by EN 15804 module (columns), including unclassified."""
        from ..model.classifications import EN15804_MODULES
        module = rows["en15804_module"].fillna(UNCLASSIFIED)
        grouped = rows.groupby(module)[list(ef31.CATEGORY_IDS)].sum()
        order = [m for m in EN15804_MODULES if m in grouped.index] + (
            [UNCLASSIFIED] if UNCLASSIFIED in grouped.index else [])
        table = grouped.loc[order].T
        table.insert(0, "Unit", [c.unit for c in ef31.CATEGORIES])
        table.insert(0, "Impact category", [c.name for c in ef31.CATEGORIES])
        table["Total"] = grouped.loc[order].sum().values
        return table.reset_index(drop=True)

    # ---------------------------------------------------------- data notes

    def data_notes(self, rows: pd.DataFrame, key: str) -> list[str]:
        """Plain-language notes on what the shown result relies on."""
        notes = []
        total = rows[key].abs().sum()
        for database in self.meta.get("databases", []):
            share = rows.loc[rows["database"] == database["name"], key].abs().sum()
            if not share or not total:
                continue
            coverage = database.get("coverage") or {}
            part = f"{share / total:.0%} of this result comes from '{database['name']}'"
            if coverage.get("derived"):
                notes.append(f"{part}, whose values are calculated back from weighted scores.")
            missing = coverage.get("missing_categories") or []
            if missing:
                notes.append(f"'{database['name']}' does not cover {', '.join(missing)}; "
                             "results in those categories are understated where it is used.")
        if self.toggles.get("uncertainty"):
            _, unscored = self.uncertainty(rows, key)
            if unscored > 0.005:
                notes.append(f"{unscored:.0%} of this result has no pedigree scores; the "
                             "uncertainty shown covers the rest.")
        credits = rows.loc[rows[key] < 0, key].sum()
        if credits < 0 and total:
            notes.append(f"Credits (negative amounts) reduce this result by "
                         f"{-credits / rows[key].clip(lower=0).sum():.1%}.")
        if not self.results.exclusions.empty:
            notes.append(f"{len(self.results.exclusions)} item(s) were knowingly left out; "
                         "see 'Input data'.")
        return notes
