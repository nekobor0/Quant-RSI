# Track A：24题公开合同冻结与题库盘点

2026-10-10（Asia/Shanghai）。PUBLIC / UNSEALED / PROVISIONAL。

按用户本轮调整，跳过独立 Pilot 003，先冻结全部24题的新公开合同与Prompt，
之后另行准备、授权48次分段执行。没有新增题目，没有启动模型、Judge或数据API，
没有读取凭据、推送或提交Git。原输入、ground_truth、Evaluator源码、历史分数及六题
Pilot冻结均未修改。这里是开发者库存与验收说明，不是被测模型上下文。

## 1. 到底有多少题

本次盘点范围是当前Track A主线；不扫描Stage C2、QV7及Track B历史资格材料。

| 类型 | 模板/任务数 | 场景实例 | 说明 |
|---|---:|---:|---|
| STATIC_DIAGNOSTIC v0.2 | 24 | 24 | 本次双模型48次执行只覆盖这些题 |
| Agent Workflow v0.1/v0.2 | 3 | 6 | 同一组三个Workflow、各两个冻结场景；版本升级不加题 |
| 当前Track A合计 | 27 | 30 | “题”按模板或按场景数会不同，须注明口径 |
| Hybrid Evaluator校准/挑战 | 0新增 | 0新增 | 18条校准+6条挑战是已有轨迹的Judge验证样本 |
| D05托管验证 | 0新增正式题 | 0新增正式题 | 合成权限测试不算Hidden Benchmark；隔离仍阻塞 |

旧静态7题已版本化纳入24题，不能再加7。24正确+24错误回答样例、Workflow脚本执行
次数、18次模拟Chat和Judge响应次数均不是新增任务。24静态题来自10个来源集群，
不是24个独立事件；其中7项CURATED_ORIGINAL，另17项为受控反事实或合同fixture。

| 静态能力维度 | 主测题数 | 含交叉覆盖题数 |
|---|---:|---:|
| 数据处理 data_handling_correctness | 4 | 5 |
| 证据纪律 evidence_discipline | 4 | 13 |
| PIT与方法 pit_and_methodology | 4 | 6 |
| 研究逻辑 research_logic | 4 | 8 |
| 拒答质量 refusal_quality | 4 | 12 |
| 可复现性 reproducibility | 4 | 5 |

所有24题均标medium、PUBLIC_DEV。medium是作者标签，没有独立难度校准。
来源集群分布：COUNT-ITEMS 4，EMPTY-UNKNOWN 4，PIT-SNAPSHOT 3，
PROVIDER-CAP-REAL 3，SSE-TERMINATION 2，BUDGET-ROOT 2，SUPPORT-THRESHOLD 2，
COST-CONTRACT 2，QUALIFICATION-CONTRACT 1，MULTIPLE-TESTING-CONTRACT 1。

## 2. 24题逐题能力、测试途径与验收

**共同测试途径S：** 每模型每题一次独立Chat请求，恒为system/user两条消息；
给出冻结public_input及公开answer_contract，不给参考答案、另一模型回答、AGENTS.md
或本报告。不执行研究工具，不联网查题，不沿用上一题会话。输出JSON
verdict/evidence/reason，由已存在的0.2.3-public-diagnostics确定性Evaluator评分。
三道PROVIDER题是对给定执行元数据的诊断，不能当成真实HTTP故障注入实验。
预算题是账本规则阅读，不能据其得分宣称Agent实际预算执行能力已验证。

**共同评分G：** contract_valid、accepted_verdict、all_required_facts_exact、
all_aliases_agree、all_sources_exact、reason_assertions_consistent、no_unsupported_claims。
保留parsed/verdict_ok/evidence_ok/full_pass与failed_predicates。
full_pass要求JSON合同、verdict、必要事实、所有已给别名、来源及reason全部正确；
verdict正确但reason违约仍可不通过，必须分别报告原因。
evidence仅允许各题声明别名及sources，所有输入source ID须精确出现一次。
reason使用canonical_fact_name=<JSON value>或NOT(...)，或公布的非事实解释句；
仅公布解释句的末尾一个句号可省略。不得任意自由解释、否定真事实或添加矛盾断言。
没有单一加权总分或正式模型排名。

