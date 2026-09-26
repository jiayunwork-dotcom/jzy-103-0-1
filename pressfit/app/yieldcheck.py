"""接触面屈服校核与警告。

按开口圆筒（平面应力，轴向应力取 0）在配合面上的两个主应力
σ_θ（环向）、σ_r（径向，等于 -p）估算 von Mises 等效应力：

    σ_vm = sqrt( σ_θ² + σ_r² - σ_θ·σ_r )

只有调用方提供了材料屈服强度时才进行判据；没给就不做猜测，也不
因此阻止结果返回。等效应力超过屈服即给出明确的中文警告，编排层
据此不再把弹性接触压力乘摩擦系数当作"可传转矩上限"返回。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .elasticity import ContactSolution


def von_mises_plane_stress(stress_a: float, stress_b: float) -> float:
    """两个面内主应力下的平面应力 von Mises 等效应力（MPa）。"""
    return math.sqrt(stress_a * stress_a + stress_b * stress_b - stress_a * stress_b)


@dataclass(frozen=True)
class YieldAssessment:
    """轴、毂两侧的屈服评估结果。

    :param within_elastic: 双方是否均处于弹性区
    :param shaft_von_mises: 轴接触面等效应力（MPa）
    :param hub_von_mises: 轮毂接触面等效应力（MPa）
    :param warnings: 屈服警告文案，弹性时为空
    """

    within_elastic: bool
    shaft_von_mises: float
    hub_von_mises: float
    warnings: tuple[str, ...]


def assess_yield(
    solution: ContactSolution,
    shaft_yield_strength_mpa: float | None,
    hub_yield_strength_mpa: float | None,
) -> YieldAssessment:
    """对比轴、毂接触面等效应力与各自屈服强度，给出屈服警告。

    屈服强度为 None 的一侧不参与判据（调用方未提供，不做猜测）。
    """
    shaft_vm = von_mises_plane_stress(
        solution.shaft_hoop_stress, solution.radial_stress
    )
    hub_vm = von_mises_plane_stress(
        solution.hub_hoop_stress, solution.radial_stress
    )

    warnings: list[str] = []
    if (
        shaft_yield_strength_mpa is not None
        and shaft_vm > shaft_yield_strength_mpa
    ):
        warnings.append(
            f"轴接触面等效应力 {shaft_vm:.1f} MPa 已超过其屈服强度 "
            f"{shaft_yield_strength_mpa:.1f} MPa，轴侧进入塑性，弹性接触解失效"
        )
    if (
        hub_yield_strength_mpa is not None
        and hub_vm > hub_yield_strength_mpa
    ):
        warnings.append(
            f"轮毂接触面等效应力 {hub_vm:.1f} MPa 已超过其屈服强度 "
            f"{hub_yield_strength_mpa:.1f} MPa，毂侧进入塑性，弹性接触解失效"
        )

    return YieldAssessment(
        within_elastic=not warnings,
        shaft_von_mises=shaft_vm,
        hub_von_mises=hub_vm,
        warnings=tuple(warnings),
    )
