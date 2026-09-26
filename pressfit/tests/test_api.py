"""HTTP 接口层测试：路由、错误响应、配合档登记与隔离。"""

from __future__ import annotations

import pytest

from tests.conftest import make_params, steel_payload


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_calculate_with_inline_params(client):
    """临时传一组参数直接算。"""
    response = client.post("/api/calculate", json=steel_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["contact_pressure_mpa"] == pytest.approx(63.0, abs=1e-9)
    assert body["max_transmissible_torque_nm"] == pytest.approx(1484.40, rel=1e-4)
    assert body["within_elastic"] is True
    assert body["warnings"] == []


def test_calculate_by_registered_fit_name(client):
    """点名已登记的档来算。"""
    register = client.post(
        "/api/fits",
        json={"name": "steel-50x40", "params": make_params().model_dump()},
    )
    assert register.status_code == 201

    response = client.post("/api/calculate", json={"fit": "steel-50x40"})
    assert response.status_code == 200
    assert response.json()["contact_pressure_mpa"] == pytest.approx(63.0, abs=1e-9)


def test_calculate_with_override_does_not_mutate_registered_fit(client):
    """对已登记档临时覆盖过盈量，只影响本次计算，不回写登记表。"""
    client.post(
        "/api/fits",
        json={"name": "steel-50x40", "params": make_params().model_dump()},
    )
    response = client.post(
        "/api/calculate",
        json={"fit": "steel-50x40", "interference_mm": 0.04},
    )
    assert response.status_code == 200
    assert response.json()["contact_pressure_mpa"] == pytest.approx(126.0, abs=1e-9)

    fetched = client.get("/api/fits/steel-50x40")
    assert fetched.status_code == 200
    assert fetched.json()["interference_mm"] == pytest.approx(0.02)


def test_two_registered_fits_stay_independent(client):
    """不同的档各算各的，参数不得彼此渗透。"""
    client.post(
        "/api/fits",
        json={
            "name": "thin",
            "params": make_params(hub_outer_radius_mm=40.0).model_dump(),
        },
    )
    client.post(
        "/api/fits",
        json={
            "name": "thick",
            "params": make_params(hub_outer_radius_mm=80.0).model_dump(),
        },
    )
    p_thin = client.post("/api/calculate", json={"fit": "thin"}).json()[
        "contact_pressure_mpa"
    ]
    p_thick = client.post("/api/calculate", json={"fit": "thick"}).json()[
        "contact_pressure_mpa"
    ]
    assert p_thick > p_thin
    # 再算一次 thin，结果不变（未被 thick 污染）。
    p_thin_again = client.post("/api/calculate", json={"fit": "thin"}).json()[
        "contact_pressure_mpa"
    ]
    assert p_thin_again == pytest.approx(p_thin)


def test_unknown_fit_returns_404(client):
    response = client.post("/api/calculate", json={"fit": "nope"})
    assert response.status_code == 404
    assert "未登记" in response.json()["detail"]


def test_missing_both_fit_and_params_returns_422(client):
    response = client.post("/api/calculate", json={})
    assert response.status_code == 422
    assert "二选一" in response.json()["detail"]


@pytest.mark.parametrize(
    "overrides,fragment",
    [
        ({"interference_mm": -0.01}, "过盈量不能为负"),
        (
            {"interference_mm": 0.0, "friction_coefficient": 0.15},
            "过盈量为零",
        ),
        ({"contact_radius_mm": 0.0}, "半径必须为正"),
        ({"hub_outer_radius_mm": -50.0}, "半径必须为正"),
        ({"length_mm": 0.0}, "配合长度必须为正"),
        ({"shaft_e_gpa": 0.0}, "弹性模量必须为正"),
        ({"hub_e_gpa": -210.0}, "弹性模量必须为正"),
        ({"shaft_nu": 0.6}, "泊松比"),
        ({"friction_coefficient": -0.1}, "摩擦系数不能为负"),
    ],
)
def test_invalid_input_rejected_before_calculation(client, overrides, fragment):
    """非法输入在计算开始前被 422 挡下，detail 中带中文原因。"""
    response = client.post("/api/calculate", json=steel_payload(**overrides))
    assert response.status_code == 422
    assert fragment in response.json()["detail"]


def test_yield_warning_over_http_withholds_torque(client):
    """进入塑性：结果里明确标出屈服警告，可传转矩置 null。"""
    response = client.post(
        "/api/calculate", json=steel_payload(hub_yield=100.0)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["within_elastic"] is False
    assert body["max_transmissible_torque_nm"] is None
    assert any("塑性" in w for w in body["warnings"])
    assert body["contact_pressure_mpa"] == pytest.approx(63.0, abs=1e-9)


def test_thermal_assembly_over_http(client):
    """温差装配信息由调用方给出时才叠加等效过盈。"""
    payload = steel_payload(shaft_alpha=12e-6, hub_alpha=12e-6)
    payload["params"]["thermal"] = {"hub_delta_t_k": 80.0, "shaft_delta_t_k": 0.0}
    response = client.post("/api/calculate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["effective_interference_mm"] == pytest.approx(0.044, rel=1e-12)
    assert body["contact_pressure_mpa"] == pytest.approx(138.6, rel=1e-9)


def test_thermal_without_alpha_rejected_over_http(client):
    payload = steel_payload()
    payload["params"]["thermal"] = {"hub_delta_t_k": 80.0}
    response = client.post("/api/calculate", json=payload)
    assert response.status_code == 422
    assert "线膨胀系数" in response.json()["detail"]


def test_fit_registry_crud(client):
    params = make_params().model_dump()
    assert client.post("/api/fits", json={"name": "a", "params": params}).status_code == 201
    assert client.post("/api/fits", json={"name": "b", "params": params}).status_code == 201

    listing = client.get("/api/fits")
    assert listing.status_code == 200
    assert listing.json()["fits"] == ["a", "b"]

    fetched = client.get("/api/fits/a")
    assert fetched.status_code == 200
    assert fetched.json()["geometry"]["contact_radius_mm"] == pytest.approx(25.0)

    assert client.delete("/api/fits/a").status_code == 204
    assert client.get("/api/fits/a").status_code == 404
    assert client.get("/api/fits").json()["fits"] == ["b"]


def test_register_invalid_fit_rejected(client):
    """坏参数不允许登记成档。"""
    bad = make_params(length_mm=0.0).model_dump()
    response = client.post("/api/fits", json={"name": "bad", "params": bad})
    assert response.status_code == 422
    assert "配合长度必须为正" in response.json()["detail"]
    assert client.get("/api/fits").json()["fits"] == []
