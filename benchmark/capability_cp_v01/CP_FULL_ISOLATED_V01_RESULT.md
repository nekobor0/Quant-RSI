# 四道CP完整隔离工程验收 v0.1

日期：2026-10-10（Asia/Shanghai）。

**结果：PASS_CP_FULL_ISOLATED_ENGINEERING。** 四题参考实现4/4、等价实现4/4通过；八个错误对照8/8被检出，均保留通过项，没有统一判全零。
这是作者受控合成代码的离线工程验收，不是任何真实模型的代码能力验证，也不是普遍正确性证明。
Track A保持 **PUBLIC / UNSEALED / PROVISIONAL**；真实Agent/Judge能力UNVERIFIED，D08未验收，D05未授予完整托管资格；Track B、D11/D12/D04B不变。

## 实际范围

本轮直接用户授权：完成四道CP的完整隔离性质测试、错误对照及独立冻结。

- 使用已有固定镜像，没有拉取、重建镜像或修改Docker/Windows/WSL配置。
- 16个成功留证的实际容器会话；加上首次监督器失败，共17次尝试，未超过声明的24次工程上限。
- 每个任务分别执行参考、等价实现及两个错误对照，每种实现在独立容器中运行全部该题探针。
- 每会话函数探针数：CP01=24、CP02=21、CP03=30、CP04=22。成功留证共388次函数调用；另有CP04每会话一次调用者修改旧返回对象，共4次。
- 首次失败会话内部执行次数UNKNOWN，不能加进388次已验证分母。
- 16/16轨迹及追加诊断可离线回放，回放无模型调用、无容器启动、无工具重执行。
- 模型、Judge、行情或研究数据API均0次；未读取凭据，未提交或推送Git。
- 只查询并清理本轮创建的精确容器ID；17/17已确认不存在。未操作其他容器。

## 每题覆盖及外部判据

`cases.json`包含人工可核对的设定值、预期异常、性质归属、变形关系和最终保留对象状态；计算参考值不调用被测函数。`public_contract.json`继承原合同的行为定义，没有改变原补集合同。
允许浮点结果绝对误差1e-8；字典键集合、字符串、异常类型、空值及序列长度严格核验。输入前后快照使用规范JSON哈希精确比较，不用浮点容差隐藏微小输入修改。

| 任务 | 公开性质组 | 具体核验 |
|---|---:|---|
| Q-CP-01 `normalize_rows` | 6 | 空输入；按security/date排序；排列不变；相同重复幂等；冲突必须ValueError，包含价格差仅1e-9的冲突；字段缺失/额外字段、非法行/容器、空标识符、bool/非数值/非正/NaN/±Inf价格；标识符空格精确保留；修改返回行不能改输入。 |
| Q-CP-02 `lagged_mean` | 6 | 空输入；window=1、等于或超过长度；不足历史时None；严格使用values[t-window:t]；改变当前及未来值、追加未来后缀的前缀不变关系；正整数且排除bool；非法值/元组/空输入下非法window；输入保持。 |
| Q-CP-03 `interval_pnl` | 8 | 空输入、零信号、空输入也验证cost；空头、方向反转；q[0]=0及一期信号滞后；末期信号改变不影响本期输出；turnover取相邻仓位绝对差，反转换手2；费用对齐；算术pnl_sum而非复利；长度不匹配、非法收益/信号/费用、bool/NaN/±Inf及非list；输入保持。 |
| Q-CP-04 `build_ledger` | 6 | 空输入和多次调用后空输入；同进程两次A；同进程A/B/A；修改早先返回对象后再次A；早先修改不能污染其他已返回对象；每次累计从0开始；负/小数金额、相同event_id的多个事件不擅自去重；输入不变；非法事件字段、标识符、类型及非有限金额。 |

全部26个公开性质组均有实际容器观察。97种具体函数探针每种在四个实现中运行；这代表冻结有限样本上的性质检查，不等于对所有Python输入的形式化证明。
NaN/±Inf和tuple无法作为严格JSON原生值，因此以明确的`$float`/`$tuple`合成标签传输，在容器内部受控仪表层转换。公开输入只含函数调用、参数及调用者修改动作，不含预期值或评分规则。
CP04全部连续调用与修改动作在**同一个隔离Python进程**完成，未通过每次新建进程掩盖状态污染。

## 区分能力与原分保留

`results.json`原样保存执行输出及逐调用谓词：事实/异常、输入、保留状态、仪表结构。原26组分数是“该组探针连同共享门禁”的复合判定，因此计算错误可能连带使输入所在分组失败；不能把这个组分数直接解释成实际输入被修改。

