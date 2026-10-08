# Quant RSI HARNESS

独立量化研究 Agent Harness。目标是固定任务、数据、环境、Eval 和搜索预算下的可信研究产出，不是最大历史回测收益。

## 当前 Stage C2 入口（2026-10-08）

pandas UTC来源收口本轮完成离线取证，入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/pandas_222_utc_source_closure_01/PANDAS_222_SOURCE_PROVENANCE.md`。用户转述官方v2.2.2模块初始化gettz("UTC")摘录，官方timezones.pyx原始字节未取得，已提交独立1次固定raw源码获取预算（search0/retry0），尚未批准或使用。本机冻结.pyd SHA未变，安装元数据支持Anaconda defaults py312h0158946_0构建渠道；发现RECORD所登记模块SHA/212480字节与实际冻结SHA/224536字节不同，原因UNKNOWN，不断言篡改或合法修补，缺少缓存发行包与路径级处理记录。UTC回退合同为候选，完整24项预算为不可启动草案，未编制入口/Diff，未要求不现实的完整编译复现。40项离线完整性检查通过、14组保护根前后指纹一致；原始安装元数据、哈希差异及dateutil固定资源纳入22成员审计包。网络/API/导入预跑/诊断/suite/真实凭据/native Registry/正式验证及Critic均0。资格仍NOT_PASS，Stage C2/D11/D12/D04B和Full Census/执行状态不变；不生成真实V02，停止等待源码获取授权与来源审计。旧现场、V3 UNKNOWN、HTTP风险及12+3偏差保留。以下为历史轮次记录。

时区依赖收口本轮仅静态分析，入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/timezone_dependency_resolution_01/TIMEZONE_DEPENDENCY_RESOLUTION.md`。冻结源码确认Gettz对WindowsError/OSError的Missing-Key回退存在，已核对并留存随包2024a zoneinfo原文字节，UTC32/64位TZif候选为固定零偏移无DST。但QV6未采集实际时区请求名，pandas编译扩展对应timezones.pyx缺失，无法证明原请求必落在固定资源支持域、避开host-local或None分支。按任务停止条件未正式选择A/B、未生成新入口/Diff，完整24项预算仅为不可启动条件草案，源SHA为空。48项静态证据检查通过，13组历史/生产保护根前后指纹一致；网络/API/测试/预跑/凭据/native Registry/正式验证及Critic均0。资格仍NOT_PASS，Stage C2=BLOCKED_INCOMPLETE，D11/D12/D04B=NOT_READY，Full Census query_ready=false，execution_authorized=false；不生成真实V02请求。等待人工审计与原始调用/编译来源材料，旧QV6额度保持已耗尽，V3历史UNKNOWN、HTTP风险及12+3预算偏差不变。以下为历史轮次记录。

