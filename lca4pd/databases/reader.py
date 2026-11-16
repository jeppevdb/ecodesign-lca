"""Read an impact-factor workbook according to a protocol.

A protocol is a small TOML file (see ``protocols/``) that says where the
dataset columns and the EF 3.1 columns are. Headings are found by their text,
not by fixed positions, so a new release with a shifted column still reads.
"""

from __future__ import annotations

import hashlib
import math
import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..method import ef31
from ..model import units
from .sheets import iter_rows, sheet_names

HEADER_AREA = 40            # rows searched for headings
NOT_COVERED_BELOW = 0.1     # share of non-zero datasets below which a category counts as not covered
PARTLY_COVERED_BELOW = 0.5  # … and below which it counts as only partly covered
SCORE_TOLERANCE = 1e-3
PROTOCOL_DIR = Path(__file__).parent / "protocols"


class ProtocolMismatch(ValueError):
    """The file does not have the layout the protocol describes."""


@dataclass(frozen=True)
class Item:
    key: str
    name: str
    unit: str
    location: str | None
    category: str | None
    relink_key: str | None
    values: tuple[float, ...]        # characterised results per unit, in ef31.CATEGORIES order


@dataclass
class ImportReport:
    protocol: str
    sheet: str | None = None
    version: str | None = None
    datasets: int = 0
    derived: bool = False            # values calculated back from weighted points
    coverage: dict[str, float] = field(default_factory=dict)   # category id -> share non-zero
    missing_categories: list[str] = field(default_factory=list)  # category names
    partial_categories: list[str] = field(default_factory=list)
    messages: list[tuple[str, str]] = field(default_factory=list)  # ("warning" | "info", text)

    def warn(self, text: str) -> None:
        self.messages.append(("warning", text))

    def info(self, text: str) -> None:
        self.messages.append(("info", text))

    def as_coverage(self) -> dict:
        """What the project stores about the database."""
        return {"derived": self.derived, "missing_categories": self.missing_categories,
                "partial_categories": self.partial_categories}


@dataclass
class ParsedDatabase:
    kind: str                        # "process" or "flow"
    file_name: str
    file_hash: str
    items: list[Item]
    report: ImportReport


@dataclass(frozen=True)
class Protocol:
    id: str
    title: str
    value_mode: str
    sheet: str
    method: dict
    columns: dict
    categories: dict
    compare: tuple = ()
    version: dict | None = None

    @classmethod
    def load(cls, path) -> "Protocol":
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
        if data.get("value_mode") not in ("characterised", "weighted_points"):
            raise ValueError(f"{path}: value_mode must be 'characterised' or 'weighted_points'.")
        missing = set(ef31.CATEGORY_IDS) - set(data.get("categories", {}))
        if missing:
            raise ValueError(f"{path}: no heading given for {', '.join(sorted(missing))}.")
        return cls(
            id=data["id"], title=data.get("title", data["id"]), value_mode=data["value_mode"],
            sheet=data.get("sheet", ""), method=data["method"], columns=data["columns"],
            categories=data["categories"], compare=tuple(data.get("compare", ())),
            version=data.get("version"),
        )


def load_protocols(directory=PROTOCOL_DIR) -> dict[str, Protocol]:
    protocols = (Protocol.load(path) for path in sorted(Path(directory).glob("*.toml")))
    return {protocol.id: protocol for protocol in protocols}


# ----------------------------------------------------------------- helpers

