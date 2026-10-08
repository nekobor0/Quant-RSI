# GPT‑Astra：Quant RSI HARNESS 架构与开发任务书

> 版本：v0.1  
> 角色：GPT‑Astra = Principal Research Architect / Orchestrator  
> 执行环境：Codex；可把明确、边界清晰的实现任务拆给 GPT‑6 Sol、DeepSeek 或其他 worker agent。  
> 目标：不是让 Astra 直接“挖出最好策略”，而是让 Astra **设计并推进一个能够可靠评价、约束和提升 Quant Research Agent 的 Harness**。

---

## 1. Mission

构建一个面向量化研究 Agent 的 Research Harness，使不同模型在**相同数据、相同信息集、相同交易语义、相同搜索预算和相同 Eval** 下完成量化研究任务，并能够区分：

1. 模型是否会提出可证伪、机制清晰的研究假设；
2. 是否能正确获取/处理 point-in-time 数据；
3. 是否能写出正确、可复算的研究代码；
4. 是否会发生未来信息、幸存者偏差、data snooping、p-hacking、benchmark gaming；
5. 是否能主动发现并证伪错误想法；
6. 是否能把统计预测转换成考虑成本、容量、风险后的 implementable edge；
7. 是否能在 sealed OOS 与 prospective shadow 中保持有效；
8. 不同基础模型/Agent 架构之间的真实能力差异。

**Harness 的北极星指标不是 max backtest Sharpe，而是 Reliable Research Output under Controlled Search。**

---

## 2. 当前工作与 Harness 的边界

本任务不是重写完整交易系统，也不是直接替代现有 Quant Research Harness。

Astra 首先应检查现有仓库，识别哪些能力已经存在，优先复用 canonical 对象与基础设施。已知现有体系已经强调：

- Hypothesis 单一可证伪；
- PIT / survivorship；
- Experiment → Evidence；
- structured falsification；
- promotion gate；
- trial / evidence governance；
- Agent / Quant / Human 边界；
- data source lineage；
- A 股现实执行语义；
- shadow / paper validation。

因此新 Quant RSI HARNESS 应优先定位为：

```text
Existing QuantTradingSystem / Research Harness
                  ↑
        executable research environment
                  ↑
        Quant RSI Agent Harness
        ├── Task / Scenario Generator
        ├── Agent Orchestration
        ├── Search Budget Controller
        ├── Eval & Hidden Tests
        ├── Research Trace / Trial Ledger
        └── Benchmark / Model Comparison
```

不要创建第二套彼此冲突的 Hypothesis、Evidence、EventCard、DataSpec truth store。

---

# 3. Astra 第一阶段必须先做的工作：Current-State Audit

在写新架构或代码前，Astra 必须扫描仓库并交付：

### 3.1 Inventory
- 当前研究对象/schema；
- 数据层与 PIT 能力；
- 回测/组合/执行模块；
- 当前 Agent 接口；
- 已有 test / acceptance gate；
- experiment / evidence / trial ledger；
- report / artifact 存储；
- 当前 model / prompt / tool invocation 记录能力。

### 3.2 Gap Matrix

对下列目标逐项输出：

```yaml
capability:
  current_state: PRESENT | PARTIAL | ABSENT | CONFLICT
  canonical_owner: ""
  evidence_paths: []
  gaps: []
  proposed_action: REUSE | EXTEND | ADAPTER | NEW
  priority: P0 | P1 | P2
```

### 3.3 禁止
- 不读现有代码就另起炉灶；
- 仅凭 README 宣称功能已经存在；
- 为了“架构优雅”复制 canonical 对象；
- 在 Audit 阶段大规模重构。

---

# 4. Target Architecture 初步设想

Astra 可以调整模块边界，但必须保留以下职责分离。

## 4.1 Control Plane

### A. Task Registry
定义每个 benchmark/research task：

```yaml
task_id:
research_type:
market:
universe:
asof_cutoff:
allowed_data:
target:
horizon:
benchmark:
execution_assumption:
search_budget:
compute_budget:
sealed_eval_id:
success_contract:
```

### B. Research Orchestrator
负责：
- 读取 Task；
- 分解阶段；
- 调度 worker；
- 管理 artifact dependency；
- 不直接改最终 Eval。

### C. Search Budget Controller
必须记录：
- hypotheses_seen；
- factor_variants；
- parameter_trials；
- model_trials；
- retries；
- prompt revisions；
- human interventions；
- wall-clock / token / compute usage。

没有这个分母，研究显著性不可解释。

### D. Trial / Research Trace Ledger
append-only，至少保存：

```text
task_id
run_id
agent/model/version
prompt hash
code commit
data snapshot
experiment spec
result
decision
failure
next action
```

