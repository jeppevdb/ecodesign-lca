import pandas as pd
import holoviews as hv
import panel as pn
from panel import pane, bind, Row, Column
from holoviews import opts
from impact_report_generation.src.utils.loaders import parameter_df
from impact_report_generation.src.utils.selectors import (
    local_component_selector,
    country_selector,
    characterized_impact_selector_with_score,
    impact_unit_label
)
from .generate_intro import global_component_sel

hv.extension("bokeh")
pn.extension()

def build():
    """
    Creates:
      - a local component override selector
      - a country selector
      - a characterized + single-score impact category selector
    Resets the local override whenever the global component changes.
    Defines a view that:
      - picks component from override or global
      - filters parameter_df for that component
      - pivots on selected scenario_setting and sums the chosen impact_cat
      - computes percent deviations vs average
      - builds a tornado overlay of best/worst bars
    Assembles layout with:
      * a Markdown header
      * one row of selectors
      * the reactive tornado view
    Returns the Column layout.
    """
    # dropdown for local component override
    local_component_select = local_component_selector()

    # reset local override when global component changes
    global_component_sel.param.watch(
        lambda ev: setattr(local_component_select, "value", "Use global selection"),
        "value"
    )

    # read-only display of the current global component
    global_display = pn.bind(
        lambda v: pane.Markdown(f"**Global Component Selected:** {v}", margin=(8,10,0,0)),
        global_component_sel
    )

    # dropdown for country selection
    country_select = country_selector()

    # dropdown for characterized + single-score impact category
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    @pn.depends(
        global_sel=global_component_sel,
        local_sel=local_component_select,
        country=country_select,
        impact_cat=impact_sel
    )
    def view(global_sel, local_sel, country, impact_cat):
        """
        Filters parameter_df by chosen component,
        pivots data and computes percent deviations,
        and returns a tornado overlay or a message if no deviation.
        """
        # pick override or fall back to global
        component = global_sel if local_sel == "Use global selection" else local_sel

        # load and filter data for that component
        df = parameter_df().query("component == @component")

        # pivot selected impact category by scenario_setting
        pivot = (
            df
            .groupby(["country", "selected_parameter", "scenario_setting"], as_index=False)[impact_cat]
            .sum()
            .pivot_table(
                index=["country", "selected_parameter"],
                columns="scenario_setting",
                values=impact_cat,
                fill_value=0
            )
            .reset_index()
        )

        # compute percent changes vs average
        pivot["pct_best"]  = 100 * (pivot["best"]  - pivot["average"]) / pivot["average"]
        pivot["pct_worst"] = 100 * (pivot["worst"] - pivot["average"]) / pivot["average"]

        # filter to the selected country
        sub = pivot[pivot["country"] == country].copy()

        # if no deviation at all, show a note
        if sub[["pct_best", "pct_worst"]].abs().max().max() == 0:
            return pane.Markdown(
                f"The results for the {component} component are not affected by scenario changes."
            )

        # compute max deviation for sorting
        sub["max_deviation"] = sub[["pct_best", "pct_worst"]].abs().max(axis=1)
        sub = sub.sort_values("max_deviation")

        # enforce categorical order on x-axis
        sub["selected_parameter"] = pd.Categorical(
            sub["selected_parameter"],
            categories=sub["selected_parameter"],
            ordered=True
        )

        # build tornado bars
        best_bars = hv.Bars(sub, "selected_parameter", "pct_best") .opts(color="green", invert_axes=True)
        worst_bars = hv.Bars(sub, "selected_parameter", "pct_worst").opts(color="red",   invert_axes=True)

        # overlay with zero line
        height = max(300, 25 * len(sub))
        return (best_bars * worst_bars * hv.VLine(0)).opts(
            opts.Bars(
                width=800,
                height=height,
                ylabel="Percent change compared to average scenario",
                xlabel=None,
                tools=["hover"],
                title=f"Tornado – {component} / {country}",
                legend_position="right"
            )
        )

    # layout: header + selectors row + tornado view
    header = pane.Markdown("### Parameter-Sensitivity Tornado")
    controls = Row(
        global_display,
        Column(pane.Markdown("#### Override Component"), local_component_select),
        country_select,
        impact_sel,
        unit_label,
        sizing_mode="stretch_width"
    )

    return Column(
        header,
        controls,
        view,
        sizing_mode="stretch_both"
    )