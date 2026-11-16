"""Import of user-supplied impact-factor files (see docs/design_2.0.md, step 1)."""

from pathlib import Path

from . import flows, link
from .library import Library
from .reader import (ImportReport, ParsedDatabase, Protocol, ProtocolMismatch, detect,
                     describe_headings, load_protocols, read_process_database)

__all__ = ["Library", "Protocol", "ProtocolMismatch", "ParsedDatabase", "ImportReport",
           "read_file", "detect_file", "load_protocols", "describe_headings", "link", "flows"]


def detect_file(path) -> list[str]:
    """Ids of the formats that can read ``path``."""
    if flows.is_flow_list(path):
        return [flows.PROTOCOL_ID]
    return detect(path)


def read_file(path, protocol_id: str | None = None) -> ParsedDatabase:
    """Read an uploaded file, recognising its format unless one is named."""
    checked = False
    if protocol_id is None:
        found = detect_file(path)
        if not found:
            raise ProtocolMismatch(
                "The file matches none of the known database formats: "
                + ", ".join(load_protocols()) + f", {flows.PROTOCOL_ID}.")
        protocol_id, checked = found[0], True
    if protocol_id == flows.PROTOCOL_ID:
        return flows.read_flow_list(path, _checked=checked)
    protocols = load_protocols()
    if protocol_id not in protocols:
        raise ProtocolMismatch(f"Unknown database format '{protocol_id}'.")
    return read_process_database(path, protocols[protocol_id])