---

## 4.2 Research Plane

推荐角色，而非强制绑定具体模型：

### Principal Investigator / Orchestrator — Astra
- 任务理解；
- 假设树；
- dependency graph；
- 分派任务；
- 合并证据；
- 最终 research dossier。

### Researcher
- 文献/机制；
- competing explanations；
- Hypothesis Card；
- falsification conditions。

### Data / Environment Agent
- DataSpec；
- PIT；
- data-quality checks；
- universe reconstruction；
- source lineage。

### Implementer
- feature / experiment / backtest 代码；
- unit tests；
- reproducible artifacts。

### Critic / Red Team
- leakage；
- look-ahead；
- survivorship；
- statistical errors；
- hidden assumptions；
- untradeable returns；
- alternative explanations。

### Deterministic Evaluator
**不应是普通生成 Agent。**
- 使用锁定的 eval code；
- 访问 sealed data；
- 执行 hard gates；
- 生成 machine-readable EvalResult。

Worker 可由 GPT‑6 Sol、DeepSeek 等承担，但**架构必须 model-agnostic**。

---

# 5. Agent Independence / Separation of Duties

以下约束建议设为 P0：

1. 生成 candidate 的 Agent 不得修改其 final evaluator。
2. Sealed OOS 标签/未来区间对研究 Agent 不可见。
3. Critic 至少在逻辑上与 Implementer 独立；优先 cross-model review。
4. Astra 可汇总 Critic 意见，但不得通过“重跑直到过关”绕过 search budget。
5. Eval 失败必须进入 ledger；不能删除失败 run。
6. 修改 Task/Eval contract 必须 version bump，且旧结果不得和新版本混排。

---

# 6. ENV：初步设计要求

Astra 需要在 Audit 后输出 `ENV_SPEC.yaml`。至少拆成三种环境：

## 6.1 Research / Development Env
Agent 可见：
- development data；
- validation data（使用次数受控）；
-文档与允许的数据源；
-代码执行环境。

Agent 不可见：
- sealed test；
- future shadow outcomes。

## 6.2 Sealed Eval Env
特点：
- data snapshot 固定；
- cleaning 固定；
- market calendar 固定；
- transaction-cost model 固定；
- deterministic seeds；
- evaluator read-only；
- candidate artifact input-only；
- 输出 EvalResult，不能由 Agent 改写。

## 6.3 Prospective Shadow Env
- 真实时间推进；
- 只有当时可得信息；
- 记录 signal timestamp → executable timestamp；
- paper execution；
- 用于最终验证衰减、滑点和操作可靠性。

## 6.4 A 股最低市场语义

除非任务明确是海外/跨资产 benchmark，A 股任务至少必须处理：

- T+1；
- 交易日历；
- 上市/退市；
- ST / 风险警示的 as-of 状态；
- 停复牌；
- 涨跌停与无法成交；
- 复权与 corporate action；
- 历史指数/行业成员有效区间；
- lot / volume unit；
- 手续费、税费、spread、slippage；
- 小盘/微盘可交易性；
- decision timestamp 与 first executable bar。

---

# 7. EVAL：核心设计

## 7.1 先 Hard Gates，后 Score Vector

不推荐一开始把全部能力压成单一总分。

### Hard Gates
建议：

```text
G0 Contract valid
G1 PIT / no future information
G2 Reproducible
G3 Search ledger complete
G4 Statistical protocol valid
G5 Execution assumptions valid
G6 Sealed OOS untouched
G7 Evidence lineage complete
```

任一关键 gate FAIL，研究结果不能进入“策略表现排行榜”。

### Score Vector
通过 Gates 后，再记录：

```yaml
research_quality:
  problem_definition:
  hypothesis_falsifiability:
  mechanism_quality:
  competing_explanations:
data_quality:
  pit_correctness:
  survivorship_control:
  lineage:
implementation:
  correctness:
  tests:
  reproducibility:
statistics:
  multiple_testing_control:
  robustness:
  calibration:
economic_validity:
  risk_adjustment:
  cost_adjustment:
  capacity:
  portfolio_increment:
generalization:
  temporal_oos:
  cross_sectional:
  cross_market:
research_behavior:
  negative_result_handling:
  self_correction:
  critic_response:
efficiency:
  trials:
  compute:
  tokens:
  wall_clock:
```

如果未来需要单一 leaderboard score，权重必须：
- 事前冻结；
- 版本化；
- 不因模型表现修改；
- 同时保留原始向量。

---

## 7.2 Eval Task Families

### E0 — Contract / Schema
测试 Agent 是否正确理解 task、冻结 target、horizon、benchmark。

