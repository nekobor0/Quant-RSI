# 统一离线重评：评测器句号容忍（0.2.0 → 0.2.2-period-tolerant）

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
