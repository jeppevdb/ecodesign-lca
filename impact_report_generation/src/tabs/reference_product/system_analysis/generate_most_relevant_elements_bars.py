import holoviews as hv, pandas as pd, panel as pn
from panel import pane, Row, Column
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import country_selector, scenario_selector, characterized_impact_selector_with_score, impact_unit_label
from impact_report_generation.src.utils.selectors import get_base_assemblies, get_countries, get_scenarios
hv.extension("bokeh")
pn.extension()

def build():
    df        = scenario_df()
    impact_sel    = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    scenarios = get_scenarios()
    countries = get_countries()
    assemblies= get_base_assemblies()
    number_of_assemblies = len(assemblies)

    # ── Impact selector row ──
    base_row = Row(pane.Markdown("Select impact category for entire tab:"),
        impact_sel,
        unit_label,
        sizing_mode="stretch_width"
    )

    # ── Row 1: Stacked by assembly → component, choose scenario & country ──
    scen_sel1   = scenario_selector()
    country_sel1 = country_selector()
    
    @pn.depends(scenario=scen_sel1, country=country_sel1, impact=impact_sel)
    def view1(scenario, country, impact):
        sub  = df[(df["scenario_setting"]==scenario) & (df["country"]==country)]
        agg  = sub.groupby(["assembly","component"])[impact].sum().reset_index()
        order= (
            agg.groupby("assembly")[impact]
               .sum()
               .sort_values(ascending=False)
               .index
        )
        agg["assembly"] = pd.Categorical(agg["assembly"], order, ordered=True)
        return hv.Bars(
            agg, ["assembly","component"], impact
        ).opts(
            stacked=True,
            width=max(500, 200*number_of_assemblies), height=400,
            xrotation=45,
            tools=["hover"],
            title=f"{scenario.capitalize()} / {country}",
            show_legend=False,
            framewise=True,
            ylim=(0, None)
        )

    view1_pane = pn.panel(view1, linked_axes=False)

    row1 = Column(
        pane.Markdown("#### 1. Stacked by assembly & component"),
        Row(scen_sel1, country_sel1, sizing_mode="stretch_width"),
        view1_pane,
        sizing_mode="stretch_width"
    )

    # ── Row 2: Bar by assembly → scenario, choose country ──
    country_sel2 = country_selector()

    @pn.depends(country=country_sel2, impact=impact_sel)
    def view2(country, impact):
        sub = df[df["country"]==country]
        agg = sub.groupby(["assembly","scenario_setting"])[impact]\
                 .sum().reset_index()
        agg["scenario_setting"] = pd.Categorical(
            agg["scenario_setting"], scenarios, ordered=True
        )
        return hv.Bars(
            agg, ["assembly","scenario_setting"], impact
        ).opts(
            width=max(500, 200*number_of_assemblies), height=400,
            xrotation=45,
            tools=["hover"],
            title=f"By Assembly & Scenario / {country}",
            framewise=True,
            ylim=(0, None)
        )

    view2_pane = pn.panel(view2, linked_axes=False)

    row2 = Column(
        pane.Markdown("#### 2. By assembly & scenario"),
        country_sel2,
        view2_pane,
        sizing_mode="stretch_width"
    )

    # ── Row 3: Bar by assembly → country, choose scenario ──
    scen_sel3 = scenario_selector()

    @pn.depends(scenario=scen_sel3, impact=impact_sel)
    def view3(scenario, impact):
        sub = df[df["scenario_setting"]==scenario]
        agg = sub.groupby(["assembly","country"])[impact]\
                 .sum().reset_index()
        agg["country"] = pd.Categorical(agg["country"], countries, ordered=True)
        return hv.Bars(
            agg, ["assembly","country"], impact
        ).opts(
            width=max(500, 200*number_of_assemblies), height=400,
            xrotation=45,
            tools=["hover"],
            title=f"By Assembly & Country / {scenario}",
            framewise=True,
            ylim=(0, None)
        )

    view3_pane = pn.panel(view3, linked_axes=False)

    row3 = Column(
        pane.Markdown("#### 3. By assembly & country"),
        scen_sel3,
        view3_pane,
        sizing_mode="stretch_width"
    )

    # ── Full layout ──
    header = pane.Markdown("### Single-score by assembly & component, per country")
    return Column(header, base_row, row1, row2, row3, sizing_mode="stretch_width")
