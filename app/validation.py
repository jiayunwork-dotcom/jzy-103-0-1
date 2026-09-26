"""输入合法性检查：所有非法输入必须在力学计算开始前拦截。

错误以 :class:`ValidationError` 抛出，携带错误码、中文原因与出错字段，
接口层统一转成带原因的 422 响应，绝不让计算跑到中途因除零等抛出
看不懂的栈信息。
"""

from __future__ import annotations

import math
from typing import Any

from .domain import Assembly, Geometry, Material
from .elasticity import thermal_interference

# 泊松比取开区间：-1 < nu < 0.5（0.5 为不可压缩极限，避开退化）。
POISSON_LOWER = -1.0
POISSON_UPPER = 0.5


class ValidationError(Exception):
    """带错误码与原因的输入校验错误（接口层映射为 422）。"""

    def __init__(self, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "field": self.field, "message": self.message}


def _require_finite(value: float, code: str, message: str, field: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValidationError(code, message, field)


def validate_material(material: Material, role: str) -> None:
    """校验单个零件的材料参数。role 为 'shaft' / 'hub'，用于定位字段。"""
    prefix = "轴" if role == "shaft" else "轮毂"

    _require_finite(
        material.elastic_modulus,
        f"{role.upper()}_ELASTIC_MODULUS_INVALID",
        f"{prefix}弹性模量必须是有限数值",
        f"{role}.elastic_modulus",
    )
    if material.elastic_modulus <= 0:
        raise ValidationError(
            f"{role.upper()}_ELASTIC_MODULUS_INVALID",
            f"{prefix}弹性模量必须为正，收到 {material.elastic_modulus:g}",
            f"{role}.elastic_modulus",
        )

    _require_finite(
        material.poisson_ratio,
        f"{role.upper()}_POISSON_RATIO_INVALID",
        f"{prefix}泊松比必须是有限数值",
        f"{role}.poisson_ratio",
    )
    if not (POISSON_LOWER < material.poisson_ratio < POISSON_UPPER):
        raise ValidationError(
            f"{role.upper()}_POISSON_RATIO_INVALID",
            f"{prefix}泊松比必须在 ({POISSON_LOWER:g}, {POISSON_UPPER:g}) 开区间内，"
            f"收到 {material.poisson_ratio:g}",
            f"{role}.poisson_ratio",
        )

    if material.yield_strength is not None:
        _require_finite(
            material.yield_strength,
            f"{role.upper()}_YIELD_STRENGTH_INVALID",
            f"{prefix}屈服强度必须是有限数值或省略",
            f"{role}.yield_strength",
        )
        if material.yield_strength <= 0:
            raise ValidationError(
                f"{role.upper()}_YIELD_STRENGTH_INVALID",
                f"{prefix}屈服强度若给定必须为正，收到 {material.yield_strength:g}",
                f"{role}.yield_strength",
            )


def validate_geometry(geometry: Geometry) -> None:
    """校验配合几何。"""
    _require_finite(
        geometry.shaft_outer_radius,
        "SHAFT_OUTER_RADIUS_INVALID",
        "轴外半径必须是有限数值",
        "geometry.shaft_outer_radius",
    )
    if geometry.shaft_outer_radius <= 0:
        raise ValidationError(
            "SHAFT_OUTER_RADIUS_INVALID",
            f"轴外半径必须为正，收到 {geometry.shaft_outer_radius:g}",
            "geometry.shaft_outer_radius",
        )

    _require_finite(
        geometry.shaft_inner_radius,
        "SHAFT_INNER_RADIUS_INVALID",
        "轴内半径必须是有限数值（实心轴填 0）",
        "geometry.shaft_inner_radius",
    )
    if geometry.shaft_inner_radius < 0:
        raise ValidationError(
            "SHAFT_INNER_RADIUS_INVALID",
            f"轴内半径不允许为负（实心轴填 0），收到 {geometry.shaft_inner_radius:g}",
            "geometry.shaft_inner_radius",
        )
    if geometry.shaft_inner_radius >= geometry.shaft_outer_radius:
        raise ValidationError(
            "SHAFT_INNER_RADIUS_INVALID",
            "轴内半径必须严格小于轴外半径",
            "geometry.shaft_inner_radius",
        )

    _require_finite(
        geometry.hub_outer_radius,
        "HUB_OUTER_RADIUS_INVALID",
        "轮毂外半径必须是有限数值",
        "geometry.hub_outer_radius",
    )
    if geometry.hub_outer_radius <= 0:
        raise ValidationError(
            "HUB_OUTER_RADIUS_INVALID",
            f"轮毂外半径必须为正，收到 {geometry.hub_outer_radius:g}",
            "geometry.hub_outer_radius",
        )
    if geometry.hub_outer_radius <= geometry.shaft_outer_radius:
        raise ValidationError(
            "HUB_OUTER_RADIUS_INVALID",
            "轮毂外半径必须严格大于轴外半径（配合面半径），否则厚壁圆筒公式不成立",
            "geometry.hub_outer_radius",
        )

    _require_finite(
        geometry.length,
        "LENGTH_INVALID",
        "配合长度必须是有限数值",
        "geometry.length",
    )
    if geometry.length <= 0:
        raise ValidationError(
            "LENGTH_INVALID",
            f"配合长度必须为正，收到 {geometry.length:g}",
            "geometry.length",
        )


def validate_assembly(assembly: Assembly | None) -> None:
    """校验温差装配信息（不给则不校验、不编造）。"""
    if assembly is None:
        return
    fields = (
        ("alpha_shaft", assembly.alpha_shaft, "轴的线膨胀系数"),
        ("alpha_hub", assembly.alpha_hub, "轮毂的线膨胀系数"),
        ("delta_t_shaft", assembly.delta_t_shaft, "轴相对装配参考温度的温升"),
        ("delta_t_hub", assembly.delta_t_hub, "轮毂相对装配参考温度的温升"),
    )
    for field_name, value, label in fields:
        _require_finite(
            value,
            "ASSEMBLY_VALUE_INVALID",
            f"{label}必须是有限数值",
            f"assembly.{field_name}",
        )


def validate_calculation(
    shaft_material: Material,
    hub_material: Material,
    geometry: Geometry,
    mechanical_interference: float,
    friction_coefficient: float | None,
    assembly: Assembly | None,
) -> float:
    """计算前的完整校验，返回计入温差后的有效过盈量。"""
    validate_material(shaft_material, "shaft")
    validate_material(hub_material, "hub")
    validate_geometry(geometry)
    validate_assembly(assembly)

    _require_finite(
        mechanical_interference,
        "INTERFERENCE_INVALID",
        "机械过盈量必须是有限数值",
        "interference",
    )
    if mechanical_interference < 0:
        raise ValidationError(
            "INTERFERENCE_NEGATIVE",
            f"机械过盈量不允许为负，收到 {mechanical_interference:g}；"
            "负值意味着轴比孔小，不属于过盈配合",
            "interference",
        )

    if friction_coefficient is not None:
        _require_finite(
            friction_coefficient,
            "FRICTION_COEFFICIENT_INVALID",
            "摩擦系数必须是有限数值或省略",
            "friction_coefficient",
        )
        if friction_coefficient < 0:
            raise ValidationError(
                "FRICTION_COEFFICIENT_INVALID",
                f"摩擦系数不允许为负，收到 {friction_coefficient:g}",
                "friction_coefficient",
            )

    delta_t = (
        thermal_interference(assembly, geometry.shaft_outer_radius)
        if assembly is not None
        else 0.0
    )
    effective = mechanical_interference + delta_t

    if effective < 0:
        raise ValidationError(
            "EFFECTIVE_INTERFERENCE_NEGATIVE",
            "叠加温差膨胀后有效过盈量为负，装配时无法形成接触压力；"
            f"机械过盈 {mechanical_interference:g}，温差等效过盈 {delta_t:g}",
            "interference",
        )

    if effective == 0.0 and friction_coefficient is not None:
        raise ValidationError(
            "INTERFERENCE_ZERO_WITH_TORQUE",
            "有效过盈量为零时接触压力必为零，不能要求按摩擦计算可传转矩；"
            "若只做零过盈的退化核对，请省略 friction_coefficient",
            "interference",
        )

    return effective
