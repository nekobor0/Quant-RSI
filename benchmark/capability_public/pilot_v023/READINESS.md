# 六题公开合同 v0.2.3：准备完成，真实执行未授权

日期：2026-10-10。Track A = PUBLIC / UNSEALED / PROVISIONAL。
本轮完成公开规则修订、统一离线重评、新 freeze/执行申请和必要测试。
真实模型 API 调用 0 次、真实凭据读取 0 次。仅核对公开价格文档；未提交或推送 Git。

## 公开合同与评分边界

`answer_policy.json` 是两模型共用的公开规则，不从 ground_truth 生成。Prompt 和新
system prompt 明确：PASS 表示证据支持所请求的限定判断，包括执行故障诊断；
诊断 PASS 不等于 Provider 成功、研究结论正确或策略资格。

- 公布的非事实解释句可以省略一个末尾句号，沿用冻结 0.2.2 的窄容忍。
- 公布失败分类及定义：TOKEN_BUDGET_EXHAUSTED、EMPTY_CONTENT、HTTP_ERROR、
  TRANSPORT_FAILED、BUSINESS_ERROR、PROVIDER_RESPONSE_INVALID。
- `finish_reason=length` 表示生成 token 额度耗尽，可能消耗在 reasoning 和可见输出；
  没有可见内容不能证明研究结论错误。
- 只在 A-PROVIDER-TOKEN-LIMIT 的 failure_class 字符串值上，接受精确值
  `TOKEN_BUDGET_EXHAUSTED`、`TOKEN_LIMIT`、`length`；evidence 与 reason/NOT 同样适用。
  不折叠大小写、不猜其他字符串、不改 verdict，不对其他任务或字段扩大接受范围。
- 这是根据公开响应进行的事后政策修订，两模型规则相同；新增通过不是模型能力提升，
  也不证明模型此前已经遵守旧合同。该诊断题的枚举命名负担被明确减小，不应与旧版本
  成绩混合统计或用于正式排名。

原24题的任务、public_input、ground_truth、原0.2.0 Oracle、0.2.2源码和旧freeze
全部保留未动。新增 evaluator_023.py 临时替换受限诊断值比较，其他硬判定委托原评分器。
入口只支持串行执行；临时模块绑定会恢复，不能与其他评分/模型线程并发运行。

## 已有响应的统一离线重评

`REEVAL_0_2_3.json` 并列保存三个版本评分及原始响应/Prompt/Trace引用和SHA绑定。
复用原Trace校验器、原分数比较和证据核验，没有覆盖任何原运行或旧重评。

| 批次 | 原0.2.0 | 0.2.2 | 新0.2.3 |
|---|---|---|---|
| Pilot 002，12项 | 6/12 | 9/12 | 10/12 |
| Pilot 001，5项含1次Provider故障 | 0/5 | 0/5 | 0/5 |

新增通过是 MiMo token-limit 的值别名得到同规则接受。DeepSeek 同题的 failure_class
也获接受，但 `INSUFFICIENT_EVIDENCE` 没有被自动改为 PASS，仍不满足新诊断终态规则。
另外一项不通过是 DeepSeek backtest 的额外 evidence 字段。两条 token-limit 历史回答
都保留 PUBLIC_CONTRACT_AMBIGUITY_REVIEW_REQUIRED，不把新合同追溯为旧模型已知指令。
Pilot 002 控制器预算违规继续存在，数据仅作工程证据，不能因为新重评分而变为合规执行。

核验前后44个相关历史证据/原评分输入/旧重评文件哈希一致。

## 离线工程验证

新测试26项，相关回归 **277 passed**。覆盖公开精确别名/否定、错误终态、其他事实、
大小写和格式反例、无ground_truth泄露的合同生成、授权前拒绝、12次模拟请求的冻结
消息/原生参数、Trace版本标记、模块恢复、无重试、失败留证、未知usage停止和只读回放。
首次测试有一项因把两厂商token参数统一假设为max_tokens而失败；已修正测试为各自
max_tokens/max_completion_tokens，运行实现及额度未改变。最终上述回归通过。
未重跑D05、Workflow、Hybrid、Stage C2、QV7或全仓测试。

