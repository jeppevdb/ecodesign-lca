import holoviews as hv
import pandas as pd
import panel as pn
from panel import pane, widgets, Row, Column
from holoviews import opts

#  loader with the design_variation_* columns
from impact_report_generation.src.utils.loaders import design_scenario_df
# shared “master” assembly selector
from impact_report_generation.src.tabs.design_changes.assembly_redesigns.generate_intro import global_assembly_sel
from impact_report_generation.src.utils.selectors import get_scenarios, get_countries, characterized_impact_selector_with_score, impact_unit_label, local_design_assembly_selector

hv.extension("bokeh")
pn.extension()

def build():
    # 1) Load & filter to base + assembly‐level redesigns
    df = design_scenario_df()
    df_base = df[df["design_variation_type"] == "base_design"]
    df_vars = df[df["design_variation_level"]== "assembly"]
    df_assy = pd.concat([df_base, df_vars], ignore_index=True)



    # 3) Widgets: local override + impact metric
    local_assy = local_design_assembly_selector()
    # whenever the global selector changes, reset the local
    global_assembly_sel.param.watch(
        lambda ev: setattr(local_assy, "value", "Use global selection"),
        "value"
    )
    global_display = pn.bind(
    lambda v: pane.Markdown(f"**Globally selected assembly:** {v}", margin=(8,10,0,0)),
    global_assembly_sel
    )

    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)

    # 4) Prepare static lists
    scenarios = get_scenarios()
    countries = get_countries()
    
    # 5) Build the reactive view
    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel=local_assy,
        impact=impact_sel
    )

    def view(global_sel, local_sel, impact):
        assy = global_sel if local_sel == "Use global selection" else local_sel
        # df_co = df_assy[df_assy["design_variation_assembly"] == assy]
        df_c = df_assy[(df_assy["assembly"] == assy)]
        rows = []
        for country in countries:
            charts = []
            df_ct = df_c[df_c["country"] == country]

            for scen in scenarios:
                # 1) slice base & variants
                base = df_ct[
                    (df_ct.design_variation_type == "base_design") &
                    # (df_ct.assembly == assy) &
                    (df_ct.scenario_setting     == scen)
                ].copy()
                var  = df_ct[
                    (df_ct.design_variation_type != "base_design") &
                    # (df_ct.assembly == assy) &
                    (df_ct.design_variation_assembly == assy) &
                    (df_ct.scenario_setting     == scen)
                ].copy()

                # 2) tag variation numbers
                base["variation"] = 0
                var["variation"]  = var["design_variation_variation"].astype(int)
                # 3) aggregate each
                agg_base = (
                    base
                    .groupby(["variation","component"])[impact]
                    .sum()
                    .reset_index()
                )
                agg_var = (
                    var
                    .groupby(["variation","component"])[impact]
                    .sum()
                    .reset_index()
                )
                desc_map = pd.concat([base, var], ignore_index=True)[[
                    "variation", "design_variation_description"
                ]].drop_duplicates(subset="variation").set_index("variation")


                # 4) glue together & enforce order
                agg = pd.concat([agg_base, agg_var], ignore_index=True)
                agg["description"] = agg["variation"].map(desc_map["design_variation_description"])

                vars = sorted(agg["variation"].unique())
                # agg["variation"] = pd.Categorical(agg["variation"],
                #                                 categories=var_order,
                #                                 ordered=True)

                # 5) build the stacked‐by‐process bar chart
                bars = hv.Bars(
                    agg,
                    kdims=["variation","component"],
                    vdims=[impact, "description"]
                ).opts(
                    opts.Bars(
                        stacked=True,
                        width=350,
                        height=350,
                        xrotation=45,
                        title=f"{scen.capitalize()} — {country}",
                        tools=["hover"],
                        bar_width = 0.5,
                        framewise=True,
                        ylim=(0, None),
                        xlabel="Variation number",
                        xticks=[(v, str(v)) for v in vars],
                        ylabel=impact,
                        show_legend=False,
                        hover_tooltips=[
                            ("Variation", "@variation"),
                            ("Description", "@description"),
                            ("Component", "@component"),
                            (impact, f"@{impact}")
                        ]
                    )
                )
                charts.append(bars)

            rows.append(Row(*charts, sizing_mode="stretch_width"))

        return Column(*rows, sizing_mode="stretch_both")
    

    # 6) Wrap it up
    header   = pane.Markdown("## Assembly-Level Redesign Stacks")
    controls = pn.Row(  
                    global_display,
                    local_assy,
                    impact_sel,
                    unit_label,
                    sizing_mode="stretch_width"
                    )
    view_pane = pn.panel(view, linked_axes=False)

    return Column(
        header,
        controls,
        view_pane,
        sizing_mode="stretch_width"
    )
