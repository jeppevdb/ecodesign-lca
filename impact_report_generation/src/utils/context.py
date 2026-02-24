import pandas as pd
import panel as pn
import plotly.graph_objects as go
from impact_report_generation.src.utils.loaders import scenario_description, country_variations
from impact_report_generation.src.utils.selectors import get_countries

pn.extension("plotly")

def scenario_guide_card() -> pn.Card:
    """
    Returns a Card containing:
      - A table of scenario parameters (best/average/worst case)
      - A section on regional variations with modeled country codes
      - A table of regional variation assumptions
    """
    scenario_description_df = scenario_description()
    # Intro for scenario settings
    intro = """
### Scenario Guide

Throughout the report, one of three scenario settings can be chosen:

- **Best-case:** lowest-impact assumptions  
- **Average:** nominal/default assumptions  
- **Worst-case:** highest-impact assumptions  

In the table below, an overview of how the inputs differ based on different scenario settings is provided:
"""

    # Scenario parameters table
    params_df = scenario_description_df[[
        "scenario",
        "description",
        "best_case_assumption",
        "average_case_assumption",
        "worst_case_assumption"
    ]]

    params_fig = go.Figure(
        data=[
            go.Table(
                header=dict(
                    values=list(params_df.columns),
                    fill_color="lightgrey",
                    align="left"
                ),
                cells=dict(
                    values=[params_df[col].tolist() for col in params_df.columns],
                    align="left"
                )
            )
        ]
    )
    params_fig.update_layout(width=1000, margin=dict(t=10, b=10, l=10, r=10))
    params_pane = pn.pane.Plotly(
        params_fig,
        config={"displayModeBar": False},
        # sizing_mode="stretch_width",
    )

    # Regional variations section
    # Get unique country codes used in the LCA
    countries = get_countries()
    country_list = ", ".join(countries)
    regional_intro = f"""
### Regional variations

Results were modelled for use in the following regions: {country_list}

Details on how modelling assumptions change according to the selected region can be found in the table below:
"""

    # Load and display country variation assumptions
    country_variations_df = country_variations()
    rv_fig = go.Figure(
        data=[
            go.Table(
                header=dict(
                    values=list(country_variations_df.columns),
                    fill_color="lightgrey",
                    align="left"
                ),
                cells=dict(
                    values=[country_variations_df[col].tolist() for col in country_variations_df.columns],
                    align="left"
                )
            )
        ]
    )
    rv_fig.update_layout(width=1000, margin=dict(t=10, b=10, l=10, r=10))
    rv_pane = pn.pane.Plotly(
        rv_fig,
        config={"displayModeBar": False},
        # sizing_mode="stretch_width",
    )

    # Assemble the card
    card = pn.Card(
        pn.Column(
            pn.pane.Markdown(intro, sizing_mode="stretch_width"),
            params_pane,
            pn.pane.Markdown(regional_intro, sizing_mode="stretch_width"),
            rv_pane,
            sizing_mode="stretch_width"
        ),
        title="ℹ️ Scenario Guide",
        collapsible=False,
        width = 1200
    )

    return card

import panel as pn
from pathlib import Path

def navigation_card() -> pn.Card:
    """
    Returns a Card containing a use-case driven navigation guide,
    loading its content from markdowns/navigation.md.
    """
    md_path = Path(__file__).parent.parent / "markdowns" / "navigation.md"
    content = md_path.read_text(encoding="utf-8")
    pane = pn.pane.Markdown(content, sizing_mode="stretch_width")
    return pn.Card(
        pane,
        title="🔍 Report Navigator",
        collapsible=False,
        sizing_mode="stretch_width"
    )

def visualization_guide_card() -> pn.Card:
    """
    Returns a Card with a Visualization Guide loaded from markdowns/visualizations.md.
    """
    md_path = Path(__file__).parent.parent / "markdowns" / "visualizations.md"
    content = md_path.read_text(encoding="utf-8")
    pane = pn.pane.Markdown(content, sizing_mode="stretch_width")
    return pn.Card(
        pane,
        title="📊 Visualization Guide",
        collapsible=False,
        sizing_mode="stretch_width"
    )

import panel as pn


import os
import panel as pn

def glossary_card() -> pn.Card:
    """
    Returns a Card containing a glossary of LCA terms and concepts,
    loading its content from markdowns/glossary.md.
    """
    md_path = Path(__file__).parent.parent / "markdowns" / "glossary.md"
    content = md_path.read_text(encoding="utf-8")
    pane = pn.pane.Markdown(content, sizing_mode="stretch_width")
    return pn.Card(
        pane,
        title="📚 LCA glossary",
        collapsible=False,
        sizing_mode="stretch_width"
    )

