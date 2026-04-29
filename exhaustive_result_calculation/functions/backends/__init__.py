import os
from pathlib import Path
from typing import Callable

_BACKENDS = ("openlca", "brightway")


def get_backend(name: str | None = None) -> Callable[[Path, Path], None]:
    """Return the extract_lca_data function for the requested backend.

    Resolution order: explicit ``name`` argument → ``LCA_BACKEND`` env var → "openlca".
    """
    backend_name = name or os.environ.get("LCA_BACKEND", "openlca")
    if backend_name == "openlca":
        from .openlca import extract_lca_data
        return extract_lca_data
    if backend_name == "brightway":
        from .brightway import extract_lca_data
        return extract_lca_data
    raise ValueError(
        f"Unknown LCA backend: {backend_name!r}. "
        f"Valid options: {', '.join(_BACKENDS)}"
    )
