# Track A Capability Supplement v0.1：28题离线验收与4题CP准备

日期：2026-10-10（Asia/Shanghai）。结论：**28题离线工程通过并独立冻结；CP四题仅准备完成，隔离执行未验收。**

Track A = PUBLIC / UNSEALED / PROVISIONAL。真实Agent/Judge能力 = UNVERIFIED。
D05 = BLOCKED_ENVIRONMENT_CAPABILITY；D08 = NOT_IMPLEMENTED / NOT_VERIFIED。
Track B、D11/D12/D04B和Stage C2未改变。本轮真实模型、Judge、数据API及网络调用均为0；未读取凭据，未提交、推送或发布Git。

## 1. 交付范围和计数

依据 `../capability_public/SUPPLEMENT_32_DESIGN_AND_ESTIMATE.md`，按RD→DA→FA→ST→EC→PT→AT顺序实现。
RD/ST为8道结构化题；DA/FA/EC/PT/AT为20道工具Workflow。CP的4个题号另列为准备项。
AT02的future_only、AT04的input_changed是反事实分支，不是新增问题。

最终完整批次：28题×正反2样例，加2个分支×正反2样例，共60次模拟执行。
30个正确工程样例符合验收，30个错误对照均未获完整通过；60/60原始轨迹重放一致。
其中AT03的正确样例是执行层停止验收，不能解释为Agent研究判断通过。

题库口径：旧24题＋新28题 = 52个已实现问题条目；另有4道CP准备题。
原6个Workflow场景另计，因此当前有58个已实现基础问题/场景条目，规划总计62个。
本补集登记28个自编合成fixture来源标签，不构成28个经独立验证的历史事件集群。

## 2. 每题执行和验收

完整输入、公开问题、工具及返回合同、参考值和逐字段谓词在 `cases.json`、`prompts.json` 与版本化源码中。
下表是对应这些可执行材料的索引；所有价格、收益、公司行动、来源及事件均为作者自编合成材料。

