import pandas as pd
import holoviews as hv  # unused but kept for extension
import panel as pn
import plotly.express as px
from panel import pane, bind, Column, Row, widgets
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import (
    scenario_selector,
    country_selector,
    characterized_impact_selector_with_score,
    impact_unit_label
)

pn.extension("plotly")

# load raw scenario dataframe once
df = scenario_df()

def sunburst_chart(scenario, country, impact_category):
    """
    build a sunburst chart for a given scenario, country, and impact metric
    - filters raw_data by scenario and country
    - groups by system, assembly, component:
        * sums the chosen impact_category
        * averages uncertainty_score
    - plots a Plotly sunburst with value=impact_category
    """
    # filter to selected scenario & country
    df_filtered = df.query(
        "scenario_setting == @scenario and country == @country"
    )
    df_agg = (
        df_filtered
        .assign(weighted_uncertainty = df_filtered["uncertainty_score"] * df_filtered[impact_category])
        .groupby(["system","assembly","component"], as_index=False)
        .agg(
            **{impact_category: (impact_category, "sum")},
            weighted_uncertainty=("weighted_uncertainty","sum")
        )
    )
    df_agg["uncertainty_score"] = df_agg["weighted_uncertainty"] / df_agg[impact_category]
    df_agg = df_agg.drop(columns="weighted_uncertainty")
    impact_category_short = impact_category if impact_category == "single_score" else impact_category.replace("Characterized -", "")

    # build sunburst figure
    fig = px.sunburst(
        df_agg,
        # without the system in the center
        # path=["assembly", "component"],
        # with the system in the center
        path=["system", "assembly", "component"],
        values=impact_category,
        color="uncertainty_score",
        range_color=[1, 5],
        color_continuous_scale=[(0, "green"), (0.5, "yellow"), (1, "red")],
        title=f"{impact_category_short} uncertainty - Scenario: {scenario} – Country: {country}",
        # text_auto=True
        )
    fig.update_layout(
        coloraxis_colorbar=dict(
            tickfont=dict(size=22),  # ← increase this to make 1–5 much bigger
            title=dict(text="Uncertainty score", font=dict(size=22)),
            thickness=18,            # optional: make the bar itself wider
            len=0.9                  # optional: make it longer
        )
    )  
    # fig.update_traces(
    #     marker_colorbar=dict(
    #         title=dict(text='Uncertainty score', font=dict(size=20)),
    #         tickfont=dict(size=14)
    #     )
    # )

    # adjust layout margins and size
    fig.update_layout(
        margin=dict(t=50, b=100, l=0, r=0),
        width=1350,
        height=1150,
        uniformtext=dict(mode='hide', minsize=15),
        
    )
    fig.update_traces(
        # insidetextorientation='radial',
        insidetextfont=dict(size=16, color='black'),
        textfont_size=16,
    ) 
    # adjust colorbar font size
    # for trace in fig.data:
    #     # sunburst traces carry their continuous‐color legend on trace.marker.colorbar
    #     colorbar = getattr(trace.marker, "colorbar", None)
    #     if colorbar is not None:
    #         # bump up the tick labels
    #         colorbar.tickfont = dict(size=15)
    #         # bump up the colorbar title font
    #         # (some versions use 'titlefont', others 'title.font')
    #         if hasattr(colorbar, "titlefont"):
    #             colorbar.titlefont = dict(size=16)
    #         else:
    #             colorbar.title = dict(font=dict(size=16))


    # return as a Plotly pane
    return pane.Plotly(fig, config={"displayModeBar": True})

def build():
    """
    creates selectors for:
      - scenario (from get_scenarios)
      - country (from get_countries)
      - impact category (characterized + single_score)
    binds them to sunburst_chart to make a reactive view
    assembles a layout with:
      * markdown header
      * row of all selectors
      * the sunburst view
    returns the panel Column
    """
    # dropdown for scenario
    scenario_select = scenario_selector()
    # dropdown for country
    country_select = country_selector()
    # dropdown for impact category
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)

    # bind selectors to chart function
    sunburst_view = bind(
        sunburst_chart,
        scenario=scenario_select,
        country=country_select,
        impact_category=impact_sel
    )

    # header and controls row
    header = pane.Markdown("### Uncertainty sunburst")
    controls = Row(
        scenario_select,
        country_select,
        impact_sel,
        unit_label,
        sizing_mode="stretch_width"
    )

    # final layout
    return Column(
        header,
        controls,
        sunburst_view,
        sizing_mode="stretch_both"
    )
