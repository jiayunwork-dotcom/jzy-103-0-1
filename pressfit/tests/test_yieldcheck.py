"""屈服校核与"进入塑性不返回弹性转矩上限"行为的测试。"""

from __future__ import annotations

import pytest

from app import service
from app.elasticity import ContactSolution
from app.yieldcheck import assess_yield, von_mises_plane_stress


def test_von_mises_hand_calc():
    """预置算例：轴面 63 MPa、毂面 147 MPa。"""
    assert von_mises_plane_stress(-63.0, -63.0) == pytest.approx(63.0, abs=1e-9)
    assert von_mises_plane_stress(105.0, -63.0) == pytest.approx(147.0, abs=1e-9)


def test_assessment_no_yield_strength_means_elastic():
    """未提供屈服强度时不做猜测，按弹性处理、无警告。"""
    solution = ContactSolution(63.0, -63.0, 105.0, -63.0)
    assessment = assess_yield(solution, None, None)
    assert assessment.within_elastic is True
    assert assessment.warnings == ()


def test_assessment_below_yield_is_elastic():
    solution = ContactSolution(63.0, -63.0, 105.0, -63.0)
    assessment = assess_yield(solution, 400.0, 400.0)
    assert assessment.within_elastic is True
    assert assessment.warnings == ()
    assert assessment.shaft_von_mises == pytest.approx(63.0)
    assert assessment.hub_von_mises == pytest.approx(147.0)


def test_hub_yield_exceeded_flags_warning():
    """毂面等效应力 147 MPa > 屈服 100 MPa，必须给出明确屈服警告。"""
    solution = ContactSolution(63.0, -63.0, 105.0, -63.0)
    assessment = assess_yield(solution, 400.0, 100.0)
    assert assessment.within_elastic is False
    assert len(assessment.warnings) == 1
    assert "轮毂" in assessment.warnings[0]
    assert "塑性" in assessment.warnings[0]


def test_service_withholds_torque_after_yield():
    """已屈服时不能把弹性压力乘摩擦系数当作可传转矩上限返回。"""
    from tests.conftest import make_params

    params = make_params(hub_yield=100.0)  # 毂面 147 MPa > 100 MPa
    result = service.calculate(params)
    assert result.within_elastic is False
    assert result.warnings  # 有明确警告，绝不闷头返回
    assert result.max_transmissible_torque_nm is None
    assert result.max_axial_force_n is None
    # 接触压力本身仍作为弹性参考值给出。
    assert result.contact_pressure_mpa == pytest.approx(63.0, abs=1e-9)


def test_service_elastic_case_returns_torque():
    from tests.conftest import make_params

    result = service.calculate(make_params(hub_yield=400.0))
    assert result.within_elastic is True
    assert result.warnings == []
    assert result.max_transmissible_torque_nm == pytest.approx(1484.40, rel=1e-4)
