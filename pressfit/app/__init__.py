"""过盈配合接触核算服务。

模块划分：

- ``elasticity``：Lamé 厚壁圆筒理论，位移连续条件求接触压力与接触面应力
- ``torque``：接触压力到可传转矩/轴向力的摩擦换算
- ``yieldcheck``：接触面 von Mises 等效应力与屈服警告
- ``validation``：计算前的输入合法性检查
- ``registry``：进程内命名的配合档登记
- ``schemas``：HTTP 请求/响应数据模型
- ``service``：编排各计算块，产出结果
- ``main``：FastAPI 接口层
"""

__version__ = "1.0.0"
