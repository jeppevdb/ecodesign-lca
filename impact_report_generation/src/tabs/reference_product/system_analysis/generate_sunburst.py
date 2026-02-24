import panel as pn, plotly.express as px, pandas as pd
from panel import pane, widgets, Row, Column
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import characterized_impact_selector_with_score, country_checkbox, get_countries, get_scenarios, impact_unit_label

pn.extension("plotly")

def build():
    """
    creates a system-level sunburst analysis view
    loads the scenario-based dataframe
    defines selectors for country and impact category
    defines a reactive view function that:
        loops through each selected country
        for each scenario, builds a plotly sunburst chart
        assembles rows of charts per country
    assembles a column layout with:
        a markdown header
        controls row of selectors
        the reactive view
    returns the column layout
    """
    df = scenario_df()
    scenarios = get_scenarios()
    country_sel = country_checkbox()
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)

    @pn.depends(countries=country_sel, impact_cat=impact_sel)
    def view(countries, impact_cat):
        """
        params:
            countries (list[str]): selected countries to show
            impact_cat (str): selected impact category column name
        returns:
            pn.Column of per-country sunburst plots
        """
        rows = []
        for country in countries:
            row_figs = []
            sub_country = df[df["country"] == country]
            for scen in scenarios:
                sub = sub_country[sub_country["scenario_setting"] == scen]
                fig = px.sunburst(
                    sub,
                    path=["system", "assembly"],
                    values=impact_cat,
                    color="uncertainty_score",
                    range_color=[1, 5],
                    color_continuous_scale=[(0, "green"), (0.5, "yellow"), (1, "red")],
                    title=f"{scen.capitalize()} – {country}"
                )
                fig.update_layout(
                    margin=dict(t=40, b=40, l=0, r=0),
                    height=350
                )
                row_figs.append(
                    pane.Plotly(
                        fig,
                        config={"displayModeBar": False},
                        sizing_mode="stretch_width"
                    )
                )
            rows.append(
                Column(
                    pane.Markdown(f"### country: {country}"),
                    Row(*row_figs, sizing_mode="stretch_width"),
                    sizing_mode="stretch_width"
                )
            )
        return Column(*rows, sizing_mode="stretch_both")

    header = pane.Markdown("## system-level sunburst analysis")
    controls = pn.Row(impact_sel, unit_label, country_sel, sizing_mode="stretch_width")

    return Column(header, controls, view, sizing_mode="stretch_both")
