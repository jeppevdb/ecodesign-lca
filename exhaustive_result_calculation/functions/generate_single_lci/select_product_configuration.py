def select_product_configuration(variation, lci_df):
    """
    Selects the LCI data for a specific design variation dict:
      variation["design_variation"] must be a dict with keys
        level      ∈ {"system","assembly","component"}
        system     str
        assembly   str or None
        component  str or None
        variation  int

    Args:
        variation (dict): must contain key "design_variation" → dict as above.
        lci_df (pd.DataFrame): must have columns
            "system", "system_variation_number",
            "assembly", "assembly_variation_number",
            "component", "component_variation_number"

    Returns:
        pd.DataFrame: filtered to exactly the rows for that product configuration.
    """
    import pandas as pd

    dv = variation["design_variation"]
    level      = dv["level"]
    target_sys = dv["system"]
    target_asm = dv["assembly"]
    target_cmp = dv["component"]
    target_var = dv["variation"]

    df = lci_df.copy()
    df = df[df["variation_area"] == "production"]
    
    # 1) SYSTEM‐LEVEL
    if level == "system":
        df = df[df["system_variation_number"] == target_var]
        df = df[df["assembly_variation_number"] == 0]
        df = df[df["component_variation_number"] == 0]

        return df
        
    # 2) ASSEMBLY‐LEVEL
    if level == "assembly":
        df = df[df["system_variation_number"] == 0]
        df_targeted_assembly = df[df["assembly"] == target_asm]
        df_targeted_assembly = df_targeted_assembly[df_targeted_assembly["assembly_variation_number"] == target_var]    
        df_other_assemblies = df[df["assembly"] != target_asm]
        df_other_assemblies = df_other_assemblies[df_other_assemblies["assembly_variation_number"] == 0]
        df_assembly_level = pd.concat([df_targeted_assembly, df_other_assemblies], ignore_index=True)
        return df_assembly_level
    # 3) COMPONENT‐LEVEL
    if level == "component":
        df = df[df["system_variation_number"] == 0]
        df = df[df["assembly_variation_number"] == 0]
        df_targeted_component = df[df["component"] == target_cmp]
        df_targeted_component = df_targeted_component[df_targeted_component["component_variation_number"] == target_var]    
        df_other_components = df[df["component"] != target_cmp]
        df_other_components = df_other_components[df_other_components["component_variation_number"] == 0]
        df_component_level = pd.concat([df_targeted_component, df_other_components], ignore_index=True)
        return df_component_level


