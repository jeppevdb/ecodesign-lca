from typing import Protocol
from pathlib import Path


class LCABackend(Protocol):
    def __call__(self, lci_file_path: Path, out_dir: Path) -> None: ...
