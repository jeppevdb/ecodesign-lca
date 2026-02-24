import io
import pandas as pd
import panel as pn
from panel import Column, Row, pane
from panel.widgets import Button, Tabulator, FileDownload, Select

from impact_report_generation.src.utils.loaders import (
    scenario_df,
    design_scenario_df,
)
from impact_report_generation.src.utils.selectors import (
    characterized_impact_selector_with_score,
    country_selector,
    scenario_selector,
    impact_unit_label,
    get_unit,
)

pn.extension()

def detail_row(header_text, sentence, table):
    """
    Helper to build a collapsible section with:
    - a header
    - a summary sentence
    - a Show details button
    - a hidden Tabulator + CSV download
    """
    hdr = pane.Markdown(f"### **{header_text}**", sizing_mode="stretch_width")
    txt = pane.Markdown(sentence, sizing_mode="stretch_width")
    btn = Button(
        name="Show details",
        button_type="light",
        width=100,
        styles={"border": "2px solid #4099da", "border-radius": "4px"}
    )
    dl_csv = FileDownload(
        callback=lambda df=table: io.BytesIO(df.to_csv(index=False).encode("utf-8")),
        filename=f"{header_text}.csv",
        label="Download CSV",
        button_type="light",
        width=100
    )
    tbl_pane = Tabulator(table, show_index=False, layout="fit_data_table", theme="semantic-ui")
    tbl_pane.visible = False
    dl_csv.visible = False
    btn.on_click(lambda ev: (
        setattr(tbl_pane, "visible", not tbl_pane.visible),
        setattr(dl_csv, "visible", not dl_csv.visible)
    ))
    return Column(hdr, txt, btn, tbl_pane, dl_csv, sizing_mode="stretch_width")


