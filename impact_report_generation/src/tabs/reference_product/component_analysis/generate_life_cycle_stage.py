import holoviews as hv
import panel as pn
from panel import pane, Row, Column
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import (
    local_component_selector,
    characterized_impact_selector_with_score,
    impact_unit_label
)
from .generate_intro import global_component_sel

hv.extension("bokeh")
pn.extension()

def build():
    """
    creates a local component override selector
    displays the current global component
    creates a characterized + single score impact category selector
    resets the local override whenever the global component changes
    defines a view that:
        picks component based on override or global
        filters scenario_df for that component
        groups by lifecycle_stage & country, summing the chosen impact category
        makes one bar chart per scenario_setting
    assembles layout with:
        a markdown header
        a row of selectors placed above the charts
        the reactive bar view
    returns the column layout
    """
    # use the selector factory for local override
    local_component_sel = local_component_selector()

    # reset local override to placeholder when global changes
    global_component_sel.param.watch(
        lambda ev: setattr(local_component_sel, "value", "Use global selection"),
        "value"
    )

    # show which component is selected globally
    global_display = pn.bind(
        lambda v: pane.Markdown(f"**Global component:** {v}", margin=(8,10,0,0)),
        global_component_sel
    )

    # dropdown for choosing impact category (characterized + single_score)
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    @pn.depends(
        global_sel=global_component_sel,
        local_sel=local_component_sel,
        impact_cat=impact_sel
    )
    def view(global_sel, local_sel, impact_cat):
        """
        params:
          global_sel (str): the globally selected component
          local_sel (str): the overridden component or placeholder
          impact_cat (str): selected impact category column
        returns:
          a Row of holoviews Bars for average/best/worst scenarios
        """
        # decide which component to use
        component = global_sel if local_sel == "Use global selection" else local_sel

        # filter data to that component
        data = scenario_df().query("component == @component")

        bars = []
        for scenario in ["average", "best", "worst"]:
            # filter to this scenario
            df_scen = data[data["scenario_setting"] == scenario]
            # group by lifecycle_stage and country, summing the chosen metric
            aggregated = (
                df_scen
                .groupby(["lifecycle_stage", "country"])[impact_cat]
                .sum()
                .reset_index()
            )
            # build the bar chart for this scenario
            bars.append(
                hv.Bars(aggregated, ["lifecycle_stage", "country"], impact_cat)
                  .opts(
                      width=400, height=350, stacked=False,
                      title=f"{scenario.capitalize()} scenario",
                      tools=["hover"], legend_position="right"
                  )
            )

        # lay out the three charts side by side
        return Row(*bars, sizing_mode="stretch_width")

    # top-level title
    header = pane.Markdown("### Impacts by life-cycle stage & country")

    # put global display, override selector, and impact selector in one row
    controls = Row(
        global_display,
        local_component_sel,
        impact_sel,
        unit_label,
        sizing_mode="stretch_width"
    )

    return Column(
        header,
        controls,
        view,
        sizing_mode="stretch_width"
    )
