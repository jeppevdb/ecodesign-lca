import panel as pn
import plotly.express as px
import pandas as pd
from panel import pane, widgets, Row, Column

from impact_report_generation.src.utils.loaders import design_scenario_df
from impact_report_generation.src.tabs.design_changes.assembly_redesigns.generate_intro import global_assembly_sel
from impact_report_generation.src.utils.selectors import impact_unit_label, get_scenarios, characterized_impact_selector_with_score, country_selector, local_design_assembly_selector
pn.extension("plotly")

def build():
    # 1) Load & filter to base + assembly-level redesigns
    df = design_scenario_df()
    df_base = df[df["design_variation_type"]  == "base_design"]
    df_vars = df[df["design_variation_level"] == "assembly"]

    # 2) Widgets
    local_assy = local_design_assembly_selector()
    global_assembly_sel.param.watch(
        lambda ev: setattr(local_assy, "value", "Use global selection"), "value"
    )
    global_display = pn.bind(
    lambda v: pane.Markdown(f"**Globally selected assembly:** {v}", margin=(8,10,0,0)),
    global_assembly_sel
    )
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    country_sel = country_selector()
    scenarios = get_scenarios()

    # 3) Reactive view: one row per variation, three sunbursts per row
    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel= local_assy,
        impact_cat=impact_sel,
        country=   country_sel
    )
    def view(global_sel, local_sel, impact_cat, country):
        assy = global_sel if local_sel == "Use global selection" else local_sel
        sub_base = df_base.query(
        "assembly == @assy"
        )
        sub_vars = df_vars.query(
        "assembly == @assy and design_variation_assembly==@assy"
        )
        
        df_c = pd.concat([sub_base, sub_vars], ignore_index=True)
        df_c["variation"] = df_c["design_variation_variation"].astype(int)
        rows = []

        for var in sorted(df_c["variation"].unique()):
            panes = []
            df_var = df_c[df_c["variation"] == var]
            for scen in scenarios:
                sub = df_var[
                    (df_var["scenario_setting"] == scen) &
                    (df_var["country"] == country)
                ]
                description = sub["design_variation_description"].values[0]
                fig = px.sunburst(
                    sub,
                    path=["assembly", "component"],
                    values=impact_cat,
                    color="uncertainty_score",
                    range_color=[1,5],
                    color_continuous_scale=[(0,"green"),(0.5,"yellow"),(1,"red")],
                    title=f"{scen.capitalize()}"
                )
                fig.update_layout(
                    margin=dict(t=40,b=40,l=0,r=0),
                    height=300
                )
                panes.append(pane.Plotly(
                    fig,
                    config={"displayModeBar": False},
                    sizing_mode="stretch_width"
                ))

            rows.append(
                Column(
                    pane.Markdown(f"### {description}"),
                    Row(*panes, sizing_mode="stretch_width"),
                    sizing_mode="stretch_width"
                )
            )

        return Column(*rows, sizing_mode="stretch_both")

    # 4) Layout
    header = pane.Markdown("## assembly-Level Sunburst — by Scenario")
    controls1 = pn.Row(
        global_display,
        local_assy,
        country_sel,
        sizing_mode="stretch_width"
    )

    controls2 = pn.Row(
        impact_sel,
        unit_label,
        sizing_mode="stretch_width"
    )
    return Column(header, controls1, controls2, view, sizing_mode="stretch_both")
