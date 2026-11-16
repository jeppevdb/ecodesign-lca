"""Results of a calculation, with saving and loading.

Results are kept in their own file next to the project, not inside it:
row-level results would let impact factors of the datasets used be worked
out, so a project file can be shared without them.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..method import ef31

RUN_COLUMNS = ["design", "setting", "market", "varied_scenario"]
IMPACT_COLUMNS = [*ef31.CATEGORY_IDS, "single_score"]
_TABLES = ("inventory", "costs", "nodes", "exclusions")


@dataclass
class Results:
    inventory: pd.DataFrame      # one row per entry or pathway leg, per run, per one product
    costs: pd.DataFrame          # price of every element per run (empty unless cost is on)
    nodes: pd.DataFrame          # the product tree, including alternatives
    exclusions: pd.DataFrame     # what was deliberately left out, with reasons
    meta: dict = field(default_factory=dict)

    # --------------------------------------------------------------- views

    def view(self, design: str = "Base design", setting: str = "average",
             market: str | None = None, varied_scenario: str | None = None) -> pd.DataFrame:
        """The full inventory behind one result ("as calculated")."""
        frame = self.inventory
        mask = (frame["design"] == design) & (frame["setting"] == setting)
        if market is not None:
            mask &= frame["market"] == market
        if varied_scenario is None:
            mask &= frame["varied_scenario"].isna()
        else:
            mask &= frame["varied_scenario"] == varied_scenario
        return frame[mask]

    def totals(self) -> pd.DataFrame:
        """Impact per product for every run."""
        return (self.inventory.groupby(RUN_COLUMNS, dropna=False, sort=False)[IMPACT_COLUMNS]
                .sum().reset_index())

    def subtree(self, frame: pd.DataFrame, node_id: int) -> pd.DataFrame:
        """Rows of an element and everything below it."""
        return frame[frame["path_ids"].str.contains(f"/{node_id}/", regex=False)]

    def scenario_direction_warnings(self) -> list[str]:
        """Scenarios whose best case scores worse than their worst case."""
        totals = self.totals()
        varied = totals[totals["varied_scenario"].notna()]
        if varied.empty:
            return []
        table = varied.pivot_table(index=["varied_scenario", "market"], columns="setting",
                                   values="single_score")
        wrong = table[table["best"] > table["worst"] * (1 + 1e-9)]
        return [f"Scenario '{scenario}' gives a higher single score in its best case than in "
                f"its worst case (market '{market}'): the values may be the wrong way round."
                for scenario, market in wrong.index]

    # ---------------------------------------------------------------- file

    def save(self, path) -> None:
        path = Path(path)
        if path.exists():
            path.unlink()
        with sqlite3.connect(path) as conn:
            for name in _TABLES:
                getattr(self, name).to_sql(name, conn, index=False)
            conn.execute("CREATE TABLE meta (value TEXT)")
            conn.execute("INSERT INTO meta VALUES (?)", (json.dumps(self.meta),))
        conn.close()

    @classmethod
    def load(cls, path) -> "Results":
        conn = sqlite3.connect(path)
        try:
            tables = {name: pd.read_sql_query(f"SELECT * FROM {name}", conn) for name in _TABLES}
            meta = json.loads(conn.execute("SELECT value FROM meta").fetchone()[0])
        finally:
            conn.close()
        return cls(**tables, meta=meta)

    def is_current(self, project) -> bool:
        """False if the project changed since these results were calculated."""
        from .engine import fingerprint
        return self.meta.get("fingerprint") == fingerprint(project)
