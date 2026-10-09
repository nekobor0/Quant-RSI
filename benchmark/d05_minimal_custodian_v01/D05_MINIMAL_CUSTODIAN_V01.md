# D05 Minimal Custodian v0.1

本轮结果：**BLOCKED_ENVIRONMENT_CAPABILITY**。没有授予
PASS_OFFLINE_ISOLATION_ENGINEERING，也没有授予 D05_FULL_SEALED_QUALIFIED。
没有可用 Worker 提交，因此 Worker → Custodian 独立评分演示未执行。
按用户指定的环境阻塞停止条件收口，不继续增加模拟隔离层。

Track A 保持 PUBLIC / UNSEALED / PROVISIONAL；D05 deployment_status 仍是
NOT_IMPLEMENTED，D08 未验收，Track B 与 D11/D12/D04B、sealed 资格均不变。
真实 Agent / Judge / 数据 API 调用为 0，未推送 Git。

## 已检查的复用能力

读取 HANDOFF、AGENTS、contracts/decisions.yaml、预算治理政策、B1/B2 的
TraceStore、SearchBudget、eval/isolation.py、eval/gates.py、EvalResult，以及
Workflow v0.2 和 Hybrid v0.1 报告及相关接口。没有重跑这些冻结基线的验收，
也没有扫描全仓计算哈希。

- TraceStore 可直接保留追加事件与哈希链；本轮用它记录实际启动探针及交付绑定。
  它不防御数据库的 OS 文件所有者，因此必须位于真正的 Custodian 权限区域。
- SearchBudget 已有 root、派发前预留、UNKNOWN/BREACH 阻断和结算；未来可直接复用。
  本轮只使用治理政策内的 3 次工程启动探针，没有科学搜索、新候选或模型调用；
  启动记录明确是 post_execution_record，不补造过去的预算预留/Worker 执行事件。
- 原 MockIsolation 明确是 SYNTHETIC_MOCK，按约定隐藏对象不能满足 D05。
- B2 确定性 Evaluator 的输入绑定、硬门禁及 EvalResult 可复用；G6 仍要求
  BENCHMARK_GRADE_SEALED_INFRASTRUCTURE_ABSENT，不通过本轮自动改写。
- Workflow 的公开上下文/允许工具释放、动作解析与确定性事实核验可复用；
  Hybrid 的匿名 Packet、JudgeResultValidator 与追加保存可复用。没有改原 Rubric。

## 实际环境与探针证据

当前为普通 Windows 用户进程。可见令牌特权没有列出
SeAssignPrimaryTokenPrivilege、SeIncreaseQuotaPrivilege 或 SeImpersonatePrivilege；
这不是失败根因的确定证明。Docker CLI 已安装，但本地 Linux engine 命名管道
dockerDesktopLinuxEngine 不存在；version/image ls 均无法连接，未拉镜像、启动
Docker 服务或创建容器。

新增 scripts/d05_restricted_worker.ps1 只在工作区下全新的
.d05_synthetic_probe_* 直接子目录建立测试区域。private 目录关闭继承，只允许
当前 Custodian SID；public 授予 Users 读取，inbox 授予 Users 写入。真实调用
CreateRestrictedToken 和 CreateProcessAsUser，禁用最大特权；不继承句柄，
使用只含 SystemRoot/WINDIR/PATH/TEMP/TMP 的干净子进程环境。没有读取、输出
或传入实际模型凭据，没有改系统目录/桌面/生产材料的 ACL，也没有创建系统账户。

| 启动 | 候选受限身份 | 原生退出状态 | Worker 收据 |
|---|---|---|---|
| 1 | restricting SID = BUILTIN Users | 0xC0000022 / STATUS_ACCESS_DENIED | 无 |
| 2 | 同上；工作目录修正为可读 public | 0xC0000022 / STATUS_ACCESS_DENIED | 无 |
| 3 | restricting SIDs = 原令牌 groups（排除 user SID） | 0xC0000142 / STATUS_DLL_INIT_FAILED | 无 |

三次原生进程启动调用都返回了子 PID，但子进程在运行受控 Worker 代码前退出。
第一次原始包装状态为 PROBE_EXECUTED，仅表示调用启动 API，不能解释为 Worker
执行成功；原始记录未改写，统一的 interpreted_status 标为环境阻塞。
**启动 Access Denied 不等于读取 private Oracle 被拒绝的证据。**
第二、三次包装状态明确 BLOCKED_ENVIRONMENT_CAPABILITY。最终交付探针也用
非零退出码表示阻塞。未定位 DLL 初始化失败的具体根因，未尝试修改宿主机
共享安全对象权限以强行通过。

