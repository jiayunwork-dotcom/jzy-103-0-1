"""HTTP 接口层的数据契约（Pydantic 模型）与领域对象互转。

校验分工：类型/可空性由 Pydantic 挡在最外层；物理含义与计算前置条件
（正数、过盈非负等）由 :mod:`app.validation` 用中文原因拦截。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import Assembly, Geometry, Material
from .registry import Profile


class MaterialIn(BaseModel):
    """材料参数。yield_strength 不给则该侧不做屈服判断。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field("", description="材料名称，仅用于结果展示")
    elastic_modulus: float = Field(..., description="弹性模量 E，Pa")
    poisson_ratio: float = Field(..., description="泊松比 nu")
    yield_strength: float | None = Field(None, description="屈服强度，Pa")

    def to_domain(self) -> Material:
        return Material(
            name=self.name,
            elastic_modulus=float(self.elastic_modulus),
            poisson_ratio=float(self.poisson_ratio),
            yield_strength=(
                None if self.yield_strength is None else float(self.yield_strength)
            ),
        )


class GeometryIn(BaseModel):
    """完整几何（直接计算或登记档时使用）。"""

    model_config = ConfigDict(extra="forbid")

    shaft_outer_radius: float = Field(..., description="轴外半径（配合面半径）r_i，m")
    shaft_inner_radius: float = Field(
        0.0, description="轴内半径 r_si，m；实心轴填 0"
    )
    hub_outer_radius: float = Field(..., description="轮毂外半径 r_o，m")
    length: float = Field(..., description="配合长度 L，m")

    def to_domain(self) -> Geometry:
        return Geometry(
            shaft_outer_radius=float(self.shaft_outer_radius),
            shaft_inner_radius=float(self.shaft_inner_radius),
            hub_outer_radius=float(self.hub_outer_radius),
            length=float(self.length),
        )


class GeometryOverride(BaseModel):
    """点名已登记档时的几何覆盖；所有字段可选，未给沿用档内值。"""

    model_config = ConfigDict(extra="forbid")

    shaft_outer_radius: float | None = None
    shaft_inner_radius: float | None = None
    hub_outer_radius: float | None = None
    length: float | None = None

    def to_domain_merge_base(self, base: Geometry) -> Geometry:
        return Geometry(
            shaft_outer_radius=(
                base.shaft_outer_radius
                if self.shaft_outer_radius is None
                else float(self.shaft_outer_radius)
            ),
            shaft_inner_radius=(
                base.shaft_inner_radius
                if self.shaft_inner_radius is None
                else float(self.shaft_inner_radius)
            ),
            hub_outer_radius=(
                base.hub_outer_radius
                if self.hub_outer_radius is None
                else float(self.hub_outer_radius)
            ),
            length=base.length if self.length is None else float(self.length),
        )


class AssemblyIn(BaseModel):
    """温差装配信息；整块给了才计入热膨胀等效过盈。"""

    model_config = ConfigDict(extra="forbid")

    alpha_shaft: float = Field(..., description="轴的线膨胀系数，1/K")
    alpha_hub: float = Field(..., description="轮毂的线膨胀系数，1/K")
    delta_t_shaft: float = Field(
        0.0, description="轴相对装配参考温度的温升，K（冷装为负）"
    )
    delta_t_hub: float = Field(
        0.0, description="轮毂相对装配参考温度的温升，K（热装为正）"
    )

    def to_domain(self) -> Assembly:
        return Assembly(
            alpha_shaft=float(self.alpha_shaft),
            alpha_hub=float(self.alpha_hub),
            delta_t_shaft=float(self.delta_t_shaft),
            delta_t_hub=float(self.delta_t_hub),
        )


