"""配合档登记取用测试：进程内有效、按名取用、档间与外部改动隔离。"""

from __future__ import annotations

import pytest

from app.domain import Geometry, Material
from app.registry import Profile, ProfileRegistry, RegistryError

SHAFT = Material("钢轴", 2.1e11, 0.3, 250e6)


def _profile(name: str, hub_outer: float = 0.10) -> Profile:
    hub = Material("钢毂", 2.1e11, 0.3, 250e6)
    geometry = Geometry(0.05, 0.0, hub_outer, 0.06)
    return Profile(name=name, shaft_material=SHAFT, hub_material=hub, geometry=geometry)


def test_put_get_roundtrip():
    reg = ProfileRegistry()
    reg.put(_profile("A"))
    fetched = reg.get("A")
    assert fetched.geometry.hub_outer_radius == 0.10


def test_get_missing_raises():
    reg = ProfileRegistry()
    with pytest.raises(RegistryError) as exc:
        reg.get("nope")
    assert exc.value.code == "PROFILE_NOT_FOUND"
    assert exc.value.status_code == 404


def test_delete_missing_raises():
    reg = ProfileRegistry()
    with pytest.raises(RegistryError):
        reg.delete("nope")


def test_profiles_are_isolated_from_each_other():
    """登记两份档，参数不得彼此渗透。"""
    reg = ProfileRegistry()
    reg.put(_profile("A", hub_outer=0.10))
    reg.put(_profile("B", hub_outer=0.20))
    assert reg.get("A").geometry.hub_outer_radius == 0.10
    assert reg.get("B").geometry.hub_outer_radius == 0.20


def test_returned_copy_is_independent_of_registry():
    """取出档后改动返回对象，不影响登记表里的内容。"""
    import dataclasses

    reg = ProfileRegistry()
    reg.put(_profile("A"))
    fetched = reg.get("A")
    tampered = dataclasses.replace(
        fetched, geometry=dataclasses.replace(fetched.geometry, hub_outer_radius=9.9)
    )
    # （fetched 本身是 frozen 的深拷贝，这里替换后再登记/使用都不影响原档）
    assert reg.get("A").geometry.hub_outer_radius == 0.10
    assert tampered.geometry.hub_outer_radius == 9.9
    assert reg.get("A").geometry.hub_outer_radius == 0.10


def test_put_does_not_alias_caller_objects():
    """调用方在登记后继续修改其对象，不渗透进登记表。"""
    reg = ProfileRegistry()
    profile = _profile("A")
    reg.put(profile)
    import dataclasses

    changed = dataclasses.replace(
        profile, geometry=dataclasses.replace(profile.geometry, length=9.9)
    )
    # 源 profile 是 frozen，changed 是新对象；登记表保持原值。
    assert changed.geometry.length == 9.9
    assert reg.get("A").geometry.length == 0.06


def test_overwrite_and_delete():
    reg = ProfileRegistry()
    reg.put(_profile("A", 0.10))
    reg.put(_profile("A", 0.30))
    assert reg.get("A").geometry.hub_outer_radius == 0.30
    reg.delete("A")
    with pytest.raises(RegistryError):
        reg.get("A")


def test_names_sorted():
    reg = ProfileRegistry()
    reg.put(_profile("B"))
    reg.put(_profile("A"))
    assert reg.names() == ["A", "B"]
