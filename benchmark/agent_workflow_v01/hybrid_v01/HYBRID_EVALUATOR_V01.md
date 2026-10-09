# HYBRID_EVALUATOR_V0.1

状态：受约束 Judge 层的离线工程完成。PUBLIC / UNSEALED / PROVISIONAL；真实 Judge 未校准，真实 Research Agent UNVERIFIED，D08 NOT_IMPLEMENTED。D06 无单一总分、D11/D12/D04B、原 Workflow 和 STATIC_DIAGNOSTIC 冻结基线以及 Track B 门禁均保持不变。未调用 Luna 或任何真实被测模型，未请求外部数据、价格或文档。

## 程序与 Judge 的边界

确定性评分保留原版本与向量，Judge 只能追加逐维度 0—3 / INSUFFICIENT_EVIDENCE 的解释性评分。任何确定性 false 禁止正向 Judge 分，null 强制弃评。Judge 不签发 Workflow PASS，不授予科学资格，不解决独立性，也不形成模型总分或排名。

| 维度 | 程序独占 | Judge 可评价 |
|---|---|---|
| FINAL_DECISION_CORRECT | Frozen conclusion truth, aliases and contradictions; Judge cannot infer new facts. | Precision, calibrated refusal and whether the stated decision is justified by the cited process. |
| TOOL_SELECTION_VALID | Whitelist, parameter types, authentic observation/trial refs. | Relevance, economical ordering, reasonable alternative tools. |
| TOOL_RESULT_USED_CORRECTLY | Actual observation values and support for final facts. | Synthesis, interpretation and careful use of negative evidence. |
| STATE_TRANSITION_VALID | Actual reserve/execute/settle, prerequisites, unresolved tool failure and future-value withholding. | Adaptive next decisions and response to new observations or failures. |
| BUDGET_COMPLIANT | SearchBudget reservations, usage unknown/breach, tool/step/candidate limits; cost UNKNOWN blocks future real calls. | Frugality, stopping discipline and proportional evidence collection. |
| EVIDENCE_TRACE_COMPLETE | Anchored append-only integrity, actual references, required execution evidence. | Evidence organization, provenance clarity and auditability. |

完整逐维评分锚点在 rubric.json：0 为明确错误/违反硬条件或质量完全不支持，1 为局部/薄弱过程，2 为基本充分但有小缺口，3 为完整且适度的证据与过程；每个维度有具体锚点。合法但次优选择可以被 Judge 给较低质量分，而原合法性布尔分保持不变。猜中正确事实但没有工具证据可以保留程序事实 true、Judge 支持质量 0—1。弃评是未知，不等于零分或错误。

## Packet、引用和追加保存

hybrid_judge.py 的 judge_packet 先调用相应 v01/v02 冻结回放与 anchor 核验，再提取任务公开部分、动作、真实观察、FINAL、原六维评分/硬门禁及预算摘要。模型/provider/run 身份不进入 JudgePacket，观察和动作映射为 O/A/L/D 引用；原事件 ID/hash、来源版本和身份留在单独 private_receipts.json，不能随评审 prompt 发送。手工真值、参考评分范围和 source_profile 不发给 Judge。

Packet 内容哈希、公开 Rubric 和专用 system prompt 均冻结。JudgeResultValidator 校验精确结构、类型、六维覆盖、0—3 范围、实际引用、硬维度冲突、弃评理由和可程序核验的弃评事实。原始 Judge 回复及非法结果也通过原 TraceStore 追加保存，既不覆盖原轨迹，也不覆盖原评分；replay_judgment 重验保存输出、packet 绑定及原分数，不重新调用 Judge。Packet 工厂与本地 TraceStore 仍是可信执行层边界，不声称防御 OS 文件所有者或具外部 custody。

## 18 条校准样本与实际离线验证

样本是原 v01 正确/错误结论轨迹 12 条，加已完成 v02 的过程错误 6 条。calibration_reference.json 的参考范围及逐样本 references.json 的人工核对判据预先由工程作者手写；没有使用 Judge 输出作为真值，也尚未获得独立人工复核。原来源模型/真值/Evaluator 与本轮模拟 Judge 同作者，身份与结果独立性不足。

