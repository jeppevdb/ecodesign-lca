import holoviews as hv, pandas as pd, panel as pn
from panel import pane, bind, widgets, Column
from impact_report_generation.src.utils.loaders import scenario_df
from impact_report_generation.src.utils.selectors import get_normalized_impact_cats, country_selector, scenario_selector

hv.extension("bokeh")
normalized_impact_cats = get_normalized_impact_cats()
_agg = (
    scenario_df()
      .melt(id_vars=["scenario_setting", "country"],
            value_vars=normalized_impact_cats,
            var_name="impact_category",
            value_name="value")
      .groupby(["scenario_setting", "country", "impact_category"])["value"]
      .sum().reset_index()
)

def _chart(scenario, country):
    sub = _agg.query("scenario_setting == @scenario and country == @country").copy()
    sub = sub.sort_values("value", ascending=False)
    sub["impact_category"] = pd.Categorical(sub["impact_category"],
                                            sub["impact_category"], True)
    
    def adjust_padding(plot, element):
        plot.state.min_border_bottom = 200
        plot.state.min_border_left   = 250
    
    return hv.Bars(sub, "impact_category", "value").opts(
        width=60*len(normalized_impact_cats), 
        height=800, 
        xrotation=45,
        title=f"{scenario} / {country}", 
        tools=["hover"], 
        margin=(50, 50, 150, 150),
        hooks= [adjust_padding],
        fontsize={
                'xticks': '13pt',    
                'labels': '13pt',    
                'title': '13pt'      
                },
        ylabel="Normalized impact per functional unit"

        # min_border_bottom=200,
        # min_border_left=300
        )

def build():
    scen_sel   = scenario_selector()
    country_sel= country_selector()
    view       = bind(_chart, scenario=scen_sel, country=country_sel)
    header     = pane.Markdown("### Normalised impact categories")
    return Column(header, pn.Row(scen_sel, country_sel, sizing_mode="stretch_width"), view,
                  sizing_mode="stretch_both")


