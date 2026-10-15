# Workflow measurement v02.3 修复结果与Roadmap

日期2026-10-15。已完成用户授权的1—2项：独立测量修复、公开evidence字段合同澄清、已有响应离线复核。
MiMo/DeepSeek Provider诊断与真实重测继续暂缓；新增模型/API、Judge、数据API、工具或容器执行均为0，未读取凭据、未Git提交/推送。
一次任务只交付本报告，配套新源码、测试、公开合同及追加重评数据。未创建新真实执行授权或恢复旧批次。

## 独立修复版本

源码：src/quant_rsi/harness/workflow_measurement_v023.py。
测量版本workflow-measurement-v02.3；公开合同workflow-public-contract-v02.3。
旧workflow_transport_batch、workflow_http_comparison、原Evaluator、旧freeze及所有运行原始记录不改，故旧入口仍可呈现其历史失败。
新模块的CLI只有prepare/review，没有真实start或凭据入口；新model_request是可供后续冻结入口复用的修复接点，本轮不替换任何已授权真实入口。
直接复用原解析器、Provider归一化、确定性Oracle、TraceStore和SearchBudget，不建立新账本、评分体系或工具执行器。

1. 接受动作与被拒绝解析对象分离。code多字段、字段类型、大小及非法JSON按相同规则重新检查，拒绝后accepted action恒为None。原始响应留在原Trace；新失败收据将rejected_candidate单独记录，不把它冒充可执行动作。
2. 旧MiMo部分解析对象作为legacy证据解释，仅在重新解析的错误及对象与原收据一致、没有FINAL/容器执行且终止为INVALID_ACTION时接受其历史形态。不能只信任原error标签；伪造失败分类的反例被拒绝。
3. 预算判据通过ATTEMPT_STARTED.attempt_id→budget_root_run_id精确映射settlement。对Oracle建立只含本预算根结算的评分视图，原始事件和全批预算投影不变。C23的BREACH不再污染C2；同一根内真正的超限、UNKNOWN和停止约束仍保留。
4. 新公开FINAL.evidence明确为array、items=string、uniqueItems=true，增加仅示意格式的FINAL例子。数组元素仍须是实际可引用的OBS/INPUT，示例ID不授予权限。不改变真值、工具、必要观察、CP或评分事实谓词。

## 冻结与输入边界

freeze SHA：fc5480fceb510d2873fa9c35e4302a1ca3302476e641b017145d43694812e995。
entry SHA：98f16329dc03f07a9ea3d0684f0a800807688b45330660f05a0ef2d8982d9f75。
freeze绑定本模块、定向测试、两份来源freeze以及新action_contract/public_initial_messages，仅处理本轮变更与关键依赖。
新的公开消息只变更action_contract的版本、evidence类型及格式说明；system、题设、工具、limits、事实输出合同均保持原内容；四道CP公开消息完全相同。
该freeze是离线测量/公开合同版本，不是可启动新真实批次的执行授权。Provider额度、deadline及未知usage规则未被放宽。

## 已有三批记录离线复核

执行：PYTHONPATH=src，python -B -m quant_rsi.harness.workflow_measurement_v023 review --write。
结果保存于本目录REEVALUATION.json，逐条并列保留score_original、score_v023及独立expression_review；已写结果拒绝再次覆盖。
复核实际读取原SQLite只读连接及JSON，验证anchor/链/来源freeze、原请求和响应、原观察、预算结算、CP提交/公开输入哈希及隔离回执、原评分事件、逐题导出、批次计数与总账；未调用模型、工具或重执行提交代码。
旧逐题评分使用当时事件前缀可复现；新精确作用域评分在完整Trace上核验。不是截断原Trace来掩盖后续错误，也不把新复核成功冒充旧replay命令成功。

| 来源 | 已记录题数 | 新严格通过计数 | 独立表达诊断 | 修复后离线核验 |
|---|---:|---:|---:|---|
| Luna TRACK_A_CODEX_LUNA_32_V01_001 | 32 | 31 | 0 | VERIFIED |
| MiMo TRACK_A_HTTP_MIMO_MATCHED32_V01_001 | 21 | 19 | 0 | VERIFIED |
| DeepSeek TRACK_A_HTTP_DEEPSEEK_MATCHED32_V01_001 | 23 | 15 | 7 | VERIFIED |

新核验状态为OFFLINE_FIXED_MEASUREMENT_REVIEW_VERIFIED。严格计数不变：
- MiMo CP01多余action仍是格式失败；CP02超时及1次未知usage不改，不执行其代码、不退预留。
- DeepSeek C2预算合规，与原题完成时评分一致；CP04总输出超限继续失败，真实usage全部保留。
- DeepSeek七题引用字符串仍不符合严格数组parser，不能自动转成严格PASS。对明确分隔、无重复、全部对应真实允许ID的字符串，只在内存中进行有限解释性复核：七项事实及来源均正确，admitted_as_score=false。此规则不按模型身份选择，也不会生成/补充新证据。
- Luna RD02的final_test_count失败继续保留。AT03是执行层预期停止通过，没有模型故障后FINAL，不解释为模型自主停止能力。
- MiMo11题、DeepSeek9题未派发保持NOT_DISPATCHED；两家的AT03仍NOT_EXERCISED。不拼装成单批完整32题或正式排名。

## 工程验证

