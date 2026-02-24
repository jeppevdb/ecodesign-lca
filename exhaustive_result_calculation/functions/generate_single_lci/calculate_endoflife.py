
import pandas as pd

def calculate_endoflife(filtered_lci_df_post_transport):
    """
    Adds End-of-Life (EoL) processes for each unique component based on its EoL material type.

    Args:
        lci_df (pd.DataFrame): The LCI dataset.

    Returns:
        pd.DataFrame: Updated LCI dataset with End-of-Life processes added for each component.
    """
    filtered_lci_df_post_eol = filtered_lci_df_post_transport.copy()

    # extract eol rows from the dataset
    eol_rows = filtered_lci_df_post_eol[filtered_lci_df_post_eol["variation_area"] == "end_of_life"]

    # identify unique components from Production stage
    unique_components = filtered_lci_df_post_eol[filtered_lci_df_post_eol["variation_area"] == "production"].drop_duplicates(
        subset=["assembly", "component"]
    )

    # list to store new EoL rows
    new_eol_rows = []

    for _, component_row in unique_components.iterrows():
        eol_material = component_row["eol_pathway"]

        # find EoL rows that match the component's material type
        matching_eol_rows = eol_rows[eol_rows["eol_pathway"] == eol_material]

        for _, eol_row in matching_eol_rows.iterrows():
            new_row = eol_row.copy()

            # scale process_amount by component weight (only once per component)
            new_row["process_amount"] *= component_row["component_weight"]

            # replace the first 8 columns with those from the component row
            new_row.iloc[:11] = component_row.iloc[:11]
            new_row["lifecycle_stage"] = "End-of-Life"
            # append to new EoL rows list
            new_eol_rows.append(new_row)
            print(new_row)
    # append new EoL rows to the dataset
    filtered_lci_df_post_eol = pd.concat([filtered_lci_df_post_eol, pd.DataFrame(new_eol_rows)], ignore_index=True)

    return filtered_lci_df_post_eol
