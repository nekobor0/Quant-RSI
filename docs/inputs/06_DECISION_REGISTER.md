# Quant RSI HARNESS Decision Register — Seed

这些问题不阻塞 Astra 的仓库审计，但在对应 Phase 进入实现前必须显式决策并版本化。

| ID | Decision | v0.1 推荐默认值 | 何时必须冻结 |
|---|---|---|---|
| D01 | 首版市场范围 | 先以现有 A 股日频研究闭环为主；港股通/ETF 作为兼容扩展，不先扩大 Eval 面 | Phase 0 |
| D02 | Harness 主要评价对象 | Research Agent 为主；Execution Agent 单独赛道 | Phase 0 |
| D03 | 网络权限 | 设 closed-data benchmark + open-research 两种模式，不混分 | Phase 3 |
| D04 | Trial budget | 每类 Task 事前设预算；重试计入 trial ledger | Phase 4 |
| D05 | Hidden set | sealed + versioned；Agent 不可读取标签；更新即 version bump | Phase 4 |
| D06 | 单一总分 | v0.1 不设；使用 hard gates + score vector | Phase 4 |
| D07 | Worker 模型 | Astra 负责编排；GPT‑6 Sol / DeepSeek 作为可替换 worker | Phase 5 |
| D08 | Critic 独立性 | 优先 cross-model critic；至少与 implementer 分离上下文 | Phase 5 |
| D09 | Prospective shadow | 必须存在，但首版排行榜不要求立即积累足够长样本 | Phase 9 |
| D10 | Live order | v0.1 禁止真实自动下单，只做 research/paper/shadow | Phase 0 |

## 需要长期维护的版本键

```yaml
benchmark_run:
  task_version:
  env_version:
  data_snapshot_id:
  cleaning_spec_version:
  evaluator_version:
  cost_model_version:
  agent_model:
  agent_model_version:
  prompt_or_policy_hash:
  code_commit:
```

任何一个核心版本变化，都应视为新的 benchmark condition，不能把成绩与旧版本直接混排。
