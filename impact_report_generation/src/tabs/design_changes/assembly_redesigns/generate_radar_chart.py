import pandas as pd
import panel as pn
import plotly.graph_objects as go
from panel import pane, widgets, Row, Column

from impact_report_generation.src.utils.loaders import design_scenario_df
from impact_report_generation.src.tabs.design_changes.assembly_redesigns.generate_intro import global_assembly_sel
from impact_report_generation.src.utils.selectors import scenario_selector, country_selector, get_characterized_impact_cats, local_design_assembly_selector

pn.extension("plotly")

def build():
    # 1) Load & filter to base + assembly‐level redesigns
    df = design_scenario_df()
    
    df_base = df[df["design_variation_type"]  == "base_design"]
    df_vars = df[df["design_variation_level"] == "assembly"]


    # 2) assembly & scenario/country selectors
    local_assy = local_design_assembly_selector()
    global_assembly_sel.param.watch(
        lambda ev: setattr(local_assy, "value", "Use global selection"), "value"
    )
    global_display = pn.bind(
    lambda v: pane.Markdown(f"**Globally selected assembly:** {v}", margin=(8,10,0,0)),
    global_assembly_sel
    )

    scenario_sel = scenario_selector()
    country_sel = country_selector()

    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel=local_assy,
        scenario=scenario_sel,
        country=country_sel
    )
    def view(global_sel, local_sel, scenario, country):
        assy = global_sel if local_sel == "Use global selection" else local_sel
        # create separate base and variations sub dfs
        sub_base = df_base.query(
            "assembly == @assy and scenario_setting == @scenario and country == @country"
        )
        sub_vars = df_vars.query(
        "assembly == @assy and design_variation_assembly==@assy and scenario_setting == @scenario and country == @country"
        )
        # concatenate them back together
        sub=pd.concat([sub_base, sub_vars], ignore_index=True)       

        # cast variation and pull out impact columns + description
        sub = sub.assign(
            variation=sub["design_variation_variation"].astype(int),
            description=sub["design_variation_description"]
        )
        # get a list of characterized impact columns
        impact_cats = get_characterized_impact_cats()

        # aggregate sums for each (variation, description)
        agg = (
            sub
            .groupby(["variation", "description"])[impact_cats]
            .sum()
            .reset_index()
        )

        # get the base‐case totals (we assume exactly one row where variation == 0)
        base_totals = agg.loc[agg["variation"] == 0, impact_cats].iloc[0]

        # compute % of base for every row
        pct = agg.copy()
        for cat in impact_cats:
            pct[cat] = pct[cat] / base_totals[cat] * 100
        pct = pct.fillna(0)

        max_pct = pct[impact_cats].values.max()

        # remove prefixes
        clean_cats = [cat.replace("Characterized -", "") for cat in impact_cats]
        # close the loop
        theta = clean_cats + [clean_cats[0]]
        # build the Plotly radar
        fig = go.Figure()
        for _, row in pct.iterrows():
            r = row[impact_cats].tolist() + [row[impact_cats].iloc[0]]
            var = row["variation"]
            desc = row["description"]
            name = f"{desc} ({'Base' if var == 0 else f'Var {var}'})"
            fig.add_trace(go.Scatterpolar(
                r=r,
                theta=theta,
                fill="toself",
                mode="lines+markers",
                name=name,
                hovertemplate=[
                    f"<b>{cat}</b>: {row[cat]:.1f}% of base<br>"
                    for cat in impact_cats
                ] + [""]  # last element for the loop‐closing point
            ))

        fig.update_layout(
            title=f"<b>-           Total impacts per characterized impact category (% of base design) - Scenario: {scenario} - Country: {country}</b>",
            polar=dict(
                radialaxis=dict(range=[0, max_pct * 1.05], tickformat=".0f", visible=True)
            ),
            title_font=dict(size=20),           # title text size
            legend=dict(title="Variation", font=dict(size=20)),    # legend entry text size
            font=dict(size=20), 
            margin=dict(t=100, b=50, l=0, r=0),
            # legend=dict(title="Variation")
        )

        return pane.Plotly(fig, config={"displayModeBar": True}, height= 600, sizing_mode="stretch_width")
    
    # 5) Layout
    header   = pane.Markdown("### assembly‐Level Impact Radar")
    controls = pn.Row(
        global_display,
        local_assy,
        scenario_sel,
        country_sel,
        sizing_mode="stretch_width"
    )

    return Column(header, controls, view, sizing_mode="stretch_both")
