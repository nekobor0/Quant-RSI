# Track A 能力评测：离线可验证部分完成报告

日期：2026-10-08
状态：**OFFLINE_VERIFIED / NO_MODEL_CALLS_MADE**
标签：`PUBLIC` / `UNSEALED` / `PROVISIONAL`

> 本报告只记录离线可验证的成果。**未调用任何真实模型**，因此本报告不包含
> 任何模型能力结论、排名或分数比较。真实双模型对比待模型访问方式确定后执行。

## 1. 本轮交付

按战略重排的 P0 顺序，先完成"首次真实多模型对比"中**不依赖模型访问**的全部部分，
使真实模型接入后只需替换 provider，不改动判分逻辑。

| 交付物 | 路径 | 作用 |
|---|---|---|
| 治理策略 | `docs/governance/BUDGET_AND_GATE_POLICY_v1.md` | 三账本分离、R0–R3 风险分级、双轨资格、独立性三分、常设优先规则 |
| 任务夹具 | `benchmark/capability_public/fixtures.json` | 7 个公开任务、6 个能力维度、确定性 Oracle 规格；SHA-256 `d0c8d88e13c179a4a9db52d6fdf7bd7433428a01f36cd8dde0686766ac36d155` |
| 任务清单 | `benchmark/capability_public/tasks.yaml` | 任务来源、维度映射、可读的任务说明 |
| 确定性判分器 | `src/quant_rsi/harness/capability_oracle.py` | 逐字精确判分，**无 LLM judge** |
| Provider 抽象 | `src/quant_rsi/harness/providers.py` | 离线 mock 与真实 chat 模型共用同一接口 |
| 对比 runner | `src/quant_rsi/harness/comparison.py` | 同条件多模型执行、分数向量、失败轨迹、append-only trace |
| 测试 | `tests/test_capability_comparison.py` | 38 项，其中 35 项为判分器与 run 契约验证 |

## 2. 任务设计：来自真实失败，而非凭空构造

7 个任务全部取自本项目真实数据工作中**实际发生过**的失败或歧义。这是它们
有判分价值的原因——每个都有确定真值，且都不需要 PIT 历史数据工程。

| 任务 | 真实来源 | 正确处置 | 测得能力 |
|---|---|---|---|
| `A-META-COUNT-ITEMS` | 真实 Tushare 响应 `code=0`、`count=0`，但 `items` 含 1 行 | `FLAG_INCONSISTENT` | 据载荷而非元数据下结论 |
| `A-EMPTY-VS-FAILURE` | 旧停牌 Pilot 三次调用被 HTTP 错误回退为空表，根因 UNKNOWN | `INSUFFICIENT_EVIDENCE` | 区分"合法空表"与"静默失败" |
| `A-PIT-BACKFILL-REFUSAL` | 主表为 `CURRENT_STATIC_SNAPSHOT`，无 `available_at` | `REFUSE` | 当前快照不得回填历史 PIT |
| `A-PIT-ANNOUNCEMENT-VS-EFFECTIVE` | 终止上市公告 20170208 发布、20170214 生效 | `PASS`（正向对照） | 公告日≠生效日，二者不可互换 |
| `A-DELIST-NOT-SUSPENSION` | 退市后 0 行只是与已知终止上市一致 | `REFUSE` | 缺失不得自动归因 |
| `A-BUDGET-ESCAPE` | 原设计禁止 retry/改名重置额度 | `REFUSE` | 搜索预算不可通过改名逃逸 |
| `A-INSUFFICIENT-SUPPORT` | 正确否决坏策略计入能力但不构成策略通过 | `REFUSE` | 证据不足时正确否决 |

**任务集本身是已公开暴露的**（都来自本项目自己的工作记录），因此仅适用于
Track A 开发期评测，**不得作为 hidden set**。真正的 hidden 实例必须由独立
托管者新建。

## 3. 判分方式：确定性、可复核、无 LLM judge

每个任务在任何模型运行**之前**固定：可接受 verdict 集合、必须精确匹配的
evidence 键值、必须存在但取值自由的键、必须成对出现的键，以及被显式禁止的
取值。额外字段一律不惩罚。

关键保护（均有测试）：

- 缺失 `verdict`/`reason`/`evidence` 任一键 → `MISSING_CONTRACT_KEYS`
- verdict 正确但 evidence 错 → `EVIDENCE_MISMATCH`（与 verdict 错误分开记录）
- 必填键以 `UNKNOWN`/`null`/空串作答 → `EMPTY_SENTINEL` 拒绝
- 在"证据不足"任务中上报胜者（`terminal=H1`）→ `FORBIDDEN_EVIDENCE_VALUE`
- JSON 不可解析 → `UNPARSEABLE_OR_INVALID_FORMAT`
- **调用本身失败 → `TRANSPORT_FAILED`**

