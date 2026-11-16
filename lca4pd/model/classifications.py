"""Fixed pick-lists used across the model."""

# Optional features chosen in the calculation setup. All can be changed later.
TOGGLES = (
    "uncertainty",
    "ghg_protocol",
    "en15804",
    "cost",
    "internal_numbers",
    "scenarios",
    "alternatives",
)

# A stage's role ties it to built-in behaviour. Stages without a role are
# user-defined and can only be used for production entries.
STAGE_ROLES = ("raw_materials", "manufacturing", "distribution", "use", "end_of_life")

DEFAULT_STAGES = (
    ("Raw materials", "raw_materials"),
    ("Manufacturing", "manufacturing"),
    ("Distribution", "distribution"),
    ("Use", "use"),
    ("End-of-Life", "end_of_life"),
)

ENTRY_TYPES = (
    "production_input",
    "production_waste",
    "production_emission",
    "cost",
    "exclusion",
    "use",
)
PRODUCTION_TYPES = ("production_input", "production_waste", "production_emission")

PATHWAY_KINDS = ("supplier", "gate_to_customer", "eol")

PARAMETER_TARGETS = ("entry", "pathway_leg", "node_weight", "node_price")

PEDIGREE_INDICATORS = (
    "reliability",
    "completeness",
    "temporal",
    "geographical",
    "technological",
)
PEDIGREE_FIELDS = tuple(f"ped_{name}" for name in PEDIGREE_INDICATORS)

GHG_CATEGORIES = {
    "1": "Scope 1 – Direct emissions",
    "2": "Scope 2 – Purchased energy",
    "3.1": "Scope 3.1 – Purchased goods and services",
    "3.2": "Scope 3.2 – Capital goods",
    "3.3": "Scope 3.3 – Fuel- and energy-related activities",
    "3.4": "Scope 3.4 – Upstream transportation and distribution",
    "3.5": "Scope 3.5 – Waste generated in operations",
    "3.6": "Scope 3.6 – Business travel",
    "3.7": "Scope 3.7 – Employee commuting",
    "3.8": "Scope 3.8 – Upstream leased assets",
    "3.9": "Scope 3.9 – Downstream transportation and distribution",
    "3.10": "Scope 3.10 – Processing of sold products",
    "3.11": "Scope 3.11 – Use of sold products",
    "3.12": "Scope 3.12 – End-of-life treatment of sold products",
    "3.13": "Scope 3.13 – Downstream leased assets",
    "3.14": "Scope 3.14 – Franchises",
    "3.15": "Scope 3.15 – Investments",
}

EN15804_MODULES = {
    "A1": "A1 – Raw material supply",
    "A2": "A2 – Transport to manufacturer",
    "A3": "A3 – Manufacturing",
    "A4": "A4 – Transport to site",
    "A5": "A5 – Installation",
    "B1": "B1 – Use",
    "B2": "B2 – Maintenance",
    "B3": "B3 – Repair",
    "B4": "B4 – Replacement",
    "B5": "B5 – Refurbishment",
    "B6": "B6 – Operational energy use",
    "B7": "B7 – Operational water use",
    "C1": "C1 – Deconstruction",
    "C2": "C2 – Transport to waste processing",
    "C3": "C3 – Waste processing",
    "C4": "C4 – Disposal",
    "D": "D – Benefits and loads beyond the system boundary",
}
