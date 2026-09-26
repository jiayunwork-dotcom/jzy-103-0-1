"""FastAPI 接口层：只负责接收请求、调度各块、拼出响应。

路由：

* ``GET  /health``                存活探针
* ``POST /api/fits``              登记（或覆盖）命名配合档
* ``GET  /api/fits``              列出已登记档名
* ``GET  /api/fits/{name}``       查看某档参数
* ``DELETE /api/fits/{name}``     删除某档
* ``POST /api/calculate``         过盈配合核算（点名档或内联参数）
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import __version__, registry, service
from .schemas import (
    CalculateRequest,
    CalculateResponse,
    FitParams,
    RegisterFitRequest,
)
from .validation import FitValidationError

app = FastAPI(
    title="过盈配合接触核算服务",
    version=__version__,
    description="基于 Lamé 厚壁圆筒理论的轴-轮毂过盈配合接触压力、"
    "可传转矩与接触面屈服校核（仅 HTTP 接口，无网页界面）。",
)


@app.exception_handler(FitValidationError)
async def fit_validation_handler(request, exc: FitValidationError) -> JSONResponse:
    """业务校验错误统一为 422，detail 中直接给出中文原因。"""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/api/fits", status_code=201)
def register_fit(request: RegisterFitRequest) -> dict[str, str]:
    # 登记内容本身也要先过合法性检查，避免坏档被存下后反复绊倒计算。
    # 登记路径允许零过盈（可作为模板，核算时再覆盖过盈量），故只做
    # 几何/材料等硬约束检查：用一个临时摩擦系数为 None 的视图即可，
    # 零过盈 + 无摩擦并不非法。
    from .validation import validate_fit

    validate_fit(request.params)
    registry.store.register(request.name, request.params)
    return {"name": request.name, "status": "registered"}


@app.get("/api/fits")
def list_fits() -> dict[str, list[str]]:
    return {"fits": registry.store.names()}


@app.get("/api/fits/{name}")
def get_fit(name: str) -> FitParams:
    try:
        return registry.store.get(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"配合档 '{name}' 未登记")


@app.delete("/api/fits/{name}", status_code=204)
def delete_fit(name: str) -> None:
    if not registry.store.remove(name):
        raise HTTPException(status_code=404, detail=f"配合档 '{name}' 未登记")


@app.post("/api/calculate", response_model=CalculateResponse)
def calculate(request: CalculateRequest) -> CalculateResponse:
    if request.fit is None and request.params is None:
        raise FitValidationError(
            "请求必须二选一：用 fit 指定已登记配合档，或用 params 直接内联参数"
        )

    if request.fit is not None:
        try:
            params = registry.store.get(request.fit)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=f"配合档 '{request.fit}' 未登记"
            )
        # 顶层字段是对已登记档的临时覆盖；registry 已返回深拷贝，
        # 这里的改动不会回写到登记表。
        updates: dict[str, object] = {}
        if request.interference_mm is not None:
            updates["interference_mm"] = request.interference_mm
        if request.friction_coefficient is not None:
            updates["friction_coefficient"] = request.friction_coefficient
        if request.thermal is not None:
            updates["thermal"] = request.thermal
        if updates:
            params = params.model_copy(update=updates)
    else:
        params = request.params

    # service 内部先做 validate_fit，非法输入在计算前即被 422 挡回。
    return service.calculate(params)
