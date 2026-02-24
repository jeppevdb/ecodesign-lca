import panel as pn
from .generate_intro   import build as _sec1
from .generate_impact_categories import build as _sec3
from .generate_life_cycle_stage import build as _sec4
from .generate_tornado  import build as _sec5
from .generate_sunburst import build as _sec6
from .generate_most_relevant_bars import build as _sec7
def build_tab():
    return pn.Tabs(
        ("Introduction",   _sec1()),
        ("Most relevant processes", _sec7()),
        ("Most relevant life cycle stages", _sec4()),
        ("Most relevant impact categories", _sec3()),
        ("Uncertainty distribution", _sec6()),
        ("Most relevant scenario parameters", _sec5()),
        dynamic=True
    )

