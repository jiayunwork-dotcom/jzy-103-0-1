"""弹性解的物理规律测试（位移连续/组合柔度这一块直接盯）。"""

from __future__ import annotations

import pytest

from app.elasticity import (
    Material,
    hub_compliance_factor,
    shaft_compliance_factor,
    solve_contact_pressure,
)

STEEL = Material(elastic_modulus=210_000.0, poisson_ratio=0.3)


def solve(
    interference: float,
    *,
    contact_radius: float = 25.0,
    shaft_inner_radius: float = 0.0,
    hub_outer_radius: float = 50.0,
    shaft: Material = STEEL,
    hub: Material = STEEL,
):
    return solve_contact_pressure(
        interference,
        contact_radius,
        shaft_inner_radius,
        hub_outer_radius,
        shaft,
        hub,
    )


def test_zero_interference_gives_zero_pressure_and_stresses():
    """过盈量为零：接触压力为零，配合面应力也全为零。"""
    result = solve(0.0)
    assert result.pressure == 0.0
    assert result.shaft_hoop_stress == 0.0
    assert result.hub_hoop_stress == 0.0
    assert result.radial_stress == 0.0


def test_pressure_proportional_to_interference():
    """其它条件不变，过盈量翻倍，接触压力随之翻倍。"""
    p1 = solve(0.02).pressure
    p2 = solve(0.04).pressure
    assert p1 > 0
    assert p2 == pytest.approx(2.0 * p1, rel=1e-12)


def test_thicker_hub_raises_pressure():
    """单独把轮毂加厚（外径加大），柔度下降，同过盈下压力升高。"""
    p_thin = solve(0.02, hub_outer_radius=40.0).pressure
    p_base = solve(0.02, hub_outer_radius=50.0).pressure
    p_thick = solve(0.02, hub_outer_radius=80.0).pressure
    assert p_thick > p_base > p_thin
    # 外径趋于无穷时 κ_h 趋近 1+ν，压力趋于上界，单调性严格。
    kappa_40 = hub_compliance_factor(25.0, 40.0, 0.3)
    kappa_80 = hub_compliance_factor(25.0, 80.0, 0.3)
    assert kappa_80 < kappa_40


def test_hollow_shaft_more_compliant_lowers_pressure():
    """空心轴比实心轴柔，同样过盈下压力更低。"""
    p_solid = solve(0.02, shaft_inner_radius=0.0).pressure
    p_hollow = solve(0.02, shaft_inner_radius=15.0).pressure
    assert 0 < p_hollow < p_solid
    kappa_solid = shaft_compliance_factor(25.0, 0.0, 0.3)
    kappa_hollow = shaft_compliance_factor(25.0, 15.0, 0.3)
    assert kappa_hollow > kappa_solid


def test_softer_material_raises_pressure():
    """单独降低某一侧材料模量（更柔），接触压力下降。"""
    soft_steel = Material(elastic_modulus=100_000.0, poisson_ratio=0.3)
    p_soft_shaft = solve(0.02, shaft=soft_steel).pressure
    p_base = solve(0.02).pressure
    assert p_soft_shaft < p_base


def test_hand_calc_solid_steel_shaft_contact_pressure():
    """预置算例手算值：p = 63.0 MPa，环向应力 ±63 / 105 MPa。"""
    result = solve(0.02)
    assert result.pressure > 0
    assert result.pressure == pytest.approx(63.0, abs=1e-9)
    assert result.hub_hoop_stress == pytest.approx(105.0, abs=1e-9)
    assert result.shaft_hoop_stress == pytest.approx(-63.0, abs=1e-9)
    assert result.radial_stress == pytest.approx(-63.0, abs=1e-9)
