"""钉死力学关系的自动化测试（需求逐条对应）：

1. 过盈量为零 -> 接触压力为零、可传转矩为零；
2. 过盈量翻倍 -> 接触压力与可传转矩同步翻倍；
3. 摩擦系数单独翻倍 -> 可传转矩翻倍，接触压力不变；
4. 轮毂加厚（外径加大）-> 组合柔度下降、同过盈下接触压力升高；
5. 预置钢轴—钢毂手算算例作为回归基准，接触压力为正。
"""

from __future__ import annotations

import pytest

from app import presets
from app.domain import Assembly, Geometry, Material
from app.elasticity import combined_compliance, solve_elastic, thermal_interference
from app.service import calculate
from app.torque import torque_capacity

STEEL_SHAFT = Material("钢轴", 2.1e11, 0.3, 250e6)
STEEL_HUB = Material("钢毂", 2.1e11, 0.3, 250e6)
BASE_GEOMETRY = Geometry(
    shaft_outer_radius=0.05,
    shaft_inner_radius=0.0,
    hub_outer_radius=0.10,
    length=0.06,
)
DELTA = 3.0e-5
MU = 0.15


def _run(delta: float, mu: float | None, geometry: Geometry = BASE_GEOMETRY):
    return calculate(
        shaft_material=STEEL_SHAFT,
        hub_material=STEEL_HUB,
        geometry=geometry,
        mechanical_interference=delta,
        friction_coefficient=mu,
        assembly=None,
    )


def test_zero_interference_gives_zero_pressure_and_torque():
    """关系 1：零过盈时 p=0；给 mu 算转矩会被前置拦截，
    退化核对（不给 mu）下名义转矩亦为零。"""
    result = _run(0.0, None)
    assert result.contact_pressure == 0.0
    assert result.torque_capacity is None
    assert result.contact_area > 0

    # 直接在换算层钉住：零压力乘进摩擦公式，转矩就是零。
    assert (
        torque_capacity(
            MU,
            result.contact_pressure,
            BASE_GEOMETRY.shaft_outer_radius,
            BASE_GEOMETRY.length,
        )
        == 0.0
    )

    # 零过盈却又要求算转矩：计算前带原因打回。
    from app.validation import ValidationError

    with pytest.raises(ValidationError) as exc:
        _run(0.0, MU)
    assert exc.value.code == "INTERFERENCE_ZERO_WITH_TORQUE"


def test_doubling_interference_doubles_pressure_and_torque():
    """关系 2：过盈翻倍，压力与可传转矩同步翻倍（线性弹性）。"""
    base = _run(DELTA, MU)
    doubled = _run(2 * DELTA, MU)

    assert doubled.contact_pressure == pytest.approx(2 * base.contact_pressure, rel=1e-12)
    assert doubled.torque_capacity == pytest.approx(
        2 * base.torque_capacity, rel=1e-12
    )
    # 摩擦与几何未动，转矩/压力比值保持不变。
    assert doubled.torque_capacity / doubled.contact_pressure == pytest.approx(
        base.torque_capacity / base.contact_pressure, rel=1e-12
    )


def test_doubling_friction_doubles_torque_only():
    """关系 3：摩擦系数单独翻倍，转矩翻倍，接触压力保持不变。"""
    base = _run(DELTA, MU)
    double_mu = _run(DELTA, 2 * MU)

    assert double_mu.contact_pressure == pytest.approx(
        base.contact_pressure, rel=1e-12, abs=0.0
    )
    assert double_mu.torque_capacity == pytest.approx(
        2 * base.torque_capacity, rel=1e-12
    )


@pytest.mark.parametrize("outer", [0.075, 0.10, 0.15, 0.25, 0.50])
def test_thicker_hub_raises_pressure_against_reference(outer):
    """关系 4：与固定参考（r_o=0.10）比，外径更大则压力更高、柔度更低；
    外径更小则相反。"""
    geometry = Geometry(0.05, 0.0, outer, 0.06)
    compliance = combined_compliance(STEEL_SHAFT, STEEL_HUB, geometry)
    pressure = solve_elastic(DELTA, STEEL_SHAFT, STEEL_HUB, geometry).contact_pressure

    c_ref = combined_compliance(STEEL_SHAFT, STEEL_HUB, BASE_GEOMETRY)
    p_ref = solve_elastic(DELTA, STEEL_SHAFT, STEEL_HUB, BASE_GEOMETRY).contact_pressure

    if outer > 0.10:
        assert compliance < c_ref
        assert pressure > p_ref
    elif outer < 0.10:
        assert compliance > c_ref
        assert pressure < p_ref
    else:
        assert pressure == pytest.approx(p_ref, rel=1e-12)
    assert pressure > 0.0


