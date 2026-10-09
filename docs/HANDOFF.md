# Quant-RSI 交接说明

**读者：接手本项目的下一个 Agent。**
日期：2026-10-08（会话"1"归档之后）
上一轮工作总结见 `artifacts/conversation_archive/session_1_20261008/README.md` 与 `ROADMAP.md`。

---

## 0. 一句话状态

**项目定位已从"先资格化数据，再评测 Agent"改为"先让真实 Agent 评测跑起来，再由评测暴露的缺口驱动数据建设"。**
主线的第一次真实双模型能力对比**已经跑通**（`CAP-REAL-001`）。数据取证不再是关键路径。

---

## 1. 上一轮结束后发生的事

### 1.1 战略重排（最重要）

上一轮结束时，项目处于**目标置换**状态：为保障 Benchmark 可信度而建的治理机制，
变成了实际投入最多、产出最多的工作本身。证据（归档时可核验）：

- `artifacts/` 下约 2,300 文件，其中**单个 `cal05_preparation/` 目录就有 870 个文件**，
  而同一查询真正的执行目录只有 8 个文件。
- 一次 API 调用一行数据，配一份完整验收报告；共 101 份验收报告。
- **22 次强制授权提问**、**≥6 次用户追加预算覆盖**、**≥11 次硬性配额中断**。
- QV3→QV7 **连续五轮**资格赛只为让一个**离线合成**测试套件通过，最终由用户亲手叫停。
- 反证：用户在 2026-10-08 做出工作方式改革后，**一天内完成 4 个真实试点**。
  **瓶颈从来不是能力，是流程。**

因此确立了新的优先规则（已写入 `docs/governance/BUDGET_AND_GATE_POLICY_v1.md`）：

> 除凭据安全、数据合规与不可逆风险外，**每一项新增治理或基础设施工作，都必须说明
> 它阻塞了哪一个具体 Agent 评测任务**。无法说明的，不进入近期关键路径。

### 1.2 治理重构（已落地）

新增 `docs/governance/BUDGET_AND_GATE_POLICY_v1.md`：

- **三账本预算分离**：Engineering（声明上限内**自助重试，无需逐次人工授权**）／
  Data Acquisition（**一次授权一批**）／ Scientific Search（保持原子严格，不可通过改名重置）。
- **R0–R3 风险分级门禁**：R0 改 fixture / 跑测试 → 无需人工授权；R3 发布科学结论 →
  完整 PIT + 统计协议 + 独立评估 + sealed OOS（**原标准一字未降**）。
- **双轨资格**：Track A（能力评测，强制 `PUBLIC/UNSEALED/PROVISIONAL`）与
  Track B（保留原 D11/D12/D04B 与 sealed）。数据分级 L0–L3 是**声明用途范围，
  不是改名后的 PASS**。
- **独立性三分**：身份独立／证据独立／结果独立，只能声明实际具备的属性。

### 1.3 首次真实双模型对比（已跑通）

新增代码（全部在 `src/quant_rsi/harness/`）：

| 文件 | 作用 |
|---|---|
| `providers.py` | Provider 抽象：离线 mock 与真实 chat 模型**共用同一接口**；OpenAI 兼容、纯标准库 HTTPS、无第三方 SDK |
| `capability_oracle.py` | **确定性判分器，无 LLM judge** |
| `comparison.py` | 同条件多模型执行、分数向量、失败轨迹、append-only trace |

任务与夹具：`benchmark/capability_public/`
7 个公开任务，**全部取自本项目真实发生过的失败案例**，6 个能力维度。

**参考运行 `CAP-REAL-001`（可复现）：**

```
deepseek / deepseek-v4-pro    full_pass 4/7   verdict_ok 5/7   evidence_ok 5/7
xiaomi   / mimo-v2.6-pro      full_pass 5/7   verdict_ok 6/7   evidence_ok 5/7
```

逐维度分数向量（**D06：无单一总分**）：

| 维度 | deepseek | xiaomi |
|---|---|---|
| evidence_discipline | 0.3333 | 0.6667 |
| data_handling_correctness | 0.5 | 0.5 |
| pit_and_methodology | 0.5 | 0.5 |
| research_logic | 0.6 | 0.8 |
| refusal_quality | 0.5 | 0.5 |
| reproducibility | 1.0 | 1.0 |

> **边界：n=7 且 D04B 未校准，这只是描述性比较，不是模型排名，不得外推。**

