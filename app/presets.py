"""预置算例：可手算核对的钢轴—钢毂配合，回归基准。

参数（SI 单位）
===============
- 配合面半径 r_i = 0.05 m（50 mm）
- 实心轴 r_si = 0
- 轮毂外半径 r_o = 0.10 m（轮毂壁厚 = 50 mm）
- 配合长度 L = 0.06 m（60 mm）
- 钢：E = 2.1e11 Pa，nu = 0.3，屈服强度 250 MPa
- 径向过盈量 delta = 0.00003 m（0.03 mm，单边）
- 摩擦系数 mu = 0.15

手算
====
轮毂厚壁项：
    K_h = (r_o^2 + r_i^2)/(r_o^2 - r_i^2)
        = (0.01 + 0.0025)/(0.01 - 0.0025)
        = 0.0125/0.0075 = 5/3

柔度系数：
    C_s = (1 - nu)/E = 0.7/E
    C_h = (K_h + nu)/E = (5/3 + 0.3)/E = (59/30)/E ≈ 1.96667/E
    C_s + C_h = (0.7 + 59/30)/E = (8/3)/E

接触压力：
    p = delta / (r_i * (C_s + C_h))
      = delta * E / (r_i * 8/3)
      = 3e-5 * 2.1e11 / (0.05 * 8/3)
      = 4.725e7 Pa = 47.25 MPa（正值）

环向应力：
    轴（实心）：sigma_t,s = -p = -47.25 MPa
    毂        ：sigma_t,h = p * K_h = 47.25 * 5/3 = 78.75 MPa（拉）

毂内表面等效应力（sigma_r = -p，平面应力）：
    sigma_v = sqrt(sigma_t^2 + p^2 + sigma_t*p)
            = sqrt(78.75^2 + 47.25^2 + 78.75*47.25) MPa
            = 110.25 MPa
    110.25 MPa < 250 MPa，弹性安全，不发屈服警告。

可传转矩：
    T = 2*pi*mu*p*r_i^2*L
      = 2*pi*0.15*4.725e7*0.05^2*0.06
      ≈ 6679.8 N·m
"""

from __future__ import annotations

import math

from .domain import Geometry, Material

PRESET_NAME = "steel-demo"

STEEL_SHAFT = Material(
    name="钢轴 45",
    elastic_modulus=2.1e11,
    poisson_ratio=0.3,
    yield_strength=250e6,
)
STEEL_HUB = Material(
    name="钢毂 45",
    elastic_modulus=2.1e11,
    poisson_ratio=0.3,
    yield_strength=250e6,
)
DEMO_GEOMETRY = Geometry(
    shaft_outer_radius=0.05,
    shaft_inner_radius=0.0,
    hub_outer_radius=0.10,
    length=0.06,
)
DEMO_INTERFERENCE = 3.0e-5
DEMO_FRICTION = 0.15

# 回归基准（与上面闭式推导一致）
EXPECTED_CONTACT_PRESSURE = 47.25e6
EXPECTED_SHAFT_HOOP = -47.25e6
EXPECTED_HUB_HOOP = 78.75e6
EXPECTED_HUB_VON_MISES = 110.25e6
EXPECTED_TORQUE = (
    2.0 * math.pi * DEMO_FRICTION * 47.25e6 * 0.05**2 * 0.06
)

PRESET_DESCRIPTION = (
    "钢轴配钢毂手算基准：实心轴 r_i=50 mm、r_o=100 mm、L=60 mm，"
    "E=210 GPa、nu=0.3、屈服 250 MPa，单边过盈 0.03 mm，mu=0.15；"
    "接触压力 47.25 MPa，毂面环向应力 78.75 MPa，"
    "毂等效应力 110.25 MPa（未屈服），可传转矩约 6679.8 N·m。"
)


def example_request() -> dict:
    """该预置算例对应的 /calculate 请求体（点名预置档 + 本次过盈/摩擦）。"""
    return {
        "profile": PRESET_NAME,
        "interference": DEMO_INTERFERENCE,
        "friction_coefficient": DEMO_FRICTION,
    }


def preset_catalog() -> list[dict]:
    """预置算例目录。"""
    return [
        {
            "name": PRESET_NAME,
            "description": PRESET_DESCRIPTION,
            "registered": True,
            "example_request": example_request(),
            "expected": {
                "contact_pressure_pa": EXPECTED_CONTACT_PRESSURE,
                "shaft_hoop_stress_pa": EXPECTED_SHAFT_HOOP,
                "hub_hoop_stress_pa": EXPECTED_HUB_HOOP,
                "hub_equivalent_stress_pa": EXPECTED_HUB_VON_MISES,
                "torque_capacity_nm": EXPECTED_TORQUE,
                "yielded": False,
            },
        }
    ]
