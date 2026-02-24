def select_countries(variation, lci_df):
    """
    Filters the LCI dataset to:
    Keep only lifecycle stage rows relevant to the selected country.

    Args:
        df (pd.DataFrame): The full LCI DataFrame.
        country (str): Country filter for Use stage, Distribution, and End-of-Life .

    Returns:
        pd.DataFrame: LCI DataFrame filtered for the selected country.
    """
    # # extract the selected country variation from the JSON entry
    country_variation = variation["country"]

    # build a mask that’s True if country is NaN, empty, or matches country_variation
    mask = (
        lci_df["country"].isna()
        | (lci_df["country"] == "")
        | (lci_df["country"] == country_variation)
    )

    lci_df_post_country = lci_df[mask].copy()

    return lci_df_post_country