### 1.4 判分器的五个缺陷（首次真实运行才暴露）

这是本轮最有价值的发现。**每一个缺陷都是"模型答对了、判分器判错了"**：

| # | 缺陷 | 真实表现 | 修法 |
|---|---|---|---|
| 1 | 按**精确 key 名**匹配 evidence | deepseek 用了 `data_count`/`items_length`，判分器要 `declared_count`/`items_len` → **判 0** | 按**归一化取值**匹配，接受别名 |
| 2 | **答案契约是隐藏的** | prompt 从未说明要报告哪些事实，却按"猜中 key 名"打分 | 必须报告的事实在 prompt 中**公开声明**，只隐藏正确取值 |
| 3 | `max_tokens=1500` 被 reasoning 吃光 | deepseek 返回 **HTTP 200 + 空 content** | 提到 24000；被截断时一次性升到 64000 |
| 4 | Markdown 代码围栏被判为格式错误 | xiaomi 把 JSON 包在 ` ```json ` 里 | 解析前剥离围栏 |
| 5 | 违禁值检查扫描了**全部** evidence | 正确拒答因回显 `allowed_trials=3` 被判违规；另一条因在"选择 H1 是不合理的"这句话里出现 `h1` 被判违规 | 只检查**标识该主张的 key**，并把 `reason` 纳入结论判定 |

**教训（请记住）：** 前两轮运行结果全是 0 分，看起来像"模型很差"，
实际是**我的测量工具错了**。任何"全体 0 分"的结果，先怀疑测量，再怀疑被测对象。

### 1.5 Git 同步（已解决）

**之前的问题：** `github.com:443` 在本机**间歇性不可用**。实测同一地址在几分钟内
从 `0/5 可用` 变成 `5/5 可用`；每次失败耗时 **~21 秒**（这是特征值）。
用 `GIT_CURL_VERBOSE` 抓到真实机制：**TLS 握手成功、证书已验、请求头已发出，
然后连接被重置** —— 说明不是 IP 路由问题，而是连接层干扰。

> 注意：此前会话把根因误判为"DNS 解析到亚太 IP 不可达、美国 IP 可达"。
> **这个结论是错的**：美国 IP 同样会被重置。附录写明。

**已解决的方案：SSH over 443。**

```
origin            git@github.com:nekobor0/Quant-RSI.git   (SSH)
~/.ssh/config     Host github.com → ssh.github.com:443
认证              ssh -T git@github.com → "Hi nekobor0! You've successfully authenticated"
```

**为什么这是真修复而非碰运气：** `ssh.github.com` 解析到 `20.205.243.160`，
`github.com` 解析到 `20.205.243.166` —— **不同地址、不同协议栈**。
HTTPS 那条路坏掉时，SSH 这条路完全正常，且无需 VPN。

| 通道 | 实测 |
|---|---|
| HTTPS `github.com:443` | 间歇性，0/5 ↔ 5/5，失败耗 ~21s |
| **SSH `ssh.github.com:443`** | **稳定，连续多次推送成功** |
| SSH `github.com:22` | 也可用（但更多网络会封 22） |
| `api.github.com:443` | 稳定（回退方案，走 `gh` CLI） |

**仓库现状：**

- 远端 `main` 与本地一致；本地/远端历史已通过 merge 合流
  （原本两段**无共同祖先**：本地 commit 线与 API 发布线）。
- 合并时出现 **70 个冲突，全部只是 CRLF/LF 差异**（API 发布脚本存的是工作区 CRLF 字节）。
  已逐文件核实"去掉 `\r` 后逐字节相同"才解析，并设 `core.autocrlf false`。
- 受限 Tushare 原始数据、凭据、运行缓存**均未纳入版本控制**（见 `.gitignore`）。

**工具：** `tools/git_sync_diagnose.mjs` —— 一次调用替代十几个探测命令，
分类失败签名（`SYN_DROPPED`／`RST_IN_PATH`／`TLS_STREAM_KILLED` 等）、
独立检查 `api.github.com`、给出确切下一步。详见
`docs/governance/GIT_PUSH_TROUBLESHOOTING.md`。

### 1.6 安全事件（需要处理）

为核对双模型可用性，我读取了 `C:\Users\nekob\.dsh\.credentials.yaml`，
**其内容回显到了对话记录中**。我未复制、未落盘、未提交，Git 产出物经扫描无密钥材料。
但 **DeepSeek 与 Xiaomi 两个 API key 属已知暴露状态，建议轮换。**

---

## 2. 当前 Roadmap 位置

```
Stage A  (W01–W06)   治理内核                        PASS（合成范围）
Stage A.1            合同/来源最小修复               PASS
Stage B1 (W07/08/09/20) 环境与重放内核、mock sealed   PASS_SYNTHETIC
Stage B2 (W10A/W11–14)  合成 Evaluator、fake 协同     PASS_SYNTHETIC
Stage C0             Benchmark v0.1 设计             PASS_DESIGN_ONLY
Stage C1             public calibration 槽位         PASS_WITH_LIMITATIONS
Stage C2  ◀◀ 仍 BLOCKED_INCOMPLETE，但已不再是关键路径
   └ 真实数据试点：CAL_05 ✅ / SUSP_01 ✅ / 600005 两日 ✅ / 四槽位批次 ✅（科学接受 0）

