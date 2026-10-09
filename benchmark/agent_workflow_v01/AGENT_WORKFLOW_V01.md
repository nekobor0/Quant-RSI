# Track A Agent Workflow v0.1

**PASS_OFFLINE_ENGINEERING；真实 Agent Workflow 能力仍 UNVERIFIED。** Track A 保持 **PUBLIC / UNSEALED / PROVISIONAL**。真实网络、模型 API、真实 Token、受限 Tushare 数据与实盘操作均为零；未执行旧 Pilot、24 题真实评测或原 24 题完整 mock 验收，未改变 Track B、D11/D12/D04B、Stage C2 或 sealed 状态。

此前六题 Pilot 按当前用户决定登记为 **PASS_OFFLINE_COMPATIBILITY_READINESS**，真实兼容性 **UNVERIFIED**、执行 **DEFERRED_BY_USER**。沿用既有准备结果，不追加 Pilot 准备或治理收口。

## 已完成的执行链

`WorkerRequest + 公开任务/动作合同 → Agent.step → TOOL_CALL / FINAL → 白名单与参数验证 → SearchBudget.reserve → 独立 FixtureTools.execute → 结构化观察与 settle → 下一轮上下文 → Workflow Evaluator`。

Agent 初始上下文只含任务摘要、工具与公开回答合同，没有 fixture 内容、真值或预写工具答案。观察和历史动作实际进入下一轮，输入哈希随上下文变化。执行层独占 fixture、预算与观察引用；工具结果中的文本没有权限、预算或判分权。禁止在 TOOL_CALL 中自报结果或执行成功；FINAL 必须引用真实支持结论的观察。公开别名、合法 JSON fence、有限数值表示与 nullable vintage 语义均有验证，不复用静态任务的 reason 语法。

统一上限：每场景 **8 个 Agent 步骤、6 次工具调用、自动重试 0**。Agent 步骤、工具调用及 WFA-03 合成 trial 均先 reserve 后 settle，跨轮累计到同一预算根。canonical `validation_queries` 计工具调用；`attempts` 包含三类预留，上限 16。正常工程调用 candidate_trials=0，WFA-03 的既有/新增合成 trial 使用原预算协议记数，不产生真实策略搜索或科学资格。

支持 COMPLETED、TOOL_ERROR、INVALID_ACTION、BUDGET_EXHAUSTED、MAX_STEPS_EXCEEDED、AGENT_FAILED。工具失败、未知引用或超限会停止；未结算 trial 不能 FINAL。模型改写 run_id/task_id 等参数无效，同一持久 trace 内同 fixture/脚本模型改名启动会拒绝新预算根。边界是可信监督进程，不宣称任意恶意 Python 代码的 OS 隔离、身份认证或跨任意新数据库的全局预算服务。资源片段有实际 wall/CPU 记录，既有 memory 字段不代表 OS 内存强制隔离。

## B1/B2 复用边界

| 既有能力 | 结论与实际使用 |
|---|---|
| WorkerRequest / 输入哈希 | **直接复用 schema**，每步绑定 context/fixture/case/policy 哈希、工具与主体；不冒称旧 invoke 已执行新动作 |
| TraceStore | **直接复用**原子 append-only、SQLite 禁改触发器、哈希链与 anchor 检查；不声称独立外部 custody/sealed |
| SearchBudget.reserve/settle | **直接复用**预算、失败、拒绝、已用 trial、root 和累计资源；没有第二套 search 计数器 |
| TaskContract / BenchmarkCondition / AgentBenchmarkRun / ExperimentSpec | **适配复用**固定人工场景到原账本合同；legacy CLOSED_DATA 字段仅为原内核结构兼容，公开能力结果独立标注 Track A，不改变 D03 或科学门禁 |
| DataSpec / SnapshotManifest / PITView | **适配复用**规范化人工 vintage 记录、可用时间、版本和生效过滤；内嵌 fixture 通过 canonical bytes resolver 作为 snapshot 的 `fixture.json`，没有真实市场 PIT 合格声明 |
| simulate | **无法直接复用这三个任务**：它是固定日线纸面执行器；本轮不伪装回测。synthetic trial 真正计算固定输入的常量信号和验证样本诊断 |
| B1/B2 FakeProvider / invoke / run_once | **无法直接执行新循环**：exact FakeProvider、固定字节和单次 synthetic-daily 限制保持不变；不等于已支持真实多轮模型 |
| B1 replay / code bundle | **原 replay 无法直接复用**：只重算日线操作；复用 dependency_lock 与 trace 核验，新 replay 仅检查冻结观察/动作/结论，不调用 Agent、不执行工具、不重新采样；没有全仓 code bundle 扫描 |
| B2 Evaluator / v0.2 Evaluator | **无法直接作为 Workflow 评分器**；仅复用严格确定性事实比较，新评分检查过程与证据。原静态 Evaluator/Oracle 未改 |
| ChatProvider / ProviderReply | **ProviderReply 直接复用**；`AgentStepProvider.step(WorkerRequest, context)` 给出未来适配面。现有 ChatProvider 的固定静态 SYSTEM_PROMPT 不适合动作合同，ChatWorkflowAdapter 在本轮明确禁用，不声称真实接通 |

新增源码仅四个模块：[执行入口](../../src/quant_rsi/harness/agent_workflow.py)、[工具层](../../src/quant_rsi/harness/workflow_tools.py)、[脚本策略与未来接口](../../src/quant_rsi/harness/workflow_agents.py)、[Workflow Evaluator](../../src/quant_rsi/harness/workflow_oracle.py)，以及对应测试与本目录工件。未修改 B1/B2 共享协议或历史 C2 源码。

