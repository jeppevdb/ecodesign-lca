import panel as pn
from .generate_intro   import build as _sec1
from .system_redesigns.generate_system_section import build as _sec2
from .assembly_redesigns.generate_assembly_section import build as _sec4
from .component_redesigns.generate_component_section   import build as _sec5
from impact_report_generation.src.utils.loaders import design_scenario_df


def build_tab():
    
    df=design_scenario_df()
    # return a pane with the text 'No design scenarios were modelled yet' if there are no rows with "design_variation"
    if not (df["design_variation_index"] > 0).any():
        return pn.pane.Markdown(
            "No design scenarios were modelled yet.",
            margin=(10, 10, 10, 10),
            styles={"color": "red"}
        )
    else:
        return pn.Tabs(
            ("Introduction",   _sec1()),
            ("System redesigns",     _sec2()),
            ("Assembly redesigns",     _sec4()),
            ("Component redesigns",     _sec5()),
            dynamic=True
        )

