import os
import panel as pn
import os
import panel as pn
from impact_report_generation.src.utils.loaders import design_scenario_df

df=design_scenario_df()
df_assy = df[df["design_variation_level"] == "assembly"]
assemblies = df_assy["design_variation_assembly"].dropna().unique().tolist()
global_assembly_sel = pn.widgets.Select(
name='Global assembly selection',
options=assemblies,
value=assemblies[0],
)

def build():
    """
    Load and return the intro text as a Panel Markdown pane.
    """

    here = os.path.dirname(__file__)
    md_path = os.path.join(here, "intro_text.md")
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    return pn.Column(pn.pane.Markdown(content, sizing_mode="stretch_width"), pn.Row(global_assembly_sel, sizing_mode="stretch_width"))

