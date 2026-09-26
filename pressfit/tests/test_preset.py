"""预置算例回归基准：钢轴配钢毂，手算值钉死。

几何/材料/工况见 tests/conftest.py 顶部注释。预期：
p = 63.0 MPa，T ≈ 1484.40 N·m，轴面环向 -63 MPa、毂面环向 105 MPa，
轴面等效 63 MPa、毂面等效 147 MPa，弹性区内、无警告。
"""

from __future__ import annotations

import pytest

from app import service
from tests.conftest import make_params


def test_steel_on_steel_preset_regression():
    result = service.calculate(make_params())

    # 接触压力为正值，且等于手算基准。
    assert result.contact_pressure_mpa > 0
    assert result.contact_pressure_mpa == pytest.approx(63.0, abs=1e-9)

    # 可传转矩。
    assert result.max_transmissible_torque_nm == pytest.approx(1484.40, rel=1e-4)
    assert result.max_axial_force_n == pytest.approx(
        0.15 * 63.0 * 2.0 * 3.141592653589793 * 25.0 * 40.0, rel=1e-12
    )

    # 配合面环向应力与等效应力。
    assert result.shaft_interface_stress.hoop_mpa == pytest.approx(-63.0, abs=1e-9)
    assert result.hub_interface_stress.hoop_mpa == pytest.approx(105.0, abs=1e-9)
    assert result.shaft_interface_stress.radial_mpa == pytest.approx(-63.0, abs=1e-9)
    assert result.hub_interface_stress.radial_mpa == pytest.approx(-63.0, abs=1e-9)
    assert result.shaft_interface_stress.von_mises_mpa == pytest.approx(63.0, abs=1e-9)
    assert result.hub_interface_stress.von_mises_mpa == pytest.approx(147.0, abs=1e-9)

    # 屈服强度 400 MPa 下应处于弹性区，无警告。
    assert result.within_elastic is True
    assert result.warnings == []
    assert result.effective_interference_mm == pytest.approx(0.02)