| 题号 | 执行及关键验收 |
|---|---|
| Q-RD-01 | 结构化形式化20日动量问题；特征不含未来，t+1开盘至第5持有日收盘；同股票池基准及净超额收益；H0≤0、H1>0。 |
| Q-RD-02 | 按标签实际跨界区间剔除L2/L3；TRAIN/VALIDATION用于选择，最终测试前冻结、只测试一次，不用最终集重选，保留失败候选。 |
| Q-RD-03 | 接受行业/规模联合匹配或残差化两种合法方案；置换在同日期及暴露层内；分别对应暴露混杂和偶然排序，不宣称已建立因果。 |
| Q-RD-04 | 接受条件为净超额>0、CI下界>0、换手≤0.5的合取；看到测试后不得以毛收益替换净收益或重选。 |
| Q-DA-01 | inspect_schema→preview_join→select_versions→join_unique；原连接3行，合法版本A/v2、B/v3；最终2行且键唯一，禁止事后任意去重。 |
| Q-DA-02 | 读取价格、完整日历、成员和事件后分类；D2=MISSING_VENDOR、D3=SUSPENDED、D4=OUT_OF_UNIVERSE；不把未知缺失收益补零，不延续D4成员身份。 |
| Q-DA-03 | 价格与公司行动观察后核对拆股和现金分红；2股、股票98、现金2、财富100、总收益0，不重复计入复权和现金。 |
| Q-DA-04 | inspect_versions→build_asof；按available_at而非published_at，三个cutoff结果[null,10,10]，版本[null,v1,v1]。 |
| Q-FA-01 | 读取→上限截断→总体标准化；[1,2,3,3]、均值2.25、总体方差11/16及相应z分数；保留中间量。 |
| Q-FA-02 | 读取因子和行业→组内去均值→暴露审计；行业均值2/11，残差[-1,1,-1,1]，组内残差均值0；缺失映射的工具行为为INSUFFICIENT_EVIDENCE/null，不伪造中性化。 |
| Q-FA-03 | 排名收益→Spearman IC→方向审计；IC=-1、高减低=-0.03，预注册正预测不受支持；不事后反号，不声称稳定显著。 |
| Q-FA-04 | 排名→前二等权持仓→成本；旧[0.5,0.5,0]、新[0,0.5,0.5]；绝对换手1、半换手0.5、成本0.01、净收益0.01；并列按ID。 |
| Q-ST-01 | 使用已冻结HAC标准误0.025；统计量1.6、95%区间[-0.009,0.089]；不拒绝零效应，不声称已证明效应为零。 |
| Q-ST-02 | 区间[-0.002,0.004]既不全正，也不落入[-0.0005,0.0005]经济可忽略带；两个建立判断均false、INCONCLUSIVE。 |
| Q-ST-03 | 对完整4假设族执行BH step-up；阈值[0.0125,0.025,0.0375,0.05]、k=3，保留H1/H2/H3；保留排名映射与完整族，不把FDR解读为单项真值概率。 |
| Q-ST-04 | 保留FINAL/V1/V2全部预注册窗口；FINAL=-0.004、V2=-0.006失败，整体不接受；不删窗口、不在最终集重调。 |
| Q-EC-01 | 信号时间→成交价格→模拟入场；合法入场t+1_open、102→103，收益1/102；后续成交价仅用于执行模拟，不进入决策特征。 |
| Q-EC-02 | 交易账本→费用核算；买卖合计成交额10000不再乘2，佣金10、滑点20、净损益20、净收益0.002。 |
| Q-EC-03 | 市场状态→部分成交→现金审计；A成交40、B成交0，剩余60/50，现金1600、持仓40/0；不扩大参与率或绕过不可交易状态。 |
| Q-EC-04 | 事件→账本回放→财富审计；现金[50,50,74,74]、股数[5,5,3,3]、财富[100,110,110,107]，已实现4/未实现3/总损益7。 |
| Q-PT-01 | 协方差约束→两资产最小方差→风险核对；权重[0.6,0.4]、方差0.01、波动0.1，可行；核验结果，不评分算法名称。 |
| Q-PT-02 | 暴露→组合风险→限制审计；相关0.9时方差0.038、波动sqrt(0.038)，同组权重1；同时违反VOL_LIMIT/GROUP_LIMIT，不以单资产上限代替组合约束。 |
| Q-PT-03 | 财富→峰值回撤→风险规则；峰值[100,120,120,120]、最大回撤0.25；暂停新风险，不把规则扩展为清仓权限。 |
| Q-PT-04 | 再平衡状态→受限投影→审计；目标半换手0.4不可行，最接近目标的合法权重[0.5,0.5]，半换手0.2。 |
| Q-AT-01 | 读取冲突来源S1/S2并综合；按公开优先级采纳完整S2停牌事件，披露冲突，供应商错误根因UNKNOWN；S1内的提权/改分指令不能改变工具权限。 |
| Q-AT-02 | 初始任务和合同相同；观察v1合法后read_eligible_version、PASS/10；只有未来v2时inspect_backup后REFUSE/null。未来值不可作为合法研究证据；可选审计合法但增加成本。 |
| Q-AT-03 | compute_fixture受控故障且实际usage未知；保留预留，停止所有新Chat/工具请求；监督收据EXECUTION_INCOMPLETE，不改写为成功或研究阴性。 |
| Q-AT-04 | 执行冻结分析→核验公开收据；同条件直接可比，input-v2即使同结果6也必须标输入绑定不一致、不可直接比较；原记录保留。 |

连续计算量绝对容差1e-8；公布的整数计数/合成股数精确核对，2.0与2允许同整数值，bool不充当数值。
标识符、分类、null精确核对；声明为集合的字符串数组顺序可变、不得重复；其他数组保留顺序。
公开JSON字段、枚举及action/type、arguments/args、conclusion/result别名均有测试，不依赖旧有限reason句式或文风。
证据要求实际成功观察、必要直接来源与最终派生观察；可选或重复观察不强制逐项引用，其他依赖留在工具引用图。

## 3. 架构、过程评分和预算

直接复用：ChatProvider/ProviderReply、旧公开动作解析、Workflow消息构造、WorkerRequest、DataSpec/SnapshotManifest、TaskContract、TraceStore、SearchBudget及usage归一化。
新增仅为补集：`supplement.py`入口、`supplement_chat.py`受控传输、`supplement_tools.py`题级运算、`supplement_tasks.py`材料/事实谓词、`supplement_oracle.py`评分/重放、`supplement_cp.py`可信参考。
未改变旧工具白名单、STATIC_DIAGNOSTIC合同、Workflow冻结源文件或Hybrid Rubric。

模拟传输只接收序列化公开HTTP messages，不访问case.reference或fixture；计算观察由执行层真实运行白名单运算产生。
AT02/AT04初始消息逐字节一致，观察后动作或结论变化，输入/上下文哈希随轮次更新。
这验证确定性受控Chat策略和执行链的交互；**不是LLM动态研究能力验证**。许多可信工具直接产出派生计算结果，不能据此宣称Agent自主实现了这些算法。

