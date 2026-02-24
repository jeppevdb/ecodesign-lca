import pandas as pd
import holoviews as hv
import panel as pn
from holoviews import opts
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import scenario_selector, country_selector

hv.extension("bokeh")

# Load data
df = scenario_df()
# Helper to build links between two levels
def _build_links(src, tgt, data=df):
    links = (
        data.groupby(["scenario_setting", "country", src, tgt])["single_score"]
            .sum().reset_index(name="value")
            .assign(
                source=lambda d: d[src].astype(str),
                target=lambda d: d[tgt].astype(str)
            )
    )
    return links

# Build the component -> assembly links
links_comp_assy = _build_links(
    src="assembly",
    tgt="system",

)

# Function to create a Sankey for a given scenario, country, and assembly
def make_sankey_comp_assy(scenario, country):
    # Filter links for chosen scenario, country, and assembly
    sub = links_comp_assy.query(
        "scenario_setting == @scenario and country == @country"
    )[["source", "target", "value"]].copy()

    # Handle negative values: reverse link direction
    neg = (
        sub[sub.value < 0]
            .assign(
                value=lambda d: d.value.abs(),
                source=lambda d: d.target,
                target=lambda d: d.source
            )
    )
    pos = sub[sub.value >= 0]
    sankey_df = pd.concat([pos, neg])

    # Compute dynamic height based on number of unique nodes
    num_nodes = len(pd.unique(sankey_df[["source","target"]].values.ravel()))
    height = max(400, num_nodes * 25)

    title = f"{scenario} — {country}"
    sankey = hv.Sankey(sankey_df).opts(
        opts.Sankey(
            width=550,
            height=height,
            node_width=20,
            edge_color="source",
            label_position="outer",
            title=title
        )
    )
    return sankey

# Build the Panel layout
def build():
    # Widget selectors
    scen_opts = [s for s in sorted(df["scenario_setting"].unique())
                 if s.lower() in ("average", "best", "worst")]
    scen_sel = pn.widgets.RadioButtonGroup(
        name="Scenario",
        options=scen_opts,
        value=scen_opts[0]
    )

    # Generate a grid of Sankeys per country and scenario
    def update_grid(scenario):
        rows = []
        for country in sorted(df["country"].unique()):
            cells = []
            for scen in scen_opts:
                cells.append(make_sankey_comp_assy(scen, country))
            row = pn.Row(*cells, sizing_mode="stretch_width")
            caption = pn.pane.Markdown(f"#### {country}")
            rows.append(pn.Column(caption, row))
        return pn.Column(*rows)

    grid = pn.bind(update_grid, scenario=scen_sel)

    # Assemble full layout
    layout = pn.Column(
        pn.pane.Markdown("### Assembly → System Sankey per Country and Scenario"),
        grid,
        sizing_mode="stretch_both"
    )
    return layout