```powershell
$env:PYTHONPATH='src'
python -B -m quant_rsi.harness.compatibility_pilot_023
python -B -m quant_rsi.harness.evaluator_023 --write
```

第一条默认只做离线检查；第二条只重评已保存的非敏感响应，不读凭据、不发请求。
已有重评文件若内容不一致则拒绝覆盖。

## 新批次冻结及预算

run_id：`TRACK_A_V023_PUBLIC_CONTRACT_COMPATIBILITY_PILOT_003`。
六题顺序保留为：A-META-COUNT-ITEMS、A-PIT-VINTAGE-PASS、A-MULTIPLE-TESTING、
A-BACKTEST-NOT-RUN、A-SUPPORT-THRESHOLD-PASS、A-PROVIDER-TOKEN-LIMIT。
两个模型：`deepseek-flash`（V4.1 Flash服务名）、`mimo-v2.6-pro`。
模型权重不可变版本尚未得到完整保证，仍检查响应模型身份。

| 绑定 | SHA-256 |
|---|---|
| freeze.json | `2baf9281c195383681232c723c9f86a34878c8882fa4968b1e55e4e8d265b2c2` |
| 实际入口 compatibility_pilot_023.py | `38025d530f6290e38733671b7511de3d7fc6da0ac926d36a71dde4249c2f9a44` |
| evaluator_023.py | `ee5c8b2bf6114f8b2020a0ca59bcf282c6c616ee7fd0d06196cc27636560c878` |
| answer_policy.json | `4a4aa518f415bfdcef4feb8787019305c21f1e2e7d84efd89887e05863fefd09` |
| REEVAL_0_2_3.json | `0effa4542560afe6c7ef9e8af622eb5e6479bbd1854ff2b70fe572ae536985d8` |

最多12次，每模型6次、每模型/任务一次，无自动重试、补跑、增额、替换或第三模型。
单次输入16384、生成24000 tokens（含reasoning），总输入196608、生成288000。
socket timeout 300秒，调度窗口3600秒；socket超时不是完整生成墙钟保证。
人民币测量上限¥3.00（DeepSeek¥1.80、MiMo¥1.20），逐次派发前预留，峰时全缓存未
命中上界估计¥2.507520。外部付费控制器批准调用数0，批准预算¥0.00。