## 冻结任务与实际结果

[cases.json](cases.json) 固定三个 Workflow、六个场景、手写参考事实、规范化数据与预算合同；[action_contract.json](action_contract.json) 公开动作/参数/别名/引用/拒答语义；[freeze.json](freeze.json) 绑定关键新增与复用源码、输入、测试、运行时与依赖。真值不由 Agent 动作或最终回答生成。Agent、真值和 Evaluator 同作者，**身份独立性不足，D08 未实现**。

| 场景 | 每个脚本的步骤 / 实际工具调用 | 正确行为 |
|---|---:|---|
| WFA-01 anomaly | 4 / 3 | count=0、items=3；一行可接受，两行分别因证券不符/非法价格拒绝；接受有效行并提示元数据异常 |
| WFA-01 normal | 4 / 3 | 两行有效且元数据一致；正常接受，不能普遍拒答 |
| WFA-02 available | 4 / 3 | v1 合法；v2 发布时间早于决策但 available_at 较晚，v3 后发布，v4 后生效，均不使用 |
| WFA-02 unavailable | 4 / 3 | 无可用版本，正确拒答；被拒版本的数据值不释放 |
| WFA-03 remaining | 5 / 4 | 既有 1/2 trial；预留并执行一个合成诊断，发现无效后结算失败，累计 2/2，停止并拒绝策略 |
| WFA-03 exhausted | 2 / 1 | 既有 2/2 trial；查询账本后直接停止，不执行新 trial |

六项评分向量在各场景内分别如下；**不加权、不产生单一总分**：

| 脚本 | FINAL_DECISION_CORRECT | TOOL_SELECTION_VALID | TOOL_RESULT_USED_CORRECTLY | STATE_TRANSITION_VALID | BUDGET_COMPLIANT | EVIDENCE_TRACE_COMPLETE |
|---|---|---|---|---|---|---|
| 正确脚本 A | true | true | true | true | true | true |
| 错误结论脚本 B | false | true | false | true | true | true |

A 的六个场景 Workflow PASS；B 虽正确执行相同工具链，六个错误结论都不能取得完整 PASS。这是已知脚本行为的工程对照，不是模型排名、区分度或科学能力结论；正确拒绝无效试验也不授予策略科学 PASS。

最终一次端到端批次共 **12 次执行、46 个 Agent 步骤、34 次真实离线工具调用、88 项 canonical 预留**，12 条轨迹回放一致。8 个 fixture candidate_variant 计数包含 6 个预先使用的合成 trial 和 2 个新增合成 trial；真实策略搜索为 0。执行片段合计 wall 1006ms / CPU 569ms，并非完整 CLI 墙钟或真实模型延迟。

必要测试 **100 passed**：41 项 Workflow 测试、59 项相关预算/Worker/PIT 接口回归。验证多轮依赖、白名单与非法参数、累计预算/拒绝、严格两步上限 guard、工程故障、未来信息拒绝、合法版本与拒答、伪造工具成功、别名/引用等价表达、未结算 trial、输入/预算/trace/最终结论变更以及无工具重新执行的 replay。保留 **15 条预期工程失败记录**：INVALID_ACTION 9、BUDGET_EXHAUSTED 2、AGENT_FAILED 2、TOOL_ERROR 1、MAX_STEPS_EXCEEDED 1。异常不登记为研究答案错误。

最终交付：[完整结果](offline_run_verified/results.json)、[append-only trace 导出](offline_run_verified/trace.json)、[工程失败记录](offline_run_verified/engineering_failures.json)、[验证摘要及工件哈希](validation.json)。原 SQLite trace 留在本地；失败记录保存测试时绑定和原分数。最后仅移除两处未使用导入，最终源绑定下再次通过全部端到端/replay 检查，没有改写旧轨迹。共使用 3/6 次 pytest、3/3 个工程离线批次；两个前序本地批次保留但不作为最终交付。**未发现阻断本轮离线验收的关键执行缺陷**。

最终 freeze SHA：`1e55e53b886dc4117e4232ca4379c48dd2b0ede6ecaafa7931f6cd496821c486`。回放校验动作/上下文哈希、实际工具结果、reserve/execute/settle 顺序、trial 状态、累计预算和原结论/分数；源绑定或输入变化会拒绝。当前源码不可直接重放旧版本的绑定，不会静默拿今天的源码重采样。整个过程没有 sealed、外部 custody 或独立作者保证。

## 入口与下一阶段最小工作

新执行目录必须不存在，已有 run 不重启：

```powershell
$env:PYTHONPATH='src'
python -B -m quant_rsi.harness.agent_workflow --output .pytest_tmp/new_workflow_batch
```

已冻结结果的回放接口为 `replay(events, result, expected_anchor=Anchor(...))`；输入可直接来自交付的 trace.json / results.json，既不需要凭据，也不调用任何工具或模型。

未来真实 ChatProvider 接入仅需：①取得新的真实批量授权与必要密钥轮换确认；②用公开动作 system prompt 与累计观察序列替换原静态 prompt，保留现有 HTTPS/ProviderReply 逻辑；③按供应商原生参数冻结每步和跨轮 token/费用预算并记录真实模型/usage/finish_reason；④以同一动作解析器、执行层和 Evaluator 验证多轮响应。当前只能证明这个接口及离线路径，真实适配器尚未接通，不能登记 REAL_AGENT_WORKFLOW_PASS。

本轮完成后停止；不启动真实模型、Compatibility Pilot、24 题全量、D05/Hidden、D11/D12/D04B、BASIC_03、Full Census、策略搜索或实盘。不追加治理收口。
