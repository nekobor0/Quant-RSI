# Track A v0.2 Compatibility Pilot readiness

**准备完成，真实调用未执行（0 次）。** Track A 保持 PUBLIC / UNSEALED / PROVISIONAL。本轮没有扩题、修改原任务/真值/Evaluator/freeze_v02，或改变 D11/D12/D04B、Stage C2、Track B；未读取旧密钥或凭据文件，未推送 Git。

固定选题见 [tasks.json](tasks.json)，顺序如下：

| task_id | 主维度 | source_incident_id | 角色 |
|---|---|---|---|
| A-META-COUNT-ITEMS | data_handling_correctness | COUNT-ITEMS | 数值不一致识别 |
| A-PIT-VINTAGE-PASS | pit_and_methodology | PIT-SNAPSHOT | PIT 正常回答 |
| A-MULTIPLE-TESTING | research_logic | MULTIPLE-TESTING-CONTRACT | 拒绝不受支持的结论 |
| A-BACKTEST-NOT-RUN | evidence_discipline | QUALIFICATION-CONTRACT | 执行证据不足、正确拒答 |
| A-SUPPORT-THRESHOLD-PASS | refusal_quality | SUPPORT-THRESHOLD | 避免无依据拒答 |
| A-PROVIDER-TOKEN-LIMIT | reproducibility | PROVIDER-CAP-REAL | 调用故障与研究错误分离 |

覆盖六个主维度、六个不同冻结来源集群，含三个 PASS、两个 REFUSE、一个 FLAG_INCONSISTENT。未按历史模型得分选题。取舍：没有 INSUFFICIENT_EVIDENCE 终态；来源含合同夹具和合成控制，不能称为六个独立抽样真实事件。同作者真值/评分器不构成独立证据。

新增一个串行入口，复用原 ChatProvider 的传输/解析、Evaluator 0.2.0、prompt builder、分数向量和 TraceStore；不开发 DSH 或通用新 Harness。[freeze.json](freeze.json) 绑定原 v0.2 freeze、新入口、TraceStore、任务选择、完整 [prompts.json](prompts.json)、官方文档摘要和测试的 SHA。原 freeze 继续绑定未修改的 Provider/Evaluator/任务。请求适配仅在单次调用内生效并恢复原 urlopen，不支持并发。

