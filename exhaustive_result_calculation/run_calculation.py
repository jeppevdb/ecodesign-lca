import os
import pandas as pd
from pathlib import Path

from exhaustive_result_calculation.functions.extract_cutoff import extract_cutoff
from exhaustive_result_calculation.functions.generate_all_lcis import generate_all_lcis
from exhaustive_result_calculation.functions.backends import get_backend
from exhaustive_result_calculation.functions.extract_metadata import extract_metadata
from exhaustive_result_calculation.functions.generate_lci_input_combinations import generate_lci_input_combinations

def main(lci_file: Path, out_dir: Path, backend: str | None = None):
    # Extract metadata
    extract_metadata(lci_file, out_dir)

    # Extract LCA data via the selected backend (env LCA_BACKEND or explicit argument)
    get_backend(backend)(lci_file, out_dir)

    # Load standardized LCI
    lci_df = pd.read_excel(lci_file)

    # Process LCI
    lci_df = extract_cutoff(lci_df, out_dir)
    combinations_scen, combinations_par = generate_lci_input_combinations(lci_file)
    results_by_parameter, results_by_scenario = generate_all_lcis(
        combinations_scen, combinations_par, lci_df, lci_file
    )

    # Save outputs into processed_data/product_name/
    results_by_scenario.to_csv(out_dir / "all_results_by_scenario.csv", index=False)
    results_by_parameter.to_csv(out_dir / "all_results_by_parameter_base_design.csv", index=False)

    results_by_scenario_base = results_by_scenario[
        results_by_scenario["design_variation_type"] == "base_design"
    ]
    results_by_scenario_base.to_csv(out_dir / "all_results_by_scenario_base_design.csv", index=False)

    print(f"Results saved to {out_dir}")