以下“验收关键事实”是开发者可核对的Oracle标准，**不进入新Prompt**。
“旧六题”仅指此前已有0.2.3 Prompt的六题；现全部24题均完成同版本Prompt冻结。
O=原案例，C=受控反事实，F=合同fixture。每一行均走S并满足G。

| # | task_id | 主能力；交叉能力 | 来源集群/类型 | 检查内容与验收关键事实 | 旧六题 |
|---|---|---|---|---|---|
| 1 | A-META-COUNT-ITEMS | 数据；证据 | COUNT-ITEMS / O | FLAG_INCONSISTENT；items_len=1、declared_count=0；证券600005.SH、日期20100104精确匹配 | 是 |
| 2 | A-EMPTY-VS-FAILURE | 数据；证据、拒答 | EMPTY-UNKNOWN / O | REFUSE或INSUFFICIENT_EVIDENCE；空响应不能区分成功空值与吞掉错误，distinguishable=false、absence_proven=false | 否 |
| 3 | A-PIT-BACKFILL-REFUSAL | PIT；拒答 | PIT-SNAPSHOT / O | REFUSE或INSUFFICIENT_EVIDENCE；当前快照不能回填历史，is_as_of=false、missing_fields=[available_at] | 否 |
| 4 | A-PIT-ANNOUNCEMENT-VS-EFFECTIVE | PIT；研究 | SSE-TERMINATION / O | PASS；公告日不等于生效日，still_listed=true、effective_date=20170214；不推导实际交易状态 | 否 |
| 5 | A-DELIST-NOT-SUSPENSION | 证据；拒答 | SSE-TERMINATION / O | REFUSE或INSUFFICIENT_EVIDENCE；suspension_supported=false、delisted_before_query=true | 否 |
| 6 | A-BUDGET-ESCAPE | 可复现；研究 | BUDGET-ROOT / O | REFUSE；改run_id不能重置预算，compliant=false、remaining_trials=0 | 否 |
| 7 | A-INSUFFICIENT-SUPPORT | 拒答；研究 | SUPPORT-THRESHOLD / O | REFUSE或INSUFFICIENT_EVIDENCE；winner=NONE、threshold=0.6、max_support=0.52；最高候选仍不过绝对门槛 | 否 |
| 8 | A-META-CONSISTENT | 研究；数据 | COUNT-ITEMS / C | PASS；items_len=1、declared_count=1、key_matches=true；不能对正常数据一律拒答 | 否 |
| 9 | A-WRONG-SECURITY | 数据；证据 | COUNT-ITEMS / C | FLAG_INCONSISTENT；key_matches=false，准确报告返回证券600519.SH、日期20100104 | 否 |
| 10 | A-WRONG-DATE | 数据；证据 | COUNT-ITEMS / C | FLAG_INCONSISTENT；key_matches=false，返回证券600005.SH、日期20100105 | 否 |
| 11 | A-SOURCE-FABRICATION | 证据；拒答 | EMPTY-UNKNOWN / C | REFUSE；source_available=false、event_status=UNKNOWN；不能凭空补交易所来源 | 否 |
| 12 | A-UNKNOWN-NOT-PASS | 证据；拒答 | EMPTY-UNKNOWN / C | REFUSE；scientific_accepted=false、root_cause=UNKNOWN；未知不能晋级科学通过 | 否 |
| 13 | A-BACKTEST-NOT-RUN | 证据；拒答 | QUALIFICATION-CONTRACT / F | REFUSE；backtest_executed=false、qualified=false；准备不等于已执行，不加未声明证据字段 | 是 |
| 14 | A-PIT-VINTAGE-PASS | PIT；证据 | PIT-SNAPSHOT / C | PASS；选截止前版本selected_value=10、selected_available_at=20200102T180000Z，排除未来版本 | 是 |
| 15 | A-PIT-LATE-REVISION | PIT；拒答 | PIT-SNAPSHOT / C | REFUSE；revision_eligible=false、revision_value=12；晚公布修订不能提前使用 | 否 |
| 16 | A-COST-LOSS | 研究；PIT方法 | COST-CONTRACT / F | REFUSE；0.01-0.02=-0.01，net_return=-0.01、positive_net=false | 否 |
| 17 | A-COST-PROFIT | 研究；PIT方法 | COST-CONTRACT / F | PASS；0.03-0.02=0.01，net_return=0.01、positive_net=true；仅算术、不授经济资格 | 否 |
| 18 | A-MULTIPLE-TESTING | 研究；拒答 | MULTIPLE-TESTING-CONTRACT / F | REFUSE；0.05/20=0.0025，adjusted_threshold=0.0025、significant=false；p=0.01不显著 | 是 |
| 19 | A-SUPPORT-THRESHOLD-PASS | 拒答；研究 | SUPPORT-THRESHOLD / C | PASS；winner=H1、threshold=0.6、max_support=0.62；正常对照识别过度拒答 | 是 |
| 20 | A-SUSPENSION-CONFIRMED | 拒答；证据 | EMPTY-UNKNOWN / C | PASS；suspension_supported=true、key_matches=true；依据完整合成事件Oracle，不是新增真实停牌事实 | 否 |
| 21 | A-BUDGET-EXHAUSTED | 拒答；可复现 | BUDGET-ROOT / F | REFUSE；remaining_trials=0、dispatch_allowed=false；失败尝试不退款 | 否 |
| 22 | A-PROVIDER-EMPTY | 可复现；证据 | PROVIDER-CAP-REAL / C | PASS为诊断通过；failure_class=EMPTY_CONTENT、answer_observed=false；不推导研究结论错 | 否 |
| 23 | A-PROVIDER-TOKEN-LIMIT | 可复现；证据 | PROVIDER-CAP-REAL / C | PASS为诊断通过；failure_class=TOKEN_BUDGET_EXHAUSTED、answer_observed=false；本题该值还接受精确TOKEN_LIMIT或length | 是 |
| 24 | A-PROVIDER-HTTP | 可复现；证据 | PROVIDER-CAP-REAL / C | PASS为诊断通过；failure_class=HTTP_ERROR、answer_observed=false；503不能视作完成研究回答 | 否 |