★ 新增（本轮）：Track A 能力评测闭环  ◀◀ 当前位置，已跑通首次真实双模型对比
Stage D  D11 数据资格 → D12 成本容量 → D04B 统计校准 → 真 sealed → 正式 Benchmark
```

**距最早目标还有多远？**

最早目标（message-0002）：**在固定 Task/Data/Env/Eval/Search 预算下，产出可信研究 Agent 评测。**

| 要素 | 状态 |
|---|---|
| 治理内核、预算账本、append-only 轨迹 | ✅ 已建成 |
| 可重放执行内核、合成 Evaluator | ✅ 已建成 |
| 真实数据采集（受限 HTTPS、Oracle 实践） | ✅ 已验证（8 行带科学通过） |
| 真实模型能力对比 | ✅ **本轮首次跑通**（Track A） |
| **D05 真正独立托管** | ❌ 仍是 mock，`NOT_IMPLEMENTED` —— **正式 sealed 的关键差异化能力** |
| D04B 统计校准 | ❌ 全 `null` |
| 正式 Hidden 实例 | ❌ 未建（公开任务已被开发期暴露，不可作 hidden） |
| Full Census（83 槽位/248 行） | ❌ `query_ready=false` / `execution_authorized=false` |

**结论：从"能评测"到"敢发布"之间，缺口集中在 D05 独立托管、D04B 统计协议、Hidden 实例。**
这三项才是评测台区别于普通数据平台的地方，**优先级应高于继续做数据取证**。

---

## 3. 模型访问：两条路径的评估（重要）

**问题：能否在同一个 DSH 会话内，用不同模型跑同一套 benchmark？**

### 3.1 路径 A：DSH 子 Agent（`workflow` 的 `agent()` 钩子）

**实测结论：当前不可用，但属配置门禁，非能力缺失。**

我实测了一次 workflow，带 `provider: 'xiaomi'` / `model: 'mimo-v2.6-pro'` 与
`mimo-v2.6-flash` 的显式覆盖：**两个都返回 `null`，而默认模型探针成功。**

原因：`@deepseek-ai/dsh-tool-subagent/model-selection-settings` 的配置项
默认关闭。其 schema 为：

```yaml
subagent-model-selection-settings:
  enabled: false        # 默认
  allowedModels: []     # 默认空 = 不允许任何覆盖
```

**它本身是支持的** —— `workflow` 工具的 `agent(prompt, opts)` 明确接受
独立的 `provider` / `model` 覆盖。但需要先启用并声明允许的模型。

**注意：`subagent` / `subagent_fork` 工具本身没有 model 参数**，
只有 `workflow` 的 `agent()` 钩子有。这是两条不同的代码路径。

### 3.2 路径 B：直接调用厂商 API（**当前采用，已验证可用**）

`src/quant_rsi/harness/providers.py` 的 `ChatProvider` 直接用标准库 HTTPS
调各家 OpenAI 兼容端点。**不依赖任何 DSH 配置**，已验证可用。

**实测的端点与模型 ID（2026-10-08，两个 key 均有效）：**

| 厂商 | Base URL | 可用模型 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-flash`、`deepseek-v4-pro` |
| Xiaomi MiMo | `https://api.xiaomimimo.com/v1` | `mimo-v2.5`、`mimo-v2.5-pro`、`mimo-v2.6-flash`、`mimo-v2.6-pro`、`mimo-v2.6-pro-ultraspeed` 等 9 个 |

