# 过盈配合接触核算服务

轴—轮毂过盈（压）配合的常驻 HTTP 核算服务：给定几何、材料、过盈量与摩擦系数，
按 Lamé 厚壁圆筒理论计算**接触压力**、**最大可传转矩/轴向力**和轴、孔在接触面
处的**环向应力**，并做接触面屈服校核。仅提供 HTTP/JSON 接口，无网页界面，
不涉及采购与库存。

- 运行时：Python 3.12，FastAPI，纯标准库数学（封闭解析解，无需求解器）
- 配合档：进程内按名登记的可复用材料/几何参数，不落库、不跨重启
- 单位约定：长度 **mm**、弹性模量输入 **GPa**、应力 **MPa**、转矩 **N·m**

## 物理模型

配合面标称半径 R，轴内孔半径 R_i（实心轴为 0），轮毂外半径 R_o，径向过盈量 δ。
轴外表面径向收缩、毂孔内表面径向胀开，位移之和等于过盈量（位移连续条件）：

```
p = δ / [ R · ( κ_s/E_s + κ_h/E_h ) ]

κ_s = (R² + R_i²)/(R² - R_i²) - ν_s    # 轴；实心轴退化为 1 - ν_s
κ_h = (R_o² + R²)/(R_o² - R²) + ν_h    # 轮毂
```

轮毂越厚（R_o 越大）κ_h 越小、组合柔度越低，同过盈下接触压力越高。
配合面应力与承载：

```
σ_θ,s = -p·(R²+R_i²)/(R²-R_i²)        轴面环向（压）
σ_θ,h =  p·(R_o²+R²)/(R_o²-R²)        毂面环向（拉）
σ_r   = -p                            配合面径向
T_max = μ·p·2πR²L                     最大可传转矩（μ 由调用方给定）
F_max = μ·p·2πRL                      最大轴向力
```

屈服校核取配合面平面应力 von Mises：`σ_vm = √(σ_θ² + σ_r² − σ_θσ_r)`。
任一侧超过其屈服强度即返回明确警告，且**不再给出可传转矩**（字段为 `null`），
不把已进入塑性的弹性接触压力乘摩擦系数当作承载上限。

温差装配（可选，调用方提供才计入）：

```
δ_eff = δ + (α_h·ΔT_h − α_s·ΔT_s)·R
```

ΔT 均为相对装配环境的温升（正为加热）；加热轮毂、冷却轴均增大可装配过盈。

## 一键构建与运行

```bash
docker build -t pressfit .
docker run --rm -p 8000:8000 pressfit        # 接口直接对外可用
```

容器内跑交付测试：

```bash
docker run --rm pressfit python -m pytest -q
```

本地裸跑（Python 3.12）：

```bash
pip install -r requirements-dev.txt
python -m pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

服务启动后交互文档位于 `/docs`（OpenAPI），存活探针 `GET /health`。

## 接口

### 直接核算 `POST /api/calculate`

```json
{
  "params": {
    "geometry": {
      "contact_radius_mm": 25,
      "shaft_inner_radius_mm": 0,
      "hub_outer_radius_mm": 50,
      "length_mm": 40
    },
    "shaft_material": {"elastic_modulus_gpa": 210, "poisson_ratio": 0.3,
                        "yield_strength_mpa": 400, "thermal_expansion_per_k": 1.2e-5},
    "hub_material":   {"elastic_modulus_gpa": 210, "poisson_ratio": 0.3,
                        "yield_strength_mpa": 400, "thermal_expansion_per_k": 1.2e-5},
    "interference_mm": 0.02,
    "friction_coefficient": 0.15,
    "thermal": {"hub_delta_t_k": 80, "shaft_delta_t_k": 0}
  }
}
```

`friction_coefficient`（摩擦系数）和 `thermal`（温差装配）均为可选，不给就
不核算转矩、不叠加热过盈，服务从不自行假定。响应示例（常温工况）：

```json
{
  "contact_pressure_mpa": 63.0,
  "effective_interference_mm": 0.02,
  "max_transmissible_torque_nm": 1484.40,
  "max_axial_force_n": 59376.1,
  "shaft_interface_stress": {"hoop_mpa": -63.0, "radial_mpa": -63.0, "von_mises_mpa": 63.0},
  "hub_interface_stress":   {"hoop_mpa": 105.0, "radial_mpa": -63.0, "von_mises_mpa": 147.0},
  "within_elastic": true,
  "warnings": []
}
```

### 配合档（进程内登记）

```bash
# 登记
curl -X POST localhost:8000/api/fits -H 'Content-Type: application/json' -d \
  '{"name":"steel-50x40","params":{ ... 同上 ... }}'
# 点名核算（可临时覆盖过盈量/摩擦系数/温差，不改动登记档本体）
curl -X POST localhost:8000/api/calculate -H 'Content-Type: application/json' -d \
  '{"fit":"steel-50x40","interference_mm":0.04}'
```

另支持 `GET /api/fits`、`GET /api/fits/{name}`、`DELETE /api/fits/{name}`。

### 非法输入

计算开始前统一校验并返回 **422** 与中文原因（不是跑到中途报栈）：过盈量为负、
零过盈又要求算转矩、任一半径不为正或几何不包含、配合长度不为正、弹性模量不为正、
泊松比越界、摩擦系数为负、给了温差但缺线膨胀系数等。点名不存在的档返回 **404**。

## 预置手算算例（回归基准）

钢轴配钢毂：R = 25 mm（Ø50）、R_o = 50 mm（Ø100）、实心轴、L = 40 mm、
E = 210 GPa、ν = 0.3、δ = 0.02 mm、μ = 0.15：

```
κ_s = 0.7，κ_h = 5/3 + 0.3 ≈ 1.96667
p   = 0.02 × 210000 / [25 × 2.66667] = 63.0 MPa
σ_θ,h = 105.0 MPa，σ_θ,s = −63.0 MPa
σ_vm,h = 147.0 MPa，σ_vm,s = 63.0 MPa
T = 0.15 × 63 × 2π × 25² × 40 / 1000 ≈ 1484.40 N·m
```

该算例以 `tests/test_preset.py` 钉为回归基准；`tests/` 同时钉牢以下规律：

- 过盈量为零 → 接触压力为零、可传转矩为零
- 过盈量翻倍 → 接触压力与可传转矩同步翻倍
- 摩擦系数翻倍 → 转矩翻倍、接触压力不变
- 轮毂加厚（外径加大）→ 同过盈下接触压力升高
- 屈服后给出警告且不返回弹性外推转矩；温差等效过盈叠加与校验

## 代码组织

| 模块 | 职责 |
| --- | --- |
| `app/elasticity.py` | 位移连续与组合柔度：Lamé 解、接触压力、配合面应力 |
| `app/torque.py` | 接触压力 → 最大可传转矩/轴向力的摩擦换算 |
| `app/yieldcheck.py` | von Mises 等效应力与屈服警告 |
| `app/validation.py` | 计算前输入合法性检查（带原因） |
| `app/registry.py` | 进程内命名配合档登记（深拷贝隔离） |
| `app/schemas.py` | Pydantic 请求/响应模型 |
| `app/service.py` | 编排各计算块、温差等效过盈、拼装结果 |
| `app/main.py` | FastAPI 接口层，只做接入与调度 |
