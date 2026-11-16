import pytest

from lca4pd.model import ValidationError, units


@pytest.mark.parametrize("spelling, expected", [
    ("kg ", "kg"), ("t*km", "tkm"), ("Item(s)", "p"), ("litre", "l"),
    ("KWH", "kWh"), ("mj", "MJ"), ("ton", "t"), ("Nm3", "Nm3"),
])
def test_canonical_spelling(spelling, expected):
    assert units.canonical(spelling) == expected


def test_conversion_within_one_kind():
    assert units.convert(250, "g", "kg") == pytest.approx(0.25)
    assert units.convert(1, "kWh", "MJ") == pytest.approx(3.6)
    assert units.convert(2, "t", "kg") == pytest.approx(2000)
    assert units.convert(500, "kg*km", "tkm") == pytest.approx(0.5)


def test_conversion_across_kinds_is_refused():
    with pytest.raises(ValidationError):
        units.convert(1, "kg", "kWh")


def test_unknown_unit_only_fits_itself():
    assert units.compatible("Nm3", " Nm3 ")
    assert not units.compatible("Nm3", "m3")