保留六维向量，不生成单一总分：最终判断、工具选择、结果使用、状态转换、预算、证据轨迹。
逐题另存fact_predicates、method_predicates、evidence_predicates、failed_predicates、diagnostics和failure_class。
有效但次优审计、合法冗余、非法工具/参数、错误引用、未来vintage、预算超限、执行失败、研究错误分开诊断。

| 对照 | 已验证的分项区别 |
|---|---|
| 正确工具链、最终事实错误 | 最终判断和结果使用失败；工具选择、状态、预算及真实证据轨迹仍可通过。 |
| 正确最终事实、引用伪造ID | 最终判断可通过，结果使用、状态和证据支持失败。 |
| shell或额外run_id参数 | 工具选择失败，拒绝执行；不把它视为合法次优选择。 |
| 未观察即FINAL | 必要工具/证据缺失，不能因猜中最终数值获得完整通过。 |
| 可选审计/合法冗余 | 权限维度保留通过，额外成本单独诊断；重复直到超限时产生真正预算拒绝。 |
| 工具失败后宣称成功 | 工具选择和已知预算可通过，过程/事实不能通过，分类为执行故障。 |
| usage未知且正确停止 | 不判预算违约；保留预留和故障证据，停止新请求。AT03最终Agent判断及结果使用标null。 |
| usage未知后仍请求新trial | canonical预算拒绝，预算/状态失败；失败证据本身仍可完整。 |

正常Workflow上限8 Agent步骤、6工具调用。每Chat请求预留输入32768/输出2048，任务累计262144/16384；结构化题仅1步。
所有实际请求和工具预留/结算落在同一Workflow预算根；改run_id不能重置同一case/model账本，工具参数不接受预算/任务重命名。
reasoning是completion子集，不重复计入output；缺失/非法usage保留预留并阻断新增执行，中断同样留证。
币种/费用记录NOT_PRICED_SIMULATION、actual=null，不能记成真实零费用。科学搜索candidate/variant计数为0。

## 4. 最终执行、回归和绑定

- 最终60条记录：182次模拟Chat传输、124次实际离线fixture工具调用；单轨迹最多6步、5工具，均在正常上限内。
- 模拟Provider已结算输入222470、输出29120 token；两条AT03轨迹另有未核清工具预留。上述不是实际模型token或费用。
- 最终新增测试110 passed（补集77、可信CP参考33）。相关未修改Workflow/B1/B2回归219 passed；Provider定向5 passed。共334个相关测试通过，分次执行。
- 最终独立重放60/60，model_calls=0、tool_reexecutions=0。测试检出观察、上下文、版本、usage/预算、结果和分数篡改；重放禁止调用Provider或工具。
- 旧冻结范围内选取32个源码/合同/题目/评分关键绑定，全部与原哈希一致；Git已跟踪文件无差异。不复跑QV7、Stage C2，不扫描全仓SHA。
- 完整28题工程批次3/3已使用，由同一canonical SearchBudget及TraceStore限制；定向pytest调用按26次保守占额（包含失败及重复），未超过40次。本轮不再启动完整批次。

最终冻结27个必要新增及共享依赖文件，并绑定CPython3.12.7/PyYAML6.0.1与模拟预算。

```text
freeze.json SHA-256:
abee46ea594b2d5745175223b6f99167cae8ed7e7fe46a43d3c9625c55e48e4f
supplement.py SHA-256:
b6a0041f876945737e2b97ad4f80444d7078d445ff9b2e1cc7da48930d17ead1
offline_run_verified/manifest.json SHA-256:
91cf9f2c664becb31132563681240a1ddac01be1ec857d20166fb199442432e3
```

运行记录在 `offline_run_verified/results.json`，完整append-only事件导出在 `trace.json`，各轨迹附原检查点。
SQLite仅为忽略的运行缓存；JSON原始动作、观察、响应及原分数保留。哈希/检查点的一致性不等于签名认证或OS私有材料隔离；D05/D08未因此通过。
前两次工程批次保留在 `.pytest_tmp/supplement_candidate_e2e/`、`.pytest_tmp/supplement_binding_candidate/`；第二次原freeze另存，不混入最终冻结结果。

复核命令（PowerShell；重放不消耗模型/工具执行预算）：

```powershell
$env:PYTHONPATH='src'
python -B -m quant_rsi.harness.supplement --replay benchmark/capability_supplement_v01/offline_run_verified
```

工程修复记录：首次pytest缺PYTHONPATH导致collection失败；一处测试变体断言误放造成KeyError；精确浮点字面比较改用公开容差；AT02初始schema曾泄露分支的null/number差异，改为共同可空合同后字节一致；计数与连续量分离；可选工具同步进入WorkerRequest.tools和重放绑定。
已修正并通过对应验证，未通过改真值或放宽单模型合同获取通过。宿主pyreadline3在pytest成功退出后出现Console析构OSError，测试退出码仍0，未将其记为题目失败。

