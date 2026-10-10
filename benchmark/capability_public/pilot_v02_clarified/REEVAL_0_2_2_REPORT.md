# 统一离线重评：评测器句号容忍（0.2.0 → 0.2.2-period-tolerant）

> 2026-10-10：下文保留历史重评说明；当前工程验收、语义裁定及 Roadmap 位置见第 8 节。
> 历史 `REEVAL_0_2_2.json` 保留不变，新的证据绑定产物为 `REEVAL_0_2_2_BOUND.json`。

日期：2026-10-09
新评测器版本：`0.2.2-period-tolerant`
冻结评测器版本：`0.2.0`（**未修改**）
**网络调用 0 次；凭据读取 0 次；原分数全部保留未改。**

---

## 1. 修复内容

### 1.1 缺陷

`capability_oracle.py:559-567` 用**精确字符串相等**判断 reason clause 是否为已公布的解释句：

```python
if clause in contract['reason_explanations']:   # 公布的句子末尾「带句号」
    continue
...
mismatches.append('reason:UNSUPPORTED_CLAUSE')
```

冻结契约公布 `'The supplied fields contradict each other.'`；两个模型都写成不带句号，
于是**一个合规回答仅因一个句号被判失败**，而同一 reason 中其余 clause 全部合规。

### 1.2 修复方式（**新建版本，不改冻结评测器**）

新增 `src/quant_rsi/harness/evaluator_022.py`，实现**窄容忍**规则：

> 某个 clause 与**恰好一条**已公布句子的差异**仅为末尾一个 `.`** 时，接受为已公布解释句。

**刻意不做任何更宽的容忍**：不做大小写折叠、不合并空白、不做前缀匹配、不做模糊距离。
理由是更宽的容忍会开始猜测模型意图，而这正是该评测器设计上要避免的。

证据别名、事实取值、否定、来源、verdict 接受等**一律原样委托冻结的 0.2.0 实现**。

### 1.3 修复过程中我自己踩的坑（如实记录）

第一版实现把容忍契约写进 `suite_task()` 返回的字典，重评结果**零变化**。
查明原因：`capability_oracle.suite_fixtures()` 内部调用 `load_fixtures()`，
而它**每次调用都重新解析 JSON 文件 —— 根本没有缓存**。
所以我改的是一个用完即弃的对象。

**真正能到达评测器的缝是 `load_fixtures` 本身**，已改为替换它。
这个 bug 是因为重评报告"零行变化"才暴露的 —— 与项目一贯的教训一致：
**结果异常时先怀疑测量工具。**

---

## 2. 重评结果

### 2.1 Pilot 002（澄清合同批次，12 项）

| 指标 | 0.2.0 原分 | 0.2.2 重评 | 变化 |
|---|---|---|---|
| full_pass | 6 / 12 | **9 / 12** | **+3** |
| verdict 正确 | 11 / 12 | 11 / 12 | 0 |
| `reason:UNSUPPORTED_CLAUSE` | 5 | **0** | **−5** |

**逐项变化：**

| provider | task | full_pass | 被句号容忍救回的 clause |
|---|---|---|---|
| xiaomi | A-META-COUNT-ITEMS | ❌ → **✅** | `The supplied fields contradict each other` |
| xiaomi | A-PIT-VINTAGE-PASS | ❌ → **✅** | `The supplied evidence supports this scoped decision` |
| deepseek | A-MULTIPLE-TESTING | ❌ → **✅** | `The supplied evidence does not support the proposed claim` |
| deepseek | A-BACKTEST-NOT-RUN | ❌ → ❌ | `...does not support the proposed claim`（另因 below 仍失败） |
| xiaomi | A-PROVIDER-TOKEN-LIMIT | ❌ → ❌ | `...supports this scoped decision`（另因 below 仍失败） |

**5 个 clause 被救回，其中 3 项因此转正。**

### 2.2 Pilot 001（旧合同批次，5 项）

| 指标 | 0.2.0 原分 | 0.2.2 重评 | 变化 |
|---|---|---|---|
| full_pass | 0 / 5 | **0 / 5** | 0 |
| verdict 正确 | 4 / 5 | 4 / 5 | 0 |
| `reason:UNSUPPORTED_CLAUSE` | 3 | 3 | 0 |

**句号容忍对 Pilot 001 零影响。** 该批次的 reason 用的是**旧的 `fact={...}` 语法**，
本就没有"裸解释句"可供救回。这与"不得混合新旧 Prompt 批次"一致 —— 两批次独立计分。

---

## 3. 仍未通过的三项（均为实质性，与标点无关）

修复后 12 项中仍有 3 项失败，**全部不是句号问题**：

| provider | task | 0.2.2 failure_type | 实质原因 |
|---|---|---|---|
| deepseek | A-PROVIDER-TOKEN-LIMIT | `WRONG_TERMINAL` | 答 `INSUFFICIENT_EVIDENCE`，真值要求 `PASS` |
| xiaomi | A-PROVIDER-TOKEN-LIMIT | `DISQUALIFYING_CLAIM` | `reason:failure_class:CONTRADICTORY_ASSERTION` |
| deepseek | A-BACKTEST-NOT-RUN | `EVIDENCE_INCOMPLETE` | `unsupported_evidence_field`（多给了未声明字段） |