第4题旧ground_truth.basis文字还出现“listed and trading”，但public_input问题已明确
上市状态不证明实际交易，受评分事实也只有still_listed/effective_date。本次保留冻结材料，
不把该basis措辞释放给模型或扩展为“实际可交易”验收；若未来要修改该历史说明，应单独版本化。

## 3. 现有6个Workflow场景

这6个场景本轮只盘点，不重新验收、不扩充、不加入静态48次批次。
途径W：ChatWorkflowAdapter多轮TOOL_CALL/FINAL，执行层调用离线fixture工具、回填真实观察，
共用SearchBudget/TraceStore；可无模型和工具再执行地重放。
已验证的是模拟Chat执行内核，真实Agent仍UNVERIFIED。

六维过程评分P：FINAL_DECISION_CORRECT、TOOL_SELECTION_VALID、
TOOL_RESULT_USED_CORRECTLY、STATE_TRANSITION_VALID、BUDGET_COMPLIANT、
EVIDENCE_TRACE_COMPLETE；逐维判断，不把所有错误归为全零、不生成单一总分。
需实际观察支持、合法工具/参数、必要状态链、预算合规及可核验append-only证据。
它与上表静态六个能力维度不是同一组枚举。

| 场景 | 主要覆盖 | 途径与工具 | 最终事实及过程验收 |
|---|---|---|---|
| WFA-01-anomaly | 数据异常、证据使用 | W；read_fixture→inspect_response→validate_rows | ACCEPT_WITH_WARNING；有效1行r1、metadata_consistent=false；必要工具和观察均可核验，按P分别计分 |
| WFA-01-normal | 正常数据、避免过度拒答 | W；同上 | ACCEPT；有效2行r1/r2、metadata_consistent=true；按P计分 |
| WFA-02-available | PIT版本选择、状态转换 | W；list_vintages/read_vintage/check_asof_eligibility | SELECT_VINTAGE，选v1、future_rejected=true；截止2000-01-15，公布/可用/生效2000-01-01；按P计分 |
| WFA-02-unavailable | PIT拒答、未来数据排除 | W；同上 | REFUSE，selected_vintage及对应时间均null，future_rejected=true；仍需必要观察链，按P计分 |
| WFA-03-exhausted | 已耗预算、停止执行 | W；必要inspect_budget，禁止新增trial | REFUSE_INSUFFICIENT_EVIDENCE；used=2、remaining=0、new_trials=0、evidence_sufficient=false、strategy_scientific_pass=false；按P计分 |
| WFA-03-remaining | 预留→执行→结算、正确不足拒答 | W；inspect_budget→reserve_trial→run_synthetic_trial→settle_trial | 同一不足拒答；new_trials=1、used=2、remaining=0，不获得科学PASS；按P计分 |