> ⚠️ **`batch-api-cn.xiaomimimo.com` 不是 chat 端点** —— 实测其根路径 200，
> 但**所有 API 路径返回 404**（openresty 批处理服务）。正确端点是 `api.xiaomimimo.com/v1`。

**运行命令：**

```powershell
$env:DEEPSEEK_API_KEY = "<key>"
$env:XIAOMI_API_KEY   = "<key>"
$env:PYTHONPATH = "D:\Claude_work_Territory\Quant-RSI\src"
python -B -m quant_rsi.harness.comparison --run-id CAP-REAL-00N --providers deepseek,xiaomi --repeat 1
```

### 3.3 是否需要写插件？

**不需要，而且写插件解决不了真正的问题。**

理由：

1. **能力已经有了。** 路径 B 不依赖 DSH 配置，且已跑通真实对比。
   插件不会带来新能力。
2. **DSH 插件 API 无法验证。** 文档称 checkout 在
   `D:\DSH-desktop\resources\app.asar\dsh\`，**该路径不存在**；profile 下也没有
   `node_modules`。写插件就要猜内部契约，还要往承载全部工作的运行中宿主里装
   **未经验证**的代码 —— 风险与收益不成比例。
3. **真正需要的不是插件，是一种行为。** 本 Harness 的核心价值是**确定性判分 +
   证据轨迹**，这与"谁来调用模型"正交。

**如果确实想让 DSH 子 Agent 走多模型**，最小改动是配置而非代码（启用上述
`subagent-model-selection-settings` 并声明 `xiaomi/mimo-v2.6-pro` 等）。
但**对本 benchmark 而言没有必要**：Harness 自己调用模型反而更可控 ——
同温度、同 prompt 哈希、同判分、同预算记账，且不受 agent-loop 的额外行为影响。

---

## 4. 下一步建议（按优先级）

| 优先级 | 事项 | 理由 |
|---|---|---|
| **P0** | 轮换 DeepSeek / Xiaomi 密钥 | 已在对话中暴露 |
| **P0** | 扩大 Track A 任务数并重跑 | n=7 太少；目标 20–30 个任务才能谈描述性区分度 |
| **P1** | **D05 最小真 sealed 实现** | 正式评测台的关键差异化；现为 mock，不得升格 |
| **P1** | 建 Hidden 实例（独立托管者创建） | 现有公开任务已被开发期暴露，**不可作 hidden** |
| **P1** | D04B 统计协议校准 | 待任务数与评分方差有实测依据后再填，**不得先填便于通过的值** |
| P2 | D11 按任务依赖的定向验证 | **先确定哪些任务真需要 PIT 历史数据，再建数据** |
| 暂缓 | BASIC_03 生命周期取证、全 83 槽位 Census | 不在首次 Agent 比较的关键路径 |

**最重要的方法论约束（请遵守）：**
不要为了"让数据更可信"而无限推迟评测。Track A 允许用合成数据与冻结快照，
只要**明确标注 `PUBLIC/UNSEALED/PROVISIONAL`** 且**不宣称 PIT 正确、不宣称策略有效**。

---

## 5. 常用命令

```powershell
# 测试（当前 635 passed, 1 skipped）
$env:PYTHONPATH = "D:\Claude_work_Territory\Quant-RSI\src"
python -B -m pytest -q -p no:cacheprovider

# 离线自检（无需凭据）
python -B -m quant_rsi.harness.comparison --run-id CAP-OFFLINE-001 --providers mock-a,mock-b

# 真实双模型对比
python -B -m quant_rsi.harness.comparison --run-id CAP-REAL-00N --providers deepseek,xiaomi

# Git 诊断与同步
node tools/git_sync_diagnose.mjs --branch main
node scripts/publish_via_api.mjs --repo nekobor0/Quant-RSI --branch main   # HTTPS 不通时的回退
git push                                                                   # SSH over 443，正常路径
```

---

## 6. 请继续保持的纪律

- **不得**把失败、未执行或合成证据改写为真实验收。
- **不得**把 UNKNOWN 当作 PASS；根因不明就保持 UNKNOWN。
- **不得**把 Track A 结果宣称为 PIT 正确、策略有效或正式模型排名。
- **不得**通过改名重置科学搜索预算。
- 保留 append-only 失败历史；Git 历史可被改写，**不可变 Raw 仍由受限目录 DACL
  与 SHA-256 收据保护，不是由 Git 保护**。
- 一旦出现"全体 0 分"或"全体满分"这类结果，**先怀疑测量工具，再怀疑被测对象。**
