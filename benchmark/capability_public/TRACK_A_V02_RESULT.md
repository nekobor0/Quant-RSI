# Track A v0.2 离线结果

2026-10-09（Asia/Shanghai）。`PUBLIC / UNSEALED / PROVISIONAL`。

**离线工程完成，真实双模型测试由用户明确暂缓。** 未读取凭据文件，真实模型 API 调用
0 次，校准调用 0 次，行情采集 0 次，scientific candidate trials 0。
Stage C2、D11/D12/D04B 和 Track B 资格保持原状态。

## 交付与验证

- 原有三个 harness 模块增加 v0.2 入口，原 `fixtures.json`、`tasks.yaml`、CAP-REAL-001
  原始记录、旧评分及报告均保留。新套件使用 `--suite 0.2`；默认仍为旧套件。
- `fixtures_v02.json`：24 项 STATIC_DIAGNOSTIC，10 个来源事件或冻结合同 fixture 集群；
  7 项原案例的版本化合同，加 17 项正常对照、受控反事实或合同算术 fixture。
- `validation_samples_v02.json`：作者依据来源预先编写的 24 个正确样例与 24 个错误决策样例；
  测试另外逐项注入事实、来源、矛盾和格式错误。不能称为独立人工裁决。
- `freeze_v02.json`：顺序、真值、公开契约、代码/样例哈希、prompt、provider 和预算冻结。
  只计算本轮必要文件哈希，未扫描历史数据或重新验证 QV7。
- `offline_validation_v02.json`：非敏感完整离线 manifest，逐任务原始响应、评分谓词、
  真值、分数向量、失败分类和 cluster 差异，可随 Git 同步。
- 第 1 次定向测试：122 passed；审阅后第 2 次完整测试：**710 passed，1 skipped**，86.55 秒。
  无失败测试被删去或改写。准备脚本曾出现括号错误和 Windows 默认 GBK 读取 UTF-8 错误；
  均在产物生成前失败，随后修正，未产生真实调用。
- 独立 CLI 离线运行 `CAP-OFFLINE-V02-001`：48 次响应、98 个 trace 事件，链验证通过，
  每次响应及时持久化，预算未停止。完整运行目录仍按原约定忽略于 Git。

## 相对 CAP-REAL-001 的测量修复

| 问题 | v0.2 行为 |
|---|---|
| 别名猜测与极性混淆 | 公开有限别名与类型；所有提供的别名必须一致；`is_as_of` 不再混入含义相反的字段 |
| 未公开必答事实 | 每项 prompt 带完整 input_contract；正确取值、接受 verdict 和真值理由不进入 prompt |
| 过宽归一化 | 数值用有限 Decimal 精确比较；证券、日期和枚举按字符串精确比较；布尔不等于数值 |
| Markdown、重复 JSON key | 接受完整 json/无标签围栏；拒绝不完整围栏、重复 key、NaN、非法外层结构 |
| 正确答案掩盖错误答案 | 任一错误别名、未声明证据、不存在来源均失败，不采用“找到一个正确值即可” |
| reason 中矛盾及否定引用 | 使用公开有限断言语法；错误正向断言失败，明确 `NOT(...)` 否定错误主张可通过 |
| 空答、截断混入研究错误 | HTTP、业务、空 content、token 用尽、JSON 失败、超时和预算拒绝分别记账；partial content 保留 |
| 事后追加预算 | ChatProvider 每次只发一个请求，无 transport retry，无 64000 token 追加 |
| 不完整批次缩小分母 | 预算在调用前预留；未执行任务单列；各模型的 24 项分配分母保持不变 |
| 调用证据缺失 | 记录 requested/observed model、finish_reason、reasoning token（如供应商提供）、耗时、成本缺失；未知用量停止后续真实调用 |
| D06 单一综合量 | 删除 dimension mean 聚合；保留六维向量与独立事实、决策、执行/格式统计 |

**确定性边界：** reason 不是任意自然语言评审。允许公开非事实解释句、
`fact=<JSON value>`、`NOT(fact=<JSON value>)`，按分号分句；未支持的自由解释不予通过。
这有明确的合同成本，会影响模型表现。尚未验证其对真实模型的可用性，不声称理解所有
自然语言否定、研究推理或证据语义。来源核验是“引用 supplied fixture ID”，不替代外部真实性取证。
答案在开发仓库对开发者可见；“隐藏”仅指不释放到被测模型消息，绝非 Hidden/sealed。

CAP-REAL-001 的 14 条记录与 16 个 trace 事件经读取核验，旧 4/7、5/7 结果仍成立于旧规则。
新旧 full_pass **不能直接比较**：任务分母、事实要求、reason 契约和调用失败政策均变化。
旧答案未按新合同生成，不能把缺少新 sources/断言格式的旧答案当成能力退步。

## 覆盖和离线测量

| 维度 | 主测量项 | 含交叉覆盖项 |
|---|---:|---:|
| evidence_discipline | 4 | 13 |
| data_handling_correctness | 4 | 5 |
| pit_and_methodology | 4 | 6 |
| research_logic | 4 | 8 |
| refusal_quality | 4 | 12 |
| reproducibility | 4 | 5 |

24 项是 10 个来源集群，**不代表 24 个独立研究事件**；受控 fixture 不冒充新发生的真实事故。
成本算术与多重检验规则由 fixture 明确规定，不填充或升级 D12/D04B 实证资格。

