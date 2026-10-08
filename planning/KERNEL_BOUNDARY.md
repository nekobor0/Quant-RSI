# Stage A Kernel boundary

本阶段只实现 W01–W06，不包含 W07 数据扫描、W08 撮合、W09 权限沙箱、W10 统计计算或 W11 评分器。

## Runtime contract

W02/W03 使用不可变合同、严格 JSON 序列化与内容哈希。W04 绑定这些合同的内容哈希、Task/Env/Eval/成本/清洗/切分/预算版本。模型身份、prompt、run 和 family 不进入公平比较 condition hash，但必须进入 run provenance。synthetic 工程 Task 必须明确标记，不得凭借合同通过被提升为 empirical benchmark。

Scientific family 是最终 claim 的选择范围；benchmark budget root 是独立模型运行的配额域。一个 attempt 在 trace 中同时引用两者。merged family 对 ancestry 中 attempt ID 去重；capability 的分母只取本 budget root，不读 merged family 的搜索分母。

## Persistence and trust

W05 使用 SQLite transaction 作为本地单写入临界区；研究事件表禁止 UPDATE/DELETE，唯一 ID 幂等，同 ID 不同内容拒绝。hash 链验证可检测记录修改，外部受信锚点接口用于检测回滚/截断。事务失败不留下部分事件；已 STARTED 的失败必须通过新 terminal 事件保留。SQLite 文件可写权限持有人仍能拆除触发器或重写数据库，因此不能仅据此宣称 hostile-worker 防篡改；真实服务身份与外部锚点 custody 是后续部署条件。

W06 所有注册、quota reservation、STARTED 与 settlement 都通过 W05 的同一事务执行。quota 必须显式完整；未知维度、bool/负数/非整数用量拒绝。预留 envelope 超限记录 denial；未知资源用量保守计满并阻断该 root 的下一次 dispatch，等待 append-only reconciliation。实际资源少于 envelope 可释放未用资源；search/attempt 计数不可退款。actual 超 envelope 保留 breach 并锁住 root，不能为了通过测试隐藏超额。

独立 comparison run 有自己的相同条件预算。continuation 保留 parent 和 budget_root_run_id，必须同模型/版本/condition；不得通过 continuation 身份重置配额。重新发起独立 run 必须由 trusted scheduler 明确选择，事件记录 registration kind；kernel 不证明模型未在别处隐藏搜索，不能取代后续 supervisor/tool trace 和 custodian 审计。

## Evidence and limits

本阶段运行证据只用 synthetic fixtures。并发预算测试必须含多进程；重开连接验证持久化；崩溃恢复/事务 rollback、hash 锚点漂移、幂等冲突、失败和未知用量保留均需负例。独立 critic 只读审阅、产出 findings，修改必须回到原 owner 白名单。真实 clock/resource enforcement 与 model invocation（W12/W14）没有实现；本阶段只提供可测试的治理核算原语。


Stage A.1 adds only the provenance correction described in `planning/STAGE_A1_OWNERSHIP.md`. Its explicit file overlay is `planning/stage_a1_plan.yaml`; original W01–W20 whitelists remain historical and unchanged. No W07–W20 implementation is authorized.
