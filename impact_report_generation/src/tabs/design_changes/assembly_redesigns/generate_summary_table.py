import pandas as pd
import panel as pn
import plotly.graph_objects as go
from panel import pane, widgets, Row, Column

from impact_report_generation.src.utils.loaders import design_scenario_df
from impact_report_generation.src.tabs.design_changes.assembly_redesigns.generate_intro import global_assembly_sel
from impact_report_generation.src.utils.selectors import impact_unit_label, local_design_assembly_selector, scenario_selector, characterized_impact_selector_with_score, country_selector

pn.extension("plotly")

def build():
    # Load once
    df_full = design_scenario_df().copy()
    df_full["variation_index"] = df_full["design_variation_index"].astype(int)

    # Controls
    scenario_sel = scenario_selector()
    country_sel = country_selector()
    impact_selector = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_selector)
    
    # comps = df_full["design_variation_assembly"].dropna().unique().tolist()
    local_assembly_sel = local_design_assembly_selector()
    global_assembly_sel.param.watch(
        lambda ev: setattr(local_assembly_sel, "value", "Use global selection"), "value"
    )

    global_display = pn.bind(
    lambda v: pane.Markdown(f"**Globally selected assembly:** {v}", margin=(8,10,0,0)),
    global_assembly_sel
    )
    
    @pn.depends(
        global_assembly=global_assembly_sel,
        local_assembly=local_assembly_sel,
        scenario=scenario_sel,
        country=country_sel,
        impact_metric=impact_selector
    )
    def make_tables(global_assembly, local_assembly, scenario, country, impact_metric):
        # 1) Use global assembly if local is "Use Global"
        assy = global_assembly if local_assembly == "Use global selection" else local_assembly

        # 1) Filter for scenario & country
        df_sc = df_full[
            (df_full["scenario_setting"] == scenario) &
            (df_full["country"]           == country)
        ]

        # 2) Split into base‐design and selected‐assembly variants
        df_base_design       = df_sc[df_sc["variation_index"] == 0]
        df_assembly_variants = df_sc[
            df_sc["design_variation_assembly"] == assy
        ]
        # 3) Totals from base design
        total_system_impact      = df_base_design[impact_metric].sum()
        total_system_cost        = df_base_design.drop_duplicates("component")["component_cost"].sum()
        total_system_uncertainty = df_base_design["uncertainty_score"].mean()

        # 4) Base‐assembly from base design
        df_base_assy = df_base_design[df_base_design["assembly"] == assy]
        base_assy_impact      = df_base_assy[impact_metric].sum()
        # base_assy_cost        = df_base_assy["component_cost"].iloc[0] ########################################
        base_assy_cost = (
                        df_base_assy
                        .groupby("component")["component_cost"]
                        .mean()
                        .sum()
                    )
        base_assy_uncertainty = df_base_assy["uncertainty_score"].mean()

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
                "Impact (abs)":      base_assy_impact,
                "Impact (rel)":      f"{base_assy_impact/total_system_impact*100:.2f}%",
                "Cost (abs)":        base_assy_cost,
                "Cost (rel)":        f"{base_assy_cost/total_system_cost*100:.2f}%",
                "Uncertainty":       f"{base_assy_uncertainty:.2f}"
            }
        ])

        # 6) Build variations DataFrame
        variation_rows = []
        for vid in sorted(df_assembly_variants["design_variation_variation"].unique()):
            if vid == 0:
                continue
            df_var_total = df_assembly_variants[df_assembly_variants["design_variation_variation"] == vid]
            df_var_filtered = df_var_total[df_var_total["assembly"] == assy]
            description = df_var_total["design_variation_description"].iloc[0]
            var_imp  = df_var_filtered[impact_metric].sum()
            # var_cost = df_var_filtered["component_cost"].iloc[0] ########################################
            var_cost = (
                df_var_filtered
                .groupby("component")["component_cost"]
                .mean()
                .sum()
            )
            var_unc  = df_var_filtered["uncertainty_score"].mean()

            imp_red_abs      = base_assy_impact - var_imp
            imp_red_vs_sys   = imp_red_abs/total_system_impact*100
            imp_red_vs_assy  = imp_red_abs/base_assy_impact*100

            cost_chg_abs     = var_cost - base_assy_cost
            cost_chg_vs_assy = cost_chg_abs/base_assy_cost*100
            cost_chg_vs_sys  = cost_chg_abs/total_system_cost*100

            cost_per_imp_red = cost_chg_abs / imp_red_abs if imp_red_abs != 0 else 0

            variation_rows.append({
                "Variation ID":                 vid,
                "Description":                  description,
                "Cost per percentage impact reduction":    f"{cost_per_imp_red:.2f}",
                "Impact (absolute)":                 f"{var_imp:.2f}",
                "Impact reduction (absolute)":                f"{imp_red_abs:.2f}",
                "Impact reduction vs system (%)":        f"{imp_red_vs_sys:.2f}%",
                "Impact reduction vs assembly (%)":     f"{imp_red_vs_assy:.2f}%",
                "Cost (absolute)":                   var_cost,
                "Cost change vs assembly (%)":    f"{cost_chg_vs_assy:.2f}%",
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
        fig_variations.update_layout(height=250, margin=dict(t=10,b=10,l=10,r=10))


        return Column(
            pane.Markdown("### Base vs. assembly Summary"),
            pane.Plotly(fig_summary, config={"displayModeBar": False}, sizing_mode="stretch_width"),
            pane.Markdown("### assembly‐Level Variations vs. Base"),
            pane.Plotly(fig_variations, config={"displayModeBar": False}, sizing_mode="stretch_width"),
            sizing_mode="stretch_width"
        )

    # Layout of this sub‐subtab
    header = pane.Markdown("## assembly Summary Tables", sizing_mode="stretch_width")
    controls1 = Row(
        global_display,
        local_assembly_sel,
        scenario_sel,
        sizing_mode="stretch_width"
    )
    controls2 = Row(
        country_sel,
        impact_selector,
        unit_label,
        sizing_mode="stretch_width"
    )
    return Column(header, controls1, controls2, make_tables, sizing_mode="stretch_width")

