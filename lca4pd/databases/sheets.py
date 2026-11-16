"""Read rows from .xlsx and .ods workbooks through one interface.

Both formats are streamed, so large files (the EF 3.1 flow list is several
hundred MB once unpacked) do not have to fit in memory.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterator
from xml.etree.ElementTree import iterparse

_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_MAX_REPEAT = 1000   # trailing "repeat this empty cell/row 16000 times" markers are cut off


class UnsupportedFile(ValueError):
    pass


def sheet_names(path, stop_after: tuple[str, ...] = ()) -> list[str]:
    """Names of the sheets in a workbook.

    Listing the sheets of a large .ods file means reading through it, so
    ``stop_after`` ends the search as soon as all of those names were seen.
    """
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        workbook = openpyxl.load_workbook(path, read_only=True)
        try:
            return list(workbook.sheetnames)
        finally:
            workbook.close()
    if path.suffix.lower() == ".ods":
        names = []
        with zipfile.ZipFile(path) as archive, archive.open("content.xml") as content:
            for _, element in iterparse(content, events=("start",)):
                if element.tag == _TABLE + "table":
                    names.append(element.get(_TABLE + "name"))
                    if stop_after and set(stop_after) <= set(names):
                        break
                element.clear()
        return names
    raise UnsupportedFile(f"Only .xlsx and .ods files can be read, not '{path.suffix}'.")


def iter_rows(path, sheet: str, max_rows: int | None = None) -> Iterator[list]:
    """Yield the rows of one sheet as lists of cell values (``None`` for empty cells)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        rows = _xlsx_rows(path, sheet)
    elif suffix == ".ods":
        rows = _ods_rows(path, sheet)
    else:
        raise UnsupportedFile(f"Only .xlsx and .ods files can be read, not '{path.suffix}'.")
    pending_empty = 0   # empty rows are only passed on if data follows them
    index = 0
    for row in rows:
        if not any(cell is not None for cell in row):
            pending_empty += 1
            continue
        for emitted in [[]] * pending_empty + [row]:
            if max_rows is not None and index >= max_rows:
                return
            yield emitted
            index += 1
        pending_empty = 0


def _xlsx_rows(path: Path, sheet: str) -> Iterator[list]:
    import openpyxl
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for row in workbook[sheet].iter_rows(values_only=True):
            yield list(row)
    finally:
        workbook.close()


def _ods_cell(cell):
    value_type = cell.get(_OFFICE + "value-type")
    if value_type in ("float", "percentage", "currency"):
        return float(cell.get(_OFFICE + "value"))
    text = "\n".join("".join(paragraph.itertext()) for paragraph in cell.iter(_TEXT + "p"))
    return text if text else None


def _ods_rows(path: Path, sheet: str) -> Iterator[list]:
    with zipfile.ZipFile(path) as archive, archive.open("content.xml") as content:
        inside = False
        for event, element in iterparse(content, events=("start", "end")):
            if element.tag == _TABLE + "table":
                if event == "start":
                    inside = element.get(_TABLE + "name") == sheet
                else:
                    if inside:
                        return
                    element.clear()
            elif event == "end" and element.tag == _TABLE + "table-row":
                if inside:
                    row: list = []
                    for cell in element:
                        if not cell.tag.endswith("table-cell"):
                            continue
                        repeat = int(cell.get(_TABLE + "number-columns-repeated", "1"))
                        value = _ods_cell(cell)
                        row.extend([value] * (repeat if value is not None else min(repeat, _MAX_REPEAT)))
                    while row and row[-1] is None:
                        row.pop()
                    repeat_rows = int(element.get(_TABLE + "number-rows-repeated", "1"))
                    for _ in range(min(repeat_rows, _MAX_REPEAT) if not row else repeat_rows):
                        yield list(row)
                element.clear()