| 离线预设配置（非模型） | full_pass | verdict 正确 | evidence 正确 | 正确拒答 | provider/格式失败 |
|---|---:|---:|---:|---:|---:|
| mock-a：冻结正确回答 | 24/24 | 24/24 | 24/24 | 12/12 | 0/24、0/24 |
| mock-b：正确事实、错误决策 | 0/24 | 0/24 | 24/24 | 0/12 | 0/24、0/24 |

六维 full-pass rate：mock-a 均 1.0，mock-b 均 0.0。这是有意设置的两种样例配置，
不包含 DeepSeek/Xiaomi 输出，也不代表任一真实模型的表现。mock token=0，
reasoning/cost 供应商字段均未报告，不将缺失字段当成实测零费用。
成对比较覆盖 24 项、10 个集群；各集群平均 full-pass 差异为 1.0，cluster 等权差异 1.0；
不计算显著性或不具备依据的置信区间。

保留 `EVALUATOR_ANOMALY_REVIEW_REQUIRED`：mock-a 全满分，mock-b 全零，
valid JSON 的 verdict/evidence 分离达到冻结的 25% 阈值。它们由预设样例造成，
评分不被自动改写。测试另外覆盖两模型某维度同分、解析失败率 ≥25% 的告警。
异常调查采用上述冻结样例及注入错误；**未为了去掉告警改 Oracle**。

作者对六维代表样例作了来源与算术复核：count 0/一行、错误证券/日期、当前快照/未来修订、
净收益 -0.01/+0.01、Bonferroni 0.0025、门槛 0.60、预算剩余 0、三类 provider 元数据。
正例、错误决策和正确拒答均纳入复核；身份与结果独立性均未实现，D08 不升格。

## 真实运行计划（本轮不执行）

候选沿用历史确认的 `deepseek-v4-pro` 与 `mimo-v2.6-pro`，相同任务和契约，无工具，
temperature=0，max_tokens=24000，timeout=300 秒。模型 ID 可用性、原生 reasoning
差异及当前价格本轮未联网核实，不能称为当前可用或已校准。
24 项×2 个模型×1 次＝48 调用上限；任务优先顺序，模型先后顺序逐项交替。
固定单次输入预留上限 16384 token、输出/reasoning 合计 24000 token；保守按 UTF-8
字节加消息开销检查输入，非精确 tokenizer 计量。总预留输入 786432、输出 1152000，
请求等待预算 14400000 ms。无预检、重跑、分页、换模型或额外模型。

最坏金额公式：每个模型 `24 × (16384 × 每百万未缓存输入价 + 24000 × 每百万完整输出价) / 1000000`。
**价格、货币预算及批次授权均未批准；密钥轮换尚未确认。** 固定 24000 沿用历史设置，
不是本轮预检所得结论。若以后需要预检或原生参数调整，先单独冻结额度与版本，
不得看正式答案后追加预算。目前 freeze 标记 `DEFERRED_BY_USER`，代码也拒绝真实运行。

后续真实运行须绑定新的执行 freeze、明确批次/金额授权、凭据安全及当前 model/price 核验。
CLI 当前支持离线验证；真实调用需显式调用 run_comparison 的授权接口，旧历史不构成授权。

## 下一阶段优先级

当前 comparison 每题一次 chat，无工具调用、状态迭代或完整自主 Agent。它验证的是
STATIC_DIAGNOSTIC 的评分/执行链；未测得真实模型区分度，也未验证完整研究 Agent。

下一阶段优先做最小 AGENT_WORKFLOW，同时在获授权的公开试运行中检查合同可用性与
真实区分度；D05 独立托管在准备正式 sealed 时再独立验收。本轮不启动这两者。
适合的三个多步骤任务：

1. 读冻结 API fixture → 审计 key/count → 输出清洗后的可接纳表及拒绝理由。
   复用 WorkerRequest/input_hashes、TraceStore；新增受限 fixture 读取工具。
2. 选择 decision cutoff 前 vintage → 调用一次 synthetic-daily-v1 → 校验结果与重放。
   复用 PITView、simulate、RunManifest 与 eval.replay；不声称真实 PIT 经济资格。
3. 保留失败记录 → 在同预算 root 内判断能否重试 → 汇报剩余额度。
   复用 SearchBudget.reserve/settle、budget denial 与 orchestration.run_once 的归档结构。

B2 的 run_once 目前显式限定 FakeProvider，replay 也限定 synthetic operation；
不能直接把接口名视作已有真实 Agent 支持，需要下一轮单独实现和验收 adapter/状态循环。

## 使用与 Git

```powershell
$env:PYTHONPATH = "$PWD\src"
python -B -m pytest -q -p no:cacheprovider
python -B -m quant_rsi.harness.comparison --suite 0.2 --run-id <新的离线ID> --providers mock-a,mock-b
```

run ID 不得重用；freeze 绑定文件变更会在 dispatch 前阻止运行。新版本须保留旧结果。
本轮 10 个变更/未忽略新文件已作凭据模式和受限路径检查：命中均为 0，冻结的
10 个文件绑定全部有效，`git diff --check` 通过。没有读取或散列凭据材料；这不是历史仓库全量扫描。
必要源码、测试、fixture、freeze、可同步离线结果及本报告提交在
`codex/track-a-v02`；具体 commit/push 状态见交付消息。受限数据、凭据和缓存不提交。
本轮到此停止，不追加治理收口，不启动 Full Census、BASIC_03、D11、Hidden、sealed 或实盘。
