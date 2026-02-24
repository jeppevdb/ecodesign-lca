import panel as pn


from impact_report_generation.src.utils.loaders import design_scenario_df

def build():
    """
    Assemble the component‐redesigns subtabs:
      - Introduction (global selector + text)
      - Redesign Stacks (stacked bars vs. base)
    """
    df=design_scenario_df()
    df_comp = df[df["design_variation_level"] == "component"]

    # extract assemblies if any exist
    comp_count = df_comp["design_variation_index"].dropna().unique().tolist()

    # If no assemblies exist, show a message and return early
    if not comp_count:
        return pn.pane.Markdown(
            "No component design scenarios were modelled yet.",
            margin=(10, 10, 10, 10),
            styles={"color": "red"}
        )
    else:
        from .generate_intro   import build as _sec1
        from .generate_summary_table import build as _sec2
        from .generate_stacked_bars import build as _sec3
        from .generate_lifecycle_stage_bars import build as _sec4
        from .generate_radar_chart import build as _sec5
        from .generate_sunburst import build as _sec6
        return pn.Tabs(
            ("Introduction",    _sec1()),
            ("Summary table", _sec2()), 
            ("Redesign Stacks", _sec3()),
            ("Lifecycle bars", _sec4()),
            ("Radar charts", _sec5()),
            ("Sunburst", _sec6()),
            dynamic=True
        )