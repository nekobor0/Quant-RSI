# Pilot 001 离线评分与失败留证复核

日期：2026-10-09。范围：已有 5 条记录、4 份原始 envelope、冻结公开合同及评分器。
本轮真实 API 调用 0 次、凭据读取 0 次；未补跑、未修改冻结材料或运行证据。
Track A = `PUBLIC / UNSEALED / PROVISIONAL`；D05、D08、Track B 状态不变。

## 结论

四份完整回答的 verdict 均正确，但不能认定四份回答均满足公开合同。
DeepSeek 两份 evidence 均符合冻结真值；其 reason 暴露了公开语法描述的占位符歧义。
MiMo 另有明确的来源结构与字符串精确匹配失败，不能全部归因于 reason 解析器。
`ALL_TASKS_ZERO` 是复核触发器，不是评分器错误的证明，更不代表模型能力为零。

已确认公开 reason 描述与实际解析行为之间存在说明缺口；尚未确认无歧义合法答案被误判。
原始分数及 `confirmed_legal_answer_misjudgments: null` 保持不变。
原状态继续为 `EVALUATOR_ANOMALY_REVIEW_REQUIRED`，需先处理公开合同歧义再讨论下一轮真实调用。

## 证据核验

运行目录：`benchmark/capability_public/runs/compatibility_pilot/TRACK_A_V02_DSH_COMPATIBILITY_PILOT_001/`。

- 5 条 attempt 与 result、Trace 中的记录逐项一致；原冻结 Evaluator 离线重评分 5/5 一致。
- 4 份 raw 的 SHA 与记录一致，原始 content 与 response_text 一致，通用敏感输出检查通过。
- 保存的 prompt 与原冻结 `pilot_v02/prompts.json` 完全一致。
- SQLite 用 `mode=ro` 打开；12 个事件的哈希链和 result 中的 anchor 一致。
  该核验不构成外部独立托管或 D08 验收。
- 原运行目录所有已有文件在复核前后 SHA 一致。
- 当前 freeze SHA：`4447f5a66773152316af9acb26f61e8110aa213854ce8c2568e31aed00a4d504`。
- 当前派生入口 SHA：`4decb95f916d76f98bdd88773f7c6c7d3f0128523be695bf3533606648eb2975`。
- 原入口、Provider、Evaluator 当前 SHA 均符合该 freeze 的绑定。

## 逐条裁定

| 序列 | 模型/任务 | verdict | evidence | reason 与裁定 |
|---|---|---|---|---|
| 1 | DeepSeek / META | 正确 | 完整且精确符合真值 | 四个 `fact={...}` 子句触发四次 `reason:UNSUPPORTED_CLAUSE`；公开占位符说明有歧义 |
| 2 | MiMo / META | 正确 | 关键事实正确，但 `source` 单数字段不允许，且缺少 `sources` 数组 | 原 reason 也是 `fact={...}`，并非摘要所称裸字段语法；同时存在来源结构失败和 reason 歧义 |
| 3 | MiMo / PIT | 正确 | `selected_value=10` 正确；时间写成 `2020-01-02T180000Z`，与要求精确保留的 `20200102T180000Z` 不同 | 裸 `selected_available_at=...; selected_value=10` 语法被接受；失败是时间字符串匹配及 reason 的同一字符串断言，并非该语法被禁止 |
| 4 | DeepSeek / PIT | 正确 | 完整且精确符合真值 | `fact={...}` 与 `NOT(fact={...})` 两个子句触发不支持；公开语法歧义同序列1 |
| 5 | DeepSeek / MULTIPLE-TESTING | 无完整答案 | 不可评价 | Provider 调用故障，不能当作研究结论错误；根因 UNKNOWN |

MiMo 的 JSON 围栏已被正常解析，不是本次失败原因。
`evidence_ok` 实际包含 reason 检查；`evidence_only_ok` 在序列1、4为 true，序列2、3为 false。
这里的 full_pass 失败不覆盖独立的 `verdict_ok=true`，不得把它概括成所有能力均为零。

## 公开 reason 合同的说明缺口与最小反例

模型实际收到的 `reason_role` 写的是：

```text
fact=<JSON value>, or NOT(fact=<JSON value>)
```

没有明确写出 `fact` 是需替换为 `facts` 中规范名称的占位符，也没有给出具体例子。
解析器却要求左侧名称属于 `contract['facts']`，故字面量 `fact` 不被接受；JSON 对象也不符合这些具体事实的类型。
两个模型均在 META 采用了字面量 `fact={...}`，支持这是跨模型合同理解问题。
不能要求被测模型通过读取评分器源码来补全未明确公开的语法。

以下为复核时在内存中构造的反例，**不是替换原回答或新版正式分数**。
保持 META 的正确 verdict/evidence 不变，仅修改 reason：

