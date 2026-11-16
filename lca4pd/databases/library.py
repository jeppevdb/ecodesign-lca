"""Local store of imported databases.

Impact factors live here, on the user's machine, and never in a project file.
A project refers to a database by the fingerprint of the uploaded file, so the
same library serves every project that uses that file.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..method import ef31
from ..model import units
from .reader import ParsedDatabase

_VALUE_COLUMNS = [f"v{index}" for index in range(ef31.N)]

_DDL = f"""
CREATE TABLE IF NOT EXISTS database (
    file_hash TEXT PRIMARY KEY,
    kind      TEXT NOT NULL,
    name      TEXT NOT NULL,
    version   TEXT,
    protocol  TEXT NOT NULL,
    file_name TEXT,
    items     INTEGER NOT NULL,
    report    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS item (
    file_hash  TEXT NOT NULL REFERENCES database(file_hash) ON DELETE CASCADE,
    key        TEXT NOT NULL,
    name       TEXT NOT NULL,
    unit       TEXT NOT NULL,
    dimension  TEXT NOT NULL,
    location   TEXT,
    category   TEXT,
    relink_key TEXT,
    search     TEXT NOT NULL,
    {", ".join(f"{column} REAL NOT NULL" for column in _VALUE_COLUMNS)},
    PRIMARY KEY (file_hash, key)
);
CREATE INDEX IF NOT EXISTS item_relink ON item(file_hash, relink_key);
"""


class Library:
    def __init__(self, directory):
        """Open (or create) the library in ``directory`` (``":memory:"`` for a temporary one)."""
        if str(directory) == ":memory:":
            target = ":memory:"
        else:
            Path(directory).mkdir(parents=True, exist_ok=True)
            target = str(Path(directory) / "library.sqlite")
        self.conn = sqlite3.connect(target)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        with self.conn:
            self.conn.executescript(_DDL)

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------ databases

    def add(self, parsed: ParsedDatabase, name: str, version: str | None = None) -> str:
        """Store a parsed file and return its fingerprint. Re-adding a file replaces it."""
        report = parsed.report
        summary = {
            "datasets": report.datasets, "derived": report.derived,
            "coverage": report.coverage, "missing_categories": report.missing_categories,
            "partial_categories": report.partial_categories, "messages": report.messages,
        }
        columns = ", ".join(_VALUE_COLUMNS)
        marks = ", ".join("?" * (9 + ef31.N))
        with self.conn:
            self.conn.execute("DELETE FROM database WHERE file_hash = ?", (parsed.file_hash,))
            self.conn.execute(
                "INSERT INTO database VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (parsed.file_hash, parsed.kind, name, version or report.version,
                 report.protocol, parsed.file_name, len(parsed.items), json.dumps(summary)),
            )
            self.conn.executemany(
                f"INSERT INTO item (file_hash, key, name, unit, dimension, location, category,"
                f" relink_key, search, {columns}) VALUES ({marks})",
                ((parsed.file_hash, item.key, item.name, item.unit, units.dimension(item.unit),
                  item.location, item.category, item.relink_key,
                  " ".join(filter(None, (item.name, item.location, item.category, item.key))).casefold(),
                  *item.values) for item in parsed.items),
            )
        return parsed.file_hash

    def databases(self) -> list[dict]:
        rows = [dict(row) for row in self.conn.execute("SELECT * FROM database ORDER BY name")]
        for row in rows:
            row["report"] = json.loads(row["report"])
        return rows

    def database(self, file_hash: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM database WHERE file_hash = ?", (file_hash,)).fetchone()
        if row is None:
            return None
        return {**dict(row), "report": json.loads(row["report"])}

    def has(self, file_hash: str | None) -> bool:
        return file_hash is not None and self.database(file_hash) is not None

    def remove(self, file_hash: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM database WHERE file_hash = ?", (file_hash,))

    # ---------------------------------------------------------------- items

    @staticmethod
    def _item(row) -> dict:
        item = dict(row)
        item["values"] = tuple(item.pop(column) for column in _VALUE_COLUMNS)
        item.pop("search", None)
        return item

    def get(self, file_hash: str, key: str) -> dict | None:
        """One dataset or flow with its characterised results per unit."""
        row = self.conn.execute(
            "SELECT * FROM item WHERE file_hash = ? AND key = ?", (file_hash, key)).fetchone()
        return None if row is None else self._item(row)

    def by_relink_key(self, file_hash: str, relink_key: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM item WHERE file_hash = ? AND relink_key = ?", (file_hash, relink_key))
        return [self._item(row) for row in rows]

    def search(self, text: str = "", *, kind: str | None = None,
               databases: list[str] | None = None, dimension: str | None = None,
               limit: int = 50) -> list[dict]:
        """Find datasets whose name, location, category or key contains every word of ``text``.

        ``dimension`` restricts the result to one kind of unit (e.g. "mass" or
        "transport"), ``databases`` to the given file fingerprints.
        """
        where, params = [], []
        for word in text.casefold().split():
            where.append("i.search LIKE ? ESCAPE '\\'")
            escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        if kind:
            where.append("d.kind = ?")
            params.append(kind)
        if dimension:
            where.append("i.dimension = ?")
            params.append(dimension)
        if databases is not None:
            if not databases:
                return []
            where.append(f"i.file_hash IN ({', '.join('?' * len(databases))})")
            params.extend(databases)
        first_word = text.casefold().split()[0] if text.split() else ""
        sql = (
            "SELECT i.*, d.name AS database_name, d.kind AS kind FROM item i"
            " JOIN database d ON d.file_hash = i.file_hash"
            + (" WHERE " + " AND ".join(where) if where else "")
            # names that start with the first search word come first, then shorter names
            + " ORDER BY (i.search LIKE ? ESCAPE '\\') DESC, LENGTH(i.name), i.name LIMIT ?"
        )
        escaped_first = first_word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self.conn.execute(sql, (*params, f"{escaped_first}%", int(limit)))
        return [self._item(row) for row in rows]
