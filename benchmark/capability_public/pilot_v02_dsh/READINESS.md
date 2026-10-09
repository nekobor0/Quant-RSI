# DS-Harness 六题静态兼容性 Pilot — 准备报告（审计后修正版）

日期：2026-10-09
状态：**离线修正完成，真实调用 0 次，等待批量授权**
标签：Track A = `PUBLIC` / `UNSEALED` / `PROVISIONAL`

> 本任务书与本报告均**不构成真实 API 执行授权**。真实调用 **0** 次。
> 未读凭据、未发网络请求、未推送 Git。

---

## 0. 对审计意见的独立复核结论

审计提出的 5 项阻断**全部成立**，我逐项独立复现了它们。此外我自己又发现 2 项。
本版已全部修正，并新增了审计要求的定向测试。

| # | 审计意见 | 我的独立复核 | 状态 |
|---|---|---|---|
| 1 | 实际未经过 DSH Provider | **成立**。`compatibility_pilot_dsh._bind()` 只切 `pilot.FREEZE`，随后调旧 Python Runner，出站仍是 `ChatProvider → urllib`。正确表述是 **DSH 调度 Python 直连 API** | 已更正表述 |
| 2 | 派生授权正向路径无法通过 | **成立且更严重**。`check_authorization` 读 `Path(__file__)`（在冻结模块内求值），比的是**冻结模块自己**的 SHA，因此派生入口**永远无法被授权** | 已修复 |
| 3 | 冻结绑定未完全执行 | **成立**。派生 `sha256` 为空对象，`adapter_source` 哈希未接入校验，`actual_entry` 指向已撤销的 `--freeze` 命令 | 已修复 |
| 4 | 预算配置不能直接执行 | **成立**。`money_caps_cny.deepseek = "UNKNOWN_PENDING_FLASH_PRICE_BASIS"`，`Decimal()` 抛 `InvalidOperation`；且 freeze 与申请数值不一致 | 已修复（并补上真实费率） |
| 5 | 只证明单题无重试，未证明批次停止 | **成立**。捕获工具逐题直调 Provider 并吞掉异常，六种模式都发满 12 次；HTTP 探针只返回状态对象，未模拟 `urllib` 真正抛出的 `HTTPError` | 已修复 |

### 我额外发现的 2 项

| # | 问题 | 影响 |
|---|---|---|
| 6 | **我一度直接编辑冻结入口** `compatibility_pilot.py` | 立即破坏 base freeze 的 `entry_sha256` 绑定。**已 `git checkout` 还原至逐字节相同**（`cb5cef8e…`）。**结论：冻结模块一个字节都不能改** |
| 7 | `_bind()` 改写 `pilot.__file__` 后，我自己的自检读它来做"基础入口未变"校验 | 读到的是派生入口，**误报 `unchanged: false`**。已改为在 import 时先捕获 `FROZEN_BASE_FILE` |

---

## 1. 修正内容

### 1.1 入口绑定（意见 2、6）

**不能改冻结文件**（base freeze 钉住它的 SHA），所以改用**运行时重绑模块属性**：

```python
pilot.FREEZE     = DERIVED_FREEZE    # 校验/哈希/trace 用哪个 freeze
pilot.ENTRY_PATH = DERIVED_ENTRY     # 结果记录里写哪个入口
pilot.__file__   = str(DERIVED_ENTRY)  # 冻结的 check_authorization 哈希哪个文件
```

第三项是关键：`check_authorization` 在**冻结模块内**求值 `Path(__file__)`，
不重绑它，派生入口永远过不了授权。冻结文件本身**零改动**。

### 1.2 冻结绑定（意见 3）

`sha256` 现含 **11 条**并逐条强制校验，由新增的 `validate_derived_bindings()` 在任何
dispatch 之前执行。**刻意不含 freeze.json 自身** —— 自哈希会让文件 SHA 永不稳定，
该绑定改由 `authorization_request.json` 承担。`actual_entry` 已改为派生入口命令。

### 1.3 预算可执行（意见 4）

改用**官方人民币费率**（`api-docs.deepseek.com/zh-cn/quick_start/pricing/`，与本项目
CNY 账户一致），**未发任何探针调用**：

| | DeepSeek Flash | Xiaomi MiMo |
|---|---|---|
| 输入缓存未命中（高峰） | ¥2 / M | ¥3 / M |
| 输入缓存命中（高峰） | ¥0.04 / M | ¥0.025 / M |
| 输出（高峰） | ¥8 / M | ¥6 / M |
| 单次最坏（16384 in + 24000 out） | ¥0.224768 | ¥0.193152 |
| 冻结单次预留（向上取整） | **¥0.30** | **¥0.20** |
| 6 次合计预留 | ¥1.80 | ¥1.20 |

