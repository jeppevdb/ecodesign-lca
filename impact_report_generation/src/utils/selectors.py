import json
from pathlib import Path
import panel as pn
from panel import widgets
import pandas as pd
import param

# Import the global data directory from loaders
from impact_report_generation.src.utils import loaders


def _get_active_data_dir() -> Path:
    """Return the currently active processed_data/<product>/ directory."""
    if not hasattr(loaders, "DATA_DIR"):
        raise RuntimeError("DATA_DIR not set. Call loaders.set_data_dir(path) first.")
    return Path(loaders.DATA_DIR)


# ─── Load configuration dynamically ───────────────────────────────────────────

def _load_selectors_json() -> dict:
    data_dir = _get_active_data_dir()
    selectors_path = data_dir / "selectors.json"
    if not selectors_path.exists():
        raise FileNotFoundError(f"selectors.json not found in {data_dir}")
    with open(selectors_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_unit_mapping() -> dict:
    data_dir = _get_active_data_dir()
    units_path = data_dir / "impact_units.json"
    if not units_path.exists():
        raise FileNotFoundError(f"impact_units.json not found in {data_dir}")
    with open(units_path, "r", encoding="utf-8") as f:
        return json.load(f)


# Cache these in memory to avoid re-reading each time
_selector_data = None
_UNIT_MAPPING = None


def _ensure_loaded():
    global _selector_data, _UNIT_MAPPING
    if _selector_data is None or _UNIT_MAPPING is None:
        _selector_data = _load_selectors_json()
        _UNIT_MAPPING = _load_unit_mapping()


# ─── Getters ──────────────────────────────────────────────────────────────────

def get_countries():
    _ensure_loaded()
    return list(_selector_data.get("countries", []))

def get_scenarios():
    _ensure_loaded()
    return list(_selector_data.get("scenarios", []))

def get_base_assemblies():
    _ensure_loaded()
    return list(_selector_data.get("base_assemblies", []))

def get_base_components():
    _ensure_loaded()
    return list(_selector_data.get("base_components", []))
    
def get_alternative_assemblies():
    _ensure_loaded()
    return list(_selector_data.get("altered_assemblies", []))

def get_alternative_components():
    _ensure_loaded()
    return list(_selector_data.get("altered_components", []))
    
def get_characterized_impact_cats():
    _ensure_loaded()
    return list(_selector_data.get("characterized_impact_cats", []))

def get_normalized_impact_cats():
    _ensure_loaded()
    return list(_selector_data.get("normalized_impact_cats", []))

def get_normalized_and_weighted_impact_cats():
    _ensure_loaded()
    return list(_selector_data.get("normalized_and_weighted_impact_cats", []))

def get_single_score_cats():
    _ensure_loaded()
    return list(_selector_data.get("single_score_cats", []))

def get_all_impact_cats():
    _ensure_loaded()
    combined = []
    for key in (
        "single_score_cats",
        "characterized_impact_cats",
        "normalized_impact_cats",
        "normalized_and_weighted_impact_cats"
    ):
        combined.extend(_selector_data.get(key, []))
    seen, unique = set(), []
    for cat in combined:
        if cat not in seen:
            seen.add(cat)
            unique.append(cat)
    return unique


# ─── Selector factories ───────────────────────────────────────────────────────

def country_checkbox():
    opts = get_countries()
    return pn.widgets.CheckBoxGroup(name="Countries", options=opts, value=list(opts))

def scenario_checkbox():
    opts = get_scenarios()
    return widgets.CheckBoxGroup(name="Scenarios", options=opts, value=list(opts))

def assembly_checkbox():
    opts = get_base_assemblies()
    return widgets.CheckBoxGroup(name="Assemblies", options=opts, value=list(opts))

def component_checkbox():
    opts = get_base_components()
    return widgets.CheckBoxGroup(name="Components", options=opts, value=list(opts))

def country_selector():
    opts = get_countries()
    return widgets.Select(name="Countries to show", options=opts, value=opts[0] if opts else None)

def scenario_selector():
    opts = get_scenarios()
    return widgets.Select(name="Scenario", options=opts, value=opts[0] if opts else None)

def local_assembly_selector():
    opts = get_base_assemblies()
    return widgets.Select(name="Local assembly selection override",
                          options=["Use global selection"] + opts,
                          value="Use global selection")

def local_component_selector():
    opts = get_base_components()
    return widgets.Select(name="Local component selection override",
                          options=["Use global selection"] + opts,
                          value="Use global selection")

def local_design_assembly_selector():
    opts = get_alternative_assemblies()
    return widgets.Select(name="Local assembly selection override",
                          options=["Use global selection"] + opts,
                          value="Use global selection")

def local_design_component_selector():
    opts = get_alternative_components()
    return widgets.Select(name="Local component selection override",
                          options=["Use global selection"] + opts,
                          value="Use global selection")

def characterized_impact_selector():
    opts = get_characterized_impact_cats()
    return widgets.Select(name="Characterized Impact Category", options=opts, value=opts[0] if opts else None)

def characterized_impact_selector_with_score():
    opts = get_characterized_impact_cats()
    opts_with = ["single_score"] + [o for o in opts if o != "single_score"]
    return widgets.Select(name="Characterized Impact Category (+Single Score)", options=opts_with, value="single_score")

def normalized_impact_selector():
    opts = get_normalized_impact_cats()
    return widgets.Select(name="Normalized Impact Category", options=opts, value=opts[0] if opts else None)

def normalized_impact_selector_with_score():
    opts = get_normalized_impact_cats()
    opts_with = ["single_score"] + [o for o in opts if o != "single_score"]
    return widgets.Select(name="Normalized Impact Category (+Single Score)", options=opts_with, value="single_score")

def norm_weighted_impact_selector():
    opts = get_normalized_and_weighted_impact_cats()
    return widgets.Select(name="Normalized & Weighted Impact Category", options=opts, value=opts[0] if opts else None)

def norm_weighted_impact_selector_with_score():
    opts = get_normalized_and_weighted_impact_cats()
    opts_with = ["single_score"] + [o for o in opts if o != "single_score"]
    return widgets.Select(name="Normalized & Weighted Impact Category (+Single Score)", options=opts_with, value="single_score")

def single_score_selector():
    opts = get_single_score_cats()
    return widgets.Select(name="Single‐Score Indicator", options=opts, value=opts[0] if opts else None)

def all_impact_selector():
    opts = get_all_impact_cats()
    return widgets.Select(name="All Impact Categories", options=opts, value=opts[0] if opts else None)


# ─── Unit lookup helper ───────────────────────────────────────────────────────

def get_unit(category: str) -> str:
    """Return the unit string for a given impact category key."""
    _ensure_loaded()
    return _UNIT_MAPPING.get(category)


def impact_unit_label(impact_sel: pn.widgets.Select) -> pn.widgets.StaticText:
    """Return a dynamic label showing the unit for the selected impact category."""
    _ensure_loaded()
    label = pn.widgets.StaticText(
        name="Unit",
        value=f"The unit for the selected impact category is <b>{_UNIT_MAPPING.get(impact_sel.value)}</b>",
        sizing_mode="fixed",
        width=350
    )

    def _update(ev):
        label.value = f"The unit for the selected impact category is <b>{_UNIT_MAPPING.get(ev.new)}</b>"

    impact_sel.param.watch(_update, "value")
    return label
