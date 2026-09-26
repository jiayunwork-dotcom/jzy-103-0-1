"""配合档登记：进程运行期间可复用的材料与几何参数。

- 只在进程内存活，不落地、不跨重启保留；
- 线程安全（FastAPI 可能用线程池跑同步接口）；
- 存入与取出都做深拷贝，调用方后续改动不会渗透到已登记的档，
  不同档之间参数也互不影响。
"""

from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import dataclass

from .domain import Geometry, Material


class RegistryError(Exception):
    """配合档操作错误。"""

    def __init__(self, code: str, message: str, status_code: int = 404):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class Profile:
    """一份可复用配合档：双方材料 + 几何（过盈与摩擦每次现给）。"""

    name: str
    shaft_material: Material
    hub_material: Material
    geometry: Geometry


class ProfileRegistry:
    """线程安全的进程内配合档登记表。"""

    def __init__(self) -> None:
        self._profiles: dict[str, Profile] = {}
        self._lock = threading.RLock()

    def put(self, profile: Profile) -> None:
        """登记（或覆盖）一份档；存入的是深拷贝。"""
        with self._lock:
            self._profiles[profile.name] = deepcopy(profile)

    def get(self, name: str) -> Profile:
        """按名取档；返回的是深拷贝，调用方改动不影响登记内容。"""
        with self._lock:
            profile = self._profiles.get(name)
            if profile is None:
                raise RegistryError(
                    "PROFILE_NOT_FOUND",
                    f"未找到名为 {name!r} 的配合档；可先登记或改为直接传参计算",
                )
            return deepcopy(profile)

    def delete(self, name: str) -> None:
        with self._lock:
            if name not in self._profiles:
                raise RegistryError(
                    "PROFILE_NOT_FOUND", f"未找到名为 {name!r} 的配合档，无法删除"
                )
            del self._profiles[name]

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._profiles)

    def snapshot(self) -> dict[str, Profile]:
        """返回全部档的深拷贝（调试/展示用）。"""
        with self._lock:
            return deepcopy(self._profiles)
