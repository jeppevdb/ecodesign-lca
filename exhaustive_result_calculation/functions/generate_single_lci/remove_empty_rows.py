def remove_empty_rows(filtered_lci_df_post_eol):
    """
    Removes the original Distribution and End-of-Life rows from the LCI dataset.

    Args:
        lci_df (pd.DataFrame): The LCI dataset with added transport and EoL processes.

    Returns:
        pd.DataFrame: Updated LCI dataset without the original Distribution and EoL rows.
    """
    # filter out the original distribution and eol rows
    final_results_df = filtered_lci_df_post_eol.copy()
    final_results_df = final_results_df[~filtered_lci_df_post_eol["variation_area"].isin(["distribution", "end_of_life"])].reset_index(drop=True)
    return final_results_df


