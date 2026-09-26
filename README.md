# 过盈配合核算服务（interference-fit-service）

常驻 HTTP 服务，装配前核算**轴—轮毂过盈配合**的接触压力、靠摩擦可传递的
最大转矩、配合面环向应力，并做屈服安全提示。只提供 HTTP 接口，无网页界面，
不涉及采购或库存。

实现语言 Python（容器运行时 **3.12**，本地最低 3.11 可跑），接口层
**FastAPI**，数值部分只依赖闭式解（标准库 `math`），无重型数值栈。

---

## 力学模型（位移连续 → 组合柔度 → 接触压力）

轴外半径与孔内半径标称相同，半径差为**径向过盈量** `δ`。压合后轴面内缩
`u_s`、毂面外胀 `u_h`，位移连续：

```
δ = u_s + u_h
```

接触面压力 `p` 下，按厚壁圆筒 Lamé 解，各零件写成 `u = p · r_i · C`：

```
轮毂 C_h = (1/E_h) · ( (r_o² + r_i²)/(r_o² − r_i²) + ν_h )
轴   C_s = (1/E_s) · ( (r_i² + r_si²)/(r_i² − r_si²) − ν_s )   # 空心轴
         = (1/E_s) · (1 − ν_s)                                 # 实心轴（r_si=0）
```

于是

```
p = δ / ( r_i · (C_s + C_h) )
```

配合面环向应力（拉为正）：

```
毂：σ_t,h = p · (r_o² + r_i²)/(r_o² − r_i²)
轴：σ_t,s = −p · (r_i² + r_si²)/(r_i² − r_si²)（实心退化为 −p）
```

可传转矩（圆柱配合面 `A = 2π·r_i·L`）：

```
T = μ · p · A · r_i = 2π · μ · p · r_i² · L
```

摩擦系数 `μ` **必须由调用方给定**，服务不自行假定。

等效应力按配合面处平面应力近似（`σ_r = −p, σ_z = 0`）的 von Mises：

```
σ_v = √(σ_t² + p² + σ_t·p)
```

任一侧 `σ_v` 超过其屈服强度即标记屈服：此时 `torque_capacity` 返回 `null`，
只在 `nominal_torque` 给弹性公式外推值并附明确警告，避免把已进入塑性的
结果误当弹性安全转矩上限。

温差装配：给定双方温升与线膨胀系数才计入，热过盈定义为
`δ_t = α_s·ΔT_s·r_i − α_h·ΔT_h·r_i`，与机械过盈代数相加
（热装毂加热时为负，有效过盈下降）；**没给就不编造**。

---

## 目录结构（按职责分块）

| 文件 | 职责 |
|---|---|
| `app/elasticity.py` | 位移连续 / 组合柔度 / 接触压力 / 环向应力 / 温差等效过盈 |
| `app/torque.py` | 接触压力 → 接触面积 → 可传转矩 |
| `app/strength.py` | von Mises 等效应力与屈服校核 |
| `app/registry.py` | 进程内配合档登记（线程安全、深拷贝隔离） |
| `app/validation.py` | 输入合法性检查（计算前拦截，带原因） |
| `app/service.py` | 计算编排，把各块串起来（不接触 HTTP） |
| `app/schemas.py` | HTTP 数据契约（Pydantic）与领域对象互转 |
| `app/api.py` | FastAPI 接口层：收发、调各块、拼结果 |
| `app/presets.py` | 钢轴—钢毂手算基准预置算例 |
| `app/domain.py` | 纯领域数据结构 |

---

## 一键构建与运行

容器一起来接口即对外可用（端口 8000）：

```bash
docker build -t interference-fit-service .
docker run --rm -p 8000:8000 interference-fit-service
# 或
docker compose up --build
```

本地直接跑：

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

启动后：

- 健康检查：`GET http://localhost:8000/health`
- 交互式文档：`http://localhost:8000/docs`
- 预置算例目录：`GET /presets`

---

## 接口

### `POST /calculate` —— 过盈配合核算

既可点名已登记档，也可直接传材料与几何。单位建议 SI（m、Pa、N·m）。

直接传参：

```bash
curl -s -X POST localhost:8000/calculate -H 'Content-Type: application/json' -d '{
  "shaft": {"name":"钢轴","elastic_modulus":2.1e11,"poisson_ratio":0.3,"yield_strength":250e6},
  "hub":   {"name":"钢毂","elastic_modulus":2.1e11,"poisson_ratio":0.3,"yield_strength":250e6},
  "geometry": {"shaft_outer_radius":0.05,"shaft_inner_radius":0.0,
               "hub_outer_radius":0.10,"length":0.06},
  "interference": 0.00003,
  "friction_coefficient": 0.15
}'
```

