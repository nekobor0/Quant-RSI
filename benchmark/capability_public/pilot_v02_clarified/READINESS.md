# 六题 Pilot：公开合同澄清与失败留证

日期：2026-10-09。状态：`OFFLINE_PREPARED_REAL_CALLS_NOT_AUTHORIZED`。
本轮真实模型 API 调用0次、真实凭据读取0次、远程Git推送0次。
Track A = `PUBLIC / UNSEALED / PROVISIONAL`；D05、D08、Track B及Stage C2不变。

## 改动与旧证据边界

公开合同版本：`PUBLIC_ANSWER_CONTRACT_V0.2.1_CLARIFIED`。
确定性Evaluator仍为冻结的 `0.2.0`，任务、输入、ground_truth与system prompt均未修改。

- reason明确要求 `<canonical_fact_name>=<declared-type JSON value>`：左侧必须是facts的规范名称。
  `fact`不是字面量字段，不能写 `fact={...}`；每个分号子句只断言一个事实。
- evidence可使用原公布别名，reason只接受规范名称；不再让模型猜测两者的适用范围。
- 加入不引用ground_truth的语法示例，明确示例值不是答案。
- 明确时间和其他字符串标识符原样保留，不改写分隔符或时区。
- 明确来源是 `sources` 数组，单数 `source` 不合法。

这是一项版本化Prompt说明修正，没有扩大冻结Evaluator的接受范围。
旧4份回答没有被转换为合格答案，旧评分和Pilot001原始证据保持不变。
旧批次的5条记录离线复核仍与原分数一致；本批次不能和旧Prompt版本混合统计。

新增 `compatibility_pilot_clarified.py` 是薄适配：复用旧Runner、费用/token预留、
TraceStore、ChatProvider与Evaluator，不新增预算、Trace或评分系统。
临时绑定通过context manager退出时恢复，不修改旧入口的文件字节或永久全局状态。

## 失败留证

- 保存结构化 `transport_error`：异常类型、阶段、可用/捕获字节数，
  `IncompleteRead`还保存可获得的partial bytes和剩余期望字节数。
- HTTP错误体与部分响应最多保留1 MiB；已完整读取的非敏感模型envelope仍原样保存。
- 识别请求分发、响应读取、上下文关闭及解析/验证阶段，
  不把 `HTTP 200 + TRANSPORT_FAILED` 自动归因为非法JSON。
- 不记录任意exception字符串或HTTP认证头；对两家已授权进程内密钥、常见凭据模式、
  Unicode转义及至少12字符的已知密钥前缀做保守筛查，安全拒收的字节不落盘。
- 失败体即使恰好构成合法JSON也不作为完整研究答案提交评分。
- 未知usage保留全部费用预留并停止后续分发；不能把已知费用小计当作整轮实际费用。
- 重放以SQLite只读方式核验原始/部分字节、attempt、Trace与原评分，不读取凭据、不重调工具或模型。

历史第5次请求的缺失字节无法补回，根因继续为UNKNOWN。
本次修复只改善新运行的可观测性，不声称已经修复未知的Provider根因。

## 离线验证

最终 **262 passed**，包括24项新增定向测试，以及原Pilot、派生Pilot、
STATIC_DIAGNOSTIC v0.2与B1/B2相关回归。没有运行全仓、Workflow/Hybrid或历史Stage C2套件。

```powershell
python -B -m pytest tests/test_compatibility_pilot_clarified.py tests/test_compatibility_pilot.py tests/test_compatibility_pilot_dsh.py tests/test_capability_v02.py tests/test_capability_comparison.py tests/ledger/test_store.py tests/ledger/test_budget.py tests/ledger/test_provenance.py -q -p no:cacheprovider
```

验证包括：两模型12个请求逐字使用新冻结消息、原生参数/零重试的旧路径回归、
一次完整模拟运行及只读重放、单次失败后停止、partial bytes、非法JSON、HTTP429、
关闭连接错误、凭据回显/转义/截断边界、未知费用不记为免费、授权/固定run_id/闲时门禁。
语法示例生成经ground_truth替换测试，证明不会从真值构造示例答案。
安全过滤扩展时曾出现3个离线测试失败，原因是包装器引用了错误self；已修复并完成上述最终回归。

CLI的 `--help` 与不带授权参数的默认离线检查均已实测通过。

## 新批次绑定与预算

这是**重新冻结的完整6×2新批次**，不是补做旧7项，也不是旧失败的自动重试。

| 项 | 冻结值 |
|---|---|
| run_id | `TRACK_A_V02_CLARIFIED_COMPATIBILITY_PILOT_002` |
| freeze SHA | `fb7eb0cbcdb0e4743c1894d0e964886c958a56772023dfb007fbd853c99f00e3` |
| 实际入口SHA | `9cf23246dd943eed2c3dc88efe2be39a0b6570975465e18874a43a0426b83f6f` |
| 模型 | `deepseek-flash`、`mimo-v2.6-pro` |
| 请求 | 最多12次，每模型6次，每(模型,任务)一次，无重试 |
| 单次输入/生成上限 | 16384 / 24000 tokens；生成含reasoning |
| 总输入/生成上限 | 196608 / 288000 tokens |
| socket timeout / 调度窗口 | 300秒 / 3600秒；socket超时不是严格生成墙钟期限 |
| 自动预留上限 | DeepSeek ¥1.80、MiMo ¥1.20；测量调用合计¥3.00 |
| 峰时全缓存未命中费用上界估计 | ¥2.507520；不是已结算费用 |

