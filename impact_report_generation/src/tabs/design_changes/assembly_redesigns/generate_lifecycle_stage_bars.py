import holoviews as hv
import pandas as pd
import panel as pn
from panel import pane, widgets, Row, Column
from holoviews import opts

from impact_report_generation.src.utils.loaders import design_scenario_df
from impact_report_generation.src.tabs.design_changes.assembly_redesigns.generate_intro import global_assembly_sel
from impact_report_generation.src.utils.selectors import impact_unit_label, scenario_selector, country_selector, characterized_impact_selector_with_score, local_design_assembly_selector

hv.extension("bokeh")
pn.extension()

def build():
    # 1) Load & filter to base + assembly‐level redesigns
    df = design_scenario_df()
    df_base = df[df["design_variation_type"]  == "base_design"]
    df_vars = df[df["design_variation_level"] == "assembly"]
    # 2) Widgets
    # for design variations, different assembly selectors need to be used
    local_assy = local_design_assembly_selector()
    # reset local whenever global changes
    global_assembly_sel.param.watch(
        lambda ev: setattr(local_assy, "value", "Use global selection"),
        "value"
    )
    global_display = pn.bind(
    lambda v: pane.Markdown(f"**Globally selected assembly:** {v}", margin=(8,10,0,0)),
    global_assembly_sel
    )
    # import other widgets
    scenario_sel = scenario_selector()
    country_sel = country_selector()
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)

    # 3) Reactive view: one grouped‐bar chart
    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel= local_assy,
        scenario= scenario_sel,
        country=  country_sel,
        impact=   impact_sel
    )
    def view(global_sel, local_sel, scenario, country, impact):
        # pick assembly (local override wins)
        assy = global_sel if local_sel == "Use global selection" else local_sel
        sub_base = df_base.query(
            "assembly==@assy and scenario_setting==@scenario and country==@country"
        )
        sub_vars = df_vars.query(
            "assembly==@assy and design_variation_assembly==@assy and scenario_setting==@scenario and country==@country"
        )
        # aggregate by lifecycle_stage & variation
        agg_base = (
            sub_base
             .groupby(["lifecycle_stage","assembly_variation_number"])[impact]
             .sum()
             .reset_index()
        )
        # aggregate by lifecycle_stage & variation
        agg_vars = (
            sub_vars
             .groupby(["lifecycle_stage","assembly_variation_number"])[impact]
             .sum()
             .reset_index()
        )
        agg = pd.concat([agg_base, agg_vars], ignore_index=True)
        # preserve lifecycle_stage order as they appear
        ls_order = list(dict.fromkeys(agg["lifecycle_stage"]))
        agg["lifecycle_stage"] = pd.Categorical(
            agg["lifecycle_stage"], ls_order, ordered=True
        )

        # ensure variation IDs are sorted numerically
        var_order = sorted(agg["assembly_variation_number"].unique())
        agg["assembly_variation_number"] = pd.Categorical(
            agg["assembly_variation_number"], var_order, ordered=True
        )

        # dynamic width: at least 500px, or 100px per variation
        width = max(500, 100 * len(var_order))

        bars = hv.Bars(
            agg,
            kdims=["lifecycle_stage","assembly_variation_number"],
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
    controls1 = Row(
        global_display,
        local_assy,
        scenario_sel,

        sizing_mode="stretch_width"
    )
    controls2 = Row(
        country_sel,
        impact_sel,
        unit_label,
        sizing_mode="stretch_width"
    )
    return Column(
        header,
        controls1,
        controls2,
        view_pane,
        sizing_mode="stretch_width"
    )
