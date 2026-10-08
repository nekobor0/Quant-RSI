# Quant RSI HARNESS Target Architecture — DRAFT

依据：02 §4–9，03 H01–H15，04 phases。独立项目，不依赖其他项目；下列路径均为未来规划，不表示代码已存在。

## 最小结构与信任边界

```text
已冻结 Task + Env + Eval + Data/Cleaning/Split 引用
  → scheduler → reserve budget + append trial STARTED
  → Researcher → Implementer（仅 dev workspace）
  → candidate digest + public tests → independent Critic（独立上下文）
  → admission gate（版本/依赖/预算/critic）
  → sealed service（受信 evaluator；输入只能是固定候选产物）
  → append EvalResult + trial terminal event → dossier / versioned comparison
                                                → prospective shadow
```

主进程不能依靠 prompt 承诺实施权限隔离。worker 的 OS 身份、挂载、网络和工具 allowlist 只允许 development 输入；sealed 数据、标签、隐藏测试、签名密钥和 evaluator 写权限由独立服务持有。evaluator 维护者与当前 candidate 作者角色互斥。候选代码在无网络子沙箱执行，只取得按时点过滤的特征；不能通过日志、异常、返回值、路径探测或 metadata 读取标签。若部署环境做不到，G6=BLOCK，禁止宣称 sealed。

## 唯一对象归属

| 对象 | 规划 owner / 唯一写入者 | 边界 |
|---|---|---|
| TaskContract | contracts/task / freeze authority | 目标、horizon、基准、universe、execution timing、版本与预算；不复制数据 |
| Hypothesis / ConceptMapping | contracts/research / researcher preregistration | 一条可证伪主张；mechanism→observable→proxy→feature 引用 |
| ExperimentSpec | contracts/research / preregistration authority | 预注册研究方案；引用 Task/Data/成本/统计协议 |
| Evidence | contracts/research / evaluator evidence writer | 仅可追溯测量或证伪结果；叙述不能生成事实 |
| Candidate | contracts/research / implementer artifact writer | code/artifact digest + experiment ID；无自评晋升权限 |
| DataSpec / SnapshotManifest | contracts/data / data custodian | 数据语义、availability、清洗、版本、文件 hash；研究合同仅保存引用 |
| EnvSpec | contracts/env / environment maintainer | 状态可见性、动作、资源、执行规则；不嵌入 dataset 副本 |
| EvalSpec / EvalResult | contracts/eval / evaluator custodian | 冻结规则与独立裁决；research lifecycle 引用结果而不另设可写 verdict |
| ResearchTrace event | ledger / single writer service | 唯一 trial/family/attempt/usage/issue/decision 事实流；所有统计视图可重建 |
| RunManifest | contracts/run / scheduler | 绑定输入版本、模型、prompt、工具、code、依赖锁、seed、trace 范围 |
| WorkItem handoff | orchestrator / Astra | 复用 04 work_item_schema，加状态/产物 refs；不替代研究对象 |

新增的是上述对象的可执行绑定，不是新建一套与 Hypothesis/Evidence 等平行的名词。EventCard、完整组合引擎、live order 接口不进入首个 MVP；日频任务需要的制度事件作为 DataSpec/Env 的版本化输入。未来扩展 EventCard 前另做对象归属审查。

## 文件布局提案

`src/quant_rsi/contracts/` 保存唯一序列化合同；`ledger/` 保存不可变事实流和预算预留；`data/` 执行 PIT/cleaning；`env/` 执行仿真；`eval/` 执行确定性评估；`agents/` 为可替换模型适配器；`orchestration/` 管理状态机；`reporting/` 只生成派生视图；`shadow/` 处理未来 paper 观察。tests 按同名模块分区。

小规模 v0.1 使用单写入服务 + 原子落盘 + hash 链与受信外部锚点；reader 无写权限。无需先建设分布式平台。hash 链本身不能阻止有文件写权限的人重写整链：锚点/权限验证失败应阻断。崩溃后的 STARTED 必须补 ABORTED/UNKNOWN_TERMINATION，不能消失或退还已使用的搜索预算。

## 版本、重试、统计与晋升

冻结后只允许新 ID/新版本；历史对象不可覆盖。code_commit 未建立时只能做内容哈希绑定的工程开发，正式 benchmark 要求可重建 code tree 和依赖锁。数据/清洗/split/cost/task/env/eval/budget 变化必须新 condition，模型/prompt 是比较变量，均单独记录。新版本不能清空 parent family 的累计搜索记录，也不能让已暴露 holdout 重新变 sealed。

技术重试与科学变体分开命名但都入 trace、消耗 attempt/compute；参数、特征、prompt、人为干预引起的候选变化都消耗对应搜索维度。family_id 由服务分配，worker 不得自行分裂 family 以降低校正分母。跨模型比较的所有搜索合并纳入既定统计家族。

策略晋升与 Agent 能力记录分开：正确否决成本后无效/泄漏候选可获得研究行为分，但该策略不获得有效性标签。G0–G7 全部 PASS 才可进入策略表现比较；缺证据、未知值、审阅未决均不得默认为 PASS。shadow retirement 不重写旧 verdict，而追加降级决定。

## 落地顺序

先批准决策与合同 → append-only/预算 → 数据/Env → sealed boundary → 统计与 Eval → worker/critic/orchestration → 九类最低校准案例 → 同条件模型比较 → prospective shadow。完整依赖和白名单见 06_WORK_BREAKDOWN.md。首轮产物是 design drafts，未完成上述运行链路。
