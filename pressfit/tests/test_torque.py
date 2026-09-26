"""接触压力 → 可传转矩换算的测试。"""

from __future__ import annotations

import pytest

from app import torque


def test_torque_scales_linearly_with_friction():
    """摩擦系数单独翻倍，转矩翻倍（换算块本身不含压力，压力无从变化）。"""
    t1 = torque.max_transmissible_torque_nm(0.10, 50.0, 25.0, 40.0)
    t2 = torque.max_transmissible_torque_nm(0.20, 50.0, 25.0, 40.0)
    assert t1 > 0
    assert t2 == pytest.approx(2.0 * t1, rel=1e-12)


def test_torque_scales_linearly_with_pressure():
    """接触压力翻倍，可传转矩同步翻倍。"""
    t1 = torque.max_transmissible_torque_nm(0.15, 63.0, 25.0, 40.0)
    t2 = torque.max_transmissible_torque_nm(0.15, 126.0, 25.0, 40.0)
    assert t2 == pytest.approx(2.0 * t1, rel=1e-12)


def test_zero_pressure_gives_zero_torque():
    """过盈量为零、接触压力为零时，可传转矩也为零。"""
    assert torque.max_transmissible_torque_nm(0.15, 0.0, 25.0, 40.0) == 0.0


def test_torque_hand_calc_value():
    """预置算例手算值：T ≈ 1484.40 N·m。

    T = 0.15 × 63 N/mm² × 2π × 25² mm² × 40 mm / 1000
    """
    value = torque.max_transmissible_torque_nm(0.15, 63.0, 25.0, 40.0)
    assert value == pytest.approx(1484.40, rel=1e-4)
