# Historical Planning v0.2 work-item baseline

The original table below records Stage A authorization, not current dispatch. Current overlays: planning/stage_b1_plan.yaml and planning/stage_b2_plan.yaml (when created). Current Stage B1 scope passed; do not interpret NOT_STARTED below as current status.

# 单一职责 Work Breakdown — Planning v0.2

本轮仅授权 W01 → (W02 || W03) → W04 → W05 → W06；完成后停止。W07–W20 不授权。每项原文件白名单、最多两次修复、六次 test invocation 和工程预算上限保留。ScientificSearchFamily 与 AgentBenchmarkRun 按 02 中的 v0.2 规则分离；具体统计参数由 D04B 延期。

权威 Decision Registry：`contracts/decisions.yaml`。W01 完成 FREEZE_NOW 并保留延期，不等待 empirical/shadow 数值。W09 必须先完成 TM-01 独立托管者审阅。规划修订、证据归档与本阶段独立 critic 审核是当前用户另行授权的管理工作，不属于 W07–W20 实现。

以下表格是历史 v0.2 work-item 基线；当前状态与授权扩展以阶段 overlay 为准，原白名单保留用于审计。

```yaml
work_items:
- id: W01
  owner_role: astra
  suggested_worker: Astra or separately assigned data worker
  status: COMPLETE_STAGE_A_WITH_DECLARED_LIMITATIONS
  dispatch_authorization: AUTHORIZED_STAGE_A
  objective: 冻结独立项目决策与对象归属
  inputs:
  - 用户 Planning v0.2 修订与 Stage A 授权
  - 七份原始输入
  - contracts/decisions.yaml
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - contracts/decisions.yaml
  - tests/contracts/test_decisions.py
  deliverables:
  - D01–D13 统一 registry，D04 替换为 D04A/D04B；FREEZE_NOW/DEFER_UNTIL_EMPIRICAL/DEFER_UNTIL_SHADOW
  tests:
  - python -m pytest -q tests/contracts/test_decisions.py
  - FREEZE_NOW 已冻结；延期数值仍 null；Stage A synthetic 可执行，empirical/shadow 不可激活
  acceptance_criteria:
  - 所有 active decision ID 唯一、签核来源指向用户授权
  - 延期 empirical/shadow 决策不阻断 kernel 合成验证，也不能被视为已批准
  - 只改白名单并附测试、hash 与独立审阅
  dependencies: []
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: FROZEN_ENGINEERING_LIMITS
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 本阶段工程上限已冻结；不代表实际消耗或性能测量。
  runtime_evidence:
  - artifacts/stage_a/StageA_final.xml
  - artifacts/stage_a/StageA_final_runtime/summary.json
  - artifacts/stage_a/critic_runtime_resolution.json
  limitations: 仅本地 synthetic kernel；完整系统能力未验收；详见 stage_a_acceptance.yaml
- id: W02
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: COMPLETE_STAGE_A_WITH_DECLARED_LIMITATIONS
  dispatch_authorization: AUTHORIZED_STAGE_A
  objective: 建立唯一研究对象合同
  inputs:
  - docs/inputs/01_LITERATURE_TO_HARNESS_TAKEAWAYS.md#4
  - planning/v0.2/02_TARGET_ARCHITECTURE.md#唯一对象归属
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/contracts/research.py
  - tests/contracts/test_research.py
  deliverables:
  - Hypothesis/ConceptMapping/ExperimentSpec/Evidence/Candidate 的序列化模型
  - ScientificSearchFamily 独立 ID/claim/parent lineage；不拥有 Agent capability score
  tests:
  - python -m pytest -q tests/contracts/test_research.py
  - 反例/边界验证：单一可证伪主张；未知数值 null；来源引用必需
  - 反例/边界验证：round-trip、重复 ID、未预注册、叙述充当测量反例均覆盖
  acceptance_criteria:
  - 单一可证伪主张；未知数值 null；来源引用必需
  - round-trip、重复 ID、未预注册、叙述充当测量反例均覆盖
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W01
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: FROZEN_ENGINEERING_LIMITS
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 本阶段工程上限已冻结；不代表实际消耗或性能测量。
  runtime_evidence:
  - artifacts/stage_a/StageA_final.xml
  - artifacts/stage_a/StageA_final_runtime/summary.json
  - artifacts/stage_a/critic_runtime_resolution.json
  limitations: 仅本地 synthetic kernel；完整系统能力未验收；详见 stage_a_acceptance.yaml
- id: W03
  owner_role: data_env
  suggested_worker: Astra or separately assigned data worker
  status: COMPLETE_STAGE_A_WITH_DECLARED_LIMITATIONS
  dispatch_authorization: AUTHORIZED_STAGE_A
  objective: 建立 DataSpec 与 snapshot manifest 合同
  inputs:
  - planning/v0.2/03_ENV_SPEC_DRAFT.yaml#data_contract
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/contracts/data.py
  - tests/contracts/test_data.py
  deliverables:
  - DataSpec/SnapshotManifest 单一数据定义
  tests:
  - python -m pytest -q tests/contracts/test_data.py
  - 反例/边界验证：revision/available_at/units/hash 缺失拒绝
  - 反例/边界验证：相同内容相同 digest；替换原始文件即失败
  acceptance_criteria:
  - revision/available_at/units/hash 缺失拒绝
  - 相同内容相同 digest；替换原始文件即失败
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W01
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: FROZEN_ENGINEERING_LIMITS
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 本阶段工程上限已冻结；不代表实际消耗或性能测量。
  runtime_evidence:
  - artifacts/stage_a/StageA_final.xml
  - artifacts/stage_a/StageA_final_runtime/summary.json
  - artifacts/stage_a/critic_runtime_resolution.json
  limitations: 仅本地 synthetic kernel；完整系统能力未验收；详见 stage_a_acceptance.yaml
- id: W04
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: COMPLETE_STAGE_A_WITH_DECLARED_LIMITATIONS
  dispatch_authorization: AUTHORIZED_STAGE_A
  objective: 绑定并冻结 benchmark condition 合同
  inputs:
  - planning/v0.2/03_ENV_SPEC_DRAFT.yaml#version_binding
  - planning/v0.2/04_EVAL_SPEC_DRAFT.yaml
  - planning/v0.2/05_AGENT_ORCHESTRATION_DRAFT.yaml
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/contracts/condition.py
  - tests/contracts/test_condition.py
  deliverables:
  - TaskContract/RunManifest/EnvSpec/EvalSpec 引用与版本验证
  - AgentBenchmarkRun 独立 run ID、budget_root_run_id、family 引用；模型间同 condition 独立核算
  tests:
  - python -m pytest -q tests/contracts/test_condition.py
  - 反例/边界验证：变更 task/data/cleaning/split/env/eval/cost/budget 生成新 condition
  - 反例/边界验证：模型/prompt 为被比较变量且独立记录；研究事实仅引用 W02/W03
  - 跨模型候选可共同参与 scientific family，capability denominator 不混入其他 run
  acceptance_criteria:
  - 变更 task/data/cleaning/split/env/eval/cost/budget 生成新 condition
  - 模型/prompt 为被比较变量且独立记录；研究事实仅引用 W02/W03
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W02
  - W03
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: FROZEN_ENGINEERING_LIMITS
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 本阶段工程上限已冻结；不代表实际消耗或性能测量。
  runtime_evidence:
  - artifacts/stage_a/StageA_final.xml
  - artifacts/stage_a/StageA_final_runtime/summary.json
  - artifacts/stage_a/critic_runtime_resolution.json
  limitations: 仅本地 synthetic kernel；完整系统能力未验收；详见 stage_a_acceptance.yaml
- id: W05
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: COMPLETE_STAGE_A_WITH_DECLARED_LIMITATIONS
  dispatch_authorization: AUTHORIZED_STAGE_A
  objective: 实现追加式 research trace 存储
  inputs:
  - planning/v0.2/05_AGENT_ORCHESTRATION_DRAFT.yaml#trace
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/ledger/store.py
  - tests/ledger/test_store.py
  deliverables:
  - 单写入事件流、序号、hash 链与受信锚点接口
  tests:
  - python -m pytest -q tests/ledger/test_store.py
  - 反例/边界验证：并发/重放/部分写入/崩溃恢复保留每个失败
  - 反例/边界验证：修改删除历史或重写整链与外部锚点不符时 BLOCK
  acceptance_criteria:
  - 并发/重放/部分写入/崩溃恢复保留每个失败
  - 修改删除历史或重写整链与外部锚点不符时 BLOCK
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W04
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: FROZEN_ENGINEERING_LIMITS
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 本阶段工程上限已冻结；不代表实际消耗或性能测量。
  runtime_evidence:
  - artifacts/stage_a/StageA_final.xml
  - artifacts/stage_a/StageA_final_runtime/summary.json
  - artifacts/stage_a/critic_runtime_resolution.json
  limitations: 仅本地 synthetic kernel；完整系统能力未验收；详见 stage_a_acceptance.yaml
- id: W06
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: COMPLETE_STAGE_A_WITH_DECLARED_LIMITATIONS
  dispatch_authorization: AUTHORIZED_STAGE_A
  objective: 实现搜索预算原子预留与结算
  inputs:
  - planning/v0.2/03_ENV_SPEC_DRAFT.yaml#resource_controls
  - planning/v0.2/05_AGENT_ORCHESTRATION_DRAFT.yaml#search_control
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/ledger/budget.py
  - tests/ledger/test_budget.py
  deliverables:
  - 由 trace 派生的 per-benchmark-budget-root 原子预算，scientific-family ancestry 单独累计
  tests:
  - python -m pytest -q tests/ledger/test_budget.py
  - 反例/边界验证：并行最后一个额度仅一方获准；超额不派工
  - 反例/边界：模型 A 耗尽后模型 B 同条件额度不变；family 合并只影响最终 claim 分母
  acceptance_criteria:
  - 并行最后一个额度仅一方获准；超额不派工
  - continuation/retry 继承本 run root 预算；独立模型比较 run 不被其他 run 消耗；claim ancestry 保留全部历史；未知用量 fail closed
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W05
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: FROZEN_ENGINEERING_LIMITS
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 本阶段工程上限已冻结；不代表实际消耗或性能测量。
  runtime_evidence:
  - artifacts/stage_a/StageA_final.xml
  - artifacts/stage_a/StageA_final_runtime/summary.json
  - artifacts/stage_a/critic_runtime_resolution.json
  limitations: 仅本地 synthetic kernel；完整系统能力未验收；详见 stage_a_acceptance.yaml
- id: W07
  owner_role: data_env
  suggested_worker: Astra or separately assigned data worker
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 实现固定清洗与 PIT 可见数据视图
  inputs:
  - planning/v0.2/03_ENV_SPEC_DRAFT.yaml#data_contract
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/data/pit.py
  - tests/data/test_pit.py
  deliverables:
  - PIT revision/membership 查询与冻结训练变换
  tests:
  - python -m pytest -q tests/data/test_pit.py
  - 反例/边界验证：未来修订、当前 ST/行业回填、退市遗漏、日期时区边界可检测
  - 反例/边界验证：未来样本扰动不改变训练拟合；purge/embargo 阻止标签重叠
  acceptance_criteria:
  - 未来修订、当前 ST/行业回填、退市遗漏、日期时区边界可检测
  - 未来样本扰动不改变训练拟合；purge/embargo 阻止标签重叠
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W03
  - W04
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
- id: W08
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 实现日频 paper 执行与成本容量核算
  inputs:
  - planning/v0.2/03_ENV_SPEC_DRAFT.yaml#execution_semantics
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/env/daily.py
  - tests/env/test_daily.py
  deliverables:
  - 最小日频 simulator 与逐项成本/容量输出
  tests:
  - python -m pytest -q tests/env/test_daily.py
  - 反例/边界验证：T 收盘信号不能同收盘成交；T+1/停牌/涨跌停/部分成交/整手边界
  - 反例/边界验证：现金持仓 NAV 守恒；成本互斥扣除；规模/ADV/impact 压力输出；未知规则阻断
  acceptance_criteria:
  - T 收盘信号不能同收盘成交；T+1/停牌/涨跌停/部分成交/整手边界
  - 现金持仓 NAV 守恒；成本互斥扣除；规模/ADV/impact 压力输出；未知规则阻断
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W04
  - W07
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
- id: W09
  owner_role: evaluator_custodian
  suggested_worker: independent custodian; never candidate author
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 建立 sealed 服务与候选执行权限隔离
  inputs:
  - planning/v0.2/03_ENV_SPEC_DRAFT.yaml#environments
  - planning/v0.2/04_EVAL_SPEC_DRAFT.yaml#hidden_policy
  - planning/SEALED_THREAT_MODEL.md#TM-01
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - 候选优化历史不得用于修改当前条件的 final evaluator
  - 只允许未来另行授权的受信隐藏集；本轮没有真实 hidden 数据
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/eval/isolation.py
  - tests/eval/test_isolation.py
  deliverables:
  - OS/容器隔离适配器和访问审计
  tests:
  - python -m pytest -q tests/eval/test_isolation.py
  - 反例/边界验证：候选通过文件/工具/网络/异常/日志/metadata 均读不到标签或隐藏测试
  - 反例/边界验证：修改 evaluator、并发重提、消耗后重用 token 被阻止；无法证明隔离即 G6 BLOCK
  acceptance_criteria:
  - 候选通过文件/工具/网络/异常/日志/metadata 均读不到标签或隐藏测试
  - 修改 evaluator、并发重提、消耗后重用 token 被阻止；无法证明隔离即 G6 BLOCK
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  - SYNTHETIC_MOCK 不得声明 BENCHMARK_GRADE；部署证据与独立托管验证缺失则 BLOCK
  dependencies:
  - W04
  - W05
  - W06
  decision_dependencies:
  - D05
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
  prerequisite_artifacts:
  - TM-01 independent custodian review before W09 starts
- id: W10
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 实现预注册统计诊断
  inputs:
  - planning/v0.2/04_EVAL_SPEC_DRAFT.yaml#statistical_protocol
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/eval/statistics.py
  - tests/eval/test_statistics.py
  deliverables:
  - family-level 校正、PSR/DSR 与适用条件下 PBO/CSCV
  tests:
  - python -m pytest -q tests/eval/test_statistics.py
  - 反例/边界验证：与独立解析/手算合成参考一致并固定 RNG
  - 反例/边界验证：全零/常数/短样本/依赖 trials/缺失失败结果 fail closed；无效特征校准不过度报显著
  acceptance_criteria:
  - 与独立解析/手算合成参考一致并固定 RNG
  - 全零/常数/短样本/依赖 trials/缺失失败结果 fail closed；无效特征校准不过度报显著
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W04
  - W05
  - W06
  decision_dependencies:
  - D04B
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
- id: W20
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 实现锁定输入的复现 runner
  inputs:
  - planning/v0.2/03_ENV_SPEC_DRAFT.yaml#version_binding
  - planning/v0.2/04_EVAL_SPEC_DRAFT.yaml#G2
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/eval/replay.py
  - tests/eval/test_replay.py
  deliverables:
  - 从 RunManifest 重建运行和产物校验
  tests:
  - python -m pytest -q tests/eval/test_replay.py
  - 反例/边界验证：同输入/seed/依赖得到容差内同结果
  - 反例/边界验证：缺 artifact、改依赖、改代码 hash、非确定输出不能通过 G2
  acceptance_criteria:
  - 同输入/seed/依赖得到容差内同结果
  - 缺 artifact、改依赖、改代码 hash、非确定输出不能通过 G2
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W04
  - W05
  - W07
  - W08
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
- id: W11
  owner_role: evaluator_custodian
  suggested_worker: independent custodian; never candidate author
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 实现 G0–G7 确定性裁决
  inputs:
  - planning/v0.2/04_EVAL_SPEC_DRAFT.yaml
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - 候选优化历史不得用于修改当前条件的 final evaluator
  - 只允许未来另行授权的受信隐藏集；本轮没有真实 hidden 数据
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/eval/gates.py
  - tests/eval/test_gates.py
  deliverables:
  - 逐门禁证据检查与签名 EvalResult
  tests:
  - python -m pytest -q tests/eval/test_gates.py
  - 反例/边界验证：每个 gate 至少正例/反例/缺证据例；不认识的 validator 不能 PASS
  - 反例/边界验证：研究行为与策略晋升分离；伪造指标/忽略失败/成本不全均被拒绝
  acceptance_criteria:
  - 每个 gate 至少正例/反例/缺证据例；不认识的 validator 不能 PASS
  - 研究行为与策略晋升分离；伪造指标/忽略失败/成本不全均被拒绝
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W09
  - W10
  - W20
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
- id: W12
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 实现可替换 worker 调用与调用溯源
  inputs:
  - planning/v0.2/05_AGENT_ORCHESTRATION_DRAFT.yaml#roles
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/agents/worker.py
  - tests/agents/test_worker.py
  deliverables:
  - 统一模型适配接口；首先使用 fake provider
  tests:
  - python -m pytest -q tests/agents/test_worker.py
  - 反例/边界验证：记录精确 model/version/prompt/tool/input/output hash 和实际用量
  - 反例/边界验证：timeout/中断/未知版本/未知 token 用量留下失败；不得依赖 real credentials 测试
  acceptance_criteria:
  - 记录精确 model/version/prompt/tool/input/output hash 和实际用量
  - timeout/中断/未知版本/未知 token 用量留下失败；不得依赖 real credentials 测试
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W04
  - W06
  decision_dependencies:
  - D07
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
- id: W13
  owner_role: critic
  suggested_worker: independent DeepSeek or GPT-6 Sol
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 实现独立 critic issue 合同与审阅入口
  inputs:
  - planning/v0.2/05_AGENT_ORCHESTRATION_DRAFT.yaml#roles
  - planning/v0.2/04_EVAL_SPEC_DRAFT.yaml#rubric
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/agents/critic.py
  - tests/agents/test_critic.py
  deliverables:
  - 只读 candidate 的 evidence-linked issues/review
  tests:
  - python -m pytest -q tests/agents/test_critic.py
  - 反例/边界验证：同一身份/上下文自审被拒绝；只能写 issues 不能修改 candidate
  - 反例/边界验证：缺 evidence 的口头认可不能过审；未解决严重 issue 阻断 admission
  acceptance_criteria:
  - 同一身份/上下文自审被拒绝；只能写 issues 不能修改 candidate
  - 缺 evidence 的口头认可不能过审；未解决严重 issue 阻断 admission
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W02
  - W04
  decision_dependencies:
  - D08
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
- id: W14
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 实现最小编排状态机
  inputs:
  - planning/v0.2/05_AGENT_ORCHESTRATION_DRAFT.yaml
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/orchestration/runner.py
  - tests/orchestration/test_runner.py
  deliverables:
  - Task→预算→worker→critic→eval→trace 的运行链
  tests:
  - python -m pytest -q tests/orchestration/test_runner.py
  - 反例/边界验证：fake provider 与合成输入 E2E 可恢复且交付幂等
  - 反例/边界验证：失败/超时/预算耗尽/critic 否决全部 terminal 记录；sealed 失败无自动优化重试
  acceptance_criteria:
  - fake provider 与合成输入 E2E 可恢复且交付幂等
  - 失败/超时/预算耗尽/critic 否决全部 terminal 记录；sealed 失败无自动优化重试
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W11
  - W12
  - W13
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
- id: W15
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 建立公开合成校准案例
  inputs:
  - planning/v0.2/04_EVAL_SPEC_DRAFT.yaml#calibration_minimum
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - tests/fixtures/public/calibration.yaml
  - tests/calibration/test_public.py
  deliverables:
  - 2 replication + 2 placebo + 2 leakage + 1 cost + 1 decay + 1 制度陷阱
  tests:
  - python -m pytest -q tests/calibration/test_public.py
  - 反例/边界验证：九例各有 frozen expected outcome、synthetic=true 与证据链
  - 反例/边界验证：坏数据必须拒绝、无 edge 不奖励高收益；九例通过不冒称有统计功效或市场有效
  acceptance_criteria:
  - 九例各有 frozen expected outcome、synthetic=true 与证据链
  - 坏数据必须拒绝、无 edge 不奖励高收益；九例通过不冒称有统计功效或市场有效
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W08
  - W10
  - W14
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 9
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
- id: W16
  owner_role: evaluator_custodian
  suggested_worker: independent custodian; never candidate author
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 建立独立隐藏校准发布流程
  inputs:
  - planning/v0.2/04_EVAL_SPEC_DRAFT.yaml#hidden_policy
  - planning/v0.2/04_EVAL_SPEC_DRAFT.yaml#task_families
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - 候选优化历史不得用于修改当前条件的 final evaluator
  - 只允许未来另行授权的受信隐藏集；本轮没有真实 hidden 数据
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/eval/hidden_release.py
  - tests/eval/test_hidden_release.py
  deliverables:
  - 受信服务生成/保存隐藏变体；仓库仅存接口与测试
  tests:
  - python -m pytest -q tests/eval/test_hidden_release.py
  - 反例/边界验证：隐藏具体值/seed/labels 不写公共工作树、日志或 worker 消息
  - 反例/边界验证：只把合成 mock 用于 CI；真实隐藏集发布需独立 custodian，污染后新版本不得沿用暴露样本
  acceptance_criteria:
  - 隐藏具体值/seed/labels 不写公共工作树、日志或 worker 消息
  - 只把合成 mock 用于 CI；真实隐藏集发布需独立 custodian，污染后新版本不得沿用暴露样本
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W09
  - W11
  - W15
  decision_dependencies:
  - D05
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 9
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 白名单不能保存真实 hidden cases；需要受信存储权限后才可发布。
- id: W17
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 实现同条件模型比较报告
  inputs:
  - planning/v0.2/04_EVAL_SPEC_DRAFT.yaml#score_vector
  - planning/v0.2/03_ENV_SPEC_DRAFT.yaml#version_binding
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/reporting/comparison.py
  - tests/reporting/test_comparison.py
  deliverables:
  - hard gates + score vector + 成本资源明细，无总分
  tests:
  - python -m pytest -q tests/reporting/test_comparison.py
  - 反例/边界验证：任一 condition/budget/data/cleaning 差异分组而非混排
  - 反例/边界验证：包含失败率、拒绝质量、分母及不确定性；不自动启动模型搜索
  acceptance_criteria:
  - 任一 condition/budget/data/cleaning 差异分组而非混排
  - 包含失败率、拒绝质量、分母及不确定性；不自动启动模型搜索
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W11
  - W14
  - W16
  decision_dependencies:
  - D06
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
- id: W18
  owner_role: implementer
  suggested_worker: GPT-6 Sol or DeepSeek
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 实现 prospective shadow 记录与退化策略
  inputs:
  - planning/v0.2/03_ENV_SPEC_DRAFT.yaml#environments.shadow
  - docs/inputs/03_HARNESS_DESIGN_PRINCIPLES.yaml#H11
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - src/quant_rsi/shadow/monitor.py
  - tests/shadow/test_monitor.py
  deliverables:
  - 前向 paper 观察、availability 链和追加式 retirement
  tests:
  - python -m pytest -q tests/shadow/test_monitor.py
  - 反例/边界验证：历史回填与未来观察严格分离；future outcomes 不提前可见
  - 反例/边界验证：模拟时钟触发冻结退化阈值并追加 demote，不覆盖原 verdict；零真实订单接口
  acceptance_criteria:
  - 历史回填与未来观察严格分离；future outcomes 不提前可见
  - 模拟时钟触发冻结退化阈值并追加 demote，不覆盖原 verdict；零真实订单接口
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W05
  - W07
  - W08
  - W11
  decision_dependencies:
  - D09
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 所有数字为实施预算提案，不是已消耗统计或模型性能事实。
- id: W19
  owner_role: critic
  suggested_worker: independent DeepSeek or GPT-6 Sol
  status: NOT_STARTED
  dispatch_authorization: NOT_GRANTED_THIS_ROUND
  objective: 独立审查 MVP 运行与验收证据
  inputs:
  - 全部已完成 work item 的签名产物及测试记录
  - docs/inputs/02_ASTRA_MASTER_TASKBOOK.md#15
  forbidden_inputs:
  - 任何其他项目的代码、schema、运行结果或历史研究
  - 未获准的市场数据、网络来源、凭据和 live order 接口
  - sealed 数据、标签、隐藏测试与未来 shadow outcomes
  - 未冻结或被污染条件下的绩效反馈
  files_allowed_to_modify:
  - reviews/mvp_acceptance.yaml
  - tests/acceptance/test_release_gate.py
  deliverables:
  - 独立 issue 清单与逐条 DoD 审核结论
  tests:
  - python -m pytest -q tests/acceptance/test_release_gate.py
  - 反例/边界验证：任何缺 artifact+test、未解决 P0、污染 OOS 或预算不完整均 BLOCK
  - 反例/边界验证：不允许审阅者改实现或自审；审查不是批准实盘，也不代替未来 shadow 证据
  acceptance_criteria:
  - 任何缺 artifact+test、未解决 P0、污染 OOS 或预算不完整均 BLOCK
  - 不允许审阅者改实现或自审；审查不是批准实盘，也不代替未来 shadow 证据
  - 仅白名单 diff；附 artifact hashes、测试命令/exit code、失败记录及独立审阅引用
  dependencies:
  - W17
  - W18
  decision_dependencies: []
  max_retries: 2
  search_budget:
    status: PROPOSED_REQUIRES_FREEZE
    scope: total_per_work_item_including_all_retries
    engineering_attempts: 3
    scientific_candidate_trials: 0
    parameter_searches: 0
    prompt_search_variants: 0
    external_web_queries: 0
    sealed_submissions: 0
    synthetic_fixture_variants: 0
    max_test_invocations: 6
    max_total_tokens: 120000
    max_wall_seconds: 14400
    max_cpu_seconds: 7200
    max_memory_mb: 4096
    on_exhaustion: STOP_AND_APPEND_BLOCKED_NO_AUTO_EXTENSION
  failure_policy: 保留每次失败；issue→patch→test；2 次修复后停止，禁止另建 family 洗掉失败
  notes: 与待验收实现作者分离；此 work item 未在本轮执行。

```


Stage A.1 hotfix authorization is recorded separately in `planning/stage_a1_plan.yaml`. It changes only necessary W01–W06 contracts/ledger/tests and planning references; W07–W20 remain NOT_STARTED. Existing task file lists above are retained rather than silently widening their original scope.


Stage B1 更新：本文件保留 v0.2 原始任务白名单与历史授权状态。当前 W07/W08/W20 授权、W09 TM-01 条件授权和执行状态以 `planning/stage_b1_plan.yaml` 为准；W10/W11–W19 仍未授权。