最后一条是本轮补上的重要区分：把"调用没成功"和"模型答得差"混为一类，会让
凭据缺失这类基础设施故障看起来像模型能力差。若一次 run 全部传输失败，结果被
标记 `capability_result_valid: false` / `ALL_TRANSPORTS_FAILED_NO_CAPABILITY_EVIDENCE`，
不得读作能力结论。

## 4. 离线参考运行结果

Run `CAP-OFFLINE-REF-001`，`repeat=2`，provider 为确定性 mock（**非真实模型**）。
其唯一目的是证明整条管线可运行、可判分、可复现。

```
tasks: 7   attempts: 28   scientific_candidate_variants: 0   budget_stop: None

provider   model               full_pass  pass_rate  verdict_ok  evidence_ok
mock-a     mock-ideal-v1               6     0.8571          10            8
mock-b     mock-variance-v1            6     0.8571          10            8

dimension                        mock-a     mock-b
evidence_discipline              0.3333     0.3333
data_handling_correctness           0.5        0.5
pit_and_methodology                 0.5        0.5
research_logic                      0.4        0.4
refusal_quality                     0.5        0.5
reproducibility                     0.0        0.0

failure types: {NONE:6, EVIDENCE_MISMATCH:4, WRONG_TERMINAL:2, UNPARSEABLE_OR_INVALID_FORMAT:2}
reproducibility: stable=7  variance=0
```

**这些数字不构成任何模型结论。** mock 的能力画像是人为设定的，其作用是证明
判分器能区分"完全正确"、"verdict 对但证据错"、"verdict 错"和"格式不可解析"
四类失败，并且能检测输出方差。

`reproducibility=0.0` 是维度设计使然：该维度只挂在 `A-BUDGET-ESCAPE` 上，
而 mock 在本题输出被截断的 JSON，故未通过。这恰好演示了维度级判分是有效的。

## 5. 合同与账本合规

- **D06**：只产出分数向量，**无单一总分**（有测试断言 `total_score`/`overall` 不存在）。
- **D02**：评测研究对象是 Research Agent 的研究过程，不涉及策略经济学。
- **科学搜索预算为零**：每次 run 显式记录
  `scientific_candidate_variants: 0` 与
  `scientific_search_budget = {candidate_trials: 0, factor_variants: 0, parameter_trials: 0, hypotheses_seen: 0}`，
  并有测试断言。工程能力评测在结构上不可能被误读为策略搜索。
- **Track A 标签强制**：manifest 固定 `sealed: false`、`pit_correct: false`、
  `may_claim_tradable_alpha: false`、`is_formal_model_ranking: false`。
- **append-only**：复用既有 `TraceStore`（SQLite 触发器 + 哈希链）。同 run_id
  重跑被拒绝；直接 UPDATE trace 被拒；链完整性可复验。
- **凭据**：provider 仅在调用时从环境变量读取，进程内保留，不落盘、不回显、
  不记录哈希。已验证在无凭据环境下 run 失败关闭且产出物中无密钥材料。

## 6. 测试与回归

```
python -B -m pytest -q -p no:cacheprovider
621 passed, 1 skipped
```

其中本轮新增 38 项（`tests/test_capability_comparison.py`），既有 583 项无回归。

新增 `tests/conftest.py` 将测试临时目录改到工作区内，因为本机默认 pytest 临时
根目录不可写。该 fixture 对参数化测试名做了 Windows 安全化与长度约束。

## 7. 尚未完成 / 下一步

| 项 | 状态 | 阻塞 |
|---|---|---|
| 真实双模型对比（DeepSeek + Xiaomi MiMo） | **未执行** | 模型访问方式待定 |
| Hidden 实例（未暴露样本） | 未开始 | 需独立托管者（D05），本次不触碰 mock sealed |
| D04B 统计协议校准 | 未开始 | 待真实对比产生方差后才有依据 |
| Git 远端同步 | **已阻塞** | `github.com:443` 不可达；本地 commit 安全，通道恢复后 `git push` |

真实对比一旦执行，将产出同条件、同预算、同判分规则下的模型间分数向量与完整
失败轨迹。按 D04B 未校准的事实，7 个任务的结果**只能用于调试评估流程与描述性
比较，样本量不足以支持稳定模型排名**。

## 8. 边界声明

本报告是 Track A 工程与能力评测产物，**不是**科学资格验收。它不证明 PIT 正确、
不证明策略有效、不构成正式 Benchmark、也不构成对任何模型的正式排名。Stage C2
保持 `BLOCKED_INCOMPLETE`；D11/D12/D04B 保持 `NOT_READY`；Full Census
`query_ready=false`、`execution_authorized=false`——本轮未改动这些状态，也未
推进任何数据取证。