import panel as pn
import pandas as pd
from impact_report_generation.src.utils.loaders import system_info_df, system_structure_df


def input_data_card() -> pn.Card:
    """
    Returns a Card answering “What is the input data…?” with inline sections:
      - Functional unit & reference flow
      - System breakdown
      - Geographical and temporal scope
      - Assumptions & exclusions
      - Database & LCIA method
      - Life cycle stages
    """

    # load lookup data
    info_df = system_info_df()

    def get_items(cat: str):
        """
        Fetches one or more info strings for a given category
        """
        rows = info_df.loc[info_df['category'] == cat, 'information']
        items = []
        for v in rows:
            if isinstance(v, list):
                items.extend(v)
            elif isinstance(v, str):
                if "\n" in v:
                    items.extend([line.strip() for line in v.splitlines() if line.strip()])
                else:
                    items.append(v)
            else:
                items.append(str(v))
        return items

    # fetch fields
    fu         = get_items("functional_unit")
    rf         = get_items("reference_flow")
    inc_st     = get_items("included_life_cycle_stages")
    exc_st     = get_items("excluded_life_cycle_stages")
    countries  = get_items("countries")
    temp       = get_items("temporal_scope")
    asum       = get_items("assumptions")
    excl       = get_items("exclusions")
    databases  = get_items("databases")
    lcia_meth  = get_items("lcia_methods")

    # 1) Functional unit & reference flow
    fu_text = "## Functional unit & reference flow\n\n"
    fu_text += "**Functional unit:**\n" + "\n".join(f"- {line}" for line in fu) + "\n\n"
    fu_text += "**Reference flow:**\n" + "\n".join(f"- {line}" for line in rf)
    md_fu = pn.pane.Markdown(fu_text, sizing_mode="stretch_width")

    # 2) System breakdown
    struct_df = system_structure_df()
    groups = struct_df.groupby([
        "Assembly name within LCA report",
        "Internal assembly number & name"
    ])
    items = []
    for (name, number), subdf in groups:
        comps = subdf[[
            "Component name within LCA report",
            "Component-level unit prices",
            "Internal component number",
        ]].copy()
        pane = pn.pane.DataFrame(comps, sizing_mode="stretch_width", height=200)
        label = f"Show components for {name} (Item no. {number})"
        items.append((label, pane))
    accordion = pn.Accordion(*items, active=[], sizing_mode="stretch_width")
    md_break = pn.pane.Markdown("## System breakdown", sizing_mode="stretch_width")

    # 3) Geographical & temporal scope
    geo_text = "## Geographical & temporal scope\n\n"
    geo_text += "**Geographical areas:**\n" + "\n".join(f"- {c}" for c in countries) + "\n\n"
    geo_text += f"**Temporal scope:** Calculated for the year {temp[0] if temp else '–'}."
    md_geo = pn.pane.Markdown(geo_text, sizing_mode="stretch_width")

    # 4) Assumptions & exclusions
    asum_text = "## Assumptions & exclusions\n\n"
    asum_text += "**Assumptions:**\n" + "\n".join(f"- {a}" for a in asum) + "\n\n"
    asum_text += "**Exclusions:**\n" + "\n".join(f"- {e}" for e in excl)
    md_assum = pn.pane.Markdown(asum_text, sizing_mode="stretch_width")

    # 5) Database & LCIA method
    db_text = "## Database & LCIA method\n\n"
    if databases:
        db_text += "**Databases used:**\n" + "\n".join(f"- {d}" for d in databases) + "\n\n"
    else:
        db_text += "**Databases used:** –\n\n"
    if lcia_meth:
        db_text += "**LCIA methods applied:**\n" + "\n".join(f"- {m}" for m in lcia_meth)
    else:
        db_text += "**LCIA methods applied:** –"
    md_db = pn.pane.Markdown(db_text, sizing_mode="stretch_width")

    # 6) Life cycle stages
    stages_text = "## Life cycle stages\n\n"
    stages_text += "The impacts are calculated for, and classified according to the following stages:\n"
    stages_text += "\n".join(f"- {s}" for s in inc_st)
    if exc_st:
        stages_text += f"\n\nImpacts from {', '.join(exc_st)} were not included."
    md_stages = pn.pane.Markdown(stages_text, sizing_mode="stretch_width")

    # assemble sections
    body = pn.Column(
        md_fu,
        md_break,
        accordion,
        md_geo,
        md_assum,
        md_db,
        md_stages,
        sizing_mode="stretch_width"
    )

    return pn.Card(
        body,
        title="🔧 Input Data Overview",
        collapsible=False,
        sizing_mode="stretch_width"
    )