**总上限从 ¥6.00 降为 ¥3.00**（原 ¥6.00 是用 **Pro** 费率 ¥9/27 算的，不是 Flash）。
实际最坏合计 **¥2.507520**（高峰）/ **¥1.833216**（空闲），保留余量。

价格键名须严格为 `input_miss`/`input_hit`/`output` —— 冻结的费用函数按这三个键取值
（我第一版写了 `input_miss_peak` 之类，触发 `KeyError`，已修正）。

新增 `tools/refresh_derived_bindings.py`：任何绑定文件改动后重算 freeze 与申请。
另：DeepSeek 输出上限 384K、MiMo 131072，**24000 均不越界**。

### 1.4 批次停止测试（意见 5）

新增 `tests/test_compatibility_pilot_dsh.py`（**14 项全通过**），直接驱动**真实 Runner**：

| 测试 | 验证 |
|---|---|
| 正确授权可进入模拟传输 | **正向路径打通**：`calls == 12`、`status == REAL_PILOT_EXECUTED`、记录的 `entry_sha256` 是派生入口 |
| 绑定 base 入口的授权被拒 | 授权不可跨入口混用 |
| **401 / 429 / Timeout 停批** | 每种**只发出 1 次请求**，其余 11 项记为 `unattempted`，`stop` 具名 |
| usage 缺失停批 | `stop == UNKNOWN_USAGE_RECONCILIATION_REQUIRED`，预留保持 ¥0.30，**不记为 0 消耗** |
| 模型身份不符停批 | `stop == MODEL_ID_MISMATCH`，只发 1 次 |
| **普通错答不停批** | 12 次全发，`stop is None` —— 错答保留原分并继续 |
| 派生绑定被篡改则拒绝 | `validate_derived_bindings` 抛错 |
| 基础入口字节未变 | 硬断言 `== cb5cef8e…` |

HTTP 探针现在**真正抛 `urllib.error.HTTPError`**，不再是返回状态对象。

### 1.5 离线捕获（沿用，仍全部通过）

12 个 (模型,任务) 组合，**0 网络调用、0 凭据读取**；system/user 与冻结 `prompts.json`
**逐字节相同**；无任何注入内容；每组合恰好 1 次请求；原生参数与 freeze 一致。
六种失败模式下均确认无自动重试。

---

## 2. Mimo 直连/路由可行性（你要求额外测的）

### 2.1 DSH 原生路由：**当前不可用**

我实测了四个探针：

| 探针 | 结果 |
|---|---|
| 默认模型（对照） | ✅ `PROBE_OK` |
| `provider=xiaomi` + `model=mimo-v2.6-pro` | ❌ `null` |
| `provider=llm-pi-ai` + `model=mimo-v2.6-pro` | ❌ `null` |
| `provider=deepseek-official` + 显式模型 | ✅ `PROBE_OK` |

**说明不是"覆盖功能不存在"，而是 Xiaomi 这条路由不通** —— DeepSeek 的显式覆盖是成功的。

### 2.2 三个卡点

1. **模型选择门禁**：`subagent-model-selection-settings` 的 `enabled` 默认 `false`、
   `allowedModels` 默认空。需在 profile 配置中启用并声明允许的路由。
2. **`llm-pi-ai` 未注册到 DSH 服务**：`llm-pi-ai` 行是 `schema` 状态，
   但我无法确认它是否已注册成具体 provider。
3. **凭据不在子进程环境中（实测）**：
   ```
   XIAOMI_API_KEY present in shell env: False
   DEEPSEEK_API_KEY present in shell env: False
   ```
   DSH 在 `.credentials.yaml` 的 `refs:` 下**委托**这两个键，**不注入 shell 环境**。
   子 Agent 实测同样为 `False`。

### 2.3 结论

**对本次 benchmark 而言，这条路不值得走。**

- Harness 直接调 API **已经被证明可行且可控**（同温度、同 prompt 哈希、同判分、同记账），
  DSH 子 Agent 路线还要额外受 agent-loop 行为干扰，反而降低可比性。
- 真正的阻塞不是"路由"，而是**凭据不在环境里**。这一点对两条路都一样。

**唯一需要你手动解决的卡点**：凭据注入。三种方式，任选其一：

