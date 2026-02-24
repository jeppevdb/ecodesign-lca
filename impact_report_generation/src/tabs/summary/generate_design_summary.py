import io
import pandas as pd
import panel as pn
import plotly.express as px

from panel import pane, Row, Column
from panel.widgets import Button, FileDownload, Tabulator

from impact_report_generation.src.utils.loaders import (
    design_scenario_df,
    design_change_descriptions,
)
from impact_report_generation.src.utils.selectors import (
    get_scenarios,
    country_selector,
    scenario_selector,
    characterized_impact_selector_with_score,
)

pn.extension("plotly")

def build():
    # 1) Load & prepare
    df = design_scenario_df().copy()
    df["variation_index"] = df["design_variation_index"].astype(int)

    # 2) Controls
    country_sel = country_selector()
    scenario_sel = scenario_selector()
    impact_sel  = characterized_impact_selector_with_score()
    scenarios   = get_scenarios()

    # 3) Reactive view
    @pn.depends(country=country_sel, impact=impact_sel, selected_scen=scenario_sel)
    def view_and_tables(country, impact, selected_scen):
        df_c = df[df["country"] == country]

        # ─── A) scatter‐plot row ──────────────────────────────────────────────
        scatter_panes = []
        sub = df_c[df_c["scenario_setting"] == selected_scen]
        summary = (
            sub.groupby("variation_index")
                .apply(lambda g: pd.Series({
                    "impact_total": g[impact].sum(),
                    "cost_total":   g.drop_duplicates("component")["component_cost"].sum(),
                    "variation_level": g["design_variation_level"].dropna().unique()[0],
                    "description": ("Base design" if g["variation_index"].iloc[0] == 0
                                    else next((d for d in g["design_variation_description"]
                                                .dropna().unique() if d != "Base"), None))
                }))
                .reset_index()
        )
        base = summary[summary["variation_index"] == 0].iloc[0]
        base_imp, base_cost = base["impact_total"], base["cost_total"]
        summary["impact_pct"] = 100 * summary["impact_total"] / base_imp
        summary["cost_pct"]   = 100 * summary["cost_total"]   / base_cost
        # 1) Create the scatter using variation_index as the symbol
        fig = px.scatter(
            summary,
            x="cost_pct", y="impact_pct",
            symbol="description",
            color="variation_level",
            text="description",
            title=f"Impact vs. Cost changes per design change implementation (Country: {country}  –  Scenario: {selected_scen})",
            labels={"cost_pct":"% cost vs base", "impact_pct":"% impact vs base"}
        )

        # 2) Compute symmetric min/max around 100%
        min_val_x = min(summary["cost_pct"].min(),
                    100) * 0.95
        max_val_x = max(summary["cost_pct"].max(),
                    100) * 1.05        
        
        # 2) Compute symmetric min/max around 100%
        min_val_y = min(summary["impact_pct"].min(),
                    100) * 0.95
        max_val_y = max(summary["impact_pct"].max(),
                    100) * 1.05

        # 3) Add guide lines
        fig.add_shape(dict(
            type="line", x0=100, x1=100, y0=min_val_y, y1=max_val_y,
            line=dict(dash="dash", color="gray")
        ))
        fig.add_shape(dict(
            type="line", y0=100, y1=100, x0=min_val_x, x1=max_val_x,
            line=dict(dash="dash", color="gray")
        ))

        # 4) Style markers + text
        fig.update_traces(
            mode="markers",
            text=None,
            marker=dict(size=20, line=dict(width=1, color="black")),
            # textposition="top right",
            # textfont=dict(size=16, color="red", family="Arial Black"),
            # cliponaxis=False
        )
        short_impact_name = impact if impact == "single_score" else impact.replace('Characterized -', '')

        # 5) Layout & axis styling
        fig.update_layout(
            title_font=dict(size=20),           # title text size
            legend=dict(font=dict(size=18)),    # legend entry text size
            font=dict(size=18),                  # default font size for axis titles & tick labels            
            plot_bgcolor="rgba(240,240,240,1)",
            paper_bgcolor="white",
            margin=dict(t=60, b=30, l=80, r=30),
            height=600, width=1000,
            xaxis=dict(range=[min_val_x, max_val_x],
                    title="Total system cost (% of base design)"),
            yaxis=dict(range=[min_val_y, max_val_y],
                    title=f"Total {short_impact_name} impacts (% of base design)")
        )
        fig.update_xaxes(
            showline=True, linecolor="rgba(0,0,0,0.8)", linewidth=0.25,
            mirror=True, gridcolor="rgba(200,200,200,0.3)"
        )
        fig.update_yaxes(
            showline=True, linecolor="rgba(0,0,0,0.8)", linewidth=0.25,
            mirror=True, gridcolor="rgba(200,200,200,0.3)"
        )

        # 6) Build a lookup table for variation_index → description
        lookup = (
            summary[["variation_index", "description"]]
            .drop_duplicates()
            .sort_values("variation_index")
            .rename(columns={"variation_index":"Index", "description":"What it means"})
            .reset_index(drop=True)
        )


        # 7) Assemble final row: chart + legend
        chart_row = Row(
            pane.Plotly(fig, width=1600, height=600, sizing_mode="fixed"),
            sizing_mode="stretch_width"
        )

        # ─── B) design‐change reminder (single toggle) ───────────────────────
        details_df = design_change_descriptions()[["short_description", "long_description"]]
        details_df.columns = ["Short description", "Full description"]
        design_table = Tabulator(
            details_df,
            show_index=False,
            layout="fit_columns",
            widths={"Short description": 420},
            theme="default",
            sizing_mode="stretch_width"
        )
        design_area = Column(design_table, visible=False, sizing_mode="stretch_both")
        design_btn = Button(
            name="Click here for a quick reminder on what the different design changes mean",
            button_type="primary",
            width=600,
        )
        design_btn.on_click(lambda event: setattr(design_area, "visible", not design_area.visible))

        # ─── C) scenario‐by‐scenario summary tables ─────────────────────────
        table_sections = []
        for scen in scenarios:
            df_scen = df_c[df_c["scenario_setting"] == scen]
            group = (
                df_scen.groupby("variation_index")
                    .apply(lambda g: pd.Series({
                        "impact_total": g[impact].sum(),
                        "cost_total":   g.drop_duplicates("component")["component_cost"].sum(),
                        "uncertainty":  g["uncertainty_score"].mean(),
                        "variation_level":g["design_variation_level"].dropna().iloc[0],
                        "description": ("Base design" if g["variation_index"].iloc[0] == 0
                                        else next((d for d in g["design_variation_description"].dropna().unique() if d != "Base"), None)
                                        )
                    }))
                    .reset_index()
            )
            base = group[group["variation_index"] == 0].iloc[0]
            base_imp = base["impact_total"]
            base_cost= base["cost_total"]

            rows = []
            for _, row in group.iterrows():
                description  = row["description"]
                variation_level = row["variation_level"]
                imp  = row["impact_total"]
                cost = row["cost_total"]
                unc  = row["uncertainty"]

                imp_red_abs    = base_imp - imp
                imp_red_pct    = imp_red_abs / base_imp * 100

                cost_chg_abs   = cost - base_cost
                cost_chg_pct   = cost_chg_abs / base_cost * 100

                cost_per_unit  = (cost_chg_abs / imp_red_abs) if imp_red_abs else None
                cost_per_pct   = (cost_chg_abs / imp_red_pct)  if imp_red_pct else None

                rows.append({
                    "Variation level":              variation_level,
                    "Design variation":                    description,
                    "Total system impact":                f"{imp:.2f}",
                    "Impact reduction  vs base (absolute)":       f"{imp_red_abs:.2f}",
                    "Impact reduction vs base (%)":         f"{imp_red_pct:.2f}%",
                    "Cost (absolute)":                  f"{cost:.2f}",
                    "Cost change vs base (absolute)":      f"{cost_chg_abs:.2f}",
                    "Cost change vs base (%)":        f"{cost_chg_pct:.2f}%",
                    "Cost per unit of impact reduction":     f"{cost_per_unit:.2f}" if cost_per_unit else "-",
                    "Cost per % impact reduction":        f"{cost_per_pct:.2f}" if cost_per_pct else "-",
                    "Uncertainty":                 f"{unc:.2f}"
                })
            df_table = pd.DataFrame(rows)

            # CSV download button (capture df_table in default arg)
            dl_csv = FileDownload(
                callback=lambda df=df_table: io.BytesIO(df.to_csv(index=False).encode("utf-8")),
                filename=f"{scen}_scenario.csv",
                label="Download CSV",
                button_type="light",
                width=120,
            )

            # Tabulator for this scenario
            tbl_pane = Tabulator(
                df_table,
                show_index=False,
                layout="fit_columns",
                theme="default",
                widths={"Design variation": 420},
                configuration={
                    "renderVertical": "basic",
                    "columnDefaults": {
                        "formatter": "textarea",
                        "formatterParams": {"wrapText": True},
                        "headerWordWrap": True,
                        "variableHeight": True,
                    },
                },
            )

            # show/hide toggle for this table
            table_area = Column(tbl_pane, visible=True, sizing_mode="stretch_width")
            toggle_btn = Button(
                name="Hide summary table",
                button_type="light",
                width=140,
            )
            def make_toggle(area, btn):
                def _toggle(event):
                    area.visible = not area.visible
                    btn.name = "Hide summary table" if area.visible else "Show summary table"
                return _toggle

            toggle_btn.on_click(make_toggle(table_area, toggle_btn))

            header_row = Row(
                pane.Markdown(f"#### {scen.capitalize()} scenario - {impact} impact reductions - sold in {country}"),
                toggle_btn,
                dl_csv,
                sizing_mode="fixed",
            )

            table_sections.append(
                Column(header_row, table_area, sizing_mode="stretch_width")
            )

        # ─── assemble full view ──────────────────────────────────────────────
        return Column(
            chart_row,
            Row(design_btn, sizing_mode="stretch_width"),
            design_area,
            pane.Markdown("### Scenario-by-Scenario Summary Tables"),
            Column(*table_sections, sizing_mode="stretch_width"),
            sizing_mode="stretch_width",
        )

    # 4) Layout
    header   = pane.Markdown("## Design-Variations - Scatter Plot & Interactive Tables Comparing Impact Reduction vs Cost Changes")
    controls = Row(country_sel, scenario_sel, impact_sel, sizing_mode="stretch_width")
    return Column(header, controls, view_and_tables, sizing_mode="stretch_width")