"""接触压力到可传转矩/轴向力的摩擦换算。

配合面为圆柱面，接触面积 ``A = 2πRL``。按库仑摩擦，最大切向承载
由摩擦系数 μ、接触压力 p 决定：

    最大轴向压入/脱出力  F = μ · p · A = μ · p · 2πRL
    最大可传转矩         T = F · R = μ · p · 2πR²L

摩擦系数一律由调用方给定，本服务不做任何经验假定。

单位：p 为 MPa（= N/mm²），R、L 为 mm，则力单位 N、转矩为 N·mm，
对外返回时转矩除以 1000 换成 N·m。
"""

from __future__ import annotations

import math


def contact_area_mm2(contact_radius_mm: float, length_mm: float) -> float:
    """圆柱配合面接触面积 A = 2πRL（mm²）。"""
    return 2.0 * math.pi * contact_radius_mm * length_mm


def max_axial_force_n(
    friction_coefficient: float,
    pressure_mpa: float,
    contact_radius_mm: float,
    length_mm: float,
) -> float:
    """摩擦所能传递的最大轴向力（N）。"""
    area = contact_area_mm2(contact_radius_mm, length_mm)
    return friction_coefficient * pressure_mpa * area


def max_transmissible_torque_nm(
    friction_coefficient: float,
    pressure_mpa: float,
    contact_radius_mm: float,
    length_mm: float,
) -> float:
    """摩擦所能传递的最大转矩（N·m）。

    T = μ·p·2πR²L，先以 N·mm 计再除以 1000。p = 0 时结果自然为 0，
    因此零过盈、μ 存在的情形下可传转矩也是零。
    """
    torque_n_mm = (
        friction_coefficient
        * pressure_mpa
        * 2.0
        * math.pi
        * contact_radius_mm**2
        * length_mm
    )
    return torque_n_mm / 1000.0
