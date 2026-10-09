# Track A 能力评测：首次真实双模型对比结果

运行：**`CAP-REAL-001`**（可复现）
日期：2026-10-08
标签：`PUBLIC` / `UNSEALED` / `PROVISIONAL`

> **边界声明（先读）：** n=7，且 D04B 统计协议未校准。以下只是**描述性比较**，
> **不是模型排名，不得外推**。本结果不证明 PIT 正确、不证明任何策略有效、
> 不构成正式 Benchmark 结论。详见文末"证据边界"。

---

## 1. 结果

| provider | model | full_pass | pass_rate | verdict_ok | evidence_ok |
|---|---|---|---|---|---|
| deepseek | `deepseek-v4-pro` | 4 / 7 | 0.5714 | 5 / 7 | 5 / 7 |
| xiaomi | `mimo-v2.6-pro` | 5 / 7 | 0.7143 | 6 / 7 | 5 / 7 |

**逐维度分数向量（D06：只出向量，无单一总分）：**

| 能力维度 | deepseek | xiaomi |
|---|---|---|
| evidence_discipline（证据纪律） | 0.3333 | **0.6667** |
| data_handling_correctness（数据处理正确性） | 0.5 | 0.5 |
| pit_and_methodology（PIT 与方法论） | 0.5 | 0.5 |
| research_logic（研究逻辑） | 0.6 | **0.8** |
| refusal_quality（正确否决质量） | 0.5 | 0.5 |
| reproducibility（执行效率与复现性） | 1.0 | 1.0 |

**逐任务结果：**

| 任务 | deepseek | xiaomi |
|---|---|---|
| `A-META-COUNT-ITEMS` | PASS | PASS |
| `A-EMPTY-VS-FAILURE` | WRONG_TERMINAL | EVIDENCE_INCOMPLETE |
| `A-PIT-BACKFILL-REFUSAL` | EVIDENCE_INCOMPLETE | EVIDENCE_INCOMPLETE |
| `A-PIT-ANNOUNCEMENT-VS-EFFECTIVE` | PASS | PASS |
| `A-DELIST-NOT-SUSPENSION` | WRONG_TERMINAL | WRONG_TERMINAL |
| `A-BUDGET-ESCAPE` | PASS | PASS |
| `A-INSUFFICIENT-SUPPORT` | PASS | PASS |

**失败类型分布：**

- deepseek：`{NONE: 4, WRONG_TERMINAL: 2, EVIDENCE_INCOMPLETE: 1}`
- xiaomi：`{NONE: 5, WRONG_TERMINAL: 1, EVIDENCE_INCOMPLETE: 1}`

## 2. 运行条件（两模型完全相同）

- 7 个任务、同一组 prompt（prompt 哈希固定并记入 trace）
- `temperature = 0`、`max_tokens = 24000`（截断时一次性升到 64000）
- 同一判分器、同一预算记账、同一 append-only trace
- 实际消耗：**14 次 API 调用**，无 retry、无 pagination、无 Critic
- `scientific_candidate_variants = 0` —— 能力评测在结构上不可能被误读为策略搜索

## 3. 观察（描述性，不作为结论）

1. **两个模型都具备基础能力**，7 个任务中 4–5 个完全通过，说明任务集没有过难或失效。
2. **两者弱项不同**：deepseek 在"正确否决/终态"上失分更多（2 次 `WRONG_TERMINAL`），
   xiaomi 在证据完整性上失分（1 次 `EVIDENCE_INCOMPLETE`）。
3. **`pit_and_methodology` 两者都是 0.5**，且 `A-PIT-BACKFILL-REFUSAL` 双双未通过 ——
   这是**最有信息量的负面信号**：当前快照不得回填历史 PIT 这一条，两个模型都表述不完整。
4. **`reproducibility` 两者都是 1.0**，但那是因为该维度只挂在 `A-BUDGET-ESCAPE` 上，
   而两模型都通过了它。**该维度目前区分度不足，需要更多任务支撑。**

## 4. 本结果暴露的判分器缺陷（已修复）

首次运行结果**全是 0 分**，看起来像"模型很差"，实际是**判分器错了**。
五个缺陷全部由"模型答对、判分器判错"的真实响应驱动修复：

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | 按精确 key 名匹配 evidence | 改为按**归一化取值**匹配，接受别名 |
| 2 | 答案契约隐藏，却按猜中 key 名打分 | 必须报告的事实在 prompt 中**公开声明** |
| 3 | `max_tokens=1500` 被 reasoning 吃光 → HTTP 200 + 空 content | 提到 24000，截断时升到 64000 |
| 4 | Markdown 围栏被判为格式错误 | 解析前剥离围栏 |
| 5 | 违禁值检查扫描全部 evidence | 只检查标识该主张的 key，并把 `reason` 纳入结论判定 |

**方法论教训：** 任何"全体 0 分"或"全体满分"的结果，先怀疑测量工具，再怀疑被测对象。

## 5. 证据边界

**本运行可以证明：**

- 在同一 harness、同一预算、同一判分规则下，两个真实模型完成了 7 个确定性任务
- 两模型在这些任务上的通过矩阵与失败类型分布
- 完整原始响应、prompt 哈希、release 哈希、逐次耗时与 token 计数已持久化

**本运行不能证明：**

- **不能**用于模型排名（n=7，D04B 未校准，无置信区间，无效力检验）
- **不能**证明任何模型的普遍能力（任务均取自本项目自身历史，且**已公开暴露**）
- **不能**作为 PIT 正确性、策略有效性或可交易 Alpha 的证据
- **不能**替代 sealed OOS 或正式 Benchmark
- 任务量不足以支撑统计推断，**只可用于调试评估流程与描述性比较**

**数据与工件：**

- 完整运行记录：`benchmark/capability_public/runs/CAP-REAL-001/`
  （`records.json` 逐次原始响应、`comparison_manifest.json`、`trace.sqlite` append-only 轨迹）
- 任务与夹具：`benchmark/capability_public/fixtures.json`、`tasks.yaml`
- 判分器：`src/quant_rsi/harness/capability_oracle.py`
- mock 离线基线：`benchmark/capability_public/TRACK_A_OFFLINE_VERIFICATION.md`

**状态未变：** Stage C2 = `BLOCKED_INCOMPLETE`；D11/D12/D04B = `NOT_READY`；
Full Census `query_ready=false` / `execution_authorized=false`。
本运行未推进任何数据取证，也未改动上述状态。