QV6定向诊断已在用户明确更正Schema绑定后执行一次，入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/qv6_registry_call_diag_preparation_01/execution_evidence_01/QV6_DIAGNOSTIC_REPORT.md`。79项启动前静态检查通过，可信控制独占创建START，原额度1/1已消耗、retry=0。唯一bridge_normal实际1项失败，退出码1；新增脱敏证据直接定位第二次ConnectRegistry为dateutil.tz.win.tzwin.__init__:218，上游GettzFunc.nocache:1648与GettzFunc.__call__:1557。本机与HKLM谓词成立，原_settzkeyname身份和line35谓词不成立，diag对应原blocked事件seq=5。第一轮四步人工句柄周期完成；人工transport为0，生产Registry策略未变。后续OpenKey/QueryInfoKey/EnumValue/TZI及句柄依赖仅静态审查，未自行放行。11组旧现场、3545文件及生产依赖哈希不变，新81文件人工现场完整保留；旧授权错误及更正收据分开保留。诊断审计ZIP含实际结果、原始脱敏事件、冻结输入和依赖；安装的Python/编译模块与历史现场按外部哈希引用，不宣称完整便携运行闭包。完整24项资格仍NOT_PASS，不生成真实V02请求；V3历史根因UNKNOWN，旧12+3预算偏差不追认，HTTP风险仍ACCEPTANCE_REQUIRED。Stage C2=BLOCKED_INCOMPLETE，D11/D12/D04B=NOT_READY，Full Census query_ready=false，execution_authorized=false。已停止等待独立审计；以下静态准备段落是历史快照。

QV6第二次Registry调用调查仅完成静态准备，入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/qv6_registry_call_diag_preparation_01/SECOND_CONNECT_STATIC_CALL_GRAPH.md`。新入口仅bridge_normal，SHA-256为 `0dfe17c4be203b29d78dba5ac637e524e0d30a658ac85fc1a80e2c6dced0b24f`，新根.cal05_qv6_diag_work未创建。只在原timezone_connect拒绝判断之后、原deny_registry之前追加脱敏caller、四项布尔谓词、失败谓词与最多4层帧；原短路表达式、允许分支及所有其他Registry守卫AST未改，网络/凭据/文件系统约束保留。74项静态核查通过，107条路径最长205字符；原65文件ZIP、15依赖、9份留存可读源码、编译模块SHA及11组历史指纹一致。静态候选为_settzkeyname/list/tzwin初始化/tzwinlocal初始化；pandas本机编译扩展缺少Cython实现，二次调用来源仍UNKNOWN，未虚构历史caller。静态审计ZIP实际包含入口、Diff、Schema、检查记录、预算及源码证据，外部运行依赖按SHA说明，不宣称运行闭包完整。动态诊断/suite/import预跑、网络/API/真实凭据/native Registry、正式验证/Storage Gate/Critic均0；预算只是未授权草案，运行时资格NOT_PASS，未生成真实V02请求。原V3/V4/V5现场、Oracle及生产文件不变；停止等待独立审计和新的单次诊断授权，HTTP风险、旧预算偏差与Stage C2/Full Census状态不变。

QV5获独立用户授权后，由可信控制创建绑定START，仅启动完整计划套件一次；执行入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/bridge_qualification_v5_01/execution_evidence_01/QV5_EXECUTION_REPORT.md`。实际19/24项尝试、18通过、1失败、5未执行，退出1并停止，额度1/1消耗，无修复重跑。第19项bridge_normal的四步人工Registry存在性探针完成并关闭句柄，随后另一笔CONNECT_REGISTRY被拒绝；Bridge记录CREDENTIAL_SETUP/RuntimeError，人工transport实例1个、请求0次，具体caller/参数/拒绝条件缺少记录而保持UNKNOWN。第20—24项未执行，Registry和网络安全专项未取得通过证据，运行时资格NOT_PASS，不生成真实V02请求。人工Trusted Launch/Storage Gate/PID绑定一致，PILOT_TRACE缺失已记录；交付脚本的可选trace假定失败也保留，不构成Suite重试。源码/15项依赖/原ZIP及九组历史指纹无变化，V3历史根因仍UNKNOWN，V3/V4/V5现场保留；真实网络/API/凭据/native Registry、正式验证/Storage Gate/Critic和额外预跑均0。审计ZIP仅打包本次外层记录、冻结源码/合同和关键人工fixture元数据，其余依赖与全部fixture按SHA在原仓库引用，不宣称整仓库可由ZIP独立重跑。Stage C2/D11/D12/D04B及Full Census/执行状态不变，HTTP风险与旧预算偏差继续开放；停止等待独立审计。下段为静态准备历史快照。

QV5最小Registry兼容修订已完成静态准备，入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/bridge_qualification_v5_01/QV5_MINIMAL_FIX_DESIGN.md`。独立入口SHA-256为 `36bfa8d9b638cf5177fa404837026b9efa43ecc9d326175f9ab435102276335b`，run_id=C2_02P_CAL05_QV5_R01，工作根.cal05_qv5_work尚未建立。只为冻结dateutil原_settzkeyname的精确本地HKLM/NT Time Zones只读存在性探针提供人工Registry句柄，不调用真实注册表；原生winreg操作及其他路径/值读取/写入继续拒绝，允许和拒绝事件分开记账。原24项名称/顺序、前23项科学断言和原网络断言未改，第24项新增Registry安全断言但未运行。72项静态核查、2406条路径矩阵通过，最长217字符；65文件ZIP、15项依赖、5份第三方源码及9组历史指纹一致。生产文件、Oracle和旧V3/V4现场未改，V3历史根因仍UNKNOWN。本轮动态suite/诊断/import预跑、真实网络/API/凭据、正式validation/storage gate/Critic均0，仅提出未授权一次24项suite预算；未生成真实V02请求或授权。停止等待人工静态审计与独立测试批准，HTTP风险、历史预算偏差和Stage C2/Full Census状态不变。

