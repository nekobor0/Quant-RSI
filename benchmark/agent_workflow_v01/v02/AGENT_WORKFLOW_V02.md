# TRACK_A_AGENT_WORKFLOW_V0.2

状态：离线工程验收完成，PUBLIC / UNSEALED / PROVISIONAL。真实 Research Agent 能力 UNVERIFIED；D08 NOT_IMPLEMENTED；Track B、D11/D12/D04B 及 sealed 资格保持原状态。

## 相比 v0.1 的新增能力

新增 workflow_chat.py 的 ChatWorkflowAdapter：复用 ChatProvider/ProviderReply 原响应解析，采用独立公开 system prompt、原动作别名及参数合同，将已执行动作和真实 fixture 观察逐轮回填。传输仅接受 MockChatTransport，使用合成占位凭据，不读取环境密钥，也不存在网络回退。公开观察中的指令仍是数据。继承的 Run 注册版本字段保留 v01 legacy 标签；实际 Worker 请求明确标注 workflow-v02，结果保留 observed_model；未来真实入口必须冻结实际供应商模型版本。

新增 workflow_v02.py 只负责 Chat 执行与过程判分；SearchBudget、TraceStore、WorkerRequest、FixtureTools、PITView、动作解析、冻结真值比较与纯观察核验直接复用。v0.1 的所有 freeze、结果、trace、源码，以及 STATIC_DIAGNOSTIC 基线均未改动。v02/freeze.json 绑定原冻结哈希、新源码/测试及预算，system prompt 字节由源码绑定，公开动作合同从未修改的 v01 合同加公开 token 说明派生。

## 实際验证

最终运行 18 条：六个正确模拟 Chat、六个原错误结论策略的 Chat 格式对照、六个过程错误对照；原六个 v01 错误样本仍保留。合计 60 个 Chat 步骤、43 次实际离线工具调用。18/18 不调用模型、不重新执行工具的冻结回放一致。正确对照 6/6 完整 PASS；错误结论对照 6/6 不获完整 PASS。139 项必要定向测试通过，其中原 Workflow 与 B1/B2/Worker/PIT 回归 100 项。

受控反事实复用 WFA-02 的两个已冻结合法 fixture 版本；初始任务、公开合同和 prompt 哈希相同（efba31329fb81532fa5a71f928d56b241d3093bff7dfcb17df7123fcd200b2d2），第一步均 list_vintages。仅观察内容变化后，下一步 vintage_ids、随后读取的 vintage 和 FINAL 分别选择 v1 / 正确拒答。模拟传输逐轮从 HTTP messages 解码观察并计算动作，未使用预写响应序列或参考真值。它仍是已知测试策略，不证明真实模型具有动态研究能力。

## 六维过程区分

F/T/U/S/B/E 分别对应 FINAL_DECISION_CORRECT、TOOL_SELECTION_VALID、TOOL_RESULT_USED_CORRECTLY、STATE_TRANSITION_VALID、BUDGET_COMPLIANT、EVIDENCE_TRACE_COMPLETE；NA 表示没有可评最终结论。不产生单一总分。

| 对照 | F | T | U | S | B | E | 诊断 |
|---|---|---|---|---|---|---|---|
| illegal_tool | NA | 0 | NA | 0 | 1 | 1 | ILLEGAL_TOOL_OR_ARGUMENT |
| early_final | 1 | 1 | 0 | 0 | 1 | 1 | FINAL_WITHOUT_REQUIRED_OBSERVATIONS |
| wrong_reference | 1 | 1 | 0 | 0 | 1 | 0 | INVALID_OBSERVATION_REFERENCE |
| future_claim | 0 | 1 | 0 | 0 | 1 | 1 | WRONG_RESEARCH_CONCLUSION, FUTURE_OR_INELIGIBLE_VINTAGE_CLAIM |
| exhausted_trial | NA | 1 | NA | 0 | 0 | 1 | TOOL_EXECUTION_FAILED, BUDGET_VIOLATION_OR_UNRESOLVED_USAGE |
| tool_failure_claim | 1 | 0 | 0 | 0 | 1 | 1 | ILLEGAL_TOOL_OR_ARGUMENT, FINAL_WITHOUT_REQUIRED_OBSERVATIONS, TOOL_EXECUTION_FAILED, FINAL_AFTER_UNRESOLVED_TOOL_FAILURE |

正确工具链但错误最终事实保留 T/S/B/E 通过，F/U 失败；错误观察 ID 使 E/U/S 失败而 T/B 通过。合法额外读取及冗余调用不判成非法动作，分别追加 LEGAL_REJECTED_VINTAGE_AUDIT / REDUNDANT_LEGAL_TOOL_CALL 诊断。未来值由执行层 withheld，模型错误主张单独标注。完整 trace 的工程真实性与 FINAL 的证据引用完整性分开记录 trace_integrity。

## 资源与失败边界

每次请求先在同一 canonical root 预留 input 32768 / output 2048，单任务累计上限 input 262144 / output 16384；8 步、6 工具、0 自动重试，30s mock 客户端 timeout。输入采用序列化 UTF-8 字节数作为保守上界。output 含 reasoning，reasoning 字段另存，不重复加总；同时支持原生顶层和 details reasoning 字段。实际模拟 usage 合计 input 104385 / output 9600。这不是实际模型 token 消耗，真实 API 调用为 0。

缺失/非法 usage 结算为 UNKNOWN，保留全额预留并阻止派发；过量 usage 记 BREACH。失败或中断保留已有消耗、原响应引用和未核清预留。HTTP、业务、超时、空 content、截断、JSON、action、usage、工具故障和研究错误分别记录；HTTP 200 不等于成功。每轮 cost 带同一 budget_root_run_id，模拟费用 UNKNOWN/NOT_PRICED_SIMULATION，未声称实际免费或形成可用货币门禁。未来真实价格/币种/金额上限须重新冻结，当前入口拒绝真实传输。工具计数与科学 fixture trial 均由原账本负责；改名、参数或 prompt 中的指令不能重置预算。

## 产物和限制

最终数据：offline_run_verified/results.json、trace.json；本地 SQLite append-only。validation.json 记录测试、总量和必要哈希。一次 src 路径遗漏导致的五个收集错误已经修复；前序成功工程运行及对应执行 freeze 保留本地，未替换最终证据。

最终 freeze SHA：2382f56ab5009be5a74906cf0c11b548174ca08325fdcbcad5db933fbf590aea。入口：设置 PYTHONPATH=src 后运行 python -B -m quant_rsi.harness.workflow_v02 --output 新目录。replay(events, result, expected_anchor=Anchor(...)) 可核查保留的响应、观察、哈希、顺序、预算和评分。

当前未发现阻断本轮离线验收的关键缺陷。尚未验证供应商原生 reasoning 控制、真实 tokenizer/usage/cost、服务限流/延迟、并发或真实模型表达偏差。stdlib urlopen 适配为顺序作用域替换，非并发部署接口；本地 trace 不具外部 custody。真实 Pilot 最小条件是另行统一批量授权、必要密钥轮换确认、实际模型与原生参数、每步/累计 token 和货币硬上限、真实传输路径冻结及 0 重试。当前不申请/启动这些调用。

本任务完成后进入用户指定的第二项离线 Hybrid Evaluator 工程；不启动任何真实评测或其他科学阶段。