### E1 — Data Integrity
人工埋入：
- future field；
- survivorship-only universe；
- 当前行业映射回填历史；
- ST 状态错误；
- corporate-action trap。

目标不是“跑出收益”，而是看 Agent 能否拒绝坏数据。

### E2 — Canonical Replication
要求复现经典结果/基线：
- momentum；
- value/quality；
- pairs；
- simple trend；
- canonical A-share factor baseline。

只有 replication 达标后才允许 innovation。

### E3 — Negative / Placebo Tasks
提供理论上不应有稳定 edge 的任务，检测 Agent 是否会“硬挖出 Alpha”。

### E4 — Multiple-Testing Stress
给大量无效特征 + 少量真实信号，观察：
- false discovery rate；
- trial ledger；
- DSR/PBO；
- 是否停止搜索。

### E5 — Implementation Realism
给一个 gross alpha 明显但成本/impact 后失效的任务，检查 Agent 是否主动否决。

### E6 — Model Selection
固定同一数据、清洗、split，比较线性、树、NN 等；禁止模型通过不同数据工程“作弊”。

### E7 — Regime / Nonstationarity
训练期有效、后期失效，观察是否识别 decay、是否自动降低信心。

### E8 — End-to-End Research
从模糊研究问题 → Hypothesis → Data → Code → Evidence → Candidate → OOS → Dossier。

### E9 — Prospective Shadow
真正不回看的未来运行。

---

# 8. Eval Metrics：不要只看最终收益

建议至少同时记录：

### Scientific Reliability
- false positive rate；
- false negative / missed obvious baseline；
- replication accuracy；
- evidence calibration；
- falsification compliance。

### Strategy Economics
- OOS net return；
- net Sharpe / Sortino；
- drawdown；
- turnover；
- capacity；
- correlation / marginal portfolio contribution。

### Research Efficiency
- valid evidence per 100 trials；
- accepted hypothesis per compute budget；
- redundant experiment ratio；
- time to falsify bad hypothesis。

### Governance Quality
- leakage incidents；
- fabricated facts；
- missing provenance；
- hidden test exposure；
- manual override count。

一个 Agent 如果能更快地**否决 20 个坏想法并保留 1 个可靠 edge**，可以优于一个产出 10 个高回测 Sharpe 但全部 OOS 失效的 Agent。

---

# 9. Statistical / Overfit Controls

Astra 的详细方案必须明确实现位置，而非只写原则：

1. trial family / family_id；
2. effective number of trials；
3. White Reality Check 或等价 family-level correction；
4. PSR / DSR；
5. PBO / CSCV（适用场景）；
6. time-series OOS；
7. sealed final test；
8. microcap / liquidity sensitivity；
9. parameter stability；
10. benchmark sensitivity；
11. negative control / placebo；
12. live/shadow degradation policy。

---

# 10. Road Map

## Phase 0 — Scope Lock
交付：
- `00_SCOPE_AND_NON_GOALS.md`
- current assumptions；
- default mandate；
- benchmark version policy。

## Phase 1 — Current-State Audit
交付：
- `01_CURRENT_STATE_AUDIT.md`
- `01_GAP_MATRIX.yaml`
- reusable canonical objects map。

## Phase 2 — Target Architecture
交付：
- `02_TARGET_ARCHITECTURE.md`
- module contracts；
- object ownership；
- trust boundaries；
- dependency graph。

## Phase 3 — Environment
交付：
- `03_ENV_SPEC.yaml`
- sealed-data boundary；
- resource sandbox；
- A-share semantics；
- data snapshot/version rules。

## Phase 4 — Eval System
交付：
- `04_EVAL_SPEC.yaml`
- task families；
- hard gates；
- score vectors；
- hidden tests；
- leaderboard/versioning policy。

## Phase 5 — Agent Orchestration
交付：
- `05_AGENT_ORCHESTRATION.yaml`
- Astra/worker/critic/evaluator role contracts；
- handoff schema；
- retry/search-budget policy。

## Phase 6 — MVP Implementation
优先实现最小闭环：

```text
Task
→ Astra plan
→ worker implementation
→ Critic
→ deterministic evaluator
→ EvalResult
→ ledger
```

不要一开始追求全品类策略。

## Phase 7 — Calibration with Canonical Tasks
至少做：
- 2 个正常可复现任务；
- 2 个无 Alpha / placebo；
- 2 个 leakage trap；
- 1 个成本后失效；
- 1 个 nonstationarity；
- 1 个 A 股本土制度陷阱。

## Phase 8 — Model Comparison
同一 Harness 下比较：
- Astra；
- GPT‑6 Sol；
- DeepSeek；
- 其他候选模型。

必须固定 Task version / Env version / Eval version。