QV4定向诊断已在独立用户授权下通过绑定启动器执行一次并停止，结果入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/qv4_targeted_diag_preparation_01/execution_evidence_01/TARGETED_DIAG_REPORT.md` 和 `TARGETED_DIAG_EXECUTION_CHECKPOINT.yaml`。实际1项尝试、0通过、1失败、退出1，额度1/1消耗且无重跑。6个有序事件直接证明人工凭据回调正常返回后，Provider模块导入中的dateutil.tz.win._settzkeyname调用winreg.OpenKey被注册表守卫阻断；Provider构造未进入，人工transport为0。人工Trusted Launch和同进程Storage Gate通过，PID绑定一致；这些不属于正式验证或真实数据验收。旧V3历史根因仍UNKNOWN，22份记录及1583份工作文件/目录清单未变，生产源码未改。完整24项资格仍未通过，未生成V02真实执行请求或授权；真实网络/API/凭据读取、正式validator/storage gate/Critic和额外动态预跑均0。HTTP风险与历史预算偏差继续开放，Stage C2/D11/D12/D04B和Full Census/执行状态不变；等待人工审计。下段为原静态准备时间点记录。

本轮 `C2-02P-CAL05-QV4-TARGETED-DIAG-PREP` 静态交付入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/qv4_targeted_diag_preparation_01/TARGETED_DIAG_DESIGN.md`。仅编制第19项bridge_normal的独立诊断入口、启动程序、精确源码Diff和脱敏有序事件Schema；复用原65文件ZIP及15项冻结依赖，不替换Provider或加载器，不改变科学断言和隔离守卫。70项静态检查通过，目标路径最长205字符；入口SHA-256为 `f4146133a8eacbcb926618ec5a3fbf04240676c6011756ab695950fb1faf608b`。已留存5份当前第三方源码及版本/哈希；候选注册表冲突仍未动态证实，根因UNKNOWN。旧V3的22份记录及1583份工作文件和目录清单未变，生产源码未改，诊断工作根及授权/启动/结果均未创建。动态诊断、suite、网络/API、正式validation/storage gate和Critic均0；未取得完整24项运行时资格，不生成V02真实执行请求。下一步仅为独立人工审阅和另行批准一次精准诊断；HTTP风险、12次搜索/3次获取的历史预算偏差、Stage C2和Full Census/执行状态继续保留。

本轮 `C2-02P-CAL05-BRIDGE-NORMAL-DIAG` 只读诊断入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/bridge_normal_diagnostic_01/BRIDGE_NORMAL_FAILURE_DIAGNOSIS.md`。第19项人工Bridge记录RuntimeError、CREDENTIAL_SETUP停止、transport=0；Trusted Launch和人工Storage Gate有PASS收据，Runtime Evidence已落盘。Provider首次pandas/dateutil加载与全局注册表阻断存在静态冲突候选，但旧日志缺少子阶段与栈，根因保持UNKNOWN。仅交付报告、未批准V4预算草案和Checkpoint，未生成可运行入口、未修改生产源码或执行新测试；V3的22份记录及旧工作目录1583份文件和目录清单未变。拟定V4根路径静态最大217字符，需先审阅诊断和后续入口设计；本轮suite/API/正式validation/storage gate/Critic均0，HTTP风险及历史预算偏差保留，Stage C2/Full Census/执行状态不变。

CAL_05 V3最新批准已单独登记在 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/bridge_qualification_v3_01/reapproval_static_gate_01/AUTHORIZATION_AND_PRELAUNCH_CHECKPOINT.yaml`，当前为 `BLOCKED_PRELAUNCH_WORK_ROOT_NOT_FRESH`。源码及15项冻结依赖哈希一致，但短工作目录、启动标记和结果已存在，不能满足本次批准的fresh-root条件。此前获批V3套件已实际执行一次，19/24项尝试、18项通过，第19项bridge_normal在人工CREDENTIAL_SETUP阶段停止、transport=0、退出1，余5项未执行；未修复或重跑，旧现场保留。最新新增额度未消耗，本次登记suite/API/正式validation/storage gate/Critic均0；不生成V02真实执行请求或授权，HTTP风险和历史预算偏差保持开放。下方V3静态准备段落为此前时间点记录。

