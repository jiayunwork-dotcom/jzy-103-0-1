"""领域数据结构：贯穿各计算模块的纯数据对象。

这些 dataclass 不依赖任何 Web 框架，弹性力学、转矩、强度等模块
直接在此结构上工作，便于脱离 HTTP 做单元测试。

几何约定（所有半径/长度单位一致，建议 SI，即 m 与 Pa）：

- ``shaft_outer_radius``: 轴的外半径 r_i（配合面半径）
- ``shaft_inner_radius``: 轴的内半径 r_si；实心轴取 0
- ``hub_outer_radius``  : 轮毂外半径 r_o
- ``length``            : 配合长度 L
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    """单一零件的线弹性材料参数。"""

    name: str
    elastic_modulus: float  # E，弹性模量，Pa
    poisson_ratio: float  # nu，泊松比，无量纲
    yield_strength: float | None = None  # sigma_y，屈服强度，Pa；不给则不做屈服判断

    @property
    def label(self) -> str:
        return self.name or "未命名材料"


@dataclass(frozen=True)
class Geometry:
    """配合几何。"""

    shaft_outer_radius: float  # r_i
    shaft_inner_radius: float  # r_si，实心轴为 0
    hub_outer_radius: float  # r_o
    length: float  # L，配合长度


@dataclass(frozen=True)
class Assembly:
    """温差（热装/冷装）信息。给了才计入，不给不编造。

    各温度均为相对装配参考温度的温升（K），可正可负：
    热装时轮毂加热 ``delta_t_hub > 0``，冷装时轴冷却
    ``delta_t_shaft < 0``。
    """

    alpha_shaft: float  # 轴的线膨胀系数，1/K
    alpha_hub: float  # 毂的线膨胀系数，1/K
    delta_t_shaft: float  # 轴的温升，K
    delta_t_hub: float  # 毂的温升，K


@dataclass(frozen=True)
class ResolvedFit:
    """一次计算最终采用的参数（已合并档/临时覆盖、已计入温差）。"""

    shaft_material: Material
    hub_material: Material
    geometry: Geometry
    interference: float  # 有效径向过盈量 delta，m（含温差贡献）
    friction_coefficient: float | None  # mu；None 表示不计算转矩


@dataclass(frozen=True)
class ComponentAssessment:
    """单个零件在配合面处的强度评估。"""

    name: str
    hoop_stress: float  # 环向（周向）应力，Pa
    contact_pressure: float  # 配合面径向压应力，Pa
    equivalent_stress: float | None  # von Mises 等效应力，Pa；未给屈服强度时为 None
    yield_strength: float | None  # 屈服强度，Pa
    yielded: bool  # 是否超过屈服


@dataclass(frozen=True)
class FitResult:
    """计算编排返回的完整结果。"""

    contact_pressure: float
    torque_capacity: float | None  # 弹性可传转矩；进入塑性或未给 mu/L 时为 None
    nominal_torque: float | None  # 仅按摩擦公式算出的名义转矩，供参考
    contact_area: float
    shaft: ComponentAssessment
    hub: ComponentAssessment
    yielded: bool
    warnings: tuple[str, ...]
    notes: tuple[str, ...]
    # 过程量：便于核对与回归
    shaft_compliance: float
    hub_compliance: float
    combined_compliance: float
    shaft_radial_displacement: float
    hub_radial_displacement: float
    thermal_interference: float
    mechanical_interference: float
