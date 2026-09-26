"""HTTP 接口层测试：收发、错误结构、点名档/临时传参、预置档保护。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import presets
from app.api import app


@pytest.fixture()
def client():
    # with 块触发 lifespan，启动时登记预置 steel-demo 档。
    with TestClient(app) as c:
        yield c


STEEL_DEMO_BODY = {
    "shaft": {
        "name": "钢轴",
        "elastic_modulus": 2.1e11,
        "poisson_ratio": 0.3,
        "yield_strength": 250e6,
    },
    "hub": {
        "name": "钢毂",
        "elastic_modulus": 2.1e11,
        "poisson_ratio": 0.3,
        "yield_strength": 250e6,
    },
    "geometry": {
        "shaft_outer_radius": 0.05,
        "shaft_inner_radius": 0.0,
        "hub_outer_radius": 0.10,
        "length": 0.06,
    },
    "interference": 3e-5,
    "friction_coefficient": 0.15,
}


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert presets.PRESET_NAME in body["profiles"]


def test_presets_catalog(client):
    resp = client.get("/presets")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["presets"]]
    assert presets.PRESET_NAME in names


def test_calculate_with_inline_params_matches_regression(client):
    resp = client.post("/calculate", json=STEEL_DEMO_BODY)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["contact_pressure"] == pytest.approx(47.25e6, rel=1e-9)
    assert body["torque_capacity"] == pytest.approx(presets.EXPECTED_TORQUE, rel=1e-9)
    assert body["yielded"] is False
    assert body["shaft"]["hoop_stress"] == pytest.approx(-47.25e6, rel=1e-9)
    assert body["hub"]["hoop_stress"] == pytest.approx(78.75e6, rel=1e-9)
    # 位移连续在结果里也可核对。
    assert body["shaft_radial_displacement"] + body[
        "hub_radial_displacement"
    ] == pytest.approx(3e-5, rel=1e-9)


def test_calculate_with_named_preset_profile(client):
    body = {
        "profile": presets.PRESET_NAME,
        "interference": 3e-5,
        "friction_coefficient": 0.15,
    }
    resp = client.post("/calculate", json=body)
    assert resp.status_code == 200, resp.text
    inline = client.post("/calculate", json=STEEL_DEMO_BODY).json()
    assert resp.json()["contact_pressure"] == pytest.approx(
        inline["contact_pressure"], rel=1e-12
    )


def _relation_body(delta, mu, hub_outer=0.10):
    body = {
        "shaft": {"name": "s", "elastic_modulus": 2.1e11, "poisson_ratio": 0.3},
        "hub": {"name": "h", "elastic_modulus": 2.1e11, "poisson_ratio": 0.3},
        "geometry": {
            "shaft_outer_radius": 0.05,
            "shaft_inner_radius": 0.0,
            "hub_outer_radius": hub_outer,
            "length": 0.06,
        },
        "interference": delta,
    }
    if mu is not None:
        body["friction_coefficient"] = mu
    return body


def test_relation_checks_over_http(client):
    """四条核心关系经 HTTP 再钉一遍。"""

    def call(delta, mu, hub_outer=0.10):
        r = client.post("/calculate", json=_relation_body(delta, mu, hub_outer))
        assert r.status_code == 200, r.text
        return r.json()

    # 关系 1：零过盈（不带摩擦）-> 压力 0
    zero = call(0.0, None)
    assert zero["contact_pressure"] == 0.0
    assert zero["torque_capacity"] is None

    # 关系 2：过盈翻倍 -> 压力、转矩同步翻倍
    base = call(3e-5, 0.15)
    double_delta = call(6e-5, 0.15)
    assert double_delta["contact_pressure"] == pytest.approx(
        2 * base["contact_pressure"], rel=1e-9
    )
    assert double_delta["torque_capacity"] == pytest.approx(
        2 * base["torque_capacity"], rel=1e-9
    )

    # 关系 3：摩擦系数翻倍 -> 仅转矩翻倍，压力不动
    double_mu = call(3e-5, 0.30)
    assert double_mu["contact_pressure"] == pytest.approx(
        base["contact_pressure"], rel=1e-9
    )
    assert double_mu["torque_capacity"] == pytest.approx(
        2 * base["torque_capacity"], rel=1e-9
    )

    # 关系 4：轮毂加厚 -> 同过盈下压力升高
    thicker = call(3e-5, 0.15, hub_outer=0.20)
    assert thicker["contact_pressure"] > base["contact_pressure"]


def test_zero_interference_with_friction_rejected_over_http(client):
    body = dict(STEEL_DEMO_BODY)
    body["interference"] = 0.0
    resp = client.post("/calculate", json=body)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "INTERFERENCE_ZERO_WITH_TORQUE"
    assert err["message"]


def test_negative_interference_rejected_over_http(client):
    body = dict(STEEL_DEMO_BODY)
    body["interference"] = -1e-6
    resp = client.post("/calculate", json=body)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INTERFERENCE_NEGATIVE"


def test_bad_radius_rejected_before_calculation(client):
    body = {
        "shaft": {"elastic_modulus": 2.1e11, "poisson_ratio": 0.3},
        "hub": {"elastic_modulus": 2.1e11, "poisson_ratio": 0.3},
        "geometry": {
            "shaft_outer_radius": 0.05,
            "shaft_inner_radius": 0.0,
            "hub_outer_radius": 0.0,
            "length": 0.06,
        },
        "interference": 3e-5,
    }
    resp = client.post("/calculate", json=body)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "HUB_OUTER_RADIUS_INVALID"
    assert "轮毂外半径" in err["message"]


def test_schema_error_enveloped(client):
    """缺字段/类型错也走统一带原因错误结构，不抛栈。"""
    resp = client.post("/calculate", json={"interference": 3e-5})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "REQUEST_SCHEMA_INVALID"
    assert "message" in err


def test_unknown_profile_404(client):
    resp = client.post("/calculate", json={"profile": "no-such", "interference": 3e-5})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PROFILE_NOT_FOUND"


def test_profile_lifecycle_and_override(client):
    payload = {
        "name": "custom-fit",
        "shaft": {"elastic_modulus": 2.0e11, "poisson_ratio": 0.29},
        "hub": {"elastic_modulus": 2.0e11, "poisson_ratio": 0.29},
        "geometry": {
            "shaft_outer_radius": 0.04,
            "shaft_inner_radius": 0.0,
            "hub_outer_radius": 0.09,
            "length": 0.05,
        },
    }
    r = client.put("/profiles/custom-fit", json=payload)
    assert r.status_code == 200, r.text

    r = client.get("/profiles/custom-fit")
    assert r.status_code == 200
    assert r.json()["profile"]["geometry"]["length"] == 0.05

    # 点名档 + 本次过盈/摩擦
    r = client.post(
        "/calculate",
        json={
            "profile": "custom-fit",
            "interference": 2e-5,
            "friction_coefficient": 0.12,
        },
    )
    assert r.status_code == 200, r.text
    p_named = r.json()["contact_pressure"]

    # 几何字段级覆盖：加厚轮毂 -> 压力升高
    r = client.post(
        "/calculate",
        json={
            "profile": "custom-fit",
            "interference": 2e-5,
            "friction_coefficient": 0.12,
            "geometry_override": {"hub_outer_radius": 0.16},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["contact_pressure"] > p_named

    # 档内原值未被覆盖污染
    assert client.get("/profiles/custom-fit").json()["profile"]["geometry"][
        "hub_outer_radius"
    ] == 0.09

    r = client.delete("/profiles/custom-fit")
    assert r.status_code == 200
    assert client.get("/profiles/custom-fit").status_code == 404


def test_preset_profile_is_protected(client):
    payload = {
        "name": presets.PRESET_NAME,
        "shaft": {"elastic_modulus": 1.0, "poisson_ratio": 0.0},
        "hub": {"elastic_modulus": 1.0, "poisson_ratio": 0.0},
        "geometry": {
            "shaft_outer_radius": 1.0,
            "shaft_inner_radius": 0.0,
            "hub_outer_radius": 2.0,
            "length": 1.0,
        },
    }
    r = client.put(f"/profiles/{presets.PRESET_NAME}", json=payload)
    assert r.status_code == 409
    r = client.delete(f"/profiles/{presets.PRESET_NAME}")
    assert r.status_code == 409
    # 预置档仍可正常用于计算
    r = client.post(
        "/calculate",
        json={"profile": presets.PRESET_NAME, "interference": 3e-5},
    )
    assert r.status_code == 200


def test_yield_warning_over_http(client):
    body = {
        "shaft": {
            "elastic_modulus": 2.1e11,
            "poisson_ratio": 0.3,
            "yield_strength": 250e6,
        },
        "hub": {
            "elastic_modulus": 2.1e11,
            "poisson_ratio": 0.3,
            "yield_strength": 50e6,
        },
        "geometry": {
            "shaft_outer_radius": 0.05,
            "shaft_inner_radius": 0.0,
            "hub_outer_radius": 0.10,
            "length": 0.06,
        },
        "interference": 3e-5,
        "friction_coefficient": 0.15,
    }
    r = client.post("/calculate", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["yielded"] is True
    assert data["torque_capacity"] is None
    assert data["nominal_torque"] is not None
    assert any("不能作为可传转矩上限" in w for w in data["warnings"])


def test_thermal_assembly_over_http(client):
    body = dict(STEEL_DEMO_BODY)
    body["assembly"] = {
        "alpha_shaft": 1.2e-5,
        "alpha_hub": 1.2e-5,
        "delta_t_shaft": 0.0,
        "delta_t_hub": 20.0,
    }
    r = client.post("/calculate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    # 热装：热过盈为负，有效过盈 = 机械 + 热（负）
    assert data["thermal_interference"] < 0
    assert data["effective_interference"] == pytest.approx(
        data["interference"] + data["thermal_interference"], rel=1e-12
    )
    cold = client.post("/calculate", json=STEEL_DEMO_BODY).json()
    assert data["contact_pressure"] < cold["contact_pressure"]


def test_no_assembly_no_thermal_invention(client):
    """没给温差信息时不编造：热过盈为 0，并有说明。"""
    r = client.post("/calculate", json=STEEL_DEMO_BODY)
    data = r.json()
    assert data["thermal_interference"] == 0.0
    assert any("温差" in note for note in data["notes"])
