import os
import panel as pn

def build():
    """
    Load and return the intro text as a Panel Markdown pane.
    """
    here = os.path.dirname(__file__)
    md_path = os.path.join(here, "intro_text.md")
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    return pn.pane.Markdown(content, sizing_mode="stretch_width")
