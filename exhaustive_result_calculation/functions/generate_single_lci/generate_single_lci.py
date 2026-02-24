# Example usage within generate_single_lci
def generate_single_lci(variation, lci_df, lci_file, by_parameter=bool):
    """
    Generates a single LCI dataset for a given product configuration.
    Args:
        variation (dict): Dictionary containing the selected design variation, scenario setting, and country.
        lci_df (pd.DataFrame): The full LCI dataset.
    Returns:
        pd.DataFrame: Filtered LCI dataset for the selected configuration.
    """
    import pandas as pd 
    from exhaustive_result_calculation.functions.generate_single_lci.apply_scenario_values import apply_scenario_values
    from exhaustive_result_calculation.functions.generate_single_lci.calculate_distribution import calculate_distribution
    from exhaustive_result_calculation.functions.generate_single_lci.calculate_endoflife import calculate_endoflife
    from exhaustive_result_calculation.functions.generate_single_lci.remove_empty_rows import remove_empty_rows
    from exhaustive_result_calculation.functions.generate_single_lci.calculate_impacts import calculate_impacts
    from exhaustive_result_calculation.functions.generate_single_lci.select_product_configuration import select_product_configuration
    from exhaustive_result_calculation.functions.generate_single_lci.select_countries import select_countries

    lci_df_post_country = select_countries(variation, lci_df)

    lci_df_non_production = lci_df_post_country.copy()
    lci_df_non_production = lci_df_non_production[lci_df_non_production["variation_area"]!="production"]

    # select product configuration
    lci_df_post_design = select_product_configuration(variation, lci_df_post_country)


    # Cconcatenate the two dataframes
    filtered_lci_df = pd.concat([lci_df_post_design, lci_df_non_production])

    # apply scenario values
    filtered_lci_df_post_scenarios = apply_scenario_values(variation, filtered_lci_df, lci_file, by_parameter)

    # calculate distribution
    filtered_lci_df_post_transport = calculate_distribution(filtered_lci_df_post_scenarios)

    # add End-of-Life processes
    filtered_lci_df_post_eol = calculate_endoflife(filtered_lci_df_post_transport)

    # remove empty rows
    final_results_df = remove_empty_rows(filtered_lci_df_post_eol)

    # add impact factors
    final_results_df_with_impacts = calculate_impacts(final_results_df, lci_file)
    return final_results_df_with_impacts

