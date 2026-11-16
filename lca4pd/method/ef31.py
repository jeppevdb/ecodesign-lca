"""Environmental Footprint 3.1: impact categories, normalisation and weighting.

Normalisation factors are the global per-person values (reference year 2010,
population 6,895,889,018) and weighting factors the final EF set including
robustness, both as published by the European Commission's Joint Research
Centre (JRC) for EF 3.1. They are public reference data, not part of any
licensed database.

Single score in points = characterised result / normalisation factor
                         × weighting factor (as a fraction).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    unit: str
    normalisation: float   # characterised units per person per year
    weighting: float       # percent


CATEGORIES: tuple[Category, ...] = (
    Category("acidification", "Acidification", "mol H+ eq", 5.56e1, 6.20),
    Category("climate_change", "Climate change", "kg CO2 eq", 7.55e3, 21.06),
    Category("ecotoxicity_freshwater", "Ecotoxicity, freshwater", "CTUe", 5.67e4, 1.92),
    Category("particulate_matter", "Particulate matter", "disease incidence", 5.95e-4, 8.96),
    Category("eutrophication_marine", "Eutrophication, marine", "kg N eq", 1.95e1, 2.96),
    Category("eutrophication_freshwater", "Eutrophication, freshwater", "kg P eq", 1.61e0, 2.80),
    Category("eutrophication_terrestrial", "Eutrophication, terrestrial", "mol N eq", 1.77e2, 3.71),
    Category("human_toxicity_cancer", "Human toxicity, cancer", "CTUh", 1.73e-5, 2.13),
    Category("human_toxicity_non_cancer", "Human toxicity, non-cancer", "CTUh", 1.29e-4, 1.84),
    Category("ionising_radiation", "Ionising radiation", "kBq U235 eq", 4.22e3, 5.01),
    Category("land_use", "Land use", "pt", 8.19e5, 7.94),
    Category("ozone_depletion", "Ozone depletion", "kg CFC-11 eq", 5.23e-2, 6.31),
    Category("photochemical_ozone_formation", "Photochemical ozone formation", "kg NMVOC eq", 4.09e1, 4.78),
    Category("resource_use_fossils", "Resource use, fossils", "MJ", 6.50e4, 8.32),
    Category("resource_use_minerals_metals", "Resource use, minerals and metals", "kg Sb eq", 6.36e-2, 7.55),
    Category("water_use", "Water use", "m3 world eq", 1.15e4, 8.51),
)

CATEGORY_IDS: tuple[str, ...] = tuple(category.id for category in CATEGORIES)
BY_ID = {category.id: category for category in CATEGORIES}
N = len(CATEGORIES)

NORMALISED_UNIT = "person-year equivalent"
SINGLE_SCORE_UNIT = "Pt"


def normalised(characterised) -> list[float]:
    """Characterised results (in category order) as person-year equivalents."""
    return [value / category.normalisation for value, category in zip(characterised, CATEGORIES)]


def weighted(characterised) -> list[float]:
    """Characterised results as weighted points per category."""
    return [value / category.normalisation * category.weighting / 100
            for value, category in zip(characterised, CATEGORIES)]


def single_score(characterised) -> float:
    return sum(weighted(characterised))


def from_weighted(points) -> list[float]:
    """Characterised results calculated back from weighted points per category."""
    return [value * category.normalisation / (category.weighting / 100)
            for value, category in zip(points, CATEGORIES)]
