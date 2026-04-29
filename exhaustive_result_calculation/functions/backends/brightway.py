from pathlib import Path


def extract_lca_data(lci_file_path: Path, out_dir: Path) -> None:
    """
    Brightway backend for extracting LCA impact data.

    Contract (same as openlca backend):
      - Reads 'standardized_lci_data' and 'lcia_methods' sheets from lci_file_path
      - Writes/updates 'process_results' and 'elementary_flow_results' sheets in lci_file_path
      - Writes impact_units.json to out_dir

    Brightway does not require a running external server — all calculations happen
    within the Python environment using brightway2 / bw2calc.
    """
    raise NotImplementedError("Brightway backend is not yet implemented.")
