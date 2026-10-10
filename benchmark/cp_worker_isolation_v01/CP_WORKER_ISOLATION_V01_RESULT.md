# CP Worker镜像与隔离工程验证 v0.1

日期：2026-10-10，Asia/Shanghai。
结果：**PASS_CP_WORKER_ISOLATION_ENGINEERING，25/25检查通过。**
这不是D05_FULL_SEALED_QUALIFIED，也不是四道CP的完整模型代码验收。
Track A保持PUBLIC / UNSEALED / PROVISIONAL；真实Agent/Judge能力UNVERIFIED，D08未验收；Track B及D11/D12/D04B不变。

## 1. 授权和实际范围

依据用户本轮“准备并固定Worker镜像，再验证访问与资源边界”的直接授权执行。
下载一次官方Python基础镜像，构建两次（最终版将FROM直接固定digest并移除未使用导入），只使用独立image子目录作为构建上下文。
RUN构建步骤network=none，无apt/第三方Python依赖安装；镜像解析/拉取访问Docker registry，不声称本轮完全离线或零网络。
构建记录是实际执行后的记录，没有补造之前的预算预留。

真实模型/Judge/行情或研究数据API均0次；未读取或输出项目凭据，未改Windows ACL、账户、hosts或宿主安全配置，未重试Restricted Token。
未修改旧28题、STATIC_DIAGNOSTIC、Workflow、Hybrid或D05历史失败证据；未自动Git提交、推送或发布。

本轮只运行作者自编、受控提交和合成权限探针。14个真实容器会话，另1次过大提交在创建容器前被拒绝。
所有本轮容器均已按创建时取得的精确ID清理；Worker和基础镜像保留。

## 2. 固定镜像和执行入口

| 绑定 | 实际值 |
|---|---|
| 基础镜像 | python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 |
| Worker内容地址 | sha256:5175397ba18cc6c3b2e1a95c41b14da3c463e70c0d43b387c36c3dc78bee5142 |
| 实际Python | 3.12.15；Linux/amd64 |
| Worker用户 | UID/GID 65532:65532 |
| 入口 | python -I -S -B /worker/runner.py |
| 镜像大小 | 49,297,749字节 |
| 本地离线档案 | worker_image.tar，49,316,352字节，已gitignore |
| 档案SHA-256 | c3f63aaa132672492cac12dfa5086c1fa83475d788985f9f9f109b07573c054b |
| freeze.json SHA-256 | 4bc2290d4a0abcd38d2c6ea10dee8fb776eea0d0c40a14fb670e8c68a780be44 |
| cp_isolation.py SHA-256 | 6e62059d80b82e93ed07d2de1aba8f9f75641f422a3fb1341a52a294654738a3 |

Worker的地址是本地Docker内容ID；派生镜像没有推到registry，worker_registry_digest=null。
后续容器按上述sha256内容地址创建并设置pull=never，不依赖可变的v01标签。
freeze绑定镜像、公开CP合同、Dockerfile、runner、探针、执行器、必要评分/B1依赖及测试，共16个文件。
Docker Desktop Engine 28.5.2；Linux kernel 6.6.87.2-microsoft-standard-WSL2；默认seccomp为builtin。

