"""配合档登记：按名字保存可复用的材料与几何参数。

只在服务进程运行期间有效（进程内字典），不落库、不跨重启。登记、
取用都做深拷贝，保证各档之间以及"已登记参数"与"本次临时覆盖的
计算"之间参数互不渗透。
"""

from __future__ import annotations

import threading

from .schemas import FitParams


class FitRegistry:
    """线程安全的进程内配合档登记表。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fits: dict[str, FitParams] = {}

    def register(self, name: str, params: FitParams) -> None:
        """以 ``name`` 登记（或覆盖）一份配合档。"""
        if not name or not name.strip():
            from .validation import FitValidationError

            raise FitValidationError("配合档名称不能为空")
        with self._lock:
            # 存深拷贝，调用方后续改动入参对象不会影响已登记内容。
            self._fits[name.strip()] = params.model_copy(deep=True)

    def get(self, name: str) -> FitParams:
        """按名字取用配合档；不存在抛 ``KeyError``。

        返回的是深拷贝，调用方（含计算编排）对返回对象的任何修改都
        不会回写到登记表。
        """
        with self._lock:
            params = self._fits[name]
            return params.model_copy(deep=True)

    def exists(self, name: str) -> bool:
        with self._lock:
            return name in self._fits

    def remove(self, name: str) -> bool:
        """删除一档；不存在返回 False。"""
        with self._lock:
            return self._fits.pop(name, None) is not None

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._fits)


# 进程级单例。
store = FitRegistry()
