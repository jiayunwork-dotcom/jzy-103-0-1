"""测试公共构造器：钢轴配钢毂的常见量级算例。

手算基准（配合面半径 R = 25 mm、毂外半径 R_o = 50 mm、实心轴、
δ = 0.02 mm、L = 40 mm、E = 210 GPa、ν = 0.3、μ = 0.15）：

    κ_s = (R²+0)/(R²-0) - ν = 1 - 0.3 = 0.7
    κ_h = (R_o²+R²)/(R_o²-R²) + ν = 3125/1875 + 0.3 = 5/3 + 0.3 ≈ 1.96667
    p = δ / [ R(κ_s+κ_h)/E ]
      = 0.02 × 210000 / [ 25 × (0.7 + 1.96667) ] = 63.0 MPa
    轴面环向应力 = -p = -63.0 MPa，轴面等效应力 = 63.0 MPa
    毂面环向应力 = p × 5/3 = 105.0 MPa
    毂面等效应力 = sqrt(105² + 63² + 105×63) = 147.0 MPa
    T = μ·p·2πR²L = 0.15 × 63 × 2π × 25² × 40 N·mm ≈ 1484.40 N·m
"""

from __future__ import annotations

import pytest

from app.schemas import (
    CalculateRequest,
    FitParams,
    GeometryInput,
    MaterialInput,
    ThermalInput,
)


def make_params(
    *,
    interference_mm: float = 0.02,
    friction_coefficient: float | None = 0.15,
    contact_radius_mm: float = 25.0,
    shaft_inner_radius_mm: float = 0.0,
    hub_outer_radius_mm: float = 50.0,
    length_mm: float = 40.0,
    shaft_e_gpa: float = 210.0,
    hub_e_gpa: float = 210.0,
    shaft_nu: float = 0.3,
    hub_nu: float = 0.3,
    shaft_yield: float | None = 400.0,
    hub_yield: float | None = 400.0,
    shaft_alpha: float | None = None,
    hub_alpha: float | None = None,
    thermal: ThermalInput | None = None,
) -> FitParams:
    """构造一组可逐字段覆盖的配合参数。"""
    return FitParams(
        geometry=GeometryInput(
            contact_radius_mm=contact_radius_mm,
            shaft_inner_radius_mm=shaft_inner_radius_mm,
            hub_outer_radius_mm=hub_outer_radius_mm,
            length_mm=length_mm,
        ),
        shaft_material=MaterialInput(
            elastic_modulus_gpa=shaft_e_gpa,
            poisson_ratio=shaft_nu,
            yield_strength_mpa=shaft_yield,
            thermal_expansion_per_k=shaft_alpha,
        ),
        hub_material=MaterialInput(
            elastic_modulus_gpa=hub_e_gpa,
            poisson_ratio=hub_nu,
            yield_strength_mpa=hub_yield,
            thermal_expansion_per_k=hub_alpha,
        ),
        interference_mm=interference_mm,
        friction_coefficient=friction_coefficient,
        thermal=thermal,
    )


def steel_payload(**overrides) -> dict:
    """内联 params 形式的 /api/calculate 请求体（dict）。"""
    params = make_params(**overrides)
    return {"params": params.model_dump()}


@pytest.fixture
def client():
    """每个测试使用全新的 FastAPI TestClient 与空的配合档登记表。"""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.registry import store

    store._fits.clear()
    with TestClient(app) as c:
        yield c
    store._fits.clear()
