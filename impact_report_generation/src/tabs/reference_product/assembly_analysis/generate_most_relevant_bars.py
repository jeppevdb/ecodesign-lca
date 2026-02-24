import holoviews as hv
import pandas as pd
import panel as pn
from panel import pane, widgets, Row, Column
from holoviews import opts
from impact_report_generation.src.utils.loaders import scenario_df
# shared global selector from intro
from .generate_intro import global_assembly_sel
from impact_report_generation.src.utils.selectors import get_scenarios, get_countries, characterized_impact_selector_with_score, impact_unit_label, scenario_selector, country_selector, local_assembly_selector

hv.extension('bokeh')
pn.extension()


def build():
    df         = scenario_df()
    impact_sel     = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    scenarios= get_scenarios()
    countries = get_countries()
    # --- local override selector ---
    local_sel = local_assembly_selector()
    # reset local on global change
    global_assembly_sel.param.watch(lambda e: setattr(local_sel, 'value', 'Use Global'), 'value')

    # read-only display of global
    global_disp = pn.bind(
        lambda v: pane.Markdown(f"**Global Assembly:** {v}"),
        global_assembly_sel
    )
    # base rows
    base_row1 = Row(global_disp, local_sel, sizing_mode = "stretch_width")
    base_row2 = Row(pane.Markdown("Select impact category for entire tab:"), impact_sel, unit_label, sizing_mode="stretch_width")
    
    # --- Row 1: stacked by component → process_description; pick scenario & country ---
    scen1 = scenario_selector()
    country1 = country_selector()

    @pn.depends(global_sel=global_assembly_sel, local_sel=local_sel,
                scenario=scen1, country=country1, impact=impact_sel)
    def view1(global_sel, local_sel, scenario, country, impact):
        asm = global_sel if local_sel=='Use global selection' else local_sel
        sub = df.query("assembly==@asm and scenario_setting==@scenario and country==@country")
        sub = sub.loc[sub[impact] != 0]
        if sub.empty:
            return pane.Markdown("**No environmental data for this selection**")
        number_of_components = len(sub['component'].unique())
        agg = sub.groupby(['component','process_description'])[impact].sum().reset_index()
        # order components by total
        order = agg.groupby('component')[impact].sum().sort_values(ascending=False).index
        agg['component'] = pd.Categorical(agg['component'], order, ordered=True)
        return hv.Bars(agg, ['component','process_description'], impact).opts(
            opts.Bars(
                stacked=True,
                width=max(500, 150*number_of_components), height=400,
                xrotation=45, tools=['hover'],
                title=f"{scenario.capitalize()} / {country}",
                framewise=True, ylim=(0,None),
                show_legend=False,
            )
        )
    view1_pane = pn.panel(view1, linked_axes=False)

    row1 = Column(
        pane.Markdown('#### 1. Stacked by component & process'),
        Row(scen1, country1, sizing_mode='stretch_width'),
        view1_pane,
        sizing_mode='stretch_width'
    )

    # --- Row 2: bar by component → scenario; pick country ---
    country2 = country_selector()

    @pn.depends(global_sel=global_assembly_sel, local_sel=local_sel, impact=impact_sel, country=country2)
    def view2(global_sel, local_sel, country, impact):
        asm = global_sel if local_sel=='Use global selection' else local_sel
        sub = df.query("assembly==@asm and country==@country")
        number_of_components = len(sub['component'].unique())
        agg = sub.groupby(['component','scenario_setting'])[impact].sum().reset_index()
        agg = agg[agg[impact] != 0]  # filter out zero values

        agg['scenario_setting'] = pd.Categorical(agg['scenario_setting'], scenarios, ordered=True)
        return hv.Bars(agg, ['component','scenario_setting'], impact).opts(
            opts.Bars(
                width=max(500, 150*number_of_components), height=400,
                xrotation=45, tools=['hover'],
                title=f"By Component & Scenario / {country}",
                framewise=True, ylim=(0,None),
            )
        )

    view2_pane = pn.panel(view2, linked_axes=False)

    row2 = Column(
        pane.Markdown('#### 2. By component & scenario'),
        country2,
        view2_pane,
        sizing_mode='stretch_width'
    )

    # --- Row 3: bar by component → country; pick scenario ---
    scen3 = scenario_selector()

    @pn.depends(global_sel=global_assembly_sel, local_sel=local_sel, impact=impact_sel, scenario=scen3)
    def view3(global_sel, local_sel, scenario, impact):
        asm = global_sel if local_sel=='Use global selection' else local_sel
        sub = df.query("assembly==@asm and scenario_setting==@scenario")
        number_of_components = len(sub['component'].unique())
        agg = sub.groupby(['component','country'])[impact].sum().reset_index()
        agg = agg[agg[impact] != 0]  # filter out zero values
        agg['country'] = pd.Categorical(agg['country'], countries, ordered=True)
        return hv.Bars(agg, ['component','country'], impact).opts(
            opts.Bars(
                width=max(500, 150*number_of_components), height=400,
                xrotation=45, tools=['hover'],
                title=f"By Component & Country / {scenario}",
                framewise=True, ylim=(0,None),
                shared_axes=False
            )
        )

    view3_pane = pn.panel(view3, linked_axes=False)
                 
                          
    row3 = Column(
        pane.Markdown('#### 3. By component & country'),
        scen3,
        view3_pane,
        sizing_mode='stretch_width'
    )

    # --- assemble ---
    header = pane.Markdown('### Assembly-level: single-score breakdown by component/process')

    return Column(header, base_row2, base_row1, row1, row2, row3, sizing_mode='stretch_width')