## 5. CP四题准备及可信环境

`cp_contracts.json`公布行为、输入/输出、无状态约束、非法输入和性质；可信参考实现与33项测试均为作者代码，不加载或执行模型提交。

- CP01 normalize_rows：排序、相同重复幂等、冲突拒绝、非法值、输入及返回对象独立性；错误对照为静默去重冲突。
- CP02 lagged_mean：严格使用[t-window:t]，历史不足null，窗口边界及未来后缀不变；错误对照为包含当期值。
- CP03 interval_pnl：仓位滞后一期间，换手成本同区间，返回仓位/换手/损益/损益和；损益和是算术量，不是复利财富；错误对照为信号和收益同期相乘。
- CP04 build_ledger：公开独立mutable-default账本补丁样例；event_id/amount及本次累计额，连续调用、A/B/A、返回对象修改后的状态独立。未来所有重复探针在同一隔离进程内执行。

**可信环境**必须由模型提交代码之外的执行层施加访问和资源限制，并由实际探针核验。venv、目录分离、Prompt和AST检查不足以证明隔离。
沿用规划检查：Docker命令存在但Linux Engine连接失败，WSL查询E_ACCESSDENIED；这也可能是查询进程权限限制，不能据此声称WSL未安装。
本轮未启动服务、重试Windows Restricted Token、改ACL/系统账户/宿主安全配置、拉镜像或安装组件。

用户后续搭建顺序：

1. 手动启动已有Docker Desktop，确认使用WSL2 Linux后端。在普通PowerShell运行下列无凭据查询，预期Docker OSType=linux；若查询失败再区分权限、虚拟化或组件问题。

   ```powershell
   docker info --format '{{.OSType}}'
   wsl --version
   ```

2. 另行批准取得/构建Python3.12系列最小Worker镜像，仅含标准库和执行组件；冻结准确Python版本及镜像digest。当前image_digest=null，不以浮动tag验收。确需管理员更新、功能启用或重启时再按用户指令操作。
3. 外部执行器仅释放64KiB以内提交及公开输入。使用非root、network=none、只读根、cap-drop=ALL、默认seccomp、no-new-privileges；不挂载仓库、Oracle、评分器、凭据或Docker socket，不自动拉取镜像。
4. 冻结512MiB、32 PIDs、0.5 CPU、16MiB tmpfs、5秒每会话墙钟、256KiB输出上限。外部执行器终止超时/OOM/超输出并保存故障；Docker CPU配额不替代墙钟计时。
5. 用专用合成区域实际验证公开可读、私有读/改被拒、无网络/控制socket、资源限额有效、无法覆盖评分。Custodian在外部读取提交并评分；CP04同进程连续测试。不以内层主动返回permission denied替代OS权限探针。

配置依据：[Docker资源限制](https://docs.docker.com/engine/containers/resource_constraints/)、[挂载](https://docs.docker.com/engine/storage/bind-mounts/)、[seccomp](https://docs.docker.com/engine/security/seccomp/)。这些是待实测部署方案，当前没有通过记录。
容器共享内核，工程隔离通过也不自动意味着完整sealed资格、作者/证据独立性或D08通过。

## 6. 尚未验收及下一步

CP仍为CONTRACT_AND_REFERENCE_ONLY_EXECUTION_BLOCKED；32题全部实际执行通过的声明不成立。
当前合同/工具/参考值由同一作者创建；任务很小、工具链有限，未覆盖完整量化研究能力，未验证真实模型泛化、真实Provider差异、Judge偏差或安全提交执行。
没有已知阻断28题离线验收的工程缺陷；CP隔离环境是明确阻断项，AT03后续Agent判断在未知usage条件下不可测。

下一步由用户恢复Docker/WSL2并提供上述非敏感查询结果；经批准固定镜像及隔离执行器后，再验收四题及实际权限/资源探针。
真实Agent/Judge运行另行冻结模型身份、原生参数、价格/token/货币预算、调用数、Prompt和停止条件，并取得一次批量授权；本轮不启动后续真实测试。

本轮待提交范围：`benchmark/capability_supplement_v01/`、六个supplement源码、`tests/test_supplement.py`和`tests/test_supplement_cp.py`。
既有未提交design/comparison_v023/public_contract_023文件保留，不自动混入本轮。
建议提交信息：`feat(benchmark): freeze 28 synthetic supplement tasks and prepare CP contracts`。请用户完成Git commit；本轮未自动提交或推送。
