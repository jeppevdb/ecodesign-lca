# import pandas as pd
# import holoviews as hv  # unused but kept for extension
# import panel as pn
# import plotly.express as px
# from panel import pane, bind, Column, Row, widgets
# from impact_report_generation.src.utils.loaders import scenario_df
# from impact_report_generation.src.utils.selectors import (
#     scenario_selector,
#     country_selector,
#     impact_unit_label
# )

# def build():

#     df=scenario_df()

#     scen_sel=scenario_selector()
#     country_sel=country_selector()

#         @pn.depends(scenario=scen_sel, country=country_sel)
#         def view():
#             df_filtered = df.query("scenario_setting==@scenario and country==@country")
#             scope_emissions = (df_filtered.groupby("scope")[""]
#                     .sum()
#                     .sort_values(ascending=False)
#                     .index
#                 )
            
#             df_filtered.groupby
