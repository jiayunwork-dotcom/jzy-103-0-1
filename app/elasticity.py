"""弹性力学求解：位移连续 -> 组合柔度 -> 接触压力 -> 环向应力。

物理模型
========
轴的外半径与孔的内半径标称相同，半径之差为径向过盈量 ``delta``。
压合后轴表面径向内缩 |u_shaft|、毂表面径向外胀 |u_hub|，位移连续条件：

    delta = |u_hub| + |u_shaft|                ……(1)

接触面压力为 p（毂承受内压 p，轴承受外压 p）。按厚壁圆筒 Lamé 解：

轮毂（内半径 r_i、外半径 r_o，内压 p）内表面径向位移（向外为正）：

    u_hub = (p * r_i / E_h) * ( (r_o^2 + r_i^2)/(r_o^2 - r_i^2) + nu_h )

空心轴（内半径 r_si、外半径 r_i，外压 p）外表面径向位移（向外为正，
受压时为负，取绝对值）：

    u_shaft = -(p * r_i / E_s) * ( (r_i^2 + r_si^2)/(r_i^2 - r_si^2) - nu_s )

写成 u = p * r_i * C，其中 C 为各零件的“组合柔度系数”：

    C_hub = (1/E_h) * ( (r_o^2 + r_i^2)/(r_o^2 - r_i^2) + nu_h )
    C_s   = (1/E_s) * ( (r_i^2 + r_si^2)/(r_i^2 - r_si^2) - nu_s )

实心轴是空心轴 r_si -> 0 的极限：C_s = (1/E_s) * (1 - nu_s)。

代入 (1)：

    delta = p * r_i * (C_s + C_hub)
    p = delta / (r_i * (C_s + C_hub))

配合面处环向应力（拉为正）：

    毂内表面：sigma_t_hub = p * (r_o^2 + r_i^2)/(r_o^2 - r_i^2)（拉）
    轴表面  ：
      实心：sigma_t_shaft = -p（压）
      空心：sigma_t_shaft = -p * (r_i^2 + r_si^2)/(r_i^2 - r_si^2)（压）

温差装配
========
给定双方温升与线膨胀系数时，自由热膨胀导致的半径差变化记为
delta_thermal，定义为“轴的自由半径增量 − 毂孔的自由半径增量”：

    delta_thermal = alpha_s * dT_s * r_i - alpha_h * dT_h * r_i

于是有效过盈（压合后需靠弹性变形消化的半径差）为：

    delta_eff = delta_mech + delta_thermal

约定与直观一致：

- 热装（毂加热 dT_h>0、轴不加热）：孔径胀大，delta_thermal<0，
  有效过盈比机械过盈小，接触压力下降；
- 冷装（轴冷却 dT_s<0）：轴径缩得更小，delta_thermal<0，同理；
- 装配冷却到参考温度后，有效过盈回到机械过盈。

本服务只在调用方给定温差信息时才叠加，是否合理由调用方负责。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .domain import Assembly, Geometry, Material

SOLID_SHAFT_INNER_RADIUS = 0.0


@dataclass(frozen=True)
class ElasticSolution:
    """弹性求解的全部输出。"""

    contact_pressure: float
    shaft_hoop_stress: float
    hub_hoop_stress: float
    shaft_compliance: float
    hub_compliance: float
    combined_compliance: float
    shaft_radial_displacement: float
    hub_radial_displacement: float


def is_solid_shaft(geometry: Geometry, *, tol: float = 1e-12) -> bool:
    """轴内半径为 0（或数值意义上的 0）视为实心轴。"""
    return geometry.shaft_inner_radius <= tol * max(geometry.shaft_outer_radius, 1.0)


def shaft_compliance(shaft_material: Material, geometry: Geometry) -> float:
    """轴的柔度系数 C_s（单位 1/Pa）。"""
    r_i = geometry.shaft_outer_radius
    e_s = shaft_material.elastic_modulus
    nu_s = shaft_material.poisson_ratio

    if is_solid_shaft(geometry):
        return (1.0 - nu_s) / e_s

    r_si = geometry.shaft_inner_radius
    ratio_term = (r_i**2 + r_si**2) / (r_i**2 - r_si**2)
    return (ratio_term - nu_s) / e_s


def hub_compliance(hub_material: Material, geometry: Geometry) -> float:
    """轮毂的柔度系数 C_h（单位 1/Pa）。"""
    r_i = geometry.shaft_outer_radius
    r_o = geometry.hub_outer_radius
    e_h = hub_material.elastic_modulus
    nu_h = hub_material.poisson_ratio

    ratio_term = (r_o**2 + r_i**2) / (r_o**2 - r_i**2)
    return (ratio_term + nu_h) / e_h


def combined_compliance(
    shaft_material: Material, hub_material: Material, geometry: Geometry
) -> float:
    """组合柔度系数 C_s + C_h。"""
    return shaft_compliance(shaft_material, geometry) + hub_compliance(
        hub_material, geometry
    )


def contact_pressure(
    interference: float,
    shaft_material: Material,
    hub_material: Material,
    geometry: Geometry,
) -> float:
    """由位移连续条件解接触压力 p = delta / (r_i * (C_s + C_h))。

    过盈量为零时按连续条件直接得零压力，不依赖分母（同时避免
    极端参数下的无意义运算）。
    """
    if interference == 0.0:
        return 0.0
    compliance = combined_compliance(shaft_material, hub_material, geometry)
    return interference / (geometry.shaft_outer_radius * compliance)


def shaft_hoop_stress(pressure: float, geometry: Geometry) -> float:
    """轴在配合面处的环向应力（压应力，负值）。"""
    r_i = geometry.shaft_outer_radius
    if is_solid_shaft(geometry):
        return -pressure
    r_si = geometry.shaft_inner_radius
    ratio_term = (r_i**2 + r_si**2) / (r_i**2 - r_si**2)
    return -pressure * ratio_term


def hub_hoop_stress(pressure: float, geometry: Geometry) -> float:
    """毂在配合面处的环向应力（拉应力，正值）。"""
    r_i = geometry.shaft_outer_radius
    r_o = geometry.hub_outer_radius
    ratio_term = (r_o**2 + r_i**2) / (r_o**2 - r_i**2)
    return pressure * ratio_term


def solve_elastic(
    interference: float,
    shaft_material: Material,
    hub_material: Material,
    geometry: Geometry,
) -> ElasticSolution:
    """完整弹性求解：接触压力、双方环向应力、柔度与表面位移。"""
    c_s = shaft_compliance(shaft_material, geometry)
    c_h = hub_compliance(hub_material, geometry)
    c_total = c_s + c_h
    r_i = geometry.shaft_outer_radius

    pressure = 0.0 if interference == 0.0 else interference / (r_i * c_total)

    # 位移连续校验量：u_shaft 为内缩量（取正），u_hub 为外胀量。
    u_shaft = pressure * r_i * c_s
    u_hub = pressure * r_i * c_h

    return ElasticSolution(
        contact_pressure=pressure,
        shaft_hoop_stress=shaft_hoop_stress(pressure, geometry),
        hub_hoop_stress=hub_hoop_stress(pressure, geometry),
        shaft_compliance=c_s,
        hub_compliance=c_h,
        combined_compliance=c_total,
        shaft_radial_displacement=u_shaft,
        hub_radial_displacement=u_hub,
    )


def thermal_interference(assembly: Assembly, interface_radius: float) -> float:
    """温差引起的等效径向过盈量（m）。

    返回轴自由半径增量减毂孔自由半径增量；热装/冷装时为负，
    与机械过盈代数相加即为有效过盈。
    """
    shaft_growth = assembly.alpha_shaft * assembly.delta_t_shaft * interface_radius
    hub_growth = assembly.alpha_hub * assembly.delta_t_hub * interface_radius
    return shaft_growth - hub_growth
