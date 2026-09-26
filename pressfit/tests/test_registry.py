"""配合档登记表测试：各档各算各的、参数互不渗透。"""

from __future__ import annotations

import pytest

from app.registry import FitRegistry
from tests.conftest import make_params


def test_register_get_roundtrip():
    registry = FitRegistry()
    registry.register("steel-50x40", make_params())
    fetched = registry.get("steel-50x40")
    assert fetched.interference_mm == pytest.approx(0.02)
    assert fetched.geometry.contact_radius_mm == pytest.approx(25.0)
    assert registry.names() == ["steel-50x40"]


def test_get_returns_deep_copy_no_leak_back():
    """取出的对象被改动，不得回写登记表。"""
    registry = FitRegistry()
    registry.register("a", make_params(interference_mm=0.02))
    fetched = registry.get("a")
    fetched.interference_mm = 0.99
    fetched.geometry.contact_radius_mm = 999.0
    assert registry.get("a").interference_mm == pytest.approx(0.02)
    assert registry.get("a").geometry.contact_radius_mm == pytest.approx(25.0)


def test_register_stores_deep_copy_no_leak_in():
    """登记后调用方改动原对象，不得影响已登记内容。"""
    registry = FitRegistry()
    params = make_params(interference_mm=0.02)
    registry.register("a", params)
    params.interference_mm = 0.5
    assert registry.get("a").interference_mm == pytest.approx(0.02)


def test_multiple_fits_are_independent():
    """不同的档各算各的：登记两个几何不同的档，结果互不影响。"""
    registry = FitRegistry()
    registry.register("thin-hub", make_params(hub_outer_radius_mm=40.0))
    registry.register("thick-hub", make_params(hub_outer_radius_mm=80.0))
    thin = registry.get("thin-hub")
    thick = registry.get("thick-hub")
    assert thin.geometry.hub_outer_radius_mm == pytest.approx(40.0)
    assert thick.geometry.hub_outer_radius_mm == pytest.approx(80.0)
    assert registry.names() == ["thick-hub", "thin-hub"]


def test_remove_and_missing_key():
    registry = FitRegistry()
    registry.register("a", make_params())
    assert registry.remove("a") is True
    assert registry.remove("a") is False
    with pytest.raises(KeyError):
        registry.get("a")


def test_blank_name_rejected():
    from app.validation import FitValidationError

    registry = FitRegistry()
    with pytest.raises(FitValidationError, match="名称不能为空"):
        registry.register("   ", make_params())