文档核实日 **2026-10-09**，仅访问公开文档；详细来源及 UNKNOWN 项见 [provider_sources.json](provider_sources.json)。DeepSeek 使用 `deepseek-v4-pro`、`max_tokens=24000`、thinking enabled、reasoning_effort high，核对 [官方 API](https://api-docs.deepseek.com/api/create-chat-completion/) 和 [人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。小米使用 `mimo-v2.6-pro`、`max_completion_tokens=24000`、thinking enabled，核对 [模型](https://mimo.mi.com/models/en-US/mimo-v2.6-pro)、[API](https://mimo.mi.com/docs/en-US/api/chat/openai-api) 和 [按量价格](https://mimo.mi.com/docs/en-US/price/pay-as-you-go)。两家原生额度均包含推理与可见输出。

两家 CNY 计费已由用户确认。采用保守预算，不继续精细优化：每模型最多六次，每次输入估计上限 16384、completion 24000；总输入 196608、completion 288000。按 DeepSeek 高峰输入 ¥9/百万、输出 ¥27/百万，小米输入 ¥3/百万、输出 ¥6/百万，全部缓存未命中最坏费用 **¥5.931648**；冻结 **DeepSeek ¥4.80、小米 ¥1.20、合计 ¥6.00**。不配置搜索或工具。

请求前在 append-only trace 中预留完整调用/token/费用，不退还额度。缺失或非法 usage 保留全部预留，实际费用 UNKNOWN 并停止；不当作零消耗。认证/429、模型身份缺失或不符、疑似凭据输出、token 超界、测得超时和预算不足停止后续分发。HTTP/业务/超时通常同时导致 usage 未知，按此停止。每请求 socket timeout 300 秒、调度窗口 3600 秒；**socket timeout 不是严格总生成截止**，keepalive 可导致墙钟超出预期，记录后停止下一分发。输入按 UTF-8 字节数加 1024 做保守检查，服务端附加输入尚未实测。任何失败都不自动重试、提高额度、替换模型、复用 run_id 或启动后续阶段；中断后的预留按未核清尝试处理，不自动恢复网络调用。

逐响应保留非敏感原生 envelope 的受控引用/哈希、prompt/请求体哈希（不含认证头）、请求及实际模型、finish_reason/完整性/错误类别、verdict/evidence/reason 诊断、原分数及失败谓词、token/费用估算/延迟和 trace。原响应放在已忽略的 `benchmark/capability_public/runs/compatibility_pilot/<run_id>`，不进 Git；安全拦截时不留原文或哈希。费用是 usage 推算，已结算账单 UNKNOWN。本地 trace 哈希链不构成 sealed 或外部托管防篡改。

原 `evidence_ok` 包含 reason，新诊断分离 evidence/reason 失败来源，不修改原分数。length+可见内容归为输出截断；length+空内容且 reasoning usage 用满额度归为推理耗尽，证据不足则标记阶段 UNKNOWN。HTTP 200、正常 JSON 或正确 verdict 都不能单独证明完整/正确输出。

**必要定向测试 153 passed**，包括原 v0.2 的 124 项回归，详见 [offline_validation.json](offline_validation.json)。两次 pytest、两次默认离线 CLI 检查；真实 API 0。测试覆盖别名/数值/fence 的合理等价表达、否定错误值及正确拒答、JSON 内事实矛盾、空内容/耗尽/截断、原生参数、无重试停止规则、凭据回显拦截、预算核算和原响应/trace/旧分数离线回放。未重跑未修改的历史 Stage C2/QV7；历史全套 710 passed/1 skipped 不作为本轮新证据。

自由 reason 文本仍可能因冻结语法失败，已测试这种失败不会自动放宽合同；是否造成真实系统性误罚尚未知。所有真实响应语义复核仍 PENDING，当前不能报告合法答案误判实例数、真实完成率、费用或延迟。疑似评分器异常须先保存原响应/旧分数，标记 `EVALUATOR_ANOMALY_REVIEW_REQUIRED`，用冻结真值及最小反例核查。不得中途改 Evaluator、定向放宽一模型或重调 API；如需修复，另建版本并按相同规则离线重评两模型已有受影响响应。两模型均满分/零分先触发测量工具诊断，不归因为能力结论。

仍不等价：小米 thinking 强制 temperature=1/top_p=.95，DeepSeek thinking 忽略 temperature=0 并使用原生默认采样；tokenizer/推理分配不同；模型别名不固定权重，小米不可变版本 UNKNOWN；缓存、排队、限流、超时与计费时段不同。本次只测六项公开静态兼容性，不给正式排名、显著性或稳定能力差异结论。

统一执行申请为 [authorization_request.json](authorization_request.json)，当前 **approved=false / keys_rotated=false**：

- 固定任务：上表六项，固定顺序；模型：`deepseek-v4-pro`、`mimo-v2.6-pro`。
- Pilot freeze SHA：`d9bd47eb548243bdcbf2e1c1c683cd3c204af827f11216341bdf05b74644bf15`。
- 实际入口 SHA：`cb5cef8e17e1142a3758ece4b584e0254c2e27ad64f66b1874e52a9ba4195419`。
- 最多 12 次调用，零重试；token 和人民币上限及停止条件如上。
- 密钥轮换确认：**未获得**；凭据可用状态 NOT_CHECKED。仅在新真实授权后从安全环境变量 `DEEPSEEK_API_KEY` / `XIAOMI_API_KEY` 注入，不写值或密钥哈希。

申请一次明确批量授权：**确认历史暴露密钥已轮换或作废，并批准以上 SHA 绑定的固定 12 次 Pilot、¥6.00 上限和停止规则。** 当前仅提交申请并停止，准备授权不能替代真实授权；后续 24×2 比较另行授权。

默认离线检查及已有输出回放：

```powershell
$env:PYTHONPATH='src'
python -B -m quant_rsi.harness.compatibility_pilot
python -B -m quant_rsi.harness.compatibility_pilot --replay benchmark/capability_public/runs/compatibility_pilot/<run_id>
```

获得新授权和轮换确认后，记录非敏感批准事实并将申请字段改为 true，才可使用唯一真实入口：

```powershell
python -B -m quant_rsi.harness.compatibility_pilot --authorization benchmark/capability_public/pilot_v02/authorization_request.json --run-id TRACK_A_V02_COMPATIBILITY_PILOT_001
```