本轮 `C2-02P-CAL05-BRIDGE-QUALIFICATION-V3` 静态修订入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/bridge_qualification_v3_01/`。新入口使用项目内专用短路径 `.cal05_qv3_work`，原65文件ZIP、15项附加依赖及24项科学用例保留；新增脱敏fixture诊断及落盘哈希核对。49项静态检查通过，65成员/15依赖/20输出对24项用例计算的最长目标路径217字符；未建立工作根、未解包、未import预跑或启动套件。451份历史Pilot文件和生产源码保持原字节，V2失败根因仍UNKNOWN；需另行明确批准一次新离线套件，当前suite/API/正式validation/storage gate/Critic均0。HTTP风险、旧网络预算偏差、Stage C2及Full Census/真实执行状态不变。

本轮 `C2-02P-CAL05-BRIDGE-QUALIFICATION-V2` 获用户直接消息授权后，只启动一次离线套件；执行证据入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/bridge_qualification_v2_01/execution_evidence_01/`。107项启动前静态检查通过，入口哈希与原24项顺序一致。实际1/24项尝试、0项通过：首项pre_missing_authorization在隔离fixture准备阶段FileNotFoundError，退出1并停止，未修复或重跑；第24项网络阻断/PySocks专项未执行。保留24个已解包文件，首个缺失目标路径长278字符，路径长度仅为待审阅候选解释，根因UNKNOWN。人工transport、真实API、凭据读取、正式validation、生产存储gate、Critic均0，411个既有Pilot文件保持原字节。未生成V02真实执行预算请求或真实授权；HTTP凭据风险与12次搜索/3次获取的旧预算偏差继续开放。旧静态等待快照及0/24初始化失败记录保留，Stage C2及Full Census/执行状态不变。

本轮 `C2-02P-CAL05-REAL-LAUNCH-BRIDGE` 入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/real_launch_bridge_01/`。独立 Bridge 与 validator v2 已编制，原 provider/执行器/Oracle/历史字节未改；endpoint 与 Tushare 1.4.24 留存源码兼容性 PASS，HTTP 凭据风险仍待人类明确接受。唯一获批离线资格套件在 requests/PySocks 导入阶段 TypeError 退出1，实际0/24用例；未重跑，未运行 Bridge 或正式 validator，未生成 V02 真实执行预算请求。需另行授权独立入口修正和新一次离线资格测试。Stage C2/D11/D12/D04B、Full Census和真实执行授权状态不变，真实 API/凭据/存储 gate/Critic 均0。

本轮 `C2-02P-CAL05-EXEC-PREP` 入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/exec_preparation_01/`。真实人工收据已逐字节保留，七行写入独立 Frozen Oracle；两份新 validator 仅完成静态编制，未调用或测试。发现已审计执行器只启用 `run_synthetic`、真实 CLI 禁用，故当前真实执行仍阻塞；18/18 历史合成测试不证明真实启动就绪。一次 API/七行及 pre/post 各一次、内部 gate 一次、Raw/Derived 各2 MiB仅为未批准草案，需先另行授权真实启动桥接准备和审计。此前12次搜索/3次来源获取正式记为未追认治理偏差，科学证据保留。Stage C2、D11/D12/D04B、Full Census和执行授权状态不变；本轮网络/API/测试/Validator/存储探针/Critic均0。

