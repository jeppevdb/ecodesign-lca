import holoviews as hv
import pandas as pd
import panel as pn
import math
from panel import pane, widgets, Row, Column
from holoviews import opts
from impact_report_generation.src.utils.loaders import scenario_df
# shared global selector from intro
from .generate_intro import global_component_sel
from impact_report_generation.src.utils.selectors import get_scenarios, get_countries, get_unit, characterized_impact_selector_with_score, impact_unit_label, scenario_selector, country_selector, local_component_selector

hv.extension('bokeh')
pn.extension()

def build():
    df         = scenario_df()
    impact_sel     = characterized_impact_selector_with_score()
    unit_label = impact_unit_label(impact_sel)
    scenarios= get_scenarios()
    countries = get_countries()
    # --- local override selector ---
    local_sel = local_component_selector()
    # --- local override selector ---

    # reset local on global change
    global_component_sel.param.watch(lambda e: setattr(local_sel, 'value', 'Use Global'), 'value')

    # read-only display of global
    global_disp = pn.bind(
        lambda v: pane.Markdown(f"**Global component:** {v}"),
        global_component_sel
    )
    base_row1 = Row(pane.Markdown("Select impact category for entire tab:"), impact_sel, unit_label, sizing_mode="stretch_width")
    base_row2 = Row(global_disp, local_sel, sizing_mode = "stretch_width")

    # --- Row 1: stacked by component → process_description; pick scenario & country ---
    scen1 = scenario_selector()
    country1 = country_selector()
    @pn.depends(global_sel=global_component_sel, local_sel=local_sel,
                scenario=scen1, country=country1, impact=impact_sel)
    def view1(global_sel, local_sel, scenario, country, impact):
        comp = global_sel if local_sel=='Use global selection' else local_sel
        sub = df.query("component==@comp and scenario_setting==@scenario and country==@country")
        sub = sub.loc[sub[impact] != 0]
        if sub.empty:
            return pane.Markdown("**No environmental data for this selection**")
        number_of_processes = len(sub['database_name'].unique())
        agg = sub.groupby(['process_description'])[impact].sum().reset_index()
        # sort descending by the impact column
        agg = agg.sort_values(by=impact, ascending=False)
                # get total impacts
        total_impacts = agg[impact].sum()

        # get unit for selected impact category
        unit    = get_unit(impact) 

        # enforce that order on the x‐axis
        agg['process_description'] = pd.Categorical(
            agg['process_description'],
            categories=agg['process_description'].tolist(),
            ordered=True
        )
        y_label_adjusted = impact if impact == 'single_score' else impact.replace('Characterized -', '')
        
        # order components by total
        order = agg.groupby('process_description')[impact].sum().sort_values(ascending=False).index
        agg['process_description'] = pd.Categorical(agg['process_description'], order, ordered=True)
        return hv.Bars(agg, ['process_description'], impact).opts(
            opts.Bars(
                width=max(900, 175*number_of_processes), 
                height=650,
                xrotation=45, 
                tools=['hover'],
                title=f"{comp} (Scenario: {scenario.capitalize()} - Country: {country}) - Total impacts: {total_impacts:.2f} {unit}",
                framewise=True, 
                ylim=(0,None),        
                xaxis = 'bottom',
                margin=(50, 50, 150, 150),
                fontsize={
                        'xticks': '15pt',
                        'yticks': '15pt',    
                        'labels': '16pt',    
                        'title': '15pt'      
                        },
                ylabel=f"{y_label_adjusted} impacts ({unit})"

            )
        )

    view1_pane = pn.panel(view1, linked_axes=False)
    row1 = Column(
        pane.Markdown('#### 1. Impacts per process'),
        Row(scen1, country1, sizing_mode='stretch_width'),
        view1_pane,
        sizing_mode='stretch_width'
    )

    # --- Row 2: bar by component → scenario; pick country ---
    country2 = country_selector()

    @pn.depends(global_sel=global_component_sel, local_sel=local_sel, country=country2,impact=impact_sel)
    def view2(global_sel, local_sel, country, impact):
        comp = global_sel if local_sel=='Use global selection' else local_sel
        sub = df.query("component==@comp and country==@country")
        sub = sub.loc[sub[impact] != 0]
        if sub.empty:
            return pane.Markdown("**No environmental data for this selection**")
        number_of_processes = len(sub['process_description'].unique())
        agg = sub.groupby(['process_description','scenario_setting'])[impact].sum().reset_index()
        agg['scenario_setting'] = pd.Categorical(agg['scenario_setting'], scenarios, ordered=True)
        y_label_adjusted = impact if impact == 'single_score' else impact.replace('Characterized -', '')
        unit = get_unit(impact)
        return hv.Bars(agg, ['process_description','scenario_setting'], impact).opts(
            opts.Bars(
                width=max(500, 150*number_of_processes), height=400,
                xrotation=45, tools=['hover'],
                title=f"By Component & Scenario / {country}",
                framewise=True, ylim=(0,None), ylabel=f"{y_label_adjusted} impacts ({unit})"

            )
        )

    view2_pane = pn.panel(view2, linked_axes=False)
    row2 = Column(
        pane.Markdown('#### 2. Impact per process, compared by scenario'),
        country2,
        view2_pane,
        sizing_mode='stretch_width'
    )

    # --- Row 3: bar by component → country; pick scenario ---
    scen3 = widgets.Select(name='Scenario', options=scenarios, value=scenarios[0])

    @pn.depends(global_sel=global_component_sel, local_sel=local_sel, scenario=scen3, impact=impact_sel)
    def view3(global_sel, local_sel, scenario, impact):
        comp = global_sel if local_sel=='Use global selection' else local_sel
        sub = df.query("component==@comp and scenario_setting==@scenario")
        sub = sub.loc[sub[impact] != 0]
        if sub.empty:
            return pane.Markdown("**No environmental data for this selection**")
        number_of_processes = len(sub['process_description'].unique())
        agg = sub.groupby(['process_description','country'])[impact].sum().reset_index()
        agg['country'] = pd.Categorical(agg['country'], countries, ordered=True)
        y_label_adjusted = impact if impact == 'single_score' else impact.replace('Characterized -', '')

        unit = get_unit(impact)                                
        def style_axes(plot, element):
                # plot.state.xaxis is a list of CategoricalAxis objects --> rotate their orientation to avoid overlap:
                for ax in plot.state.xaxis:
                    ax.major_label_orientation = math.pi/4  # 45°
                    if hasattr(ax, 'group_label_orientation'):
                        ax.group_label_orientation = math.pi/4
        
        return hv.Bars(agg, ['process_description','country'], impact).opts(
            opts.Bars(
                multi_level = False,
                width=max(500, 150*number_of_processes), height=800,
                xrotation=45, tools=['hover'],
                title=f"Impact per process, compared between countries: {scenario}-case scenario",
                framewise=True, ylim=(0,None),
                fontsize={
                        'xticks': '14pt',
                        'yticks': '14pt',    
                        'labels': '14pt',    
                        'title': '14pt'      
                        },
                hooks=[style_axes],
                ylabel=f"{y_label_adjusted} impacts ({unit})"
                )
            )
    view3_pane = pn.panel(view3, linked_axes=False)
    row3 = Column(
        pane.Markdown('#### 3. Impact per process grouped '),
        scen3,
        view3_pane,
        sizing_mode='stretch_width'
    )

    # assemble 
    header = pane.Markdown('### component-level: single-score breakdown by component/process')

    return Column(header, base_row1, base_row2, row1, row2, row3, sizing_mode='stretch_width')