为避免误归因，`cp_acceptance_finalize.py`对同一批原始观察追加独立诊断，原始分数不覆盖。六个诊断维度为：

1. RESULT_FACTS_CORRECT：有效输入的实际结果。
2. INVALID_INPUT_HANDLING：非法输入的预期ValueError及空结果。
3. INPUT_PRESERVED：真实调用输入前后精确一致。
4. RETURN_STATE_INDEPENDENT：相对于每次自身返回快照，仅施加规定的调用者编辑后，其他返回对象不发生非预期变化；不因数值错误就推断状态污染。
5. METAMORPHIC_RELATIONS_VALID：排列、重复、当前/未来值、末期信号及重复调用等关联观察。
6. OBSERVATION_SCHEMA_VALID：实际结果协议和仪表记录可核验。

这些是CP代码诊断，**不是修改原Workflow六维向量**。执行故障单独记录，诊断向量为null，不当作研究/代码事实全零。

| 错误对照 | 独立诊断失败项；其他项保留通过 |
|---|---|
| CP01 silently overwrite conflict | INVALID_INPUT_HANDLING |
| CP01 return input row aliases | INPUT_PRESERVED |
| CP02 include current value | RESULT_FACTS_CORRECT、METAMORPHIC_RELATIONS_VALID |
| CP02 reverse caller input | INPUT_PRESERVED |
| CP03 charge abs(position) instead of turnover | RESULT_FACTS_CORRECT |
| CP03 compound interval PnL | RESULT_FACTS_CORRECT |
| CP04 mutable default ledger | RESULT_FACTS_CORRECT、RETURN_STATE_INDEPENDENT、METAMORPHIC_RELATIONS_VALID |
| CP04 cache and share returned objects | RESULT_FACTS_CORRECT、RETURN_STATE_INDEPENDENT |

等价实现接受不同字典字段顺序、独立循环形式和math.fsum，避免用源码/措辞匹配判正确性。原合同、原参考模块、28题结果及所有历史freeze均未修改。

## 真实隔离与资源证据

镜像内容地址：`sha256:5175397ba18cc6c3b2e1a95c41b14da3c463e70c0d43b387c36c3dc78bee5142`，Python3.12.15/Linux amd64。
此前固定Worker包的25/25实际访问/资源检查直接引用其冻结证据，不重跑已完成的OOM、PID、网络和文件权限攻击探针。
本轮每个会话启动前再次检查实际Docker配置与两个只读文件挂载：UID/GID65532、network=none、只读根、cap-drop ALL、no-new-privileges、默认seccomp、512MiB内存/无额外swap、32 PIDs、0.5CPU、16MiB/tmp。
不挂载仓库、私有参考材料、Trace、凭据或Docker socket。评分完全在宿主受信进程进行，提交代码只在容器内加载，不在宿主exec/import。

5秒Worker执行上限、64KiB提交、256KiB合并输出接受/保存上限沿用；输出上限不是保证Worker产生的字节永远不超过256KiB。
本轮成功会话Docker StartedAt→FinishedAt为0.193—0.664秒；最大保留输出18,015字节。容器聚合CPU用量仍UNKNOWN，不能写成0；CPU配额通过先前实际cgroup探针及本次配置检查确认。

## 工程故障与预算处理

首个会话触发冻结旧执行器的退出/kill竞态：监督端达到附着deadline时调用kill，Docker返回“container is not running”，旧路径丢失了此前捕获缓冲及监督器用量。保留原失败、初版freeze、源码、任务及trace于`initial_failure/`，未伪造首次输出、退出码或费用。

新增版本化`cp_acceptance_executor.py`保留输出；仅在daemon确实报告已退出且再次inspect非运行状态时处理该竞态，其他权限/kill故障仍传播。实际Worker寿命和附着耗时分别记录；监督器异常也记录实际监督进程wall/CPU并停止批次。相关受控错误路径测试通过。
后续16个会话未再触发竞态，不把单元故障模拟说成第二次真实Docker竞态。