**这三项是真实违约，不是判分缺陷：**

- **A-BACKTEST-NOT-RUN**：证据结构合同明写「Flat object: declared aliases and sources only」，
  模型多给了 `prepared` / `D04B` / `D11` / `D12`，**确属超范围字段**。
- **xiaomi / A-PROVIDER-TOKEN-LIMIT**：reason 断言与真值矛盾（`failure_class` 取值冲突），
  这是评测器按设计要拦的"矛盾断言"。
- **deepseek / A-PROVIDER-TOKEN-LIMIT**：verdict 选错。该题仍存在
  「要求一个从未公布的枚举词 `TOKEN_BUDGET_EXHAUSTED`、输入只给了 `finish_reason="length"`」
  的**测量歧义**，n=1 不足以量化，**保留为待审计项**。

---

## 4. 结论

**句号缺陷影响的量级已被准确界定：**
12 项中 5 项被误判（`reason:UNSUPPORTED_CLAUSE`），修正后 full_pass **6 → 9**。
即**原报告中 6 项失败里有 3 项是纯判分缺陷**；此前我按"仅缺句号"计数为 5 项，
其中 3 项是**独立**的通过阻塞，另 2 项虽同一原因但另有实质违约 —— 两者已区分清楚。

**Pilot 001 不受影响**，因为其 reason 使用旧语法。

**`confirmed_legal_answer_misjudgments`：3 项**（有最小反例、可离线复核）。

---

## 5. 版本与绑定

| 项 | 值 |
|---|---|
| 冻结评测器 `capability_oracle.py` SHA-256 | `ac42a75593e7c3535831c78ada304ffaddf251eb846c17414a940093cd7e4297` |
| 实测 SHA-256 | `ac42a75593e7c3535831c78ada304ffaddf251eb846c17414a940093cd7e4297` |
| **冻结评测器是否被修改** | **否（逐字节未变）** |
| 新重评器 | `src/quant_rsi/harness/evaluator_022.py` |
| 重评记录 | `benchmark/capability_public/pilot_v02_clarified/REEVAL_0_2_2.json` |
| 全量回归 | **901 passed, 1 skipped**（新增模块未破坏任何既有测试） |

**原分数与原始响应全部保留未改**；新旧两套分数（`score_original` / `score_0_2_2`）
在重评记录中并列存放，可逐条对比。

---

## 6. 复现命令

```powershell
$env:PYTHONPATH='src'
python -B -m quant_rsi.harness.evaluator_022 --write
```

无网络、无凭据。会先校验冻结评测器 SHA，若与 `ac42a755…` 不符则告警。

---

## 7. 边界声明

本重评**只**修正一处标点容忍语义，不改变任何证据/事实/来源/verdict 判定。
不得据此生成正式排名、显著性结论或稳定能力差异结论；不得与其它 prompt 版本池化。
Track A = `PUBLIC/UNSEALED/PROVISIONAL`；D05 / D08 / 真实多轮 Agent 能力状态不变。
未推送 Git。

## 8. 2026-10-10 审计补齐与当前裁定

本轮授权只覆盖离线修复、测试和证据绑定。真实 API 调用 0 次，真实凭据读取 0 次，
没有修改原冻结 Oracle、fixture、Prompt、Pilot 入口或真实运行记录。

### 8.1 三项工程补齐

1. 新增 `tests/test_evaluator_022.py`，30 项定向测试通过。验证公布解释句原样及省略
   一个末尾句号可接受；大小写、内部空白、前缀、额外标点/文字变化仍拒绝；重复匹配
   不新增容忍变体。错误事实、否定、来源、verdict、额外字段和 Provider/JSON 失败
   继续沿用原硬判定。测试的 HTTP 和凭据均为合成占位，不执行真实传输。
2. Oracle 或 fixture 哈希不匹配时，在评分及读取运行证据之前拒绝；CLI 返回非零，
   不写报告。缺失运行、证据篡改、原分数漂移也拒绝，不输出部分成功报告。
3. 新产物绑定新评测器版本及源码 SHA、原 Oracle/fixture SHA、两批的原 freeze/入口
   SHA、Prompt/result/逐次记录/原始响应/Trace 文件 SHA、Trace anchor 及逐响应引用。
   复用现有 Trace 校验器，以只读 SQLite 核验，不建立第二套 Trace/Budget。
   旧重评 JSON 不覆盖；新绑定报告已有且内容不同时拒绝写入，相同则保持原字节。

相关回归：**251 passed**，包含上述 30 项及 STATIC_DIAGNOSTIC、Pilot、预算和 Trace
相关测试。未重跑全仓、Stage C2、QV7、Workflow 或 Hybrid 的未修改历史验收。
首次测试遇到沙箱临时目录权限错误，并发现测试未注入占位环境变量；修正测试临时目录
使用及占位注入后，定向与相关回归通过。这不是 Provider 实测失败。

