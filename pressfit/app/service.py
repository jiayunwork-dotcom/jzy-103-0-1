"""计算编排：温差等效过盈、依次调用各计算块、拼装对外结果。

顺序固定为：输入校验 → 温差等效过盈 → Lamé 接触解 → 屈服校核 →
摩擦转矩换算（仅弹性区才给）。
"""

from __future__ import annotations

from . import elasticity, torque
from .schemas import CalculateResponse, FitParams, InterfaceStress
from .validation import validate_fit
from .yieldcheck import assess_yield


def _effective_interference(params: FitParams) -> tuple[float, str | None]:
    """把温差装配折算成等效径向过盈并叠加。

    未提供温差信息时原样返回常温过盈，绝不自行编造温差。温差把过盈
    抵消到 ≤ 0 时按无接触处理（等效过盈取 0 并附说明）。
    """
    base = params.interference_mm
    if params.thermal is None:
        return base, None

    alpha_h = params.hub_material.thermal_expansion_per_k
    alpha_s = params.shaft_material.thermal_expansion_per_k
    radius = params.geometry.contact_radius_mm
    # 加热轮毂（ΔT_h>0）、冷却轴（ΔT_s<0）都增大可装配过盈。
    thermal_delta = (
        alpha_h * params.thermal.hub_delta_t_k
        - alpha_s * params.thermal.shaft_delta_t_k
    ) * radius
    effective = base + thermal_delta
    if effective <= 0.0:
        return 0.0, (
            "温差效应已抵消全部常温过盈（等效过盈 "
            f"{effective:.4f} mm ≤ 0），按无接触、接触压力为零处理"
        )
    return effective, None


def calculate(params: FitParams) -> CalculateResponse:
    """执行一次完整的过盈配合核算。

    :raises FitValidationError: 输入不合法（计算开始前抛出）
    """
    # 1) 先校验，任何后续公式都不会面对非法几何/材料。
    validate_fit(params)

    geometry = params.geometry
    warnings: list[str] = []

    # 2) 温差等效过盈（没给温差就保持常温过盈）。
    effective_interference, thermal_note = _effective_interference(params)
    if thermal_note is not None:
        warnings.append(thermal_note)

    # 3) 位移连续 → 接触压力与配合面应力。GPa → MPa（×1000）。
    shaft = elasticity.Material(
        elastic_modulus=params.shaft_material.elastic_modulus_gpa * 1000.0,
        poisson_ratio=params.shaft_material.poisson_ratio,
    )
    hub = elasticity.Material(
        elastic_modulus=params.hub_material.elastic_modulus_gpa * 1000.0,
        poisson_ratio=params.hub_material.poisson_ratio,
    )
    solution = elasticity.solve_contact_pressure(
        interference=effective_interference,
        contact_radius=geometry.contact_radius_mm,
        shaft_inner_radius=geometry.shaft_inner_radius_mm,
        hub_outer_radius=geometry.hub_outer_radius_mm,
        shaft=shaft,
        hub=hub,
    )

    # 4) 屈服校核（未给屈服强度的一侧不参与判据）。
    assessment = assess_yield(
        solution,
        shaft_yield_strength_mpa=params.shaft_material.yield_strength_mpa,
        hub_yield_strength_mpa=params.hub_material.yield_strength_mpa,
    )
    warnings.extend(assessment.warnings)

    # 5) 摩擦转矩：只在调用方给了摩擦系数且接触面仍处弹性区时给出。
    max_torque_nm: float | None = None
    max_force_n: float | None = None
    if params.friction_coefficient is not None:
        if assessment.within_elastic:
            max_torque_nm = torque.max_transmissible_torque_nm(
                friction_coefficient=params.friction_coefficient,
                pressure_mpa=solution.pressure,
                contact_radius_mm=geometry.contact_radius_mm,
                length_mm=geometry.length_mm,
            )
            max_force_n = torque.max_axial_force_n(
                friction_coefficient=params.friction_coefficient,
                pressure_mpa=solution.pressure,
                contact_radius_mm=geometry.contact_radius_mm,
                length_mm=geometry.length_mm,
            )
        else:
            warnings.append(
                "接触面已进入塑性，不按弹性接触压力乘摩擦系数外推可传"
                "转矩，max_transmissible_torque_nm 置为 null"
            )

    return CalculateResponse(
        contact_pressure_mpa=solution.pressure,
        effective_interference_mm=effective_interference,
        max_transmissible_torque_nm=max_torque_nm,
        max_axial_force_n=max_force_n,
        shaft_interface_stress=InterfaceStress(
            hoop_mpa=solution.shaft_hoop_stress,
            radial_mpa=solution.radial_stress,
            von_mises_mpa=assessment.shaft_von_mises,
        ),
        hub_interface_stress=InterfaceStress(
            hoop_mpa=solution.hub_hoop_stress,
            radial_mpa=solution.radial_stress,
            von_mises_mpa=assessment.hub_von_mises,
        ),
        within_elastic=assessment.within_elastic,
        warnings=warnings,
    )
