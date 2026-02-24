import holoviews as hv
import pandas as pd
import panel as pn
from panel import pane, Row, Column
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import characterized_impact_selector_with_score, get_scenarios, get_countries, impact_unit_label, get_unit, get_base_assemblies

hv.extension("bokeh")

def build():
    """
    creates an impact category selector widget
    loads the scenario-based dataframe
    defines a reactive view that:
        loops through each country in df
        for each scenario in ['average', 'best', 'worst']:
            filters df by country and scenario_setting
            groups by assembly & component summing selected impact_cat
            orders assemblies descending by total impact
            makes a stacked bar chart for that scenario
        assembles markdown header + row of charts per country
    assembles a column layout with:
        a markdown header
        a single row of widgets (impact selector)
        the reactive country-rows view
    returns the column layout
    """
    # load the scenario dataframe once
    df = scenario_df()
    # define the countries, scenarios, and assemblies in the system
    scenarios = get_scenarios()
    countries = get_countries()
    assemblies = get_base_assemblies()
    # create the impact category dropdown (characterized + single_score)
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)

    @pn.depends(impact_cat=impact_sel)
    def view(impact_cat):
        """
        params:
          impact_cat (str): selected impact category column name
        returns:
          pn.Column of per-country bar rows
        """
        # list to hold each country's section
        country_sections = []
        # loop through each unique country
        for country in countries:
            # filter dataframe to this country
            df_country = df[df["country"] == country]
            # list to hold this country's scenario bars
            bars = []
            # create one bar chart per scenario
            for scenario in scenarios:
                # filter to this scenario
                df_scenario = df_country[df_country["scenario_setting"] == scenario]
                
                # get total impacts
                impacts = df_scenario[impact_cat].sum()

                # get unit for selected impact category
                unit    = get_unit(impact_cat)                
                    
                
                # group by assembly & component and sum the chosen impact
                aggregated = (
                    df_scenario
                    .groupby(["assembly", "component"])[impact_cat]
                    .sum()
                    .reset_index()
                )
                # order assemblies by total impact descending
                assembly_order = (
                    aggregated.groupby("assembly")[impact_cat]
                    .sum()
                    .sort_values(ascending=False)
                    .index
                )
                # apply that ordering for the x-axis
                aggregated["assembly"] = pd.Categorical(
                    aggregated["assembly"],
                    categories=assembly_order,
                    ordered=True
                )
                custom_width = len(assemblies)*100
                # build the stacked bar chart
                bars.append(
                    hv.Bars(aggregated, ["assembly", "component"], impact_cat)
                      .opts(
                            stacked=True,
                            width=max(450, custom_width),
                            height=350,
                            ylabel=f"Impact in {unit}",
                            xlabel="Assemblies (stacked by component)",
                            xrotation=45,
                            title=f"{scenario.capitalize()} scenario - total impacts: {impacts:.2f} {unit}",
                            tools=["hover"],
                            show_legend=False,
                            fontsize={
                                'xticks': '13pt',    
                                'labels': '12pt',    
                                'title': '12pt',
                                'yticks': '13pt'      
                                }
                            )
                        )

            # add a header for this country
            country_sections.append(pane.Markdown(f"### country: {country}"))
            # place all scenario bars side by side
            country_sections.append(Row(*bars, sizing_mode="stretch_width"))

        # return all country sections in one column
        return Column(*country_sections, sizing_mode="stretch_width")

    # top-level header
    header = pane.Markdown("### Results bar charts grouped by assembly and stacked by component")
    # place the impact selector above the charts
    controls = Row(impact_sel, unit_label, sizing_mode="stretch_width")

    # assemble and return the full layout
    return Column(
        header,
        controls,
        view,
        sizing_mode="stretch_width"
    )
