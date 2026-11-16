"""Unit names, aliases and conversion within one kind of unit.

Database files spell units differently ("t*km", "tkm", "Item(s)", "p").
Everything is mapped to a canonical spelling; a unit the table does not
know is only compatible with itself.
"""

from .errors import ValidationError

# canonical unit -> (dimension, factor to the dimension's base unit)
_UNITS: dict[str, tuple[str, float]] = {
    "mg": ("mass", 1e-6),
    "g": ("mass", 1e-3),
    "kg": ("mass", 1.0),
    "t": ("mass", 1e3),
    "J": ("energy", 1e-6),
    "kJ": ("energy", 1e-3),
    "MJ": ("energy", 1.0),
    "GJ": ("energy", 1e3),
    "Wh": ("energy", 3.6e-3),
    "kWh": ("energy", 3.6),
    "MWh": ("energy", 3.6e3),
    "mm": ("length", 1e-3),
    "cm": ("length", 1e-2),
    "m": ("length", 1.0),
    "km": ("length", 1e3),
    "kgkm": ("transport", 1e-3),
    "tkm": ("transport", 1.0),
    "pkm": ("person_transport", 1.0),
    "ml": ("volume", 1e-6),
    "l": ("volume", 1e-3),
    "m3": ("volume", 1.0),
    "cm2": ("area", 1e-4),
    "m2": ("area", 1.0),
    "ha": ("area", 1e4),
    "s": ("time", 1 / 3600),
    "min": ("time", 1 / 60),
    "h": ("time", 1.0),
    "d": ("time", 24.0),
    "a": ("time", 8760.0),
    "p": ("items", 1.0),
    "m2a": ("area_time", 1.0),
    "kma": ("length_time", 1.0),
    "m3km": ("volume_transport", 1.0),
}

_ALIASES = {
    "ton": "t",
    "tonne": "t",
    "tonnes": "t",
    "t*km": "tkm",
    "t.km": "tkm",
    "ton*km": "tkm",
    "metric ton*km": "tkm",
    "m2*year": "m2a",
    "km*year": "kma",
    "kg*km": "kgkm",
    "kg.km": "kgkm",
    "p*km": "pkm",
    "p.km": "pkm",
    "paskm": "pkm",
    "person*km": "pkm",
    "litre": "l",
    "liter": "l",
    "m³": "m3",
    "m²": "m2",
    "item(s)": "p",
    "item": "p",
    "items": "p",
    "piece": "p",
    "pieces": "p",
    "pcs": "p",
    "unit": "p",
    "hr": "h",
    "hour": "h",
    "day": "d",
    "year": "a",
    "yr": "a",
    "m2*a": "m2a",
    "km*a": "kma",
    "m3*km": "m3km",
}
_BY_LOWER = {name.lower(): name for name in _UNITS}


def canonical(unit: str) -> str:
    """Canonical spelling of ``unit``; unknown units are returned stripped."""
    text = " ".join(str(unit).split())
    lower = text.lower()
    if text in _UNITS:
        return text
    if lower in _ALIASES:
        return _ALIASES[lower]
    return _BY_LOWER.get(lower, text)


def dimension(unit: str) -> str:
    """Kind of unit ("mass", "energy", …). Unknown units form their own kind."""
    name = canonical(unit)
    if name in _UNITS:
        return _UNITS[name][0]
    return f"unknown:{name}"


def compatible(unit_a: str, unit_b: str) -> bool:
    return dimension(unit_a) == dimension(unit_b)


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert ``value`` between two units of the same kind."""
    if not compatible(from_unit, to_unit):
        raise ValidationError(
            f"Unit '{from_unit}' cannot be converted to '{to_unit}'.", field="unit"
        )
    source, target = canonical(from_unit), canonical(to_unit)
    if source == target:
        return value
    return value * _UNITS[source][1] / _UNITS[target][1]
