# def generate_all_lcis(combinations_scen, combinations_par, lci_df, lci_file):
def generate_all_lcis(combinations_scen, combinations_par, lci_df, lci_file):
    """
    Generates all LCI datasets for all combinations of scenarios and parameters.
    Adds a design_variation_index column: 0 for base designs (variation==0),
    1,2,3… for each unique non-zero design variation.
    Returns two pandas.DataFrame objects: 
      (results_by_parameter, results_by_scenario).
    """
    import pandas as pd
    import itertools
    from exhaustive_result_calculation.functions.generate_single_lci.generate_single_lci import generate_single_lci

    # build design_variation_index lookup 
    variation_index_map = {}
    next_idx = 1
    # go through every variation dict once (scenarios + parameters)
    for combo in itertools.chain(combinations_scen, combinations_par):
        dv = combo["design_variation"]
        key = (
            dv.get("level"),
            dv.get("system"),
            dv.get("assembly"),
            dv.get("component"),
            dv.get("variation"),
        )
        if key not in variation_index_map:
            if dv.get("variation") == 0:
                variation_index_map[key] = 0
            else:
                variation_index_map[key] = next_idx
                next_idx += 1

    def _tag_variation_columns(df, variation_dict):
        # unpack the design_variation dict into columns
        for key in ("level", "system", "assembly", "component", "variation"):
            df[f"design_variation_{key}"] = variation_dict.get(key)
        # compute base vs. alternative
        is_base = (variation_dict.get("level") == "system"
                   and variation_dict.get("variation") == 0)
        df["design_variation_type"] = "base_design" if is_base else "alternative_design"
        return df

    if not combinations_scen:
        raise ValueError("combinations_scen is empty—nothing to generate for scenarios!")
    if not combinations_par:
        raise ValueError("combinations_par is empty—nothing to generate for parameters!")

    # scenario lcis
    results_by_scenario = []
    for idx, variation in enumerate(combinations_scen, start=1):
        df = generate_single_lci(variation, lci_df, lci_file, by_parameter=False)
        df["lci_combination_index"] = idx
        df["scenario_setting"]    = variation["scenario_setting"]
        df["country"]             = variation["country"]
        df = _tag_variation_columns(df, variation["design_variation"])

        dv = variation["design_variation"]
        key = (
            dv.get("level"),
            dv.get("system"),
            dv.get("assembly"),
            dv.get("component"),
            dv.get("variation"),
        )
        df["design_variation_index"] = variation_index_map[key]

        results_by_scenario.append(df)
        print(f"Generated scenario #{idx}: {variation}")

    df_scen = pd.concat(results_by_scenario, ignore_index=True)

    # parameter-based lcis
    results_by_parameter = []
    for idx, variation in enumerate(combinations_par, start=1):
        df = generate_single_lci(variation, lci_df, lci_file, by_parameter=True)
        df["lci_combination_index"] = idx
        df["scenario_setting"]    = variation["scenario_setting"]
        df["selected_parameter"]   = variation["selected_parameter"]
        df["country"]             = variation["country"]
        df = _tag_variation_columns(df, variation["design_variation"])

        dv = variation["design_variation"]
        key = (
            dv.get("level"),
            dv.get("system"),
            dv.get("assembly"),
            dv.get("component"),
            dv.get("variation"),
        )
        df["design_variation_index"] = variation_index_map[key]

        results_by_parameter.append(df)
        print(f"Generated parameter #{idx}: {variation}")

    df_par = pd.concat(results_by_parameter, ignore_index=True)

    return df_par, df_scen

