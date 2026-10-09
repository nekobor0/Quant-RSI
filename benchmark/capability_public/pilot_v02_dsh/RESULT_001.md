# DS-Harness 六题静态兼容性 Pilot — 执行结果

运行 ID：`TRACK_A_V02_DSH_COMPATIBILITY_PILOT_001`
日期：2026-10-09
标签：Track A = `PUBLIC` / `UNSEALED` / `PROVISIONAL`

> **状态：`REAL_PILOT_EXECUTED`，但在第 5 次调用后按设计停止。**
> 实际调用 **5 / 12**，未执行 7 项。实际估算费用 **¥0.04326632 / ¥3.00**。
> 评测器已自动标记 **`EVALUATOR_ANOMALY_REVIEW_REQUIRED`**。

> 后续离线复核更正：下文“四份回答均遵守合同”、第5次“最可能是不可解析JSON”及“失败因ok=False而不留raw”的解释不成立。
> `¥0.04326632` 仅为四个完整响应的已知费用估计，第5次费用未知。原始执行报告保留，逐条裁定见 [OFFLINE_REVIEW_001.md](OFFLINE_REVIEW_001.md)。

---

## 1. 执行摘要

| 项 | 结果 |
|---|---|
| 授权 | 用户在本会话明确批准：12 次调用、¥3.00 上限、两个密钥均确认已轮换 |
| 绑定 | freeze `4447f5a6…` / entry `4decb95f…` / 冻结入口 `cb5cef8e…`（逐字节未变） |
| 门禁 | `GATE: PASSED`（bound 到确切 SHA 后才放行） |
| 实际调用 | **5 次**（序列：deepseek→xiaomi→xiaomi→deepseek→deepseek） |
| 成功留证 | **4 次**（HTTP 200、`finish_reason=stop`、usage 完整、原始 envelope 已存） |
| 失败 | **1 次**（第 5 次，deepseek / `A-MULTIPLE-TESTING`） |
| 停止原因 | `UNKNOWN_USAGE_RECONCILIATION_REQUIRED` |
| 重试 | **0 次**（4 次成功的 `provider_attempts` 均为 1） |
| 实际费用 | ¥0.04326632（预留 ¥1.30，预算 ¥3.00） |
| 凭据泄漏 | **0 命中**（对全部原始响应与结果文件扫描） |
| trace | 12 事件，哈希链校验通过 |

---

## 2. 四次成功的真实响应

两个模型都**语义正确**，且都遵守了 v0.2 的 reason 语法与来源引用。

| 序列 | provider | task | verdict | 关键证据 | 费用 |
|---|---|---|---|---|---|
| 1 | deepseek | `A-META-COUNT-ITEMS` | `FLAG_INCONSISTENT` ✅ | `declared_count=0`, `items_len=1` | ¥0.016234 |
| 2 | xiaomi | `A-META-COUNT-ITEMS` | `FLAG_INCONSISTENT` ✅ | `declared_count=0`, `items_len=1` | ¥0.005847 |
| 3 | xiaomi | `A-PIT-VINTAGE-PASS` | `PASS` ✅ | 选中 `20200102T180000Z` / `value=10` | ¥0.0090242 |
| 4 | deepseek | `A-PIT-VINTAGE-PASS` | `PASS` ✅ | 同上，并显式 `NOT(...)` 排除未来 vintage | ¥0.01216112 |

**两个模型在本题集上都答对了。** 两个格式差异值得记录（均属冻结契约允许范围）：