旧工程root仍为blocked，未知资源保留完整60,000ms wall/60,000ms supervisor CPU预留，**未调用reconcile伪造实测**。
因执行器变更，登记明确的新工程条件；新root上限为23次，已扣除首次失败，不能扩大总24次上限。变更及前驱账目记录在同一个TraceStore；Worker不能提供run_id或选择预算版本。这是作者控制的离线工程版本修复，不是让Agent用改名绕过未知usage门禁；不得套用于真实Workflow/API继续执行。
新条件实际16次、监督wall40,685ms、监督CPU1,244ms；连同前驱保守预留，总收费口径wall100,685ms、CPU61,244ms。二者均不是Worker聚合CPU。
自动重试0；另有一次明确版本修复后的工程重新执行，已包含在17次中。B1 `retries=0`表示没有同冻结版本的自动重试，不能据此宣称完全没有工程重跑。
B1要求的两个root各首次`model_trials=1`是沿用执行身份计数，不是LLM请求；真实模型调用由执行记录明确为0。scientific candidate/factor/parameter/hypothesis计数全为0。

工程pytest命令实际7次/上限10；最终定向回归 **110 passed，无skip**。覆盖新增执行/评分/回放测试、原CP引用及B1/B2预算/Trace；未运行历史QV7、Stage C2或真实比较。宿主pyreadline3进程退出析构仍打印既有WinError，pytest exit0；未归因为CP容器失败。

## 冻结及复现

- 执行freeze：`672b473101e5a9b09f5830fac2ee3b719e03b1c7d4681e995e5018eef0ece5b1`。
- 最终独立freeze：`d802f24c49e16d51e4f5cb8e2c31caf44c9695f0e2c3d704027e08807df8ab04`。
- 实际批次入口SHA：`344ca2306331895e7716004134d7e6280c3e9b19ed8f7a43bc6e28f58c6f78b2`。
- 最终追加trace：92事件，anchor `5230169ecfc88333138fc835aded64954e5a2a87e0c355941d2c607a85903cad`。

执行freeze绑定合同、Prompt、合成fixture、参考/错误/等价提交、执行器、原隔离freeze、必要B1/B2源码及测试；最终freeze绑定追加诊断和原始证据。收据保存完整文件SHA。全部16条执行观察、评分、输入/源码哈希、版本及两条件预算均可从保存字节重建核对。
收据/anchor目前由同一宿主作者保管，不能抵御拥有宿主文件权限者连同收据全部重写，不声明独立外部托管。

```powershell
$env:PYTHONPATH='src'
python -B -m quant_rsi.harness.cp_acceptance replay
python -B -m quant_rsi.harness.cp_acceptance_finalize replay
```

原run入口遇到已有结果直接拒绝，不能以重放为名重新执行容器。定向测试中的实际字节篡改反例覆盖观察、评分、版本、预算和trace；无需重新执行工具。

## 状态和下一步

28题已有离线验收，加本轮4题，新增32题现在均具备受控合成离线工程验收。原CP准备文件继续保持当时状态，新的独立包记录晋级证据；不把旧freeze就地重写。
原24题加新增32题为56道题；这不表示56题已经做过真实模型评测，也不表示跨不同任务模式可合成一个总分。

本机Docker/WSL2这一CP运行前置条件已经解除。D05的独立Custodian提交/评分通道及此前未完成的10项专门安全测试未在本轮恢复，不自动登记D05 PASS_OFFLINE_ISOLATION_ENGINEERING，更不授予D05_FULL_SEALED_QUALIFIED。D08作者、身份及结果独立性仍未验收；访问隔离不解决同一作者编题/Oracle/评分的独立性。

下一步建议先按下面范围做本地Git commit。之后择一另行授权：恢复最小D05托管验收，或冻结真实CP代码生成入口与调用预算。真实CP接入仅需Provider输出→公开代码提交协议→固定Worker→外部判分；需明确模型ID、Prompt/源码提取、每题次数、token/货币上限、usage/失败留证及凭据状态。真实Agent/Judge接入仍须单独授权，本轮不启动。

本轮待提交范围：`benchmark/capability_cp_v01/`、四个`cp_acceptance*.py`模块、`tests/test_cp_acceptance.py`、`tests/test_cp_acceptance_finalize.py`。
前一轮Worker包及`cp_isolation.py`、`cp_boundary_probes.py`、`test_cp_isolation.py`仍未跟踪，是本包冻结依赖；建议一并按明确路径提交，或先分别提交Worker准备。不要使用git add -A；不纳入其他public_contract/comparison未跟踪工作。
SQLite和synthetic_work已gitignore；旧镜像tar仍排除。建议提交信息：`feat(benchmark): accept four CP tasks in pinned Docker isolation`。

完成后停止；未启动真实模型、Judge、数据API、24题比较、D05恢复、Hidden、策略搜索或实盘。
