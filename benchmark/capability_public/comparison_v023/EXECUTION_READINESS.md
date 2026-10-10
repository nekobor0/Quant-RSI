# 24题新合同与分段48次执行：准备收口

2026-10-10。**OFFLINE_PREPARED / REAL_EXECUTION_NOT_AUTHORIZED**。
本轮仅完成离线准备：真实模型、Judge、数据API调用0次，真实凭据读取0次。
仅访问提供方公开文档核对服务名、参数和人民币费率；未联网调用模型、账户或模型列表API。
Track A保持PUBLIC / UNSEALED / PROVISIONAL。没有另做六题Pilot。

这是同目录`TASK_INVENTORY_AND_READINESS.md`之后的执行准备更新；旧报告保留历史。
24题`contracts.json`、`prompts.json`及`prompt_freeze.json`原字节复用，旧六题Prompt字节不变。
原24题输入、ground_truth、Oracle及Evaluator 0.2.3-public-diagnostics均未修改。
不合并旧Pilot成绩，不把合同修订产生的得分变化当作能力提升。

## 固定范围与顺序

统一批次身份：`TRACK_A_V023_STATIC_24X2_001`。
仅STATIC_DIAGNOSTIC，24题×2模型×1次，共最多48次。不是四个独立Pilot，不根据模型历史成绩选题。
各维度内按原task_order顺序取第1/2/3/4题，各段六个主维度分别一题：

| 段 | 固定task_id（依次） | 请求数 | 来源集群数 |
|---|---|---:|---:|
| 1 | A-DELIST-NOT-SUSPENSION；A-META-COUNT-ITEMS；A-PIT-BACKFILL-REFUSAL；A-META-CONSISTENT；A-INSUFFICIENT-SUPPORT；A-BUDGET-ESCAPE | 12 | 5 |
| 2 | A-SOURCE-FABRICATION；A-EMPTY-VS-FAILURE；A-PIT-ANNOUNCEMENT-VS-EFFECTIVE；A-COST-LOSS；A-SUPPORT-THRESHOLD-PASS；A-PROVIDER-EMPTY | 12 | 5 |
| 3 | A-UNKNOWN-NOT-PASS；A-WRONG-SECURITY；A-PIT-VINTAGE-PASS；A-COST-PROFIT；A-SUSPENSION-CONFIRMED；A-PROVIDER-TOKEN-LIMIT | 12 | 5 |
| 4 | A-BACKTEST-NOT-RUN；A-WRONG-DATE；A-PIT-LATE-REVISION；A-MULTIPLE-TESTING；A-BUDGET-EXHAUSTED；A-PROVIDER-HTTP | 12 | 6 |

全批次10个来源集群，不能当成24个独立事件。四段尺寸12+12+12+12替代旧报告未冻结的12+18+18建议。
每段第1/3/5题先DeepSeek再MiMo，第2/4/6题反向；每个模型/题目组合最多一次。
顺序完整列入execution_freeze的segments.dispatch，不另用旧预选六题作为隐含首段。

## 冻结绑定

| 工件 | SHA-256 |
|---|---|
| 原24题Prompt freeze | `41a25576041842b2a32454b68c8cfbba4b2f2b561c3dd20d8dc4981b3b032923` |
| execution_freeze.json | `90426ee50fbe112c3afab985eccd56da95634f6e34eef3ec2bf1e4a7dc60feee` |
| segmented_comparison_023.py实际入口 | `511400c30f148b6b70f3988a453fc47437a7402be2764ea3525c3054e1047a8b` |

执行freeze绑定24题Prompt/合同、原评分依赖、两个Provider原生参数、新入口/测试、分段顺序和累计预算。
freeze不进行自哈希；授权申请绑定freeze和entry SHA。
`execution_authorization_request.json`仍为approved=false、prices_reconfirmed=false、valid_on=null。
旧密钥轮换确认按已有明确人类确认保留，不重新读取旧密钥，不做凭据探测。
当前用户授权是准备工作，不能据此填approved=true，也不能继承六题批次授权。

