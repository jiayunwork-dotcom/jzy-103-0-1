"""计算编排：不接触 HTTP，负责把各计算块按顺序串起来。

流程：
1. 输入合法性检查（计算前拦截，返回有效过盈量）；
2. 弹性求解（组合柔度 -> 接触压力 -> 环向应力/表面位移）；
3. 强度校核（等效应力、屈服警告）；
4. 摩擦转矩换算——已屈服时不返回转矩上限，只给名义参考值并警告。

档与临时参数的合并发生在接口层（见 :mod:`app.api`）。
"""

from __future__ import annotations

from . import elasticity, strength, torque as torque_mod
from .domain import (
    Assembly,
    FitResult,
    Geometry,
    Material,
)
from .validation import validate_calculation


def calculate(
    *,
    shaft_material: Material,
    hub_material: Material,
    geometry: Geometry,
    mechanical_interference: float,
    friction_coefficient: float | None,
    assembly: Assembly | None,
) -> FitResult:
    """执行一次完整的过盈配合核算。"""
    # 1) 计算前校验，同时拿到计入温差的有效过盈量。
    effective_interference = validate_calculation(
        shaft_material,
        hub_material,
        geometry,
        mechanical_interference,
        friction_coefficient,
        assembly,
    )
    delta_thermal = effective_interference - mechanical_interference

    # 2) 弹性求解。
    elastic = elasticity.solve_elastic(
        effective_interference, shaft_material, hub_material, geometry
    )
    pressure = elastic.contact_pressure

    # 3) 强度校核。
    shaft_assessment = strength.assess_component(
        shaft_material.label,
        elastic.shaft_hoop_stress,
        pressure,
        shaft_material.yield_strength,
    )
    hub_assessment = strength.assess_component(
        hub_material.label,
        elastic.hub_hoop_stress,
        pressure,
        hub_material.yield_strength,
    )

    warnings: list[str] = []
    notes: list[str] = []
    yielded = shaft_assessment.yielded or hub_assessment.yielded

    for assessment in (shaft_assessment, hub_assessment):
        if assessment.yielded and assessment.equivalent_stress is not None:
            warnings.append(
                f"{assessment.name}配合面等效应力 "
                f"{assessment.equivalent_stress / 1e6:.3g} MPa 超过屈服强度 "
                f"{(assessment.yield_strength or 0.0) / 1e6:.3g} MPa，"
                "配合已进入塑性，弹性接触压力公式不再成立"
            )

    if shaft_material.yield_strength is None:
        notes.append(f"未提供{shaft_material.label}的屈服强度，轴侧未做屈服判断")
    if hub_material.yield_strength is None:
        notes.append(f"未提供{hub_material.label}的屈服强度，轮毂侧未做屈服判断")
    if assembly is None:
        notes.append("未提供温差装配信息，未计入热膨胀等效过盈")
    else:
        notes.append(
            f"温差装配引起的等效径向过盈为 {delta_thermal:.6g} m，"
            f"已与机械过盈 {mechanical_interference:.6g} m 代数叠加"
        )

    # 4) 转矩换算。面积始终给出；转矩只在弹性安全且参数齐全时返回。
    area = torque_mod.contact_area(geometry.shaft_outer_radius, geometry.length)

    nominal_torque: float | None = None
    torque_capacity: float | None = None
    if friction_coefficient is not None:
        nominal_torque = torque_mod.torque_capacity(
            friction_coefficient,
            pressure,
            geometry.shaft_outer_radius,
            geometry.length,
        )
        if yielded:
            warnings.append(
                "已发生屈服，名义摩擦转矩 "
                f"{nominal_torque:.6g} N·m 仅为弹性公式外推值，"
                "不能作为可传转矩上限，torque_capacity 置为 null"
            )
        else:
            torque_capacity = nominal_torque
    else:
        notes.append("未提供摩擦系数，未计算可传转矩")

    return FitResult(
        contact_pressure=pressure,
        torque_capacity=torque_capacity,
        nominal_torque=nominal_torque,
        contact_area=area,
        shaft=shaft_assessment,
        hub=hub_assessment,
        yielded=yielded,
        warnings=tuple(warnings),
        notes=tuple(notes),
        shaft_compliance=elastic.shaft_compliance,
        hub_compliance=elastic.hub_compliance,
        combined_compliance=elastic.combined_compliance,
        shaft_radial_displacement=elastic.shaft_radial_displacement,
        hub_radial_displacement=elastic.hub_radial_displacement,
        thermal_interference=delta_thermal,
        mechanical_interference=mechanical_interference,
    )