## Phase 9 — Prospective Shadow
连续运行，形成真正未见未来样本。

---

# 11. Astra 如何拆任务给子代理

Astra 必须先生成 Work Breakdown Structure；每个子任务必须具备：

```yaml
work_item:
  id:
  owner_role:
  objective:
  inputs:
  forbidden_inputs:
  files_allowed_to_modify:
  deliverables:
  tests:
  acceptance_criteria:
  dependencies:
  max_retries:
  search_budget:
```

推荐原则：
- 小任务单一职责；
- 一个 worker 不跨多个 canonical owner 随意重构；
- code task 必须配测试；
- spec task 必须配 validator；
- Critic 的输出是 issues，不直接静默改代码；
- 修复必须留下 issue→patch→test 链路。

---

# 12. Astra 的第一轮输出要求

**第一轮不要直接大规模开发。**

先交付以下 8 个文件：

1. `00_SCOPE_AND_NON_GOALS.md`
2. `01_CURRENT_STATE_AUDIT.md`
3. `01_GAP_MATRIX.yaml`
4. `02_TARGET_ARCHITECTURE.md`
5. `03_ENV_SPEC_DRAFT.yaml`
6. `04_EVAL_SPEC_DRAFT.yaml`
7. `05_AGENT_ORCHESTRATION_DRAFT.yaml`
8. `06_WORK_BREAKDOWN.md`

并额外生成：

```yaml
planning_report:
  inspected_paths: []
  reused_canonical_objects: []
  proposed_new_objects: []
  conflicts_found: []
  p0_blockers: []
  assumptions_needing_human_decision: []
  implementation_order: []
```

任何“已完成架构”声明必须由具体文件与测试支持。

---

# 13. 必须避免的失败模式

1. **Leaderboard overfitting**：反复针对公开 Eval 调 prompt。
2. **Same-agent self-grading**：生成者自己选择最好 run 并判定通过。
3. **Search-budget blindness**：只看最佳结果，不记录尝试次数。
4. **Data-cleaning confound**：不同模型拿不同清洗数据比较。
5. **Future leakage**：当前成分、行业、ST 状态回填历史。
6. **Microcap illusion**：收益主要来自不可交易小票却不披露。
7. **Gross-alpha illusion**：不考虑成交、冲击和税费。
8. **Metric monoculture**：只优化 Sharpe。
9. **Regime rescue**：策略失败后不断切状态直到重新显著。
10. **Narrative→Evidence**：LLM 总结未经原始数据验证直接进入 Evidence。
11. **Object duplication**：重新造一套与现有 Harness 冲突的 schema。
12. **Positive-result bias**：只保存成功实验。
13. **Unbounded autonomy**：Agent 无限搜索直到“找到 Alpha”。
14. **Benchmark drift**：不同版本结果混在同一排行榜。
15. **Premature complexity**：在 baseline、PIT、Eval 都没稳固前上复杂 multi-agent/RL。

---

# 14. 关键开放问题（不阻塞 Audit）

Astra 在 Phase 1 后应把这些问题转成 decision register，而不是自行默默假设：

- Quant RSI Harness 的首版 benchmark 是否只覆盖 A 股日频，还是从 Day 1 包含港股通/ETF？
- 最终 benchmark 是主要评价“研究 Agent”，还是也评价“策略执行 Agent”？建议首版以前者为主。
- 是否设置 closed-book 与 open-web 两套赛道？
- 每个任务的最大 trial / token / compute budget 如何统一？
- hidden final set 的更新频率和防污染机制如何设计？
- leaderboard 是否需要单一总分？建议 v0.1 先只用 hard gates + score vector。
- prospective shadow 至少运行多长周期才允许成为核心排名依据？
- 模型版本更新后，旧结果是否保留为 immutable historical run？

在这些问题被明确前，Astra 可以继续完成不依赖答案的基础设施设计。

---

# 15. Definition of Done

Quant RSI HARNESS v0.1 不是“代码能跑”就完成，而是至少满足：

```text
[ ] fixed Task contract
[ ] versioned Env
[ ] fixed-data / fixed-cleaning Eval
[ ] sealed OOS boundary
[ ] trial/search ledger
[ ] hard gates
[ ] score vector
[ ] PIT/survivorship traps
[ ] multiple-testing controls
[ ] replication tasks
[ ] negative-control tasks
[ ] implementation-realism tasks
[ ] independent critic/evaluator
[ ] model/version provenance
[ ] reproducible artifacts
[ ] prospective shadow path
```

最终目标：

> **让模型无法通过“搜索更多、挑最好、换口径、看未来、忽略成本”来伪造能力；让真正更好的 Quant Research Agent 在可复算、可证伪、可泛化的研究过程中胜出。**