必要测试 40 项 Hybrid、联合相关回归 179 项通过；覆盖结构、证据编造、弃评、事实冲突、硬门禁冲突、无 FINAL、模型身份匿名化、保留原分数及 append-only/replay。

完整离线运行：18/18 模拟正确 Judge 回复被 Validator 接受且符合人工参考范围；另 6 条受控挑战保留原始输出、旧确定性向量和复核诊断。共 24 次 mock HTTP 调用，24/24 追加记录重放一致，真实调用 0。

| 模拟对照 | Validator 接受 | 参考范围符合 |
|---|---|---|
| wrong_score | True | False |
| fabricated | False | False |
| expression_bias | True | False |
| abstain | True | False |
| hard_conflict | False | False |
| paraphrase | True | True |

wrong_score / expression_bias 的全零软评分可结构合法，但参考范围分歧触发人工复核；Validator 不能程序证明软评分正确。fabricated / hard_conflict 直接拒绝。abstain 合法但与充分参考证据不一致，需要复核；paraphrase 改写理由不改变分数/合法性。这是测试机制的已知对照，不能声称真实 Luna 偏差已经消除。

## 必须人工复核与未校准偏差

真实 Judge 的理由是否与引用事实相符、允许工具中哪条路径更合理、拒答质量、复杂证据的完整解释，以及软评分参考范围分歧需要人工核对。存在真实引用并不保证理由没有编造；这种语义错误不能由当前 Validator 完全捕获。尚未校准位置/措辞/冗长度偏差、对模型风格的偏好、自我偏好、同作者泄漏、评分稳定性和观察中的提示注入对真实模型的影响。结构性匿名化不保证风格匿名化，更不等于 D08 验收。

## 未来 Luna 的最小路径与独立授权

最小调用设计在 future_execution.json。当前会话工具元数据列出 Codex 模型槽 gpt-6-luna；它不是已核实的公开 HTTP API model ID，服务端精确版本、HTTP 端点、价格和货币上限均 UNKNOWN。当前 JudgeAdapter 是 ChatProvider/ProviderReply 的受控模拟 seam，真实 transport 被代码拒绝。

未来可设计用户明确授权的新独立 Luna 评审任务，仅提供冻结 Packet/Rubric/Prompt，并把结构化输出导入 Validator。当前 Codex 任务工具没有暴露每次评审的原生 token/费用硬上限或完整 usage；不能直接把该任务路由当作已经完成资源可执行验收的 Provider。实际启用前需要核实具有可控上限和 usage 回执的调用桥接、精确模型版本及计费，重新冻结入口。没有验证这些条件前不能启动真实 Judge，也不为凑齐路径自行调用另一个模型。

完整 18 条最小校准需每条一次，共 18 次真实 Judge 调用，0 重试，不自动第二轮复评。候选技术上限：每次 input 32768 / output 2048（包含 reasoning），总 input 589824 / output 36864、timeout 300s。这里不精算实时费用；真实价格/金额上限待实际统一执行申请冻结。预算使用 canonical SearchBudget 的独立 review Engineering 根，派发前预留；unknown usage 保留预留并停止，不能续订被测 Agent 的科学搜索预算。未来授权需同时明确路径/任务创建权限、18 次批量调用、版本与 prompt freeze、可执行 token/货币上限和停止条件。

当前无阻断离线验收的关键缺陷。真实 Luna 路径与资源可观测性、费用门禁、真实模型评分偏差仍未验证，均保留为未来真实校准条件。

## 工件与停止

freeze SHA：2baedc09f54b3f380fb2d99db5ec4665e5524334a3a90ed772c729d6173046c9。入口：PYTHONPATH=src，python -B -m quant_rsi.harness.hybrid_judge --output 新目录。交付 offline_calibration/packets.json、private_receipts.json、references.json、results.json、trace.json；validation.json 记录必要验证及哈希。private_receipts 只含非敏感身份与事件映射，无密钥，但发送 Judge 时必须排除。

两项离线工程已依次完成并停止。未来真实 Judge 统一授权另行处理；不启动 DeepSeek/MiMo/Grok/Luna、旧 Compatibility Pilot、全量公开/真实多轮、Hidden/sealed、其他科学阶段或实盘。
