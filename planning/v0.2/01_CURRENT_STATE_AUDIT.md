# Current-State Audit

当前状态：Stage A/A.1/B1 已通过各自限定验收；Stage B2 已通过限定 synthetic engineering 验收；正式研究 verdict 仍 BLOCKED。下方首轮文档审计和 Stage A 增补为历史基线，不能作为 B2 当前缺失能力列表。当前差距见 `01_GAP_MATRIX.yaml` 的 `stage_b2_update`，授权见 `../stage_b2_plan.yaml`。

范围：仅原始七份输入，独立新项目；审计结论不引用任何外部项目。机器可读索引见 planning_report.yaml，输入哈希与规划检查证据见 artifacts/planning/v0.2_validation.json。

## 文档基线 inventory

| 对象/能力 | 输入证据 | 已有内容 | 尚不能声称 |
|---|---|---|---|
| 定位与边界 | 00_START_HERE；02 §1–3 | 可信研究目标、先审计后实现 | 已有运行环境 |
| 研究对象 | 01 §4；02 §2、4 | Mechanism→Hypothesis→Observable/Proxy→Feature→Experiment→Evidence→Candidate 链条 | 已有可序列化 schema / truth store |
| 数据与 PIT | 02 §6；03 H01/H02/H06/H15 | as-of、幸存者、A 股语义、固定清洗要求 | 已有合格数据或 PIT 覆盖 |
| 回测、组合、执行 | 01 §1B；02 §6–9 | next executable bar、gross-to-net、容量、组合增量 | 已有 simulator 或真实成本参数 |
| Agent 接口 | 02 §4–5；04 roles | Researcher/Implementer/Critic/Evaluator 分权 | 已有 SDK、沙箱或模型接入 |
| Eval 与验收 | 03 hard_gates；02 §7、15 | G0–G7、score vector、E0–E9、DoD | 门禁已经执行或安全边界已证明 |
| trial/evidence | 03 H03/H04/H14；02 §4C–D | 失败保留、试验分母、append-only 要求 | 已有不可篡改存储/并发预算控制 |
| 产物与 provenance | 04 first_round_outputs；06 版本键 | 交付文件列表、model/prompt/code/data 版本 | 已有 artifact store、可重放 run |
| 文献索引 | 01；05 sources | 30 条 P01–P30 设计 prior | 原文已核验或论文结果已复现 |
| Roadmap | 04 P0–P9 | 阶段、角色、work item 必填字段 | P6–P9 已执行 |

## 冲突与缺口

1. 00/02 包含“现有体系/复用外部系统”前提；用户已明确改为独立新项目。保留输入原文，在本轮 scope override 显式消解；不能迁移其所谓现状。
2. DataSpec、Hypothesis、Evidence 等是概念名称，输入未给出完整执行 schema。先形成项目内唯一合同，再写代码，不引入同义模型。
3. D01/D02/D10 在 Phase 0 应冻结，输入仍是 seed defaults。本轮可以设计；实施前将 D01/D02 转为显式决定。D10 的禁止真实自动下单作为本轮约束执行。
4. G0–G7 只有名称，缺判定输入、失败语义、裁决权限和反例；草案补足这些内容。
5. 没有试验身份、family 继承、失败重试计数、预算并发扣减协议。仅记录 best run 无法满足 H03/H04。
6. “sealed + versioned”不等于存储隔离：必须处理进程、文件、工具、输出与日志泄漏，以及 repeated holdout 查询。
7. 成本、容量、统计阈值、真实 snapshot 和 shadow 时长未指定。全部作为待冻结协议值，不能补成虚构事实。

## 本轮验证边界

只运行规划验证器：七份输入哈希、来源 ID 完整性、九份输出存在性、YAML 可解析、H/G/E 覆盖、gap→work item 引用、DAG、文件白名单、每项输入/禁止输入/测试/验收/重试/预算、源文件未改变。验证器不会验证 PIT、OOS 隔离、统计正确性、回测或 worker 能力。

没有运行 Harness 测试、策略试验或市场数据测试；没有独立 critic 审核。本轮自检不是 independent evaluation。结论为“规划产物可审查”，不是“Harness 已完成”。


## Stage A 增补（Planning v0.2）

上文是首轮文档基线，归档快照见 archive/planning_v0.1。当前已实现 W01–W06 的五个 Python 模块、决策 registry 和对应测试；实际覆盖和剩余差距以本目录 01_GAP_MATRIX.yaml 及根目录 stage_a_acceptance.yaml 为准。最终联合测试 218 passed / 1 skipped；本机文件 symlink 创建权限受限，directory junction 反例通过。独立 runtime 审阅与最终产物 hash 以验收报告为准；不得从初始文档基线推断当前所有能力仍不存在，或从本地测试推断 sealed/empirical 已上线。
