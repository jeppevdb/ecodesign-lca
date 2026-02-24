import pandas as pd
import itertools
import json

def generate_lci_input_combinations(lci_file,
                                    save_json=False,
                                    json_file_scen="lci_by_scenario.json",
                                    json_file_par="lci_by_parameter.json"):
    # load LCI base sheet
    lci_df = pd.read_excel(lci_file, sheet_name="standardized_lci_data")
    prod   = lci_df[lci_df["variation_area"] == "production"]

    # system‑level: include variation 0
    system_variations = []
    if "system_variation_number" in prod.columns:
        for system in prod["system"].unique():
            nums = (prod.loc[prod["system"] == system, 
                             "system_variation_number"]
                        .dropna().unique().tolist())
            for num in nums:
                system_variations.append({
                    "level":     "system",
                    "system":    system,
                    "assembly":  None,
                    "component": None,
                    "variation": int(num)
                })
    else:
        base = prod["system"].drop_duplicates().iloc[0]
        system_variations.append({
            "level":     "system",
            "system":    base,
            "assembly":  None,
            "component": None,
            "variation": 0
        })

    # assembly‑level: only variation > 0
    assembly_variations = []
    if "assembly_variation_number" in prod.columns:
        asm_df = (prod.loc[prod["assembly_variation_number"] > 0,
                          ["system","assembly","assembly_variation_number"]]
                     .drop_duplicates())
        for row in asm_df.itertuples(index=False):
            assembly_variations.append({
                "level":     "assembly",
                "system":    row.system,
                "assembly":  row.assembly,
                "component": None,
                "variation": int(row.assembly_variation_number)
            })

    # component‑level: only variation > 0
    component_variations = []
    if "component_variation_number" in prod.columns:
        comp_df = (prod.loc[prod["component_variation_number"] > 0,
                            ["system","assembly","component","component_variation_number"]]
                       .drop_duplicates())
        for row in comp_df.itertuples(index=False):
            component_variations.append({
                "level":     "component",
                "system":    row.system,
                "assembly":  row.assembly,
                "component": row.component,
                "variation": int(row.component_variation_number)
            })

    # combine all design‐variation dicts
    design_variations = (
        system_variations +
        assembly_variations +
        component_variations
    )

    # unique values in "country" column
    country_variations = lci_df["country"].dropna().unique().tolist()


    # scenario names
    scen_df = pd.read_excel(lci_file, sheet_name="scenarios")
    scenario_names = scen_df["scenario"].dropna().unique().tolist()

    # nuild output with nested design_variation
    settings = ["best", "average", "worst"]

    combinations_scen = [
        {
            "design_variation": dv,
            "scenario_setting": setting,
            "country":          country
        }
        for dv, setting, country in
        itertools.product(design_variations, settings, country_variations)
    ]
    
    # for now, only include base design variations for parameters
    # to change back, delete the lines below and change base_design_variations to design_variations in the itertools line
    base_design_variations = [
        dv for dv in design_variations
        if dv["level"] == "system" and dv["variation"] == 0
    ]
    combinations_par = [
        {
            "design_variation":    dv,
            "selected_parameter":   scen,
            "scenario_setting":    setting,
            "country":             country
        }
        for dv, scen, setting, country in
        itertools.product(base_design_variations, scenario_names, settings, country_variations)
    ]

    # 6) Save JSONs - not necessary for calculation, but useful for inspection
    if save_json:
        with open(json_file_scen, "w", encoding="utf-8") as f:
            json.dump(combinations_scen, f, indent=2)
        with open(json_file_par, "w", encoding="utf-8") as f:
            json.dump(combinations_par, f, indent=2)

    return combinations_scen, combinations_par
