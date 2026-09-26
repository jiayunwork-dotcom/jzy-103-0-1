"""屈服校核与警告。

配合面处径向应力 sigma_r = -p，环向应力 sigma_t 由弹性解给出，
轴向应力按自由端面平面应力近似取 sigma_z = 0。von Mises 等效应力：

    sigma_v = sqrt(sigma_t^2 + sigma_r^2 - sigma_t*sigma_r)

代入 sigma_r = -p：

    sigma_v = sqrt(sigma_t^2 + p^2 + sigma_t*p)

未提供该零件屈服强度时不做屈服判断，只返回等效应力供调用方自行校核。
"""

from __future__ import annotations

import math

from .domain import ComponentAssessment


def equivalent_stress(hoop_stress: float, contact_pressure: float) -> float:
    """配合面处 von Mises 等效应力（平面应力近似）。"""
    sigma_r = -contact_pressure
    sigma_t = hoop_stress
    return math.sqrt(sigma_t**2 + sigma_r**2 - sigma_t * sigma_r)


def assess_component(
    name: str,
    hoop_stress: float,
    contact_pressure: float,
    yield_strength: float | None,
) -> ComponentAssessment:
    """评估单个零件：等效应力 + 是否屈服。"""
    sigma_v = equivalent_stress(hoop_stress, contact_pressure)

    if yield_strength is None:
        return ComponentAssessment(
            name=name,
            hoop_stress=hoop_stress,
            contact_pressure=contact_pressure,
            equivalent_stress=sigma_v,
            yield_strength=None,
            yielded=False,
        )

    return ComponentAssessment(
        name=name,
        hoop_stress=hoop_stress,
        contact_pressure=contact_pressure,
        equivalent_stress=sigma_v,
        yield_strength=yield_strength,
        yielded=sigma_v > yield_strength,
    )
