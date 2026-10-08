# TM-01 Sealed Evaluation Threat Model — Planning v0.2

状态：设计前置条件，必须在 W09 之前由独立 custodian 审阅；本轮不实施 W09。

## Protected assets

sealed features/labels、隐藏案例与 RNG seeds、参考输出、evaluator 镜像和规则、submission counter、访问日志、签名和存储凭据、已曝光状态。保密性与规则/结果完整性同为保护目标。

## Attacker capabilities

把 candidate/worker 当不可信：可生成任意代码、构造模型输出和工具参数、反复提交、并发重放、探测路径/网络/错误、利用缓存与共享上下文、读自身日志；可有 dev workspace 写权限。不得假定 prompt 禁令会阻止这些行为。受信 custodian/OS 被攻陷不在 mock 可证明边界内；一旦发生按 compromise 处理。

## Channels and required controls

| Channel | Attack | W09 前须冻结的控制与验证 |
|---|---|---|
| filesystem | 路径穿越、符号链接、共享挂载、临时文件 | 独立身份和存储，无 host/label mount；主动跨目录读取反例 |
| network | DNS/HTTP/回连/云 metadata | 默认禁网，含 DNS/metadata endpoint；出站反例 |
| tool | shell、browser、retrieval、插件读取私有数据 | evaluator 不继承 worker 工具；每次调用鉴权；越权工具反例 |
| log | stdout/stderr、trace、缓存、调试日志泄漏 | trusted side 清洗/配额/字段白名单，原始隐藏日志不回传 |
| error | 栈/异常包含文件路径、标签或数据片段 | sanitized opaque error IDs；构造异常验证无数据回显 |
| metadata | 文件大小/mtime/错误差异/计时/计数/模型缓存 | 最小响应、固定字段、禁止共享私有缓存；残余侧信道单独记录而非声称消除 |

## Trust and credentials

trusted custodian 独立于 candidate 作者、Orchestrator 与 Critic；拥有 sealed storage identity、read secrets、evaluator release key、结果签名 key 和 exposure registry。worker/critic/orchestrator 不拥有这些凭据。短期 candidate execution identity 仅能调用受限 feature 接口；label evaluator 是另一身份。secret 不写源代码、trace、prompt 或一般环境导出；轮换和撤销由 custodian 记录。具体部署和凭据尚未创建。

## Compromise policy

疑似泄漏即暂停当前 condition 的所有新提交，保存不可变访问与尝试记录，标记受影响结果 INVALID/UNDER_REVIEW；独立调查后撤销凭据、修补边界，并发布新未曝光 holdout。版本升级本身不能恢复旧样本的独立性。不得让失败重试免费获得更多隐藏反馈。benchmark 各模型有独立 run，但 exposure policy 仍由同一 custodian 全局约束。

## Assurance levels

`SYNTHETIC_MOCK` 只说明工程协议在假数据/模拟身份中经过测试，绝不等于 benchmark-grade sealed evaluation。`BENCHMARK_GRADE` 必须附独立身份/存储部署证据、各通道拒绝测试、权限与凭据审计、custodian 签核及剩余风险。当前等级为 `NOT_IMPLEMENTED`。W01–W06 的 hash 链和锚点接口也不证明 OS 隔离或 custodian 已部署。
