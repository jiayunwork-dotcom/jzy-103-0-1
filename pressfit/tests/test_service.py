"""编排层（service）物理规律与温差装配测试。"""

from __future__ import annotations

import pytest

from app import service
from app.schemas import ThermalInput
from tests.conftest import make_params


def test_zero_interference_gives_zero_pressure_and_torque():
    """过盈量为零：接触压力必须为零、可传转矩也为零。

    编排层规则是"零过盈 + 给了摩擦系数"在计算前被 422 挡下，因此
    这里走"零过盈、不给摩擦系数"路径：压力为零，转矩字段为 null；
    换算块在 p=0 下天然给出 0（见 test_torque.py）。
    """
    result = service.calculate(
        make_params(interference_mm=0.0, friction_coefficient=None)
    )
    assert result.contact_pressure_mpa == 0.0
    assert result.max_transmissible_torque_nm is None
    assert result.shaft_interface_stress.hoop_mpa == 0.0
    assert result.hub_interface_stress.hoop_mpa == 0.0


def test_doubling_interference_doubles_pressure_and_torque():
    """其它条件不变，过盈量翻倍，接触压力与可传转矩同步翻倍。"""
    base = service.calculate(make_params(interference_mm=0.02))
    doubled = service.calculate(make_params(interference_mm=0.04))
    assert doubled.contact_pressure_mpa == pytest.approx(
        2.0 * base.contact_pressure_mpa, rel=1e-12
    )
    assert doubled.max_transmissible_torque_nm == pytest.approx(
        2.0 * base.max_transmissible_torque_nm, rel=1e-12
    )


def test_doubling_friction_doubles_torque_but_not_pressure():
    """单独把摩擦系数翻倍：转矩翻倍，接触压力纹丝不动。"""
    base = service.calculate(make_params(friction_coefficient=0.10))
    doubled = service.calculate(make_params(friction_coefficient=0.20))
    assert doubled.max_transmissible_torque_nm == pytest.approx(
        2.0 * base.max_transmissible_torque_nm, rel=1e-12
    )
    assert doubled.contact_pressure_mpa == pytest.approx(
        base.contact_pressure_mpa, rel=1e-12
    )


def test_thicker_hub_raises_pressure_same_interference():
    """单独把轮毂加厚，同样过盈下接触压力升高。"""
    thin = service.calculate(make_params(hub_outer_radius_mm=40.0))
    thick = service.calculate(make_params(hub_outer_radius_mm=80.0))
    assert thick.contact_pressure_mpa > thin.contact_pressure_mpa


def test_thermal_expansion_adds_equivalent_interference():
    """温差装配：加热轮毂 80 K，等效过盈叠加 12e-6×80×25 = 0.024 mm。"""
    params = make_params(
        shaft_alpha=12e-6,
        hub_alpha=12e-6,
        thermal=ThermalInput(hub_delta_t_k=80.0),
    )
    result = service.calculate(params)
    assert result.effective_interference_mm == pytest.approx(0.044, rel=1e-12)
    # 压力随等效过盈线性放大：63 × 0.044/0.02 = 138.6 MPa。
    assert result.contact_pressure_mpa == pytest.approx(138.6, rel=1e-9)


def test_thermal_cooling_shaft_also_adds_interference():
    """冷却轴（ΔT_s 为负）同样增大等效过盈。"""
    params = make_params(
        shaft_alpha=12e-6,
        hub_alpha=12e-6,
        thermal=ThermalInput(shaft_delta_t_k=-80.0),
    )
    result = service.calculate(params)
    assert result.effective_interference_mm == pytest.approx(0.044, rel=1e-12)


def test_no_thermal_info_no_fabrication():
    """未提供温差信息时，等效过盈就是常温过盈，不自行编造。"""
    result = service.calculate(make_params())
    assert result.effective_interference_mm == pytest.approx(0.02)
    assert result.warnings == []


def test_thermal_canceling_interference_gives_zero_pressure():
    """温差把过盈抵消干净时按无接触处理并附说明，不得算出负压力。"""
    params = make_params(
        shaft_alpha=12e-6,
        hub_alpha=12e-6,
        thermal=ThermalInput(hub_delta_t_k=-100.0),  # -0.03 mm，净 -0.01
    )
    result = service.calculate(params)
    assert result.effective_interference_mm == 0.0
    assert result.contact_pressure_mpa == 0.0
    assert any("抵消" in w for w in result.warnings)
