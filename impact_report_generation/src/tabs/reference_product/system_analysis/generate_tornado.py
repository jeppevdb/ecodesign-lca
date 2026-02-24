import pandas as pd
import holoviews as hv
import panel as pn
from panel import pane, bind, Row, Column, widgets
from holoviews import opts
from impact_report_generation.src.utils.loaders import parameter_df
from impact_report_generation.src.utils.selectors import (
    country_selector,
    characterized_impact_selector_with_score,
    impact_unit_label
)

hv.extension("bokeh")

def make_tornado(country, impact_category):
    """
    params:
      country (str): selected country
      impact_category (str): chosen impact metric column name
    returns:
      a holoviews Sankey or Tornado-style overlay of Bars for best/worst deviations
    """
    # load and aggregate parameter data for the selected metric
    df = parameter_df()
    df_agg = (
        df
        .groupby(["country", "selected_parameter", "scenario_setting"], as_index=False)[impact_category]
        .sum()
    )

    # pivot to wide format with one column per scenario_setting
    df_pivot = (
        df_agg
        .pivot_table(
            index=["country", "selected_parameter"],
            columns="scenario_setting",
            values=impact_category,
            fill_value=0
        )
        .reset_index()
    )

    # calculate percent deviations vs average
    df_pivot["pct_best"] = 100 * (df_pivot["best"]  - df_pivot["average"]) / df_pivot["average"]
    df_pivot["pct_worst"] = 100 * (df_pivot["worst"] - df_pivot["average"]) / df_pivot["average"]

    # filter to the chosen country
    df_country = df_pivot[df_pivot["country"] == country].copy()

    # compute maximum deviation for sorting
    df_country["max_deviation"] = df_country[["pct_best", "pct_worst"]].abs().max(axis=1)
    df_country = df_country.sort_values("max_deviation")

    # maintain categorical order for selected_parameter axis
    df_country["selected_parameter"] = pd.Categorical(
        df_country["selected_parameter"],
        categories=df_country["selected_parameter"],
        ordered=True
    )

    # build Bars for best and worst deviations, axes inverted
    best_bars = hv.Bars(df_country, "selected_parameter", "pct_best", label="Impact reductions in best-case scenario").opts(color="green", invert_axes=True)
    worst_bars = hv.Bars(df_country, "selected_parameter", "pct_worst", label="Impact increase in worst-case scenario").opts(color="red",invert_axes=True)
    short_impact_name = impact_category if impact_category == "single_score" else impact_category.replace('Characterized -', '')

    # build plot
    height = max(400, 25 * len(df_country))
    tornado_plot = (best_bars * worst_bars * hv.VLine(0)).opts(
        opts.Bars(
            width=1450,
            fontsize={
                'xticks': '15pt',
                'yticks': '15pt',    
                'labels': '15pt',    
                'title': '15pt',
                'legend': '15pt'      
                },
            height=height,
            ylabel="Percent change compared to average scenario",
            xlabel="Changed parameter",
            tools=["hover"],
            show_legend=True,
            legend_position= "bottom",
            title=f"Change in {short_impact_name} impacts ({country})"
        )
    )

    return tornado_plot

def build():
    """
    creates selectors for:
      - country (dropdown)
      - impact category (characterized + single_score)
    binds selectors to make_tornado for a reactive tornado plot
    assembles a Column layout with:
      * markdown header
      * a single Row of the two selectors
      * the tornado_view
    returns the Column layout
    """
    # dropdown for country selection
    country_select = country_selector()
    # dropdown for impact category selection
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    # bind the selectors to the tornado builder
    tornado_view = bind(
        make_tornado,
        country=country_select,
        impact_category=impact_sel
    )

    header = pane.Markdown("### Tornado chart showing parameter-sensitivity of the system")
    controls = Row(country_select, impact_sel, unit_label, sizing_mode="stretch_width")

    return Column(
        header,
        controls,
        tornado_view,
        sizing_mode="stretch_both"
    )
