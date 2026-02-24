import pandas as pd
import holoviews as hv
import panel as pn
from panel import pane, bind, Row, Column
from holoviews import opts
from impact_report_generation.src.utils.loaders import parameter_df
from impact_report_generation.src.utils.selectors import (
    local_assembly_selector,
    country_selector,
    characterized_impact_selector_with_score,
    impact_unit_label
)
from .generate_intro import global_assembly_sel

hv.extension("bokeh")
pn.extension("plotly")

def build():
    """
    creates a local assembly selection override
    creates a country selector
    creates a characterized + single score impact category selector
    resets the local override whenever the global assembly changes
    defines a view that:
        chooses assembly based on override or global
        filters parameter_df for that assembly
        pivots data and computes percent deviations vs average
        builds a tornado overlay of best/worst bars
    assembles layout with:
        a markdown header
        a row of controls (global display, override, country, impact selector)
        the reactive tornado view
    returns the Column layout
    """
    # override dropdown for local assembly selection
    local_assembly_sel = local_assembly_selector()

    # reset local override back to “Use global selection” whenever global changes
    global_assembly_sel.param.watch(
        lambda ev: setattr(local_assembly_sel, "value", "Use global selection"),
        "value"
    )

    # display the current global assembly
    global_display = pn.bind(
        lambda v: pane.Markdown(f"**Global Assembly Selected:** {v}", margin=(8,10,0,0)),
        global_assembly_sel
    )

    # dropdown for country
    country_sel = country_selector()

    # dropdown for characterized + single score impact category
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)

    @pn.depends(
        global_sel=global_assembly_sel,
        local_sel=local_assembly_sel,
        country=country_sel,
        impact_cat=impact_sel
    )
    def view(global_sel, local_sel, country, impact_cat):
        """
        filters parameter_df by chosen assembly
        pivots and computes pct_best and pct_worst
        returns a holoviews Bars overlay or a message if no effect
        """
        # pick override or fall back to global
        assembly = global_sel if local_sel == "Use global selection" else local_sel

        # load and filter data
        df = parameter_df().query("assembly == @assembly")

        # pivot single_score for each scenario_setting
        pivot = (
            df
            .groupby(
                ["country", "selected_parameter", "scenario_setting"],
                as_index=False
            )[impact_cat]
            .sum()
            .pivot_table(
                index=["country", "selected_parameter"],
                columns="scenario_setting",
                values=impact_cat,
                fill_value=0
            )
            .reset_index()
        )
            
        # compute percent deviations vs average
        pivot["pct_best"]  = 100 * (pivot["best"]  - pivot["average"]) / pivot["average"]
        pivot["pct_worst"] = 100 * (pivot["worst"] - pivot["average"]) / pivot["average"]

        # if no deviation at all, show a note
        if pivot[["pct_best", "pct_worst"]].abs().max().max() == 0:
            return pane.Markdown(
                f"The results for the {assembly} assembly are not affected by scenario changes."
            )

        # filter to selected country
        sub = pivot[pivot["country"] == country].copy()

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
        best_bars = hv.Bars(sub, "selected_parameter", "pct_best").opts(color="green", invert_axes=True)
        worst_bars = hv.Bars(sub, "selected_parameter", "pct_worst").opts(color="red", invert_axes=True)

        height = max(400, 50 * len(sub))
        return (best_bars * worst_bars * hv.VLine(0)).opts(
            opts.Bars(
                width=1000,
                height=height,
                ylabel="Percentual change compared to average scenario",
                xlabel=None,
                tools=["hover"],
                title=f"Tornado – {assembly} / {country}",
                show_legend=False
            )
        )

    # top-level header
    header = pane.Markdown("### Tornado chart showing individual effects of parameters on the selected assembly")

    # pack controls into a single row
    controls1 = Row(
        global_display,
        local_assembly_sel,
        country_sel,
        sizing_mode="stretch_width"
    )
    controls2=Row(
        impact_sel,
        unit_label,
        sizing_mode="stretch_width"
    )
    return Column(
        header,
        controls1,
        controls2,
        view,
        sizing_mode="stretch_both"
    )