原始 environment_probe.json、生成的 public/worker.ps1、private 中的合成
canary 与 ACL 保留在三个忽略 Git 的本地合成目录。environment_results.json
保留三次实际报告、状态解释及生成 Worker 脚本哈希；acl_observation.json
记录第三个测试 private 目录的实际 ACL。Custodian 本地可以读取合成 canary，
但不存在 Worker 提交，不能据此登记独立评分成功。canary 只是权限探针数据，
不是新 Hidden 评测题。

交付绑定只覆盖最终探针/定向测试源码。之前的宿主 launcher 版本未被独立封存，
不声称逐次 launcher 的完整事前版本绑定。原始探针输出与后续源码绑定均追加
保留，未用更新后的源码假冒旧执行字节。

## 十项安全验收的真实状态

| 要求 | 本轮状态 |
|---|---|
| Worker 读取公开任务 | NOT_EXECUTED：受限 Worker 未开始执行 |
| Worker 直接读取私有 Oracle 被拒绝 | NOT_VERIFIED：没有文件访问拒绝收据 |
| Worker 修改私有评分规则被拒绝 | NOT_EXECUTED |
| 允许工具不泄露私有答案 | NOT_EXECUTED |
| 提交请求不能覆盖原评分 | NOT_EXECUTED |
| Custodian 独立读取 Oracle 与 Worker 提交评分 | 未完成；仅宿主可读合成 canary |
| 检测任务/评分材料篡改 | NOT_EXECUTED；仅源码/探针记录绑定被核验 |
| 保留未经授权读取失败证据 | NOT_EXECUTED；仅保留实际启动失败证据 |
| 原 Trace/已有评分不能被 Worker 覆盖 | NOT_VERIFIED；历史文件未改动不等于权限证明 |
| 工具输出指令不能提升权限 | NOT_EXECUTED |

4 项定向测试通过，只验证：原生失败证据与未授予 PASS、现有 TraceStore 链和
源码绑定、PowerShell 语法、已有测试目录在 ACL/文件修改前被拒绝。它们不是
十项权限安全测试的通过计数。共 1 次 pytest、3 次工程启动，未重跑历史测试。

## 独立性和未实现边界

身份独立性：未验证到可工作的隔离 Worker。候选 restricted token 的 user SID
仍与 Custodian 相同，不等于独立登录账户；也未验证 token/父进程句柄、ACL
所有者权限等绕过边界。权限区域的目录名称和 ACL 配置本身不是 PASS 证据。

证据独立性：仅有本地原生启动失败和 ACL 观察证据；没有独立 Custodian 对
Worker 原始提交的核验。结果独立性：探针、合成数据及判定仍由同一工程作者
生成，作者独立性不足，不能宣称 D08 完整通过。

尚未交付可用的隔离 Worker、受控提交/评分服务、匿名 JudgePacket 的生产释放
或端到端评分。本轮没有用主动返回 permission denied 的 Python 模拟替代
操作系统验证，也没有增加第二套 Trace 或 Budget。

## 最小实际部署要求

需要先提供可运行的隔离执行环境，再继续本轮范围的 1—2 个合成任务：

1. Windows 使用不同的低权限 Worker 与 Custodian 服务账户/SID，并在合成区
   验证 private ACL 只授予 Custodian；或提供已经运行的本地容器 runtime 和
   离线固定镜像，Worker 只挂载只读 public 与受限提交通道，不挂载 Oracle、
   宿主 socket/凭据，不启用特权或网络。具体部署方案尚未验收。
2. Worker 的令牌、运行时、父进程访问和所有者/重解析点边界必须真实验证。
   Custodian 单独保存 Oracle、评分配置、可信版本 pin、原 Trace 和结果。
3. 提交通道只收固定结构的最终答案与必要轨迹；不接受 Worker 提供的评分、
   Oracle 路径、身份、预算根或覆盖参数。Custodian 在现有 SearchBudget 预留
   后调用原确定性 Evaluator，并通过原 TraceStore 追加版本/提交/判分收据。
   private 材料不提交到被测 Worker 可读 Git 区域。
4. 完成真实公开读取、私有读取/写入拒绝、工具白名单、提交不可覆盖、篡改、
   失败留证和输出注入十项合成验证，再登记 PASS_OFFLINE_ISOLATION_ENGINEERING。
   D05_FULL_SEALED_QUALIFIED 仍需另行独立证据，不能从合成成功自动获得。

未来真实模型最小变化：在已经验收的 Worker 权限内接入授权的 Provider，凭据
只由可信执行服务保管，冻结真实 token/货币/timeout 和批量授权，不改变权限
或续订科学预算。未来 Luna Judge 仅从 Custodian 释放匿名 JudgePacket，排除
private_receipts 和模型身份；使用未修改的 JudgeResultValidator，原确定性
分数只追加不覆盖，软评分异常保留人工复核。本轮不启用这些调用。

结果与追加证据见 environment_results.json、trace.json；最小探针及失败记录
已交付。达到本轮环境阻塞停止条件，停止，不扩大任务。
