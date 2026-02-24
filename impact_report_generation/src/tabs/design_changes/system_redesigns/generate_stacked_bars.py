import holoviews as hv
import pandas as pd
import panel as pn
from panel import pane, widgets, Row, Column
from holoviews import opts

from impact_report_generation.src.utils.loaders import design_scenario_df
# shared “master” assembly selector
from impact_report_generation.src.tabs.design_changes.assembly_redesigns.generate_intro import global_assembly_sel

hv.extension("bokeh")
pn.extension()

def build():
    # 1) Load & filter to base + assembly‐level redesigns
    df = design_scenario_df()
    mask = (
        (df["design_variation_type"]  == "base_design") |
        (df["design_variation_level"] == "assembly")
    )
    df_assembly = df.loc[mask].copy()

    # 2) Create a unified “variation” column: 0 = base, else variation number
    df_assembly["variation"] = df_assembly.apply(
        lambda r: 0 if r.design_variation_type == "base_design"
                  else int(r.design_variation_variation),
        axis=1
    )

    # 3) Widgets: local override + impact metric
    assembly = df['design_variation_assembly'].unique().tolist()
    local_assembly = widgets.Select(
        name="Local assembly override",
        options=["Use Global"] + assembly,
        value="Use Global"
    )
    # whenever the global selector changes, reset the local
    global_assembly_sel.param.watch(
        lambda ev: setattr(local_assembly, "value", "Use Global"),
        "value"
    )

    impact_sel = widgets.Select(
        name="Impact metric",
        options=["single_score", "uncertainty_score"],
        value="single_score"
    )

    # 4) Prepare static lists
    scenarios = ["average", "best", "worst"]
    countries = sorted(df_assembly["country"].unique())

    # 5) Build the reactive view
    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel=local_assembly,
        impact=impact_sel
    )
    def view(global_sel, local_sel, impact):
        assembly = global_sel if local_sel == "Use Global" else local_sel
        df_c = df_assembly[df_assembly["assembly"] == assembly]
        rows = []

        for country in countries:
            charts = []
            df_ct = df_c[df_c["country"] == country]

            for scen in scenarios:
                sub = df_ct[df_ct["scenario_setting"] == scen]
                # aggregate by variation & component
                agg = (
                    sub
                      .groupby(["variation","component"])[impact]
                      .sum()
                      .reset_index()
                )
                # order variation bars by variation id
                var_order = sorted(agg["variation"].unique())
                agg["variation"] = pd.Categorical(
                    agg["variation"], var_order, ordered=True
                )

                # dynamic width: 200px per variation
                width = max(400, 100 * len(var_order))

                bars = hv.Bars(
                    agg,
                    kdims=["variation","component"],
                    vdims=[impact]
                ).opts(
                    opts.Bars(
                        stacked=True,
                        width=width,
                        height=350,
                        xrotation=45,
                        title=f"{scen.capitalize()} / {country}",
                        tools=["hover"],
                        framewise=True,
                        ylim=(0, None),
                        xlabel="Variation",
                        ylabel=impact,
                        show_legend=False
                    )
                )
                charts.append(bars)

            # pack the three scenario‐charts into one row
            rows.append(Row(*charts, sizing_mode="stretch_width"))

        return Column(*rows, sizing_mode="stretch_both")

    # 6) Wrap it up
    header   = pane.Markdown("## assembly-Level Redesign Stacks")
    controls = pn.Row(
        pn.Column(pane.Markdown("#### Override assembly"), local_assembly),
        impact_sel,
        sizing_mode="stretch_width"
    )
    view_pane = pn.panel(view, linked_axes=False)

    return Column(
        header,
        controls,
        view_pane,
        sizing_mode="stretch_width"
    )
