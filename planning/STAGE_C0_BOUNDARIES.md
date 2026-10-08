# Stage C0 boundaries and evidence precedence

Authority: `artifacts/stage_c0/authorized_request.txt`. This stage freezes a
reviewable **design proposal**, not benchmark tasks, data, thresholds, hidden
cases, or runtime. The project remains independent of other repositories.

Historical Stage A/A.1/B1/B2 artifacts and acceptance reports are immutable.
Intermediate artifacts remain as recorded. An independent critic resolution
may supersede an earlier review status; the corresponding stage acceptance
report is the final status entry. In particular,
`artifacts/stage_b2/acceptance_evidence_map.yaml` says
`PENDING_INDEPENDENT_CODE_CRITIC` because it is a pre-review snapshot. B2's
current accepted synthetic status is in `artifacts/stage_b2/critic_resolution.md`
and `stage_b2_acceptance.yaml`; neither historical file is changed here.

Benchmark v0.1 is a proposed closed-data, A-share ordinary-stock, daily-frequency
Research Agent capability benchmark. Public development and calibration results
cannot become formal comparison scores. Hidden evaluation requires an independent
custodian and infrastructure beyond the B2 mock. No real provider, empirical
research, strategy search, model comparison, hidden execution, or live trading
is authorized. W10B and W15–W19 are untouched.

Object ownership: TaskContract owns target, horizon, benchmark, universe,
clock, version keys and executable limits; BenchmarkCondition owns the frozen
comparison hash; DataSpec/SnapshotManifest own data and PIT facts;
SearchBudget/ResearchTrace own attempts and usage; AgentBenchmarkRun owns its
capability budget root; ScientificSearchFamily owns final scientific-claim
selection history; EvalResult/evaluator own gate outcomes. BenchmarkTaskSpec is
design metadata and references these owners. It cannot itself grant execution,
rewrite gates, create data facts, reset a budget, or declare a sealed asset.

`SnapshotManifest` today has only snapshot ID, DataSpec and file hashes;
`TaskContract.split_version` is a version binding, not concrete partition
membership. `TaskContract` has no public-prompt field, and
`BenchmarkCondition.condition_hash` hashes TaskContract only. Future
BenchmarkReleaseManifest, BenchmarkPartitionManifest, CustodianHiddenPackManifest
and BenchmarkComparisonManifest own those additional handles/digests and must
be implemented and signed before official comparison. The ownership map in
`benchmark/BENCHMARK_TASK_SCHEMA.yaml` marks these refs as future and its
example as not loadable today. This keeps existing Task/Data/Eval facts with
their canonical owners.

Proposed comparisons require identical Task/Data/Cleaning/Env/Eval and budget
policy and separate per-model AgentBenchmarkRuns. Jointly selected strategy
claims may pool ScientificSearchFamily ancestry without penalizing another
model's agent capability score. Exact numeric limits, statistical thresholds,
data windows and hidden examples remain proposals until separately frozen.

P0/P1 design-critic findings must close before C0 acceptance. Closure requires
the concrete changed artifact, reason and a fresh independent resolution note.
The stage stops at `stage_c0_acceptance.yaml`; all follow-on implementation or
calibration needs a new authorization.