def file_hash(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm(value) -> str:
    """Heading text for comparison: collapsed whitespace, case-insensitive."""
    return "" if value is None else " ".join(str(value).split()).casefold()


def repair_text(text: str) -> str:
    """Undo text that was decoded with the wrong character set ('ZÃ¼rich' -> 'Zürich')."""
    for _ in range(3):
        if "Ã" not in text and "Â" not in text:
            break
        try:
            fixed = text.encode("cp1252").decode("utf-8")
        except UnicodeError:
            break
        if fixed == text:
            break
        text = fixed
    return text


def column_index(letters: str) -> int:
    index = 0
    for letter in letters.strip().upper():
        index = index * 26 + (ord(letter) - ord("A") + 1)
    return index - 1


def as_number(value) -> float | None:
    """A cell as a float; ``None`` if empty; ``nan`` if it is not a number."""
    if value is None:
        return None
    if isinstance(value, bool):
        return math.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return math.nan


def cell(row: list, index: int):
    return row[index] if 0 <= index < len(row) else None


# ------------------------------------------------------------------ layout

@dataclass
class Layout:
    sheet: str
    data_start: int
    category_columns: dict[str, int]
    single_score_column: int | None
    block_headings: list[str]


def _find(head: list[list], label: str, skip: set[int] = frozenset()):
    wanted = norm(label)
    for r, row in enumerate(head):
        for c, value in enumerate(row):
            if c not in skip and norm(value) == wanted:
                return r, c
    return None


def _column(spec: dict, head: list[list], block: set[int]):
    """Resolve a column given by letter or by heading. Returns (column, heading row)."""
    if "column" in spec:
        return column_index(spec["column"]), -1
    for label in spec["labels"]:
        found = _find(head, label, block)
        if found:
            return found[1], found[0]
    raise ProtocolMismatch(f"no column headed {' or '.join(repr(l) for l in spec['labels'])}")


def _specs(protocol: Protocol) -> dict[str, list[dict]]:
    """Every identifying column of the protocol as a list of column specs."""
    result = {}
    for name, spec in protocol.columns.items():
        result[name] = spec if isinstance(spec, list) else [spec]
    for required in ("key", "name", "unit"):
        if required not in result:
            raise ValueError(f"Protocol '{protocol.id}' does not say where the {required} is.")
    return result


def locate(protocol: Protocol, sheet: str, head: list[list]) -> tuple[Layout, dict]:
    """Find the protocol's columns in the top rows of a sheet."""
    label = protocol.method["label"]
    found = _find(head, label)
    if not found:
        others = sorted({" ".join(str(v).split()) for row in head for v in row
                         if isinstance(v, str) and re.match(r"\s*EF\s*v?\d", v)})
        hint = f" (found instead: {', '.join(others[:6])})" if others else ""
        raise ProtocolMismatch(f"no heading '{label}'{hint}")
    method_row, first = found
    width = max(len(row) for row in head)
    block: list[int] = []
    if protocol.method.get("extent", "filled") == "until_blank":
        c = first
        while c < width and norm(cell(head[method_row], c)):
            block.append(c)
            c += 1
    else:
        for c in range(first, width):
            value = norm(cell(head[method_row], c))
            if value and value != norm(label):
                break
            block.append(c)
    block_set = set(block)

    columns, last_heading_row = {}, method_row
    for name, specs in _specs(protocol).items():
        resolved = []
        for spec in specs:
            index, row_index = _column(spec, head, block_set)
            resolved.append((index, spec.get("regex")))
            last_heading_row = max(last_heading_row, row_index)
        columns[name] = resolved

    data_start = None
    for r in range(last_heading_row + 1, len(head)):
        numeric = sum(1 for c in block
                      if (n := as_number(cell(head[r], c))) is not None and not math.isnan(n))
        if numeric * 2 >= len(block):
            data_start = r
            break
    if data_start is None:
        raise ProtocolMismatch(f"no rows with numbers below the '{label}' headings")

    headings: dict[int, set[str]] = {}
    shown: list[str] = []
    for c in block:
        parts = [norm(cell(head[r], c)) for r in range(data_start)]
        parts = [part for part in parts if part]
        headings[c] = set(parts) | {" ".join(parts)}
        shown.append(" ".join(str(cell(head[r], c)).strip() for r in range(data_start)
                              if cell(head[r], c) is not None))

    def match(labels) -> list[int]:
        wanted = {norm(l) for l in labels}
        return [c for c in block if headings[c] & wanted]

    category_columns, problems = {}, []
    for category in ef31.CATEGORIES:
        matches = match(protocol.categories[category.id])
        if len(matches) == 1:
            category_columns[category.id] = matches[0]
        else:
            problems.append(f"{category.name}: "
                            f"{'no column' if not matches else 'several columns'}")
    if problems:
        raise ProtocolMismatch(
            "EF 3.1 columns not recognised (" + "; ".join(problems) + "). Headings found: "
            + " | ".join(shown))
    score = match(protocol.method.get("single_score", []))
    layout = Layout(sheet, data_start, category_columns, score[0] if score else None, shown)
    return layout, columns


def find_layout(path, protocol: Protocol) -> tuple[Layout, dict]:
    """Locate the protocol in the workbook, or raise ``ProtocolMismatch`` saying why not."""
    names = sheet_names(path)
    pattern = re.compile(protocol.sheet, re.IGNORECASE)
    candidates = [name for name in names if pattern.search(name)] or names
    reasons = []
    for sheet in candidates:
        head = list(iter_rows(path, sheet, max_rows=HEADER_AREA))
        if not head:
            continue
        try:
            return locate(protocol, sheet, head)
        except ProtocolMismatch as error:
            reasons.append(f"sheet '{sheet}': {error}")
    raise ProtocolMismatch("; ".join(reasons) or "the workbook has no readable sheets")


def detect(path, protocols: dict[str, Protocol] | None = None) -> list[str]:
    """Ids of the protocols whose layout is found in the file."""
    matching = []
    for protocol in (protocols or load_protocols()).values():
        try:
            find_layout(path, protocol)
        except ProtocolMismatch:
            continue
        matching.append(protocol.id)
    return matching


# ------------------------------------------------------------------ reading

def _text(row: list, specs: list[tuple[int, str | None]], joiner: str) -> str | None:
    parts = []
    for index, regex in specs:
        value = cell(row, index)
        if value is None:
            continue
        text = " ".join(str(value).split())
        if regex:
            found = re.search(regex, text)
            text = found.group(1).strip() if found else ""
        if text and text.upper() != "#N/A":
            parts.append(text)
    return joiner.join(parts) or None


def _read_version(path, spec: dict | None) -> str | None:
    if not spec or spec["sheet"] not in sheet_names(path):
        return None
    for row in iter_rows(path, spec["sheet"], max_rows=HEADER_AREA):
        for c, value in enumerate(row):
            if norm(value) == norm(spec["label"]):
                rest = [v for v in row[c + 1:] if v is not None]
                return str(rest[0]).strip() if rest else None
    return None


def read_process_database(path, protocol: Protocol) -> ParsedDatabase:
    """Read every dataset of an impact-factor workbook.

    Raises ``ProtocolMismatch`` if the layout is not found. Rows that cannot be
    used are left out and counted in the report.
    """
    path = Path(path)
    layout, columns = find_layout(path, protocol)
    report = ImportReport(protocol=protocol.id, sheet=layout.sheet,
                          derived=protocol.value_mode == "weighted_points",
                          version=_read_version(path, protocol.version))
    value_columns = [layout.category_columns[cid] for cid in ef31.CATEGORY_IDS]
    compare = [(ef31.CATEGORY_IDS.index(c["category"]), column_index(c["column"]),
                c.get("tolerance", 0.01)) for c in protocol.compare]

    rows: list[Item] = []
    counts = dict(non_numeric=0, empty=0, no_unit=0, blanks=0, repaired=0,
                  no_category=0, score_off=0, score_checked=0)
    compare_off = [0] * len(compare)
    compare_checked = [0] * len(compare)

    for index, row in enumerate(iter_rows(path, layout.sheet)):
        if index < layout.data_start:
            continue
        key = _text(row, columns["key"], " ")
        if not key:
            continue                                   # section heading or empty row
        numbers = [as_number(cell(row, c)) for c in value_columns]
        if any(n is not None and math.isnan(n) for n in numbers):
            counts["non_numeric"] += 1
            continue
        if all(n is None or n == 0 for n in numbers):
            counts["empty"] += 1
            continue
        counts["blanks"] += any(n is None for n in numbers)
        values = [n or 0.0 for n in numbers]
        unit = _text(row, columns["unit"], " ")
        if not unit:
            counts["no_unit"] += 1
            continue

        if layout.single_score_column is not None:
            total = as_number(cell(row, layout.single_score_column))
            if total:
                points = values if report.derived else ef31.weighted(values)
                counts["score_checked"] += 1
                counts["score_off"] += abs(sum(points) - total) > SCORE_TOLERANCE * abs(total)
        if report.derived:
            values = ef31.from_weighted(values)
        for n, (category_index, column, tolerance) in enumerate(compare):
            reference = as_number(cell(row, column))
            if reference and not math.isnan(reference) and values[category_index]:
                compare_checked[n] += 1
                compare_off[n] += (abs(values[category_index] - reference)
                                   > tolerance * abs(reference))

        raw_name = _text(row, columns["name"], " | ") or key
        name = repair_text(raw_name)
        counts["repaired"] += name != raw_name
        category = _text(row, columns.get("category", []), " / ")
        counts["no_category"] += "category" in columns and category is None
        rows.append(Item(
            key=key, name=name, unit=units.canonical(unit),
            location=_text(row, columns.get("location", []), " "),
            category=repair_text(category) if category else None,
            relink_key=_text(row, columns.get("relink_key", []), " "),
            values=tuple(values),
        ))

    # An identifier used for several datasets is told apart by adding the name.
    # Only rows that are still indistinguishable are left out.
    seen = Counter(item.key for item in rows)
    shared = {key for key, count in seen.items() if count > 1}
    rows = [replace(item, key=f"{item.key} | {item.name}") if item.key in shared else item
            for item in rows]
    seen = Counter(item.key for item in rows)
    duplicates = {key for key, count in seen.items() if count > 1}
    result = [item for item in rows if item.key not in duplicates]
    shared = {key for key in shared
              if any(item.key.startswith(f"{key} | ") for item in result)}
    report.datasets = len(result)
    if not result:
        raise ProtocolMismatch("the layout was found but no dataset could be read")
    for category_index, category in enumerate(ef31.CATEGORIES):
        share = sum(1 for item in result if item.values[category_index] != 0) / len(result)
        report.coverage[category.id] = share
        if share < NOT_COVERED_BELOW:
            report.missing_categories.append(category.name)
            report.warn(f"'{category.name}' is zero for {1 - share:.0%} of the datasets: "
                        "treated as not covered by this database.")
        elif share < PARTLY_COVERED_BELOW:
            report.partial_categories.append(category.name)
            report.warn(f"'{category.name}' is zero for {1 - share:.0%} of the datasets: "
                        "only partly covered.")

    if report.derived:
        report.info("Values are calculated back from weighted points with the EF 3.1 "
                    "normalisation and weighting factors.")
    if shared:
        report.warn(f"{len(shared)} identifier(s) are used for more than one dataset in the "
                    "file; those datasets are stored under identifier plus name: "
                    + ", ".join(sorted(shared)[:10]))
    if duplicates:
        report.warn(f"{len(duplicates)} dataset(s) occur more than once with the same "
                    "identifier and name and were left out: "
                    + ", ".join(sorted(duplicates)[:10]))
    plain = (("non_numeric", "row(s) with text where a number is expected were left out"),
             ("empty", "dataset(s) without any EF 3.1 result were left out"),
             ("no_unit", "dataset(s) without a unit were left out"),
             ("blanks", "dataset(s) have empty cells in some categories, read as zero"),
             ("no_category", "dataset(s) have no category in the file"))
    for counter, text in plain:
        if counts[counter]:
            report.warn(f"{counts[counter]} {text}.")
    if counts["repaired"]:
        report.info(f"Broken characters were repaired in {counts['repaired']} name(s).")
    if counts["score_checked"]:
        if counts["score_off"]:
            report.warn(f"The file's EF single score differs from the sum of its categories "
                        f"for {counts['score_off']} of {counts['score_checked']} datasets.")
        else:
            report.info(f"Single score check passed for {counts['score_checked']} datasets.")
    for n, (category_index, _, tolerance) in enumerate(compare):
        name = ef31.CATEGORIES[category_index].name
        if compare_off[n]:
            report.warn(f"{name} differs by more than {tolerance:.0%} from the file's own "
                        f"reference column for {compare_off[n]} of {compare_checked[n]} datasets.")
        elif compare_checked[n]:
            report.info(f"{name} matches the file's own reference column for all "
                        f"{compare_checked[n]} comparable datasets.")
    return ParsedDatabase("process", path.name, file_hash(path), result, report)


def describe_headings(path, rows: int = 12, columns: int = 80) -> str:
    """The headings of a workbook without any of its numbers.

    Meant for sharing when a file is not recognised: it stops at the first row
    with numbers, so it shows the layout but no data.
    """
    lines = []
    for sheet in sheet_names(path):
        lines.append(f"Sheet '{sheet}'")
        for r, row in enumerate(iter_rows(path, sheet, max_rows=rows), start=1):
            numbers = sum(1 for v in row if (n := as_number(v)) is not None and not math.isnan(n))
            if numbers >= 3:
                break                                  # data starts here
            texts = [f"{c + 1}:{' '.join(v.split())[:40]}" for c, v in enumerate(row[:columns])
                     if isinstance(v, str) and v.strip() and math.isnan(as_number(v))]
            if texts:
                lines.append(f"  row {r}: " + " | ".join(texts))
    return "\n".join(lines)
