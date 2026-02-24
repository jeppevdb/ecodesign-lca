import pandas as pd
import holoviews as hv
import panel as pn
from panel import pane, Row, Column
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import (
    scenario_selector,
    country_selector,
    local_assembly_selector,
    get_normalized_impact_cats
)
from .generate_intro import global_assembly_sel

hv.extension("bokeh")
pn.extension()

# list of normalized impact categories
normalized_impact_cats = get_normalized_impact_cats()
# prepare the normalized‐impact DataFrame once
normalized_df = (
    scenario_df()
      .melt(
          id_vars=["scenario_setting", "country", "assembly"],
          value_vars=normalized_impact_cats,
          var_name="impact_category",
          value_name="value"
      )
      .groupby(
          ["scenario_setting", "country", "assembly", "impact_category"]
      )["value"].sum().reset_index()
)

def build():
    """
    creates selectors for:
      - scenario (global selector)
      - country (global selector)
      - local assembly override (dropdown)
    resets local override whenever global assembly changes
    defines a view that:
      chooses assembly based on global vs local
      filters normalized_df for that assembly, scenario, country
      sorts by value descending
      builds a Bars chart of impact_category vs value
    assembles layout with:
      * markdown header
      * row of global selectors (display + scenario + country)
      * row of override selector + chart view
    returns the Column layout
    """
    # dropdowns from selectors
    scenario_select = scenario_selector()
    country_select  = country_selector()
    local_assembly_select = local_assembly_selector()

    # whenever the global assembly changes, reset local override
    def reset_local(event):
        local_assembly_select.value = "Use global selection"
    global_assembly_sel.param.watch(reset_local, "value")

    # display current global assembly
    global_display = pn.bind(
        lambda v: pane.Markdown(f"**Global assembly selected:** {v}", margin=(8,0,0,0)),
        global_assembly_sel
    )

    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel=local_assembly_select,
        scenario=scenario_select,
        country=country_select
    )
    def view(global_sel, local_sel, scenario, country):
        """
        filters normalized_df by assembly, scenario, country
        returns a holoviews Bars plot or Text if no data
        """
        # choose which assembly to use
        assembly = global_sel if local_sel == "Use global selection" else local_sel

        # filter + sort
        subset = normalized_df.query(
            "assembly == @assembly and scenario_setting == @scenario and country == @country"
        ).sort_values("value", ascending=False)

        if subset.empty:
            return hv.Text(0.5, 0.5, f"No data for {assembly}").opts(
                width=400, height=200
            )

        # enforce categorical order for x-axis
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
            width=60 * len(normalized_impact_cats),
            height=800,
            xrotation=45,
            title=f"{assembly} — {scenario} / {country}",
            tools=["hover"],
            margin=(50,50,150,150),
            hooks=[adjust_padding]
        )

    # top‐level header
    header = pane.Markdown("### normalized impact categories")

    # row of global selectors
    global_controls = Row(
        global_display,     
        local_assembly_select,
        scenario_select,
        country_select,
        sizing_mode="stretch_width"
    )



    return Column(
        header,
        global_controls,
        view,
        sizing_mode="stretch_both"
    )
