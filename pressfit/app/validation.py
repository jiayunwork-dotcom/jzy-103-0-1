"""输入合法性检查：在任何弹性计算开始之前把非法输入挡下。

校验不通过一律抛 :class:`FitValidationError`，接口层映射为带原因的
422 响应，绝不让流程跑到中途以除零等异常形式爆出难懂的栈信息。
"""

from __future__ import annotations

from .schemas import FitParams

# 各向同性材料泊松比的热力学范围 (-1, 0.5)。
_POISSON_LOW = -1.0
_POISSON_HIGH = 0.5


class FitValidationError(ValueError):
    """核算输入不合法，消息中写明原因，可能同时含多条原因。"""


def _check_material(prefix: str, material, errors: list[str]) -> None:
    if material.elastic_modulus_gpa <= 0:
        errors.append(f"{prefix}的弹性模量必须为正，收到 {material.elastic_modulus_gpa} GPa")
    if not (_POISSON_LOW < material.poisson_ratio < _POISSON_HIGH):
        errors.append(
            f"{prefix}的泊松比必须位于 ({_POISSON_LOW}, {_POISSON_HIGH}) 区间，"
            f"收到 {material.poisson_ratio}"
        )
    if (
        material.yield_strength_mpa is not None
        and material.yield_strength_mpa <= 0
    ):
        errors.append(
            f"{prefix}的屈服强度必须为正，收到 {material.yield_strength_mpa} MPa"
        )
    if (
        material.thermal_expansion_per_k is not None
        and material.thermal_expansion_per_k <= 0
    ):
        errors.append(
            f"{prefix}的线膨胀系数必须为正，收到 {material.thermal_expansion_per_k} /K"
        )


def validate_fit(params: FitParams) -> None:
    """对一次完整核算的全部输入做合法性检查。

    收集所有发现的问题后一次性抛出，避免调用方逐条试错。几何参数、
    过盈量、摩擦系数、材料常数、温差装配信息都在此挡住。
    """
    errors: list[str] = []
    geometry = params.geometry

    # --- 几何 ---
    if geometry.contact_radius_mm <= 0:
        errors.append(
            f"配合面标称半径必须为正，收到 {geometry.contact_radius_mm} mm"
        )
    if geometry.hub_outer_radius_mm <= 0:
        errors.append(
            f"轮毂外半径必须为正，收到 {geometry.hub_outer_radius_mm} mm"
        )
    if geometry.shaft_inner_radius_mm < 0:
        errors.append(
            "轴内孔半径不能为负（实心轴取 0），收到 "
            f"{geometry.shaft_inner_radius_mm} mm"
        )
    if (
        geometry.contact_radius_mm > 0
        and geometry.shaft_inner_radius_mm >= geometry.contact_radius_mm
    ):
        errors.append(
            "轴内孔半径必须严格小于配合面标称半径，收到内孔 "
            f"{geometry.shaft_inner_radius_mm} mm、标称半径 "
            f"{geometry.contact_radius_mm} mm"
        )
    if (
        geometry.contact_radius_mm > 0
        and geometry.hub_outer_radius_mm <= geometry.contact_radius_mm
    ):
        errors.append(
            "轮毂外半径必须严格大于配合面标称半径，收到外径 "
            f"{geometry.hub_outer_radius_mm} mm、标称半径 "
            f"{geometry.contact_radius_mm} mm"
        )
    if geometry.length_mm <= 0:
        errors.append(f"配合长度必须为正，收到 {geometry.length_mm} mm")

    # --- 过盈量与摩擦系数 ---
    if params.interference_mm < 0:
        errors.append(
            f"过盈量不能为负，收到 {params.interference_mm} mm；过盈量应为"
            "轴大于孔的正半径差"
        )
    if params.interference_mm == 0 and params.friction_coefficient is not None:
        errors.append(
            "过盈量为零时不产生接触压力，无法核算可传转矩；若仅需确认"
            "零过盈下的压力结果，请省略摩擦系数"
        )
    if (
        params.friction_coefficient is not None
        and params.friction_coefficient < 0
    ):
        errors.append(
            f"摩擦系数不能为负，收到 {params.friction_coefficient}"
        )

    # --- 材料 ---
    _check_material("轴", params.shaft_material, errors)
    _check_material("轮毂", params.hub_material, errors)

    # --- 温差装配 ---
    if params.thermal is not None:
        if params.shaft_material.thermal_expansion_per_k is None:
            errors.append("提供了温差装配信息，但轴材料缺少线膨胀系数，无法折算等效过盈")
        if params.hub_material.thermal_expansion_per_k is None:
            errors.append("提供了温差装配信息，但轮毂材料缺少线膨胀系数，无法折算等效过盈")

    if errors:
        raise FitValidationError("输入不合法：" + "；".join(errors))
