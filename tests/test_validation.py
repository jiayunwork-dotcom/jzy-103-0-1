"""输入合法性前置拦截测试：非法输入在计算前以带原因错误打回。"""

from __future__ import annotations

import pytest

from app.domain import Assembly, Geometry, Material
from app.service import calculate
from app.validation import ValidationError

STEEL_SHAFT = Material("钢轴", 2.1e11, 0.3, 250e6)
STEEL_HUB = Material("钢毂", 2.1e11, 0.3, 250e6)
GEOMETRY = Geometry(0.05, 0.0, 0.10, 0.06)


def _calc(**overrides):
    params = dict(
        shaft_material=STEEL_SHAFT,
        hub_material=STEEL_HUB,
        geometry=GEOMETRY,
        mechanical_interference=3e-5,
        friction_coefficient=0.15,
        assembly=None,
    )
    params.update(overrides)
    return calculate(**params)


def _expect_error(**overrides):
    with pytest.raises(ValidationError) as exc:
        _calc(**overrides)
    return exc.value


def test_negative_interference_rejected():
    err = _expect_error(mechanical_interference=-1e-6)
    assert err.code == "INTERFERENCE_NEGATIVE"
    assert err.field == "interference"
    assert "过盈" in err.message


def test_zero_interference_with_torque_rejected():
    err = _expect_error(mechanical_interference=0.0, friction_coefficient=0.15)
    assert err.code == "INTERFERENCE_ZERO_WITH_TORQUE"


def test_zero_interference_without_torque_allowed():
    result = _calc(mechanical_interference=0.0, friction_coefficient=None)
    assert result.contact_pressure == 0.0


def test_non_positive_radii_rejected():
    bad_outer = Geometry(0.05, 0.0, 0.0, 0.06)
    err = _expect_error(geometry=bad_outer)
    assert err.code == "HUB_OUTER_RADIUS_INVALID"

    bad_shaft = Geometry(0.0, 0.0, 0.10, 0.06)
    err = _expect_error(geometry=bad_shaft)
    assert err.code == "SHAFT_OUTER_RADIUS_INVALID"

    negative_inner = Geometry(0.05, -0.01, 0.10, 0.06)
    err = _expect_error(geometry=negative_inner)
    assert err.code == "SHAFT_INNER_RADIUS_INVALID"


def test_hub_must_be_thicker_than_interface():
    bad = Geometry(0.05, 0.0, 0.04, 0.06)
    err = _expect_error(geometry=bad)
    assert err.code == "HUB_OUTER_RADIUS_INVALID"


def test_non_positive_length_rejected():
    err = _expect_error(geometry=Geometry(0.05, 0.0, 0.10, 0.0))
    assert err.code == "LENGTH_INVALID"
    err = _expect_error(geometry=Geometry(0.05, 0.0, 0.10, -0.1))
    assert err.code == "LENGTH_INVALID"


def test_non_positive_modulus_rejected():
    err = _expect_error(shaft_material=Material("坏", 0.0, 0.3))
    assert err.code == "SHAFT_ELASTIC_MODULUS_INVALID"
    err = _expect_error(hub_material=Material("坏", -2e11, 0.3))
    assert err.code == "HUB_ELASTIC_MODULUS_INVALID"


def test_poisson_range_rejected():
    err = _expect_error(hub_material=Material("坏", 2.1e11, 0.5))
    assert err.code == "HUB_POISSON_RATIO_INVALID"
    err = _expect_error(shaft_material=Material("坏", 2.1e11, -1.0))
    assert err.code == "SHAFT_POISSON_RATIO_INVALID"


def test_negative_friction_rejected():
    err = _expect_error(friction_coefficient=-0.1)
    assert err.code == "FRICTION_COEFFICIENT_INVALID"


def test_non_finite_values_rejected():
    err = _expect_error(mechanical_interference=float("nan"))
    assert err.code == "INTERFERENCE_INVALID"
    err = _expect_error(geometry=Geometry(0.05, 0.0, float("inf"), 0.06))
    assert err.code == "HUB_OUTER_RADIUS_INVALID"


def test_negative_effective_interference_rejected():
    """机械过盈非负，但温差膨胀把它抵消成负有效过盈，仍要拦截。"""
    assembly = Assembly(
        alpha_shaft=1.2e-5,
        alpha_hub=1.2e-5,
        delta_t_shaft=0.0,
        delta_t_hub=1000.0,  # 毂孔热胀量 6e-4 m，远超 3e-5 过盈
    )
    err = _expect_error(assembly=assembly, friction_coefficient=None)
    assert err.code == "EFFECTIVE_INTERFERENCE_NEGATIVE"


def test_error_payload_carries_reason():
    err = _expect_error(mechanical_interference=-1e-6)
    payload = err.to_dict()
    assert payload["code"] and payload["message"] and payload["field"]
    assert isinstance(payload["message"], str) and payload["message"]
