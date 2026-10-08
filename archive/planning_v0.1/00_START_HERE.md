# Quant RSI HARNESS × GPT‑Astra Planning Bundle v0.1

本包把两类输入合并：

1. “量化交易综述撰写”阶段阅读的 30 篇论文；
2. 现有 Quant Research Harness / QuantTradingSystem 已沉淀的治理原则。

## 文件

- `01_LITERATURE_TO_HARNESS_TAKEAWAYS.md`  
  30 篇论文逐篇映射到 Harness 设计约束，并按主题分类；包含完整 `[P01]–[P30]` 来源索引。

- `02_ASTRA_MASTER_TASKBOOK.md`  
  可直接交给 GPT‑Astra/Codex 的主任务书。重点是 Roadmap、整体架构、Agent 分工、Eval、Env、任务拆分和 Definition of Done。

- `03_HARNESS_DESIGN_PRINCIPLES.yaml`  
  机器可读设计原则、hard gates、failure modes、source links。

- `04_ASTRA_EXECUTION_PLAN.yaml`  
  机器可读 Roadmap、交付物、角色合同、首轮输出。

- `05_SOURCE_INDEX.yaml`  
  30 篇论文标题、作者、年份、文件名和主题索引。

- `06_DECISION_REGISTER.md`  
  进入开发前后需要持续维护的开放决策与推荐默认值。

## 使用建议

把整个目录放进 Quant 项目的 docs/ 或 planning/ 目录，让 Astra 先读取全部文件和当前仓库，再执行 `02_ASTRA_MASTER_TASKBOOK.md` 的 Phase 0–1。

**不要直接让 Astra 从“写代码”开始。** 首先要求它输出 Current-State Audit、Gap Matrix 与 Target Architecture；这样可以防止重新造一套与现有 Harness 冲突的对象。

## 文献来源说明

来源键采用：

`[Pxx] 原论文名 — 原文件名`

本包没有把论文叙事直接当作项目 Evidence；文献用于形成设计 prior、failure-mode checklist 与方法学约束。实际工程状态仍应由 Astra 对当前仓库进行审计。
