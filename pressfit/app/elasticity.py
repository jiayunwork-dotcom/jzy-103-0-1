"""弹性力学核心：Lamé 厚壁圆筒解与位移连续条件。

物理模型
--------
轴（实心或空心）与轮毂均按厚壁圆筒处理，配合面（半径 R）处：

* 轴外表面被压得径向收缩，位移大小 ``u_s``；
* 轮毂内表面被撑得径向胀开，位移大小 ``u_h``；
* 两者位移之和必须恰好等于径向过盈量 ``δ``：

    u_s(R) + u_h(R) = δ

开口圆筒（平面应力）下，Lamé 解给出配合面上的径向位移：

    u_s(R) = p · R / E_s · [ (R² + R_i²) / (R² - R_i²) - ν_s ]   # 轴
    u_h(R) = p · R / E_h · [ (R_o² + R²) / (R_o² - R²) + ν_h ]   # 轮毂

其中 ``R_i`` 为轴的内孔半径（实心轴取 0，此时括号退化为 1-ν_s），
``R_o`` 为轮毂外半径。两个方括号因子记为 κ_s、κ_h，分别代表轴和轮毂
的几何/材料柔度系数。位移连续条件给出：

    p = δ / [ R · ( κ_s/E_s + κ_h/E_h ) ]

轮毂外径越大，κ_h 越小并趋近 1+ν_h，组合柔度下降，同样过盈下 p 升高，
这正是"厚壁轮毂更难撑开"的定量表达。

配合面上的环向应力：

    轴外表面： σ_θ,s = -p · (R² + R_i²)/(R² - R_i²)   （压应力）
    毂内表面： σ_θ,h =  p · (R_o² + R²)/(R_o² - R²)   （拉应力）

配合面上径向应力两者均为 σ_r = -p。

单位制：长度 mm、应力 MPa（= N/mm²）。本模块只做封闭解析解，不依赖
任何数值求解器。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    """线弹性材料参数。

    :param elastic_modulus: 弹性模量 E，MPa
    :param poisson_ratio: 泊松比 ν
    """

    elastic_modulus: float
    poisson_ratio: float


@dataclass(frozen=True)
class ContactSolution:
    """接触面弹性解。应力以拉为正，单位 MPa。

    :param pressure: 接触压力 p（恒非负）
    :param shaft_hoop_stress: 轴外表面环向应力 σ_θ,s
    :param hub_hoop_stress: 轮毂内表面环向应力 σ_θ,h
    :param radial_stress: 配合面径向应力 σ_r，等于 -p
    """

    pressure: float
    shaft_hoop_stress: float
    hub_hoop_stress: float
    radial_stress: float


def shaft_compliance_factor(
    contact_radius: float, shaft_inner_radius: float, poisson_ratio: float
) -> float:
    """轴的无量纲柔度系数 κ_s。

    ``κ_s = (R² + R_i²)/(R² - R_i²) - ν``；实心轴（R_i = 0）退化为
    ``1 - ν``。调用前应由输入校验保证 ``0 ≤ R_i < R``。
    """
    r2 = contact_radius * contact_radius
    ri2 = shaft_inner_radius * shaft_inner_radius
    return (r2 + ri2) / (r2 - ri2) - poisson_ratio


def hub_compliance_factor(
    contact_radius: float, hub_outer_radius: float, poisson_ratio: float
) -> float:
    """轮毂的无量纲柔度系数 κ_h。

    ``κ_h = (R_o² + R²)/(R_o² - R²) + ν``；R_o 越大 κ_h 越小，
    轮毂越"硬"。调用前应由输入校验保证 ``R_o > R``。
    """
    r2 = contact_radius * contact_radius
    ro2 = hub_outer_radius * hub_outer_radius
    return (ro2 + r2) / (ro2 - r2) + poisson_ratio


def solve_contact_pressure(
    interference: float,
    contact_radius: float,
    shaft_inner_radius: float,
    hub_outer_radius: float,
    shaft: Material,
    hub: Material,
) -> ContactSolution:
    """由位移连续条件求接触压力及配合面环向应力。

    入参几何单位 mm，材料弹性模量单位 MPa，过盈量单位 mm，返回应力
    单位 MPa。几何与材料合法性由 :mod:`app.validation` 预先保证，本
    函数不再重复抛错。

    :param interference: 径向过盈量 δ（mm），可为 0，此时无接触
    :param contact_radius: 配合面标称半径 R（mm）
    :param shaft_inner_radius: 轴内孔半径 R_i（mm），实心轴取 0
    :param hub_outer_radius: 轮毂外半径 R_o（mm）
    :param shaft: 轴材料
    :param hub: 轮毂材料
    """
    # δ = 0 时无接触：压力、应力全部为零，避免任何无意义的舍入量。
    if interference == 0.0:
        return ContactSolution(
            pressure=0.0,
            shaft_hoop_stress=0.0,
            hub_hoop_stress=0.0,
            radial_stress=0.0,
        )

    kappa_s = shaft_compliance_factor(
        contact_radius, shaft_inner_radius, shaft.poisson_ratio
    )
    kappa_h = hub_compliance_factor(
        contact_radius, hub_outer_radius, hub.poisson_ratio
    )

    # 组合柔度（mm/MPa）：R·(κ_s/E_s + κ_h/E_h)
    combined_flexibility = contact_radius * (
        kappa_s / shaft.elastic_modulus + kappa_h / hub.elastic_modulus
    )
    pressure = interference / combined_flexibility

    r2 = contact_radius * contact_radius
    shaft_hoop = (
        -pressure * (r2 + shaft_inner_radius**2) / (r2 - shaft_inner_radius**2)
    )
    hub_hoop = pressure * (hub_outer_radius**2 + r2) / (
        hub_outer_radius**2 - r2
    )

    return ContactSolution(
        pressure=pressure,
        shaft_hoop_stress=shaft_hoop,
        hub_hoop_stress=hub_hoop,
        radial_stress=-pressure,
    )
