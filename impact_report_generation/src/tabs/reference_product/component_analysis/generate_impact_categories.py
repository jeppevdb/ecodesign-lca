import holoviews as hv
import pandas as pd
import panel as pn
from panel import pane, Row, Column
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import (
    scenario_selector,
    country_selector,
    local_component_selector,
    get_normalized_impact_cats
)
from .generate_intro import global_component_sel

hv.extension("bokeh")
pn.extension()

# prepare the normalized-impact DataFrame once
normalized_cats = get_normalized_impact_cats()
normalized_df = (
    scenario_df()
      .melt(
          id_vars=["scenario_setting", "country", "component"],
          value_vars=normalized_cats,
          var_name="impact_category",
          value_name="value"
      )
      .groupby(
          ["scenario_setting","country","component","impact_category"]
      )["value"].sum().reset_index()
)

def build():
    """
    creates selectors for:
      - scenario (dropdown)
      - country (dropdown)
      - local component override (dropdown)
      - impact category (characterized + single_score)
    resets the local override whenever the global component changes
    defines a view that:
      chooses component based on override or global
      filters normalized_df for that component, scenario, country
      sorts by value descending
      builds a Bars chart of impact_category vs value
    assembles layout with:
      * markdown header
      * a single row of all selectors
      * the reactive chart view
    returns the Column layout
    """
    # dropdown for scenario selection
    scenario_select = scenario_selector()
    # dropdown for country selection
    country_select  = country_selector()
    # local override dropdown for component
    local_component_sel = local_component_selector()

    # reset local override when global changes
    global_component_sel.param.watch(
        lambda ev: setattr(local_component_sel, "value", "Use global selection"),
        "value"
    )

    # display the current global component
    global_display = pn.bind(
        lambda v: pane.Markdown(f"**Global component selected:** {v}", margin=(8,0,0,0)),
        global_component_sel
    )

    @pn.depends(
        global_sel=global_component_sel,
        local_sel=local_component_sel,
        scenario=scenario_select,
        country=country_select,
    )
    def view(global_sel, local_sel, scenario, country):
        """
        filters normalized_df by chosen component, scenario, country
        returns a holoviews.Bars chart or a Text placeholder if no data
        """
        # pick override or fall back to global
        component = global_sel if local_sel == "Use global selection" else local_sel

        # filter and sort
        subset = normalized_df.query(
            "component == @component and scenario_setting == @scenario and country == @country"
        ).sort_values("value", ascending=False)

        if subset.empty:
            return hv.Text(0.5, 0.5, f"No data for {component}").opts(
                width=400, height=200
            )

        # enforce x-axis order based on sorted values
        subset["impact_category"] = pd.Categorical(
            subset["impact_category"],
            categories=subset["impact_category"],
            ordered=True
        )
        def adjust_padding(plot, element):
            plot.state.min_border_bottom = 200
            plot.state.min_border_left   = 250
        # build the bar chart
        return hv.Bars(subset, "impact_category", "value").opts(
            width=45 * len(normalized_cats),
            height=800,
            xrotation=45,
            title=f"{component} — {scenario} / {country}",
            tools=["hover"],
            margin=(50,50,150,150),
            hooks=[adjust_padding]
        )

    # assemble controls in one row
    controls = Row(
        global_display,
        local_component_sel,
        scenario_select,
        country_select,
        sizing_mode="stretch_width"
    )

    # top-level header
    header = pane.Markdown("### Normalized Impact Categories")

    return Column(
        header,
        controls,
        view,
        sizing_mode="stretch_both"
    )