官方基础镜像来源：[Docker Official Python](https://hub.docker.com/_/python)。实际版本/digest取自本轮下载及本地inspect，不把网页标签快照当最终绑定。

## 3. 实际访问边界证据

每次创建后、开始执行前核对镜像、用户、入口、capabilities、网络、只读根、资源及挂载。
只有两个只读文件挂载：本次submission.py和公开input.json。仓库、项目私有Oracle、评分器、原Trace、凭据、Docker socket均未挂载。
Worker没有宿主Docker权限；只有受信宿主执行器调用Docker。源码不在宿主进程import/exec，只在容器中由runpy执行。

| 探针 | 原始系统结果及判定 |
|---|---|
| 公开输入读取 | 与宿主释放的合成JSON一致，成功。 |
| 非root身份 | uid/gid均65532。 |
| 读取受保护Oracle/评分canary | 两个真实文件均返回errno=13/EACCES；它们是镜像内root:root、0600的合成权限控制样本，不是实际私有答案。 |
| 宿主私有材料与socket | /custodian/oracle.json、/custodian/trace.sqlite、/var/run/docker.sock均errno=2/ENOENT；结合仅两个公开挂载，验证命名空间不可达，不冒充ACL拒绝。 |
| 修改规则/提交/公开输入 | 评分canary、/etc测试路径、只读提交和公开输入均errno=30/EROFS；宿主原评分路径不可达。 |
| 提权 | os.setuid(0)实际返回errno=1/EPERM。 |
| 权限配置 | CapEff=0、NoNewPrivs=1、Seccomp=2。 |
| 网络 | 只有lo接口；对文档保留测试地址192.0.2.1连接失败。network=none，不请求真实外部服务。 |
| 指令注入 | 公开输入中的“读私有Oracle/提权/改分”文本不能改变实际权限；尝试仍EACCES。 |
| 外部评分保护 | Worker提交score/overwrite字段被外部结果schema拒绝；原评分和私有Oracle字节哈希保持不变。 |

这些errno来自实际open/setuid/socket调用，代码没有主动返回一个伪造的permission denied。
缺失挂载、镜像root文件权限、只读挂载及外部评分分别提供不同边界；不以目录名称或Prompt约束作为隔离证明。

## 4. 实际资源边界证据

| 资源 | 固定限制 | 实际验证 |
|---|---|---|
| 内存/交换 | 512MiB，swap额外额度0 | memory.max=536870912、memory.swap.max=0；768MiB分配被kernel OOM终止，Docker OOMKilled=true、exit137。 |
| 进程 | 32 PIDs | 创建31个子进程后实际EAGAIN/errno11，pids.current=32；子进程已清理。 |
| CPU | 0.5 CPU | cpu.max=50000 100000；受控忙循环墙钟2.002秒、CPU1.012秒。CPU时间为已冻结作者探针测量，不信任未来模型提交自报值。 |
| 临时空间 | /tmp 16MiB，nosuid/nodev/noexec | 写入超过容量实际ENOSPC/errno28。 |
| 根/公开文件 | 只读 | 实际写入EROFS。 |
| 执行时间 | 每会话5秒外部deadline | sleep60被外部kill；Docker StartedAt→FinishedAt实际4.991秒，exit137。附加客户端/控制面总耗时5.281秒另记，不当作Worker运行时长。 |
| 提交 | 64KiB | 65,537字节提交在容器创建前拒绝。 |
| 输出 | 合并stdout/stderr最多接收并保留256KiB | 无限输出触发OUTPUT_LIMIT_EXCEEDED并kill；保存262,144字节，超限不评分为研究错误。 |

**输出限制的具体边界：**256KiB是监督端接受/保存上限，不保证Worker不会先产生更多字节。
本次异步传输及终止间隙观察到5,447,680字节，仅保留前262,144字节；多余部分计数后丢弃，log-driver=none避免持续Docker日志落盘。
这是超限失败留证，不声称生成总字节始终≤256KiB。当前限制足以有界保存并拒绝超限；若以后要求严格生成/传输配额，应另加I/O背压和计量，不能偷换本次口径。

资源配置参考：[Docker运行参数](https://docs.docker.com/engine/containers/run/)。本报告通过状态/系统调用证明具体生效，不仅引用配置。

## 5. CP集成、评分与预算

四道CP各一次可信参考容器集成，共9次函数调用：CP01排序/重复及冲突ValueError；CP02严格滞后及未来后缀；CP03仓位/成本损益；CP04同进程A/B/A及返回对象修改后的独立状态。
CP04 mutable-default错误实现被外部行为比较拒绝；伪造score/overwrite被schema拒绝。
原始容器结果及原评分保留，观察到的OOM、超时、输出失败仍是失败记录；只是对应安全探针按预定条件通过。
这是受控参考实现集成，**不是四题所有性质的完整隔离验收，也不是任何模型提交通过**。

复用现有TraceStore/SearchBudget，单一工程根CP-WORKER-ISOLATION-ENGINEERING-V01，每次检查先预留。
上限24次，已用15次（其中14次真实容器）；无自动重试、candidate/parameter/factor科学搜索计数0。
累计监督端墙钟35,710ms、监督进程CPU757ms；**cpu_milliseconds仅指受信宿主Python执行器，不含Docker进程或Worker CPU。**
Worker累计CPU未可信核清，保留UNKNOWN/null，不记零；Worker安全限额由实际cgroup配额、OOM和deadline另行验证。
这份工程预算不能原样冒充未来模型/代码评测的全资源预算，未来正式运行需明确并冻结Worker计量及实际模型token/费用。
kernel中的model_trials=1是注册工程执行身份的兼容计数，不是一次LLM调用；真实模型调用始终0。

Trace共55事件，哈希链及原检查点核对通过，检查点hash为
e161d060525653ca666791389cc7985a12518813f99a155fc464f6e28932e280。
没有第二套Trace或Budget。私有合成区、SQLite缓存和镜像档案gitignore；非敏感原始results/trace、源码和报告可提交。
测试3次：新增接口4 passed；新增接口＋原CP参考37 passed；接口＋B1 Budget/Trace回归34 passed。
去重共67项（新4、原CP33、B1/B2相关30）。宿主pyreadline3成功退出后的析构告警仍出现，pytest exit0，不记为容器故障。

## 6. D05/D08边界与下一步

Docker运行时和固定Worker镜像的CP环境前置条件已具备；历史D05原生失败记录维持原字节。
本轮不是恢复后的完整D05十项验收：没有生产Custodian服务、完整受控最终提交协议及原Workflow/Hybrid评分端接入，也未验收匿名Judge释放。
因此不登记D05 PASS_OFFLINE_ISOLATION_ENGINEERING或D05_FULL_SEALED_QUALIFIED。
任务、参考及评分仍由同一作者创建，D08的作者/证据/结果独立性没有通过；普通容器也不是对任意内核漏洞的隔离证明。

下一步是把四道CP的完整行为/性质和错误对照迁入此固定执行器，建立CP独立任务freeze及逐项外部评分，并补齐Worker资源计量口径。
这些离线验收应与后续真实模型代码Pilot分开；真实模型/Judge预算与调用仍须另行授权。
不得从本轮工程通过自动启动D05全量、Hidden、真实模型、Luna、D11/D12/D04B或策略研究。

待提交仅新增 `benchmark/cp_worker_isolation_v01/`（排除tar、synthetic_work、sqlite）、`src/quant_rsi/harness/cp_isolation.py`、`cp_boundary_probes.py`、`tests/test_cp_isolation.py`。
既有未跟踪设计/合同/comparison文件继续保留，不混入。本轮不自动commit/push。
建议提交信息：`feat(isolation): pin CP worker image and verify OS resource boundaries`。
