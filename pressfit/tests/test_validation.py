"""输入合法性检查：非法输入必须在计算开始前被带原因的错误挡下。"""

from __future__ import annotations

import pytest

from app import service
from app.schemas import ThermalInput
from app.validation import FitValidationError, validate_fit
from tests.conftest import make_params


def test_negative_interference_rejected():
    with pytest.raises(FitValidationError, match="过盈量不能为负"):
        validate_fit(make_params(interference_mm=-0.01))


def test_zero_interference_with_torque_request_rejected():
    """零过盈又给了摩擦系数（即要求算转矩）必须被拒绝。"""
    with pytest.raises(FitValidationError, match="过盈量为零"):
        validate_fit(make_params(interference_mm=0.0, friction_coefficient=0.15))


def test_zero_interference_without_friction_allowed():
    """零过盈但不要求转矩（不给摩擦系数）是合法的。"""
    validate_fit(make_params(interference_mm=0.0, friction_coefficient=None))


@pytest.mark.parametrize(
    "field,value",
    [
        ("contact_radius_mm", 0.0),
        ("contact_radius_mm", -25.0),
        ("hub_outer_radius_mm", 0.0),
        ("hub_outer_radius_mm", -50.0),
    ],
)
def test_non_positive_radius_rejected(field, value):
    with pytest.raises(FitValidationError, match="半径必须为正"):
        validate_fit(make_params(**{field: value}))


def test_hub_thinner_than_contact_rejected():
    with pytest.raises(FitValidationError, match="轮毂外半径必须严格大于"):
        validate_fit(make_params(hub_outer_radius_mm=20.0))


def test_shaft_bore_reaching_contact_rejected():
    with pytest.raises(FitValidationError, match="轴内孔半径必须严格小于"):
        validate_fit(make_params(shaft_inner_radius_mm=25.0))


def test_negative_shaft_bore_rejected():
    with pytest.raises(FitValidationError, match="轴内孔半径不能为负"):
        validate_fit(make_params(shaft_inner_radius_mm=-5.0))


def test_non_positive_length_rejected():
    with pytest.raises(FitValidationError, match="配合长度必须为正"):
        validate_fit(make_params(length_mm=0.0))
    with pytest.raises(FitValidationError, match="配合长度必须为正"):
        validate_fit(make_params(length_mm=-40.0))


@pytest.mark.parametrize("field", ["shaft_e_gpa", "hub_e_gpa"])
def test_non_positive_modulus_rejected(field):
    with pytest.raises(FitValidationError, match="弹性模量必须为正"):
        validate_fit(make_params(**{field: 0.0}))
    with pytest.raises(FitValidationError, match="弹性模量必须为正"):
        validate_fit(make_params(**{field: -210.0}))


@pytest.mark.parametrize("nu", [-1.0, 0.5, 0.6])
def test_poisson_out_of_range_rejected(nu):
    with pytest.raises(FitValidationError, match="泊松比"):
        validate_fit(make_params(shaft_nu=nu))


def test_negative_friction_rejected():
    with pytest.raises(FitValidationError, match="摩擦系数不能为负"):
        validate_fit(make_params(friction_coefficient=-0.1))


def test_non_positive_yield_rejected():
    with pytest.raises(FitValidationError, match="屈服强度必须为正"):
        validate_fit(make_params(hub_yield=0.0))


def test_thermal_without_expansion_coefficient_rejected():
    with pytest.raises(FitValidationError, match="线膨胀系数"):
        validate_fit(
            make_params(thermal=ThermalInput(hub_delta_t_k=80.0))
        )


def test_valid_preset_passes():
    validate_fit(make_params())


def test_service_raises_before_computing():
    """service 入口即校验：负过盈直接抛 FitValidationError。"""
    with pytest.raises(FitValidationError, match="过盈量不能为负"):
        service.calculate(make_params(interference_mm=-0.02))