点名已登记档（过盈、摩擦每次现给；几何可逐项覆盖）：

```json
{
  "profile": "steel-demo",
  "interference": 0.00003,
  "friction_coefficient": 0.15,
  "geometry_override": {"hub_outer_radius": 0.12}
}
```

温差装配（可选，整块给了才计入）：

```json
"assembly": {"alpha_shaft":1.2e-5,"alpha_hub":1.2e-5,
             "delta_t_shaft":0.0,"delta_t_hub":20.0}
```

响应主要字段：

| 字段 | 含义 |
|---|---|
| `contact_pressure` | 接触压力 p（Pa） |
| `contact_area` | 圆柱配合面面积（m²） |
| `torque_capacity` | 弹性可传转矩（N·m）；屈服/未给 μ 时为 `null` |
| `nominal_torque` | 摩擦公式外推的名义转矩，仅参考 |
| `yielded` / `warnings` / `notes` | 屈服标志、警告、说明 |
| `shaft` / `hub` | 各自环向应力、接触压力、等效应力、屈服强度、是否屈服 |
| `interference` / `thermal_interference` / `effective_interference` | 机械/温差/有效过盈 |
| `shaft_compliance` / `hub_compliance` / `combined_compliance` | 柔度系数 |
| `shaft_radial_displacement` / `hub_radial_displacement` | 表面径向位移（两者之和等于过盈量） |

### 配合档登记（仅进程内有效）

- `GET  /profiles` 列出全部档
- `PUT  /profiles/{name}` 登记/覆盖（登记前做同样的合法性校验）
- `GET  /profiles/{name}` 取名
- `DELETE /profiles/{name}` 删除
- `GET  /presets` 预置手算基准目录

预置档 `steel-demo` 启动即登记、受保护不可改删。不同档各算各的，
登记表存取均做深拷贝，参数互不渗透，也不受调用方后续改动影响。

---

## 输入校验（计算前拦截，统一 422，带中文原因）

- 过盈量为负 → 拒绝；有效过盈（含温差）为负 → 拒绝；
- 过盈量为零且又给了摩擦系数要求算转矩 → 拒绝；
  零过盈退化核对请省略 `friction_coefficient`（此时压力为零）；
- 任一半径不为正、轴内半径 ≥ 轴外半径、毂外半径 ≤ 轴外半径 → 拒绝；
- 配合长度不为正 → 拒绝；
- 弹性模量不为正、泊松比越界、屈服强度（若给）非正 → 拒绝；
- 摩擦系数为负、各数值非有限值 → 拒绝。

错误形如：

```json
{"error": {"code": "INTERFERENCE_NEGATIVE",
           "field": "interference",
           "message": "机械过盈量不允许为负……"}}
```

---

## 预置手算基准（回归钉死）

实心钢轴配钢毂：`r_i=50 mm, r_o=100 mm, L=60 mm, E=210 GPa, ν=0.3,
屈服 250 MPa, δ=0.03 mm（单边）, μ=0.15`。

- 接触压力 **47.25 MPa**（正值）
- 轴环向应力 **−47.25 MPa**，毂环向应力 **+78.75 MPa**
- 毂内表面等效应力 **110.25 MPa < 250 MPa**（弹性安全，无警告）
- 可传转矩 **≈ 6679.8 N·m**

推导见 `app/presets.py` 顶部注释。

---

## 测试

```bash
pip install -r requirements-dev.txt
pytest
```

测试逐条钉住：

1. 过盈为零 → 接触压力为零、转矩为零；
2. 过盈翻倍 → 接触压力与可传转矩同步翻倍；
3. 摩擦系数单独翻倍 → 转矩翻倍而压力不变；
4. 轮毂加厚（外径加大）→ 组合柔度下降、同过盈下压力升高（单调 + 多点）；
5. 预置钢轴—钢毂算例数值回归；
6. 屈服时转矩上限置空并告警、未给屈服强度只算不判、空心薄壁轴先屈服；
7. 温差只在给定时叠加、热装降低有效过盈与压力；
8. 全部非法输入 422 带原因；配合档隔离、生命周期、预置档保护；
9. HTTP 层把上述核心关系与错误结构再钉一遍。
