import pandas as pd
import json
from pathlib import Path

def extract_metadata(lci_file_path: str, out_dir: Path) -> None:
    """
    Read metadata sheets and the standardized/process results sheets from the given LCI Excel file and:

      • Export each of these sheets as CSV:
          - country_variations.csv
          - scenario_descriptions.csv
          - system_info.csv
          - system_structure_and_costs.csv

      • Build a selectors dictionary from:
          - standardized_lci_data (countries, scenarios, assemblies/components)
          - process_results (impact‐category columns)

        and write it as selectors.json in the same folder.

    Parameters
    ----------
    lci_file_path : str
        Path to the Excel workbook containing all sheets.
    """
    # export metadata sheets as CSV
    metadata_sheets = [
        "country_variations",
        "scenarios",
        "system_info",
        "system_structure_and_costs",
        "design_change_descriptions",
    ]
    for sheet_name in metadata_sheets:
        try:
            df = pd.read_excel(lci_file_path, sheet_name=sheet_name)
        except ValueError:
            print(f"Warning: sheet '{sheet_name}' not found.")
            continue
        excel_path = out_dir / f"{sheet_name}.xlsx"
        df.to_excel(excel_path, index=False)
        print(f"Wrote '{sheet_name}' → {excel_path}")

    # build selectors dict
    # read standardized data and process results
    standardized_df = pd.read_excel(lci_file_path, sheet_name="standardized_lci_data")
    process_results_df = pd.read_excel(lci_file_path, sheet_name="process_results")

    # extract lists
    countries = sorted(standardized_df["country"].dropna().unique().tolist())
    scenarios = ["average", "best", "worst"]
    base_assemblies = sorted(standardized_df["assembly"].dropna().unique().tolist())
    base_components = sorted(standardized_df["component"].dropna().unique().tolist())
    altered_assemblies = sorted(
        standardized_df.loc[standardized_df["assembly_variation_number"] > 0, "assembly"]
        .dropna().unique().tolist()
    )
    altered_components = sorted(
        standardized_df.loc[standardized_df["component_variation_number"] > 0, "component"]
        .dropna().unique().tolist()
    )

    all_columns = process_results_df.columns.tolist()
    characterized_cats = sorted([c for c in all_columns if c.startswith("Characterized -")])
    normalized_and_weighted_cats = sorted([c for c in all_columns if c.startswith("Normalized &")])
    normalized_cats = sorted([c for c in all_columns if c.startswith("Normalized -")])
    single_score_cats = ["single_score"]

    selectors = {
        "countries": countries,
        "scenarios": scenarios,
        "base_assemblies": base_assemblies,
        "base_components": base_components,
        "altered_assemblies": altered_assemblies,
        "altered_components": altered_components,
        "characterized_impact_cats": characterized_cats,
        "normalized_impact_cats": normalized_cats,
        "normalized_and_weighted_impact_cats": normalized_and_weighted_cats,
        "single_score_cats": single_score_cats,
    }

    # write selectors to selectors.json
    selectors_path = out_dir / "selectors.json"
    with open(selectors_path, "w") as jf:
        json.dump(selectors, jf, indent=2)
    print(f"Wrote selectors → {selectors_path}")
