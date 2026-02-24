
import pandas as pd
import holoviews as hv
from holoviews import opts, Dimension
# import selenium

hv.extension("matplotlib")


# Load the full dataframe once
# df = scenario_df()

df = pd.read_csv(r"C:\Users\jev\OneDrive - Syddansk Universitet\thesis\holoviews_lca\calculation_model\processed_data\ellab\all_results_by_scenario_base_design.csv")

def build_links(source_col, target_col, metric_col):
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
    try:
        parts = []
        if "Component → Assembly" in levels:
            parts.append(build_links("component", "assembly", impact_cat))
        if "Assembly → System" in levels:
            parts.append(build_links("assembly", "system", impact_cat))

        if not parts:
            raise ValueError("Select at least one level.")

        sankey_df = (
            pd.concat(parts)
            .query("scenario_setting == @scenario and country == @country")
            [["source", "target", "value"]]
        )

        # Remove zeros
        sankey_df = sankey_df[sankey_df["value"] != 0]

        # Handle negative flows
        neg_flows = sankey_df[sankey_df["value"] < 0].copy()
        pos_flows = sankey_df[sankey_df["value"] > 0].copy()
        if not neg_flows.empty:
            neg_flows[["source", "target"]] = neg_flows[["target", "source"]]
            neg_flows["value"] = neg_flows["value"].abs()
        sankey_df = pd.concat([pos_flows, neg_flows], ignore_index=True)

        # Define node ordering
        source_order = sorted(sankey_df["source"].unique())
        target_order = sorted(sankey_df["target"].unique())

        sankey_df["source"] = pd.Categorical(
            sankey_df["source"], categories=source_order, ordered=True
        )
        sankey_df["target"] = pd.Categorical(
            sankey_df["target"], categories=target_order, ordered=True
        )

        # Titles and units
        unit = "kg CO2-eq"
        impact_cat_title = "Characterized -Global warming"

        # Dynamic figure height
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
                # label_text_font_size="14pt",
                cbar_width=1400,
                # height=height,
                node_width=20,
                edge_color="source",
                node_sort=False,
                label_position="left",
                title=(
                    f"Scenario setting: {scenario} case  -  "
                    f"Country: {country}  -  "
                    f"Impact category: {impact_cat_title}  -  Unit: {unit}"
                ),
                # fontsize={"title": "14pt"},
            )
        )

        return sankey

    except Exception as e:
        raise RuntimeError(f"Sankey generation failed: {e}")


def export_sankey(
    scenario="baseline",
    country="Germany",
    levels=["Component → Assembly", "Assembly → System"],
    impact_cat="Characterized -Global warming",
):
    """Generates and exports the Sankey diagram in the same folder."""
    sankey = make_sankey(scenario, country, levels, impact_cat)

    # Filenames (all saved in same directory as this script)
    base_filename = f"sankey_{scenario}_{country}_{impact_cat.replace(' ', '_').replace('-', '')}"
    base_filename = base_filename.replace("Characterized_", "").replace("__", "_")

    # Export as high-quality vector and raster
    hv.save(sankey, f"{base_filename}.svg", fmt="svg", dpi=300)
    hv.save(sankey, f"{base_filename}_300dpi.png", dpi=300)  # 300 DPI PNG
    hv.save(sankey, f"{base_filename}.pdf")       # Optional PDF version

    print(f"✅ Exported Sankey as:")
    print(f"   • {base_filename}.svg")
    print(f"   • {base_filename}_300dpi.png")
    print(f"   • {base_filename}.pdf")


# Example usage:
if __name__ == "__main__":
    export_sankey(
        scenario="average",
        country="EU",
        levels=["Component → Assembly", "Assembly → System"],
        impact_cat="Characterized -Global warming",
    )
