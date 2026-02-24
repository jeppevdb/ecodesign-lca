import holoviews as hv
import panel as pn
from panel import pane, bind, Row, Column
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import (
    local_assembly_selector,
    characterized_impact_selector_with_score,
    impact_unit_label
)
from .generate_intro import global_assembly_sel

hv.extension("bokeh")
pn.extension()

def build():
    """
    creates a local assembly override selector
    creates an impact category selector widget (characterized + single_score)
    resets local override whenever global changes
    defines a view that:
        chooses assembly based on global vs local override
        filters scenario_df for that assembly
        groups by lifecycle_stage & country, summing selected impact_cat
        makes one holoviews Bar per scenario_setting
    assembles a layout with:
        markdown header
        a row of selectors (global display, override, impact selector)
        the reactive bar view
    returns the column layout
    """
    # override dropdown for local assembly selection
    local_assembly_sel = local_assembly_selector()

    # whenever global_assembly_sel changes, reset local override
    def reset_local_override(event):
        local_assembly_sel.value = "Use global selection"
    global_assembly_sel.param.watch(reset_local_override, "value")

    # display the current global assembly in markdown
    global_display = pn.bind(
        lambda v: pane.Markdown(f"**Globally selected assembly:** {v}", margin=(8,10,0,0)),
        global_assembly_sel
    )

    # dropdown for impact category (characterized + single_score)
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel=local_assembly_sel,
        impact_cat=impact_sel
    )
    def view(global_sel, local_sel, impact_cat):
        """
        params:
          global_sel (str): selected global assembly
          local_sel (str): selected local override (or placeholder)
          impact_cat (str): chosen impact category column name
        returns:
          pn.Row of holoviews.Bars for average/best/worst scenarios
        """
        # choose the actual assembly to use
        assembly = global_sel if local_sel == "Use global selection" else local_sel

        # filter data to that assembly
        data = scenario_df().query("assembly == @assembly")

        bars = []
        # loop through each scenario setting
        for scenario in ["average", "best", "worst"]:
            df_scen = data[data["scenario_setting"] == scenario]
            grouped = (
                df_scen
                .groupby(["lifecycle_stage", "country"])[impact_cat]
                .sum()
                .reset_index()
            )
            # create a bar chart for this scenario
            bars.append(
                hv.Bars(grouped, ["lifecycle_stage", "country"], impact_cat)
                  .opts(
                      width=400, height=350, stacked=False,
                      title=f"{scenario} scenario",
                      tools=["hover"], legend_position="right"
                  )
            )

        # arrange all three scenario bars side by side
        return Row(*bars, sizing_mode="stretch_width")

    # pack all selectors into one row above the charts
    controls = Row(
        global_display,
       local_assembly_sel,
        impact_sel,
        unit_label,
        sizing_mode="stretch_width"
    )

    header = pane.Markdown("### impacts by life-cycle stage & country")

    return Column(
        header,
        controls,
        view,
        sizing_mode="stretch_width"
    )
