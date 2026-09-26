"""FastAPI 接口层：只负责把请求接进来、调好各块、把结果拼出去。

路由
====
- GET  /health                       存活检查
- GET  /presets                      预置算例（手算基准）目录
- GET  /profiles                     列出已登记配合档
- PUT  /profiles/{name}              登记/覆盖配合档
- GET  /profiles/{name}              取配合档
- DELETE /profiles/{name}            删除配合档
- POST /calculate                    过盈配合核算（点名档或直接传参）

错误统一包成 ``{"error": {code, field?, message}}`` 且带原因，不泄栈。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import presets
from .domain import FitResult
from .registry import Profile, ProfileRegistry, RegistryError
from .schemas import (
    CalculateRequest,
    CalculateResponse,
    ComponentStrengthOut,
    ProfileIn,
    ProfileOut,
)
from .service import calculate
from .validation import ValidationError

registry = ProfileRegistry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 进程启动即登记预置钢轴—钢毂算例档；只活在本进程内存中。
    registry.put(
        Profile(
            name=presets.PRESET_NAME,
            shaft_material=presets.STEEL_SHAFT,
            hub_material=presets.STEEL_HUB,
            geometry=presets.DEMO_GEOMETRY,
        )
    )
    yield


app = FastAPI(
    title="过盈配合核算服务",
    version="1.0.0",
    description="弹性力学过盈配合接触压力、可传转矩与屈服校核（仅 HTTP 接口）",
    lifespan=lifespan,
)


def _error_response(status_code: int, code: str, message: str, field=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "field": field, "message": message}},
    )


@app.exception_handler(ValidationError)
async def handle_domain_validation(request: Request, exc: ValidationError):
    return _error_response(422, exc.code, exc.message, exc.field)


@app.exception_handler(RegistryError)
async def handle_registry_error(request: Request, exc: RegistryError):
    return _error_response(exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def handle_pydantic(request: Request, exc: RequestValidationError):
    # 把 Pydantic 的类型错误也包进统一的带原因结构。
    details = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        details.append(f"{loc or '请求体'}: {err.get('msg', '类型/格式不正确')}")
    return _error_response(
        422,
        "REQUEST_SCHEMA_INVALID",
        "请求结构或字段类型不合法：" + "；".join(details),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "interference-fit", "profiles": registry.names()}


@app.get("/presets")
async def list_presets():
    return {"presets": presets.preset_catalog()}


@app.get("/profiles")
async def list_profiles():
    return {"profiles": [ProfileOut.from_domain(p) for p in registry.snapshot().values()]}


@app.put("/profiles/{name}", status_code=200)
async def put_profile(name: str, body: ProfileIn):
    if name != body.name:
        raise ValidationError(
            "PROFILE_NAME_MISMATCH",
            f"路径中的档名 {name!r} 与请求体中的 name {body.name!r} 不一致",
            "name",
        )
    if name == presets.PRESET_NAME:
        raise RegistryError(
            "PROFILE_IS_PRESET",
            f"{name!r} 为预置算例档，受保护不可登记覆盖，可换一个名称",
            status_code=409,
        )
    profile = body.to_domain()
    # 登记前同样做计算前校验，保证档本身合法。
    from .validation import validate_geometry, validate_material

    validate_material(profile.shaft_material, "shaft")
    validate_material(profile.hub_material, "hub")
    validate_geometry(profile.geometry)
    registry.put(profile)
    return {"status": "registered", "profile": ProfileOut.from_domain(profile)}


@app.get("/profiles/{name}")
async def get_profile(name: str):
    return {"profile": ProfileOut.from_domain(registry.get(name))}


@app.delete("/profiles/{name}", status_code=200)
async def delete_profile(name: str):
    if name == presets.PRESET_NAME:
        raise RegistryError(
            "PROFILE_IS_PRESET",
            f"{name!r} 为预置算例档，受保护不可删除",
            status_code=409,
        )
    registry.delete(name)
    return {"status": "deleted", "name": name}


def _result_to_response(result: FitResult, mechanical: float) -> CalculateResponse:
    return CalculateResponse(
        contact_pressure=result.contact_pressure,
        contact_area=result.contact_area,
        torque_capacity=result.torque_capacity,
        nominal_torque=result.nominal_torque,
        yielded=result.yielded,
        warnings=list(result.warnings),
        notes=list(result.notes),
        shaft=ComponentStrengthOut(
            name=result.shaft.name,
            hoop_stress=result.shaft.hoop_stress,
            contact_pressure=result.shaft.contact_pressure,
            equivalent_stress=result.shaft.equivalent_stress,
            yield_strength=result.shaft.yield_strength,
            yielded=result.shaft.yielded,
        ),
        hub=ComponentStrengthOut(
            name=result.hub.name,
            hoop_stress=result.hub.hoop_stress,
            contact_pressure=result.hub.contact_pressure,
            equivalent_stress=result.hub.equivalent_stress,
            yield_strength=result.hub.yield_strength,
            yielded=result.hub.yielded,
        ),
        interference=mechanical,
        thermal_interference=result.thermal_interference,
        effective_interference=mechanical + result.thermal_interference,
        shaft_compliance=result.shaft_compliance,
        hub_compliance=result.hub_compliance,
        combined_compliance=result.combined_compliance,
        shaft_radial_displacement=result.shaft_radial_displacement,
        hub_radial_displacement=result.hub_radial_displacement,
    )


@app.post("/calculate", response_model=CalculateResponse)
async def calculate_endpoint(req: CalculateRequest):
    if req.profile is not None:
        profile: Profile | None = registry.get(req.profile)
        # 几何字段级合并：未覆盖的字段沿用档内值。
        geometry = (
            req.geometry_override.to_domain_merge_base(profile.geometry)
            if req.geometry_override is not None
            else profile.geometry
        )
        # 材料整块替换，不给沿用档内值。
        shaft = req.shaft.to_domain() if req.shaft is not None else profile.shaft_material
        hub = req.hub.to_domain() if req.hub is not None else profile.hub_material
    else:
        profile = None
        geometry = req.geometry.to_domain()
        shaft = req.shaft.to_domain()
        hub = req.hub.to_domain()

    result = calculate(
        shaft_material=shaft,
        hub_material=hub,
        geometry=geometry,
        mechanical_interference=float(req.interference),
        friction_coefficient=(
            None
            if req.friction_coefficient is None
            else float(req.friction_coefficient)
        ),
        assembly=req.assembly.to_domain() if req.assembly is not None else None,
    )
    return _result_to_response(result, float(req.interference))