CAL_05 当前 Oracle 冻结记录为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/oracle_human_freeze_01/CAL05_HUMAN_ORACLE_FREEZE_RECEIPT.yaml`。用户于2026-10-01明确声明完成人工独立审阅，接受2023-04-10实际上市与12.8共同构成施行依据，并冻结既定七行Oracle；状态 `ORACLE_FROZEN_BY_EXPLICIT_HUMAN_CONFIRMATION`。该确认仅限Oracle，未授予API、Validator、受限数据存储、Full Census、Critic或后续执行权限。原施行补证仍在implementation_evidence_01，12次搜索/3次页面的数值预算登记偏差尚待人工审计，不由本确认追认。Stage C2、D11/D12/D04B及Full Census/执行状态不变；本次登记网络/API/测试/Validator/Critic均0。

`C2-02P-CAL05-CLOSEOUT` 本轮授权执行入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/closeout_execution_01/`。4次固定来源操作完成：3份原始HTML成功、2023规则DOCX超时未取得；无搜索、替代或重试。新版离线套件一次执行18项全部通过（退出0），生产源码未变，真实API/正式validator/Critic为0；旧10106根因仍UNKNOWN。用户选择人工独立合同审阅，尚无冻结收据；交易日条款仍缺原文，CAL_05继续NOT_READY，未生成新的真实API合同/预算。Full Census及执行状态不变，当前停止等待审计。

此前 `C2-02P-CAL05-CLOSEOUT` 的离线准备记录保留在 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/closeout_01/`。当时仅静态准备新测试入口及diff，网络、单次测试尚未批准，规则URL待提供，未检索或测试；203个历史Pilot文件未改。该阶段Checkpoint及ZIP保持原样；本轮新增测试运行证据附加在engineering目录，生产源码未修改。WinError 10106根因继续UNKNOWN。

`C2-02P-CAL05-PREP` 获授权的下一阶段已执行并停止，入口为 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/authorized_preparation_01/`。四份指定官方 HTML 原文已留存，页面操作 4/8、搜索 0；七行候选仍缺4月29/30开市边界证据及独立合同审阅。适配器、工程执行器与合成测试程序已编制，真实CLI关闭；唯一离线测试进程在导入 `unittest.mock → asyncio → _overlapped` 时失败（WinError 10106、退出1、0用例），额度1/1已消耗，未重跑。源码及失败证据保留，工程测试未通过。API/正式validation/Critic均0，Stage C2/D11/D12/D04B及原83项合同不变。

此前 `C2-02P-CAL05-PREP` 离线准备记录保留在 `artifacts/stage_c2/C2-02/scoped_pilot/cal05_preparation/`。该历史阶段仅建立指定来源索引、七行候选、待独立审阅记录及真实执行预算草案；当时网络与工程实现尚未批准，已批准的一次离线测试未使用，原文未获取、程序未实现或测试、真实验收未执行。七行不是 READY，API/网络/正式 validation/Critic 均 0；历史交付原样保留。

本轮 `C2-02P-NEXT` 仅准备传输检查方案、七项非停牌候选补证表及短 Checkpoint，入口为 `artifacts/stage_c2/C2-02/scoped_pilot/next_preparation/`。七项目前均未资格化；优先人工补 CAL_05 的官方历史版本、独立前交易日与字段语义，再另行授权实现、验收程序和真实执行。最多七项各一次只是预计 7 次调用，不是授权。API、网络、验证、Critic 均 0；Stage C2/D11/D12/D04B 和 Full Census 状态不变。

此前 `C2-02P-DIAG-01` 离线诊断已记录并停止：[诊断报告](artifacts/stage_c2/C2-02/scoped_pilot/diagnostic_01/C2_02P_DIAG_01_REPORT.md)与 [Checkpoint](artifacts/stage_c2/C2-02/scoped_pilot/diagnostic_01/C2_02P_DIAG_01_CHECKPOINT.yaml)。冻结参数/调用/序列化相同；当前 SDK 存在 HTTP 错误回退为空表的路径，但 R01 未记录 HTTP 状态，根因仍 UNKNOWN。先向提供方澄清覆盖，不申请立即 API 重查。本轮 API、正式验证、网络、Critic 均 0，历史执行字节不变。

最近真实执行 `C2-02P-V2-R01` 已执行并停止，入口是 `artifacts/stage_c2/C2-02/scoped_pilot/execution_v2_r01/README.md`、`C2_02P_V2_R01_CHECKPOINT.yaml` 和 `PACKAGE_INDEX.yaml`。在明确新授权下完成预检、受信启动控制、同进程存储 gate、三次固定 API 和一次后检。三个 SDK frame 已持久保存且独立哈希一致，返回行数 0/0/1；前两项缺失固定正事件，第三项事件比较通过，整体 `FAIL_OR_INCOMPLETE`、接受 0 行。新 API 3/3、验证 2/2、内部 gate 1/1 已消耗，无重试、Critic 或 Census。冻结代码、授权草案和 138 个历史 Pilot 文件原样保留。Stage C2 保持 `BLOCKED_INCOMPLETE`，D11/D12/D04B 均未就绪，Full Census query_ready/execution_authorized 均 false，不能继续执行。研究路径归档 `archive/stage_c2_research_path/INDEX.yaml` 和历史 ZIP 保留原样。下列 Stage B1/B2 文字为历史记录。