使用[DeepSeek官方人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)与
[MiMo官方境内实时API价格](https://mimo.mi.com/docs/en-US/price/pay-as-you-go)，2026-10-09核实。
预算用峰时上界；执行仍要求闲时覆盖调度窗口加socket超时余量。
代码按UTC工作日01:00–04:00、06:00–10:00排除高峰，保守地不利用中国节假日特例，
无需请求日历数据；窗外在读取凭据前拒绝，且不自动等待/重试。

执行通道真实名称是 **Python ChatProvider/urllib**。
DSH可以启动固定命令，但并未接入或验收DSH Provider adapter。
Python只自动核算测量请求，不能封顶外部DSH聊天控制器。
若控制器需要新增付费回合，拟议另设¥0.50硬上限，由DSH自身或服务端强制执行。
这不是Python已实现的预算；缺少该硬控制时，应改由非模型终端执行固定入口，不能假称费用已封顶。
此时¥3.00只表示测量预算，不包括DSH现有聊天费用；两类费用不得混记。

授权文件 `authorization_request.json` 当前 `approved=false`。
`keys_rotated=true`引用当前用户转递的Pilot001轮换确认，不表示本轮读取或验证了任何凭据。
用户将下列批次授权文本另行发送给执行者后，才能记录授权来源并更新批准状态。

## 可转递的新批次授权文本

```text
我批准执行 Quant-RSI 新公开合同兼容性批次。此次授权只针对下列冻结，不授权修改配置或扩大测试。

工作目录：D:\Claude_work_Territory\Quant-RSI
run_id：TRACK_A_V02_CLARIFIED_COMPATIBILITY_PILOT_002
freeze：benchmark/capability_public/pilot_v02_clarified/freeze.json
freeze SHA：fb7eb0cbcdb0e4743c1894d0e964886c958a56772023dfb007fbd853c99f00e3
入口：quant_rsi.harness.compatibility_pilot_clarified
入口 SHA：9cf23246dd943eed2c3dc88efe2be39a0b6570975465e18874a43a0426b83f6f
公开合同：PUBLIC_ANSWER_CONTRACT_V0.2.1_CLARIFIED
Evaluator：原冻结0.2.0，禁止修改。

模型：deepseek-flash、mimo-v2.6-pro，各6次。
固定任务顺序：
A-META-COUNT-ITEMS
A-PIT-VINTAGE-PASS
A-MULTIPLE-TESTING
A-BACKTEST-NOT-RUN
A-SUPPORT-THRESHOLD-PASS
A-PROVIDER-TOKEN-LIMIT

批准完整6×2新批次，最多12次，失败/发送状态不确定的请求同样消耗额度。
每对(模型,任务)最多一次；不补跑旧7项，不重试，不增加token，不换模型，不建立另一个run绕过预算。
每次输入16384、生成24000（含reasoning）；总输入196608、生成288000；timeout300秒、窗口3600秒。
测量调用人民币上限¥3.00：DeepSeek¥1.80、MiMo¥1.20，按冻结预留自动核算。

之前两个旧密钥已经轮换/作废的确认继续有效。只使用安全环境变量或既有受控注入机制；
不读取旧密钥、不回显凭据、不打印认证头或完整凭据文件。

先核验SHA。仅在冻结闲时门禁通过后执行；窗外报告等待用户再次触发，禁止自动调度或后台轮询。
不把DSH控制会话、AGENTS.md、示范答案或其他模型响应加入被测请求。
每次只发新prompts.json对应的system/user两条消息；无工具、无记忆、无跨题上下文。

DSH仅作为固定命令启动者，测量实际通过Python ChatProvider/urllib。
外部付费控制器若仍需新增回合，另批准最多¥0.50，必须由DSH或服务端硬封顶；不得凭提示词冒充费用控制。
无法落实时不启动付费控制循环，转由非模型终端执行同一固定入口；不安装插件或修改DSH配置。

本条由我直接发送/转递即为本批次明确授权。核验后只将新目录authorization_request.json的approved改为true，
记录本条授权来源；保留run_id、SHA、调用数与预算不变，不修改旧授权文件。

固定命令（PowerShell）：
Set-Location -LiteralPath 'D:\Claude_work_Territory\Quant-RSI'
$env:PYTHONPATH='src'
python -B -m quant_rsi.harness.compatibility_pilot_clarified --authorization benchmark/capability_public/pilot_v02_clarified/authorization_request.json --run-id TRACK_A_V02_CLARIFIED_COMPATIBILITY_PILOT_002

认证失败、429、模型身份异常、usage缺失/非法、凭据命中、token超限、超时或预算耗尽即停止剩余分发。
保留安全的原始/部分响应、结构化transport_error、usage、预留及Trace。HTTP200不能直接认定成功。
JSON/合同/研究答案错误保留原分数，不能在线修复或重跑。

结束后离线重放，回传完整结果目录给Codex/6.1 Sol审计。
分别报告已知usage费用小计、未核清请求和费用预留，不把小计称为整轮实际费用。
出现评分异常保留原输出和原分数，标记EVALUATOR_ANOMALY_REVIEW_REQUIRED；不混合新旧Prompt批次。
不生成正式排名、不推送Git、不启动24题全量、Workflow、Judge、Hidden、D11/D12/D04B或策略搜索。
保持PUBLIC / UNSEALED / PROVISIONAL。执行结束或停止后立即收口，不自动补做。
```
