"""屈服校核与警告测试。"""

from __future__ import annotations

from app.domain import Geometry, Material
from app.service import calculate

STEEL_E = 2.1e11
GEOMETRY = Geometry(0.05, 0.0, 0.10, 0.06)
DELTA = 3.0e-5
MU = 0.15


def test_elastic_case_no_yield_warning():
    shaft = Material("钢轴", STEEL_E, 0.3, 250e6)
    hub = Material("钢毂", STEEL_E, 0.3, 250e6)
    result = calculate(
        shaft_material=shaft,
        hub_material=hub,
        geometry=GEOMETRY,
        mechanical_interference=DELTA,
        friction_coefficient=MU,
        assembly=None,
    )
    assert result.yielded is False
    assert result.warnings == ()
    # 弹性安全：转矩上限正常返回。
    assert result.torque_capacity is not None
    assert result.torque_capacity == result.nominal_torque


def test_yielded_torque_capacity_suppressed_with_warning():
    """进入塑性后不得把名义摩擦转矩当作可传转矩上限返回。"""
    weak_hub = Material("弱毂", STEEL_E, 0.3, 50e6)  # 50 MPa，必屈服
    shaft = Material("钢轴", STEEL_E, 0.3, 250e6)
    result = calculate(
        shaft_material=shaft,
        hub_material=weak_hub,
        geometry=GEOMETRY,
        mechanical_interference=DELTA,
        friction_coefficient=MU,
        assembly=None,
    )

    assert result.yielded is True
    assert result.hub.yielded is True
    assert result.hub.equivalent_stress > 50e6
    # 关键：转矩上限置空，名义值仅作参考并给出明确中文警告。
    assert result.torque_capacity is None
    assert result.nominal_torque is not None
    assert any("屈服" in w and "不能作为可传转矩上限" in w for w in result.warnings)


def test_missing_yield_strength_skips_judgement_with_note():
    """不给屈服强度：等效应力照算，但不判屈服、只加说明。"""
    shaft = Material("钢轴", STEEL_E, 0.3, None)
    hub = Material("钢毂", STEEL_E, 0.3, None)
    result = calculate(
        shaft_material=shaft,
        hub_material=hub,
        geometry=GEOMETRY,
        mechanical_interference=DELTA,
        friction_coefficient=MU,
        assembly=None,
    )
    assert result.yielded is False
    assert result.shaft.equivalent_stress is not None
    assert result.hub.equivalent_stress is not None
    assert any("屈服强度" in note for note in result.notes)
    # 没有屈服判据，弹性转矩照常给出。
    assert result.torque_capacity is not None


def test_hollow_thin_shaft_can_yield_first():
    """薄壁空心轴的环向压应力被放大，可先于轮毂屈服。"""
    thin_shaft_geometry = Geometry(
        shaft_outer_radius=0.05,
        shaft_inner_radius=0.045,  # 壁厚仅 5 mm
        hub_outer_radius=0.10,
        length=0.06,
    )
    shaft = Material("薄壁空心轴", STEEL_E, 0.3, 100e6)
    hub = Material("厚毂", STEEL_E, 0.3, 400e6)
    result = calculate(
        shaft_material=shaft,
        hub_material=hub,
        geometry=thin_shaft_geometry,
        mechanical_interference=DELTA,
        friction_coefficient=MU,
        assembly=None,
    )
    assert result.shaft.yielded is True
    assert result.hub.yielded is False
    assert result.torque_capacity is None
