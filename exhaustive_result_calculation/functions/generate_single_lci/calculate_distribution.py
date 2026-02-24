import pandas as pd

def calculate_distribution(filtered_lci_df_post_scenarios):
    """
    Adds transport processes to each unique component in the LCI dataset by distributing 
    transport impacts proportionally to component weights.

    Args:
        lci_df (pd.DataFrame): The LCI dataset.

    Returns:
        pd.DataFrame: Updated LCI dataset with transport processes added for each component.
    """
    filtered_lci_df_post_transport = filtered_lci_df_post_scenarios.copy()

    # extract transport rows from Distribution stage
    distribution_rows = filtered_lci_df_post_scenarios[filtered_lci_df_post_scenarios["variation_area"] == "distribution"]

    # identify unique components from Production stage
    unique_components = filtered_lci_df_post_scenarios[filtered_lci_df_post_scenarios["variation_area"] == "production"].drop_duplicates(
        subset=["assembly", "component"]
    )

    # list to store new transport rows
    new_distribution_rows = []

    for _, component_row in unique_components.iterrows():
        print(component_row)

        distribution_pathway_value = component_row.get("distribution_pathway")
        if distribution_pathway_value is None:
            distribution_pathway = "Post-manufacturing distribution"
        else:
            distribution_pathway = component_row["distribution_pathway"]
        print(distribution_rows.columns)
        # find components that use this distribution pathway
        matching_distribution_rows = distribution_rows[
            (distribution_rows["distribution_pathway"] == distribution_pathway) |
            (distribution_rows["distribution_pathway"] == "Post-manufacturing distribution")
        ]
        print (matching_distribution_rows)
        # matching_distribution_rows = distribution_rows[distribution_rows["distribution_pathway"] == distribution_pathway]
        for _, distribution_row in matching_distribution_rows.iterrows():
            new_row = distribution_row.copy()

            # scale process_amount by component_weight (only once per component)
            new_row["process_amount"] *= component_row["component_weight"]

            # replace the first 10 columns with those from the component row
            new_row.iloc[:11] = component_row.iloc[:11]
            new_row["lifecycle_stage"] = "Distribution"
            # append to new transport rows list
            new_distribution_rows.append(new_row)
            print(new_row)
    # append new transport rows to the dataset
    filtered_lci_df_post_transport = pd.concat([filtered_lci_df_post_transport, pd.DataFrame(new_distribution_rows)], ignore_index=True)

    return filtered_lci_df_post_transport