| reason | 冻结结果 |
|---|---|
| `fact={"declared_count":0}` | `reason:UNSUPPORTED_CLAUSE` |
| `declared_count=0` | full_pass |
| `data_count=0` | `reason:UNSUPPORTED_CLAUSE`；该别名虽允许用于 evidence，但解析器不接受它作为 reason 左侧 |
| `declared_count=1` | `reason:declared_count:CONTRADICTORY_ASSERTION` |
| `NOT(declared_count=1)` | full_pass |
| `NOT(declared_count=0)` | `reason:declared_count:CONTRADICTORY_ASSERTION` |

其余受控变体确认：

- 序列1、4只改为规范字段断言后 full_pass，原 evidence 无需修改。
- 序列2只改 reason 仍因 `source` 失败；另改为 `sources:[...]` 才 full_pass。
- 序列3换成允许的非事实解释仍因 evidence 时间字符串失败；只改 reason 时间也仍失败。
  reason 与 evidence 均恢复输入的原时间字符串后 full_pass。

共检查13个答案变体，未创建新 Evaluator、未放宽合同、未重跑模型。
若后续修订，只能采用新的公开合同/Prompt/Evaluator 版本；不能回写本轮冻结。
任何新版离线重评分均应保留旧分数、应用于两模型所有受影响的既有响应，不能把人工修写的变体当作真实回答。

## 第5次失败：更正已有报告的归因与留证机制

原记录为 `http_status=200`、`provider_failure=TRANSPORT_FAILED`、`raw_ref=null`。
“HTTP 200 时唯一可能是 JSON 解析失败”的说法不符合当前源码。
Provider 已收到 HTTP 状态后，读取响应体仍可能失败。

通过完全模拟的传输验证（网络连接被禁止，每例传输调用1次）：

| HTTP 200 的模拟响应 | 分类 | Pilot 捕获原始字节 |
|---|---|---|
| 完整读取 `not-json` | `PROVIDER_RESPONSE_INVALID` | 有 |
| 完整读取 `[]` | `PROVIDER_RESPONSE_INVALID` | 有 |
| 读取时抛 `IncompleteRead`，异常中含 partial bytes | `TRANSPORT_FAILED` | 无 |
| 读取时抛 `OSError` | `TRANSPORT_FAILED` | 无 |

运行器并不是因为 `reply.ok=False` 就清空 raw_ref：只要 `p.raw` 已捕获且通过安全检查，就会留存。
缺口位于完整 `response.read()` 返回之前：当前捕获层不保留异常中的部分字节，也不保存结构化异常元数据。
真实第5次与读取中断反例相容，但缺少异常及原始字节，不能确认实际异常类型、服务端问题或计费情况。
停止未知 usage、保留预留、不重试的行为与本次计划一致。

未来观测修复应在新版本中保存经过安全筛选的异常类型、阶段和可获得的部分响应。
不得直接把未经筛选的异常字符串、请求认证头或任意 HTTP 错误体写入日志。
本次未实施源码修复，不改变既有执行授权绑定。

## 统计与费用边界

- 计划：6项任务、6个来源集群、12次请求。
- 实际：5次请求涉及3个集群；4个完整回答覆盖2个任务/集群。
- 每模型取得2/6个完整任务回答；DeepSeek发出3次，MiMo发出2次。
- 完整回答合同失败：各模型2/2；不能从仅2题推断六维稳定差异或正式排名。
- 原始记录均写 `provider_attempts=1`，对应Trace只有5条尝试；不是服务端侧独立请求审计。

| 模型 | 已知 input | 已知 output（含reasoning） | 已知 reasoning | usage未知请求 |
|---|---:|---:|---:|---:|
| DeepSeek | 1603 | 3180 | 2957 | 1 |
| MiMo | 1508 | 1788 | 1554 | 0 |

Reasoning 是 output 的子集，不得再次相加计费。以上仅为已知usage合计，未知请求没有被计为0。
`¥0.04326632` 是四个完整响应的已知 usage 费用估计；第5次费用未知，整轮实际费用尚未核清。
累计保留的请求费用预留为 `¥1.30`（DeepSeek `¥0.90`、MiMo `¥0.40`），不是已结算费用。

## 后续边界

先解决公开 reason 语法说明缺口和失败可观测性，再决定是否开展新授权批次。
本轮不补做7项，不启动24题全量、真实Workflow或Judge。
已有源码仍通过 Python ChatProvider/urllib 出站；DSH 是控制器/启动环境，不据此宣称验证了 DSH Provider 传输。
普通离线工程修复可按 Engineering Budget 执行；新的真实API调用仍需重新冻结并取得明确批量授权。
