import panel as pn
from .generate_intro   import build as _sec1
from .generate_sankey   import build as _sec2
from .generate_single_score  import build as _sec3
from .generate_sunburst   import build as _sec4
from .generate_tables    import build as _sec5
from .generate_design_summary  import build as _sec6


def build_tab():
    return pn.Tabs(
        ("Introduction",   _sec1()),
        ("Flow of impacts - component to system level",         _sec2()),
        ("Most relevant assemblies - ranked bar charts",   _sec3()),
        ("Uncertainty distribution - sunburst diagram",    _sec4()),
        ("Interactive and downloadable tables",            _sec5()),
        ("Design summary",            _sec6()),
        dynamic=True
    )
