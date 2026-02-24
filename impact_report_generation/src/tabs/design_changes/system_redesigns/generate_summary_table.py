import pandas as pd
import panel as pn
import plotly.graph_objects as go
from panel import pane, widgets, Row, Column

from impact_report_generation.src.utils.loaders import design_scenario_df
from .generate_intro import global_assembly_sel

pn.extension("plotly")

def build():
    # Load once
    df_full = design_scenario_df().copy()
    df_full["variation_index"] = df_full["design_variation_index"].astype(int)

    # Controls
    scenario_selector = widgets.Select(
        name="Scenario",
        options=sorted(df_full["scenario_setting"].unique()),
        value=sorted(df_full["scenario_setting"].unique())[0]
    )
    country_selector = widgets.Select(
        name="Country",
        options=sorted(df_full["country"].unique()),
        value=sorted(df_full["country"].unique())[0]
    )
    impact_selector = widgets.Select(
        name="Impact Metric",
        options=["single_score"] + sorted(c for c in df_full.columns if c.startswith("characterized_")),
        value="single_score"
    )

    @pn.depends(
        global_assembly=global_assembly_sel,
        scenario=scenario_selector,
        country=country_selector,
        impact_metric=impact_selector
    )
    def make_tables(global_assembly, scenario, country, impact_metric):
        # 1) Filter for scenario & country
        df_sc = df_full[
            (df_full["scenario_setting"] == scenario) &
            (df_full["country"]           == country)
        ]

        # 2) Split into base‐design and selected‐assembly variants
        df_base_design       = df_sc[df_sc["variation_index"] == 0]
        df_assembly_variants = df_sc[
            df_sc["design_variation_assembly"] == global_assembly
        ]
        # 3) Totals from base design
        total_system_impact      = df_base_design[impact_metric].sum()
        total_system_cost        = df_base_design.drop_duplicates("component")["component_cost"].sum()
        total_system_uncertainty = df_base_design["uncertainty_score"].mean()

        # 4) Base‐assembly from base design
        df_base_assembly = df_base_design[df_base_design["assembly"] == global_assembly]
        base_assembly_impact      = df_base_assembly[impact_metric].sum()
        base_assembly_cost = df_base_assembly.drop_duplicates("component")["component_cost"].sum()
        base_assembly_uncertainty = df_base_assembly["uncertainty_score"].mean()

        # 5) Build summary DataFrame
        df_summary = pd.DataFrame([
            {
                "Level":             "Base system",
                "Impact (abs)":      total_system_impact,
                "Impact (rel)":      "100%",
                "Cost (abs)":        total_system_cost,
                "Cost (rel)":        "100%",
                "Uncertainty":       f"{total_system_uncertainty:.2f}"
            },
            {
                "Level":             "Base assembly",
                "Impact (abs)":      base_assembly_impact,
                "Impact (rel)":      f"{base_assembly_impact/total_system_impact*100:.2f}%",
                "Cost (abs)":        base_assembly_cost,
                "Cost (rel)":        f"{base_assembly_cost/total_system_cost*100:.2f}%",
                "Uncertainty":       f"{base_assembly_uncertainty:.2f}"
            }
        ])

        # 6) Build variations DataFrame
        variation_rows = []
        for vid in sorted(df_assembly_variants["design_variation_variation"].unique()):
            if vid == 0:
                continue
            df_var_total = df_assembly_variants[df_assembly_variants["design_variation_variation"] == vid]
            df_var_filtered = df_var_total[df_var_total["assembly"] == global_assembly]
            var_imp  = df_var_filtered[impact_metric].sum()
            var_cost = df_var_filtered.drop_duplicates("component")["component_cost"].sum()
            var_unc  = df_var_filtered["uncertainty_score"].mean()

            imp_red_abs      = base_assembly_impact - var_imp
            imp_red_vs_sys   = imp_red_abs/total_system_impact*100
            imp_red_vs_comp  = imp_red_abs/base_assembly_impact*100

            cost_chg_abs     = var_cost - base_assembly_cost
            cost_chg_vs_comp = cost_chg_abs/base_assembly_cost*100
            cost_chg_vs_sys  = cost_chg_abs/total_system_cost*100

            cost_per_imp_red = cost_chg_abs / imp_red_abs if imp_red_abs != 0 else 0

            variation_rows.append({
                "Variation ID":                 vid,
                "Cost per percentage impact reduction":    f"{cost_per_imp_red:.2f}",
                "Impact (absolute)":                 var_imp,
                "Impact reduction (absolute)":                imp_red_abs,
                "Impact reduction vs system (%)":        f"{imp_red_vs_sys:.2f}%",
                "Impact reduction vs assembly (%)":     f"{imp_red_vs_comp:.2f}%",
                "Cost (absolute)":                   var_cost,
                "Cost change vs assembly (%)":    f"{cost_chg_vs_comp:.2f}%",
                "Cost change vs system (%)":       f"{cost_chg_vs_sys:.2f}%",
                "Uncertainty":                  f"{var_unc:.2f}"
            })

        df_variations = pd.DataFrame(variation_rows)
        fig_summary = go.Figure(data=[
            go.Table(
                header=dict(values=list(df_summary.columns)),
                cells=dict(values=[df_summary[col] for col in df_summary.columns])
            )
        ])
        fig_summary.update_layout(height=100, margin=dict(t=10,b=10,l=10,r=10))

        # 2) Plotly table for variations
        fig_variations = go.Figure(data=[
            go.Table(
                header=dict(values=list(df_variations.columns)),
                cells=dict(values=[df_variations[col] for col in df_variations.columns])
            )
        ])
        fig_variations.update_layout(height=150, margin=dict(t=10,b=10,l=10,r=10))


        return Column(
            pane.Markdown("### Base vs. assembly Summary"),
            pane.Plotly(fig_summary, config={"displayModeBar": False}, sizing_mode="stretch_width"),
            pane.Markdown("### assembly‐Level Variations vs. Base"),
            pane.Plotly(fig_variations, config={"displayModeBar": False}, sizing_mode="stretch_width"),
            sizing_mode="stretch_width"
        )

    # Layout of this sub‐subtab
    header = pane.Markdown("## assembly Summary Tables", sizing_mode="stretch_width")
    controls = Row(
        global_assembly_sel,
        scenario_selector,
        country_selector,
        impact_selector,
        sizing_mode="stretch_width"
    )

    return Column(header, controls, make_tables, sizing_mode="stretch_width")

