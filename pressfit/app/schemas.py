"""HTTP 请求/响应数据模型（Pydantic v2）。

所有长度以 mm 计、弹性模量以 GPa 计、应力以 MPa 计、转矩以 N·m 计。
字段的取值范围（为正、几何包含关系等）不在模型层做硬约束，而是由
:mod:`app.validation` 统一给出带中文原因的错误响应。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MaterialInput(BaseModel):
    """一种配合零件的材料参数。"""

    model_config = ConfigDict(allow_inf_nan=False)

    elastic_modulus_gpa: float = Field(..., description="弹性模量 E，GPa")
    poisson_ratio: float = Field(..., description="泊松比 ν")
    yield_strength_mpa: float | None = Field(
        default=None, description="屈服强度，MPa；不提供则不做屈服校核"
    )
    thermal_expansion_per_k: float | None = Field(
        default=None,
        description="平均线膨胀系数 α，1/K；使用温差装配时必须提供",
    )


class GeometryInput(BaseModel):
    """配合几何参数（mm）。"""

    model_config = ConfigDict(allow_inf_nan=False)

    contact_radius_mm: float = Field(
        ..., description="配合面标称半径 R（轴外半径/孔内半径）"
    )
    shaft_inner_radius_mm: float = Field(
        default=0.0, description="轴的内孔半径，实心轴取 0"
    )
    hub_outer_radius_mm: float = Field(..., description="轮毂外半径 R_o")
    length_mm: float = Field(..., description="配合（接触）长度 L")


class ThermalInput(BaseModel):
    """温差装配信息（K）。均为相对装配环境温度的温升，正为加热。

    等效过盈增量为 ``(α_h·ΔT_h - α_s·ΔT_s)·R``：加热轮毂、冷却轴
    （ΔT_s 为负）都使可装配过盈增大。任一字段缺省按 0 处理。
    """

    model_config = ConfigDict(allow_inf_nan=False)

    hub_delta_t_k: float = Field(default=0.0, description="轮毂温升 ΔT_h")
    shaft_delta_t_k: float = Field(default=0.0, description="轴温升 ΔT_s（冷却为负）")


class FitParams(BaseModel):
    """一次完整过盈配合核算所需的全部参数（也即配合档内容）。"""

    model_config = ConfigDict(allow_inf_nan=False)

    geometry: GeometryInput
    shaft_material: MaterialInput
    hub_material: MaterialInput
    interference_mm: float = Field(..., description="常温径向过盈量 δ，mm")
    friction_coefficient: float | None = Field(
        default=None,
        description="配合面摩擦系数 μ；提供时才核算可传转矩，服务不自行假定",
    )
    thermal: ThermalInput | None = Field(
        default=None, description="温差装配信息；不提供即按常温压装"
    )


class RegisterFitRequest(BaseModel):
    """登记命名配合档的请求。"""

    name: str = Field(..., description="配合档名称（唯一）")
    params: FitParams


class CalculateRequest(BaseModel):
    """核算请求：点名已登记配合档，或直接内联参数，二选一。

    点名已登记配合档时，可用顶层字段临时覆盖过盈量、摩擦系数与温差
    装配信息（配合档本体不会被修改）；不提供覆盖则按登记值计算。
    """

    fit: str | None = Field(default=None, description="已登记配合档名称")
    params: FitParams | None = Field(default=None, description="临时内联参数")
    interference_mm: float | None = Field(
        default=None, description="对已登记配合档临时覆盖的过盈量"
    )
    friction_coefficient: float | None = Field(
        default=None, description="对已登记配合档临时覆盖的摩擦系数"
    )
    thermal: ThermalInput | None = Field(
        default=None, description="对已登记配合档临时覆盖的温差装配信息"
    )


class InterfaceStress(BaseModel):
    """一个零件在配合面上的应力（MPa）。"""

    hoop_mpa: float = Field(..., description="环向应力 σ_θ")
    radial_mpa: float = Field(..., description="径向应力 σ_r = -p")
    von_mises_mpa: float = Field(..., description="von Mises 等效应力")


class CalculateResponse(BaseModel):
    """核算结果。

    屈服警告触发时 ``max_transmissible_torque_nm`` 为 null——不把
    已进入塑性的弹性接触压力乘摩擦系数当作可传转矩上限返回。
    """

    contact_pressure_mpa: float = Field(..., description="接触压力 p，MPa")
    effective_interference_mm: float = Field(
        ..., description="计入温差膨胀后的等效径向过盈量，mm"
    )
    max_transmissible_torque_nm: float | None = Field(
        ..., description="最大可传转矩，N·m；未给摩擦系数或已屈服时为 null"
    )
    max_axial_force_n: float | None = Field(
        ..., description="最大轴向压入/脱出力，N；同上规则"
    )
    shaft_interface_stress: InterfaceStress
    hub_interface_stress: InterfaceStress
    within_elastic: bool = Field(
        ..., description="轴、毂接触面是否均处于弹性区"
    )
    warnings: list[str] = Field(default_factory=list, description="警告信息")
