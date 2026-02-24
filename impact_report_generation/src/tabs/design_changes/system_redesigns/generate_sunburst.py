import panel as pn
import plotly.express as px
import pandas as pd
from panel import pane, widgets, Row, Column

from impact_report_generation.src.utils.loaders import design_scenario_df
from impact_report_generation.src.tabs.design_changes.assembly_redesigns.generate_intro import global_assembly_sel

pn.extension("plotly")

def build():
    # 1) Load & filter to base + assembly-level redesigns
    df = design_scenario_df()
    mask = (
        (df["design_variation_variation"] == 0) |
        (df["design_variation_level"]     == "assembly")
    )
    df_assembly = df.loc[mask].copy()
    df_assembly["variation"] = df_assembly["design_variation_variation"].astype(int)

    # 2) Widgets
    assemblies = df_assembly["design_variation_assembly"].dropna().unique().tolist()
    local_assembly = widgets.Select(
        name="Local assembly override",
        options=["Use Global"] + assemblies,
        value="Use Global"
    )
    global_assembly_sel.param.watch(
        lambda ev: setattr(local_assembly, "value", "Use Global"), "value"
    )

    impact_cats = ["single_score"] + [c for c in df_assembly.columns if c.startswith("characterized_")]
    impact_sel = widgets.Select(
        name="Impact category",
        options=impact_cats,
        value=impact_cats[0]
    )

    all_countries = sorted(df_assembly["country"].unique())
    country_sel = widgets.Select(
        name="Country",
        options=all_countries,
        value=all_countries[0]
    )

    scenarios = ["average", "best", "worst"]

    # 3) Reactive view: one row per variation, three sunbursts per row
    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel= local_assembly,
        impact_cat=impact_sel,
        country=   country_sel
    )
    def view(global_sel, local_sel, impact_cat, country):
        assembly = global_sel if local_sel == "Use Global" else local_sel
        df_c = df_assembly[df_assembly["assembly"] == assembly]
        rows = []

        for var in sorted(df_c["variation"].unique()):
            panes = []
            df_var = df_c[df_c["variation"] == var]
            for scen in scenarios:
                sub = df_var[
                    (df_var["scenario_setting"] == scen) &
                    (df_var["country"] == country)
                ]
                fig = px.sunburst(
                    sub,
                    path=["assembly", "component"],
                    values=impact_cat,
                    color="uncertainty_score",
                    range_color=[sub["uncertainty_score"].min(),
                                 sub["uncertainty_score"].max()],
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
                    pane.Markdown(f"### Variation {var}"),
                    Row(*panes, sizing_mode="stretch_width"),
                    sizing_mode="stretch_width"
                )
            )

        return Column(*rows, sizing_mode="stretch_both")

    # 4) Layout
    header = pane.Markdown("## assembly-Level Sunburst — by Scenario")
    controls = pn.Row(
        pn.Column(pane.Markdown("#### Override assembly"), local_assembly),
        country_sel,
        impact_sel,
        sizing_mode="stretch_width"
    )

    return Column(header, controls, view, sizing_mode="stretch_both")
