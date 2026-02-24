import pandas as pd
import panel as pn

def extract_cutoff(lci_df, out_dir):
    """
    Extracts and removes cut-off processes from the LCI dataframe,
    and returns a Panel pane for clean display in a report.

    Parameters:
    -----------
    lci_df : pd.DataFrame
        The full LCI dataframe, including a 'Cut-off' column indicating excluded processes.

    Returns:
    --------
    filtered_df : pd.DataFrame
        The original dataframe with cut-off rows removed.

    cutoff_table_pane : pn.pane.DataFrame or pn.pane.Markdown
        A Panel pane that shows the excluded processes in a clean format,
        suitable for direct use in a Holoviews/Panel report.
    """
    columns_to_keep = [
        "system", "system_variation_number", "variation_area",
        "assembly", "assembly_variation_number", "component", "component_variation_number",
        "distribution_pathway", "eol_pathway", "component_cost", "component_weight",
        "process_description", "cutoff", "lifecycle_stage",
        "database_name", "uncertainty_score", "database_datatype",
        "database_origin", "database_uuid", "process_amount", "unit",
        "parameter_codes", "country", "design_variation_description"
    ]
    # Step 1: Identify excluded (cut-off) rows
    cutoff_mask = lci_df["cutoff"] == True
    cutoff_df = lci_df.loc[cutoff_mask, [
        "system",
        "system_variation_number",
        "assembly",
        "assembly_variation_number",
        "component",
        "component_variation_number",
        "process_description",
        "lifecycle_stage"
    ]]
    print(cutoff_df)
    cutoff_df.to_excel(out_dir / "cutoff_df.xlsx", index=False)
    filtered_df = lci_df[lci_df["cutoff"] != True].reset_index(drop=True)

    filtered_df = filtered_df = filtered_df[columns_to_keep]


    return filtered_df #, cutoff_table_pane