报价核对来源：[DeepSeek官方人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
及[MiMo境内按量API价格](https://mimo.mi.com/docs/en-US/price/pay-as-you-go)，2026-10-10。
MiMo页面直接取得；DeepSeek直接获取超时，使用官方搜索索引结果（抓取标记约两周前）
核对，费率与旧freeze相同。若执行日期延后或报价更新，授权前重新核实预算基准；
不得假称已取得新的实时结算费率。实际账单和缓存条件仍UNKNOWN。

认证错误、429、身份缺失/不符、凭据命中、未知/非法usage、token超限、预算或窗口
耗尽均停止后续分发；失败/发送不确定请求也消耗次数。未知usage保留全额预留，
不视为0费用。语法/研究答案失败保存分数，不在运行中改评分器或重跑。
完整、安全的原始响应及安全部分字节、结构化transport_error沿用原留证逻辑。

实际调用仍是Python ChatProvider/urllib，没有DSH Provider插件。
用户必须从普通PowerShell/终端直接启动；入口不新增任何控制器模型调用。
`launch_channel`只是授权前提声明，Python无法识别启动命令的人/模型，也不能约束
一个已经存在的外部DSH付费会话。不得将该字段称为OS隔离或DSH控制器硬封顶。

## 统一执行申请（待用户另行授权）

`authorization_request.json`：approved=false，不能继承旧批次approved=true。
旧密钥轮换的人类确认沿用；本轮未读取或测试任何密钥。凭据若发生变化，真实执行前
需更新安全确认，仅通过安全环境变量/受控注入，不打印凭据文件或认证头。

以下是**待发送授权草案**，不是本轮已获得的真实API授权：

```text
我批准从非模型终端直接执行TRACK_A_V023_PUBLIC_CONTRACT_COMPATIBILITY_PILOT_003。
仅绑定pilot_v023/freeze.json，SHA为2baf9281c195383681232c723c9f86a34878c8882fa4968b1e55e4e8d265b2c2；
入口quant_rsi.harness.compatibility_pilot_023，SHA为38025d530f6290e38733671b7511de3d7fc6da0ac926d36a71dde4249c2f9a44。
Evaluator 0.2.3-public-diagnostics；公开合同PUBLIC_ANSWER_CONTRACT_V0.2.3。
固定六题和顺序按freeze，不扩大到24题。deepseek-flash和mimo-v2.6-pro各最多6次，总计12次。
测量费用CNY上限3.00：DeepSeek1.80、MiMo1.20；单次输入16384、生成24000，
总输入196608、生成288000；timeout300秒、窗口3600秒。失败和不确定请求同样计数。
不授权任何付费DSH控制器调用，不让模型会话启动这条命令。只由我在普通终端直接执行。
旧密钥轮换/作废确认继续有效；仅安全注入，不回显凭据。授权前核实报价仍符合预算。
禁止重试、提高额度、换模型、另建run绕过预算；停止条件全部按freeze。
本条由我直接发送/转递后才可记录授权来源并设置本批次approved=true，不能修改其他冻结字段。
完成后只做离线重放并交回Codex审计，不自动推送、扩大批次或启动后续阶段。
```

只有新的明确授权及安全注入完成后，才在用户终端运行：

```powershell
Set-Location -LiteralPath 'D:\Claude_work_Territory\Quant-RSI'
$env:PYTHONPATH='src'
python -B -m quant_rsi.harness.compatibility_pilot_023 --authorization benchmark/capability_public/pilot_v023/authorization_request.json --run-id TRACK_A_V023_PUBLIC_CONTRACT_COMPATIBILITY_PILOT_003
```

窗外拒绝时不后台等待、调度或重试。结束后可用同模块`--replay <结果目录>`离线核验。

## Roadmap与Git

当前位置仍是Track A真实静态兼容性测量修复：新合同、统一离线重评和独立批次freeze
已完成，下一步是用户commit后另行决定是否授权这次新合同验证。001/002不作废原数据，
也不因准备完成而自动获得合规Pilot资格。通过后才能另行授权24×2公开比较。
真实多轮Agent/Judge仍UNVERIFIED，各需独立预算与授权。

D05仍BLOCKED_ENVIRONMENT_CAPABILITY：此前Windows受限Worker三次未执行成功，
Docker Linux Engine当时不可用；本轮未重探环境，也未修改系统。D08仍未实现/验收：
独立上下文、身份、证据与结果的资格不能由两模型名称或目录分离代替。二者不阻塞
PUBLIC/UNSEALED/PROVISIONAL工程；它们继续阻塞独立/sealed资格声明。

当前分支codex/pilot-contract-clarification没有upstream。仅按本地缓存refs，相对
origin/main有15个本地提交，相对origin/codex/track-a-v02有13个；未fetch，因此不是
远端实时状态。建议现在commit本次版本化改动，留下可交接记录。远程同步是备份/协作
事项，不是本地SHA门禁的运行前提；可在需要远端备份时另行授权推送当前功能分支。
Git不代替被gitignore排除的原始响应/Trace备份，也不代替Custodian隔离。
本轮没有执行git add、commit、fetch或push。

建议用户检查后执行：

```powershell
git add -- benchmark/capability_public/pilot_v023 src/quant_rsi/harness/evaluator_023.py src/quant_rsi/harness/compatibility_pilot_023.py tests/test_pilot_023.py
git diff --cached --check
git commit -m "feat(pilot): freeze public diagnostic contract and terminal-only batch"
```

完成本轮准备后停止。D05、D08、Track B、D11/D12/D04B、Stage C2状态均不改变。