Stage B1 已通过限定 synthetic 工程范围验收：436 passed / 1 skipped，规划校验 384/384；W09 仅为 SYNTHETIC_MOCK，formal G6 仍 BLOCKED。Stage A.1 历史基线为 317 passed / 1 skipped，其证据保持原样。Stage B2 已在 synthetic engineering 范围内通过验收并停止后续派工；W10B/W15–W19、empirical/shadow 仍未授权。

## 当前入口

- `stage_b2_acceptance.yaml`：当前 Stage B2 限定工程验收、独立审计、失败和哈希证据。
- `artifacts/stage_b2/README.md`：本阶段证据索引，历史失败原样保留。
- `stage_b1_acceptance.yaml`：历史 Stage B1 验收、失败历史、独立复核、运行产物与哈希。
- `stage_a1_acceptance.yaml`：Stage A.1 历史验收，保持原样。
- `planning/STAGE_A1_OWNERSHIP.md`：Attempt lineage、历史 snapshot / 当前授权分离、RunManifest ownership。

- `stage_a_acceptance.yaml`：变更、测试退出码、失败记录、独立审查、运行证据和 Stage B 建议。
- `planning_report.yaml`：当前规划与授权状态。
- `contracts/decisions.yaml`：唯一有效 Decision Registry；D04A 核算规则已冻结，D04B 的统计参数延期。
- `planning/v0.2/06_WORK_BREAKDOWN.md`：历史任务基线与原始实现白名单；当前状态见 planning/stage_b2_plan.yaml。
- `planning/v0.2/02_TARGET_ARCHITECTURE.md`：目标架构与 ScientificSearchFamily / AgentBenchmarkRun 分离规则。
- `planning/SEALED_THREAT_MODEL.md`：W09 前置威胁模型；mock 不等于 benchmark-grade。
- `artifacts/stage_a/`：本轮测试、失败记录、独立 critic 和 artifact hash 证据。
- `archive/planning_v0.1/`：不可作为当前规范的首轮历史快照。

历史 Stage A/A.1 范围为 W01–W06；历史 Stage B1 范围为 W07/W08/W20 和通过 TM-01 前置审阅的 W09 mock。真实数据研究、策略搜索、真实下单和 sealed 部署均不包含在本轮实现范围。

## 离线检查（PowerShell）

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest -q -p no:cacheprovider
python planning/validate_planning.py
```

开发环境依赖：Python 3.12、PyYAML、pytest；kernel 存储采用 Python 标准库 SQLite。未进行依赖安装或调用模型 provider。测试可复现性与 runtime 限制以本轮验收报告为准。源代码 namespace package 无需额外打包脚手架。


## Stage B1

历史 B1 授权 W07 → W08 → W20，W09 在独立 TM-01 设计审阅后实现 synthetic mock。独立审计与最终回归已完成，仅验证本轮 synthetic 范围。入口为 `planning/stage_b1_plan.yaml`；完整交付记录在 `stage_b1_acceptance.yaml`。B1 当时未开放 empirical/shadow 或 W10/W11–W19；后续 B2 授权见下节。


## Stage B2 当前授权

Stage B2 的 W10A / W11–W14 synthetic Agent/Evaluator loop 已通过限定工程验收，见 `stage_b2_acceptance.yaml` 与 `planning/stage_b2_plan.yaml`。正式研究 verdict 仍 BLOCKED：G4 缺 D04B 校准，G6 缺 benchmark-grade sealed infrastructure。W10B、W15–W19、真实 provider/市场数据均未授权。

Canonical regression：设置 `PYTHONPATH=src` 后，从项目根目录运行 `python -m pytest -q -p no:cacheprovider`；`pytest.ini` 将发现范围限定为 `tests/`，保留但不收集 artifacts 中的历史测试。