def build_tab():
    # load data & selectors
    df = scenario_df()
    impact_sel = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    country_sel = country_selector()
    scenario_sel = scenario_selector()

    intro = pane.Markdown(
        "Below you'll find key LCA results with optional details. "
        "Use the selectors to choose country, scenario, and impact category."
    )

    @pn.depends(impactcat=impact_sel, country=country_sel, scenario=scenario_sel)
    def view(impactcat, country, scenario):
        sel_df = df[(df.scenario_setting == scenario) & (df.country == country)]
        unit = get_unit(impactcat)

        header_txt = pane.Markdown(
            f"**Results for {impactcat} in {country}, '{scenario}' scenario.**"
        )

        # 1) Assemblies
        asm = sel_df.groupby("assembly")[impactcat].sum()
        asm_contribs, asm_tbl = top90(asm, "Assembly")
        asm_sentence = (
            f"**Over 90% of total system impact** is caused by the following assemblies: "
            + " ".join(f"{n} ({p}%)" for n,p in asm_contribs[:-1])
            + f" and {asm_contribs[-1][0]} ({asm_contribs[-1][1]}%)."
        )
        sec1 = detail_row("Most relevant assemblies", asm_sentence, asm_tbl)

        # 2) Components
        cmp = sel_df.groupby("component")[impactcat].sum()
        cmp_contribs, cmp_tbl = top90(cmp, "Component")
        cmp_sentence = (
            f"**Over 90% of total system impact** is caused by the following components: "
            + " ".join(f"{n} ({p}%)" for n,p in cmp_contribs[:-1])
            + f" and {cmp_contribs[-1][0]} ({cmp_contribs[-1][1]}%)."
        )
        sec2 = detail_row("Most relevant components", cmp_sentence, cmp_tbl)

        # 3) Lifecycle stages
        stg = sel_df.groupby("lifecycle_stage")[impactcat].sum()
        stg_contribs, stg_tbl = top90(stg, "Stage")
        stg_sentence = (
            f"**Over 90% of total system impact** is caused during the "
            + " ".join(f"{n} ({p}%)" for n,p in stg_contribs[:-1])
            + f" and {stg_contribs[-1][0]} ({stg_contribs[-1][1]}%) stages."
        )
        sec3 = detail_row("Most relevant life-cycle stages", stg_sentence, stg_tbl)

        # 4) Cost-effective design changes

        ddf = design_scenario_df().copy()
        if ddf["design_variation_index"].nunique() < 2:
            sec4 = pane.Markdown(
                "No design scenarios were modelled yet.",
                margin=(10, 10, 10, 10),
                styles={"color": "red"},
                sizing_mode="stretch_width"
            )
        else:
            ddf['variation_index'] = ddf['design_variation_index'].astype(int)
            dd_sel = ddf[(ddf.country == country) & (ddf.scenario_setting == scenario)]
            summary = (
                dd_sel.groupby('variation_index')
                    .apply(lambda g: pd.Series({
                        'description': ('Base design' if g['variation_index'].iloc[0] == 0 else
                                        next(d for d in g['design_variation_description'].unique() if d != 'Base')),
                        'impact_total': g[impactcat].sum(),
                        'cost_total':   g.drop_duplicates('component')['component_cost'].sum(),
                    }))
                    .reset_index()
            )
            base_imp = summary.loc[summary.variation_index == 0, 'impact_total'].iloc[0]
            base_cost = summary.loc[summary.variation_index == 0, 'cost_total'].iloc[0]
            rows = []
            for _, r in summary.iterrows():
                if r.variation_index == 0:
                    continue
                imp = r['impact_total']
                cost = r['cost_total']
                imp_red = base_imp - imp
                cost_chg = cost - base_cost
                cpu = cost_chg / imp_red if imp_red else None
                rows.append({
                    'Design change': r['description'],
                    f'Total system impact ({unit})': imp,
                    'Impact reduction (abs)': imp_red,
                    'Total cost': cost,
                    'Cost change (abs)': cost_chg,
                    f'Cost per unit of reduction ({unit})': cpu
                })
            ce_df = pd.DataFrame(rows)
            # sort numeric CPU ascending (handles negative first)
            ce_df = ce_df.sort_values(by=f'Cost per unit of reduction ({unit})')
            # format numeric columns for display
            disp_df = ce_df.copy()
            disp_df[f'Total system impact ({unit})'] = disp_df[f'Total system impact ({unit})'].map(lambda x: f"{x:.2f}")
            disp_df['Impact reduction (abs)'] = disp_df['Impact reduction (abs)'].map(lambda x: f"{x:.2f}")
            disp_df['Total cost'] = disp_df['Total cost'].map(lambda x: f"{x:.2f}")
            disp_df['Cost change (abs)'] = disp_df['Cost change (abs)'].map(lambda x: f"{x:.2f}")
            disp_df[f'Cost per unit of reduction ({unit})'] = disp_df[f'Cost per unit of reduction ({unit})'].map(lambda x: f"{x:.2f}")

            items = [
                f"- {row['Design change']}: {row[f'Cost per unit of reduction ({unit})']} DKK/{unit}"
                for _, row in disp_df.iterrows()
            ]
            sentence = "The most cost-effective design changes are:\n" + "\n".join(items)
            sec4 = detail_row("Most cost-effective design changes", sentence, disp_df)

        return Column(header_txt, sec1, sec2, sec3, sec4, sizing_mode="stretch_width")

    header = pane.Markdown("# Executive Summary", sizing_mode="stretch_width")
    controls = Row(country_sel, scenario_sel, impact_sel, unit_label, sizing_mode="fixed")
    return Column(header, intro, controls, view, sizing_mode="stretch_width")


def top90(series: pd.Series, label: str):
    perc = (series / series.sum() * 100).round(1).sort_values(ascending=False)
    contribs, cum = [], 0.0
    for name, p in perc.items():
        contribs.append((name, p))
        cum += p
        if cum >= 90:
            break
    tbl = perc.reset_index(name="Contribution share (%)")
    tbl = tbl.rename(columns={tbl.columns[0]: label})
    main = tbl[tbl["Contribution share (%)"] > 2].copy()
    rem = tbl.loc[tbl["Contribution share (%)"] <= 2, "Contribution share (%)"].sum().round(1)
    main = pd.concat([main, pd.DataFrame([{label: "Remaining", "Contribution share (%)": rem}])], ignore_index=True)
    return contribs, main