## 提供方与费用

请求模型：DeepSeek **deepseek-flash**，MiMo **mimo-v2.6-pro**；实际响应必须返回匹配model，否则停止。
DeepSeek官方当前将deepseek-flash映射至V4.1-Flash；服务别名不是不可变权重版本。
MiMo不可变权重版本仍UNKNOWN。文档核对不等于真实服务已探测。

端点沿用：`https://api.deepseek.com/v1/chat/completions`、`https://api.xiaomimimo.com/v1/chat/completions`。
两模型只收到冻结system/user两条消息；无另一模型答案、AGENTS.md、审计任务书、参考答案、工具或历史会话。

单次输入预留16384 tokens，生成额度24000 tokens（reasoning包含在生成额度内，不重复相加）。
DeepSeek：max_tokens=24000、thinking.enabled、reasoning_effort=high；temperature=0.0沿用但思考模式忽略。
MiMo：max_completion_tokens=24000、thinking.enabled；实际temperature=1.0、top_p=0.95。
同数字生成上限不代表相同推理投入，tokenizer和采样条件不等价；必须保留这些限制。

| 预算 | DeepSeek | MiMo | 全批次 |
|---|---:|---:|---:|
| 请求数上限 | 24 | 24 | 48 |
| 输入预留上限 | 393216 | 393216 | 786432 |
| 生成预留上限 | 576000 | 576000 | 1152000 |
| 单次费用预留CNY | 0.30 | 0.20 | — |
| 累计货币预留CNY | 7.20 | 4.80 | **12.00** |
| 峰时/全缓存未命中理论上界CNY | 5.394432 | 4.635648 | **10.030080** |

计算使用官方人民币每百万tokens费率：DeepSeek未命中输入2、输出8；MiMo未命中输入3、输出6。
单次上界分别0.224768、0.193152，向上预留0.30、0.20；不依赖缓存折扣或闲时折扣才能满足额度。
请求前必须预留，跨段按同一Trace中的PILOT_RESERVED累计；失败不退款，未知usage保留全额预留。
usage派生费用为估计，**不是已结算账单，也不是提供方账户级消费硬封顶**；同账户其他调用不在此账本内。

官方来源均于2026-10-10取得：