测试命令2次，未启动新的完整模拟题库批次：
- 首轮新增14项通过。
- 最终新增及相关解析/Provider/合同回归35 passed、9 deselected，exit0。排除全量旧模拟批次、会改写旧重评文件的测试及无关旧原生会话检查，没有重跑QV7或Stage C2。
- 反例覆盖错误JSON、重复键、非对象、code类型/大小、extra action、evidence字符串/重复元素/非字符串、伪造失败分类、C2/C23作用域、缺失reservation；真实旧响应验证跨题预算误罚消除、拒绝对象不执行、Provider失败不洗成研究结论。
- 三份真实批次共76条题目记录全部完成独立离线核验。新拒绝收据接点通过受控传输单元检查，无真实网络。
pytest退出后仍有环境既存pyreadline3析构句柄告警，不改变测试退出0；本轮不修改终端环境。

## Roadmap当前位置

原始目标是在冻结Task/Data/Env/Eval/Search预算下建立可信Research Agent评测台，测量研究过程与证据，而非寻找最高收益策略或凑出漂亮模型分数。

| 工作层 | 当前实际进展 | 未获得的资格 |
|---|---|---|
| 预算、Trace、确定性评分与重放 | 工程内核已建；本次修复真实失败揭示的重放/作用域缺陷 | 不代表没有未来缺陷或正式排名资格 |
| STATIC_DIAGNOSTIC | 24题公开基线及四模型真实作答/审计已有结果，实验条件限制保留 | 非隐藏集，不外推完整研究能力 |
| 补集题库 | 32题=20Workflow+4CP+8结构化；连同原24题共56题，另有WFA六场景，不能混为同一执行模式 | 不是所有模型均完整执行56题 |
| 真实多轮与代码能力 | MiMo完成WFA验证及补集部分；Luna完整32题；最新两家共同19Workflow已有证据，DeepSeek有3项CP执行通过 | MiMo/DeepSeek新32题覆盖未完整，重测暂缓 |
| Hybrid Evaluator | Rubric、JudgePacket、Validator和18条校准/6条挑战离线工程完成 | 真实Judge仍未校准；尚无过程质量的真实软评分验收 |
| D05 | Docker最小托管已于2026-10-10取得PASS_OFFLINE_ISOLATION_ENGINEERING，早期环境阻塞已经解除 | D05_FULL_SEALED_QUALIFIED=false；不扩称独立机构托管 |
| D08 | 尚未验收，作者/评审/结果独立性仍有缺口 | 换模型或新上下文不自动等于完整D08 |
| Track B | 原D11/D12/D04B、Stage C2及科学门禁保持原状态 | 未获得PIT、策略经济有效性、交易或sealed科学资格 |

当前处于“公开能力基线已能运行，正在验证测量可信度与研究过程质量”的阶段。
可以对第一阶段作有限结论：系统已观察到真实多轮工具使用和部分隔离代码能力；本轮模型差异混有合同/Provider条件，不支持正式排序。
MiMo/DeepSeek完整32题并不是下一阶段的必要门禁，暂缓重测无需让主线继续等待，也不将未完成改写为通过。

## 跳过重测后的建议顺序

下一项建议是**复用既有18条校准样本，准备并单独授权一次真实匿名Judge校准**，不是再扩题或反复同题横评。
理由：当前许多工具辅助事实题接近满分，确定性判据能检查真假、引用和权限，但尚未真实验证“工具路径是否合理、证据综合是否充分、结论是否适度”等软质量测量。
最低工作：沿用冻结Rubric/参考锚点/Validator，使用已经验证的受控模型传输，冻结一次18请求、零自动重试的评审预算和Prompt；匿名packet排除模型身份、私有收据及参考判分；严格保留原确定性结果。实评前核对人工可检查参考范围；输出结构合法不等于评分正确。
该18条校准材料来自已有受控轨迹，不是当前三个模型32题的新成绩，也不自动授予D08。
若随后评价当前真实补集轨迹，需要一个薄的来源适配：既有hybrid_judge.judge_packet只接受v01/v02轨迹，不能把新JSON/统一传输轨迹伪装为已支持来源；应接入本次已验证的来源核验和匿名引用，不重新建设Judge体系。

Judge校准之后，下一核心能力验证建议转为**一个小范围端到端研究任务**：冻结L0/L1数据与问题，让Agent提出可证伪计划、获取/处理证据、编写和执行分析、识别失败并形成结论。明确区分工具代算与模型代码实现。它测量长程研究整合，而不是继续增加近满分的短事实题。
该任务可用现有合成材料或另行授权的固定快照；不把L1宣称为PIT正确或可交易alpha，不自动启动Full Census、D11/D12/D04B、Hidden或策略搜索。
Judge不是所有端到端任务的硬前置：若软评分尚未可靠，可先保留确定性事实与过程证据、用人工复核软部分，不再因评审基础设施无限推迟研究任务。

本轮仅给出上述下一步建议，不自动启动真实Judge、数据获取、新研究任务或重测。推荐先将本次最小修订做一次本地Git提交，远程推送仍需明确授权。

## 本次待提交范围

- src/quant_rsi/harness/workflow_measurement_v023.py
- tests/test_workflow_measurement_v023.py
- benchmark/agent_workflow_v01/measurement_v023/（公开合同、消息、freeze、追加REEVALUATION及本报告）

建议提交信息：fix(workflow): version rejection replay and exact budget-root scoring。
既有其他未提交产物不混入本次范围。状态继续PUBLIC / UNSEALED / PROVISIONAL。
