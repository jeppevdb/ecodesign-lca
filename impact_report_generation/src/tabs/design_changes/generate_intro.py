
import os
import panel as pn
import os
import panel as pn
from impact_report_generation.src.utils.loaders import design_change_descriptions

df=design_change_descriptions()
df = df.rename(columns={
    "short_description": "Short description used in graphs",
    "long_description":  "Full description of what the design change represents",
})

design_df = pn.widgets.Tabulator(
    df,
    show_index=False,
    layout="fit_data_stretch",
    sizing_mode="stretch_width",
    )

def build():
    """
    Load and return the intro text as a Panel Markdown pane.
    """

    here = os.path.dirname(__file__)
    md_path = os.path.join(here, "intro_text.md")
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    return pn.Column(pn.pane.Markdown(content, sizing_mode="stretch_width"), pn.Row(design_df, sizing_mode="stretch_width"))