证据核对：42 个相关原始证据/冻结评分输入/旧重评文件在生成新报告前后哈希一致；
新旧重评逐行评分完全一致。Pilot 002 仍为 6/12 → 9/12，Pilot 001 仍为 0/5 → 0/5。

| 绑定 | SHA-256 |
|---|---|
| 新评测器源码 | `c76ef9fe5b1f3cb6f145ada6d1f4f640cc328aa85753c5b72e23413160c05eff` |
| `REEVAL_0_2_2_BOUND.json` | `96d1f427adae41252accd8a10ad9b78cd22bf4d8baad98101c84b4beccfd12ac` |

复现：`python -B -m quant_rsi.harness.evaluator_022 --write`，环境设置 `PYTHONPATH=src`。
模块限离线串行重评，临时替换 fixture loader 时不得与其他评分线程并发执行。
这些是本地完整性绑定，不是外部 Custodian 或不可篡改封存证明。

### 8.2 替代历史过度判断

- 新规则下新增 3 项 full_pass，是已确认的**评分规则变化**；原公开合同使用精确句子，
  尚不能据此认定 3 项已满足旧合同却被实现误判。
  当前 `confirmed_legal_answer_misjudgments = null`，替代上文的“3 项”及 RESULT_002
  中的“5 项”历史声明。未来合同应明确公布解释句的末尾句号可省略。
- A-BACKTEST-NOT-RUN 的额外 evidence 字段违反已公布的字段白名单，此问题仍成立。
- A-PROVIDER-TOKEN-LIMIT 的未公布枚举同时影响两模型：MiMo 输出 `TOKEN_LIMIT`，
  DeepSeek 输出 `length`，均与真值 `TOKEN_BUDGET_EXHAUSTED` 不符。冻结判定及分数
  原样保留，但不得将 MiMo 的取值冲突直接归为已确认的事实错误，同时只对 DeepSeek
  保留合同歧义。两者共同保持 `EVALUATOR_ANOMALY_REVIEW_REQUIRED`；DeepSeek 的
  verdict 与原真值不符亦须结合公开诊断终态含义审查。
- Pilot 002 控制器硬封顶违反明确执行前提，标记
  `NONCOMPLIANT_CONTROLLER_BUDGET_ENGINEERING_EVIDENCE_ONLY`。不删除、清零、混合
  新旧批次或自动重跑；不将测量调用的小计当成含控制器的完整费用。

0.2.2 现为**完成补齐的离线重评候选**，不是已经重新冻结并获得真实执行授权的版本。
本轮未改既有公开合同或 token-limit 任务；后续修订需新版本及统一适用于两模型的规则。

### 8.3 当前 Roadmap 位置及下一步

旧 HANDOFF 的 2026-10-08 状态是历史快照；当前用户确认状态及本次证据优先。
当前位置：**Track A 的真实 STATIC_DIAGNOSTIC 兼容性测量修复阶段**。

| 工作线 | 当前证据状态 |
|---|---|
| STATIC_DIAGNOSTIC v0.2 | 24 项公开冻结基线保留；不能视为已完成 24×2 实测 |
| 六题兼容性 Pilot | 001 部分执行；002 完整响应留证但控制器预算违规，不能登记合规验收 |
| Evaluator 0.2.2 | 离线工程补齐、证据绑定及相关回归通过；新合同/真实执行 freeze 未建立 |
| AGENT_WORKFLOW v0.2 | 离线多轮、预算、工具和过程判分完成；真实 Agent 能力 UNVERIFIED |
| HYBRID_EVALUATOR v0.1 | 离线校准/Validator 完成；真实 Judge 能力 UNVERIFIED |
| D05 / D08 | BLOCKED_ENVIRONMENT_CAPABILITY / NOT_IMPLEMENTED、NOT_VERIFIED |
| Track B、Stage C2、D11/D12/D04B | 保留原状态，没有晋级或重验 |

下一步先解决 token-limit 的公开枚举与诊断 verdict 含义，明确句号可省略，绑定新的
合同、评测器与最小执行配置。规则必须与具体模型无关，原冻结任务及旧分数继续保留。
已有响应先统一离线重评。若需验证修改后的实际回答契约，再申请一次独立六题批次；
用户直接在非模型终端启动固定入口，测量预算由代码控制，避免无硬封顶的付费控制器。
该批次是验证新合同，不是补做旧请求或为消除违规重跑。

兼容性、测量与预算门禁满足后，才进入另行授权的 24×2 公开比较；真实多轮 Agent
Pilot 及 Luna Judge 校准仍各需独立预算冻结与授权。D05 等待真实隔离环境，不重试
Restricted Token、不扩题、不启动 Hidden、策略搜索或实盘。

Track A = PUBLIC / UNSEALED / PROVISIONAL；D08 独立性未验收。本轮完成后停止。
