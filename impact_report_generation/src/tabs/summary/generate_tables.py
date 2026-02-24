import io
import pandas as pd
import panel as pn
from panel.widgets import CheckBoxGroup, Select, Checkbox, Button, Tabulator, FileDownload
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import (
    characterized_impact_selector_with_score,
    get_characterized_impact_cats,
    get_unit
)

pn.extension('tabulator')

def build():
    """
    Table Configurator Tab

    Provides global Scenario and Country selectors and five collapsible sections:
    1. Impact by Assembly
    2. Impact by Component
    3. Impact by Lifecycle Stage
    4. Impact by LCA Database Process
    5. Impact by Characterized Impact Category

    Each section includes its own controls, dynamically filtered by the global selectors,
    a CSV download button with filenames reflecting current selections, and an interactive table.
    Tables now include scenario and country columns explicitly.
    """
    # Load data
    df = scenario_df().copy()

    # Global selectors
    scenarios = sorted(df['scenario_setting'].dropna().unique().tolist())
    countries = sorted(df['country'].dropna().unique().tolist())
    scenario_filter = CheckBoxGroup(name='Scenarios', options=scenarios, value=scenarios)
    country_filter = CheckBoxGroup(name='Countries', options=countries, value=countries)

    # Helper to get filtered df
    def filtered_df():
        return df[
            df['scenario_setting'].isin(scenario_filter.value) &
            df['country'].isin(country_filter.value)
        ]

    # Helper to format filename parts
    def filename_parts(impact, subset=None):
        sc = ",".join(scenario_filter.value)
        ct = ",".join(country_filter.value)
        parts = [
            f"(impact_category={impact})",
            f"(scenarios={sc})",
            f"(countries={ct})",
        ]
        if subset is not None:
            parts.append(f"(selected_subset={subset})")
        return parts

    # Helper to build section
    def make_section(title, desc, widgets, depends_on, table_fn):
        header = pn.pane.Markdown(f"### {title}")
        description = pn.pane.Markdown(desc)
        toggle = Button(name="Show Section", button_type="primary")
        content = pn.Column(visible=False)
        def _toggle(event):
            content.visible = not content.visible
            toggle.name = "Hide Section" if content.visible else "Show Section"
        toggle.on_click(_toggle)
        @pn.depends(*depends_on)
        def view(*args):
            df_f = filtered_df()
            return table_fn(df_f)
        content.extend(widgets + [view])
        return header, description, toggle, content

    # Section table functions with formatted filenames and fit_data layout
    def asm_table(df_f):
        impact = impact1.value
        summary = df_f.groupby(['scenario_setting', 'country', 'assembly'])[impact].sum().reset_index()
        summary.columns = ['Scenario', 'Country', 'Assembly', 'Impacts']
        summary['Unit'] = get_unit(impact)
        part1, part2, part3 = filename_parts(impact)
        prefix = "assembly_impacts"
        fn = f"{prefix}_{part1}_{part2}_{part3}.csv"
        download = FileDownload(callback=lambda s=summary: io.BytesIO(s.to_csv(index=False).encode()), filename=fn, label="Download CSV")
        tbl = Tabulator(summary, show_index=False, layout='fit_data', pagination='local', page_size=100, sizing_mode='stretch_width')
        return pn.Column(download, tbl)

    def comp_table(df_f):
        impact = impact2.value
        summary = df_f.groupby(['scenario_setting', 'country', 'component']).agg({impact:'sum','component_weight':'sum','component_cost':'sum'}).reset_index()
        summary.columns = ['Scenario','Country','Component','Impacts','Weight','Cost']
        summary['Unit'] = get_unit(impact)
        part1, part2, part3 = filename_parts(impact)
        prefix = "component_impacts"
        fn = f"{prefix}_{part1}_{part2}_{part3}.csv"
        download = FileDownload(callback=lambda s=summary: io.BytesIO(s.to_csv(index=False).encode()), filename=fn, label="Download CSV")
        tbl = Tabulator(summary, show_index=False, layout='fit_data', pagination='local', page_size=100, sizing_mode='stretch_width')
        return pn.Column(download, tbl)

    def stage_table(df_f):
        impact = impact3.value
        full = full3.value
        asm = sel3_asm.value
        cmp = sel3_cmp.value
        d = df_f if full else (df_f[df_f['assembly']==asm] if asm!='All' else df_f[df_f['component']==cmp])
        subset = 'Full system' if full else (asm if asm!='All' else cmp)
        summary = d.groupby(['scenario_setting', 'country', 'lifecycle_stage'])[impact].sum().reset_index()
        summary.insert(0, 'Selected subset', pd.Series([subset] * len(summary)))
        summary.columns = ['Selected subset','Scenario','Country','Lifecycle stage','Impacts']
        summary['Unit'] = get_unit(impact)
        parts = filename_parts(impact, subset)
        prefix = "lifecycle_impacts"
        fn = f"{prefix}_{'_'.join(parts)}.csv"
        download = FileDownload(callback=lambda s=summary: io.BytesIO(s.to_csv(index=False).encode()), filename=fn, label="Download CSV")
        tbl = Tabulator(summary, show_index=False, layout='fit_data', pagination='local', page_size=100, sizing_mode='stretch_width')
        return pn.Column(download, tbl)

    def db_table(df_f):
        impact = impact4.value
        full = full4.value
        asm = sel4_asm.value
        cmp = sel4_cmp.value
        d = df_f if full else (df_f[df_f['assembly']==asm] if asm!='All' else df_f[df_f['component']==cmp])
        subset = 'Full system' if full else (asm if asm!='All' else cmp)
        summary = d.groupby(['scenario_setting', 'country', 'database_name'])[impact].sum().reset_index()
        summary.insert(0, 'Selected subset', pd.Series([subset] * len(summary)))
        summary.columns = ['Selected subset','Scenario','Country','LCA database process name','Impacts']
        summary['Unit'] = get_unit(impact)
        parts = filename_parts(impact, subset)
        prefix = "database_impacts"
        fn = f"{prefix}_{'_'.join(parts)}.csv"
        download = FileDownload(callback=lambda s=summary: io.BytesIO(s.to_csv(index=False).encode()), filename=fn, label="Download CSV")
        tbl = Tabulator(summary, show_index=False, layout='fit_data', pagination='local', page_size=100, sizing_mode='stretch_width')
        return pn.Column(download, tbl)

    def cat_table(df_f):
        full = full5.value
        asm = sel5_asm.value
        cmp = sel5_cmp.value
        stage = sel5_stage.value
        d = df_f
        if not full:
            if asm!='All': d = d[d['assembly']==asm]
            elif cmp!='All': d = d[d['component']==cmp]
            elif stage!='All': d = d[d['lifecycle_stage']==stage]
        summary = d.groupby(['scenario_setting', 'country'])[get_characterized_impact_cats()].sum().reset_index().melt(id_vars=['scenario_setting','country'], var_name='Impacts category', value_name='Impacts')
        subset = 'Full system' if full else (asm if asm!='All' else cmp if cmp!='All' else stage)
        summary.insert(0, 'Selected subset', pd.Series([subset] * len(summary)))
        summary.columns = ['Selected subset','Scenario','Country','Impacts category','Impacts']
        summary['Unit'] = summary['Impacts category'].map(get_unit)
        parts = filename_parts(impact_category if False else 'characterized', subset)
        prefix = "characterized_impacts"
        fn = f"{prefix}_{'_'.join(parts)}.csv"
        download = FileDownload(callback=lambda s=summary: io.BytesIO(s.to_csv(index=False).encode()), filename=fn, label="Download CSV")
        tbl = Tabulator(summary, show_index=False, layout='fit_data', pagination='local', page_size=100, sizing_mode='stretch_width')
        return pn.Column(download, tbl)

    # Instantiate section controls
    impact1 = characterized_impact_selector_with_score(); impact1.name="Impact Category"
    sec1 = make_section(
        "1. Impact by Assembly",
        "Group total impact by assembly for a selected impact category.",
        [impact1], [impact1, scenario_filter, country_filter], asm_table
    )
    impact2 = characterized_impact_selector_with_score(); impact2.name="Impact Category"
    sec2 = make_section(
        "2. Impact by Component",
        "Group total impact by component (with weight & cost).",
        [impact2], [impact2, scenario_filter, country_filter], comp_table
    )
    impact3 = characterized_impact_selector_with_score(); impact3.name="Impact Category"
    full3 = Checkbox(name='Full system', value=True)
    sel3_asm = Select(name='Assembly', options=['All']+sorted(df['assembly'].unique()), value='All')
    sel3_cmp = Select(name='Component', options=['All']+sorted(df['component'].unique()), value='All')
    sec3 = make_section(
        "3. Impact by Lifecycle Stage",
        "Group impact by lifecycle stage for full system or subset.",
        [impact3, full3, sel3_asm, sel3_cmp],
        [impact3, full3, sel3_asm, sel3_cmp, scenario_filter, country_filter], stage_table
    )
    impact4 = characterized_impact_selector_with_score(); impact4.name="Impact Category"
    full4 = Checkbox(name='Full system', value=True)
    sel4_asm = Select(name='Assembly', options=['All']+sorted(df['assembly'].unique()), value='All')
    sel4_cmp = Select(name='Component', options=['All']+sorted(df['component'].unique()), value='All')
    sec4 = make_section(
        "4. Impact by LCA Database Process",
        "Group by database process for full system or subset.",
        [impact4, full4, sel4_asm, sel4_cmp],
        [impact4, full4, sel4_asm, sel4_cmp, scenario_filter, country_filter], db_table
    )
    full5 = Checkbox(name='Full system', value=True)
    sel5_asm = Select(name='Assembly', options=['All']+sorted(df['assembly'].unique()), value='All')
    sel5_cmp = Select(name='Component', options=['All']+sorted(df['component'].unique()), value='All')
    sel5_stage = Select(name='Lifecycle stage', options=['All']+sorted(df['lifecycle_stage'].unique()), value='All')
    sec5 = make_section(
        "5. Impact by Characterized Category",
        "Sum impacts by category for full system or subset.",
        [full5, sel5_asm, sel5_cmp, sel5_stage],
        [full5, sel5_asm, sel5_cmp, sel5_stage, scenario_filter, country_filter], cat_table
    )

    # Assemble layout
    sections = [sec1, sec2, sec3, sec4, sec5]
    items = []
    for hdr, desc, tog, pnl in sections:
        items.extend([hdr, desc, tog, pnl])

    return pn.Column(
        pn.pane.Markdown("## Table Configurator Overview\nSelect scenarios and countries to filter all tables, then expand a section to view and download its data."),
        pn.Row(scenario_filter, country_filter, sizing_mode='stretch_width'),
        *items,
        sizing_mode='stretch_width'
    )
