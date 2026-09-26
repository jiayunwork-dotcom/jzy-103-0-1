"""接触压力 -> 可传转矩的换算。

配合面为圆柱面，面积 A = 2*pi*r_i*L；法向压紧力为 p*A，
最大静摩擦力为 mu*p*A，摩擦力对轴线的力臂为 r_i，故：

    T_max = mu * p * A * r_i = 2 * pi * mu * p * r_i^2 * L

摩擦系数 mu 必须由调用方给定，本模块不替调用方假定。
"""

from __future__ import annotations

import math


def contact_area(interface_radius: float, length: float) -> float:
    """圆柱配合面面积 A = 2*pi*r_i*L。"""
    return 2.0 * math.pi * interface_radius * length


def torque_capacity(
    friction_coefficient: float,
    contact_pressure: float,
    interface_radius: float,
    length: float,
) -> float:
    """按库仑摩擦计算可传转矩上限（弹性范围内成立）。"""
    area = contact_area(interface_radius, length)
    return friction_coefficient * contact_pressure * area * interface_radius
