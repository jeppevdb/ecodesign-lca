import holoviews as hv
import pandas as pd
import panel as pn
from panel import pane, widgets, Row, Column
from holoviews import opts
from impact_report_generation.src.utils.loaders import design_scenario_df

hv.extension('bokeh')
pn.extension()

def build():
    df       = design_scenario_df()
    impact   = 'single_score'
    scenarios = ['average','best','worst']
    countries = sorted(df['country'].unique())

    # only keep base + component‐level variations
    df_comp = df.query("design_variation_level in ['base','component']")

    # component selector
    components = sorted(df_comp['component'].unique())
    component_sel = widgets.Select(
        name='Component selection',
        options= components,
        value=components[0]
    )

    # ── Row 1: Stacked by variation → process_description ──
    scenario_sel   = widgets.Select(name='Scenario', options=scenarios, value=scenarios[0])
    country_sel= widgets.Select(name='Country',  options=countries,  value=countries[0])

    @pn.depends(component=component_sel,
                scenario=scenario_sel, country=country_sel)
    def view1(component, scenario, country):
        comp = component
        sub = df_comp.query(
            "component==@comp and scenario_setting==@scenario and country==@country"
        )
        # aggregate by variation + process
        agg = (
            sub.groupby(['design_variation_variation','process_description'])[impact]
               .sum().reset_index()
        )
        # order variations by total impact descending
        order = (
            agg.groupby('design_variation_variation')[impact]
               .sum().sort_values(ascending=False).index
        )
        agg['design_variation_variation'] = pd.Categorical(
            agg['design_variation_variation'], order, ordered=True
        )
        return hv.Bars(
            agg, ['design_variation_variation','process_description'], impact
        ).opts(
            opts.Bars(
                stacked=True,
                width=600,
                height=400,
                xrotation=45,
                title=f"{scenario.capitalize()} / {country}",
                tools=['hover'],
                framewise=True, ylim=(0,None)
            )
        )

    view1_pane = pn.panel(view1, linked_axes=False)
    row1 = Column(
        pane.Markdown('#### 1. Stacked by variation & process'),
        Row(scenario_sel, country_sel, sizing_mode='stretch_width'),
        view1_pane,
        sizing_mode='stretch_width'
    )

    # ── Row 2: Bars by variation → scenario ──
    country2 = widgets.Select(name='Country', options=countries, value=countries[0])
    @pn.depends(component=component_sel, country=country_sel)

    def view2(component, country):
        comp = component
        sub = df_comp.query("component==@comp and country==@country")
        agg = (
            sub.groupby(['design_variation_variation','scenario_setting'])[impact]
               .sum().reset_index()
        )
        agg['scenario_setting'] = pd.Categorical(
            agg['scenario_setting'], scenarios, ordered=True
        )
        order = (
            agg.groupby('design_variation_variation')[impact]
               .sum().sort_values(ascending=False).index
        )
        agg['design_variation_variation'] = pd.Categorical(
            agg['design_variation_variation'], order, ordered=True
        )
        return hv.Bars(
            agg, ['design_variation_variation','scenario_setting'], impact
        ).opts(
            opts.Bars(
                width=600,
                height=400,
                xrotation=45,
                title=f"By variation & scenario / {country}",
                tools=['hover'],
                framewise=True, ylim=(0,None)
            )
        )

    view2_pane = pn.panel(view2, linked_axes=False)
    row2 = Column(
        pane.Markdown('#### 2. By variation & scenario'),
        country2,
        view2_pane,
        sizing_mode='stretch_width'
    )

    # ── Row 3: Bars by variation → country ──
    scen3 = widgets.Select(name='Scenario', options=scenarios, value=scenarios[0])

    @pn.depends(component=component_sel,
                scenario=scenario_sel)
    def view3(component, scenario):
        comp=component
        sub = df_comp.query("component==@comp and scenario_setting==@scenario")
        agg = (
            sub.groupby(['design_variation_variation','country'])[impact]
               .sum().reset_index()
        )
        agg['country'] = pd.Categorical(agg['country'], countries, ordered=True)
        order = (
            agg.groupby('design_variation_variation')[impact]
               .sum().sort_values(ascending=False).index
        )
        agg['design_variation_variation'] = pd.Categorical(
            agg['design_variation_variation'], order, ordered=True
        )
        return hv.Bars(
            agg, ['design_variation_variation','country'], impact
        ).opts(
            opts.Bars(
                width=600,
                height=400,
                xrotation=45,
                title=f"By variation & country / {scenario}",
                tools=['hover'],
                framewise=True, ylim=(0,None)
            )
        )

    view3_pane = pn.panel(view3, linked_axes=False)
    row3 = Column(
        pane.Markdown('#### 3. By variation & country'),
        scen3,
        view3_pane,
        sizing_mode='stretch_width'
    )

    # --- assemble the tab ---
    header   = pane.Markdown('### Component-Level Design Comparison')
    controls = Row(
        pn.Column(pane.Markdown('Override component'), component_sel),
        sizing_mode='stretch_width'
    )
    return Column(header, controls, row1, row2, row3, sizing_mode='stretch_width')