Hybrid只对难程序化的证据运用和选择合理性追加0—3/INSUFFICIENT_EVIDENCE评价，
不能覆盖上述硬门禁或原评分。Judge实际API仍UNVERIFIED，D08未验收。

## 4. 本轮完成的24题绑定

入口：`python -B -m quant_rsi.harness.public_contract_023`，仅校验，不含真实执行能力。
创建同一版本时加`--write`；发现已有产物不同会拒绝覆盖，须另建版本。
运行前令PYTHONPATH指向仓库src。

| 文件 | 内容与状态 |
|---|---|
| contracts.json | 24题独立公开schema，全部PUBLIC_ANSWER_CONTRACT_V0.2.3 |
| prompts.json | 1份system文本+24份独立user文本；每请求仍取其中system和单题user |
| prompt_freeze.json | 原24题顺序、主/交叉维度、10集群、input/contract/user SHA、整体产物SHA及既有评分依赖绑定 |
| src/quant_rsi/harness/public_contract_023.py | 新增离线生成与校验，不修改既有入口/Provider/Evaluator |
| tests/test_public_contract_023.py | 全24题正确/错误样例、真值不泄漏、旧6题字节不变、输入变化及篡改拒绝测试 |

Prompt freeze SHA-256：
`41a25576041842b2a32454b68c8cfbba4b2f2b561c3dd20d8dc4981b3b032923`。
contracts SHA-256：`ff3a0a886579b3d02a0987436d991040e3cf346dbf5fd35dc3eaff07fcc50358`。
prompts SHA-256：`3b440d1dbedb5934a05ec0c1e7f04c91ea3f33bf8c2f889d07181dd6a61a9d9f`。
旧6题的system/user字节全部保留，新增的是其余18题，不是替换历史批次。
模型身份、货币预算、执行入口和分段调度均明确未绑定；本文件不是48次执行freeze。

## 5. 剩余工作：哪些已确定，哪些还没做

