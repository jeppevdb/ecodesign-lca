import panel as pn
from .generate_intro   import build as _sec1
from .generate_most_relevant_elements_bars import build as _sec2
from .generate_stage_bars import build as _sec3
from .generate_normalised import build as _sec4
from .generate_tornado  import build as _sec5
from .generate_sunburst import build as _sec6
# from .generate_assembly_contributions import build as _sec7

def build_tab():
    return pn.Tabs(
        ("Introduction",   _sec1()),
        ("Most relevant assemblies", _sec2()),
        # ("Impact distributions - Sankey diagram", None)
        # ("Cost-to-impact ratio for assemblies - Bubble chart", None),
        ("Most relevant life cycle stages", _sec3()),
        ("Most relevant impact categories", _sec4()),
        ("Uncertainty distribution", _sec6),
        # ("Uncertainty distribution - Sankey diagram", _sec7),
        ("Most relevant scenario parameters", _sec5),
        dynamic=True
    )