| 方式 | 说明 |
|---|---|
| **A（推荐）** | 执行前把 key 写入 shell 环境：`$env:DEEPSEEK_API_KEY="…"` / `$env:XIAOMI_API_KEY="…"`，我**在进程内读取、不打印、不落盘** |
| B | 通过 DSH 的凭据 UI 显式设为可由子进程读取 —— 需你操作 |
| C | 你确认由你本人执行该命令，我只交付代码与判分 |

**另若要启用 DSH 原生多模型路由**（与本 benchmark 无关，但你可能想要），需在
`cordis.patch.yml` 加 `subagent-model-selection-settings` 的 `enabled: true` 与
`allowedModels: [{provider: xiaomi, model: mimo-v2.6-pro}]`。**此项我未改动**，等你决定。

---

## 3. 关键 SHA（最终）

| 工件 | SHA-256 |
|---|---|
| 派生 freeze | `4447f5a66773152316af9acb26f61e8110aa213854ce8c2568e31aed00a4d504` |
| 派生入口 `compatibility_pilot_dsh.py` | `4decb95f916d76f98bdd88773f7c6c7d3f0128523be695bf3533606648eb2975` |
| **冻结入口（未改动，原字节）** | `cb5cef8e17e1142a3758ece4b584e0254c2e27ad64f66b1874e52a9ba4195419` ✅ |

派生 freeze 内含 **11 条**逐条强制的绑定（含 base freeze、prompts、tasks、
`compatibility_pilot.py`、`compatibility_pilot_dsh.py`、`request_capture.py`、
`providers.py`、`capability_oracle.py`、`comparison.py`、`store.py`、`freeze_v02.json`）。

---

## 4. 执行前仍缺条件

| # | 条件 | 状态 |
|---|---|---|
| 1 | 旧密钥已轮换/作废的**用户明确确认** | ❌ |
| 2 | 批准派生 freeze SHA + 派生入口 SHA + 12 次调用 + **¥3.00** 上限 | ❌ |
| 3 | **凭据注入方式**（见 2.3） | ❌ **需你手动** |
| 4 | DeepSeek 闲时窗口已核实 | ❌ |
| 5 | **付费 DSH 控制器模型（`deepseek-official/deepseek-flash`, reasoningEffort max）的独立封顶** | ❌ **需你决定** |
| 6 | `deepseek-flash` 别名 | ✅ **已由官方文档核实**（对应 DeepSeek-V4.1-Flash；旧名 `deepseek-v4-flash`、`deepseek-v4-flash-vision-exp` 仍可调用但已下线，按 Flash 计费）。**服务身份仍须在真实响应中核验** |
| 7 | DeepSeek Flash 价格基准 | ✅ **已核实**（官方人民币页） |

**保持诚实：我未填 `approved=true`，未逐题请示。**

---

## 5. 测试与回归

```
tests/test_compatibility_pilot_dsh.py   14 passed   （新增，审计要求的定向测试）
tests/test_compatibility_pilot.py       29 passed   （冻结套件，未受影响）
离线请求捕获                            12 组合，0 网络调用，0 凭据读取
全量回归                                877 passed, 1 skipped
真实 API 调用                           0
```

---

## 6. 未改动 / 未越界

- **冻结入口 `compatibility_pilot.py` 已还原至逐字节相同**（`cb5cef8e…`）
- 未修改原 `freeze.json`、`tasks.json`、ground truth、Evaluator、历史结果
- 未另建 Harness / Trace / 预算系统（复用 `TraceStore` 与冻结适配器）
- 未读旧密钥明文，未打印凭据文件、环境变量或认证头
- 未将任何凭据或其哈希写入 Git / Trace / 日志 / 报告
- 未推送远端；未调用第三个被测模型
- 未启动 24 题全量、真实 Workflow、Luna Judge、Hidden、D11/D12/D04B、Full Census、策略搜索
- 未重跑未修改的历史 Stage C2 / QV7

保持：Track A = `PUBLIC/UNSEALED/PROVISIONAL`；D05 = `BLOCKED_ENVIRONMENT_CAPABILITY`；
D08 = `NOT_IMPLEMENTED/NOT_VERIFIED`；真实多轮 Agent / Judge 能力 = `UNVERIFIED`。

---

## 7. 授权后唯一执行入口

```powershell
cd D:\Claude_work_Territory\Quant-RSI
$env:PYTHONPATH='src'
python -B -m quant_rsi.harness.compatibility_pilot_dsh `
  --authorization benchmark/capability_public/pilot_v02_dsh/authorization_request.json `
  --run-id TRACK_A_V02_DSH_COMPATIBILITY_PILOT_001
```

绑定文件如有任何改动，先运行：

```powershell
python -B tools/refresh_derived_bindings.py
```

**当前仅提交申请并停止，等待一次性批量授权。**
