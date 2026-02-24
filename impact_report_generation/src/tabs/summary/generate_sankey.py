import pandas as pd
import holoviews as hv
import panel as pn
from holoviews import opts, Dimension
from panel import pane, bind, widgets, Column, Row
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import (
    scenario_selector,
    country_selector,
    characterized_impact_selector_with_score,
    impact_unit_label,
    get_unit,
)

hv.extension("bokeh")

# Load the full dataframe once
df = scenario_df()


def build_links(source_col, target_col, metric_col):
    """
    Group df by scenario_setting, country, source_col, target_col
    Sum metric_col to get 'value'
    Assign source = source_col value as string
    Assign target = target_col value as string
    Return grouped dataframe with [scenario_setting, country, source, target, value]
    """
    grouped = (
        df.groupby(
            ["scenario_setting", "country", source_col, target_col]
        )[metric_col]
        .sum()
        .reset_index(name="value")
    )
    return grouped.assign(
        source=lambda d: d[source_col].astype(str),
        target=lambda d: d[target_col].astype(str)
    )


def make_sankey(scenario, country, levels, impact_cat):
    """
    Generate a Sankey diagram for the selected scenario, country, and impact category.
    Handles negative impacts by reversing those flows and taking absolute values.
    Returns a Markdown warning if Sankey generation fails.
    """
    try:
        parts = []
        if "Component → Assembly" in levels:
            parts.append(build_links("component", "assembly", impact_cat))
        if "Assembly → System" in levels:
            parts.append(build_links("assembly", "system", impact_cat))

        if not parts:
            return hv.Text(0.5, 0.5, "Select at least one level").opts(width=400, height=200)

        sankey_df = (
            pd.concat(parts)
            .query("scenario_setting == @scenario and country == @country")
            [["source", "target", "value"]]
        )

        # Remove zeros
        sankey_df = sankey_df[sankey_df["value"] != 0]

        # 🔧 Fix: handle negative flows — reverse direction and make positive
        neg_flows = sankey_df[sankey_df["value"] < 0].copy()
        pos_flows = sankey_df[sankey_df["value"] > 0].copy()
        if not neg_flows.empty:
            neg_flows[["source", "target"]] = neg_flows[["target", "source"]]
            neg_flows["value"] = neg_flows["value"].abs()
        sankey_df = pd.concat([pos_flows, neg_flows], ignore_index=True)

        # Define ordering for each depth
        source_order = sorted(sankey_df["source"].unique())
        target_order = sorted(sankey_df["target"].unique())

        sankey_df["source"] = pd.Categorical(
            sankey_df["source"], categories=source_order, ordered=True
        )
        sankey_df["target"] = pd.Categorical(
            sankey_df["target"], categories=target_order, ordered=True
        )

        # Titles and units
        unit = get_unit(impact_cat)
        impact_cat_title = (
            impact_cat if impact_cat == "single_score" else impact_cat.replace("Characterized -", "")
        )

        # Compute height dynamically based on unique nodes
        height = max(
            400,
            len(pd.unique(sankey_df[["source", "target"]].values.ravel())) * 30,
        )

        sankey = hv.Sankey(
            sankey_df,
            kdims=["source", "target"],
            vdims=[Dimension("value", value_format=lambda x: f"{x:.2f}")],
        ).opts(
            opts.Sankey(
                label_text_font_size="14pt",
                width=1400,
                height=height,
                node_width=20,
                edge_color="source",
                node_sort=False,
                label_position="outer",
                title=(
                    f"Scenario setting: {scenario} case  -  "
                    f"Country: {country}  -  "
                    f"Impact category:  {impact_cat_title}  -  Unit: {unit}"
                ),
                fontsize={"title": "14pt"},
            )
        )

        return sankey

    except Exception as e:
        # Graceful fallback in case of recursion or layout errors
        msg = (
            f"⚠️ The Sankey diagram could not be generated.\n\n"
            f"**Reason:** {type(e).__name__}: {e}\n\n"
            f"This usually happens when the data contains cycles, negative links, or invalid structure."
        )
        return pn.pane.Markdown(
            msg,
            styles={"color": "red", "font-weight": "bold"},
            sizing_mode="stretch_width",
        )


def build():
    """
    Create selectors for scenario, country, impact category, and levels.
    Bind selectors to make_sankey to produce reactive Sankey diagram.
    Assemble a Column layout and return it.
    """
    scenario_select = scenario_selector()
    country_select = country_selector()
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    level_check = widgets.CheckBoxGroup(
        name="Include levels",
        options=["Component → Assembly", "Assembly → System"],
        value=["Component → Assembly", "Assembly → System"],
    )

    # Selector rows
    controls1 = Row(
        scenario_select,
        country_select,
        level_check,
        sizing_mode="stretch_width",
    )
    controls2 = Row(
        impact_sel,
        unit_label,
        sizing_mode="stretch_width",
    )

    # Reactive sankey view with error-safe binding
    sankey_view = bind(
        make_sankey,
        scenario=scenario_select,
        country=country_select,
        levels=level_check,
        impact_cat=impact_sel,
    )

    header = pane.Markdown("### Interactive Sankey Diagram")

    return Column(
        header,
        controls1,
        controls2,
        sankey_view,
        sizing_mode="stretch_both",
    )

