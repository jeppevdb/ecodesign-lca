from types import SimpleNamespace

import pytest

from lca4pd.model import Project


@pytest.fixture
def empty():
    project = Project.create(":memory:", "Test")
    yield project
    project.close()


@pytest.fixture
def lamp():
    """A small but complete project: a lamp with a housing (two parts) and a bought-in LED module.

    Returns the project plus the ids the tests need.
    """
    p = Project.create(":memory:", "Lamp")
    ids = SimpleNamespace(p=p)
    ids.eu, ids.us = p.add_market("EU"), p.add_market("US")
    db = p.add_database("process", "TestDB")
    flows = p.add_database("flow", "EF 3.1 flows")
    ids.db = db

    def ref(key, unit, database=db):
        return p.dataset_ref(database, key, name=key, unit=unit)

    ids.steel, ids.plastic = ref("steel", "kg"), ref("plastic", "kg")
    ids.moulding = ref("injection moulding", "kg")
    ids.el_eu, ids.el_us = ref("electricity EU", "kWh"), ref("electricity US", "kWh")
    ids.truck, ids.ship = ref("truck", "t*km"), ref("ship", "tkm")
    ids.recycling, ids.landfill = ref("recycling", "kg"), ref("landfill", "kg")
    ids.incineration = ref("e-waste incineration", "kg")
    ids.co2 = ref("carbon dioxide, air", "kg", flows)
    ids.raw = p.stage_by_role("raw_materials")["id"]
    ids.manufacturing = p.stage_by_role("manufacturing")["id"]

    for market, distance in ((ids.eu, 500), (ids.us, 7000)):
        gate = p.add_pathway("gate_to_customer", market_id=market)
        p.add_leg(gate, dataset_ref_id=ids.truck, amount=distance)

    ids.supplier = p.add_pathway("supplier", "LED supplier")
    p.add_leg(ids.supplier, dataset_ref_id=ids.truck, amount=400)
    p.add_leg(ids.supplier, dataset_ref_id=ids.ship, amount=1000)

    ids.eol_metal = p.add_pathway("eol", "Metal")
    ids.leg_recycling = p.add_leg(ids.eol_metal, dataset_ref_id=ids.recycling, amount=0.8)
    ids.leg_landfill = p.add_leg(ids.eol_metal, dataset_ref_id=ids.landfill, amount=0.2)
    ids.eol_ewaste = p.add_pathway("eol", "E-waste")
    p.add_leg(ids.eol_ewaste, dataset_ref_id=ids.incineration, amount=1)

    ids.lamp = p.add_node(None, "Lamp", eol_mode="split", has_use_inputs=True)
    ids.housing = p.add_node(ids.lamp, "Housing", production_site="on_site", eol_mode="split")
    ids.base = p.add_node(ids.housing, "Base", weight=1.0, production_site="on_site",
                          eol_mode="whole", eol_pathway_id=ids.eol_metal)
    ids.shade = p.add_node(ids.housing, "Shade", quantity=2, weight=0.25,
                           production_site="on_site", eol_mode="whole",
                           eol_pathway_id=ids.eol_metal)
    ids.led = p.add_node(ids.lamp, "LED module", weight=0.1, weight_is_total=True,
                         production_site="supplier", supplier_pathway_id=ids.supplier,
                         eol_mode="whole", eol_pathway_id=ids.eol_ewaste)
    ids.chip = p.add_node(ids.led, "Chip")

    ids.base_steel = p.add_entry(ids.base, "production_input", stage_id=ids.raw,
                                 dataset_ref_id=ids.steel, amount=1.05, description="Steel")
    p.add_entry(ids.shade, "production_input", stage_id=ids.raw,
                dataset_ref_id=ids.plastic, amount=250, unit="g", description="Plastic")
    p.add_entry(ids.shade, "production_input", stage_id=ids.manufacturing,
                dataset_ref_id=ids.moulding, amount=0.25, description="Moulding")
    p.add_entry(ids.chip, "production_input", stage_id=ids.raw,
                dataset_ref_id=ids.plastic, amount=0.01, description="Chip material")
    p.add_entry(ids.housing, "production_input", stage_id=ids.manufacturing,
                dataset_ref_id=ids.el_eu, amount=0.2, description="Assembly electricity")
    ids.use = p.add_entry(ids.lamp, "use", amount=120, description="Electricity in use")
    p.set_market_dataset(ids.use, ids.eu, ids.el_eu)
    p.set_market_dataset(ids.use, ids.us, ids.el_us)
    yield ids
    p.close()
