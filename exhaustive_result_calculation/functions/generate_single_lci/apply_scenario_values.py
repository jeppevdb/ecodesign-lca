import pandas as pd
import ast

def apply_scenario_values(variation,
                          filtered_lci_df,
                          lci_file,
                          by_parameter):
    """
    Applies scenario scaling factors to the filtered LCI df via nested loops.

    Args:
        variation (dict):
            - must include "Scenario Setting": "best"/"average"/"worst"
            - if by_parameter=True, must also include "Selected scenario"
        filtered_lci_df (pd.DataFrame): LCI data after product configuration
        lci_file (str): path to Excel file with sheet "scenarios"
        by_parameter (bool):
            - False => apply the chosen setting to every scenario row
            - True  => apply "average" to all scenario rows except the one
                       whose 'scenario' matches variation["Selected scenario"]

    Returns:
        pd.DataFrame: with in-place scaling of each scenario’s affected columns.
    """
    # load and prepare the scenarios sheet
    scen_df = pd.read_excel(lci_file, sheet_name="scenarios")
    # strip quotes from parameter_code and parse columns_affected
    scen_df["parameter_code"] = scen_df["parameter_code"].astype(str).str.strip('"')
    scen_df["columns_affected"] = scen_df["columns_affected"].apply(ast.literal_eval)
    # convert comma-numbers to floats
    for lvl in ("best", "average", "worst"):
        scen_df[lvl] = (
            scen_df[lvl]
            .astype(str).str.replace(",", ".")
            .astype(float)
        )

    scenario_setting      = variation["scenario_setting"]
    selected_scenario = variation.get("selected_parameter")

    # copy and parse the LCI df
    df = filtered_lci_df.copy()
    df["parameter_codes"] = df["parameter_codes"].apply(
        lambda x: ast.literal_eval(x) if isinstance(x, str) and x.strip().startswith("[") else x
    )

    # ensure all affected columns exist and are numeric
    all_cols = set().union(*scen_df["columns_affected"])
    for col in all_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # eested loops: scenario-row → each df-row
    for _, scen in scen_df.iterrows():
        code_key      = scen["parameter_code"]     # e.g. "steel_recycling_rate"
        affected_cols = scen["columns_affected"]   # e.g. ["process amount"]

        # pick factor
        if by_parameter:
            if scen["scenario"] == selected_scenario:
                factor = scen[scenario_setting]
            else:
                factor = scen["average"]
        else:
            factor = scen[scenario_setting]

        # skip if missing
        if pd.isna(factor):
            continue

        # for each row in df, check presence and apply
        for idx, row in df.iterrows():
            codes = row["parameter_codes"]
            if not isinstance(codes, (list, tuple)):
                continue
            if code_key not in codes:
                continue

            # apply factor to each listed column
            for col in affected_cols:
                if col in df.columns:
                    df.at[idx, col] *= factor

    return df



