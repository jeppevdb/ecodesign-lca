import panel as pn
import plotly.express as px
import pandas as pd
from panel import pane, Row, Column
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import (
    local_assembly_selector,
    characterized_impact_selector_with_score,
    country_checkbox,
    impact_unit_label
)
from .generate_intro import global_assembly_sel

pn.extension("plotly")

def build():
    """
    creates:
      - a local assembly override selector
      - an impact category selector (characterized + single_score)
      - a country checkbox group
    resets local override when the global assembly changes
    defines a view that:
      picks assembly from global or local override
      filters df by assembly, then loops through each country and scenario
      builds a sunburst for each scenario/country
    assembles a layout with:
      * markdown header
      * a single row of selectors (override, impact, countries)
      * the reactive sunburst view
    returns the Column layout
    """
    # load the full dataframe
    df = scenario_df()
    scenarios = ["average", "best", "worst"]

    # dropdown to override the global assembly selection
    local_assembly_sel = local_assembly_selector()

    # reset the local override whenever the global changes
    def reset_local(event):
        local_assembly_sel.value = "Use global selection"
    global_assembly_sel.param.watch(reset_local, "value")
    # display the current global assembly in markdown
    global_display = pn.bind(
        lambda v: pane.Markdown(f"**Globally selected assembly:** {v}", margin=(8,10,0,0)),
        global_assembly_sel
    )
    # dropdown for characterized + single_score impact category
    impact_sel = characterized_impact_selector_with_score()
    unit_label  = impact_unit_label(impact_sel)

    # multi-select checkbox for countries
    country_sel = country_checkbox()

    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel=local_assembly_sel,
        impact_cat=impact_sel,
        countries=country_sel
    )
    def view(global_sel, local_sel, impact_cat, countries):
        """
        filters df by chosen assembly
        loops through each selected country
        for each scenario builds a Plotly sunburst
        returns a Column of per-country rows
        """
        # choose the assembly to use
        assembly = global_sel if local_sel == "Use global selection" else local_sel
        df_assembly = df[df["assembly"] == assembly]

        country_rows = []
        for country in countries:
            # filter to this country
            df_country = df_assembly[df_assembly["country"] == country]
            figs = []
            for scenario in scenarios:
                # filter to this scenario
                df_scen = df_country[df_country["scenario_setting"] == scenario]
                # build sunburst chart
                fig = px.sunburst(
                    df_scen,
                    path=["assembly", "component"],
                    values=impact_cat,
                    color="uncertainty_score",
                    range_color=[1, 5],
                    color_continuous_scale=[(0, "green"), (0.5, "yellow"), (1, "red")],
                    title=f"{scenario.capitalize()} – {country}"
                )
                # tighten margins and fix height
                fig.update_layout(margin=dict(t=40, b=40, l=0, r=0), height=350)
                figs.append(pane.Plotly(fig, config={"displayModeBar": False}, sizing_mode="stretch_width"))

            # add a header and the row of charts for this country
            country_rows.append(pane.Markdown(f"### Country: {country}"))
            country_rows.append(Row(*figs, sizing_mode="stretch_width"))

        # stack all country sections
        return Column(*country_rows, sizing_mode="stretch_both")

    # header and controls row
    header = pane.Markdown("## Assembly-Level Sunburst Analysis")
    controls = Row(
        global_display,
        local_assembly_sel,
        impact_sel,
        unit_label,
        country_sel,
        sizing_mode="stretch_width"
    )
    
    return Column(
        header,
        controls,
        view,
        sizing_mode="stretch_both"
    )