- **xiaomi** 用 ` ```json ` 围栏包裹（契约明确允许「one optional json/untagged code fence」）
- **deepseek** 在 reason 中用 `fact={...}` 与 `NOT(fact={...})`，且未写 `source=` 子句
- **xiaomi** 在 reason 中用裸 `key="value"`，未用 `fact=` 语法

---

## 3. 第 5 次失败的准确性质

deepseek / `A-MULTIPLE-TESTING`：

```
http_status      : 200
transport_ok     : False
provider_failure : TRANSPORT_FAILED
provider_attempts: 1          ← 未重试
wall_ms          : 31726
input/output_tokens: None
raw_ref          : None       ← 原始响应未留存
cost_status      : UNKNOWN_USAGE
```

**代码路径已经查清**：冻结记录把该次归类为 `TRANSPORT_FAILED`，即 `reply.ok is False`。
在 `providers.py` 中，**HTTP 状态为 200 时唯一能令 `ok=False` 的路径是响应体未能解析**。
因此最可能的性质是：**服务端返回了一个无法解析为 JSON 的 200 响应体**
（例如空体、错误页或截断的流），耗时 31.7 秒后失败。

**根因状态：`UNKNOWN`。** 我无法进一步归因，因为：
**该次的原始响应字节未被捕获**（`raw_ref` 为 null）。这是本次执行的一个真实证据缺口。

**运行器的行为是正确的**：HTTP 200 未被当作生成成功；未知 usage 保留全额预留、
未记为 0 消耗、未重试、未提高额度、未替换模型，并停止了后续 7 次分发。

---

## 4. 评测器异常标记（必须处理）

冻结评测器自动给出：

```json
{
  "status": "EVALUATOR_ANOMALY_REVIEW_REQUIRED",
  "automatic_score_change": false,
  "reasons": [
    "ALL_TASKS_ZERO", "ALL_TASKS_ZERO:deepseek", "ALL_TASKS_ZERO:xiaomi",
    "ALL_MODELS_SAME_DIMENSION:...(6 项全部)",
    "VERDICT_EVIDENCE_SPLIT_GE_25_PERCENT"
  ]
}
```

**这正是任务书预警的情形，也正是我在本项目历史中反复强调的教训：
"全体 0 分"先怀疑测量工具，不要先归因于能力。**

### 4.1 计分向量显示了什么

| provider | completion | task_completion | provider_fail | **reason_contract_failures** | contract_fail |
|---|---|---|---|---|---|
| deepseek | 0.333 | 0.333 | 0.167 | **2** | 0.333 |
| xiaomi | 0.333 | 0.333 | 0.0 | **2** | 0.167 |

四个回答的 **verdict 全部正确**，但 `reason_contract_failures` 各为 **2**。
冻结的 `evidence_ok` 是 **evidence 与 reason 的合取**，因此 reason 语法不合规
即可把一次语义正确的回答压成 0 分。

### 4.2 强信号：疑似评分器问题

综合以下三点，**有充分理由怀疑这是判分而非能力问题**：

1. 两模型四个回答 **verdict 全对**，且关键事实值都正确；
2. 两个模型**各自**都被记了 2 次 reason 契约失败，但用的是**完全不同的**语法变体
   （deepseek 用 `fact={...}`，xiaomi 用裸 `k="v"`）—— 两种都很像"合理但未被冻结语法接受"；
3. 评测器**自己**就报了 `ALL_TASKS_ZERO` 与 `VERDICT_EVIDENCE_SPLIT_GE_25_PERCENT`。

**状态：`EVALUATOR_ANOMALY_REVIEW_REQUIRED`。**
按任务书规定，我**未修改评测器**、**未自动重跑 API**、**保留了原响应与原分数**。
是否构成"合法答案误判"需要人工/独立复核裁定，`confirmed_legal_answer_misjudgments: null`。

---

## 5. 未执行项（7 项）

```
xiaomi  / A-MULTIPLE-TESTING
xiaomi  / A-BACKTEST-NOT-RUN
deepseek/ A-BACKTEST-NOT-RUN
deepseek/ A-SUPPORT-THRESHOLD-PASS
xiaomi  / A-SUPPORT-THRESHOLD-PASS
xiaomi  / A-PROVIDER-TOKEN-LIMIT
deepseek/ A-PROVIDER-TOKEN-LIMIT
```

**未自动补做**（任务书禁止「补做一题」）。若需完成剩余 7 次，须**另行授权**，
并绑定新的 run 与当前 freeze/entry SHA。

---

## 6. 一个需要提请注意的仪表缺口

**该次失败的原始响应未留存**，因为冻结记录在 `reply.ok is False` 时把 `raw_ref` 置空
且未保留传输异常文本。后果：

- 无法判定该次是"服务端 200 + 不可解析体"还是别的传输异常；
- 根因只能停在 `UNKNOWN`。

**这不是判分问题，而是可观测性问题。** 修复方式（**需另行授权**，因为会改变 freeze/entry SHA）：

1. 在 `providers.py` 的失败分支保留 `transport_error` 文本与已读到的原始字节；
2. 在冻结记录中新增一个**只读的** `transport_error` 字段（不改任何评分逻辑、不改预算）。

我**未擅自实施**，因为本轮授权绑定的是确切的 freeze/entry SHA，改代码会使该授权失效。

---

## 7. 证据与可复核性

运行目录（**已 gitignore，未进入版本控制**）：

```
benchmark/capability_public/runs/compatibility_pilot/TRACK_A_V02_DSH_COMPATIBILITY_PILOT_001/
  prompts.json          冻结 system + 逐题 user（与 prompts.json 源逐字节相同）
  attempt_01..05.json   逐次记录（含 score 与 diagnostics）
  raw_01..04.json       4 次成功的原始 envelope（第 5 次无）
  result.json           完整结果、计分向量、异常审查、未执行清单
  trace.sqlite          append-only 轨迹，12 事件，哈希链 OK
```

**离线重放**（无凭据、无网络，会重算原分数并校验一致性）：

```powershell
$env:PYTHONPATH='src'
python -B -m quant_rsi.harness.compatibility_pilot_dsh `
  --replay benchmark/capability_public/runs/compatibility_pilot/TRACK_A_V02_DSH_COMPATIBILITY_PILOT_001
```

---

## 8. 边界声明

本结果**只**报告兼容性、完成率、契约/Provider 失败率与审计发现。

- **不得**据此生成单一总分、正式排名、显著性结论或稳定能力差异结论
- **不得**把四项 PASS verdict 当作策略资格（PASS 意为"所请求的受限动作有支持"，非策略合格）
- 六题含合同夹具与合成控制，**不是六个独立抽样的真实事件**
- 同作者真值/评分器不构成独立证据

保持：Track A = `PUBLIC/UNSEALED/PROVISIONAL`；D05 = `BLOCKED_ENVIRONMENT_CAPABILITY`；
D08 = `NOT_IMPLEMENTED/NOT_VERIFIED`；真实多轮 Agent / Judge 能力 = `UNVERIFIED`。
Stage C2 / D11 / D12 / D04B / Full Census 状态不变。
