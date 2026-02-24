import panel as pn
import plotly.express as px
import pandas as pd
from panel import pane, Row, Column
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import (
    local_component_selector,
    characterized_impact_selector_with_score,
    impact_unit_label,
    get_scenarios,
    country_checkbox
)
from .generate_intro import global_component_sel

pn.extension("plotly")

def build():
    """
    creates:
      - a local component override selector
      - a characterized + single score impact category selector
      - a country checkbox group
    resets the local override whenever the global component changes
    defines a reactive view that:
      chooses component from global or local override
      filters df by that component, then loops through scenarios and countries
      builds a Plotly sunburst per scenario/country
    assembles layout with:
      * markdown header
      * row of selectors above the charts
      * the reactive sunburst view
    returns the Column layout
    """
    # load the full dataframe
    df = scenario_df()
    scenarios = get_scenarios()


    # override dropdown for local component selection
    local_component_sel = local_component_selector()

    # reset local override when global changes
    def reset_local_override(event):
        local_component_sel.value = "Use global selection"
    global_component_sel.param.watch(reset_local_override, "value")

    # display the current global component
    global_display = pn.bind(
        lambda v: pane.Markdown(f"**Global component:** {v}", margin=(8,10,0,0)),
        global_component_sel
    )

    # dropdown for impact category (characterized + single_score)
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    # multi-select for countries
    country_sel = country_checkbox()

    @pn.depends(
        global_sel=global_component_sel,
        local_sel=local_component_sel,
        impact_cat=impact_sel,
        countries=country_sel
    )
    def view(global_sel, local_sel, impact_cat, countries):
        """
        filters df by chosen component
        loops through each selected country and scenario
        builds a sunburst chart for each
        returns a Column of per-country Rows
        """
        # pick actual component to use
        component = global_sel if local_sel == "Use global selection" else local_sel
        df_comp = df[df["component"] == component]

        country_sections = []
        for country in countries:
            figs = []
            df_country = df_comp[df_comp["country"] == country]
            for scenario in scenarios:
                # filter to this scenario
                df_scen = df_country[df_country["scenario_setting"] == scenario]
                # build sunburst chart
                fig = px.sunburst(
                    df_scen,
                    path=["component", "process_description"],
                    values=impact_cat,
                    color="uncertainty_score",
                    range_color=[1, 5],
                    color_continuous_scale=[(0, "green"), (0.5, "yellow"), (1, "red")],
                    title=f"{scenario.capitalize()} – {country}"
                )
                # tighten margins and fix height
                fig.update_layout(margin=dict(t=40, b=40, l=0, r=0), height=350)
                figs.append(pane.Plotly(fig, config={"displayModeBar": False}, sizing_mode="stretch_width"))

            # add header and row of charts for this country
            country_sections.append(pane.Markdown(f"### Country: {country}"))
            country_sections.append(Row(*figs, sizing_mode="stretch_width"))

        return Column(*country_sections, sizing_mode="stretch_both")

    # header and controls row
    header = pane.Markdown("## Component-Level Uncertainty Levels")
    controls = Row(
        local_component_sel,
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
