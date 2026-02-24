import panel as pn
from .generate_intro   import build as _sec1
from .system_analysis.generate_system_section import build_tab as _sec2
from .assembly_analysis.generate_assembly_section import build_tab as _sec3
from .component_analysis.generate_component_section   import build_tab as _sec4


def build_tab():
    
    return pn.Tabs(
        ("Introduction",   _sec1()),
        ("System-level analysis",          _sec2()),
        ("Assembly-level analysis",     _sec3()),
        ("Component-level analysis",     _sec4()),
        dynamic=True
    )

