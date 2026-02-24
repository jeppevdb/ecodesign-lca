import pandas as pd
import panel as pn
import plotly.graph_objects as go
from panel import pane, widgets, Row, Column

from impact_report_generation.src.utils.loaders import design_scenario_df
from impact_report_generation.src.tabs.design_changes.assembly_redesigns.generate_intro import global_assembly_sel

pn.extension("plotly")

def build():
    # 1) Load & filter to base + assembly‐level redesigns
    df = design_scenario_df()
    mask = (
        (df["design_variation_variation"]  == 0 ) |
        (df["design_variation_level"] == "assembly")
    )
    df_assembly = df.loc[mask].copy()

    # 2) assembly & scenario/country selectors
    assemblies = df_assembly["design_variation_assembly"].dropna().unique().tolist()
    local_assembly = widgets.Select(
        name="Local assembly override",
        options=["Use Global"] + assemblies,
        value="Use Global"
    )
    global_assembly_sel.param.watch(
        lambda ev: setattr(local_assembly, "value", "Use Global"), "value"
    )

    scenario_sel = widgets.Select(
        name="Scenario", options=["average","best","worst"], value="average"
    )
    country_sel = widgets.Select(
        name="Country",
        options=sorted(df_assembly["country"].unique()),
        value=sorted(df_assembly["country"].unique())[0]
    )

    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel=local_assembly,
        scenario=scenario_sel,
        country=country_sel
    )
    def view(global_sel, local_sel, scenario, country):
        assy = global_sel if local_sel == "Use Global" else local_sel
        sub = df_assembly.query(
            "assembly == @assy and scenario_setting == @scenario and country == @country"
        )
        # pull out only the characterized impact columns
        impact_cats = [c for c in sub.columns if c.startswith("characterized_")]

        # make sure variation ID is an int
        sub = sub.copy()
        sub["variation"] = sub["design_variation_variation"].astype(int)

        # 1) sum each impact category by variation
        grouped = (
            sub
            .groupby("variation")[impact_cats]
            .sum()
        )

        # 2) extract the base‐case totals (variation 0)
        if 0 in grouped.index:
            base = grouped.loc[0]
        else:
     
            raise KeyError(f"No variation 0 found for {assy}/{scenario}/{country}")

        # 3) compute % of base
        pct = grouped.div(base, axis=1) * 100
        pct = pct.fillna(0)   # in case base was zero in any category

        # 4) determine the maximum % for  radar scale
        max_pct = pct.values.max()        


        # 5) Close the loop on categories for the radar
        cats = impact_cats + [impact_cats[0]]

        # 6) Build the spider chart traces
        fig = go.Figure()
        for variation, row in pct.iterrows():
            r = row.tolist() + [row.iloc[0]]
            name = "Base (100%)" if variation == 0 else f"Var {variation}"
            fig.add_trace(go.Scatterpolar(
                r=r, theta=cats, fill="toself", mode="lines+markers", name=name
            ))

        # 7) Set radial axis to [0, max_pct*1.05]
        fig.update_layout(
            title=f"Impacts % of Base · {assy} / {scenario} / {country}",
            polar=dict(radialaxis=dict(range=[0, max_pct*1.05], tickformat=".0f", visible=True)),
            margin=dict(t=50, b=50, l=0, r=0),
            legend=dict(title="Variation")
        )

        return pane.Plotly(fig, config={"displayModeBar": False}, sizing_mode="stretch_width")
 
    # 5) Layout
    header   = pane.Markdown("### assembly‐Level Impact Radar")
    controls = pn.Row(
        pn.Column(pane.Markdown("#### Override assembly"), local_assembly),
        scenario_sel,
        country_sel,
        sizing_mode="stretch_width"
    )

    return Column(header, controls, view, sizing_mode="stretch_both")