- [DeepSeek模型、人民币价格与闲时定义](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
- [DeepSeek思考模式参数](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)
- [MiMo境内按量价格](https://mimo.mi.com/docs/en-US/price/pay-as-you-go)
- [MiMo生成额度、usage及finish_reason](https://mimo.mi.com/docs/en-US/api/chat/openai-api)
- [MiMo思考模式采样参数](https://mimo.mi.com/docs/en-US/api/guidance/model-hyperparameters)

DeepSeek人民币工作日峰时为北京时间9—12、14—18，其余及周末为闲时。入口保留旧UTC保守闲时核验，
不请求节假日日历；每段必须有3600秒调度窗口加300秒socket timeout的闲时余量，窗口不足直接拒绝，不后台等待。
socket timeout=300秒不是严格生成墙钟终止保证；超时或测量超额停止后续分发。
每段调度最多3600秒，累计活跃调度预留窗口14400秒；段间暂停时间不增加调用、token或费用额度。

授权须填UTC valid_on，明确该日期官方费率仍不高于冻结峰时费率。每个请求前检查日期；跨日期未确认则停止。
正常段间暂停跨日期时，可由用户重新确认报价及授权日期，但只能延续同一根和剩余额度，不能重置已使用数。
价格已上涨则不得靠prices_reconfirmed=true继续，需新版本预算及另行明确授权。

## 执行、暂停与硬停止

新增专用入口只做跨段适配，直接复用冻结pilot的串行run、ChatProvider/urllib、失败留证及评分。
本静态入口沿用原PILOT_RESERVED/PILOT_ATTEMPT预算事件，在**同一个TraceStore**里原子校验跨段额度；
没有第二套数据库或科学搜索账本。Workflow的SearchBudget接口和所有科学门禁未改，candidate_trials=0。
若未来接入多轮Agent，应使用其已冻结SearchBudget路径，不能把这套静态调用统计当作实际研究预算能力验收。

实际输出根固定为`benchmark/capability_public/runs/segmented_v023/TRACK_A_V023_STATIC_24X2_001/`，已被Git忽略。
CLI不提供新run_id或任意输出根以绕过账本。root下只有一个trace.sqlite；各段保存自己的原始响应、记录、Prompt和结果收据。
summary.json是同一批次累计投影，可以更新；原回答、原评分和Trace事件不能覆盖。
重放重新计算投影与分数并核验原字节，不调用模型、工具或网络，使用只读SQLite连接。

每次命令只执行指定的一段，不自动启动下一段。只允许顺序1→2→3→4，重复、跳段、并发重复claim均拒绝。
正常完成为SEGMENT_PAUSED。全零/全满、格式失败率、verdict/evidence分裂等原冻结异常触发器出现时，
状态为ANOMALY_REVIEW_REQUIRED：先核查原响应、旧分数、真值及最小反例，不能凭分数放行。
用户明确记录复核结论后，允许同版本继续；确认阻断性测量错误则永久停止本批次，后续另版本离线重评已有响应。
复核声明只是人类提供的操作记录，不构成D08资格或密码学身份认证。

认证/429、身份不符或缺失、疑似凭据输出、未知或非法usage、token超限、预算/窗口超限、运行中断、
不完整执行收据或确认测量阻断均禁止后续分发。请求发送状态不确定仍占用预留，不可补做或重跑。
已有完整usage的空content/length输出归Provider失败；完整但答错的内容归研究错误。二者都保存原记录、禁止重试；
按继承规则，完整usage的普通回答失败可继续当前段，段末再进行异常审查。
HTTP 200不等于生成成功，失败原始字节及安全部分内容和结构化transport_error继续留存。

固定评分分母为每模型24题；报告已尝试、未尝试和实际来源覆盖，缺失usage/费用不冒充0。
无正式排名、显著性、单一加权总分或稳定能力差异结论；静态Provider诊断题也不是故障注入实验。

## 离线验收与失败记录

相关回归**108 passed**：新48次入口、全24题合同、原v0.2.3入口及TraceStore回归。
源码共享接口未改；不重跑Workflow、Hybrid、D05、CP、QV7、Stage C2或全仓测试。

验证包含完整四段模拟48次请求、两个模型/题目组合唯一、冻结消息逐字节一致、原生参数、无重试、
单根累计额度、第二段失败保留第一段预算、未知usage及中断留预留、原始失败留证、篡改拒绝、无执行重放、
分母24、异常暂停/继续/永久停止、运行跨日拒绝。全部模拟响应由测试fixture生成；不能当作真实模型成绩。

工程上限12次定向测试命令、8次完整模拟48次批次；实际测试命令3次、完整模拟批次3次，无科学搜索。
第一次62 passed/2 failed：导出Trace和attempt文件按解析JSON比较，追加空格未拒绝，被凭据访问断言抓住。
修复为规范原字节校验后107 passed；补充逐请求跨日门禁后最终108 passed。
初次开发freeze保留为`execution_freeze.preacceptance.json`，**不得授权它**；只有上表最终execution_freeze可授权。
`OFFLINE_VALIDATION.json`保留失败名称、修复说明及测试结果，不覆盖旧报告或模型分数。
pyreadline退出析构的Windows无效句柄警告仍存在，pytest exit 0；未改环境组件。

## 一次性授权草案

下面是供用户在报价确认后另行发送的草案，本轮未获此真实执行授权。所有四段共用一次48次范围授权；
段间仅更新日期确认或记录异常复核，不逐题审批。

```text
我批准从本人操作的普通非模型终端，分段执行TRACK_A_V023_STATIC_24X2_001。
仅绑定comparison_v023/execution_freeze.json：
90426ee50fbe112c3afab985eccd56da95634f6e34eef3ec2bf1e4a7dc60feee；
实际入口quant_rsi.harness.segmented_comparison_023：
511400c30f148b6b70f3988a453fc47437a7402be2764ea3525c3054e1047a8b。
固定24题、四段顺序按freeze；deepseek-flash与mimo-v2.6-pro各24次，总计最多48次，每组合一次。
输入每次16384、生成每次24000（含reasoning）；累计输入786432、生成1152000。
CNY费用预留上限12.00：DeepSeek7.20、MiMo4.80；timeout300秒，每段窗口3600秒，累计14400秒。
我确认旧密钥轮换/作废确认继续有效，并通过安全环境变量注入，不回显凭据。
我已核对[填写UTC日期YYYY-MM-DD]的官方费率不高于freeze中的峰时费率；valid_on填写该UTC日期。
批准paid_controller_calls=0、controller费用=0；不授权付费DSH控制器驱动，不由模型会话自动启动命令。
本条由我直接发送或转递后才可把本批次授权文件approved设为true，记录本消息来源并确认报价日期。
四段共用一个预算根，失败或未知usage不退款；禁止重试、提高额度、换模型、改名重置或自动启动下一段。
出现异常先离线审查；确认评分阻断、不可核查usage、留证缺口或运行中断即停止，不补做已尝试项。
不修改原评分器或任务，不启动新增32题、Workflow、Judge、Hidden、策略搜索或实盘；不自动Git推送。
```

入口本身没有付费控制器调用；launch_channel是用户启动前提声明，不能证明或硬限制外部DSH会话消费。
因此此草案要求本人普通终端启动，不把旧Pilot 002控制器违规通过重评分洗成合规执行。

## 命令与下一步

当前只能执行默认离线校验：

```powershell
Set-Location -LiteralPath 'D:\Claude_work_Territory\Quant-RSI'
$env:PYTHONPATH='src'
python -B -m quant_rsi.harness.segmented_comparison_023
```

真正获授权后，仅由用户在普通终端逐段执行，将N按顺序填1、2、3、4；命令不会自动执行下一段：

```powershell
python -B -m quant_rsi.harness.segmented_comparison_023 --segment N --authorization benchmark/capability_public/comparison_v023/execution_authorization_request.json
python -B -m quant_rsi.harness.segmented_comparison_023 --replay
```

如有测量异常，在已进行原始证据复核后，由用户记录continue或stop，而不是按成绩自动放行：

```powershell
python -B -m quant_rsi.harness.segmented_comparison_023 --review-segment N --decision continue --note '填写实际原响应及谓词复核结论，不填凭据' --authorization benchmark/capability_public/comparison_v023/execution_authorization_request.json
```

准备已完成，实际48次运行仍未开始。下一步仅为本地commit并另行统一真实执行授权；不再新增Pilot或题库工作。
D05最小托管工程已经PASS，但完整sealed资格未通过；D08仍NOT_IMPLEMENTED / NOT_VERIFIED，真实Agent/Judge仍UNVERIFIED。
本次24×2不加入新增28题、CP4题或多轮Workflow，它们属于不同执行模式，未来需要各自冻结与授权。
Track B、D11/D12/D04B及Stage C2不变。

本轮建议Git提交范围：`benchmark/capability_public/comparison_v023/`、
`src/quant_rsi/harness/public_contract_023.py`、`segmented_comparison_023.py`、
`tests/test_public_contract_023.py`、`test_segmented_comparison_023.py`。
建议信息：`feat(comparison): freeze 24-task contracts and cumulative four-segment execution`。
此前D05待提交文件和补集设计稿保留，不自动混入。本轮未commit、push或发布；完成准备后停止。