def test_compliance_monotonic_in_hub_thickness():
    """随轮毂外径单调加大，组合柔度严格递减、接触压力严格递增。"""
    outers = [0.06, 0.08, 0.10, 0.15, 0.30, 1.0, 10.0]
    compliances = []
    pressures = []
    for outer in outers:
        geometry = Geometry(0.05, 0.0, outer, 0.06)
        compliances.append(combined_compliance(STEEL_SHAFT, STEEL_HUB, geometry))
        pressures.append(solve_elastic(DELTA, STEEL_SHAFT, STEEL_HUB, geometry).contact_pressure)

    for prev, nxt in zip(compliances, compliances[1:]):
        assert nxt < prev
    for prev, nxt in zip(pressures, pressures[1:]):
        assert nxt > prev


def test_displacement_continuity_closes():
    """位移连续：轴内缩量 + 毂外胀量必须正好等于过盈量。"""
    result = _run(DELTA, None)
    solution = solve_elastic(DELTA, STEEL_SHAFT, STEEL_HUB, BASE_GEOMETRY)
    total = solution.shaft_radial_displacement + solution.hub_radial_displacement
    assert total == pytest.approx(DELTA, rel=1e-12)
    assert result.shaft_radial_displacement + result.hub_radial_displacement == pytest.approx(
        DELTA, rel=1e-12
    )


def test_preset_steel_demo_regression():
    """关系 5：预置手算基准，数值钉死。"""
    result = calculate(
        shaft_material=presets.STEEL_SHAFT,
        hub_material=presets.STEEL_HUB,
        geometry=presets.DEMO_GEOMETRY,
        mechanical_interference=presets.DEMO_INTERFERENCE,
        friction_coefficient=presets.DEMO_FRICTION,
        assembly=None,
    )

    assert result.contact_pressure > 0
    assert result.contact_pressure == pytest.approx(
        presets.EXPECTED_CONTACT_PRESSURE, rel=1e-12
    )
    assert result.shaft.hoop_stress == pytest.approx(presets.EXPECTED_SHAFT_HOOP, rel=1e-12)
    assert result.hub.hoop_stress == pytest.approx(presets.EXPECTED_HUB_HOOP, rel=1e-12)
    assert result.hub.equivalent_stress == pytest.approx(
        presets.EXPECTED_HUB_VON_MISES, rel=1e-12
    )
    assert result.torque_capacity == pytest.approx(presets.EXPECTED_TORQUE, rel=1e-12)
    assert result.yielded is False
    assert result.warnings == ()


def test_hollow_shaft_limits_to_solid():
    """空心轴公式在内半径趋于 0 时必须收敛到实心轴结果。"""
    solid = solve_elastic(DELTA, STEEL_SHAFT, STEEL_HUB, BASE_GEOMETRY)
    nearly_solid = Geometry(0.05, 1.0e-9, 0.10, 0.06)
    hollow = solve_elastic(DELTA, STEEL_SHAFT, STEEL_HUB, nearly_solid)

    assert hollow.contact_pressure == pytest.approx(solid.contact_pressure, rel=1e-9)
    assert hollow.shaft_hoop_stress == pytest.approx(solid.shaft_hoop_stress, rel=1e-7)


def test_thermal_interference_only_when_given():
    """温差信息：给了才叠加；热装使有效过盈下降，压力随之下降。"""
    cold = _run(DELTA, MU)
    assembly = Assembly(
        alpha_shaft=1.2e-5,
        alpha_hub=1.2e-5,
        delta_t_shaft=0.0,
        delta_t_hub=20.0,  # 轮毂加热 20 K，孔径胀大 1.2e-5 m（仍小于机械过盈）
    )
    delta_t = thermal_interference(assembly, BASE_GEOMETRY.shaft_outer_radius)
    # 约定：轴增长 − 毂增长；热装时为负。
    assert delta_t == pytest.approx(-1.2e-5 * 20 * 0.05, rel=1e-12)

    hot = calculate(
        shaft_material=STEEL_SHAFT,
        hub_material=STEEL_HUB,
        geometry=BASE_GEOMETRY,
        mechanical_interference=DELTA,
        friction_coefficient=MU,
        assembly=assembly,
    )
    assert hot.thermal_interference < 0
    assert hot.contact_pressure < cold.contact_pressure
    # 有效过盈 = 机械过盈 + 带符号热过盈（此处为减量）；压力线性正比。
    assert hot.contact_pressure == pytest.approx(
        cold.contact_pressure * (DELTA + delta_t) / DELTA, rel=1e-12
    )