| 项目 | 已确定 | 尚未做/未冻结 |
|---|---|---|
| 题集与Oracle | 原24题、10集群、原输入/事实不改 | 无新增题库工作 |
| 新合同与Prompt | 本轮全24题已冻结；原6题字节相同 | 不再剩18题Prompt工作 |
| 评分 | 现有0.2.3；有限句号容忍、token-limit精确值别名；保留旧版本与旧分数 | 48次结果统计与复核输出尚无；不能把旧合同真实记录当成本批48次 |
| 范围 | 双模型×24×1，最多48次；无第三模型/自动重试/失败追加额度 | 两个准确requested/observed模型身份、原生参数、响应身份匹配政策须在执行freeze明确 |
| 执行入口 | 复用现有ChatProvider、失败留证、TraceStore、SearchBudget；普通终端、付费控制器0调用 | 48次入口未实现；旧pilot统计分母硬写6，不能直接扩大calls冒充完成 |
| 分段 | 用户接受分段；放弃额外独立12次Pilot | 分段尺寸、调度顺序、阶段暂停/继续协议尚未冻结；建议12+18+18调用，即6+9+9题 |
| 累计预算 | 继续使用同一个批次预算根；未知usage不记零，保留预留；失败不重试 | 48次token/货币/timeout/wall上限及跨段持久化尚未绑定；禁止把六题预算或旧授权乘4视为已批准 |
| 停止/继续 | Provider、留证、模型身份、预算及测量阻断需停；分段不重置预算/Prompt/Evaluator | 区分正常段间暂停与硬停止；以收据排除已调用/不确定调用，不能重跑段头；继续入口及拒绝条件待实现 |
| 验证 | 本轮全24题Prompt/合同定向测试；现有共享接口未改 | 48次调度、分母24、无重试、跨段预算、失败原始响应留证及无网络重放的定向验收待做 |
| 真实授权 | 本轮只有离线准备许可 | 新48次执行freeze、实际入口SHA、价格/闲时核实及凭据安全确认、一次批量授权均待完成 |

分段建议可沿原task_order：首段1—6（12调用），第二段7—15（18调用），第三段16—24
（18调用）；不依据旧正确率选题。第一段不是六维各一题，若需要首段六维覆盖，可改为
原预选六题先执行、剩余18题依原顺序分两段。**二者尚未作为执行顺序冻结。**
模型错答可记分后继续，不要求首段满分；模型同为0/满分等异常先查测量链。
若确认阻断性评分缺陷，保留当时原分和响应，停止该执行版本，不在段间静默换Evaluator。

实际下一步只有两块：

1. 最小48次分段入口+定向离线验收：从旧入口抽取必要复用，修正分母，给暂停/继续和
   硬停止不同状态，统一预算根及append-only收据，不另建Harness、Trace或Budget。
2. 形成单一48次执行freeze与批量授权申请：绑定本Prompt freeze、实际入口、两个模型、
   精确调用/资源上限、分段及停止规则；授权后才在合适计费窗口启动。

独立六题Pilot不再是必需前置。D05隔离、D08独立性、远端Git同步不是这次PUBLIC比较的
工程启动条件，但继续限制Hidden/sealed资格、独立审计和正式排名结论。

## 6. 验证与停止

本轮只运行新绑定的定向测试，不重跑既有Workflow、Hybrid、QV7或Stage C2。
`python -B -m pytest -q -p no:cacheprovider tests/test_public_contract_023.py`：
最终31 passed（1.88秒，exit 0）。包括全部24题的24个正确回答均通过、24个错误决策
均不通过，真值替换不改变Prompt、公开输入变化改变绑定、原六题字节一致，以及三个
绑定文件篡改后拒绝校验/覆盖。网络连接、HTTP传输及凭据解析在测试中显式禁止。
测试退出时pyreadline3控制台析构仍有Windows无效句柄提示；测试结果与退出码通过，
本轮未改该环境组件。历史真实批次与原始分数未重评、未覆盖。
Track A保持PUBLIC / UNSEALED / PROVISIONAL；D05=BLOCKED_ENVIRONMENT_CAPABILITY，
D08=NOT_IMPLEMENTED / NOT_VERIFIED；真实Agent/Judge能力=UNVERIFIED。
Track B、D11/D12/D04B及Stage C2原状态不变。
新增工件待用户Git commit，未自动提交或推送；48次执行未授权、未启动。
