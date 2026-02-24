import holoviews as hv
import math
import panel as pn
from panel import pane, Row, Column
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import (
    characterized_impact_selector_with_score,
    get_scenarios,
    impact_unit_label,
    get_unit
)

hv.extension("bokeh")

def build():
    """
    creates an impact category selector widget
    loads the scenario-based dataframe
    defines a reactive function that:
        loops through each scenario from get_scenarios()
        filters df for that scenario
        groups by lifecycle_stage & country, summing the selected impact
        makes a holoviews bar plot for each scenario
    assembles a column layout with:
        a markdown header
        the selector widget
        the reactive bar plots
    returns the column layout
    """
    # selector widget for choosing which impact category to plot
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    # load the precomputed scenarios dataframe once
    df = scenario_df()

    # reactive plot builder: updates whenever the selector value changes
    @pn.depends(impact_cat=impact_sel)
    def _make_bars(impact_cat):
        """
        params:
          impact_cat (str): column name of the selected impact category
        returns:
          pn.row of holoviews.bars objects for each scenario
        """
        bars = []
        # loop through each scenario
        for scen in get_scenarios():
            # filter to this scenario
            sub = df[df["scenario_setting"] == scen]
            # aggregate by lifecycle_stage and country
            agg = (
                sub
                .groupby(["lifecycle_stage", "country"])[impact_cat]
                .sum()
                .reset_index()
            )
            unit = get_unit(impact_cat)

            def style_axes(plot, element):
                # plot.state.xaxis is a list of CategoricalAxis objects --> rotate their orientation to avoid overlap:
                for ax in plot.state.xaxis:
                    ax.major_label_orientation = math.pi/4  # 45°
                    if hasattr(ax, 'group_label_orientation'):
                        ax.group_label_orientation = math.pi/4
            y_label_adjusted = impact_cat if impact_cat == 'single_score' else impact_cat.replace('Characterized -', '')

            # create a holoviews bar chart
            bars.append(
                hv.Bars(
                    agg,
                    ["lifecycle_stage", "country"],
                    impact_cat
                ).opts(
                    width=500,
                    height=500,
                    multi_level=False,
                    stacked=False,
                    # xrotation=45,
                    title=f"{scen.capitalize()}-case scenario",
                    tools=["hover"],
                    legend_position="right",
                    hooks = [style_axes],
                    ylabel=f"{y_label_adjusted} impacts ({unit})",
                    fontsize={
                        'xticks': '14pt',
                        'yticks': '14pt',    
                        'labels': '14pt',    
                        'title': '14pt'      
                        }
                )
            )
        # return a responsive row of charts
        return Row(*bars, sizing_mode="stretch_width")

    # header markdown
    header = pane.Markdown("### Impacts by life-cycle stage & country")
    controls = Row(impact_sel, unit_label, sizing_mode="stretch_width")
    # assemble and return the full layout
    return Column(
        header,          # title
        controls,      # dropdown selector
        _make_bars,      # dynamic chart row
        sizing_mode="stretch_width"
    )