class CalculateRequest(BaseModel):
    """核算请求：要么点名已登记档，要么直接给全材料与几何。"""

    model_config = ConfigDict(extra="forbid")

    profile: str | None = Field(None, description="已登记配合档名称")
    shaft: MaterialIn | None = None
    hub: MaterialIn | None = None
    geometry: GeometryIn | None = None
    geometry_override: GeometryOverride | None = Field(
        None, description="用档时对档内几何的逐项覆盖"
    )
    interference: float = Field(
        ..., description="机械径向过盈量 delta，m（轴半径减孔半径）"
    )
    friction_coefficient: float | None = Field(
        None, description="摩擦系数 mu；不给则不算转矩，服务不自行假定"
    )
    assembly: AssemblyIn | None = Field(
        None, description="温差装配信息；不给不计入热膨胀"
    )

    @model_validator(mode="after")
    def _check_source(self) -> "CalculateRequest":
        if self.profile is None:
            missing = [
                name
                for name, value in (
                    ("shaft", self.shaft),
                    ("hub", self.hub),
                    ("geometry", self.geometry),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    "未指定 profile 时必须直接给全 shaft、hub、geometry；"
                    f"缺少：{', '.join(missing)}"
                )
        return self


class ProfileIn(BaseModel):
    """登记/覆盖一份配合档。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="配合档名称")
    shaft: MaterialIn
    hub: MaterialIn
    geometry: GeometryIn

    def to_domain(self) -> Profile:
        return Profile(
            name=self.name,
            shaft_material=self.shaft.to_domain(),
            hub_material=self.hub.to_domain(),
            geometry=self.geometry.to_domain(),
        )


class ComponentStrengthOut(BaseModel):
    """单个零件的配合面应力结果。"""

    name: str
    hoop_stress: float = Field(..., description="环向应力，Pa（拉正压负）")
    contact_pressure: float = Field(..., description="径向接触压应力，Pa")
    equivalent_stress: float | None = Field(
        None, description="von Mises 等效应力，Pa"
    )
    yield_strength: float | None = Field(None, description="屈服强度，Pa")
    yielded: bool = Field(..., description="等效应力是否超过屈服")


class CalculateResponse(BaseModel):
    """核算结果。"""

    contact_pressure: float = Field(..., description="接触压力 p，Pa")
    contact_area: float = Field(..., description="配合面面积，m^2")
    torque_capacity: float | None = Field(
        None,
        description="弹性可传转矩，N·m；进入塑性或未给摩擦系数时为 null",
    )
    nominal_torque: float | None = Field(
        None, description="按摩擦公式外推的名义转矩，N·m（仅参考）"
    )
    yielded: bool = Field(..., description="是否有任一零件发生屈服")
    warnings: list[str]
    notes: list[str]
    shaft: ComponentStrengthOut
    hub: ComponentStrengthOut
    interference: float = Field(..., description="机械径向过盈量，m")
    thermal_interference: float = Field(
        ..., description="温差等效径向过盈量，m；未给温差时为 0"
    )
    effective_interference: float = Field(
        ..., description="参与弹性计算的有效过盈量，m"
    )
    shaft_compliance: float = Field(..., description="轴柔度系数，1/Pa")
    hub_compliance: float = Field(..., description="轮毂柔度系数，1/Pa")
    combined_compliance: float = Field(..., description="组合柔度系数，1/Pa")
    shaft_radial_displacement: float = Field(..., description="轴面径向内缩量，m")
    hub_radial_displacement: float = Field(..., description="毂面径向外胀量，m")


class ErrorResponse(BaseModel):
    error: dict[str, object]


class ProfileOut(BaseModel):
    name: str
    shaft: MaterialIn
    hub: MaterialIn
    geometry: GeometryIn

    @classmethod
    def from_domain(cls, profile: Profile) -> "ProfileOut":
        return cls(
            name=profile.name,
            shaft=MaterialIn(
                name=profile.shaft_material.name,
                elastic_modulus=profile.shaft_material.elastic_modulus,
                poisson_ratio=profile.shaft_material.poisson_ratio,
                yield_strength=profile.shaft_material.yield_strength,
            ),
            hub=MaterialIn(
                name=profile.hub_material.name,
                elastic_modulus=profile.hub_material.elastic_modulus,
                poisson_ratio=profile.hub_material.poisson_ratio,
                yield_strength=profile.hub_material.yield_strength,
            ),
            geometry=GeometryIn(
                shaft_outer_radius=profile.geometry.shaft_outer_radius,
                shaft_inner_radius=profile.geometry.shaft_inner_radius,
                hub_outer_radius=profile.geometry.hub_outer_radius,
                length=profile.geometry.length,
            ),
        )
