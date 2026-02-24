import holoviews as hv
import pandas as pd
import panel as pn
from panel import pane, widgets, Row, Column
from holoviews import opts

from impact_report_generation.src.utils.loaders import design_scenario_df
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

    # unify variation ID: 0=base, else the integer variation number
    df_assembly["variation"] = df_assembly.apply(
        lambda r: 0 if r.design_variation_type == "base_design"
                  else int(r.design_variation_variation),
        axis=1
    )

    # 2) Widgets
    assemblies = df_assembly["design_variation_assembly"].unique().tolist()
    local_assembly = widgets.Select(
        name="Local assembly override",
        options=["Use Global"] + assemblies,
        value="Use Global"
    )
    # reset local whenever global changes
    global_assembly_sel.param.watch(
        lambda ev: setattr(local_assembly, "value", "Use Global"),
        "value"
    )

    scenario_sel = widgets.Select(
        name="Scenario",
        options=["average", "best", "worst"],
        value="average"
    )
    country_sel = widgets.Select(
        name="Country",
        options=sorted(df_assembly["country"].unique()),
        value=sorted(df_assembly["country"].unique())[0]
    )
    impact_sel = widgets.Select(
        name="Impact metric",
        options=["single_score", "uncertainty_score"],
        value="single_score"
    )

    # 3) Reactive view: one grouped‐bar chart
    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel= local_assembly,
        scenario= scenario_sel,
        country=  country_sel,
        impact=   impact_sel
    )
    def view(global_sel, local_sel, scenario, country, impact):
        # pick assembly (local override wins)
        assy = global_sel if local_sel == "Use Global" else local_sel
        sub = df_assembly.query(
            "assembly==@assy and scenario_setting==@scenario and country==@country"
        )

        # aggregate by lifecycle_stage & variation
        agg = (
            sub
             .groupby(["lifecycle_stage","variation"])[impact]
             .sum()
             .reset_index()
        )

        # preserve lifecycle_stage order as they appear
        ls_order = list(dict.fromkeys(agg["lifecycle_stage"]))
        agg["lifecycle_stage"] = pd.Categorical(
            agg["lifecycle_stage"], ls_order, ordered=True
        )

        # ensure variation IDs are sorted numerically
        var_order = sorted(agg["variation"].unique())
        agg["variation"] = pd.Categorical(
            agg["variation"], var_order, ordered=True
        )

        # dynamic width: at least 500px, or 100px per variation
        width = max(500, 100 * len(var_order))

        bars = hv.Bars(
            agg,
            kdims=["lifecycle_stage","variation"],
            vdims=[impact]
        ).opts(
            opts.Bars(
                stacked=False,
                width=width,
                height=400,
                xrotation=45,
                title=f"{assy} — {scenario} / {country}",
                tools=["hover"],
                framewise=True,    # autoscale y‐axis
                ylim=(0, None),
                xlabel="Lifecycle Stage",
                ylabel=impact,
            )
        )
        return bars

    view_pane = pn.panel(view, linked_axes=False)

    # 4) Layout
    header = pane.Markdown("### assembly‐Level Variation by Lifecycle Stage")
    controls = Row(
        pn.Column(pane.Markdown("#### Override assembly"), local_assembly),
        scenario_sel,
        country_sel,
        impact_sel,
        sizing_mode="stretch_width"
    )

    return Column(
        header,
        controls,
        view_pane,
        sizing_mode="stretch_width"
    )
